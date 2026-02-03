# modules/neo4j_skoda_rag.py
import os
import re
from typing import List, Tuple, Optional

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import TokenTextSplitter
from langchain_community.graphs import Neo4jGraph
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_community.vectorstores import Neo4jVector
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores.neo4j_vector import remove_lucene_chars
import logging
# ---- Guard: sadece Skoda kapsamı ----
SKODA_MODELS = {
    "fabia", "scala", "kamiq", "karoq", "kodiaq",
    "octavia", "superb", "enyaq", "elroq"
}

def is_skoda_question(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    if "skoda" in t or "škoda" in t or "yüce auto" in t or "yuce auto" in t:
        return True
    return any(m in t for m in SKODA_MODELS)

class Entities(BaseModel):
    names: List[str] = Field(..., description="Named entities (person/org/product/model) in the question")

def generate_full_text_query(input_str: str) -> str:
    words = [el for el in remove_lucene_chars(input_str).split() if el]
    if not words:
        return ""
    q = ""
    for w in words[:-1]:
        q += f" {w}~2 AND"
    q += f" {words[-1]}~2"
    return q.strip()

class Neo4jSkodaRAG:
    """
    Neo4j GraphRAG (Skoda-only):
    - Ingest: SkodaKB.md -> chunks -> LLMGraphTransformer -> Neo4jGraph
    - Retrieve: entity fulltext + hybrid vector search
    - Answer: constrained to Skoda domain
    """

    def __init__(
        self,
        *,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        openai_api_key: str,
        llm_model: str = "gpt-4o-mini",
        embed_model: str = "text-embedding-3-small",
        enabled: bool = True,
    ):
        self.enabled = enabled
        if not enabled:
            return

        os.environ["OPENAI_API_KEY"] = openai_api_key

        self.graph = Neo4jGraph(
            url=neo4j_uri,
            username=neo4j_user,
            password=neo4j_password
        )

        self.llm = ChatOpenAI(temperature=0, model=llm_model)
        self.embed = OpenAIEmbeddings(model=embed_model)

        # Entity extractor chain
        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "Extract entities ONLY if they are relevant to Skoda cars, trims, features, or people."),
                ("human", "Extract entities from: {question}")
            ]
        )
        self.entity_chain = prompt | self.llm.with_structured_output(Entities)

        # Indeksleri garanti et
        self._ensure_indexes()

        # Vector index (Document label + text prop)
        self.vector_index = Neo4jVector.from_existing_graph(
            self.embed,
            search_type="hybrid",
            node_label="Document",
            text_node_properties=["text"],
            embedding_node_property="embedding",
        )

    def _ensure_indexes(self):
        # Entity fulltext index (id alanında arar)
        self.graph.query(
            "CREATE FULLTEXT INDEX entity IF NOT EXISTS FOR (e:__Entity__) ON EACH [e.id]"
        )

    def ingest_skoda_kb_markdown(self, md_path: str, *, max_docs: int = 1):
        """
        md_path: örn. static/kb/SkodaKB.md
        """
        if not self.enabled:
            return

        loader = TextLoader(md_path, encoding="utf-8")
        raw_docs = loader.load()[:max_docs]

        splitter = TokenTextSplitter(chunk_size=512, chunk_overlap=24)
        docs = splitter.split_documents(raw_docs)

        transformer = LLMGraphTransformer(llm=self.llm)
        graph_docs = transformer.convert_to_graph_documents(docs)

        self.graph.add_graph_documents(
            graph_docs,
            baseEntityLabel=True,
            include_source=True,
        )

        # Neo4jVector.from_existing_graph kullandığın için:
        # - Document.text üzerinden embedding'leri hesaplayıp embedding property'ye yazar.
        # (Aynı dokümanı tekrar ingest ediyorsan duplicate oluşabilir; istersen önce temizleme ekleriz.)

    def _structured_retriever(self, question: str) -> str:
        """
        Entity fulltext -> komşuluk ilişkileri (kısa graph context)
        """
        if not self.enabled:
            return ""

        out = []
        entities = self.entity_chain.invoke({"question": question})
        for ent in (entities.names or []):
            q = generate_full_text_query(ent)
            if not q:
                continue
            rows = self.graph.query(
                """
                CALL db.index.fulltext.queryNodes('entity', $query, {limit:2})
                YIELD node, score
                CALL {
                  WITH node
                  MATCH (node)-[r]->(neighbor)
                  RETURN node.id + ' - ' + type(r) + ' -> ' + neighbor.id AS output
                  UNION ALL
                  WITH node
                  MATCH (node)<-[r]-(neighbor)
                  RETURN neighbor.id + ' - ' + type(r) + ' -> ' + node.id AS output
                }
                RETURN output LIMIT 50
                """,
                {"query": q},
            )
            out.extend([r["output"] for r in rows if r.get("output")])
        return "\n".join(out).strip()
    def ensure_fulltext_index(self):
        # hangi label var? adaylardan ilk bulunanı seç
        label_candidates = ["Entity", "SkodaEntity", "Skoda_Entity"]
        with self.driver.session(database=self.db) as s:
            labels = [r["label"] for r in s.run("CALL db.labels() YIELD label RETURN label")]
            chosen = next((lb for lb in label_candidates if lb in labels), None)
            if not chosen:
                # hiçbiri yoksa en çok kullanılan label'ı seçmek için basit bir fallback
                chosen = labels[0] if labels else None
            if not chosen:
                return

            # önce minimal property ile kur (name varsa)
            # name yoksa text/title vb. için senin graph yapına göre uyarlaman gerekir
            s.run(f"CREATE FULLTEXT INDEX skoda_entity IF NOT EXISTS FOR (e:`{chosen}`) ON EACH [e.name]")
            s.run("CALL db.awaitIndexes()")

    def answer(self, question: str, chat_history: Optional[List[Tuple[str, str]]] = None) -> str:
        if not self.enabled:
            return ""
        if not is_skoda_question(question):
            return "Üzgünüm, yalnızca Škoda ve Yüce Auto ile ilgili konularda yardımcı olabilirim."

        structured = self._structured_retriever(question)
        unstructured = [d.page_content for d in self.vector_index.similarity_search(question, k=4)]

        context = f"""[STRUCTURED]
    
{structured}

[UNSTRUCTURED]
{"\n\n".join(unstructured)}
""".strip()

        sys = (
            "Sen Škoda Türkiye dijital satış danışmanısın.\n"
            "KURAL: SADECE verilen CONTEXT'e dayanarak cevap ver.\n"
            "- Škoda dışı marka/model/konu hakkında cevap verme.\n"
            "- Context'te yoksa 'Bu bilgi KB’de yok.' de.\n"
            "- Kısa ve net: 2–6 cümle.\n"
        )

        # chat_history istersen burada da kullanırız (şimdilik opsiyonel)
        msg = f"CONTEXT:\n{context}\n\nSoru:\n{question}"

        resp = self.llm.invoke(
            [
                {"role": "system", "content": sys},
                {"role": "user", "content": msg},
            ]
        )
        return (getattr(resp, "content", "") or "").strip()
