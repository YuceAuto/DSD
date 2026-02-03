import re
import unicodedata

def strip_tr_suffixes(word: str) -> str:
    """
    Türkçe kelimelerden yaygın iyelik, hal ve yönelme eklerini temizler.
    Örn:
      'torku' -> 'tork'
      'gücü' -> 'güc'
      'menzilden' -> 'menzil'
      'kapısından' -> 'kapı'
    """
    if not word:
        return word
    w = word.lower()

    # Tipik son ek kalıpları (hepsi isteğe göre genişletilebilir)
    suffixes = [
        "nın", "nin", "nun", "nün",
        "dan", "den", "tan", "ten",
        "nda", "nde", "nda", "nde",
        "ına", "ine", "una", "üne",
        "a", "e", "u", "ü", "ı", "i",   # yalın sesli ekler
        "ya", "ye",
        "yla", "yle", "la", "le",
        "da", "de", "ta", "te",
    ]

    for suf in sorted(suffixes, key=len, reverse=True):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break

    return w


def normalize_tr_text(text: str) -> str:
    """
    Türkçe karakterleri normalize eder, küçük harfe çevirir,
    gereksiz boşlukları ve işaretleri temizler, yaygın ekleri kaldırır.
    """
    if not text:
        return ""

    # Unicode normalize (örn. “İ̇” vs “İ” farklarını düzelt)
    text = unicodedata.normalize("NFKD", text)

    # Türkçe karakter düzeltmeleri
    text = text.replace("İ", "İ").replace("ı̇", "i")

    # ASCII dışında kalan diakritikleri temizle
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    # Küçük harfe çevir
    text = text.lower()

    # Noktalama ve özel karakterleri boşluğa çevir
    text = re.sub(r"[^0-9a-zçğıöşü\s]", " ", text)

    # Fazla boşlukları sil
    text = re.sub(r"\s+", " ", text).strip()

    # --- Yeni: Türkçe ek temizleme (her kelimeye uygula)
    tokens = [strip_tr_suffixes(tok) for tok in text.split()]
    text = " ".join(tokens)

    return text
