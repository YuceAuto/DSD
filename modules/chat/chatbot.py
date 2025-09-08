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
from collections import Counter
from flask import stream_with_context  # en üste diğer Flask importlarının yanına

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
# -- Fiyat tablosu
from modules.data.fiyat_data import FIYAT_LISTESI_MD

import math
from modules.data.ev_specs import EV_RANGE_KM, FUEL_SPECS   # 1. adımda oluşturduk
import math

import secrets
ASSISTANT_NAMES = {
    "fabia", "scala", "kamiq", "karoq", "kodiaq",
    "octavia", "superb", "elroq", "enyaq"
}
import re
from modules.data.text_norm import normalize_tr_text
def clean_city_name(raw: str) -> str:
    """
    'Fabia İzmir' → 'İzmir'
    'Kodiaq Ankara' → 'Ankara'
    """
    txt = normalize_tr_text(raw)
    for m in ASSISTANT_NAMES:
        txt = re.sub(rf"\b{m}\b", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s{2,}", " ", txt).strip()
    return txt.title()
TWO_LOC_PAT = (
    r"([a-zçğıöşü\s]+?)\s*"                       # konum‑1
    r"(?:ile|ve|,|-|dan|den)?\s+"                 # bağlaçlar
    r"([a-zçğıöşü\s]+?)\s+"                       # konum‑2
    r"(?:arası|arasında)?\s*"                     # opsiyonel "arası"
    r"(?:kaç\s+km|kaç\s+saat|ne\s+kadar\s+sürer|mesafe|sürer)"
)


# Yeni: Kaç şarj sorularını ayrıştır
# utils/parsers.py  (veya mevcut dosyanız neredeyse)
import re

MODELS = r"(?:fabia|scala|kamiq|karoq|kodiaq|octavia|superb|enyaq|elroq)"
FUEL_WORDS = r"(?:depo|yakıt|benzin)"
CHARGE_OR_FUEL = rf"(?:şarj|{FUEL_WORDS})"



_PLACE_ID_CACHE: dict[str, str] = {}




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

def extract_model_trim_pairs(text: str):
    """
    Metinden (model, trim) çiftlerini sırayla çıkarır.
    Model: fabia|scala|kamiq|karoq|kodiaq|octavia|enyaq|elroq|superb
    Trim: bir sonraki model/bağlaç/noktalama gelene kadar olan kelimeler
    """
    MODEL_WORDS = r"(?:fabia|scala|kamiq|karoq|kodiaq|octavia|enyaq|elroq|superb)"
    SEP_WORDS   = r"(?:ve|&|ile|and)"          # bağlaçlar
    WORD        = r"[0-9a-zçğıöşü\.-]+"        # trim tokenları

    t = (text or "").lower()
    model_iter = list(re.finditer(rf"\b({MODEL_WORDS})\b", t, flags=re.IGNORECASE))
    pairs = []

    for i, m in enumerate(model_iter):
        model = m.group(1).lower()
        start = m.end()
        end   = model_iter[i+1].start() if (i + 1) < len(model_iter) else len(t)

        segment = t[start:end]
        # ÖNEMLİ: Kelime-bağlaçların yanı sıra noktalama da ayırıcı
        segment = re.split(rf"(?:\b{SEP_WORDS}\b|[,.;:|\n\r]+)", segment, maxsplit=1)[0]

        trim_tokens = re.findall(WORD, segment, flags=re.IGNORECASE)
        trim = " ".join(trim_tokens).strip()

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
    def _normalize_spec_key_for_dedup(self, key: str) -> str:
        """
        Aynı anlama gelen ama farklı yazılmış teknik başlıkları tek bir
        kanonik biçime çevirir. Bu sayede birleşik tabloda satırlar tekrarlanmaz.
        """
        if not key:
            return key

        t = key

        # 1) Genel biçim sadeleştirme
        t = re.sub(r'\s+', ' ', t).strip()
        t = re.sub(r'\s*/\s*', '/', t)       # " / " -> "/"
        t = re.sub(r'\(\s*', '(', t)         # "( x" -> "(x"
        t = re.sub(r'\s*\)', ')', t)         # "x )" -> "x)"
        t = re.sub(r'0\s*[-–—]\s*100', '0-100', t)  # "0 – 100" -> "0-100"

        # 2) Birimler: tutarlı yazım
        t = re.sub(r'(?i)\b(?:lt|litre)\b', 'l', t)
        t = re.sub(r'(?i)l\s*/\s*100\s*km', 'l/100 km', t)
        t = re.sub(r'(?i)km\s*/\s*(?:h|sa(?:at)?)', 'km/h', t)
        t = re.sub(r'(?i)\bco2\b', 'CO2', t)

        # 3) Türkçe karakter varyantlarını toparla
        t = re.sub(r'(?i)genislik', 'Genişlik', t)
        t = re.sub(r'(?i)yukseklik', 'Yükseklik', t)
        t = re.sub(r'(?i)ivme(?:leme|lenme)?', 'İvme', t)

        # 4) Alias kuralları (ilk eşleşen kural uygulanır)
        rules: list[tuple[str, str]] = [
            # Motor / performans
            (r'(?i)^silindir\s*say[ıi]s[ıi]$',                  'Silindir Sayısı'),
            (r'(?i)^silindir\s*hacmi',                          'Silindir Hacmi (cc)'),
            (r'(?i)^çap\s*/\s*strok',                           'Çap / Strok (mm)'),
            (r'(?i)^maks(?:\.|imum)?\s*g[üu]ç\b.*',             'Maks. güç (kW/PS @ dev/dak)'),
            (r'(?i)^maks(?:\.|imum)?\s*tork\b.*',               'Maks. tork (Nm @ dev/dak)'),
            (r'(?i)^maks(?:\.|imum)?\s*h[ıi]z\b.*',             'Maks. hız (km/h)'),
            (r'(?i)^(?:i̇)?vme.*\(0-100.*',                     '0-100 km/h (sn)'),

            # Yakıt tüketimi (WLTP evreleri)
            (r'(?i)^d[üu]ş[üu]k\s*faz.*',                       'Düşük Faz (l/100 km)'),
            (r'(?i)^orta\s*faz.*',                              'Orta Faz (l/100 km)'),
            (r'(?i)^y[üu]ksek\s*faz.*',                         'Yüksek Faz (l/100 km)'),
            (r'(?i)^ekstra\s*y[üu]ksek\s*faz.*',                'Ekstra Yüksek Faz (l/100 km)'),
            (r'(?i)^birleşik.*(l/100\s*km|l/100km|lt/100\s*km)', 'Birleşik (l/100 km)'),

            # Emisyon
            (r'(?i)^co2.*',                                     'CO2 Emisyonu (g/km)'),

            # Boyutlar / ağırlık / bagaj / lastik
            (r'(?i)^uzunluk\s*/\s*genişlik\s*/\s*yükseklik',    'Uzunluk/Genişlik/Yükseklik (mm)'),
            (r'(?i)^dingil\s*mesafesi',                         'Dingil mesafesi (mm)'),
            (r'(?i)^bagaj\s*hacmi',                             'Bagaj hacmi (dm3)'),
            (r'(?i)^ağ[ıi]rl[ıi]k.*',                           'Ağırlık (Sürücü Dahil) (kg)'),
            (r'(?i)^lastikler?|^lastik\s*ölç[üu]s[üu]',         'Lastikler'),

            # EV (batarya & şarj & menzil)
            (r'(?i)^batarya\s*kapasitesi.*br[üu]t',             'Batarya kapasitesi (brüt kWh)'),
            (r'(?i)^batarya\s*kapasitesi.*net',                 'Batarya kapasitesi (net kWh)'),
            (r'(?i)^(?:elektrikli\s*)?menzil.*wltp.*şehir.*içi','Menzil (WLTP, şehir içi)'),
            (r'(?i)^(?:elektrikli\s*)?menzil.*wltp',            'Menzil (WLTP)'),
            (r'(?i)^(?:ac\s*onboard|dahili\s*ac|ac\s*şarj).*',  'Dahili AC şarj (kW)'),
            (r'(?i)^(?:dc|h[ıi]zl[ıi])\s*şarj\s*g[üu]c[üu].*',  'DC şarj gücü (kW)'),
            (r'(?i)^dc\s*şarj.*(?:10|%10)\s*[-–]\s*80%?.*',     'DC şarj 10-80% (dk)'),
            (r'(?i)^şarj\s*soketi.*',                           'Şarj soketi'),
            (r'(?i)^batarya\s*kimyas[ıi]',                      'Batarya kimyası'),
            (r'(?i)^batarya\s*ısıtma',                          'Batarya ısıtma'),
        ]

        for pat, repl in rules:
            if re.search(pat, t):
                t = repl
                break

        # 5) Son rötuşlar: büyük/küçük harf ve boşluklar
        t = t.strip()
        # İster Title(), ister olduğu gibi bırakın; CO2 gibi kısaltmaları bozmamak için dokunmuyoruz.
        # self.logger.debug("[spec-dedup] %r -> %r", key, t)  # isterseniz açın

        return t

    def _get_teknik_md_for_model(self, model: str) -> str | None:
        """Model için teknik özellik Markdown tablosunu döndürür."""
        return self.TECH_SPEC_TABLES.get((model or "").lower())

    def _clean_spec_name(self, s: str) -> str:
        """Özellik adını temizler (HTML, LaTeX kırpma, fazla boşlukları düzeltme)."""
        s = remove_latex_and_formulas(s or "")
        s = re.sub(r"<[^>]*>", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        s = self._normalize_spec_key_for_dedup(s)
        return s

    def _parse_teknik_md_to_dict(self, md: str) -> tuple[list[str], dict[str, str]]:
        """
        2 sütunlu Markdown teknik tabloyu 'özellik -> değer' sözlüğüne çevirir.
        Dönüş: (özellik_sırası, sözlük)
        """
        order: list[str] = []
        data: dict[str, str] = {}

        if not md:
            return order, data

        lines = [ln.strip() for ln in md.strip().splitlines() if "|" in ln]
        for ln in lines:
            # Ayırıcı satırı atla
            if re.match(r'^\s*\|\s*[-:]+', ln):
                continue

            cells = [c.strip() for c in ln.split("|")]
            # Baş ve sondaki boş hücreleri kırp (| Özellik | Değer | → ['', 'Özellik', 'Değer', ''])
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]

            if len(cells) < 2:
                continue

            key = self._clean_spec_name(cells[0])
            val = cells[1].strip()

            # Başlığa denk gelen satırları atla
            if not key or key.lower() in ("özellik", "ozellik", "feature", "spec", "specification"):
                continue

            if key not in data:
                data[key] = val
                order.append(key)

        return order, data

    def _build_teknik_comparison_table(self, models: list[str], only_keywords: list[str] | None = None) -> str:
        """
        Birden fazla modelin teknik tablolarını yan yana karşılaştırma Markdown'ı üretir.
        - Teknik markdown'ı olmayan modeller de başlıkta yer alır (hücreler '—').
        - Model sayısı çok fazlaysa tabloyu otomatik olarak parçalara böler.
        """
        models = [m.lower() for m in models if m]
        if len(models) < 2:
            return ""

        # 1) Tüm modeller için sözlükleri hazırla (olmayanlar boş sözlük)
        parsed_for: dict[str, dict[str, str]] = {}
        order_for:  dict[str, list[str]] = {}
        for m in models:
            md = self._get_teknik_md_for_model(m) or ""
            if md.strip():
                order, d = self._parse_teknik_md_to_dict(md)
            else:
                order, d = [], {}
            parsed_for[m] = d
            order_for[m]  = order

        # 2) Özellik anahtarlarının birleşik sırası (ilk görülen modele göre)
        all_keys: list[str] = []
        seen = set()
        for m in models:
            for k in order_for[m]:
                if k not in seen:
                    seen.add(k)
                    all_keys.append(k)

        # Hiç anahtar çıkmadıysa yine de boş bir tablo iskeleti dön
        if not all_keys:
            header = ["Özellik"] + [m.title() for m in models]
            skel = (
                "| " + " | ".join(header) + " |\n" +
                "|" + "|".join(["---"] * len(header)) + "|\n" +
                "| — " + " | ".join(["—"] * (len(header) - 1)) + " |"
            )
            return fix_markdown_table(skel)

        # 3) Opsiyonel filtre
        if only_keywords:
            kws = [normalize_tr_text(k).lower() for k in only_keywords]
            def match_any(spec: str) -> bool:
                spec_norm = normalize_tr_text(spec).lower()
                return any(kw in spec_norm for kw in kws)
            filtered = [k for k in all_keys if match_any(k)]
            if filtered:
                all_keys = filtered

        # 4) Çok geniş tabloyu parçalara böl (örn. 6 model/sayfa)
        max_per = int(getattr(self, "MAX_COMPARE_MODELS_PER_TABLE", 6))
        chunks = [models[i:i+max_per] for i in range(0, len(models), max_per)]

        tables: list[str] = []
        for chunk in chunks:
            header = ["Özellik"] + [m.title() for m in chunk]
            lines  = [
                "| " + " | ".join(header) + " |",
                "|" + "|".join(["---"] * len(header)) + "|"
            ]
            for k in all_keys:
                row = [k] + [parsed_for[m].get(k, "—") for m in chunk]
                lines.append("| " + " | ".join(row) + " |")
            tables.append(fix_markdown_table("\n".join(lines)))

        return "\n\n".join(tables)


    def _detect_spec_filter_keywords(self, text: str) -> list[str]:
        """
        Kullanıcı 'sadece ...' / 'yalnızca ...' dediyse, virgülle ayrılmış özellik anahtarlarını çıkar.
        Örn: '... sadece beygir, tork, 0-100' → ['beygir','tork','0-100']
        """
        t = (text or "").lower()
        m = re.search(r"(?:sadece|yaln[ıi]zca)\s*[:\-]?\s*([a-z0-9çğıöşü\s,\/\+\-]+)", t)
        if not m:
            return []
        raw = m.group(1)
        parts = re.split(r"[,\n\/]+|\s+ve\s+|\s+ile\s+", raw)
        parts = [p.strip() for p in parts if p.strip()]
        return parts

    def _is_long_content(self, text: str, *, treat_as_table: bool = False) -> bool:
        if not text:
            return False
        wc = self._count_words(text)
        tok = self._approx_tokens(text)

        if treat_as_table:
            # Markdown satırları
            md_rows = sum(
                1 for ln in text.splitlines()
                if ln.strip().startswith("|") and "|" in ln
            )
            # HTML <tr> satırları
            html_rows = len(re.findall(r"<tr\b", text, flags=re.IGNORECASE))
            rows = max(md_rows, html_rows)

            return (
                wc  >= self.LONG_TABLE_WORDS
                or rows >= self.LONG_TABLE_ROWS
                or tok >= self.LONG_TOKENS
            )

        # Düz metinler için
        return (wc >= self.LONG_DELIVER_WORDS) or (tok >= self.LONG_TOKENS)

    def _count_words(self, text: str) -> int:
        """
        TR-dostu kelime sayacı. Markdown/HTML/LaTeX parazitini olabildiğince temizler.
        """
        if not text:
            return 0
        # LaTeX/HTML gürültüsünü azalt
        s = remove_latex_and_formulas(text)
        s = re.sub(r"<[^>]+>", " ", s)  # HTML etiketleri
        s = normalize_tr_text(s or "")
        # Harf/rakam + Türkçe karakterleri kelime kabul et
        words = re.findall(r"[0-9a-zçğıöşü]+", s, flags=re.IGNORECASE)
        return len(words)

    def _count_models_in_text(self, text: str) -> dict[str, int]:
        """
        Verilen metinde Skoda model adlarının (fabia, scala, kamiq, karoq, kodiaq,
        octavia, superb, elroq, enyaq) kaç kez geçtiğini sayar.
        Normalleştirilmiş token bazlı sayım yapar (Unicode/Türkçe güvenli).
        """
        if not text:
            return {}
        s = normalize_tr_text(text or "").lower()
        # Harf ve rakamları tokenlara ayır (Türkçe karakterler dahil)
        tokens = re.findall(r"[0-9a-zçğıöşü]+", s, flags=re.IGNORECASE)

        MODELS = ["fabia", "scala", "kamiq", "karoq", "kodiaq",
                "octavia", "superb", "elroq", "enyaq"]
        cnt = Counter(t for t in tokens if t in MODELS)

        # Sıfırları at
        return {m: c for m, c in cnt.items() if c > 0}

    def _approx_tokens(self, *chunks: str) -> int:
        # Kabaca: 1 token ≈ 4 karakter (+%10 pay)
        total_chars = sum(len(c or "") for c in chunks)
        return int(total_chars / 4 * 1.10)

    def _deliver_locally(
        self,
        body: str,
        original_user_message: str = "",
        user_id: str | None = None,
        model_hint: str | None = None
    ) -> bytes:
        out_md = self.markdown_processor.transform_text_to_markdown(body or "")
        if '|' in out_md and '\n' in out_md:
            out_md = fix_markdown_table(out_md)
        else:
            out_md = self._coerce_text_to_table_if_possible(out_md)
        resp_bytes = out_md.encode("utf-8")
        if self._should_attach_contact_link(original_user_message):
            resp_bytes = self._with_contact_link_prefixed(resp_bytes, user_id=user_id, model_hint=model_hint)
        if self._should_attach_site_link(original_user_message):
            resp_bytes = self._with_site_link_appended(resp_bytes)
        return resp_bytes

    def _render_table_via_test_assistant(
        self,
        user_id: str,
        table_source_text: str,
        title: str | None = None,
        original_user_message: str = ""
    ) -> bytes:
        """
        Verilen kaynak metinden (Markdown/HTML/KV blok) tablo üretimini TEST asistanına devreder.
        ÇIKTI: Yalnızca Markdown tablo (kod bloğu yok, ekstra yorum yok)
        """
        # TEST asistan tanımlı değilse emniyetli geri dönüş
        # --- NEW: Çok uzun kaynak metni asistana yollama (kelime/satır/token)
        if self._is_long_content(table_source_text, treat_as_table=True):
            self.logger.warning("[TEST RENDER] Long table source; returning locally.")
            return self._deliver_locally(table_source_text, original_user_message, user_id)

        if not self.TEST_ASSISTANT_ID:
            out = table_source_text
            if self._looks_like_kv_block(out):
                out = self._coerce_text_to_table_if_possible(out)
            if '|' in out and '\n' in out:
                out = fix_markdown_table(out)
            resp = out.encode("utf-8")
            if self._should_attach_contact_link(original_user_message):
                resp = self._with_contact_link_prefixed(resp, user_id=user_id)
            if self._should_attach_site_link(original_user_message):
                resp = self._with_site_link_appended(resp)
            return resp

        prev_msg = (self.user_states.get(user_id, {}) or {}).get("prev_user_message") or ""
        ctx_lines = []
        if original_user_message:
            ctx_lines.append(f"- Güncel Soru: {original_user_message}")
        if prev_msg:
            ctx_lines.append(f"- Önceki Soru: {prev_msg}")
        ctx = ("BAĞLAM:\n" + "\n".join(ctx_lines) + "\n") if ctx_lines else ""

        # --- NEW: Zaten tablo / KV ise yerelde dön
        if self._looks_like_markdown_table(table_source_text) or self._looks_like_kv_block(table_source_text):
            out = table_source_text
            if self._looks_like_kv_block(out):
                out = self._coerce_text_to_table_if_possible(out)
            if '|' in out and '\n' in out:
                out = fix_markdown_table(out)
            resp = out.encode("utf-8")
            if self._should_attach_contact_link(original_user_message):
                resp = self._with_contact_link_prefixed(resp, user_id=user_id)
            if self._should_attach_site_link(original_user_message):
                resp = self._with_site_link_appended(resp)
            return resp

        # --- NEW: Çok uzun kaynak metni asistana yollama
        if self._approx_tokens(table_source_text) > 6500:
            self.logger.warning("[TEST RENDER] Source too long; returning locally.")
            return self._deliver_locally(table_source_text, original_user_message, user_id)

        header = (f"Başlık: {title}\n" if title else "")
        content = (
            "Aşağıda tabloya dönüştürülmesi gereken içerik var.\n"
            "GÖREV:\n"
            "- Yalnızca düzgün bir Markdown TABLO üret (ek yorum/ön yazı/son yazı yok).\n"
            "- Kod bloğu (```) KULLANMA.\n"
            "- Eğer içerik 'Özellik: Değer' satırlarıysa 2 sütunlu tabloya çevir (Başlıklar: 'Özellik', 'Değer').\n"
            "- HTML <table> gelirse düzgün bir Markdown tabloya çevir.\n"
            "- Türkçe karakterleri ve sayı biçimlerini koru.\n\n"
            f"{ctx}"
            f"{header}"
            "---TABLO KAYNAĞI BAŞLANGIÇ---\n"
            f"{table_source_text}\n"
            "---TABLO KAYNAĞI BİTİŞ---"
        )

        try:
            out = self._ask_assistant(
                user_id=user_id,
                assistant_id=self.TEST_ASSISTANT_ID,
                content=content,
                timeout=60.0,
                instructions_override=(
                    "Sadece düzgün bir Markdown tablo yaz. Kod bloğu kullanma. "
                    "Veri eksikse hücreyi ‘—’ ile doldur; özür/uyarı ekleme."
                ),
                ephemeral=True   # <-- NEW
            ) or ""

            # Markdown post‑process: hizalama + son çare tabloya çevirme
            out_md = self.markdown_processor.transform_text_to_markdown(out)
            if '|' in out_md and '\n' in out_md:
                out_md = fix_markdown_table(out_md)
            else:
                out_md = self._coerce_text_to_table_if_possible(out_md)

            resp_bytes = out_md.encode("utf-8")
            if self._should_attach_contact_link(original_user_message):
                resp_bytes = self._with_contact_link_prefixed(resp_bytes, user_id=user_id)
            if self._should_attach_site_link(original_user_message):
                resp_bytes = self._with_site_link_appended(resp_bytes)

            return resp_bytes
        except Exception as e:
            self.logger.error(f"[bridge] _render_table_via_test_assistant failed: {e}")
            # Emniyetli geri dönüş
            fallback = table_source_text
            if self._looks_like_kv_block(fallback):
                fallback = self._coerce_text_to_table_if_possible(fallback)
            if '|' in fallback and '\n' in fallback:
                fallback = fix_markdown_table(fallback)
            resp = fallback.encode("utf-8")
            if self._should_attach_contact_link(original_user_message):
                resp = self._with_contact_link_prefixed(resp, user_id=user_id)
            if self._should_attach_site_link(original_user_message):
                resp = self._with_site_link_appended(resp)
            return resp
    
    def _answer_from_scratch_via_test_assistant(self, user_id: str, original_user_message: str) -> bytes:
        """
        Birinci kod 'tablo' sinyali verdiğinde: soruyu baştan 'test' asistanına yönlendir.
        Bu sürüm, güncel soru + önceki soru + önceki cevaptaki model adlarını sayar,
        en sık geçen model(ler)e odaklanır. Eşitlikte listedeki tüm modeller için tablo üretir.
        ÇIKTI hedefi: TABLO.
        """
        # TEST asistanı yoksa emniyetli geri dönüş
        if not self.TEST_ASSISTANT_ID:
            self.logger.warning("TEST_ASSISTANT_ID not configured; answering with current assistant instead.")
            fallback_asst = self.user_states.get(user_id, {}).get("assistant_id")
            if fallback_asst:
                out = self._ask_assistant(
                    user_id=user_id,
                    assistant_id=fallback_asst,
                    content=original_user_message,
                    timeout=60.0
                ) or ""
                out_md = self.markdown_processor.transform_text_to_markdown(out)
                if '|' in out_md and '\n' in out_md:
                    out_md = fix_markdown_table(out_md)
                else:
                    out_md = self._coerce_text_to_table_if_possible(out_md)
                resp_bytes = out_md.encode("utf-8")
                if self._should_attach_contact_link(original_user_message):
                    resp_bytes = self._with_contact_link_prefixed(resp_bytes, user_id=user_id)
                if self._should_attach_site_link(original_user_message):
                    resp_bytes = self._with_site_link_appended(resp_bytes)
                return resp_bytes
            return self._with_site_link_appended("Uygun bir asistan bulunamadı.\n".encode("utf-8"))

        # --- BAĞLAM: önceki SORU + önceki CEVAP
        prev_q = (self.user_states.get(user_id, {}) or {}).get("prev_user_message") or ""
        prev_a = (self.user_states.get(user_id, {}) or {}).get("prev_assistant_answer") or ""

        # --- MODEL SAYIMI: güncel soru + önceki soru + önceki cevap
        cur_counts = self._count_models_in_text(original_user_message)
        primary_models: list[str] = []

        if cur_counts:
            # Sadece güncel mesajı baz al
            maxc = max(cur_counts.values())
            primary_models = sorted([m for m, c in cur_counts.items() if c == maxc])
            # 'last_models' sadece kullanıcının bu turda yazdıklarıyla güncellensin
            self.user_states[user_id]["last_models"] = set(cur_counts.keys())
        else:
            # Güncel mesajda model yoksa: düşük ağırlıklı geri düşüşler
            prev_q_models = set(self._count_models_in_text(prev_q).keys()) if prev_q else set()
            prev_a_models = set(self._count_models_in_text(prev_a).keys()) if prev_a else set()
            state_models  = set(self.user_states.get(user_id, {}).get("last_models", set()))
            asst_model    = self.ASSISTANT_NAME_MAP.get(self.user_states.get(user_id, {}).get("assistant_id", ""), "")

            counts = Counter()
            # Önceki soru ve state biraz daha kuvvetli
            for m in prev_q_models: counts[m] += 2
            for m in state_models:  counts[m] += 2
            # Önceki cevap sadece presence ve düşük ağırlık
            for m in prev_a_models: counts[m] += 1
            if asst_model: counts[asst_model] += 1

            if counts:
                top = max(counts.values())
                primary_models = sorted([m for m, c in counts.items() if c == top])
        # --- Model odaklı yönlendirme metni
        model_guide = ""
        if primary_models:
            if len(primary_models) == 1:
                model_guide = (
                    f"MODEL ODAK: {primary_models[0].title()} odaklı cevap ver. "
                    "Tabloyu yalnızca bu model için üret.\n"
                )
            else:
                joined = ", ".join(m.title() for m in primary_models)
                model_guide = (
                    "MODEL ODAK: Aşağıdaki modeller eşit sıklıkta tespit edildi: "
                    f"{joined}. Tablo tek olmalı; ilk sütun 'Model' olsun ve "
                    "yalnızca bu modelleri kapsasın (her model için bir satır).\n"
                )

        # --- Önceki cevabı çok uzunsa kırp (token güvenliği)
        prev_a_trim = prev_a[:1200] if prev_a else ""

        # Güncel mesajda model varsa önceki cevabı bağlama KATMAYALIM
        include_prev_a = not bool(cur_counts)

        instruction = (
            
            "BAĞLAM:\n"
            f"- Güncel Soru: {original_user_message}\n"
            + (f"- Önceki Soru: {prev_q}\n" if (prev_q and not cur_counts) else "")
            + (f"- Önceki Yanıt: {prev_a_trim}\n" if (include_prev_a and prev_a_trim) else "")
            + "\n"
            "ÇIKTI: SADECE düzgün bir Markdown TABLO.\n"
        )

        out = self._ask_assistant(
            user_id=user_id,
            assistant_id=self.TEST_ASSISTANT_ID,
            content=instruction,
            timeout=60.0,
            instructions_override=(
                "Sadece düzgün bir Markdown tablo yaz; kod bloğu yok; Türkçe; "
                "veri yetersizse ‘—’; özür/ret metni yazma."
            ),
            ephemeral=True   # her çağrıda temiz thread
        ) or ""

        # Güvenli post‑process
        out_md = self.markdown_processor.transform_text_to_markdown(out)
        if '|' in out_md and '\n' in out_md:
            out_md = fix_markdown_table(out_md)
        else:
            out_md = self._coerce_text_to_table_if_possible(out_md)

        resp_bytes = out_md.encode("utf-8")
        if self._should_attach_contact_link(original_user_message):
            resp_bytes = self._with_contact_link_prefixed(resp_bytes, user_id=user_id)
        if self._should_attach_site_link(original_user_message):
            resp_bytes = self._with_site_link_appended(resp_bytes)
        return resp_bytes




    def _coerce_text_to_table_if_possible(self, text: str) -> str:
        """
        Düz metni anlamlı bir tabloya çevirmeye çalışır.
        - 'Özellik: Değer' satırları ≥3 ise 2 sütunlu tablo yapar.
        - Madde işaretli (•, -, *) liste ≥3 ise tek sütunlu tablo yapar.
        Dönüş: Mümkünse tablo; değilse orijinal metin.
        """
        if not text:
            return text

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return text

        # 1) Özellik: Değer
        kv = []
        kv_regex = re.compile(r'^\s*[-*•]?\s*([^:|]+?)\s*[:：]\s*(.+)$')
        for ln in lines:
            m = kv_regex.match(ln)
            if m:
                k = re.sub(r'\s+', ' ', m.group(1)).strip()
                v = re.sub(r'\s+', ' ', m.group(2)).strip()
                if k and v:
                    kv.append((k, v))
        if len(kv) >= 3:
            table = ["| Özellik | Değer |", "|---|---|"]
            for k, v in kv:
                table.append(f"| {k} | {v} |")
            return "\n".join(table)

        # 2) Madde listesi (tek sütun)
        bullets = []
        for ln in lines:
            if re.match(r'^\s*[-*•]\s+', ln):
                bullets.append(re.sub(r'^\s*[-*•]\s+', '', ln))
        if len(bullets) >= 3 and len(bullets) >= len(lines) * 0.6:
            table = ["| Liste |", "|---|"]
            table += [f"| {item} |" for item in bullets]
            return "\n".join(table)

        return text

    def _proxy_first_service_answer(self, user_message: str, user_id: str) -> dict:
        """
        Birinci servis (Birinci Kod) /api/raw_answer endpoint’ine proxy çağrı yapar.
        Tablo/görsel dışı metin yanıtı istediğimizde kullanılır.
        """
        try:
            payload = {"question": user_message, "user_id": user_id}
            headers = {
                "Content-Type": "application/json",
                "X-Bridge-Key": self.FIRST_SHARED_SECRET or ""
            }
            r = requests.post(self.FIRST_SERVICE_URL, json=payload, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json() if r.content else {}
            # Beklenen alanlar: answer, conversation_id, assistant_id
            return data or {}
        except Exception as e:
            self.logger.error(f"[bridge] First service error: {e}")
            return {"answer": "", "error": str(e)}

    def _looks_like_table_or_image(self, text: str) -> bool:
        """Birinci servisten dönen içeriğin tablo/görsel içerip içermediğini kaba olarak anlar."""
        if not text:
            return False
        t = text.lower()
        # basit tablo ipuçları (markdown header ve sütun çizgisi)
        if ("|\n" in text or "\n|" in text) and re.search(r"\|\s*[-:]+\s*\|", text):
            return True
        # tipik görsel ipuçları
        if "![ " in t or "![" in t or "<img" in t or "/static/images/" in t:
            return True
        return False

    def _strip_tables_and_images(self, text: str) -> str:
        """
        BİRİNCİ SERVİS'TEN GELEN İÇERİKTEKİ YALNIZCA GÖRSELLERİ ayıklar.
        Markdown tabloları KORUR.
        """
        if not text:
            return text

        lines = text.splitlines()
        filtered = []
        for ln in lines:
            ln_low = ln.lower()

            # Markdown image: ![alt](url)  (satırı komple at)
            if re.search(r'!\[[^\]]*\]\([^)]+\)', ln):
                continue

            # HTML <img ...>  (satırı komple at)
            if "<img" in ln_low:
                continue

            # Projeye özgü statik görsel yolları
            if "/static/images/" in ln_low:
                continue

            filtered.append(ln)

        out = "\n".join(filtered).strip()
        return out if out else " "
    def _looks_like_markdown_table(self, text: str) -> bool:
        """Basit bir Markdown tablo tespiti: başlık satırı + ayırıcı satır + dikey çizgiler."""
        if not text or '|' not in text:
            return False
        has_pipe_lines = re.search(r'^\s*\|.*\|\s*$', text, flags=re.MULTILINE)
        has_header_sep = re.search(r'\|\s*[-:]{3,}\s*(\|\s*[-:]{3,}\s*)+\|', text)
        return bool(has_pipe_lines and has_header_sep)

    def _looks_like_kv_block(self, text: str) -> bool:
        """
        'Özellik: Değer' biçiminde en az 3 satır varsa tabloya çevrilebilir kabul et.
        - Madde işaretli satırları da destekler (•, -, *)
        """
        if not text:
            return False
        kv_lines = re.findall(r'^\s*[-*•]?\s*[^:|]{2,}\s*[:：]\s*.+$', text, flags=re.MULTILINE)
        return len(kv_lines) >= 3

    def _looks_like_html_table(self, text: str) -> bool:
        """HTML tablo tespiti."""
        if not text:
            return False
        t = text.lower()
        return ('<table' in t) and ('</table>' in t)

    def _looks_like_table_intent(self, text: str) -> bool:
        """Markdown tablo, HTML tablo veya KV blok → tablo niyeti."""
        return (
            self._looks_like_markdown_table(text)
            or self._looks_like_html_table(text)
            or self._looks_like_kv_block(text)
        )

    def _deliver_via_test_assistant(self, user_id: str, answer_text: str, original_user_message: str = "") -> bytes:
    # TEST asistanı yoksa zaten yerelde dön…
        if not self.TEST_ASSISTANT_ID:
            self.logger.warning("TEST_ASSISTANT_ID not configured; returning raw bridged answer.")
            resp_bytes = answer_text.encode("utf-8")
            if self._should_attach_contact_link(original_user_message):
                resp_bytes = self._with_contact_link_prefixed(resp_bytes, user_id=user_id)
            if self._should_attach_site_link(original_user_message):
                resp_bytes = self._with_site_link_appended(resp_bytes)
            return resp_bytes

        # --- NEW: uzun içeriklerde doğrudan yerelde teslim ---
        if self._is_long_content(answer_text):
            self.logger.info("[TEST DELIVER] Skipping TEST assistant (long content).")
            return self._deliver_locally(
                body=answer_text,
                original_user_message=original_user_message,
                user_id=user_id
            )

        # (devamı aynı)
        content = (
            "Aşağıdaki metin son kullanıcı cevabıdır. Metni olduğu gibi, "
            "Markdown biçimini koruyarak ve ek yorum katmadan İLET.\n\n"
            f"{answer_text}"
        )
        try:
            out = self._ask_assistant(
                user_id=user_id,
                assistant_id=self.TEST_ASSISTANT_ID,
                content=content,
                timeout=60.0,
                instructions_override="Sadece ilet; açıklama ekleme; biçimi koru.",
                ephemeral=True
            )
            out_md = self.markdown_processor.transform_text_to_markdown(out or "")
            if '|' in out_md and '\n' in out_md:
                out_md = fix_markdown_table(out_md)
            else:
                out_md = self._coerce_text_to_table_if_possible(out_md)

            resp_bytes = out_md.encode("utf-8")
            if self._should_attach_contact_link(original_user_message):
                resp_bytes = self._with_contact_link_prefixed(resp_bytes, user_id=user_id)
            if self._should_attach_site_link(original_user_message):
                resp_bytes = self._with_site_link_appended(resp_bytes)
            return resp_bytes
        except Exception as e:
            self.logger.error(f"[bridge] deliver via test assistant failed: {e}")
            resp_bytes = answer_text.encode("utf-8")
            if self._should_attach_contact_link(original_user_message):
                resp_bytes = self._with_contact_link_prefixed(resp_bytes, user_id=user_id)
            if self._should_attach_site_link(original_user_message):
                resp_bytes = self._with_site_link_appended(resp_bytes)
            return resp_bytes

    def _feedback_marker(self, conversation_id: int) -> bytes:
        # görünmez veri taşıyıcı
        html = f'<span class="conv-marker" data-conv-id="{conversation_id}" style="display:none"></span>'
        return html.encode("utf-8")
    
    

    def _should_attach_contact_link(self, message: str) -> bool:
        """Test sürüş / satış formunu yalnızca uygun niyetlerde ekle."""
        if not message:
            return False

        # Zaten var olan fiyat niyeti belirleyicinizi kullanın
        if self._is_price_intent(message):
            return True

        msg_norm = normalize_tr_text(message).lower()
        raw_keywords = [
            "test sürüşü", "testsürüş", "deneme sürüş", "randevu",
            "satın al", "satinal", "teklif", "kredi", "finansman",
            "leasing", "taksit", "kampanya", "stok", "teslimat", "bayi"
        ]
        # diakritik güvenli karşılaştırma
        kw = [normalize_tr_text(k).lower() for k in raw_keywords]
        msg_compact = re.sub(r"\s+", "", msg_norm)
        return any(k in msg_norm or k.replace(" ", "") in msg_compact for k in kw)


    def _is_test_drive_intent(self, message: str) -> bool:
        """'test sürüşü' / 'testsürüş' / 'deneme sürüş' gibi niyetleri diakritik güvenli yakalar."""
        if not message:
            return False
        msg_norm = normalize_tr_text(message).lower()
        cmp_msg = re.sub(r"\s+", "", msg_norm)  # boşluksuz varyantı da tara
        candidates = ["test sürüş", "testsürüş", "deneme sürüş"]
        candidates = [normalize_tr_text(c).lower() for c in candidates]
        return any(
            c in msg_norm or c.replace(" ", "") in cmp_msg
            for c in candidates
        )

    def _purge_kac_entries(self) -> int:
        removed = 0
        for uid in list(self.fuzzy_cache.keys()):
            for aid in list(self.fuzzy_cache[uid].keys()):
                lst = self.fuzzy_cache[uid][aid]
                new_lst = [it for it in lst if not self._has_kac_word(it.get("question",""))]
                removed += (len(lst) - len(new_lst))
                self.fuzzy_cache[uid][aid] = new_lst
        self.logger.info(f"[CACHE] Purge: 'kaç' içeren {removed} kayıt silindi.")
        return removed
    def _has_kac_word(self, text: str) -> bool:
        """
        'kaç' ailesini diakritik güvenli yakalar: 'kaç', 'kaça', 'kaç km', 'kac', 'kaca', 'kaçıncı' vb.
        Yalnızca kelime başında eşleşir (yakacağım gibi iç gövde eşleşmelerini dışlar).
        """
        if not text:
            return False

        t_raw = (text or "").lower()
        # ham metinde dene (ç harfiyle)
        if re.search(r"(?<!\w)ka[çc]\w*", t_raw):
            return True

        # normalize edilmiş metinde tekrar dene (ç -> c vb.)
        t_norm = normalize_tr_text(text).lower()
        if re.search(r"(?<!\w)kac\w*", t_norm):
            return True

        return False

    def _yield_fiyat_listesi(self, user_message: str, user_id: str | None = None):
        # 0) Fiyat sorularında test sürüş / satış formu uygundur (tekrarları marker ile engeller)
        if user_id is not None:
            yield self._contact_link_html(user_id=user_id).encode("utf-8")

        """
        'fiyat' geçen mesajlarda fiyat tablosunu döndürür.
        Model belirtilmişse filtreler; Octavia/Superb için 'combi',
        Enyaq için 'coupe/coupé/kupe/kupé' anahtarlarını dikkate alır.
        """
        lower_msg = user_message.lower()

        # 1) Hangi modeller istenmiş?
        models = self._extract_models(user_message)
        want_combi = "combi" in lower_msg
        want_coupe = any(k in lower_msg for k in ["coupe", "coupé", "kupe", "kupé"])

        # 2) Model -> tabloda arama etiketleri
        tags = set()
        if "fabia" in models:   tags.add("FABIA")
        if "scala" in models:   tags.add("SCALA")
        if "kamiq" in models:   tags.add("KAMIQ")
        if "karoq" in models:   tags.add("KAROQ")
        if "kodiaq" in models:  tags.add("KODIAQ")
        if "elroq" in models:   tags.add("ELROQ")
        if "octavia" in models:
            if want_combi:
                tags.add("OCTAVIA COMBI")
            else:
                tags.update({"OCTAVIA", "OCTAVIA COMBI"})
        if "superb" in models:
            if want_combi:
                tags.add("SUPERB COMBI")
            else:
                tags.update({"SUPERB", "SUPERB COMBI"})
        if "enyaq" in models:
            if want_coupe:
                tags.update({"ENYAQ COUP", "ENYAQ COUPÉ", "ENYAQ COUPE"})
            else:
                tags.update({"ENYAQ", "ENYAQ COUP", "ENYAQ COUPÉ", "ENYAQ COUPE"})

        # 3) Tabloyu (gerekirse) filtrele
        md = FIYAT_LISTESI_MD
        if tags:
            lines = FIYAT_LISTESI_MD.strip().splitlines()
            if len(lines) >= 2:
                header, sep = lines[0], lines[1]
                body = lines[2:]
                filtered = []
                for row in body:
                    parts = row.split("|")
                    if len(parts) > 2:
                        first_cell = parts[1].strip().upper()
                        if any(tag in first_cell for tag in tags):
                            filtered.append(row)
                if filtered:
                    md = "\n".join([header, sep] + filtered)

        # 4) Markdown hizasını düzelt
        md_fixed = fix_markdown_table(md)

        # 5) Başlık (UTF‑8) + tablo öncesi boş satır
        yield "<b>Güncel Fiyat Listesi</b><br><br>".encode("utf-8")
        yield ("\n" + md_fixed + "\n\n").encode("utf-8")  # ← tabloyu kapatmak için boş satır ŞART

        # 6) Filtreli çıktıysa 'Tüm fiyatlar' linki (tablodan ayrı paragraf)
        if tags:
            link_html = (
                "<br>• <a href=\"#\" onclick=\"sendMessage('fiyat');return false;\">"
                "Tüm fiyatları göster</a><br>"
            )
            yield link_html.encode("utf-8")
    
    def _fuzzy_contains(self, text: str, phrase: str, threshold: float | None = None) -> bool:
        """
        'text' içinde 'phrase' yaklaşık olarak var mı?
        - Boşlukları normalize eder
        - Alt dizi pencerelerinde difflib oranı hesaplar
        """
        t = normalize_tr_text(text or "").lower()
        p = normalize_tr_text(phrase or "").lower()

        # hızlı kazanımlar
        if p in t:
            return True

        # boşlukları kaldırıp karakter bazında karşılaştır
        t_comp = re.sub(r"\s+", "", t)
        p_comp = re.sub(r"\s+", "", p)
        if p_comp in t_comp:
            return True

        import difflib
        thr = threshold if threshold is not None else getattr(self, "PRICE_INTENT_FUZZY_THRESHOLD", 0.80)
        L = len(p_comp)
        if L == 0:
            return False

        # pencere uzunluğunu ±2 karakter toleransla tara
        minL = max(1, L - 2)
        maxL = L + 2
        n = len(t_comp)
        for win_len in range(minL, maxL + 1):
            for i in range(0, max(0, n - win_len) + 1):
                chunk = t_comp[i:i + win_len]
                if difflib.SequenceMatcher(None, chunk, p_comp).ratio() >= thr:
                    return True
        return False


    def _is_price_intent(self, text: str, threshold: float | None = None) -> bool:
        """
        Fiyat niyeti:
        - 'fiyat' kökü ve türevleri, 'liste fiyat', 'anahtar teslim'
        - 'kaça' (diakritikli/diakr.) veya 'kaç para'
        - 'ne kadar' (ancak bariz teknik/menzil/yakıt bağlamları yoksa)
        Not: Sadece 'kaç' tek başına fiyat değildir.
        """
        t_raw = (text or "").lower()
        t_norm = normalize_tr_text(text or "").lower()
        thr = threshold if threshold is not None else getattr(self, "PRICE_INTENT_FUZZY_THRESHOLD", 0.80)

        # 0) Açık fiyat kelimeleri
        if re.search(r"\b(fiyat|liste\s*fiyat|anahtar\s*teslim(?:i)?)\b", t_norm):
            return True

        # 1) Para birimi işaretleri (rakam + TL/₺)
        if re.search(r"(?:\b\d{1,3}(?:\.\d{3})*(?:,\d+)?|\b\d+(?:,\d+)?)\s*(tl|₺)\b", t_norm):
            return True

        # 2) Kaça / kaç para  → sadece SINIRLI ve KESİN eşleşme (fuzzy yok!)
        if re.search(r"\bkaça\b", t_raw) or re.search(r"\bkaca\b", t_norm):
            return True
        if re.search(r"\bkaç\s+para\b", t_raw) or re.search(r"\bkac\s+para\b", t_norm):
            return True

        # 3) 'ne kadar' → fiyat say; fakat teknik/menzil/yakıt gibi bağlamlar varsa sayma
        if re.search(r"\bne\s+kadar\b", t_raw):
            # negatif bağlamlar
            if re.search(r"\b(yakar|yakit|yakıt|sarj|şarj|menzil|range|km|kilometre|bagaj|hiz|hız|hizlanma|hızlanma|0[-–]100|beygir|hp|ps|tork)\b", t_norm):
                # ancak yanında açık fiyat kelimesi varsa yine fiyat say
                if re.search(r"\b(fiyat|tl|₺|lira|ücret|bedel)\b", t_norm):
                    return True
                return False
            return True  # düz 'ne kadar' → fiyat

        # 4) Yazım hatalı 'fiyat' yakala (fiayt/fıyat/fyat...)
        tokens = re.findall(r"[a-zçğıöşü]+", t_norm)
        import difflib
        for tok in tokens:
            if tok == "fiat":  # marka ile karışmasın
                continue
            if tok.startswith("fiyat"):
                return True
            if len(tok) >= 4 and difflib.SequenceMatcher(None, tok[:5], "fiyat").ratio() >= thr:
                return True

        # 5) ÖNEMLİ: 'kaç' tek başına (veya 'kac') asla fiyat değildir
        if re.search(r"(?<!\w)ka[çc]\b", t_raw) or re.search(r"(?<!\w)kac\b", t_norm):
            return False

        return False


    def _resolve_display_model(self, user_id: str, model_hint: str | None = None) -> str:
        if model_hint:
            return model_hint.title()
        last_models = self.user_states.get(user_id, {}).get("last_models", set())
        if last_models and len(last_models) == 1:
            return next(iter(last_models)).title()
        asst_id = self.user_states.get(user_id, {}).get("assistant_id")
        if asst_id:
            mapped = self.ASSISTANT_NAME_MAP.get(asst_id, "")
            if mapped:
                return mapped.title()
        return "Skoda"


    def _contact_link_html(self, user_id: str | None = None, model_hint: str | None = None) -> str:
        model_display = self._resolve_display_model(user_id, model_hint)
        return (
            '<!-- SKODA_CONTACT_LINK -->'
            '<p style="margin:8px 0 12px;">'
            f'Skoda&rsquo;yı en iyi deneyerek hissedersiniz. '
            'Test sürüşü randevusu: '
            '<a href="https://www.skoda.com.tr/satis-iletisim-formu" target="_blank" rel="noopener">'
            'Satış &amp; İletişim Formu</a>.'
            '</p>'
        )

    def _site_link_html(self) -> str:
        return (
            '<!-- SKODA_SITE_LINK -->'
            '<p style="margin:8px 0 12px;">'
            'Daha fazla bilgi için resmi web sitemizi ziyaret edebilirsiniz: '
            '<a href="https://www.skoda.com.tr/" target="_blank" rel="noopener">skoda.com.tr</a>.'
            '</p>'
        )

    def _with_site_link_appended(self, body) -> bytes:
        body_bytes = body if isinstance(body, (bytes, bytearray)) else str(body).encode("utf-8")
        marker = b"<!-- SKODA_SITE_LINK -->"
        if marker in body_bytes:
            return body_bytes
        return body_bytes + b"\n" + self._site_link_html().encode("utf-8")
    def _should_attach_site_link(self, message: str) -> bool:
        """Kullanıcı 'daha fazla/ayrıntı' isterse site linkini ekle."""
        if not message:
            return False
        m = normalize_tr_text(message).lower()
        more_kw = [
            "daha fazla", "daha fazlasi", "daha cok", "daha çok",
            "detay", "detayli", "detaylı", "ayrinti", "ayrıntı",
            "devam", "continue", "more", "tell me more",
            "site", "web", "resmi site", "skoda sitesi", "skoda.com.tr"
        ]
        return any(k in m for k in more_kw)


    def _with_contact_link_prefixed(self, body, user_id: str | None = None, model_hint: str | None = None) -> bytes:
        body_bytes = body if isinstance(body, (bytes, bytearray)) else str(body).encode("utf-8")
        marker = b"<!-- SKODA_CONTACT_LINK -->"
        if marker in body_bytes:
            return body_bytes
        return self._contact_link_html(user_id=user_id, model_hint=model_hint).encode("utf-8") + body_bytes
    def __init__(self, logger=None, static_folder='static', template_folder='templates'):
        self.app = Flask(
            __name__,
            static_folder=os.path.join(os.getcwd(), static_folder),
            template_folder=os.path.join(os.getcwd(), template_folder),
            
        )
        self.MAX_COMPARE_MODELS_PER_TABLE = int(os.getenv("MAX_COMPARE_MODELS_PER_TABLE", "6"))

        # __init__ içinde (diğer os.getenv okumalarının yanına)
        self.LONG_DELIVER_WORDS = int(os.getenv("LONG_DELIVER_WORDS", "30"))   # metin için varsayılan: 30 kelime
        self.LONG_TABLE_WORDS   = int(os.getenv("LONG_TABLE_WORDS", "800"))    # tablo/kaynak için kelime eşiği
        self.LONG_TABLE_ROWS    = int(os.getenv("LONG_TABLE_ROWS", "60"))      # tablo satır eşiği
        self.LONG_TOKENS        = int(os.getenv("LONG_TOKENS", "6500"))        # güvenlik tavanı (yaklaşık token)

        self.FIRST_SERVICE_URL   = os.getenv("FIRST_SERVICE_URL", "http://127.0.0.1:5000/api/raw_answer")
        self.FIRST_SHARED_SECRET = os.getenv("FIRST_SHARED_SECRET", "")
        # "test" asistan ID'si: .env yoksa Config'ten 'test' map'ini dene
        self.TEST_ASSISTANT_ID   = os.getenv("TEST_ASSISTANT_ID") or self._assistant_id_from_model_name("test")

        self.PRICE_INTENT_FUZZY_THRESHOLD = float(os.getenv("PRICE_INTENT_FUZZY_THRESHOLD", "0.80"))
        self.MODEL_FUZZY_THRESHOLD = float(os.getenv("MODEL_FUZZY_THRESHOLD", "0.80"))
        self.IMAGE_INTENT_LIFETIME = int(os.getenv("IMAGE_INTENT_LIFETIME", "60"))
        self.MODEL_CANONICALS = [
            "fabia", "scala", "kamiq", "karoq", "kodiaq",
            "octavia", "superb", "enyaq", "elroq"
        ]
        CORS(self.app)
        self.app.secret_key = secrets.token_hex(16)
        # __init__ içinde (mevcut TEKNIK_MD importlarının sonrasında)
        self.TECH_SPEC_TABLES = {
            "fabia":   FABIA_TEKNIK_MD,
            "scala":   SCALA_TEKNIK_MD,
            "kamiq":   KAMIQ_TEKNIK_MD,
            "karoq":   KAROQ_TEKNIK_MD,
            "kodiaq":  KODIAQ_TEKNIK_MD,
            "octavia": OCTAVIA_TEKNIK_MD,
            "superb":  SUPERB_TEKNIK_MD,
            "enyaq":   ENYAQ_TEKNIK_MD,
            "elroq":   ELROQ_TEKNIK_MD,
        }

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
        self._purge_kac_entries()
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
        @self.app.route("/idle_prompts", methods=["GET"])
        def idle_prompts():
            user_id = request.args.get("user_id", "guest")
            try:
                html = self._idle_prompts_html(user_id)
                return jsonify({"html": html})
            except Exception as e:
                return jsonify({"html": f"<div>Örnek talepler yüklenemedi: {str(e)}</div>"}), 200
        @self.app.route("/", methods=["GET"])
        def home():
            return render_template("index.html")

        @self.app.route("/ask/<string:username>", methods=["POST"])
        def ask(username):
            return self._ask(username)
        @self.app.route("/ask", methods=["POST"])
        def ask_plain():
            # Frontend zaten body'de user_id gönderiyor, yine de bir "guest" adı geçelim
            return self._ask(username="guest")


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
        step0 = self._correct_model_typos(user_message)   # ← önce model
        step1 = self._correct_image_keywords(step0)
        final_corrected = self._correct_trim_typos(step1)
        return final_corrected
    def _set_pending_image(self, user_id: str):
        self.user_states.setdefault(user_id, {})["pending_image_ts"] = time.time()

    def _is_pending_image(self, user_id: str) -> bool:
        ts = self.user_states.get(user_id, {}).get("pending_image_ts")
        return bool(ts and (time.time() - ts <= self.IMAGE_INTENT_LIFETIME))

    def _clear_pending_image(self, user_id: str):
        if user_id in self.user_states:
            self.user_states[user_id]["pending_image_ts"] = None


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

    

    def _apply_case_like(self, src: str, dst: str) -> str:
        """Kaynağın biçemine benzer biçimde hedefi döndür (BÜYÜK / Başlık / küçük)."""
        if src.isupper():
            return dst.upper()
        if src.istitle():
            return dst.title()
        return dst

    def _correct_model_typos(self, user_message: str) -> str:
        """
        'fabi' → 'fabia', 'karok' → 'karoq' vb.
        Kelime bazında fuzzy eşleştirip yalnızca model adlarını düzeltir.
        """
        canon = ["fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"]

        def repl(m):
            token = m.group(0)
            norm = normalize_tr_text(token).lower()
            best = self.utils.fuzzy_find(norm, canon, threshold=self.MODEL_FUZZY_THRESHOLD)
            if best:
                return self._apply_case_like(token, best)
            return token

        # Türkçe karakterler dahil kelime yakala
        return re.sub(r"\b[0-9A-Za-zçğıöşüÇĞİÖŞÜ]+\b", repl, user_message)


    def _search_in_assistant_cache(self, user_id, assistant_id, new_question, threshold):
        if self._has_kac_word(new_question):
            return None, None
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
        if self._has_kac_word(new_question):
            self.logger.info("[CACHE] Bypass: 'kaç' tespit edildi -> _find_fuzzy_cached_answer kapatıldı.")
            return None

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
        """
        Metinden Skoda model adlarını çıkarır (yazım hatalarıyla birlikte).

        Çalışma biçimi:
        1) normalize_tr_text ile küçük harfe indirip doğrudan içerme kontrolü
        2) Türkçe dostu tokenizasyon ve token başına fuzzy eşleşme
            (örn. 'fabi' -> 'fabia', 'karok' -> 'karoq', 'kodıak' -> 'kodiaq')

        Dönüş: {'fabia', 'karoq'} gibi normalize (küçük harf) model adları kümesi.
        """
        if not text:
            return set()

        s = normalize_tr_text(text).lower()

        CANON = (
            "fabia", "scala", "kamiq", "karoq", "kodiaq",
            "octavia", "superb", "enyaq", "elroq", "test"
        )

        # 1) Hızlı yol: doğrudan metin içinde geçenler
        found = {m for m in CANON if m in s}

        # 2) Fuzzy: yazım hataları için kelime bazlı tarama
        #    (Türkçe karakterleri koruyan bir regex ile tokenizasyon)
        tokens = re.findall(r"[0-9a-zçğıöşü]+", s, flags=re.IGNORECASE)

        # Yanlış pozitifleri azaltmak için birkaç basit filtre
        SKIP_TOKENS = {"fiat"}                        # başka marka
        SKIP_PREFIXES = ("fiyat",)                    # 'fiyat' ~ 'fabia' karışmasın
        th = getattr(self, "MODEL_FUZZY_THRESHOLD", 0.80)

        for tok in tokens:
            if len(tok) < 3:
                continue
            if tok in SKIP_TOKENS:
                continue
            if any(tok.startswith(pfx) for pfx in SKIP_PREFIXES):
                continue

            best = self.utils.fuzzy_find(tok, CANON, threshold=th)
            if best:
                found.add(best)

        return found
    
        

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
            data = request.get_json(silent=True) or request.form or {}
            if not isinstance(data, dict):
                return jsonify({"error":"Invalid payload; send JSON or form-encoded."}), 400
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
        lower_corrected = corrected_message.lower().strip()
        user_models_in_msg = self._extract_models(corrected_message)
        price_intent = self._is_price_intent(corrected_message)
        if user_id not in self.user_states:
            self.user_states[user_id] = {}
            self.user_states[user_id]["threads"] = {}
        # --- NEW: Bu oturumda önceki kullanıcı sorusunu bağlam olarak kullanacağız
        prev_q = self.user_states.get(user_id, {}).get("last_user_message")
        self.user_states[user_id]["prev_user_message"] = prev_q
        prev_ans = (self.user_states.get(user_id, {}) or {}).get("last_assistant_answer")
        self.user_states[user_id]["prev_assistant_answer"] = prev_ans

        last_models = self.user_states[user_id].get("last_models", set())
        if (not user_models_in_msg) and last_models and (not price_intent):
            joined_models = " ve ".join(last_models)
            corrected_message = f"{joined_models} {corrected_message}".strip()
            user_models_in_msg = self._extract_models(corrected_message)
            lower_corrected = corrected_message.lower().strip()
        if (not user_models_in_msg) and last_models and ("fiyat" not in lower_corrected):
            joined_models = " ve ".join(last_models)
            corrected_message = f"{joined_models} {corrected_message}".strip()
            user_models_in_msg = self._extract_models(corrected_message)
            lower_corrected = corrected_message.lower().strip()
        if user_models_in_msg:
            self.user_states[user_id]["last_models"] = user_models_in_msg

        word_count = len(corrected_message.strip().split())
        local_threshold = 1.0 if word_count < 5 else 0.9

        lower_corrected = corrected_message.lower().strip()
        is_image_req = self.utils.is_image_request(corrected_message)
        skip_cache_for_price_all = ("fiyat" in lower_corrected and not user_models_in_msg)
        user_trims_in_msg = extract_trims(lower_corrected)
        skip_cache_for_price_all = (price_intent and not user_models_in_msg)
        skip_cache_for_kac = self._has_kac_word(corrected_message)
        old_assistant_id = self.user_states[user_id].get("assistant_id")
        new_assistant_id = None
        if is_non_sentence_short_reply(corrected_message):
            self.logger.info("Kısa/cümle olmayan cevap: cache devre dışı.")
            cached_answer = None
        else:
            # Fuzzy Cache kontrol (Sadece görsel isteği değilse)
            cached_answer = None
            if not is_image_req and not skip_cache_for_price_all and not skip_cache_for_kac:
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
                        ans_bytes = cached_answer
                        if self._should_attach_site_link(corrected_message):
                            ans_bytes = self._with_site_link_appended(ans_bytes)

                        return self.app.response_class(ans_bytes, mimetype="text/plain")

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
                msg = self._with_site_link_appended("Uygun bir asistan bulunamadı.\n")
                return self.app.response_class(msg, mimetype="text/plain")


        self.user_states[user_id]["assistant_id"] = new_assistant_id

        

        # Fuzzy Cache kontrol (Sadece görsel isteği değilse)
        cached_answer = None
        if not is_image_req and not skip_cache_for_price_all and not skip_cache_for_kac:
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
                    ans_bytes = cached_answer
                    if self._should_attach_site_link(corrected_message):
                        ans_bytes = self._with_site_link_appended(ans_bytes)

                    return self.app.response_class(ans_bytes, mimetype="text/plain")
                    

        final_answer_parts = []

        def caching_generator():
            try:
                for chunk in self._generate_response(corrected_message, user_id, name_surname):
                    # ---> Güvenli: her parçayı bytes'a çevir
                    if not isinstance(chunk, (bytes, bytearray)):
                        chunk = str(chunk).encode("utf-8")

                    final_answer_parts.append(chunk)
                    yield chunk
            except Exception as ex:
                error_text = f"Bir hata oluştu: {str(ex)}\n"
                safe_err = error_text.encode("utf-8")
                final_answer_parts.append(safe_err)
                self.logger.error(f"caching_generator hata: {ex}")
                yield self._with_site_link_appended(safe_err)
            finally:
                # Artık final_answer_parts yalnızca bytes: bu join düşmez
                full_answer = b"".join(final_answer_parts).decode("utf-8", errors="ignore")

                conversation_id = save_to_db(user_id, user_message, full_answer, username=name_surname)

                self.user_states[user_id]["last_conversation_id"] = conversation_id
                self.user_states[user_id]["last_user_message"] = user_message
                self.user_states[user_id]["last_assistant_answer"] = full_answer

                if (not is_image_req and not is_non_sentence_short_reply(corrected_message) and not skip_cache_for_kac):
                    answer_bytes = b"".join(final_answer_parts)          # zaten bytes
                    self._store_in_fuzzy_cache(user_id, name_surname, corrected_message, answer_bytes, new_assistant_id, conversation_id)
                yield f"\n[CONVERSATION_ID={conversation_id}]".encode("utf-8")
                yield self._feedback_marker(conversation_id)
        return self.app.response_class(
            stream_with_context(caching_generator()),
            mimetype="text/html; charset=utf-8",
        )

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
        requested_trim = (requested_trim or "").lower().strip()
        if not requested_trim:
            return image_list  # Trim belirtilmemişse eleme yapma

        requested_variants = normalize_trim_str(requested_trim)

        # 1) 'Diğer' varyantları çıkar ama İSTENEN varyantların parçası olanları listeye alma
        other_variants = []
        for trim_name, variants in TRIM_VARIANTS.items():
            if trim_name == requested_trim:
                continue
            for v in variants:
                # Örn. v='prestige' iken, 'e prestige 60' içinde zaten geçiyor → eleme listesine alma
                if any(v in rv for rv in requested_variants):
                    continue
                other_variants.append(v)

        # Token sınırları: '_' '-' veya boşluk
        def has_variant(name, variant):
            pat = rf'(^|[ _\-]){re.escape(variant)}($|[ _\-])'
            return re.search(pat, name) is not None

        filtered = []
        for img_file in image_list:
            lower_img = img_file.lower()

            # a) Başka bir varyant ayrı bir token olarak geçiyorsa atla
            if any(has_variant(lower_img, v) for v in other_variants):
                continue

            # b) İstenen varyant ayrı bir token olarak geçiyor mu?
            has_requested = any(has_variant(lower_img, rv) for rv in requested_variants)
            # c) Dosya adında herhangi bir trim izi var mı?
            has_any_trim  = any(has_variant(lower_img, v) for v in TRIM_VARIANTS_FLAT)

            # d) İstenen varyant varsa tut; yoksa genel foto ise yine tut
            if has_requested or not has_any_trim:
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
    

        
    def _ensure_thread(self, user_id: str, assistant_id: str) -> str:
        """Kullanıcının bu asistana ait thread’ini oluşturur veya döndürür."""
        threads = self.user_states[user_id].setdefault("threads", {})
        thread_id = threads.get(assistant_id)

        if not thread_id:
            t = self.client.beta.threads.create()      # boş thread
            thread_id = t.id
            threads[assistant_id] = thread_id
        return thread_id    
    def _ask_assistant(
        self,
        user_id: str,
        assistant_id: str,
        content: str,
        timeout: float = 60.0,
        instructions_override: str | None = None,   # <-- NEW
        ephemeral: bool = False                     # <-- NEW
    ) -> str:
        # Thread seçimi
        if ephemeral:
            # Her çağrıda tertemiz thread (geçmiş taşınmaz)
            t = self.client.beta.threads.create()
            thread_id = t.id
        else:
            thread_id = self._ensure_thread(user_id, assistant_id)

        # 1) Kullanıcı mesajını ekle
        self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content
        )

        # 2) Run başlat (override varsa ekle)
        run_kwargs = {"thread_id": thread_id, "assistant_id": assistant_id}
        if instructions_override:
            run_kwargs["instructions"] = instructions_override

        run = self.client.beta.threads.runs.create(**run_kwargs)

        # 3) Tamamlanana kadar bekle
        start = time.time()
        while time.time() - start < timeout:
            run = self.client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run.status == "completed":
                break
            if run.status == "failed":
                raise RuntimeError(run.last_error["message"])
            time.sleep(0.5)

        # 4) Son asistan mesajını al
        msgs = self.client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=5)
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
        
        self.logger.info(f"[_generate_response] Kullanıcı ({user_id}): {user_message}")
        if self._is_test_drive_intent(user_message):
            yield self._contact_link_html(
                user_id=user_id,
                model_hint=self._resolve_display_model(user_id)
            ).encode("utf-8")
            # İsterseniz yanında hızlı örnek talepleri de gösterelim:
            return
        assistant_id = self.user_states[user_id].get("assistant_id", None)
        if "current_trim" not in self.user_states[user_id]:
            self.user_states[user_id]["current_trim"] = ""

        lower_msg = user_message.lower()
        price_intent = self._is_price_intent(user_message)
        teknik_keywords = [
            "teknik özellik", "teknik veriler", "teknik veri", "motor özellik", "motor donanım", "motor teknik", "teknik tablo", "teknik", "performans"
        ]
                # ✅ Karşılaştırma sinyali (erken hesaplayalım)
        compare_keywords = ["karşılaştır", "karşılaştırma", "kıyas", "kıyasla", "kıyaslama", "vs", "vs."]
        wants_compare = any(ck in lower_msg for ck in compare_keywords)
        models_in_msg2 = list(self._extract_models(user_message))

        if price_intent:  # ← ESKİ: if "fiyat" in lower_msg:
            yield from self._yield_fiyat_listesi(user_message, user_id=user_id)
            return

        if any(kw in lower_msg for kw in teknik_keywords):
    # 🔴 ÖNEMLİ: Karşılaştırma niyeti varsa veya 2+ model varsa
    # bu blok tek-model tablosu üretmesin; aşağıdaki karşılaştırma
    # koduna düşsün (return etme).
            if wants_compare or len(models_in_msg2) >= 2:
                pass  # karşılaştırma bloğuna geçilecek
            else:
                # Tek model için mevcut davranış aynı kalsın; fakat seçimi deterministik yapalım
                pairs_for_order = extract_model_trim_pairs(lower_msg)
                found_model = None
                if pairs_for_order:
                    found_model = pairs_for_order[0][0]  # cümlede ilk geçen model
                elif len(models_in_msg2) == 1:
                    found_model = models_in_msg2[0]
                elif assistant_id:
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
        
                # --- FIYAT L\u0130STES\u0130 ---
        if "fiyat" in lower_msg:
            # Belirtilen modele g\u00f6re filtreleyerek ya da tam liste halinde fiyat tablosunu d\u00f6n
            yield from self._yield_fiyat_listesi(user_message, user_id=user_id)
            return
        # --- TEKNİK KARŞILAŞTIRMA / KIYAS ---
        compare_keywords = ["karşılaştır", "karşılaştırma", "kıyas", "kıyasla", "kıyaslama", "vs", "vs."]

        has_teknik_word = any(kw in lower_msg for kw in [
            "teknik özellik", "teknik veriler", "teknik veri", "motor özellik", "motor donanım",
            "motor teknik", "teknik tablo", "teknik", "performans"
        ])
        wants_compare = any(ck in lower_msg for ck in compare_keywords)

        # Mesajda 2+ model varsa ve teknik/kıyas sinyali geldiyse karşılaştırma yap
        models_in_msg = list(self._extract_models(user_message))  # set -> liste
        pairs_for_order = extract_model_trim_pairs(lower_msg)     # sıralı tespit için

        # Sıralı model listesi (tekrarsız)
        ordered_models = []
        for m, _ in pairs_for_order:
            if m not in ordered_models:
                ordered_models.append(m)
        # fallback: sıraya dair ipucu yoksa set'ten gelenler
        if len(ordered_models) < len(models_in_msg):
            for m in models_in_msg:
                if m not in ordered_models:
                    ordered_models.append(m)

        if has_teknik_word and (wants_compare or len(ordered_models) >= 2):
            # En az iki geçerli model?
            valid = [m for m in ordered_models if m in self.TECH_SPEC_TABLES]
            if len(valid) < 2:
                # En az iki geçerli teknik tablo yoksa devam et (tek model akışına düşsün)
                pass
            else:
                only = self._detect_spec_filter_keywords(lower_msg)  # opsiyonel: 'sadece ...'
                md = self._build_teknik_comparison_table(valid, only_keywords=(only or None))
                if not md:
                    yield "Karşılaştırma için uygun teknik tablo bulunamadı.<br>".encode("utf-8")
                    return

                title = " vs ".join([m.title() for m in valid])
                yield f"<b>{title} — Teknik Özellikler Karşılaştırması</b><br>".encode("utf-8")
                yield (md + "\n\n").encode("utf-8")

                # Hızlı ekleme linkleri (kullanıcı deneyimi)
                others = [m for m in self.MODEL_VALID_TRIMS.keys() if m not in valid and m in self.TECH_SPEC_TABLES]
                if others:
                    links = "<b>Karşılaştırmaya ekle:</b><br>"
                    for m in others:
                        cmd = (" ".join(valid) + f" ve {m} teknik özellikler karşılaştırma").strip()
                        safe_cmd = cmd.replace("'", "\\'")
                        links += f"""&bull; <a href="#" onclick="sendMessage('{safe_cmd}');return false;">{m.title()}</a><br>"""
                    yield links.encode("utf-8")
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
        image_mode = is_image_req or self._is_pending_image(user_id)
        if image_mode:
            user_models_in_msg2 = self._extract_models(user_message)
            if not user_models_in_msg2 and "last_models" in self.user_states[user_id]:
                user_models_in_msg2 = self.user_states[user_id]["last_models"]

            if user_models_in_msg2:
                self._clear_pending_image(user_id)  # bekleme bayrağını sil
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
                # model yoksa kullanıcıdan iste ama bekleme bayrağını ayarla
                self._set_pending_image(user_id)
                yield ("Hangi modelin görsellerine bakmak istersiniz? "
                    "(Fabia, Kamiq, Scala, Karoq, Enyaq, Elroq vb.)<br>")
                return
        # 7.9) KÖPRÜ: Tablo/Görsel akışları haricinde — birinci servisten yanıt al,
