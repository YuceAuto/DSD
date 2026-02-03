# modules/neo4j_skoda_rag.py
from __future__ import annotations

import os
import re
from typing import List, Tuple, Optional

try:
    from neo4j import GraphDatabase
except Exception:
    GraphDatabase = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


class Neo4jSkodaRAG:
    """
    ChatbotAPI içinde kullanılan eski isim ile uyumluluk katmanı.
    - chatbot.py: self.neo4j_rag.enabled
    - chatbot.py: self.neo4j_rag.answer(question, chat_history=[...])
    - chatbot.py: self.neo4j_rag.ingest_skoda_kb_markdown(path)
    """

    def __init__(
        self,
        *,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        openai_api_key: str,
        enabled: bool = True,
        neo4j_db: str | None = None,
    ):
        self.NEO4J_DB = neo4j_db or os.getenv("NEO4J_DB", "neo4j")
        self.embed_model = os.getenv("EMBED_MODEL", "text-embedding-3-large")
        self.top_k = int(os.getenv("NEO4J_RAG_TOP_K", "5"))
        self.vector_index = os.getenv("NEO4J_VECTOR_INDEX", "skoda_chunks_vec")
        self.fulltext_index = os.getenv("NEO4J_FULLTEXT_INDEX", "skoda_chunks_ft")

        self.enabled = bool(enabled)

        # Kütüphane yoksa otomatik kapat
        if GraphDatabase is None or OpenAI is None:
            self.enabled = False

        # API key yoksa kapat
        if not (openai_api_key or "").strip():
            self.enabled = False

        self._driver = None
        self._client = None

        if self.enabled:
            # Bağlantı dene (hata olursa da kapat)
            try:
                self._driver = GraphDatabase.driver(
                    neo4j_uri,
                    auth=(neo4j_user, neo4j_password),
                )
                # hızlı ping
                with self._driver.session(database=self.NEO4J_DB) as s:
                    s.run("RETURN 1").consume()

                self._client = OpenAI(api_key=openai_api_key)
            except Exception:
                self.enabled = False
                try:
                    if self._driver:
                        self._driver.close()
                except Exception:
                    pass
                self._driver = None
                self._client = None

    def close(self):
        try:
            if self._driver:
                self._driver.close()
        except Exception:
            pass

    # ---------------------------
    # Ingest (opsiyonel)
    # ---------------------------
    def ingest_skoda_kb_markdown(self, md_path: str, *, reset: bool = False) -> bool:
        """
        İstersen KB'yi Neo4j'e chunk olarak basar.
        Neo4j tarafında vector index destekliyorsa vector index de kurmayı dener.
        Desteklemiyorsa fulltext ile çalışır.
        """
        if not self.enabled or not md_path or not os.path.exists(md_path):
            return False

        text = ""
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()

        chunks = self._chunk_text(text, chunk_chars=1200, overlap=150)
        if not chunks:
            return False

        with self._driver.session(database=self.NEO4J_DB) as s:
            if reset:
                s.run("MATCH (c:SkodaChunk) DETACH DELETE c").consume()

            # Fulltext index (her Neo4j sürümünde genelde var)
            try:
                s.run(
                    f"CREATE FULLTEXT INDEX {self.fulltext_index} IF NOT EXISTS "
                    f"FOR (c:SkodaChunk) ON EACH [c.text]"
                ).consume()
            except Exception:
                pass

            # Embedding + upsert
            for i, ch in enumerate(chunks):
                emb = self._embed(ch)
                s.run(
                    """
                    MERGE (c:SkodaChunk {id: $id})
                    SET c.text = $text,
                        c.embedding = $emb
                    """,
                    id=f"chunk_{i}",
                    text=ch,
                    emb=emb,
                ).consume()

            # Vector index dene (Neo4j 5.11+)
            try:
                dim = len(self._embed("test"))
                s.run(
                    f"CREATE VECTOR INDEX {self.vector_index} IF NOT EXISTS "
                    f"FOR (c:SkodaChunk) ON (c.embedding) "
                    f"OPTIONS {{ indexConfig: {{ `vector.dimensions`: {dim}, `vector.similarity_function`: 'cosine' }} }}"
                ).consume()
            except Exception:
                # Vector index yoksa sorun değil (fulltext fallback var)
                pass

        return True

    # ---------------------------
    # Answer
    # ---------------------------
    def answer(self, question: str, chat_history: Optional[List[Tuple[str, str]]] = None) -> str:
        if not self.enabled or not question:
            return ""

        ctx_chunks = self._retrieve(question, k=self.top_k)
        if not ctx_chunks:
            return ""

        history_txt = ""
        if chat_history:
            # son 1-2 tur yeter
            hh = chat_history[-2:]
            history_txt = "\n".join([f"Q: {q}\nA: {a}" for q, a in hh])

        system = (
            "Sen Škoda Türkiye dijital satış danışmanısın.\n"
            "Kurallar:\n"
            "- SADECE verilen bağlamdan cevap ver.\n"
            "- Bağlamda yoksa: 'Bu bilgi Neo4j KB’de yok.' de.\n"
            "- Uydurma sayı/özellik yazma.\n"
            "- 2–6 cümle.\n"
        )
        user = (
            f"Önceki konuşma (varsa):\n{history_txt}\n\n"
            f"Bağlam:\n" + "\n\n".join([f"- {c}" for c in ctx_chunks]) + "\n\n"
            f"Soru: {question}"
        )

        try:
            resp = self._client.chat.completions.create(
                model=os.getenv("GEN_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=300,
            )
            out = (resp.choices[0].message.content or "").strip()
            return out
        except Exception:
            return ""

    # ---------------------------
    # Internal helpers
    # ---------------------------
    def _embed(self, text: str) -> List[float]:
        text = (text or "").strip()
        if not text:
            return []
        em = self._client.embeddings.create(model=self.embed_model, input=text)
        return list(em.data[0].embedding)

    def _retrieve(self, query: str, k: int = 5) -> List[str]:
        emb = self._embed(query)
        if not emb:
            return []

        with self._driver.session(database=self.NEO4J_DB) as s:
            # 1) Vector index varsa onu dene
            try:
                res = s.run(
                    f"""
                    CALL db.index.vector.queryNodes($index, $k, $emb)
                    YIELD node, score
                    RETURN node.text AS text, score
                    ORDER BY score DESC
                    LIMIT $k
                    """,
                    index=self.vector_index,
                    k=int(k),
                    emb=emb,
                )
                rows = [r["text"] for r in res if (r.get("text") or "").strip()]
                if rows:
                    return rows
            except Exception:
                pass

            # 2) Fulltext fallback
            try:
                q = self._sanitize_fulltext(query)
                res = s.run(
                    f"""
                    CALL db.index.fulltext.queryNodes($index, $q)
                    YIELD node, score
                    RETURN node.text AS text, score
                    ORDER BY score DESC
                    LIMIT $k
                    """,
                    index=self.fulltext_index,
                    q=q,
                    k=int(k),
                )
                return [r["text"] for r in res if (r.get("text") or "").strip()]
            except Exception:
                return []

    def _sanitize_fulltext(self, s: str) -> str:
        s = (s or "").lower()
        s = re.sub(r"[^0-9a-zçğıöşü\s]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _chunk_text(self, text: str, *, chunk_chars: int = 1200, overlap: int = 150) -> List[str]:
        t = (text or "").strip()
        if not t:
            return []
        t = re.sub(r"\n{3,}", "\n\n", t)

        chunks = []
        i = 0
        while i < len(t):
            j = min(len(t), i + chunk_chars)
            ch = t[i:j].strip()
            if ch:
                chunks.append(ch)
            if j >= len(t):
                break
            i = max(0, j - overlap)
        return chunks
