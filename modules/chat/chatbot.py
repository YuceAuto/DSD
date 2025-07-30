import os
import time
import logging
import re
import openai
import difflib
import queue
import threading
import random
import requests
import urllib.parse
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv

# Aşağıdaki import'lar sizin projenizdeki dosya yollarına göre uyarlanmalıdır:
from modules.managers.image_manager import ImageManager
from modules.managers.markdown_utils import MarkdownProcessor
from modules.config import Config
from modules.utils import Utils
from modules.db import create_tables, save_to_db, send_email, get_db_connection, update_customer_answer

# -- ENYAQ tabloları
from modules.data.enyaq_data import (
    ENYAQ_E_PRESTIGE_60_MD,
    ENYAQ_COUPE_E_SPORTLINE_60_MD,
    ENYAQ_COUPE_E_SPORTLINE_85X_MD
)
# -- ELROQ tablosu
from modules.data.elroq_data import ELROQ_E_PRESTIGE_60_MD

# Fabia, Kamiq, Scala tabloları
from modules.data.scala_data import (
    SCALA_ELITE_MD,
    SCALA_PREMIUM_MD,
    SCALA_MONTE_CARLO_MD
)
from modules.data.kamiq_data import (
    KAMIQ_ELITE_MD,
    KAMIQ_PREMIUM_MD,
    KAMIQ_MONTE_CARLO_MD
)
from modules.data.fabia_data import (
    FABIA_PREMIUM_MD,
    FABIA_MONTE_CARLO_MD
)

# Karoq tabloları
from modules.data.karoq_data import (
    KAROQ_PREMIUM_MD,
    KAROQ_PRESTIGE_MD,
    KAROQ_SPORTLINE_MD
)
from modules.data.kodiaq_data import (
    KODIAQ_PREMIUM_MD,
    KODIAQ_PRESTIGE_MD,
    KODIAQ_SPORTLINE_MD,
    KODIAQ_RS_MD
)

from modules.data.octavia_data import (
    OCTAVIA_ELITE_MD,
    OCTAVIA_PREMIUM_MD,
    OCTAVIA_PRESTIGE_MD,
    OCTAVIA_SPORTLINE_MD,
    OCTAVIA_RS_MD
)
from modules.data.superb_data import (
    SUPERB_PREMIUM_MD,
    SUPERB_PRESTIGE_MD,
    SUPERB_LK_CRYSTAL_MD,
    SUPERB_SPORTLINE_PHEV_MD
)
from modules.data.test_data import (
    TEST_E_PRESTIGE_60_MD,
    TEST_PREMIUM_MD,
    TEST_PRESTIGE_MD,
    TEST_SPORTLINE_MD
)

from modules.data.fabia_teknik import(
    FABIA_TEKNIK_MD
)
from modules.data.scala_teknik import(
    SCALA_TEKNIK_MD
)
from modules.data.kamiq_teknik import(
    KAMIQ_TEKNIK_MD
)
from modules.data.karoq_teknik import(
    KAROQ_TEKNIK_MD
)
from modules.data.kodiaq_teknik import(
    KODIAQ_TEKNIK_MD
)
from modules.data.octavia_teknik import(
    OCTAVIA_TEKNIK_MD
)
from modules.data.superb_teknik import(
    SUPERB_TEKNIK_MD
)
from modules.data.enyaq_teknik import(
    ENYAQ_TEKNIK_MD
)
from modules.data.elroq_teknik import(
    ELROQ_TEKNIK_MD
)
import math
from modules.data.ev_specs import EV_RANGE_KM, FUEL_SPECS   # 1. adımda oluşturduk
import math

import secrets
ASSISTANT_NAMES = {
    "fabia", "scala", "kamiq", "karoq", "kodiaq",
    "octavia", "superb", "elroq", "enyaq"
}
import re
def clean_city_name(raw: str) -> str:
    """
    'Fabia İzmir' → 'İzmir'
    'Kodiaq Ankara' → 'Ankara'
    """
    txt = raw.lower()
    # Modele ait kelimeleri boşluğa çevir
    for m in ASSISTANT_NAMES:
        txt = re.sub(rf"\b{m}\b", "", txt, flags=re.IGNORECASE)
    # Artık kalan fazla boşlukları sıkıştır
    txt = re.sub(r"\s{2,}", " ", txt).strip()
    return txt.title()
TWO_LOC_PAT = (
    r"([a-zçğıöşü\s]+?)\s*"                       # konum‑1
    r"(?:ile|ve|,|-|dan|den)?\s+"                 # bağlaçlar
    r"([a-zçğıöşü\s]+?)\s+"                       # konum‑2
    r"(?:arası|arasında)?\s*"                     # opsiyonel "arası"
    r"(?:kaç\s+km|kaç\s+saat|ne\s+kadar\s+sürer|mesafe|sürer)"
)

def parse_distance_question(msg: str):
    """
    “Çankaya ile Buca arası kaç km?” ➞ ('Çankaya', 'Buca')
    """
    msg = msg.lower()
    m = re.search(TWO_LOC_PAT, msg)
    if not m:
        return (None, None)
    return (
        clean_city_name(m.group(1)),
        clean_city_name(m.group(2))
    )
# Yeni: Kaç şarj sorularını ayrıştır
# utils/parsers.py  (veya mevcut dosyanız neredeyse)
import re

MODELS = r"(?:fabia|scala|kamiq|karoq|kodiaq|octavia|superb|enyaq|elroq)"
FUEL_WORDS = r"(?:depo|yakıt|benzin)"
CHARGE_OR_FUEL = rf"(?:şarj|{FUEL_WORDS})"
def parse_charging_question(msg: str):
    """
    Örnek: “milas bodrum arasında elroq ile kaç şarj” → ('Milas', 'Bodrum', 'elroq', None)
    """
    if not msg:
        return (None, None, None, None)

    msg = msg.lower()

    # 1) <şehir‑1> … <şehir‑2> … kaç şarj
    pat1 = (
        r"([a-zçğıöşü\s]+?)\s*(?:['’]?d[ae]n|dan|den)\s+"
        r"([a-zçğıöşü\s]+?)\s*(?:['’]?y?[ae]|ya|ye|a|e)\s+"
        rf"(?:({MODELS})\s*(?:['’]?l[ae])?\s*)?"
        rf".*?kaç\s+{CHARGE_OR_FUEL}\w*"
    )
    m1 = re.search(pat1, msg, re.DOTALL)
    if m1:
        return (
            clean_city_name(m1.group(1)),
            clean_city_name(m1.group(2)),
            m1.group(3),   # model
            None
        )

    # 2) model … kaç şarj … <şehir‑1> … <şehir‑2>
    pat2 = (
        rf"({MODELS})\s*(?:ile|la|le)?\s*.*?"
        r"kaç\s+şarj\w*\s*"
        r"(?:ile\s+)?"                 # <‑‑ eklenen kısım
        r"([a-zçğıöşü\s]+?)\s*(?:['’]?d[ae]n|dan|den)\s+"
        r"([a-zçğıöşü\s]+?)\s+(?:['’]?y?[ae]|ya|ye|a|e)\b"
    )
    m2 = re.search(pat2, msg, re.DOTALL)
    if m2:
        return (
            clean_city_name(m2.group(2)),
            clean_city_name(m2.group(3)),
            m2.group(1),   # model
            None
        )

    # 3) model … <şehir‑1> … <şehir‑2> … kaç şarj
    pat3 = (
        rf"({MODELS})\s*(?:ile|la|le)?\s*"
        r"([a-zçğıöşü\s]+?)\s*(?:['’]?d[ae]n|dan|den)\s+"
        r"(?:ile\s+)?"
        r"([a-zçğıöşü\s]+?)\s*(?:['’]?y?[ae]|ya|ye|a|e)\s+"
        rf".*?kaç\s+{CHARGE_OR_FUEL}\w*"
    )
    m3 = re.search(pat3, msg, re.DOTALL)
    if m3:
        return (
            clean_city_name(m3.group(2)),
            clean_city_name(m3.group(3)),
            m3.group(1),   # model
            None
        )

    # 4) “<şehir‑1> <şehir‑2> arası … kaç şarj”
    pat4 = (
        r"([a-zçğıöşü\s]+?)\s+"          # şehir‑1
        r"([a-zçğıöşü\s]+?)\s+"          # şehir‑2
        r"(?:arası|arasında)\s*"
        rf"(?:({MODELS})\s*(?:ile|la|le)?\s*)?"
        rf".*?kaç\s+{CHARGE_OR_FUEL}\w*"
    )
    m4 = re.search(pat4, msg, re.DOTALL)
    if m4:
        return (
            clean_city_name(m4.group(1)),
            clean_city_name(m4.group(2)),
            m4.group(3),   # model
            None
        )
    
    pat5 = (
        rf"({MODELS})\s*(?:ile|la|le)?\s*.*?"
        r"kaç\s+şarj\w*\s*"
        r"([a-zçğıöşü\s]+?)\s*(?:['’]?d[ae]n|dan|den)\s+"
        r"([a-zçğıöşü\s]+?)\s*(?:['’]?y?[ae]|ya|ye|a|e)"
    )
    m5 = re.search(pat5, msg, re.DOTALL)
    if m5:
        return (
            clean_city_name(m5.group(2)),
            clean_city_name(m5.group(3)),
            m5.group(1),   # model
            None
        )

    # 3) model … <şehir‑1> … <şehir‑2> … kaç şarj
    pat6 = (
        rf"({MODELS})\s*(?:ile|la|le)?\s*"
        r"([a-zçğıöşü\s]+?)\s*(?:['’]?d[ae]n|dan|den)\s+"
        r"([a-zçğıöşü\s]+?)\s*(?:['’]?y?[ae]|ya|ye|a|e)\s+"
        rf".*?kaç\s+{CHARGE_OR_FUEL}\w*"
    )
    m6 = re.search(pat6, msg, re.DOTALL)
    if m6:
        return (
            clean_city_name(m6.group(2)),
            clean_city_name(m6.group(3)),
            m6.group(1),   # model
            None
        )

    return (None, None, None, None)

# utils/parsers.py  (veya mevcut dosyanız neredeyse)
FUEL_WORDS = r"(?:benzin|yakıt|depo|litre)"
def parse_fuel_question(msg: str):
    """
    'milas marmaris arasında karoq kaç litre yakar'
    → ('Milas', 'Marmaris', 'karoq', None)
    """
    if not msg:
        return (None, None, None, None)
    msg = msg.lower()

    # 1)  <şehir1> … <şehir2> … <model>? … (kaç|ne kadar) {FUEL_WORDS}
    pat = (
        r"([a-zçğıöşü\s]+?)\s*(?:['’]?d[ae]n|dan|den)?\s+"      # şehir‑1
        r"([a-zçğıöşü\s]+?)\s*(?:['’]?y?[ae]|ya|ye|a|e)?\s+"    # şehir‑2
        rf"(?:({MODELS})\s*(?:ile|la|le)?\s*)?"                 # model (isteğe bağlı)
        r".*?(?:kaç|ne\s+kadar)\s+" + FUEL_WORDS                # yakıt sözcükleri
    )
    m = re.search(pat, msg, re.DOTALL)
    if m:
        return (
            clean_city_name(m.group(1)),
            clean_city_name(m.group(2)),
            m.group(3),   # model (veya None)
            None
        )
    return (None, None, None, None)


GOOGLE_API_KEY = "AIzaSyAy3vtaMa62ikEYJ0Dy9-XiSh_we3Or640"

_PLACE_ID_CACHE: dict[str, str] = {}

def _resolve_place_id(city: str) -> str | None:
    """‘İstanbul’ vb. şehir adını Google‑place_id’ye çevirir (Türkiye ile sınırlı)."""
    if city in _PLACE_ID_CACHE:
        return _PLACE_ID_CACHE[city]

    geo_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address":  f"{city}, Türkiye",
        "language": "tr",
        "region":   "tr",
        "key":      GOOGLE_API_KEY,
    }
    try:
        rsp = requests.get(geo_url, params=params, timeout=8)
        rsp.raise_for_status()
        js = rsp.json()
    except requests.RequestException:
        return None

    best: str | None = None
    for res in js.get("results", []):
        kinds = set(res.get("types", []))
        if "locality" in kinds or "administrative_area_level_1" in kinds:
            best = res["place_id"]; break
        if best is None and "place_id" in res:
            best = res["place_id"]

    if best:
        _PLACE_ID_CACHE[city] = best
    return best

