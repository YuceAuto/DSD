# modules/search/base_search.py

import logging
import pyodbc
import difflib
import re

logger = logging.getLogger("BaseSearch")
logger.setLevel(logging.INFO)


class BaseSearch:
    """
    Arama motorları için ortak altyapı:
    - SQL connection
    - similarity hesaplama
    - normalize (boşluk temizleme + synonym temizleme SearchRouter tarafından yapılacak)
    """

    def __init__(self):
        logger.info("[BaseSearch] Initialized")

    # ---------------------------------------------------------------
    # SQL BAĞLANTISI
    # ---------------------------------------------------------------
    def _connect(self):
        return pyodbc.connect(
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=10.0.0.20\\SQLYC;"
            "DATABASE=SkodaBot;"
            "UID=skodabot;"
            "PWD=Skodabot.2024;"
        )

    # ---------------------------------------------------------------
    # SIMILARITY (difflib)
    # ---------------------------------------------------------------
    def _similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

    # ---------------------------------------------------------------
    # TEMEL NORMALIZE (sadece boşluklar, özel karakterler)
    # NOTE: Synonym normalize artık SearchRouter yapacak!
    # ---------------------------------------------------------------
    def _basic_normalize(self, text: str) -> str:
        if not text:
            return ""
        t = text.lower()
        t = re.sub(r"\s+", " ", t)  # fazla boşluk
        t = t.strip()
        return t
    # ---------------------------------------------------------------
    # TÜRKÇE NORMALİZASYON (diakritik kaldırma)
    # ---------------------------------------------------------------
    def _normalize_tr(self, text: str) -> str:
        if not text:
            return ""

        t = text.lower()
        replacements = {
            "ç": "c",
            "ğ": "g",
            "ı": "i",
            "ö": "o",
            "ş": "s",
            "ü": "u",
        }

        for src, tgt in replacements.items():
            t = t.replace(src, tgt)

        t = re.sub(r"\s+", " ", t).strip()
        return t
    
    def _normalize_feature_text(self, text: str):
        if not text:
            return ""

        import re
        t = text.lower()

        # Türkçe karakter düzeltme
        t = self._normalize_tr(t)

        # özel karakterleri temizle
        t = t.replace("(", " ").replace(")", " ")
        t = t.replace("–", "-").replace("—", "-")
        t = t.replace("/", " ")
        t = t.replace(",", " ")

        # km/h -> km h
        t = t.replace("km/h", "km h").replace("km h", "km h")

        # fazla boşluk
        t = re.sub(r"\s+", " ", t).strip()

        return t
    
    def _token_similarity(self, a: str, b: str) -> float:
        a = self._normalize_feature_text(a)
        b = self._normalize_feature_text(b)

        ta = set(a.split())
        tb = set(b.split())

        if not ta or not tb:
            return 0.0

        intersection = len(ta.intersection(tb))
        union = len(ta.union(tb))

        return intersection / union

    # ---------------------------------------------------------------
    # DEBUG PRINT (tüm search engine’lerde ortak)
    # ---------------------------------------------------------------
    def _debug(self, *args):
        """Terminal çıktılarını kolay yönetmek için."""
        print("[SEARCH-DEBUG]:", *args)


   

