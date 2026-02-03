# -*- coding: utf-8 -*-
import re
from modules.db import get_db_connection
from modules.data.superb_data import SUPERB_DATA_MD

# ---------- yardımcılar ----------
def md_table_to_rows(md_text: str):
    lines = [ln for ln in (md_text or "").splitlines() if ln.strip()]
    if not any('|' in ln for ln in lines):
        return (None, None)
    header = None; sep_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith('|') and ln.strip().endswith('|'):
            if i+1 < len(lines) and re.match(r'^\s*\|(?:\s*:?-+:?\s*\|)+\s*$', lines[i+1]):
                header = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                sep_idx = i + 1
                break
    if not header:
        return (None, None)
    rows = []
    for ln in lines[sep_idx+1:]:
        if not (ln.strip().startswith('|') and ln.strip().endswith('|')):
            break
        rows.append([c.strip() for c in ln.strip().strip('|').split('|')])
    return header, rows

def money_tr(val: str):
    if val is None: return None
    s = (val.replace('.', '').replace('\u00A0',' ').replace(' ', '').replace(',', '.'))
    s = re.sub(r'[^\d\.\-]', '', s)
    try: return float(s)
    except: return None

def idx_of(headers_norm, *keys):
    for i,h in enumerate(headers_norm):
        for k in keys:
            if k in h: return i
    return None

