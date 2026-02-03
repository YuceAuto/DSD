# -*- coding: utf-8 -*-
from modules.kb_repo import MSSQLKb

def show(tag, hits):
    print(f"[{tag}] HIT SAYISI:", len(hits))
    for h in hits[:5]:
        sec2 = h.get("section_h2") or ""
        sec3 = h.get("section_h3") or ""
        print(f"- {sec2} / {sec3} :: {h['snippet'][:120]}")

def main():
    # db_check.py ile aynı davranış için prefer_env=True
    #kb = MSSQLKb(prefer_env=True)
    kb = MSSQLKb()
    # Hangi DB'ye bağlıyız?
    cur = kb.conn.cursor()
    cur.execute("SELECT DB_NAME()")
    print("DB:", cur.fetchone()[0])

    # Sık geçtiğini gördüğümüz kelimelerle deneyelim
    queries = ["Uzunluk", "Net Satış (TL)", "Opsiyon", "CO2", "KESSY"]
    models  = ["Enyaq","Fabia","Kamiq","Karoq","Kodiaq","Octavia","Scala","Superb"]

    # 1) modelsiz genel aramalar (LIKE fallback)
    for q in queries:
        show(f"GENEL '{q}'", kb.search_chunks(q, top_k=10, model_hint=None))

    # 2) model ipucuyla
    for m in models:
        for q in ["Uzunluk", "Opsiyon", "Net Satış (TL)"]:
            show(f"{m} '{q}'", kb.search_chunks(q, top_k=10, model_hint=m))

if __name__ == "__main__":
    main()