def get_google_route_info(from_city: str, to_city: str):
    """
    Google Directions API’den (sürüş) mesafe, süre ve polyline döner.
    Hata durumunda distance_km ve duration_min None olur, error alanı açıklama içerir.
    """
    # Şehir isimlerini kesinleştirmek için Google Place ID kullan
    from_id = _resolve_place_id(from_city)
    to_id   = _resolve_place_id(to_city)
    if from_id and to_id:
        from_city = f"place_id:{from_id}"
        to_city   = f"place_id:{to_id}"

    def _fmt(loc: str) -> str:
        # place_id ile başlıyorsa “,Türkiye” ekleme
        return loc if loc.startswith("place_id:") else f"{loc},Türkiye"

    base_url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin":      _fmt(from_city),
        "destination": _fmt(to_city),
        "mode":        "driving",
        "language":    "tr",
        "region":      "tr",
        "key":         GOOGLE_API_KEY,
    }

    try:
        resp = requests.get(base_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        return None, f"HTTP bağlantı hatası: {exc}", None, None

    logging.warning(
        "Google Directions → status=%s | %s ➜ %s | err=%s",
        data.get("status"), from_city, to_city, data.get("error_message"),
    )

    if data.get("status") != "OK":
        return None, f"Google Directions hata: {data.get('status')} – {data.get('error_message','')}", None, None

    leg = data["routes"][0]["legs"][0]
    distance_km = leg["distance"]["value"] / 1000        # metre → km
    duration_min = leg["duration"]["value"] / 60         # saniye → dakika
    polyline = data["routes"][0]["overview_polyline"]["points"]

    return distance_km, duration_min, polyline, None

def google_static_map_with_route(polyline, from_city, to_city):
    # İki şehir için marker ve rota çizimi
    base = "https://maps.googleapis.com/maps/api/staticmap?"
    params = {
        "size": "600x300",
        "maptype": "roadmap",
        "markers": [
            f"color:green|label:A|{from_city},Türkiye",
            f"color:red|label:B|{to_city},Türkiye",
        ],
        "path": f"color:0x0000ff|weight:5|enc:{polyline}",
        "key": GOOGLE_API_KEY
    }

    # markers paramı birden çok ise stringle birleştir
    url = (base +
        "size={size}&maptype={maptype}&markers={m1}&markers={m2}&path={path}&key={key}".format(
            size=params["size"],
            maptype=params["maptype"],
            m1=urllib.parse.quote(params["markers"][0]),
            m2=urllib.parse.quote(params["markers"][1]),
            path=urllib.parse.quote(params["path"]),
            key=params["key"]
        )
    )
    return url




def parse_route_question(user_message):
    """
    Rota sorularında <şehir1>, <şehir2> ikilisini döndürür.
    • Mesajın değişmeyen kopyası üzerinde çalışır.
    • Eğer ilk kelime bir asistan adı ise o kelimeyi geçer.
    • Eşleşme sonrasında hâlâ asistan adı yakalanmışsa sonuç geçersiz sayılır.
    Dönen değer: (from_city, to_city)  — hiç eşleşme yoksa (None, None)
    """
    if not user_message:
        return None, None

    # 0) Küçük harfe çevir, baş‑son boşlukları temizle
    msg = user_message.lower().strip()

    # 1) İlk kelime asistan adı mı?  → Sil ve devam et
    words = msg.split()
    if words and words[0] in ASSISTANT_NAMES:
        msg = " ".join(words[1:]).lstrip()

    # 2) Rota kalıpları (mevcut listenizden kopyalandı)
    patterns = [
        r"([a-zçğıöşü\s]+?)\s+ile\s+([a-zçğıöşü\s]+?)\s+arası\s+kaç\s+km",
        r"([a-zçğıöşü\s]+?)\s+ile\s+([a-zçğıöşü\s]+?)\s+kaç\s+km",
        r"([a-zçğıöşü\s]+?)\s+([a-zçğıöşü\s]+?)\s+arası\s+kaç\s+km",
        r"([a-zçğıöşü\s]+?)\s+([a-zçğıöşü\s]+?)\s+kaç\s+km",
        # Süre / saat varyantları
        r"([a-zçğıöşü\s]+?)\s+ile\s+([a-zçğıöşü\s]+?)\s+arası\s+ne\s+kadar\s+sürer",
        r"([a-zçğıöşü\s]+?)\s+ile\s+([a-zçğıöşü\s]+?)\s+arası\s+kaç\s+saat",
        r"([a-zçğıöşü\s]+?)\s+([a-zçğıöşü\s]+?)\s+ne\s+kadar\s+sürer",
        r"([a-zçğıöşü\s]+?)\s+([a-zçğıöşü\s]+?)\s+kaç\s+saat",
    ]

    # 3) Desenleri sırayla dene
    for pat in patterns:
        m = re.search(pat, msg)
        if not m:
            continue

        city1 = clean_city_name(m.group(1))
        city2 = clean_city_name(m.group(2))

        # 3a) Yakalanan kelimeler hâlâ asistan adıysa bu eşleşmeyi geç
        if city1.lower() in ASSISTANT_NAMES or city2.lower() in ASSISTANT_NAMES:
            continue

        return city1, city2  # Geçerli sonuç

    # Hiçbir desen tutmadı
    return None, None




def fix_markdown_table(md_table: str) -> str:
    """
    Markdown tablolarda tüm satırlarda eşit sütun olmasını ve kaymaların önlenmesini sağlar.
    """
    lines = [line for line in md_table.strip().split('\n') if line.strip()]
    # Sadece | içeren satırları al
    table_lines = [line for line in lines if '|' in line]
    if not table_lines:
        return md_table
    # Maksimum sütun sayısını bul
    max_cols = max(line.count('|') for line in table_lines)
    fixed_lines = []
    for line in table_lines:
        # Satır başı/sonu boşluk ve | temizle
        clean = line.strip()
        if not clean.startswith('|'):
            clean = '|' + clean
        if not clean.endswith('|'):
            clean = clean + '|'
        # Eksik sütunları tamamla
        col_count = clean.count('|') - 1
        if col_count < max_cols - 1:
            clean = clean[:-1] + (' |' * (max_cols - col_count - 1)) + '|'
        fixed_lines.append(clean)
    return '\n'.join(fixed_lines)


CACHE_STOPWORDS = {
    "evet", "evt", "lutfen", "lütfen", "ltfen", "evet lutfen", "evt lutfen", "evt ltfn","evet lütfen", "tabi", "tabii", "isterim", "olur", "elbette", "ok", "tamam",
    "teşekkürler", "teşekkür ederim", "anladım", "sağol", "sağ olun", "sağolun", "yes", "yea", "yeah", "yep", "ok", "okey", "okay", "please", "yes please", "yeah please"
}


def is_non_sentence_short_reply(msg: str) -> bool:
    """
    Kısa, cümle olmayan, yalnızca onay/ret/klişe cevap mı kontrol eder.
    Noktalama ve gereksiz boşlukları atar. Kelime sayısı 1-3 arasında ve yüklem yoksa da engeller.
    """
    msg = msg.strip().lower()
    msg_clean = re.sub(r"[^\w\sçğıöşü]", "", msg)
    # Tam eşleşme stoplist'te mi?
    if msg_clean in CACHE_STOPWORDS:
        return True
    # Çok kısa (<=3 kelime), bariz cümle öznesi/yüklem yoksa
    if len(msg_clean.split()) <= 3:
        # Cümlede özne/yüklem (örn. istiyorum, yaparım, ben, var, yok...) yoksa
        if not re.search(r"\b(ben|biz|sen|siz|o|yaparım|yapabilirim|alabilirim|istiyorum|olabilir|olacak|var|yok)\b", msg_clean):
            return True
    return False
load_dotenv()

# ----------------------------------------------------------------------
# 0) YENİ: Trim varyant tabloları  ➜  “mc”, “ces60” v.b. kısaltmaları da
# ----------------------------------------------------------------------
TRIM_VARIANTS = {
    "premium": ["premium"],
    "monte carlo": ["monte carlo", "monte_carlo", "montecarlo", "mc"],
    "elite": ["elite"],
    "prestige": ["prestige"],
    "sportline": ["sportline", "sport_line", "sport-line", "sl"],
    "rs": ["rs"],
    "e prestige 60": ["e prestige 60", "eprestige60"],
    "coupe e sportline 60": ["coupe e sportline 60", "ces60"],
    "coupe e sportline 85x": ["coupe e sportline 85x", "ces85x"],
    "e sportline 60": ["e sportline 60", "es60"],
    "e sportline 85x": ["e sportline 85x", "es85x"],
    "l&k crystal": ["l&k crystal", "lk crystal", "crystal", "l n k crystal"],
    "sportline phev": ["sportline phev", "e‑sportline", "phev", "Sportline Phev"],
}
VARIANT_TO_TRIM = {v: canon for canon, lst in TRIM_VARIANTS.items() for v in lst}
# Yardımcı: Düz liste
TRIM_VARIANTS_FLAT = [v for lst in TRIM_VARIANTS.values() for v in lst]
def normalize_trim_str(t: str) -> list:
    """
    Bir trim adını, dosya adlarında karşılaşılabilecek tüm varyantlara genişletir.
    Örn. "monte carlo" ➜ ["monte carlo", "monte_carlo", "montecarlo", "mc"]
    """
    t = t.lower().strip()
    base = [t, t.replace(" ", "_"), t.replace(" ", "")]
    extra = TRIM_VARIANTS.get(t, [])
    # dict.fromkeys() ➜ sıralı & tekrarsız
    return list(dict.fromkeys(base + extra))

def extract_trims(text: str) -> set:
    text_lower = text.lower()
    possible_trims = [
        "premium", "monte carlo", "elite", "prestige",
        "sportline", "rs",
        "e prestige 60", "coupe e sportline 60", "coupe e sportline 85x",
        "e sportline 60", "e sportline 85x",
        "l&k crystal", "sportline phev",
    ]
    # 1) Ham eşleşmeleri topla
    raw_hits = []
    for t in possible_trims:
        variants = normalize_trim_str(t)
        if any(v in text_lower for v in variants):
            raw_hits.append(t)

    # 2) Birbirinin parçası olan kısa trimleri ele (örn. "sportline" < "sportline phev")
    hits = set(raw_hits)
    for t_short in raw_hits:
        for t_long in raw_hits:
            if t_short != t_long and t_short in t_long:
                if len(t_long) > len(t_short):
                    hits.discard(t_short)

    return hits
    found_trims = set()
    for t in possible_trims:
        variants = normalize_trim_str(t)
        if any(v in text_lower for v in variants):
            found_trims.add(t)
    return found_trims

def extract_model_trim_pairs(text):
    pattern = r"(fabia|scala|kamiq|karoq|kodiaq|octavia|enyaq|elroq|superb)\s*([a-zA-Z0-9\s]+)?"

    pairs = []
    split_candidates = re.split(r"\b(?:ve|&|ile|,|and)\b", text.lower())
    for piece in split_candidates:
        piece = piece.strip()
        if not piece:
            continue
        matches = re.findall(pattern, piece)
        for m in matches:
            model = m[0].strip()
            trim = m[1].strip() if m[1] else ""
            pairs.append((model, trim))
    return pairs
def remove_latex_and_formulas(text):
    # LaTeX blocklarını kaldır: \[ ... \] veya $$ ... $$
    text = re.sub(r'\\\[.*?\\\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\$\$.*?\$\$', '', text, flags=re.DOTALL)
    # Inline LaTeX: $...$
    text = re.sub(r'\$.*?\$', '', text)
    # Süslü parantez ve içeriği { ... }
    text = re.sub(r'\{.*?\}', '', text)
    # \times, \div gibi kaçan matematiksel ifadeler
    text = text.replace('\\times', 'x')
    text = text.replace('\\div', '/')
    text = text.replace('\\cdot', '*')
    # Diğer olası kaçan karakterler (\approx, vb.)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    # Gereksiz çift boşlukları düzelt
    text = re.sub(r'\s{2,}', ' ', text)
    # Baş ve son boşluk
    text = text.strip()
    return text


class ChatbotAPI:

    def _get_ev_range_km(self, model: str, trim: str) -> float | None:
        """
        Eldeki model‑trim ikilisi için menzil döndürür (km).
        Trim gelmemişse yalnızca modele bakar.
        """
        key_exact = (model.lower(), trim.lower())
        key_model_only = (model.lower(), "")
        return (
            EV_RANGE_KM.get(key_exact) or
            EV_RANGE_KM.get(key_model_only) or
            None
        )
        # ------------------------------------------------------------------
    # EV (şarj) ve ICE (depo) menzilini tek yerden hesapla
    # ------------------------------------------------------------------
    def _lookup_range_and_unit(self, model: str, trim: str) -> tuple[float | None, str]:
        """
        Dönen değer  →  (menzil_km, 'şarj' | 'depo' | '')
        'menzil_km' None ise model/trim için veri yok demektir.
        """
        key_exact = (model.lower(), trim.lower())
        key_model = (model.lower(), "")

        # 1) Elektrikli araç (EV)
        rng = EV_RANGE_KM.get(key_exact) or EV_RANGE_KM.get(key_model)
        if rng:
            return rng, "şarj"

        # 2) İçten yanmalı (ICE): depo hacmi + ort. tüketimden menzil
        spec = FUEL_SPECS.get(key_exact) or FUEL_SPECS.get(key_model)
        if spec:
            tank = spec["tank_l"]
            l100 = spec["l_per_100km"]
            if tank > 0 and l100 > 0:
                rng_km = tank / l100 * 100.0   # basit ortalama
                return rng_km, "depo"

        return None, ""   # veri bulunamadı


    def _charges_needed(self, distance_km: float, range_km: float) -> int:
        """
        Kaç defa şarj etmem gerektiğini kaba olarak hesaplar.
        Varsayım: %100 dolu batarya ile başlanıyor.
        Tam sayıya yuvarlanırken route riskini azaltmak için daima yukarı yuvarlarız.
        """
        if range_km <= 0:
            return -1
        # İlk batarya ile katedilen mesafe ➜ (distance / range) - 1
        required_full_cycles = distance_km / range_km
        # Başlangıç şarjı zaten dolu; geriye gereken ekstra şarj sayısı:
        extra_charges = math.ceil(required_full_cycles) - 1
        return max(extra_charges, 0)
    def _fuel_needed_litre(self, distance_km: float, l_per_100: float) -> float:
        """Mesafe ve ort. tüketime göre toplam litre hesabı."""
        return distance_km * l_per_100 / 100.0

    def _get_gpt_journey_with_model(self, rd: dict, user_id: str) -> str:
        """
        rd        : _get_route_data() çıktısı
        user_id   : aktif kullanıcı
        DÖNÜŞ     : 3‑4 cümlelik dilimizde (MD) paragraf
        """
        assistant_id = self.user_states[user_id].get("assistant_id")
        if not assistant_id:
            return ""

        model_name = self.ASSISTANT_NAME_MAP.get(assistant_id, "").title()
        trim_name  = self.user_states[user_id].get("current_trim", "").title()

        if not model_name:
            return ""

        car_label = f"{model_name} {trim_name}".strip()

        prompt = (
            f"Kullanıcı {rd['from']}‑{rd['to']} yolculuğunu **{car_label}** ile yapacak. "
            f"Mesafe {rd['distance_km']:.1f} km, ortalama süre {rd['duration_min']:.0f} dakika.\n\n"
            "• Bu aracın sürüş konforu, yakıt/enerji verimliliği, güvenlik ve sürücü destek sistemlerinden "
            "bahsederek yolculuğun nasıl geçeceğini 3‑4 cümlelik samimi, akıcı bir paragrafta anlat. "
            "Teknik terimleri basitleştir, satış dili yerine dostça bir ton kullan."
        )
        return self._ask_assistant(user_id, assistant_id, prompt)
    def __init__(self, logger=None, static_folder='static', template_folder='templates'):
        self.app = Flask(
            __name__,
            static_folder=os.path.join(os.getcwd(), static_folder),
            template_folder=os.path.join(os.getcwd(), template_folder)
        )
        CORS(self.app)
        self.app.secret_key = secrets.token_hex(16)

        self.logger = logger if logger else self._setup_logger()

        create_tables()

        openai.api_key = os.getenv("OPENAI_API_KEY")
        self.client = openai

        self.config = Config()
        self.utils = Utils()

        self.image_manager = ImageManager(images_folder=os.path.join(static_folder, "images"))
        self.image_manager.load_images()

        self.markdown_processor = MarkdownProcessor()

        # Önemli: Config içindeki ASSISTANT_CONFIG ve ASSISTANT_NAME_MAP
        self.ASSISTANT_CONFIG = self.config.ASSISTANT_CONFIG
        self.ASSISTANT_NAME_MAP = self.config.ASSISTANT_NAME_MAP

        self.user_states = {}
        self.fuzzy_cache = {}
        self.fuzzy_cache_queue = queue.Queue()

        self.stop_worker = False
        self.worker_thread = threading.Thread(target=self._background_db_writer, daemon=True)
        self.worker_thread.start()

        self.CACHE_EXPIRY_SECONDS = 43200

        self.MODEL_VALID_TRIMS = {
            "fabia": ["premium", "monte carlo"],
            "scala": ["elite", "premium", "monte carlo"],
            "kamiq": ["elite", "premium", "monte carlo"],
            "karoq": ["premium", "prestige", "sportline"],
            "kodiaq": ["premium", "prestige", "sportline", "rs"],
            "octavia": ["elite", "premium", "prestige", "sportline", "rs"],
            "superb": ["premium", "prestige", "l&k crystal", "sportline phev"],
            "enyaq": [
                "e prestige 60",
                "coupe e sportline 60",
                "coupe e sportline 85x",
                "e sportline 60",
                "e sportline 85x"
            ],
            "elroq": ["e prestige 60"]
        }

        # Renk anahtar kelimeleri
        self.KNOWN_COLORS = [
            "fabia premium gümüş", 
            "Renk kadife kırmızı",
            "metalik gümüş",
            "mavi",
            "beyazi",
            "beyaz",
            "bronz",
            "altın",
            "gri",
            "büyülü siyah",
            "Kamiq gümüş",
            "Scala gümüş",
            "lacivert",
            "koyu",
            "timiano yeşil",
            "turuncu",
            "krem",
            "şimşek",
            "bronz altın"
            "e_Sportline_Coupe_60_Exclusive_Renk_Olibo_Yeşil",
            "monte carlo gümüş",
            "elite gümüş",
            "Kodiaq_Premium_Opsiyonel_Döşeme"
            # Tek kelimelik ana renkler
            "kırmızı",
            "siyah",
            "gümüş",
            "yeşil",
        ]

        self.logger.info("=== YENI VERSIYON KOD CALISIYOR ===")

        self._define_routes()

    def _setup_logger(self):
        logger = logging.getLogger("ChatbotAPI")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger

    def _define_routes(self):
        @self.app.route("/", methods=["GET"])
        def home():
            return render_template("index.html")

        @self.app.route("/ask/<string:username>", methods=["POST"])
        def ask(username):
            return self._ask(username)

        @self.app.route("/check_session", methods=["GET"])
        def check_session():
            if 'last_activity' in session:
                _ = time.time()
            return jsonify({"active": True})

        @self.app.route("/like", methods=["POST"])
        def like_endpoint():
            data = request.get_json()
            conv_id = data.get("conversation_id")
            if not conv_id:
                return jsonify({"error": "No conversation_id provided"}), 400
            try:
                update_customer_answer(conv_id, 1)
                return jsonify({"status": "ok"}), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/dislike", methods=["POST"])
        def dislike_endpoint():
            data = request.get_json()
            conv_id = data.get("conversation_id")

            if not conv_id:
                return jsonify({"error": "No conversation_id provided"}), 400

            try:
                update_customer_answer(conv_id, 2)
                self._remove_from_fuzzy_cache(conv_id)

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM cache_faq WHERE conversation_id=?", (conv_id,))
                conn.commit()
                conn.close()

                return jsonify({
                    "status": "ok",
                    "conversation_id": conv_id
                }), 200

            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/feedback/<string:message_id>", methods=["POST"])
        def feedback(message_id):
            import pyodbc
            from flask import request, jsonify

            data = request.get_json()
            feedback_value = data.get("feedback")

            try:
                conn = pyodbc.connect(
                    "DRIVER={ODBC Driver 17 for SQL Server};"
                    "SERVER=10.0.0.20\\SQLYC;"
                    "DATABASE=SkodaBot;"
                    "UID=skodabot;"
                    "PWD=Skodabot.2024;"
                )
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE [dbo].[conversations]
                    SET [yorum] = ?
                    WHERE id = ?
                """, feedback_value, message_id)

                conn.commit()
                cursor.close()
                conn.close()

                update_customer_answer(message_id, 2)
                self._remove_from_fuzzy_cache(message_id)

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM cache_faq WHERE conversation_id=?", (message_id,))
                conn.commit()
                conn.close()

                return jsonify({
                    "status": "ok",
                    "conversation_id": message_id
                }), 200

            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500

    def _remove_from_fuzzy_cache(self, conversation_id):
        conv_id_int = int(conversation_id)
        for user_id in list(self.fuzzy_cache.keys()):
            for asst_id in list(self.fuzzy_cache[user_id].keys()):
                original_list = self.fuzzy_cache[user_id][asst_id]
                filtered_list = [
                    item for item in original_list
                    if item.get("conversation_id") != conv_id_int
                ]
                self.fuzzy_cache[user_id][asst_id] = filtered_list

    def _background_db_writer(self):
        self.logger.info("Background DB writer thread started.")
        while not self.stop_worker:
            try:
                record = self.fuzzy_cache_queue.get(timeout=5.0)
                if record is None:
                    continue

                user_id, username, q_lower, ans_bytes, conversation_id, _ = record

                conn = get_db_connection()
                cursor = conn.cursor()
                sql = """
                INSERT INTO cache_faq
                    (user_id, username, question, answer, conversation_id, created_at)
                VALUES (?, ?, ?, ?, ?, GETDATE())
                """
                cursor.execute(sql, (
                    user_id,
                    username,
                    q_lower,
                    ans_bytes.decode("utf-8"),
                    conversation_id
                ))
                conn.commit()
                conn.close()

                self.logger.info(f"[BACKGROUND] Kaydedildi -> user_id={user_id}, question={q_lower[:30]}...")
                self.fuzzy_cache_queue.task_done()

            except queue.Empty:
                pass
            except Exception as e:
                self.logger.error(f"[BACKGROUND] DB yazma hatası: {str(e)}")
                time.sleep(2)

        self.logger.info("Background DB writer thread stopped.")

    def _correct_all_typos(self, user_message: str) -> str:
        step1 = self._correct_image_keywords(user_message)
        final_corrected = self._correct_trim_typos(step1)
        return final_corrected

    def _correct_image_keywords(self, user_message: str) -> str:
        possible_image_words = [
            "görsel", "görseller", "resim", "resimler", "fotoğraf", "fotoğraflar", "görünüyor", "görünüyo", "image", "img"
        ]
        splitted = user_message.split()
        corrected_tokens = []
        for token in splitted:
            best = self.utils.fuzzy_find(token, possible_image_words, threshold=0.9)
            if best:
                corrected_tokens.append(best)
            else:
                corrected_tokens.append(token)
        return " ".join(corrected_tokens)

    def _correct_trim_typos(self, user_message: str) -> str:
        known_words = [
            "premium", "elite", "monte", "carlo", "prestige", "sportline",
            "e", "prestige", "60", "coupe", "85x"
        ]
        splitted = user_message.split()
        new_tokens = []
        for token in splitted:
            best = self.utils.fuzzy_find(token, known_words, threshold=0.9)
            if best:
                new_tokens.append(best)
            else:
                new_tokens.append(token)

        combined_tokens = []
        skip_next = False
        for i in range(len(new_tokens)):
            if skip_next:
                skip_next = False
                continue
            if i < len(new_tokens) - 1:
                if (new_tokens[i].lower() == "monte" and new_tokens[i+1].lower() == "carlo"):
                    combined_tokens.append("monte carlo")
                    skip_next = True
                else:
                    combined_tokens.append(new_tokens[i])
            else:
                combined_tokens.append(new_tokens[i])

        return " ".join(combined_tokens)

    def _search_in_assistant_cache(self, user_id, assistant_id, new_question, threshold):
        if not assistant_id:
            return None, None
        if user_id not in self.fuzzy_cache:
            return None, None
        if assistant_id not in self.fuzzy_cache[user_id]:
            return None, None

        new_q_lower = new_question.strip().lower()
        now = time.time()
        best_ratio = 0.0
        best_answer = None

        for item in self.fuzzy_cache[user_id][assistant_id]:
            if (now - item["timestamp"]) > self.CACHE_EXPIRY_SECONDS:
                continue
            old_q = item["question"]
            ratio = difflib.SequenceMatcher(None, new_q_lower, old_q).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_answer = item["answer_bytes"]

        if best_ratio >= threshold:
            return best_answer, best_ratio

        return None, None

    def _find_fuzzy_cached_answer(self, user_id: str, new_question: str, assistant_id: str, threshold=0.9):
        ans, ratio = self._search_in_assistant_cache(user_id, assistant_id, new_question, threshold)
        if ans:
            return ans
        return None

    def _store_in_fuzzy_cache(self, user_id: str, username: str, question: str,
                              answer_bytes: bytes, assistant_id: str, conversation_id: int):
        q_lower = question.strip().lower()
        if user_id not in self.fuzzy_cache:
            self.fuzzy_cache[user_id] = {}
        if assistant_id not in self.fuzzy_cache[user_id]:
            self.fuzzy_cache[user_id][assistant_id] = []

        self.fuzzy_cache[user_id][assistant_id].append({
            "conversation_id": conversation_id,
            "question": q_lower,
            "answer_bytes": answer_bytes,
            "timestamp": time.time()
        })

        record = (user_id, username, q_lower, answer_bytes, conversation_id, time.time())
        self.fuzzy_cache_queue.put(record)

    def _extract_models(self, text: str) -> set:
        lower_t = text.lower()
        models = set()
        if "fabia" in lower_t:
            models.add("fabia")
        if "scala" in lower_t:
            models.add("scala")
        if "kamiq" in lower_t:
            models.add("kamiq")
        if "karoq" in lower_t:
            models.add("karoq")
        if "kodiaq" in lower_t:
            models.add("kodiaq")
        if "enyaq" in lower_t:
            models.add("enyaq")
        if "elroq" in lower_t:
            models.add("elroq")
        if "octavia" in lower_t:
            models.add("octavia")
        if "superb" in lower_t:
            models.add("superb")
        if "test" in lower_t:
            models.add("test")
        return models

    def _assistant_id_from_model_name(self, model_name: str):
        model_name = model_name.lower()
        for asst_id, keywords in self.ASSISTANT_CONFIG.items():
            for kw in keywords:
                if kw.lower() == model_name:
                    return asst_id
        return None

    def _pick_least_busy_assistant(self):
        if not self.ASSISTANT_CONFIG:
            return None
        assistant_thread_counts = {}
        for asst_id in self.ASSISTANT_CONFIG.keys():
            count = 0
            for uid, state_dict in self.user_states.items():
                threads = state_dict.get("threads", {})
                if asst_id in threads:
                    count += 1
            assistant_thread_counts[asst_id] = count

        min_count = min(assistant_thread_counts.values())
        candidates = [aid for aid, c in assistant_thread_counts.items() if c == min_count]
        if not candidates:
            return None
        return random.choice(candidates)

    def _ask(self, username):
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "Invalid JSON format."}), 400
        except Exception as e:
            self.logger.error(f"JSON parsing error: {str(e)}")
            return jsonify({"error": "Invalid JSON format."}), 400

        user_message = data.get("question", "")
        user_id = data.get("user_id", username)
        name_surname = data.get("nam_surnam", username)
        
        if not user_message:
            return jsonify({"response": "Please enter a question."})

        # Session aktivite kontrolü
        if 'last_activity' not in session:
            session['last_activity'] = time.time()
        else:
            session['last_activity'] = time.time()

        corrected_message = self._correct_all_typos(user_message)
        user_models_in_msg = self._extract_models(corrected_message)

        if user_id not in self.user_states:
            self.user_states[user_id] = {}
            self.user_states[user_id]["threads"] = {}

        last_models = self.user_states[user_id].get("last_models", set())
        if not user_models_in_msg and last_models:
            joined_models = " ve ".join(last_models)
            corrected_message = f"{joined_models} {corrected_message}".strip()
            user_models_in_msg = self._extract_models(corrected_message)
            self.logger.info(f"[MODEL-EKLEME] Önceki modeller eklendi -> {joined_models}")

        if user_models_in_msg:
            self.user_states[user_id]["last_models"] = user_models_in_msg

        word_count = len(corrected_message.strip().split())
        local_threshold = 1.0 if word_count < 5 else 0.9

        lower_corrected = corrected_message.lower().strip()
        is_image_req = self.utils.is_image_request(corrected_message)
        user_trims_in_msg = extract_trims(lower_corrected)
        old_assistant_id = self.user_states[user_id].get("assistant_id")
        new_assistant_id = None
        if is_non_sentence_short_reply(corrected_message):
            self.logger.info("Kısa/cümle olmayan cevap: cache devre dışı.")
            cached_answer = None
        else:
            # Fuzzy Cache kontrol (Sadece görsel isteği değilse)
            cached_answer = None
            if not is_image_req:
                cached_answer = self._find_fuzzy_cached_answer(
                    user_id,
                    corrected_message,
                    new_assistant_id,
                    threshold=local_threshold
                )
                # ... (model/trim uyum kontrollerin burada devam ediyor) ...
                if cached_answer:
                    answer_text = cached_answer.decode("utf-8")
                    models_in_answer = self._extract_models(answer_text)
                    if user_models_in_msg and not user_models_in_msg.issubset(models_in_answer):
                        self.logger.info("Model uyuşmazlığı -> cache bypass.")
                        cached_answer = None
                    else:
                        trims_in_answer = extract_trims(answer_text)
                        if len(user_trims_in_msg) == 1:
                            single_trim = list(user_trims_in_msg)[0]
                            if (single_trim not in trims_in_answer) or (len(trims_in_answer) > 1):
                                self.logger.info("Trim uyuşmazlığı -> cache bypass.")
                                cached_answer = None
                        elif len(user_trims_in_msg) > 1:
                            if user_trims_in_msg != trims_in_answer:
                                self.logger.info("Trim uyuşmazlığı (çoklu) -> cache bypass.")
                                cached_answer = None

                    if cached_answer:
                        self.logger.info("Fuzzy cache match bulundu, önbellekten yanıt dönülüyor.")
                        time.sleep(1)
                        return self.app.response_class(cached_answer, mimetype="text/plain")
        # --- YENİ SON ---
        # Model tespitinden asistan ID'si seç
        if len(user_models_in_msg) == 1:
            found_model = list(user_models_in_msg)[0]
            new_assistant_id = self._assistant_id_from_model_name(found_model)
            if new_assistant_id and new_assistant_id != old_assistant_id:
                self.logger.info(f"[ASISTAN SWITCH] {old_assistant_id} -> {new_assistant_id}")
                self.user_states[user_id]["assistant_id"] = new_assistant_id

        elif len(user_models_in_msg) > 1:
            first_model = list(user_models_in_msg)[0]
            new_assistant_id = self._assistant_id_from_model_name(first_model)
            if new_assistant_id and new_assistant_id != old_assistant_id:
                self.logger.info(f"[ASISTAN SWITCH] Çoklu -> İlk model {first_model}, ID {new_assistant_id}")
                self.user_states[user_id]["assistant_id"] = new_assistant_id
        else:
            new_assistant_id = old_assistant_id

        if new_assistant_id is None and old_assistant_id:
            new_assistant_id = old_assistant_id

        # Eğer hiçbir modelle eşleşemediyse, en az yoğun asistanı seç
        if not new_assistant_id:
            new_assistant_id = self._pick_least_busy_assistant()
            if not new_assistant_id:
                # Tek seferlik DB kaydı
                save_to_db(user_id, user_message, "Uygun asistan bulunamadı.", username=name_surname)
                return self.app.response_class("Uygun bir asistan bulunamadı.\n", mimetype="text/plain")

        self.user_states[user_id]["assistant_id"] = new_assistant_id

        

        # Fuzzy Cache kontrol (Sadece görsel isteği değilse)
        cached_answer = None
        if not is_image_req:
            cached_answer = self._find_fuzzy_cached_answer(
                user_id,
                corrected_message,
                new_assistant_id,
                threshold=local_threshold
            )
            if cached_answer:
                # Trim ve model uyumu kontrolü
                answer_text = cached_answer.decode("utf-8")
                models_in_answer = self._extract_models(answer_text)
                if user_models_in_msg and not user_models_in_msg.issubset(models_in_answer):
                    self.logger.info("Model uyuşmazlığı -> cache bypass.")
                    cached_answer = None
                else:
                    trims_in_answer = extract_trims(answer_text)
                    if len(user_trims_in_msg) == 1:
                        single_trim = list(user_trims_in_msg)[0]
                        if (single_trim not in trims_in_answer) or (len(trims_in_answer) > 1):
                            self.logger.info("Trim uyuşmazlığı -> cache bypass.")
                            cached_answer = None
                    elif len(user_trims_in_msg) > 1:
                        if user_trims_in_msg != trims_in_answer:
                            self.logger.info("Trim uyuşmazlığı (çoklu) -> cache bypass.")
                            cached_answer = None

                if cached_answer:
                    self.logger.info("Fuzzy cache match bulundu, önbellekten yanıt dönülüyor.")
                    time.sleep(1)
                    return self.app.response_class(cached_answer, mimetype="text/plain")

        final_answer_parts = []

        def caching_generator():
            try:
                for chunk in self._generate_response(corrected_message, user_id, name_surname):
                    final_answer_parts.append(chunk)
                    yield chunk
            except Exception as ex:
                error_text = f"Bir hata oluştu: {str(ex)}\n"
                final_answer_parts.append(error_text.encode("utf-8"))
                self.logger.error(f"caching_generator hata: {ex}")
            finally:
                full_answer = b"".join(
                    p if isinstance(p, bytes) else p.encode("utf-8")
                    for p in final_answer_parts
                ).decode("utf-8", errors="ignore")

                conversation_id = save_to_db(
                    user_id,
                    user_message,
                    full_answer,
                    username=name_surname
                )

                self.user_states[user_id]["last_conversation_id"] = conversation_id

                 # --- YENİ BAŞLANGIÇ: Cache'e kısa/klişe yanıtı hiç kaydetme! ---
                if not is_image_req and not is_non_sentence_short_reply(corrected_message):
                    self._store_in_fuzzy_cache(
                        user_id,
                        name_surname,
                        corrected_message,
                        b"".join(final_answer_parts),
                        new_assistant_id,
                        conversation_id
                    )
                # --- YENİ SON ---

                yield f"\n[CONVERSATION_ID={conversation_id}]".encode("utf-8")

        return self.app.response_class(caching_generator(), mimetype="text/plain")

    # --------------------------------------------------------
    #                   GÖRSEL MANTIĞI
    # --------------------------------------------------------

    def _make_friendly_image_title(self, model: str, trim: str, filename: str) -> str:
        base_name_no_ext = os.path.splitext(filename)[0]
        base_name_no_ext = base_name_no_ext.replace("_", " ")
        base_name_no_ext = base_name_no_ext.title()

        skip_words = [model.lower(), trim.lower()]
        final_words = []
        for w in base_name_no_ext.split():
            if w.lower() not in skip_words:
                final_words.append(w)
        friendly_title = " ".join(final_words).strip()
        return friendly_title if friendly_title else base_name_no_ext

    def _exclude_other_trims(self, image_list, requested_trim):
        """
        1. İstenen trim dışındaki herhangi bir trim varyantını (örn. "mc", "ces60")
           içeren dosyaları çıkartır.
        2. İstenen trim varyantını içeren **veya** hiç trim barındırmayan
           (genel foto) dosyaları bırakır.
        """
        requested_trim = requested_trim.lower().strip()
        if not requested_trim:
            return image_list  # Kullanıcı trim belirtmediyse dokunma

        requested_variants = normalize_trim_str(requested_trim)

        # Diğer tüm trimlerin varyant listesi
        other_variants = []
        for trim_name in TRIM_VARIANTS.keys():
            if trim_name != requested_trim:
                other_variants.extend(TRIM_VARIANTS[trim_name])

        filtered = []
        for img_file in image_list:
            lower_img = img_file.lower()

            # a) Başka bir trim varyantı içeriyorsa, atla
            if any(v in lower_img for v in other_variants):
                continue

            # b) İstenen trim varyantını içeriyorsa
            has_requested = any(v in lower_img for v in requested_variants)

            # c) Karar
            #    • İstenen trim geçiyorsa: tut
            #    • Hiçbir trim izi yoksa   : genel foto ➜ tut
            if has_requested or not any(v in lower_img for v in TRIM_VARIANTS_FLAT):
                filtered.append(img_file)

        return filtered

    # Rastgele renk görseli
    def _show_single_random_color_image(self, model: str, trim: str):
        model_trim_str = f"{model} {trim}".strip().lower()
        all_color_images = []
        found_any = False

        for clr in self.KNOWN_COLORS:
            filter_str = f"{model_trim_str} {clr}"
            results = self.image_manager.filter_images_multi_keywords(filter_str)
            if results:
                all_color_images.extend(results)
                found_any = True

        if not found_any:
            for clr in self.KNOWN_COLORS:
                fallback_str = f"{model} {clr}"
                results2 = self.image_manager.filter_images_multi_keywords(fallback_str)
                if results2:
                    all_color_images.extend(results2)

        all_color_images = list(set(all_color_images))  # Tekilleştir

        # Trim eleme
        all_color_images = self._exclude_other_trims(all_color_images, trim)

        # Karoq + siyah --> döşeme/koltuk hariç tut
        if model.lower() == "karoq":
            exclude_keywords = ["döşeme", "koltuk", "tam deri", "yarı deri", "thermoflux"]
            filtered = []
            for img in all_color_images:
                lower_img = img.lower()
                if "siyah" in lower_img and any(ek in lower_img for ek in exclude_keywords):
                    continue
                filtered.append(img)
            all_color_images = filtered

        if not all_color_images:
            yield f"{model.title()} {trim.title()} için renk görseli bulunamadı.<br>".encode("utf-8")
            return

        chosen_image = random.choice(all_color_images)
        img_url = f"/static/images/{chosen_image}"
        friendly_title = self._make_friendly_image_title(model, trim, os.path.basename(chosen_image))

        html_block = f"""
<p><b>{friendly_title}</b></p>
<div style="text-align: center; margin-bottom:20px;">
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}','normal')">
    <img src="{img_url}" alt="{friendly_title}" style="max-width: 350px; cursor:pointer;" />
  </a>
