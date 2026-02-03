# modules/chat/search/technic_search.py

import logging
from modules.chat.search.base_search import BaseSearch

logger = logging.getLogger("TechnicSearch")
logger.setLevel(logging.INFO)


class TechnicSearch(BaseSearch):
    """
    Teknik özellik arama motoru.
    Tablo: Imported_KODA_<MODEL>_MY_20251
    """

    SIM_THRESHOLD = 0.65

    def __init__(self):
        super().__init__()
        print("\n[TechnicSearch] Initialized\n")

    # ---------------------------------------------------------------
    def _load_technic_table(self, model):
        table = f"Imported_KODA_{model.upper()}_MY_20251"
        print(f"[Technic] Tablo okunuyor: {table}")

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(f"SELECT * FROM dbo.{table}")
            rows = cursor.fetchall()
            columns = [c[0] for c in cursor.description]
        except Exception as e:
            print("[Technic] Tablo okunamadı:", e)
            return None, None

        return rows, columns

    # ---------------------------------------------------------------
    def _extract_feature(self, detected_feature, rows, columns):

        if not detected_feature:
            print("[Technic] detected_feature yok → INSIGHT=0")
            return None, 0.0

        # gelişmiş normalize
        feature_norm = self._normalize_feature_text(detected_feature)

        if "Ozellik" not in columns:
            print("[Technic] Tabloda Ozellik yok!")
            return None, 0.0

        idx = columns.index("Ozellik")
        sims = []

        for r in rows:
            ft_raw = str(r[idx])
            ft_norm = self._normalize_feature_text(ft_raw)

            sim = self._similarity(feature_norm, ft_norm)
            sims.append((sim, ft_raw))

        sims_sorted = sorted(sims, reverse=True)[:3]

        print("\n[Technic] ==== TOP 3 SIMILARITY ====")
        for sc, ft in sims_sorted:
            print(f"  {ft} → sim={sc:.4f}")
        print("====================================\n")

        best_score, best_feature = sims_sorted[0]
        return best_feature, best_score


    # ---------------------------------------------------------------
    def run(self, message, model, detected_feature):

        print("\n================= [TECHNIC ENGINE START] =================")
        print(f"  → MESAJ:            {message}")
        print(f"  → MODEL:            {model}")
        print(f"  → DETECTED FEATURE: {detected_feature}")
        print("==========================================================\n")

        rows, columns = self._load_technic_table(model)
        if not rows:
            return {"insight": 0}

        best_feature, best_score = self._extract_feature(detected_feature, rows, columns)

        if not best_feature:
            print("[Technic] Feature bulunamadı → INSIGHT=-1")
            return {
                "insight": -1,
                "model": model,
                "feature": detected_feature,
                "reason": "not_available"
            }

        print(f"[Technic] En iyi eşleşen özellik: {best_feature} (sim={best_score:.4f})")

        if best_score < self.SIM_THRESHOLD:
            print(f"[Technic] sim<{self.SIM_THRESHOLD} → FEATURE YOK → INSIGHT=-1")
            return {
                "insight": -1,
                "model": model,
                "feature": detected_feature,
                "reason": "not_available"
            }

        idx = columns.index("Ozellik")
        matched_row = None
        for r in rows:
            if str(r[idx]).lower().strip() == best_feature.lower().strip():
                matched_row = r
                break

        # ❗ EXACT ROW MATCH YOKSA → MODELDE BU ÖZELLİK YOK
        if not matched_row:
            print("[Technic] DB row bulunamadı → FEATURE YOK → INSIGHT=-1")
            return {
                "insight": -1,
                "model": model,
                "feature": detected_feature,
                "reason": "not_available"
            }

        values = []
        for col, val in zip(columns, matched_row):
            if col.lower() in ["id", "model", "ozellik"]:
                continue
            values.append({"field": col, "value": str(val)})

        result = {
            "insight": 1,
            "model": model,
            "category": "technic",
            "query_text": message,
            "detected_feature": detected_feature,
            "db_feature": best_feature,
            "db_values": values
        }

        print("============= [TECHNIC] INSIGHT=1 JSON ]==============")
        print(result)
        print("=======================================================\n")

        return result


