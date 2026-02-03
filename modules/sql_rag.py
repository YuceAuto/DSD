# modules/sql_rag.py
import os, glob, sqlite3, hashlib, re
from dataclasses import dataclass
from typing import List, Optional

DEFAULT_DB = os.getenv("SQL_RAG_DB", os.path.join(os.getcwd(), "data", "sql_rag.db"))

@dataclass
class RetrievedChunk:
    id: int
    doc_path: str
    title: str
    section: str
    text: str
    fts_score: float

class SQLRAG:
    """
    *.sql.md dosyalarından RAG.  (FTS5 tabanlı; istenirse vektör desteği eklenebilir.)
    """
    def __init__(self, kb_glob: str, db_path: str = DEFAULT_DB, top_k: int = 6):
        self.kb_glob = kb_glob
        self.db_path = db_path
        self.top_k = int(os.getenv("SQL_RAG_TOPK", top_k))
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    # --- DB bootstrap ---------------------------------------------------------
    def _conn(self):
        con = sqlite3.connect(self.db_path)
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        return con

    def _init_db(self):
        with self._conn() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE,
                title TEXT,
                mtime REAL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                doc_id INTEGER NOT NULL,
                ord INTEGER NOT NULL,
                section TEXT,
                text TEXT NOT NULL,
                sha TEXT UNIQUE,
                FOREIGN KEY(doc_id) REFERENCES documents(id)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(
                text, 
                content='chunks', 
                content_rowid='id', 
                tokenize='unicode61'
            );
            """)
            # ileri kullanım için (vektörler)
            con.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    chunk_id INTEGER PRIMARY KEY,
                    vector BLOB
                );
            """)

    # --- Index build/update ---------------------------------------------------
    def build_or_update_index(self, force: bool = False):
        paths = sorted(glob.glob(self.kb_glob, recursive=True))
        with self._conn() as con:
            for p in paths:
                if not os.path.isfile(p):
                    continue
                mtime = os.path.getmtime(p)
                row = con.execute("SELECT id, mtime FROM documents WHERE path=?", (p,)).fetchone()
                if row and not force and mtime <= (row[1] or 0):
                    continue  # güncel
                title = os.path.basename(p)
                if row:
                    doc_id = row[0]
                    con.execute("UPDATE documents SET title=?, mtime=? WHERE id=?", (title, mtime, doc_id))
                    con.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
                    con.execute("DELETE FROM chunks_fts WHERE rowid NOT IN (SELECT id FROM chunks)")
                    con.execute("DELETE FROM embeddings WHERE chunk_id NOT IN (SELECT id FROM chunks)")
                else:
                    cur = con.execute("INSERT INTO documents(path, title, mtime) VALUES(?,?,?)", (p, title, mtime))
                    doc_id = cur.lastrowid

                with open(p, "r", encoding="utf-8") as f:
                    raw = f.read()

                for ord_i, (section, text) in enumerate(self._chunk_sql_md(raw), start=1):
                    sha = hashlib.sha1((p + "|" + section + "|" + text).encode("utf-8")).hexdigest()
                    cur = con.execute(
                        "INSERT INTO chunks(doc_id, ord, section, text, sha) VALUES (?,?,?,?,?)",
                        (doc_id, ord_i, section, text, sha)
                    )
                    con.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?,?)", (cur.lastrowid, text))

            con.execute("DELETE FROM chunks_fts WHERE rowid NOT IN (SELECT id FROM chunks)")
            con.execute("VACUUM")

    def _chunk_sql_md(self, text: str):
        """
        Başlıklar (##/###) ve ```sql kod blokları korunarak chunk’lanır.
        """
        section = "Genel"
        buf = []
        MAX_CHARS = int(os.getenv("SQL_RAG_CHUNK_CHARS", "1800"))

        def flush():
            nonlocal buf
            if not buf: 
                return
            blob = "\n".join(buf).strip()
            if not blob:
                buf = []
                return
            # boyutu aşarsa son kısmı alın (güncel bağlamı korumak için)
            if len(blob) > MAX_CHARS:
                blob = blob[-MAX_CHARS:]
            yield (section, blob)
            buf = []

        in_code = False
        fence_lang = None

        for line in text.splitlines():
            # başlık
            if re.match(r"^#{1,6}\s+", line) and not in_code:
                yield from flush()
                section = re.sub(r"^#{1,6}\s+", "", line).strip() or "Bölüm"
                continue

            # code fence tespiti
            if line.strip().startswith("```"):
                lang = line.strip().strip("`").lower().replace(" ", "")
                if not in_code:
                    in_code = True
                    fence_lang = lang or ""
                else:
                    in_code = False
                    fence_lang = None
                buf.append(line)
                continue

            buf.append(line)

            if sum(len(x) for x in buf) >= MAX_CHARS and not in_code:
                yield from flush()

        yield from flush()

    # --- Retrieval ------------------------------------------------------------
    def search(self, query: str, limit: Optional[int] = None) -> List[RetrievedChunk]:
        k = limit or self.top_k
        q = (query or "").strip()
        if not q:
            return []
        with self._conn() as con:
            rows = con.execute("""
                SELECT c.id, d.path, d.title, c.section, c.text,
                       bm25(chunks_fts) AS rank
                FROM chunks_fts 
                JOIN chunks c ON c.id = chunks_fts.rowid
                JOIN documents d ON d.id = c.doc_id
                WHERE chunks_fts MATCH ?
                ORDER BY rank LIMIT ?
            """, (q, max(k*3, k))).fetchall()

            # BM25'te küçük 'rank' daha iyi; 0..1 skoruna çevir (yüksek daha iyi)
            if not rows:
                # naive fallback
                rows = con.execute("""
                    SELECT c.id, d.path, d.title, c.section, c.text, 0.0 AS rank
                    FROM chunks c JOIN documents d ON d.id=c.doc_id
                    WHERE c.text LIKE ? LIMIT ?
                """, (f"%{q}%", k)).fetchall()

            ranks = [r[5] for r in rows]
            if ranks:
                rmin, rmax = min(ranks), max(ranks)
                def norm(r): 
                    return 1.0 if rmax == rmin else 1.0 - ((r - rmin) / (rmax - rmin))
            else:
                def norm(_): return 0.5

            out: List[RetrievedChunk] = []
            for r in rows[:k]:
                out.append(RetrievedChunk(
                    id=r[0], doc_path=r[1], title=r[2], section=r[3], text=r[4],
                    fts_score=norm(r[5])
                ))
            return out

    def as_context(self, query: str, limit: Optional[int] = None) -> str:
        chunks = self.search(query, limit=limit)
        if not chunks:
            return ""
        blocks = []
        for i, ch in enumerate(chunks, 1):
            header = f"[Kaynak {i}] {os.path.basename(ch.doc_path)} ▸ {ch.section}"
            blocks.append(f"{header}\n\n{ch.text}\n")
        return "\n\n---\n\n".join(blocks)