</div>
"""
        yield html_block.encode("utf-8")

    # Spesifik renk görseli
    def _show_single_specific_color_image(self, model: str, trim: str, color_keyword: str):
        model_trim_str = f"{model} {trim}".strip().lower()
        search_str_1 = f"{model_trim_str} {color_keyword.lower()}"
        results = self.image_manager.filter_images_multi_keywords(search_str_1)
        results = list(set(results))

        results = self._exclude_other_trims(results, trim)

        if not results and trim:
            fallback_str_2 = f"{model} {color_keyword.lower()}"
            fallback_res = self.image_manager.filter_images_multi_keywords(fallback_str_2)
            fallback_res = list(set(fallback_res))
            fallback_res = self._exclude_other_trims(fallback_res, "")
            results = fallback_res

        # Karoq + siyah --> döşeme/koltuk hariç tut
        if model.lower() == "karoq" and color_keyword.lower() == "siyah":
            exclude_keywords = ["döşeme", "koltuk", "tam deri", "yarı deri", "thermoflux"]
            filtered = []
            for img in results:
                lower_img = img.lower()
                if any(ex_kw in lower_img for ex_kw in exclude_keywords):
                    continue
                filtered.append(img)
            results = filtered

        if not results:
            yield f"{model.title()} {trim.title()} - {color_keyword.title()} rengi için görsel bulunamadı.<br>".encode("utf-8")
            return

        yield f"<b>{model.title()} {trim.title()} - {color_keyword.title()} Rengi</b><br>".encode("utf-8")
        yield b'<div style="display: flex; flex-wrap: wrap; gap: 20px;">'
        for img_file in results:
            img_url = f"/static/images/{img_file}"
            friendly_title = self._make_friendly_image_title(model, trim, os.path.basename(img_file))
            block_html = f"""
