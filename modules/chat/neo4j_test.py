from neo4j import GraphDatabase
import os

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
pwd = os.getenv("NEO4J_PASSWORD")
db  = os.getenv("NEO4J_DB", "neo4j")

driver = GraphDatabase.driver(uri, auth=(user, pwd))
with driver.session(database=db) as s:
    print(s.run("RETURN 1 AS ok").single()["ok"])
driver.close()
