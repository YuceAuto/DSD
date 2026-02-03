# -*- coding: utf-8 -*-
import os, re, sys, json, hashlib, argparse
from pathlib import Path
import pyodbc
# --- ELROQ yapılandırılmış aktarım yardımcıları -----------------------------
import re, json
from modules.data.elroq_data import ELROQ_DATA_MD
def _md_table_to_rows(md_text: str):
    lines = [ln for ln in md_text.splitlines() if ln.strip()]
    # basit md tablo seçimi
    if not any('|' in ln for ln in lines):
        return None, None
    # başlık + ayırıcıyı bul
    header, sep_idx = None, None
    for i, ln in enumerate(lines):
        if ln.strip().startswith('|') and ln.strip().endswith('|'):
            # ayırıcı var mı?
            if i+1 < len(lines) and re.match(r'^\s*\|(?:\s*:?-+:?\s*\|)+\s*$', lines[i+1]):
                header = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                sep_idx = i+1
                break
    if not header:
        return None, None
    rows = []
    for ln in lines[sep_idx+1:]:
        if not (ln.strip().startswith('|') and ln.strip().endswith('|')):
            break
        cells = [c.strip() for c in ln.strip().strip('|').split('|')]
        rows.append(cells)
    return header, rows

def _parse_money_tr(val: str):
    if val is None: return None
    s = val.replace('.', '').replace('\u00A0',' ').replace(' ', '').replace(',', '.')
    s = re.sub(r'[^\d\.\-]', '', s)
    try:
        return float(s)
    except:
        return None