<div style="text-align: center; margin: 5px;">
  <div style="font-weight: bold; margin-bottom: 8px;">{friendly_title}</div>
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}','normal')">
    <img src="{img_url}" alt="{friendly_title}" style="max-width: 300px; cursor:pointer;" />
  </a>
</div>
"""
            yield block_html.encode("utf-8")
        yield b"</div><br>"

    def _show_category_images(self, model: str, trim: str, category: str):
        model_trim_str = f"{model} {trim}".strip().lower()

        if category.lower() in ["renkler", "renk"]:
            all_color_images = []
            found_any = False
            for clr in self.KNOWN_COLORS:
                flt = f"{model_trim_str} {clr}"
                results = self.image_manager.filter_images_multi_keywords(flt)
                if results:
                    all_color_images.extend(results)
                    found_any = True

            if not found_any:
                for clr in self.KNOWN_COLORS:
                    flt2 = f"{model} {clr}"
                    results2 = self.image_manager.filter_images_multi_keywords(flt2)
                    if results2:
                        all_color_images.extend(results2)

            all_color_images = list(set(all_color_images))
            if model.lower() == "karoq":
                exclude_keywords = ["döşeme", "koltuk", "tam deri", "yarı deri", "thermoflux"]
                all_color_images = [
                    img for img in all_color_images
                    if not any(ex_kw in img.lower() for ex_kw in exclude_keywords)
                ]
            all_color_images = self._exclude_other_trims(all_color_images, trim)
            heading = f"<b>{model.title()} {trim.title()} - Tüm Renk Görselleri</b><br>"
            yield heading.encode("utf-8")

            if not all_color_images:
                yield f"{model.title()} {trim.title()} için renk görseli bulunamadı.<br>".encode("utf-8")
                return

            yield b'<div style="display: flex; flex-wrap: wrap; gap: 20px;">'
            for img_file in all_color_images:
                img_url = f"/static/images/{img_file}"
                friendly_title = self._make_friendly_image_title(model, trim, os.path.basename(img_file))
                block_html = f"""
