# check_neo4j_kbvectors.py
import os
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DB = os.getenv("NEO4J_DB", "neo4j")

NODE_LABEL = os.getenv("NEO4J_RAG_NODE_LABEL", "Chunk")
EMB_PROP = os.getenv("NEO4J_RAG_EMB_PROP", "embedding")
TEXT_PROP = (os.getenv("NEO4J_RAG_TEXT_PROPS", "text").split(",")[0] or "text").strip()
VEC_INDEX = os.getenv("NEO4J_VECTOR_INDEX_NAME", "vector")

def run(q, **params):
    with driver.session(database=NEO4J_DB) as s:
        return s.run(q, **params).data()

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
try:
    print("\n=== 1) Node sayısı ===")
    q1 = f"MATCH (n:{NODE_LABEL}) RETURN count(n) AS cnt"
    print(run(q1)[0])

    print("\n=== 2) Embedding var mı? (null olmayan) + dim ===")
    q2 = f"""
    MATCH (n:{NODE_LABEL})
    WHERE n.{EMB_PROP} IS NOT NULL
    RETURN count(n) AS withEmb,
           min(size(n.{EMB_PROP})) AS minDim,
           max(size(n.{EMB_PROP})) AS maxDim
    """
    print(run(q2)[0])

    print("\n=== 3) source dağılımı (KbVectors_Equip/Spec/Price/Other görmelisin) ===")
    q3 = f"""
    MATCH (n:{NODE_LABEL})
    RETURN n.source AS source, count(*) AS c
    ORDER BY c DESC
    """
    for r in run(q3)[:12]:
        print(r)

    print("\n=== 4) doc_id örnekleri (KbVectors_*:<id> gibi olmalı) ===")
    q4 = f"""
    MATCH (n:{NODE_LABEL})
    RETURN n.doc_id AS doc_id, n.source AS source
    LIMIT 10
    """
    for r in run(q4):
        print(r)

    print("\n=== 5) VECTOR index ONLINE mı? ===")
    q5 = """
    SHOW INDEXES YIELD name, type, state
    WHERE type='VECTOR'
    RETURN name, state
    """
    for r in run(q5):
        print(r)

    print("\n=== 6) VECTOR index gerçekten çalışıyor mu? (self-match testi) ===")
    # Bir node'un embedding'ini alıp vector query ile kendisini bulmayı deniyoruz.
    q_get = f"""
    MATCH (n:{NODE_LABEL})
    WHERE n.{EMB_PROP} IS NOT NULL
    RETURN n.doc_id AS doc_id, n.{EMB_PROP} AS emb
    LIMIT 1
    """
    row = run(q_get)
    if not row:
        print("⚠️ Embedding'li node bulunamadı (ingest eksik olabilir).")
    else:
        emb = row[0]["emb"]
        doc_id = row[0]["doc_id"]
        q_vec = """
        CALL db.index.vector.queryNodes($indexName, $k, $embedding)
        YIELD node, score
        RETURN node.doc_id AS doc_id, node.source AS source, score
        """
        res = run(q_vec, indexName=VEC_INDEX, k=5, embedding=emb)
        print(f"Seed doc_id: {doc_id}")
        for r in res:
            print(r)

    print("\n=== 7) text prop dolu mu? (ilk 3 örnek) ===")
    q7 = f"""
    MATCH (n:{NODE_LABEL})
    WHERE n.{TEXT_PROP} IS NOT NULL
    RETURN substring(n.{TEXT_PROP}, 0, 120) AS text120, n.source AS source
    LIMIT 3
    """
    for r in run(q7):
        print(r)

finally:
    driver.close()
