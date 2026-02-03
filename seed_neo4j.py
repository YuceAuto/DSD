import os
from dotenv import load_dotenv, find_dotenv

from modules.neo4j_skoda_graphrag import Neo4jSkodaGraphRAG

def getenv_any(*keys, default=None):
    for k in keys:
        v = os.getenv(k)
        if v and str(v).strip():
            return v.strip()
    return default

def main():
    # ✅ .env yükle (app.py’de yaptığını burada da yapmalısın)
    load_dotenv(find_dotenv(usecwd=True), override=True)

    # ✅ Env isimleri projeden projeye değişiyor olabilir → fallback’lı al
    neo4j_uri  = getenv_any("NEO4J_URI", "NEO4J_BOLT_URL", "NEO4J_URL")
    neo4j_user = getenv_any("NEO4J_USERNAME", "NEO4J_USER")
    neo4j_pass = getenv_any("NEO4J_PASSWORD", "NEO4J_PASS", "NEO4J_PW")
    neo4j_db   = getenv_any("NEO4J_DB", "NEO4J_DATABASE", default="neo4j")
    openai_key = getenv_any("OPENAI_API_KEY")

    # Fail-fast (NoneType yerine net hata)
    missing = [k for k,v in {
        "NEO4J_URI": neo4j_uri,
        "NEO4J_USERNAME/NEO4J_USER": neo4j_user,
        "NEO4J_PASSWORD": neo4j_pass,
        "OPENAI_API_KEY": openai_key,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"❌ Eksik ENV: {missing}. .env yüklenmiyor veya değişken isimleri farklı.")

    print("✅ ENV OK:", neo4j_uri, neo4j_user, neo4j_db)

    rag = Neo4jSkodaGraphRAG(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_pass,
        openai_api_key=openai_key,
        enabled=True,
        neo4j_db=neo4j_db,
    )

    # SkodaKB yolu (ister env’den ister sabit ver)
    kb_path = getenv_any(
        "SKODAKB_PATH",
        default=r"C:\Users\yuceuipathadmin\Documents\UrunBot\static\kb\SkodaKB.md"
    )

    # ✅ RAG Document node’larını bas (reset=True ilk sefer için mantıklı)
    rag.ingest_skodakb_by_model(kb_path, reset=True, source="SkodaKB")

    rag.close()
    print("✅ Seeding bitti.")

if __name__ == "__main__":
    main()
