# ================================================================
# ===============     MULTI FEATURE ENGINE      ===================
# ================   (GENEL ORCHESTRATOR)   =======================
# ================================================================

import re
from modules.chat.search.SearchRouter import SearchRouter
from modules.chat.search.technic_search import TechnicSearch
from modules.chat.search.equipment_search import EquipmentSearch


class MultiFeatureEngine:
    """
    Genel orchestrator:
    - Tek model → Çoklu feature (max 3)
    - Her parse için kategori + feature tespiti
    - Kategoriye göre doğru search engine’i çalıştırır
    - Sonuçları array halinde toplar
    """

    MAX_FEATURES = 3

    def __init__(self):
        print("\n[MultiFeature] Engine initialized")
        self.router = SearchRouter()
        self.tech_engine = TechnicSearch()
        self.eq_engine = EquipmentSearch()
        # ileride: self.price_engine = PriceSearch() gibi eklenebilir


    # ------------------------------------------------------------
    # Mesajı 1–3 parçaya ayır
    # ------------------------------------------------------------
    def _split_message(self, message):
        print("\n[MultiFeature] Mesaj parçalanıyor...")

        parts = re.split(r"\s+ve\s+|\s+ile\s+|,|\s+veya\s+", message)
        parts = [p.strip() for p in parts if p.strip()]

        print(f"[MultiFeature] BULUNAN PARÇALAR → {parts}")

        return parts[:self.MAX_FEATURES]

    def _map_models_to_features(self, message, models, features):
        msg = self.router._normalize_tr(message)
        pairs = []

        # --------------------------------------------
        # 1) TEK MODEL → TÜM FEATURE'LARI VER
        # --------------------------------------------
        if len(models) == 1:
            model = models[0]
            for f in features:
                pairs.append((model, f))
            return pairs

        # --------------------------------------------
        # 2) ÇOKLU MODEL → EN YAKIN FEATURE'I SEÇ
        # --------------------------------------------
        for model in models:
            model_norm = self.router._normalize_tr(model)
            model_pos = msg.find(model_norm)

            best_feature = None
            best_distance = 999999

            for f in features:
                matched_norm = self.router._normalize_tr(f["matched"])
                feat_pos = msg.find(matched_norm)

                # Feature bulunamadıysa atla
                if feat_pos == -1:
                    continue

                # Modelden ÖNCE gelen özellik bu modele ait değildir
                if feat_pos < model_pos:
                    continue

                # Mesafe hesabı
                dist = feat_pos - model_pos

                if dist < best_distance:
                    best_distance = dist
                    best_feature = f

            # Eğer uygun bir feature bulunduysa ekle
            if best_feature:
                pairs.append((model, best_feature))

        return pairs


    def _extract_trim_from_field(self, field_value):
        """
        TechnicSearch için TRIM'i 'field' değerinden çıkarır.
        Örnek:
        'Kamiq_Elite_1_0_TSI_115_PS_DSG'
        Çıktı:
        'Elite 1.0 TSI 115 PS DSG'
        """
        if not field_value:
            return None

        parts = field_value.split("_")

        # ilk parça 'Kamiq' → trim değil
        trim_parts = parts[1:]  

        # Okunabilir hale getir
        return " ".join(trim_parts)

    # ------------------------------------------------------------
    # ANA ÇALIŞMA FONKSİYONU
    # ------------------------------------------------------------
    def process(self, message, models: list):

        print("\n=============== [MULTI FEATURE ENGINE BAŞLADI] ===============")
        print(f"Mesaj : {message}")
        print(f"Modeller : {models}")
        print("===============================================================\n")

        # ----------------------------------------------------
        # 0) MODEL KONTROLÜ
        # ----------------------------------------------------
        if not models:
            print("[MultiFeature] Model bulunamadı → INSIGHT=0")
            return {"insight": 0, "results": []}

        # ----------------------------------------------------
        # 1) FEATURE EXTRACTION (çoklu)
        # ----------------------------------------------------
        features = self.router.detect_all_features(message)
        print("[MultiFeature] Bulunan özellikler:", features)

        if not features:
            print("[MultiFeature] Hiç feature bulunamadı → INSIGHT=0")
            return {"insight": 0, "results": []}

        # ----------------------------------------------------
        # 2) MODEL–FEATURE MAPPING (matched üzerinden)
        # ----------------------------------------------------
        pairs = self._map_models_to_features(message, models, features)
        print("[MultiFeature] MODEL-FEATURE eşleşmeleri:", pairs)

        results = []
        overall_insight = 0

        # ----------------------------------------------------
        # 3) HER MODEL + FEATURE İŞLENİR
        # ----------------------------------------------------
        for model, feature_obj in pairs:

            if not feature_obj:
                print(f"[WARN] {model.upper()} için feature eşleşmedi → insight=0")
                results.append({
                    "model": model,
                    "feature": None,
                    "category": None,
                    "insight": 0,
                    "reason": "no_feature_found"
                })
                continue

            feature_main = feature_obj["main"]
            matched_text = feature_obj["matched"]

            print(f"\n--- İşleniyor: MODEL={model.upper()} | MAIN={feature_main} | MATCHED={matched_text}")

            # ----------------------------------------------------
            # 3.1) KATEGORİ DOĞRULAMA (SearchRouter → similarity check)
            # ----------------------------------------------------
            info = self.router.detect_category(matched_text)
            category = info["category"]

            print(f"[DEBUG] Kategori tespiti: {category}")

            if not category:
                print(f"[WARN] {model.upper()} için kategori bulunamadı → insight=0")
                results.append({
                    "model": model,
                    "feature": feature_main,
                    "category": None,
                    "insight": 0,
                    "reason": "no_category"
                })
                continue

            # ----------------------------------------------------
            # 3.2) ENGINE SEÇİMİ
            # ----------------------------------------------------
            if category == "technic":
                print("[ENGINE] → TechnicSearch çalışıyor...")
                res = self.tech_engine.run(message, model, feature_main)

            elif category == "equipment":
                print("[ENGINE] → EquipmentSearch çalışıyor...")
                res = self.eq_engine.run(message, model, feature_main)

            else:
                print(f"[WARN] Bilinmeyen kategori '{category}' → insight=0")
                res = {
                    "model": model,
                    "feature": feature_main,
                    "category": category,
                    "insight": 0
                }

            # ----------------------------------------------------
            # 3.3) Sonucu ekle
            # ----------------------------------------------------
            results.append(res)
            if res.get("insight") == 1:
                overall_insight = 1


        # ----------------------------------------------------
        # 4) FINAL RESULT
        # ----------------------------------------------------
        print("\n================= [MULTI FEATURE SONUÇ] ==================")
        print(f"[MultiFeature] OVERALL INSIGHT → {overall_insight}")
        print("[MultiFeature] TÜM SONUÇ BLOKLARI:")
        for r in results:
            print("   →", r)
        print("==========================================================\n")
        
        
        # ===========================================================
        # 5) CLEAN & MINIMAL JSON — LLM için sade veri hazırlanıyor
        # ===========================================================

        clean_results = []

        for r in results:

            model = r.get("model")
            feature = r.get("db_feature") or r.get("feature")

            if not model or not feature:
                continue

            # 1) BULUNAN ÖZELLİK
            if r.get("insight") == 1:
                values = r.get("db_values") or []
                value_list = []

                for v in values:
                    if isinstance(v, dict):
                        trim = v.get("trim") or self._extract_trim_from_field(v.get("field"))
                        val = v.get("value")
                        value_list.append(f"{trim}: {val}")

                clean_results.append({
                    "model": model.capitalize(),
                    "feature": feature,
                    "value": " | ".join(value_list),
                    "status": "found"
                })

            # 2) BU MODELDE BU ÖZELLİK YOK
            elif r.get("insight") == -1:
                clean_results.append({
                    "model": model.capitalize(),
                    "feature": feature,
                    "status": "not_found"
                })

        # --- FINAL INSIGHT KARARI ---

        if any(r["status"] == "found" for r in clean_results):
            final_insight = 1
        elif any(r["status"] == "not_found" for r in clean_results):
            final_insight = -1
        else:
            final_insight = 0

        return {
            "insight": final_insight,
            "user_query": message,
            "results": clean_results
        }


