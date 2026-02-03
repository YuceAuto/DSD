_TURK_UPPER_MAP = str.maketrans("iı", "İI")      # ‘i’ → ‘İ’, ‘ı’ → ‘I’

def turkish_title(text: str) -> str:
        """
        Sadece ilk harfi Türkçe kurallarına göre büyütür,
        geri kalan kısmı küçük bırakır.
        """
        if not text:
            return text
        text = text.strip()
        first = text[0].translate(_TURK_UPPER_MAP).upper()
        return first + text[1:].lower()