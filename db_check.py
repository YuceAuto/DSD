# -*- coding: utf-8 -*-
import os
from modules.kb_repo import MSSQLKb
from modules.kb_repo import MSSQLKb
kb = MSSQLKb() 
#kb = MSSQLKb(prefer_env=True)  # <-- ortamdaki MSSQL_CONN_STR'ü zorla kullan
cur = kb.conn.cursor()

cur.execute("SELECT DB_NAME()")
print("DB:", cur.fetchone()[0])

# Hızlı sayımlar
cur.execute("SELECT COUNT(*) FROM kb.Document"); print("Document:", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM kb.Chunk");    print("Chunk   :", cur.fetchone()[0])

# İçerikte 'Uzunluk' geçen ilk 3 parça
cur.execute("""
SELECT TOP 3 d.model_name, c.doc_id, c.ord, LEFT(c.content_txt,120)
FROM kb.Chunk c
JOIN kb.Document d ON d.doc_id = c.doc_id
WHERE c.content_txt LIKE N'%Uzunluk%'
ORDER BY c.doc_id DESC, c.ord
""")
rows = cur.fetchall()
print("LIKE test rows:", len(rows))
for r in rows:
    print("-", r)
