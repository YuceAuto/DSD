import os
from neo4j import GraphDatabase
from langchain_openai import OpenAIEmbeddings

# (Opsiyonel) .env yüklemek istersen:
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=True)
except Exception:
    pass

# ---- Neo4j bağlantı bilgileri ----
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://4a20633d.databases.neo4j.io")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")  # .env veya sistem env'den gelsin
NEO4J_DATABASE = os.getenv("NEO4J_DB", "neo4j")

# ---- OpenAI API key ----
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY bulunamadı. .env içine ekle veya ortam değişkeni olarak set et.")

if not NEO4J_PASSWORD:
    raise RuntimeError("NEO4J_PASSWORD bulunamadı. .env içine ekle veya ortam değişkeni olarak set et.")

# ---- Embeddings ----
emb = OpenAIEmbeddings(
    model="text-embedding-3-large",
    api_key=OPENAI_API_KEY,
)  # 3072

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

BATCH_SIZE = 50

# ✅ Burayı ihtiyacına göre seç:
# - yeni trim bazlı chunk'lar: octavia_graph_trim
# - eski chunk'lar: octavia_graph
CHUNK_SOURCE = "octavia3_graph_trim"

with driver.session(database=NEO4J_DATABASE) as s:
    rows = s.run(
        """
        MATCH (c:Chunk)
        WHERE c.source=$src AND c.embedding IS NULL
        RETURN c.doc_id AS doc_id, c.text AS text
        LIMIT 1000
        """,
        src=CHUNK_SOURCE
    ).data()

    print("Embedding basılacak chunk sayısı:", len(rows))

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        texts = [r["text"] for r in batch]
        vecs = emb.embed_documents(texts)

        payload = [{"doc_id": batch[j]["doc_id"], "embedding": vecs[j]} for j in range(len(batch))]

        s.run(
            """
            UNWIND $rows AS r
            MATCH (c:Chunk {doc_id:r.doc_id})
            SET c.embedding = r.embedding,
                c.updated_at = timestamp()
            """,
            rows=payload
        ).consume()

driver.close()
print("OK")
