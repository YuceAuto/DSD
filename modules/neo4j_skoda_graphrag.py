import os  
import re
import time
from typing import List, Tuple, Optional

from pydantic import BaseModel, Field
from neo4j import GraphDatabase

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_text_splitters import TokenTextSplitter
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_neo4j import Neo4jGraph
from langchain_community.vectorstores import Neo4jVector
import json
import time
from neo4j.exceptions import ServiceUnavailable, SessionExpired, DatabaseError
from neo4j.exceptions import DatabaseError

import json
import math

try:
    import pyodbc
except Exception:
    pyodbc = None
# deprecation fix
from langchain_neo4j.vectorstores.neo4j_vector import remove_lucene_chars
import logging


class Entities(BaseModel):
    names: List[str] = Field(..., description="Metinde geçen kişi/organizasyon/entity isimleri")

OTHER_BRANDS = [
    "bmw","mercedes","audi","volkswagen","vw","tesla","toyota","honda","hyundai",
    "kia","ford","renault","peugeot","citroen","opel","fiat","nissan","volvo"
]
def generate_full_text_query(s: str) -> str:
    words = [w for w in remove_lucene_chars(s).split() if w]
    if not words:
        return ""
    # fuzzy (~2) AND zinciri
    return " AND ".join([f"{w}~2" for w in words]).strip()


