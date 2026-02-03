# modules/kb_repo.py
from __future__ import annotations
import re
import pyodbc
from typing import Any, Dict, List, Optional, Sequence, Tuple
from modules.db import get_db_connection

_TXT_TYPES = {"varchar", "nvarchar", "ntext", "text", "char", "nchar"}

def _qual(schema: str, table: str) -> str:
    return f"[{schema}].[{table}]"

def _like_param(s: str) -> str:
    # Güvenli LIKE paramı – % ve _ işaretlerini kaçır
    s = s.replace("%", "[%]").replace("_", "[_]")
    return f"%{s}%"

class MSSQLKb:
    """
    SkodaBot KB erişimi (MSSQL).
    - Kolon adları farklı ortamlarda değişebileceği için yöntemler 'esnek' çalışır:
      Model/Trim/Feature/Available gibi eşleşen kolon adlarını sys.columns üzerinden keşfeder.
    """

    def __init__(self, default_schema: str = "kb"):
        self.default_schema = default_schema

    # ---------- ŞEMA / METADATA ----------

    def _columns(self, schema: str, table: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT c.name AS name,
               t.name AS type_name,
               c.max_length AS max_length,
               c.precision AS precision_,
               c.scale AS scale_,
               c.is_nullable AS is_nullable
        FROM sys.columns c
        JOIN sys.types t ON c.user_type_id = t.user_type_id
        WHERE c.object_id = OBJECT_ID(?)
        ORDER BY c.column_id;
        """
        fqn = f"{schema}.{table}"
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, (fqn,))
            rows = cur.fetchall()
        out = []
        for r in rows:
            out.append({
                "name": r[0],
                "type": r[1],
                "len": int(r[2]) if r[2] is not None else None,
                "prec": int(r[3]) if r[3] is not None else None,
                "scale": int(r[4]) if r[4] is not None else None,
                "null": bool(r[5]),
            })
        return out

    def fetch_table_count(self, table: str, schema: Optional[str] = None) -> int:
        schema = schema or self.default_schema
        sql = f"SELECT COUNT(1) FROM {_qual(schema, table)} WITH (NOLOCK);"
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql)
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

    def fetch_table_summary(self, table: str, schema: Optional[str] = None, sample_rows: int = 0) -> Dict[str, Any]:
        schema = schema or self.default_schema
        cols = self._columns(schema, table)
        cnt = self.fetch_table_count(table, schema)
        out: Dict[str, Any] = {"count": cnt, "columns": cols}
        if sample_rows > 0:
            sel = f"SELECT TOP {int(sample_rows)} * FROM {_qual(schema, table)} WITH (NOLOCK);"
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute(sel)
                rows = cur.fetchall()
                colnames = [d[0] for d in cur.description]
            out["samples"] = {
                "columns": colnames,
                "rows": [tuple(r) for r in rows]
            }
        return out

    def fetch_table_rows(
        self,
        table: str,
        schema: Optional[str] = None,
        where_like: Optional[List[Tuple[str, str]]] = None,
        order_by: Optional[str] = None,
        top: int = 1000,
        columns: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Esnek 'LIKE' filtreli satır çekimi. Olmayan kolon isimleri otomatik atlanır.
        """
        schema = schema or self.default_schema
        all_cols = [c["name"] for c in self._columns(schema, table)]

        sel_cols = columns if columns else all_cols
        sel_cols = [c for c in sel_cols if c in all_cols]
        if not sel_cols:
            sel_cols = all_cols

        wh_parts, params = [], []
        if where_like:
            for col, pat in where_like:
                if not col or not pat:
                    continue
                if col not in all_cols:
                    continue
                wh_parts.append(f"LOWER(CAST([{col}] AS NVARCHAR(MAX))) LIKE LOWER(?)")
                params.append(_like_param(pat))

        where_sql = ("WHERE " + " AND ".join(wh_parts)) if wh_parts else ""
        order_sql = ""
        if order_by and order_by in all_cols:
            order_sql = f" ORDER BY [{order_by}]"

        sql = f"SELECT TOP {int(top)} " + ", ".join(f"[{c}]" for c in sel_cols) + \
              f" FROM {_qual(schema, table)} WITH (NOLOCK) {where_sql}{order_sql};"

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()

        return {"columns": sel_cols, "rows": [tuple(r) for r in rows]}

    # ---------- ÖZELLİK 'VAR MI?' SORGUSU (SpecItem) ----------

    def _find_col(self, schema: str, table: str, candidates: Sequence[str]) -> Optional[str]:
        cols = [c["name"] for c in self._columns(schema, table)]
        lower = {c.lower(): c for c in cols}
        for cand in candidates:
            if cand.lower() in lower:
                return lower[cand.lower()]
        return None

    def feature_availability(
        self,
        *,
        model: Optional[str],
        feature_terms: Sequence[str],
        trim: Optional[str] = None,
        schema: Optional[str] = None
    ):
        """
        kb.SpecItem'da 'özellik var mı' kontrolü. Esnek kolon adlarıyla çalışır.
        SELECT sırası: Model, Feature, Available, Trim  (Available 3. sütun!)
        """
        schema = schema or self.default_schema
        tbl = "SpecItem"

        model_col   = self._find_col(schema, tbl, ["Model", "ModelName", "ModelCode"])
        trim_col    = self._find_col(schema, tbl, ["Trim", "Variant", "Donanim", "Grade"])
        feat_col    = self._find_col(schema, tbl, ["FeatureName", "Feature", "Name", "Spec", "Title", "Item"])
        avail_col   = self._find_col(schema, tbl, ["Available", "IsAvailable", "Status", "Value", "Presence", "StdOps"])

        # Arama yapılacak metin kolonu yoksa erkenden çık
        if not feat_col:
            return []

        # WHERE inşası
        where_sql, params = [], []

        if model and model_col:
            where_sql.append(f"LOWER(CAST([{model_col}] AS NVARCHAR(MAX))) LIKE LOWER(?)")
            params.append(_like_param(model))

        if trim and trim_col:
            where_sql.append(f"LOWER(CAST([{trim_col}] AS NVARCHAR(MAX))) LIKE LOWER(?)")
            params.append(_like_param(trim))

        # Feature eşleşmeleri (OR)
        or_chunks = []
        for t in feature_terms:
            if not t:
                continue
            or_chunks.append(f"LOWER(CAST([{feat_col}] AS NVARCHAR(MAX))) LIKE LOWER(?)")
            params.append(_like_param(t))
        if or_chunks:
            where_sql.append("(" + " OR ".join(or_chunks) + ")")

        where_final = ("WHERE " + " AND ".join(where_sql)) if where_sql else ""

        # Available sütunu yoksa, var/yok kestirimi için 0/1 üretelim (Standart/Opsiyonel -> 1)
        avail_sel = (
            f"""
            CASE
              WHEN LOWER(CAST([{feat_col}] AS NVARCHAR(MAX))) LIKE '%opsiyonel%' THEN 1
              WHEN LOWER(CAST([{feat_col}] AS NVARCHAR(MAX))) LIKE '%standart%'  THEN 1
              {f"WHEN [{avail_col}] IN (1,'1','Evet','Yes','Var','S','O','Standart','Opsiyonel') THEN 1" if avail_col else ""}
              ELSE 0
            END AS Available
            """
        )

        # SELECT sırasını Model, Feature, Available, Trim olarak kuralım
        sel_parts = []
        sel_parts.append(f"{f'[{model_col}]' if model_col else 'NULL'} AS Model")
        sel_parts.append(f"[{feat_col}] AS Feature")
        sel_parts.append(avail_sel)  # 3. sütun Available!
        sel_parts.append(f"{f'[{trim_col}]' if trim_col else 'NULL'} AS Trim")

        sql = f"""
        SELECT TOP 200 {", ".join(sel_parts)}
        FROM {_qual(schema, tbl)} WITH (NOLOCK)
        {where_final}
        ORDER BY 1,2;
        """

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
        return rows

    # ---------- Serbest metin RAG araması (4 tablo) ----------

    def _text_columns(self, schema: str, table: str) -> List[str]:
        cols = self._columns(schema, table)
        return [c["name"] for c in cols if (c["type"] or "").lower() in _TXT_TYPES]

    def _search_table_hits(
        self,
        *,
        schema: str,
        table: str,
        terms: Sequence[str],
        model_hint: Optional[str] = None,
        top_k: int = 6,
        join_registry: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Tek tablo (veya TableRow+TableRegistry join) üzerinde LIKE tabanlı skorlamalı arama.
        """
        txt_cols = self._text_columns(schema, table)
        if not txt_cols:
            return []

        # Metin alanlarını tek bir Expression'da birleştir
        text_expr = " + ' ' + ".join([f"COALESCE(CAST([{c}] AS NVARCHAR(MAX)),'')" for c in txt_cols])
        text_expr = f"RTRIM(LTRIM({text_expr}))"

        where_parts, params = [], []
        term_like_parts = []
        for t in terms:
            term_like_parts.append(f"LOWER({text_expr}) LIKE LOWER(?)")
            params.append(_like_param(t))

        if term_like_parts:
            where_parts.append("(" + " OR ".join(term_like_parts) + ")")

        score_expr = " + ".join([f"CASE WHEN LOWER({text_expr}) LIKE LOWER(?) THEN 1 ELSE 0 END" for _ in terms])
        params.extend([_like_param(t) for t in terms])

        # Model ipucuna biraz ağırlık ver
        if model_hint:
            score_expr = f"({score_expr}) + 2*CASE WHEN LOWER({text_expr}) LIKE LOWER(?) THEN 1 ELSE 0 END"
            params.append(_like_param(model_hint))

        base_from = f"FROM {_qual(schema, table)} WITH (NOLOCK)"

        # TableRow + TableRegistry joini istenirse (TableId ortak kolonu varsa)
        if join_registry and table.lower() == "tablerow":
            # Hangi kolonla join?
            row_cols  = set(self._columns(schema, "TableRow")[i]["name"] for i in range(len(self._columns(schema, "TableRow"))))
            reg_cols  = set(self._columns(schema, "TableRegistry")[i]["name"] for i in range(len(self._columns(schema, "TableRegistry"))))
            key = None
            for cand in ["TableId", "TableID", "RegistryId", "TableRefId"]:
                if cand in row_cols and cand in reg_cols:
                    key = cand
                    break
            if key:
                base_from = (
                    f"FROM {_qual(schema, 'TableRow')} r WITH (NOLOCK) "
                    f"JOIN {_qual(schema, 'TableRegistry')} g WITH (NOLOCK) ON r.[{key}] = g.[{key}]"
                )
                # Metin ifadesini r+g alanları ile genişletelim
                txt_r = self._text_columns(schema, "TableRow")
                txt_g = self._text_columns(schema, "TableRegistry")
                expr_r = " + ' ' + ".join([f"COALESCE(CAST(r.[{c}] AS NVARCHAR(MAX)),'')" for c in txt_r]) or "''"
                expr_g = " + ' ' + ".join([f"COALESCE(CAST(g.[{c}] AS NVARCHAR(MAX)),'')" for c in txt_g]) or "''"
                text_expr = f"RTRIM(LTRIM(({expr_r}) + ' ' + ({expr_g})))"

                # WHERE/Score ifadelerini yeniden kur
                where_parts, params = [], []
                term_like_parts = [f"LOWER({text_expr}) LIKE LOWER(?)" for _ in terms]
                where_parts.append("(" + " OR ".join(term_like_parts) + ")")
                params.extend([_like_param(t) for t in terms])

                score_expr = " + ".join([f"CASE WHEN LOWER({text_expr}) LIKE LOWER(?) THEN 1 ELSE 0 END" for _ in terms])
                params.extend([_like_param(t) for t in terms])
                if model_hint:
                    score_expr = f"({score_expr}) + 2*CASE WHEN LOWER({text_expr}) LIKE LOWER(?) THEN 1 ELSE 0 END"
                    params.append(_like_param(model_hint))

        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        sql = f"""
        SELECT TOP {int(top_k * 3)}
               ({score_expr}) AS score,
               LEFT({text_expr}, 400) AS snippet
        {base_from}
        {where_sql}
        ORDER BY score DESC;
        """

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()

        hits = []
        for r in rows:
            try:
                score = float(r[0] or 0)
                snip  = str(r[1] or "").strip()
                if score <= 0 or not snip:
                    continue
                hits.append({"score": score, "snippet": snip})
            except Exception:
                continue
        return hits[:top_k]

    def search_chunks(self, query: str, top_k: int = 6, model_hint: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Sorguyu 4 tabloda (SpecItem, WheelItem, TableRegistry, TableRow+Registry) arar,
        skorlayıp en iyi 'snippet'leri döndürür.
        """
        if not query or not query.strip():
            return []

        # Basit anahtar kelime çıkarımı
        tokens = re.findall(r"[0-9a-zçğıöşü]+", query.lower())
        terms = [t for t in tokens if len(t) >= 3]
        # Basit sinyaller kaybolmasın
        if len(" ".join(terms)) < 3:
            terms.append(query.strip())

        schema = self.default_schema
        out: List[Dict[str, Any]] = []

        # 1) SpecItem (özellik/var-yok ağırlıklı)
        out += self._search_table_hits(schema=schema, table="SpecItem", terms=terms, model_hint=model_hint, top_k=top_k)

        # 2) WheelItem
        out += self._search_table_hits(schema=schema, table="WheelItem", terms=terms, model_hint=model_hint, top_k=top_k)

        # 3) TableRegistry (başlıklar, vb.)
        out += self._search_table_hits(schema=schema, table="TableRegistry", terms=terms, model_hint=model_hint, top_k=top_k)

        # 4) TableRow + TableRegistry birlikte (varsa ortak TableId ile)
        out += self._search_table_hits(schema=schema, table="TableRow", terms=terms, model_hint=model_hint, top_k=top_k, join_registry=True)

        # Skora göre toparla (aynı snippet tekrarını kırp)
        out = sorted(out, key=lambda x: x.get("score", 0), reverse=True)
        seen = set()
        unique = []
        for h in out:
            key = h["snippet"][:180]
            if key in seen:
                continue
            seen.add(key)
            unique.append(h)
            if len(unique) >= top_k:
                break
        return unique
