# -*- coding: utf-8 -*-
import re, os, pyodbc
from modules.db import get_db_connection
from modules.data.elroq_data import ELROQ_DATA_MD
def md_table_to_rows(md_text: str):
    lines = [ln for ln in (md_text or "").splitlines() if ln.strip()]
    if not any('|' in ln for ln in lines):
        return None, None
    header = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith('|') and ln.strip().endswith('|'):
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
        rows.append([c.strip() for c in ln.strip().strip('|').split('|')])
    return header, rows

def parse_money_tr(val: str):
    if val is None: return None
    s = (val.replace('.', '').replace('\u00A0',' ').replace(' ', '').replace(',', '.'))
    s = re.sub(r'[^\d\.\-]', '', s)
    try: return float(s)
    except: return None

def load_elroq_structured_to_db(conn, doc_id: int, md: str):
    cur = conn.cursor()
    model = "Elroq"
    trim  = "e-Prestige"

    # 1) Opsiyon fiyatları (e-Prestige — Opsiyonel Donanımlar)
    m = re.search(r'##\s*e.?Prestige\s*—\s*Opsiyonel Donanımlar.*?\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        hdr, rows = md_table_to_rows(m.group(1))
        if hdr and rows:
            nh = [re.sub(r'\s+',' ', h).lower() for h in hdr]
            def fidx(*keys):
                for i,h in enumerate(nh):
                    for k in keys:
                        if k in h: return i
                return None
            idx_code = fidx('kod')
            idx_desc = fidx('açıklama','aciklama','tanım','tanim','description')
            idx_net  = fidx('net satış','net satis','net')
            idx_25   = fidx('%25','25')
            for r in rows:
                code = r[idx_code].strip() if idx_code is not None and idx_code < len(r) else None
                if not code: continue
                desc = r[idx_desc].strip() if idx_desc is not None and idx_desc < len(r) else None
                net  = parse_money_tr(r[idx_net]) if idx_net is not None and idx_net < len(r) else None
                at25 = parse_money_tr(r[idx_25]) if idx_25 is not None and idx_25 < len(r) else None
                cur.execute("""
                IF NOT EXISTS(
                    SELECT 1 FROM kb.PriceItem WHERE model_name=? AND ISNULL(trim_name,'')=ISNULL(?, '') AND code=?
                )
                    INSERT INTO kb.PriceItem(doc_id, model_name, trim_name, code, description, price_net, price_at_25)
                    VALUES (?,?,?,?,?,?,?);
                """, (model, trim, code, doc_id, model, trim, code, desc, net, at25))

    # 2) Donanım tabloları (Kategori → Özellik → Durum)
    for cat in [r'Güvenlik', r'Konfor\s*&\s*Teknoloji', r'Tasarım']:
        p = re.compile(rf'###\s*{cat}\s*\n\n([\s\S]+?)(?:\n\n---|\Z)', re.IGNORECASE)
        m = p.search(md)
        if not m: continue
        hdr, rows = md_table_to_rows(m.group(1))
        if not (hdr and rows): continue
        for r in rows:
            feat = (r[0] if len(r)>0 else '').strip()
            stat = (r[1] if len(r)>1 else '').strip()
            if not feat: continue
            st = "Standart" if re.search(r'^(s|standart)', stat, re.IGNORECASE) else ("Opsiyonel" if 'ops' in stat.lower() else (stat or None))
            cur.execute("""
                INSERT INTO kb.FeatureItem(doc_id, model_name, trim_name, category, feature, status)
                VALUES (?,?,?,?,?,?)
            """, (doc_id, model, trim, re.sub(r'\s+',' ', cat.replace('\\','')), feat, st))

    # 3) DÖŞEME (madde listesi)
    m = re.search(r'##\s*DÖŞEME\s*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        for ln in m.group(1).splitlines():
            ln = ln.strip()
            if ln.startswith('- '):
                feat = re.sub(r'^-\s*', '', ln)
                cur.execute("""
                    INSERT INTO kb.FeatureItem(doc_id, model_name, trim_name, category, feature, status)
                    VALUES (?,?,?,?,?,?)
                """, (doc_id, model, trim, 'Döşeme', feat, 'Standart'))

    # 4) JANT SEÇENEKLERİ (madde listesi)
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

    # 5) RENK SEÇENEKLERİ
    m = re.search(r'##\s*RENK SEÇENEKLERİ\s*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        block = m.group(1)
        for line in block.splitlines():
            line = line.strip()
            if not line: continue
            m2 = re.match(r'^\*\*(.+?)\:\*\*\s*(.+)$', line)  # **Exclusive:** Ay Beyazı (2Y2Y), ...
            if not m2: continue
            grp, rest = m2.group(1).strip(), m2.group(2).strip()
            for token in re.split(r'\s{2,}|,\s*', rest):
                token = token.strip().strip(',')
                if not token: continue
                name, code = token, None
                m3 = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', token)
                if m3:
                    name, code = m3.group(1).strip(), m3.group(2).strip()
                cur.execute("""
                    INSERT INTO kb.ColorItem(doc_id, model_name, color_group, color_name, color_code, availability)
                    VALUES (?,?,?,?,?,?)
                """, (doc_id, model, grp, name, code, None))

    # 6) TEKNİK VERİLER (Özellik | Değer)
    m = re.search(r'##\s*Teknik Veriler\s*—\s*ELROQ.*?\n\n([\s\S]+?)\n\n', md, re.IGNORECASE)
    if m:
        hdr, rows = md_table_to_rows(m.group(1))
        if hdr and rows:
            for r in rows:
                if len(r) < 2: continue
                key, val = r[0].strip(), r[1].strip()
                cur.execute("""
                    INSERT INTO kb.SpecItem(doc_id, model_name, trim_name, spec_key, spec_value, unit)
                    VALUES (?,?,?,?,?,?)
                """, (doc_id, model, trim, key, val, None))

    cur.close()
    conn.commit()

def main():
    # 1) DB bağlantısı
    conn = get_db_connection()

    # 2) kb.Document kaydı aç (varsa reuse)
    cur = conn.cursor()
    source = "modules/elroq_data.py::ELROQ_DATA_MD"

    # 1) Varsa mevcut doc_id’yi al
    cur.execute("SELECT TOP (1) doc_id FROM kb.Document WHERE source_path=?", (source,))
    row = cur.fetchone()

    if row and row[0]:
        doc_id = int(row[0])
    else:
        # 2) Yoksa ekle ve INSERTED.doc_id ile al
        cur.execute("""
            INSERT INTO kb.Document
                (source_path, source_type, model_name, trim_name, title, version_tag, content_hash)
            OUTPUT INSERTED.doc_id
            VALUES (?, 'python_md', 'Elroq', 'e-Prestige', 'ELROQ DATA', NULL, 0x00);
        """, (source,))
        doc_id = int(cur.fetchone()[0])

    cur.close()
    conn.commit()


    # 3) Tablolara yaz
    load_elroq_structured_to_db(conn, doc_id, ELROQ_DATA_MD)
    conn.close()
    print("ELROQ structured load OK. doc_id:", doc_id)

if __name__ == "__main__":
    main()
