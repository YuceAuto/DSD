import os
import sys

# ============================================================
# 1) Proje root'u sys.path'e ekle (modules import'u için)
# ============================================================
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# (Opsiyonel) .env dosyan varsa otomatik yükle
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=True)
except Exception:
    pass

from modules.neo4j_skoda_graphrag import Neo4jSkodaGraphRAG

# ============================================================
# 2) Env kontrol (None gelmesin)
# ============================================================
NEO4J_URI = (os.getenv("NEO4J_URI") or "").strip()
NEO4J_USERNAME = (os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER") or "").strip()
NEO4J_PASSWORD = (os.getenv("NEO4J_PASSWORD") or "").strip()
NEO4J_DB = (os.getenv("NEO4J_DB") or "neo4j").strip()

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()

missing = []
if not NEO4J_URI: missing.append("NEO4J_URI")
if not NEO4J_USERNAME: missing.append("NEO4J_USERNAME (or NEO4J_USER)")
if not NEO4J_PASSWORD: missing.append("NEO4J_PASSWORD")
if not OPENAI_API_KEY: missing.append("OPENAI_API_KEY")

if missing:
    raise RuntimeError(
        "Eksik environment variable(lar): " + ", ".join(missing) + "\n\n"
        "PowerShell örneği:\n"
        "  $env:OPENAI_API_KEY='sk-...'\n"
        "  $env:NEO4J_URI='neo4j+s://...'\n"
        "  $env:NEO4J_USERNAME='neo4j'\n"
        "  $env:NEO4J_PASSWORD='...'\n"
        "  python build_chunks_once.py\n"
    )

# ============================================================
# 3) Chunk üret + ingest
# ============================================================
MODEL_ID = os.getenv("MODEL_ID", "octavia").strip().lower()
RESET = os.getenv("RESET", "1").strip() == "1"          # 1 ise eski Chunk'ları siler
SOURCE = os.getenv("SOURCE", "GraphBlocks").strip()

print("== CONFIG ==")
print("MODEL_ID:", MODEL_ID)
print("RESET:", RESET)
print("SOURCE:", SOURCE)

rag = Neo4jSkodaGraphRAG(
    neo4j_uri=NEO4J_URI,
    neo4j_user=NEO4J_USERNAME,
    neo4j_password=NEO4J_PASSWORD,
    openai_api_key=OPENAI_API_KEY,
    enabled=True,
    neo4j_db=NEO4J_DB,
)

# Bu fonksiyonları neo4j_skoda_graphrag.py içine class method olarak eklemiş olmalısın
rag.ingest_from_graph_blocks(MODEL_ID, reset=RESET, source=SOURCE)
rag.close()

print("OK ✅")
