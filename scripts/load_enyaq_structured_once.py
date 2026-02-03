# -*- coding: utf-8 -*-
import re, os, pyodbc
from modules.db import get_db_connection
from modules.data.enyaq_data import ENYAQ_DATA_MD

# ---- yardımcılar ----
def md_table_to_rows(md_text: str):
    lines = [ln for ln in (md_text or "").splitlines() if ln.strip()]
    if not any('|' in ln for ln in lines): return (None, None)
    header = None; sep_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith('|') and ln.strip().endswith('|'):
            if i+1 < len(lines) and re.match(r'^\s*\|(?:\s*:?-+:?\s*\|)+\s*$', lines[i+1]):
                header = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                sep_idx = i + 1
                break
    if not header: return (None, None)
    rows = []
    for ln in lines[sep_idx+1:]:
        if not (ln.strip().startswith('|') and ln.strip().endswith('|')): break
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

# ---- yükleme ----
def load_enyaq_structured_to_db(conn, doc_id: int, md: str):
    cur = conn.cursor()
    MODEL = "Enyaq"

    # ---------- 1) OPSIYON FIYATLARI (3 tablo) ----------
    price_blocks = [
        # (başlık regex, trim_adi, kolonlar)
        (r'##\s*e.?Prestige\s*60\s*—\s*Opsiyonel Donanımlar.*?\n\n([\s\S]+?)\n\n---',
         "e-Prestige 60",
         {"net":"net satis","at25":"%25","at55":"%55"}),

        (r'##\s*Enyaq\s*Coup[eé]\s*e.?Sportline\s*60\s*—\s*Opsiyonel Donanımlar.*?\n\n([\s\S]+?)\n\n---',
         "Coupé e-Sportline 60",
         {"net":"net satis","at25":"%25","at55":"%55"}),

        (r'##\s*Enyaq\s*Coup[eé]\s*e.?Sportline\s*85x\s*—\s*Opsiyonel Donanımlar.*?\n\n([\s\S]+?)\n\n---',
         "Coupé e-Sportline 85x",
         {"net":"net satis","at75":"%75"}),
    ]
    for rx, trim, cols in price_blocks:
        m = re.search(rx, md, re.IGNORECASE)
        if not m: continue
        hdr, rows = md_table_to_rows(m.group(1))
        if not (hdr and rows): continue
        nh = [re.sub(r'\s+',' ', h).lower() for h in hdr]
        i_code = idx_of(nh, "kod")
        i_desc = idx_of(nh, "açıklama","aciklama","tanım","tanim","description")
        i_net  = idx_of(nh, "net satis","net satış","net")
        i_25   = idx_of(nh, "%25","25")
        i_55   = idx_of(nh, "%55","55")
        i_75   = idx_of(nh, "%75","75")

        for r in rows:
            code = (r[i_code] if i_code is not None and i_code < len(r) else "").strip()
            if not code: continue
            desc = (r[i_desc] if i_desc is not None and i_desc < len(r) else "").strip()
            pnet = money_tr(r[i_net]) if i_net is not None and i_net < len(r) else None
            p25  = money_tr(r[i_25]) if i_25 is not None and i_25 < len(r) else None
            p55  = money_tr(r[i_55]) if i_55 is not None and i_55 < len(r) else None
            p75  = money_tr(r[i_75]) if i_75 is not None and i_75 < len(r) else None

            cur.execute("""
            IF NOT EXISTS(
                SELECT 1 FROM kb.PriceItem WHERE model_name=? AND ISNULL(trim_name,'')=ISNULL(?, '') AND code=?
            )
                INSERT INTO kb.PriceItem(doc_id, model_name, trim_name, code, description, price_net, price_at_25, price_at_55, price_at_75)
                VALUES (?,?,?,?,?,?,?,?,?);
            """, (MODEL, trim, code, doc_id, MODEL, trim, code, desc, pnet, p25, p55, p75))

    # ---------- 2) DONANIM TABLOLARI (matris 3 sütun) ----------
    def load_feature_matrix(cat_title, block_rx):
        m = re.search(block_rx, md, re.IGNORECASE)
        if not m:
            return

        hdr, rows = md_table_to_rows(m.group(1))
        if not (hdr and rows):
            return

        # Başlıklar: Özellik | <trim1> | <trim2> | <trim3> ...
        trims = [ (t or "").strip() for t in hdr[1:] ]

        for r in rows:
            if not r:
                continue
            feat = (r[0] if len(r) > 0 else "").strip()
            if not feat:
                continue

            for idx, tname in enumerate(trims, start=1):
                # Hücre eksikse boş kabul et
                raw = r[idx] if idx < len(r) else ""
                val = (raw or "").strip()

                # Durumu normalize et
                low = val.lower()
                if low.startswith('s') or 'standart' in low:
                    status = 'Standart'
                elif 'ops' in low or 'opsiyon' in low:
                    status = 'Opsiyonel'
                elif low in ('yok', '—', '-', ''):
                    status = 'Yok'
                else:
                    # Hücrede uzun metin varsa (ör. "Canton 12 hoparlör/625 W") status'e olduğu gibi yaz
                    # ve kolon limitine takılmamak için kırp
                    status = val[:200] if val else None

                cur.execute("""
                    INSERT INTO kb.FeatureItem(doc_id, model_name, trim_name, category, feature, status)
                    VALUES (?,?,?,?,?,?)
                """, (doc_id, MODEL, tname, cat_title, feat, status))

    load_feature_matrix("Güvenlik", r'###\s*Güvenlik\s*\n\n([\s\S]+?)\n\n---')
    load_feature_matrix("Konfor & Teknoloji", r'###\s*Konfor\s*&\s*Teknoloji\s*\n\n([\s\S]+?)\n\n---')
    load_feature_matrix("Tasarım", r'###\s*Tasarım\s*\n\n([\s\S]+?)\n\n---')

    # ---------- 3) DÖŞEME (özet maddeler) ----------
    m = re.search(r'##\s*DÖŞEME\s*\(Özet\)\s*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        for ln in m.group(1).splitlines():
            ln = ln.strip()
            if ln.startswith('- '):
                cur.execute("""
                    INSERT INTO kb.FeatureItem(doc_id, model_name, trim_name, category, feature, status)
                    VALUES (?,?,?,?,?,?)
                """, (doc_id, MODEL, None, 'Döşeme (Özet)', re.sub(r'^-\s*','',ln), None))

    # ---------- 4) STANDART & OPSIYONEL JANTLAR (maddeler) ----------
    m = re.search(r'##\s*STANDART\s*&\s*OPSİYONEL\s*JANTLAR\s*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        for ln in m.group(1).splitlines():
            ln = ln.strip()
            if not ln.startswith('- '): continue
            txt = re.sub(r'^-\s*', '', ln)
            # uygunluk ipuçları
            avail = 'Standart' if 'Standart' in txt else ('Opsiyonel' if 'Opsiyonel' in txt else None)
            # satırdan trim ipucunu kaba çek
            t_hint = None
            if 'e-Prestige' in txt or 'e-Prestige' in txt: t_hint = 'e-Prestige 60'
            if 'e-Sportline' in txt or 'e-Sportline' in txt: t_hint = 'Coupé e-Sportline 60'  # 85x bilgisi zaten ayrı tabloda var
            cur.execute("""
                INSERT INTO kb.WheelItem(doc_id, model_name, trim_name, wheel_desc, availability)
                VALUES (?,?,?,?,?)
            """, (doc_id, MODEL, t_hint, txt, avail))

    # ---------- 5) RENK SEÇENEKLERİ ----------
    m = re.search(r'##\s*RENK SEÇENEKLERİ\s*\n\n([\s\S]+?)\n\n---', md, re.IGNORECASE)
    if m:
        blk = m.group(1)
        for line in blk.splitlines():
            line = line.strip()
            if not line: continue
            mm = re.match(r'^\*\*(.+?)\:\*\*\s*(.+)$', line)  # **Metalik:** Ay Beyazı (2Y2Y), ...
            if not mm: continue
            grp, rest = mm.group(1).strip(), mm.group(2).strip()
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

    # ---------- 6) TEKNİK VERİLER (özet tablo – 3 trim sütunu) ----------
    m = re.search(r'##\s*Teknik Veriler\s*—\s*\(Özet Tablo\)\s*\n\n([\s\S]+?)\n\n', md, re.IGNORECASE)
    if m:
        hdr, rows = md_table_to_rows(m.group(1))
        if hdr and rows and len(hdr) >= 2:
            trims = hdr[1:]  # 3 trim sütunu
            for r in rows:
                if not r: continue
                spec_key = r[0].strip()
                for idx, tname in enumerate(trims, start=1):
                    if idx >= len(r): continue
                    val = r[idx].strip()
                    cur.execute("""
                        INSERT INTO kb.SpecItem(doc_id, model_name, trim_name, spec_key, spec_value, unit)
                        VALUES (?,?,?,?,?,?)
                    """, (doc_id, MODEL, tname, spec_key, val, None))

    cur.close()
    conn.commit()

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    source = "modules/data/enyaq_data.py::ENYAQ_DATA_MD"

    # mevcut doc_id varsa al, yoksa oluştur
    cur.execute("SELECT TOP (1) doc_id FROM kb.Document WHERE source_path=?", (source,))
    row = cur.fetchone()
    if row and row[0]:
        doc_id = int(row[0])
    else:
        cur.execute("""
            INSERT INTO kb.Document
                (source_path, source_type, model_name, trim_name, title, version_tag, content_hash)
            OUTPUT INSERTED.doc_id
            VALUES (?, 'python_md', 'Enyaq', NULL, 'ENYAQ DATA', NULL, 0x00);
        """, (source,))
        doc_id = int(cur.fetchone()[0])
    cur.close(); conn.commit()

    load_enyaq_structured_to_db(conn, doc_id, ENYAQ_DATA_MD)
    conn.close()
    print("ENYAQ structured load OK. doc_id:", doc_id)

if __name__ == "__main__":
    main()
