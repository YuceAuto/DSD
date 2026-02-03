import os
from neo4j import GraphDatabase
from langchain_openai import OpenAIEmbeddings

# .env yükle (varsa)
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=True)

NEO4J_URI=os.getenv("NEO4J_URI")
NEO4J_USERNAME=os.getenv("NEO4J_USERNAME","neo4j")
NEO4J_PASSWORD=os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE=os.getenv("NEO4J_DB","neo4j")

emb = OpenAIEmbeddings(model="text-embedding-3-large")  # 3072
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

B=50
with driver.session(database=NEO4J_DATABASE) as s:
    rows = s.run("""
        MATCH (o:OPTION)
        WHERE o.embedding IS NULL
        RETURN o.id AS id, (coalesce(o.name,'') + ' ' + coalesce(o.category,'') + ' ' + coalesce(o.code,'')) AS text
        LIMIT 2000
    """).data()

    for i in range(0, len(rows), B):
        batch = rows[i:i+B]
        vecs = emb.embed_documents([r["text"] for r in batch])
        payload = [{"id": batch[j]["id"], "embedding": vecs[j]} for j in range(len(batch))]
        s.run("""
            UNWIND $rows AS r
            MATCH (o:OPTION {id:r.id})
            SET o.embedding = r.embedding, o.updated_at = timestamp()
        """, rows=payload).consume()

driver.close()
print("OK")