class Neo4jSkodaGraphRAG:
    """
    - LLMGraphTransformer ile graph'e entity/relation yaz
    - Neo4jVector hybrid arama (Document.text + embedding)
    - Fulltext entity index ile structured neighbor traversal
    """
    _WANTS_TABLE_RE = re.compile(r"\b(tablo|tabloda)\b", re.IGNORECASE)
    _WANTS_LIST_RE = re.compile(r"\b(listele|liste halinde)\b", re.IGNORECASE)
    _COMPARE_NOISE = re.compile(
        r"\b(vs|versus|arasında|hangisi|kıyas|kiyas|karşılaştır|karsilastir|fark|mı|mi|mu|mü)\b",
        re.IGNORECASE
    )
    _GENERAL_INFO_RE = re.compile(
        r"\b(hakkında|ile ilgili|bilgi ver|bilgi verebilir misin|tanıt|anlat|nedir|genel)\b",
        re.IGNORECASE
    )
    _RECORD_LINE_RE = re.compile(r"(?im)^\s*(?:\*\*)?kayıt(?:\*\*)?\s*:\s*(.+?)\s*$")

    # Neo4jSkodaGraphRAG class içine ekle
    # ✅ BUNU EKLE (class scope!)
    _FEATURE_Q_RE = re.compile(
        r"\b(var mı|varmi|mevcut mu|bulunuyor mu|oluyor mu)\b",
        re.IGNORECASE
    )
    _VARIANT_HINT_RE = re.compile(r"\b(e[-\s]?sportline|85x|85\b|60\b|coupe)\b", re.IGNORECASE)
    _TRIM_ALIASES = {
        # --- Binek / SUV (TR) ---
        "elite": [
            "elite",
        ],
        "premium": [
            "premium",
        ],
        "prestige": [
            "prestige",
        ],
        "sportline": [
            "sportline", "sport line", "sport-line",
        ],
        "monte carlo": [
            "monte carlo", "montecarlo", "monte-carlo", "mc",
        ],
        "rs": [
            "rs", "vrs", "v rs", "v-rs",
        ],

        # --- L&K Crystal (TR - Superb) ---
        "l&k crystal": [
            "l&k crystal", "l & k crystal", "l and k crystal",
            "lk crystal", "l k crystal",
            "laurin & klement crystal", "laurin klement crystal",
            "l&k", "l & k", "laurin & klement", "laurin klement",
        ],

        # --- Elektrikli (TR) ---
        "e-prestige": [
            "e-prestige", "e prestige", "eprestige", "e_prestige",
        ],
        "e-sportline": [
            "e-sportline", "e sportline", "esportline", "e_sportline",
        ],
        "e-sportline phev": [
            "e-sportline phev", "e sportline phev", "esportline phev",
            "e-sportline p hev", "e sportline p hev",
        ],

        # (opsiyonel) Kullanıcı sadece "pHEV" yazarsa yakalamak istersen:
        # "phev": ["phev", "p hev", "plug-in", "plug in"],
    }
    # Neo4jSkodaGraphRAG içine (class scope)
    _MODEL_TOKENS_RE = re.compile(r"\b(fabia|scala|kamiq|karoq|kodiaq|octavia|superb|enyaq|elroq|skoda|škoda)\b", re.IGNORECASE)

    _TR_BOILERPLATE_RE = re.compile(
        r"\b(var mı|varmi|mevcut mu|bulunuyor mu|oluyor mu|ile ilgili|hakkında|söyler misin|bakabilir misin|diyor mu|nedir)\b",
        re.IGNORECASE
    )
    _BAGAJ_PAIR_RE = re.compile(
    r"(\d{3,4})\s*/\s*(\d{3,4})\s*(?:litre|l)\b", re.IGNORECASE
)
    _COMBI_HINT_RE = re.compile(r"\b(combi|kombi|station|wagon|estate)\b", re.IGNORECASE)
    _SEDAN_HINT_RE = re.compile(r"\b(sedan|liftback|lift back|lift-back)\b", re.IGNORECASE)
    def _bagaj_retrieve_cypher(self, *, model_id: str, trims: list[str]) -> dict:
        if not model_id:
            return {"sedan": None, "combi": None, "rows": []}

        trim_terms = [(t or "").lower() for t in (trims or []) if (t or "").strip()]

        cypher = """
        MATCH (c:Chunk)
        WITH c,
            toLower(coalesce(c.text,'')) AS tl,
            replace(toLower(coalesce(c.text,'')),'.','') AS tl_nodot
        WHERE tl CONTAINS $model_id
        AND tl CONTAINS 'bagaj'
        AND (tl_nodot CONTAINS '1555' OR tl_nodot CONTAINS '1700')
        AND (
            $has_trim = false OR
            all(t IN $trim_terms WHERE tl CONTAINS t)
        )
        RETURN coalesce(c.text,'') AS text
        LIMIT 50
        """

        rows = self._run_cypher_traced(self._uid(), cypher, {
            "model_id": model_id.lower(),
            "has_trim": bool(trim_terms),
            "trim_terms": trim_terms,
        }) or []

        # 1.555 / 1555 gibi noktalı yazımları normalize ederek parse et
        sedan = None
        combi = None
        pair_re = re.compile(r"(\d{3,4})\s*/\s*(\d{1,2}\.?\d{3})\s*(?:litre|l)\b", re.IGNORECASE)

        for r in rows:
            txt = (r.get("text") or "")
            txt_nd = txt.replace(".", "")  # 1.555 -> 1555
            for a, b in re.findall(r"(\d{3,4})\s*/\s*(\d{4})\s*(?:litre|l)\b", txt_nd, flags=re.IGNORECASE):
                a_i = int(a); b_i = int(b)
                if b_i == 1555:
                    sedan = (a_i, b_i)
                elif b_i == 1700:
                    combi = (a_i, b_i)

        return {"sedan": sedan, "combi": combi, "rows": rows}
    def _bagaj_dual_body_compact(self, model_id: str, trims: list[str]) -> list[dict]:
        trims_l = [(t or "").strip().lower() for t in (trims or []) if (t or "").strip()]
        cypher = """
        MATCH (m:CAR_MODEL {id:$model_id})-[:HAS_TRIM]->(t:TRIM)
        WHERE $has_trim = false OR any(x IN $trims WHERE toLower(coalesce(t.name,t.id,'')) CONTAINS x)
        MATCH (t)-[:HAS_TECH_SPEC]->(s:TECH_SPEC)
        WHERE toLower(coalesce(s.feature,'')) CONTAINS 'bagaj'
        AND toLower(coalesce(s.body_type,'')) IN ['sedan','combi']
        WITH
        coalesce(t.name,t.id,'') AS trim_name,
        toLower(coalesce(s.body_type,'')) AS body_type,
        max(toInteger(coalesce(s.open_l,0)))   AS open_l,
        max(toInteger(coalesce(s.folded_l,0))) AS folded_l
        WITH trim_name,
            collect({body_type: body_type, open_l: open_l, folded_l: folded_l}) AS bodies
        WITH trim_name,
            [b IN bodies WHERE b.body_type='sedan'][0] AS sedan,
            [b IN bodies WHERE b.body_type='combi'][0] AS combi
        RETURN
        trim_name,
        sedan.open_l  AS sedan_open_l,
        sedan.folded_l AS sedan_folded_l,
        combi.open_l  AS combi_open_l,
        combi.folded_l AS combi_folded_l
        ORDER BY trim_name;
        """
        return self._run_cypher_traced(self._uid(), cypher, {
            "model_id": model_id,
            "has_trim": bool(trims_l),
            "trims": trims_l
        }) or []

    def _bagaj_dual_body_cypher(self, model_id: str, trims: list[str]) -> list[dict]:
        trims_l = [(t or "").strip().lower() for t in (trims or []) if (t or "").strip()]
        cypher = """
        MATCH (m:CAR_MODEL {id:$model_id})-[:HAS_TRIM]->(t:TRIM)
        WHERE $has_trim = false OR any(x IN $trims WHERE toLower(coalesce(t.name,t.id,'')) CONTAINS x)
        MATCH (t)-[:HAS_TECH_SPEC]->(s:TECH_SPEC)
        WHERE toLower(coalesce(s.feature,'')) CONTAINS 'bagaj'
        AND toLower(coalesce(s.body_type,'')) IN ['sedan','combi']
        RETURN
        coalesce(t.name,t.id,'') AS trim_name,
        toLower(coalesce(s.body_type,'')) AS body_type,
        toInteger(coalesce(s.open_l,0))   AS open_l,
        toInteger(coalesce(s.folded_l,0)) AS folded_l,
        coalesce(s.value,'') AS value
        ORDER BY trim_name, body_type;
        """
        return self._run_cypher_traced(self._uid(), cypher, {
            "model_id": model_id,
            "has_trim": bool(trims_l),
            "trims": trims_l
        }) or []

    def _bagaj_from_techspec(self, model_id: str, trims: list[str]):
        trim_where, trim_params = self._match_trim_clause(trims)

        cypher = f"""
        MATCH (m:CAR_MODEL {{id:$model_id}})
        OPTIONAL MATCH (m)-[:HAS_TRIM]->(t:TRIM)
        WHERE 1=1 {trim_where}
        MATCH (t)-[:HAS_TECH_SPEC]->(s:TECH_SPEC)
        WHERE toLower(coalesce(s.feature,'')) CONTAINS 'bagaj'
        RETURN
        coalesce(t.name,t.id,'') AS trim_name,
        coalesce(s.feature,'')   AS feature,
        coalesce(s.body_type,'') AS body_type,
        coalesce(s.open_l,'')    AS open_l,
        coalesce(s.folded_l,'')  AS folded_l,
        coalesce(s.value,'')     AS value
        """

        rows = self._run_cypher_traced(self._uid(), cypher, {"model_id": model_id, **trim_params}) or []
        return rows

    def _split_bagaj_lines(self, text: str):
        sedan_lines, combi_lines, unknown = [], [], []
        for ln in (text or "").splitlines():
            s = ln.strip()
            if not s:
                continue

            low = s.lower()

            # ✅ 1) RAKAMLA AYIR (en sağlamı)
            # Sedan/Liftback tipik: 600 / 1555
            if "1555" in low or re.search(r"\b600\s*/\s*1555\b", low):
                sedan_lines.append(ln)
                continue

            # Combi tipik: 640 / 1700
            if "1700" in low or re.search(r"\b640\s*/\s*1700\b", low):
                combi_lines.append(ln)
                continue

            # ✅ 2) Kelime ipucu ile ayır (varsa)
            if self._COMBI_HINT_RE.search(s):
                combi_lines.append(ln)
                continue
            if self._SEDAN_HINT_RE.search(s):
                sedan_lines.append(ln)
                continue

            # ✅ 3) Bagaj satırı gibi ama belirsizse unknown
            if self._BAGAJ_PAIR_RE.search(s) or ("bagaj" in low and ("litre" in low or " l" in low)):
                unknown.append(ln)

        return sedan_lines, combi_lines, unknown


    def _extract_feature_query(self, user_question: str) -> str:
        """
        Fulltext'e gidecek 'özellik araması' metnini çıkarır.
        Örn: 'octavia elite de head up display var mı' -> 'head up display'
        """
        q = (user_question or "").strip()
        if not q:
            return ""

        # 1) modeli sil
        q = self._MODEL_TOKENS_RE.sub(" ", q)

        # 2) trim kelimelerini sil (elite/premium vb.)
        #    (TRIM_ALIASES içindeki tüm anahtarları ve aliasları çıkar)
        ql = q.lower()
        for trim_key, aliases in self._TRIM_ALIASES.items():
            for a in aliases:
                if a:
                    ql = ql.replace(a.lower(), " ")
        q = ql

        # 3) var mı / mevcut mu gibi boilerplate sil
        q = self._TR_BOILERPLATE_RE.sub(" ", q)

        # 4) fazla boşluk
        q = re.sub(r"\s+", " ", q).strip()

        # Çok kısaldıysa fallback: hiç yoksa boş döndür
        return q

    def _feature_retrieve_fulltext(self, *, model_id: str, trims: list[str], question: str,
                               limit_hits: int = 25, limit_rows: int = 200,
                               rel_whitelist: list[str] | None = None):
        if not model_id or not question:
            return {"hits": [], "text": ""}

        raw = (question or "").strip()

        plain_q = (self._extract_feature_query(raw) or raw).lower()
        plain_q = re.sub(r"\b(da|de|ta|te)\b", " ", plain_q)
        plain_q = re.sub(r"\s+", " ", plain_q).strip()

        trim_where, trim_params = self._match_trim_clause(trims)

        cypher = f"""
        MATCH (m:CAR_MODEL {{id:$model_id}})
        OPTIONAL MATCH (m)-[:HAS_TRIM]->(t:TRIM)
        WHERE 1=1 {trim_where}

        CALL (m, t) {{
        WITH m, t
        MATCH (t)-[r]->(n)
        WHERE $has_trim = true AND type(r) IN $rel_whitelist
        RETURN coalesce(t.name,t.id,'') AS trim_name,
                type(r) AS rel_type,
                coalesce(r.availability, r.type, '') AS availability,
                n AS n

        UNION

        WITH m
        MATCH (m)-[:HAS_TRIM]->(t2:TRIM)-[r]->(n)
        WHERE $has_trim = false AND type(r) IN $rel_whitelist
        RETURN coalesce(t2.name,t2.id,'') AS trim_name,
                type(r) AS rel_type,
                coalesce(r.availability, r.type, '') AS availability,
                n AS n
        }}
        WITH trim_name, rel_type, availability, n
        WHERE n IS NOT NULL AND NOT 'Chunk' IN labels(n)

        WITH trim_name, rel_type, availability,
            labels(n) AS labels,
            coalesce(n.feature,n.name,n.description,n.text,'') AS feature,
            coalesce(n.value,'') AS value,
            toLower(
                coalesce(n.feature,'') + ' ' +
                coalesce(n.name,'') + ' ' +
                coalesce(n.description,'') + ' ' +
                coalesce(n.text,'') + ' ' +
                coalesce(n.value,'')
            ) AS hay
        WHERE hay CONTAINS $q

        RETURN trim_name, rel_type, availability, labels, feature, value
        LIMIT $limit
        """
        # ✅ DB’de gerçekten olan relation’lara göre default whitelist
        rel_whitelist = rel_whitelist or [
            "HAS_EQUIPMENT",
            "HAS_FEATURE",
            "HAS_TECH_SPEC",
            "HAS_OPTION",
            "HAS_OPTION_PRICE",
            "HAS_PRICE",
            "HAS_COLOR",
            "HAS_COLOR_NAME",
            "HAS_COLOR_CODE",
            "HAS_COLOR_TYPE",
            "HAS_INTERIOR",
            "HAS_MULTIMEDIA_EQUIPMENT",
            "HAS_WHEEL_PACKAGE",
            "REQUIRES",
        ]


        params = {
            "q": plain_q,
            "model_id": model_id,
            "limit": int(limit_rows),
            "has_trim": bool(trims),
            "rel_whitelist": rel_whitelist,   # 🔥 artık burası direkt rel_whitelist
            **trim_params
        }

        rows = self._run_cypher_traced(self._uid(), cypher, params) or []

        # text üret
        text_lines = []
        for r in rows:
            trim_name = (r.get("trim_name") or "").strip() or "-"
            labels = r.get("labels") or []
            feature = (r.get("feature") or "").strip()
            value = (r.get("value") or "").strip()
            cat = "EQUIPMENT" if "EQUIPMENT" in labels else (labels[0] if labels else "FEATURE")
            fv = f"{feature}: {value}".strip(": ").strip() if value else feature
            if fv:
                text_lines.append(f"Kayıt: {model_id} | - | {trim_name} | {cat} | {fv}")

        return {"hits": rows, "text": "\n".join(text_lines).strip(), "plain_q": plain_q}



        # --- Kategori ipuçları (özellikle "var mı" sorularında TECH_SPEC'e düşmesin) ---
    _EQUIPMENT_HINTS = [
        "cam tavan", "panoramik", "panoramik tavan", "sunroof", "tavan",
        "head up", "head-up", "hud", "head up display",
        "koltuk ısıt", "koltuk isit", "ısıtmalı koltuk", "isitmali koltuk",
        "adaptif hız", "adaptif hiz", "acc",
        "şerit", "serit", "lane", "travel assist", "park assist", "kamera", "elektrikli",
    ]
    _SAFETY_HINTS = [
        "airbag", "abs", "esp", "adas", "acil fren", "front assist",
        "blind spot", "kör nokta", "kor nokta", "side assist"
    ]
    _MULTIMEDIA_HINTS = [
        "carplay", "android auto", "multimedya", "ekran", "navigasyon",
        "ses sistemi", "usb", "bluetooth"
    ]
    _INTERIOR_HINTS = [
        "alcantara", "deri", "koltuk", "döşeme", "doseme", "ambiyans", "ambient", "iç", "ic"
    ]
    _OPTION_HINTS = [
        "opsiyon", "opsiyonel", "fiyat", "price", "paket", "paketi"
    ]
    def _wheel_retrieve(self, model_id: str, trims: list[str], limit: int = 200):
        trim_where, trim_params = self._match_trim_clause(trims)
        cypher = f"""
        MATCH (m:CAR_MODEL {{id:$model_id}})
        OPTIONAL MATCH (m)-[:HAS_TRIM]->(t:TRIM)
        WHERE 1=1 {trim_where}

        OPTIONAL MATCH (t)-[:HAS_WHEEL_PACKAGE]->(wp:WheelPackage)
        OPTIONAL MATCH (wp)-[:REQUIRES]->(w:WHEEL)

        WITH m,t, collect(DISTINCT w) AS ws
        UNWIND ws AS node
        WITH m,t,node WHERE node IS NOT NULL
        RETURN
        m.id AS model_id,
        coalesce(t.name,t.id,'') AS trim_name,
        'WHEEL' AS category,
        coalesce(node.name,node.feature,node.code,node.description,'') AS feature,
        coalesce(node.value,node.data,'') AS value
        LIMIT $limit
        """
        rows = self._run_cypher_traced(self._uid(), cypher, {"model_id": model_id, "limit": limit, **trim_params}) or []
        # text formatına çevir
        lines = []
        for r in rows:
            fv = r["feature"] if not r["value"] else f'{r["feature"]}: {r["value"]}'
            lines.append(f'Kayıt: {model_id} | - | {r["trim_name"] or "-"} | WHEEL | {fv}')
        return {"hits": rows, "text": "\n".join(lines).strip()}

    def _infer_category(self, question: str) -> str | None:
        ql = (question or "").lower()

        # teknik
        if "teknik" in ql or "tech" in ql:
            return "TECH_SPEC"

        # net ipuçları (cam tavan / HUD gibi)
        if any(k in ql for k in self._EQUIPMENT_HINTS):
            return "EQUIPMENT"
        if any(k in ql for k in self._SAFETY_HINTS):
            return "SAFETY"
        if any(k in ql for k in self._MULTIMEDIA_HINTS):
            return "MULTIMEDIA"
        if any(k in ql for k in self._INTERIOR_HINTS):
            return "INTERIOR"
        if any(k in ql for k in self._OPTION_HINTS):
            return "OPTION"

        # jant/renk
        if "jant" in ql or "wheel" in ql:
            return "WHEEL"
        if "renk" in ql or "color" in ql:
            return "COLOR"

        # donanım/özellik/paket
        if any(k in ql for k in ["donanım", "donanim", "paket", "özellik", "ozellik", "standart"]):
            return "EQUIPMENT"

        return None

    def _match_trim_clause(self, trims: list[str]) -> tuple[str, dict]:
        """
        trims: ["premium"] gibi _extract_trims_in_text'ten gelen anahtarlar
        TRIM node'larını name/id üzerinden esnek yakalamak için WHERE üretir.
        """
        if not trims:
            return "", {}

        # ör: premium -> "premium"
        # name/id içinde geçsin
        where_parts = []
        params = {}
        for i, t in enumerate(trims):
            key = f"trim{i}"
            params[key] = t.lower()
            where_parts.append(f"(toLower(coalesce(t.name,'')) CONTAINS ${key} OR toLower(coalesce(t.id,'')) CONTAINS ${key})")

        return " AND (" + " OR ".join(where_parts) + ")", params

    def _relation_retrieve(self, *, ql_neo, model_id: str, trims: list[str], category: str, limit: int = 500):
        
        if not model_id or not category:
            return {"hits": [], "text": ""}

        # Trim filtresi (Trim node'unda name ile)
        trim_where, trim_params = self._match_trim_clause(trims)  # t alias'ını kullanıyor; aşağıda t:Trim var

        # --- CATEGORY ROUTING ---
        cat = (category or "").upper()

        # 0) Ortak root (Model -> BodyType -> Trim)
        root = f"""
        MATCH (m:Model)
        WHERE toLower(m.name) CONTAINS toLower($model_id)
        OPTIONAL MATCH (m)-[:HAS_BODY_TYPE]->(b:BodyType)-[:HAS_TRIM]->(t:Trim)
        WHERE 1=1 {trim_where}
        """

        # 1) TECH_SPEC -> Feature (HAS_FEATURE)  [NEW MODEL: value/unit on relationship]
        if cat == "TECH_SPEC":
            cypher = root + """
            OPTIONAL MATCH (t)-[r:HAS_FEATURE]->(f:Feature)
            WITH m, t, f, r
            WHERE f IS NOT NULL
            RETURN
            m.name AS model_id,
            coalesce(t.name,'') AS trim_name,
            'TECH_SPEC' AS category,
            coalesce(f.name,'') AS feature,
            trim(
                coalesce(toString(r.value), '') +
                CASE WHEN coalesce(r.unit,'') <> '' THEN ' ' + r.unit ELSE '' END
            ) AS value
            LIMIT $limit
            """
            rows = self._run_cypher_traced(
                self._uid(),
                cypher,
                {"model_id": model_id, "limit": int(limit), **trim_params}
            ) or []
        
            lines = []
            for r in rows:
                if (r.get("feature") or "").strip():
                    val = (r.get("value") or "").strip()
                    fv = f"{r['feature']}: {val}".strip(": ").strip()
                    lines.append(f"Kayıt: {model_id} | - | {r.get('trim_name','-') or '-'} | TECH_SPEC | {fv}")
            return {"hits": rows, "text": "\n".join(lines).strip()}
        # EQUIPMENT: liste + arama + availability intent
        if cat == "EQUIPMENT":
            def pick_availabilities(ql: str) -> list[str]:
                q = (ql or "").lower()

                # yok / bulunmaz / mevcut değil
                if any(k in q for k in ["yok", "bulunmaz", "mevcut değil", "bulunmuyor"]):
                    return ["NotAvailable"]

                # opsiyonel / isteğe bağlı
                if any(k in q for k in ["opsiyon", "opsiyonel", "isteğe bağlı"]):
                    return ["Optional"]

                # var / vardır / neler var
                if any(k in q for k in ["neler var", "var mı", "vardır", "mevcut"]):
                    return ["Standard"]

                return []  # filtre yok (hepsi)
            question_text = (ql_neo or "")
            availabilities = pick_availabilities(question_text)

            # q: sistemin extractor'ı yoksa en azından soru metnini kullan
            q_raw = (trim_params.get("q") or "").strip()
            if not q_raw:
                q_raw = question_text

            cypher = f"""
            MATCH (m:Model)
            WHERE toLower(m.name) CONTAINS toLower($model_id)

            MATCH (m)-[:HAS_BODY_TYPE]->(b:BodyType)-[:HAS_TRIM]->(t:Trim)
            WHERE 1=1 {trim_where}

            MATCH (t)-[r:HAS_EQUIPMENT]->(e:Equipment)

            WITH m, b, t, r, e,
                trim(coalesce(toString(r.type), '')) AS availability,
                toLower(trim(coalesce(e.name,'') + ' ' + coalesce(e.description,''))) AS hay,
                // q temizle: apostrof ve fazla boşluk
                toLower(trim(replace(replace($q, \"'\", \"\"), '\"', ''))) AS q2

            WHERE (size($availabilities) = 0 OR availability IN $availabilities)
            AND (q2 = '' OR hay CONTAINS q2)

            RETURN
            m.name AS model_id,
            b.name AS body_type,
            coalesce(t.name,'') AS trim_name,
            'EQUIPMENT' AS category,
            coalesce(e.name,'') AS feature,
            availability AS value
            ORDER BY body_type, trim_name, feature
            LIMIT $limit
            """

            params = {
                "model_id": model_id,
                "q": q_raw,
                "availabilities": availabilities,
                "limit": int(limit),
                **trim_params
            }

            rows = self._run_cypher_traced(self._uid(), cypher, params) or []

            lines = []
            for r in rows:
                feat = (r.get("feature") or "").strip()
                if not feat:
                    continue
                bt = r.get("body_type","-") or "-"
                tr = r.get("trim_name","-") or "-"
                val = (r.get("value") or "").strip()
                lines.append(f"Kayıt: {r.get('model_id', model_id)} | {bt} | {tr} | EQUIPMENT | {feat}: {val}".strip())

            return {"hits": rows, "text": "\n".join(lines).strip()}
        

        # 3) OPTION -> Option (HAS_OPTION)
        if cat == "OPTION":
            cypher = root + """
            OPTIONAL MATCH (t)-[:HAS_OPTION]->(o:Option)
            WITH m,t,o WHERE o IS NOT NULL
            RETURN
            m.name AS model_id,
            coalesce(t.name,'') AS trim_name,
            'OPTION' AS category,
            coalesce(o.name, o.code, '') AS feature,
            coalesce(o.category,'') AS value
            LIMIT $limit
            """
            rows = self._run_cypher_traced(self._uid(), cypher, {"model_id": model_id, "limit": int(limit), **trim_params}) or []
            lines = []
            for r in rows:
                feat = (r.get("feature") or "").strip()
                if feat:
                    val = (r.get("value") or "").strip()
                    fv = f"{feat}: {val}".strip(": ").strip() if val else feat
                    lines.append(f"Kayıt: {model_id} | - | {r.get('trim_name','-') or '-'} | OPTION | {fv}")
            return {"hits": rows, "text": "\n".join(lines).strip()}

        # 4) OPTION_PRICE -> OptionPrice (HAS_OPTION -> HAS_PRICE)
        # DB’de HAS_OPTION_PRICE yok; bunun yerine HAS_PRICE var.
        if cat in {"OPTION_PRICE", "PRICE"}:
            cypher = root + """
            OPTIONAL MATCH (t)-[:HAS_OPTION]->(o:Option)-[:HAS_PRICE]->(op:OptionPrice)
            WITH m,t,o,op WHERE op IS NOT NULL
            RETURN
            m.name AS model_id,
            coalesce(t.name,'') AS trim_name,
            'OPTION_PRICE' AS category,
            coalesce(op.option_code, o.code, o.name, '') AS feature,
            // tax + price format
            trim(
                'tax=' + coalesce(toString(op.tax_rate), toString(op.tax_rate_raw), '') +
                ' price=' + coalesce(toString(op.price), toString(op.prices_raw), '')
            ) AS value
            LIMIT $limit
            """
            rows = self._run_cypher_traced(self._uid(), cypher, {"model_id": model_id, "limit": int(limit), **trim_params}) or []
            lines = []
            for r in rows:
                feat = (r.get("feature") or "").strip()
                if feat:
                    val = (r.get("value") or "").strip()
                    lines.append(f"Kayıt: {model_id} | - | {r.get('trim_name','-') or '-'} | OPTION | {feat}: {val}")
            return {"hits": rows, "text": "\n".join(lines).strip()}

        # 5) MULTIMEDIA -> MultimediaEquipment
        if cat == "MULTIMEDIA":
            cypher = root + """
            OPTIONAL MATCH (t)-[:HAS_MULTIMEDIA_EQUIPMENT]->(me:MultimediaEquipment)
            WITH m,t,me WHERE me IS NOT NULL
            RETURN
            m.name AS model_id,
            coalesce(t.name,'') AS trim_name,
            'MULTIMEDIA' AS category,
            coalesce(me.name,'') AS feature,
            trim(coalesce(toString(me.size), toString(me.size_raw), '') + ' ' + coalesce(me.unit,'')) AS value
            LIMIT $limit
            """
            rows = self._run_cypher_traced(self._uid(), cypher, {"model_id": model_id, "limit": int(limit), **trim_params}) or []
            lines = []
            for r in rows:
                feat = (r.get("feature") or "").strip()
                if feat:
                    val = (r.get("value") or "").strip()
                    fv = f"{feat}: {val}".strip(": ").strip() if val else feat
                    lines.append(f"Kayıt: {model_id} | - | {r.get('trim_name','-') or '-'} | MULTIMEDIA | {fv}")
            return {"hits": rows, "text": "\n".join(lines).strip()}

        # 6) INTERIOR -> Interior
        if cat == "INTERIOR":
            cypher = root + """
            OPTIONAL MATCH (t)-[:HAS_INTERIOR]->(i:Interior)
            WITH m,t,i WHERE i IS NOT NULL
            RETURN
            m.name AS model_id,
            coalesce(t.name,'') AS trim_name,
            'INTERIOR' AS category,
            coalesce(i.name,'') AS feature,
            trim(coalesce(i.interior_type,'') + ' ' + coalesce(i.color,'')) AS value
            LIMIT $limit
            """
            rows = self._run_cypher_traced(self._uid(), cypher, {"model_id": model_id, "limit": int(limit), **trim_params}) or []
            lines = []
            for r in rows:
                feat = (r.get("feature") or "").strip()
                if feat:
                    val = (r.get("value") or "").strip()
                    fv = f"{feat}: {val}".strip(": ").strip() if val else feat
                    lines.append(f"Kayıt: {model_id} | - | {r.get('trim_name','-') or '-'} | INTERIOR | {fv}")
            return {"hits": rows, "text": "\n".join(lines).strip()}

        # 7) WHEEL -> WheelPackage
        if cat == "WHEEL":
            cypher = root + """
            OPTIONAL MATCH (t)-[:HAS_WHEEL_PACKAGE]->(wp:WheelPackage)
            WITH m,t,wp WHERE wp IS NOT NULL
            RETURN
            m.name AS model_id,
            coalesce(t.name,'') AS trim_name,
            'WHEEL' AS category,
            coalesce(wp.name,'') AS feature,
            coalesce(wp.type,'') AS value
            LIMIT $limit
            """
            rows = self._run_cypher_traced(self._uid(), cypher, {"model_id": model_id, "limit": int(limit), **trim_params}) or []
            lines = []
            for r in rows:
                feat = (r.get("feature") or "").strip()
                if feat:
                    val = (r.get("value") or "").strip()
                    fv = f"{feat}: {val}".strip(": ").strip() if val else feat
                    lines.append(f"Kayıt: {model_id} | - | {r.get('trim_name','-') or '-'} | WHEEL | {fv}")
            return {"hits": rows, "text": "\n".join(lines).strip()}

        # 8) COLOR -> ColorName/Code/Type zinciri
        if cat == "COLOR":
            cypher = root + """
            OPTIONAL MATCH (t)-[:HAS_COLOR_NAME]->(cn:ColorName)-[:HAS_COLOR_CODE]->(cc:ColorCode)-[:HAS_COLOR_TYPE]->(ct:ColorType)
            WITH m,t,cn,cc,ct
            WHERE cn IS NOT NULL
            RETURN
            m.name AS model_id,
            coalesce(t.name,'') AS trim_name,
            'COLOR' AS category,
            cn.name AS feature,
            trim(coalesce(cc.code,'') + ' ' + coalesce(ct.name,'')) AS value
            LIMIT $limit
            """
            rows = self._run_cypher_traced(self._uid(), cypher, {"model_id": model_id, "limit": int(limit), **trim_params}) or []
            lines = []
            for r in rows:
                feat = (r.get("feature") or "").strip()
                if feat:
                    val = (r.get("value") or "").strip()
                    fv = f"{feat}: {val}".strip(": ").strip() if val else feat
                    lines.append(f"Kayıt: {model_id} | - | {r.get('trim_name','-') or '-'} | COLOR | {fv}")
            return {"hits": rows, "text": "\n".join(lines).strip()}

        # Default: boş
        return {"hits": [], "text": ""}

    def _is_feature_yesno_question(self, q: str) -> bool:
        return bool(self._FEATURE_Q_RE.search(q or ""))

    def _relation_retrieve_any_category(
        self,
        *,
        ql_neo,
        model_id: str,
        trims: list[str],
        categories: list[str],
        limit_each: int = 250,
    ) -> dict:
        """
        Kategori belirsizse birden fazla kategoriyle dene ve hepsini birleştir.
        Return: {"hits": [...], "text": "..."}
        """
        all_hits = []
        text_parts = []
        for cat in categories:
            res = self._relation_retrieve(ql_neo, model_id=model_id, trims=trims, category=cat, limit=limit_each) or {}
            hits = res.get("hits") or []
            t = (res.get("text") or "").strip()
            if hits:
                all_hits.extend(hits)
            if t:
                text_parts.append(t)
        return {"hits": all_hits, "text": "\n".join(text_parts).strip()}

    def _feature_yesno_multi(self, *, model_id: str, trims: list[str], question: str) -> dict:
        # ✅ (1) kategori tahmini ve whitelist seçimi
        cat = self._infer_category(question)  # kamera için genelde "EQUIPMENT"

        rel_whitelist = ["HAS_EQUIPMENT", "HAS_OPTION_PRICE"]  # dar liste

        # Kamera/var mı sorularında sadece equipment/option tarafına odaklan
        if not (cat == "EQUIPMENT" and ("kamera" in (question or "").lower())):
            # geniş liste (diğer var mı soruları için)
            rel_whitelist = [
                "HAS_EQUIPMENT","HAS_OPTION_PRICE","HAS_MULTIMEDIA","HAS_INTERIOR",
                "HAS_COLOR","HAS_WHEEL","HAS_TECH_SPEC","HAS_SAFETY"
            ]

        # ✅ (2) Artık bu whitelist ile fulltext relation araması
        result = self._feature_retrieve_fulltext(
            model_id=model_id,
            trims=trims,
            question=question,
            limit_hits=60,
            limit_rows=600,
            rel_whitelist=rel_whitelist,   # 🔥 yeni param
        ) or {}

        hits = result.get("hits") or []
        plain_q = (result.get("plain_q") or "").strip().lower()

        def _is_available(av: str) -> bool:
            avl = (av or "").strip().lower()

            # ✅ availability yoksa "var" sayma
            if not avl:
                return False

            # normalize
            avl = avl.replace(" ", "").replace("_", "")

            # ❌ mevcut değil
            if avl in {"notavailable", "yok", "no", "false", "0"}:
                return False

            # ✅ mevcut (standart/opsiyonel)
            if avl in {"standard", "standart", "optional", "opsiyonel", "option"}:
                return True

            # bilinmeyen bir string gelirse güvenli tarafta kal
            return False

        if not plain_q:
            return {"found": False, "message": "Bu özellik için net bir bilgi bulunamadı.", "hits": hits}

        # "cam tavan" -> satır içinde geçiyor mu?
        matched = []
        for r in hits:
            feat = (r.get("feature") or "").lower()
            val = (r.get("value") or "").lower()
            if plain_q in feat or plain_q in val:
                matched.append(r)
        # ✅ SADECE EQUIPMENT ilişkilerinden gelen hit'leri dikkate al (kamera gibi var mı sorularında şart)
        matched = [
            r for r in matched
            if (r.get("rel_type") == "HAS_EQUIPMENT") and ("EQUIPMENT" in (r.get("labels") or []))
        ]

        if not matched:
            return {"found": False, "message": "KB’de bu özellik için net bir kayıt bulunamadı.", "hits": hits}

        # Trim yoksa: hangi trimlerde var/yok
        if not trims:
            by_trim = {}
            for r in matched:
                tr = (r.get("trim_name") or "").strip() or "-"
                by_trim.setdefault(tr, []).append(r)

            available = sorted([t for t, rr in by_trim.items() if any(_is_available(x.get("availability")) for x in rr)])
            not_available = sorted([t for t, rr in by_trim.items() if rr and all(not _is_available(x.get("availability")) for x in rr)])

            if available:
                msg = "Bu özellik bazı versiyonlarda mevcut. Mevcut olanlar: " + ", ".join(available) + "."
                if not_available:
                    msg += " Mevcut olmayanlar: " + ", ".join(not_available) + "."
                return {"found": True, "yes": True, "message": msg, "hits": matched}

            # hepsi notavailable
            if not_available:
                return {"found": True, "yes": False, "message": "Bu özellik listelenen versiyonlarda mevcut değil.", "hits": matched}

            return {"found": False, "message": "KB’de bu özellik için net bir kayıt bulunamadı.", "hits": matched}

        # Trim verilmişse: en az bir available kayıt varsa evet
        # ✅ Trim verilmişse: availability ile STD/OPTIONAL/NOTAVAILABLE kararını ver
        # ✅ Trim verilmişse: availability'ye göre karar
        avs = [(r.get("availability") or "").strip().lower() for r in matched]
        avs = [a for a in avs if a]
        avs = [a.replace(" ", "").replace("_", "") for a in avs]

        has_std = any(a in {"standard","standart"} for a in avs)
        has_opt = any(a in {"optional","opsiyonel","option"} for a in avs)
        has_na  = any(a in {"notavailable","yok","no","false","0"} for a in avs)

        if has_std:
            return {"found": True, "yes": True, "message": "Evet, bu versiyonda bu özellik standart olarak sunulmaktadır.", "hits": matched}

        if has_opt:
            return {"found": True, "yes": True, "message": "Evet, bu versiyonda bu özellik opsiyonel olarak sunulmaktadır.", "hits": matched}

        if has_na:
            return {"found": True, "yes": False, "message": "Hayır, bu versiyonda bu özellik mevcut değil.", "hits": matched}

        return {"found": False, "message": "Bu özellik için net bir uygunluk kaydı bulunamadı.", "hits": matched}


    def _render_with_llm(self, *, question: str, context_text: str, has_data: bool, wants_table: bool) -> str:
        style_guard = (
            "Cevabı HER ZAMAN Türkçe ver.\n"
            "Sadece verilen bağlama dayan. UYDURMA.\n"
            "Bağlamda veri varsa 'KB’de yok' deme.\n"
            "Yıldız (*) kullanma. Madde işareti '-' olsun.\n"
            "Kaynak/dosya adı yazma.\n"
        )

        task_guard = (
            f"VERİ DURUMU: has_data={has_data}\n"
            "Bağlam 'Kayıt:' satırlarından oluşur.\n"
            "Eğer kullanıcı 'var mı' diyorsa, bağlamdaki kayıtlara göre cevap ver.\n"
            "Eğer kullanıcı 'nedir / teknik özellikler' diyorsa, bağlamdaki kayıtları tablo veya maddelerle sun.\n"
        )

        if wants_table:
            task_guard += (
                "ÇIKTI: Önce Markdown TABLO ver (en az 10 satır mümkünse), sonra en fazla 2 cümle açıklama.\n"
            )
        else:
            task_guard += (
                "ÇIKTI: Önce 1 cümle özet, sonra en fazla 6 madde.\n"
            )

        prompt = ChatPromptTemplate.from_messages([
            ("system", style_guard + "\n" + task_guard),
            ("human", "Bağlam:\n{context}\n\nSoru: {question}\nCevap:")
        ])

        ans = (prompt | self.llm | StrOutputParser()).invoke({"context": context_text, "question": question}).strip()
        return self._sanitize_text(ans)


    def _extract_trims_in_text(self, q: str) -> list[str]:
        ql = (q or "").lower()
        found = []
        for trim_key, keys in self._TRIM_ALIASES.items():
            if any(k in ql for k in keys):
                found.append(trim_key)

        # uniq (sıra koru)
        out = []
        for t in found:
            if t not in out:
                out.append(t)
        return out


    def _pretty_trim(self, t: str) -> str:
        low = (t or "").strip().lower()
        if low == "rs":
            return "RS"
        if low == "l&k crystal":
            return "L&K Crystal"
        if low == "e-prestige":
            return "e-Prestige"
        if low == "e-sportline":
            return "e-Sportline"
        if low == "e-sportline phev":
            return "e-Sportline PHEV"
        if low == "monte carlo":
            return "Monte Carlo"
        return " ".join(w.capitalize() for w in low.split())

    def _score_record(self, feature: str, group: str, question: str) -> int:
        q = (question or "").lower()
        f = (feature or "").lower()
        g = (group or "").lower()

        score = 0

        # Kullanıcı soru kelimeleri özellik/grup içinde geçiyorsa yüksek puan
        for w in q.split():
            if len(w) < 3:
                continue
            if w in f or w in g:
                score += 5

        # Genel soruda bile “çekirdek” alanlara hafif öncelik (istersen değiştir)
        core_boost = [
            "motor", "ivmelenme", "maks", "hız", "tüketim", "yakıt", "menzil",
            "bagaj", "güvenlik", "kamera", "multimedya", "carplay", "android",
            "şarj", "donanım", "paket"
        ]
        if any(k in f for k in core_boost) or any(k in g for k in core_boost):
            score += 3

        # Çok uzun opsiyon paketi satırlarını biraz geri it (çok yer kaplıyor)
        if len(feature) > 120:
            score -= 2

        return score

    def _extract_record_rows(self, text: str) -> list[tuple[str, str, str, str, str, str]]:
        """
        'Kayıt: Model | Body | Trim | Grup | Özellik: Değer' satırlarını parse eder.
        Return: (model, body, trim, group, feature, value)
        """
        if not text:
            return []

        rows = []
        for m in self._RECORD_LINE_RE.finditer(text):
            line = m.group(1).strip()
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 5:
                continue

            model = parts[0]
            body = parts[1]
            trim = parts[2]
            group = parts[3]
            feat_val = " | ".join(parts[4:]).strip()

            if ":" in feat_val:
                feature, value = [x.strip() for x in feat_val.split(":", 1)]
            else:
                feature, value = feat_val, ""

            rows.append((model, body, trim, group, feature, value))

        # uniq
        seen = set()
        uniq = []
        for r in rows:
            if r in seen:
                continue
            seen.add(r)
            uniq.append(r)
        return uniq

    def _records_to_compact_text(self, rows, *, limit: int, question: str) -> str:
        scored = []
        for model, body, trim, group, feature, value in rows:
            s = self._score_record(feature, group, question)
            scored.append((s, (trim, group, feature, value)))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [r for _, r in scored[:limit]]

        lines = []
        for trim, group, feature, value in top:
            feature = feature.strip()
            value = (value or "").strip()
            if value:
                lines.append(f"{trim} | {group} | {feature}: {value}")
            else:
                lines.append(f"{trim} | {group} | {feature}")
        return "\n".join(lines)
    def _shorten(self, s: str, n: int = 90) -> str:
            s = (s or "").strip()
            return s if len(s) <= n else (s[:n].rstrip() + "…")
    def _records_to_bullets(self, rows, *, limit: int = 20, question: str = "") -> str:
        if not rows:
            return ""

        # Skorla → en iyi limit kadarını al
        scored = []
        for model, body, trim, group, feature, value in rows:
            s = self._score_record(feature, group, question)
            scored.append((s, (model, body, trim, group, feature, value)))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [r for _, r in scored[:limit]]

        out = []
        out.append("Kamiq için en alakalı bilgiler:")
        
        for model, body, trim, group, feature, value in top:
            short_feature = self._shorten(feature, 90)
            short_value = self._shorten(value, 40)
            val = f": {short_value}" if short_value else ""
            out.append(f"- {trim} | {group} | {short_feature}{val}")


        out.append("Hangi trim veya hangi konu (teknik, güvenlik, multimedya, paketler) istersin?")
        return "\n".join(out)


    def _hybrid_vector_search_traced(self, query: str, k: int) -> list[str]:
        self.ensure_indexes()
        uid = self._uid()

        # OpenAIEmbeddings (LangChain) ile query embedding
        emb = self.emb.embed_query(query)  # list[float]

        # Fulltext tarafı için güvenli lucene
        lucene_q = self._safe_lucene_query(query) or query

        cypher = """
    CALL () {
    CALL db.index.vector.queryNodes($index, $k, $embedding)
    YIELD node, score
    WITH collect({node: node, score: score}) AS nodes, max(score) AS mx
    UNWIND nodes AS n
    RETURN n.node AS node, CASE WHEN mx = 0 THEN 0 ELSE (n.score / mx) END AS score

    UNION

    CALL db.index.fulltext.queryNodes($keyword_index, $query, {limit: $k})
    YIELD node, score
    WITH collect({node: node, score: score}) AS nodes, max(score) AS mx
    UNWIND nodes AS n
    RETURN n.node AS node, CASE WHEN mx = 0 THEN 0 ELSE (n.score / mx) END AS score
    }
    WITH node, max(score) AS score
    ORDER BY score DESC
    LIMIT $k
    RETURN
    reduce(str = '', p IN $text_props | str + '\\n' + p + ': ' + coalesce(node[p], '')) AS text,
    score
    """

        rows = self._run_cypher_traced(uid, cypher, {
            "index": self.vector_index_name,          # env: NEO4J_VECTOR_INDEX_NAME
            "keyword_index": self.doc_index_name,     # env: NEO4J_DOC_FULLTEXT_INDEX
            "k": int(k),
            "embedding": emb,
            "query": lucene_q,
            "text_props": self.text_props or ["text"],
        })

        return [r["text"] for r in rows if r.get("text")]

    def _uid(self) -> str | None:
        # ChatbotAPI _answer_via_neo4j_only içinde set ediyorsun:
        # self.neo4j_graphrag._current_user_id = userf_id
        return getattr(self, "_current_user_id", None)

    def _run_cypher_traced(self, user_id: str | None, cypher: str, params: dict):
        # user_id yoksa bile en az class loglasın
        try:
            if hasattr(self, "_tlog") and user_id:
                self._tlog(user_id, "NEO4J_CYPHER_SEND", cypher=cypher, params=params)
        except Exception:
            pass

        with self.driver.session(database=self.neo4j_db) as s:
            rows = s.run(cypher, params).data()

        try:
            if hasattr(self, "_tlog") and user_id:
                self._tlog(user_id, "NEO4J_CYPHER_RECV", rows_count=len(rows), sample=rows[:3])
        except Exception:
            pass

        return rows

    def _history_to_text(self, chat_history, max_items: int = 8) -> str:
        """
        chat_history farklı formatlarda gelebilir:
        - [{"role": "...", "content": "..."}, ...]
        - LangChain message objeleri (msg.content)
        """
        if not chat_history:
            return ""

        items = chat_history[-max_items:]
        parts = []
        for it in items:
            if isinstance(it, dict):
                c = (it.get("content") or "").strip()
            else:
                c = (getattr(it, "content", "") or "").strip()
            if c:
                parts.append(c)
        return "\n".join(parts)

    def _extract_models_from_history(self, chat_history) -> list[str]:
        txt = self._history_to_text(chat_history, max_items=10)
        if not txt:
            return []
        return self._extract_models_in_text(txt)

    def _infer_model_from_variant(self, q: str, last_models: list[str]) -> list[str]:
        """
        'e-Sportline 85X' gibi ifadelerde model yoksa:
        - Son modeller içinde enyaq/elroq varsa onu tercih et
        - Yoksa default enyaq (istersen burada elroq'a da kırabilirsin)
        """
        ql = (q or "").lower()
        if not self._VARIANT_HINT_RE.search(ql):
            return []

        # Son model elektriklilerden biriyse onu kullan
        for m in reversed(last_models or []):
            if m in {"enyaq", "elroq"}:
                return [m]

        # Aksi halde varsayılan (senin kullanımın: Enyaq)
        return ["enyaq"]

    def _resolve_models(self, user_question: str, chat_history=None) -> list[str]:
        # 1) mesajın kendisi
        models = self._extract_models_in_text(user_question)
        if models:
            return models

        # 2) geçmişten
        hist_models = self._extract_models_from_history(chat_history)
        if hist_models:
            # variant ipucu varsa, geçmişteki elektrikliyi tercih et
            via_variant = self._infer_model_from_variant(user_question, hist_models)
            return via_variant or hist_models

        # 3) sadece variant ipucu (geçmiş yoksa)
        return self._infer_model_from_variant(user_question, [])

    def _clean_compare_query(self, question: str, models: list[str], keep: str) -> str:
        q = (question or "").lower()
        # diğer model adlarını çıkar
        for m in models:
            if m != keep:
                q = re.sub(rf"\b{re.escape(m.lower())}\b", " ", q)
        # compare gürültüsünü çıkar
        q = self._COMPARE_NOISE.sub(" ", q)
        q = re.sub(r"\s+", " ", q).strip()
        return q
    def ingest_prechunked_kb_md(self, md_path: str, *, reset: bool = False, source: str = "SkodaKB"):
        if not self.enabled:
            return

        label = self.node_label or "Chunk"
        text_prop = (self.text_props[0] if self.text_props else "text")
        emb_prop  = self.emb_prop or "embedding"

        with open(md_path, "r", encoding="utf-8") as f:
            raw = f.read()

        # Dosya zaten '---' ile bloklara ayrılmış görünüyor
        blocks = [b.strip() for b in re.split(r"\n-{3,}\n", raw) if b.strip()]
        if not blocks:
            raise RuntimeError("KB dosyası boş veya bloklara ayrılamadı.")

        if reset:
            with self.driver.session(database=self.neo4j_db) as s:
                s.run(f"MATCH (d:{label}) DETACH DELETE d").consume()

        embs = self.emb.embed_documents(blocks)

        rows = []
        for i, (t, e) in enumerate(zip(blocks, embs)):
            rows.append({"doc_id": f"{source}:{i}", "text": t, "embedding": e, "source": source})

        B = 200
        with self.driver.session(database=self.neo4j_db) as s:
            for i in range(0, len(rows), B):
                batch = rows[i:i+B]
                s.run(
                    f"""
                    UNWIND $rows AS r
                    MERGE (d:{label} {{doc_id: r.doc_id}})
                    SET d.{text_prop} = r.text,
                        d.{emb_prop}  = r.embedding,
                        d.source      = r.source,
                        d.updated_at  = timestamp()
                    """,
                    rows=batch
                ).consume()

        self.ensure_indexes()
        self._init_vector_index()

    _MY_YEAR_RE = re.compile(r"\bMY\s*[-:]?\s*(\d{2,4})\b", re.IGNORECASE)
    _MY_YEAR_STUCK_RE = re.compile(r"\bMY(\d{2,4})\b", re.IGNORECASE)
    _MY_ALONE_RE = re.compile(r"\bMY\b", re.IGNORECASE)
    def _is_equipment_question(self, q: str) -> bool:
        ql = (q or "").lower()
        if "teknik" in ql:
            return False
        return any(k in ql for k in [
            "donanım", "donanim",
            "özellik", "ozellik",
            "paket", "paketi",
            "versiyon", "trim",
            "standart", "opsiyon", "opsiyonel",
            "var mı", "varmi", "mevcut mu"
        ])

    def _strip_my_tokens(self, text: str) -> str:
        """
        'MY' (Model Year) ifadesi cevaplarda görünmesin.
        - 'MY 24', 'MY-24', 'MY:2024', 'MY2024' -> 'Model Yılı 2024' (veya 20xx)
        - tek başına 'MY' -> sil
        """
        if not text:
            return text

        def fmt_year(m):
            y = m.group(1)
            if len(y) == 2 and y.isdigit():
                yy = 2000 + int(y)   # 24 -> 2024
            else:
                yy = int(y) if y.isdigit() else y
            return f"Model Yılı {yy}"

        t = self._MY_YEAR_RE.sub(fmt_year, text)
        t = self._MY_YEAR_STUCK_RE.sub(lambda m: fmt_year(m), t)
        t = self._MY_ALONE_RE.sub("", t)

        # boşluk temizliği
        t = re.sub(r"[ \t]{2,}", " ", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()

    _BODY_STYLE_SYNONYMS = {
    "combi": ["combi", "kombi", "station", "wagon", "estate"],
    # Skoda TR'de bazen "Sedan" deniyor ama aslında liftback; ikisini birlikte ele alıyoruz
    "sedan": ["sedan", "liftback", "lift back", "lift-back"],
    }

    def _extract_body_style_in_text(self, q: str) -> Optional[str]:
        ql = (q or "").lower()
        for style, keys in self._BODY_STYLE_SYNONYMS.items():
            if any(k in ql for k in keys):
                return style
        return None

    def _doc_matches_body_style(self, doc_text: str, body_style: Optional[str]) -> bool:
        if not body_style:
            return True
        tl = (doc_text or "").lower()
        keys = self._BODY_STYLE_SYNONYMS.get(body_style, [])
        return any(k in tl for k in keys)

    # class Neo4jSkodaGraphRAG: içine ekle
    _FILE_EXT_LINE_RE = re.compile(r"\.(xlsx|xls|pdf|docx|pptx|csv|png|jpe?g|webp)\b", re.IGNORECASE)
    _SOURCE_KV_LINE_RE = re.compile(r"^\s*(kaynak|source|dosya|file)\s*[:\-]", re.IGNORECASE)

    # Sende görünen tipik “kaynak/tablo” token’larını burada topla
    _INTERNAL_SOURCE_TOKEN_RE = re.compile(
        r"\b(?:Ozellik_Info|SkodaKB|Skoda_GraphRAG_[A-Za-z0-9_]+|KbVectors_[A-Za-z0-9_]+|"
        r"EquipmentList_[A-Za-z0-9_]+|PriceList_[A-Za-z0-9_]+|ImportedList_[A-Za-z0-9_]+)\b",
        re.IGNORECASE
    )

    def _strip_sources_and_filenames(self, text: str) -> str:
        """
        Context/answer içinden:
        - 'source/kaynak/dosya:' satırlarını
        - .xlsx/.pdf vb dosya adı geçen satırları
        - belirli internal token'ları
        temizler.
        """
        if not text:
            return text

        out_lines = []
        for ln in text.splitlines():
            s = ln.strip()
            if not s:
                out_lines.append(ln)
                continue

            # "Kaynak: ..." gibi satırları komple at
            if self._SOURCE_KV_LINE_RE.search(s):
                continue

            # Satır dosya adı gibi görünüyorsa komple at
            if self._FILE_EXT_LINE_RE.search(s):
                # çoğu durumda dosya adı tek başına satır oluyor
                # güvenli tarafta kalıp satırı atıyoruz
                continue

            # internal token'ları satır içinden sil
            ln = self._INTERNAL_SOURCE_TOKEN_RE.sub("", ln)

            out_lines.append(ln)

        cleaned = "\n".join(out_lines)

        # Kalan “dosya adı parçası” geçerse (çok nadir) sök
        cleaned = re.sub(
            r"[\w\-\(\)\s,\.ÇĞİÖŞÜçğıöşü]+?\.(xlsx|xls|pdf|docx|pptx|csv|png|jpe?g|webp)\b",
            "",
            cleaned,
            flags=re.IGNORECASE
        )

        # fazla boşluk/satır düzelt
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _strip_asterisks(self, text: str) -> str:
        """
        Cevaplarda '*' istemiyorsun:
        - '* madde' -> '- madde'
        - kalan tüm '*' karakterlerini sil
        """
        if not text:
            return text
        t = re.sub(r"(?m)^\s*\*\s+", "- ", text)  # yıldızlı maddeyi dash yap
        t = t.replace("*", "")                    # kalan tüm yıldızları kaldır
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()

    def _sanitize_text(self, text: str) -> str:
        text = self._strip_sources_and_filenames(text)
        text = self._strip_my_tokens(text)      # ✅ MY temizliği
        text = self._strip_asterisks(text)
        return text


    def _looks_non_skoda(self, q: str) -> bool:
        ql = (q or "").lower()

        # Skoda veya Skoda modelleri geçiyorsa: in-domain
        if "skoda" in ql or "škoda" in ql:
            return False
        if self._extract_models_in_text(q):
            return False

        # Buraya geldiysek: Skoda ile ilgili değil (hava durumu, matematik, başka marka vs.)
        return True


    def _skoda_redirect_answer(self) -> str:
        return (
            "Yalnızca Škoda hakkında yardımcı olabilirim.\n"
            "İstersen şunlardan birini seçebilirsin:\n"
            "- Şehir içi: Fabia / Scala\n"
            "- B-SUV: Kamiq\n"
            "- SUV: Karoq / Kodiaq\n"
            "- Elektrikli: Enyaq / Elroq\n"
            "Hangi modeli veya ihtiyacı (SUV, elektrikli, aile, şehir içi) hedefliyorsun?"
        )
    # "özelliklerini kıyasla/karşılaştır" gibi genel istekleri yakala
    _GENERIC_FEATURE_COMPARE_RE = re.compile(
        r"\b(özelliklerini|ozelliklerini)\s+(kıyasla|kiyasla|karşılaştır|karsilastir)\b",
        re.IGNORECASE
    )

    # Spesifik kriter kelimeleri (kullanıcı net bir kriter söylüyorsa)
    _SPECIFIC_COMPARE_KEYS = [
        "bagaj", "menzil", "sarj", "şarj", "tork", "güç", "guc",
        "uzunluk", "genişlik", "genislik", "yükseklik", "yukseklik",
        "0-100", "ivme", "dönüş", "donus", "co2", "wltp"
    ]

    def _is_generic_feature_compare(self, q: str) -> bool:
        return bool(self._GENERIC_FEATURE_COMPARE_RE.search(q or ""))

    def _has_specific_compare_criteria(self, q: str) -> bool:
        ql = (q or "").lower()
        return any(k in ql for k in self._SPECIFIC_COMPARE_KEYS)

    def _is_compare_question(self, q: str) -> bool:
        ql = (q or "").lower()
        if re.search(r"\b(m[iıuü])\b", ql):  # "kamiq mi", "octavia mı" gibi
            return True
        return any(k in ql for k in [
            "karşılaştır", "karsilastir", "kıyas", "kiyas",
            "fark", "farkı", "farki", "vs", "arasında", "hangisi"
        ])
    def _extract_models_in_text(self, q: str) -> list[str]:
        ql = (q or "").lower()
        models = ["fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"]
        return [m for m in models if m in ql]
    _HTML_RE = re.compile(r"<[^>]+>")

    def _safe_lucene_query(self, s: str) -> str:
        if not s:
            return ""
        # html temizle
        s = self._HTML_RE.sub(" ", s)
        s = s.replace("&bull;", " ").replace("•", " ")
        # çok uzunsa kısalt (fulltext için yeterli)
        s = " ".join(s.split())[:240]
        # lucene özel karakterlerini temizle + fuzzy AND query üret
        return generate_full_text_query(s)

    def _keyword_retrieve(self, query: str, k: int = 8) -> str:
        cypher = """
        CALL db.index.fulltext.queryNodes($idx, $q, {limit: $k})
        YIELD node, score
        RETURN node.text AS text
        ORDER BY score DESC
        """
        q = self._safe_lucene_query(query)
        if not q:
            return ""

        # 🔍 log input
        try:
            if hasattr(self, "_tlog"):
                self._tlog(getattr(self, "_current_user_id", None) or "guest", "NEO4J_FULLTEXT_QUERY",
                        idx=self.doc_index_name, lucene=q, k=k)
        except Exception:
            pass

        try:
            rows = self._run_cypher_traced(
            self._uid(),
            cypher,
            {"idx": self.doc_index_name, "q": q, "k": k}
            )
        except Exception:
            return ""

        # 🔍 log output
        try:
            if hasattr(self, "_tlog"):
                self._tlog(getattr(self, "_current_user_id", None) or "guest", "NEO4J_FULLTEXT_RESULT",
                        rows_count=len(rows), sample=rows[:2])
        except Exception:
            pass

        return "\n\n".join([r["text"] for r in rows if r.get("text")])

    def _concat_with_budget(self, docs, *, max_chunks: int, max_chars: int) -> str:
        out, total, used = [], 0, 0

        # 🚀 docs[:max_chunks] yerine tüm docs'u dön, sadece bütçeyle kırp
        for d in docs:
            t = (d.page_content or "").strip()
            if not t:
                continue

            add = len(t) + 2
            if total + add > max_chars:
                break

            out.append(t)
            total += add
            used += 1

            # İstersen max_chunks yine “üst güvenlik” olsun:
            if used >= max_chunks:
                break

        return "\n\n".join(out).strip()


    def _unstructured_retriever(
        self,
        question: str,
        *,
        models=None,
        compare_mode: bool = False,
        body_style: Optional[str] = None,
        strict_body_style: bool = False,
        k_search: int = 24,
        max_chunks: int = 12,
        max_chars: int = 28000,
    ) -> str:
        


        self._init_vector_index()
        q = question or ""
        models = models or self._extract_models_in_text(q)

        # ✅ NORMAL: hiç model yoksa geniş arama yap
        if not models:
            texts = self._hybrid_vector_search_traced(q, k_search)
            # concat_with_budget bekliyorsa Document’a çevir:
            docs = [Document(page_content=t) for t in texts if t.strip()]
            return self._concat_with_budget(docs, max_chunks=max_chunks, max_chars=max_chars)



        # ✅ NORMAL: 1 model varsa query'yi model ile boost et + hafif filtre
        if not compare_mode and len(models) == 1:
            m = models[0]
            bs = body_style or ""
            texts = self._hybrid_vector_search_traced(f"{m} {bs} {q}".strip(), k_search)
            docs = [Document(page_content=t) for t in texts if t.strip()]


            m_l = m.lower()
            docs = [d for d in docs if m_l in (d.page_content or "").lower()]

            # ✅ gövde tipi verilmişse (veya strict istenmişse) mutlaka filtrele
            if body_style or strict_body_style:
                docs = [d for d in docs if self._doc_matches_body_style(d.page_content, body_style)]

            if not docs:
                # fulltext fallback (model + body_style birlikte)
                return self._keyword_retrieve(f"{m} {bs} {q}".strip(), k=8)

            return self._concat_with_budget(docs, max_chunks=max_chunks, max_chars=max_chars)


        # ✅ COMPARE: 2+ modelde model başına ayrı retrieval + round-robin
        # ✅ COMPARE: 2+ modelde model başına ayrı retrieval (model bazlı temiz query) + MODEL başlıkları
        per_model = max(4, math.ceil(max_chunks / max(1, len(models))))
        oversample = per_model * 5  # biraz artır (daha iyi kapsama)
        docs_by_model = {}

        for m in models:
            clean_q = self._clean_compare_query(q, models, keep=m)
            query_m = f"{m} {clean_q}".strip()

            docs = self.vector_index.similarity_search(query_m, k=oversample)

            m_l = m.lower()
            docs_m = [d for d in docs if m_l in (d.page_content or "").lower()]

            if body_style or strict_body_style:
                docs_m = [d for d in docs_m if self._doc_matches_body_style(d.page_content, body_style)]

            if not docs_m:
                # keyword fallback
                txt = self._keyword_retrieve(f"{m} {clean_q} {(body_style or '')}".strip(), k=10)
                docs_by_model[m] = [Document(page_content=txt)] if txt.strip() else []
            else:
                docs_by_model[m] = docs_m[:per_model]

        # ✅ En kritik kısım: context'i model başlıklarıyla ayır
        parts = []
        for m in models:
            texts = []
            for d in docs_by_model.get(m, []):
                t = (d.page_content or "").strip()
                if t:
                    texts.append(t)
            if texts:
                parts.append(f"### MODEL: {m.upper()}\n" + "\n\n".join(texts))

        return "\n\n".join(parts).strip()



    def ingest_documents_only(self, file_path: str, *, reset: bool = False, source: str = "SkodaKB"):
        """
        SkodaKB.md -> chunk -> (Document {doc_id, text, embedding, source})
        RAG'in kesin çalışması için en net ingest.
        """
        if not self.enabled:
            return

        label = self.node_label or "Document"           # env: NEO4J_RAG_NODE_LABEL
        text_prop = (self.text_props[0] if self.text_props else "text")   # env: NEO4J_RAG_TEXT_PROPS
        emb_prop  = self.emb_prop or "embedding"        # env: NEO4J_RAG_EMB_PROP

        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()

        if not raw.strip():
            raise RuntimeError(f"Boş dosya: {file_path}")

        # İstersen reset: Eski Document kayıtlarını temizle
        if reset:
            cypher = """
                CALL db.index.fulltext.queryNodes($idx, $query, {limit: 2})
                YIELD node, score
                CALL (node) {
                WITH node
                MATCH (node)-[r]->(neighbor)
                WHERE type(r) <> 'MENTIONS'
                RETURN coalesce(node.id,'') + ' - ' + type(r) + ' -> ' + coalesce(neighbor.id,'') AS output
                UNION ALL
                WITH node
                MATCH (node)<-[r]-(neighbor)
                WHERE type(r) <> 'MENTIONS'
                RETURN coalesce(neighbor.id,'') + ' - ' + type(r) + ' -> ' + coalesce(node.id,'') AS output
                }
                RETURN output
                LIMIT 50
                """

            rows = self._run_cypher_traced(
                self._uid(),
                cypher,
                {"idx": self.entity_index_name, "query": q}
            )


        splitter = TokenTextSplitter(chunk_size=512, chunk_overlap=24)
        docs = splitter.split_documents([Document(page_content=raw)])
        chunks = [d.page_content for d in docs if (d.page_content or "").strip()]

        # embedding üret
        embs = self.emb.embed_documents(chunks)   # list[list[float]]

        rows = []
        for i, (t, e) in enumerate(zip(chunks, embs)):
            rows.append({
                "doc_id": f"{source}:{i}",
                "text": t,
                "embedding": e,
                "source": source
            })

        # write
        B = 100
        with self.driver.session(database=self.neo4j_db) as s:
            for i in range(0, len(rows), B):
                batch = rows[i:i+B]
                s.run(
                    f"""
                    UNWIND $rows AS r
                    MERGE (d:{label} {{doc_id: r.doc_id}})
                    SET d.{text_prop} = r.text,
                        d.{emb_prop}  = r.embedding,
                        d.source      = r.source,
                        d.updated_at  = timestamp()
                    """,
                    rows=batch
                ).consume()

        # indexleri garanti et
        self.ensure_indexes()

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        openai_api_key: str,
        enabled: bool = True,
        neo4j_db: Optional[str] = None,
    ):
        self.enabled = bool(enabled)
        if not self.enabled:
            return

        # --- config ---
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.neo4j_db = neo4j_db or os.getenv("NEO4J_DB", "neo4j")
        self.node_label = os.getenv("NEO4J_RAG_NODE_LABEL", "Chunk")
        self.text_props = [p.strip() for p in os.getenv("NEO4J_RAG_TEXT_PROPS", "text").split(",") if p.strip()]
        self.emb_prop   = os.getenv("NEO4J_RAG_EMB_PROP", "embedding")

        self.vector_index_name = os.getenv("NEO4J_VECTOR_INDEX_NAME", "vector")

        self.entity_index_name = os.getenv("NEO4J_ENTITY_FULLTEXT_INDEX", "entity")
        self.doc_index_name = os.getenv("NEO4J_DOC_FULLTEXT_INDEX", "skoda_document_text")

        self.chat_model = os.getenv("NEO4J_RAG_CHAT_MODEL", "gpt-4o-mini")
        self.embed_model = os.getenv("NEO4J_RAG_EMBED_MODEL", "text-embedding-3-large")

        # --- ENV (bazı LC bileşenleri hala ENV okuyor) ---
        os.environ["OPENAI_API_KEY"] = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        # __init__ içinde, openai_api_key geldikten sonra ekle:

        self.openai_api_key = openai_api_key  # sakla (gerekirse)
        os.environ["OPENAI_API_KEY"] = openai_api_key  # LangChain çoğu sürümde buradan okur

        # Embedding nesnesi
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError:
            from langchain.embeddings.openai import OpenAIEmbeddings  # eski sürüm fallback

        embed_model = os.getenv("EMBED_MODEL", "text-embedding-3-large")

        try:
            self.embeddings = OpenAIEmbeddings(model=embed_model)
        except TypeError:
            # bazı sürümlerde parametre adı farklı olabiliyor
            self.embeddings = OpenAIEmbeddings(model_name=embed_model)

        os.environ["NEO4J_URI"] = self.neo4j_uri
        os.environ["NEO4J_USERNAME"] = self.neo4j_user
        os.environ["NEO4J_PASSWORD"] = self.neo4j_password
        os.environ["NEO4J_DATABASE"] = self.neo4j_db  # LangChain sıklıkla bunu okuyor

        # --- LangChain Graph: DB'yi explicit ver (kritik) ---
        self.graph = Neo4jGraph(
            url=self.neo4j_uri,
            username=self.neo4j_user,
            password=self.neo4j_password,
            database=self.neo4j_db,
        )

        # --- Neo4j Driver (ham cypher + index işleri) ---
        self.driver = GraphDatabase.driver(
            self.neo4j_uri,
            auth=(self.neo4j_user, self.neo4j_password),
        )

        # --- LLM & Embeddings ---
        self.max_output_tokens = int(os.getenv("NEO4J_RAG_MAX_OUTPUT_TOKENS", "4000"))
        self.max_table_output_tokens = int(os.getenv("NEO4J_RAG_MAX_TABLE_OUTPUT_TOKENS", "12000"))
        self.max_context_chars = int(os.getenv("NEO4J_RAG_MAX_CONTEXT_CHARS", "60000"))
        self.relation_only = os.getenv("NEO4J_RELATION_ONLY", "0") == "1"



        try:
            self.llm = ChatOpenAI(
                temperature=0,
                model=self.chat_model,
                max_tokens=self.max_output_tokens,
            )
        except TypeError:
            # Bazı sürümlerde max_tokens doğrudan kabul edilmeyebilir
            self.llm = ChatOpenAI(
                temperature=0,
                model=self.chat_model,
                model_kwargs={"max_tokens": self.max_output_tokens},
            )

        self.emb = OpenAIEmbeddings(model=self.embed_model)

        # --- Entity extraction chain ---
        ent_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You are extracting organization and person entities from the text."),
                ("human", "Extract entities from: {question}"),
            ]
        )
        self.entity_chain = ent_prompt | self.llm.with_structured_output(Entities)

        # --- Graph transformer ---
        self.llm_transformer = LLMGraphTransformer(llm=self.llm)

        # --- Vector index (lazy) ---
        self.vector_index: Optional[Neo4jVector] = None

        # --- ensure indexes ---
        self.ensure_indexes()

    def close(self):
        try:
            self.driver.close()
        except Exception:
            pass

    @staticmethod
    def _qident(name: str) -> str:
        # index adı güvenliği
        if not re.fullmatch(r"[0-9A-Za-z_]+", name or ""):
            raise ValueError(f"Invalid index name: {name!r}")
        return f"`{name}`"

    def ensure_indexes(self):
        """
        Fulltext indexleri yoksa yaratır ve ONLINE olana kadar kısa süre bekler.
        """
        try:
            if not self.enabled:
                return

            idx_entity = self.entity_index_name
            idx_doc = self.doc_index_name

            with self.driver.session(database=self.neo4j_db) as s:
                exists = s.run(
                    """
                    SHOW INDEXES YIELD name, type
                    WHERE type='FULLTEXT' AND name IN [$a,$b]
                    RETURN collect(name) AS names
                    """,
                    a=idx_entity,
                    b=idx_doc,
                ).single()["names"]

                if idx_entity not in exists:
                    s.run(
                        f"""
                        CREATE FULLTEXT INDEX {self._qident(idx_entity)} IF NOT EXISTS
                        FOR (e:__Entity__)
                        ON EACH [e.id]
                        """
                    ).consume()

                if idx_doc not in exists:
                    # Chunk label'ı ve text prop'ları ile
                    props = ", ".join([f"n.{p}" for p in self.text_props])
                    s.run(
                        f"""
                        CREATE FULLTEXT INDEX {self._qident(idx_doc)} IF NOT EXISTS
                        FOR (n:{self.node_label})
                        ON EACH [{props}]
                        """
                    ).consume()

                # ONLINE bekle
                t0 = time.time()
                while True:
                    rows = s.run(
                        """
                        SHOW INDEXES YIELD name, type, state
                        WHERE type='FULLTEXT' AND name IN [$a,$b]
                        RETURN name, state
                        """,
                        a=idx_entity,
                        b=idx_doc,
                    ).data()
                    states = {r["name"]: r["state"] for r in rows}
                    if states.get(idx_entity) == "ONLINE" and states.get(idx_doc) == "ONLINE":
                        break
                    if time.time() - t0 > 20:
                        break
                    time.sleep(0.3)
        except DatabaseError as e:
            msg = str(e)
            if "WriteOnReadOnlyAccessDbException" in msg or "read-only" in msg:
                logging.warning("[NEO4J] DB read-only, schema/index creation skipped.")
                return
            raise
    def _init_vector_index(self):
        if self.vector_index is not None:
            return

        try:
            self.vector_index = Neo4jVector.from_existing_graph(
                embedding=self.emb,
                search_type="hybrid",
                node_label=self.node_label,              # Document
                text_node_properties=self.text_props,    # ["text"]
                embedding_node_property=self.emb_prop,   # "embedding"
                url=self.neo4j_uri,
                username=self.neo4j_user,
                password=self.neo4j_password,
                database=self.neo4j_db,
                index_name=self.vector_index_name,       # "vector"
                keyword_index_name=self.doc_index_name,  # "keyword"
            )
        except TypeError:
            # Bazı langchain sürümleri index_name parametresi kabul etmiyor
            self.vector_index = Neo4jVector.from_existing_graph(
                embedding=self.emb,
                search_type="hybrid",
                node_label=self.node_label,
                text_node_properties=self.text_props,
                embedding_node_property=self.emb_prop,
                url=self.neo4j_uri,
                username=self.neo4j_user,
                password=self.neo4j_password,
                database=self.neo4j_db,
            )

    def ingest_markdown(self, md_path: str, reset: bool = False):
        """
        SkodaKB.md -> chunk -> graph docs -> Neo4j'ye bas
        """
        if not self.enabled:
            return

        if reset:
            with self.driver.session(database=self.neo4j_db) as s:
                s.run("MATCH (d:Document) DETACH DELETE d").consume()
                s.run("MATCH (e:__Entity__) DETACH DELETE e").consume()

        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()

        splitter = TokenTextSplitter(chunk_size=512, chunk_overlap=24)
        docs = splitter.split_documents([Document(page_content=text)])

        graph_docs = self.llm_transformer.convert_to_graph_documents(docs)

        self.graph.add_graph_documents(
            graph_docs,
            baseEntityLabel=True,
            include_source=True,
        )

        self.ensure_indexes()
        self._init_vector_index()

    def _structured_retriever(self, question: str) -> str:
        try:
            ents = self.entity_chain.invoke({"question": question})
            names = ents.names or []
        except Exception:
            names = []

        if not names:
            return ""

        out_lines: List[str] = []
        for entity in names:
            q = generate_full_text_query(entity)
            if not q:
                continue

            cypher = """
            CALL db.index.fulltext.queryNodes($idx, $query, {limit: 2})
            YIELD node, score
            CALL {
            WITH node
            MATCH (node)-[r:!MENTIONS]->(neighbor)
            RETURN node.id + ' - ' + type(r) + ' -> ' + neighbor.id AS output
            UNION ALL
            WITH node
            MATCH (node)<-[r:!MENTIONS]-(neighbor)
            RETURN neighbor.id + ' - ' + type(r) + ' -> ' + node.id AS output
            }
            RETURN output LIMIT 50
            """

            try:
                with self.driver.session(database=self.neo4j_db) as s:
                    rows = s.run(cypher, {"idx": self.entity_index_name, "query": q}).data()
                out_lines.extend([r["output"] for r in rows if r.get("output")])

            except Exception as e:
                # ✅ Index yoksa structured'ı kapat, unstructured devam etsin
                msg = str(e).lower()
                if "no such fulltext schema index" in msg:
                    try:
                        self.ensure_indexes()  # bir kere daha dene
                    except Exception:
                        pass
                    continue
                # başka bir hata ise de structured'ı kapat
                continue

        return "\n".join(out_lines)


     
    def ingest_text_to_ragchunk(self, text: str, *, source: str = "SkodaKB", reset: bool = False):
        """
        Metni chunk'layıp :RAGChunk(text, embedding, source, chunk_id) olarak Neo4j'ye yazar.
        """
        if not self.enabled:
            return

        label = os.getenv("NEO4J_RAG_NODE_LABEL", "RAGChunk")
        text_prop = (os.getenv("NEO4J_RAG_TEXT_PROPS", "text") or "text").split(",")[0].strip()
        emb_prop  = os.getenv("NEO4J_RAG_EMB_PROP", "embedding")
        vdim = int(os.getenv("NEO4J_VECTOR_DIM", "3072"))  # 1536 kullanıyorsan env’den değiştir

        if reset:
            with self.driver.session(database=self.neo4j_db) as s:
                s.run(f"MATCH (c:{label}) DETACH DELETE c").consume()

        splitter = TokenTextSplitter(chunk_size=512, chunk_overlap=24)
        docs = splitter.split_documents([Document(page_content=text)])

        chunks = [d.page_content for d in docs if (d.page_content or "").strip()]
        if not chunks:
            return

        # Embeddings
        embs = self.emb.embed_documents(chunks)  # list[list[float]]

        # Boyut doğrula
        if embs and len(embs[0]) != vdim:
            raise ValueError(f"Embedding dim mismatch: got={len(embs[0])} expected={vdim}. "
                            f"NEO4J_RAG_EMBED_MODEL/NEO4J_VECTOR_DIM ayarlarını eşitle.")

        rows = []
        for i, (t, e) in enumerate(zip(chunks, embs)):
            rows.append({"chunk_id": f"{source}:{i}", "text": t, "embedding": e, "source": source})

        # Batch write
        B = 100
        with self.driver.session(database=self.neo4j_db) as s:
            for i in range(0, len(rows), B):
                batch = rows[i:i+B]
                s.run(
                    f"""
                    UNWIND $rows AS r
                    MERGE (c:{label} {{chunk_id: r.chunk_id}})
                    SET c.{text_prop} = r.text,
                        c.{emb_prop}  = r.embedding,
                        c.source      = r.source,
                        c.updated_at  = timestamp()
                    """,
                    rows=batch
                ).consume()

    
    def _strip_markdown_tables(self, text: str) -> str:
        if not text:
            return text
        lines = text.splitlines()
        out = []
        i = 0

        def is_sep_line(s: str) -> bool:
            s2 = s.replace("|", "").replace(":", "").strip()
            return s2 and all(ch in "- " for ch in s2)

        while i < len(lines):
            line = lines[i]
            # header '|' içeriyor ve bir sonraki satır --- ayraç gibiyse tablo başlıyor
            if ("|" in line) and (i + 1 < len(lines)) and is_sep_line(lines[i + 1]):
                i += 2
                while i < len(lines) and ("|" in lines[i]):
                    i += 1
                continue
            out.append(line)
            i += 1

        return "\n".join(out).strip()
    _BAGAJ_PAIR_RE = re.compile(r"(\d{3,4})\s*/\s*(\d{3,4})\s*(?:litre|l)\b", re.IGNORECASE)
    _COMBI_HINT_RE = re.compile(r"\b(combi|kombi|station|wagon|estate)\b", re.IGNORECASE)
    _SEDAN_HINT_RE = re.compile(r"\b(sedan|liftback|lift back|lift-back)\b", re.IGNORECASE)
    
    def answer(self, question: str, chat_history=None) -> str:
        user_question = (question or "").strip()
        uid = getattr(self, "_current_user_id", None)

        print("RELATION_ONLY =", self.relation_only)
        print("ENV NEO4J_RELATION_ONLY =", os.getenv("NEO4J_RELATION_ONLY"))

        if hasattr(self, "_tlog") and uid:
            self._tlog(uid, "RELATION_ONLY_FLAG", value=self.relation_only)

        if hasattr(self, "_tlog") and uid:
            self._tlog(uid, "RAG_ANSWER_START", question=user_question, history=chat_history)
        # ✅ MODEL DEVAMLILIĞI: sadece bu satır bile fark ettirir
        resolved_models = self._resolve_models(user_question, chat_history)
        # ✅ BAGAJ (TEK YOL): RS/Sportline dahil, sedan+combi her zaman
        trims = self._extract_trims_in_text(user_question) or []

        ql = (user_question or "").lower()
        is_bagaj = "bagaj" in ql
        is_bagaj_volume = bool(
            re.search(r"\bbagaj\b", ql) and
            (
                re.search(r"\b(hacmi|hacim|kaç litre|kac litre|litre)\b", ql) or
                re.search(r"\b(\d+\s*l)\b", ql)
            )
        )
        explicit_rs = bool(re.search(r"\brs\b", ql))
        explicit_sportline = ("sportline" in ql)

        # ✅ MODELI BURADA TANIMLA (üstte!)
        models_for_bagaj = resolved_models or []
        # Kullanıcı trim söyledi mi?
        explicit_rs = bool(re.search(r"\brs\b", ql))
        explicit_sportline = ("sportline" in ql)

        if is_bagaj_volume and models_for_bagaj and len(models_for_bagaj) == 1 and models_for_bagaj[0] in {"octavia", "superb"}:
            m = models_for_bagaj[0]

            # ✅ 1) Trim varsa (veya RS/Sportline açıkça söylendiyse): trim bazlı göster
            if trims or explicit_rs or explicit_sportline:
                if explicit_rs and "rs" not in trims:
                    trims.append("rs")
                if explicit_sportline and "sportline" not in trims:
                    trims.append("sportline")

                rows = self._bagaj_dual_body_compact(m, trims) or []
                if rows:
                    out = []
                    for r in rows:
                        tr = (r.get("trim_name") or "").strip() or m.capitalize()
                        out.append(f"<b>{tr} bagaj hacmi</b>")

                        so = r.get("sedan_open_l"); sf = r.get("sedan_folded_l")
                        co = r.get("combi_open_l"); cf = r.get("combi_folded_l")

                        if so and sf:
                            out.append(f"- Sedan/Liftback: {so} litre (koltuklar açık), {sf} litre (koltuklar yatık)")
                        if co and cf:
                            out.append(f"- Combi: {co} litre (koltuklar açık), {cf} litre (koltuklar yatık)")
                        out.append("")
                    return "<br>".join(out).strip()

            # ✅ 2) Trim yoksa: TEK cevap (RS/Sportline listeme yok!)
            rows = self._bagaj_dual_body_compact(m, []) or []
            if rows:
                # tüm trimlerden gelen değerler aynıysa zaten tek çift çıkar,
                # yine de güvenli olsun diye max folded ile seçiyoruz:
                def to_int(x):
                    try: return int(x)
                    except: return -1

                best_sedan = max(rows, key=lambda r: to_int(r.get("sedan_folded_l")), default=None)
                best_combi = max(rows, key=lambda r: to_int(r.get("combi_folded_l")), default=None)

                out = [f"<b>{m.capitalize()} bagaj hacmi</b>"]

                if best_sedan and best_sedan.get("sedan_open_l") and best_sedan.get("sedan_folded_l"):
                    out.append(f"- Sedan/Liftback: {best_sedan['sedan_open_l']} litre (koltuklar açık), {best_sedan['sedan_folded_l']} litre (koltuklar yatık)")
                if best_combi and best_combi.get("combi_open_l") and best_combi.get("combi_folded_l"):
                    out.append(f"- Combi: {best_combi['combi_open_l']} litre (koltuklar açık), {best_combi['combi_folded_l']} litre (koltuklar yatık)")

                # (İstersen sonuna bir soru ekle)
                out.append("İstersen RS veya Sportline için ayrıca da paylaşabilirim.")
                return "<br>".join(out).strip()
        # trims'i zaten extract ediyorsun ama RS kaçarsa zorla ekle
        

        # ✅ Follow-up’larda "Skoda değil" sanmasın
        if self._looks_non_skoda(user_question) and not resolved_models:
            return self._skoda_redirect_answer()

        if not self.enabled:
            return ""

        # index dene
        try:
            self.ensure_indexes()
        except Exception:
            pass
        
        # ✅ Artık models buradan gelsin
        models = resolved_models
        ql = user_question.lower()
        ql_neo = ql
        trims = self._extract_trims_in_text(user_question)
        trim_compare_mode = (len(models) == 1 and len(trims) >= 2)

        # ============================
        # RELATION-ONLY (EARLY RETURN)
        # ============================
        category = self._infer_category(user_question) or "TECH_SPEC"

        if self.relation_only:
            if not models:
                return "Hangi model için bakayım? (Fabia, Scala, Kamiq, Karoq, Kodiaq, Octavia, Superb, Enyaq, Elroq)"

            m0 = models[0]

            # ✅ 1) 'var mı / mevcut mu' soruları: tek kategoriye saplanma, tüm whitelist'te ara
            if self._is_feature_yesno_question(user_question):
                r = self._feature_yesno_multi(model_id=m0, trims=trims, question=user_question) or {}
                if r.get("found"):
                    return self._sanitize_text(r.get("message", "") or "")

                # feature aramada çıkmadıysa: yine de tüm kategorilerden context dene
                cats = ["EQUIPMENT", "OPTION", "MULTIMEDIA", "INTERIOR", "SAFETY", "WHEEL", "COLOR", "TECH_SPEC"]
                res_any = self._relation_retrieve_any_category(ql_neo, model_id=m0, trims=trims, categories=cats, limit_each=250) or {}
                ctx_any = (res_any.get("text") or "").strip()
                if ctx_any:
                    return self._render_with_llm(
                        question=user_question,
                        context_text=ctx_any,
                        has_data=True,
                        wants_table=bool(self._WANTS_TABLE_RE.search(user_question))
                    )

                return "KB’de bu özellik için net bir kayıt bulunamadı."

            # ✅ 2) Diğer sorular: kategori varsa onu çek, yoksa tüm kategorileri dene
            category = self._infer_category(user_question)
            if category:
                res = self._relation_retrieve(ql_neo, model_id=m0, trims=trims, category=category, limit=800) or {}
            else:
                cats = ["EQUIPMENT", "OPTION", "MULTIMEDIA", "INTERIOR", "SAFETY", "WHEEL", "COLOR", "TECH_SPEC"]
                res = self._relation_retrieve_any_category(ql_neo, model_id=m0, trims=trims, categories=cats, limit_each=250) or {}
                category = "MIXED"

            relation_ctx = (res.get("text") or "").strip()
            hits = res.get("hits") or []

            if not hits or not relation_ctx:
                return "KB’de bu bilgi yok."

            wants_table = bool(self._WANTS_TABLE_RE.search(user_question)) or ("teknik" in ql) or (category == "TECH_SPEC")
            return self._render_with_llm(
                question=user_question,
                context_text=relation_ctx,
                has_data=True,
                wants_table=wants_table
            )


        compare_mode = trim_compare_mode or (len(models) >= 2) or self._is_compare_question(user_question)


        is_general_info = bool(self._GENERAL_INFO_RE.search(user_question)) and not self._is_equipment_question(user_question)

        long_mode = bool(re.search(r"\b(detay|detaylı|ayrıntı|tum|tüm|hepsi|tamamı)\b", ql))
        exhaustive_mode = bool(re.search(r"\b(hepsi|tamamı|tümü|tumu|listele|tümünü|tamamını)\b", ql))
        wants_table = bool(self._WANTS_TABLE_RE.search(user_question))

        body_style = self._extract_body_style_in_text(user_question)
        is_equipment = self._is_equipment_question(user_question)
        is_bagaj = "bagaj" in ql
        

        needs_table = bool(is_equipment or compare_mode or exhaustive_mode or wants_table or trim_compare_mode)
        # ✅ Bagaj sorularında: önce Cypher ile sedan+combi yakala (LLM'e bırakma)
        # ✅ Bagaj sorularında: önce TECH_SPEC (body_type) üzerinden kesin çek
        
        # ✅ BAGAJ: sedan + combi her zaman ayrı ayrı (tek yol)
        if "bagaj" in ql and models and len(models) == 1 and models[0] in {"octavia", "superb"}:
            m = models[0]

            # Edge-case: trim extractor bazen RS’i kaçırıyor -> metinde rs/sportline varsa trims'e ekle
            qlow = ql
            if not trims:
                if re.search(r"\brs\b", qlow):
                    trims = ["rs"]
                elif "sportline" in qlow:
                    trims = ["sportline"]

            rows = self._bagaj_dual_body_compact(m, trims) or []
            if rows:
                out = []
                for r in rows:
                    tr = (r.get("trim_name") or "").strip() or m.capitalize()

                    out.append(f"<b>{tr} bagaj hacmi</b>")

                    so = r.get("sedan_open_l")
                    sf = r.get("sedan_folded_l")
                    if so and sf:
                        out.append(f"- Sedan/Liftback: {so} litre (koltuklar açık), {sf} litre (koltuklar yatık)")

                    co = r.get("combi_open_l")
                    cf = r.get("combi_folded_l")
                    if co and cf:
                        out.append(f"- Combi: {co} litre (koltuklar açık), {cf} litre (koltuklar yatık)")

                    out.append("")  # boş satır

                return "<br>".join(out).strip()



        if is_general_info:
            long_mode = True
            #exhaustive_mode = True

        # ✅ retrieval_question: follow-up ise modele boost bas
        retrieval_question = user_question
        if uid and hasattr(self, "_tlog"):
            self._tlog(uid, "RAG_PARSE",
                    resolved_models=resolved_models,
                    compare_mode=compare_mode,
                    long_mode=long_mode,
                    is_equipment=is_equipment,
                    body_style=body_style,
                    retrieval_question=retrieval_question)
        retrieval_question = user_question

        # model adı mesajda yoksa ekle
        if models and not any(m in ql for m in models):
            retrieval_question = f"{' '.join(models)} {retrieval_question}".strip()

        # trim compare ise trimleri de ekle (EN SON)
        if trim_compare_mode and models:
            retrieval_question = f"{models[0]} {' '.join(trims)} {user_question}".strip()


        # (senin generic compare genişletmen aynı kalabilir)
        is_generic_compare = compare_mode and not re.search(
            r"\b(dönüş|donus|sarj|şarj|tork|menzil|bagaj|güç|guc|hp|kw|0-100)\b",
            ql
        )
        if is_generic_compare:
            retrieval_question = retrieval_question + " bagaj hacmi menzil şarj sarj süresi güç tork ölçüler güvenlik"

        # ✅ 3) chunk sayıları
        if compare_mode:
            k_search = 70
            max_chunks = 40
        elif is_equipment:
            k_search = 70
            max_chunks = 40
        elif long_mode:
            k_search = 90
            max_chunks = 60
        else:
            k_search = 60          # daha fazla aday çek
            max_chunks = 40        # context'e daha fazla sok


                # ✅ Relation-First Graph Retrieval (önce graph traversal)
         # trims zaten var: trims = self._extract_trims_in_text(user_question)

        if models:
            # şimdilik tek model için net davran
            m0 = models[0]
            rel_res = self._relation_retrieve(
                model_id=m0,
                trims=trims,            # ör: ["premium"]
                category=category or "",# ör: "TECH_SPEC"
                limit=300
            )
            relation_ctx = (rel_res or {}).get("text", "")
            relation_hits = (rel_res or {}).get("hits", [])


        # Eğer relation ile içerik geldiyse, bunu unstructured bağlamı olarak kullan
        # ve vector aramayı ya tamamen atla ya da fallback yap
        if relation_ctx.strip():
            structured = ""      # istersen structured'a da koyabilirsin
            unstructured = relation_ctx

            # log
            if hasattr(self, "_tlog") and uid:
                self._tlog(uid, "NEO4J_RELATION_RETRIEVE_HIT",
                          model=models, trims=trims, category=category,
                          ctx_len=len(unstructured), preview=unstructured[:600])
        else:
            if hasattr(self, "_tlog") and uid:
                self._tlog(uid, "NEO4J_RELATION_RETRIEVE_MISS",
                          model=models, trims=trims, category=category)
         

        if self.relation_only:
            if not models:
                return "Hangi model için bakayım? (Fabia, Scala, Kamiq, Karoq, Kodiaq, Octavia, Superb, Enyaq, Elroq)"

            # Tek model odaklı (istersen compare için genişletirsin)
            m0 = models[0]

            rel_res2 = self._relation_retrieve(
                model_id=m0,
                trims=trims,
                category=category or "TECH_SPEC",  # default istersen
                limit=400
            )
            relation_ctx = (rel_res2 or {}).get("text", "")
            relation_hits = (rel_res2 or {}).get("hits", [])


            relation_ctx = self._sanitize_text(relation_ctx)

            if not relation_ctx.strip():
                # relation-only modunda fallback YOK
                return "KB’de bu bilgi yok."

            # Relation context'ten cevap üret (LLM'e ver)
            structured = ""
            unstructured = relation_ctx

            context = f"""Structured data:
        {structured}

        Unstructured data:
        {unstructured}
        """.strip()

            # Aşağıda senin mevcut prompt/LLM kısmın aynen devam edebilir
            # ama önemli: vector/fulltext çağrılarına hiç girmeyecek.

        # ✅ 4) retrieval
        structured = self._structured_retriever(retrieval_question)
        # Bagaj için aramayı body keyword ile güçlendir
        sedan_q = f"{retrieval_question} sedan liftback"
        combi_q = f"{retrieval_question} combi kombi station wagon estate"
        # (A) Octavia/Superb bagaj özel kuralı
        if is_bagaj and len(models) == 1 and models[0] in {"octavia", "superb"} and body_style is None:
            m = models[0]

            if hasattr(self, "_tlog") and uid:
                self._tlog(uid, "NEO4J_VECTORSEARCH_SEND",
                        query=retrieval_question, models=[m], compare_mode=False,
                        k_search=k_search, max_chunks=max_chunks, max_chars=self.max_context_chars,
                        body_style="sedan")

            sedan_ctx = self._unstructured_retriever(
                sedan_q,
                models=[m],
                compare_mode=False,
                body_style="sedan",
                strict_body_style=False,   # ✅ kritik: strict kapalı
                k_search=k_search,
                max_chunks=max_chunks,
                max_chars=self.max_context_chars,
            )

            if hasattr(self, "_tlog") and uid:
                self._tlog(uid, "NEO4J_VECTORSEARCH_SEND",
                        query=retrieval_question, models=[m], compare_mode=False,
                        k_search=k_search, max_chunks=max_chunks, max_chars=self.max_context_chars,
                        body_style="combi")

            combi_ctx = self._unstructured_retriever(
                combi_q,
                models=[m],
                compare_mode=False,
                body_style="combi",
                strict_body_style=False,   # ✅ kritik: strict kapalı
                k_search=k_search,
                max_chunks=max_chunks,
                max_chars=self.max_context_chars,
            )
            # sedan_ctx bazen hiç dolmuyor -> 1555/600 ile keyword fallback
            if not sedan_ctx or "1555" not in sedan_ctx:
                extra = self._keyword_retrieve(f"{m} bagaj 1555 600", k=12)
                if extra.strip():
                    sedan_ctx = (sedan_ctx + "\n" + extra).strip()

            # combi için de istersen güçlendir
            if not combi_ctx or "1700" not in combi_ctx:
                extra = self._keyword_retrieve(f"{m} bagaj 1700 640", k=12)
                if extra.strip():
                    combi_ctx = (combi_ctx + "\n" + extra).strip()

            sedan_lines, _, unknown1 = self._split_bagaj_lines(sedan_ctx)
            _, combi_lines, unknown2 = self._split_bagaj_lines(combi_ctx)

            unknown = unknown1 + unknown2

            unstructured = (
                f"{m.upper()} SEDAN/LIFTBACK BAĞLAMI:\n" + "\n".join(sedan_lines) + "\n\n"
                f"{m.upper()} COMBI BAĞLAMI:\n" + "\n".join(combi_lines) + "\n\n"
                f"{m.upper()} (GÖVDE TİPİ BELİRSİZ SATIRLAR):\n" + "\n".join(unknown)
            ).strip()

        else:
            if hasattr(self, "_tlog") and uid:
                self._tlog(uid, "NEO4J_VECTORSEARCH_SEND",
                        query=retrieval_question, models=models, compare_mode=compare_mode,
                        k_search=k_search, max_chunks=max_chunks, max_chars=self.max_context_chars,
                        body_style=body_style)

            unstructured = self._unstructured_retriever(
                retrieval_question,
                models=models,
                compare_mode=compare_mode,
                body_style=body_style,
                strict_body_style=bool(body_style),
                k_search=k_search,
                max_chunks=max_chunks,
                max_chars=self.max_context_chars,
            )

        # ✅ RECV: unstructured hazırlandıktan HEMEN SONRA (sanitize’dan ÖNCE)
        if hasattr(self, "_tlog") and uid:
            self._tlog(uid, "NEO4J_VECTORSEARCH_RECV",
                    structured_len=len(structured or ""),
                    unstructured_len=len(unstructured or ""),
                    structured_preview=(structured or "")[:600],
                    unstructured_preview=(unstructured or "")[:600])

        # ✅ 5) context temizliği (logdan sonra)
        structured = self._sanitize_text(structured)
        unstructured = self._sanitize_text(unstructured)
        # ✅ Genel soruda tablo yok ama "ne bulduysa" çok ver: LLM bypass, record satırlarını listele
        if is_general_info and not needs_table:
            rows = self._extract_record_rows(unstructured)
            compact = self._records_to_compact_text(rows, limit=20, question=user_question)

            if compact.strip():
                # ✅ LLM ile doğal dile çevir (tablo yok!)
                system2 = (
                    "Cevabı HER ZAMAN Türkçe ver.\n"
                    "Tablo yazma. '|' karakteri kullanma.\n"
                    "Madde işareti olarak sadece '-' kullan.\n"
                    "En fazla 8 madde kullan.\n"
                    "Verilen maddeler dışına çıkma, uydurma.\n"
                    "Önce 2-3 cümle genel özet yaz, sonra maddeler.\n"
                )
                human2 = (
                    "Aşağıdaki maddeler Kamiq için KB'den çıkarılmış en alakalı 20 kayıttır.\n"
                    "Bunları kullanıcıya doğal ve anlaşılır bir cevap olarak anlat:\n\n"
                    f"{compact}\n\n"
                    f"Soru: {user_question}"
                )

                llm2 = ChatOpenAI(temperature=0, model=self.chat_model, max_tokens=900)
                ans2 = (ChatPromptTemplate.from_messages([('system', system2), ('human', human2)]) | llm2 | StrOutputParser()).invoke({})
                return self._sanitize_text(ans2)


        if hasattr(self, "_tlog") and uid:
            self._tlog(uid, "NEO4J_VECTORSEARCH_RECV",
                    structured_len=len(structured or ""),
                    unstructured_len=len(unstructured or ""),
                    structured_preview=structured[:600] if structured else "",
                    unstructured_preview=unstructured[:600] if unstructured else "")

        context = f"""Structured data:
    {structured}

    Unstructured data:
    {unstructured}
    """.strip()

        # ✅ 6) context boşsa
        if not (structured or unstructured):
            if not models:
                return "Hangi model için bakayım? (Fabia, Scala, Kamiq, Karoq, Kodiaq, Octavia, Superb, Enyaq, Elroq)"
            return "Bu soruya ait içerik bulunamadı. Daha spesifik sorabilir misin? (ör. yıl/motor/versiyon)"

        # ✅ 7) prompt guard'lar
        style_guard = (
            "Cevabı HER ZAMAN Türkçe ver.\n"
            "Markdown kullanabilirsin.\n"
            "Gerektiğinde Markdown tablo kullan: '|' ve ayraç satırı '---' serbest.\n"
            "Yıldız (*) karakteri ASLA kullanma. Madde işareti olarak sadece '-' kullan.\n"
            "Kaynak/dosya adı/tablo adı/index adı (örn. .xlsx, Ozellik_Info vb.) ASLA yazma.\n"
        )
        table_priority_guard = (
            "TABLO ÖNCELİĞİ:\n"
            "- Çıktının %95'i tablo olmalı.\n"
            "- Tabloyu ÖZETLEME; bağlamda gördüğün her benzersiz (model/versiyon + özellik) kaydını tabloya satır olarak ekle.\n"
            "- Satır atlama yapma. Bağlamda 30+ satır üretebiliyorsan en az 30 satır üret.\n"
            "- Tablo dışındaki açıklama en fazla 1 kısa cümle olsun.\n"
            "- 'Not' sütunu 12 kelimeyi geçmesin.\n"
            "- Aynı özelliğin farklı trimlerdeki her satırı ayrı satır olarak yaz.\n"
            "- Bağlamda geçen her sayısal değeri ilgili satıra koy.\n"
        )

        ql = user_question.lower()

        long_mode = bool(re.search(r"\b(detay|detaylı|ayrıntı|tum|tüm|hepsi|tamamı)\b", ql))
        exhaustive_mode = bool(re.search(r"\b(hepsi|tamamı|tümü|tumu|listele|tümünü|tamamını)\b", ql))
        general_info_guard = ""
        if is_general_info and not needs_table:
            general_info_guard = (
                "GENEL BİLGİ MODU:\n"
                "- Kullanıcı genel bilgi istiyor.\n"
                "- Bağlamda geçen tüm farklı özellikleri mümkün olduğunca kapsa.\n"
                "- Sadece teknik değerleri seçip diğerlerini atlama.\n"
                "- Madde işaretleri '-' ile olsun.\n"
            )

        if exhaustive_mode:
            detail_guard = (
                "ÇIKTI KISITLARI:\n"
                "- Sadece bağlamda geçen bilgileri yaz.\n"
                "- ÖZETLEME yapma.\n"
                "- Bağlamda gördüğün her benzersiz (trim/özellik/değer) kaydını yaz.\n"
                "- Madde sayısı sınırı yok.\n"
                "- Sonunda en fazla 1 takip sorusu sor.\n"
            )
        elif long_mode:
            detail_guard = (
                "ÇIKTI KISITLARI:\n"
                "- İlk satır: 1–2 cümle genel tanıtım.\n"
                "- ÖZETLEME yapma; bağlamda geçen bilgileri tek tek yaz.\n"
                "- En fazla 20 madde kullan (10 değil).\n"
                "- Maddeleri şu başlıklarla grupla: Teknik, Motor/Şanzıman, Donanım, Opsiyon Paketleri.\n"
                "- Sadece bağlamda geçenleri yaz, uydurma.\n"
                "- Sonunda en fazla 1 takip sorusu sor.\n"
            )
        else:
            detail_guard = (
                "ÇIKTI KISITLARI (HATA ÖNLEME):\n"
                "- İlk satır: Net cevap (1 cümle).\n"
                "- Ardından en fazla 4 madde kullan.\n"
                "- Sadece bağlamda açıkça geçen bilgileri yaz.\n"
                "- Cevaba koyduğun her sayı/ölçü bağlamda birebir geçmeli; geçmiyorsa yazma.\n"
                "- Bağlamda cevap yoksa TAM OLARAK şu cümleyi yaz: 'KB’de bu bilgi yok.'\n"
                "- Sonra sadece 1 netleştirici soru sor (yıl/trim/motor gibi).\n"
            )


        body_guard = ""
        if body_style and not compare_mode:
            other = "Sedan/Liftback" if body_style == "combi" else "Combi"
            body_guard = (
                f"Kullanıcı gövde tipi olarak '{body_style}' belirtti.\n"
                f"Yanıtta '{other}' gövde tipine ait bagaj hacmi veya ölçü değerlerini ASLA verme.\n"
                "Bagaj cevabında MUTLAKA iki ayrı başlık kullan:\n"
                "- 'Sedan/Liftback Bagaj Hacmi'\n"
                "- 'Combi Bagaj Hacmi'\n"
                "Başlıklar arasında değer karıştırma.\n"
                "Bir satırda trim listesi (RS, Sportline vb.) geçiyorsa, o değerin hangi trimleri kapsadığını aynı satırda belirt.\n"
            )
        elif is_bagaj and len(models) == 1 and models[0] in {"octavia", "superb"} and body_style is None:
            body_guard = (
                "Kullanıcı gövde tipini belirtmedi.\n"
                "Bagaj hacmi değerlerini Sedan/Liftback ve Combi için ayrı ayrı başlıklarla ver.\n"
                "Değerleri karıştırma; her başlık altında sadece o gövde tipinin değerleri yer alsın.\n"
                "Bagaj cevabında MUTLAKA iki ayrı başlık kullan:\n"
                "- 'Sedan/Liftback Bagaj Hacmi'\n"
                "- 'Combi Bagaj Hacmi'\n"
                "Başlıklar arasında değer karıştırma.\n"
                "Bir satırda trim listesi (RS, Sportline vb.) geçiyorsa, o değerin hangi trimleri kapsadığını aynı satırda belirt.\n"
            )
        trim_headers = [self._pretty_trim(t) for t in trims]

        trim_compare_guard = (
            "Bu bir aynı model içinde TRIM/versiyon karşılaştırmasıdır.\n"
            "- Cevabın İLK kısmında mutlaka bir Markdown tablo ver.\n"
            f"- Tablo kolonları: Kriter | " + " | ".join(trim_headers) + " | Not\n"
            "- Bağlamda geçen kriterleri tabloya ekle.\n"
            "- Eğer bir kriter sadece bir trimde geçiyorsa diğer trim hücresi '—' olsun.\n"
            "- Tablo sonrası en fazla 4 madde ile kısa yorum yap.\n"
            "- Sonunda 1 kısa takip sorusu sor.\n"
        )
        equipment_guard = ""
        if is_equipment and not compare_mode:
            equipment_guard = (
                "Bu bir donanım/özellik sorusu.\n"
                "- Cevabın İLK kısmında mutlaka bir Markdown tablo ver.\n"
                "- Eğer tek model varsa: Model/Versiyon | Özellik | Durum | Not\n"
                "- Bağlamda gördüğün her özelliği ayrı satır yap.\n"
                "- Tablo sonrası açıklama en fazla 1 cümle.\n"
            )

        equipment_compare_guard = (
            "Bu bir karşılaştırmalı donanım/özellik sorusu.\n"
            "- Kullanıcının sorduğu özellik(ler)i aynen al ve SADECE onları kıyasla.\n"
            "- Cevabın İLK kısmında mutlaka bir Markdown tablo ver.\n"
            f"- Tablo kolonları: Özellik | " + " | ".join([m.capitalize() for m in models]) + " | Not\n"
            "- Her satırda aynı özelliğin her modeldeki durumunu yaz.\n"
            "- 'Bilgi yok' / 'bilgi mevcut değil' gibi ifadeleri ASLA yazma.\n"
            "- Bağlamda veri yoksa ilgili hücreyi '—' bırak.\n"
            "- Bağlamda olmayan bilgi uydurma.\n"
            "- Tablo sonrası en fazla 4 madde ile farkı açıkla.\n"
            "- 'Öneri:' satırını sadece bağlamda veri varsa yaz.\n"
            "- Sonunda 1 kısa takip sorusu sor.\n"
        )

        compare_guard = (
            "Bu bir karşılaştırma/tercih sorusuysa:\n"
            "- Cevabın İLK kısmında mutlaka bir Markdown tablo ver.\n"
            f"- Tablo kolonları: Kriter | " + " | ".join([m.capitalize() for m in models]) + " | Not\n"
            "- SADECE bağlamda açıkça geçen kriterleri tabloya ekle.\n"
            "- Bağlamda geçmeyen bir kriteri ASLA tabloya koyma.\n"
            "- 'Bilgi yok' / 'bilgi mevcut değil' gibi ifadeler ASLA yazma.\n"
            "- Eğer bir kriter yalnızca tek modelde geçiyorsa, o kriteri EKLEME (kriteri tamamen atla).\n"
            "- Tablo sonrası en fazla 4 madde ile kısa yorum yap.\n"
            "- 'Öneri:' satırını sadece bağlamda veri varsa yaz.\n"
            "- Sonunda 1 kısa takip sorusu sor.\n"
        )

        skoda_only_guard = (
            "Sen yalnızca Škoda markası ve Škoda modelleri hakkında konuşan bir asistansın.\n"
            "Yanıtta Škoda dışındaki hiçbir marka/model/şirket ismini ASLA yazma.\n"
            "Soru içinde Škoda modeli geçiyorsa, doğrudan o model(ler) üzerinden cevap ver.\n"
            "Soru içinde model geçiyorsa ASLA 'Hangi Škoda modeli?' diye geri sorma.\n"
            "Skoda ile ilgili normal sorularda politika cümlesi yazma.\n"
            "Bağlam yetersizse, sadece Škoda modelleri hakkında genel otomotiv bilgisiyle mantıksal öneri yap.\n"
            "Sonunda en fazla 1 takip sorusu sor.\n"
        )

        # ✅ 8) compare modunda equipment_compare kullanımı (ham soruya göre)
        use_equipment_compare = (
            compare_mode
            and is_equipment
            and self._has_specific_compare_criteria(user_question)
            and not self._is_generic_feature_compare(user_question)
        )
        active_compare_guard = compare_guard
        if trim_compare_mode:
            active_compare_guard = trim_compare_guard
        elif use_equipment_compare:
            active_compare_guard = equipment_compare_guard


        system_text = (
            skoda_only_guard
            + style_guard
            + (table_priority_guard if needs_table else "")
            + general_info_guard
            + detail_guard
            + body_guard
            + equipment_guard
            + (active_compare_guard if compare_mode else "")
        )


        human_text = (
            "Sadece aşağıdaki bağlama dayanarak cevap ver:\n"
            "{context}\n\n"
            "Soru: {question}\n"
            "Cevap:"
        )


        prompt = ChatPromptTemplate.from_messages([
            ("system", system_text),
            ("human", human_text),
        ])

        llm_for_call = self.llm
        if needs_table:
            llm_for_call = ChatOpenAI(
                temperature=0,
                model=self.chat_model,
                max_tokens=self.max_table_output_tokens,
            )
        messages = prompt.format_messages(context=context, question=user_question)
        sys_msg = messages[0].content if messages else ""
        hum_msg = messages[1].content if len(messages) > 1 else ""

        if uid and hasattr(self, "_tlog"):
            self._tlog(uid, "LLM_SEND",
                    model=self.chat_model,
                    needs_table=needs_table,
                    system_preview=sys_msg[:800],
                    human_preview=hum_msg[:1200],
                    context_len=len(context),
                    question=user_question)

        chain = prompt | llm_for_call | StrOutputParser()


        try:
            ans = (chain.invoke({"context": context, "question": user_question}) or "").strip()
            if hasattr(self, "_tlog") and uid:
                self._tlog(uid, "LLM_RECV", answer=ans)

            ans = self._sanitize_text(ans)
            if hasattr(self, "_tlog") and uid:
                self._tlog(uid, "FINAL_ANSWER_SANITIZED", answer=ans)

            return ans
        except Exception as e:
            logging.exception("answer() failed: %s", e)
            return "Bir hata oluştu, tekrar dener misin?"