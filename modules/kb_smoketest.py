# -*- coding: utf-8 -*-
from modules.kb_repo import MSSQLKb

def show(tag, hits):
    print(f"[{tag}] HIT SAYISI:", len(hits))
    for h in hits[:5]:
        sec2 = h.get("section_h2") or ""
        sec3 = h.get("section_h3") or ""
        print(f"- {sec2} / {sec3} :: {h['snippet'][:120]}")

def main():
    kb = MSSQLKb()

    # 1) modelsiz genel aramalar (LIKE fallback)
    for q in ["Uzunluk", "Net Satış (TL)", "Opsiyon", "KESSY", "CO2"]:
        show(f"GENEL '{q}'", kb.search_chunks(q, top_k=10, model_hint=None))

    # 2) model ipucuyla (SSMS'te gördüğünüz modeller)
    models = ["Enyaq","Fabia","Kamiq","Karoq","Kodiaq","Octavia","Scala","Superb"]
    for model in models:
        for q in ["Uzunluk", "Opsiyon", "Net Satış (TL)"]:
            show(f"{model} '{q}'", kb.search_chunks(q, top_k=10, model_hint=model))

    # 3) hangi DB'ye bağlıyız?
    cur = kb.conn.cursor()
    cur.execute("SELECT DB_NAME()")
    print("DB:", cur.fetchone()[0])

if __name__ == "__main__":
    main()
