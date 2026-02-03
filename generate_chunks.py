import os
from modules.neo4j_skoda_graphrag import Neo4jSkodaGraphRAG

OPENAI_API_KEY = "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"

NEO4J_URI="neo4j+s://4a20633d.databases.neo4j.io"
NEO4J_USERNAME="neo4j"
NEO4J_PASSWORD="ss3o_V9DirgVa5pKFrqGgfonE89KAJy-zFjylzD2Fxw"
NEO4J_DATABASE="neo4j"

rag = Neo4jSkodaGraphRAG(
    neo4j_uri=NEO4J_URI,
    neo4j_user=NEO4J_USERNAME,
    neo4j_password=NEO4J_PASSWORD,
    openai_api_key=OPENAI_API_KEY,
    enabled=True,
    neo4j_db=NEO4J_DATABASE,
)

count = rag.generate_chunks_from_graph(source="GRAPH_TRIM", reset=True)
print("Üretilen chunk sayısı:", count)

rag.close()
