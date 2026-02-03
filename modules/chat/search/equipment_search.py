# modules/chat/search/equipment_search.py

import logging
from modules.chat.search.base_search import BaseSearch

logger = logging.getLogger("EquipmentSearch")
logger.setLevel(logging.INFO)


class EquipmentSearch(BaseSearch):
    """
    Donanım (EquipmentList) arama motoru.
    Tablo: EquipmentList_KODA_<MODEL>_MY_20251
    """

    SIM_THRESHOLD = 0.65   # eşik

    def __init__(self):
        super().__init__()
        print("\n[EquipmentSearch] Initialized\n")

    # ---------------------------------------------------------------
    # Modelin equipment tablosunu oku
    # ---------------------------------------------------------------
    def _load_equipment_table(self, model):
        table = f"EquipmentList_KODA_{model.upper()}_MY_20251"
        print(f"[Equipment] Tablo okunuyor: {table}")

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(f"SELECT * FROM dbo.{table}")
            rows = cursor.fetchall()
            columns = [c[0] for c in cursor.description]
        except Exception as e:
            print("[Equipment] Tablo okunamadı:", e)
            return None, None

        return rows, columns

    # ---------------------------------------------------------------
    # detected_feature kullanarak similarity hesaplama
    # ---------------------------------------------------------------
    def _extract_feature(self, detected_feature, rows, columns):

        if not detected_feature:
            print("[Equipment] detected_feature yok → INSIGHT=0")
            return None, 0.0

        feature_norm = self._normalize_feature_text(detected_feature)

        if "Ozellik" not in columns:
            print("[Equipment] Tabloda Ozellik kolonu yok!")
            return None, 0.0

        idx = columns.index("Ozellik")
        sims = []

        for r in rows:
            ft_raw = str(r[idx])
            ft_norm = self._normalize_feature_text(ft_raw)
            sim1 = self._similarity(feature_norm, ft_norm)
            sim2 = self._token_similarity(feature_norm, ft_norm)
            sim  = max(sim1, sim2)
            sims.append((sim, ft_raw))

        sims_sorted = sorted(sims, reverse=True)[:3]

        print("\n------------ [EQUIPMENT] TOP 3 SIMILARITY -------------")
        for sc, ft in sims_sorted:
            print(f"  • '{ft}'  →  sim={sc:.4f}")
        print("--------------------------------------------------------\n")

        best_score, best_feature = sims_sorted[0]
        return best_feature, best_score

    # ---------------------------------------------------------------
    # ANA RUN FONKSİYONU
    # ---------------------------------------------------------------
    def run(self, message, model, detected_feature):

        print("\n===================== [EQUIPMENT ENGINE] =====================")
        print(f"  → MESAJ:            {message}")
        print(f"  → MODEL:            {model}")
        print(f"  → DETECTED FEATURE: {detected_feature}")
        print("==============================================================\n")

        # 1) Tabloyu yükle
        rows, columns = self._load_equipment_table(model)
        if not rows:
            return {"insight": 0}

        # 2) Feature extract
        best_feature, best_score = self._extract_feature(detected_feature, rows, columns)

        # --- BEST FEATURE YOK
        if not best_feature:
            print("[Equipment] Feature bulunamadı → INSIGHT=-1")
            return {
                "insight": -1,
                "model": model,
                "feature": detected_feature,
                "reason": "not_available"
            }

        print(f"  ✔ SEÇİLEN FEATURE → '{best_feature}' | SCORE={best_score:.4f}")

        # --- SIMILARITY EŞİK ALTINDA
        if best_score < self.SIM_THRESHOLD:
            print(f"  ✖ Threshold düşük → BU MODELDE YOK → INSIGHT=-1")
            return {
                "insight": -1,
                "model": model,
                "feature": detected_feature,
                "reason": "not_available"
            }

        # 4) Eşleşen satırı bul
        idx = columns.index("Ozellik")
        matched_row = None
        for r in rows:
            if str(r[idx]).lower().strip() == best_feature.lower().strip():
                matched_row = r
                break

        # --- EXACT ROW MATCH YOKSA
        if not matched_row:
            print("[Equipment] DB row bulunamadı → FEATURE YOK → INSIGHT=-1")
            return {
                "insight": -1,
                "model": model,
                "feature": detected_feature,
                "reason": "not_available"
            }

        print("------------ [EQUIPMENT] SEÇİLEN DB SATIRI -------------")
        print("  Ozellik :", best_feature)
        for col, val in zip(columns, matched_row):
            print(f"  {col:15} : {val}")
        print("--------------------------------------------------------\n")

        # Trim / value kolonlarını topla
        values = []
        for col, val in zip(columns, matched_row):
            if col.lower() in ["id", "model", "ozellik"]:
                continue
            values.append({"trim": col, "value": str(val)})

        # JSON üret
        result = {
            "insight": 1,
            "model": model,
            "category": "equipment",
            "query_text": message,
            "detected_feature": detected_feature,
            "db_feature": best_feature,
            "db_values": values
        }

        print("============= [EQUIPMENT] INSIGHT=1 → JSON ÇIKTISI =============")
        print(result)
        print("=================================================================\n")

        return result
