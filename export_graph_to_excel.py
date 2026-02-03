import os
import pandas as pd
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

# ✅ .env oku (varsa)
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=True)
except Exception:
    pass

# ---- Env (senin kullandığın isimlerle uyumlu) ----
NEO4J_URI = (os.getenv("NEO4J_URI") or "").strip()
NEO4J_USER = (os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER") or "neo4j").strip()
NEO4J_PASSWORD = (os.getenv("NEO4J_PASSWORD") or "").strip()
NEO4J_DB = (os.getenv("NEO4J_DATABASE") or os.getenv("NEO4J_DB") or "neo4j").strip()

OUT_XLSX = os.getenv("OUT_XLSX", "neo4j_graph_export4.xlsx")
LIMIT_NODES = int(os.getenv("LIMIT_NODES", "20000"))
LIMIT_EDGES = int(os.getenv("LIMIT_EDGES", "50000"))

def _require_env():
    missing = []
    if not NEO4J_URI:
        missing.append("NEO4J_URI")
    if not NEO4J_PASSWORD:
        missing.append("NEO4J_PASSWORD")
    if missing:
        raise RuntimeError(
            f"Eksik env: {', '.join(missing)}\n"
            f"Çözüm:\n"
            f"1) PowerShell'de set et: $env:NEO4J_URI='...' ; $env:NEO4J_PASSWORD='...'\n"
            f"veya\n"
            f"2) Bu klasöre .env koy: NEO4J_URI=... / NEO4J_PASSWORD=...\n"
        )

def run_query(driver, cypher: str, params=None):
    params = params or {}
    with driver.session(database=NEO4J_DB) as s:
        res = s.run(cypher, params)
        return [r.data() for r in res]

def main():
    _require_env()

    try:
        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_lifetime=60 * 30,
        )
    except Exception as e:
        raise RuntimeError(f"Driver oluşturulamadı: {e}")

    # Bağlantı testi
    try:
        with driver.session(database=NEO4J_DB) as s:
            s.run("RETURN 1 AS ok").single()
    except AuthError:
        raise RuntimeError("Kimlik doğrulama hatası: kullanıcı adı/şifre yanlış.")
    except ServiceUnavailable as e:
        raise RuntimeError(f"Bağlantı hatası (URI/Network): {e}")
    except Exception as e:
        raise RuntimeError(f"Bağlantı testi başarısız: {e}")

    # 1) Nodes (property uyarıları olmasın diye minimum kolon)
    nodes_q = """
    MATCH (n)
    RETURN elementId(n) AS eid,
           labels(n) AS labels,
           keys(n) AS prop_keys
    LIMIT $lim
    """
    nodes = run_query(driver, nodes_q, {"lim": LIMIT_NODES})

    # 2) All Edges
    edges_q = """
    MATCH (a)-[r]->(b)
    RETURN elementId(a) AS from_eid,
           labels(a) AS from_labels,
           type(r) AS rel_type,
           elementId(b) AS to_eid,
           labels(b) AS to_labels,
           keys(r) AS rel_prop_keys
    LIMIT $lim
    """
    edges_all = run_query(driver, edges_q, {"lim": LIMIT_EDGES})

    # 3) İlişki tipleri (MENTIONS var mı görmek için)
    reltypes = run_query(driver, "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType")

    # DataFrame + Excel
    df_nodes = pd.DataFrame(nodes)
    df_edges = pd.DataFrame(edges_all)
    df_reltypes = pd.DataFrame(reltypes)

    for df in [df_nodes, df_edges]:
        for col in df.columns:
            df[col] = df[col].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        df_nodes.to_excel(writer, sheet_name="nodes", index=False)
        df_edges.to_excel(writer, sheet_name="edges_all", index=False)
        df_reltypes.to_excel(writer, sheet_name="relationship_types", index=False)

    driver.close()
    print(f"✅ Export OK: {OUT_XLSX}")
    print(f"DB: {NEO4J_DB} | Nodes: {len(df_nodes)} | Edges: {len(df_edges)}")

if __name__ == "__main__":
    main()
