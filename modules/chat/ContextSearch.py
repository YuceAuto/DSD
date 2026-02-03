# modules/chat/ContextSearch.py
import logging
from modules.data.text_norm import normalize_tr_text
from modules.chat.nlu_config import MODEL_LIST, MODEL_TRIMS, TRIM_SYNONYMS
from modules.chat.nlu_config import TECH_SYNONYMS ,TECH_KEYWORDS
from modules.chat.nlu_config import EQUIP_SYNONYMS

logger = logging.getLogger("ContextSearch")
logger.setLevel(logging.INFO)


class ContextSearch:

    # 🚗 ROTA / MESAFE → LLM
    LLM_CONTEXT_WORDS = [
        "ankara", "istanbul", "izmir",
        "yol", "mesafe", "kaç şarj", "kaç sarj",
        "kaç km", "kaç km yol", "şehir dışı", "şehir içi"
    ]



    def __init__(self):
        logger.info("[ContextSearch] Initialized")

    # 🔍 MODEL TESPİTİ
    def detect_model(self, msg: str):
        for m in MODEL_LIST:
            if m in msg:
                return m
        return None

    # 🔍 TRIM TESPİTİ (opsiyonel)
    def detect_trim(self, msg: str, model: str | None):
        if not model:
            return None
        for trim in MODEL_TRIMS.get(model, []):
            if trim in msg:
                return trim
        for syn, real in TRIM_SYNONYMS.items():
            if syn in msg and real in MODEL_TRIMS.get(model, []):
                return real
        return None

    # 🔍 TEKNİK ÖZELLİK TESPİTİ
    def detect_technical_feature(self, msg: str):
        msg = msg.lower()

        # exact matches
        for kw in TECH_KEYWORDS:
            if kw in msg:
                return kw

        # synonym matches
        for syn, real in TECH_SYNONYMS.items():
            if syn in msg:
                return real

        return None
    
    # 🔍 donanım ÖZELLİK TESPİTİ
    def detect_equipment_feature(self, msg: str):
        msg = msg.lower()

        # 1) Synonym eşleşmesi → canonical donanım
        for syn, canon in EQUIP_SYNONYMS.items():
            if syn in msg:
                return canon

        # 2) “var mı / varmı / mevcut mu” sinyali varsa ama synonym yok
        existence_signals = ["var mı", "varmi", "mevcut mu", "bulunuyor mu"]
        if any(x in msg for x in existence_signals):
            # donanımı yakalayamadı → None döner ama intent yine equipment_query olacak
            return None

        return None


    # 🔍 CONTEXT TESPİTİ (şehir, yol, mesafe)
    def detect_context(self, msg: str):
        found = []
        for w in self.LLM_CONTEXT_WORDS:
            if w in msg:
                found.append(w)
        return found

    def classify(self, user_message: str):
        msg = normalize_tr_text(user_message or "").lower()

        model = self.detect_model(msg)
        trim = self.detect_trim(msg, model)
        technical = self.detect_technical_feature(msg)
        context = self.detect_context(msg)
        equipment = self.detect_equipment_feature(msg)   # <-- YENİ

        # ----------------------------------------
        # 1) DONANIM INTENT (equipment_query)
        # ----------------------------------------
        if equipment is not None or any(x in msg for x in ["var mı", "varmi", "mevcut mu", "bulunuyor mu"]):
            return {
                "model": model,
                "trim": trim,
                "technical_feature": None,
                "equipment_feature": equipment,
                "context": context,
                "intent": "equipment_query",
                "ratio": 1.0,
                "answer_type": "std"     # DB'ye yönlenecek
            }

        # ----------------------------------------
        # 2) TEKNİK INTENT
        # ----------------------------------------
        if technical:
            intent = "technical_metric"

            if technical in ["menzil", "wltp menzil", "şehir içi menzil"]:
                answer_type = "std"
                ratio = 1.0

            elif context:
                intent = "range_calculation"
                answer_type = "llm"
                ratio = 0.0

            else:
                answer_type = "std"
                ratio = 1.0

        # ----------------------------------------
        # 3) CONTEXT = ROTA / MESAFE
        # ----------------------------------------
        elif context:
            intent = "complex_route"
            answer_type = "llm"
            ratio = 0.0

        # ----------------------------------------
        # 4) GENERIC MODEL SORULARI
        # ----------------------------------------
        else:
            intent = "generic_db_query"
            answer_type = "std"
            ratio = 0.50

        # ----------------------------------------
        # FINAL RESULT
        # ----------------------------------------
        result = {
            "model": model,
            "trim": trim,
            "technical_feature": technical,
            "equipment_feature": None,
            "context": context,
            "intent": intent,
            "ratio": ratio,
            "answer_type": answer_type,
        }

        logger.info(f"[CS-ROUTING] {result}")
        return result