<div style="text-align: center; margin: 5px;">
  <div style="font-weight: bold; margin-bottom: 8px;">{friendly_title}</div>
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}','normal')">
    <img src="{img_url}" alt="{friendly_title}" style="max-width: 300px; cursor:pointer;" />
  </a>
</div>
"""
                yield block_html.encode("utf-8")
            yield b"</div><br>"
            return

        filter_str = f"{model_trim_str} {category}".strip().lower()
        found_images = self.image_manager.filter_images_multi_keywords(filter_str)
        found_images = list(set(found_images))
        found_images = self._exclude_other_trims(found_images, trim)
        heading = f"<b>{model.title()} {trim.title()} - {category.title()} Görselleri</b><br>"
        yield heading.encode("utf-8")

        if not found_images:
            yield f"{model.title()} {trim.title()} için '{category}' görseli bulunamadı.<br>".encode("utf-8")
            return

        yield b'<div style="display: flex; flex-wrap: wrap; gap: 20px;">'
        for img_file in found_images:
            img_url = f"/static/images/{img_file}"
            friendly_title = self._make_friendly_image_title(model, trim, os.path.basename(img_file))
            block_html = f"""
<div style="text-align: center; margin: 5px;">
  <div style="font-weight: bold; margin-bottom: 8px;">{friendly_title}</div>
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}','normal')">
    <img src="{img_url}" alt="{friendly_title}" style="max-width: 300px; cursor:pointer;" />
  </a>
