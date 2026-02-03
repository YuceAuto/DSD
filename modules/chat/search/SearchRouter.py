# modules/chat/search/search_router.py
# SearchRouter (Uzun – Eski Yapıya Benzer – Yeni Feature Tabanlı)

import re
import logging
from modules.chat.search.base_search import BaseSearch

logger = logging.getLogger("SearchRouter")
logger.setLevel(logging.INFO)


class SearchRouter(BaseSearch):
    """
    Yeni SearchRouter:
    - NLU_Keywords tamamen kaldırıldı
    - Kategori tespitini sadece Feature_Keywords_Technical & Feature_Keywords_Donanim üzerinden yapar
    - Similarity hesaplamaları eski yapıya benzer blok akışında tutuldu
    - detect_feature = feature_main (DB'deki Ozellik ile %100 uyumlu)
    """

    TECH_TABLE = "Feature_Keywords_Technical"
    EQ_TABLE   = "Feature_Keywords_Donanim"
    SIM_THRESHOLD = 0.65  # kategori seçme eşiği

    def __init__(self):
        super().__init__()
        print("\n=================[ SearchRouter Initialized ]=================")
        print("   Yeni sistem aktif → Feature tabanlı kategori tespiti")
        print("===============================================================\n")

    # =====================================================================
    # TABLO OKUMA BLOĞU (uzun form)
    # =====================================================================
    def _read_feature_table(self, table_name):
        """
        Verilen Feature_Keywords tablosunu okur.
        Dönüş: [(feature_main, synonyms)]
        """
        print(f"[DB] '{table_name}' tablosu okunuyor...")

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(f"SELECT feature_main, synonyms FROM dbo.{table_name}")
            rows = cursor.fetchall()
            print(f"[DB] {table_name} → {len(rows)} satır çekildi\n")
        except Exception as e:
            print(f"[ERR] Tablo okunamadı: {table_name}", e)
            return []

        return rows

    # =====================================================================
    # ANA SIMILARITY HESAPLAMA BLOĞU (uzun, açıklamalı)
    # =====================================================================
    def _calc_best_similarity(self, message_norm, rows, table_label):
        """
        Tablodaki tüm feature_main & synonyms üzerinden similarity skorlarını hesaplar.
        Ancak ekrana sadece TOP-3 sonucu yazar.
        """

        print(f"\n----- [{table_label}] Similarity Hesaplaması Başladı -----")

        sim_list = []  # (sim, feature_main, matched_text)

        # 1) Tüm similarity değerlerini hesapla ama LOG basma
        for main, syn in rows:
            main_norm = self._normalize_tr(main or "")
            syn_norm  = self._normalize_tr(syn or "")

            syn_list = [s.strip() for s in syn_norm.split(";")] if syn_norm else []

            # synonyms similarity
            for s in syn_list:
                if not s:
                    continue

                if s in message_norm:
                    sim = 1.0
                else:
                    sim = self._similarity(message_norm, s)

                sim_list.append((sim, main, s))

            # feature_main similarity
            sim_main = self._similarity(message_norm, main_norm)
            sim_list.append((sim_main, main, main_norm))

        # Hiç eşleşme yoksa
        if not sim_list:
            print(f"[{table_label}] Eşleşme bulunamadı.\n")
            return None, 0.0

        # 2) Büyükten küçüğe sırala
        sim_list_sorted = sorted(sim_list, reverse=True, key=lambda x: x[0])

        # 3) TOP-3 göster
        top3 = sim_list_sorted[:3]

        print(f"\n----- [{table_label}] TOP 3 SIMILARITY -----")
        for sim, main, text in top3:
            print(f"  • MAIN='{main}' | MATCH='{text}' | sim={sim:.4f}")
        print("------------------------------------------------------------\n")

        # 4) En iyi sonucu döndür
        best_sim, best_main, best_text = sim_list_sorted[0]

        return best_main, best_sim

    # =====================================================================
    # KATEGORI TESPIT BLOĞU
    # =====================================================================
    def detect_category(self, feature_text):
        """
        Tek bir özelliğin teknik mi donanım mı olduğunu belirler.
        Eğer hiçbir kategori yeterince güçlü değilse → kategori=None döner.
        """
        print("\n--- CATEGORY CHECK FOR FEATURE ---")
        print("Feature Text :", feature_text)

        f_norm = self._normalize_tr(feature_text)

        # Feature tablolarını oku
        tech_rows = self._read_feature_table(self.TECH_TABLE)
        eq_rows   = self._read_feature_table(self.EQ_TABLE)

        best_tech = 0.0
        best_eq   = 0.0

        # ---- TECH SIMILARITY ----
        for main, syn in tech_rows:
            main_norm = self._normalize_tr(main or "")
            best_tech = max(best_tech, self._similarity(f_norm, main_norm))

            if syn:
                for s in syn.split(";"):
                    s_norm = self._normalize_tr(s)
                    best_tech = max(best_tech, self._similarity(f_norm, s_norm))

        # ---- EQUIPMENT SIMILARITY ----
        for main, syn in eq_rows:
            main_norm = self._normalize_tr(main or "")
            best_eq = max(best_eq, self._similarity(f_norm, main_norm))

            if syn:
                for s in syn.split(";"):
                    s_norm = self._normalize_tr(s)
                    best_eq = max(best_eq, self._similarity(f_norm, s_norm))

        print(f"TECH SIM: {best_tech:.3f} | EQUIP SIM: {best_eq:.3f}")

        # ---- EŞİK KONTROLÜ ----
        if best_tech < self.SIM_THRESHOLD and best_eq < self.SIM_THRESHOLD:
            print("Kategori bulunamadı (eşikler düşük) → None")
            return {"category": None}

        # ---- KATEGORI SEÇ ----
        if best_tech >= best_eq:
            print("→ KATEGORI: TECHNIC")
            return {"category": "technic"}

        else:
            print("→ KATEGORI: EQUIPMENT")
            return {"category": "equipment"}
        
    # =====================================================================
    # YENI: Mesajdaki TÜM feature_main değerlerini çıkarır
    # =====================================================================
    def detect_all_features(self, message: str):
        """
        Mesajdaki bütün özellikleri bulur.
        Hem feature_main hem matched synonym sağlar.
        """
        message_norm = self._normalize_tr(message)
        results = []
        seen_features = set()   # duplicate önleme

        tech_rows = self._read_feature_table(self.TECH_TABLE)
        eq_rows   = self._read_feature_table(self.EQ_TABLE)

        # --------------------------
        # 1) TECH FEATURES
        # --------------------------
        for main, syn in tech_rows:
            if not main:
                continue

            main_norm = self._normalize_tr(main)
            matched = None

            # synonyms tarama
            if syn:
                syn_list = [self._normalize_tr(s) for s in syn.split(";") if s.strip()]
                for s in syn_list:
                    if s and s in message_norm:
                        matched = s
                        break

            # direct main match
            if not matched and main_norm in message_norm:
                matched = main_norm

            # Eğer eşleştiyse ekle
            if matched and main not in seen_features:
                results.append({
                    "main": main,
                    "matched": matched,
                    "category": "technic"
                })
                seen_features.add(main)

        # --------------------------
        # 2) EQUIPMENT FEATURES
        # --------------------------
        for main, syn in eq_rows:
            if not main:
                continue

            main_norm = self._normalize_tr(main)
            matched = None

            if syn:
                syn_list = [self._normalize_tr(s) for s in syn.split(";") if s.strip()]
                for s in syn_list:
                    if s and s in message_norm:
                        matched = s
                        break

            if not matched and main_norm in message_norm:
                matched = main_norm

            if matched and main not in seen_features:
                results.append({
                    "main": main,
                    "matched": matched,
                    "category": "equipment"
                })
                seen_features.add(main)

        return results

    # =====================================================================
    #  YENİ: AKILLI MODEL TESPİTİ (tam, fuzzy, en yakın tek model)
    # =====================================================================
    def detect_models(self, message: str) -> set:
        """
        Kullanıcı mesajındaki Skoda model adlarını deterministik, 
        yüksek doğruluklu şekilde tespit eder. Fuzzy yok, findall yok.
        """

        if not message:
            return set()

        # Normalize Türkçe karakterler + temizleme
        msg = self._normalize_tr(message).lower()
        msg = re.sub(r"[^a-z0-9 ]", " ", msg)
        msg = re.sub(r"\s+", " ", msg).strip()

        MODELS = ["fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"]

        # 1) TAM KELİME EŞLEŞMESİ
        exact_matches = {m for m in MODELS if f" {m} " in f" {msg} "}
        if exact_matches:
            return exact_matches

        # 2) BİTİŞİK SUBSTRING EŞLEŞMESİ
        substring_matches = {m for m in MODELS if m in msg}
        if substring_matches:
            return substring_matches

        # 3) SAFE-PREFIX EŞLEŞMESİ (KÖK KONTROLÜ)
        MODEL_PREFIXES = {
            "fabi": "fabia",
            "scal": "scala",
            "kami": "kamiq",
            "karo": "karoq",
            "kodi": "kodiaq",
            "octa": "octavia",
            "supe": "superb",
            "enya": "enyaq",
            "elro": "elroq"
        }

        prefix_matches = set()
        for pref, model in MODEL_PREFIXES.items():
            if pref in msg:
                prefix_matches.add(model)

        return prefix_matches


