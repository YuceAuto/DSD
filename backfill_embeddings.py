import os
from dotenv import load_dotenv, find_dotenv

from modules.neo4j_skoda_graphrag import Neo4jSkodaGraphRAG  # path doğru

def must_get(name: str) -> str:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        raise RuntimeError(f"ENV missing: {name}")
    return str(v).strip()

def main():
    # ✅ .env dosyasını yükle (proje kökünden bulur)
    load_dotenv(find_dotenv(usecwd=True), override=True)

    # ✅ ENV doğrula (None gelmesin)
    openai_key = "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"
    neo4j_uri = "neo4j+s://4a20633d.databases.neo4j.io"
    neo4j_user = "neo4j"
    neo4j_pass = "ss3o_V9DirgVa5pKFrqGgfonE89KAJy-zFjylzD2Fxw"
    neo4j_db="neo4j"


    neo = Neo4jSkodaGraphRAG(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_pass,
        openai_api_key=openai_key,
        enabled=True,
        neo4j_db=neo4j_db,
    )
    print("NEO4J_URI used:", neo4j_uri)
    print("NEO4J_USER used:", neo4j_user)
    print("NEO4J_DB used:", neo.neo4j_db)

    with neo.driver.session(database=neo.neo4j_db) as s:
        info = s.run("CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition").data()
        print("DBMS:", info)

        

    with neo.driver.session(database=neo.neo4j_db) as s:
        r = s.run("""
                MATCH (c:Chunk) WHERE c.source=$src
                RETURN count(c) AS total,
                    sum(CASE WHEN c.embedding IS NULL THEN 1 ELSE 0 END) AS missing
            """, {"src": "GRAPH_TRIM_V2"}).single()
        print("PY CHECK total:", r["total"], "missing:", r["missing"], "db:", neo.neo4j_db)

    n = neo.backfill_embeddings_for_source("GRAPH_TRIM_V2", batch=150)
    print("Backfilled embeddings:", n)
    
    neo.close()

if __name__ == "__main__":
    main()