</div>
"""
            yield block_html.encode("utf-8")
        yield b"</div><br>"

    def _show_categories_links(self, model, trim):
        model_title = model.title()
        trim_title = trim.title() if trim else ""
        if trim_title:
            base_cmd = f"{model} {trim}"
            heading = f"<b>{model_title} {trim_title} Kategoriler</b><br>"
        else:
            base_cmd = f"{model}"
            heading = f"<b>{model_title} Kategoriler</b><br>"

        categories = [
            ("Dijital Gösterge Paneli", "dijital gösterge paneli"),
            ("Direksiyon Simidi", "direksiyon simidi"),
            ("Döşeme", "döşeme"),
            ("Jant", "jant"),
            ("Multimedya", "multimedya"),
            ("Renkler", "renkler"),
        ]
        html_snippet = heading
        for label, keyw in categories:
            link_cmd = f"{base_cmd} {keyw}".strip()
            html_snippet += f"""&bull; <a href="#" onclick="sendMessage('{link_cmd}');return false;">{label}</a><br>"""

        return html_snippet

    # --------------------------------------------------------
    #                 OPENAI BENZERİ CEVAP
    # --------------------------------------------------------
    def _get_gpt_answer_for_route(self, from_city, to_city, user_message, user_id):
        """Aynı rota sorusunu GPT'ye tekrar sorup daha genel açıklama/gpt yanıtı döner.
        """
        try:
            assistant_id = self.user_states[user_id].get("assistant_id", None)
            if not assistant_id:
                return None
            threads_dict = self.user_states[user_id].get("threads", {})
            thread_id = threads_dict.get(assistant_id)
            if not thread_id:
                new_thread = self.client.beta.threads.create(
                    messages=[{"role": "user", "content": user_message}]
                )
                thread_id = new_thread.id
                threads_dict[assistant_id] = thread_id
                self.user_states[user_id]["threads"] = threads_dict
            else:
                self.client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=user_message
                )

            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )
            start_time = time.time()
            timeout = 60
            while time.time() - start_time < timeout:
                run = self.client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                if run.status == "completed":
                    msg_response = self.client.beta.threads.messages.list(thread_id=thread_id)
                    for msg in msg_response.data:
                        if msg.role == "assistant":
                            content = str(msg.content)
                            content_md = self.markdown_processor.transform_text_to_markdown(content)
                            if '|' in content_md and '\n' in content_md:
                                content_md = fix_markdown_table(content_md)
                            return content_md
                    break
                elif run.status == "failed":
                    return "GPT yanıtı alınamadı."
                time.sleep(0.5)
            return "GPT yanıtı zaman aşımına uğradı."
        except Exception as e:
            return f"GPT yanıtı alınamadı: {str(e)}"

    def _get_route_data(self, from_city: str, to_city: str) -> dict:
        distance_km, duration_min, polyline, error = get_google_route_info(from_city, to_city)
        return {
            "from": from_city, "to": to_city,
            "distance_km": distance_km, "duration_min": duration_min,
            "polyline": polyline, "error": error
        }

    def _yield_route_map(self, rd: dict):
        map_url = google_static_map_with_route(rd["polyline"],
                                           rd["from"], rd["to"])
        html = (
            '<div style="text-align:center;margin-bottom:12px;">'
            f'  <img src="{map_url}" alt="{rd["from"]} ‑ {rd["to"]} rota" '
            '       style="max-width:600px;width:100%;height:auto;display:block;">'
            '</div>'
        )
        yield html.encode("utf-8")
    def _route_prompt(self, rd: dict) -> str:
            """GPT’ye verilecek özet bilgi + talimat."""
            return (
                f"Kullanıcı {rd['from']} ile {rd['to']} kara yolu mesafesini sordu.\n"
                f"- Mesafe: {rd['distance_km']:.1f} km\n"
                f"- Süre: {rd['duration_min']:.0f} dakika\n\n"
                "Bu veriyi samimi, akıcı ve tek paragrafta özetle; "
                "istersen kısaca yol tavsiyesi ekle."
            )
    def _get_gpt_route_brief(self, rd: dict, user_id: str) -> str:
        assistant_id = self.user_states[user_id].get("assistant_id")
        if not assistant_id:
            assistant_id = self._pick_least_busy_assistant()
            self.user_states[user_id]["assistant_id"] = assistant_id

        prompt = (
            "'from' hiçbir zaman mevcut asistan adı olmasın örneğin: Fabia, scala, kamiq, karoq, kodiaq, octavia, superb, elroq, enyaq." 
            f"{rd['from']} ile {rd['to']} arasındaki kara yolu mesafesi "
            f"{rd['distance_km']:.1f} km, ortalama sürüş süresi "
            f"{rd['duration_min']:.0f} dakikadır. "
            "Kullanıcıya bunu samimi ve tek paragraf hâlinde özetle. Mevcut asistan adını konum olarak asla alma."
        )
        return self._ask_assistant(user_id, assistant_id, prompt)
        
    def _ensure_thread(self, user_id: str, assistant_id: str) -> str:
        """Kullanıcının bu asistana ait thread’ini oluşturur veya döndürür."""
        threads = self.user_states[user_id].setdefault("threads", {})
        thread_id = threads.get(assistant_id)

        if not thread_id:
            t = self.client.beta.threads.create()      # boş thread
            thread_id = t.id
            threads[assistant_id] = thread_id
        return thread_id    
    def _ask_assistant(self,
                   user_id: str,
                   assistant_id: str,
                   content: str,
                   timeout: float = 60.0) -> str:
        """Verilen içeriği thread’e yazar, run’ı başlatır, cevabı döner."""
        thread_id = self._ensure_thread(user_id, assistant_id)

        # 1) Kullanıcı mesajını ekle
        self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content
        )

        # 2) Run başlat
        run = self.client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id
        )

        # 3) Tamamlanana kadar bekle
        start = time.time()
        while time.time() - start < timeout:
            run = self.client.beta.threads.runs.retrieve(
                thread_id=thread_id, run_id=run.id
            )
            if run.status == "completed":
                break
            if run.status == "failed":
                raise RuntimeError(run.last_error["message"])
            time.sleep(0.5)

        # 4) Son asistan mesajını al
        msgs = self.client.beta.threads.messages.list(
            thread_id=thread_id, order="desc", limit=5
        )
        for m in msgs.data:
            if m.role == "assistant":
                return m.content[0].text.value
        return "Yanıt bulunamadı."
    ##############################################################################
# ChatbotAPI._generate_response
##############################################################################
    def _generate_response(self, user_message: str, user_id: str, username: str = ""):
    # ------------------------------------------------------------------
    #  ROTA / MESAFE SORGUSU
    # ------------------------------------------------------------------
        # ---  YAKIT (benzin/dizel) SORUSU  ------------------------------------
        f1, f2, fuel_model, fuel_trim = parse_fuel_question(user_message)

        if f1 and f2:
            # model tanımlı değilse oturumdan çek
            if not fuel_model:
                asst_id = self.user_states[user_id].get("assistant_id")
                fuel_model = (
                    self.ASSISTANT_NAME_MAP.get(asst_id, "").lower()
                    if asst_id else None
                ) or next(iter(self.user_states[user_id].get("last_models", [])), None)

            if not fuel_model:
                yield ("Hangi modeli kullanacağınızı da belirtir misiniz? "
                    "(örn. *karoq*, *octavia* …)").encode("utf-8")
                return

            rd = self._get_route_data(f1, f2)
            if rd["error"]:
                yield rd["error"].encode("utf-8")
                return

            # FUEL_SPECS’ten tüketim verisi
            spec = FUEL_SPECS.get((fuel_model, (fuel_trim or "").lower())) \
                or FUEL_SPECS.get((fuel_model, ""))
            if not spec:
                yield f"{fuel_model.title()} modeli için ortalama yakıt verisi bulunamadı.".encode("utf-8")
                return

            l100 = spec["l_per_100km"]             # lt / 100 km
            litre = self._fuel_needed_litre(rd["distance_km"], l100)

            # Harita
            yield from self._yield_route_map(rd)
            yield b"<!-- SPLIT -->"

            # Özet
            txt = (
                f"**{f1} – {f2}** arası yol yaklaşık **{rd['distance_km']:.0f} km**.\n\n"
                f"{fuel_model.title()} için fabrika ortalaması **{l100:.1f} L/100 km** alındığında "
                f"bu yolculukta yaklaşık **{litre:.1f} litre** yakıt harcarsınız.\n\n"
                "_Gerçek tüketim; hız, yük, klima ve yol durumuna göre değişebilir._"
            )
            yield txt.encode("utf-8")
            return
        # ----------------------------------------------------------------------

        c1, c2, ev_model, ev_trim = parse_charging_question(user_message)
        if c1 and c2:                    # eşleşme varsa model olmayabilir
    # ▸ model yoksa oturumdan/fallback
            if not ev_model:
                asst_id  = self.user_states[user_id].get("assistant_id")
                ev_model = (
                    self.ASSISTANT_NAME_MAP.get(asst_id, "").lower() 
                    if asst_id else None
                ) or next(iter(self.user_states[user_id].get("last_models", [])), None)

            if not ev_model:
                yield ("Hangi modeli kullandığınızı da belirtir misiniz? "
                    "(örn. *enyaq*, *kodiaq* …)").encode("utf-8")
                return

        if c1 and c2 and ev_model:
            rd = self._get_route_data(c1, c2)
            if rd["error"]:
                yield rd["error"].encode("utf-8")
                return

            range_km, unit = self._lookup_range_and_unit(ev_model, ev_trim or "")
            if range_km is None:
                msg = (f"{ev_model.title()} {ev_trim.title() if ev_trim else ''} için "
                    "menzil / tüketim verisi bulunamadı.")
                yield msg.encode("utf-8")
                return

            charges = self._charges_needed(rd["distance_km"], range_km)
            unit_txt = "şarj" if unit == "şarj" else "yakıt ikmâli"

            # Harita
            yield from self._yield_route_map(rd)
            yield b"<!-- SPLIT -->"

            # Sonuç paragrafı
            summary = (
                f"**{c1} – {c2}** güzergâhı yaklaşık **{rd['distance_km']:.0f} km**. "
                f"{ev_model.title()} {ev_trim.title() if ev_trim else ''} modelinin tek {unit} menzili "
                f"**{range_km:.0f} km** kabul edildiğinde, yola tam dolu başladığınızda "
                f"**{charges} {unit_txt}** gerekir.\n\n"
                "_Gerçek ihtiyaç; sürüş stili, hava ve hızınıza göre değişebilir._"
            )
            yield summary.encode("utf-8")

            # İsterseniz yolculuk deneyimi / GPT yorumu ekleyin:
            journey_txt = self._get_gpt_journey_with_model(rd, user_id)
            if journey_txt:
                yield b"\n\n"
                yield journey_txt.encode("utf-8")
            return


        from_city, to_city = parse_route_question(user_message)
        if from_city and to_city:
            rd = self._get_route_data(from_city, to_city)
            if rd["error"]:
                yield rd["error"].encode("utf-8")
                return

            # AŞAMA 1 – Statik harita resmi
            yield from self._yield_route_map(rd)
            yield b"<!-- SPLIT -->"                 # front‑end ayraç

            # AŞAMA 2 – Mesafe & süre özeti
            brief_txt = self._get_gpt_route_brief(rd, user_id)
            yield brief_txt.encode("utf-8")

            # AŞAMA 3 – Mevcut modelle yolculuk hissi
            journey_txt = self._get_gpt_journey_with_model(rd, user_id)
            if journey_txt:
                yield b"\n\n"
                yield journey_txt.encode("utf-8")
            return                     # rota sorusu tamamlandı
        self.logger.info(f"[_generate_response] Kullanıcı ({user_id}): {user_message}")
        assistant_id = self.user_states[user_id].get("assistant_id", None)
        if "current_trim" not in self.user_states[user_id]:
            self.user_states[user_id]["current_trim"] = ""

        lower_msg = user_message.lower()
        teknik_keywords = [
            "teknik özellik", "teknik veriler", "teknik veri", "motor özellik", "motor donanım", "motor teknik", "teknik tablo", "teknik", "performans"
        ]

        if any(kw in lower_msg for kw in teknik_keywords):
            user_models_in_msg2 = self._extract_models(user_message)
            found_model = None
            if len(user_models_in_msg2) == 1:
                found_model = list(user_models_in_msg2)[0]
            elif len(user_models_in_msg2) > 1:
                found_model = list(user_models_in_msg2)[0]

            if not found_model and assistant_id:
                found_model = self.ASSISTANT_NAME_MAP.get(assistant_id, "").lower()

            if found_model and found_model.lower() == "fabia":
                yield "<b>Fabia Teknik Özellikleri</b><br>"
                yield FABIA_TEKNIK_MD.encode("utf-8")
                return
            if found_model and found_model.lower() == "scala":
                yield "<b>Scala Teknik Özellikleri</b><br>"
                yield SCALA_TEKNIK_MD.encode("utf-8")
                return
            if found_model and found_model.lower() == "kamiq":
                yield "<b>Kamiq Teknik Özellikleri</b><br>"
                yield KAMIQ_TEKNIK_MD.encode("utf-8")
                return
            if found_model and found_model.lower() == "karoq":
                yield "<b>Karoq Teknik Özellikleri</b><br>"
                yield KAROQ_TEKNIK_MD.encode("utf-8")
                return
            if found_model and found_model.lower() == "kodiaq":
                yield "<b>Kodiaq Teknik Özellikleri</b><br>"
                yield KODIAQ_TEKNIK_MD.encode("utf-8")
                return
            if found_model and found_model.lower() == "enyaq":
                yield "<b>Enyaq Teknik Özellikleri</b><br>"
                yield ENYAQ_TEKNIK_MD.encode("utf-8")
                return
            if found_model and found_model.lower() == "elroq":
                yield "<b>Elroq Teknik Özellikleri</b><br>"
                yield ELROQ_TEKNIK_MD.encode("utf-8")
                return
            if found_model and found_model.lower() == "octavia":
                yield "<b>Octavia Teknik Özellikleri</b><br>"
                yield OCTAVIA_TEKNIK_MD.encode("utf-8")
                return
            if found_model and found_model.lower() == "superb":
                yield "<b>Superb Teknik Özellikleri</b><br>"
                yield SUPERB_TEKNIK_MD.encode("utf-8")
                return
            

        # 1) Kategori eşleşmesi
        categories_pattern = r"(dijital gösterge paneli|direksiyon simidi|döşeme|jant|multimedya|renkler)"
        cat_match = re.search(
            fr"(fabia|scala|kamiq|karoq|kodiaq|octavia|enyaq|elroq|superb)\s*(premium|monte carlo|elite|prestige|sportline|e prestige 60|coupe e sportline 60|coupe e sportline 85x|e sportline 60|e sportline 85x|rs)?\s*({categories_pattern})",
             lower_msg
        )
        if cat_match:
            time.sleep(1)
            matched_model = cat_match.group(1)
            matched_trim = cat_match.group(2) or ""
            matched_category = cat_match.group(3)

            if matched_trim and (matched_trim not in self.MODEL_VALID_TRIMS[matched_model]):
                yield from self._yield_invalid_trim_message(matched_model, matched_trim)
                return

            self.user_states[user_id]["current_trim"] = matched_trim
            yield from self._show_category_images(matched_model, matched_trim, matched_category)
            cat_links_html = self._show_categories_links(matched_model, matched_trim)
            yield cat_links_html.encode("utf-8")
            return

        # 2) Renkli görsel pattern
        color_req_pattern = (
            r"(fabia|scala|kamiq|karoq|kodiaq|octavia|enyaq|elroq|superb)"
            r"\s*(premium|monte carlo|elite|prestige|sportline|"
            r"e prestige 60|coupe e sportline 60|coupe e sportline 85x|"
            r"e sportline 60|e sportline 85x)?"
            r"\s+([a-zçığöşü]+)\s*(?:renk)?\s*"
            r"(?:görsel(?:er)?|resim(?:ler)?|foto(?:ğ|g)raf(?:lar)?|nasıl\s+görün(?:üyo?r)?|görün(?:üyo?r)?|göster(?:ir)?\s*(?:misin)?|göster)"
        )
        clr_match = re.search(color_req_pattern, lower_msg)
        if clr_match:
            matched_model = clr_match.group(1)
            matched_trim = clr_match.group(2) or ""
            matched_color = clr_match.group(3)
                    # ------------------------------------------------------------------
        #  >>>>  YENİ KONTROL – 'premium' vb. aslında bir trim mi?
        # ------------------------------------------------------------------
            # Eğer 'renk' olarak yakalanan kelime aslında bir trim varyantıysa
            variant_lower = matched_color.lower().strip()
            if variant_lower in VARIANT_TO_TRIM:
                # Bu durumda akışı 'model + trim + görsel' mantığına yönlendiriyoruz
                matched_trim = VARIANT_TO_TRIM[variant_lower]   # kanonik trim adı
                # Trim doğrulaması
                if matched_trim not in self.MODEL_VALID_TRIMS[matched_model]:
                    yield from self._yield_invalid_trim_message(matched_model, matched_trim)
                    return

                # Doğrudan rastgele trim görseli
                yield from self._show_single_random_color_image(matched_model, matched_trim)
                cat_links_html = self._show_categories_links(matched_model, matched_trim)
                yield cat_links_html.encode("utf-8")
                return
        # ------------------------------------------------------------------
        #  >>>>  (Bundan sonrası – 'renk' olarak devam eden eski kod – değişmedi)
        # ------------------------------------------------------------------
            

            if matched_trim and (matched_trim not in self.MODEL_VALID_TRIMS[matched_model]):
                yield from self._yield_invalid_trim_message(matched_model, matched_trim)
                return

            # Renk eşleşmesi
            color_found = None
            possible_colors_lower = [c.lower() for c in self.KNOWN_COLORS]
            close_matches = difflib.get_close_matches(matched_color, possible_colors_lower, n=1, cutoff=0.6)
            if close_matches:
                best_match_lower = close_matches[0]
                for c in self.KNOWN_COLORS:
                    if c.lower() == best_match_lower:
                        color_found = c
                        break

            if not color_found:
                yield (f"Üzgünüm, '{matched_color}' rengi için bir eşleşme bulamadım. "
                       f"Rastgele renk gösteriyorum...<br>").encode("utf-8")
                yield from self._show_single_random_color_image(matched_model, matched_trim)
                cat_links_html = self._show_categories_links(matched_model, matched_trim)
                yield cat_links_html.encode("utf-8")
                return
            else:
                yield from self._show_single_specific_color_image(matched_model, matched_trim, color_found)
                cat_links_html = self._show_categories_links(matched_model, matched_trim)
                yield cat_links_html.encode("utf-8")
                return
        
        model_color_trim_pattern = (
            r"(fabia|scala|kamiq|karoq|kodiaq|octavia|enyaq|elroq|superb)"            # model
            r"\s+([a-zçığöşü]+)"                               # renk kelimesi
            r"\s+(premium|monte carlo|elite|prestige|sportline|"
            r"e prestige 60|coupe e sportline 60|coupe e sportline 85x|"
            r"e sportline 60|e sportline 85x)"                  # trim
            r"\s*(?:renk)?\s*"                                 # ops. “renk”
            r"(?:görsel(?:er)?|resim(?:ler)?|foto(?:ğ|g)raf(?:lar)?"
            r"|nasıl\s+görün(?:üyo?r)?|görün(?:üyo?r)?|göster(?:ir)?\s*(?:misin)?|göster)"
        )
        mct_match = re.search(model_color_trim_pattern, lower_msg)
        if mct_match:
            matched_model  = mct_match.group(1)
            matched_color  = mct_match.group(2)
            matched_trim   = mct_match.group(3)

            # Trim doğrulaması
            if matched_trim not in self.MODEL_VALID_TRIMS[matched_model]:
                yield from self._yield_invalid_trim_message(matched_model, matched_trim)
                return

            # Renk yakın eşleşmesi
            color_found = None
            possible_colors_lower = [c.lower() for c in self.KNOWN_COLORS]
            close_matches = difflib.get_close_matches(matched_color.lower(), possible_colors_lower, n=1, cutoff=0.6)
            if close_matches:
                best_lower = close_matches[0]
                color_found = next(c for c in self.KNOWN_COLORS if c.lower() == best_lower)

            if not color_found:
                # Renk bulunamadıysa rastgele trim görseli
                yield (f"'{matched_color}' rengi bulunamadı; rastgele {matched_trim.title()} görseli gösteriyorum…<br>").encode("utf-8")
                yield from self._show_single_random_color_image(matched_model, matched_trim)
            else:
                yield from self._show_single_specific_color_image(matched_model, matched_trim, color_found)

            cat_links_html = self._show_categories_links(matched_model, matched_trim)
            yield cat_links_html.encode("utf-8")
            return


        # 3) Ters sıra renk + model + görsel
        reverse_color_pattern = (
            r"([a-zçığöşü]+)\s+"
            r"(fabia|scala|kamiq|karoq|kodiaq|octavia|enyaq|elroq|superb)"
            r"(?:\s+(premium|monte carlo|elite|prestige|sportline|"
            r"e prestige 60|coupe e sportline 60|coupe e sportline 85x|"
            r"e sportline 60|e sportline 85x))?"
            r"\s*(?:renk)?\s*"
            r"(?:görsel(?:er)?|resim(?:ler)?|foto(?:ğ|g)raf(?:lar)?|nasıl\s+görün(?:üyo?r)?|görün(?:üyo?r)?|göster(?:ir)?\s*(?:misin)?|göster)"
        )
        rev_match = re.search(reverse_color_pattern, lower_msg)
        if rev_match:
            matched_color = rev_match.group(1)
            matched_model = rev_match.group(2)
            matched_trim = rev_match.group(3) or ""

            if matched_trim and (matched_trim not in self.MODEL_VALID_TRIMS[matched_model]):
                yield from self._yield_invalid_trim_message(matched_model, matched_trim)
                return

            # Renk yakın eşleşme
            color_found = None
            possible_colors_lower = [c.lower() for c in self.KNOWN_COLORS]
            close_matches = difflib.get_close_matches(matched_color, possible_colors_lower, n=1, cutoff=0.6)
            if close_matches:
                best_match_lower = close_matches[0]
                for c in self.KNOWN_COLORS:
                    if c.lower() == best_match_lower:
                        color_found = c
                        break

            if not color_found:
                yield (f"Üzgünüm, '{matched_color}' rengi için bir eşleşme bulamadım. "
                       f"Rastgele renk gösteriyorum...<br>").encode("utf-8")
                yield from self._show_single_random_color_image(matched_model, matched_trim)
                cat_links_html = self._show_categories_links(matched_model, matched_trim)
                yield cat_links_html.encode("utf-8")
                return
            else:
                yield from self._show_single_specific_color_image(matched_model, matched_trim, color_found)
                cat_links_html = self._show_categories_links(matched_model, matched_trim)
                yield cat_links_html.encode("utf-8")
                return

        # 4) Birden fazla model + görsel
        pairs = extract_model_trim_pairs(lower_msg)
        is_image_req = self.utils.is_image_request(lower_msg)
        if len(pairs) >= 2 and is_image_req:
            time.sleep(1)
            for (model, trim) in pairs:
                yield f"<b>{model.title()} Görselleri</b><br>".encode("utf-8")
                yield from self._show_single_random_color_image(model, trim)
                cat_links_html = self._show_categories_links(model, trim)
                yield cat_links_html.encode("utf-8")
            return

        # 5) Tek model + trim + “görsel”
        model_trim_image_pattern = (
            r"(fabia|scala|kamiq|karoq|kodiaq|octavia|enyaq|elroq|superb)"
            r"(?:\s+(premium|monte carlo|elite|prestige|sportline|"
            r"e prestige 60|coupe e sportline 60|coupe e sportline 85x|"
            r"e sportline 60|e sportline 85x))?\s+"
            r"(?:görsel(?:er)?|resim(?:ler)?|foto(?:ğ|g)raf(?:lar)?)"
        )
        match = re.search(model_trim_image_pattern, lower_msg)
        if match:
            time.sleep(1)
            matched_model = match.group(1)
            matched_trim = match.group(2) or ""

            if matched_trim and (matched_trim not in self.MODEL_VALID_TRIMS[matched_model]):
                yield from self._yield_invalid_trim_message(matched_model, matched_trim)
                return

            self.user_states[user_id]["current_trim"] = matched_trim
            yield from self._show_single_random_color_image(matched_model, matched_trim)
            cat_links_html = self._show_categories_links(matched_model, matched_trim)
            yield cat_links_html.encode("utf-8")
            return

        # 6) Opsiyonel tablo istekleri
        user_trims_in_msg = extract_trims(lower_msg)
        pending_ops_model = self.user_states[user_id].get("pending_opsiyonel_model", None)

        if "opsiyonel" in lower_msg:
            self.logger.info("DEBUG -> 'opsiyonel' kelimesi bulundu. Model aranıyor.")
            found_model = None
            user_models_in_msg2 = self._extract_models(user_message)
            if len(user_models_in_msg2) == 1:
                found_model = list(user_models_in_msg2)[0]
            elif len(user_models_in_msg2) > 1:
                found_model = list(user_models_in_msg2)[0]

            if not found_model and assistant_id:
                found_model = self.ASSISTANT_NAME_MAP.get(assistant_id, "").lower()

            # Elroq tek donanım => doğrudan
            if found_model and found_model.lower() == "elroq":
                the_trim = "e prestige 60"
                yield from self._yield_opsiyonel_table(user_id, user_message, "elroq", the_trim)
                return

            # Enyaq => hepsini beraber gösterelim
            if found_model and found_model.lower() == "enyaq":
                yield from self._yield_multi_enyaq_tables()
                return

            if not found_model:
                yield "Hangi modelin opsiyonel donanımlarını görmek istersiniz?"
                return
            else:
                self.logger.info(f"DEBUG -> Opsiyonel istenen model: {found_model}")
                old_model_name = self.ASSISTANT_NAME_MAP.get(assistant_id, "").lower()
                if found_model != old_model_name:
                    new_asst = self._assistant_id_from_model_name(found_model)
                    if new_asst and new_asst != assistant_id:
                        self.logger.info(f"[ASISTAN SWITCH][OPSİYONEL] {old_model_name} -> {found_model}")
                        self.user_states[user_id]["assistant_id"] = new_asst

                self.user_states[user_id]["pending_opsiyonel_model"] = found_model
                if len(user_trims_in_msg) == 1:
                    found_trim = list(user_trims_in_msg)[0]
                    if found_trim not in self.MODEL_VALID_TRIMS.get(found_model, []):
                        yield from self._yield_invalid_trim_message(found_model, found_trim)
                        return
                    time.sleep(1)
                    yield from self._yield_opsiyonel_table(user_id, user_message, found_model, found_trim)
                    return
                else:
                    # Trim seçmemişse tablo linkleri
                    if found_model.lower() == "fabia":
                        yield from self._yield_trim_options("fabia", ["premium", "monte carlo"])
                        return
                    elif found_model.lower() == "scala":
                        yield from self._yield_trim_options("scala", ["elite", "premium", "monte carlo"])
                        return
                    elif found_model.lower() == "kamiq":
                        yield from self._yield_trim_options("kamiq", ["elite", "premium", "monte carlo"])
                        return
                    elif found_model.lower() == "karoq":
                        yield from self._yield_trim_options("karoq", ["premium", "prestige", "sportline"])
                        return
                    elif found_model.lower() == "kodiaq":
                        yield from self._yield_trim_options("kodiaq", ["premium", "prestige", "sportline", "rs"])
                        return
                    elif found_model.lower() == "octavia":
                        yield from self._yield_trim_options("octavia", ["elite", "premium", "prestige", "sportline", "rs"])
                        return
                    elif found_model.lower() == "superb":
                        yield from self._yield_trim_options("superb", ["premium", "prestige", "l&k crystal", "sportline phev"])
                        return
                    elif found_model.lower() == "enyaq":
                        yield from self._yield_trim_options("enyaq", [
                            "e prestige 60",
                            "coupe e sportline 60",
                            "coupe e sportline 85x",
                            "e sportline 60",
                            "e sportline 85x"
                        ])
                        return
                    elif found_model.lower() == "elroq":
                        yield from self._yield_trim_options("elroq", ["e prestige 60"])
                        return
                    else:
                        yield f"'{found_model}' modeli için opsiyonel donanım listesi tanımlanmamış.\n".encode("utf-8")
                        return

        # Eğer zaten opsiyonel mod bekliyorsak
        if pending_ops_model:
            self.logger.info(f"DEBUG -> pending_ops_model={pending_ops_model}, user_trims_in_msg={user_trims_in_msg}")
            if user_trims_in_msg:
                if len(user_trims_in_msg) == 1:
                    found_trim = list(user_trims_in_msg)[0]
                    if found_trim not in self.MODEL_VALID_TRIMS.get(pending_ops_model, []):
                        yield from self._yield_invalid_trim_message(pending_ops_model, found_trim)
                        return
                    time.sleep(1)
                    yield from self._yield_opsiyonel_table(user_id, user_message, pending_ops_model, found_trim)
                    return
                else:
                    if pending_ops_model.lower() == "fabia":
                        yield from self._yield_trim_options("fabia", ["premium", "monte carlo"])
                        return
                    elif pending_ops_model.lower() == "scala":
                        yield from self._yield_trim_options("scala", ["elite", "premium", "monte carlo"])
                        return
                    elif pending_ops_model.lower() == "kamiq":
                        yield from self._yield_trim_options("kamiq", ["elite", "premium", "monte carlo"])
                        return
                    elif pending_ops_model.lower() == "karoq":
                        yield from self._yield_trim_options("karoq", ["premium", "prestige", "sportline"])
                        return
                    elif pending_ops_model.lower() == "kodiaq":
                        yield from self._yield_trim_options("kodiaq", ["premium", "prestige", "sportline", "rs"])
                        return
                    elif pending_ops_model.lower() == "octavia":
                        yield from self._yield_trim_options("octavia", ["elite", "premium", "prestige", "sportline", "rs"])
                        return
                    elif pending_ops_model.lower() == "superb":
                        yield from self._yield_trim_options("superb", ["premium", "prestige", "l&k crystal", "sportline phev"])
                        return 
                    elif pending_ops_model.lower() == "enyaq":
                        yield from self._yield_trim_options("enyaq", [
                            "e prestige 60",
                            "coupe e sportline 60",
                            "coupe e sportline 85x",
                            "e sportline 60",
                            "e sportline 85x"
                        ])
                        return
                    elif pending_ops_model.lower() == "elroq":
                        yield from self._yield_trim_options("elroq", ["e prestige 60"])
                        return
                    else:
                        yield f"'{pending_ops_model}' modeli için opsiyonel donanım listesi tanımlanmamış.\n".encode("utf-8")
                        return
            else:
                # Hiç trim yazmadıysa
                if pending_ops_model.lower() == "fabia":
                    yield from self._yield_trim_options("fabia", ["premium", "monte carlo"])
                    return
                elif pending_ops_model.lower() == "scala":
                    yield from self._yield_trim_options("scala", ["elite", "premium", "monte carlo"])
                    return
                elif pending_ops_model.lower() == "kamiq":
                    yield from self._yield_trim_options("kamiq", ["elite", "premium", "monte carlo"])
                    return
                elif pending_ops_model.lower() == "karoq":
                    yield from self._yield_trim_options("karoq", ["premium", "prestige", "sportline"])
                    return
                elif pending_ops_model.lower() == "kodiaq":
                   yield from self._yield_trim_options("kodiaq", ["premium", "prestige", "sportline", "rs"])                     
                elif pending_ops_model.lower() == "octavia":
                    yield from self._yield_trim_options("octavia", ["elite", "premium", "prestige", "sportline", "rs"])
                    return
                elif pending_ops_model.lower() == "enyaq":
                    yield from self._yield_trim_options("enyaq", [
                        "e prestige 60",
                        "coupe e sportline 60",
                        "coupe e sportline 85x",
                        "e sportline 60",
                        "e sportline 85x"
                    ])
                    return
                elif pending_ops_model.lower() == "elroq":
                    yield from self._yield_trim_options("elroq", ["e prestige 60"])
                    return
                else:
                    yield f"'{pending_ops_model}' modeli için opsiyonel donanım listesi tanımlanmamış.\n".encode("utf-8")
                    return

        # 7) Görsel (image) isteği
        if is_image_req:
            user_models_in_msg2 = self._extract_models(user_message)
            if not user_models_in_msg2 and "last_models" in self.user_states[user_id]:
                user_models_in_msg2 = self.user_states[user_id]["last_models"]

            if user_models_in_msg2:
                if len(user_models_in_msg2) > 1:
                    yield "Birden fazla model algılandı, rastgele görseller paylaşıyorum...<br>"
                    for m in user_models_in_msg2:
                        yield f"<b>{m.title()} Görselleri</b><br>".encode("utf-8")
                        yield from self._show_single_random_color_image(m, "")
                        cat_links_html = self._show_categories_links(m, "")
                        yield cat_links_html.encode("utf-8")
                    return
                else:
                    single_model = list(user_models_in_msg2)[0]
                    yield f"<b>{single_model.title()} için rastgele görseller</b><br>".encode("utf-8")
                    yield from self._show_single_random_color_image(single_model, "")
                    cat_links_html = self._show_categories_links(single_model, "")
                    yield cat_links_html.encode("utf-8")
                    return
            else:
                yield ("Hangi modelin görsellerine bakmak istersiniz? "
                       "(Fabia, Kamiq, Scala, Karoq, Enyaq, Elroq vb.)<br>")
                return

        # 8) Eğer buraya geldiysek => OpenAI API'ye gidilecek
        if not assistant_id:
            yield "Uygun bir asistan bulunamadı.\n"
            return

        try:
            threads_dict = self.user_states[user_id].get("threads", {})
            thread_id = threads_dict.get(assistant_id)

            # Thread yoksa oluştur
            if not thread_id:
                new_thread = self.client.beta.threads.create(
                    messages=[{"role": "user", "content": user_message}]
                )
                thread_id = new_thread.id
                threads_dict[assistant_id] = thread_id
                self.user_states[user_id]["threads"] = threads_dict
            else:
                # Mevcut threade yeni kullanıcı mesajını ekle
                self.client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=user_message
                )

            # Asistan ile koş
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )

            start_time = time.time()
            timeout = 60
            assistant_response = ""

            # run tamamlanana veya fail olana kadar bekle
            while time.time() - start_time < timeout:
                run = self.client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                if run.status == "completed":
                    msg_response = self.client.beta.threads.messages.list(thread_id=thread_id)
                    for msg in msg_response.data:
                        if msg.role == "assistant":
                            content = str(msg.content)
                            content_md = self.markdown_processor.transform_text_to_markdown(content)
                            # --- YENİ EK: Tablo fix'i burada uygula ---
                            if '|' in content_md and '\n' in content_md:
                                content_md = fix_markdown_table(content_md)
                            assistant_response = content
                            yield content_md.encode("utf-8")
                    break
                elif run.status == "failed":
                    yield "Yanıt oluşturulamadı.\n"
                    return
                time.sleep(0.5)

            if not assistant_response:
                yield "Yanıt alma zaman aşımına uğradı.\n"
                return

        except Exception as e:
            error_msg = f"Hata: {str(e)}"
            self.logger.error(f"Yanıt oluşturma hatası: {str(e)}")
            yield f"{error_msg}\n".encode("utf-8")

    def _yield_invalid_trim_message(self, model, invalid_trim):
        msg = f"{model.title()} {invalid_trim.title()} modelimiz bulunmamaktadır.<br>"
        msg += (f"{model.title()} {invalid_trim.title()} modelimiz yok. "
                f"Aşağıdaki donanımlarımızı inceleyebilirsiniz:<br><br>")
        yield msg.encode("utf-8")

        valid_trims = self.MODEL_VALID_TRIMS.get(model, [])
        for vt in valid_trims:
            cmd_str = f"{model} {vt} görsel"
            link_label = f"{model.title()} {vt.title()}"
            link_html = f"""&bull; <a href="#" onclick="sendMessage('{cmd_str}');return false;">{link_label}</a><br>"""
            yield link_html.encode("utf-8")

    def _yield_opsiyonel_table(self, user_id, user_message, model_name, trim_name):
        self.logger.info(f"_yield_opsiyonel_table() called => model={model_name}, trim={trim_name}")
        time.sleep(1)
        table_yielded = False

        # Fabia
        if model_name == "fabia":
            if "premium" in trim_name:
                yield FABIA_PREMIUM_MD.encode("utf-8")
                table_yielded = True
            elif "monte" in trim_name:
                yield FABIA_MONTE_CARLO_MD.encode("utf-8")
                table_yielded = True
            else:
                yield "Fabia için geçerli donanımlar: Premium / Monte Carlo\n"

        # Scala
        elif model_name == "scala":
            if "premium" in trim_name:
                yield SCALA_PREMIUM_MD.encode("utf-8")
                table_yielded = True
            elif "monte" in trim_name:
                yield SCALA_MONTE_CARLO_MD.encode("utf-8")
                table_yielded = True
            elif "elite" in trim_name:
                yield SCALA_ELITE_MD.encode("utf-8")
                table_yielded = True
            else:
                yield "Scala için geçerli donanımlar: Premium / Monte Carlo / Elite\n"

        # Kamiq
        elif model_name == "kamiq":
            if "elite" in trim_name:
                yield KAMIQ_ELITE_MD.encode("utf-8")
                table_yielded = True
            elif "premium" in trim_name:
                yield KAMIQ_PREMIUM_MD.encode("utf-8")
                table_yielded = True
            elif "monte" in trim_name:
                yield KAMIQ_MONTE_CARLO_MD.encode("utf-8")
                table_yielded = True
            else:
                yield "Kamiq için geçerli donanımlar: Elite / Premium / Monte Carlo\n"

        # Karoq
        elif model_name == "karoq":
            if "premium" in trim_name:
                yield KAROQ_PREMIUM_MD.encode("utf-8")
                table_yielded = True
            elif "prestige" in trim_name:
                yield KAROQ_PRESTIGE_MD.encode("utf-8")
                table_yielded = True
            elif "sportline" in trim_name:
                yield KAROQ_SPORTLINE_MD.encode("utf-8")
                table_yielded = True
            else:
                yield "Karoq için geçerli donanımlar: Premium / Prestige / Sportline\n"

                # Kodiaq  -----------------------------------------------------------------
        elif model_name == "kodiaq":
            if "premium" in trim_name:
                yield KODIAQ_PREMIUM_MD.encode("utf-8")
            elif "prestige" in trim_name:
                yield KODIAQ_PRESTIGE_MD.encode("utf-8")
            elif "sportline" in trim_name:
                yield KODIAQ_SPORTLINE_MD.encode("utf-8")
            elif "rs" in trim_name:
                yield KODIAQ_RS_MD.encode("utf-8")
            else:
                yield "Kodiaq için geçerli donanımlar: Premium / Prestige / Sportline / RS\n"
            table_yielded = True
        elif model_name == "octavia":
            if "elite" in trim_name:
                yield OCTAVIA_ELITE_MD.encode("utf-8")
            elif "premium" in trim_name:
                yield OCTAVIA_PREMIUM_MD.encode("utf-8")
            elif "prestige" in trim_name:
                yield OCTAVIA_PRESTIGE_MD.encode("utf-8")
            elif "sportline" in trim_name:
                yield OCTAVIA_SPORTLINE_MD.encode("utf-8")
            elif "rs" in trim_name:
                yield OCTAVIA_RS_MD.encode("utf-8")
            else:
                yield "Octavia için geçerli donanımlar: Elite / Premium / Prestige / Sportline / RS\n"
            table_yielded = True
        elif model_name == "test":
            if "e prestige 60" in trim_name:
                yield TEST_E_PRESTIGE_60_MD.encode("utf-8")
            elif "premium" in trim_name:
                yield TEST_PREMIUM_MD.encode("utf-8")
            elif "prestige" in trim_name:
                yield TEST_PRESTIGE_MD.encode("utf-8")
            elif "sportline" in trim_name:
                yield TEST_SPORTLINE_MD.encode("utf-8")
            else:
                yield "Test için geçerli donanımlar: E-prestige 60 / Premium / Prestige / Sportline\n"
            table_yielded = True
        # Enyaq
        elif model_name == "enyaq":
            tr_lower = trim_name.lower()
            if "e prestige 60" in tr_lower:
                yield ENYAQ_E_PRESTIGE_60_MD.encode("utf-8")
                table_yielded = True
            elif ("coupe e sportline 60" in tr_lower) or ("e sportline 60" in tr_lower):
                yield ENYAQ_COUPE_E_SPORTLINE_60_MD.encode("utf-8")
                table_yielded = True
            elif ("coupe e sportline 85x" in tr_lower) or ("e sportline 85x" in tr_lower):
                yield ENYAQ_COUPE_E_SPORTLINE_85X_MD.encode("utf-8")
                table_yielded = True
            else:
                yield f"Enyaq için {trim_name.title()} opsiyonel tablosu bulunamadı.\n".encode("utf-8")
        elif model_name == "octavia":
            if "elite" in trim_name:
                yield OCTAVIA_ELITE_MD.encode("utf-8"); table_yielded = True
            elif "premium" in trim_name:
                yield OCTAVIA_PREMIUM_MD.encode("utf-8"); table_yielded = True
            elif "prestige" in trim_name:
                yield OCTAVIA_PRESTIGE_MD.encode("utf-8"); table_yielded = True
            elif "sportline" in trim_name:
                yield OCTAVIA_SPORTLINE_MD.encode("utf-8"); table_yielded = True
            elif "rs" in trim_name:
                yield OCTAVIA_RS_MD.encode("utf-8"); table_yielded = True
            else:
                yield "Octavia için geçerli donanımlar: Elite / Premium / Prestige / Sportline / RS\n"
        elif model_name == "test":
            if "e prestige 60" in trim_name:
                yield TEST_E_PRESTIGE_60_MD.encode("utf-8"); table_yielded = True
            elif "premium" in trim_name:
                yield TEST_PREMIUM_MD.encode("utf-8"); table_yielded = True
            elif "prestige" in trim_name:
                yield TEST_PRESTIGE_MD.encode("utf-8"); table_yielded = True
            elif "sportline" in trim_name:
                yield TEST_SPORTLINE_MD.encode("utf-8"); table_yielded = True
            else:
                yield "Test için geçerli donanımlar: E-prestige 60 / Premium / Prestige / Sportline / RS\n"
        
        elif model_name == "superb":
            if "premium" in trim_name:
                yield SUPERB_PREMIUM_MD.encode("utf-8")
            elif "prestige" in trim_name:
                yield SUPERB_PRESTIGE_MD.encode("utf-8")
            elif ("l&k" in trim_name) or ("crystal" in trim_name):
                yield SUPERB_LK_CRYSTAL_MD.encode("utf-8")
            elif "sportline" in trim_name:
                yield SUPERB_SPORTLINE_PHEV_MD.encode("utf-8")
            else:
                yield "Superb için geçerli donanımlar: Premium / Prestige / L&K Crystal / Sportline PHEV\n"
            table_yielded = True
        # Elroq
        elif model_name == "elroq":
            tr_lower = trim_name.lower()
            if "e prestige 60" in tr_lower:
                yield ELROQ_E_PRESTIGE_60_MD.encode("utf-8")
                table_yielded = True
            else:
                yield f"Elroq için {trim_name.title()} opsiyonel tablosu bulunamadı.\n".encode("utf-8")

        else:
            yield f"'{model_name}' modeli için opsiyonel tablo bulunamadı.\n".encode("utf-8")

        self.logger.info(f"_yield_opsiyonel_table() result => table_yielded={table_yielded}")
        if table_yielded:
            if model_name == "fabia":
                all_trims = ["premium", "monte carlo"]
            elif model_name == "scala":
                all_trims = ["elite", "premium", "monte carlo"]
            elif model_name == "kamiq":
                all_trims = ["elite", "premium", "monte carlo"]
            elif model_name == "karoq":
                all_trims = ["premium", "prestige", "sportline"]
            elif model_name == "kodiaq":
                all_trims = ["premium", "prestige", "sportline", "rs"]
            elif model_name == "enyaq":
                all_trims = [
                    "e prestige 60",
                    "coupe e sportline 60",
                    "coupe e sportline 85x",
                    "e sportline 60",
                    "e sportline 85x"
                ]
            elif model_name == "elroq":
                all_trims = ["e prestige 60"]
            elif model_name == "octavia":
                all_trims = ["elite", "premium", "prestige", "sportline", "rs"]
            elif model_name == "test":
                all_trims = ["e prestige 60", "premium", "prestige", "sportline"]
            elif model_name == "superb":
                all_trims = ["premium", "prestige", "l&k crystal", "sportline phev"]
            else:
                all_trims = []

            normalized_current = trim_name.lower().strip()
            other_trims = [t for t in all_trims if t not in normalized_current]

            if other_trims:
                html_snippet = """