#            sonra 'test' asistanı üzerinden kullanıcıya ilet
        # 7.9) KÖPRÜ: ...
        try:
            bridge = self._proxy_first_service_answer(user_message=user_message, user_id=user_id)
            bridge_answer      = (bridge.get("answer") or "").strip()
            bridge_table_md    = (bridge.get("table_md") or "").strip() if isinstance(bridge, dict) else ""
            bridge_table_html  = (bridge.get("table_html") or "").strip() if isinstance(bridge, dict) else ""
            bridge_table_title = (bridge.get("table_title") or "").strip() if isinstance(bridge, dict) else ""
            bridge_table_flag  = bool(bridge.get("table_intent")) if isinstance(bridge, dict) else False
        except Exception:
            bridge_answer = ""
            bridge_table_md = ""
            bridge_table_html = ""
            bridge_table_title = ""
            bridge_table_flag = False

        # --- YENİ: TABLO SİNYALİ VARSA BİRİNCİ KODU BIRAK, SORUYU 'TEST' ASİSTANA BAŞTAN YÖNLENDİR ---
        if bridge_table_flag or bridge_table_md or bridge_table_html or self._looks_like_table_intent(bridge_answer):
            long_blob = bridge_table_md or bridge_table_html or bridge_answer
            if self._approx_tokens(long_blob) > 6500:
                self.logger.warning("[BRIDGE] Big table detected; returning locally.")
                safe = long_blob
                if '|' in safe and '\n' in safe:
                    safe = fix_markdown_table(safe)
                else:
                    safe = self._coerce_text_to_table_if_possible(safe)
                yield self._deliver_locally(safe, user_message, user_id)
                return
            out_bytes = self._answer_from_scratch_via_test_assistant(user_id=user_id, original_user_message=user_message)
            yield out_bytes
            return

        # (Tablo sinyali yoksa eski davranış: köprü cevabını TEST asistanı üzerinden ilet)
        if bridge_answer:
            # Görselleri kaldır (tablo varsa da artık buraya düşmeyecek)
            bridge_answer = self._strip_tables_and_images(bridge_answer)
            # Hafif post-process
            if '|' in bridge_answer and '\n' in bridge_answer:
                bridge_answer = fix_markdown_table(bridge_answer)
            else:
                bridge_answer = self._coerce_text_to_table_if_possible(bridge_answer)

            out_bytes = self._deliver_via_test_assistant(
                user_id=user_id,
                answer_text=bridge_answer,
                original_user_message=user_message
            )
            yield out_bytes
            return




        # (Bridge boş dönerse normal '8) OpenAI API' yerel akışınıza düşsün.)

        # 8) Eğer buraya geldiysek => OpenAI API'ye gidilecek
        if not assistant_id:
            yield self._with_site_link_appended("Uygun bir asistan bulunamadı.\n")
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
                    try:
                        # SDK sürümünüz destekliyorsa run_id ile daraltın
                        msg_response = self.client.beta.threads.messages.list(
                            thread_id=thread_id,
                            run_id=run.id,
                            order="desc",
                            limit=5
                        )
                    except TypeError:
                        # Eski SDK: run_id parametresi yoksa sadece en yeni mesajlara bak
                        msg_response = self.client.beta.threads.messages.list(
                            thread_id=thread_id,
                            order="desc",
                            limit=5
                        )

                    latest_assistant = next((m for m in msg_response.data if m.role == "assistant"), None)
                    if not latest_assistant:
                        yield self._with_site_link_appended("Asistan yanıtı bulunamadı.\n")
                        break

                    parts = []
                    for part in latest_assistant.content:
                        if getattr(part, "type", None) == "text":
                            parts.append(part.text.value)
                    content = "\n".join(parts).strip()

                    content_md = self.markdown_processor.transform_text_to_markdown(content)
                    if '|' in content_md and '\n' in content_md:
                        content_md = fix_markdown_table(content_md)

                    assistant_response = content
                    models_in_msg_now = self._extract_models(user_message)
                    model_hint = next(iter(models_in_msg_now)) if len(models_in_msg_now) == 1 else None

                    resp_bytes = content_md.encode("utf-8")
                    
                    if self._should_attach_contact_link(user_message):
                        resp_bytes = self._with_contact_link_prefixed(
                            resp_bytes, user_id=user_id, model_hint=model_hint
                        )

                    if self._should_attach_site_link(user_message):
                        resp_bytes = self._with_site_link_appended(resp_bytes)

                    yield resp_bytes
                    # ÖNEMLİ: while döngüsünden çık
                    break
                elif run.status == "failed":
                    yield self._with_site_link_appended("Yanıt oluşturulamadı.\n")
                    return
                time.sleep(0.5)

            if not assistant_response:
                yield self._with_site_link_appended("Yanıt alma zaman aşımına uğradı.\n")
                return

        except Exception as e:
            error_msg = f"Hata: {str(e)}\n"
            self.logger.error(f"Yanıt oluşturma hatası: {str(e)}")
            yield self._with_site_link_appended(error_msg.encode("utf-8"))

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

    def _idle_prompts_html(self, user_id: str) -> str:
        """Kullanıcı pasif kaldığında gösterilecek tıklanabilir örnek talepler."""
        model = (self._resolve_display_model(user_id) or "Skoda").lower()
        suggestions = []

        if model in self.MODEL_VALID_TRIMS:
            trims = self.MODEL_VALID_TRIMS[model]
            first_trim = trims[0] if trims else ""
            suggestions = [
                "Test sürüşü",
                f"{model} fiyat",
                f"{model} teknik özellikler",
                (f"{model} {first_trim} opsiyonel" if first_trim else f"{model} opsiyonel"),
                f"{model} siyah görsel",
            ]
        else:
            suggestions = [
                "Test sürüşü",
                "Fiyat",
                "Octavia teknik özellikler",
                "Karoq Premium opsiyonel",
                "Kamiq gümüş görsel",
            ]

        html = [
            '<div class="idle-prompts" style="margin-top:10px;">',
            "<b>Örnek talepler:</b><br>"
        ]
        for p in suggestions:
            # Gönderilecek komut olduğu gibi kalsın; link metni kullanıcı dostu görünsün
            safe_cmd = p.replace("'", "\\'")
            html.append(f"&bull; <a href=\"#\" onclick=\"sendMessage('{safe_cmd}');return false;\">{p}</a><br>")
        html.append("</div>")
        return "".join(html)

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