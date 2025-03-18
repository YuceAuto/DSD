import re
import logging
import difflib  # EKLENDİ: difflib.SequenceMatcher ile benzerlik hesaplanacak
from modules.config import Config

class Utils:
    def __init__(self):
        self.config = Config()

    @staticmethod
    def setup_logger():
        logger = logging.getLogger("ChatbotAPI")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger

    def is_image_request(self, message):
        msg = message.lower()
        return ("resim" in msg) or ("fotoğraf" in msg) or ("görsel" in msg)

    def extract_image_keyword(self, message, assistant_name):
        lower_msg = message.lower()
        brand_lower = assistant_name.lower()
        cleaned = lower_msg.replace(brand_lower, "")
        cleaned = re.sub(r"(resim|fotoğraf|görsel)\w*", "", cleaned, flags=re.IGNORECASE)

        common_phrases = [
            r"paylaşabilir\s?misin", r"paylaşır\s?mısın",
            r"lütfen", r"istiyorum", r"\?$"
        ]
        for p in common_phrases:
            cleaned = re.sub(p, "", cleaned, flags=re.IGNORECASE)

        final_keyword = cleaned.strip()
        return final_keyword if final_keyword else None

    def parse_color_names(self, text: str) -> list:
        lower_text = text.lower()
        found = []
        for color in self.config.KNOWN_COLORS:
            if color in lower_text:
                found.append(color)
        return found

    #
    # EKLENDİ: fuzzy_find fonksiyonu
    #
    def fuzzy_find(self, user_word, candidate_list, threshold=0.7):
        """
        user_word: kullanıcıdan gelen kelime (ör: 'premum')
        candidate_list: doğru kelimeler listesi (ör: ['premium','elite','monte','carlo'])
        threshold: benzerlik eşiği (0.7 => %70)

        Döner: candidate_list içinden en iyi eşleşen kelime veya None
        """
        best_match = None
        best_ratio = 0.0
        for candidate in candidate_list:
            ratio = difflib.SequenceMatcher(None, user_word.lower(), candidate.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = candidate
        if best_ratio >= threshold:
            return best_match
        return None

    def get_priority_for_mc(self, filename: str) -> int:
        lower_f = filename.lower()
        for index, pattern_keywords in enumerate(self.config.monte_carlo_12):
            if all(k in lower_f for k in pattern_keywords):
                return index
        return 999

    def get_priority_for_prem_elite(self, filename: str) -> int:
        lower_f = filename.lower()
        for index, pattern_keywords in enumerate(self.config.premium_elite_12):
            if all(k in lower_f for k in pattern_keywords):
                return index
        return 999

    def get_priority_for_fabia_12(self, filename: str) -> int:
        lower_f = filename.lower()
        for index, pattern_keywords in enumerate(self.config.fabia_12):
            if all(k in lower_f for k in pattern_keywords):
                return index
        return 999

    def get_priority_for_scala_12(self, filename: str) -> int:
        lower_f = filename.lower()
        for index, pattern_keywords in enumerate(self.config.scala_12):
            if all(k in lower_f for k in pattern_keywords):
                return index
        return 999

    def get_priority_for_kamiq_12(self, filename: str) -> int:
        lower_f = filename.lower()
        for index, pattern_keywords in enumerate(self.config.kamiq_12):
            if all(k in lower_f for k in pattern_keywords):
                return index
        return 999

    def _custom_scala_sort(self, image_list):
        def order_key(item):
            item_lower = item.lower()
            for index, keywords in enumerate(self.config.custom_order_scala):
                if all(k in item_lower for k in keywords):
                    return index
            return len(self.config.custom_order_scala)
        return sorted(image_list, key=order_key)

    def _custom_kamiq_sort(self, image_list):
        def order_key(item):
            item_lower = item.lower()
            for index, keywords in enumerate(self.config.custom_order_kamiq):
                if all(k in item_lower for k in keywords):
                    return index
            return len(self.config.custom_order_kamiq)
        return sorted(image_list, key=order_key)

    def _default_7step_sort(self, image_list):
        def is_monte_carlo_standard(name):
            return ("monte" in name and "carlo" in name and "opsiyonel" not in name)
        def is_monte_carlo_optional(name):
            return ("monte" in name and "carlo" in name and "opsiyonel" in name)
        def is_premium_standard(name):
            return ("premium" in name and "opsiyonel" not in name)
        def is_premium_optional(name):
            return ("premium" in name and "opsiyonel" in name)
        def is_elite_standard(name):
            return ("elite" in name and "opsiyonel" not in name)
        def is_elite_optional(name):
            return ("elite" in name and "opsiyonel" in name)

        monte_carlo_std = []
        monte_carlo_opt = []
        premium_std = []
        premium_opt = []
        elite_std = []
        elite_opt = []
        leftover = []

        for img in image_list:
            lower_name = img.lower()
            if is_monte_carlo_standard(lower_name):
                monte_carlo_std.append(img)
            elif is_monte_carlo_optional(lower_name):
                monte_carlo_opt.append(img)
            elif is_premium_standard(lower_name):
                premium_std.append(img)
            elif is_premium_optional(lower_name):
                premium_opt.append(img)
            elif is_elite_standard(lower_name):
                elite_std.append(img)
            elif is_elite_optional(lower_name):
                elite_opt.append(img)
            else:
                leftover.append(img)

        monte_carlo_std.sort()
        monte_carlo_opt.sort()
        premium_std.sort()
        premium_opt.sort()
        elite_std.sort()
        elite_opt.sort()
        leftover.sort()

        return (
            monte_carlo_std
            + monte_carlo_opt
            + premium_std
            + premium_opt
            + elite_std
            + elite_opt
            + leftover
        )

    def multi_group_sort(self, image_list, desired_group=None):
        if desired_group == "scala_custom":
            return self._custom_scala_sort(image_list)
        elif desired_group == "kamiq_custom":
            return self._custom_kamiq_sort(image_list)
        elif desired_group == "monte_carlo":
            image_list.sort(key=self.get_priority_for_mc)
            return image_list
        elif desired_group == "premium_elite":
            image_list.sort(key=self.get_priority_for_prem_elite)
            return image_list
        elif desired_group == "fabia_12":
            image_list.sort(key=self.get_priority_for_fabia_12)
            return image_list
        elif desired_group == "scala_12":
            image_list.sort(key=self.get_priority_for_scala_12)
            return image_list
        elif desired_group == "kamiq_12":
            image_list.sort(key=self.get_priority_for_kamiq_12)
            return image_list
        else:
            return self._default_7step_sort(image_list)