<br><br>
<div style="margin-top:10px;">
  <b>Diğer donanımlarımıza ait opsiyonel donanımları görmek için donanıma tıklamanız yeterli:</b>
  <ul>
"""
                for ot in other_trims:
                    command_text = f"{model_name} {ot} opsiyonel"
                    display_text = ot.title()
                    html_snippet += f"""    <li>
      <a href="#" onclick="sendMessage('{command_text}'); return false;">{display_text}</a>
    </li>
"""
                html_snippet += "  </ul>\n</div>\n"
                yield html_snippet.encode("utf-8")

        self.user_states[user_id]["pending_opsiyonel_model"] = None

    def _yield_trim_options(self, model: str, trim_list: list):
        model_title = model.title()
        msg = f"Hangi donanımı görmek istersiniz?<br><br>"

        for trim in trim_list:
            trim_title = trim.title()
            command_text = f"{model} {trim} opsiyonel"
            link_label = f"{model_title} {trim_title}"
            msg += f"""&bull; <a href="#" onclick="sendMessage('{command_text}');return false;">{link_label}</a><br>"""

        yield msg.encode("utf-8")

    def _yield_multi_enyaq_tables(self):
        time.sleep(1)

        yield b"<b>Enyaq e Prestige 60 - Opsiyonel Tablosu</b><br>"
        yield ENYAQ_E_PRESTIGE_60_MD.encode("utf-8")
        yield b"<hr style='margin:15px 0;'>"

        yield b"<b>Enyaq Coupe e Sportline 60 - Opsiyonel Tablosu</b><br>"
        yield ENYAQ_COUPE_E_SPORTLINE_60_MD.encode("utf-8")
        yield b"<hr style='margin:15px 0;'>"

        yield b"<b>Enyaq Coupe e Sportline 85x - Opsiyonel Tablosu</b><br>"
        yield ENYAQ_COUPE_E_SPORTLINE_85X_MD.encode("utf-8")

    def run(self, debug=True):
        self.app.run(debug=debug)

    def shutdown(self):
        self.stop_worker = True
        self.worker_thread.join(5.0)
        self.logger.info("ChatbotAPI shutdown complete.")