# modules/utils/model_detect.py (örnek küçük yardımcı)
def detect_model(text: str) -> str | None:
    models = ["octavia","enyaq","elroq","karoq","kodiaq","fabia","kamiq","scala","superb"]
    t = (text or "").lower()
    found = [m for m in models if m in t]
    if len(found) == 1:
        return found[0].capitalize()
    return None  # birden fazla ya da hiç yoksa
