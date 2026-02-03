# modules/utils/text_utils.py (yeni)
import re
_TR_UP = str.maketrans("iışğüöç", "İIŞĞÜÖÇ")
def title_tr(sentence: str) -> str:
    def _fix(w):
        return w[:1].translate(_TR_UP).upper() + w[1:].lower()
    return " ".join(_fix(w) for w in re.split(r"\s+", sentence.strip()) if w)