# ---------- yükleme ----------
def load_superb_structured_to_db(conn, doc_id: int, md: str):
    cur = conn.cursor()
    MODEL = "Superb"

    # 1) OPSİYON FİYATLARI
    # Premium (%90, %100)
    # Prestige (%90, %100)
    # L&K Crystal (%90, %100, %170)
    # e-Sportline PHEV (%75)
    price_blocks = [
        (r'##\s*Premium\s*—\s*Opsiyonel Donanımlar\s*\n\n([\s\S]+?)\n\n---',
         "Premium",  ["%90","%100"]),
        (r'##\s*Prestige\s*—\s*Opsiyonel Donanımlar\s*\n\n([\s\S]+?)\n\n---',
         "Prestige", ["%90","%100"]),
        (r'##\s*L&K\s*Crystal\s*—\s*Opsiyonel Donanımlar\s*\n\n([\s\S]+?)\n\n---',
         "L&K Crystal", ["%90","%100","%170"]),
        (r'##\s*e\-Sportline\s*PHEV\s*—\s*Opsiyonel Donanımlar\s*\n\n([\s\S]+?)\n\n---',
         "e-Sportline", ["%75"]),
    ]
    for rx, trim, _pct in price_blocks:
        m = re.search(rx, md, re.IGNORECASE)
        if not m: 
            continue
        hdr, rows = md_table_to_rows(m.group(1))
        if not (hdr and rows): 
            continue
        nh = [re.sub(r'\s+',' ', h).lower() for h in hdr]
        i_code = idx_of(nh, "kod")
        i_desc = idx_of(nh, "açıklama","aciklama","tanım","tanim","description")
        i_net  = idx_of(nh, "net satis","net satış","net")
        i_75   = idx_of(nh, "%75","75")
        i_90   = idx_of(nh, "%90","90")
        i_100  = idx_of(nh, "%100","100")
        i_170  = idx_of(nh, "%170","170")

        for r in rows:
            code = (r[i_code] if i_code is not None and i_code < len(r) else "").strip()
            if not code: 
                continue
            desc = (r[i_desc] if i_desc is not None and i_desc < len(r) else "").strip()
            pnet = money_tr(r[i_net]) if i_net is not None and i_net < len(r) else None
            p75  = money_tr(r[i_75])  if i_75  is not None and i_75  < len(r) else None
            p90  = money_tr(r[i_90])  if i_90  is not None and i_90  < len(r) else None
            p100 = money_tr(r[i_100]) if i_100 is not None and i_100 < len(r) else None
            p170 = money_tr(r[i_170]) if i_170 is not None and i_170 < len(r) else None

            # INSERT (mevcutsa pas geç)
            cur.execute("""
            IF NOT EXISTS(
                SELECT 1 FROM kb.PriceItem WHERE model_name=? AND ISNULL(trim_name,'')=ISNULL(?, '') AND code=?
            )
                INSERT INTO kb.PriceItem(
                    doc_id, model_name, trim_name, code, description,
                    price_net, price_at_75, price_at_90, price_at_100, price_at_170
                )
                VALUES (?,?,?,?,?,?,?,?,?,?);
            """, (MODEL, trim, code, doc_id, MODEL, trim, code, desc, pnet, p75, p90, p100, p170))

    # 2) DONANIM MATRİSLERİ — 4 sütun (Premium, Prestige, L&K Crystal, e-Sportline)
    def load_feature_matrix(cat_title, block_rx):
        m = re.search(block_rx, md, re.IGNORECASE)
        if not m: return
        hdr, rows = md_table_to_rows(m.group(1))
        if not (hdr and rows): return
        trims = [ (t or "").strip() for t in hdr[1:] ]
        for r in rows:
            if not r: continue
            feat = (r[0] if len(r)>0 else "").strip()
            if not feat: continue
            for idx, tname in enumerate(trims, start=1):
                raw = r[idx] if idx < len(r) else ""
                val = (raw or "").strip()
                low = val.lower()
                if low.startswith('s') or 'standart' in low:
                    status = 'Standart'
                elif 'ops' in low or 'opsiyon' in low:
                    status = 'Opsiyonel'
                elif low in ('yok','—','-',''):
                    status = 'Yok'
                else:
                    status = val[:200] if val else None
                cur.execute("""
                    INSERT INTO kb.FeatureItem(doc_id, model_name, trim_name, category, feature, status)
                    VALUES (?,?,?,?,?,?)
                """, (doc_id, MODEL, tname, cat_title, feat, status))

    load_feature_matrix("Güvenlik", r'###\s*Güvenlik\s*\n\n([\s\S]+?)\n\n---')
    load_feature_matrix("Konfor & Teknoloji", r'###\s*Konfor\s*&\s*Teknoloji\s*\n\n([\s\S]+?)\n\n---')
    load_feature_matrix("Tasarım", r'###\s*Tasarım\s*\n\n([\s\S]+?)\n\n---')

    # 3) DÖŞEME (Özet) – madde listesi
    m = re.search(r'##\s*DÖŞEME\s*\(Özet\)\s*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if not m:
        m = re.search(r'##\s*Döşeme\s*\(Özet\)\s*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        for ln in m.group(1).splitlines():
            ln = ln.strip()
            if ln.startswith('- '):
                cur.execute("""
                    INSERT INTO kb.FeatureItem(doc_id, model_name, trim_name, category, feature, status)
                    VALUES (?,?,?,?,?,?)
                """, (doc_id, MODEL, None, 'Döşeme (Özet)', re.sub(r'^-\s*','',ln), None))

    # 4) STANDART & OPSİYONEL JANTLAR – madde listesi
    m = re.search(r'##\s*STANDART\s*&\s*OPSİYONEL\s*JANTLAR\s*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        for ln in m.group(1).splitlines():
            ln = ln.strip()
            if not ln.startswith('- '): continue
            txt = re.sub(r'^-\s*','',ln)
            avail = 'Standart' if 'Standart' in txt else ('Opsiyonel' if 'Opsiyonel' in txt else None)
            trim_hint = None  # açıklama içinde zaten hangi trimlerde olduğu yazıyor
            cur.execute("""
                INSERT INTO kb.WheelItem(doc_id, model_name, trim_name, wheel_desc, availability)
                VALUES (?,?,?,?,?)
            """, (doc_id, MODEL, trim_hint, txt, avail))

    # 5) RENK SEÇENEKLERİ – gruplar (Metalik/Exclusive/Opal)
    m = re.search(r'##\s*RENK SEÇENEKLERİ\s*\(Özet\)\s*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        blk = m.group(1)
        groups = [
            (r'^\-\s*\*\*Metalik\:\*\*\s*(.+)$', 'Metalik'),
            (r'^\-\s*\*\*Exclusive\:\*\*\s*(.+)$', 'Exclusive'),
            (r'^\-\s*\*\*Opal\:\*\*\s*(.+)$', 'Opal'),
        ]
        for line in blk.splitlines():
            line = line.strip()
            for pat, grp in groups:
                mm = re.match(pat, line, re.IGNORECASE)
                if not mm: 
                    continue
                rest = mm.group(1).strip()
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
                    """, (doc_id, MODEL, grp, name, code, None))

    # 6) Bilgi-Eğlence & Gösterge (Görsel Özet)
    m = re.search(r'##\s*Bilgi[-\-]Eğlence\s*&\s*Gösterge\s*\(Görsel\s*Özet\)\s*\n\n([\s\S]+?)\n\n$', md, re.IGNORECASE)
    if m:
        for ln in m.group(1).splitlines():
            t = ln.strip()
            if not t or not t.startswith('- '): continue
            cur.execute("""
                INSERT INTO kb.FeatureItem(doc_id, model_name, trim_name, category, feature, status)
                VALUES (?,?,?,?,?,?)
            """, (doc_id, MODEL, None, 'Bilgi-Eğlence & Gösterge (Özet)', re.sub(r'^-\s*','',t), None))

    cur.close()
    conn.commit()

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    source = "modules/data/superb_data.py::SUPERB_DATA_MD"

    # document kaydı (varsa reuse)
    cur.execute("SELECT TOP (1) doc_id FROM kb.Document WHERE source_path=?", (source,))
    row = cur.fetchone()
    if row and row[0]:
        doc_id = int(row[0])
    else:
        cur.execute("""
            INSERT INTO kb.Document
                (source_path, source_type, model_name, trim_name, title, version_tag, content_hash)
            OUTPUT INSERTED.doc_id
            VALUES (?, 'python_md', 'Superb', NULL, 'SUPERB DATA', NULL, 0x00);
        """, (source,))
        doc_id = int(cur.fetchone()[0])
    cur.close(); conn.commit()

    load_superb_structured_to_db(conn, doc_id, SUPERB_DATA_MD)
    conn.close()
    print("SUPERB structured load OK. doc_id:", doc_id)

if __name__ == "__main__":
    main()
