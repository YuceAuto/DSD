import os

class Config:
    def __init__(self):
        # static/images yolu
        self.static_path = os.path.join(os.getcwd(), "static")
        self.image_paths = os.path.join(self.static_path, "images")

        # Stopwords (görsel aramada ayıklanacak kelimeler)
        self.stopwords = {
            "model", "araç", "arac", "paylaşabilir", "paylaşır",
            "misin", "mısın", "lütfen", "istiyorum", "?",
            "görsel", "resim", "fotoğraf", "fotograf"
        }

        # =================================================
        # A S S I S T A N T   C O N F I G
        # =================================================
        self.ASSISTANT_CONFIG = {
            "asst_zHRanQW6MFeNJGT0jHpoFui9": ["Kamiq"],
            "asst_ird4cTcv0F7GfD8wNP6EeY6m": ["Fabia"],
            "asst_auvtMOFGNr5eBTdpj84djsHl": ["Scala"],
            "asst_tsOiy8kcBg5LFj9y5GIExhVp": ["Karoq"],
            "asst_wtNfFO8xRIxkIllnd3jSniX4": ["Enyaq"],
            "asst_k5bzE3OgZPHWqqznI9Q6xZWu": ["Elroq"],
            "asst_B6FOudmcuC87S8ShPscN8GKs": ["Superb"],
            # YENİ: KODIAQ
            "asst_RsNmuLkbWbScrgE1crVV38Ct": ["Kodiaq"],
            "asst_5UshQUbxpJBu49DHIeeNalqW": ["Octavia"]
        }

        self.ASSISTANT_NAME_MAP = {
            "asst_zHRanQW6MFeNJGT0jHpoFui9": "Kamiq",
            "asst_ird4cTcv0F7GfD8wNP6EeY6m": "Fabia",
            "asst_auvtMOFGNr5eBTdpj84djsHl": "Scala",
            "asst_tsOiy8kcBg5LFj9y5GIExhVp": "Karoq",
            "asst_wtNfFO8xRIxkIllnd3jSniX4": "Enyaq",
            "asst_k5bzE3OgZPHWqqznI9Q6xZWu": "Elroq",
            "asst_B6FOudmcuC87S8ShPscN8GKs": "Superb",
            # YENİ: KODIAQ
            "asst_RsNmuLkbWbScrgE1crVV38Ct": "Kodiaq",
            "asst_5UshQUbxpJBu49DHIeeNalqW": "Octavia"
        }

        # Bilinen renkler
        self.KNOWN_COLORS = [
            "ay beyazı",
            "gümüş",
            "çelik gri",
            "grafit gri",
            "büyülü siyah",
            "kadife kırmızısı",
            "yarış mavisi",
            "phoenix turuncu"
        ]
        self.MODEL_VALID_TRIMS = {
            # … mevcut modeller …
            "kodiaq": ["premium", "prestige", "sportline", "rs"],
            "superb": ["premium", "prestige", "l&k crystal", "sportline phev"],
            "octavia": ["elite", "premium", "prestige", "sportline", "rs"],
            "test": ["premium", "prestige", "sportline", "e-Prestige 60"]
}

        # A) Monte Carlo listesi (12 adım)
        self.monte_carlo_12 = [
            ["monte", "carlo", "direksiyon", "simidi"],
            ["monte", "carlo", "döşeme", "standart"],
            ["monte", "carlo", "döşeme", "opsiyonel"],
            ["monte", "carlo", "ön", "dekor", "standart"],
            ["monte", "carlo", "ön", "dekor", "opsiyonel"],
            ["monte", "carlo", "ön", "konsol", "standart"],
            ["monte", "carlo", "ön", "konsol", "opsiyonel"],
            ["monte", "carlo", "gösterge", "paneli"],
            ["monte", "carlo", "multimedya"],
            ["monte", "carlo", "jant", "standart"],
            ["monte", "carlo", "opsiyonel", "pjf", "jant"],
            ["monte", "carlo", "jant", "opsiyonel"]
        ]

        # B) Premium/Elite listesi (12 adım)
        self.premium_elite_12 = [
            ["direksiyon", "simidi"],
            ["döşeme", "standart"],
            ["döşeme", "opsiyonel"],
            ["ön", "dekor", "standart"],
            ["ön", "dekor", "opsiyonel"],
            ["ön", "konsol", "standart"],
            ["ön", "konsol", "opsiyonel"],
            ["gösterge", "paneli"],
            ["multimedya"],
            ["jant", "standart"],
            ["jant", "opsiyonel"],
            ["premium", "ve", "monte", "carlo", "opsiyonel", "pjf", "jant"]
        ]

        # C) Fabia / Scala / Kamiq (12 adım)
        self.fabia_12 = [
            ["fabia", "direksiyon", "simidi"],
            ["fabia", "döşeme", "standart"],
            ["fabia", "döşeme", "opsiyonel"],
            ["fabia", "ön", "dekor", "standart"],
            ["fabia", "ön", "dekor", "opsiyonel"],
            ["fabia", "ön", "konsol", "standart"],
            ["fabia", "ön", "konsol", "opsiyonel"],
            ["fabia", "gösterge", "paneli"],
            ["fabia", "multimedya"],
            ["fabia", "jant", "standart"],
            ["fabia", "jant", "opsiyonel"],
            ["fabia", "opsiyonel", "pjf", "jant"]
        ]
        self.scala_12 = [
            ["scala", "direksiyon", "simidi"],
            ["scala", "döşeme", "standart"],
            ["scala", "döşeme", "opsiyonel"],
            ["scala", "ön", "dekor", "standart"],
            ["scala", "ön", "dekor", "opsiyonel"],
            ["scala", "ön", "konsol", "standart"],
            ["scala", "ön", "konsol", "opsiyonel"],
            ["scala", "gösterge", "paneli"],
            ["scala", "multimedya"],
            ["scala", "jant", "standart"],
            ["scala", "jant", "opsiyonel"],
            ["scala", "opsiyonel", "pjf", "jant"]
        ]
        self.kamiq_12 = [
            ["kamiq", "direksiyon", "simidi"],
            ["kamiq", "döşeme", "standart"],
            ["kamiq", "döşeme", "opsiyonel"],
            ["kamiq", "ön", "dekor", "standart"],
            ["kamiq", "ön", "dekor", "opsiyonel"],
            ["kamiq", "ön", "konsol", "standart"],
            ["kamiq", "ön", "konsol", "opsiyonel"],
            ["kamiq", "gösterge", "paneli"],
            ["kamiq", "multimedya"],
            ["kamiq", "jant", "standart"],
            ["kamiq", "jant", "opsiyonel"],
            ["kamiq", "opsiyonel", "pjf", "jant"]
        ]

        # Scala özel sıralama
        self.custom_order_scala = [
            ["scala", "monte", "carlo", "standart", "direksiyon", "simidi"],
            ["scala", "premium", "standart", "direksiyon", "simidi"],
            ["scala", "elite", "standart", "direksiyon", "simidi"],
            ["scala", "monte", "carlo", "standart", "döşeme"],
            ["scala", "monte", "carlo", "standart", "kapı", "döşeme"],
            ["scala", "premium", "lodge", "standart", "döşeme"],
            ["scala", "premium", "lodge", "standart", "kapı", "döşeme"],
            ["scala", "premium", "suite", "opsiyonel", "döşeme"],
            ["scala", "premium", "suite", "opsiyonel", "kapı", "döşeme"],
            ["scala", "elite", "studio", "standart", "döşeme"],
            ["scala", "elite", "studio", "standart", "kapı", "döşeme"],
            ["scala", "monte", "carlo", "standart", "ön", "dekor"],
            ["scala", "premium", "lodge", "standart", "ön", "dekor"],
            ["scala", "premium", "suite", "opsiyonel", "ön", "dekor"],
            ["scala", "elite", "studio", "standart", "ön", "dekor"],
            ["scala", "monte", "carlo", "standart", "ön", "konsol"],
            ["scala", "premium", "lodge", "standart", "ön", "konsol"],
            ["scala", "premium", "suite", "opsiyonel", "ön", "konsol"],
            ["scala", "elite", "studio", "standart", "ön", "konsol"],
            ["scala", "monte", "carlo", "standart", "dijital", "gösterge", "paneli"],
            ["scala", "premium", "standart", "gösterge", "paneli"],
            ["scala", "elite", "standart", "gösterge", "paneli"],
            ["scala", "monte", "carlo", "standart", "multimedya", "sistemi"],
            ["scala", "premium", "standart", "multimedya", "sistemi"],
            ["scala", "elite", "standart", "multimedya", "sistemi"],
            ["scala", "monte", "carlo", "pji", "standart", "jant"],
            ["scala", "premium", "pj5", "standart", "jant"],
            ["scala", "1.0", "premium", "pj7", "opsiyonel", "jant"],
            ["scala", "premium", "pjg", "opsiyonel", "jant"],
            ["scala", "premium", "pjn", "opsiyonel", "jant"],
            ["scala", "premium", "pjp", "opsiyonel", "jant"],
            ["scala", "elite", "pj5", "standart", "jant"],
            ["scala", "elite", "pj7", "opsiyonel", "jant"],
            ["scala", "elite", "pjg", "opsiyonel", "jant"],
            ["scala", "elite", "pjp", "opsiyonel", "jant"],
            ["scala", "ay", "beyazı"],
            ["scala", "gümüş"],
            ["scala", "çelik", "gri"],
            ["scala", "grafit", "gri"],
            ["scala", "büyülü", "siyah"],
            ["scala", "kadife", "kırmızısı"],
            ["scala", "yarış", "mavisi"]
        ]

        # Kamiq özel sıralama
        self.custom_order_kamiq = [
            ["kamiq", "monte", "carlo", "standart", "direksiyon", "simidi"],
            ["kamiq", "premium", "standart", "direksiyon", "simidi"],
            ["kamiq", "elite", "standart", "direksiyon", "simidi"],
            ["kamiq", "monte", "carlo", "standart", "döşeme"],
            ["kamiq", "monte", "carlo", "standart", "kapı", "döşeme"],
            ["kamiq", "premium", "lodge", "standart", "döşeme"],
            ["kamiq", "premium", "lodge", "standart", "kapı", "döşeme"],
            ["kamiq", "premium", "suite", "opsiyonel", "döşeme"],
            ["kamiq", "premium", "suite", "opsiyonel", "kapı", "döşeme"],
            ["kamiq", "elite", "studio", "standart", "döşeme"],
            ["kamiq", "elite", "studio", "standart", "kapı", "döşeme"],
            ["kamiq", "monte", "carlo", "standart", "ön", "dekor"],
            ["kamiq", "premium", "lodge", "standart", "ön", "dekor"],
            ["kamiq", "premium", "suite", "opsiyonel", "ön", "dekor"],
            ["kamiq", "elite", "studio", "standart", "ön", "dekor"],
            ["kamiq", "monte", "carlo", "standart", "ön", "konsol"],
            ["kamiq", "premium", "lodge", "standart", "ön", "konsol"],
            ["kamiq", "premium", "suite", "opsiyonel", "ön", "konsol"],
            ["kamiq", "elite", "studio", "standart", "ön", "konsol"],
            ["kamiq", "monte", "carlo", "standart", "dijital", "gösterge", "paneli"],
            ["kamiq", "premium", "standart", "gösterge", "paneli"],
            ["kamiq", "elite", "standart", "gösterge", "paneli"],
            ["kamiq", "monte", "carlo", "standart", "multimedya", "sistemi"],
            ["kamiq", "premium", "standart", "multimedya", "sistemi"],
            ["kamiq", "elite", "standart", "multimedya", "sistemi"],
            ["kamiq", "monte", "carlo", "pji", "standart", "jant"],
            ["kamiq", "premium", "pjg", "standart", "jant"],
            ["kamiq", "1.0", "premium", "pj7", "opsiyonel", "jant"],
            ["kamiq", "premium", "pjg", "opsiyonel", "jant"],
            ["kamiq", "premium", "pjn", "opsiyonel", "jant"],
            ["kamiq", "premium", "pjp", "opsiyonel", "jant"],
            ["kamiq", "elite", "p02", "standart", "jant"],
            ["kamiq", "1.0", "elite", "pj7", "opsiyonel", "jant"],
            ["kamiq", "elite", "pjg", "opsiyonel", "jant"],
            ["kamiq", "elite", "pjp", "opsiyonel", "jant"],
            ["kamiq", "ay", "beyazı"],
            ["kamiq", "gümüş"],
            ["kamiq", "graptihe", "gri"],
            ["kamiq", "büyülü", "siyah"],
            ["kamiq", "kadife", "kırmızısı"],
            ["kamiq", "yarış", "mavisi"],
            ["kamiq", "phoenix", "turuncu"]
        ]