def load_elroq_structured_to_db(conn, doc_id: int, md: str):
    """
    ELROQ_DATA_MD içeriğini kb.PriceItem, kb.FeatureItem, kb.SpecItem,
    kb.ColorItem, kb.WheelItem tablolarına yazar.
    """
    cur = conn.cursor()
    model = "Elroq"
    trim  = "e-Prestige"

    # ---------------- Opsiyon Fiyatları ----------------
    m = re.search(r'##\s*e.?Prestige\s*—\s*Opsiyonel Donanımlar.*?\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        tbl = m.group(1)
        hdr, rows = _md_table_to_rows(tbl)
        if hdr and rows:
            nh = [re.sub(r'\s+',' ', h).lower() for h in hdr]
            try:
                idx_code = nh.index('kod')
                idx_desc = nh.index('açıklama') if 'açıklama' in nh else nh.index('aciklama')
            except ValueError:
                idx_code = idx_desc = None
            idx_net = None
            for i,h in enumerate(nh):
                if 'net satış' in h or 'net satis' in h:
                    idx_net = i
                    break
            idx_25 = None
            for i,h in enumerate(nh):
                if '%25' in h or '25' in h:
                    idx_25 = i
                    break
            if idx_code is not None and idx_desc is not None:
                for r in rows:
                    code = r[idx_code].strip() if idx_code < len(r) else None
                    desc = r[idx_desc].strip() if idx_desc < len(r) else None
                    net  = _parse_money_tr(r[idx_net]) if idx_net is not None and idx_net < len(r) else None
                    at25 = _parse_money_tr(r[idx_25]) if idx_25 is not None and idx_25 < len(r) else None
                    if code:
                        # MERGE gibi davran: yoksa ekle
                        cur.execute("""
                        IF NOT EXISTS(
                            SELECT 1 FROM kb.PriceItem WHERE model_name=? AND ISNULL(trim_name,'')=ISNULL(?, '') AND code=?
                        )
                            INSERT INTO kb.PriceItem(doc_id, model_name, trim_name, code, description, price_net, price_at_25)
                            VALUES (?,?,?,?,?,?,?);
                        """, (model, trim, code, doc_id, model, trim, code, desc, net, at25))

    # ---------------- Donanım Listesi (Kategori→Özellik→Durum) -------------
    # Güvenlik / Konfor & Teknoloji / Tasarım başlıkları altındaki tablolar
    for cat in [r'Güvenlik', r'Konfor\s*&\s*Teknoloji', r'Tasarım']:
        p = re.compile(rf'###\s*{cat}\s*\n\n([\s\S]+?)(?:\n\n---|\Z)', re.IGNORECASE)
        m = p.search(md)
        if not m:
            continue
        tbl = m.group(1)
        hdr, rows = _md_table_to_rows(tbl)
        if hdr and rows:
            # genelde "Özellik | e-Prestige"
            for r in rows:
                feat = (r[0] if len(r)>0 else "").strip()
                stat = (r[1] if len(r)>1 else "").strip()
                if not feat:
                    continue
                # durum normalize
                st = "Standart" if re.search(r'^(s|standart)', stat, re.IGNORECASE) else ("Opsiyonel" if 'ops' in stat.lower() else stat)
                cur.execute("""
                    INSERT INTO kb.FeatureItem(doc_id, model_name, trim_name, category, feature, status)
                    VALUES (?,?,?,?,?,?)
                """, (doc_id, model, trim, re.sub(r'\s+',' ', cat.replace('\\','')), feat, st or None))

    # ---------------- Döşeme (madde listesi) -------------------------------
    m = re.search(r'##\s*DÖŞEME\s*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        blob = m.group(1)
        for ln in blob.splitlines():
            ln = ln.strip()
            if ln.startswith('- '):
                feat = re.sub(r'^-\s*', '', ln)
                cur.execute("""
                    INSERT INTO kb.FeatureItem(doc_id, model_name, trim_name, category, feature, status)
                    VALUES (?,?,?,?,?,?)
                """, (doc_id, model, trim, 'Döşeme', feat, 'Standart'))

    # ---------------- Jant Seçenekleri (madde listesi) ----------------------
    m = re.search(r'##\s*JANT SEÇENEKLERİ\s*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        for ln in m.group(1).splitlines():
            ln = ln.strip()
            if ln.startswith('- '):
                txt = re.sub(r'^-\s*', '', ln)
                avail = 'Standart' if 'Standart' in txt else ('Opsiyonel' if 'Opsiyonel' in txt else None)
                cur.execute("""
                    INSERT INTO kb.WheelItem(doc_id, model_name, trim_name, wheel_desc, availability)
                    VALUES (?,?,?,?,?)
                """, (doc_id, model, trim, txt, avail))

    # ---------------- Renk Seçenekleri (grup başlıklarına göre) ------------
    m = re.search(r'##\s*RENK SEÇENEKLERİ\s*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        block = m.group(1)
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            # "Exclusive: Kadife Kırmızı (K1K1)"
            m2 = re.match(r'^\*\*(.+?)\:\*\*\s*(.+)$', line)
            if m2:
                grp = m2.group(1).strip()
                rest = m2.group(2).strip()
                # Ay Beyazı (2Y2Y), Yarış Mavisi (8X8X) ...
                for token in re.split(r'\s{2,}|,\s*', rest):
                    token = token.strip().strip(',')
                    if not token: continue
                    name = token
                    code = None
                    m3 = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', token)
                    if m3:
                        name = m3.group(1).strip()
                        code = m3.group(2).strip()
                    cur.execute("""
                        INSERT INTO kb.ColorItem(doc_id, model_name, color_group, color_name, color_code, availability)
                        VALUES (?,?,?,?,?,?)
                    """, (doc_id, model, grp, name, code, None))

    # ---------------- Multimedya/Gösterge/Direksiyon (madde listesi) -------
    m = re.search(r'##\s*Multimedya.*Direksiyon.*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        for ln in m.group(1).splitlines():
            ln = ln.strip()
            if ln.startswith('- '):
                feat = re.sub(r'^-\s*', '', ln)
                cur.execute("""
                    INSERT INTO kb.FeatureItem(doc_id, model_name, trim_name, category, feature, status)
                    VALUES (?,?,?,?,?,?)
                """, (doc_id, model, trim, 'Multimedya/Gösterge/Direksiyon', feat, 'Standart'))

    # ---------------- Teknik Veriler (Özellik | Değer) ----------------------
    m = re.search(r'##\s*Teknik Veriler\s*—\s*ELROQ.*?\n\n([\s\S]+?)\n\n', md, re.IGNORECASE)
    if m:
        hdr, rows = _md_table_to_rows(m.group(1))
        if hdr and rows:
            for r in rows:
                if len(r) < 2: 
                    continue
                key = r[0].strip()
                val = r[1].strip()
                unit = None
                # basit ünite saptama
                if re.search(r'\b(km/s|km/h|kwh|kw|ps|nm|kg|mm|m)\b', val.lower()):
                    unit = None  # zaten değerin içinde; isterseniz ayrıştırırız
                cur.execute("""
                    INSERT INTO kb.SpecItem(doc_id, model_name, trim_name, spec_key, spec_value, unit)
                    VALUES (?,?,?,?,?,?)
                """, (doc_id, model, trim, key, val, unit))

    cur.close()
    conn.commit()

def get_conn():
        # Önce uygulamanın kendi DB bağlantısını dene
    try:
        # repo-root'u ortamdan alın (komut satırında vereceğiz)
        repo_root = os.getenv("URUNBOT_REPO_ROOT")
        if repo_root:
            sys.path.insert(0, repo_root)
        from modules.db import get_db_connection
        return get_db_connection()   # sizin çalışan bağlantınız
    except Exception:
        # Olmazsa MSSQL_CONN_STR dene
        conn_str = os.getenv("MSSQL_CONN_STR")
        if not conn_str:
            raise RuntimeError("DB bağlantısı kurulamadı. get_db_connection() veya MSSQL_CONN_STR gerekiyor.")
        import pyodbc
        return pyodbc.connect(conn_str)
    
def sha256_bytes(text: str) -> bytes:
    return hashlib.sha256((text or '').encode('utf-8','ignore')).digest()

def guess_model_from_name(name: str) -> str:
    n = name.lower()
    for model in ['octavia','enyaq','elroq','karoq','kodiaq','fabia','kamiq','scala','superb']:
        if model in n: return model.capitalize()
    return None

def turkish_number_to_decimal(s: str):
    if s is None: return None
    s = str(s).strip()
    if not s: return None
    s = s.replace('.', '').replace(' ', '').replace('\u00A0','').replace(',', '.')
    s = re.sub(r'[^\d\.\-]', '', s)
    if s in ('','.', '-', '.-'): return None
    try: return float(s)
    except: return None

MD_BLOCK_VAR_RE = re.compile(r'(?P<name>[A-Z0-9_]+_MD)\s*=\s*(?P<quote>"""|\'\'\')(.*?)(?P=quote)', re.DOTALL)

TABLE_HEADER_RE = re.compile(r'^\s*\|.+\|\s*$', re.MULTILINE)
TABLE_SEP_RE    = re.compile(r'^\s*\|(?:\s*:?-+:?\s*\|)+\s*$', re.MULTILINE)

def yield_markdown_tables(lines):
    i, n = 0, len(lines)
    while i < n:
        if TABLE_HEADER_RE.match(lines[i]) and i+1 < n and TABLE_SEP_RE.match(lines[i+1]):
            header = [c.strip() for c in lines[i].strip().strip('|').split('|')]
            i += 2
            rows = []
            while i < n and TABLE_HEADER_RE.match(lines[i]):
                row = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                rows.append(row); i += 1
            yield header, rows
        else:
            i += 1

def split_chunks(text: str, max_chars=1200, overlap=180):
    text = text.replace('\r\n','\n')
    lines = text.split('\n')
    h2 = h3 = None; buf = []; chars = 0; ord_no = 0
    def flush():
        nonlocal buf, chars, ord_no
        if not buf: return None
        content = '\n'.join(buf).strip()
        if not content: buf=[]; chars=0; return None
        ord_no += 1; out=(ord_no,h2,h3,content,content); buf=[]; chars=0; return out

    for raw in lines:
        if raw.startswith('## '):
            rec = flush(); 
            if rec: yield rec
            h2 = raw[3:].strip(); h3 = None
        elif raw.startswith('### '):
            rec = flush()
            if rec: yield rec
            h3 = raw[4:].strip()
        else:
            if chars >= max_chars:
                rec = flush()
                if rec: yield rec
            buf.append(raw); chars += len(raw)+1
    rec = flush()
    if rec: yield rec

def upsert_document(conn, source_path, source_type, model_name, trim_name, title, version_tag, content_text):
    cur = conn.cursor()
    h = sha256_bytes(content_text or "")
    cur.execute("""
        INSERT INTO kb.Document
            (source_path, source_type, model_name, trim_name, title, version_tag, content_hash)
        OUTPUT INSERTED.doc_id
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (source_path, source_type, model_name, trim_name, title, version_tag, pyodbc.Binary(h)))
    new_id = int(cur.fetchone()[0])
    cur.close()
    return new_id
def insert_chunks(conn, doc_id, chunks):
    cur = conn.cursor()
    for ord_no, h2, h3, content, content_txt in chunks:
        cur.execute("""
            INSERT INTO kb.Chunk(doc_id,ord,section_h2,section_h3,content,content_txt,tokens_guess)
            VALUES (?,?,?,?,?,?,?)
        """, (doc_id, ord_no, h2, h3, content, content_txt, None))
    cur.close()

def insert_table_registry(conn, doc_id, section_h2, title, col_schema, row_count):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO kb.TableRegistry
            (doc_id, section_h2, title, col_schema, row_count)
        OUTPUT INSERTED.table_id
        VALUES (?, ?, ?, ?, ?)
    """, (doc_id, section_h2, title, json.dumps(col_schema, ensure_ascii=False), row_count))
    tid = int(cur.fetchone()[0])
    cur.close()
    return tid
def insert_table_rows(conn, table_id, header, rows):
    cur = conn.cursor()
    for rn, row in enumerate(rows, start=1):
        for col, val in zip(header, row):
            cur.execute("""
                INSERT INTO kb.TableRow(table_id,row_no,col_name,col_value) VALUES (?,?,?,?)
            """, (table_id, rn, col, val))
    cur.close()

def try_insert_optionitems(conn, model_name, h2, doc_id, header, rows):
    normalized_headers = [h.lower() for h in header]
    try:
        idx_code = next(i for i,h in enumerate(normalized_headers) if 'kod' in h)
        idx_desc = next(i for i,h in enumerate(normalized_headers) if 'açıklama' in h or 'aciklama' in h)
    except StopIteration:
        return 0

    def find_idx(name):
        for i,h in enumerate(normalized_headers):
            if name in h:
                return i
        return None

    idx_net  = find_idx('net')
    idx_at80 = find_idx('%80') or find_idx('80')
    idx_at90 = find_idx('%90') or find_idx('90')

    sql_merge = """
    MERGE kb.OptionItem AS tgt
    USING (SELECT ? AS model_name, ? AS trim_name, ? AS code) AS src
      ON (tgt.model_name = src.model_name
          AND ISNULL(tgt.trim_name,'') = ISNULL(src.trim_name,'')
          AND tgt.code = src.code)
    WHEN NOT MATCHED THEN
      INSERT (model_name, trim_name, code, description, price_net, price_at_80, price_at_90, doc_id)
      VALUES (src.model_name, src.trim_name, src.code, ?, ?, ?, ?, ?);
    """

    cur = conn.cursor()
    count = 0
    for row in rows:
        code = row[idx_code].strip() if idx_code < len(row) else None
        desc = row[idx_desc].strip() if idx_desc < len(row) else None

        def to_num(idx):
            if idx is None or idx >= len(row): return None
            return turkish_number_to_decimal(row[idx])

        net  = to_num(idx_net)
        at80 = to_num(idx_at80)
        at90 = to_num(idx_at90)

        if not code:
            continue

        # Parametre sayısı: 3 (src) + 5 (insert) = 8 ✔️
        cur.execute(sql_merge, (model_name or '', h2 or '', code, desc, net, at80, at90, doc_id))
        count += 1

    cur.close()
    return count


def process_markdown_doc(conn, path: Path):
    text = path.read_text(encoding='utf-8', errors='ignore')
    model = guess_model_from_name(path.name)
    title = None
    m = re.search(r'^\s*#\s*(.+)$', text, re.MULTILINE)
    if m: title = m.group(1).strip()
    doc_id = upsert_document(conn, str(path).replace('\\','/'), 'markdown', model, None, title, None, text)
    chunks = list(split_chunks(text)); insert_chunks(conn, doc_id, chunks)
    lines = text.splitlines()
    for header, rows in yield_markdown_tables(lines):
        table_id = insert_table_registry(conn, doc_id, None, None, header, len(rows))
        insert_table_rows(conn, table_id, header, rows)
        if model: try_insert_optionitems(conn, model, None, doc_id, header, rows)

def process_python_md_doc(conn, path: Path):
    text = path.read_text(encoding='utf-8', errors='ignore')
    model = guess_model_from_name(path.name)
    for m in re.finditer(r'([A-Z0-9_]+_MD)\s*=\s*("""|\'\'\')(.*?)(\2)', text, re.DOTALL):
        const_name, content = m.group(1), m.group(3)
        title = None
        m1 = re.search(r'^\s*#\s*(.+)$', content, re.MULTILINE)
        if m1: title = m1.group(1).strip()
        source = f"{str(path).replace('\\','/')}::{const_name}"
        doc_id = upsert_document(conn, source, 'python_md', model, None, title, None, content)
        chunks = list(split_chunks(content)); insert_chunks(conn, doc_id, chunks)
        lines = content.splitlines()
        for header, rows in yield_markdown_tables(lines):
            table_id = insert_table_registry(conn, doc_id, None, None, header, len(rows))
            insert_table_rows(conn, table_id, header, rows)
            if model: try_insert_optionitems(conn, model, None, doc_id, header, rows)

def run(repo_root: str, drop_and_recreate: bool=False):
    repo = Path(repo_root)
    md_dir = repo / 'static' / 'kb'
    py_data_dir = repo / 'modules' / 'data'
    conn = get_conn()
    cur = conn.cursor()
    if drop_and_recreate:
        cur.execute('DELETE FROM kb.Document;'); conn.commit()
    cur.close()
    total = 0
    if md_dir.exists():
        for p in sorted(md_dir.glob('*.md')):
            print('[MD]', p.name); process_markdown_doc(conn, p); conn.commit(); total += 1
    if py_data_dir.exists():
        for p in sorted(py_data_dir.glob('*.py')):
            if p.name.endswith(('_data.py','_teknik.py')):
                print('[PY_MD]', p.name); process_python_md_doc(conn, p); conn.commit(); total += 1
    print('Bitti, belge sayısı:', total); conn.close()

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo-root', required=True)
    ap.add_argument('--drop-and-recreate', type=int, default=0)
    a = ap.parse_args()
    run(a.repo_root, bool(a.drop_and_recreate))
