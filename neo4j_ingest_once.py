import os, sys 
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))  # "modules" importu için
load_dotenv(ROOT / ".env", override=True)

from modules.neo4j_skoda_graphrag import Neo4jSkodaGraphRAG

def must_env(key: str) -> str:
    v = os.getenv(key)
    if not v:
        raise RuntimeError(f"ENV eksik: {key} ('.env' içine ekle veya set et)")
    return v

rag = Neo4jSkodaGraphRAG(
    neo4j_uri=must_env("NEO4J_URI"),
    neo4j_user=must_env("NEO4J_USER"),
    neo4j_password=must_env("NEO4J_PASSWORD"),
    openai_api_key=must_env("OPENAI_API_KEY"),
    enabled=True,
    neo4j_db=os.getenv("NEO4J_DB", "neo4j"),
)

kb_path = ROOT / "static" / "kb" / "SkodaKB.md"
rag.ingest_documents_only(str(kb_path), reset=True)  # <-- ÖNEMLİ: Document'leri basar
print("✅ INGEST OK")
