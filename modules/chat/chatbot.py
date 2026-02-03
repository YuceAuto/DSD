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
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=True)
import numpy as np
# Aşağıdaki import'lar sizin projenizdeki dosya yollarına göre uyarlanmalıdır:
from modules.managers.image_manager import ImageManager
from modules.managers.markdown_utils import MarkdownProcessor
from modules.config import Config
from modules.utils import Utils
from modules.db import create_tables, save_to_db, send_email, get_db_connection, update_customer_answer
from openai import OpenAI
from modules.openai_assistant_runner import AssistantRunner
import json, time, os, secrets

# -- ENYAQ tabloları 
from modules.data.enyaq_data import ENYAQ_DATA_MD 
# -- ELROQ tablosu 
from modules.data.elroq_data import ELROQ_DATA_MD 
# Fabia, Kamiq, Scala tabloları 
from modules.data.scala_data import SCALA_DATA_MD 
from modules.data.kamiq_data import KAMIQ_DATA_MD 
from modules.data.fabia_data import FABIA_DATA_MD   
# Karoq tabloları 
from modules.data.karoq_data import KAROQ_DATA_MD 
from modules.data.kodiaq_data import KODIAQ_DATA_MD 
from modules.data.octavia_data import OCTAVIA_DATA_MD 
from modules.data.superb_data import SUPERB_DATA_MD
from modules.data.test_data import (
    TEST_E_PRESTIGE_60_MD,
    TEST_PREMIUM_MD,
    TEST_PRESTIGE_MD,
    TEST_SPORTLINE_MD
)
from openai import OpenAI
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
# -- FABIA

from modules.data.fabia_teknik import FABIA_TEKNIK_MD

# -- SCALA

from modules.data.scala_teknik import SCALA_TEKNIK_MD

# -- KAMIQ

from modules.data.kamiq_teknik import KAMIQ_TEKNIK_MD

# -- KAROQ

from modules.data.karoq_teknik import KAROQ_TEKNIK_MD

# -- KODIAQ

from modules.data.kodiaq_teknik import KODIAQ_TEKNIK_MD

# -- OCTAVIA

from modules.data.octavia_teknik import OCTAVIA_TEKNIK_MD

# -- SUPERB

from modules.data.superb_teknik import SUPERB_TEKNIK_MD

# -- ENYAQ

from modules.data.enyaq_teknik import ENYAQ_TEKNIK_MD

# -- ELROQ
from modules.data.elroq_teknik import ELROQ_TEKNIK_MD
import math
from modules.data.ev_specs import EV_RANGE_KM, FUEL_SPECS   # 1. adımda oluşturduk
import math
from modules.data.text_norm import normalize_tr_text as normalize_tr_text_light
from modules.data.text_norm import normalize_tr_text as normalize_tr_text_base
from neo4j import GraphDatabase
from modules.trace_debug import (
    trace_request,
    maybe_enable_trace_from_payload,
    trace_footer_bytes,
    traced_sql_conn,
    traced_openai_client,
    span,
    tracer,
)
import secrets
from contextlib import nullcontext
from modules.trace_debug import trace_request, trace_footer_html, tracer

 # tüm metodları göster
# --- Türkçe lemma + opsiyonel HuggingFace embedding helper'ları ---

try:
    from sentence_transformers import SentenceTransformer
    _HF_SEM_MODEL = SentenceTransformer(
        os.getenv("HF_TURKISH_EMB_MODEL", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
    )
except Exception:
    _HF_SEM_MODEL = None
from modules.data.city_coords_tr import build_tr_location_dicts
from modules.data.text_norm import normalize_tr_text

CITY_COORDS_TR, DISTRICT_COORDS_TR, CITY_COORDS_TR_NORM, DISTRICT_COORDS_TR_NORM = build_tr_location_dicts(
    normalize_fn=normalize_tr_text
)
# İlçe adı -> (il_norm, (lat, lon), il_adı, ilçe_adı)
DISTRICT_FLAT_NORM = {}
for il_ad, ilceler in (DISTRICT_COORDS_TR or {}).items():
    iln = normalize_tr_text(il_ad)
    for ilce_ad, ll in (ilceler or {}).items():
        ilce_n = normalize_tr_text(ilce_ad)
        DISTRICT_FLAT_NORM[ilce_n] = (iln, ll, il_ad, ilce_ad)



ASSISTANT_NAMES = {
    "fabia", "scala", "kamiq", "karoq", "kodiaq",
    "octavia", "superb", "elroq", "enyaq"
}
# =========================
# TRIP CALC (Kaç şarj / kaç depo) - OFFLINE mesafe (kuş uçuşu)
# =========================


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    import math
    R = 6371.0
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi/2)**2) + math.cos(p1)*math.cos(p2)*(math.sin(dlmb/2)**2)
    return 2 * R * math.asin(math.sqrt(a))

def _extract_km_from_text(text: str) -> float | None:
    """
    "450 km" / "450km" / "450 KM" -> 450.0
    """
    if not text:
        return None
    t = normalize_tr_text_base(text).lower()
    m = re.search(r"\b(\d{2,5}(?:[.,]\d+)?)\s*km\b", t)
    if not m:
        return None
    raw = m.group(1).replace(",", ".")
    try:
        return float(raw)
    except Exception:
        return None

def _extract_two_places(text: str) -> tuple[str | None, str | None, dict, dict]:
    """
    Dönüş:
      a_name, b_name, a_meta, b_meta
    meta: {"type": "city"|"district", "il": "...", "ilce": "...", "coord": (lat, lon)}
    """
    if not text:
        return None, None, {}, {}

    raw = text.strip()

    # 1) "X'dan Y'ye" yakala
    m = re.search(
        r"([A-Za-zÇĞİÖŞÜçğıöşü\s]+?)\s*(?:'?(?:dan|den|tan|ten))\s+"
        r"([A-Za-zÇĞİÖŞÜçğıöşü\s]+?)\s*(?:'?(?:ya|ye|a|e))\b",
        raw, flags=re.IGNORECASE
    )
    if m:
        a = clean_city_name(m.group(1))
        b = clean_city_name(m.group(2))

        # ✅ eğer temizlikten sonra hala boş/tek kelime bile kalmadıysa ngram fallback'e geç
        if not a or not b:
            pass
        else:
            a_norm = normalize_tr_text_base(a)
            b_norm = normalize_tr_text_base(b)

            a_meta = {}
            b_meta = {}

            ll1 = CITY_COORDS_TR_NORM.get(a_norm) or (DISTRICT_FLAT_NORM.get(a_norm) or (None, None, None, None))[1]
            ll2 = CITY_COORDS_TR_NORM.get(b_norm) or (DISTRICT_FLAT_NORM.get(b_norm) or (None, None, None, None))[1]

            if ll1:
                a_meta = {"type": "city", "il": a, "ilce": None, "coord": ll1}
            if ll2:
                b_meta = {"type": "city", "il": b, "ilce": None, "coord": ll2}

            return a, b, a_meta, b_meta



    # 2) Token/ngram ile il/ilçe bul (en sağlam)
    t = normalize_tr_text_base(raw).lower()
    toks = re.findall(r"[0-9a-zçğıöşü]+", t)
    toks = [strip_tr_suffixes(x) for x in toks if x]

    hits = []  # (start_idx, length, display_name, meta)
    # uzun ngram önce (3->2->1)
    for n in (3, 2, 1):
        for i in range(0, len(toks) - n + 1):
            phrase = " ".join(toks[i:i+n]).strip()
            if not phrase:
                continue
            phrase_norm = normalize_tr_text_base(phrase)

            # İl mi?
            if phrase_norm in CITY_COORDS_TR_NORM:
                ll = CITY_COORDS_TR_NORM[phrase_norm]
                disp = phrase.title()
                hits.append((i, n, disp, {"type":"city", "il": disp, "ilce": None, "coord": ll}))
                continue

            # İlçe mi?
            if phrase_norm in DISTRICT_FLAT_NORM:
                iln, ll, il_ad, ilce_ad = DISTRICT_FLAT_NORM[phrase_norm]
                disp = ilce_ad
                hits.append((i, n, disp, {"type":"district", "il": il_ad, "ilce": ilce_ad, "coord": ll}))

    if not hits:
        return None, None, {}, {}

    # çakışmaları azalt: erken index + uzun ifade öncelikli
    hits.sort(key=lambda x: (x[0], -x[1]))

    chosen = []
    used_spans = []
    for i, n, disp, meta in hits:
        span = (i, i+n)
        # overlap varsa atla
        if any(not (span[1] <= s[0] or span[0] >= s[1]) for s in used_spans):
            continue
        chosen.append((disp, meta))
        used_spans.append(span)
        if len(chosen) == 2:
            break

    if len(chosen) < 2:
        return None, None, {}, {}

    return chosen[0][0], chosen[1][0], chosen[0][1], chosen[1][1]


# Kullanıcı modelle ilgili genel bilgi isterse dönecek sabit metinler
MODEL_GENERAL_INFO = {
    "kamiq": (
        "Skoda Kamiq, şehir içi ve şehir dışı kullanıma uygun, pratik ve modern bir SUV modelidir. "
        "Öne çıkan genel özellikleri şunlardır:\n\n"
        "Genel Özellikler\n"
        "Boyutlar: Kompakt tasarımıyla şehir içinde kolay manevra sağlar. "
        "Uzunluğu 4.241 mm, genişliği 1.793 mm ve yüksekliği 1.562 mm'dir.\n"
        "Bagaj Hacmi: 400 litre bagaj kapasitesine sahiptir ve arka koltuklar yatırıldığında "
        "bu kapasite 1.395 litreye kadar çıkabilir.\n"
        "Motor Seçenekleri:\n"
        "- 1.0 TSI, 115 PS gücünde, 3 silindirli motor.\n"
        "- 1.5 TSI, 150 PS gücünde, 4 silindirli motor.\n"
        "Her iki motor da 7 ileri DSG otomatik şanzımanla sunulmaktadır.\n"
        "Yakıt Tüketimi: WLTP standartlarına göre birleşik yakıt tüketimi "
        "5.6 - 6.1 litre/100 km aralığındadır.\n"
        "Güvenlik: Standart olarak şerit takip sistemi, ön bölge frenleme asistanı, "
        "çoklu çarpışma freni ve sürücü yorgunluk tespit sistemi gibi ileri seviye "
        "güvenlik özellikleri sunulmaktadır.\n\n"
        "Donanım Seviyeleri\n"
        "Elite: Temel güvenlik ve konfor özelliklerini içerir. Bi-LED ön farlar, "
        "manuel klima ve 8\" dijital gösterge paneli gibi standart donanımlara sahiptir.\n"
        "Premium: Çift bölgeli otomatik klima, geri görüş kamerası, kablosuz şarj ünitesi "
        "ve 10.25\" dijital gösterge paneli gibi daha ileri özelliklerle donatılmıştır.\n"
        "Monte Carlo: Spor tasarım detayları ve en üst düzey donanımları sunar. "
        "Full LED Matrix ön farlar, spor direksiyon simidi ve panoramik cam tavan "
        "gibi özellikleri içerir.\n\n"
        "Konfor ve Teknoloji\n"
        "Kablosuz SmartLink (Apple CarPlay ve Android Auto) ile mobil cihazlar kolayca bağlanabilir.\n"
        "8.25\" dokunmatik multimedya sistemi tüm donanımlarda standarttır.\n"
        "İleri teknolojiler arasında elektrikli bagaj kapağı, otomatik park pilotu ve "
        "çeşitli sürüş modları bulunur.\n\n"
        "Kamiq, geniş iç mekanı, modern tasarımı ve zengin donanım seçenekleriyle "
        "her türlü kullanıcı ihtiyacına hitap eder. Daha detaylı bilgi için sorularınızı belirtebilirsiniz."
    ), "fabia": (
        "Skoda Fabia, kompakt bir hatchback model olup şık tasarımı, gelişmiş güvenlik özellikleri "
        "ve yüksek teknolojili donanımlarıyla dikkat çeken bir araçtır. İşte Skoda Fabia'nın öne çıkan genel özellikleri:\n\n"
        "Güvenlik:\n"
        "- Sürücü ve ön yolcu hava yastıkları, yan ve perde hava yastıkları\n"
        "- Yaya algılama özellikli ön bölge frenleme asistanı\n"
        "- Şerit takip sistemi, yorgunluk tespit sistemi, çoklu çarpışma freni\n"
        "- Elektronik stabilite kontrol sistemi (ESC) ve yokuş kalkış desteği\n"
        "- Acil durum çağrı sistemi (E-Call)\n"
        "- ISOFIX çocuk koltuğu sabitleme özelliği\n\n"
        "Konfor ve Teknoloji:\n"
        "- Start & Stop sistemi ve anahtarsız giriş-çalıştırma (KESSY FULL)\n"
        "- Geri görüş kamerası ve park mesafe sensörleri (ön/arka)\n"
        "- 8.25\" dokunmatik multimedya sistemi, kablosuz Apple CarPlay & Android Auto\n"
        "- Çift bölgeli tam otomatik klima ve arka havalandırma çıkışları\n"
        "- Dijital gösterge paneli (modeline göre 8\" veya 10.25\")\n\n"
        "Tasarım:\n"
        "- LED gündüz sürüş farları ve arka aydınlatma grubu\n"
        "- 16\"–18\" arasında değişen alüminyum alaşımlı jant seçenekleri\n"
        "- Siyah detaylarla zenginleştirilmiş Monte Carlo modeli ile sportif bir tasarım alternatifi\n\n"
        "Motor Seçenekleri:\n"
        "- 1.0 TSI (115 PS) ve 1.5 TSI (150 PS) turboşarjlı benzinli motor seçenekleri\n"
        "- 7 ileri otomatik DSG şanzıman\n"
        "- Düşük yakıt tüketimi ve emisyon değerleri (WLTP normlarına uygun)\n\n"
        "Bagaj Kapasitesi:\n"
        "- Standart 380 litre bagaj hacmi, arka koltuklar katlandığında 1.190 litreye kadar çıkabilir.\n\n"
        "Eğer daha fazla bilgi almak istediğiniz özel bir konu (örneğin, donanımlar, renk seçenekleri, "
        "motor özellikleri) varsa, size daha detaylı yardımcı olabilirim!"
    ), "scala": (
        "Skoda Scala, modern tasarımı, geniş iç mekanı ve zengin donanım özellikleriyle dikkat çeken "
        "kompakt bir hatchback modelidir. İşte Scala ile ilgili genel bilgiler:\n\n"
        "Motor Seçenekleri\n"
        "1.0 TSI: 115 PS güç ve 200 Nm tork sunar. 0-100 km/sa hızlanma 10.1 saniyedir. "
        "Ortalama yakıt tüketimi 5.4–5.8 lt/100 km'dir.\n"
        "1.5 TSI: 150 PS güç ve 250 Nm tork sunar. 0-100 km/sa hızlanma 8.2 saniyedir. "
        "Ortalama yakıt tüketimi 5.6–6.1 lt/100 km'dir.\n"
        "Her iki motor seçeneği de 7 ileri DSG otomatik şanzımanla birlikte sunulur.\n\n"
        "Boyutlar\n"
        "- Uzunluk: 4.362 mm\n"
        "- Genişlik: 1.793 mm\n"
        "- Yükseklik: 1.493 mm\n"
        "- Aks Mesafesi: 2.636 mm\n"
        "- Bagaj Hacmi: 467 litre (arka koltuklar yatırıldığında 1.410 litreye çıkar)\n\n"
        "Donanım Seviyeleri\n"
        "Elite: Temel donanım seviyesidir. LED gündüz sürüş farları, 8.25\" multimedya sistemi ve "
        "8\" dijital gösterge paneli gibi özelliklerle gelir.\n"
        "Premium: Ekstra konfor ve teknoloji sunar. Köşe dönüş özellikli LED sis farları, geri görüş kamerası, "
        "kablosuz şarj ünitesi ve çift bölgeli otomatik klima gibi özellikler eklenmiştir.\n"
        "Monte Carlo: Spor tasarım detaylarıyla öne çıkar. Full LED Matrix far grubu, 10.25\" dijital gösterge paneli, "
        "panoramik cam tavan ve Monte Carlo logolu spor direksiyon simidi gibi özellikler sunar.\n\n"
        "Güvenlik Özellikleri\n"
        "Standart olarak sürücü ve yolcu hava yastıkları, şerit takip sistemi, yorgunluk tespit sistemi, "
        "çoklu çarpışma freni, elektronik stabilite kontrol sistemi ve acil durum çağrı sistemi (E-Call) bulunur.\n"
        "ISOFIX çocuk koltuğu bağlantı noktaları tüm donanım seviyelerinde mevcuttur.\n\n"
        "Konfor ve Teknoloji\n"
        "- Kablosuz SmartLink (Apple CarPlay & Android Auto)\n"
        "- Yüksek kaliteli multimedya sistemleri\n"
        "- Opsiyonel olarak panoramik cam tavan ve elektrikli bagaj kapağı\n\n"
        "Eğer daha fazla detay veya belirli bir donanım seviyesi hakkında bilgi almak isterseniz, lütfen belirtin!"
    ),"karoq": (
        "Skoda Karoq, şehir içi ve şehir dışı kullanıma uygun, pratik ve modern bir SUV modelidir. "
        "Öne çıkan genel özellikleri şunlardır:\n\n"
        "Genel Özellikler\n"
        "Merhaba, hoş geldiniz!\n"
        "Size Skoda'nın SUV segmentindeki güçlü oyuncusu olan Yeni Karoq modelimizi tanıtmaktan büyük memnuniyet duyarım.\n"
        "Karoq, hem şehir içinde hem de uzun yolculuklarda konfor, güvenlik ve performansı bir arada sunmak için tasarlandı. "
        "Üç farklı donanım seviyesiyle ihtiyaçlarınıza en uygun versiyonu kolaylıkla bulabilirsiniz:\n\n"
        "Skoda Karoq Premium\n"
        "• Giriş seviyesi olmasına rağmen yüksek güvenlik ve teknoloji donanımlarıyla dikkat çeker.\n"
        "• 150 PS gücünde 1.5 TSI motor ve DSG otomatik şanzıman ile güçlü ve konforlu bir sürüş deneyimi sunar.\n"
        "• 17\" Scutus Aero alüminyum jantlar, LED farlar, çift bölgeli tam otomatik klima gibi özelliklerle donatılmıştır.\n\n"
        "Skoda Karoq Prestige\n"
        "• Gelişmiş konfor arayanlar için ideal.\n"
        "• Elektrikli bagaj kapağı, KESSY tam anahtarsız giriş ve çalıştırma, Full LED Matrix farlar gibi birçok üst düzey özellik sunar.\n"
        "• İç mekânda yarı deri döşeme, ambiyans aydınlatma ve ısıtmalı ön koltuklar gibi konfor detayları bulunur.\n\n"
        "Skoda Karoq Sportline\n"
        "• Dinamik tasarım ve sportif detaylardan hoşlananlar için!\n"
        "• 19\" Sagitarius Aero jantlar, siyah tasarım detayları, Sportline logolu direksiyon ve özel Thermoflux döşeme ile dikkat çeker.\n"
        "• Adaptif hız sabitleyici, dijital gösterge paneli ve F1 vites kulakçıklarıyla sürüş keyfini bir üst seviyeye taşır.\n\n"
        "Öne Çıkan Ortak Özellikler:\n"
        "• 150 PS güç, 250 Nm tork ile güçlü performans\n"
        "• 6.1 – 6.4 lt/100 km birleşik yakıt tüketimi\n"
        "• 521 litre bagaj hacmi, arka koltuklar yatırıldığında 1.630 litreye kadar çıkıyor\n"
        "• 10.25\" dijital gösterge paneli, SmartLink (Apple CarPlay & Android Auto) desteği\n\n"
        "Sürüş güvenliği, teknolojik donanımlar ve konforun mükemmel birleşimini arıyorsanız, Skoda Karoq tam size göre!\n"
        "Dilerseniz sizin için uygun donanım seviyesini birlikte seçebilir, opsiyonel özellikleri inceleyebiliriz."
    ), "kodiaq": (
    "Güç, Konfor ve Akılcı Tasarım Tek Bir SUV'da Buluştu: Yeni Škoda Kodiaq\n\n"
    "Hayatınızda her şeyden biraz fazlasını istiyorsanız, Yeni Škoda Kodiaq tam size göre. "
    "İster şehirde ister doğada olun, Kodiaq her yolculuğu keyfe dönüştürüyor. "
    "Şık tasarımı, geniş iç hacmi ve üstün teknolojileriyle sınıfında fark yaratıyor.\n\n"
    "Güçlü Motor Seçenekleri\n"
    "150 PS’lik 1.5 TSI mHEV motor ile ekonomi ve performansı dengede tutun, "
    "ya da 265 PS’lik 2.0 TSI motorla dört çeker gücün keyfini çıkarın. "
    "Her sürüşte size güven veren performans Kodiaq’ta standart.\n\n"
    "Geniş ve Konforlu İç Mekan\n"
    "7 kişiye kadar oturma alanı sunan iç mekân, kaliteli malzemeler ve ergonomik detaylarla donatıldı. "
    "İleri sürüş destek sistemleri, üç bölgeli tam otomatik klima, akıllı dijital ekranlar ve ses sistemiyle "
    "her yolculuk bir deneyime dönüşüyor.\n\n"
    "Üst Düzey Güvenlik\n"
    "Yaya algılama özellikli ön bölge frenleme sistemi, şerit takip asistanı, "
    "trafik sıkışıklığı asistanı ve daha fazlası sayesinde siz ve sevdikleriniz her an güvendesiniz.\n\n"
    "Tarz Sahibi Dış Görünüm\n"
    "Kodiaq, zarif hatları, 18\" ila 20\" arasında değişen jant seçenekleri, "
    "parlak siyah cam çerçeveleri ve dinamik aydınlatmalarıyla güçlü bir duruş sergiliyor.\n\n"
    "Akıllı Çözümler\n"
    "Sanal pedal ile bagaj kapağını ayak hareketinizle açın, kablosuz şarj ünitesiyle kablo karmaşasına son verin, "
    "Smart Comfort giriş özelliğiyle aracınız sizi tanısın ve koltuğunuzu otomatik olarak ayarlasın.\n\n"
    "Škoda Kodiaq ile tanışın, yolculuklarınıza seviye atlatın.\n"
    "Dilerseniz donanım farkları veya opsiyonel özellikleri de detaylıca paylaşabilirim."
    ), "octavia": (
    "ŠKODA OCTAVIA – Sınıfının Zirvesinde Bir Sedan\n\n"
    "Akıllı Tasarım, Güçlü Performans, Etkileyici Konfor\n"
    "Yeni Skoda Octavia, şıklığı ve teknolojiyi bir araya getiren, modern yaşamın tüm ihtiyaçlarına "
    "cevap veren akıllı bir sedan. Geniş iç hacmi, yüksek donanım seviyeleri ve düşük yakıt tüketimi ile "
    "hem şehir içi hem de uzun yolculuklar için ideal bir yol arkadaşı.\n\n"
    "Motor ve Performans\n"
    "1.5 TSI mHEV 150 PS motoruyla hem performans hem ekonomi sunar.\n"
    "8.5 saniyede 0-100 km/s hızlanma, 229 km/s maksimum hız.\n"
    "Yalnızca 4.9 – 5.2 lt/100 km birleşik yakıt tüketimi ile ekonomik sürüş.\n"
    "2.0 TSI 265 PS (RS versiyonunda) ile performans tutkunlarına özel!\n\n"
    "Konfor ve Geniş İç Hacim\n"
    "600 litre bagaj hacmi ile sınıfının en iyilerinden.\n"
    "Premium ve Prestige donanımlarda anahtarsız giriş, arka kol dayama, elektrikli bagaj kapağı gibi "
    "özelliklerle günlük yaşam çok daha konforlu.\n\n"
    "Akıllı Teknoloji\n"
    "Kablosuz SmartLink, 10” veya 13” multimedya ekranları, sesli komut sistemi ile her an bağlantıda kalın.\n"
    "Gelişmiş sürüş destek sistemleri, şerit takip, adaptif hız sabitleyici ve daha fazlasıyla güvenliğiniz ön planda.\n\n"
    "Göz Alıcı Tasarım\n"
    "Modern çizgileri, LED aydınlatmaları ve dikkat çekici jant seçenekleri ile her bakışta fark edilir.\n"
    "Farklı renk seçenekleriyle tarzınızı yansıtır.\n\n"
    "Maksimum Güvenlik\n"
    "Tüm donanım seviyelerinde 7 hava yastığı, şerit takip asistanı, yorgunluk tespit sistemi, çoklu çarpışma freni "
    "gibi gelişmiş güvenlik özellikleri standart.\n\n"
    "İster aile aracı olarak ister günlük şehir trafiğinde konforlu ve güvenli bir sürüş arıyorsanız, "
    "Skoda Octavia tam size göre!"
    ), "superb": (
    "Yeni Skoda Superb ile Sürüşe Prestij Katın\n\n"
    "Zarif tasarımı, akıllı teknolojileri ve etkileyici performansıyla Yeni Skoda Superb, "
    "sizi ayrıcalıklı hissettirmek için tasarlandı. Şehir içinden uzun yolculuklara kadar her anınızda "
    "konforu ve güvenliği bir arada sunuyor.\n\n"
    "Dikkat Çekici Dış Tasarım\n"
    "Özellik / Detay\n"
    "Jant Seçenekleri: 17\" Mintaka’dan 19” Veritate ve Torcular’a kadar zengin seçenekler\n"
    "Aydınlatma: FULL LED Matrix farlar ve 3D Dinamik arka sinyaller\n"
    "Renk Alternatifleri: Metalik, Exclusive ve Opak renk seçenekleri\n\n"
    "İç Mekânda Lüks ve Konfor\n"
    "Özellik / Detay\n"
    "Bilgi Eğlence Sistemi: 10\" ve 13\" dokunmatik ekran, SmartLink, Canton ses sistemi opsiyonel\n"
    "Döşeme Seçenekleri: Deri, Suedia ve özel Sportline döşemeler\n"
    "Koltuk Konforu: Masaj fonksiyonlu, ısıtmalı ve havalandırmalı koltuk seçenekleri\n\n"
    "Gelişmiş Güvenlik Teknolojileri\n"
    "Özellikler / Donanım Seviyelerinde Sunulma Durumu\n"
    "Şerit Takip Asistanı Plus: Prestige, L&K Crystal, e-Sportline\n"
    "Adaptif Hız Sabitleyici (210 km/s): Prestige ve üstü\n"
    "360° Çevre Görüş Kamerası + Park Asistanı: L&K Crystal ve e-Sportline\n"
    "Ön Bölge Frenleme Asistanı: Tüm donanım seviyelerinde standart\n\n"
    "Motor ve Performans\n"
    "Motor Seçeneği / Güç (PS) / 0-100 km/h / Ortalama Tüketim (lt/100 km)\n"
    "1.5 TSI mHEV: 150 PS, 0-100 km/h 9.2 sn, 5.3–5.6 lt/100 km\n"
    "2.0 TDI 4x4: 193 PS, 0-100 km/h 7.5 sn, 5.8–5.9 lt/100 km\n"
    "2.0 TSI 4x4: 265 PS, 0-100 km/h 5.6 sn, 7.6–7.7 lt/100 km\n"
    "e-Sportline PHEV: 204 PS, 0-100 km/h 8.1 sn, 0.4 lt/100 km (Elektrikli destekli)\n\n"
    "PHEV (Plug-in Hybrid) – e-Sportline\n"
    "Elektrikli menzil (şehir içi): 151 km\n"
    "Şarj süresi (11 kW AC): 2 saat 30 dakika\n"
    "Günlük kullanımda sıfıra yakın yakıt tüketimi sunar.\n\n"
    "Yeni Skoda Superb, sürüş keyfini ileri teknolojiyle birleştiren, her detayı özenle düşünülmüş bir otomobil. "
    "İster prestijli bir iş aracı, ister ailece yolculuklarda güvenli bir yoldaş arıyor olun, Superb "
    "beklentilerinizi fazlasıyla karşılayacaktır."
    ), "elroq": (
    "Skoda Elroq, sadece bir SUV değil; modern teknolojiyi, zarafeti ve sürdürülebilirliği "
    "bir arada sunan tamamen elektrikli bir yaşam deneyimi sunan bir modeldir.\n\n"
    "Performans ve Verimlilik\n"
    "- 150 kW (204 PS) güç üreten elektrik motoru sayesinde Elroq, 0’dan 100 km/s hıza yaklaşık 8 saniyede ulaşabilir.\n"
    "- Lityum iyon bataryasıyla şehir içinde 543 km’ye kadar, kombine kullanımda ise 422 km menzil sunar.\n"
    "- 165 kW DC hızlı şarj desteği sayesinde batarya, %10'dan %80'e yaklaşık 24 dakikada şarj edilebilir.\n\n"
    "Boyutlar ve Konfor\n"
    "- Uzunluk: 4.488 mm, Genişlik: 1.884 mm, Yükseklik: 1.632 mm.\n"
    "- Bu ölçüler, şehir içi manevra kabiliyetini korurken aynı zamanda ferah bir iç mekân sunar.\n"
    "- Bagaj hacmi 470 litredir; arka koltuklar katlandığında 1.580 litreye kadar genişletilebilir.\n\n"
    "Şarj Altyapısı\n"
    "- 11 kW AC şarj ve 165 kW DC hızlı şarj desteği ile hem evde hem de yolda esnek şarj imkânı sağlar.\n"
    "- 11 kW AC şarj ile batarya yaklaşık 6 saat 30 dakikada tamamen doldurulabilir.\n\n"
    "Güvenlik ve Sürüş Destek Sistemleri\n"
    "- Yarı otonom sürüş destek sistemleri ile güvenli ve konforlu sürüş sunar.\n"
    "- Adaptif hız sabitleyici, şerit takip asistanı Plus, ön bölge frenleme sistemi ve arka trafik uyarı sistemi gibi "
    "birçok gelişmiş güvenlik donanımıyla hem sizin hem de ailenizin güvenliği en üst düzeyde korunur.\n\n"
    "Teknoloji ve Konfor\n"
    "- 13” multimedya sistemi, kablosuz Apple CarPlay ve Android Auto desteği ile her zaman bağlantıda kalmanızı sağlar.\n"
    "- Isı pompası, tam otomatik çift bölgeli klima, ambiyans aydınlatma ve kablosuz şarj özelliği gibi birçok premium "
    "özellik Elroq’ta standart olarak sunulmaktadır.\n\n"
    "Tasarım\n"
    "- Siyah tam deri koltuk döşemeleri, UDC (unique dark chrome) dış detaylar ve 19” Proteus alüminyum alaşımlı jantlarla "
    "şık ve sportif bir duruş sergiler.\n"
    "- Dinamik LED aydınlatmalar ve özenle işlenmiş gövde çizgileriyle hem gündüz hem gece dikkat çeken bir tasarıma sahiptir.\n\n"
    "Elroq, tamamen elektrikli yapısı, yüksek menzili, güçlü performansı ve kapsamlı güvenlik/konfor donanımlarıyla "
    "hem şehir içi kullanıma hem de uzun yolculuklara uygun modern bir SUV olarak öne çıkar."
    ), "enyaq": (
    "Skoda Enyaq, gerek şehir içinde gerekse uzun yolculuklarda elektrikli mobilitenin "
    "konforunu ve güvenliğini en üst seviyede yaşamak isteyenler için tasarlanmış tamamen "
    "elektrikli bir SUV modelidir.\n\n"
    "Performans ve Menzil\n"
    "• e-Prestige 60: 204 PS güç ve 59 kWh net batarya kapasitesiyle 423 km’ye kadar menzil sunar; "
    "0–100 km/s hızlanmasını yaklaşık 8,1 saniyede tamamlar.\n"
    "• Coupé e-Sportline 60: Aynı batarya ve performans değerlerini daha sportif coupé gövde ile sunar; "
    "menzil 431 km’ye kadar çıkabilir.\n"
    "• Coupé e-Sportline 85x: 285 PS güce sahip dört çeker versiyon, 77 kWh net bataryasıyla 535 km’ye kadar menzil sunar "
    "ve 0–100 km/s hızlanmasını yaklaşık 6,7 saniyede gerçekleştirir.\n\n"
    "Konfor ve Teknoloji\n"
    "Tüm donanım seviyelerinde yüksek teknoloji ve konfor donanımları standarttır:\n"
    "• 13\" bilgi-eğlence ekranı\n"
    "• Kablosuz Apple CarPlay & Android Auto\n"
    "• Geri görüş kamerası (Coupé e-Sportline 85x’te 360° kamera ve head-up display mevcuttur)\n"
    "• Isıtmalı ön koltuklar ve masaj fonksiyonlu sürücü koltuğu\n"
    "• Üç bölgeli tam otomatik klima sistemi\n"
    "• Elektrikli bagaj kapağı ve panoramik cam tavan seçenekleri\n\n"
    "Güvenlikte Yeni Standartlar\n"
    "Enyaq, gelişmiş sürüş destek sistemleriyle yüksek güvenlik seviyesi sunar:\n"
    "• Şerit takip asistanı\n"
    "• Adaptif hız sabitleyici\n"
    "• Sürücü yorgunluk tespit sistemi\n"
    "• e-Call acil çağrı sistemi\n"
    "• Şerit değiştirme asistanı, trafik sıkışıklığı asistanı ve yarı otonom sürüş fonksiyonlarıyla ileri seviye sürüş desteği\n\n"
    "Tasarım ve Stil\n"
    "• Dış tasarımda coupé çizgiler, dinamik LED farlar ve güçlü SUV duruşu öne çıkar.\n"
    "• İç mekânda suedia veya deri döşeme, ambiyans aydınlatma gibi detaylarla premium bir atmosfer sunulur.\n"
    "• Sportline versiyonlarda siyah dış aynalar, özel çamurluk detayları ve 21\" jant seçenekleriyle daha agresif, sportif bir görünüm elde edilir.\n\n"
    "Kısacası Enyaq, güçlü performansı, uzun menzili, yüksek güvenlik seviyesi ve "
    "konfor odaklı iç mekânı ile tam elektrikli, şık ve teknolojik bir SUV arayan kullanıcılar için ideal bir seçenektir."
    )
    }
import re
from modules.data.text_norm import normalize_tr_text
# === Özellik eşanlam kümesi (örnek) ===
FEATURE_SYNONYMS = {
    # -- HAVA YASTIKLARI / PASİF GÜVENLİK --
    "Perde/yan hava yastıkları": [
        r"yan\s*perde\s*hava\s*yast[ıi]k(?:lar[ıi])?",
        r"perde\s*hava\s*yast[ıi]k(?:lar[ıi])?",
        r"yan\s*hava\s*yast[ıi]k(?:lar[ıi])?"
    ],
    "Ön hava yastıkları": [
        r"[öo]n\s*hava\s*yast[ıi]k(?:lar[ıi])?",
        r"front\s*air\s*bag"
    ],
    "Sürücü diz hava yastığı": [
        r"s[üu]r[üu]c[üu]\s*diz\s*hava\s*yast[ıi]g[ıi]",
        r"driver'?s?\s*knee\s*air\s*bag"
    ],
    "Orta/merkez hava yastığı": [
        r"(?:orta|merkez)\s*hava\s*yast[ıi]g[ıi]",
        r"central\s*air\s*bag|center\s*air\s*bag"
    ],
    "ISOFIX çocuk koltuğu bağlantıları": [
        r"\bisofix\b",
        r"i-?sofix",
        r"child\s*seat\s*anchor"
    ],
    "Aktif gergili emniyet kemerleri": [
        r"aktif\s*gerg[ıi]li\s*emniyet\s*kemer",
        r"pre-?tensioner|pretensioner"
    ],

    # -- SÜRÜŞ DESTEK / ADAS --
    "Şerit takip asistanı (Lane Assist)": [
        r"şerit\s*takip(?:\s*asistan[ıi])?",
        r"lane\s*assist"
    ],
    "Şerit ortalama (Lane Centering)": [
        r"şerit\s*ortalama",
        r"lane\s*centr(?:e|ing)"
    ],
    "Şerit değiştirme asistanı (Side Assist)": [
        r"şerit\s*de[ğg][ıi]ştirme\s*asistan[ıi]",
        r"side\s*assist"
    ],
    "Kör nokta uyarı sistemi (Blind Spot)": [
        r"k[öo]r\s*nokta\s*(?:uyar[ıi])?",
        r"blind\s*spot\s*(?:monitor|detect|warning)"
    ],
    "Arka çapraz trafik uyarısı (RCTA)": [
        r"arka\s*[çc]apraz\s*trafik",
        r"rear\s*cross\s*traffic",
        r"\brcta\b"
    ],
    "Trafik işareti algılama (TSR)": [
        r"trafik\s*i[şs]areti\s*(?:tan[ıi]ma|alg[ıi]lama)",
        r"traffic\s*sign\s*(?:recognition|assist)",
        r"\btsr\b"
    ],
    "Sürücü yorgunluk algılama": [
        r"yorgunluk\s*(?:alg[ıi]lama|tespit)",
        r"driver\s*(?:drowsiness|attention)\s*(?:alert|assist)"
    ],
    "Ön bölge asistanı / AEB (Front Assist)": [
        r"front\s*assist",
        r"[öo]n\s*b[öo]lge\s*asistan[ıi]",
        r"(?:ac[ıi]l|otomatik)\s*fren",
        r"\baeb\b|automatic\s*emergency\s*brak"
    ],
    "Yaya/bisikletli algılama": [
        r"yaya\s*alg[ıi]lama|bisikletli\s*alg[ıi]lama",
        r"pedestrian|cyclist\s*detection"
    ],
    "Hız sabitleyici (Cruise Control)": [
        r"h[ıi]z\s*sabitleyici",
        r"cruise\s*control"
    ],
    "Adaptif hız sabitleyici (ACC)": [
        r"adaptif\s*h[ıi]z\s*sabitleyici",
        r"\bacc\b",
        r"adaptive\s*cruise"
    ],
    "Stop & Go": [
        r"stop\s*&?\s*go",
        r"trafik\s*asistan[ıi]\s*stop\s*go"
    ],
    "Hız sınırlayıcı (Speed Limiter)": [
        r"h[ıi]z\s*s[ıi]n[ıi]rlay[ıi]c[ıi]",
        r"speed\s*limiter"
    ],
    "Akıllı hız asistanı (ISA)": [
        r"ak[ıi]ll[ıi]\s*h[ıi]z\s*asistan[ıi]",
        r"\bisa\b",
        r"intelligent\s*speed"
    ],
    "Yokuş kalkış desteği (HHC/HSA)": [
        r"yoku[şs]\s*kalk[ıi][şs]\s*destek",
        r"\bhhc\b|\bhsa\b",
        r"hill\s*hold"
    ],
    "Yokuş iniş desteği (HDC)": [
        r"yoku[şs]\s*[ıi]ni[şs]\s*destek",
        r"\bhdc\b",
        r"hill\s*descent"
    ],
    "Park asistanı (otomatik park)": [
        r"park\s*asistan[ıi]",
        r"park\s*assist",
        r"otomatik\s*park"
    ],
    "Ön park sensörleri": [
        r"[öo]n\s*park\s*sens[öo]r(?:ler[ıi])?",
        r"front\s*parking\s*sensor"
    ],
    "Arka park sensörleri": [
        r"arka\s*park\s*sens[öo]r(?:ler[ıi])?",
        r"rear\s*parking\s*sensor"
    ],
    "Park sensörleri (ön+arka)": [
        r"(?:[öo]n\s*ve\s*arka|[öo]n-?\/?arka)\s*park\s*sens[öo]r",
        r"park\s*sens[öo]r(?:ler[ıi])?\s*(?:[öo]n\s*ve\s*arka|[öo]n-?\/?arka)"
    ],
    "Geri görüş kamerası": [
        r"geri\s*g[öo]r[üu][şs]\s*kamera",
        r"rear\s*view\s*camera|revers(?:e|ing)\s*camera"
    ],
    "360° çevre görüş kamerası": [
        r"(?:360|360°)\s*kamera",
        r"(?:ç|c)evre\s*g[öo]r[üu][şs]",
        r"(?:top|area)\s*view\s*camera"
    ],

    # -- AYDINLATMA / FARLAR --
    "FULL LED ön farlar": [
        r"full\s*led\s*([öo]n|far)",
        r"top\s*led\s*[öo]n\s*far"
    ],
    "Matrix LED farlar (DLA)": [
        r"matrix\s*led",
        r"\bdla\b",
        r"dynam[ıi]k\s*light\s*assist"
    ],
    "Viraj aydınlatma (Cornering)": [
        r"viraj\s*ayd[ıi]nlatma",
        r"cornering\s*light"
    ],
    "Uzun far asistanı (HBA)": [
        r"uzun\s*far\s*asistan[ıi]",
        r"\bhba\b",
        r"high\s*beam\s*assist"
    ],
    "Adaptif far sistemi (AFS)": [
        r"adaptif\s*far",
        r"\bafs\b"
    ],
    "LED gündüz sürüş farları (DRL)": [
        r"g[üu]nd[üu]z\s*s[üu]r[üu][şs]\s*far",
        r"\bdrl\b",
        r"daytime\s*running"
    ],
    "Sis farları": [
        r"sis\s*far",
        r"fog\s*(?:lamp|light)"
    ],
    "Far yıkama": [
        r"far\s*y[ıi]kama",
        r"headlam?p\s*washer"
    ],
    "Far yükseklik ayarı": [
        r"far\s*y[üu]kseklik\s*ayar",
        r"headlight\s*level(?:ing)?"
    ],
    "Top LED arka aydınlatma": [
        r"top\s*led\s*arka\s*ayd[ıi]nlatma",
        r"arka\s*led\s*([gğ]rup|far|stop)"
    ],

    # -- DIŞ DONANIM / CAMLAR / AYNA --
    "Elektrikli katlanır yan aynalar": [
        r"elektrik(?:li)?\s*katlan[ıi]r\s*(?:yan\s*)?ayna",
        r"power\s*fold(?:ing)?\s*mirror"
    ],
    "Isıtmalı yan aynalar": [
        r"[ıi]s[ıi]tmal[ıi]\s*(?:yan\s*)?ayna",
        r"heated\s*mirror"
    ],
    "Otomatik kararan iç dikiz aynası": [
        r"otomatik\s*kararan\s*(?:[ıi]ç\s*)?dikiz\s*ayna",
        r"electrochrom(?:ic|e)\s*(?:rear\s*view|mirror)"
    ],
    "Yağmur sensörü": [
        r"ya[gğ]mur\s*sens[öo]r[üu]",
        r"rain\s*sensor"
    ],
    "Işık/far sensörü": [
        r"(?:far|[ıi][şs][ıi]k)\s*sens[öo]r[üu]",
        r"light\s*sensor"
    ],
    "Karartılmış arka camlar (Privacy Glass)": [
        r"karart[ıi]lm[ıi][şs]\s*arka\s*cam",
        r"privacy\s*glass|tinted\s*rear\s*window"
    ],
    "Isıtmalı ön cam": [
        r"[ıi]s[ıi]tmal[ıi]\s*[öo]n\s*cam",
        r"heated\s*windshield|heated\s*windscreen"
    ],
    "Isıtmalı arka cam": [
        r"[ıi]s[ıi]tmal[ıi]\s*arka\s*cam",
        r"heated\s*rear\s*window"
    ],
    "Panoramik cam tavan": [
        r"panoramik\s*cam\s*tavan",
        r"panoramic\s*(?:glass\s*)?roof"
    ],
    "Açılır cam tavan (Sunroof)": [
        r"a[cç][ıi]l[ıi]r\s*cam\s*tavan",
        r"sun\s*roof|sunroof"
    ],
    "Tavan rayları (Roof Rails)": [
        r"tavan\s*ray",
        r"roof\s*rail"
    ],

    # -- İÇ MEKÂN / KONFOR --
    "Ön koltuk ısıtma": [
        r"[öo]n\s*koltuk\s*[ıi]s[ıi]tma",
        r"heated\s*front\s*seat"
    ],
    "Arka koltuk ısıtma": [
        r"arka\s*koltuk\s*[ıi]s[ıi]tma",
        r"heated\s*rear\s*seat"
    ],
    "Direksiyon ısıtma": [
        r"direksiyon\s*[ıi]s[ıi]tma",
        r"heated\s*steering"
    ],
    "Elektrikli sürücü/ön koltuk": [
        r"elektrik(?:li)?\s*(?:s[üu]r[üu]c[üu]|[öo]n)\s*koltuk",
        r"power\s*(?:driver|front)\s*seat"
    ],
    "Hafızalı sürücü koltuğu": [
        r"haf[ıi]zal[ıi]\s*s[üu]r[üu]c[üu]\s*koltuk",
        r"memory\s*driver\s*seat"
    ],
    "Masaj fonksiyonlu koltuk": [
        r"masaj\s*fonksiyonu?\s*koltuk",
        r"seat\s*massage"
    ],
    "Ön kol dayama": [
        r"[öo]n\s*kol\s*dayama",
        r"front\s*armrest|center\s*armrest"
    ],
    "Arka kol dayama": [
        r"arka\s*kol\s*dayama",
        r"rear\s*armrest"
    ],
    "Arka havalandırma ızgaraları": [
        r"arka\s*hava(?:land[ıi]rma)?\s*[ıi]zgara",
        r"rear\s*air\s*vent"
    ],
    "Çift bölgeli otomatik klima": [
        r"[çc][ıi]ft\s*b[öo]lgeli\s*klima",
        r"dual\s*zone\s*(?:auto(?:matic)?\s*)?climate"
    ],
    "Üç bölgeli klima": [
        r"[üu][çc]\s*b[öo]lgeli\s*klima|3\s*zone",
        r"tri-?zone\s*climate"
    ],
    "Hava kalitesi sensörü": [
        r"hava\s*kalites[ıi]\s*sens[öo]r",
        r"air\s*quality\s*sensor"
    ],
    "Toz/Polen filtresi": [
        r"(?:toz|polen)\s*f[ıi]ltres[ıi]",
        r"pollen\s*filter|pm\s*2\.?5"
    ],
    "Ambiyans aydınlatma": [
        r"ambi?yans\s*ayd[ıi]nlatma",
        r"ambient\s*light"
    ],
    "LED iç aydınlatma": [
        r"led\s*[ıi][çc]\s*ayd[ıi]nlatma",
        r"interior\s*led\s*light"
    ],
    "Ön elektrikli camlar": [
        r"[öo]n\s*elektrik(?:li)?\s*cam",
        r"front\s*power\s*window"
    ],
    "Arka elektrikli camlar": [
        r"arka\s*elektrik(?:li)?\s*cam",
        r"rear\s*power\s*window"
    ],
    "Tek dokunuş cam (One-touch)": [
        r"tek\s*dokunu[şs]\s*cam",
        r"one-?touch\s*window"
    ],
    "Cam sıkışma önleyici (Anti-pinch)": [
        r"cam\s*s[ıi]k[ıi][şs]ma\s*[öo]nleyici",
        r"anti\s*pinch"
    ],

    # -- MULTİMEDYA / BAĞLANTILAR / GÖSTERGE --
    "Dijital gösterge paneli (Virtual Cockpit)": [
        r"dijital\s*g[öo]sterge",
        r"virtual\s*cockpit|sanal\s*kokpit"
    ],
    "Head-up display (HUD)": [
        r"head\s*[-\s]?up\s*display",
        r"\bhud\b"
    ],
    "Büyük dokunmatik ekran": [
        r"dokunmatik\s*ekran",
        r"touch\s*screen|touchscreen"
    ],
    "Navigasyon sistemi": [
        r"navigasyon\s*sistem[ıi]",
        r"navigation\s*system|satnav"
    ],
    "Apple CarPlay": [
        r"apple\s*car\s*play|carplay",
        r"\bcarplay\b"
    ],
    "Android Auto": [
        r"android\s*auto"
    ],
    "Kablosuz Apple CarPlay/Android Auto": [
        r"kablosuz\s*(?:apple\s*carplay|android\s*auto)",
        r"wireless\s*(?:carplay|android\s*auto)"
    ],
    "Bluetooth": [
        r"\bbluetooth\b"
    ],
    "USB-C": [
        r"\busb-?c\b"
    ],
    "USB-A": [
        r"\busb-?a\b"
    ],
    "AUX giriş": [
        r"\baux\b",
        r"aux(?:iliary)?\s*input"
    ],
    "Kablosuz şarj (Qi)": [
        r"kablosuz\s*[şs]arj",
        r"\bqi\b",
        r"wireless\s*charg"
    ],
    "DAB dijital radyo": [
        r"\bdab\b",
        r"digital\s*radio"
    ],
    "Ses sistemi": [
        r"ses\s*sistemi",
        r"sound\s*system|audio\s*system"
    ],
    "CANTON ses sistemi": [
        r"\bcanton\b",
        r"canton\s*(?:ses|sound)"
    ],
    "Bolero multimedya": [
        r"\bbolero\b"
    ],
    "Amundsen navigasyon": [
        r"\bamundsen\b"
    ],
    "Columbus navigasyon": [
        r"\bcolumbus\b"
    ],
    "Sesli komut": [
        r"sesli\s*komut",
        r"voice\s*control"
    ],
    "eSIM / Online hizmetler (Škoda Connect)": [
        r"\besim\b|skoda\s*connect",
        r"onl[ıi]ne\s*h[ıi]zmet|online\s*service"
    ],
    "Sürüş bilgisayarı / Yol bilgisayarı (MFA)": [
        r"(?:s[üu]r[üu][şs]|yol)\s*bilgisayar[ıi]",
        r"trip\s*computer|multi-?function\s*display|mfa"
    ],

    # -- GÜVENLİK SİSTEMLERİ / SÜRÜŞ DİNAMİĞİ --
    "ABS (kilitlenme önleyici fren)": [
        r"\babs\b",
        r"kilitlenme\s*[öo]nleyici\s*fren"
    ],
    "EBD (Elektronik fren gücü dağıtımı)": [
        r"\bebd\b",
        r"electronic\s*brake\s*force"
    ],
    "EBA/BAS (Acil fren destek)": [
        r"\beba\b|\bbas\b",
        r"ac[ıi]l\s*fren\s*destek|brake\s*assist"
    ],
    "ASR/TCS (Çekiş kontrol sistemi)": [
        r"\basr\b|\btcs\b",
        r"[çc]eki[şs]\s*kontrol"
    ],
    "ESP/ESC (Elektronik denge/stabilite)": [
        r"\besp\b|\besc\b",
        r"elektronik\s*(?:denge|stabilite)"
    ],
    "XDS/XDS+": [
        r"\bxds\+?\b",
        r"electronic\s*diff(?:erential)?\s*lock"
    ],
    "Lastik basınç izleme (TPMS)": [
        r"lastik\s*bas[ıi]n[cç]\s*(?:izleme|kontrol)",
        r"\btpms\b|tire\s*pressure"
    ],
    "Dört çeker (AWD/4x4)": [
        r"(?:4x4|awd|all\s*wheel\s*drive|d[öo]rt\s*[çc]eker)"
    ],
    "Sürüş modları (Drive Mode Select)": [
        r"s[üu]r[üu][şs]\s*mod(?:lar[ıi])?",
        r"drive\s*mode\s*select|mode\s*seçimi|drive\s*select"
    ],
    "Adaptif süspansiyon (DCC)": [
        r"adaptif\s*s[üu]spansiyon",
        r"\bdcc\b|dynamic\s*chassis\s*control"
    ],
    "Spor süspansiyon": [
        r"spor\s*s[üu]spansiyon",
        r"sport\s*suspension"
    ],
    "Diferansiyel kilidi": [
        r"diferansiyel\s*kilit",
        r"diff(?:erential)?\s*lock"
    ],

    # -- AKTARMA / FREN / KUMANDA --
    "Elektronik park freni (EPB)": [
        r"elektronik\s*park\s*fren[ıi]",
        r"\bepb\b|electric\s*parking\s*brake"
    ],
    "Auto Hold": [
        r"auto\s*hold",
        r"otomatik\s*tutu[şs]"
    ],
    "Start/Stop sistemi": [
        r"start\s*\/?\s*stop\s*sistem[ıi]?",
        r"motor\s*dur-?kalk|stop-?start"
    ],
    "Paddle shifter (Direksiyon kulakçıkları)": [
        r"(?:vites|direksiyon)\s*kulak[cç][ıi]k",
        r"paddle\s*shift(?:er)?"
    ],

    # -- TEKER/JANT/LASTİK --
    "Alaşım jantlar": [
        r"ala[sş][ıi]m\s*jant",
        r"alloy\s*wheel"
    ],
    "Çelik jantlar": [
        r"[çc]elik\s*jant",
        r"steel\s*wheel"
    ],
    "Yedek lastik": [
        r"yedek\s*lastik",
        r"spare\s*(?:wheel|tire|tyre)"
    ],
    "Lastik tamir kiti": [
        r"lastik\s*tamir\s*kit",
        r"tyre|tire\s*repair\s*kit"
    ],
    "Runflat lastikler": [
        r"run-?flat",
        r"\brft\b"
    ],

    # -- BAGAJ / PRATİKLİK --
    "Elektrikli bagaj kapağı": [
        r"elektrik(?:li)?\s*bagaj\s*kapa[ğg][ıi]",
        r"power\s*(?:tailgate|liftgate)"
    ],
    "Eller serbest bagaj (Virtual Pedal)": [
        r"ayak(?:la)?\s*a[cç]ma|virtual\s*pedal",
        r"hands-?free\s*(?:tailgate|access)"
    ],
    "Bagaj bölmesi aydınlatma": [
        r"bagaj\s*ayd[ıi]nlatma",
        r"trunk\s*light|cargo\s*light"
    ],
    "Bagaj filesi / Cargo net": [
        r"bagaj\s*files[ıi]",
        r"cargo\s*net|trunk\s*net"
    ],
    "Bagaj kancaları": [
        r"bagaj\s*kanca",
        r"cargo\s*hook"
    ],
    "Çift taraflı/katlı bagaj zemini": [
        r"bagaj\s*zemin[ıi]\s*(?:[çc][ıi]ft\s*y[öo]nl[üu]|[çc][ıi]ft\s*katl[ıi])",
        r"(?:double|dual)\s*(?:sided|floor)\s*(?:trunk|cargo)"
    ],
    "12V priz (bagaj/ön)": [
        r"12\s*v\s*pr[ıi]z|12v\s*socket|power\s*outlet"
    ],
    "230V priz": [
        r"230\s*v\s*pr[ıi]z|230v\s*socket|household\s*socket"
    ],

    # -- İÇ TRİM / DÖŞEME / DİREKSİYON --
    "Deri direksiyon": [
        r"deri\s*direksiyon",
        r"leather\s*steering"
    ],
    "Spor (çok fonksiyonlu) direksiyon": [
        r"(?:spor|[çc]ok\s*fonksiyonlu)\s*direksiyon",
        r"(?:sport|multi-?function)\s*steering"
    ],
    "Deri koltuklar": [
        r"deri\s*koltuk",
        r"leather\s*seat"
    ],
    "Alcantara/mikrofiber döşeme": [
        r"alcantara|mikro\s*fiber|mikrofiber",
        r"microfibre|microfiber"
    ],
    "Aydınlatmalı kapı eşikleri": [
        r"ayd[ıi]nlatmal[ıi]\s*kap[ıi]\s*e[sş][ıi][ğg][iı]",
        r"illuminated\s*door\s*sill"
    ],
    "Deri vites topuzu": [
        r"deri\s*vites",
        r"leather\s*gear\s*(?:lever|knob)"
    ],

    # -- ÇOCUK / KONFOR EKLERİ --
    "Çocuk kilidi": [
        r"[çc]ocuk\s*kilidi",
        r"child\s*lock"
    ],
    "Arka kapı güneş perdeleri": [
        r"arka\s*kap[ıi]\s*perde",
        r"rear\s*sun\s*blind|rear\s*sunblind"
    ],
    "Arka cam güneş perdesi": [
        r"arka\s*cam\s*perde",
        r"rear\s*window\s*blind"
    ],
    "Soğutmalı torpido": [
        r"so[gğ]utmal[ıi]\s*torpido",
        r"cooled\s*glove\s*box|glovebox"
    ],
    "Aydınlatmalı torpido": [
        r"ayd[ıi]nlatmal[ıi]\s*torpido",
        r"illuminated\s*glove\s*box|glovebox"
    ],

    # -- ANAHTARSIZ ERİŞİM / ALARM --
    "Anahtarsız giriş (Keyless Entry)": [
        r"anahtar(?:s[ıi]z)\s*giri[şs]",
        r"keyless\s*entry",
        r"\bkessy\b"
    ],
    "Anahtarsız çalıştırma (Push Start)": [
        r"anahtar(?:s[ıi]z)?\s*[çc]al[ıi][şs]t[ıi]rma",
        r"(?:start\s*stop|push\s*button)\s*(?:d[üu][ğg]me|start)"
    ],
    "Merkezi kilit (uzaktan kumandalı)": [
        r"merkezi\s*kilit",
        r"central\s*locking"
    ],
    "Hırsızlık alarmı": [
        r"h[ıi]rs[ıi]zl[ıi]k\s*alarm[ıi]",
        r"theft\s*alarm|anti-?theft"
    ],
    "Immobilizer": [
        r"immobilizer|immobiliser"
    ],

    # -- EV ÖZEL / ŞARJ --
    "AC şarj (On-board charger)": [
        r"\bac\s*[şs]arj\b",
        r"on-?board\s*charger|onboard\s*charger"
    ],
    "DC hızlı şarj": [
        r"\bdc\s*h[ıi]zl[ıi]\s*[şs]arj",
        r"dc\s*fast\s*charg"
    ],
    "Isı pompası": [
        r"[ıi]s[ıi]\s*pompa",
        r"heat\s*pump"
    ],
    "Tip 2 şarj kablosu": [
        r"tip\s*2\s*kablo",
        r"type\s*2\s*cable"
    ],

    # -- SIMPLY CLEVER (Škoda) --
    "Kapı içi şemsiye": [
        r"kap[ıi]\s*[iı]ci\s*şemsiye|kap[ıi]\s*[iı]çi\s*şemsiye",
        r"umbrella\s*in\s*door"
    ],
    "Yakıt kapağında buz kazıyıcı": [
        r"yak[ıi]t\s*kapa[gğ][ıi]nda\s*buz\s*kaz[ıi]y[ıi]c[ıi]",
        r"ice\s*scraper\s*fuel"
    ],
    "Kapı içi çöp kutusu": [
        r"(?:kap[ıi]\s*[iı]ci|kap[ıi]\s*[iı]çi)\s*[çc][öo]p\s*kutus[uu]",
        r"door\s*waste\s*bin|trash"
    ],
    "Tablet/telefon tutucu": [
        r"tablet|telefon\s*tutucu",
        r"(?:tablet|phone)\s*holder"
    ],
}
# Hız için derlenmiş regex
FEATURE_INDEX = [(canon, [re.compile(p, re.I) for p in pats]) for canon, pats in FEATURE_SYNONYMS.items()]

def canonicalize_feature(name: str) -> tuple[str, str]:
    """
    Donanım satır adını kanonik anahtara çevirir.
    Dönüş: (feature_key, display_name)
    feature_key: tablo birleştirmede kullanılan anahtar
    display_name: tabloda gösterilecek okunur metin
    """
    raw = (name or "").strip()
    norm = normalize_tr_text(raw).lower()
    # 1) Regex eşleşmesi
    for canon, pats in FEATURE_INDEX:
        if any(p.search(norm) for p in pats):
            return canon, canon   # anahtar = gösterim
    # 2) Fuzzy yedek (varsa çok yakın başlıkla eşle)
    import difflib
    best = difflib.get_close_matches(norm, [normalize_tr_text(c).lower() for c in FEATURE_SYNONYMS.keys()], n=1, cutoff=0.88)
    if best:
        # best değeri normalize halde; orijinal kanonik stringi bulalım
        for canon in FEATURE_SYNONYMS.keys():
            if normalize_tr_text(canon).lower() == best[0]:
                return canon, canon
    # 3) Son çare: normalize adı anahtar yap, orijinali göster
    return norm, raw

def clean_city_name(raw: str) -> str:
    """
    'Fabia İzmir'     → 'İzmir'
    'elroqla ankara'  → 'Ankara'
    'kodiaq ile izmir'→ 'İzmir'
    """
    if not raw:
        return ""

    # normalize + tokenle
    txt = normalize_tr_text(raw).lower()
    toks = re.findall(r"[0-9a-zçğıöşü]+", txt)

    # ekleri kırp + model tokenlarını at
    kept = []
    for w in toks:
        w2 = strip_tr_suffixes(w)          # elroqla -> elroq
        if w2 in ASSISTANT_NAMES:
            continue
        kept.append(w2)

    out = " ".join(kept).strip()
    return out.title()

TWO_LOC_PAT = (
    r"([a-zçğıöşü\s]+?)\s*"
    r"(?:ile|ve|,|-|dan|den|tan|ten)?\s+"
    r"([a-zçğıöşü\s]+?)\s*"
    r"(?:arası|arasında)?\s*"
    r"(?:kaç\s+km|kaç\s+saat|ne\s+kadar\s+sürer|mesafe|sürer|kaç\s+şarj(?:la|ile)?|kaç\s+defa\s+şarj)"
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
    'fiyatı ne kadar', 'menzili kaç km' gibi gerçek soruları
    ASLA kısa cevap sayma.
    """
    if not msg:
        return False

    msg = msg.strip().lower()
    msg_clean = re.sub(r"[^\w\sçğıöşü]", "", msg)
    # ✅ yıl + trim / donanım cevabı: short-reply sayma
    if re.search(r"\b20\d{2}\b", msg_clean):
        return False

    # ✅ trim kelimesi içeriyorsa short-reply sayma (premium/prestige vs.)
    try:
        if any(t in msg_clean.split() for t in TRIM_VARIANTS_FLAT):
            return False
    except Exception:
        pass

    # ✅ fiyat devam soruları: ASLA kısa cevap sayma (model hafızası çalışsın)
    if msg_clean in {"ne kadar", "nekadar", "kaç para", "kac para", "kaça", "kaca"}:
        return False

    # 0) Skoda alanına ait anahtar kelimeler geçiyorsa → KESİNLİKLE kısa cevap değildir
    domain_keywords = [
        "fiyat", "menzil",
        "donan", "opsiyon", "ops",
        "teknik", "özellik", "ozellik",
        "renk", "görsel", "gorsel", "resim", "foto", "fotograf", "fotoğraf",
        "motor", "tork", "güç", "guc", "beygir", "hp", "ps", "kw",
        "bagaj", "kapı", "kapi"
    ]
    if any(k in msg_clean for k in domain_keywords):
        return False

    # 1) Soru işareti varsa genelde gerçek soru → kısa cevap sayma
    if "?" in msg:
        return False

    # 2) Tam eşleşme stoplist'te mi?
    if msg_clean in CACHE_STOPWORDS:
        return True

    # 3) Çok kısa (<=3 kelime), bariz cümle öznesi/yüklem yoksa engelle
    words = msg_clean.split()
    if re.search(
        r"\b(ağırl|agirlik|kg|tork|güç|guc|beygir|hp|ps|kw|"
        r"0\s*[-–—]?\s*100|hız|hiz|maks|co2|emisyon|"
        r"tüketim|tuketim|batarya|kwh|şarj|sarj|menzil)\b",
        msg_clean
    ):
        return False
    if len(words) <= 3:
        # Cümlede özne/yüklem (örn. istiyorum, yaparım, ben, var, yok...) yoksa
        if not re.search(
            r"\b(ben|biz|sen|siz|o|yaparım|yapabilirim|alabilirim|istiyorum|olabilir|olacak|var|yok)\b",
            msg_clean
        ):
            return True

    return False


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
def normalize_tr_text_suffix(txt):
    import re
    txt = re.sub(r"\s+", " ", (txt or "").strip().lower())
    tokens = [strip_tr_suffixes(w) for w in txt.split()]
    return " ".join(tokens)

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
    import re
    text_lower = (text or "").lower()
    text_lower = re.sub(r"[_-–—-]+", " ", text_lower)   # tire/alt çizgi → boşluk
    text_lower = re.sub(r"\s+", " ", text_lower).strip()

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
import contextlib
try:
    import pyodbc
except Exception:
    pyodbc = None
_STD_KEYS = ["standart", "seri", "temel"]
_OPT_KEYS = ["opsiyonel", "opsiyon", "ops.", "ek paket", "ekstra", "aksesuar"]
PRICE_TOKENS_ROW = (
    "fiyat", "liste fiyat", "listefiyat", "anahtar teslim", "anahtar teslimi",
    "kampanya fiyat", "satış fiyat", "bedel", "ücret", "tl", "₺", "price", "listprice"
)
PRICE_TOKENS_COL = (
    "fiyat", "anahtar", "price", "listprice", "anahtar teslim"
)
KB_MISSING_PAT = re.compile(
    r"\bkb\s*['’]?\s*de\s*yok\b|\bkbde\s*yok\b",
    re.IGNORECASE
)
from modules.sql_rag import SQLRAG
# --- Basit varyant üretici (TR güvenli) ---
def _gen_variants(s: str) -> list[str]:
    s = (s or "").strip()
    if not s:
        return []
    import re, unicodedata
    def norm_tr(x: str) -> str:
        from modules.data.text_norm import normalize_tr_text
        return re.sub(r"\s+", " ", normalize_tr_text(x or "").lower()).strip()
    base = norm_tr(s)
    out = {s, base, base.replace(" ", ""), base.replace(" ", "_")}
    # 1 kelimelik kısaltımsı varyantlar için
    toks = [t for t in re.findall(r"[0-9a-zçğıöşü]+", base) if len(t) >= 2]
    if len(toks) >= 2:
        out.add(" ".join(toks[:2]))
    return list(dict.fromkeys([x for x in out if x]))
# ⬇️ Bunu importların hemen altına ekleyin (normalize_tr_text'ten önce)
def strip_tr_suffixes(word: str) -> str:
    if not word: 
        return word
    w = word.lower()
        # 🚫 Model adlarını olduğu gibi koru
    if w in ("fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"):
        return w

    suffixes = [
        "nın","nin","nun","nün",
        "dan","den","tan","ten",
        "nda","nde",
        "ına","ine","una","üne",
        "ya","ye",
        "yla","yle","la","le",
        "da","de","ta","te",
        "a","e","u","ü","ı","i",
    ]
    for suf in sorted(suffixes, key=len, reverse=True):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)]
            break

    # 🔧 Türkçe yumuşama düzeltmesi: sondaki 'ğ' köke geri dönerken 'k' olur
    if w.endswith("ğ"):
        w = w[:-1] + "k"

    # Çok görülen istisnayı garantiye al
    if w in ("ağırlığ","agırlığ"):
        w = w + "k"   # → ağırlık / agırlık

    return w
# --- Eşleştirme için parantez içini yok saymakta kullanılacak ---
_PAREN_RE = re.compile(r"\(.*?\)")

def strip_parens_for_match(s: str) -> str:
    """
    Eşleştirme amaçlı: 
    'Gözlük saklama kabı (Panoramik cam tavan ile sunulmamaktadır.)'
    → 'Gözlük saklama kabı '
    """
    return _PAREN_RE.sub("", s or "")

def lemmatize_tr_tokens(tokens: list[str]) -> list[str]:
    """
    Basit lemma helper:
    - Şimdilik strip_tr_suffixes ile kök almaya benzer bir davranış veriyor.
    - İleride gerçek bir Türkçe lemmatizer (Zemberek / Stanza) eklemek istersen
      sadece burayı değiştirmen yeterli.
    """
    return [strip_tr_suffixes(t) for t in tokens]
def embed_semantic_local(text: str) -> np.ndarray | None:
    """
    HuggingFace sentence-transformer ile yerel embedding.
    HF modeli yoksa None döner, sistem OpenAI embedding'leriyle devam eder.
    """
    if _HF_SEM_MODEL is None:
        return None
    if not text:
        return None
    vec = _HF_SEM_MODEL.encode(text, normalize_embeddings=True)  # L2-normalize
    return np.array(vec, dtype=np.float32)


FEATURE_INDEX = [(canon, [re.compile(p, re.I) for p in pats]) for canon, pats in FEATURE_SYNONYMS.items()]
# --- Teknik metrikler için LIKE kalıpları (SQL arama anahtarları) ---
_SPEC_KEYWORDS = {
    # TORK
    "tork": (
        [
            "%tork%",          # Türkçe
            "%torque%",        # İngilizce
        ],
        None
    ),

    # GÜÇ / BEYGİR
    "güç": (
        [
            "%güç%", "%guc%",
            "%beygir%", "%hp%", "%ps%",
            "%power%", "%kw%",
        ],
        None
    ),

    # 0-100 HIZLANMA
    "0-100": (
        [
            "%0-100%",
            "%0 %100%",
            "%0%100%",
        ],
        None
    ),

    # MAKSİMUM HIZ
    "maksimum hız": (
        [
            "%maks%hız%",
            "%maks%hiz%",
            "%max%speed%",
            "%top%speed%",
        ],
        None
    ),

    # MENZİL
    "menzil": (
        [
            "%menzil%",
            "%range%",
            "%WLTP%menzil%",
            "%WLTP%range%",
        ],
        None
    ),

    # CO2 / EMİSYON
    "co2": (
        [
            "%co2%",
            "%emisyon%",
            "%emission%",
        ],
        None
    ),

    # YAKIT TÜKETİMİ
    "yakıt tüketimi": (
        [
            "%tüketim%", "%tuketim%",
            "%l/100 km%", "%l/100km%",
            "%lt/100 km%",
        ],
        None
    ),
    # BATARYA (kWh)
    "batarya": (
        [
            "%batarya%",
            "%battery%",
            "%kwh%",
            "%kWh%",
            "%kapasite%",
            "%capacity%",
            "%net%",
            "%brüt%", "%brut%",
        ],
        None
    ),

    # ŞARJ (AC/DC)
    "sarj": (
        [
            "%şarj%", "%sarj%",
            "%ac%şarj%", "%ac%sarj%",
            "%dc%şarj%", "%dc%sarj%",
            "%10%80%", "%10-80%",
            "%charging%", "%charge%",
        ],
        None
    ),
    # AĞIRLIK
    "agirlik": (
        [
            "%ağırlık%", "%agirlik%",
            "%weight%",
            "%kg%",
        ],
        None
    ),
    # YAKIT DEPOSU / DEPO HACMİ
    "depo": (
        [
            "%depo%", "%depo hacmi%",
            "%yakıt%depo%", "%yakit%depo%",
            "%fuel%tank%", "%tank%",
            "%l%"  # bazı tablolarda litre birimiyle geçebiliyor
        ],
        None
    ),

}
import json, time, secrets

def _now_ms():
    return int(time.time() * 1000)

def _make_trace_id():
    return secrets.token_hex(8)

def _preview(v, limit=500):
    if v is None:
        return None
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    s = s.replace("\n", "\\n")
    return s[:limit] + ("…" if len(s) > limit else "")

def _safe(obj, max_list=8, max_str=800):
    if obj is None:
        return None
    if isinstance(obj, str):
        return {"len": len(obj), "preview": _preview(obj, max_str)}
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, dict):
        keys = list(obj.keys())
        out = {}
        for k in keys[:max_list]:
            out[str(k)] = _safe(obj[k], max_list=max_list, max_str=max_str)
        return {"keys": keys[:max_list], "more_keys": max(0, len(keys) - max_list), "sample": out}
    if isinstance(obj, (list, tuple, set)):
        lst = list(obj)
        sample = [_safe(x, max_list=max_list, max_str=max_str) for x in lst[:max_list]]
        return {"count": len(lst), "sample": sample}
    s = str(obj)
    return {"type": type(obj).__name__, "len": len(s), "preview": _preview(s, max_str)}

def _redact_params(params: dict | None):
    if not params:
        return {}
    out = {}
    for k, v in params.items():
        if isinstance(v, (list, tuple)) and len(v) > 50:
            out[k] = {"type": "list", "count": len(v)}
        elif isinstance(v, (bytes, bytearray, memoryview)):
            out[k] = {"type": "bytes", "len": len(v)}
        else:
            out[k] = v
    return out


class ChatbotAPI:
    import difflib
    import re
    import re, unicodedata
    NET_WEAK_RE = re.compile(
    r"(genellikle|değişkenlik\s*gösterebilir|netleştirebilmem|"
    r"hangi\s+donan[ıi]m|hangi\s+paket|belirtebilir\s+misiniz|"
    r"ister\s+misiniz|hangisini\s+merak|emin\s+değilim|tahmin|yaklaşık|"
    r"bilgi\s+bulunamad[ıi]|kayıt\s+yok|ulaşamıyorum)",
    re.IGNORECASE
)   

    def _preview(v, limit=500):
        if v is None:
            return None
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
        s = s.replace("\n", "\\n")
        return s[:limit] + ("…" if len(s) > limit else "")

    def _safe(obj, max_list=8, max_str=800):
        # Büyük objeleri logda patlatma: sadece özetle
        if obj is None:
            return None
        if isinstance(obj, str):
            return {"len": len(obj), "preview": _preview(obj, max_str)}
        if isinstance(obj, (int, float, bool)):
            return obj
        if isinstance(obj, dict):
            keys = list(obj.keys())
            out = {}
            for k in keys[:max_list]:
                out[str(k)] = _safe(obj[k], max_list=max_list, max_str=max_str)
            return {"keys": keys[:max_list], "more_keys": max(0, len(keys) - max_list), "sample": out}
        if isinstance(obj, (list, tuple, set)):
            lst = list(obj)
            sample = [_safe(x, max_list=max_list, max_str=max_str) for x in lst[:max_list]]
            return {"count": len(lst), "sample": sample}
        # fallback
        s = str(obj)
        return {"type": type(obj).__name__, "len": len(s), "preview": _preview(s, max_str)}

    def _redact_params(params: dict | None):
        if not params:
            return {}
        out = {}
        for k, v in params.items():
            # embedding/vector gibi devasa şeyleri loglama
            if isinstance(v, (list, tuple)) and len(v) > 50:
                out[k] = {"type": "list", "count": len(v)}
            elif isinstance(v, (bytes, bytearray, memoryview)):
                out[k] = {"type": "bytes", "len": len(v)}
            else:
                out[k] = v
        return out

    def _now_ms():
        return int(time.time() * 1000)

    def _make_trace_id():
        return secrets.token_hex(8)

    def _tlog(self, user_id: str, event: str, **fields):
        """
        PIPELINE_TRACE=1 iken JSON log basar.
        Her event'te trace_id bulunur.
        """
        if os.getenv("PIPELINE_TRACE", "0") != "1":
            return

        st = self.user_states.setdefault(user_id, {})
        trace_id = st.get("_trace_id") or "-"
        payload = {
            "ts_ms": _now_ms(),
            "trace_id": trace_id,
            "event": event,
        }

        # alanları güvenli özetle
        for k, v in fields.items():
            if k in {"cypher_params", "params"} and isinstance(v, dict):
                payload[k] = _redact_params(v)
            else:
                payload[k] = v if isinstance(v, (int, float, bool)) else _safe(v)

        try:
            self.logger.info("[PIPELINE] %s", json.dumps(payload, ensure_ascii=False))
        except Exception:
            # logger format sorunu olursa sessiz geç
            pass

        # trace_debug varsa oraya da düşür (opsiyonel)
        try:
            from modules.trace_debug import tracer
            tracer().step(event, **{k: (v if isinstance(v, (int, float, bool, str)) else str(v)) for k, v in fields.items()})
        except Exception:
            pass

    def _looks_like_trim_only_reply(self, msg: str) -> bool:
        if not msg:
            return False

        # model yazıldıysa trim-only değildir
        try:
            if self._extract_models_all(msg):
                return False
        except Exception:
            pass

        # tire/altçizgi normalize
        t = re.sub(r"[_-–—-]+", " ", (msg or "").lower())
        t = re.sub(r"\s+", " ", t).strip()

        try:
            return bool(extract_trims(t))   # senin TRIM_VARIANTS tabanlı fonksiyon
        except Exception:
            # en azından sportline/premium/prestige gibi ana kelimeler
            return bool(re.search(r"\b(premium|prestige|elite|sportline|rs|monte\s*carlo|crystal|85x|60)\b", t))

    def _answer_multi_model_spec_any(self, user_message: str, models: list[str]) -> str | None:
        # 1) SQL dene
        out = self._answer_multi_model_spec_from_sql(user_message, models)
        if out:
            return out

        # 2) Teknik MD fallback
        req = []
        try:
            req = self._find_requested_specs(user_message) or []
        except Exception:
            req = []

        # _find_requested_specs boşsa, basit map:
        if not req:
            sk = self._spec_key_from_query(user_message) or ""
            MAP = {
                "agirlik": "Ağırlık (Sürücü Dahil) (kg)",
                "bagaj": "Bagaj hacmi (dm3)",
                "boyutlar": "Uzunluk/Genişlik/Yükseklik (mm)",
                "menzil": "Menzil (WLTP)",
                "0-100": "0-100 km/h (sn)",
                "depo": "Yakıt deposu (L)", 
            }
            if sk in MAP:
                req = [MAP[sk]]

        if req and len(models) >= 2:
            # mevcut helper’ın var:
            ans = self._answer_two_model_spec_diff(models[:2], req[0])
            return ans

        return None

    def _strip_forbidden_ui_blocks(self, text: str) -> str:
        if not text:
            return text
        t = str(text)
        low = normalize_tr_text(t).lower()

        segment_labels = ["b-suv:", "suv:", "hatchback:", "sedan:", "elektrikli:", "c-suv:", "d-suv:"]
        if ("istersen" in low and "seç" in low) and sum(lbl in low for lbl in segment_labels) >= 2:
            out = []
            skipping = False
            for ln in t.splitlines():
                ln_low = normalize_tr_text(ln).lower()
                if ("istersen" in ln_low and "seç" in ln_low):
                    skipping = True
                    continue
                if skipping:
                    # blok bitişi: boş satır ya da feedback bar vs.
                    if not ln.strip():
                        skipping = False
                    continue
                if any(lbl in ln_low for lbl in segment_labels):
                    continue
                out.append(ln)
            cleaned = "\n".join(out).strip()
            return cleaned if cleaned else "Soruyu iki model üzerinden cevaplayabilmem için hangi 2 Škoda modeliyle kıyaslayayım?"

        return t


    # ChatbotAPI class içine ekle
    def _needs_model_for_domain(self, domain: str) -> bool:
        return domain in {"SPEC", "EQUIP", "PRICE", "IMAGE"}

    def _infer_domain_fast(self, msg: str) -> str:
        # Mevcut fonksiyonlarını kullan: en güvenlisi bu
        try:
            return self._infer_domain(msg)  # PRICE/EQUIP/SPEC/OTHER
        except Exception:
            pass

        # fallback
        if self._is_price_intent(msg):
            return "PRICE"
        if self._is_spec_question(msg):
            return "SPEC"
        if self._is_equipment_presence_question(msg):
            return "EQUIP"
        if self.utils.is_image_request(msg) or self._is_image_intent_local(msg):
            return "IMAGE"
        if self._is_model_recommendation_intent(msg) or self._is_product_range_intent(msg):
            return "RECO"
        return "OTHER"

    def _resolve_slots(self, user_id: str, msg: str) -> dict:
        """
        domain + model(ler) çöz.
        - Mesajda 2+ model varsa: cmp_models güncellenir, models=[m1,m2]
        - Mesajda model yoksa ve cmp_models varsa: models=[m1,m2] döner
        """
        st = self.user_states.setdefault(user_id, {})
        domain = self._infer_domain_fast(msg)

        # 1) Mesajda açık model(ler)
        try:
            models_now = self._extract_models_all(msg) or []
        except Exception:
            models_now = list(self._extract_models(msg or "")) if hasattr(self, "_extract_models") else []

        models_now = [m.strip().lower() for m in models_now if m]
        # uniq + sıra koru
        uniq = []
        for m in models_now:
            if m not in uniq:
                uniq.append(m)
        models_now = uniq

        # 1.a) Mesajda 2+ model varsa -> cmp_models güncelle
        if len(models_now) >= 2:
            st["cmp_models"] = models_now[:2]
            st["last_models"] = set(models_now[:2])   # ✅ ekle
            return {"domain": domain, "model": None, "models": models_now[:2], "ambiguous": False, "from": "msg_multi"}

        # 1.b) Mesajda 1 model varsa -> cmp_models'ı güncelle (multi moddan çıkış)
        if len(models_now) == 1:
            m = models_now[0]
            self._set_active_model(user_id, m, from_user=True)
            try:
                aid = self._assistant_id_from_model_name(m)
                if aid:
                    st["assistant_id"] = aid
            except Exception:
                pass
            st["cmp_models"] = [m]  # ✅ artık tek-model bağlam
            return {"domain": domain, "model": m, "models": [m], "ambiguous": False, "from": "msg_single"}
        # ✅ TRIM-only follow-up ise: aktif modeli kullan
        if self._looks_like_trim_only_reply(msg):
            active = (st.get("active_model") or "").strip().lower()
            last_user = (st.get("last_user_model") or "").strip().lower()

            m = active or last_user
            if m:
                # trim’i state’e de yaz (opsiyonel ama faydalı)
                try:
                    tr = list(extract_trims(re.sub(r"[_-–—-]+", " ", msg.lower())))
                    if tr:
                        st["current_trim"] = next(iter(tr))
                except Exception:
                    pass

                return {"domain": domain, "model": m, "models": [m], "ambiguous": False, "from": "trim_followup"}

        # 2) Mesajda model yok -> cmp_models var mı?
        cm = st.get("cmp_models") or []
        if isinstance(cm, (set, tuple)):
            cm = list(cm)
        cm = [str(x).strip().lower() for x in cm if str(x).strip()]
        cm = list(dict.fromkeys(cm))
        # ✅ Compare bağlamı kaybolduysa: son asistan cevabından 2 modeli geri yükle
        if len(cm) < 2:
            last_a = (st.get("last_assistant_answer") or "")
            try:
                back = self._extract_models_all(last_a) or []
            except Exception:
                back = []
            back = [b.strip().lower() for b in back if b]
            back = list(dict.fromkeys(back))
            if len(back) >= 2:
                cm = back[:2]
                st["cmp_models"] = cm[:2]
                st["last_models"] = set(cm[:2])

        # Model gerektiren domainlerde: cmp_models 2 ise multi-mode döndür
        if self._needs_model_for_domain(domain) and len(cm) >= 2:
            return {"domain": domain, "model": None, "models": cm[:2], "ambiguous": False, "from": "state_cmp"}

        # 3) Tek model gerekiyorsa eski davranış (active/last_user)
        if self._needs_model_for_domain(domain):
            active = (st.get("active_model") or "").strip().lower() or None
            last_user = (st.get("last_user_model") or "").strip().lower() or None
            m = active or last_user or (cm[0] if len(cm) == 1 else None)
            if m:
                try:
                    aid = self._assistant_id_from_model_name(m)
                    if aid:
                        st["assistant_id"] = aid
                except Exception:
                    pass
                return {"domain": domain, "model": m, "models": [m], "ambiguous": False, "from": "state_single"}

            return {"domain": domain, "model": None, "models": [], "ambiguous": True, "from": "none"}

        # 4) Model gerekmeyen domain
        return {"domain": domain, "model": None, "models": cm[:2], "ambiguous": False, "from": "none"}
    def _answer_equipment_presence_multi_models(self, user_id: str, msg_no_model: str, models: list[str]) -> str:
        """
        Aynı soruyu iki model için cevaplar (donanım var mı / hangi pakette vb.)
        """
        st = self.user_states.setdefault(user_id, {})
        # state’i koru (özellikle last_user_model)
        old_active = st.get("active_model")
        old_last_user = st.get("last_user_model")
        old_last_models = st.get("last_models")
        old_asst = st.get("assistant_id")

        outs = []
        for m in (models or [])[:2]:
            try:
                # modele göre context
                st["active_model"] = m
                # mesajı modele enjekte etmeden pipeline’ı çağır (model state’ten gelsin)
                txt = self._answer_equipment_presence_pipeline(user_id, msg_no_model) or ""
                outs.append(f"**{m.title()}**: {txt}".strip())
            except Exception as e:
                outs.append(f"**{m.title()}**: (Bu model için cevap üretilemedi: {e})")
            finally:
                # her turda assistant_id değişmesin diye geri al
                if old_asst is not None:
                    st["assistant_id"] = old_asst

        # state’i geri yükle
        st["active_model"] = old_active
        st["last_user_model"] = old_last_user
        st["last_models"] = old_last_models
        if old_asst is not None:
            st["assistant_id"] = old_asst

        return "\n\n".join(outs).strip()

    def _answer_price_multi_models(self, user_id: str, msg_no_model: str, models: list[str]) -> str:
        """
        Aynı fiyat sorusunu iki model için cevaplar (PriceList satırı / liste).
        """
        outs = []
        for m in (models or [])[:2]:
            # price_row_from_pricelist model bulmak için mesaja modeli yazmak zorunda
            md = self._price_row_from_pricelist(f"{m} {msg_no_model}".strip(), user_id=user_id)
            if md:
                outs.append(f"<b>{m.title()}:</b><br>\n{md}")
            else:
                outs.append(f"<b>{m.title()}:</b> Fiyat tablosunda bu soruya karşılık gelen satır bulunamadı.")
        return "<br><hr style='margin:12px 0;'><br>".join(outs)

    # ChatbotAPI class içine ekle
    def _get_last_user_model(self, user_id: str) -> str | None:
        st = self.user_states.get(user_id, {}) or {}
        m = (st.get("last_user_model") or "").strip().lower()
        return m or None

    def _feedback_bar_html(self, conversation_id: int) -> str:
        # Eski butonlarını kullanmak için: span -> button
        # Not: class'lara hem eski hem yeni isimleri koydum; senin eski CSS/JS hangisini arıyorsa çalışsın.
        return (
            f'<div class="dsd-feedback feedback-bar feedback-buttons" data-conv-id="{conversation_id}">'
            f'  <button type="button" class="fb-btn like like-btn btn-like" data-fb="1" title="Faydalı">👍</button>'
            f'  <button type="button" class="fb-btn dislike dislike-btn btn-dislike" data-fb="2" title="İyileştir">👎</button>'
            f'</div>'
        )
    def _feedback_buttons_html(self, conversation_id: int) -> str:
        # (Eski tarz) ikonlu butonlar – SVG ile (emoji değil)
        return f"""
    <div class="yugii-feedback" data-conv-id="{conversation_id}">
    <button type="button" class="fb-btn fb-like" onclick="yugiiSendFeedback(this,1)" aria-label="Faydalı">
        <svg viewBox="0 0 24 24" class="fb-ic" aria-hidden="true">
        <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3v11z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M7 11l4-8a2 2 0 0 1 2-1h0a2 2 0 0 1 2 2v5h3.5a2 2 0 0 1 2 2l-1 9a2 2 0 0 1-2 2H7V11z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    </button>

    <button type="button" class="fb-btn fb-dislike" onclick="yugiiSendFeedback(this,2)" aria-label="Faydalı değil">
        <svg viewBox="0 0 24 24" class="fb-ic" aria-hidden="true">
        <path d="M17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3V2z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M17 13l-4 8a2 2 0 0 1-2 1h0a2 2 0 0 1-2-2v-5H3.5a2 2 0 0 1-2-2l1-9a2 2 0 0 1 2-2H17v11z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    </button>
    </div>
    """


    def _feedback_marker(self, conversation_id: int) -> bytes:
        html = (
            self._feedback_bar_html(conversation_id)
            + f'<span class="conv-marker" data-conv-id="{conversation_id}" style="display:none"></span>'
        )
        return html.encode("utf-8")


    def _wrap_stream_with_feedback(self, gen, *, user_id: str, user_message: str, username: str):
        buf = []
        try:
            for chunk in gen:
                if chunk is None:
                    continue
                if not isinstance(chunk, (bytes, bytearray)):
                    chunk = str(chunk).encode("utf-8")

                try:
                    chunk = self._sanitize_bytes(chunk)
                except Exception:
                    pass

                buf.append(chunk)
                yield chunk
        finally:
            try:
                full_answer = b"".join(buf).decode("utf-8", errors="ignore")
                # ✅ FINAL çıktıyı logla
                try:
                    self._tlog(user_id, "USER_DELIVERED",
                            user_message=user_message,
                            final_answer=full_answer,
                            answer_source=(self.user_states.get(user_id, {}) or {}).get("answer_source"),
                            answer_source_meta=(self.user_states.get(user_id, {}) or {}).get("answer_source_meta"))
                except Exception:
                    pass
                # ✅ STATE GÜNCELLE (kritik)
                st = self.user_states.setdefault(user_id, {})
                st["last_user_message"] = user_message
                st["last_assistant_answer"] = full_answer
                try:
                    hist = session.get("skoda_chat_history", [])
                    hist.append({"role": "user", "content": user_message})
                    hist.append({"role": "assistant", "content": full_answer})
                    session["skoda_chat_history"] = hist[-12:]
                except Exception as _e:
                    pass
                # (opsiyonel) aktif modeli cevaptan güncelle
                try:
                    self._update_active_model_from_answer(user_id, user_message, full_answer)
                except Exception:
                    pass

                conv_id = save_to_db(user_id, user_message, full_answer, username=username)

                yield self._feedback_marker(conv_id)

            except Exception as e:
                try:
                    self.logger.error(f"[FEEDBACK-WRAP] save/state failed: {e}")
                except Exception:
                    pass
                return



    def _respond_one_shot_with_feedback(self, *, user_id: str, user_message: str, username: str, body: str | bytes):
        """
        Deterministik tek cevaplar için: (EquipmentList/Neo4j/trip/tdi vs.)
        """
        def gen():
            if isinstance(body, (bytes, bytearray)):
                yield body
            else:
                yield self._deliver_locally(body=body, original_user_message=user_message, user_id=user_id)

        wrapped = self._wrap_stream_with_feedback(
            gen(),
            user_id=user_id,
            user_message=user_message,
            username=username
        )
        return self.app.response_class(
            stream_with_context(wrapped),
            mimetype="text/html; charset=utf-8",
        )

    def _answer_equipment_presence_pipeline(self, user_id: str, user_message: str) -> str:
        """
        Yeni akış:
        EquipmentList(SQL) -> (yoksa) Neo4j(vector)->LLM
        Neo4j yoksa: sabit 'bulunmamaktadır' (opsiyonel asistan fallback)
        """
        # 1) Önce EquipmentList (SQL) – deterministik
        txt, final, meta = self._answer_equipment_presence_strict(user_id, user_message, return_meta=True)

        # Model yoksa vs. final cevap -> direkt dön
        if final and meta.get("reason") == "need_model":
            self._set_answer_source(user_id, "equip_need_model")
            return txt

        # EquipmentList bulduysa -> direkt dön
        if final and meta.get("found"):
            self._set_answer_source(user_id, "equipmentlist_sql", **meta)
            return txt

        # 2) EquipmentList bulamadı -> Neo4j fallback açık mı?
        if not getattr(self, "ENABLE_EQUIP_NEO4J_FALLBACK", True):
            self._set_answer_source(user_id, "equip_missing_no_neo4j_fallback", **(meta or {}))
            return "Bu modelde istediğiniz özellik bulunmamaktadır."

        # 3) Neo4j hazır mı?
        if not self._neo4j_ready():
            self._set_answer_source(user_id, "equip_missing_neo4j_not_ready", **(meta or {}))

            # İstersen Neo4j yokken assistant opsiyonel fallback
            if getattr(self, "EQUIP_ASSISTANT_IF_NO_NEO4J", False):
                try:
                    asst = self._fallback_via_assistant(user_id, user_message, reason="EQUIP_NO_NEO4J_OPTIONAL")
                    asst = (asst or "").strip()
                    # Zayıf/kaçamaksa sabite dön
                    if asst and (not self._is_answer_weak_global(user_message, asst)):
                        self._set_answer_source(user_id, "assistant_equip_no_neo4j", **(meta or {}))
                        return asst
                except Exception as e:
                    try:
                        self.logger.error(f"[EQUIP][ASSISTANT-OPT] failed: {e}")
                    except Exception:
                        pass

            return "Bu modelde istediğiniz özellik bulunmamaktadır."

        # 4) Neo4j (vector search) -> LLM (senin mevcut neo4j_rag/neo4j_graphrag answer() zaten bunu yapıyor)
        neo = ""
        try:
            neo = (self._answer_via_neo4j_only(user_id, user_message) or "").strip()
        except Exception as e:
            try:
                self.logger.error(f"[EQUIP][NEO4J] answer failed: {e}")
            except Exception:
                pass
            neo = ""

        # Neo4j cevabı güçlü ise dön
        if neo and (not self._is_answer_weak_global(user_message, neo)) and (not self._is_negative_kb_answer(neo)):
            self._set_answer_source(user_id, "neo4j_equip_rag", **(meta or {}))
            return neo

        # Neo4j'de de yoksa: sabit mesaj
        self._set_answer_source(user_id, "equip_missing_after_neo4j", **(meta or {}))
        return "Bu modelde istediğiniz özellik bulunmamaktadır."

    def _neo4j_ready(self) -> bool:
        """
        Neo4j ayağa kalktı mı? (cache'li)
        verify_connectivity pahalı olabileceği için TTL ile cache'lenir.
        """
        ttl = float(os.getenv("NEO4J_HEALTH_TTL", "15"))  # saniye
        now = time.time()

        h = getattr(self, "_neo4j_health", None) or {"ok": False, "ts": 0.0}
        if (now - float(h.get("ts", 0.0))) < ttl:
            return bool(h.get("ok", False))

        ok = False
        drv = getattr(self, "neo4j_driver", None)
        if drv:
            try:
                drv.verify_connectivity()
                ok = True
            except Exception as e:
                try:
                    self.logger.warning(f"[NEO4J] connectivity failed: {e}")
                except Exception:
                    pass
                ok = False

        self._neo4j_health = {"ok": ok, "ts": now}
        return ok

    def _neo4j_history(self, user_id: str):
        st = (self.user_states.get(user_id, {}) or {})

        # ✅ 1) Session’dan gelen history varsa onu kullan
        hist = st.get("neo4j_chat_history")
        if isinstance(hist, list) and hist:
            return hist

        # ✅ 2) fallback: son 1 tur
        if st.get("last_user_message") and st.get("last_assistant_answer"):
            return [
                {"role": "user", "content": st["last_user_message"]},
                {"role": "assistant", "content": st["last_assistant_answer"]},
            ]
        return []


    def _is_equipment_question_soft(self, user_id: str, text: str) -> bool:
        if not text:
            return False

        # Donanım değilse hiç bulaşma
        if self._is_price_intent(text):
            return False
        if self._is_trip_calc_question(text):
            return False
        if self.utils.is_image_request(text) or self._is_image_intent_local(text):
            return False
        if self._is_spec_question(text):
            return False

        t = normalize_tr_text(text).lower()

        # klasik donanım sinyalleri
        if self._is_equipment_presence_question(text):
            return True

        if any(k in t for k in [
            "donanım","donanim","opsiyonel","standart","paket",
            "hangi paket","hangi donanım","hangi donanim",
            "hangi versiyon","hangi versiyonda",
            "sunuluyor","mevcut","geliyor"
        ]):
            return True

        # FEATURE_SYNONYMS regex’lerinden birine yakalanırsa donanım say
        try:
            for _canon, pats in FEATURE_INDEX:
                if any(p.search(t) for p in pats):
                    return True
        except Exception:
            pass

        # Model biliniyorsa HF semantik ile “donanım olabilir” kanıtı
        try:
            model = self._current_model(user_id, text)
        except Exception:
            model = None

        if model and _HF_SEM_MODEL is not None:
            try:
                hits = self._semantic_feature_match_equipment(model, text, topn=1) or []
                if hits and float(hits[0].get("score") or 0.0) >= float(os.getenv("EQUIP_EVIDENCE_SIM_MIN", "0.70")):
                    return True
            except Exception:
                pass

        return False


    def _answer_via_neo4j_only(self, user_id: str, user_message: str) -> str:
        msg = (user_message or "").strip()
        if not msg:
            return ""
        # graphrag çağrısından hemen önce
        self.neo4j_graphrag._current_user_id = user_id

        self._tlog(user_id, "NEO4J_ONLY_START", question=msg)

        hist = self._neo4j_history(user_id)
        self._tlog(user_id, "NEO4J_HISTORY", history=hist)

        # 1) neo4j_graphrag
        try:
            if getattr(self, "neo4j_graphrag", None) and self.neo4j_graphrag.enabled:
                self._tlog(user_id, "NEO4J_GRAPHRAG_CALL", question=msg)
                out = self.neo4j_graphrag.answer(msg, chat_history=hist) or ""
                out = out.strip()
                self._tlog(user_id, "NEO4J_GRAPHRAG_RETURN", answer=out)
                if out:
                    self._set_answer_source(user_id, "neo4j_graphrag")
                    return out
        except Exception as e:
            self._tlog(user_id, "NEO4J_GRAPHRAG_ERROR", error=str(e))

        # 2) neo4j_rag fallback
        try:
            if getattr(self, "neo4j_rag", None) and self.neo4j_rag.enabled:
                self._tlog(user_id, "NEO4J_RAG_CALL", question=msg)
                out = self.neo4j_rag.answer(msg, chat_history=hist) or ""
                out = out.strip()
                self._tlog(user_id, "NEO4J_RAG_RETURN", answer=out)
                if out:
                    self._set_answer_source(user_id, "neo4j_rag")
                    return out
        except Exception as e:
            self._tlog(user_id, "NEO4J_RAG_ERROR", error=str(e))

        self._tlog(user_id, "NEO4J_ONLY_EMPTY")
        return ""


    # ============================================================
# ✅ Assistants (beta.threads) - SAĞLAM ÇAĞRI KATMANI
# ============================================================
    def _set_answer_source(self, user_id: str, src: str, **meta):
        st = self.user_states.setdefault(user_id, {})
        st["answer_source"] = src
        st["answer_source_meta"] = meta
        try:
            self.logger.info(f"[ANSWER-SRC] user_id={user_id} src={src} meta={meta}")
        except Exception:
            pass


    def _company_person_from_neo4j(self, q: str) -> dict | None:
        rows = self._neo4j_read("""
            MATCH (p:Person)
            WHERE toLower(p.username)=toLower($q) OR toLower(p.name)=toLower($q)
            OPTIONAL MATCH (p)-[:WORKS_IN]->(d:Department)
            OPTIONAL MATCH (p)-[:REPORTS_TO]->(m:Person)
            RETURN p{.*, department:d.name, manager:m.name} AS person
            LIMIT 1
        """, {"q": q})
        if not rows:
            return None
        return rows[0].get("person")

    def _neo4j_read(self, cypher: str, params: dict | None = None) -> list[dict]:
        if not self.neo4j_driver:
            return []
        params = params or {}
        try:
            with span("NEO4J", "execute_query", cypher=cypher, params=params):
                records, summary, keys = self.neo4j_driver.execute_query(
                    cypher,
                    database_=self.NEO4J_DB,
                    **params
                )
            try:
                tracer().step("NEO4J_READ_DONE", rows=len(records))
            except Exception:
                pass

            return [r.data() for r in records]
        except Exception as e:
            try:
                self.logger.error(f"[NEO4J] read error: {e}")
            except Exception:
                pass
            return []

    def _neo4j_write(self, cypher: str, params: dict | None = None) -> bool:
        if not self.neo4j_driver:
            return False
        params = params or {}
        try:
            # ✅ Trace: execute_query (write) çağrısını yakala
            with span("NEO4J", "execute_query_write", cypher=cypher, params=params):
                self.neo4j_driver.execute_query(
                    cypher,
                    database_=self.NEO4J_DB,
                    **params
                )
            try:
                tracer().step("NEO4J_WRITE_DONE", ok=True)
            except Exception:
                pass

            return True
        except Exception as e:
            try:
                self.logger.error(f"[NEO4J] write error: {e}")
            except Exception:
                pass
            return False

    def _ask_assistant_net(
        self,
        *,
        user_id: str,
        assistant_id: str,
        user_message: str,
        timeout: float = 60.0,
        instructions_override: str | None = None,
        tool_resources_override: dict | None = None,
        ephemeral: bool = False,
    ) -> str:
        """
        Geriye dönük uyumluluk:
        Eski kodların çağırdığı _ask_assistant_net(...) -> yeni _ask_assistant wrapper'ına yönlenir.
        """
        return self._ask_assistant(
            user_id=user_id,
            assistant_id=assistant_id,
            content=user_message,
            timeout=timeout,
            instructions_override=instructions_override,
            tool_resources_override=tool_resources_override,
            ephemeral=ephemeral,
        )

    def _fallback_via_assistant(self, user_id: str, user_message: str, reason: str = "") -> str:
        """
        Beta threads assistant fallback (tek gerçek kaynak burası olsun).
        """
        hist = self._neo4j_history(user_id)  # ✅ en başa
        if os.getenv("NEO4J_ONLY","0") == "1":
            out = self._answer_via_neo4j_only(user_id, user_message)
            return out or "Bu bilgi Neo4j bilgi tabanında bulunamadı."
        try:
            if getattr(self, "neo4j_rag", None) and self.neo4j_rag.enabled:
                if not self._mentions_non_skoda(user_message):

                    out = self.neo4j_rag.answer(user_message, chat_history=hist)
                    if out and "Bu bilgi KB’de yok" not in out:
                        self._set_answer_source(user_id, "neo4j_rag")  # ✅ EKLE
                        return out
        except Exception as e:
            self.logger.error(f"[NEO4J-RAG] fallback failed: {e}")

        # buradan sonra Assistant'a düşüyor
        self._set_answer_source(user_id, "assistant_fallback")  # ✅ EKLE
        # _fallback_via_assistant() en başına ekle:
        try:
            if getattr(self, "neo4j_rag", None) and self.neo4j_rag.enabled:
                if not self._mentions_non_skoda(user_message):
                    hist = []
                    st = self.user_states.get(user_id, {}) or {}
                    if st.get("last_user_message") and st.get("last_assistant_answer"):
                        hist = [(st["last_user_message"], st["last_assistant_answer"])]

                    out = self.neo4j_rag.answer(user_message, chat_history=hist)
                    if out and "Bu bilgi KB’de yok" not in out:
                        return out
        except Exception as e:
            self.logger.error(f"[NEO4J-RAG] fallback failed: {e}")

        try:
            st = self.user_states.get(user_id, {}) or {}
            asst_id = st.get("assistant_id")

            if not asst_id:
                # varsa kendi chooser'ların
                if hasattr(self, "_pick_assistant_for_message"):
                    asst_id = self._pick_assistant_for_message(user_id, user_message)
                if not asst_id and hasattr(self, "_pick_least_busy_assistant"):
                    asst_id = self._pick_least_busy_assistant()

                if asst_id:
                    self.user_states.setdefault(user_id, {})["assistant_id"] = asst_id

            if not asst_id:
                return "Hemen yardımcı olayım 😊 Hangi Škoda modelini sorduğunuzu yazar mısınız?"

            # Beta threads runner
            out = self.assistant_runner.ask(
                user_states=self.user_states,
                user_id=user_id,
                assistant_id=asst_id,
                content=user_message,
                timeout=60.0,
                instructions_override=None,
                tool_resources_override=None,
                ephemeral=False
            ) or ""

            return out.strip() or "Hemen yardımcı olayım 😊 Hangi Škoda modelini sorduğunuzu yazar mısınız?"

        except Exception as e:
            try:
                self.logger.error(f"[fallback_via_assistant] failed reason={reason} err={e}")
            except Exception:
                pass
            return "Hemen yardımcı olayım 😊 Hangi Škoda modelini sorduğunuzu yazar mısınız?"

    def _fallback_via_chat(self, user_id: str, user_message: str, reason: str = "") -> str:
        """
        Eski isim: _fallback_via_chat
        Yeni sistemde sizde bazen _fallback_via_assistant / _ask_assistant_net / assistant_runner.ask var.
        Bu wrapper, hangisi varsa onu çağırır. Hiçbiri yoksa güvenli bir mesaj döner.
        """
        if os.getenv("NEO4J_ONLY","0") == "1":
            out = self._answer_via_neo4j_only(user_id, user_message)
            return out or "Bu bilgi Neo4j bilgi tabanında bulunamadı."
        try:
            

            # 2) _ask_assistant_net varsa onu kullan
            if hasattr(self, "_ask_assistant_net"):
                asst_id = (self.user_states.get(user_id, {}) or {}).get("assistant_id")
                if not asst_id:
                    return "Hemen yardımcı olayım 😊 Hangi Škoda modelini sorduğunuzu yazar mısınız?"
                out = self._ask_assistant_net(
                    user_id=user_id,
                    assistant_id=asst_id,
                    user_message=user_message,
                    timeout=60.0,
                    ephemeral=True
                ) or ""
                return out.strip()

            # 3) assistant_runner.ask (beta threads) varsa onu kullan
            if hasattr(self, "assistant_runner") and self.assistant_runner:
                asst_id = (self.user_states.get(user_id, {}) or {}).get("assistant_id")
                if not asst_id:
                    return "Hemen yardımcı olayım 😊 Hangi Škoda modelini sorduğunuzu yazar mısınız?"
                out = self.assistant_runner.ask(
                    user_states=self.user_states,
                    user_id=user_id,
                    assistant_id=asst_id,
                    content=user_message,
                    timeout=60.0,
                    instructions_override=None,
                    tool_resources_override=None,
                    ephemeral=False
                ) or ""
                return out.strip()

        except Exception as e:
            try:
                self.logger.error(f"[fallback_via_chat] failed reason={reason} err={e}")
            except Exception:
                pass

        # Son çare: güvenli mesaj
        return self._fallback_via_assistant(user_id, user_message, reason=reason)
    def _ask_assistant(
        self,
        *,
        user_id: str,
        assistant_id: str,
        content: str,
        timeout: float = 60.0,
        instructions_override: str | None = None,
        tool_resources_override: dict | None = None,
        ephemeral: bool = False,
    ):
        """
        Geriye dönük uyumluluk wrapper'ı.
        Eski kodlar _ask_assistant(...) çağırınca AssistantRunner'a yönlendirir.
        """
        if not getattr(self, "assistant_runner", None):
            raise AttributeError("assistant_runner is not initialized")

        return self.assistant_runner.ask(
            user_states=self.user_states,
            user_id=user_id,
            assistant_id=assistant_id,
            content=content,
            timeout=timeout,
            instructions_override=instructions_override,
            tool_resources_override=tool_resources_override,
            ephemeral=ephemeral,
        )

    def _available_assistant_ids(self) -> list[str]:
        """
        Sistemde kullanılabilir assistant_id listesini toplar.
        Öncelik: ASSISTANT_NAME_MAP (asst_id -> model)
        Ek: ASSISTANT_CONFIG (asst_id -> cfg)
        """
        ids = set()
        try:
            ids.update((getattr(self, "ASSISTANT_NAME_MAP", {}) or {}).keys())
        except Exception:
            pass
        try:
            ids.update((getattr(self, "ASSISTANT_CONFIG", {}) or {}).keys())
        except Exception:
            pass

        # boş/None temizle
        out = [i for i in ids if isinstance(i, str) and i.strip()]
        # istersen sadece "asst_" ile başlayanları tut:
        # out = [i for i in out if i.startswith("asst_")]
        return out

    def _pick_least_busy_assistant(self) -> str | None:
        """
        En az kullanıcıya atanmış assistant_id’yi seçer.
        (Gerçek zamanlı kuyruk vs yok; pratik load-balance: user_states sayımı)
        """
        ids = self._available_assistant_ids()
        if not ids:
            return None

        counts = Counter()
        try:
            for _uid, st in (getattr(self, "user_states", {}) or {}).items():
                aid = (st or {}).get("assistant_id")
                if aid:
                    counts[aid] += 1
        except Exception:
            pass

        min_count = min(counts.get(aid, 0) for aid in ids)
        candidates = [aid for aid in ids if counts.get(aid, 0) == min_count]
        return random.choice(candidates) if candidates else ids[0]

    def _pick_assistant_for_message(self, user_id: str, user_message: str) -> str | None:
        """
        Mesajdan modele göre assistant seçer. Bulamazsa least-busy’e düşer.
        """
        # 1) Mesajdan model yakala
        models = []
        try:
            models = self._extract_models_all(user_message or "")
        except Exception:
            models = []

        if models:
            aid = self._assistant_id_from_model_name(models[0])
            if aid:
                return aid

        # 2) active_model varsa onu dene
        try:
            st = (getattr(self, "user_states", {}) or {}).get(user_id, {}) or {}
            active = (st.get("active_model") or "").strip().lower()
            if active:
                aid = self._assistant_id_from_model_name(active)
                if aid:
                    return aid
        except Exception:
            pass

        # 3) son çare
        return self._pick_least_busy_assistant()
    def _yield_rag_summary_block(self, user_id: str, user_message: str):
        """
        Bazı yerlerde streaming sonunda çağrılıyor.
        Eğer RAG özeti üretmiyorsanız bile ÇÖKMEMESİ için boş generator.
        """
        try:
            if not getattr(self, "RAG_SUMMARY_EVERY_ANSWER", False):
                return
            # İstersen burada CS ratio / route vb. debug gösterebilirsin.
            # Şimdilik boş bırakıyoruz (crash fix).
            return
            yield  # unreachable (generator işareti)
        except Exception:
            return


    def _yield_sql_rag_block(self, user_id: str, user_message: str):
        """
        Aynı mantık: yoksa crash ediyordu. Şimdilik no-op.
        """
        try:
            if not getattr(self, "USE_SQL_RAG", False):
                return
            return
            yield
        except Exception:
            return

    def _assistant_id_from_model_name(self, model_name: str) -> str | None:
        """
        'kodiaq' -> ilgili assistant_id
        Kaynak önceliği:
        1) self.MODEL_TO_ASSISTANT_ID (hazır ters map)
        2) self.ASSISTANT_NAME_MAP (asst_id -> model) ters çevirerek
        3) self.ASSISTANT_CONFIG içinden (varsa) model alanını bularak
        """
        if not model_name:
            return None

        m = normalize_tr_text(str(model_name)).lower().strip()
        m = strip_tr_suffixes(m)  # elroqun -> elroq gibi

        # 1) hazır map
        asst = getattr(self, "MODEL_TO_ASSISTANT_ID", {}).get(m)
        if asst:
            return asst

        # 2) ASSISTANT_NAME_MAP ters tarama
        for asst_id, slug in (getattr(self, "ASSISTANT_NAME_MAP", {}) or {}).items():
            if normalize_tr_text(str(slug or "")).lower().strip() == m:
                return asst_id

        # 3) ASSISTANT_CONFIG içinden bul (farklı şemalara toleranslı)
        for asst_id, cfg in (getattr(self, "ASSISTANT_CONFIG", {}) or {}).items():
            if not isinstance(cfg, dict):
                continue
            slug = cfg.get("model") or cfg.get("model_slug") or cfg.get("name") or cfg.get("assistant_name")
            if slug and normalize_tr_text(str(slug)).lower().strip() == m:
                return asst_id

        return None

    def _ensure_vector_store_and_upload(self):
        # geriye dönük isim: eski çağrılar bozulmasın
        return self._ensure_sql_vector_store_and_upload()


    def _net_global_instructions(self, user_message: str) -> str:
        return (
            "Sen Škoda Türkiye dijital satış danışmanısın.\n"
            "KURALLAR (ZORUNLU):\n"
            "- Cevabı NET ver. Yuvarlak/kaçamak ifade kullanma.\n"
            "- İlk cümle: doğrudan cevap (1 satır).\n"
            "- Sonra en fazla 3 madde ile detay.\n"
            "- Eğer bilgi gerçekten eksikse SADECE 1 soru sor.\n"
            "- Gereksiz soru sorma (özellikle 'hangi donanım merak ediyorsunuz?' gibi).\n"
            "- Sayısal değer uydurma. Bilgi yoksa 'Bu bilgi KB’de yok.' de.\n"
            "- Kullanıcının yazmadığı model isimlerini ekleme.\n"
            "- 2–6 cümleyi geçme.\n"
            "\n"
            "FORMAT:\n"
            "Net cevap: ...\n"
            "- ...\n"
            "- ...\n"
            "- ...\n"
            "Gerekirse tek soru: ...?\n"
        )

    def _is_answer_weak_global(self, question: str, answer: str) -> bool:
        if not answer or len(answer.strip()) < 25:
            return True
        a = answer.strip()

        # teknik/sayısal soruysa rakam yoksa zayıf say
        try:
            needs_num = bool(self._needs_numbers(question))
        except Exception:
            needs_num = bool(re.search(r"\b(kaç|km|sn|nm|kw|ps|hp|0-100|menzil|tork|güç)\b", (question or "").lower()))
        if needs_num and not re.search(r"\d", a):
            return True

        # çok fazla soru soruyorsa zayıf say (özellikle liste sorularında)
        if a.count("?") >= 2:
            return True

        # “yuvarlak” kalıplar
        if self.NET_WEAK_RE.search(a):
            return True

        return False
     


    def _answer_equipment_presence_strict(self, user_id: str, user_message: str, *, return_meta: bool = False):
        # 1) Model bul
        model = None
        try:
            model = self._current_model(user_id, user_message)
        except Exception:
            model = None
        if not model:
            ms = list(self._extract_models(user_message or ""))
            model = ms[0] if ms else None

        if not model:
            txt = "Bunu kontrol edebilmem için hangi Škoda modeli olduğunu yazar mısınız? (Örn: Kamiq)"
            if return_meta:
                return txt, True, {"reason": "need_model", "model": None, "feature": None, "found": False}
            return txt

        model = model.lower().strip()
        self._set_active_model(user_id, model)

        # 2) EquipmentList’ten feature bul
        trims, status_map, feature_title = self._feature_lookup_any(model, user_message)
        self.logger.info(f"[EQUIP-STRICT] model={model} feature={feature_title} trims={len(trims)}")

        # 3) Eşleşme yoksa: burada "final değil" => üst katman fallback denesin
        if not trims or not status_map or not feature_title:
            txt = "Bu modelde istediğiniz özellik bulunmamaktadır."
            if return_meta:
                return txt, False, {"reason": "not_in_equipmentlist", "model": model, "feature": feature_title, "found": False}
            return txt

        # 4) Bulduysak netleştir (S/O/—)
        sent = self._nlg_equipment_status(
            model_name=model,
            feature=feature_title,
            trims=trims,
            status_map=status_map
        )
        txt = (sent or "").strip() or f"{model.title()} için '{feature_title}' bilgisi bulundu."

        if return_meta:
            return txt, True, {"reason": "equipmentlist_hit", "model": model, "feature": feature_title, "found": True}
        return txt

    def get_place_coord(place: str, *, province_hint: str | None = None):
        p = normalize_tr_text(place)

        # 1) İl adı direkt
        if p in CITY_COORDS_TR_NORM:
            return CITY_COORDS_TR_NORM[p]

        # 2) İlçe + il ipucu ile
        if province_hint:
            iln = normalize_tr_text(province_hint)
            ll = (DISTRICT_COORDS_TR_NORM.get(iln) or {}).get(p)
            if ll:
                return ll

        # 3) İlçe tek başına geldiyse: tüm illerde ara (ilk bulduğunu döner)
        for iln, dmap in DISTRICT_COORDS_TR_NORM.items():
            if p in dmap:
                return dmap[p]

        return None
    PRESENCE_RE = re.compile(
    
    r"\b(var m[ıi]|varmi|yok mu|yokmu|mevcut mu|bulunuyor mu|oluyor mu|geliyor mu)\b"
    )

    TEKNIK_KW = [
        "tork", "güç", "guc", "beygir", "hp", "ps", "kw",
        "0-100", "0 – 100", "0 100", "ivme", "hızlanma",
        "maksimum hız", "maks hiz", "menzil", "range",
        "tüketim", "tuketim", "l/100", "lt/100",
        "co2", "emisyon", "bagaj hacmi", "dm3",
    ]
    WEAK_ANSWER_RE = re.compile(
    r"(değişkenlik\s*gösterebilir|genellikle|hangi\s+motor|hangi\s+donan[ıi]m|hangi\s+versiyon|netleştirebilmem)",
    re.IGNORECASE
    )
        # =========================
    # TRIP CALC (Kaç şarj / kaç depo)
    # =========================
    def _is_trip_calc_question(self, text: str) -> bool:
        if not text:
            return False
        t = normalize_tr_text(text).lower()

        trip_words = [
            "kaç şarj", "kac sarj", "kaç defa şarj", "kac defa sarj",
            "kaç kez şarj", "kac kez sarj",
            "kaç depo", "kac depo",
            "tek şarj", "tek sarj",
            "şarjla", "sarjla",
        ]
        # rota sinyali: km yazmış ya da 2 şehir var
        has_trip = any(w in t for w in trip_words)
        has_km = _extract_km_from_text(t) is not None
        a, b, _, _ = _extract_two_places(text)

        has_route = has_km or (a is not None and b is not None)

        # "şarj gücü / 10-80 kaç dk" gibi sorular trip calc değil (SPEC)
        non_trip_spec = any(x in t for x in ["10-80", "10 80", "dc", "ac", "kwh", "şarj süresi", "sarj suresi", "şarj gücü", "sarj gucu"])
        if non_trip_spec and not ("ankara" in t or "istanbul" in t or has_km):
            return False
        self.logger.info(f"[TRIP] is_trip={has_trip} has_route={has_route} a={a} b={b}")
        return has_trip and has_route

    def _trip_calc_distance_km(self, text: str) -> tuple[float | None, str]:
        km = _extract_km_from_text(text)
        if km:
            return km, "Mesafe kullanıcı ifadesinden alındı."

        a, b, a_meta, b_meta = _extract_two_places(text)
        if not a or not b:
            # kullanıcıya km sormuyoruz; sadece “rota anlaşılamadı” diyebiliriz
            return None, "Rota (2 yer) bulunamadı."

        # koordinatlar (il/ilçe fark etmez)
        an = normalize_tr_text_base(a)
        bn = normalize_tr_text_base(b)
        ll1 = CITY_COORDS_TR_NORM.get(an) or (DISTRICT_FLAT_NORM.get(an) or (None, None, None, None))[1]
        ll2 = CITY_COORDS_TR_NORM.get(bn) or (DISTRICT_FLAT_NORM.get(bn) or (None, None, None, None))[1]


        # meta boş geldiyse (X'dan Y'ye regex yolu), normal map'ten bulmayı dene
        if not ll1:
            an = normalize_tr_text(a)
            ll1 = CITY_COORDS_TR_NORM.get(an) or (DISTRICT_FLAT_NORM.get(an) or (None, None, None, None))[1]
        if not ll2:
            bn = normalize_tr_text(b)
            ll2 = CITY_COORDS_TR_NORM.get(bn) or (DISTRICT_FLAT_NORM.get(bn) or (None, None, None, None))[1]

        if not ll1 or not ll2:
            return None, f"Koordinat bulunamadı: {a} → {b}"

        crow = _haversine_km(ll1[0], ll1[1], ll2[0], ll2[1])

        # Kuş uçuşu → yol yaklaşımı
        road_km = crow * float(os.getenv("TRIP_ROAD_FACTOR", "1.28"))
        note = f"Mesafe otomatik hesaplandı: {a} → {b} (yaklaşık)"
        self.logger.info(f"[TRIP] coord miss: a={a} an={an} ll1={ll1} | b={b} bn={bn} ll2={ll2}")

        return road_km, note

    def _answer_trip_calc(self, user_id: str, user_message: str) -> str:
        """
        EV için: 'kaç şarj' tahmini (durak sayısı)
        ICE için: 'kaç depo' tahmini (durak sayısı)
        """
        q = user_message or ""

        # 1) Model bul
        model = None
        ms = list(self._extract_models(q))
        if ms:
            model = ms[0]
        else:
            model = self._get_active_model(user_id)

        if not model:
            return "Elbette 😊 Hangi Škoda modeli için hesaplayayım? (Örn: Elroq, Enyaq)"

        model = model.lower().strip()

        # 2) Mesafe bul
        dist_km, note = self._trip_calc_distance_km(q)
        if not dist_km:
            return (
                f"{model.title()} için hesaplayabilmem adına rota mesafesini km olarak yazar mısın? "
                "Örn: 'Ankara İstanbul 450 km' veya 'Ankara’dan İstanbul’a'."
            )

        # 3) EV mi ICE mi?
        is_ev = False
        try:
            is_ev = model in (EV_RANGE_KM or {})
        except Exception:
            is_ev = model in {"elroq", "enyaq"}  # güvenli fallback

        # 4) Kullanılabilir menzil (varsayımlar)
        reserve = float(os.getenv("TRIP_RESERVE_RATIO", "0.10"))          # %10 batarya/depo rezerv
        real_world = float(os.getenv("TRIP_REALWORLD_RATIO", "0.75"))     # WLTP -> gerçek kullanım
        usable_ratio = max(0.40, min(0.95, (1.0 - reserve) * real_world))

        if is_ev:
            wltp_range = None
            try:
                wltp_range = float(EV_RANGE_KM.get(model))
            except Exception:
                wltp_range = None

            if not wltp_range:
                return (
                    f"{model.title()} için menzil bilgisi sözlüğümde yok. "
                    "Hangi versiyon/menzil (km) üzerinden hesaplayayım?"
                )

            usable_km = wltp_range * usable_ratio

            import math
            # Kaç “şarjla” = kaç bacak: ceil(distance/usable)
            legs = max(1, int(math.ceil(dist_km / usable_km)))
            stops = max(0, legs - 1)

            return (
                f"{model.title()} ile yaklaşık **{dist_km:.0f} km** yol için, pratik kullanımda "
                f"(**kullanılabilir menzil ≈ {usable_km:.0f} km**) **{stops} kez hızlı şarj** ile gidebilirsiniz.\n"
                f"- Hesap notu: {note}\n"
                f"- Varsayım: WLTP menzilin ~%{int(usable_ratio*100)}’i kullanılabilir kabul edildi (hız/iklim/rota etkiler).\n"
                "İstersen hız (120–130), mevsim (kış/yaz) ve yük durumunu yaz; daha isabetli ayarlayayım."
            )

        # ICE (depo) — varsa FUEL_SPECS’ten
        try:
            spec = (FUEL_SPECS or {}).get(model, {})
        except Exception:
            spec = {}

        tank_l = None
        cons_l100 = None

        # sözlük formatın değişebileceği için toleranslı al
        for k in ["tank_l", "tank", "depo_l", "depo"]:
            if k in spec:
                try: tank_l = float(spec[k])
                except: pass
        for k in ["cons_l100", "consumption_l100", "tuketim_l100", "tüketim_l100"]:
            if k in spec:
                try: cons_l100 = float(spec[k])
                except: pass

        if not tank_l or not cons_l100:
            return (
                f"{model.title()} için 'kaç depo' hesabı yapabilmem adına ortalama tüketim (L/100 km) "
                "ve depo hacmi (L) bilgisi gerekir. İstersen 'ortalama 7.0 L/100 km' gibi bir değer yaz; hesaplayayım."
            )

        range_km = (tank_l / cons_l100) * 100.0
        usable_km = range_km * usable_ratio

        import math
        legs = max(1, int(math.ceil(dist_km / usable_km)))
        stops = max(0, legs - 1)

        return (
            f"{model.title()} ile yaklaşık **{dist_km:.0f} km** yol için, pratik kullanımda "
            f"(**kullanılabilir menzil ≈ {usable_km:.0f} km**) **{stops} kez yakıt ikmali** ile gidebilirsiniz.\n"
            f"- Hesap notu: {note}\n"
            f"- Varsayım: depo/menzilin ~%{int(usable_ratio*100)}’i kullanılabilir kabul edildi.\n"
            "Kullanım tipi (şehir içi/otoyol) ve ortalama hızını yazarsan daha doğru hesaplayabilirim."
        )

    def _answer_trim_diff_from_sql(self, model: str, a_trim: str, b_trim: str, *, detailed: bool = False) -> str:
        tname = self._latest_equipment_table_for(model)
        if not tname:
            return f"{model.title()} için donanım tablosu bulunamadı."

        order_a, smap_a, dmap_a = self._equipment_dict_from_table(tname, preferred_trim=a_trim)
        order_b, smap_b, dmap_b = self._equipment_dict_from_table(tname, preferred_trim=b_trim)

        # birleşik feature sırası
        all_keys = []
        for k in order_a + order_b:
            if k not in all_keys:
                all_keys.append(k)

        def pretty(code: str) -> str:
            return "Standart" if code == "S" else ("Opsiyonel" if code == "O" else "—")

        # bucket'lar
        a_only = []       # A var, B yok
        b_only = []       # B var, A yok
        diff_status = []  # ikisinde de var ama S/O farklı
        both_same = []    # ikisinde de var ve aynı (S/S veya O/O)

        for k in all_keys:
            sa = smap_a.get(k, "—")
            sb = smap_b.get(k, "—")
            name = dmap_a.get(k) or dmap_b.get(k) or str(k)

            has_a = sa != "—"
            has_b = sb != "—"

            if has_a and not has_b:
                a_only.append((name, pretty(sa), "—"))
            elif has_b and not has_a:
                b_only.append((name, "—", pretty(sb)))
            elif has_a and has_b and sa != sb:
                diff_status.append((name, pretty(sa), pretty(sb)))
            elif has_a and has_b:
                both_same.append((name, pretty(sa), pretty(sb)))

        # --- KISA MOD (senin mevcut davranışın gibi) ---
        if not detailed:
            if not a_only:
                return (
                    f"{model.title()} {a_trim.title()}’de olup {b_trim.title()}’da olmayan ayrı bir donanım kaydı görünmüyor. "
                    f"İstersen tersini ({b_trim.title()} → {a_trim.title()}) veya detaylı tabloyu göstereyim."
                )
            lines = [f"**{model.title()} {a_trim.title()}’de olup {b_trim.title()}’da olmayan donanımlar ({len(a_only)} adet):**"]
            for name, a_stat, _ in a_only:
                lines.append(f"- {name} ({a_trim.title()}: {a_stat})")
            lines.append("")
            lines.append(f"Detay istersen: **'{model} {a_trim} ile {b_trim} detaylı fark'** yazabilirsin.")
            return "\n".join(lines)

        # --- DETAYLI MOD: ÖZET + TABLO + TERS YÖN ---
        def md_table(rows, title):
            if not rows:
                return f"**{title}:** _(kayıt yok)_"
            out = [f"**{title} ({len(rows)}):**", "| Özellik | " + a_trim.title() + " | " + b_trim.title() + " |", "|---|---|---|"]
            for (name, va, vb) in rows:
                out.append(f"| {name} | {va} | {vb} |")
            return "\n".join(out)

        parts = []
        parts.append(f"**{model.title()} — {a_trim.title()} vs {b_trim.title()} (Detaylı Donanım Analizi)**")
        parts.append("")
        parts.append("**Özet**")
        parts.append(f"- {a_trim.title()}’e özel: **{len(a_only)}**")
        parts.append(f"- {b_trim.title()}’e özel: **{len(b_only)}**")
        parts.append(f"- İkisinde de var ama statü farklı: **{len(diff_status)}**")
        parts.append(f"- İkisinde de var ve aynı: **{len(both_same)}**")
        parts.append("")

        parts.append(md_table(a_only, f"{a_trim.title()}’de var, {b_trim.title()}’da yok"))
        parts.append("")
        parts.append(md_table(b_only, f"{b_trim.title()}’da var, {a_trim.title()}’de yok"))
        parts.append("")
        parts.append(md_table(diff_status, "İkisinde de var ama statü farklı (Standart/Opsiyonel)"))

        return "\n".join(parts)


    def _try_deterministic_answer(self, user_id: str, msg: str) -> str | None:
        # --- NEO4J: company people quick pass (örnek) ---
        qn = normalize_tr_text(msg).lower()
        if any(k in qn for k in ["mail", "email", "telefon", "tel", "dahili", "departman", "title", "ünvan", "unvan"]):
            # çok basit kişi adayı: ilk kelimeyi dene (istersen senin parse fonksiyonunu bağlarız)
            cand = (msg or "").strip().split()[0]
            p = self._company_person_from_neo4j(cand)
            if p:
                name = f"{p.get('name','')} {p.get('surname','')}".strip()
                return f"{name} — {p.get('title','')} / {p.get('department','')}"
        if not msg:
            return None
        if self._is_trip_calc_question(msg):
            return self._answer_trip_calc(user_id, msg)

        q = normalize_tr_text(msg).lower()

        # 1) Model bul (mesajdan veya active_model)
        model = None
        ms = list(self._extract_models(msg))
        if ms:
            model = ms[0]
        else:
            model = self._get_active_model(user_id)

        # -------------------------
        # A) “Kaç / liste” tipleri
        # -------------------------
        # Trim/donanım sayısı / listesi
        if any(x in q for x in [
            "kaç donan", "kac donan",
            "kaç paket", "kac paket",
            "donanım seviyesi", "donanim seviyesi",
            "donanım seviyeleri", "donanim seviyeleri",
        ]):
            if not model:
                return "Hangi Škoda modeli için donanım seviyelerini görmek istersiniz? (Örn: Karoq, Kamiq, Octavia)"
            trims = self.MODEL_VALID_TRIMS.get(model.lower(), []) or []
            if not trims:
                return f"{model.title()} için donanım seviyesi bilgisi tanımlı değil."
            return f"{model.title()} modelinde {len(trims)} donanım seviyesi bulunur: {', '.join(t.title() for t in trims)}."

        # Ürün gamı (genel model listesi)
        if any(x in q for x in ["ürün gam", "urun gam", "hangi modeller var", "model listesi", "modeller neler"]):
            # MODELS sabit listen varsa onu kullan, yoksa MODEL_VALID_TRIMS keys
            models = ["Fabia","Scala","Kamiq","Karoq","Kodiaq","Octavia","Superb","Elroq","Enyaq"]
            return "Škoda ürün gamında öne çıkan modeller: " + ", ".join(models) + "."

        # EV menzil sözlüğü (genel)
        if any(x in q for x in ["menzil listesi", "elektrikli menzil", "wltp menzil"]):
            try:
                from modules.data.ev_specs import EV_RANGE_KM
                if EV_RANGE_KM:
                    lines = [f"- {m.title()}: {v} km" for m, v in EV_RANGE_KM.items()]
                    return "Elektrikli modeller için WLTP menzil özeti:\n" + "\n".join(lines)
            except Exception:
                pass

        return None
    def _detect_same_model_trim_diff(self, text: str) -> tuple[str | None, str | None, str | None]:
        """
        'Karoq prestige'de olup sportline'da olmayan donanımlar'
        -> (karoq, prestige, sportline)
        """
        if not text:
            return None, None, None

        raw = (text or "").lower()

        # tek model şart
        models = list(self._extract_models(text))
        if len(models) != 1:
            return None, None, None
        model = models[0]

        # en az 2 trim şart
        trims = list(extract_trims(raw))
        valid = set(self.MODEL_VALID_TRIMS.get(model, []) or [])
        trims = [t for t in trims if t in valid]
        if len(trims) < 2:
            return None, None, None

        # set-diff niyeti var mı?
        diff_markers = ["olup", "olmayan", "hariç", "haric", "dışında", "disinda"]
        if not any(w in raw for w in diff_markers):
            return None, None, None

        # Varsayılan yön: metinde ilk geçen 2 trim
        a, b = trims[0], trims[1]

        # "A ... olup B ... olmayan" yönünü daha doğru yakala
        if ("olup" in raw) and ("olmayan" in raw):
            idx_olup = raw.find("olup")
            left = raw[:idx_olup]
            right = raw[idx_olup:]

            left_trims = [t for t in trims if t in left]
            right_trims = [t for t in trims if t in right]

            if left_trims and right_trims:
                a = left_trims[-1]   # olup'un solunda geçen son trim
                b = right_trims[0]   # olup'tan sonra geçen ilk trim

        return model, a, b

    def _rag_instructions_numeric_table(self, user_message: str) -> str:
        q = (user_message or "").lower()

        wants_table = any(k in q for k in ["tablo", "teknik tablo", "tablosunu", "listele", "liste", "karşılaştır", "kıyas", "vs"])
        needs_num = False
        try:
            needs_num = bool(self._needs_numbers(user_message))
        except Exception:
            needs_num = any(k in q for k in ["kaç", "km", "sn", "nm", "kw", "ps", "hp", "0-100", "menzil", "tork", "güç"])

        # Ortak kurallar (SQL YOK, sadece file_search)
        rules = [
            "SENİN TEK KAYNAĞIN file_search sonuçlarıdır (SQL veya başka kaynak kullanma).",
            "Bulduğun sayıları ve birimleri AYNEN yaz (ör. 8,1 sn / 535 km / 250 Nm).",
            "Varsayım yapma, uydurma sayı yazma.",
            "Kaynak/URL/dosya adı/ID/citation yazma."
        ]

        # Sayı zorunluluğu
        if needs_num:
            rules += [
                "Kullanıcı sayısal değer istiyor: cevapta EN AZ 1 rakam geçmek ZORUNLU.",
                "Eğer file_search içinde bu sayısal değer bulunamazsa TAM OLARAK şunu yaz: 'KB’de bu sayısal değer yok.'",
                "Sonra 1 netleştirici soru sor (model yılı/trim/motor)."
            ]

        # Tablo zorunluluğu
        if wants_table:
            rules += [
                "ÇIKTI ZORUNLU: En sonda düzgün bir Markdown tablo ver (başlık satırı + --- ayırıcı).",
                "Tabloda KB’de olmayan hücrelere '—' yaz."
            ]
        else:
            # tablo istememişse bile mini tablo verelim (senin isteğine uygun)
            rules += [
                "ÇIKTI: Cevabın sonunda küçük bir Markdown tablo ver:",
                "| Alan | Değer |",
                "|---|---|",
                "| Model | ... |",
                "| Özellik | ... |",
                "| Değer | ... |"
            ]

        return "KURALLAR:\n- " + "\n- ".join(rules)

    def _is_equipment_query_by_evidence(self, user_id: str, text: str) -> bool:
        """
        Cümle kalıbından bağımsız donanım sorusu tespiti.
        Amaç: 'hangi pakette / hangi donanımda / sunuluyor mu' gibi soruları da
        EquipmentList/DB akışına sokmak.

        True dönerse: donanım sorgusu gibi davran.
        """
        import re

        if not text:
            return False

        t_norm = normalize_tr_text(text).lower()

        # 0) Donanım listesi/özet gibi GENEL istekleri buradan geçirme
        # (bunların ayrı akışları var)
        if re.search(r"\b(donan[ıi]m\s*listesi|donan[ıi]mlar\s*neler|donan[ıi]mlar)\b", t_norm):
            return False

        # 1) Fiyat / görsel / teknik metrikse donanım route'u yapma
        if self._is_price_intent(text):
            return False

        if self.utils.is_image_request(text) or self._is_image_intent_local(text):
            return False

        try:
            if self._spec_key_from_query(text):
                return False
        except Exception:
            pass

        # 2) Model çöz
        model = None
        try:
            model = self._current_model(user_id, text)
        except Exception:
            model = None
        if not model:
            return False

        # 3) Semantik en yakın satır var mı?
        try:
            hits = self._semantic_feature_match_equipment(model, text, topn=1) or []
        except Exception:
            hits = []

        # Eşikler (ENV ile oynayabilirsin)
        HARD = float(os.getenv("EQUIP_EVIDENCE_SIM_HARD", "0.80"))   # çok güvenli
        MIN  = float(os.getenv("EQUIP_EVIDENCE_SIM_MIN",  "0.70"))   # güvenli + safe_match

        if hits:
            best = hits[0]
            sim = float(best.get("score") or 0.0)
            oz  = (best.get("ozellik") or "").strip()

            # çok yüksekse direkt kabul
            if sim >= HARD:
                return True

            # orta-yüksekse "safe match" ile doğrula
            if sim >= MIN and oz:
                try:
                    if self._is_safe_equipment_match(text, oz):
                        return True
                except Exception:
                    pass

        # 4) Yedek kanıt: TR/EN keyword araması (hafif)
        try:
            if self._feature_exists_tr_en(model, text):
                return True
        except Exception:
            pass

        return False

    def _default_trim_for_model(self, model_slug: str) -> str | None:
        m = (model_slug or "").lower().strip()
        lst = (self.MODEL_VALID_TRIMS.get(m) or [])
        return lst[0] if lst else None

    def _pick_single_value_from_range(self, rr: dict | None, *, trim_hint: str | None) -> float | None:
        """
        rr: _spec_range_from_imported çıktısı
        trim_hint: 'e prestige 60' gibi
        -> tek bir numeric döndür (önce trim ile, yoksa ilk numeric)
        """
        if not rr:
            return None

        vals = rr.get("values") or []   # [(col, '8,1 sn'), ...]
        if not vals:
            # fallback: min varsa onu dön (tek değer yaklaşımı)
            return rr.get("min")

        # Trim kolon adlarını çıkar
        cols = [c for c, _ in vals]

        # 1) Trim ile kolon seç
        if trim_hint:
            try:
                col = self._match_trim_column_name(trim_hint, cols)
            except Exception:
                col = None

            if col:
                raw = next((v for c, v in vals if c == col), None)
                num = self._parse_first_float(raw or "")
                if num is not None:
                    return num

        # 2) Trim bulunamadıysa: ilk numeric değeri dön
        for _c, raw in vals:
            num = self._parse_first_float(raw or "")
            if num is not None:
                return num

        return None

    def _parse_first_float(self, s: str) -> float | None:
        """
        TR/EU sayı formatlarını doğru çözer.
        Örn:
        '2.057 kg'   -> 2057.0
        '1.978'      -> 1978.0
        '1,978'      -> 1978.0 (binlik)
        '1978,5'     -> 1978.5 (ondalık)
        '1.234,56'   -> 1234.56
        '1,234.56'   -> 1234.56
        """
        import re

        if not s:
            return None

        txt = str(s).strip().replace("\u00a0", " ")
        m = re.search(r"(\d{1,3}(?:[.,\s]\d{3})+|\d+(?:[.,]\d+)?)", txt)
        if not m:
            return None

        num = m.group(1).strip()

        # boşlukla binlik: "2 057" -> "2057"
        num = re.sub(r"\s+", "", num)

        # Hem . hem , varsa: son görünen ayraç ondalıktır (EU: 1.234,56 / US: 1,234.56)
        if "." in num and "," in num:
            last_dot = num.rfind(".")
            last_com = num.rfind(",")

            if last_com > last_dot:
                # EU: 1.234,56 -> 1234.56
                num = num.replace(".", "")
                num = num.replace(",", ".")
            else:
                # US: 1,234.56 -> 1234.56
                num = num.replace(",", "")

        # Sadece '.' var
        elif "." in num and "," not in num:
            parts = num.split(".")
            # Eğer nokta sonrası her grup 3 hane ise bu binliktir: 2.057, 1.978, 12.345.678
            if len(parts) >= 2 and all(len(p) == 3 for p in parts[1:]):
                num = "".join(parts)
            # değilse ondalık sayıdır: 8.5 gibi
            # (dokunma)

        # Sadece ',' var
        elif "," in num and "." not in num:
            parts = num.split(",")
            # Eğer virgül sonrası 3 hane ise bu binliktir: 1,978 -> 1978
            if len(parts) == 2 and len(parts[1]) == 3:
                num = "".join(parts)
            else:
                # 1978,5 -> 1978.5
                num = num.replace(",", ".")

        try:
            return float(num)
        except Exception:
            return None



    def _is_spec_question(self, text: str) -> bool:
        """
        Teknik/sayısal cevap gerektiren soruları yakala.
        """
        if not text:
            return False
        t = normalize_tr_text(text).lower()
        # sizin mevcut spec matcher'ınız da var; en güvenlisi:
        try:
            if self._spec_key_from_query(text):
                return True
        except Exception:
            pass

        # ekstra güvenlik: birim/sayı soruları
        return any(k in t for k in [
            "ağırlık", "agirlik", "kg",
            "menzil", "range", "km",
            "0-100", "hızlanma", "ivme", "sn",
            "tork", "nm",
            "güç", "guc", "kw", "ps", "hp",
            "maksimum hız", "maks hiz", "km/h",
            "tüketim", "tuketim", "l/100", "lt/100",
            "co2", "emisyon", "g/km",
            "bagaj", "dm3",
            "uzunluk", "genişlik", "yukseklik", "yükseklik", "dingil",
            "depo", "yakıt deposu", "yakit deposu", "depo hacmi"
        ])


    def _spec_range_from_imported(self, model_slug: str, canon_key: str) -> dict | None:
        """
        Imported_KODA_<MODEL> tablosundan ilgili metrik satırını bulur,
        tüm trim kolonlarında numeric değerleri tarar ve min/max döndürür.
        """
        import contextlib, re

        m = (model_slug or "").strip().upper()
        if not m or not canon_key:
            return None

        conn = self._sql_conn()
        cur = conn.cursor()
        try:
            # Tabloyu bul
            # Tabloyu bul (ENYAQ Coupe gibi özel isimleri de yakala)
            qctx = getattr(self, "_LAST_SPEC_QUERY", "") or ""
            prefer_coupe = (m == "ENYAQ") and ("coup" in qctx or "kupe" in qctx or "kup" in qctx)

            patterns = [
                f"Imported\\_KODA\\_{m}\\_MY\\_%",
                f"Imported\\_KODA\\_{m}\\_\\_%",   # double underscore varyantları
                f"Imported\\_KODA\\_{m}%",        # genel fallback
                f"Imported\\_{m}%",               # çok eski adlandırmalar
            ]

            row = None
            for pat in patterns:
                if prefer_coupe:
                    cur.execute(
                        """
                        SELECT TOP 1 name
                        FROM sys.tables
                        WHERE name LIKE ? ESCAPE '\\' AND UPPER(name) LIKE '%COUP%'
                        ORDER BY name DESC
                        """,
                        (pat,),
                    )
                    row = cur.fetchone()
                    if row:
                        break

                cur.execute(
                    """
                    SELECT TOP 1 name
                    FROM sys.tables
                    WHERE name LIKE ? ESCAPE '\\'
                    ORDER BY name DESC
                    """,
                    (pat,),
                )
                row = cur.fetchone()
                if row:
                    break

            if not row:
                return None

            tname = row[0]

            # Kolonları al
            cur.execute(f"SELECT TOP 0 * FROM [{tname}]")
            cols = [c[0] for c in cur.description] if cur.description else []
            if not cols:
                return None

            # Ozellik kolonu
            name_col = None
            for cand in ["Ozellik", "Özellik", "SpecName", "Name", "Title", "Attribute"]:
                if cand in cols:
                    name_col = cand
                    break
            if not name_col:
                name_col = next((c for c in cols if re.search(r"(ozellik|özellik|name|title|attribute)", c, re.I)), None)
            if not name_col:
                return None

            trim_cols = [c for c in cols if c not in ("id", "ID", "Model", name_col)]
            if not trim_cols:
                return None

            # Tüm satırlar
            cur.execute(
                f"SELECT [{name_col}], {', '.join(f'[{c}]' for c in trim_cols)} "
                f"FROM [{tname}] WITH (NOLOCK)"
            )
            rows = cur.fetchall()
            if not rows:
                return None

            def nrm(x: str) -> str:
                return re.sub(r"\s+", " ", normalize_tr_text(x or "")).lower().strip()

            def matches(canon: str, oz_norm: str) -> bool:
                # canon_key burada genellikle: "agirlik" / "menzil" / "0-100" ...
                c = canon.lower()

                if c in {"agirlik", "ağırlık"}:
                    return ("ağırlık" in oz_norm) or ("agirlik" in oz_norm) or ("weight" in oz_norm)
                if c == "menzil":
                    return ("menzil" in oz_norm) or ("range" in oz_norm) or ("wltp" in oz_norm)
                if c == "0-100":
                    return ("0-100" in oz_norm) or ("0 100" in oz_norm) or ("ivme" in oz_norm)
                if c in {"güç", "guc"}:
                    return ("güç" in oz_norm) or ("guc" in oz_norm) or ("power" in oz_norm) or ("kw" in oz_norm) or ("ps" in oz_norm)
                if c == "tork":
                    return ("tork" in oz_norm) or ("torque" in oz_norm) or ("nm" in oz_norm)
                if c in {"maksimum hız", "max_hiz"}:
                    return (("maks" in oz_norm) and ("hiz" in oz_norm or "hız" in oz_norm)) or ("max speed" in oz_norm) or ("top speed" in oz_norm)
                if c in {"yakıt tüketimi", "tuketim"}:
                    return ("tüketim" in oz_norm) or ("tuketim" in oz_norm) or ("l/100" in oz_norm) or ("lt/100" in oz_norm)
                if c == "co2":
                    return ("co2" in oz_norm) or ("emisyon" in oz_norm) or ("g/km" in oz_norm)
                if c == "bagaj":
                    return ("bagaj" in oz_norm) or ("dm3" in oz_norm) or ("luggage" in oz_norm) or ("trunk" in oz_norm) or ("cargo" in oz_norm)
                # boyutlar vb. için geniş bırak
                if c == "boyutlar":
                    return any(k in oz_norm for k in ["uzunluk", "genişlik", "genislik", "yükseklik", "yukseklik", "dingil"])
                
                if c in {"depo", "yakıt deposu", "yakit deposu"}:
                    return ("depo" in oz_norm) or ("yakıt" in oz_norm) or ("yakit" in oz_norm) or ("tank" in oz_norm) or ("fuel" in oz_norm)
                return False
            best = None
            best_score = -999

            # Kullanıcı "şehir içi/kombine" gibi ipuçları veriyorsa satır seçimini buna göre puanlayalım
            qctx = getattr(self, "_LAST_SPEC_QUERY", "") or ""
            want_city = ("şehir" in qctx) or ("sehir" in qctx) or ("city" in qctx)
            want_comb = ("kombine" in qctx) or ("birleşik" in qctx) or ("birlesik" in qctx) or ("combined" in qctx)

            for r in rows:
                oz_raw = str(r[0] or "").strip()
                oz_norm = nrm(oz_raw)
                if not matches(canon_key, oz_norm):
                    continue

                score = 0
                if canon_key == "menzil":
                    is_city = ("şehir" in oz_norm) or ("sehir" in oz_norm) or ("city" in oz_norm)
                    is_comb = ("kombine" in oz_norm) or ("birleşik" in oz_norm) or ("birlesik" in oz_norm) or ("combined" in oz_norm)
                    if want_city:
                        score += 20 if is_city else -10
                    elif want_comb:
                        score += 20 if is_comb else 0
                        score -= 10 if is_city else 0
                    else:
                        score += 5 if is_comb else 0
                        score -= 3 if is_city else 0

                # numeric içeren satırları biraz öne al
                blob = " ".join(str(x or "") for x in r[1:])
                if re.search(r"\d", blob):
                    score += 2

                if score > best_score:
                    best_score = score
                    best = r

            if not best:
                return None

            title = str(best[0] or "").strip()

            # Trim kolonlarındaki numeric'leri topla
            nums = []
            raw_values = []
            for i, c in enumerate(trim_cols, start=1):
                v = str(best[i] or "").strip()
                if not v:
                    continue
                raw_values.append((c, v))
                num = self._parse_first_float(v)
                if num is not None:
                    nums.append(num)

            if not nums:
                return {
                    "model": model_slug.lower(),
                    "title": title,
                    "min": None,
                    "max": None,
                    "values": raw_values,
                }

            return {
                "model": model_slug.lower(),
                "title": title,
                "min": min(nums),
                "max": max(nums),
                "values": raw_values,
            }

        finally:
            with contextlib.suppress(Exception): cur.close()
            with contextlib.suppress(Exception): conn.close()


    def _answer_multi_model_spec_from_sql(self, user_message: str, models: list[str]) -> str | None:
        if not user_message or not models or len(models) < 2:
            return None

        # ✅ önce anahtarı çıkar
        try:
            spec_key = self._spec_key_from_query(user_message)
        except Exception:
            spec_key = None

        qn = normalize_tr_text(user_message).lower()
        if not spec_key:
            if any(k in qn for k in ["ağırlık", "agirlik", "kg"]):
                spec_key = "agirlik"
            elif any(k in qn for k in ["menzil", "range", "wltp"]):
                spec_key = "menzil"
            elif any(k in qn for k in ["depo", "yakıt deposu", "yakit deposu", "fuel tank", "tank"]):
                spec_key = "depo"

        if not spec_key:
            return None

        # ✅ artık depo branch çalışır
        if spec_key == "depo":
            def tank_from_fuel_specs(mslug: str) -> float | None:
                try:
                    spec = (FUEL_SPECS or {}).get(mslug, {}) or {}
                except Exception:
                    spec = {}
                for k in ("tank_l", "tank", "depo_l", "depo"):
                    if k in spec:
                        try:
                            return float(spec[k])
                        except Exception:
                            pass
                return None

            m1, m2 = models[0].lower(), models[1].lower()

            v1 = tank_from_fuel_specs(m1)
            v2 = tank_from_fuel_specs(m2)

            # SQL’de varsa onu da dene (yoksa sözlükle devam)
            r1 = self._spec_range_from_imported(m1, "depo")
            r2 = self._spec_range_from_imported(m2, "depo")

            # sözlük yoksa SQL’den tek değer seç
            if v1 is None:
                v1 = self._pick_single_value_from_range(r1, trim_hint=self._default_trim_for_model(m1))
            if v2 is None:
                v2 = self._pick_single_value_from_range(r2, trim_hint=self._default_trim_for_model(m2))

            if v1 is None and v2 is None:
                return None  # üstteki akış Neo4j'e düşsün

            label = "Yakıt deposu (L)"
            def fmt(x): return "—" if x is None else f"{float(x):.0f} L"

            out = [
                f"{label}:",
                f"- {m1.title()}: {fmt(v1)}",
                f"- {m2.title()}: {fmt(v2)}",
            ]
            if v1 is not None and v2 is not None:
                out.append(f"- Fark ({m2.title()} - {m1.title()}): {float(v2 - v1):.0f} L")
            return "\n".join(out)

        try:
            spec_key = self._spec_key_from_query(user_message)
        except Exception:
            spec_key = None

        # _spec_key_from_query içinde ağırlık yoksa bile burada yakalayalım
        qn = normalize_tr_text(user_message).lower()
        if not spec_key:
            if any(k in qn for k in ["ağırlık", "agirlik", "kg"]):
                spec_key = "agirlik"
            elif any(k in qn for k in ["menzil", "range", "wltp"]):
                spec_key = "menzil"

        if not spec_key:
            return None

        # satır seçimi için query context'i kaydet (şehir içi/kombine ayrımı)
        try:
            self._LAST_SPEC_QUERY = qn
        except Exception:
            pass

        # sadece ilk 2 modeli kıyasla (istersen 3+ için genişletirsin)
        m1, m2 = models[0].lower(), models[1].lower()

        r1 = self._spec_range_from_imported(m1, spec_key)
        r2 = self._spec_range_from_imported(m2, spec_key)
        if spec_key == "menzil":
            unit = "km"
            label = (r1.get("title") if r1 and r1.get("title") else "Menzil (WLTP)")
        if not r1 and not r2:
            return None

        # birim/etiket
        unit = ""
        if spec_key == "agirlik":
            unit = "kg"
            label = "Ağırlık"
        elif spec_key == "menzil":
            unit = "km"
            label = "Menzil"
        elif spec_key == "0-100":
            unit = "sn"
            label = "0-100 km/h"
        else:
            label = spec_key

        def fmt_range(rr):
            if not rr:
                return "—"
            mn, mx = rr.get("min"), rr.get("max")
            if mn is None or mx is None:
                return "—"
            if abs(mx - mn) < 1e-6:
                return f"{mn:.0f} {unit}".strip()
            return f"{mn:.0f}–{mx:.0f} {unit}".strip()

        # --- TRIM HINT: kullanıcı trim yazdıysa onu kullan, yazmadıysa modele göre default ---
        trims_in_q = list(extract_trims(qn))  # senin fonksiyonun zaten var
        global_trim_hint = trims_in_q[0] if len(trims_in_q) == 1 else None

        t1 = global_trim_hint or self._default_trim_for_model(m1)
        t2 = global_trim_hint or self._default_trim_for_model(m2)

        n1 = self._pick_single_value_from_range(r1, trim_hint=t1)
        n2 = self._pick_single_value_from_range(r2, trim_hint=t2)

        # Birim/etiket
        if spec_key == "agirlik":
            unit, label = "kg", "Ağırlık"
            fmt = lambda x: f"{x:.0f} {unit}"
        elif spec_key == "menzil":
            unit, label = "km", "Menzil (Kombine)"
            fmt = lambda x: f"{x:.0f} {unit}"
        elif spec_key == "0-100":
            unit, label = "sn", "0-100 km/h"
            # ✅ ondaliği KORU
            fmt = lambda x: f"{x:.1f} {unit}"
        elif spec_key == "batarya":
            unit, label = "kWh", "Batarya Kapasitesi"
            fmt = lambda x: f"{x:.0f} {unit}"   # istersen .1f
        else:
            unit, label = "", spec_key
            fmt = lambda x: f"{x}"

        a1 = "—" if n1 is None else fmt(float(n1))
        a2 = "—" if n2 is None else fmt(float(n2))

        diff_txt = ""
        if (n1 is not None) and (n2 is not None):
            d = float(n2) - float(n1)
            if spec_key == "0-100":
                diff_txt = f"{d:.1f} {unit}"
            else:
                diff_txt = f"{d:.0f} {unit}".strip()


        # fark aralığı (min/max aralığı varsa)
        diff_txt = ""
        if r1 and r2 and (r1.get("min") is not None) and (r1.get("max") is not None) and (r2.get("min") is not None) and (r2.get("max") is not None):
            # min fark = (m2_min - m1_max) , max fark = (m2_max - m1_min)
            dmin = (r2["min"] - r1["max"])
            dmax = (r2["max"] - r1["min"])
            # mutlak aralık yaz
            lo = min(dmin, dmax)
            hi = max(dmin, dmax)
            if abs(hi - lo) < 1e-6:
                diff_txt = f"{hi:.0f} {unit}"
            else:
                diff_txt = f"{lo:.0f}–{hi:.0f} {unit}"

        out = []
        out.append(f"{label} (SQL):")
        out.append(f"- {m1.title()} ({(t1 or '—')}): {a1}")
        out.append(f"- {m2.title()} ({(t2 or '—')}): {a2}")
        if diff_txt:
            out.append(f"- Fark ({m2.title()} - {m1.title()}): {diff_txt}")
        else:
            out.append("- Fark: (hesaplanamadı)")
        out.append("İstersen farklı donanım/motor (trim) ile tekrar hesaplayayım.")
        return "\n".join(out)


     


    def _assistant_asked_question_recently(self, user_id: str) -> bool:
        st = self.user_states.get(user_id, {}) or {}
        last_a = (st.get("last_assistant_answer") or "").strip()
        if not last_a:
            return False

        # Son asistan cevabı soru mu?
        if "?" in last_a:
            return True

        # Soru işareti yoksa da bazı soru kalıpları
        t = normalize_tr_text(last_a).lower()
        if re.search(r"\b(ister misiniz|ister misin|belirtir misiniz|seçer misiniz|hangisini)\b", t):
            return True

        return False


    def _rewrite_followup_if_needed(self, user_id: str, msg: str) -> str:
        """
        Pending set edilmemiş olsa bile:
        - Asistan bir önceki mesajda soru sorduysa
        - Kullanıcı kısa bir cevap verdiyse (evet/premium/2025 vb.)
        bunu follow-up gibi yeniden yazar.
        """
        if not msg:
            return msg
        # ✅ Kullanıcı mesajında model varsa follow-up rewrite yapma
        try:
            if self._extract_models_all(msg):
                return msg
        except Exception:
            pass
        # Pending varsa zaten _resolve_pending() halleder
        st = self.user_states.get(user_id, {}) or {}
        if st.get("pending"):
            return msg

        if self._assistant_asked_question_recently(user_id) and self._looks_like_followup(msg):
            last_a = (st.get("last_assistant_answer") or "").strip()
            # aktif modeli de ekle (varsa)
            model = (st.get("active_model") or "").strip()
            prefix = f"{model} " if model else ""
            return f"{prefix}Önceki soru: {last_a}\nKullanıcı yanıtı: {msg}".strip()

        return msg

    def _pending_from_assistant_text(self, assistant_text: str) -> tuple[str | None, dict]:
        """
        Asistan cevabı bir netleştirme sorusu mu? (trim/model/yıl vb.)
        Döner: (kind, payload) veya (None, {})
        """
        if not assistant_text:
            return None, {}

        t = normalize_tr_text(assistant_text).lower()

        # Donanım/trim seçtiriyor mu?
        if re.search(r"\bhangi\b.*\b(donan[ıi]m|paket|versiyon|donan[ıi]m\s*seviyesi)\b", t):
            # cevapta model geçiyorsa onu da payload'a koy
            ms = self._extract_models_all(assistant_text) if hasattr(self, "_extract_models_all") else []
            return "trim_select", {"topic": "donanım seviyesi", "models": ms[:1]}

        # Model yılı / yıl sorusu
        if re.search(r"\bhangi\b.*\b(model\s*y[ıi]l[ıi]|y[ıi]l)\b", t):
            ms = self._extract_models_all(assistant_text) if hasattr(self, "_extract_models_all") else []
            return "clarification", {"topic": "model yılı", "models": ms[:1]}

        return None, {}

    def _verify_answer_fit(
        self,
        question: str,
        candidate_text: str,
        *,
        group: str | None = None,
        score: float | None = None,
        strict: bool = True
    ) -> bool:
        """
        Tek iş: candidate_text, question'ı cevaplıyor mu?
        - Domain uyumu (EQUIP/SPEC/PRICE)
        - Token overlap
        - Sayısal gerekiyorsa sayısal var mı
        - Emin değilsek LLM YES/NO doğrulama
        """
        if not candidate_text or not question:
            return False

        # 1) Senin mevcut genel gate'in varsa onu kullan
        try:
            if score is not None:
                ok = self._should_use_kb_hit_general(question, float(score), group, candidate_text)
            else:
                ok = self._should_use_kb_hit_general(question, 0.77, group, candidate_text)
            if ok:
                return True
        except Exception:
            pass

        # 2) Daha sıkı modda, overlap şartı uygula
        if strict:
            try:
                if not self._content_overlap_ok(question, candidate_text, min_overlap=1):
                    # overlap yoksa son karar: LLM verify
                    return bool(self._llm_verify_hit(question, candidate_text))
            except Exception:
                # overlap hesaplayamazsa LLM verify
                return bool(self._llm_verify_hit(question, candidate_text))

        # 3) Sıkı değilse bile son kurtarıcı LLM verify
        try:
            return bool(self._llm_verify_hit(question, candidate_text))
        except Exception:
            return False

    def _maybe_set_pending(self, user_id: str, assistant_text: str, context: dict):
        """
        assistant_text: asistanın döndürdüğü son cevap
        context: o turda hangi modeller/trimler konuşuldu, hangi moddaydık vb.
        """
        if not assistant_text:
            return

        st = self.user_states.setdefault(user_id, {})

        # basit sinyal: cevap soru ile bitiyor mu?
        if "?" not in assistant_text:
            return

        # örnek: kıyas sorularında "hangisi daha önemli?" -> compare_preference
        # bunu daha genel yapmak için context üzerinden kind ver:
        kind = context.get("pending_kind") or "clarification"

        st["pending"] = {
            "kind": kind,
            "payload": context.get("pending_payload", {}),
            "created_at": time.time(),
            "expires_at": time.time() + 180,  # 3 dk
            "question": assistant_text[-250:]  # debug için
        }
    def _looks_like_followup(self, msg: str) -> bool:
        if not msg:
            return False
        m = msg.strip()
        if len(m) <= 18:
            return True  # "ekonomik olsun", "evet", "hayır", "DSG", "şehir içi" vb.
        if "?" in m:
            return False  # genelde yeni soru
        # "olsun/olması/isterim/tercihim" gibi cevap kalıpları
        low = normalize_tr_text(m).lower()
        # ✅ trim kelimesiyse kesin follow-up
        if low in set(TRIM_VARIANTS_FLAT):
            return True
        if any(k in low for k in ["olsun", "olması", "isterim", "tercihim", "öncelik", "benim için", "bana göre"]):
            return True
        return False
    def _resolve_pending(self, user_id: str, msg: str) -> str:
        st = self.user_states.get(user_id, {}) or {}
        pend = st.get("pending")
        if not pend:
            return msg

        if time.time() > float(pend.get("expires_at") or 0):
            st["pending"] = None
            return msg

        if not self._looks_like_followup(msg):
            return msg

        kind = pend.get("kind")
        payload = pend.get("payload", {}) or {}

        # ✅ En genel fallback: “Önceki soruya yanıt: ...”
        base = payload.get("topic") or "Önceki soru"
        models = payload.get("models") or []

        if kind == "compare_preference" and len(models) >= 2:
            st["pending"] = None
            m1, m2 = models[0], models[1]
            return f"{m1} ve {m2} karşılaştırması: önceliğim {msg}".strip()

        # başka pending türleri:
        if kind == "yesno":
            st["pending"] = None
            return f"{base}: yanıt {msg}".strip()

        if kind == "trim_select":
            st["pending"] = None
            return f"{base}: seçtiğim donanım {msg}".strip()
        st["pending"] = None
        models = payload.get("models") or []
        base_q = payload.get("base_question") or msg

        mm = " ve ".join(models[:2]) if len(models) >= 2 else ""
        ans = normalize_tr_text(msg).lower()

        if "teknik" in ans:
            return f"{mm} {base_q}".strip()
        if "donan" in ans or "donanim" in ans:
            return f"{mm} {base_q}".strip()

        # beklenmeyen cevap -> tek soru
        return f"{mm} {base_q} (teknik mi donanım mı?)".strip()
        # default
        st["pending"] = None
        return f"{base}: {msg}".strip()

    def _get_active_model(self, user_id: str) -> str | None:
        st = self.user_states.get(user_id, {}) or {}
        m = (st.get("active_model") or "").strip().lower()
        return m or None

    def _set_active_model(self, user_id: str, model: str | None, *, from_user: bool = True):
        st = self.user_states.setdefault(user_id, {})

        if model:
            m = model.strip().lower()

            # mevcut compare context'i oku
            cm = st.get("cmp_models") or []
            cm = [str(x).strip().lower() for x in cm if str(x).strip()]
            cm = list(dict.fromkeys(cm))

            st["active_model"] = m

            # ✅ last_user_model sadece gerçekten kullanıcı tek model söylediyse güncellensin
            if from_user:
                st["last_user_model"] = m

                # ✅ ÖNEMLİ: Halihazırda compare moddaysak (2 model) burada cmp_models'ı EZME
                # (multi bağlam korunur; tek modele düşürme işini _resolve_slots yapıyor)
                if len(cm) < 2:
                    st["cmp_models"] = [m]

            # ✅ last_models: compare varsa 2 modeli koru
            cm2 = st.get("cmp_models") or []
            cm2 = [str(x).strip().lower() for x in cm2 if str(x).strip()]
            cm2 = list(dict.fromkeys(cm2))
            if len(cm2) >= 2:
                st["last_models"] = set(cm2[:2])
            else:
                st["last_models"] = {m}

        else:
            st["active_model"] = None




    def _update_active_model_from_answer(self, user_id: str, user_message: str, assistant_answer: str):
        """
        Kullanıcı yeni model yazmadıysa, asistan cevabından aktif modeli günceller.
        - Cevapta TEK model geçiyorsa -> active_model = o
        - Kullanıcı 'tek model' istediyse -> cevapta geçen ilk modeli active_model yap
        """
        if not assistant_answer:
            return

        # Kullanıcı mesajında model varsa zaten _apply_model_memory/_current_model güncelliyor
        if self._extract_models_all(user_message or ""):
            return

        # Asistan cevabındaki modeller (sıralı)
        ans_models = self._extract_models_all(assistant_answer or "")
        if not ans_models:
            return

        # 1) Cevapta tek model: en güvenlisi
        if len(ans_models) == 1:
            self._set_active_model(user_id, ans_models[0], from_user=False)
            return

        # 2) Kullanıcı "sadece/tek/1 model" diyorsa: cevaptaki ilk modeli kilitle
        import re
        qn = normalize_tr_text(user_message or "").lower()
        if re.search(r"\b(sadece|tek|1)\s*model\b", qn):
            self._set_active_model(user_id, ans_models[0])
            return

        # Aksi halde (cevapta birden fazla model var) aktif model KİLİTLEME.

    def _is_model_recommendation_intent(self, text: str) -> bool:
        if not text:
            return False
        t = normalize_tr_text(text).lower()

        # araç seçimi / öneri niyeti
        keys = [
            "model öner", "model oneri", "öner", "oneri", "tavsiye",
            "hangi modeli", "hangi model", "hangisini almalıyım", "hangisini almalıyim",
            "araba bakıyorum", "arac bakiyorum", "araç bakıyorum",
            "az yakan", "az yakıt", "az yakit", "ekonomik", "düşük tüketim", "dusuk tuketim",
            "küçük", "kucuk", "kompakt", "şehir içi", "sehir ici"
        ]
        if any(k in t for k in keys):
            return True

        return False

    def _is_tdi_question(self, text: str) -> bool:
        t = normalize_tr_text(text or "").lower()
        return ("tdi" in t) or ("dizel" in t) or ("diesel" in t)
    def _answer_tdi_rule(self, user_message: str) -> str:
        """
        Kurumsal kural: TDI sadece Superb + Kodiaq.
        Burada LLM yok, DB yok -> direkt kesin cevap.
        """
        models = list(self._extract_models_all(user_message or ""))  # senin mevcut fonksiyonun
        models = [m.lower() for m in models]

        allowed = getattr(self, "TDI_MODELS", {"superb", "kodiaq"})

        # Kullanıcı spesifik bir model sormuşsa:
        if models:
            m = models[0]
            if m in allowed:
                return f"Evet, {m.title()} modelinde TDI motor seçeneği bulunmaktadır. Hangi model yılı için bakmamı istersiniz?"
            else:
                # ✅ Karoq gibi yanlış yönlenmeyi burada kesin kesiyoruz
                allow_txt = " ve ".join([x.title() for x in sorted(allowed)])
                return f"Hayır, {m.title()} modelinde TDI motor seçeneği bulunmuyor. TDI motor seçenekleri sadece {allow_txt} modellerinde sunuluyor. Hangisini incelim?"

        # Kullanıcı genel soruyorsa:
        allow_txt = " ve ".join([x.title() for x in sorted(allowed)])
        return f"TDI motor seçenekleri güncel ürün gamında sadece {allow_txt} modellerinde bulunmaktadır. Superb mi Kodiaq mı düşünüyorsunuz?"

    def _is_powertrain_question(self, text: str) -> bool:
        t = normalize_tr_text(text or "").lower()
        keys = [
            "tdi", "tsi", "dizel", "diesel", "benzin", "hybrid", "hibrit",
            "mhev", "m-hev", "m he v",
            "phev", "p-hev", "plug in", "plug-in",
            "motor", "motor seçene", "motor secene",
            "şanzıman", "dsg", "4x4", "awd", "çekiş", "cekis"
        ]
        return any(k in t for k in keys)
    def _sanitize_model_hallucinations(self, user_message: str, answer: str, evidence: str = "") -> str:
        """
        Kullanıcı sormadığı ve kanıtta geçmeyen model adlarını cevaptan ayıklar.
        Özellikle motor/tdi/dizel gibi riskli sorularda kullan.
        """
        if not answer:
            return answer

        # Kullanıcının izin verdiği modeller: soruda geçen + kanıtta geçen
        asked = set(self._extract_models_all(user_message or ""))
        ev_models = set(self._extract_models_all(evidence or "")) if evidence else set()
        allowed = asked | ev_models

        # Eğer kullanıcı hiç model yazmadıysa: cevaptan TÜM model isimlerini temizle
        # (çünkü “hangi modellerde TDI var?” sorusunda uydurma riski çok yüksek)
        all_models = {"fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"}

        def drop_sentence_if_has_disallowed_model(sent: str) -> bool:
            s_models = set(self._extract_models_all(sent))
            # disallowed = sent içindeki modellerden allowed dışı olanlar
            disallowed = (s_models - allowed) if allowed else s_models
            return bool(disallowed)

        # Cümlelere böl, “yasak model” içeren cümleleri at
        import re
        parts = re.split(r"(?<=[.!?])\s+", answer.strip())
        kept = [p for p in parts if p.strip() and not drop_sentence_if_has_disallowed_model(p)]

        cleaned = " ".join(kept).strip()

        # Eğer temizleyince çok boşaldıysa: güvenli yönlendirici cevap dön
        if len(cleaned) < 20:
            if self._is_powertrain_question(user_message):
                return (
                    "TDI (dizel) motor seçenekleri model yılına ve pazara göre değişebiliyor. "
                    "Hangi Škoda modeli ve hangi model yılı (örn. 2024/2025) için kontrol etmemi istersiniz?"
                )
            return "Hemen yardımcı olayım 😊 Hangi Škoda modelini düşünüyorsunuz?"

        return cleaned

    def _sanitize_invalid_trims_in_answer(self, model: str, text: str) -> str:
        """
        Cevap içinde modele ait olmayan trim/donanım adı geçiyorsa temizler.
        Basit sürüm: geçersiz trim kelimelerini kaldırır.
        """
        if not text or not model:
            return text

        model = model.lower().strip()
        valid = set(self.MODEL_VALID_TRIMS.get(model, []))

        # Sisteminde geçen trim varyant sözlüğünü kullan (VARIANT_TO_TRIM/normalize_trim_str varsa)
        # Yoksa en azından temel trim kelimelerini yakala:
        possible = [
            "premium", "prestige", "elite", "sportline", "monte carlo", "rs",
            "e prestige 60", "e sportline 60", "e sportline 85x",
            "coupe e sportline 60", "coupe e sportline 85x", "l&k crystal", "sportline phev"
        ]

        low = text.lower()

        # Metinde geçen trim adaylarını bul
        mentioned = []
        for t in possible:
            if t in low:
                mentioned.append(t)

        # Geçersizleri temizle
        for t in mentioned:
            # t kanonik değilse kanoniğe çevir (varsa)
            canon = VARIANT_TO_TRIM.get(t, t)
            if canon not in valid:
                # direkt kelimeyi kaldır (trim’i tamamen sil)
                text = re.sub(rf"\b{re.escape(t)}\b", "", text, flags=re.IGNORECASE)

        # boşlukları toparla
        text = re.sub(r"\s{2,}", " ", text).strip()
        return text

    def _build_context_pack(self, user_id: str, user_message: str) -> dict:
        # --- 1) Slots (yapılandırılmış durum) ---
        model = None
        try:
            model = self._current_model(user_id, user_message)
        except Exception:
            model = None

        trims = []
        try:
            trims = list(extract_trims((user_message or "").lower()))
        except Exception:
            trims = []

        domain = "OTHER"
        try:
            domain = self._infer_domain(user_message)
        except Exception:
            pass

        slots = {
            "active_model": model,
            "trims": trims,
            "domain": domain,
            "cs_route": (self.user_states.get(user_id, {}) or {}).get("cs_answer_type"),
            "cs_ratio": (self.user_states.get(user_id, {}) or {}).get("cs_ratio_01"),
        }

        # --- 2) Evidence (seçilmiş kanıt) ---
        # En pratik: senin hazır fonksiyonun
        evidence = ""
        try:
            evidence = self._build_db_context(user_message, user_id=user_id, relax=True) or ""
        except Exception:
            evidence = ""

        # --- 3) Summary (kısa konuşma özeti) ---
        st = self.user_states.get(user_id, {}) or {}
        prev_q = (st.get("last_user_message") or "")[:300]
        prev_a = (st.get("last_assistant_answer") or "")[:400]
        summary = ""
        if prev_q or prev_a:
            summary = f"Önceki soru: {prev_q}\nÖnceki yanıt: {prev_a}"

        return {"slots": slots, "evidence": evidence, "summary": summary}


    def _infer_domain(self, q: str) -> str:
        """EQUIP / SPEC / PRICE / OTHER"""
        qn = normalize_tr_text(q or "").lower()

        if self._is_price_intent(q):
            return "PRICE"

        # var mı / bulunuyor mu -> donanım
        equip_triggers = [
            "donanım", "donanim", "opsiyonel", "standart", "paket", "özellik", "ozellik",
            "hangi paket", "hangi donanım", "hangi donanim", "hangi versiyon", "hangi versiyonda",
            "hangi pakette", "hangi donanımda", "hangi donanimda"
        ]
        if self._is_equipment_presence_question(q) or any(k in qn for k in equip_triggers):
            return "EQUIP"


        # teknik/sayı odaklı -> SPEC
        spec_kw = [
            "tork","güç","guc","beygir","hp","ps","kw","0-100","hızlanma","ivme",
            "maksimum hız","menzil","range","tüketim","l/100","co2","emisyon",
            "uzunluk","genişlik","yukseklik","yükseklik","dingil","bagaj","hacim","ölçü","boyut", "depo", "yakıt deposu", "yakit deposu", "depo hacmi", "fuel tank"
        ]
        if any(k in qn for k in spec_kw):
            return "SPEC"

        return "OTHER"


    def _content_overlap_ok(self, q: str, text: str, min_overlap: int = 1) -> bool:
        import re
        qn = normalize_tr_text(q or "").lower()
        tn = normalize_tr_text(text or "").lower()

        STOP = {
            "var","yok","mi","mı","mu","mü","ne","nedir","ile","ve","veya","icin","için",
            "donanım","donanim","özellik","ozellik","paket","model","skoda",
            "fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq",
            "premium","prestige","sportline","elite","rs","monte","carlo"
        }

        qt = [w for w in re.findall(r"[0-9a-zçğıöşü]+", qn) if w not in STOP and len(w) >= 3]
        tt = set([w for w in re.findall(r"[0-9a-zçğıöşü]+", tn) if w not in STOP and len(w) >= 3])

        overlap = sum(1 for w in set(qt) if w in tt)
        return overlap >= min_overlap


    def _needs_numbers(self, q: str) -> bool:
        qn = normalize_tr_text(q or "").lower()
        # “kaç / ne kadar / ölçü / teknik” gibi sorular çoğu zaman sayısal cevap ister
        return any(k in qn for k in [
            "kaç", "ne kadar", "km", "km/h", "sn", "nm", "kw", "ps", "hp",
            "uzunluk", "genişlik", "yükseklik", "dingil", "bagaj", "hacim",
            "menzil", "tork", "güç", "0-100", "tüketim", "co2"
        ])


    def _llm_verify_hit(self, q: str, hit_text: str) -> bool:
        """
        Emin değilsek ucuz LLM'e YES/NO doğrulat.
        NOT: Bu, tek tek kural yazdırmaz; genel bir guard'dır.
        """
        import os, re
        try:
            resp = self.client.chat.completions.create(
                model=os.getenv("VERIFY_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role":"system","content":
                        "You are a strict verifier. Decide if the given TEXT answers the QUESTION.\n"
                        "Return ONLY 'YES' or 'NO'. No explanation."},
                    {"role":"user","content": f"QUESTION:\n{q}\n\nTEXT:\n{hit_text}"}
                ],
                temperature=0.0,
                max_tokens=3
            )
            out = (resp.choices[0].message.content or "").strip().upper()
            return out.startswith("YES")
        except Exception:
            return False


    def _should_use_kb_hit_general(self, q: str, score: float, group: str | None, hit_text: str) -> bool:
        """
        Genel gate:
        - domain uyumu
        - içerik overlap
        - sayısal gerekirse sayı şartı
        - emin değilsek LLM verify
        """
        dom = self._infer_domain(q)
        grp = (group or "").upper().strip()

        # 1) Domain uyumu (genel)
        if dom == "SPEC" and grp not in {"SPEC"}:
            return False
        if dom == "PRICE" and grp not in {"PRICE"}:
            return False
        if dom == "EQUIP" and grp not in {"EQUIP"}:
            return False

        # 2) Sayı gerekiyorsa hit'te sayı yoksa reddet (genel)
        if self._needs_numbers(q) and not any(ch.isdigit() for ch in (hit_text or "")):
            # burada LLM verify bile yapmaya gerek yok, genelde kesin false positive
            return False

        # 3) Basit overlap: en az 1 anlamlı kelime ortak olsun
        # Skor çok yüksekse (örn >=0.78) overlap’i biraz gevşetebiliriz
        if score < 0.78:
            if not self._content_overlap_ok(q, hit_text, min_overlap=1):
                # Emin değilsek LLM doğrula (genel kurtarıcı)
                return self._llm_verify_hit(q, hit_text)

        return True

    def _is_weak_answer(self, query: str, answer: str) -> bool:
        if not answer:
            return True
        a = (answer or "").strip()
        if len(a) < 30:
            return True

        # teknik soruysa ama cevapta hiç sayı yoksa -> weak
        try:
            is_spec = bool(self._spec_key_from_query(query) or self._find_requested_specs(query))
        except Exception:
            is_spec = False
        if is_spec and not re.search(r"\d", a):
            return True

        return bool(self.WEAK_ANSWER_RE.search(a))

    def _extract_models_all(self, text: str) -> list[str]:
        """
        Sıkı + gevşek + spaced model yakalamayı tek yerde toplar,
        sırayı korumaya çalışır.
        """
        if not text:
            return []

        t = text or ""

        # 1) Sıralı yakalama (extract_model_trim_pairs zaten sende var)
        ordered = []
        try:
            pairs = extract_model_trim_pairs(t.lower())
            for m, _ in pairs:
                m = (m or "").strip().lower()
                if m and m not in ordered:
                    ordered.append(m)
        except Exception:
            pass

        # 2) Sıkı set (token bazlı)
        strict = []
        try:
            strict = list(self._extract_models(t))
        except Exception:
            strict = []

        # 3) Loose + spaced
        loose = []
        try:
            loose = list(self._extract_models_loose(t) | self._extract_models_spaced(t))
        except Exception:
            loose = []

        # Birleştir (sırayı koru)
        out = []
        for x in ordered + strict + loose:
            if x and x not in out:
                out.append(x)
        return out

    def _should_fallback_to_assistant(self, text: str) -> bool:
        if not text:
            return True
        t = (text or "").strip()
        if len(t) < 12:   # çok kısa / boş gibi
            return True
        # mevcut fonksiyonun zaten var:
        if self._is_negative_kb_answer(t):
            return True
        return False

        # ------------------------------------------------------------
    #  EQUIPMENTLIST için HF embedding tabanlı RAM index
    # ------------------------------------------------------------
    def _facts_from_kb_row(self, group: str, table_name: str, row: dict, user_message: str) -> dict:
        model = (self._guess_model_for_query(table_name) or "").title()

        if group == "SPEC":
            title = row.get("Ozellik") or row.get("Özellik") or row.get("SpecName") or row.get("Name") or row.get("Title") or ""
            skip = {"id","ID","Model","Ozellik","Özellik","SpecName","Name","Title","Attribute"}
            trim_cols = [c for c in row.keys() if c not in skip]

            chosen = []
            pref = getattr(self, "CURRENT_TRIM_HINT", None)
            if pref:
                col = self._match_trim_column_name(pref, trim_cols)
                if col:
                    v = str(row.get(col) or "").strip()
                    if v:
                        chosen.append((col, v))

            if not chosen:
                for c in trim_cols:
                    v = str(row.get(c) or "").strip()
                    if v:
                        chosen.append((c, v))
                    if len(chosen) >= 2:
                        break

            return {"kind": "SPEC", "model": model, "title": str(title).strip(),
                    "values": [{"trim_col": c, "value": v} for c, v in chosen]}

        if group == "EQUIP":
            title = row.get("Ozellik") or row.get("Özellik") or row.get("Donanim") or row.get("Donanım") or ""
            skip = {"id","ID","Model","Ozellik","Özellik","Donanim","Donanım","Equipment","Name","Title"}
            trim_cols = [c for c in row.keys() if c not in skip]

            status = [{"trim_col": c, "status": self._normalize_equipment_status(row.get(c))} for c in trim_cols[:10]]
            return {"kind": "EQUIP", "model": model, "title": str(title).strip(), "status": status}

        return {"kind": group, "model": model, "raw": self._row_to_text(table_name, row)}
    def _nlg_sales_from_facts(self, facts: dict, user_message: str) -> str:
        import os, json, re

        sys = (
            "Sen Škoda Türkiye dijital satış danışmanısın. Sana verilecek FACTS tek kaynaktır.\n"
            "KURALLAR:\n"
            "- FACTS dışında yeni teknik bilgi UYDURMA.\n"
            "- FACTS içindeki sayı ve birimleri AYNEN koru.\n"
            "- 3–5 cümle yaz: net cevap -> fayda/duygu -> 1 kısa soru.\n"
        )

        payload = {"question": user_message, "facts": facts}

        resp = self.client.chat.completions.create(
            model=os.getenv("GEN_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.4,
            max_tokens=260,
        )
        out = (resp.choices[0].message.content or "").strip()

        # basit imza kontrol: facts içindeki sayılar çıktı içinde var mı?
        def nums(s: str):
            return {"".join(ch for ch in n if ch.isdigit()) for n in re.findall(r"\d+(?:[.,]\d+)?", s or "")}

        expected = set()
        for v in (facts.get("values") or []):
            expected |= nums(v.get("value",""))

        if expected:
            got = nums(out)
            if not expected.issubset(got):
                return ""  # güvenlik: rakamlar tutmadı

        return out

    def _kb_best_hit(self, query: str, user_id: str | None = None):
        is_equip = self._is_equipment_presence_question(query or "")
        k = 12 if is_equip else 1

        hits = self._kb_vector_search(query, k=k, min_score=0.0, user_id=user_id)
        if not hits:
            return None

        if not is_equip:
            return hits[0]

        qn = normalize_tr_text(query).lower()
        # kullanıcı “elektrikli koltuk” gibi net bir ifade yazdıysa
        exact_phrases = []
        if "elektrikli koltuk" in qn:
            exact_phrases.append("elektrikli koltuk")

        def ozellik_from_text(t: str) -> str:
            # _row_to_text EquipmentList’te ilk parça genelde Ozellik oluyor
            return (t.split("|", 1)[0] if t else "").strip()

        def score_hit(s: float, d: dict) -> tuple:
            txt = (d.get("text") or "")
            oz  = normalize_tr_text(ozellik_from_text(txt)).lower()

            bonus = 0
            # 1) exact phrase Ozellik içinde geçiyorsa güçlü bonus
            for ph in exact_phrases:
                if ph in oz:
                    bonus += 100
            # 2) “Ozellik tam eşitlik” daha da güçlü
            if exact_phrases and oz == exact_phrases[0]:
                bonus += 200

            # 3) EquipmentList satırlarını tercih et (Imported/Price kaçmasın)
            tname = (d.get("table") or "").lower()
            if tname.startswith("equipmentlist_"):
                bonus += 20

            return (bonus, s)  # önce bonus, sonra vektör skoru

        best = max(hits, key=lambda it: score_hit(it[0], it[1]))
        return best


    def _sql_has_column(self, cur, table_name: str, col_name: str) -> bool:
        """
        dbo.<table_name> içinde col_name var mı? (safe check)
        """
        try:
            cur.execute(
                "SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(?) AND name = ?",
                (f"dbo.{table_name}", col_name)
            )
            return cur.fetchone() is not None
        except Exception:
            return False

    def _spec_key_from_text(self, text: str) -> str | None:
        if not text:
            return None
        t = normalize_tr_text(text).lower()

        if any(k in t for k in ["menzil", "range", "wltp"]):
            return "menzil"
        if any(k in t for k in ["uzunluk", "genişlik", "genislik", "yükseklik", "yukseklik", "dingil", "boyut"]):
            return "boyutlar"
        if "bagaj" in t or "dm3" in t:
            return "bagaj"
        if any(k in t for k in ["ağırlık", "agirlik", "kg"]):
            return "agirlik"
        if "lastik" in t:
            return "lastik"
        if any(k in t for k in ["tork", "nm"]):
            return "tork"
        if any(k in t for k in ["güç", "guc", "beygir", "hp", "ps", "kw", "power"]):
            return "guc"
        if "0-100" in t or "0 100" in t or "hızlanma" in t or "ivme" in t:
            return "0-100"
        if any(k in t for k in ["maksimum hız", "maks hiz", "max speed", "top speed", "km/h"]):
            return "max_hiz"
        if any(k in t for k in ["tüketim", "tuketim", "l/100", "lt/100"]):
            return "tuketim"
        if "co2" in t or "emisyon" in t:
            return "co2"
        if any(k in t for k in ["batarya", "kwh"]):
            return "batarya"
        if any(k in t for k in ["şarj", "sarj", "ac", "dc", "10-80", "10 80"]):
            return "sarj"

        return None


    def _spec_key_from_query(self, query: str) -> str | None:
        if not query:
            return None
        q = normalize_tr_text(query).lower()
        # ✅ Trip-calc sorularını SPEC'e sokma
        if re.search(r"\b(kac|kaç)\s+(sarj|şarj)\b", q) or re.search(r"\b(kac|kaç)\s+depo\b", q):
            return None
        if any(k in q for k in ["menzil", "range", "wltp"]):
            return "menzil"
        if any(k in q for k in ["uzunluk", "genişlik", "genislik", "yükseklik", "yukseklik", "dingil", "boyut"]):
            return "boyutlar"
        if "bagaj" in q:
            return "bagaj"
        if any(k in q for k in ["ağırlık", "agirlik"]):
            return "agirlik"
        if "lastik" in q:
            return "lastik"
        if "tork" in q:
            return "tork"
        if any(k in q for k in ["güç", "guc", "beygir", "hp", "ps", "kw"]):
            return "guc"
        if re.search(r"\b0\s*[-–—]?\s*100\b", q) or "hızlanma" in q or "ivme" in q:
            return "0-100"
        if any(k in q for k in ["maksimum hız", "maks hiz", "hız", "hiz", "max speed", "top speed"]):
            return "max_hiz"
        if any(k in q for k in ["tüketim", "tuketim", "l/100", "lt/100"]):
            return "tuketim"
        if "co2" in q or "emisyon" in q:
            return "co2"
        if any(k in q for k in ["batarya", "kwh"]):
            return "batarya"
        if any(k in q for k in ["şarj", "sarj", "ac", "dc"]):
            return "sarj"
        if any(k in q for k in ["depo", "yakıt deposu", "yakit deposu", "depo hacmi", "fuel tank"]):
            return "depo"

        return None

    def _is_product_range_intent(self, text: str) -> bool:
        t = normalize_tr_text(text or "").lower()
        keys = [
            "ürün gam", "urun gam", "model gam", "ürün gamı", "urun gami",
            "hangi modeller var", "model listesi", "modeller neler",
            "skoda ürün gam", "skoda model"
        ]
        return any(k in t for k in keys)

     


    def _is_optional_inference_answer(self, text: str) -> bool:
        if not text:
            return False
        raw = (text or "").lower()
        norm = (normalize_tr_text_light(text) or "").lower()

        # “standart donanım listesinde görünmüyor” + “opsiyonel” + “fiyat/opsiyon listesi” sinyali
        keys = [
            "standart donanım", "standart donanim", "standart değil", "standart degil",
            "opsiyonel", "opsiyon list", "fiyat / opsiyon", "fiyat/opsiyon", "fiyat", "opsiyon"
        ]
        hit = lambda s: any(k in s for k in keys)

        # Hem standart hem opsiyonel geçsin istiyoruz
        need1 = ("standart" in raw or "standart" in norm)
        need2 = ("opsiyon" in raw or "opsiyon" in norm)

        return need1 and need2 and (hit(raw) or hit(norm))

    def _is_optional_list_intent(self, text: str) -> bool:
        t = (text or "").lower()
        # opsiyon + donanım/paket + liste kelimeleri
        return (
            ("opsiyon" in t or "opsiyonel" in t)
            and ("donan" in t or "paket" in t)
            and any(w in t for w in ["neler", "nelerdir", "liste", "hepsi", "tümü", "tumu", "tamamı", "tamami"])
        )

    def _is_negative_kb_answer(self, text: str) -> bool:
        if not text:
            return True
        raw  = (text or "").lower().strip()
        norm = (normalize_tr_text_light(text) or "").lower().strip()

        NEG = [
            r"ulaşamıyorum", r"erişemiyorum",
            r"bilgi bulunmuyor", r"bilgi bulunamad", r"bilgi bulunmamakt",
            r"kayıt bulunmuyor", r"kayıt bulunamad", r"kayıt yok",
            r"veritaban.*(bulunamad|bulunmuyor|yok)",
            r"sorunuzu tam anlamad", r"tekrardan sorabilir misiniz",
        ]
        return any(re.search(p, raw, re.I) or re.search(p, norm, re.I) for p in NEG)

        def hit(p: str) -> bool:
            return (re.search(p, raw, re.I) is not None) or (re.search(p, norm, re.I) is not None)

        if any(hit(p) for p in NEG_PATTERNS):
            return True

        # ekstra güvenlik (LLM “ancak ...” diye eklese bile)
        if ("veritab" in raw or "veritab" in norm) and ("bulunamad" in raw or "bulunmamakt" in raw or "bulunamad" in norm or "bulunmamakt" in norm):
            return True

        return False




     
    def _missing_feature_msg(self, user_message: str, user_id: str | None = None) -> str:
        model = None
        try:
            model = self._current_model(user_id or "", user_message)
        except Exception:
            pass
        if not model:
            ms = list(self._extract_models(user_message or ""))
            model = ms[0] if ms else None

        if model:
            return f"İstediğiniz özellik {model.title()} için bulunmamaktadır."
        return "İstediğiniz özellik için bulunmamaktadır."

    def _otv_brackets_from_pricelist(self, model_slug: str) -> list[int]:
        """
        PriceList_KODA_<MODEL> tablosundaki kolon adlarından ÖTV yüzdelerini çıkarır.
        Örn: 'Anahtar_Teslim___80_OTV_' -> 80
        """
        import re, contextlib

        m = (model_slug or "").strip().lower()
        if not m:
            return []

        tname = self._latest_pricelist_table_for(m)
        if not tname:
            return []

        conn = self._sql_conn()
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT TOP 0 * FROM [dbo].[{tname}] WITH (NOLOCK)")
            cols = [c[0] for c in cur.description] if cur.description else []

            pcts = set()
            for c in cols:
                low = (c or "").lower()
                if "otv" not in low and "ötv" not in low:
                    continue
                # 25_OTV, %25 OTV, 25 ÖTV gibi varyantlar
                m1 = re.search(r"(\d{1,3})\s*[_\s-]*(?:otv|ötv)\b", low)
                if m1:
                    pcts.add(int(m1.group(1)))

            return sorted(pcts)
        finally:
            with contextlib.suppress(Exception): cur.close()
            with contextlib.suppress(Exception): conn.close()

    def _product_range_from_sql(self) -> list[dict]:
        import contextlib, re

        def norm_model_name(s: str) -> str:
            s = (s or "").strip()
            # "Enyaq iV" gibi yazımları normalize etmek istersen:
            if s.lower().startswith("enyaq"):
                return "Enyaq"
            return s

        conn = self._sql_conn()
        cur = conn.cursor()
        try:
            out = []

            # A) MODEL_SEGMENT tablosu (varsa)
            seg_items = []
            cur.execute("""
                SELECT TOP 1 name
                FROM sys.tables WITH (NOLOCK)
                WHERE name LIKE 'MODEL_SEGMENT_KODA_MY_%'
                ORDER BY name DESC
            """)
            row = cur.fetchone()
            if row:
                tname = row[0]
                cur.execute(f"SELECT TOP 500 * FROM dbo.[{tname}] WITH (NOLOCK)")
                cols = [c[0] for c in cur.description] if cur.description else []
                rows = cur.fetchall()

                def pick(colnames):
                    for c in colnames:
                        if c in cols:
                            return c
                    return None

                model_col = pick(["Model", "MODEL", "model"])
                seg_col   = pick(["Segment", "SEGMENT", "segment"])

                for r in rows:
                    d = {cols[i]: r[i] for i in range(len(cols))}
                    m = norm_model_name(str(d.get(model_col) or "").strip()) if model_col else ""
                    s = str(d.get(seg_col) or "").strip() if seg_col else ""
                    if m:
                        seg_items.append({"model": m, "segment": s})

            # B) sys.tables üzerinden modeller (her zaman ek kaynak)
            cur.execute("""
                SELECT name FROM sys.tables WITH (NOLOCK)
                WHERE name LIKE 'PriceList\\_KODA\\_%' ESCAPE '\\'
                OR name LIKE 'EquipmentList\\_KODA\\_%' ESCAPE '\\'
                OR name LIKE 'Imported\\_KODA\\_%' ESCAPE '\\'
            """)
            names = [r[0] for r in cur.fetchall()]

            table_models = set()
            for n in names:
                # ELROQ gibi isimleri yakalamak için daha toleranslı regex:
                m = re.search(r"KODA_([A-Z]+)(?:_|$)", (n or "").upper())
                if m:
                    table_models.add(m.group(1).title())

            # C) Birleştir (segment varsa segmenti koru)
            seg_map = {x["model"].lower(): x for x in seg_items}
            for tm in sorted(table_models):
                k = tm.lower()
                if k not in seg_map:
                    seg_map[k] = {"model": tm, "segment": ""}

            out = list(seg_map.values())

            # İstersen sabit bir sıralama ver:
            prefer = ["Fabia","Scala","Octavia","Superb","Kamiq","Karoq","Kodiaq","Elroq","Enyaq"]
            out.sort(key=lambda x: prefer.index(x["model"]) if x["model"] in prefer else 999)

            return out

        finally:
            with contextlib.suppress(Exception): cur.close()
            with contextlib.suppress(Exception): conn.close()

    def _build_db_context(self, user_message: str, user_id: str | None = None, relax: bool = False) -> str:
            parts = []

            q_norm = normalize_tr_text(user_message or "").lower()

            # 1) Model yakala (mesaj + state)
            model = None
            try:
                model = self._current_model(user_id or "", user_message)
            except Exception:
                model = None
            if not model:
                ms = list(self._extract_models(user_message or ""))
                model = ms[0] if ms else None

            # --- 0) MODEL SNAPSHOT (model yakalandıysa temel teknik verileri ekle) ---
            if model:
                try:
                    snap = []
                    for key in ["0-100", "güç", "tork", "maksimum hız", "menzil", "yakıt tüketimi", "co2", "bagaj hacmi"]:
                        v = self._generic_spec_from_sql(model, key)
                        if v:
                            snap.append(f"- {key}: {v}")
                    if snap:
                        parts.append("[MODEL_SNAPSHOT]\n" + "\n".join(snap))
                except Exception:
                    pass


            

            # 2) Öncelik: deterministik SQL (senin mevcut fonksiyonlarını kullan)
            # 2.a) Fiyat intent -> PriceList tek satır ya da trim liste
            if self._is_price_intent(user_message):
                md = self._price_row_from_pricelist(user_message, user_id=user_id)
                if md:
                    parts.append(f"[PRICE_SQL]\n{md}")

            # 2.b) Donanım var mı / opsiyonel mi
            # (EquipmentList + semantic + synonym arama zaten _feature_lookup_any içinde var)
            equip_like = (
                self._is_equipment_presence_question(user_message)
                or any(k in q_norm for k in [
                    "donanım", "donanim", "opsiyonel", "standart", "özellik", "ozellik",
                    "hangi paket", "hangi donanım", "hangi donanim", "hangi versiyon", "hangi pakette",
                    "hangi donanımda", "hangi donanimda"
                ])
            )

            # ✅ asıl yenilik: evidence ile de EQUIP'e sok
            if (not equip_like) and model:
                try:
                    equip_like = self._is_equipment_query_by_evidence(user_id or "", user_message)
                except Exception:
                    equip_like = False
            if equip_like and model:
                trims, status_map, feature_title = self._feature_lookup_any(model, user_message)
                # ✅ ZORUNLU: soru ↔ feature_title uyumlu mu?
                if feature_title:
                    if not self._is_safe_equipment_match(user_message, feature_title):
                        # emin değilsek LLM YES/NO da sor (çok kısa)
                        if not self._llm_verify_hit(user_message, feature_title):
                            trims, status_map, feature_title = [], {}, None
                if trims and status_map:
                    parts.append(f"[EQUIP_SQL]\nmodel={model}\nfeature={feature_title}\nstatus_map={status_map}")
                else:
                    try:
                        sem_hits = self._semantic_feature_match_equipment(model, user_message, topn=5)
                        if sem_hits:
                            lines = []
                            for h in sem_hits:
                                oz = h["ozellik"]
                                score = round(float(h["score"]), 3)
                                row = h["row"]
                                tcols = h["trim_cols"] or []
                                smap = {c: self._normalize_equipment_status(row.get(c)) for c in tcols}
                                lines.append(f"- sim={score} | ozellik={oz} | status_map={smap}")
                            parts.append("[EQUIP_NEAREST]\n" + "\n".join(lines))
                    except Exception:
                        pass
            # 2.c) Teknik metrik (0-100 / tork / güç / menzil vs.)
            requested_specs = []
            try:
                requested_specs = self._find_requested_specs(user_message) or []
            except Exception:
                requested_specs = []
            is_metric = bool(requested_specs) or any(k in q_norm for k in [
                "tork","güç","guc","beygir","hp","ps","kw","0-100","ivme","hızlanma","menzil","range","tüketim","co2","emisyon"
            ])
            if is_metric and model:
                val, canon_key, row_md = self._generic_spec_from_sql(model, q_norm, return_meta=True)
                if val:
                    parts.append(f"[SPEC_SQL]\nmodel={model}\ncanon={canon_key}\nvalue={val}\nrow={row_md or ''}")

            # 3) Hybrid RAG (KbVectors tabloların da DB’de) -> ekstra bağlam
            # Burada "cevap üretme", sadece top-k context çek.
            try:
                k = 18 if relax else 12
                min_score = 0.25 if relax else None
                hits = self._kb_vector_search(user_message, k=k, min_score=min_score, user_id=user_id)
                if hits:
                    ctx = "\n".join([f"- ({round(s,3)}) {d['text']}" for s, d in hits])
                    parts.append(f"[KBVECTORS]\n{ctx}")
            except Exception:
                pass

            # 4) Genel bilgi (ürün gamı / model overview) için DB_TEXT (önerdiğim KB_Text tablosu)
            # Eğer bunu kurduysan çok işe yarar (Fabia genel bilgi gibi).
            try:
                if ("ürün gam" in q_norm) or ("urun gam" in q_norm):
                    txt = self._kb_text_lookup(None, "PRODUCT_RANGE")
                    if txt:
                        parts.append(f"[KB_TEXT]\n{txt}")
                if model and any(x in q_norm for x in ["genel bilgi", "hakkında", "ile ilgili bilgi", "tanıt"]):
                    txt = self._kb_text_lookup(model.upper(), "MODEL_OVERVIEW")
                    if txt:
                        parts.append(f"[KB_TEXT]\n{txt}")
            except Exception:
                pass

            return "\n\n".join([p for p in parts if p.strip()]).strip()
    def _answer_from_db_only(self, user_message: str, user_id: str | None = None) -> str:
        q_norm = normalize_tr_text(user_message or "").lower()

        # ✅ ÖTV dilimi / oranı sorusu -> PriceList kolonlarından cevapla (fiyat göstermeden)
        if ("ötv" in q_norm or "otv" in q_norm) and any(k in q_norm for k in ["dilim", "oran", "yüzde", "%"]):
            model = None
            try:
                model = self._current_model(user_id or "", user_message)
            except Exception:
                model = None
            if not model:
                ms = list(self._extract_models(user_message or ""))
                model = ms[0] if ms else None

            if not model:
                return "ÖTV dilimini kontrol edebilmem için hangi Škoda modelini sorduğunuzu yazar mısınız?"

            pcts = self._otv_brackets_from_pricelist(model)
            if not pcts:
                return f"{model.title()} için PriceList tablosunda ÖTV yüzdesi bilgisi bulunamadı."

            if len(pcts) == 1:
                return f"{model.title()} için listemizde görünen ÖTV yüzdesi: %{pcts[0]}. Hangi donanım/motor seçeneği için bakmamı istersiniz?"

            joined = ", ".join(f"%{x}" for x in pcts)
            return (
                f"{model.title()} için listemizde birden fazla ÖTV yüzdesi görünüyor: {joined}. "
                "Hangi donanım seviyesi veya motor seçeneği için bakmamı istersiniz?"
            )
        # ✅ Ürün gamı sorusunu DB’den direkt cevapla (DB_ONLY short-circuit fix)
        if ("ürün gam" in q_norm) or ("urun gam" in q_norm) or ("model gam" in q_norm):
            items = self._product_range_from_sql()
            if items:
                # kısa, net liste
                models = [f"{x['model']}" + (f" ({x['segment']})" if x.get("segment") else "") for x in items]
                joined = ", ".join(models)

                return (
                    f"Škoda ürün gamında öne çıkan modeller: {joined}. "
                    "İstersen kullanım ihtiyacını (şehir içi/uzun yol/aile/elektrikli) söyle, sana uygun modeli birlikte seçelim."
                )
            return (
                "Škoda ürün gamı bilgisi için veritabanımda kayıt bulamadım. "
                "Hangi gövde tipini düşünüyorsun (SUV, hatchback, sedan, elektrikli)?"
            )

        # (mevcut akışın devamı)
        ctx = self._build_db_context(user_message, user_id=user_id, relax=False)

        # 1) İlk pas boşsa -> relax pas
        if not ctx:
            ctx = self._build_db_context(user_message, user_id=user_id, relax=True)

        # 2) Hâlâ boşsa: “yorumlayarak” yönlendiren güvenli mesaj
        if not ctx:
            return self._fallback_via_assistant(user_id, user_message, reason="DB context boş (SQL hit yok)")

            if model:
                return (
                    f"{model.title()} için bu soruya doğrudan karşılık gelen bir kayıt bulunamadı. "
                    "İsterseniz hangi donanım seviyesini (Premium/Prestige/Sportline gibi) kastettiğinizi yazın; "
                    "ona göre tekrar kontrol edebilirim."
                )
            return (
                "Bu soruya doğrudan karşılık gelen bir kayıt bulamadım. "
                "Hangi Skoda modelini ve (varsa) donanım seviyesini belirtir misiniz?"
            )


        sys = (
            "Sen Škoda Türkiye için dijital satış danışmanısın.\n"
            "KURAL: SADECE aşağıdaki DB bağlamına dayanarak cevap ver.\n"
            "- DB bağlamında yoksa: 'veritabanında karşılığı bulunamadı' de.\n"
            "- Bağlamda geçen model adları DIŞINDA model adı yazma.\n"
            "- Sayıları/birimleri AYNEN koru (asla değiştirme).\n"
            "Cevap: 2–4 cümle, sonunda 1 kısa soru.\n"
            "DB bağlamını ham şekilde kopyalama; yorumlayıp sonuç cümlesi üret."
        )

        usr = f"Kullanıcı sorusu: {user_message}\n\nDB bağlamı:\n{ctx}"

        try:
            resp = self.client.chat.completions.create(
                model=os.getenv("GEN_MODEL", "gpt-4o-mini"),
                messages=[{"role": "system", "content": sys},
                        {"role": "user", "content": usr}],
                temperature=0.4,
                max_tokens=220,
            )
            out = (resp.choices[0].message.content or "").strip()
            return out or "Bu konuda bilgi tabanımda kayıt yok."
        except Exception:
            # LLM hata verirse en azından “kayıt var ama üretemedim” demeyelim,
            # güvenli fallback:
            return "Bu konuda bilgi tabanımda kayıt var; şu an yanıt üretilemedi."

    def _kb_postfetch_row(self, table_name: str, row_key: str) -> dict | None:
        """
        KB hit'inden gelen (table_name, row_key) ile orijinal SQL satırını getirir.
        row_key = kaynak tablodaki id beklenir.
        """
        if not table_name or not row_key:
            return None
        conn = self._sql_conn()
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT * FROM [dbo].[{table_name}] WITH (NOLOCK) WHERE id = ?", (row_key,))
            row = cur.fetchone()
            if not row or not cur.description:
                return None
            cols = [c[0] for c in cur.description]
            return {cols[i]: row[i] for i in range(len(cols))}
        except Exception as e:
            self.logger.error(f"[KB-POSTFETCH] fail table={table_name} row_key={row_key}: {e}")
            return None
        finally:
            try: cur.close()
            except: pass
            try: conn.close()
            except: pass

    def _disambiguate_feature_via_gpt(self, user_text: str, candidates: list[str]) -> int | None:
        """
        Bir donanım sorusu için, olası 'Ozellik' satırları arasından
        en uygun olanı GPT'ye seçtirir.

        Dönüş: 0-based index (candidates içindeki sıra) veya None.
        """
        import os, json, re

        if not candidates:
            return None
        if len(candidates) == 1:
            return 0

        try:
            sys_msg = (
                "You work for Skoda Türkiye as a digital sales assistant. "
                "Your ONLY job in this task is: given a Turkish user question "
                "about a single equipment feature and a list of candidate "
                "equipment row titles from SQL (column 'Ozellik'), choose the ONE "
                "candidate that best describes the feature the user is asking about.\n\n"
                "Rules:\n"
                "- Focus on the *specific feature*, not generic words like 'koltuk', 'sistem', 'paket'.\n"
                "- For example, if the question is about 'ısıtmalı ön koltuk', prefer rows that "
                "contain 'ısıtmalı' or 'koltuk ısıtma' over rows that only say 'havalandırmalı ön koltuk'.\n"
                "- Do NOT invent new features, just choose from the given candidates.\n"
                "- Return ONLY the index (0-based) of the best candidate as a plain integer. "
                "No explanation, no extra text."
            )

            payload = {
                "question": user_text,
                "candidates": candidates,
            }

            resp = self.client.chat.completions.create(
                model=os.getenv("GEN_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user",   "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.0,
                max_tokens=4,
            )
            raw = (resp.choices[0].message.content or "").strip()
            # İçinden ilk sayı geçen şeyi yakala (sadece '1' yazmazsa bile)
            m = re.search(r"\d+", raw)
            if not m:
                return None
            idx = int(m.group(0))
            if 0 <= idx < len(candidates):
                return idx
            return None
        except Exception as e:
            if hasattr(self, "logger"):
                self.logger.error(f"[EQUIP-GPT-DISAMBIG] hata: {e}")
            return None

    def _expand_feature_keywords_via_openai(self, user_text: str, model_slug: str | None = None) -> list[str]:
        """
        Kullanıcının donanım sorusundan tek bir özellik çıkarıp
        bu özellik için Türkçe/İngilizce kısa arama ifadeleri (eş anlamlılar) üretir.

        Örnek:
           'kamiq de sunroof var mı' →
           ['sunroof', 'cam tavan', 'panoramik cam tavan']

        Yanıt: max ~6 adet, 1–3 kelimelik string listesi.
        """
        import os, json, re

        try:
            base_model = os.getenv("GEN_MODEL", "gpt-4o-mini")

            sys_msg = (
                "You are an assistant that works for a car dealer (Škoda Türkiye). "
                "Your ONLY job is: given a Turkish user question about a car equipment "
                "feature, extract that single feature and output 3–6 short search phrases "
                "for that feature in Turkish and English. "
                "Each phrase must be 1–3 words (no sentences). "
                "Include both the dictionary word (e.g. 'sunroof') and Turkish "
                "variants (e.g. 'cam tavan', 'panoramik cam tavan'). "
                "DO NOT mention trims, versions, prices, or models. "
                "Answer STRICTLY as a JSON list of strings, nothing else."
            )

            user_payload = {
                "question": user_text,
                "model": (model_slug or "").lower()
            }

            resp = self.client.chat.completions.create(
                model=base_model,
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                temperature=0.0,
                max_tokens=120,
            )
            raw = (resp.choices[0].message.content or "").strip()

            # Önce JSON dene
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    kws = [str(x).strip() for x in data if str(x).strip()]
                else:
                    kws = []
            except Exception:
                # JSON değilse virgül / satır bazlı parçala
                parts = re.split(r"[,\n;]+", raw)
                kws = [p.strip() for p in parts if p.strip()]

            # Çok uzunları ve cümleleri ele
            clean = []
            for k in kws:
                if len(k.split()) > 4:
                    continue
                clean.append(k)

            # Tekilleştir
            seen = set()
            out = []
            for k in clean:
                kl = k.lower()
                if kl not in seen:
                    seen.add(kl)
                    out.append(k)
            self.logger.info(f"[EQUIP-GPT] keywords for '{user_text}': {out}")
            return out
        except Exception as e:
            self.logger.error(f"[EQUIP-GPT] hata: {e}")
            return []

    def _build_equip_sem_index_for(self, model_code: str):
        """
        EquipmentList_KODA_<MODEL> tablosunu RAM'e alır ve
        her 'Ozellik' satırı için HF embedding üretir.
        Tek seferlik çalışır, sonuç self._equip_sem_index'e cache'lenir.
        """
        import contextlib

        key = (model_code or "").upper().strip()
        if not key:
            return

        # Zaten oluşturulmuşsa tekrar yapma
        if key in self._equip_sem_index:
            return

        # HF modeli yoksa bu feature devre dışı
        if _HF_SEM_MODEL is None:
            self._equip_sem_index[key] = None
            return

        tname = self._latest_equipment_table_for(model_code)
        if not tname:
            self.logger.info(f"[EQUIP-SEM] EquipmentList tablosu bulunamadı: model={key}")
            self._equip_sem_index[key] = None
            return

        conn = self._sql_conn()
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT TOP 0 * FROM [dbo].[{tname}] WITH (NOLOCK)")
            cols = [c[0] for c in cur.description] if cur.description else []
            if not cols:
                self._equip_sem_index[key] = None
                return

            # Özellik kolonu
            name_candidates = ["Equipment","Donanim","Donanım","Ozellik","Özellik",
                               "Name","Title","Attribute","Feature"]
            feat_col = next((c for c in name_candidates if c in cols), None)
            if not feat_col:
                feat_col = next(
                    (c for c in cols
                     if re.search(r"(equip|donan|özellik|ozellik|name|title|attr)", c, re.I)),
                    None
                )
            if not feat_col:
                self.logger.info(f"[EQUIP-SEM] Özellik kolonu bulunamadı: table={tname}")
                self._equip_sem_index[key] = None
                return

            # Trim kolonları (id / Model / Ozellik hariç her şey)
            trim_cols = [c for c in cols if c not in ("id", "ID", "Model", feat_col)]
            if not trim_cols:
                self._equip_sem_index[key] = None
                return

            cur.execute(f"SELECT * FROM [dbo].[{tname}] WITH (NOLOCK)")
            rows = cur.fetchall()
            if not rows:
                self._equip_sem_index[key] = None
                return

            items = []
            for r in rows:
                d = {cols[i]: r[i] for i in range(len(cols))}
                oz = (d.get(feat_col) or "").strip()
                if not oz:
                    continue

                vec = embed_semantic_local(oz)
                if vec is None:
                    continue

                items.append({
                    "ozellik": oz,
                    "vec": vec,
                    "row": d,
                })

            if not items:
                self._equip_sem_index[key] = None
                return

            self._equip_sem_index[key] = {
                "feat_col": feat_col,
                "trim_cols": trim_cols,
                "items": items,
            }
            self.logger.info(
                f"[EQUIP-SEM] Index hazır: model={key}, table={tname}, rows={len(items)}"
            )
        finally:
            with contextlib.suppress(Exception):
                cur.close()
            with contextlib.suppress(Exception):
                conn.close()

    def _semantic_feature_match_equipment(self, model: str, user_text: str, topn: int = 1) -> list[dict]:
        """
        HF sentence-transformer kullanarak:
        - Kullanıcı cümlesini vektöre çevirir
        - EquipmentList'teki tüm 'Ozellik' satırlarıyla cosine benzerliği hesaplar
        - En yakın topn satırı döndürür.

        Dönüş:
        [
            {
              "ozellik": ...,
              "row": {...},           # SQL satırı dict
              "score": float,
              "trim_cols": [ ... ]    # hangi kolonlar trim
            },
            ...
        ]
        """
        import numpy as np

        if not model or not user_text:
            return []

        # HF modeli yoksa bu yol kapalı
        if _HF_SEM_MODEL is None:
            return []

        key = (model or "").upper().strip()
        # Index yoksa oluştur
        self._build_equip_sem_index_for(key)
        sem_idx = self._equip_sem_index.get(key)
        if not sem_idx:
            return []

        items = sem_idx.get("items") or []
        trim_cols = sem_idx.get("trim_cols") or []

        q_vec = embed_semantic_local(user_text)
        if q_vec is None:
            return []

        hits = []
        for it in items:
            v = it["vec"]
            # embed_semantic_local normalize_embeddings=True ile çağrılıyor → dot = cosine
            sim = float(np.dot(q_vec, v))
            hits.append((sim, it))

        if not hits:
            return []

        hits.sort(key=lambda x: x[0], reverse=True)
        out = []
        for sim, it in hits[:max(1, topn)]:
            out.append({
                "ozellik": it["ozellik"],
                "row": it["row"],
                "score": sim,
                "trim_cols": trim_cols,
            })
        # Debug log
        best = out[0]
        self.logger.info(
            "[EQUIP-SEM] '%s' ~ '%s' sim=%.3f (model=%s)",
            user_text,
            best["ozellik"],
            best["score"],
            model
        )
        return out

    def _probe_equipment_presence(self, user_id: str, text: str) -> bool:
        """
        '... var mı?' cümlesi gerçekten donanım satırına karşılık geliyorsa
        keyword listesi yerine SQL tablosunu kullanarak donanım intent'i döndür.
        """
        if not text:
            return False

        t_norm = normalize_tr_text(text).lower()

        # 1) Var/yok/mevcut kalıbı yoksa → donanım var/yok sorusu değildir
        if not self.PRESENCE_RE.search(t_norm):
            return False

        # 2) Fiyat niyeti ise hiç bulaşma (PriceList'e gidecek)
        if self._is_price_intent(text):
            return False

        # 3) Teknik/metrik kelimeler geçiyorsa (tork, 0-100, menzil...) → teknik blok baksın
        if any(k in t_norm for k in self.TEKNIK_KW):
            return False

        # 4) Hangi model için? (mesaj + state + asistan bağlamı)
        model = self._current_model(user_id, text)
        if not model:
            return False

        # 5) Bu modelin IMPORTED_* / EquipmentList_* tablolarında
        #    bu soruya yakın bir donanım satırı var mı?
        try:
            # Daha güçlü olan: lemma + HF-SEM kullanan RAM cache fonksiyonun
            rows = self._query_all_features_from_imported(model, text, topn=1)
            if rows:
                # Buraya geldiysek zaten _query_all_features_from_imported
                # skor ve overlap filtrelerini geçti demektir
                return True

            # Yedek: isim olarak geçiyor mu?
            if self._feature_exists_tr_en(model, text):
                return True

        except Exception as e:
            self.logger.error(f"[EQUIP-PROBE] hata: {e}")

        return False


    def _detect_same_model_trim_compare(self, text: str) -> tuple[str | None, list[str]]:
        """
        Örn:
        'Karoq prestige ve Sportline donanım farkları nelerdir'
        --> ('karoq', ['prestige', 'sportline'])
        """
        if not text:
            return None, []

        # Karşılaştırma kelimeleri için normalize et
        t_norm = normalize_tr_text(text).lower()

        # 1) Aynı model mi?
        models = list(self._extract_models(text))
        if len(models) != 1:
            return None, []

        model = models[0]

        # 2) Karşılaştırma niyeti var mı?
        compare_words = [
            "fark", "farkı", "farkları", "farklar",
            "karşılaştır", "karşılaştırma", "kıyas", "kıyasla", "vs", "vs."
        ]
        if not any(w in t_norm for w in compare_words):
            return None, []

        # 3) TRIM’LERİ HAM METİNDEN ARA (normalize_tr_text kullanma!)
        text_lower = text.lower()
        trims = list(extract_trims(text_lower))
        if len(trims) < 2:
            return None, []

        # 4) Modelin geçerli trim listesine göre filtrele
        valid_trims = self.MODEL_VALID_TRIMS.get(model, []) or []
        if valid_trims:
            ordered = [tr for tr in trims if tr in valid_trims]
            if len(ordered) >= 2:
                return model, ordered

        return model, trims

    def _detect_multi_model_trim_compare(self, text: str) -> dict[str, list[str]]:
        """
        Örnekler:
          'Fabia Premium ve Scala Premium donanım farkları'
          → {'fabia': ['premium'], 'scala': ['premium']}

          'Fabia Premium, Kamiq Monte Carlo ve Scala Premium karşılaştır'
          → {'fabia': ['premium'], 'kamiq': ['monte carlo'], 'scala': ['premium']}

        En az 2 FARKLI model ve her model için en az 1 trim varsa
        {model_slug: [trim1, trim2, ...]} döndürür; aksi halde {}.
        """
        if not text:
            return {}

        # Normalize sadece niyet kontrolü için
        t_norm = normalize_tr_text(text).lower()

        # Karşılaştırma niyeti yoksa uğraşma
        compare_words = [
            "fark", "farkı", "farkları", "farklar",
            "karşılaştır", "karşılaştırma", "kıyas", "kıyasla", "vs", "vs."
        ]
        if not any(w in t_norm for w in compare_words):
            return {}

        # 🔴 ÖNEMLİ: Model–segment çiftlerini HAM METİNDEN al
        pairs = extract_model_trim_pairs(text)
        if len(pairs) < 2:
            return {}

        by_model: dict[str, list[str]] = {}

        for m, seg in pairs:
            m = (m or "").lower().strip()
            seg = (seg or "").lower().strip()
            if not m or not seg:
                continue

            # Bu model için geçerli trim listesi
            valid_trims = self.MODEL_VALID_TRIMS.get(m, []) or []
            if not valid_trims:
                continue

            # Segment içinden trim’i çek: "premium farkları nedir" → ["premium"]
            seg_trims = list(extract_trims(seg))
            if not seg_trims:
                continue

            # Sadece bu model için geçerli olanları bırak
            seg_trims = [t for t in seg_trims if t in valid_trims]
            if not seg_trims:
                continue

            # Şimdilik model başına ilk trim yeterli: "premium"
            tr = seg_trims[0]

            by_model.setdefault(m, [])
            if tr not in by_model[m]:
                by_model[m].append(tr)

        # En az iki farklı model olmalı
        if len(by_model) < 2:
            return {}

        return by_model


    def _is_equipment_presence_question(self, text: str) -> bool:
        """
        'karoq da ... var mı' gibi, fiyat veya teknik metrik içermeyen
        tüm 'var mı / yok mu' sorularını donanım var/yok sorusu say.
        """
        if not text:
            return False

        t = normalize_tr_text(text).lower()

        # 1) Fiyat sorusuysa donanım sayma
        if self._is_price_intent(text):
            return False

        # 2) 'var mı / yok mu / mevcut mu / bulunuyor mu / geliyor mu' kalıbı olmalı
        presence_kw = [
            "var mi", "var mı", "varmi",
            "yok mu", "yokmu",
            "mevcut mu", "mevcutmu",
            "bulunuyor mu", "bulunuyor mu",
            "oluyor mu", "geliyor mu",
        ]
        if not any(kw in t for kw in presence_kw):
            return False

        # 3) Teknik/metrik kelimeler geçiyorsa (tork, 0-100, menzil vb.) donanım sayma
        teknik_kw = [
            "tork", "güç", "guc", "beygir", "hp", "ps", "kw",
            "0-100", "0 – 100", "0 100", "ivme", "hızlanma",
            "maksimum hız", "maks hiz", "menzil", "range",
            "tüketim", "tuketim", "l/100", "lt/100",
            "co2", "emisyon", "bagaj", "hacim", "dm3",
        ]
        if any(k in t for k in teknik_kw):
            return False

        # 🔹 Artık ekstra kelime listesi yok:
        # Bu noktaya geldiysek, bu soruyu donanım var/yok sorusu kabul et.
        return True


    def _vector_tables_config(self):
        """
        Fiziksel vektör tablolarının isimlerini döndürür.
        USE_MSSQL_NATIVE_VECTOR=1 ise ...Native_*,
        aksi halde normal VARBINARY tabloları kullanılır.
        """
        if getattr(self, "USE_MSSQL_NATIVE_VECTOR", False):
            return {
                "EQUIP": "KbVectorsNative_Equip",
                "PRICE": "KbVectorsNative_Price",
                "SPEC":  "KbVectorsNative_Spec",
                "OTHER": "KbVectorsNative_Other",
            }
        else:
            return {
                "EQUIP": "KbVectors_Equip",
                "PRICE": "KbVectors_Price",
                "SPEC":  "KbVectors_Spec",
                "OTHER": "KbVectors_Other",
            }

    def _current_model(self, user_id: str, text: str | None = None) -> str | None:
        st = self.user_states.setdefault(user_id, {})

        # ✅ SIRALI yakala
        models_in_msg = []
        try:
            models_in_msg = self._extract_models_all(text or "") or []
        except Exception:
            # fallback: eski set (sırasız)
            models_in_msg = list(self._extract_models(text or "")) if hasattr(self, "_extract_models") else []

        models_in_msg = [m.strip().lower() for m in models_in_msg if m]
        # uniq + order
        uniq = []
        for m in models_in_msg:
            if m not in uniq:
                uniq.append(m)
        models_in_msg = uniq

        # ✅ Mesajda 2+ model varsa: compare bağlamını güncelle ama tek modele DÜŞÜRME
        if len(models_in_msg) >= 2:
            st["cmp_models"] = models_in_msg[:2]
            st["last_models"] = set(models_in_msg[:2])

            # active_model istersen ilk model olsun ama from_user=False (cmp'yi bozmasın)
            st["active_model"] = models_in_msg[0]
            return models_in_msg[0]

        # ✅ Mesajda tek model varsa: normal
        if len(models_in_msg) == 1:
            m = models_in_msg[0]
            self._set_active_model(user_id, m, from_user=True)
            return m

        # ✅ Mesajda model yoksa: aktif/last_user/cmp tekli
        active = (st.get("active_model") or "").strip().lower() or None
        if active:
            return active

        last_user = (st.get("last_user_model") or "").strip().lower() or None
        if last_user:
            return last_user

        cm = st.get("cmp_models") or []
        cm = [str(x).strip().lower() for x in cm if str(x).strip()]
        cm = list(dict.fromkeys(cm))
        if len(cm) == 1:
            return cm[0]

        last_models = st.get("last_models", set())
        if isinstance(last_models, (set, list, tuple)) and len(last_models) == 1:
            return list(last_models)[0].lower()

        asst_id = st.get("assistant_id")
        if asst_id:
            mapped = (self.ASSISTANT_NAME_MAP.get(asst_id, "") or "").lower()
            if mapped:
                return mapped

        return None



    def _apply_model_memory(self, user_id: str, user_message: str) -> tuple[str, set, str]:
        state = self.user_states.setdefault(user_id, {})

        corrected = self._correct_all_typos(user_message or "")
        lower = corrected.lower().strip()

        # 1) Bu mesajda açık/gevşek model var mı?
        models_now = []
        try:
            models_now = self._extract_models_all(corrected) or []
        except Exception:
            models_now = []

        # ✅ Kullanıcı bu mesajda model söylediyse: normal davran
        if models_now:
            m = models_now[0]
            self._set_active_model(user_id, m, from_user=True)
            return corrected, set(models_now), lower

        # ✅ YENİ: compare bağlamı varsa (2 model) -> tek model enjekte ETME
        cm = state.get("cmp_models") or []
        cm = [str(x).strip().lower() for x in cm if str(x).strip()]
        cm = list(dict.fromkeys(cm))
        if len(cm) >= 2:
            # mesajı bozma; _resolve_slots zaten state_cmp ile iki modeli döndürecek
            return corrected, set(), lower

        # 2) (eski) tek model hafızası
        last_user_model = self._get_last_user_model(user_id)
        active = self._get_active_model(user_id)
        use_model = last_user_model or active

        if use_model and (not is_non_sentence_short_reply(corrected)):
            injected = f"{use_model} {corrected}".strip()
            return injected, {use_model}, injected.lower().strip()

        return corrected, set(), lower




    def _get_model_general_info(self, text: str) -> str | None:
        """
        Kullanıcı sadece modele dair genel bilgi istiyorsa
        (ör. 'kamiq', 'kamiq ile ilgili bilgi verebilir misin')
        ilgili sabit tanıtım metnini döndürür.
        """
        if not text:
            return None

        t_norm = normalize_tr_text(text).lower()

        # En az bir Skoda modeli geçmeli
        models = list(self._extract_models(text))
        if not models:
            return None

        model = models[0]  # ilk görünen modeli al

        # Eğer fiyat / teknik / donanım / görsel niyeti varsa GENEL BİLGİ sayma
        if self._is_price_intent(text):
            return None

        if self.utils.is_image_request(text) or self._is_image_intent_local(text):
            return None

        # Teknik metrik veya donanım kelimeleri varsa da genel tanıtım değildir
        teknik_kw = [
            "tork", "güç", "guc", "beygir", "hp", "ps", "kw",
            "0-100", "ivme", "hızlanma", "menzil", "tüketim", "tuketim",
            "co2", "emisyon", "bagaj", "yakıt", "yakit", "şarj", "sarj"
        ]
        equip_kw = ["donanım", "donanim", "opsiyon", "opsiyonel", "paket", "renk", "görsel", "resim"]
        if any(k in t_norm for k in teknik_kw + equip_kw):
            return None

        # Pozitif tetikleyiciler: 'hakkında / ilgili / bilgi ver / genel bilgi / tanıt'
        positive_triggers_raw = [
            "hakkinda bilgi", "hakkında bilgi",
            "ile ilgili bilgi", "ile ilgili genel bilgi",
            "genel bilgi", "bilgi ver", "bilgi verebilir misin",
            "bilgi almak", "tanit", "tanıt", "tanitim", "tanıtım",
            "nasildir", "nasıldır", "nasıl bir araç", "hangi segmente ait"
        ]
        # 🔧 normalize_tr_text kullanan sürüm (ek-kırpma ile uyumlu)
        positive_triggers = [normalize_tr_text(kw).lower()
                             for kw in positive_triggers_raw]

        if any(kw in t_norm for kw in positive_triggers):
            return MODEL_GENERAL_INFO.get(model)

        # Ek zekâ: mesaj neredeyse sadece model + filler kelimelerden oluşuyorsa da genel bilgi say
        import re
        # model adını at
        t_no_model = re.sub(rf"\b{model}\b", "", t_norm)
        tokens = [w for w in t_no_model.split() if w]

        stop = {
            "ile", "ilgili", "bilgi", "ver", "vere", "verir", "misin",
            "mısın", "hakkında", "hakkinda", "biraz", "bana", "kısaca",
            "kisaca", "lütfen", "lutfen"
        }
        content_tokens = [w for w in tokens if w not in stop]

        # Örn: "kamiq", "kamiq ile ilgili bilgi", "kamiq hakkında biraz bilgi" gibi
        if not content_tokens:
            return MODEL_GENERAL_INFO.get(model)

        return None


    def _is_kb_rag_description_intent(self, text: str) -> bool:
        """
        'octavia elite ve premium arasındaki fark',
        'superb premium donanım listesi',
        'kamiq elite donanım öne çıkanlar' gibi
        model + trim odaklı, özet/donanım/fark sorularını yakalar.

        Amaçı: Bu tip soruları doğrudan Hybrid RAG (KbVectors + gpt-4o-mini)
        pipeline'ına göndermek.
        """
        if not text:
            return False

        # Türkçe normalize edilmiş hâl
        t = normalize_tr_text(text).lower()

        # En az bir Skoda model adı geçmeli
        if not self._extract_models(text):
            return False

        # 1) Donanım listesi / öne çıkanlar
        desc_phrases = [
            "donanim listesi",
            "donanim liste",
            "donanim one cikan",
            "donanim one cikanlar",
            "one cikan donanimlar",
            "one cikanlar",
            "donanimlar neler",
            "donanim olarak neler",
            "ozellikleri neler",
            "ozellikleri nelerdir",
        ]
        if any(kw in t for kw in desc_phrases):
            return True

        # 2) Trim(ler) arası fark soruları
        if "fark" in t and ("arasinda" in t or "arasi" in t):
            trims = extract_trims(t)
            if trims:   # en az bir trim varsa
                return True

        # 3) '… ile ilgili bilgi ver / özetler misin' tarzı cümleler
        info_phrases = [
            "ile ilgili bilgi ver",
            "hakkinda bilgi ver",
            "kisaca anlat",
            "ozetler misin",
            "ozet bilgi",
            "ozet gec",
        ]
        if any(kw in t for kw in info_phrases):
            return True

        return False



    def _is_skoda_smalltalk_context(self, msg: str) -> bool:
        """
        Small talk mesajı Skoda / Yüce Auto bağlamında mı?
        Değilse ekonomi, siyaset, genel dünya gündemi vb. için
        small talk cevabı ÜRETME, sabit red cevabına düşeceğiz.
        """
        if not msg:
            return False

        t = normalize_tr_text(msg).lower()
        if is_non_sentence_short_reply(msg):
            return True
        # 1) Basit selam / hal-hatır soruları serbest
        if self._is_smalltalk_message(msg):
            return True

        # 2) Skoda / Yüce Auto / modeller geçiyorsa serbest
        if "skoda" in t or "yüce auto" in t or "yuce auto" in t or "yugii" in t:
            return True
        if self._extract_models(msg):
            return True

        # 3) Ekonomi / siyaset / genel gündem + marka dışı konular ise BLOKLA
        off_topic_keywords = [
            "ekonomi", "enflasyon", "faiz", "döviz", "dolar", "euro",
            "tl ne olur", "borsa", "seçim", "secim", "siyaset", "hükümet",
            "hukumet", "politik", "politika", "savaş", "savash", "rusya",
            "abd", "amerika", "avrupa birliği",
        ]
        if any(k in t for k in off_topic_keywords):
            return False

        # 4) Diğer otomobil markaları da small talk'ta yasak
        if self._mentions_non_skoda(msg):
            return False
        
        # Varsayılan: güvenli tarafta kabul et
        return False

    def _is_hard_car_intent(self, msg: str) -> bool:
        """
        Kullanıcı artık gerçekten somut araç bilgisi istiyor mu?
        (model adı, fiyat, teknik veri, donanım, renk, görsel, test sürüşü vb.)
        Böyle bir durumda smalltalk modundan çıkarız.
        """
        if not msg:
            return False

        t = normalize_tr_text(msg).lower()
         # 🔹 0.a) Genel araç / SUV arayışı, model yazmasa bile
        shopping_keywords = [
            "suv", "c suv", "b suv", "d suv",
            "c-suv", "b-suv", "d-suv",
            "araç bakıyorum", "arac bakiyorum",
            "araba bakıyorum", "araba bakiyorum",
            "yeni araç", "yeni arac", "yeni araba",
            "araç tavsiye", "arac tavsiye", "araba tavsiye",
            "hangi model", "hangi suv", "hangi skoda",
            "b segment", "c segment", "d segment",
        ]
        if any(k in t for k in shopping_keywords):
            return True

        # 🔹 0) Saf donanım / özellik kelimeleri (model yazmasa bile)
        feature_keywords = [
            "cam tavan", "panoramik cam tavan", "sunroof",
            "head up display", "head-up display", "hud",
            "matrix led", "matrix far", "dcc", "dcc pro",
            "dijital gösterge", "dijital gösterge paneli",
            "direksiyon simidi", "direksiyon",
            "jant", "jantlar",
            "döşeme", "doseme", "koltuk",
            "karartılmış arka cam", "karartilmis arka cam", "arka cam karartma",
            "kör nokta", "blind spot",
            "geri görüş kamera", "geri gorus kamera",
            "park asistanı", "park assist",
        ]
        if any(k in t for k in feature_keywords):
            return True

        # 1) Skoda model adı geçtiyse net niyet
        if self._extract_models(msg):
            return True

        # 2) Sert niyet anahtar kelimeleri
        hard_keywords = [
            # fiyat / satın alma
            "fiyat", "anahtar teslim", "kampanya", "taksit", "kredi", "finansman", "tl", "₺",
            # teknik / performans
            "teknik", "motor", "tork", "beygir", "ps", "hp", "kw",
            "0-100", "0 – 100", "0 100", "ivme", "hızlanma", "maksimum hız", "menzil",
            "yakıt", "yakit", "tüketim", "tuketim",
            "co2", "emisyon", "bagaj", "yakıyor", "elektrik", "batarya", "kapasite",
            # donanım / paket
            "donanım", "donanim", "opsiyon", "opsiyonel", "paket",
            # renk / görsel
            "renk", "görsel", "gorsel", "resim", "foto", "fotograf", "fotoğraf",
            # test sürüşü
            "test sürüş", "testsürüş", "deneme sürüş"
        ]
        if any(k in t for k in hard_keywords):
            return True

        # 3) Soru cümlesi ve tipik bilgi kalıpları
        if "?" in msg and any(kw in t for kw in ["ne kadar", "kaç ", "kac ", "nedir"]):
            return True

        return False


    def _is_smalltalk_message(self, msg: str) -> bool:
        """
        Sadece selamlaşma / küçük sohbet içeren basit mesaj mı?
        Örn: 'merhaba', 'selam', 'nasılsın', 'iyi akşamlar', 'günaydın' vb.
        """
        if not msg:
            return False

        import re
        # ❗ Küçük sohbet için normalize_tr_text KULLANMA,
        # ekleri kesmediğimiz ham metni kullan.
        m = re.sub(r"\s+", " ", msg.strip().lower())

        # Çok uzun cümleleri smalltalk saymayalım
        if len(m) > 40:
            return False

        # Selam / hal hatır kalıpları
        if re.search(r"\b(merhaba|selam|slm|s\.a|sa|hi|hello|selamlar)\b", m):
            return True
        if re.search(r"(naber|nbr|nasılsın|nasilsin|iyidir|iyiyim|ne var ne yok)", m):
            return True
        if re.search(r"(günaydın|gunaydin|iyi akşamlar|iyi aksamlar|iyi geceler)", m):
            return True

        return False


    def _answer_smalltalk_via_openai(self, user_message: str, user_id: str) -> bytes:
        import os

        st = self.user_states.setdefault(user_id, {})

        # Her zaman EN SON soru–cevap üzerinden bağlam kur
        prev_q = st.get("last_user_message") or st.get("prev_user_message") or ""
        prev_ans = st.get("last_assistant_answer") or st.get("prev_assistant_answer") or ""

        # İstersen bunları da güncelle ki log’da takip kolay olsun
        st["prev_user_message"] = prev_q
        st["prev_assistant_answer"] = prev_ans
        # Eğer daha önce herhangi bir cevap verdiysek, kullanıcı bizi zaten tanıyor say
        intro_done = st.get("smalltalk_intro_done", False)
        if prev_ans:
            intro_done = True

        if intro_done:
            intro_instruction = (
                "Kullanıcı seni zaten tanıyor. Kesinlikle tekrar 'Merhaba, ben DSD…' "
                "gibi bir giriş yapma, asla kendini tanıtma. "
                "Sanki biraz önce verdiğin cevaptan sohbet etmeye devam ediyormuşsun gibi davran."
            )
        else:
            # Bu sadece gerçekten konuşma full small talk ile başladıysa devreye girer
            intro_instruction = (
                "Eğer bu konuşma tamamen selamlaşma ile başladıysa (örneğin kullanıcı sadece "
                "'merhaba', 'nasılsın' gibi şeyler yazdıysa) en fazla 1 cümleyle çok kısa bir "
                "tanıtım yapabilirsin. Araçla ilgili sorulardan SONRA gelen kısa cevaplarda "
                "KESİNLİKLE kendini tanıtma."
            )

        # Bağlam bloğu: önceki cevap + önceki soru
        context_block = ""
        if prev_ans or prev_q:
            context_block = (
                "Önceki konuşma bağlamı:\n"
                f"- Senin bir önceki cevabın: {prev_ans}\n"
                f"- Kullanıcının o cevaptan önceki sorusu: {prev_q}\n"
                "Şu anki kullanıcı mesajı bu cevaba kısa bir tepki / yorum / devam niteliğindedir "
                "(örneğin 'oldukça önemli', 'bence güzel', 'evet isterim' gibi). "
                "Lütfen bu bağlamda aynı konu üzerinden sohbeti SÜRDÜR; yeni konu açma, "
                "genel karşılama cümleleri ('Merhaba, ben DSD, nasıl yardımcı olabilirim?') kullanma.\n"
            )

        system_msg = (
            "Sen Yüce Auto için geliştirilmiş kurumsal dijital satış danışmanı 'DSD'sin. "
            "Kullanıcı şu anda ağır teknik veri veya net fiyat istemiyor, daha çok sohbet "
            "ederek fikir almak istiyor. "
            "Küçük sohbet yapabilirsin AMA yalnızca Skoda, otomobil kullanımı, araç seçimi "
            "ve Yüce Auto ile ilgili konularda konuşursun. "

            "Kullanıcı Yüce Auto hakkında bir şey sorarsa mutlaka şunu özellikle belirt: "
            "'Yüce Auto, Škoda’nın Türkiye'deki tek yetkili distribütörüdür.' "

            "Türkiye'nin veya dünyanın ekonomik durumu, siyaset, döviz, yatırım, başka otomobil "
            "markaları gibi konulara ek olarak araçların üretim yerleri hakkında da "
            "KESİNLİKLE bilgi veya yorum VERME. "
            "Böyle bir soru gelirse kısa bir şekilde şunu söyle: "
            "'Bu konuda yorum yapamıyorum, ben sadece Skoda ve Yüce Auto ile ilgili yardımcı olabilirim.' "

            "Her zaman Türkçe, samimi ve profesyonel bir dille cevap ver. "
            "Cevapların genelde tek cümle olsun; maksimum 2 cümleyi geçme. "
            "Veritabanı, SQL, tablo, kaynak gibi teknik şeylerden bahsetme. "

            "Sadece şu modeller üzerinden konuş: Fabia, Scala, Kamiq, Karoq, Kodiaq, Octavia, Superb, Elroq, Enyaq. "

            f"{context_block}"
            f"{intro_instruction}"
        )

        try:
            resp = self.client.chat.completions.create(
                model=os.getenv("GEN_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.7,
                max_tokens=220,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                text = "Skoda modelleri hakkında konuşabiliriz, kullanım tarzını biraz anlatır mısın? 😊"
        except Exception as e:
            self.logger.error(f"[SMALLTALK] hata: {e}")
            text = "Skoda modelleri hakkında konuşabiliriz, kullanım tarzını biraz anlatır mısın? 😊"

        # Artık bu konuşmada smalltalk tanıtımı yapılmış say
        st["smalltalk_intro_done"] = True

        return text.encode("utf-8")


    def _safe_kb_hit(self, query: str, text: str) -> bool:
        import re
        q_norm = normalize_tr_text(query).lower()
        t_norm = normalize_tr_text(text).lower()

        q_tokens = set(re.findall(r"[0-9a-zçğıöşü]+", q_norm))
        t_tokens = set(re.findall(r"[0-9a-zçğıöşü]+", t_norm))

        STOP = {
            "var","yok","mi","mı","mu","mü",
            "ne","nedir","ile","ve","veya","ya","yada",
            "icin","için","olan","hakkinda","hakkında","ilgili",
            "donanim","donanım","özellik","ozellik","paket",
            "skoda","model","tablo"
        }
        MODEL_TOKENS = {"fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"}
        GENERIC = {"elektrikli","otomatik","sistem","sistemi","güvenlik","guvenlik","konfor"}

        q_content = {w for w in q_tokens if w not in STOP and w not in MODEL_TOKENS}
        t_content = {w for w in t_tokens if w not in STOP}

        strong_overlap = (q_content & t_content) - GENERIC
        # 🔹 Karşılaştırma ise, overlap tamamen boşsa bile en azından
        # sayısal / teknik kayıtları kaçırmamak için biraz esnek ol
        if not strong_overlap:
            q_low = normalize_tr_text(query).lower()
            if any(w in q_low for w in ["karşılaştır","kıyas","vs","vs."]):
                # sadece tamamen alakasız satırları ele
                return bool(q_content)  # içerik varsa bırak
            return False

        return True
        return bool(strong_overlap)

    def _is_safe_equipment_match(self, user_text: str, feature_title: str) -> bool:
        """
        EquipmentList'ten gelen feature_title gerçekten user_text'teki donanımı
        temsil ediyor mu? Tereddüt varsa False dön.
        Genel yaklaşım:
        1) Hem soru hem satır için canonical feature key üret.
        2) Key'ler eşitse → direkt kabul.
        3) Eşit değilse → genel overlap ve birkaç çok genel güvenlik kuralı ile karar ver.
        """
        import re as _re

        t = normalize_tr_text(user_text or "").lower()
        f = normalize_tr_text(feature_title or "").lower()

        # 0) Canonical eşleştirme: en güçlü sinyal
        q_key, _ = canonicalize_feature(user_text)
        f_key, _ = canonicalize_feature(feature_title)

        if q_key and f_key and q_key == f_key:
            if hasattr(self, "logger"):
                self.logger.info(
                    "[EQUIP-SAFE] ACCEPT (canonical match) %r -> %r for %r",
                    feature_title, f_key, user_text
                )
            return True

        # 1) Çok genel ama kritik negatif kurallar
        q_tokens = set(_re.findall(r"[0-9a-zçğıöşü]+", t))
        f_tokens = set(_re.findall(r"[0-9a-zçğıöşü]+", f))

        # 1.a) 'koltuk' soruyorsa, satırda mutlaka 'koltuk' geçmeli
        if "koltuk" in q_tokens and "koltuk" not in f_tokens:
            if hasattr(self, "logger"):
                self.logger.info(
                    "[EQUIP-SAFE] REJECT (seat missing) %r for %r",
                    feature_title, user_text
                )
            return False

        # 1.b) 'koltuk' sorup 'bagaj' geçen satırı ekstra blokla
        if "koltuk" in q_tokens and "bagaj" in f_tokens:
            return False

        # 2) Genel overlap kuralı – en az bir anlamlı ortak kelime şartı
        STOP = {
            "var","yok","mi","mı","mu","mü",
            "ne","nedir","ile","ve","veya","ya","yada",
            "icin","için","olan","hakkinda","hakkında","ilgili",
            "donanim","donanım","özellik","ozellik","paket"
        }
        MODEL_TOKENS = {"fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"}
        GENERIC = {"elektrikli","otomatik","sistem","sistemi","güvenlik","guvenlik","konfor"}

        q_content = {w for w in q_tokens if w not in STOP and w not in MODEL_TOKENS}
        f_content = {w for w in f_tokens if w not in STOP}

        strong_overlap = (q_content & f_content) - GENERIC

        if q_content and not strong_overlap:
            if hasattr(self, "logger"):
                self.logger.info(
                    "[EQUIP-SAFE] REJECT (no strong overlap) %r for %r (q=%s, f=%s)",
                    feature_title, user_text, q_content, f_content
                )
            return False

        # 3) Multi-word sorularda biraz daha sıkı davran
        CONTENT_STOP = {
            "var", "yok", "mi","mı","mu","mü",
            "ne","kadar","nedir","olan","ile","ve",
            "opsiyonel","standart","donanım","donanim","özellik","ozellik"
        }
        content_tokens = {
            w for w in q_tokens
            if w not in CONTENT_STOP and w not in MODEL_TOKENS
        }
        if len(content_tokens) >= 2 and len(strong_overlap) < 2:
            if hasattr(self, "logger"):
                self.logger.info(
                    "[EQUIP-SAFE] REJECT (weak overlap for multi-word query) %r for %r",
                    feature_title, user_text
                )
            return False

        # Buraya geldiysek eşleşmeye izin ver
        return True





    def _opt_jant_table_from_sql(self, model: str) -> str | None:
        """
        Jant opsiyonlarını
        Opt_Jant_KODA_<MODEL>_MY_% tablosundan çeker ve Markdown tablo olarak döndürür.
        """
        import contextlib

        m = (model or "").strip().lower()
        if not m:
            return None

        tname = self._latest_opt_jant_table_for(m)
        if not tname:
            self.logger.info(f"[OPT-JANT] tablo bulunamadı: model={m}")
            return None

        conn = self._sql_conn()
        cur  = conn.cursor()
        try:
            cur.execute(f"SELECT * FROM [dbo].[{tname}] WITH (NOLOCK)")
            rows = cur.fetchall()
            if not rows or not cur.description:
                return None

            cols = [c[0] for c in cur.description]
            data = [{cols[i]: r[i] for i in range(len(cols))} for r in rows]

            # Model / Özellik / id kolonlarını öne al
            prefer = [c for c in ["Model", "Ozellik", "Özellik", "id"] if c in cols]
            md = self._rows_to_markdown_table(data, prefer_cols=prefer, chunk=1000)
            try:
                md = fix_markdown_table(md)
            except Exception:
                pass
            return md.strip()
        finally:
            with contextlib.suppress(Exception):
                cur.close()
            with contextlib.suppress(Exception):
                conn.close()

    def _latest_opt_jant_table_for(self, model: str) -> str | None:
        """
        Örn. 'enyaq' ->
          - Opt_Jant_KODA_ENYAQ__MY_20251
          - Opt_Jant_ENYAQ__MY_20251 (eski isim)
        içinden, ada göre en yeni olanı döndürür.
        """
        import contextlib

        m = (model or "").strip().upper()
        if not m:
            return None

        conn = self._sql_conn()
        cur  = conn.cursor()
        try:
            patterns = [
                f"Opt\\_Jant\\_KODA\\_{m}%",  # yeni isimlendirme
                f"Opt\\_Jant\\_{m}%",        # olası eski isim
            ]

            for pat in patterns:
                cur.execute(
                    """
                    SELECT TOP 1 name
                    FROM sys.tables WITH (NOLOCK)
                    WHERE name LIKE ? ESCAPE '\\'
                    ORDER BY name DESC
                    """,
                    (pat,),
                )
                row = cur.fetchone()
                if row:
                    self.logger.info(f"[OPT-JANT] tablo bulundu: {row[0]} (pattern={pat})")
                    return row[0]

            self.logger.info(f"[OPT-JANT] hiçbir tablo bulunamadı (model={m})")
            return None

        finally:
            with contextlib.suppress(Exception):
                cur.close()
            with contextlib.suppress(Exception):
                conn.close()

    def _opt_dgm_table_from_sql(self, model: str, user_text: str | None = None) -> str | None:
        """
        Direksiyon / Gösterge Paneli / Multimedya opsiyonlarını
        Opt_Direksiyon_Gosterge_Multimedya_KODA_<MODEL>_MY_% tablosundan çeker
        ve Markdown tablo döndürür.

        user_text verilirse:
        - 'direksiyon'  → sadece direksiyon satırları
        - 'gösterge'    → sadece gösterge paneli satırları
        - 'multimedya'  → sadece multimedya satırları
        aksi halde tüm tablo döner.
        """
        import contextlib

        m = (model or "").strip().lower()
        if not m:
            return None

        tname = self._latest_opt_dgm_table_for(m)
        if not tname:
            self.logger.info(f"[OPT-DGM] tablo bulunamadı: model={m}")
            return None

        conn = self._sql_conn()
        cur  = conn.cursor()
        try:
            cur.execute(f"SELECT * FROM [dbo].[{tname}] WITH (NOLOCK)")
            rows = cur.fetchall()
            if not rows or not cur.description:
                return None

            cols = [c[0] for c in cur.description]
            data = [{cols[i]: r[i] for i in range(len(cols))} for r in rows]

            # ---- İsteğe göre satır filtrele ----
            if user_text:
                # ⬇️ normalize_tr_text yerine direkt lower kullan
                q = (user_text or "").lower()

                # Açıklama kolonu (Aciklama / Açıklama / Description...)
                acik_col = None
                for cand in ("Aciklama", "Açıklama", "ACIKLAMA", "Description", "DESC"):
                    if cand in cols:
                        acik_col = cand
                        break

                if acik_col:
                    def _contains(row, word_tr: str):
                        txt = str(row.get(acik_col) or "").lower()
                        return word_tr in txt

                    filtered = []
                    if "direksiyon" in q:
                        filtered = [r for r in data if _contains(r, "direksiyon")]
                    elif "gösterge" in q or "gosterge" in q:
                        filtered = [
                            r for r in data
                            if _contains(r, "gösterge") or _contains(r, "gosterge")
                        ]
                    elif "multimedya" in q:
                        filtered = [r for r in data if _contains(r, "multimedya")]

                    if filtered:
                        data = filtered

            # Model + Açıklama kolonlarını öne al
            prefer = [c for c in ["Model", "Aciklama", "Açıklama"] if c in cols]
            md = self._rows_to_markdown_table(data, prefer_cols=prefer, chunk=1000)
            try:
                md = fix_markdown_table(md)
            except Exception:
                pass
            return md.strip()
        finally:
            with contextlib.suppress(Exception):
                cur.close()
            with contextlib.suppress(Exception):
                conn.close()


    def _latest_opt_dgm_table_for(self, model: str) -> str | None:
        """
        Örn. 'enyaq' -> 
          - Opt_Direksiyon_Gosterge_Multimedya_KODA_ENYAQ__MY_20251   (yeni isim)
          - Opt_GostergePaneli_KODA_ENYAQ__MY_20251                    (eski isim)
          - Opt_GostergePaneli_ENYAQ__MY_20251                         (daha eski)
        """
        import contextlib

        m = (model or "").strip().upper()
        if not m:
            return None

        conn = self._sql_conn()
        cur  = conn.cursor()
        try:
            patterns = [
                # Yeni isimlendirme
                f"Opt\\_Direksiyon\\_Gosterge\\_Multimedya\\_KODA\\_{m}%",
                # Eski isimlendirmeler
                f"Opt\\_GostergePaneli\\_KODA\\_{m}%",
                f"Opt\\_GostergePaneli\\_{m}%",
            ]

            for pat in patterns:
                cur.execute(
                    """
                    SELECT TOP 1 name
                    FROM sys.tables WITH (NOLOCK)
                    WHERE name LIKE ? ESCAPE '\\'
                    ORDER BY name DESC
                    """,
                    (pat,),
                )
                row = cur.fetchone()
                if row:
                    self.logger.info(f"[OPT-DGM] tablo bulundu: {row[0]} (pattern={pat})")
                    return row[0]

            self.logger.info(f"[OPT-DGM] hiçbir tablo bulunamadı (model={m})")
            return None

        finally:
            with contextlib.suppress(Exception):
                cur.close()
            with contextlib.suppress(Exception):
                conn.close()


    def _pretty_price_header(self, col_name: str) -> str:
        """
        PriceList kolon adını kullanıcıya daha okunur hale getirir.
        Örn: 'Net_Satis__TL_'  -> 'Net Satış (TL)'
             'Anahtar_Teslim___25_OTV_' -> 'Anahtar Teslim (%25 ÖTV)'
        """
        import re
        s = col_name or ""
        raw = s

        # Alt çizgileri boşluğa çevir
        s = s.replace("__", "_")
        s = s.replace("_", " ").strip()

        # Net Satış
        s = re.sub(r"(?i)net\s*satis", "Net Satış", s)

        # Anahtar Teslim + ÖTV yüzdesi
        m = re.search(r"(?i)anahtar\s*teslim.*?(\d+)\s*otv", s)
        if m:
            pct = m.group(1)
            return f"Anahtar Teslim (%{pct} ÖTV)"

        # TL ipucu
        if "tl" in s.lower():
            return "Net Satış (TL)"

        return raw.replace("_", " ").strip()

    def _price_row_from_pricelist(self, user_message: str, user_id: str | None = None) -> str | None:
        """
        PriceList_KODA_<MODEL>_* tablosundan, kullanıcının sorduğu opsiyon/paket satırını bulur.
        - Eğer kullanıcı belirli bir opsiyonu/paketi tarif ediyorsa → tek satır + açıklama.
        - Eğer kullanıcı sadece trim belirtiyorsa (ör. 'Kamiq Elite opsiyonel donanımlar neler') →
        o trime ait TÜM satırları tablo halinde döndürür.
        """
        import re, contextlib

        q = normalize_tr_text(user_message or "").lower()
        if not q:
            return None

        # 🔹 Trim ipucunu yakala (premium / elite / monte carlo vb.)
        trim_hint = None
        try:
            trim_set = extract_trims(user_message.lower())
            if trim_set:
                trim_hint = next(iter(trim_set))  # tek bir trim bekliyoruz
        except Exception:
            trim_hint = None

        # 🔹 Basit normalizasyon (PriceList kolonları için – strip_tr_suffixes KULLANMIYORUZ)
        def norm(s: str) -> str:
            s = (s or "").strip().lower()
            s = re.sub(r"\s+", " ", s)
            return s

        # Trim varyantlarını (monte carlo → monte_carlo / montecarlo / mc vb.) üret
        trim_variants_norm: list[str] = []
        if trim_hint:
            try:
                trim_variants_norm = [norm(v) for v in normalize_trim_str(trim_hint)]
            except Exception:
                trim_variants_norm = [norm(trim_hint)]

        # 1) Modeli bul
        models = list(self._extract_models(user_message))
        model = models[0] if models else None

        if not model and user_id:
            last_models = (self.user_states.get(user_id, {}) or {}).get("last_models", set())
            if len(last_models) == 1:
                model = list(last_models)[0]

        if not model:
            return None

        m_slug = model.lower()
        tname = self._latest_pricelist_table_for(m_slug)
        if not tname:
            self.logger.info(f"[PRICE] PriceList tablosu bulunamadı: model={m_slug}")
            return None

        conn = self._sql_conn()
        cur  = conn.cursor()
        try:
            # Şemayı al
            cur.execute(f"SELECT TOP 0 * FROM [dbo].[{tname}] WITH (NOLOCK)")
            cols = [c[0] for c in cur.description] if cur.description else []
            if not cols:
                return None

            # Önemli kolonlar
            model_col = next((c for c in cols if norm(c) in {"model", "modelname"}), None)
            trim_col  = next((c for c in cols if "trim" in norm(c) or "donan" in norm(c) or "variant" in norm(c)), None)
            code_col  = next((c for c in cols if "kod"  in norm(c) or "code"    in norm(c)), None)
            desc_col  = next((c for c in cols if any(k in norm(c) for k in ["aciklama", "açıklama", "description"])), None)

            # Fiyat kolonları (Net_Satis / Anahtar_Teslim / Price / Fiyat)
            price_cols = [
                c for c in cols
                if re.search(r"(net\s*satis|netsatis|net_satis|anahtar\s*teslim|anahtar_teslim|price|fiyat)",
                            norm(c), re.I)
            ]
            # Model/Trim/Kod/Açıklama kolonlarını fiyat listesinden çıkar
            for c in [model_col, trim_col, code_col, desc_col]:
                if c in price_cols:
                    price_cols.remove(c)

            if not (code_col or desc_col) or not price_cols:
                self.logger.info(f"[PRICE] Uygun kolon bulunamadı: table={tname}")
                return None

            # Veriyi çek (çok büyük olmasın diye TOP 500)
            cur.execute(f"SELECT TOP 500 * FROM [dbo].[{tname}] WITH (NOLOCK)")
            rows = cur.fetchall()
            if not rows:
                return None

            # Tüm satırları dict'e çevir
            records = [{cols[i]: r[i] for i in range(len(cols))} for r in rows]

            # 🔹 Trim filtresi — varyantlarla birlikte
            if trim_variants_norm and trim_col:
                filtered = []
                for rec in records:
                    trim_val = str(rec.get(trim_col) or "")
                    trim_n = norm(trim_val)
                    if any(v and v in trim_n for v in trim_variants_norm):
                        filtered.append(rec)

                if filtered:
                    self.logger.info(
                        f"[PRICE] Trim filtresi uygulandı: hint='{trim_hint}', "
                        f"variants={trim_variants_norm}, rows={len(filtered)}"
                    )
                    records = filtered
                else:
                    self.logger.info(
                        f"[PRICE] Trim filtresi için eşleşme bulunamadı, tüm satırlar kullanılıyor. "
                        f"(hint='{trim_hint}', variants={trim_variants_norm})"
                    )

            # --  Soru tokenları ----------------------------------------------------
            stop = {
                "fiyat", "fiyati", "fiyatı", "fiyati?", "fiyati?",
                "ne", "kadar", "nedir", "mi", "mı", "mu", "mü",
                "tl", "₺", "tl?", "otv", "ötv", "otv?", "ötv?",
                "opsiyon", "opsiyonu", "opsiyonlar", "opsiyonel",
                "opsiyonun", "seçeneği", "seçenek", "secenek",
            }
            tokens_raw = [w for w in re.findall(r"[0-9a-zçğıöşü]+", q) if w not in stop]

            # Genel/generic kelimeler
            generic_tokens = {
                "opsiyon", "opsiyonel", "opsiyonlar", "opsiyonlari", "opsiyonları",
                "paket", "paketi", "paketler",
                "donanim", "donanım", "donanimlar", "donanımlar", "donanımlar",
                "seçenek", "secenek", "seçenekler", "secenekler",
                "neler", "nelerdir",
                "hepsi", "tumu", "tümü", "tamami", "tamamı",
                "fiyatlar", "fiyatlari", "fiyatları",
            }

            # Model + trim kelimeleri
            model_tokens = {model.lower()} if model else set()
            for v in trim_variants_norm:
                for p in re.findall(r"[0-9a-zçğıöşü]+", v):
                    model_tokens.add(p)

            # 🔹 Bu soru sadece "trim + genel kelimeler" mi soruyor?
            only_generic_tokens = True
            for w in tokens_raw:
                if (w not in generic_tokens) and (w not in model_tokens):
                    only_generic_tokens = False
                    break

            # Skorlamada kullanılacak "özgül" tokenlar
            tokens = [
                w for w in tokens_raw
                if w not in generic_tokens and w not in model_tokens
            ]
                    # ===================================================================
            #  YENİ: SADECE MODEL + OPSİYONEL DONANIM → TÜM PRICELIST TABLOSU
            #  Örn: "Kamiq opsiyonel donanımlar neler"
            # ===================================================================
            asks_full_list = (
                "opsiyon" in q and
                (
                    "donan" in q or
                    any(w in q for w in ["neler", "nelerdir", "tümü", "tumu",
                                         "tamamı", "tamami", "hepsi", "liste"])
                )
            )

            if (
                not trim_variants_norm   # trim hiç belirtilmemiş
                and trim_col            # tabloda Trim kolonu var
                and asks_full_list
                and only_generic_tokens # ekstra spesifik kelime yok
            ):
                # Bu model için tüm satırları tablo olarak döndür
                full_records = records[:]  # PriceList tablosu zaten ilgili model için seçili

                if full_records:
                    header_labels = []
                    if model_col:
                        header_labels.append("Model")
                    if trim_col:
                        header_labels.append("Trim")
                    if code_col:
                        header_labels.append("Kod")
                    if desc_col:
                        header_labels.append("Açıklama")
                    for pc in price_cols:
                        header_labels.append(self._pretty_price_header(pc))

                    if not header_labels:
                        return None

                    lines = []
                    lines.append("| " + " | ".join(header_labels) + " |")
                    lines.append("|" + "|".join(["---"] * len(header_labels)) + "|")

                    for rec in full_records:
                        row_cells = []
                        if model_col:
                            row_cells.append(self._safe_cell(rec.get(model_col)))
                        if trim_col:
                            row_cells.append(self._safe_cell(rec.get(trim_col)))
                        if code_col:
                            row_cells.append(self._safe_cell(rec.get(code_col)))
                        if desc_col:
                            row_cells.append(self._safe_cell(rec.get(desc_col)))
                        for pc in price_cols:
                            row_cells.append(self._safe_cell(rec.get(pc)))
                        lines.append("| " + " | ".join(row_cells) + " |")

                    md = "\n".join(lines)
                    try:
                        md = fix_markdown_table(md)
                    except Exception:
                        pass

                    title = f"{model.title()} opsiyon fiyatları"
                    return f"<b>{title}</b><br>\n\n{md}\n"


            # ===  EĞER SADECE TRIM SORULDUYSA → O TRİME AİT TÜM KAYITLAR  =========
            # Örn: "Kamiq Elite opsiyonel donanımlar neler"
            if trim_variants_norm and trim_col and (
                only_generic_tokens or ("opsiyon" in q and "donan" in q)
            ):
                trim_records = records[:]  # zaten yukarıda trim filtresi uygulandıysa sadece o trim var

                if trim_records:
                    header_labels = []
                    if model_col:
                        header_labels.append("Model")
                    if trim_col:
                        header_labels.append("Trim")
                    if code_col:
                        header_labels.append("Kod")
                    if desc_col:
                        header_labels.append("Açıklama")
                    for pc in price_cols:
                        header_labels.append(self._pretty_price_header(pc))

                    if not header_labels:
                        return None

                    lines = []
                    lines.append("| " + " | ".join(header_labels) + " |")
                    lines.append("|" + "|".join(["---"] * len(header_labels)) + "|")

                    for rec in trim_records:
                        row_cells = []
                        if model_col:
                            row_cells.append(self._safe_cell(rec.get(model_col)))
                        if trim_col:
                            row_cells.append(self._safe_cell(rec.get(trim_col)))
                        if code_col:
                            row_cells.append(self._safe_cell(rec.get(code_col)))
                        if desc_col:
                            row_cells.append(self._safe_cell(rec.get(desc_col)))
                        for pc in price_cols:
                            row_cells.append(self._safe_cell(rec.get(pc)))
                        lines.append("| " + " | ".join(row_cells) + " |")

                    md = "\n".join(lines)
                    try:
                        md = fix_markdown_table(md)
                    except Exception:
                        pass

                    trim_title = trim_hint.title() if trim_hint else str(trim_records[0].get(trim_col) or "").strip()
                    title = f"{model.title()} {trim_title} opsiyon fiyatları"
                    return f"<b>{title}</b><br>\n\n{md}\n"

            # ===  Aksi halde: belirli bir opsiyon/paket satırı bul  =================
            best_row = None
            best_score = 0.0

            for rec in records:
                desc_raw = str(rec.get(desc_col) or "").strip()
                code_raw = str(rec.get(code_col) or "").strip()

                desc_n = norm(desc_raw)
                code_n = norm(code_raw)

                trim_raw = str(rec.get(trim_col) or "").strip() if trim_col else ""
                trim_n   = norm(trim_raw)

                if not desc_n and not code_n and not trim_n:
                    continue

                score = 0.0

                # Trim sinyali
                if trim_variants_norm and trim_n:
                    if any(v and v in trim_n for v in trim_variants_norm):
                        score += 7.0

                # Kod tam geçiyorsa güçlü sinyal
                if code_n and code_n in q:
                    score += 8.0

                # Açıklama ↔ cümle eşleşmesi
                if desc_n and (desc_n in q or q in desc_n):
                    score += 6.0

                # Token bazlı eşleşme (sadece özgül içerik tokenları)
                for t in tokens:
                    if t and t in desc_n:
                        score += 2.0
                    if code_n and t == code_n:
                        score += 4.0
                    if code_n and t in code_n:
                        score += 2.0

                if score > best_score:
                    best_score = score
                    best_row = rec

            MIN_SCORE = 2.0  # eskiden 4.0'dı

            if not best_row or best_score < MIN_SCORE:
                # Daha detaylı debug: hangi satıra en çok yaklaştık?
                dbg_desc = (best_row.get(desc_col) if (best_row and desc_col) else "") if isinstance(best_row, dict) else ""
                dbg_code = (best_row.get(code_col) if (best_row and code_col) else "") if isinstance(best_row, dict) else ""
                self.logger.info(
                    "[PRICE] Eşleşme yok / skor düşük "
                    f"(score={best_score:.2f}, model={m_slug}, "
                    f"trim_hint={trim_hint}, best_desc='{dbg_desc}', best_code='{dbg_code}', q='{q}')"
                )
                return None

            # ---------- Tek satırlık Markdown tablo ----------
            header_labels = []
            row_cells = []

            if model_col:
                header_labels.append("Model")
                row_cells.append(self._safe_cell(best_row.get(model_col)))

            if trim_col:
                header_labels.append("Trim")
                row_cells.append(self._safe_cell(best_row.get(trim_col)))

            if code_col:
                header_labels.append("Kod")
                row_cells.append(self._safe_cell(best_row.get(code_col)))

            if desc_col:
                header_labels.append("Açıklama")
                row_cells.append(self._safe_cell(best_row.get(desc_col)))

            for pc in price_cols:
                header_labels.append(self._pretty_price_header(pc))
                row_cells.append(self._safe_cell(best_row.get(pc)))

            if not header_labels:
                return None

            lines = []
            lines.append("| " + " | ".join(header_labels) + " |")
            lines.append("|" + "|".join(["---"] * len(header_labels)) + "|")
            lines.append("| " + " | ".join(row_cells) + " |")

            md = "\n".join(lines)
            try:
                md = fix_markdown_table(md)
            except Exception:
                pass

            title = f"{model.title()} opsiyon fiyatı"

            # -------- Tablo altı metinsel özet --------
            trim_txt = str(best_row.get(trim_col) or "").strip() if trim_col else ""
            desc_txt = str(best_row.get(desc_col) or "").strip() if desc_col else ""

            def _with_tl(val: str) -> str:
                v = (val or "").strip()
                low = v.lower()
                if not v:
                    return v
                return v if ("tl" in low or "₺" in low) else (v + " TL")

            # Net satış kolonu seç
            main_col = None
            for pc in price_cols:
                n = norm(pc)
                if "net" in n and "satis" in n:
                    main_col = pc
                    break
            if not main_col and price_cols:
                main_col = price_cols[0]

            main_raw = str(best_row.get(main_col) or "").strip() if main_col else ""
            main_val = _with_tl(main_raw) if main_raw else ""
            label_main = self._pretty_price_header(main_col) if main_col else ""

            # Anahtar teslim kolonu (varsa)
            key_col = None
            for pc in price_cols:
                n = norm(pc)
                if "anahtar" in n:
                    key_col = pc
                    break
            key_raw = str(best_row.get(key_col) or "").strip() if key_col else ""
            key_val = _with_tl(key_raw) if key_raw else ""
            label_key = self._pretty_price_header(key_col) if key_col else ""

            narrative = ""
            try:
                pieces = []
                if main_val:
                    pieces.append(f"{label_main}: {main_val}")
                if key_val:
                    pieces.append(f"{label_key}: {key_val}")
                value_for_nlg = " | ".join(pieces) if pieces else main_val

                metric = f"Opsiyon: {(desc_txt or 'Metalik Renk')}"
                narrative = self._nlg_via_openai(
                    model_name=model.title(),
                    metric=metric,
                    value=value_for_nlg,
                    tone=os.getenv("NLG_TONE", "neutral"),
                    length=os.getenv("NLG_LENGTH", "short"),
                )
            except Exception as e:
                self.logger.error(f"[PRICE-NLG] hata: {e}")
                narrative = ""

            if not narrative and main_val:
                mt = model.title()
                trim_disp = ""
                if trim_txt:
                    if trim_txt.startswith(mt):
                        trim_disp = trim_txt[len(mt):].strip()
                    else:
                        trim_disp = trim_txt.strip()

                model_txt = mt
                if trim_disp:
                    model_txt += f" {trim_disp}"

                base = f"{model_txt} için {(desc_txt or 'bu')} opsiyonunun"
                if key_val:
                    narrative = (
                        f"{base} {label_main.lower()} {main_val}, "
                        f"{label_key.lower()} ise {key_val} seviyesindedir."
                    )
                else:
                    narrative = f"{base} {label_main.lower()} {main_val} seviyesindedir."

            if narrative:
                return f"<b>{title}</b><br>\n\n{md}\n\n{narrative}\n"
            else:
                return f"<b>{title}</b><br>\n\n{md}\n"

        finally:
            with contextlib.suppress(Exception):
                cur.close()
            with contextlib.suppress(Exception):
                conn.close()





    def _latest_pricelist_table_for(self, model: str) -> str | None:
        """
        Örn. 'ELROQ' -> önce PriceList_KODA_ELROQ_MY_%,
        o yoksa diğer PriceList_KODA_ELROQ_% tablosuna düşer.
        """
        import contextlib

        m = (model or "").strip().upper()
        if not m:
            return None

        conn = self._sql_conn()
        cur  = conn.cursor()
        try:
            patterns = [
                # 1) Önce MY_20xx formatlı güncel tabloyu dene
                f"PriceList\\_KODA\\_{m}\\_MY\\_%",
                # 2) Bulunamazsa eski isimlendirmelere düş
                f"PriceList\\_KODA\\_{m}%",
            ]

            for pat in patterns:
                cur.execute(
                    """
                    SELECT TOP 1 name
                    FROM sys.tables WITH (NOLOCK)
                    WHERE name LIKE ? ESCAPE '\\'
                    ORDER BY name DESC
                    """,
                    (pat,),
                )
                row = cur.fetchone()
                if row:
                    self.logger.info(f"[PRICE] tablo bulundu: {row[0]} (pattern={pat})")
                    return row[0]

            self.logger.info(f"[PRICE] hiçbir PriceList tablosu bulunamadı (model={m})")
            return None

        finally:
            with contextlib.suppress(Exception):
                cur.close()
                conn.close()



    def _is_price_intent(self, text: str, threshold: float | None = None) -> bool:
        """
        YALNIZCA gerçek fiyat sorularını yakalar ama
        opsiyon/paket/renk + 'ne kadar / kaç para' gibi cümleleri de kapsar.

        Örnek:
        - 'Fabia fiyatları'                      -> True
        - 'Octavia anahtar teslim fiyatı ne?'    -> True
        - 'Kamiq Premium akıllı çözümler paketi ne kadar?' -> True
        - 'kaç para?'                            -> False
        - 'menzili ne kadar / kaç km'           -> False
        """
        if not text:
            return False

        t_norm = normalize_tr_text(text).lower()

        # 1) 'fiyat' kelimesi ve türevleri, 'anahtar teslim', 'liste fiyat'
        if "fiyat" in t_norm or "liste fiyat" in t_norm or "anahtar teslim" in t_norm:
            return True

        import re

        # 2) Rakam + TL / ₺ (750.000 TL, 1.450.000₺ gibi)
        if re.search(r"(?:\b\d{1,3}(?:\.\d{3})*(?:,\d+)?|\b\d+(?:,\d+)?)\s*(tl|₺)\b", t_norm):
            return True

        # 3) 'ne kadar / kaç para / kaça' ama sadece fiyat bağlamında
        has_ne_kadar = ("ne kadar" in t_norm) or ("nekadar" in t_norm)
        has_kac_para = ("kaç para" in t_norm) or ("kac para" in t_norm)
        has_kaca     = ("kaça" in t_norm) or ("kaca" in t_norm)

        if has_ne_kadar or has_kac_para or has_kaca:
            # teknik / fiyat-dışı konular varsa ASLA fiyat sayma
            non_price_ctx = [
                "menzil", "range", "yakıt", "tüketim", "tuketim",
                "0-100", "0 – 100", "0 100", "ivme", "hız", "hiz",
                "tork", "güç", "guc", "ps", "kw", "co2", "emisyon",
                "bagaj", "hacim", "dm3", "kapı", "kapi", "km", "km/h",
                "ne kadar sürer", "kaç saat"
            ]
            if any(w in t_norm for w in non_price_ctx):
                return False

            # ✅ MODEL varsa: "Fabia ne kadar?" gibi sorular fiyat sayılır
            if self._extract_models(text):
                return True

            # fiyat bağlam kelimeleri varsa yine fiyat say
            price_ctx = [
                "opsiyon", "opsiyonel", "paket", "donanım", "donanim",
                "renk", "metalik", "kod", "ops.",
                "anahtar teslim", "liste fiyat", "kampanya", "net satış", "net satis",
                "ötv", "otv", "vergi"
            ]
            if any(w in t_norm for w in price_ctx):
                return True


        # 4) Geri kalan hiçbir şey (saf 'ne kadar', 'kaç para', 'kaça' vs.) fiyat sayılmasın
        return False


    def _spec_row_markdown_from_imported(self, model_code: str, canon_key: str) -> str | None:
        """
        Imported_KODA_<MODEL>_MY_% tablosundan, istenen kanonik metrik satırını
        tek satırlık bir Markdown tablo olarak döndürür.
        Örn: 'yakıt tüketimi' için:
        | Teknik Özellik                      | Kodiaq Premium ... | Kodiaq Prestige ... | ... |
        | Birleşik tüketim, Birleşik (l/100) | 7,5                | 7,6                 | ... |
        """
        import contextlib, re

        m = (model_code or "").strip().upper()
        if not m or not canon_key:
            return None

        def nrm(s: str) -> str:
            return re.sub(r"\s+", " ", normalize_tr_text(s or "")).lower().strip()

        canon = canon_key.lower()

        conn = self._sql_conn()
        cur = conn.cursor()
        try:
            # 1) İlgili Imported_* tablosunu bul
            cur.execute(
                """
                SELECT TOP 1 name
                FROM sys.tables
                WHERE name LIKE ? ESCAPE '\\'
                ORDER BY name DESC
                """,
                (f"Imported\\_KODA\\_{m}\\_MY\\_%",),
            )
            row = cur.fetchone()
            if not row:
                return None

            tname = row[0]

            # 2) Kolonları oku
            cur.execute(f"SELECT TOP 0 * FROM [{tname}]")
            cols = [c[0] for c in cur.description] if cur.description else []
            if not cols:
                return None

            # Özellik kolonu
            name_col = None
            for cand in ["Ozellik", "Özellik", "SpecName", "Name", "Title", "Attribute"]:
                if cand in cols:
                    name_col = cand
                    break
            if not name_col:
                name_col = next(
                    (c for c in cols if re.search(r"(ozellik|özellik|name|title|attribute)", c, re.I)),
                    None,
                )
            if not name_col:
                return None

            # Trim kolonları = id / Model / Ozellik dışındaki her şey
            trim_cols = [c for c in cols if c not in ("id", "ID", "Model", name_col)]
            if not trim_cols:
                return None

            # 3) Tüm satırları oku
            cur.execute(
                f"SELECT [{name_col}], {', '.join(f'[{c}]' for c in trim_cols)} "
                f"FROM [{tname}] WITH (NOLOCK)"
            )
            rows = cur.fetchall()
            if not rows:
                return None

            def matches(canon_key: str, oz_norm: str) -> bool:
                if canon_key == "tork":
                    return "tork" in oz_norm
                if canon_key == "güç":
                    return ("guc" in oz_norm or "güç" in oz_norm or "motor gücü" in oz_norm)
                if canon_key == "0-100":
                    return ("0-100" in oz_norm or "0 100" in oz_norm or "ivme" in oz_norm)
                if canon_key == "maksimum hız":
                    return (
                        ("maks" in oz_norm and ("hiz" in oz_norm or "hız" in oz_norm))
                        or "max speed" in oz_norm
                        or "top speed" in oz_norm
                    )
                if canon_key == "yakıt tüketimi":
                    return (
                        ("birlesik" in oz_norm or "birleşik" in oz_norm or "kombine" in oz_norm)
                        and ("l/100" in oz_norm or "l / 100" in oz_norm or "100 km" in oz_norm)
                    )
                if canon_key == "co2":
                    return ("co2" in oz_norm or "emisyon" in oz_norm)
                # ✅ YENİ: MENZİL
                if canon_key == "menzil":
                    return ("menzil" in oz_norm) or ("range" in oz_norm) or ("wltp" in oz_norm and ("km" in oz_norm))
                if canon_key == "batarya":
                    # "Batarya kapasitesi (net kWh)" / "brüt kWh" / "Battery capacity" vb.
                    return ("batarya" in oz_norm or "battery" in oz_norm) and ("kwh" in oz_norm or "k w h" in oz_norm)

                if canon_key == "sarj":
                    return ("şarj" in oz_norm or "sarj" in oz_norm or "charging" in oz_norm or "charge" in oz_norm) and (
                        ("ac" in oz_norm) or ("dc" in oz_norm) or ("10-80" in oz_norm) or ("%10" in oz_norm and "%80" in oz_norm)
                    )
                if canon_key in {"agirlik", "ağırlık"}:
                    return ("ağırlık" in oz_norm) or ("agirlik" in oz_norm) or ("weight" in oz_norm) or ("kg" in oz_norm)

                return False

            qctx = getattr(self, "_LAST_SPEC_QUERY", "") or ""
            want_city = ("şehir" in qctx) or ("sehir" in qctx) or ("city" in qctx)
            want_comb = ("kombine" in qctx) or ("birlesik" in qctx) or ("birleşik" in qctx) or ("combined" in qctx)

            cands = []  # (score, row_tuple)
            for r in rows:
                oz_raw = str(r[0] or "").strip()
                oz_norm = nrm(oz_raw)
                if not matches(canon, oz_norm):
                    continue

                score = 0
                if canon == "menzil":
                    is_city = ("şehir" in oz_norm) or ("sehir" in oz_norm) or ("city" in oz_norm)
                    is_comb = ("kombine" in oz_norm) or ("birlesik" in oz_norm) or ("birleşik" in oz_norm) or ("combined" in oz_norm)

                    if want_city:
                        score += 20 if is_city else -10
                    elif want_comb:
                        score += 20 if is_comb else 0
                        score -= 10 if is_city else 0
                    else:
                        score += 5 if is_comb else 0
                        score -= 3 if is_city else 0

                cands.append((score, r))

            best_row = None
            if cands:
                cands.sort(key=lambda x: x[0], reverse=True)
                best_row = cands[0][1]


            if not best_row:
                return None

            feature_title = str(best_row[0] or "").strip()

            # 4) Markdown tabloyu üret
            header_labels = ["Teknik Özellik"] + [
                self._pretty_trim_header(c) for c in trim_cols
            ]

            lines = []
            # başlık
            lines.append(
                "| " + " | ".join(self._safe_cell(h) for h in header_labels) + " |"
            )
            # ayraç
            lines.append("|" + "|".join(["---"] * len(header_labels)) + "|")

            # satır
            row_cells = [self._safe_cell(feature_title)]
            for idx, c in enumerate(trim_cols, start=1):
                v = str(best_row[idx] or "").strip() if idx < len(best_row) else ""
                row_cells.append(self._safe_cell(v) if v else "—")
            lines.append("| " + " | ".join(row_cells) + " |")

            md = "\n".join(lines)
            try:
                md = fix_markdown_table(md)
            except Exception:
                pass
            return md
        finally:
            with contextlib.suppress(Exception):
                cur.close()
            with contextlib.suppress(Exception):
                conn.close()

    def _pretty_trim_header(self, col_name: str) -> str:
        """
        SQL kolon adını (Karoq_Premium_1_5_TSI_150_PS_DSG)
        kullanıcı dostu başlığa çevirir (Karoq Premium 1.5 TSI 150 PS DSG).
        """
        import re

        s = col_name or ""

        # 1_5_TSI → 1.5_TSI, 2_0_TDI → 2.0_TDI, 1_5_mHEV → 1.5_mHEV vb.
        s = re.sub(
            r"(\d)_([0-9])_(TSI|TDI|MPI|mHEV|PHEV)",
            r"\1.\2_\3",
            s,
            flags=re.IGNORECASE,
        )

        # Kalan alt çizgileri boşluğa çevir
        s = s.replace("_", " ")

        return s.strip()

    def _match_all_trim_columns(self, trim_hint: str, trim_cols: list[str]) -> list[str]:
        """
        Bir trim için (örn. 'premium') Imported_* tablosundaki TÜM eşleşen kolonları döndürür.
        Örn:
          trim_hint = 'premium'
          trim_cols = ['Scala_Elite_1_0_TSI_115_PS_DSG',
                       'Scala_Premium_1_0_TSI_115_PS_DSG',
                       'Scala_Premium_1_5_TSI_150_PS_DSG',
                       'Scala_Monte_Carlo_1_5_TSI_150_PS_DSG']
          --> ['Scala_Premium_1_0_TSI_115_PS_DSG',
               'Scala_Premium_1_5_TSI_150_PS_DSG']
        """
        if not trim_hint or not trim_cols:
            return []

        variants = normalize_trim_str(trim_hint)  # mevcut fonksiyon
        norm_variants = [
            normalize_tr_text(v).lower().replace(" ", "_")
            for v in variants if v
        ]

        matched = []
        for col in trim_cols:
            col_norm = normalize_tr_text(col).lower().replace(" ", "_")
            if any(v and v in col_norm for v in norm_variants):
                matched.append(col)

        # Sıra bozulmasın, tekrarlı olmasın
        seen = set()
        uniq = []
        for c in matched:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        return uniq

    def _match_trim_column_name(self, trim_hint: str, trim_cols: list[str]) -> str | None:
        """
        CURRENT_TRIM_HINT ile gelen trim adını (premium / monte carlo / e prestige 60 vb.)
        Imported_* tablolarındaki kolon isimleriyle sağlam şekilde eşleştirir.

        Örn:
          trim_hint = "monte carlo"
          trim_cols = ["Fabia_Premium_1_0_TSI_115_PS_DSG",
                       "Fabia_Monte_Carlo_1_5_TSI_150_PS_DSG"]
          --> "Fabia_Monte_Carlo_1_5_TSI_150_PS_DSG"
        """
        if not trim_hint or not trim_cols:
            return None

        # Trim için tüm varyantları üret (boşluksuz, alt çizgili, kısaltmalar vs.)
        variants = normalize_trim_str(trim_hint)  # global fonksiyon
        norm_variants = [
            normalize_tr_text(v).lower().replace(" ", "_")
            for v in variants
            if v
        ]

        best_col = None
        best_score = 0

        for col in trim_cols:
            col_norm = normalize_tr_text(col).lower().replace(" ", "_")
            for v in norm_variants:
                if v and v in col_norm:
                    # daha uzun varyant = daha güçlü eşleşme
                    score = len(v)
                    if score > best_score:
                        best_score = score
                        best_col = col
                    break  # bu kolon için başka varyanta bakmaya gerek yok

        return best_col

    def _spec_from_imported_by_ozellik(self, model_code: str, canon_key: str) -> str | None:
        """
        Imported_KODA_<MODEL>_MY_% tablosundan, Ozellik satırına bakarak
        tek bir teknik değer döndürür (Maks. hız, tork, 0-100, Birleşik tüketim, CO2…).

        Bu sürüm SQL'de WHERE LIKE kullanmak yerine:
        - Tabloyu bir kez okuyup
        - Python tarafında Ozellik metnini normalize ederek eşleştirir.
        Böylece 'Maks. tork [Nm / dev/dak]' vb. satırları kaçırma riski kalmaz.
        """

        import contextlib
        import re

        m = (model_code or "").strip().upper()
        if not m or not canon_key:
            return None

        def nrm(s: str) -> str:
            return re.sub(r"\s+", " ", normalize_tr_text(s or "")).lower().strip()

        canon = canon_key.lower()

        conn = self._sql_conn()
        cur = conn.cursor()
        try:
            # 1) İlgili Imported_KODA_<MODEL> tablosunu bul
            cur.execute(
                """
                SELECT TOP 1 name
                FROM sys.tables
                WHERE name LIKE ? ESCAPE '\\'
                ORDER BY name DESC
                """,
                (f"Imported\\_KODA\\_{m}\\_MY\\_%",),
            )
            row = cur.fetchone()
            if not row:
                self.logger.info(f"[SQL-SPEC] Imported_KODA_{m}_MY_% tablosu bulunamadı.")
                return None

            tname = row[0]

            # 2) Kolonları oku
            cur.execute(f"SELECT TOP 0 * FROM [{tname}]")
            cols = [c[0] for c in cur.description] if cur.description else []
            if not cols:
                return None

            # Ozellik kolonu
            name_col = None
            for cand in ["Ozellik", "Özellik", "SpecName", "Name", "Title", "Attribute"]:
                if cand in cols:
                    name_col = cand
                    break
            if not name_col:
                name_col = next(
                    (c for c in cols if re.search(r"(ozellik|özellik|name|title|attribute)", c, re.I)),
                    None,
                )
            if not name_col:
                return None

            # Trim kolonları = id / Model / Ozellik dışındaki her şey
            trim_cols = [c for c in cols if c not in ("id", "ID", "Model", name_col)]
            if not trim_cols:
                return None

            # 3) Tüm satırları oku
            cur.execute(
                f"SELECT [{name_col}], {', '.join(f'[{c}]' for c in trim_cols)} "
                f"FROM [{tname}] WITH (NOLOCK)"
            )
            rows = cur.fetchall()
            if not rows:
                return None

            # 4) Hangi Ozellik satırı arandığını metin üzerinden belirle
            def matches(canon_key: str, oz_norm: str) -> bool:
                if canon_key == "tork":
                    # 'tork' içeren satır (Maks. tork [Nm / dev/dak] ...)
                    return "tork" in oz_norm
                if canon_key == "güç":
                    return ("guc" in oz_norm or "güç" in oz_norm or "motor gücü" in oz_norm)
                if canon_key == "0-100":
                    return ("0-100" in oz_norm or "0 100" in oz_norm or "ivme" in oz_norm)
                if canon_key == "maksimum hız":
                    return (
                        ("maks" in oz_norm and ("hiz" in oz_norm or "hız" in oz_norm))
                        or "max speed" in oz_norm
                        or "top speed" in oz_norm
                    )
                if canon_key == "yakıt tüketimi":
                    # Birleşik / Kombine faz
                    return (
                        ("birlesik" in oz_norm or "birleşik" in oz_norm or "kombine" in oz_norm)
                        and ("l/100" in oz_norm or "l / 100" in oz_norm or "100 km" in oz_norm)
                    )
                if canon_key == "co2":
                    return ("co2" in oz_norm or "emisyon" in oz_norm)
                if canon_key == "menzil":
                    return ("menzil" in oz_norm) or ("range" in oz_norm) or ("wltp" in oz_norm)
                if canon_key in {"agirlik", "ağırlık"}:
                    return ("ağırlık" in oz_norm) or ("agirlik" in oz_norm) or ("weight" in oz_norm) or ("kg" in oz_norm)

                return False

            qctx = getattr(self, "_LAST_SPEC_QUERY", "") or ""
            want_city = ("şehir" in qctx) or ("sehir" in qctx) or ("city" in qctx)
            want_comb = ("kombine" in qctx) or ("birlesik" in qctx) or ("birleşik" in qctx) or ("combined" in qctx)

            cands = []  # (score, rec_dict)
            for r in rows:
                oz_raw = str(r[0] or "").strip()
                oz_norm = nrm(oz_raw)
                if not matches(canon, oz_norm):
                    continue

                rec = {([name_col] + trim_cols)[i]: r[i] for i in range(1 + len(trim_cols))}

                score = 0
                # --- MENZİL satırını doğru seç ---
                if canon == "menzil":
                    is_city = ("şehir" in oz_norm) or ("sehir" in oz_norm) or ("city" in oz_norm)
                    is_comb = ("kombine" in oz_norm) or ("birlesik" in oz_norm) or ("birleşik" in oz_norm) or ("combined" in oz_norm)

                    if want_city:
                        score += 20 if is_city else -10
                    elif want_comb:
                        score += 20 if is_comb else 0
                        score -= 10 if is_city else 0
                    else:
                        # kullanıcı belirtmediyse: kombineyi tercih et, şehir içini geri at
                        score += 5 if is_comb else 0
                        score -= 3 if is_city else 0

                # değer hücresinde rakam varsa + (daha güvenilir)
                blob = " ".join(str(rec.get(c) or "") for c in trim_cols)
                if re.search(r"\d", blob):
                    score += 2

                cands.append((score, rec))

            best_rec = None
            if cands:
                cands.sort(key=lambda x: x[0], reverse=True)
                best_rec = cands[0][1]


            if not best_rec:
                self.logger.info(f"[SQL-SPEC] Imported_{m} içerisinde '{canon}' için uygun Ozellik satırı bulunamadı.")
                return None

            # 5) CURRENT_TRIM_HINT varsa o trime ait kolonu seç
            trim_cols_local = trim_cols[:]  # kısayol
            trim_pref = getattr(self, "CURRENT_TRIM_HINT", None)
            if trim_pref:
                col_name = self._match_trim_column_name(trim_pref, trim_cols_local)
                if col_name:
                    val = str(best_rec.get(col_name) or "").strip()
                    if val:
                        return val

            # 6) Aksi halde: sayısal değer içeren trim kolonları arasından en anlamlıyı seç
            candidates = []
            for c in trim_cols_local:
                v = str(best_rec.get(c) or "").strip()
                if not v:
                    continue
                # sadece başlıkla birebir aynıysa ve rakam yoksa at
                if nrm(v) == nrm(best_rec.get(name_col)) and not re.search(r"\d", v):
                    continue
                score = 0
                if re.search(r"\d", v):
                    score += 3
                # tipik üniteler → ekstra puan
                if re.search(r"(nm|kw|ps|hp|km/?h|sn|g/km|l/100\s*km|kwh|dm3|cc)", v.replace(" ", ""), re.I):
                    score += 3
                score += min(2, len(re.findall(r"\d", v)))
                if score > 0:
                    candidates.append((score, v))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                return candidates[0][1]

            # Eğer hiçbir kolon sayısal veri içermiyorsa son çare: ilk dolu trim hücresini dön
            for c in trim_cols_local:
                v = str(best_rec.get(c) or "").strip()
                if v:
                    return v

            return None

        finally:
            with contextlib.suppress(Exception):
                cur.close()
            with contextlib.suppress(Exception):
                conn.close()


    def _build_spec_comparison_table_from_sql( 
        self,
        models: list[str],
        trim: str | None = None,
        trims_per_model: dict[str, list[str]] | None = None,
    ) -> str:
        self.logger.info("### _build_spec_comparison_table_from_sql YENI VERSIYON CALISTI ###")

        """
        Imported_KODA_<MODEL>_MY_% tablolarından Ozellik + TRIM kolonlarını çekip
        SQL'deki teknik tabloyu önyüze taşır.

        - Karoq gibi tablolarda Premium kolonuna yanlışlıkla Ozellik kopyalanmışsa:
        Premium için aynı satırdaki diğer trim kolonlarından (Prestige/Sportline) değer alır.
        - Kodiaq gibi tablolarda Ozellik kolonunda 1,2,3 gibi ID’ler varsa:
        Gerçek başlığı ilk trim kolonundaki metinden çıkarır ve onu kullanır
        (Silindir Sayısı, Silindir Hacmi (cc) vb.)
        """
        import contextlib, re

        models = [m.lower() for m in (models or []) if m]
        if not models:
            return ""

        # === 1) Her model için Imported_* tablosunu RAM'e al ===
        per_model: dict[str, dict] = {}
        all_features: list[str] = []

        conn = self._sql_conn()
        cur = conn.cursor()
        try:
            for m in models:
                key = (m or "").upper().strip()
                if not key:
                    continue

                # İlgili Imported_KODA_<MODEL> tablosunu bul
                cur.execute(
                    """
                    SELECT TOP 1 name
                    FROM sys.tables
                    WHERE name LIKE ? ESCAPE '\\'
                    ORDER BY name DESC
                    """,
                    (f"Imported\\_KODA\\_{key}\\_MY\\_%",),
                )
                row = cur.fetchone()
                if not row:
                    continue
                tname = row[0]

                # Kolonları oku
                cur.execute(f"SELECT TOP 0 * FROM [{tname}]")
                cols = [c[0] for c in cur.description] if cur.description else []
                if not cols:
                    continue

                # Özellik kolonu
                name_col = None
                for cand in ["Ozellik", "Özellik", "SpecName", "Name", "Title", "Attribute"]:
                    if cand in cols:
                        name_col = cand
                        break
                if not name_col:
                    name_col = next(
                        (
                            c for c in cols
                            if re.search(r"(ozellik|özellik|name|title|attribute)", c, re.I)
                        ),
                        None,
                    )
                if not name_col:
                    continue

                # Trim kolonları = id / Model / Ozellik dışındaki her şey
                trim_cols = [c for c in cols if c not in ("id", "ID", "Model", name_col)]
                if not trim_cols:
                    continue

                # Tüm satırları oku
                cur.execute(
                    f"SELECT [{name_col}], {', '.join(f'[{c}]' for c in trim_cols)} "
                    f"FROM [{tname}] WITH (NOLOCK)"
                )
                rows = cur.fetchall()

                feat_order: list[str] = []
                feat_map: dict[str, dict] = {}

                def _is_good_label(s: str) -> bool:
                    # "1", "2" gibi saf sayı başlıkları eliyoruz
                    s = str(s or "").strip()
                    if not s:
                        return False
                    if re.fullmatch(r"\d+", s):  # sadece rakam
                        return False
                    # en az bir harf olsun
                    return bool(re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", s))

                for r in rows:
                    raw_oz = str(r[0] or "").strip()

                    # Varsayılan başlık Ozellik
                    label = raw_oz

                    # Eğer Ozellik kolonunda düzgün bir metin yoksa (ör. '1','2','3'):
                    # Kodiaq örneği gibi -> ilk trim kolonundan anlamlı başlık bul
                    if not _is_good_label(label):
                        for i, c in enumerate(trim_cols, start=1):
                            cand = r[i]
                            if _is_good_label(cand):
                                label = str(cand).strip()
                                break

                    if not label:
                        continue

                    # Bu label'ı sözlük anahtarı olarak kullanıyoruz
                    feat_key = label

                    if feat_key not in feat_order:
                        feat_order.append(feat_key)

                    vals = {}
                    for i, c in enumerate(trim_cols, start=1):
                        vals[c] = r[i]
                    feat_map[feat_key] = vals

                per_model[m] = {
                    "order":    feat_order,
                    "rows":     feat_map,
                    "trim_cols": trim_cols,
                }

                for feat in feat_order:
                    if feat not in all_features:
                        all_features.append(feat)
        finally:
            with contextlib.suppress(Exception):
                cur.close()
            with contextlib.suppress(Exception):
                conn.close()

        if not all_features:
            return ""

        # === 2) Hangi model için hangi trim(ler) istenmiş? ===
        logical_trims: dict[str, list[str | None]] = {}
        if trims_per_model:
            for m in models:
                logical_trims[m] = list(trims_per_model.get(m, []))
        elif trim:
            for m in models:
                logical_trims[m] = [trim]
        else:
            # trim belirtilmediyse: modeldeki TÜM kolonları göster
            for m in models:
                logical_trims[m] = [None]

        # === 3) Mantıksal trimleri gerçek SQL kolonlarına genişlet ===
        # effective_cols: [(header, model_slug, sql_col_name|None), ...]
        effective_cols: list[tuple[str, str, str | None]] = []

        for m in models:
            md = per_model.get(m)
            if not md:
                continue
            trim_cols = md["trim_cols"]
            wanted = logical_trims.get(m, [None])

            for trim_name in wanted:
                if trim_name is None:
                    # Bu modeldeki tüm kolonları göster
                    for sql_col in trim_cols:
                        header = sql_col.replace("_", " ")
                        effective_cols.append((header, m, sql_col))
                else:
                    matches = self._match_all_trim_columns(trim_name, trim_cols)
                    if not matches:
                        header = f"{m.title()} {trim_name.title()}"
                        effective_cols.append((header, m, None))
                    elif len(matches) == 1:
                        sql_col = matches[0]
                        header = sql_col.replace("_", " ")
                        effective_cols.append((header, m, sql_col))
                    else:
                        # Aynı trim adı altında birden fazla motor/versiyon varsa hepsini ayrı sütun yap
                        for sql_col in matches:
                            header = sql_col.replace("_", " ")
                            effective_cols.append((header, m, sql_col))

        if not effective_cols:
            return ""

        # === 4) Markdown tabloyu üret ===
        header_labels = [h for (h, _m, _c) in effective_cols]

        lines: list[str] = []
        # Başlık satırı
        header_row = ["Teknik Özellik"] + header_labels
        safe_header_cells = [self._safe_cell(c) for c in header_row]
        lines.append("| " + " | ".join(safe_header_cells) + " |")
        # Ayırıcı satırı
        lines.append("|" + "|".join(["---"] * len(safe_header_cells)) + "|")

        # Gövde satırları
        for feat in all_features:
            row_cells = [self._safe_cell(feat)]

            for (_hdr, m, sql_col) in effective_cols:
                model_data = per_model.get(m) or {}
                row_vals   = (model_data.get("rows") or {}).get(feat, {}) or {}
                val = "—"

                if sql_col:
                    raw_v = row_vals.get(sql_col)
                    if raw_v is not None:
                        s = str(raw_v).strip()
                        # 1) Hücre, özellik adıyla bire bir aynıysa -> bozuk veri say
                        same_as_feat = normalize_tr_text(s).lower() == normalize_tr_text(feat).lower()
                        # 2) Rakam içeriyor mu?
                        has_digit    = bool(re.search(r"\d", s))

                        # Eğer sadece başlık kopyalanmışsa (Karoq Premium bug)
                        # VE içinde rakam yoksa, bunu değer olarak kullanma
                        if not (same_as_feat and not has_digit):
                            val = s  # normal durum

                # 3) Hâlâ '—' ise, aynı satırdaki diğer trim kolonlarından sayısal bir
                #    değer bulup fallback olarak kullan (motor aynıysa iş görür)
                if val == "—":
                    for other_col, other_v in row_vals.items():
                        if other_col == sql_col:
                            continue
                        if other_v is None:
                            continue
                        s2 = str(other_v).strip()
                        if not s2:
                            continue
                        if normalize_tr_text(s2).lower() == normalize_tr_text(feat).lower():
                            continue
                        if re.search(r"\d", s2):  # içinde sayı olan ilk mantıklı değer
                            val = s2
                            break

                row_cells.append(self._safe_cell(val))

            lines.append("| " + " | ".join(row_cells) + " |")

        md = "\n".join(lines)

        try:
            first_lines = md.splitlines()[:3]
            self.logger.info("[SPEC-TBL RAW] FIRST 3:\n%s", "\n".join(first_lines))
        except Exception as _e:
            self.logger.error(f"[SPEC-TBL RAW] debug print failed: {_e}")

        return md








    def _nlg_equipment_compare(
        self,
        models: list[str],
        table_md: str,
        tone: str = "neutral",
        length: str = "short",
    ) -> str:
        """
        Donanım karşılaştırma tablosunu (Markdown) okuyup
        3–5 cümlelik showroom dili bir özet üretir.
        Örn: Kamiq ve Scala donanım açısından nerede benzer,
        nerede ayrışıyor, hangisi daha zengin gibi.
        """
        import os

        if not table_md or not models:
            return ""

        sys_msg = (
            "You are a Turkish automotive sales consultant working for Škoda Türkiye. "
            "Kullanıcıya iki veya daha fazla Škoda modelinin hem donanım hem de teknik "
            "veri karşılaştırmasını anlatan kısa ve etkileyici paragraflar yazarsın. "
            "Her zaman akıcı Türkçe kullan; 3–5 cümle yaz. "
            "Önce ortak güçlü noktaları, sonra bir modelin diğerine göre öne çıktığı "
            "donanım ve performans farklarını (güç, tork, hızlanma, menzil vb.) vurgula. "
            "Tablodan öğrendiğin bilgiler dışına çıkma, tahmin ekleme. "
            "Cevabında tabloya veya Markdown'a atıf yapma; sadece kullanıcıya hitap eden metin yaz. "
            "Son cümlenin sonunda, nazik bir soru ile bitir (örneğin: "
            "'Peki sizin kullanımınıza hangisi daha yakın görünüyor?' gibi)."
        )

        models_title = ", ".join(m.title() for m in models)

        user_content = (
            f"Modeller: {models_title}\n\n"
            "Aşağıda bu modellerin donanım karşılaştırma tablosu var (Markdown formatında):\n"
            f"{table_md}\n\n"
            "Bu tabloya dayanarak, modellerin nerede benzer olduğunu ve "
            "nerede ayrıştığını anlatan 3–5 cümlelik kısa bir showroom açıklaması yaz."
        )

        try:
            resp = self.client.chat.completions.create(
                model=os.getenv("NLG_MODEL", "gpt-4o"),
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.5,
                max_tokens=220,
            )
            text = (resp.choices[0].message.content or "").strip()
            return text
        except Exception as e:
            self.logger.error(f"[NLG-EQUIP-CMP] hata: {e}")
            return ""

    
    def _nlg_equipment_status(
        self,
        model_name: str,
        feature: str,
        trims: list[str],
        status_map: dict[str, str],
        tone: str = None,
        length: str = "short",
    ) -> str:
        """
        Tek bir donanım için (örn. cam tavan) trim bazlı S/O/Yok durumlarını
        LLM kullanmadan, deterministik Türkçe cümleye çevirir.

        Örnek giriş:
            trims = [
                'Octavia_Sportline_1_5_TSI_150_PS_DSG',
                'Octavia_Sportline_Combi_1_5_TSI_150_PS_DSG',
                'Octavia_RS_2_0_TSI_265_PS_DSG',
                'Octavia_RS_Combi_2_0_TSI_265_PS_DSG',
            ]
            status_map = {trim: 'S' / 'O' / '—', ...}

        Çıkış:
            "Octavia modelinde panoramik cam tavan, Sportline ve Sportline Combi ile
             RS ve RS Combi versiyonlarında standart olarak sunulmaktadır.
             Sizin için bu donanımın standart olması ne kadar önemli?"
        """

        if not trims or not status_map:
            return ""

        # -----------------------------
        # 1) Trim isimlerini grupla
        # -----------------------------
        def agg_status(old: str | None, new: str | None) -> str:
            # Kod önceliği: S > O > —
            order = {"S": 2, "O": 1, "—": 0, None: -1}
            if order.get(new, -1) > order.get(old, -1):
                return new or "—"
            return old or "—"

        grouped: dict[str, str] = {}

        for t in trims:
            code = status_map.get(t, "—")  # S/O/— bekleniyor
            low = (t or "").lower()

            # 1.a) Trim bazını bul (premium / prestige / sportline / rs / monte carlo ...)
            base_trim = None
            for canon in TRIM_VARIANTS.keys():
                for v in normalize_trim_str(canon):
                    v_low = v.lower()
                    if v_low and v_low in low:
                        base_trim = canon
                        break
                if base_trim:
                    break

            # Yedek: doğrudan isim içinde ara
            if not base_trim:
                for simple in ["premium", "elite", "prestige", "sportline", "monte carlo", "rs"]:
                    s1 = simple.replace(" ", "_")
                    if simple in low or s1 in low:
                        base_trim = simple
                        break

            if not base_trim:
                base_trim = t  # son çare: kolon adı

            label = base_trim.title()

            # 1.b) Gövde tipi: Combi olanları ayır
            if "combi" in low:
                label = f"{label} Combi"

            grouped[label] = agg_status(grouped.get(label), code)

        if not grouped:
            return ""

        # -----------------------------
        # 2) Statüye göre gruplandır
        # -----------------------------
        labels_by_status = {"S": [], "O": [], "—": []}
        for label, code in grouped.items():
            c = code if code in labels_by_status else "—"
            labels_by_status[c].append(label)

        def join_labels_tr(labels: list[str]) -> str:
            labels = [l for l in labels if l]
            if not labels:
                return ""
            if len(labels) == 1:
                return labels[0]
            if len(labels) == 2:
                return f"{labels[0]} ve {labels[1]}"
            return ", ".join(labels[:-1]) + f" ve {labels[-1]}"

        model_disp = model_name.title() if model_name else "Bu model"
        feat_disp = feature or "bu donanım"

        sentences = []

        # Standart olanlar
        if labels_by_status["S"]:
            s_labels = join_labels_tr(sorted(labels_by_status["S"]))
            sentences.append(
                f"{model_disp} modelinde {feat_disp}, {s_labels} versiyonlarında standart olarak sunulmaktadır."
            )

        # Opsiyonel olanlar
        if labels_by_status["O"]:
            o_labels = join_labels_tr(sorted(labels_by_status["O"]))
            sentences.append(
                f"Aynı donanım, {o_labels} versiyonlarında ise opsiyonel olarak tercih edilebilmektedir."
            )

        # Hiç sunulmayanlar
        if labels_by_status["—"]:
            n_labels = join_labels_tr(sorted(labels_by_status["—"]))
            sentences.append(
                f"{feat_disp}, {n_labels} versiyonlarında sunulmamaktadır."
            )

        # Kapanış sorusu
        sentences.append("Sizin için bu donanımın standart olması ne kadar önemli?")

        return " ".join(sentences)



    def _extract_models_spaced(self, text: str) -> set:
        """
        'k o d i a q' gibi harfleri ayrı yazımları yakalar.
        """
        import re
        t = normalize_tr_text(text or "").lower()
        models = ["fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"]
        found = set()
        for m in models:
            # k\s*o\s*d\s*i\s*a\s*q deseni
            pat = r"\b" + r"\s*".join(list(m)) + r"\b"
            if re.search(pat, t):
                found.add(m)
        return found

    def _extract_models_loose(self, text: str) -> set:
        """
        'ko diaq', 'k o d i a q', 'koi aq' gibi dağınık/ufak hatalı yazımları yakalamaya çalışır.
        - Harf dışını atar, token'ları 1-2 birleşik pencerelerle dener.
        - difflib eşleşmesi ≥ 0.72 ise model sayar.
        """
        import difflib, re
        t = normalize_tr_text(text or "").lower()
        tokens = re.findall(r"[a-zçğıöşü]+", t)
        if not tokens:
            return set()

        # 1) Tek token ve 2'li bitişik pencereleri dene (örn. "koi"+"aq" -> "koiaq")
        combos = set(tokens)
        combos.update("".join(tokens[i:i+2]) for i in range(len(tokens)-1))

        MODELS = ["fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"]
        found = set()
        for s in combos:
            for m in MODELS:
                if difflib.SequenceMatcher(None, s, m).ratio() >= 0.72:
                    found.add(m)
        return found

    def _has_loose_model_attempt(self, text: str) -> bool:
        """Mesaj yeni bir model yazmaya çalışıyor gibi mi? (gevşek tespit)"""
        return bool(self._extract_models_loose(text))

    def _best_value_from_row(self, cols, row, name_cols):
        """
        Aynı satırdaki 'değer' hücresini bulur.
        - Önce value/desc/unit/data gibi kolonlara bakar
        - Rakama/üniteye göre skorlar, en yüksek skorlu hücreyi döner
        """
        trim_pref = getattr(self, "CURRENT_TRIM_HINT", None)
        if trim_pref:
            # name_cols dışındaki kolonlar trim olabilir
            value_cols = [c for c in cols if c not in name_cols]
            col_name = self._match_trim_column_name(trim_pref, value_cols)
            if col_name and col_name in cols:
                idx = cols.index(col_name)
                cell = str(row[idx] or "").strip()
                if cell:
                    return cell

        import re
        units_re = re.compile(r"(nm|kw|ps|hp|km/?h|sn|g/km|l/100\s*km|kwh|dm3|cc)", re.I)
        value_like = re.compile(r"(deger|değer|value|val|content|desc|açıklama|aciklama|icerik|içerik|spec|specval|spec_value|unit|birim|data|veri|number|num)", re.I)

        # 1) Önce 'değer-benzeri' kolonları değerlendir
        candidates = []
        for i, c in enumerate(cols):
            if c in name_cols:
                continue
            cell = str(row[i] or "").strip()
            if not cell:
                continue
            score = 0
            if value_like.search(c):      score += 2
            if re.search(r"\d", cell):    score += 3
            if units_re.search(cell.replace(" ", "")): score += 3
            score += min(2, len(re.findall(r"\d", cell)))
            candidates.append((score, cell))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        # 2) Olmadıysa tüm kolonlar içinde rakam/ünite arayarak dene
        fallback = []
        for i, c in enumerate(cols):
            if c in name_cols:
                continue
            cell = str(row[i] or "").strip()
            if not cell:
                continue
            score = (3 if re.search(r"\d", cell) else 0) + (3 if units_re.search(cell.replace(" ", "")) else 0)
            if score:
                fallback.append((score, cell))
        if fallback:
            fallback.sort(key=lambda x: x[0], reverse=True)
            return fallback[0][1]

        
        num_unit = re.compile(r"\d")
        unit_pat = re.compile(r"(nm|kw|ps|hp|km/?h|sn|g/km|l/100\s*km|kwh|dm3|cc)", re.I)
        for i, c in enumerate(cols):
            if c in name_cols:
                continue
            cell = str(row[i] or "").strip()
            if num_unit.search(cell) and unit_pat.search(cell.replace(" ", "")):
                return cell
        return ""

    def _semantic_match_column(self, user_query: str, columns: list[str]) -> str | None:
        """
        Kullanıcının yazdığı doğal ifadeyi (ör. 'torku', 'gücü', 'menzili')
        SQL tablosundaki en uygun kolonla eşleştirir.
        OpenAI Embedding (text-embedding-3-small) kullanır.
        """
        from openai import OpenAI
        import numpy as np
        import os, re

        from modules.trace_debug import traced_openai_client
        client = traced_openai_client(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))
        model = "text-embedding-3-small"

        # --- 1️⃣ Normalize ve sadeleştir ---
        q = re.sub(r"[^0-9a-zçğıöşü\s]", " ", user_query.lower()).strip()
        if not q or not columns:
            return None

        try:
            # --- 2️⃣ Kullanıcı sorgusunun embedding'i ---
            q_emb = np.array(client.embeddings.create(model=model, input=q).data[0].embedding)

            # --- 3️⃣ Kolon embedding'leri ---
            sims = []
            for col in columns:
                col_norm = re.sub(r"[^0-9a-zçğıöşü\s]", " ", col.lower()).strip()
                c_emb = np.array(client.embeddings.create(model=model, input=col_norm).data[0].embedding)
                sim = float(np.dot(q_emb, c_emb) / (np.linalg.norm(q_emb) * np.linalg.norm(c_emb)))
                sims.append((sim, col))

            # --- 4️⃣ En benzer kolon seçimi ---
            sims.sort(reverse=True)
            best_sim, best_col = sims[0]
            if best_sim > 0.75:
                self.logger.info(f"[EMB-MATCH] '{user_query}' → '{best_col}' (sim={best_sim:.2f})")
                return best_col
        except Exception as e:
            self.logger.error(f"[EMB-MATCH] hata: {e}")
        return None

    
    def _emit_spec_sentence(self, model: str | None, title: str, val: str) -> bytes:
        """
        SQL'den bulunan tek bir değer için:
        - Eğer içinde sayı varsa → teknik veri gibi davran (tork, güç, 0-100 vb.)
        - Eğer sayı yoksa → donanım / var-yok / standart-opsiyonel bilgisi gibi davran.
        """
        import re

        mdl = (model or "").title()
        txt_val = (val or "").strip()

        # 📌 1) Sayı YOKSA: donanım bilgisi gibi yorumla
        if not re.search(r"\d", txt_val):
            # Durumu normalize et (S = Standart, O = Opsiyonel, — = Yok)
            status = self._normalize_equipment_status(txt_val)

            if status == "S":
                msg = f"{mdl} modelinde bu özellik standart olarak sunuluyor."
            elif status == "O":
                msg = f"{mdl} modelinde bu özellik opsiyonel (ek paket/opsiyon) olarak sunuluyor."
            elif status == "—":
                msg = f"{mdl} modelinde bu özellik bulunmuyor."
            else:
                # Standart/opsiyonel/yok dışı serbest metinler için
                msg = f"{mdl} için bu özellik veritabanında '{txt_val}' olarak kayıtlı."

            return msg.encode("utf-8")

        # 📌 2) Sayı VARSA: eski teknik-veri davranışı
        nlg = self._nlg_via_openai(
            model_name=(model or ""),
            metric=title,
            value=txt_val,
            tone=os.getenv("NLG_TONE","neutral"),
            length=os.getenv("NLG_LENGTH","short"),
        )
        if nlg:
            return nlg.encode("utf-8")

        # Güvenli yedek cümle
        return f"{mdl} için {title.lower()}, {txt_val}.".encode("utf-8")

    def _nlg_via_openai(self, *, model_name: str, metric: str, value: str,
                    tone: str = "neutral", length: str = "short") -> str:
        """
        SQL'den gelen değeri OpenAI ile 1 paragraf doğal Türkçe cümleye çevirir.
        Rakam/ölçüleri aynen korumaya zorlar. Hata olursa "" döner.
        """
        import json, re, os

        def _sig_tokens(s: str):
            import re
            s = s or ""
            # sayıları topla (1,978 / 2.033 / 85x → 1978, 2033, 85)
            nums = re.findall(r"\d+(?:[.,]\d+)?", s)
            nums_norm = {"".join(ch for ch in n if ch.isdigit()) for n in nums if n}
            # temel ünite/desenleri yakala
            units = set()
            low = s.lower()
            for u in ["kg","nm","kw","ps","hp","km/h","dm3","sn","l/100 km","wltp","%","kwh"]:
                if u in low.replace(" ", ""):
                    units.add(u.replace(" ", ""))
            return nums_norm, units

        def _sig_ok(value: str, text: str) -> bool:
            v_nums, v_units = _sig_tokens(value)
            t_nums, t_units = _sig_tokens(text)
            # Değer tarafındaki tüm sayılar metinde geçiyorsa ve (varsa) birimler de korunmuşsa ok
            if v_nums and not v_nums.issubset(t_nums):
                return False
            if v_units and not v_units.issubset(t_units):
                return False
            return True

        sys_msg = (
            "You are a Turkish automotive sales consultant working for Škoda Türkiye. "
            "You write rich, emotional, and persuasive paragraphs that sound like a human consultant "
            "talking to a customer in a showroom. "
            "Always respond in fluent Turkish, using long, descriptive sentences (3–5 sentences total). "
            "Blend technical facts with sensory and emotional details — how the car feels, what it says about lifestyle, "
            "and how it makes driving enjoyable. "
            "Include all numbers and units EXACTLY as provided (never change them). "
            "End with one short, friendly question that naturally invites engagement, "
            "like 'Denemek ister misiniz?' or 'Sizce bu size yakışmaz mı?'. "
            "Example style: "
            "‘Octavia, 8,5 saniyelik 0-100 km/s hızlanmasıyla sadece performans değil, konforla birleşen çevikliğini de hissettiriyor. "
            "Modern çizgileri ve sessiz motor yapısıyla her yolculuk keyifli hale geliyor. "
            "Peki siz bu dinamizmi direksiyon başında denemek ister misiniz?’"
        )
        user_payload = {
            "lang": "tr",
            "tone": tone,            # neutral|persuasive|sporty|formal
            "length": length,        # short|medium|long
            "model": model_name,
            "metric": metric,
            "value": value,
        }

        try:
            from modules.trace_debug import span

            payload_len = 0
            try:
                payload_len = len(json.dumps(user_payload, ensure_ascii=False))
            except Exception:
                payload_len = len(str(user_payload))

            with span("LLM", "chat.completions.create",
                    model=os.getenv("NLG_MODEL", "gpt-4o"),
                    in_chars=payload_len):
                resp = self.client.chat.completions.create(
                    model=os.getenv("NLG_MODEL", "gpt-4o"),
                    messages=[
                        {"role":"system","content": sys_msg},
                        {"role":"user","content": json.dumps(user_payload, ensure_ascii=False)}
                    ],
                    temperature=0.4,
                    max_tokens=220,
                )

            text = (resp.choices[0].message.content or "").strip()
            # Sayısal koruma: value’daki rakam/ölçü imzası çıktıda da olmalı
            if _sig_ok(value, text):
                return text
            return ""  # imza tutmadıysa güvenlik gereği boş dön
        except Exception:
            return ""

    def _has_fulltext(self, conn, table_name: str, column_name: str) -> bool:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT 1
                FROM sys.fulltext_indexes fi
                JOIN sys.objects o ON o.object_id = fi.object_id
                JOIN sys.fulltext_index_columns fic ON fic.object_id = fi.object_id
                JOIN sys.columns c ON c.object_id = fic.object_id AND c.column_id = fic.column_id
                WHERE o.name = ? AND c.name = ?
            """, (table_name, column_name))
            return cur.fetchone() is not None
        except Exception:
            return False

    def _sanitize_for_fulltext(self, s: str) -> str:
        # CONTAINS güvenliği için harf/rakam/boşluk dışını at
        import re
        return re.sub(r"[^0-9a-zçğıöşü\s]", " ", (s or "").lower()).strip()

    def _make_where_for_keywords(self, feat_col: str, kws: list[str], use_fulltext: bool, collate: str):
        """
        Full-Text açıksa: CONTAINS(FORMSOF(THESAURUS,...)), değilse: LIKE %...%
        Güvenli olanları FT'ye, kalanları LIKE'a yollar.
        """
        import re
        where_parts, params = [], []
        if use_fulltext:
            safe_terms = []
            like_terms = []
            for kw in kws:
                k = self._sanitize_for_fulltext(kw)
                # Çok kısa/boş veya sadece sayı ise LIKE'a bırak
                if len(k) < 2 or re.fullmatch(r"\d+", k):
                    like_terms.append(kw)
                else:
                    safe_terms.append(k)
            # FT: her güvenli terim için FORMSOF(THESAURUS, "...")
            for st in safe_terms:
                where_parts.append(f"CONTAINS([{feat_col}], 'FORMSOF(THESAURUS, \"{st}\")')")
            # LIKE fallback
            for kw in like_terms:
                where_parts.append(f"LOWER(CONVERT(NVARCHAR(4000),[{feat_col}])) COLLATE {collate} LIKE ?")
                params.append(f"%{kw}%")
        else:
            for kw in kws:
                where_parts.append(f"LOWER(CONVERT(NVARCHAR(4000),[{feat_col}])) COLLATE {collate} LIKE ?")
                params.append(f"%{kw}%")
        if not where_parts:
            where_parts.append("1=0")
        return " OR ".join(where_parts), params

    def _gen_variants(self, s: str) -> list[str]:
        return _gen_variants(s)

    def _forced_match_rules(self, q_norm: str):
        """Soruya göre zorunlu POS/NEG eşleşme regex’lerini döndürür."""
        def rx(s): return re.compile(s, re.I)

        # rule tetik anahtarları (soruda geçerse kural aktif)
        rules = []

        # CAM TAVAN / SUNROOF
        if re.search(r"\bcam\s*tavan\b|\bsun\s*roof\b|\bsunroof\b|\bpanoramik\s*cam\s*tavan\b|\ba[cç]ılır\s*cam\s*tavan\b", q_norm):
            rules.append((
                # POS: şu ifadelerden biri şart
                [rx(r"cam\s*tavan"), rx(r"sun\s*roof|sunroof"),
                rx(r"panoramik\s*cam\s*tavan"), rx(r"a[cç]ılır\s*cam\s*tavan")],
                # NEG: geçerse elenir
                [rx(r"tavan\s*ray")]
            ))

        # MATRIX LED FAR
        if re.search(r"\bmatrix\b|\bdla\b", q_norm):
            rules.append((
                [
                    # “LED Matrix”, “Full LED Matrix”, “Matrix LED”, DLA…
                    rx(r"(?:full\s*)?led\s*matrix"),
                    rx(r"matrix\s*led"),
                    rx(r"\bdla\b"),
                    rx(r"dynamic\s*light\s*assist"),
                    # güvenli varyant: 'matrix' ve 'far' aynı satırda
                    rx(r"matrix.*far|far.*matrix"),
                ],
                # arka aydınlatma/Top LED gibi alakasızları dışla
                [rx(r"top\s*led\s*arka"), rx(r"arka\s*ayd[ıi]nlatma")]
            ))

        # DCC / DCC PRO
        if re.search(r"\bdcc\b", q_norm) or "dcc pro" in q_norm:
            rules.append((
                [rx(r"\bdcc(\s*pro)?\b"), rx(r"dynamic\s*chassis\s*control")],
                []
            ))

        # Kör nokta (örnek)
        if re.search(r"k[öo]r\s*nokta|blind\s*spot", q_norm):
            rules.append((
                [rx(r"k[öo]r\s*nokta"), rx(r"blind\s*spot")],
                []
            ))
        # PARK ASİSTANI (otomatik park)
        if re.search(r"\bpark\s*asistan[ıi]\b|\botomatik\s*park\b|park\s*assist", q_norm):
            rules.append((
                [rx(r"park\s*asistan[ıi]"), rx(r"park\s*assist"), rx(r"otomatik\s*park")],
                [rx(r"far\s*asistan[ıi]"), rx(r"\bhba\b")]  # uzun/dinamik farı dışla
            ))


        # Kural yoksa boş döndür
        return rules

    def _load_imported_table_all(self, model_code: str) -> list[dict]:
        """
        Imported_* tablo(lar)ından ilgili modelin TÜM satırlarını RAM'e alır.
        Dönüş: [{'ozellik': str, 'ePrestige': str|None, 'deger': str|None}, ...]
        """
        key = (model_code or "").upper().strip()
        if not key:
            return []
        if key in self._imported_cache:
            return self._imported_cache[key]

        rows_out = []
        coll = os.getenv("SQL_CI_COLLATE", "Turkish_100_CI_AI")

        with self._sql_conn() as conn:
            cur = conn.cursor()
            # ELROQ için: Imported_KODA_ELROQ_MY_% gibi isimler seti
            cur.execute("""
                SELECT name FROM sys.tables
                WHERE name LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\' OR name LIKE ?
                OR name LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\'
                ORDER BY name DESC
            """, (f"Imported\\_KODA\\_{key}\\_MY\\_%", f"Imported\\_{key}%", f"Imported\\_{key.title()}%",
          f"TechSpecs\\_KODA\\_{key}\\_%", f"KODA\\_{key}\\_%"))
            tables = [r[0] for r in cur.fetchall()]

            for t in tables:
                try:
                    cur.execute(f"SELECT TOP 0 * FROM [{t}]")
                except Exception:
                    continue
                cols = [c[0] for c in cur.description] if cur.description else []
                # Kolon isimlerini tolerant seç
                prest_col = next((c for c in cols if re.search(r"^(ePrestige|Prestige|StdOps|Status)$", c, re.I)), None)
                name_col = next((c for c in cols if re.search(
                    r"^(Ozellik|Özellik|Donanim|Donanım|Name|Title|Attribute|SpecName|FeatureName|Description)$", c, re.I)), None)
                val_col = next((c for c in cols if re.search(
                    r"^(Deger|Değer|Value|Content|Description|Icerik|İçerik|SpecValue|Data|Veri)$", c, re.I)), None)
                if not name_col and not val_col:
                    continue

                # Tüm satırları çek (gerekirse sayıyı sınırlayabilirsin)
                cur.execute(f"SELECT {', '.join([c for c in [name_col, prest_col, val_col] if c])} FROM [{t}] WITH (NOLOCK)")
                for r in cur.fetchall():
                    d = {}
                    i = 0
                    if name_col:
                        d["ozellik"] = (r[i] or "").strip(); i += 1
                    else:
                        d["ozellik"] = ""
                    if prest_col:
                        d["ePrestige"] = (r[i] or "").strip(); i += 1
                    else:
                        d["ePrestige"] = None
                    if val_col:
                        d["deger"] = (r[i] or "").strip()
                    else:
                        d["deger"] = None

                    # Boş şeritleri (---) eleyelim
                    norm = normalize_tr_text(d["ozellik"]).lower()
                    if norm and not re.fullmatch(r"[-–—\.]*", norm):
                        rows_out.append(d)

        self._imported_cache[key] = rows_out
        return rows_out


    def _query_all_features_from_imported(self, model_code: str, user_text: str, topn:int=1) -> list[dict]:
        """
        Imported_* RAM önbelleğinden arama yapar; SADECE en alakalı satır(lar)ı döndürür.
        Dönüş: [{'ozellik':..., 'durum': 'Standart|Opsiyonel|Var|—', 'deger': '...','_score':float}, ...]
        EŞLEŞME YOKSA -> [] döner.
        """
        data = self._load_imported_table_all(model_code)
        if not data:
            return []

        def nrm(s): 
            return re.sub(r"\s+", " ", normalize_tr_text(s or "").lower()).strip()

        q_norm = nrm(user_text)

        # --- YENİ: token + lemma + bigram seti ---
        raw_tokens = [w for w in re.findall(r"[0-9a-zçğıöşü]+", q_norm) if len(w) >= 2]
        lemma_tokens = lemmatize_tr_tokens(raw_tokens)

        # Tekrarsız birleşik token listesi
        tokens = list(dict.fromkeys(raw_tokens + lemma_tokens))

        # Bigrams (lemma dahil)
        bigrams = [" ".join([tokens[i], tokens[i+1]]) for i in range(len(tokens)-1)]

        terms = set(tokens + bigrams)
        self.logger.info(
            "[LEMMA-DEBUG] q='%s' | raw=%s | lemmas=%s | terms=%s",
            user_text, raw_tokens, lemma_tokens, list(terms)
        )

        if hasattr(self, "_to_english_terms"):
            for t in (self._to_english_terms(user_text) or []):
                tt = nrm(t)
                if tt: terms.add(tt)
        for abbr in ["dcc","dcc pro","acc","isa","hud","rcta","drl","udc"]:
            if re.search(rf"\b{abbr}\b", q_norm):
                terms.add(abbr)

        # Sık gelen ama genelde "genel" olan başlıkları zayıflat (alakasız kaçışı azaltır)
        GENERIC_WEAK = {
            "ağırlık","agırlık","güç aktarımı","guc aktarimi","rejeneratif frenleme",
            "arka cam sileceği","ambiyans aydınlatma","karartılmış arka camlar"
        }

        SCORE_MIN = 3 if len(tokens) >= 2 else 2

        patt_exact = [re.compile(rf"(?<!\w){re.escape(t)}(?!\w)") for t in terms if " " not in t]
        patt_phrase = [re.compile(re.escape(t)) for t in terms if " " in t]

        hits = []
        for row in data:
            oz_full = row.get("ozellik") or ""
            # Eşleştirme için parantez dışı kısım
            oz = nrm(strip_parens_for_match(oz_full))
            dg = nrm(row.get("deger"))
            if not oz and not dg:
                continue


            score = 0.0

            # tam ifade (bigrams/fraseler) → +3
            for p in patt_phrase:
                if p.search(oz):
                    score += 3
                elif dg and p.search(dg):
                    score += 1.5

            # tam kelime sınırı → +2, kısmi içerme → +1
            for p in patt_exact:
                if p.search(oz):
                    score += 2
                elif dg and p.search(dg):
                    score += 1

            # kaba kısmi: soru metninin parçası özellikte geçiyorsa
            for t in terms:
                if t in oz:
                    score += 1
                        # --- YENİ: HuggingFace semantik benzerlik (varsa) ---
            try:
                q_vec = embed_semantic_local(user_text)
                oz_vec = embed_semantic_local(row.get("ozellik") or "")
                if q_vec is not None and oz_vec is not None:
                    # normalize_embeddings=True kullandığımız için dot = cosine
                    sem_sim = float(np.dot(q_vec, oz_vec))
                    # 0.0–1.0 aralığını 0–4 puana map et
                    if sem_sim > 0:
                        score += sem_sim * 4.0
                        self.logger.info(f"[HF-SEM] '{user_text}' ~ '{row.get('ozellik')}' sim={sem_sim:.3f}")

            except Exception:
                # HF modeli yoksa ya da hata verirse sessizce atla
                pass

            # “genel” başlıkları zayıflat
            if any(g in oz for g in GENERIC_WEAK):
                score -= 1.0

            if score <= 0:
                continue

            # DURUM üretimi
            raw_p = nrm(row.get("ePrestige") or "")
            if raw_p in {"standart","standard","std","s"}:
                durum = "Standart"
            elif raw_p in {"ops","opsiyonel","optional","o"}:
                durum = "Opsiyonel"
            else:
                durum = "Var" if row.get("deger") else "—"

            hits.append({
                "ozellik": (row.get("ozellik") or "").strip(),  # full text ekranda gözüksün
                "durum": durum,
                "deger": (row.get("deger") or "").strip(),
                "_score": score
            })

        if not hits:
            return []

        # ZORUNLU KURALLAR: soru belirli bir özelliği net istiyorsa
        rules = self._forced_match_rules(q_norm)
        if rules:
            def ok_by_rules(oz_low: str) -> bool:
                for pos_list, neg_list in rules:
                    if any(n.search(oz_low) for n in neg_list):
                        return False
                    if not any(p.search(oz_low) for p in pos_list):
                        return False
                return True

            filtered = [h for h in hits if ok_by_rules(nrm(h["ozellik"]))]
            if filtered:
                hits = filtered
            else:
                # hiçbiri POS/NEG kurallara uymuyorsa "eşleşme yok" say
                return []

        # --- BURADAN SONRASI: SERT EŞİK + TOKEN OVERLAP KONTROLÜ ---

        # 1) skor’a göre sırala
        hits.sort(key=lambda h: (-h["_score"], len(h["ozellik"])))
        best = hits[0]

        # 2) minimum skor eşiği
        HARD_MIN = 3.0
        if best["_score"] < HARD_MIN:
            self.logger.info(
                f"[EQUIP] best score below HARD_MIN: {best['_score']:.2f} < {HARD_MIN} "
                f"for query='{user_text}', best='{best['ozellik']}'"
            )
            return []

        # 3) soru token’ları kümesi
        q_tokens_set = set(tokens)

        # 4) özelliğin token’ları
        import re as _re
        oz_tokens = set(_re.findall(r"[0-9a-zçğıöşü]+", nrm(best["ozellik"])))

        # 4.a ÖZEL KURAL: soru "koltuk" içerip özellik "bagaj" içeriyorsa asla eşleştirme
        if "koltuk" in q_tokens_set and "bagaj" in oz_tokens:
            self.logger.info(
                f"[EQUIP] seat vs trunk clash -> ignore row '{best['ozellik']}' "
                f"for query='{user_text}'"
            )
            return []

        # 5) çok genel kelimeleri overlap’ten çıkar
        GENERIC_OVERLAP_STOP = {"elektrikli", "otomatik", "sistem", "sistemi"}

        strong_overlap = (oz_tokens & q_tokens_set) - GENERIC_OVERLAP_STOP

        # 6) hiç anlamlı ortak kelime yoksa eşleşmeyi yok say
        if not strong_overlap:
            self.logger.info(
                f"[EQUIP] Weak overlap, ignoring best hit '{best['ozellik']}' "
                f"for query='{user_text}' (q_tokens={q_tokens_set}, oz_tokens={oz_tokens})"
            )
            return []
                # 6.b Çok kelimeli ifadelerde daha sıkı eşleşme şartı
        # Soruya ait "anlamlı" kelimeleri çıkart (model adları, yardımcı kelimeler hariç)
        CONTENT_STOP = {
            "var", "yok", "mi", "mı", "mu", "mü",
            "ne", "kadar", "nedir", "olan", "ile", "ve",
            "opsiyonel", "standart", "donanım", "donanim", "özellik", "ozellik"
        }
        MODEL_TOKENS = {"fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"}

        content_tokens = {
            t for t in q_tokens_set
            if t not in CONTENT_STOP and t not in MODEL_TOKENS
        }

        # Eğer cümlede en az 2 anlamlı kelime varsa, satırda da en az 2 tanesi bulunmalı.
        if len(content_tokens) >= 2 and len(strong_overlap) < 2:
            self.logger.info(
                f"[EQUIP] Overlap too weak for multi-word query; "
                f"ignoring '{best['ozellik']}' for query='{user_text}' "
                f"(content_tokens={content_tokens}, overlap={strong_overlap})"
            )
            return []


        self.logger.info(
            f"[EQUIP] ACCEPT '{best['ozellik']}' for '{user_text}' "
            f"(score={best['_score']:.2f}, overlap={strong_overlap})"
        )

        # En alakalı 1 satırı döndür
        return hits[:1]

    def _render_feature_hits_compact(self, rows: list[dict]) -> str:
        if not rows:
            return ""
        if len(rows) == 1:
            r = rows[0]
            val = f" — {r['deger']}" if r["deger"] else ""
            return f"**{r['ozellik']}**: {r['durum']}{val}"
        # 2–3 satır gerekiyorsa min tablo:
        out = ["| Özellik | Durum | Değer |", "|---|---|---|"]
        for r in rows:
            out.append(f"| {r['ozellik']} | {r['durum']} | {r['deger'] or '—'} |")
        return "\n".join(out)



    def _render_feature_hits_table(self, hits: list[dict]) -> str:
        if not hits:
            return ""
        lines = ["| Özellik | Durum | Değer |", "|---|---|---|"]
        for h in hits:
            lines.append(f"| {h['ozellik']} | {h['durum']} | {h['deger'] or '—'} |")
        return "\n".join(lines)

    def _feature_lookup_any(self, model: str, user_text: str) -> tuple[list[str], dict, str | None]:
        """
        Donanım (EquipmentList) araması için ortak giriş noktası.
        1) HF embedding ile semantik eşleşme (varsa)
        2) GPT ile üretilmiş eş anlamlı arama kelimeleri
        3) QUICK_HINTS + TR→EN ile klasik LIKE fallback

        Dönüş: (trims, status_map, feature_title)
        """
        import re
        if not model or not user_text:
            return [], {}, None

        # =========================================
        # 0) HF SEMANTIC MATCH (synonym'siz, saf anlam)
        # =========================================
        try:
            sem_hits = self._semantic_feature_match_equipment(model, user_text, topn=3)
        except Exception as e:
            self.logger.error(f"[EQUIP-SEM] hata: {e}")
            sem_hits = []

        if sem_hits:
            best = sem_hits[0]
            sim  = best["score"]
            row  = best["row"]
            oz   = best["ozellik"]
            trim_cols = best["trim_cols"] or []

            trust_semantic = False
            # ✅ NEW: Zorunlu kural filtresi (cam tavan vs tavan rayı gibi kaçışları engeller)
            passed_rules = True
            try:
                q_norm = normalize_tr_text(user_text).lower()
                rules = self._forced_match_rules(q_norm)   # senin fonksiyonun zaten var
                if rules:
                    oz_low = re.sub(r"\s+", " ", normalize_tr_text(oz)).lower()
                    for pos_list, neg_list in rules:
                        # NEG geçiyorsa veto
                        if any(n.search(oz_low) for n in neg_list):
                            passed_rules = False
                            break
                        # POS şartı varsa ve hiçbiri yoksa veto
                        if pos_list and not any(p.search(oz_low) for p in pos_list):
                            passed_rules = False
                            break
            except Exception:
                passed_rules = True  # hata olursa sistemi kilitleme

            # 1) Çok yüksek benzerlikte (≥0.80) token overlap arama → tam otomatik eş anlam
            if sim >= 0.80 and passed_rules:
                trust_semantic = True
            elif sim >= 0.70 and passed_rules and self._is_safe_equipment_match(user_text, oz):
                trust_semantic = True

            else:
                self.logger.info(
                    "[EQUIP-SEM] REJECT semantic hit '%s' (sim=%.3f) for query='%s'",
                    oz, sim, user_text
                )

            if trust_semantic:
                trims = []
                status_map = {}
                for col in trim_cols:
                    raw = row.get(col)
                    trims.append(col)
                    status_map[col] = self._normalize_equipment_status(raw)

                return trims, status_map, oz

        # =========================================
        # 1) GPT ile eş anlamlı arama kelimeleri üret
        # =========================================
        needles_set = set()

        try:
            gpt_kws = self._expand_feature_keywords_via_openai(user_text, model_slug=model)
        except Exception as e:
            self.logger.error(f"[EQUIP-GPT] expand error: {e}")
            gpt_kws = []

        for k in gpt_kws:
            nk = self._norm_alias(k)
            if len(nk) >= 2:
                needles_set.add(nk)

        # =========================================
        # 2) QUICK_HINTS + TR→EN fallback ile genişlet
        # =========================================
        q = self._norm_alias(user_text)

        QUICK_HINTS = {
            "park asistan": [
                "park asistan", "park assist", "otomatik park"
            ],
            "cam tavan": [
                "cam tavan", "panoramik cam tavan", "açılır cam tavan",
                "glass roof"
            ],
            "matrix": [
                "matrix", "matrix led", "dla", "dynamic light assist"
            ],
            "geri görüş": [
                "geri görüş kamera", "rear view camera", "reverse camera"
            ],
            "360": [
                "360 kamera", "area view", "top view camera"
            ],
        }

        for k, lst in QUICK_HINTS.items():
            if k in q:
                for s in lst:
                    nk = self._norm_alias(s)
                    if len(nk) >= 2:
                        needles_set.add(nk)

        # TR→EN map (sunroof vb.) — mevcut helper
        for s in (self._to_english_terms(user_text) or []):
            nk = self._norm_alias(s)
            if len(nk) >= 2:
                needles_set.add(nk)

        # Orijinal cümleden token/bigram
        toks = [t for t in re.findall(r"[0-9a-zçğıöşü]+", q) if len(t) >= 2]
        bigrams = [" ".join([toks[i], toks[i+1]]) for i in range(len(toks)-1)]
        for s in toks + bigrams:
            nk = self._norm_alias(s)
            if len(nk) >= 2:
                needles_set.add(nk)

        needles = list(dict.fromkeys(needles_set))

        if not needles:
            self.logger.info(f"[EQUIP] no needles generated for '{user_text}' (model={model})")
            return [], {}, None

        # =========================================
        # 3) EquipmentList LIKE sorgusu
        # =========================================
        trims, status_map, feature_title = self._feature_status_from_equipment(
            model,
            feature_keywords=needles,
            original_query=user_text,   # 👈 GPT için ham soru
        )
        return trims, status_map, feature_title



    def seed_feature_catalog_from_equipment(self):
        conn = self._sql_conn(); cur = conn.cursor()
        try:
            cur.execute("SELECT name FROM sys.tables WHERE name LIKE 'EquipmentList\\_KODA\\_%' ESCAPE '\\'")
            tables = [r[0] for r in cur.fetchall()]
            cand_cols = ["Equipment","Donanim","Donanım","Ozellik","Özellik","Name","Title","Attribute","Feature"]

            seen = set()
            for t in tables:
                # özellik kolonu
                cur.execute("""
                SELECT TOP 1 c.name
                FROM sys.columns c
                WHERE c.object_id = OBJECT_ID(?) AND c.name IN ({})
                """.format(",".join(["?"]*len(cand_cols))), [t] + cand_cols)
                row = cur.fetchone()
                if not row: 
                    continue
                feat_col = row[0]
                cur.execute(f"SELECT DISTINCT CAST([{feat_col}] AS NVARCHAR(200)) FROM {t} WHERE [{feat_col}] IS NOT NULL")
                for (val,) in cur.fetchall():
                    raw = (val or "").strip()
                    if not raw: 
                        continue
                    key = raw  # kanonik gösterimi şimdilik ham ad
                    if key in seen: 
                        continue
                    seen.add(key)

                    # 1) katalog'a ekle (yoksa)
                    cur.execute("IF NOT EXISTS(SELECT 1 FROM dbo.FeatureCatalog WHERE feature_key = ?) INSERT INTO dbo.FeatureCatalog(feature_key,display_name) VALUES(?,?)",
                                (key, key, raw))

                    # 2) alias çeşitleri
                    variants = _gen_variants(raw)
                    for a in variants:
                        cur.execute("IF NOT EXISTS(SELECT 1 FROM dbo.FeatureAlias WHERE alias_norm = ?) INSERT INTO dbo.FeatureAlias(alias_norm,feature_key,lang,source_note) VALUES(?,?,?,?)",
                                    (a, key, None, 'harvest'))
            conn.commit()
        finally:
            cur.close(); conn.close()

    # --- Basit TR→EN/EN→TR mini sözlük (ihtiyaca göre genişletilebilir) ---
    # TR→EN sözlük: ihtiyaca göre genişlet
    TR_EN_MAP = {
        "dcc pro": ["dcc pro", "dynamic chassis control pro"],
        "dcc": ["dcc", "dynamic chassis control", "adaptive suspension"],
        "adaptif süspansiyon": ["adaptive suspension", "dcc"],
        "panoramik cam tavan": ["panoramic roof", "glass roof"],
        "cam tavan": ["sunroof", "glass roof", "opening roof"],
        "açılır cam tavan": ["sunroof", "opening roof"],
        "geri görüş kamerası": ["rear view camera", "reverse camera"],
        "360 kamera": ["360 camera", "area view", "top view camera"],
        "kör nokta": ["blind spot", "blind spot monitor"],
        "arka çapraz trafik": ["rear cross traffic", "rcta"],
        "şerit takip": ["lane assist", "lane keeping"],
        "şerit ortalama": ["lane centering"],
        "ön bölge asistanı": ["front assist", "aeb", "automatic emergency braking"],
        "ambiyans aydınlatma": ["ambient light", "ambient lighting"],
        "kablosuz şarj": ["wireless charging", "qi charging"],
        "matrix led": ["matrix led", "dynamic light assist", "dla"],
        "uzun far asistanı": ["high beam assist", "hba"],
        "elektrikli bagaj kapağı": ["power tailgate", "power liftgate"],
    }

    @staticmethod
    def _norm_alias(s: str) -> str:
        import re
        return re.sub(r"\s+", " ", normalize_tr_text(s or "").lower()).strip()

    @staticmethod
    def _to_english_terms(text: str) -> list[str]:
        base = ChatbotAPI._norm_alias(text)
        terms = set()
        for tr_key, en_list in ChatbotAPI.TR_EN_MAP.items():
            if tr_key in base:
                for en in en_list:
                    t = ChatbotAPI._norm_alias(en)
                    terms.add(t); terms.add(t.replace(" ", ""))
        # yaygın kısaltmalar
        for abbr in ["dcc","acc","isa","hud","rcta","drl"]:
            if re.search(rf"\b{abbr}\b", base):
                terms.add(abbr)
        # cam tavan birleşik varyant
        if "cam tavan" in base or "camtavan" in base.replace(" ",""):
            terms.update(["sunroof","glass roof","glassroof"])
        return [t for t in terms if len(t) >= 2]

    def _feature_exists_tr_en(self, model_slug: str, user_text: str) -> bool:
        """
        Imported_* (ve benzeri) tablolarda Özellik/Değer alanlarında
        TR+EN anahtar kelime arar. Bulursa True döner.
        """
        import contextlib, re
        if not model_slug or not user_text:
            return False

        needles = set()
        q = self._norm_alias(user_text)
        needles |= {q, q.replace(" ", "")}
        for w in q.split():
            needles.add(w); needles.add(w.replace(" ",""))
        for e in self._to_english_terms(user_text):
            needles.add(e); needles.add(e.replace(" ",""))
        needles = [n for n in needles if len(n) >= 2]

        m = (model_slug or "").strip().upper()
        coll = os.getenv("SQL_CI_COLLATE", "Turkish_100_CI_AI")

        conn = self._sql_conn(); cur = conn.cursor()
        try:
            # İlgili Imported_* tablolarını topla
            pats = [f"Imported\\_KODA\\_{m}\\_MY\\_%", f"Imported\\_{m}%", f"Imported\\_{m.capitalize()}%"]
            tables = []
            for p in pats:
                cur.execute("SELECT name FROM sys.tables WHERE name LIKE ? ESCAPE '\\' ORDER BY name DESC", (p,))
                tables += [r[0] for r in cur.fetchall()]

            for t in dict.fromkeys(tables):
                try:
                    cur.execute(f"SELECT TOP 0 * FROM [{t}]")
                except Exception:
                    continue
                cols = [c[0] for c in cur.description]
                name_cols = [c for c in cols if re.search(r"(ozellik|özellik|name|title|attribute)", c, re.I)]
                val_cols  = [c for c in cols if re.search(
                    r"(deger|değer|value|val|content|desc|açıklama|aciklama|icerik|içerik|spec|specval|spec_value|unit|birim|data|veri|number|num)",
                    c, re.I)]

                if not name_cols and not val_cols:
                    continue

                where, params = [], []
                for nc in (name_cols + val_cols):
                    for n in needles:
                        where.append(f"LOWER(CONVERT(NVARCHAR(4000),[{nc}])) COLLATE {coll} LIKE ?")
                        params.append(f"%{n}%")
                if not where:
                    continue

                sql = f"SELECT TOP 1 1 FROM [{t}] WITH (NOLOCK) WHERE " + " OR ".join(where)
                cur.execute(sql, params)
                if cur.fetchone():
                    return True
        finally:
            with contextlib.suppress(Exception): cur.close()
            with contextlib.suppress(Exception): conn.close()
        return False

    def _feature_status_from_equipment(
            self,
            model: str,
            feature_keywords: list[str],
            original_query: str | None = None,   # 👈 YENİ
        ) -> tuple[list[str], dict, str | None]:
        import re, contextlib
        m = (model or "").strip().upper()
        if not m or not feature_keywords:
            return [], {}, None

        # 1) En güncel tablo
        tname = self._latest_equipment_table_for(model)
        if not tname:
            return [], {}, None

        conn = self._sql_conn(); cur = conn.cursor()
        try:
            cur.execute(f"SELECT TOP 0 * FROM [dbo].[{tname}] WITH (NOLOCK)")
            cols = [c[0] for c in cur.description] if cur.description else []
            if not cols:
                return [], {}, None

            # Özellik/isim kolonu
            name_candidates = ["Equipment","Donanim","Donanım","Ozellik","Özellik","Name","Title","Attribute","Feature"]
            feat_col = next((c for c in name_candidates if c in cols), None)
            if not feat_col:
                feat_col = next((c for c in cols if re.search(r"(equip|donan|özellik|ozellik|name|title|attr)", c, re.I)), None)
            if not feat_col:
                return [], {}, None

            # --- 📌 TRIM KOLONLARI (YENİ) ---
            # kolon isimlerini normalize et (alt çizgi / & / boşluk farklarını yok say)
            def norm(s: str) -> str:
                return normalize_tr_text(s or "").lower().replace("_", " ").strip()

            low2orig = {norm(c): c for c in cols}

            known_trims = [
                "premium",
                "elite",
                "prestige",
                "sportline",
                "monte carlo",
                "montecarlo",
                "monte_carlo",
                "rs",
                "l&k crystal",   # LK_Crystal kolonunu da yakalar
                "lk crystal",
                "sportline phev",
                "esportline",    # eSportline için
                "e prestige 60",
                "e sportline 60",
                "coupe e sportline 60",
                "e sportline 85x",
                "coupe e sportline 85x",
            ]

            trim_cols: list[str] = []
            for t in known_trims:
                k = norm(t)
                if k in low2orig:
                    trim_cols.append(low2orig[k])
            if not trim_cols:
                for c in cols:
                    if c == feat_col:
                        continue
                    c_norm = norm(c)
                    if any(w in c_norm for w in ["premium","elite","prestige","sportline","monte","crystal","rs","e prestige","e sportline"]):
                        trim_cols.append(c)

            if not trim_cols:
                return [], {}, None

            # 3) LIKE filtresi
            coll = os.getenv("SQL_CI_COLLATE", "Turkish_100_CI_AI")
            use_ft_env = os.getenv("USE_MSSQL_FULLTEXT", "0") == "1"
            use_ft = False
            try:
                use_ft = use_ft_env and self._has_fulltext(conn, tname, feat_col)
            except Exception:
                use_ft = False

            where_sql, params = self._make_where_for_keywords(feat_col, feature_keywords, use_fulltext=use_ft, collate=coll)
            sql = f"""
                SELECT TOP 30 [{feat_col}], {', '.join(f'[{c}]' for c in trim_cols)}
                FROM [dbo].[{tname}] WITH (NOLOCK)
                WHERE {where_sql}
            """
            cur.execute(sql, params)
            rows = cur.fetchall()
            if not rows:
                return [], {}, None


            # ✅ BURAYA EKLE (rows geldikten hemen sonra)
            q_norm = normalize_tr_text(original_query or " ".join(feature_keywords)).lower()
            rules = self._forced_match_rules(q_norm)

            # rows geldikten hemen sonra
            cur.execute(sql, params)
            rows = cur.fetchall()
            self.logger.info(f"[EQUIP-SQL] table={tname} rows={len(rows)} keywords={feature_keywords[:6]}")

            if not rows:
                return [], {}, None

            def nrm(s: str) -> str:
                return re.sub(r"\s+", " ", normalize_tr_text(s or "")).lower().strip()

            # ✅ sonra rules filtresi
            q_norm = normalize_tr_text(original_query or " ".join(feature_keywords)).lower()
            rules = self._forced_match_rules(q_norm)

            def _ok_by_rules(oz_text: str) -> bool:
                oz_low = nrm(oz_text)
                for pos_list, neg_list in rules:
                    if any(n.search(oz_low) for n in neg_list):
                        return False
                    if pos_list and not any(p.search(oz_low) for p in pos_list):
                        return False
                return True

            if rules:
                filtered_rows = []
                for r in rows:
                    oz_raw = str(r[0] or "").strip()
                    if _ok_by_rules(oz_raw):
                        filtered_rows.append(r)

                if not filtered_rows:
                    return [], {}, None

                rows = filtered_rows


            if rules:
                filtered_rows = []
                for r in rows:
                    oz_raw = str(r[0] or "").strip()
                    if _ok_by_rules(oz_raw):
                        filtered_rows.append(r)

                if not filtered_rows:
                    return [], {}, None

                rows = filtered_rows

            if not rows:
                return [], {}, None

            # 4) En iyi satırı seç (özellik adını keyword'lere göre skorla)
            def nrm(s: str) -> str:
                return re.sub(r"\s+", " ", normalize_tr_text(s or "")).lower().strip()

            # Kullanıcıdan gelen feature_keywords → normalize
            norm_keywords = [self._norm_alias(k) for k in feature_keywords if k]
            norm_keywords = [k for k in dict.fromkeys(norm_keywords) if len(k) >= 2]

            def row_score(oz_full: str) -> float:
                """
                Eşleştirme skorunu HEP parantez dışındaki kısma göre hesapla.
                Örn:
                  'Gözlük saklama kabı (Panoramik cam tavan ile sunulmamaktadır.)'
                  → sadece 'Gözlük saklama kabı' üzerinden skor verilir.
                """
                # Parantez içini at
                #oz_main = strip_parens_for_match(oz_full)
                oz_main = oz_full
                oz_main_norm = nrm(oz_main)

                score = 0.0
                for k in norm_keywords:
                    if not k:
                        continue
                    if all(word in oz_main_norm for word in k.split()):
                        # daha uzun varyant = daha güçlü eşleşme
                        score += 2.0 + len(k) / 5.0
                return score

            scored_rows: list[tuple[float, int, tuple, str]] = []  # (score, idx, row, oz_raw)

            def row_score_loose(oz_full: str) -> float:
                oz_norm = nrm(oz_full)
                score = 0.0

                # 1) Tam ifade geçiyorsa güçlü bonus
                for k in norm_keywords:
                    if not k:
                        continue
                    if k in oz_norm:
                        score += 4.0
                        continue

                    # 2) Kelime kapsaması: kaç kelime tuttu?
                    ks = [w for w in k.split() if w]
                    if not ks:
                        continue
                    hit = sum(1 for w in ks if w in oz_norm)
                    if hit:
                        score += 1.2 * hit
                        if hit == len(ks):
                            score += 1.0  # tüm kelimeler tuttuysa ekstra

                return score

            for idx, r in enumerate(rows):
                oz_raw = str(r[0] or "").strip()
                sc = row_score_loose(oz_raw)
                scored_rows.append((sc, idx, r, oz_raw))

            # Hepsi 0 bile olsa en azından birini seçebilelim (sonra safe_match zaten eleyecek)
            scored_rows.sort(key=lambda x: x[0], reverse=True)

            best_score, best_idx, best_row, best_oz = scored_rows[0]


            # Skora göre sırala (yüksek → düşük)
            scored_rows.sort(key=lambda x: x[0], reverse=True)
            best_score, best_idx, best_row, best_oz = scored_rows[0]
            # ✅ FINAL CHECK: soru gerçekten bu satırı istiyor mu?
            if original_query:
                if not self._is_safe_equipment_match(original_query, best_oz):
                    # son şans: YES/NO verifier
                    if not self._llm_verify_hit(original_query, best_oz):
                        return [], {}, None
            # --- GPT ile belirsiz durumlarda disambig yap ---
            if original_query and len(scored_rows) > 1:
                second_score = scored_rows[1][0]
                # Çok bariz bir fark yoksa (ör. ilk ikinin skoru birbirine yakınsa)
                # GPT'ye soralım. İstersen bu eşiği oynayabilirsin.
                if best_score < 4.0 or (best_score - second_score) < 1.5:
                    top_k = min(5, len(scored_rows))
                    cand_ozellikler = [oz for (_s, _i, _r, oz) in scored_rows[:top_k]]
                    gpt_idx = self._disambiguate_feature_via_gpt(original_query, cand_ozellikler)
                    if gpt_idx is not None and 0 <= gpt_idx < top_k:
                        best_score, best_idx, best_row, best_oz = scored_rows[gpt_idx]

            # Buradan sonrası senin mevcut kodunun devamı
            # (rec, status_map, feature_title vb.)
            rec = { ([feat_col] + trim_cols)[i]: best_row[i] for i in range(1 + len(trim_cols)) }

            status_map = {}
            for tc in trim_cols:
                raw = rec.get(tc)
                status_map[tc] = self._normalize_equipment_status(raw)

            feature_title = (rec.get(feat_col) or "").strip()
            trims_pretty = [tc for tc in trim_cols]
            return trims_pretty, status_map, feature_title

        finally:
            with contextlib.suppress(Exception): cur.close()
            with contextlib.suppress(Exception): conn.close()


    def _generic_spec_from_sql(self, model_slug: str, want: str, return_meta: bool = False):

        import re, contextlib
        m = (model_slug or "").strip().upper()
        if not m or not want:
            return None

        self.logger.info(f"[SQL-SPEC] Checking model={m}, want={want}, STRICT={getattr(self,'STRICT_MODEL_ONLY',False)}")

        # --- 1) Hangi metrik? (tork, güç, 0-100, menzil vs.) ---
        want_norm_all = normalize_tr_text(want).lower()
        self._LAST_SPEC_QUERY = want_norm_all
        key_hits = []
        for canon, (like_terms, _) in (self._SPEC_KEYWORDS or {}).items():
            key_low = normalize_tr_text(canon).lower()
            if key_low in want_norm_all:
                key_hits.append(canon)

        if re.search(r"\b0\s*[-–—]?\s*100\b", want_norm_all):
            if "0-100" not in key_hits:
                key_hits.append("0-100")

        word_map = {
            "tork":       "tork",
            "torque":     "tork",
            "güç":        "güç",
            "beygir":     "güç",
            "hp":         "güç",
            "ps":         "güç",
            "menzil":     "menzil",
            "range":      "menzil",
            "co2":        "co2",
            "emisyon":    "co2",
            "tüketim":    "yakıt tüketimi",
            "l/100":      "yakıt tüketimi",
            "maks":       "maksimum hız",
            "hız":        "maksimum hız",
            "hiz":        "maksimum hız",
            "ağırlık":    "agirlik",
            "agirlik":    "agirlik",
            "weight":     "agirlik",
            "kg":         "agirlik",
        }
        for w, k in word_map.items():
            if w in want_norm_all and k not in key_hits:
                key_hits.append(k)

        if not key_hits:
            # Bu soru teknik değil (elektrikli mi, 4x4 mü vs.) → SQL spec arama yapma
            return (None, None, None) if return_meta else None
                # 🔹 ÖNCE Imported_KODA_<MODEL> tablosunda Ozellik'e göre direkt ara
        # (Maks. hız, 0-100, Birleşik, CO₂ gibi satırlar için)
        primary_key = key_hits[0]  # ilk kanonik anahtar
        numeric_required = True

        val_direct = self._spec_from_imported_by_ozellik(m, primary_key)
        # ✅ Bu sorgu metnini menzil satırı seçimi için sakla (kombine/şehir içi ayrımı)
        

        if val_direct:
            self.logger.info(f"[SQL-SPEC] DIRECT Imported_KODA hit ({primary_key}) -> {val_direct}")
            if return_meta:
                row_md = self._spec_row_markdown_from_imported(m, primary_key)
                return val_direct, primary_key, row_md
            return val_direct

        def terms_for(canon_key: str) -> list[str]:
            like_terms, _ = self._SPEC_KEYWORDS.get(canon_key, ([], None))
            if like_terms:
                return like_terms[:]
            return [f"%{normalize_tr_text(canon_key).lower()}%"]

        final_like_terms: list[str] = []
        for k in key_hits:
            final_like_terms.extend(terms_for(k))

        collate = os.getenv("SQL_CI_COLLATE", "Turkish_100_CI_AI")

        def _scan_tables(cur, patterns: list[str]) -> str | None:
            """Verilen pattern listesinde sırayla gezip ilk anlamlı satırı döndürür."""
            for p in patterns:
                self.logger.info(f"[SQL-SPEC] scanning pattern={p}")
                cur.execute("SELECT name FROM sys.tables WHERE name LIKE ? ESCAPE '\\' ORDER BY name DESC", (p,))
                for (tname,) in cur.fetchall():
                    # STRICT_MODEL_ONLY → tabloda model adı geçsin
                    if getattr(self, "STRICT_MODEL_ONLY", False):
                        T = tname.upper()
                        if not (f"_{m}_" in T or T.endswith(f"_{m}") or T.startswith(f"{m}_")):
                            continue
                    try:
                        cur.execute(f"SELECT TOP 0 * FROM [{tname}]")
                        cols = [c[0] for c in cur.description]
                    except Exception as e:
                        self.logger.warning(f"[SQL-SPEC] table read failed (schema): {tname}, err: {e}")
                        continue

                    # Değer kolonları
                    val_cols = [c for c in cols if re.search(
                        r"(deger|değer|value|val|content|desc|description|açıklama|aciklama|"
                        r"icerik|içerik|spec|specval|spec_value|unit|birim|data|veri|number|num)",
                        c, re.I
                    )]
                    if not val_cols:
                        val_cols = [c for c in cols if c.lower() not in ('id', 'model', 'ozellik', 'özellik')]

                    name_cols = [c for c in cols if re.search(
                        r"(ozellik|özellik|name|title|attribute|specname|featurename)",
                        c, re.I
                    ) and c not in val_cols]

                    if not name_cols and not val_cols:
                        continue

                    target_cols = name_cols + val_cols
                    where_parts, params = [], []
                    for nc in target_cols:
                        for lt in final_like_terms:
                            where_parts.append(
                                f"LOWER(CONVERT(NVARCHAR(4000),[{nc}])) COLLATE {collate} LIKE ?"
                            )
                            params.append(lt)

                    if not where_parts:
                        continue

                    vblob_expr = " + ' ' + ".join([f"CONVERT(NVARCHAR(4000),[{c}])" for c in val_cols]) if val_cols else "''"

                    sql = (
                        f"SELECT TOP 20 {', '.join(target_cols)}, ({vblob_expr}) AS _vblob "
                        f"FROM [{tname}] WITH (NOLOCK) WHERE " + " OR ".join(where_parts) + " "
                        f"ORDER BY CASE WHEN ({vblob_expr}) LIKE '%[0-9]%' THEN 0 ELSE 1 END, "
                        f"LEN(({vblob_expr})) DESC"
                    )
                    try:
                        cur.execute(sql, params)
                        row = cur.fetchone()
                    except Exception as e:
                        self.logger.warning(f"[SQL-SPEC] table read failed: {tname}, err: {e}")
                        continue

                    if not row:
                        continue

                    val = self._best_value_from_row(target_cols, row, set(name_cols))
                    if numeric_required and not re.search(r"\d", val or ""):
                        continue
                    if not val:
                        # Son çare: tüm değer benzeri kolonları birleştir
                        val = " ".join(
                            str(row[target_cols.index(c)] or "").strip()
                            for c in target_cols if c not in name_cols
                        ).strip()

                    if val:
                        self.logger.info(f"[SQL-SPEC] HIT {tname} -> {val[:160]}")
                        return val

            return None

        conn = self._sql_conn(); cur = conn.cursor()
        try:
            # 2) ÖNCE Imported dışındaki teknik tablolarda ara
            primary_patterns = [
                f"Imported\\_KODA\\_{m}\\_MY\\_%",
                f"Imported\\_{m}%",
                f"Imported\\_{m.capitalize()}%",
            ]
            val = _scan_tables(cur, primary_patterns)
            if val:
                return (val, primary_key, None) if return_meta else val

            # 3) Diğer teknik tablolara bak (TechSpecs vb.)
            secondary_patterns = [
                f"TechSpecs\\_KODA\\_{m}\\_MY\\_%",

                # ❌ teknik metrik ararken bunlar yanlışlıkla "Standart" döndürebiliyor
                # f"EquipmentList\\_KODA\\_{m}\\_MY\\_%",
                # f"PriceList\\_KODA\\_{m}\\_MY\\_%",

                f"%{m}%",
            ]
            val = _scan_tables(cur, secondary_patterns)
            if val:
                return (val, primary_key, None) if return_meta else val
        except Exception as e:
            self.logger.error(f"[SQL-SPEC] generic error: {e}")
        finally:
            with contextlib.suppress(Exception): cur.close()
            with contextlib.suppress(Exception): conn.close()

        return (None, None, None) if return_meta else None


        


    def _bagaj_hacmi_from_sql(self, model_slug: str) -> str | None:
        """
        Ör: model_slug='scala' -> TechSpecs/Imported tablolardan bagaj hacmi satırını bulur.
        Dönüş: '467 / 1.410 dm3' gibi ham değer (bulursa).
        Yedek: Teknik MD tablosundan 'Bagaj hacmi (dm3)' anahtarını okur.
        """
        import re, contextlib
        m = (model_slug or "").strip().upper()
        if not m:
            return None

        name_cols_candidates  = ["SpecName","Name","Title","Attribute","Ozellik","Özellik","Donanim","Donanım","Key","Anahtar"]
        value_cols_candidates = ["SpecValue","Value","Deger","Değer","Content","Description","Icerik","İçerik","Data","Veri","Unit","Birim"]

        # Çok dilli/desenli arama: bagaj + boot + luggage + cargo + trunk
        # dm3/Litre gibi birim ipuçları sonradan ikinci filtrede kullanılacak
        name_like_terms = ["%bagaj%", "%bagaj hacmi%", "%boot%", "%luggage%", "%cargo%", "%trunk%"]

        patts = [
            f"TechSpecs\\_KODA\\_{m}\\_MY\\_%",
            f"Imported\\_KODA\\_{m}\\_MY\\_%",
            f"Imported\\_{m.capitalize()}%",   # Imported_Scala...
            f"Imported\\_{m}%"                 # Imported_SCALA...
        ]

        conn = self._sql_conn(); cur = conn.cursor()
        try:
            cand_tables = []
            for p in patts:
                cur.execute("""
                    SELECT TOP 8 name FROM sys.tables
                    WHERE name LIKE ? ESCAPE '\\'
                    ORDER BY name DESC
                """, (p,))
                cand_tables += [r[0] for r in cur.fetchall()]

            seen = set()
            for tname in [x for x in cand_tables if not (x in seen or seen.add(x))]:
                # Kolonları al
                try:
                    cur.execute(f"SELECT TOP 0 * FROM [{tname}]")
                except Exception:
                    continue
                cols = [c[0] for c in cur.description] if cur.description else []
                if not cols:
                    continue

                # Kolon adaylarını çıkar
                name_cols  = [c for c in name_cols_candidates  if c in cols]
                value_cols = [c for c in value_cols_candidates if c in cols]
                if not name_cols:
                    # heuristik kolon seçimi
                    name_cols = [c for c in cols if re.search(r"(name|title|attr|özellik|ozellik|donan[ıi]m|key)", c, re.I)]
                if not value_cols:
                    value_cols = [c for c in cols if re.search(r"(value|değer|deger|content|desc|birim|unit|data|veri)", c, re.I)]
                if not name_cols or not value_cols:
                    continue

                # Çoklu LIKE ile ara
                where_parts = []
                params = []
                for nc in name_cols:
                    for term in name_like_terms:
                        where_parts.append(f"[{nc}] LIKE ?")
                        params.append(term)
                sql = f"SELECT TOP 20 {', '.join([f'[{c}]' for c in name_cols+value_cols])} FROM [{tname}] WHERE " + " OR ".join(where_parts)
                try:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
                except Exception:
                    continue

                # Önce 'bagaj' içerenleri, yoksa 'boot/luggage/...' içerenleri değerlendir
                for r in rows:
                    rec = { (name_cols+value_cols)[i]: r[i] for i in range(len(name_cols+value_cols)) }
                    name_blob = " ".join(str(rec.get(c) or "") for c in name_cols).lower()
                    val_blob  = " ".join(str(rec.get(c) or "") for c in value_cols).strip()
                    if any(k in name_blob for k in ["bagaj", "boot", "luggage", "cargo", "trunk"]) and val_blob:
                        return val_blob

            # --- Yedek: Teknik MD tablosundan çek ---
             

        finally:
            with contextlib.suppress(Exception): cur.close()
            with contextlib.suppress(Exception): conn.close()

        return None
    def _kapi_sayisi_from_sql(self, model_slug: str) -> str | None:
        """
        'kapı' / 'door(s)' satırını bulur. Yedek: teknik MD’den 'Kapı sayısı' benzeri anahtarları dener.
        """
        import re, contextlib
        m = (model_slug or "").strip().upper()
        if not m:
            return None

        name_terms = ["%kapı%", "%kapi%", "%door%"]
        name_cols_candidates  = ["SpecName","Name","Title","Attribute","Ozellik","Özellik","Donanim","Donanım","Key","Anahtar"]
        value_cols_candidates = ["SpecValue","Value","Deger","Değer","Content","Description","Icerik","İçerik","Data","Veri","Unit","Birim"]

        patts = [
            f"TechSpecs\\_KODA\\_{m}\\_MY\\_%",
            f"Imported\\_KODA\\_{m}\\_MY\\_%",
            f"Imported\\_{m.capitalize()}%",
            f"Imported\\_{m}%"
        ]

        conn = self._sql_conn(); cur = conn.cursor()
        try:
            cand_tables = []
            for p in patts:
                cur.execute("""SELECT TOP 8 name FROM sys.tables WHERE name LIKE ? ESCAPE '\\' ORDER BY name DESC""", (p,))
                cand_tables += [r[0] for r in cur.fetchall()]

            seen = set()
            for tname in [x for x in cand_tables if not (x in seen or seen.add(x))]:
                try:
                    cur.execute(f"SELECT TOP 0 * FROM [{tname}]")
                except Exception:
                    continue
                cols = [c[0] for c in cur.description] if cur.description else []
                if not cols: continue
                name_cols  = [c for c in name_cols_candidates  if c in cols] or [c for c in cols if re.search(r"(name|title|attr|özellik|donan[ıi]m|key)", c, re.I)]
                value_cols = [c for c in value_cols_candidates if c in cols] or [c for c in cols if re.search(r"(value|değer|content|desc|data|veri)", c, re.I)]
                if not name_cols or not value_cols: continue

                where_parts, params = [], []
                for nc in name_cols:
                    for term in name_terms:
                        where_parts.append(f"[{nc}] LIKE ?")
                        params.append(term)
                if not where_parts: 
                    continue
                sql = f"SELECT TOP 20 {', '.join([f'[{c}]' for c in name_cols+value_cols])} FROM [{tname}] WHERE " + " OR ".join(where_parts)
                try:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
                except Exception:
                    continue

                for r in rows:
                    rec = { (name_cols+value_cols)[i]: r[i] for i in range(len(name_cols+value_cols)) }
                    name_blob = " ".join(str(rec.get(c) or "") for c in name_cols).lower()
                    val_blob  = " ".join(str(rec.get(c) or "") for c in value_cols).strip()
                    if any(k in name_blob for k in ["kapı","kapi","door"]) and val_blob:
                        return val_blob
        finally:
            with contextlib.suppress(Exception): cur.close()
            with contextlib.suppress(Exception): conn.close()

        # Yedek: teknik MD’den yakalamaya çalış
         
        return None


    def _strip_code_fences(self, s: str) -> str:
    
        if not s:
            return s
        # ```...``` (dil etiketli/etiketsiz) kod bloklarını kaldır
        s = re.sub(r"```.*?```", "", s, flags=re.DOTALL)
        # 4 boşluk/sekme ile başlayan kod satırlarını kaldır
        s = re.sub(r"(?m)^(?: {4,}|\t).*$", "", s)
        # inline `kod` parçalarını kaldır
        s = re.sub(r"`[^`]+`", "", s)
        # gereksiz boşluklar
        s = re.sub(r"\n{3,}", "\n\n", s).strip()
        return s

    def _glob_sql_md_files(self):
        import glob, os
        files = []
        for base in self.SQL_RAG_DIRS:
            root = os.path.join(os.getcwd(), base)
            files.extend(glob.glob(os.path.join(root, "**", "*.sql.md"), recursive=True))
        # Tekilleştir ve var olanları al
        files = [f for f in dict.fromkeys(files) if os.path.isfile(f)]
        self.logger.info(f"[SQL-RAG] Found {len(files)} *.sql.md file(s).")
        return files

    def _ensure_sql_vector_store_and_upload(self):
        vs_api = self._vs_api()
        if not vs_api:
            self.logger.warning("[SQL-RAG] vector_stores API yok; atlandı.")
            return
        try:
            # 1) Vector store yoksa oluştur
            if not self.VECTOR_STORE_SQL_ID:
                vs = vs_api.create(name=self.VECTOR_STORE_SQL_NAME)
                self.VECTOR_STORE_SQL_ID = vs.id

            # 2) Dosyaları topla
            files = self._glob_sql_md_files()
            if not files:
                self.logger.warning("[SQL-RAG] *.sql.md bulunamadı.")
                return

            # 3) Yükle
            batches_api = getattr(vs_api, "file_batches", None)
            files_api   = getattr(vs_api, "files", None)
            from contextlib import ExitStack  # <-- dosyanın başında da olabilir
            if batches_api and hasattr(batches_api, "upload_and_poll"):
                with ExitStack() as stack:
                    fhs = [stack.enter_context(open(p, "rb")) for p in files]
                    batches_api.upload_and_poll(vector_store_id=self.VECTOR_STORE_SQL_ID, files=fhs)

                     
            elif files_api and hasattr(files_api, "create_and_poll"):
                for p in files:
                    with open(p, "rb") as fh:
                        files_api.create_and_poll(
                            vector_store_id=self.VECTOR_STORE_SQL_ID,
                            file=fh
                        )
            else:
                # En basit geri dönüş
                for p in files:
                    with open(p, "rb") as fh:
                        self.client.files.create(file=fh, purpose="assistants")
            self.logger.info(f"[SQL-RAG] Upload done. VS_ID={self.VECTOR_STORE_SQL_ID}")
        except Exception as e:
            self.logger.error(f"[SQL-RAG] init failed: {e}")
    # Trim adları: standart donanım tablosu başlığında sık geçer
    # ChatbotAPI içinde, _answer_with_sql_rag'i DB vektörlerine çevirelim
        # ChatbotAPI içinde, eski SQL-RAG fonksiyonunun yerine:
    def _answer_with_sql_rag(self, user_message: str, user_id: str) -> bytes | None:
        """
        LLM SQL-RAG modu (YENİ):

        Eskiden:
            - OpenAI Vector Store (VECTOR_STORE_SQL_ID)
            - file_search tool
            - .sql.md dosyalarına göre cevap üretiyordu.

        Şimdi:
            - Doğrudan MSSQL → KbVectors → Hybrid RAG (_answer_with_hybrid_rag)
            - Yani ContextSearch 'llm' dediğinde, KBVectors üzerinden SQL içeriğiyle
              cevap üretiliyor.

        Dönüş: UTF-8 byte string (Flask response_class için).
        """

        # Hybrid RAG kapalıysa hiç deneme
        if not getattr(self, "HYBRID_RAG", False):
            self.logger.info("[HYBRID-RAG] HYBRID_RAG=0, atlanıyor.")
            return b""

        # STRICT_SQL_ONLY modunda genel LLM kullanma
        if getattr(self, "STRICT_SQL_ONLY", False):
             return ""

        # 1) Hybrid RAG ile metin cevabı al
        try:
            text = self._answer_with_hybrid_rag(user_message, user_id=user_id) or ""
        except Exception as e:
            self.logger.error(f"[HYBRID-RAG] _answer_with_hybrid_rag hata: {e}")
            return b""

        text = (text or "").strip()
        if not text:
            return b""

        # 2) Kaynak / citation izlerini temizle + daha net ton uygula
        try:
            text = self._strip_source_mentions(text)
        except Exception:
            pass

        try:
            text = self._enforce_assertive_tone(text)
        except Exception:
            pass

        # 3) Markdown'a dönüştür ve tablo hizasını düzelt
        try:
            md = self.markdown_processor.transform_text_to_markdown(text)
        except Exception:
            md = text

        if '|' in md and '\n' in md:
            try:
                md = fix_markdown_table(md)
            except Exception:
                pass

        return md.encode("utf-8")


 

    def _drop_kb_missing_rows_from_markdown(self, md: str) -> str:
        if not md or '|' not in md:
            return md

        def split_row(ln: str):
            return [c.strip() for c in ln.strip().strip('|').split('|')]

        lines = md.splitlines()
        out, i, n = [], 0, len(lines)
        while i < n:
            if '|' in lines[i]:
                start = i
                if i+1 < n and re.search(r'^\s*\|\s*[-:]', lines[i+1]):
                    # header + sep + body
                    i += 2
                    while i < n and '|' in lines[i]:
                        i += 1
                    block = lines[start:i]

                    # satırları süz
                    new_block = []
                    for k, ln in enumerate(block):
                        if k == 1:  # ayraç satırı
                            new_block.append(ln); continue
                        cells = split_row(ln)
                        row_text = normalize_tr_text(" ".join(cells)).lower()
                        if KB_MISSING_PAT.search(row_text):
                            continue  # KB’de yok barındıran tüm satırı düş
                        new_block.append(ln)

                    # eğer header + sep haricinde hiç gövde kalmadıysa tabloyu komple atla
                    if len(new_block) >= 2 and any('|' in r for r in new_block[2:]):
                        out.extend(new_block)
                else:
                    out.append(lines[i]); i += 1
            else:
                out.append(lines[i]); i += 1
        return "\n".join(out)

    def _drop_kb_missing_rows_from_html(self, html: str) -> str:
        if not html or "<table" not in html.lower():
            return html

        # <tr> bazında tarayıp, metninde "KB’de yok" varyantları geçen satırları sil
        def kill_row(m):
            row = m.group(0)
            plain = normalize_tr_text(re.sub(r"<[^>]+>", " ", row)).lower()
            return "" if KB_MISSING_PAT.search(plain) else row

        return re.sub(r"<tr[^>]*>.*?</tr>", kill_row, html, flags=re.I | re.S)

    def _drop_kb_missing_rows_from_any(self, text: str) -> str:
        if not text:
            return text
        t = text
        if "<table" in t.lower():
            t = self._drop_kb_missing_rows_from_html(t)
        if '|' in t and re.search(r'\|\s*[-:]', t):
            t = self._drop_kb_missing_rows_from_markdown(t)
        # ardışık boş satırları toparla
        t = re.sub(r"\n{3,}", "\n\n", t).strip()
        return t
    def _strip_price_from_markdown_table(self, md: str) -> str:
        lines = [ln for ln in (md or "").splitlines()]
        if not lines or not any('|' in ln for ln in lines):
            return md

        def split_row(ln: str):
            cells = [c.strip() for c in ln.strip().strip('|').split('|')]
            return cells

        # Tablo bloklarını işle
        out, i, n = [], 0, len(lines)
        while i < n:
            if '|' in lines[i]:
                # header + sep yakala
                start = i
                if i+1 < n and re.search(r'^\s*\|\s*[-:]', lines[i+1]):
                    i += 2
                    # gövde satırlarını topla
                    while i < n and '|' in lines[i]:
                        i += 1
                    block = lines[start:i]

                    # --- kolon temizleme: header'a bak ---
                    header = split_row(block[0])
                    sep    = block[1]
                    col_keep = [True]*len(header)
                    for idx, h in enumerate(header):
                        h_low = normalize_tr_text(h).lower()
                        if any(tok in h_low for tok in PRICE_TOKENS_COL):
                            col_keep[idx] = False
                    # Eğer tüm kolonlar elenirse, tabloyu tamamen kaldır
                    if not any(col_keep):
                        continue

                    # --- satır temizleme + kolon drop ---
                    new_block = []
                    for k, ln in enumerate(block):
                        if k == 1:  # ayraç satırı
                            # ayraç kolonlarını da kısalt
                            kept = [seg for j, seg in enumerate(ln.strip().strip('|').split('|')) if j < len(col_keep) and col_keep[j]]
                            new_block.append("|" + "|".join(kept) + "|")
                            continue

                        cells = split_row(ln)
                        row_text_low = normalize_tr_text(" ".join(cells)).lower()
                        # satır komple "fiyat" içeriyorsa atla
                        if any(tok in row_text_low for tok in PRICE_TOKENS_ROW):
                            continue
                        kept = [c for j, c in enumerate(cells) if j < len(col_keep) and col_keep[j]]
                        if kept:
                            new_block.append("| " + " | ".join(kept) + " |")
                    if len(new_block) >= 2:
                        out.extend(new_block)
                else:
                    out.append(lines[i]); i += 1
            else:
                out.append(lines[i]); i += 1
        return "\n".join(out)

    def _strip_price_from_html_table(self, html: str) -> str:
        s = html or ""
        if "<table" not in s.lower():
            return html
        # 1) Fiyat barındıran <tr> satırlarını komple sil
        pat_row = re.compile(r"<tr[^>]*>.*?</tr>", re.I | re.S)
        def kill_row(m):
            row = m.group(0)
            low = normalize_tr_text(re.sub(r"<[^>]+>", " ", row)).lower()
            return "" if any(tok in low for tok in PRICE_TOKENS_ROW) else row
        s = pat_row.sub(kill_row, s)

        # 2) Header’da fiyat geçen kolonları silmek için th/td bazlı hızlı yaklaşım:
        # (Basit ve güvenli: header hücresinde fiyat geçiyorsa tüm satırlarda o index'i çıkar.)
        # Header'ı yakala
        header_cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", s, re.I | re.S)
        if header_cells:
            # ilk header satırını normalize et
            head_texts = [normalize_tr_text(re.sub(r"<[^>]+>", " ", c)).lower() for c in header_cells]
            drop_idx = {i for i, t in enumerate(head_texts) if any(tok in t for tok in PRICE_TOKENS_COL)}
            if drop_idx:
                # her <tr> için aynı indexlerdeki <td>/<th>’ları çıkar
                def drop_cols_in_tr(tr_html: str) -> str:
                    cells = re.findall(r"(<t[hd][^>]*>.*?</t[hd]>)", tr_html, re.I | re.S)
                    if not cells:
                        return tr_html
                    kept = [c for j, c in enumerate(cells) if j not in drop_idx]
                    return re.sub(r"(<t[hd][^>]*>.*?</t[hd]>)", "", tr_html, count=0, flags=re.I | re.S).replace("", "") if not kept else \
                        re.sub(r"(<t[hd][^>]*>.*?</t[hd]>)", "§CELL§", tr_html, flags=re.I | re.S).replace("§CELL§"*len(cells), "".join(kept))
                s = re.sub(r"(<tr[^>]*>.*?</tr>)", lambda m: drop_cols_in_tr(m.group(1)), s, flags=re.I | re.S)
        return s

    def _strip_price_from_any(self, text: str) -> str:
        if not text:
            return text
        t = text
        low = t.lower()
        if "<table" in low:
            t = self._strip_price_from_html_table(t)
        if ('|' in t and re.search(r'\|\s*[-:]', t)):
            t = self._strip_price_from_markdown_table(t)
        # KV türü düz metin satırlarını da temizle (örn. "Fiyat Aralığı: ...")
        t = re.sub(r"(?im)^\s*[-*•]?\s*(fiyat|liste\s*fiyatı?|anahtar\s*teslimi?|price|bedel|ücret)\s*[:：].*$", "", t)
        # TL / ₺ ile biten çıplak hücreleri de güvenli tarafta “—” yap
        t = re.sub(r"(\b\d{1,3}(?:\.\d{3})*(?:,\d+)?\s*(tl|₺)\b)", "—", t, flags=re.I)
        # Fazla boş satırları toparla
        t = re.sub(r"\n{3,}", "\n\n", t).strip()
        return t
    @staticmethod
    def _strip_tags(s: str) -> str:
        import re
        return re.sub(r"<[^>]*>", " ", s or "")

    def _score_standard_table(self, table_blob: str) -> int:
        """
        'Standart donanım' tablosu seçiminde kullanılacak sezgisel skor.
        + Trim adı/başlığı, + 'Standart' hücreleri → pozitif
        + Teknik terimler/aşırı sayısal yoğunluk → negatif
        """
        txt = table_blob
        if "<table" in (table_blob or "").lower():
            txt = self._strip_tags(table_blob)
        low = self._norm(txt)

        score = 0
        # 1) Trim ipuçları başlıkta + gövdede
        for w in self.TRIM_HINTS:
            if w in low:
                score += 2

        # 2) 'Standart' sözcüğü (çeşitli yazımlar)
        score += 3 * low.count("standart")

        # 3) Teknik ipuçlarını cezalandır
        for k in self.TECH_HINTS:
            if k in low:
                score -= 1

        # 4) Aşırı sayısal yoğunluk cezalandır (teknik tablolar çok sayı içerir)
        import re
        digits = len(re.findall(r"\d", low))
        pipes  = low.count("|")
        if digits > 50 or digits > max(20, pipes*3):
            score -= 3

        return score

    @staticmethod
    def _norm(s: str) -> str:
        import unicodedata
        s = unicodedata.normalize("NFKD", s or "").lower()
        return "".join(c for c in s if not unicodedata.combining(c))

    @staticmethod
    def _find_html_tables(html: str) -> list[str]:
        out, i = [], 0
        while True:
            start = html.lower().find("<table", i)
            if start == -1: break
            end = html.lower().find("</table>", start)
            if end == -1: break
            out.append(html[start:end+8])
            i = end + 8
        return out

    @staticmethod
    def _html_header_text(table_html: str) -> str:
        import re
        thead = re.search(r"<thead.*?>(.*?)</thead>", table_html, re.I|re.S)
        block = thead.group(1) if thead else re.search(r"<tr.*?>(.*?)</tr>", table_html, re.I|re.S).group(1)
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", block, re.I|re.S)
        text = " | ".join(re.sub(r"<.*?>", "", c) for c in cells)
        return ChatbotAPI._norm(text)

    @staticmethod
    def _classify_header(txt_norm: str) -> str|None:
        if ("kod" in txt_norm) and any(k in txt_norm for k in ("aciklama","açıklama","net satis","net satış","anahtar teslim")):
            return "optional"
        if "ozellik" in txt_norm or "özellik" in txt_norm:
            return "standard"
        return None

    def extract_tables_any(self, content: str) -> list[dict]:
        if not content: return []
        c = content.strip()
        tables = []

        if "<table" in c.lower():
            for tbl in self._find_html_tables(c):
                header_txt = self._html_header_text(tbl)
                kind = self._classify_header(header_txt) or "unknown"
                tables.append({"kind": kind, "text": tbl})
            return tables

        # Markdown (borulu)
        lines = c.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("|") and i + 1 < len(lines):
                align = lines[i+1].replace("|","").strip()
                if set(align) <= set("-: "):
                    j = i + 2
                    while j < len(lines) and lines[j].strip().startswith("|"):
                        j += 1
                    tbl = "\n".join(lines[i:j]).strip()
                    header_norm = self._norm(lines[i])
                    kind = self._classify_header(header_norm) or ("standard" if ("ozellik" in header_norm or "özellik" in header_norm) else "unknown")
                    tables.append({"kind": kind, "text": tbl})
                    i = j
                    continue
            i += 1
        return tables

    def select_table(self, content: str, kind: str) -> str | None:
        tables = self.extract_tables_any(content)
        candidates = [t["text"] for t in tables if t["kind"] == kind]

        # Yedek: sınıflandıramadıysa kaba eşleşme
        if not candidates:
            n = lambda s: self._norm(s)
            if kind == "optional":
                candidates = [t["text"] for t in tables if ("kod" in n(t["text"])) and (("net satis" in n(t["text"]) or "aciklama" in n(t["text"]) or "açıklama" in n(t["text"])))]
            else:
                candidates = [t["text"] for t in tables if ("ozellik" in n(t["text"]) or "özellik" in n(t["text"]))]

        if not candidates:
            return None

        if kind == "optional":
            # Üstteki (1.) opsiyonel tablo
            return candidates[0]

        # kind == 'standard' → en alttakini değil, "standart donanım"ı en iyi temsil edeni seç
        if len(candidates) == 1:
            return candidates[0]

        # Puanlayıp en yüksek skoru seç (teknik tabloyu eler)
        scored = sorted(((self._score_standard_table(c), idx, c) for idx, c in enumerate(candidates)), reverse=True)
        # Eğer puanlar çok yakınsa (eşit), sıralamada ortadakini tercih edin (2. tablo)
        best_score, best_idx, best_blob = scored[0]
        if len(candidates) >= 2:
            # “eşitlik / belirsizlik” halinde 2. sıradakine bias ver
            top2_score = scored[1][0]
            if abs(best_score - top2_score) <= 1:
                return candidates[min(1, len(candidates)-1)]
        return best_blob

    def handle_equipment_request(self, user_id, user_message, model_name: str, trim_name: str | None):
        intent = detect_equipment_intent(user_message)  # 'optional' | 'standard'

        # İçerik kaynakları (sende nasıl adlandırıldıysa onlara bağla)
        html_or_md_optional = getattr(self, "_lookup_opsiyonel_md", lambda *a, **k: None)(model_name, trim_name)
        html_or_md_standard = getattr(self, "_lookup_standart_md",  lambda *a, **k: None)(model_name, trim_name)
        html_or_md_mixed    = getattr(self, "_lookup_donanim_md",   lambda *a, **k: None)(model_name, trim_name)

        # 1) Doğrudan tek tablo kaynağı varsa onu kullan
        chosen = (html_or_md_optional if intent=="optional" else html_or_md_standard)

        # 2) Yoksa karışık içerikten ayıkla
        if not chosen and html_or_md_mixed:
            chosen = self.select_table(html_or_md_mixed, intent)


        title = f"{model_name.title()} {trim_name.title() if trim_name else ''} - " + ("Opsiyonel Donanımlar" if intent=="optional" else "Standart Donanımlar")

        if not chosen:
            yield f"<b>{title}</b><br>İstenen tablo içerikte bulunamadı.".encode("utf-8")
            return  # *** çok önemli: başka hiçbir şey basma ***

        # Markdown ise HTML'e çevir; HTML ise doğrudan gönder
        if chosen.lstrip().startswith("|"):
            try:
                html = fix_markdown_table(chosen)  # sende varsa
            except Exception:
                html = f"<pre>{chosen}</pre>"
        else:
            html = chosen

        yield f"<b>{title}</b>".encode("utf-8")
        yield html.encode("utf-8")
        # md opsiyonel kaynak
        md = self._lookup_opsiyonel_md(model_name, trim_name) or ""
        if not md:
            # karma içerik kaynağın varsa:
            mixed = getattr(self, "_lookup_donanim_md", lambda *a, **k: None)(model_name, trim_name) or ""
            md = self.select_table(mixed, "optional") or ""

        if md:
            title = f"{model_name.title()} {trim_name.title()} - Opsiyonel Donanımlar"
            if md.lstrip().startswith("|"):
                md = fix_markdown_table(md)
            yield f"<b>{title}</b><br>".encode("utf-8")
            yield md.encode("utf-8")
            return

        return  # *** ikincil içeriklerin gönderilmesini kesin engelle ***


    def render_optional_only(md_optional: str | None, md_mixed: str | None) -> str | None:
        """
        Opsiyonel donanım istenirse: sadece Kod/Açıklama/Net Satış tablosunu döndür.
        Önce saf opsiyonel MD'yi, yoksa birleşik MD içinden 'optional' tabloyu seçer.
        """
        if md_optional and md_optional.strip():
            return md_optional.strip()
        if md_mixed:
            pick = select_table_by_kind(md_mixed, "optional")
            if pick: return pick
        return None

    def render_standard_only(md_standard: str | None, md_mixed: str | None) -> str | None:
        """
        Standart donanım istenirse: sadece Özellik başlıklı tabloyu döndür.
        Önce saf standart MD'yi, yoksa birleşik MD içinden 'standard' tabloyu seçer.
        """
        if md_standard and md_standard.strip():
            return md_standard.strip()
        if md_mixed:
            pick = select_table_by_kind(md_mixed, "standard")
            if pick: return pick
        return None


    def _extract_md_tables(md: str):
        """
        MD içindeki tabloları yakalar ve her biri için {'kind': 'optional'|'standard'|'unknown', 'text': '...'} döndürür.
        'optional' kriteri: header satırında 'kod' + ('açıklama' veya 'net satış' veya 'anahtar teslim')
        'standard' kriteri: header satırında 'özellik'
        """
        if not md:
            return []
        lines = md.splitlines()
        tables = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("|"):
                # Tablo hizalama satırı var mı?
                if i + 1 < len(lines) and "|" in lines[i+1] and set(lines[i+1].replace("|","").strip()) <= set("-: "):
                    # Tabloyu topla
                    j = i + 2
                    while j < len(lines) and lines[j].strip().startswith("|"):
                        j += 1
                    tbl_lines = lines[i:j]
                    header = tbl_lines[0].lower()
                    if ("kod" in header) and ("açıklama" in header or "net satış" in header or "anahtar teslim" in header):
                        kind = "optional"
                    elif "özellik" in header:
                        kind = "standard"
                    else:
                        kind = "unknown"
                    tables.append({"kind": kind, "text": "\n".join(tbl_lines).strip()})
                    i = j
                    continue
            i += 1
        return tables

    def select_table_by_kind(md: str, kind: str) -> str | None:
        """
        'optional' için üstteki ilk tablo, 'standard' için alttaki son tablo döndürülür.
        (Görseldeki konuma göre seçim kuralı.)
        """
        tables = _extract_md_tables(md)
        candidates = [t["text"] for t in tables if t["kind"] == kind]
        if not candidates:
            return None
        return candidates[0] if kind == "optional" else candidates[-1]



    def detect_equipment_intent(text: str) -> str | None:
        """
        Kullanıcı metninden niyet çıkar: 'standard' | 'optional' | None
        Çakışmada 'opsiyonel' önceliklidir (fiyat/kod tablosu istendiği varsayımı).
        """
        t = (text or "").lower()
        has_std = any(k in t for k in _STD_KEYS) and "donan" in t
        has_opt = any(k in t for k in _OPT_KEYS) or ("opsiyon" in t and "donan" in t)
        if has_opt and not has_std: return "optional"
        if has_std and not has_opt: return "standard"
        if has_opt and has_std:
            return "optional" if t.rfind("opsiyon") > t.rfind("standart") else "standard"
        return "standard"  # belirsizse varsayılan

     

    def _equipment_from_unified(self, models: list[str], trim: str|None=None, only_keywords: list[str]|None=None):
        conn = self._sql_conn(); cur = conn.cursor()
        try:
            trim_clause = ""
            params = {"m0": models[0], "m1": models[1]}

            if trim:
                trim_clause = " AND LOWER(eq.trim_name) = LOWER(:trim) "
                params["trim"] = trim

            sql = f"""
            SELECT
            eq.feature_name                                   AS feature,
            MAX(CASE WHEN eq.model_slug = :m0 THEN eq.has END) AS {models[0]},
            MAX(CASE WHEN eq.model_slug = :m1 THEN eq.has END) AS {models[1]}
            FROM equipment_flat eq
            WHERE eq.model_slug IN (:m0, :m1)
            {trim_clause}
            GROUP BY eq.feature_name
            ORDER BY eq.feature_name COLLATE NOCASE;
            """


            if only_keywords:
                # çoklu anahtar kelime OR
                like_sql = " OR ".join(["feature_name LIKE ?"]*len(only_keywords))
                sql += " AND (" + like_sql + ")"
                for k in only_keywords:
                    params.append(f"%{k}%")

            cur.execute(sql, params)
            rows = cur.fetchall()
        finally:
            cur.close(); conn.close()

        # pivotu Python’da tamamla (istersen SQL’de PIVOT da yapabilirsin)
        feats = {}
        for feat, model, status in rows:
            feats.setdefault(feat, {}).setdefault(model.title(), status)

        header = ["Özellik"] + [m.title() for m in models]
        lines = ["| " + " | ".join(header) + " |",
                "|" + "|".join(["---"]*len(header)) + "|"]
        for feat in sorted(feats.keys()):
            row = [feat] + [feats[feat].get(m.title(), "—") for m in models]
            lines.append("| " + " | ".join(row) + " |")
        return fix_markdown_table("\n".join(lines))
    def harvest_raw_feature_names(sql_conn):
        cur = sql_conn.cursor()
        cur.execute("""
        SELECT name FROM sys.tables WHERE name LIKE 'EquipmentList\_%' ESCAPE '\\'
        """)
        tables = [r[0] for r in cur.fetchall()]

        cand_cols = ["Equipment","Donanim","Donanım","Ozellik","Özellik","Name","Title","Attribute","Feature"]
        seen = set()
        out  = []

        for t in tables:
            # feature kolonu hangisi?
            cur.execute("""
            SELECT TOP 1 c.name
            FROM sys.columns c
            WHERE c.object_id = OBJECT_ID(?)
                AND c.name IN ({})
            """.format(",".join(["?"]*len(cand_cols))), [t] + cand_cols)
            row = cur.fetchone()
            if not row: 
                continue
            feat_col = row[0]

            cur.execute(f"SELECT DISTINCT CAST([{feat_col}] AS NVARCHAR(200)) FROM {t}")
            for (val,) in cur.fetchall():
                if not val: 
                    continue
                key = (val.strip(),)
                if key in seen:
                    continue
                seen.add(key)
                out.append(val.strip())

        return out  # bunu CSV’ye yaz, insan onayından sonra FeatureCatalog/FeatureAlias’a yükle

    def _answer_two_model_spec_diff(self, models: list[str], canon_key: str) -> str | None:
        models = [m.lower() for m in models if m]
        if len(models) < 2:
            return None
        values = []
        for m in models[:2]:  # ilk iki model
            v = self._get_spec_value(m, canon_key)
            values.append((m, v or "—"))

        (m1, v1), (m2, v2) = values[0], values[1]
        n1,u1 = self._numeric_from_value(v1)
        n2,u2 = self._numeric_from_value(v2)

        # birimler uyuşmuyorsa sadece değerleri yaz
        if (n1 is None) or (n2 is None) or (u1 != u2):
            return f"{m1.title()} {canon_key}: {v1}; {m2.title()} {canon_key}: {v2}."

        diff = n1 - n2  # not: + ise m1 > m2
        # 0-100 gibi 'düşük daha iyi' metriklerinde yorumu ters yazalım
        lower_is_better = ("0-100" in canon_key) or ("sn" in u1.lower())
        if lower_is_better:
            better = m1 if n1 < n2 else (m2 if n2 < n1 else None)
        else:
            better = m1 if n1 > n2 else (m2 if n2 > n1 else None)

        sign = "±" if diff == 0 else ""
        diff_txt = f"{abs(diff):.2f} {u1}".rstrip(" .0")
        if better:
            return (f"{m1.title()} {canon_key}: {v1}; {m2.title()} {canon_key}: {v2}. "
                    f"Fark: {diff_txt}. Daha {'hızlı' if lower_is_better else 'yüksek'} olan: {better.title()}.")
        else:
            return (f"{m1.title()} {canon_key}: {v1}; {m2.title()} {canon_key}: {v2}. "
                    f"Fark: {sign}{diff_txt}. Değerler eşit görünüyor.")

    def _numeric_from_value(self, val: str) -> tuple[float | None, str]:
        """
        '210 km/h' -> (210.0, 'km/h')
        '8,5 sn'   -> (8.5, 'sn')
        '150 PS (110 kW)' -> (150.0, 'PS')
        """
        if not val:
            return None, ""
        s = val.strip().replace(",", ".")
        m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*([A-Za-z%/\.°\- ]*)", s)
        if not m:
            return None, ""
        num = float(m.group(1))
        unit = (m.group(2) or "").strip()
        return num, unit

    def _get_spec_value(self, model: str, canon_key: str) -> str | None:
        md = self._get_teknik_md_for_model(model)
        if not md:
            return None
        _, d = self._parse_teknik_md_to_dict(md)
        return self._get_spec_value_from_dict(d, canon_key)

    def _detect_equipment_filter_keywords(self, text: str) -> list[str]:
        """
        'sadece ...' / 'yalnızca ...' ile belirtilen donanım adı anahtarlarını çıkarır.
        Örn: 'sadece jant, far, multimedya' -> ['jant','far','multimedya']
        """
        t = (text or "").lower()
        m = re.search(r"(?:sadece|yaln[ıi]zca)\s*[:\-]?\s*([a-z0-9çğıöşü\s,\/\+\-]+)", t)
        if not m:
            return []
        raw = m.group(1)
        parts = re.split(r"[,\n\/]+|\s+ve\s+|\s+ile\s+", raw)
        return [p.strip() for p in parts if p.strip()]

    def _latest_equipment_table_for(self, model: str) -> str | None:
        """
        Örn. 'fabia' -> 'EquipmentList_KODA_FABIA_MY_20251'
        sys.tables içinden ilgili modele ait en yeni tabloyu seçer (adına göre DESC).
        """
        m = (model or "").strip().upper()
        # KODA_ / KODA yazımları için tolerans (sende KODA geçiyor)
        pat = f"EquipmentList\\_KODA\\_{m}\\_MY\\_%"
        conn = self._sql_conn()
        cur  = conn.cursor()
        try:
            cur.execute("""
                SELECT TOP 1 name
                FROM sys.tables WITH (NOLOCK)
                WHERE name LIKE ? ESCAPE '\\'
                ORDER BY name DESC
            """, (pat,))
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            cur.close(); conn.close()

    def _normalize_equipment_status(self, *values) -> str:
        """
        S: Standart, O: Opsiyonel, —: Yok/Bilinmiyor
        Farklı kolonlardan gelen ham değerleri normalize eder.
        """
        txt = " ".join([str(v) for v in values if v is not None]).strip()
        if not txt:
            return "—"
        t = normalize_tr_text(txt).lower()

        # Pozitif/standart sinyalleri
        pos_markers = ["standart", "standard", "std", "s ", " s", " (s)", "evet", "yes", "1", "var"]
        if any(mark in f" {t} " for mark in pos_markers):
            return "S"

        # Opsiyonel sinyalleri
        opt_markers = ["ops", "opsiyonel", "optional", "o ", " o", " (o)"]
        if any(mark in f" {t} " for mark in opt_markers):
            return "O"

        # Tek harfli kodlar (temiz)
        if t in {"s"}:
            return "S"
        if t in {"o"}:
            return "O"

        # Boş / tire / yok
        if t in {"-", "—", "yok", "none", "0", "hayir", "hayır", "no"}:
            return "—"

        # Sayısal/serbest değerler (bazı tablolarda 'Value' kolonuna 'S'/'O' yerine açıklama düşebiliyor)
        # Heuristic: 'ops' geçiyorsa O, 'std/standart' geçiyorsa S, aksi halde — bırak.
        if "ops" in t or "opsiyonel" in t:
            return "O"
        if "std" in t or "standart" in t or "standard" in t:
            return "S"

        return "—"


    def _equipment_dict_from_table(self, table_name: str, *, preferred_trim: str | None = "premium") -> tuple[list[str], dict[str, str], dict[str, str]]:
        """
        DÖNÜŞ:
        feature_order_keys: satır anahtarları sırası (kanonik)
        status_map:        { feature_key: 'S'/'O'/'—' }
        display_map:       { feature_key: 'Gösterim Adı' }
        """
        conn = self._sql_conn(); cur = conn.cursor()
        try:
            cur.execute(f"SELECT * FROM [dbo].[{table_name}] WITH (NOLOCK)")
            cols = [c[0] for c in cur.description] if cur.description else []
            rows = cur.fetchall()
        finally:
            cur.close(); conn.close()

        if not rows:
            return [], {}, {}

        def norm(s): return normalize_tr_text(s or "").lower().replace("_", " ").strip()
        low2orig = {norm(c): c for c in cols}

        # Özellik adı adayı
        name_candidates = ["Equipment","Donanim","Donanım","Ozellik","Özellik","Name","Title","Attribute","Feature"]
        feat_col = next((low2orig[norm(c)] for c in name_candidates if norm(c) in low2orig), None)

        # (YENİ) Kod kolonlarını da kontrol et
        code_candidates = ["Code","Kod","FeatureCode","OptionCode","EquipmentCode"]
        code_col = next((low2orig[norm(c)] for c in code_candidates if norm(c) in low2orig), None)

        # Trim kolon seçimi (sizdeki mantık korunuyor)
        TRIM_COL_KEYS = [
            "premium","elite","prestige","sportline",
            "monte carlo","monte_carlo","montecarlo",
            "rs","l&k crystal","l n k crystal","lk crystal",
            "sportline phev",
            "e prestige 60","coupe e sportline 60","coupe e sportline 85x",
            "e sportline 60","e sportline 85x"
        ]
        present_trims = [low2orig[k] for k in TRIM_COL_KEYS if k in low2orig]

        # --- 1) preferred_trim geldiyse: önce onu bulmaya çalış ---
        chosen_trim_col = None
        if preferred_trim:
            pref_norm = norm(preferred_trim)           # örn. "monte carlo"

            # 1.a) Tam norm eşleşme (kolon normu == "monte carlo")
            if pref_norm in low2orig:
                chosen_trim_col = low2orig[pref_norm]
            else:
                # 1.b) Trim varyantlarını dene ("montecarlo", "monte_carlo", "mc"...)
                for v in normalize_trim_str(preferred_trim):
                    v_norm = norm(v)
                    if v_norm in low2orig:
                        chosen_trim_col = low2orig[v_norm]
                        break

                # 1.c) Hâlâ yoksa: kolon adının içinde geçiyor mu diye ara
                if not chosen_trim_col:
                    for c_norm, orig in low2orig.items():
                        # Özellik / kod kolonlarını trim adayı yapma
                        if orig in (feat_col, code_col):
                            continue

                        # "monte carlo" komple geçiyorsa
                        if pref_norm and pref_norm in c_norm:
                            chosen_trim_col = orig
                            break

                        # varyantlardan biri kolon isminde geçiyorsa
                        for v in normalize_trim_str(preferred_trim):
                            v_norm = norm(v)
                            if v_norm and v_norm in c_norm:
                                chosen_trim_col = orig
                                break
                        if chosen_trim_col:
                            break

        # --- 2) Hâlâ bulunamadıysa: ENV fallback (EQUIP_BASE_TRIM) ---
        if not chosen_trim_col:
            base_trim = (os.getenv("EQUIP_BASE_TRIM", "") or "").strip().lower()
            if base_trim:
                base_norm = norm(base_trim)
                if base_norm in low2orig:
                    chosen_trim_col = low2orig[base_norm]

        # --- 3) Son çare: listedeki ilk trim kolonu (premium vb.) ---
        if not chosen_trim_col and present_trims:
            chosen_trim_col = present_trims[0]

        # Debug için log atalım (SSMS’ten bakarken çok işe yarar)
        self.logger.info(
            f"[EQUIP_DICT] table={table_name}, preferred_trim={preferred_trim!r}, "
            f"chosen_col={chosen_trim_col}, cols={cols}"
        )
         
        feature_order_keys, status_map, display_map = [], {}, {}
        seen = set()
        for r in rows:
            d = {cols[i]: r[i] for i in range(len(cols))}
            raw_name = str(d.get(feat_col) or "").strip()
            if not raw_name:
                continue

            # 🔑 Önce kodu dene
            if code_col and d.get(code_col):
                key = f"code:{str(d[code_col]).strip().lower()}"
                disp = raw_name
            else:
                key, disp = canonicalize_feature(raw_name)

            if key not in seen:
                feature_order_keys.append(key); seen.add(key)
                display_map[key] = disp   # gösterim adını sakla

            raw_status = d.get(chosen_trim_col) if chosen_trim_col else None
            status_map[key] = self._normalize_equipment_status(raw_status)

        return feature_order_keys, status_map, display_map



    def _build_equipment_comparison_table_from_sql(
        self,
        models: list[str],
        only_keywords: list[str] | None = None,
        trim: str | None = None,
        trims_per_model: dict[str, list[str]] | None = None
    ) -> str:
        """
        Modelleri donanım açısından karşılaştırır, ancak her MODEL x TRIM
        kombinasyonunu ayrı sütun olarak gösterir.

        Tek model verilirse de çalışır; o modelin tüm trimlerini ayrı sütun yapar.
        """
        models = [m.lower() for m in models if m]
        if not models:          # 👈 eskiden len(models) < 2 ise return "" vardı, onu kaldırıyoruz
            return ""

        # Özellik sırası ve görünen isimler
        feature_order: list[str] = []
        feature_display: dict[str, str] = {}

        # Hücreler: feature_key -> { "Scala Elite": "Standart", ... }
        cell_status: dict[str, dict[str, str]] = {}

        # Sütun başlıkları (model + trim)
        col_headers: list[str] = []

        def pretty(code: str | None) -> str:
            if code == "S":
                return "Standart"
            if code == "O":
                return "Opsiyonel"
            return "-"

        for m in models:
            tname = self._latest_equipment_table_for(m)
            if not tname:
                continue

            # Bu model için tanımlı trim listesi
            all_trims_for_model = list(self.MODEL_VALID_TRIMS.get(m, []))

            # 1) Model başına özel trim listesi (örn. {'scala':['premium'], 'kamiq':['monte carlo']})
            chosen_trims: list[str] = []
            if trims_per_model and m in trims_per_model:
                wanted_norms = {
                    normalize_tr_text(t).lower()
                    for t in trims_per_model[m]
                }
                chosen_trims = [
                    t for t in all_trims_for_model
                    if normalize_tr_text(t).lower() in wanted_norms
                ]

            # 2) Ortak trim parametresi (scala ve kamiq premium karşılaştırma)
            elif trim:
                want = normalize_tr_text(trim).lower()
                chosen_trims = [
                    t for t in all_trims_for_model
                    if normalize_tr_text(t).lower() == want
                ]

            # 3) Hiçbiri yoksa: modelin tüm trimleri
            else:
                chosen_trims = all_trims_for_model

            if not chosen_trims:
                continue

            # Her trim için tabloyu ayrı sütun olarak işle
            for tr in chosen_trims:
                header = f"{m.title()} {tr.title()}"
                col_headers.append(header)

                order_keys, smap, dmap = self._equipment_dict_from_table(
                    tname,
                    preferred_trim=tr
                )

                for key in order_keys:
                    if key not in feature_order:
                        feature_order.append(key)
                    if key not in feature_display:
                        feature_display[key] = dmap.get(key, key)

                    cell_status.setdefault(key, {})[header] = pretty(smap.get(key, "—"))

        # Hiç sütun çıkmadıysa
                # Hiç sütun çıkmadıysa
        if not col_headers or not feature_order:
            return ""

        # Markdown tabloyu üret
        header_row = ["Özellik"] + col_headers
        lines = [
            "| " + " | ".join(header_row) + " |",
            "|" + "|".join(["---"] * len(header_row)) + "|",
        ]

        for key in feature_order:
            row_cells = [feature_display.get(key, key)]
            status_map_for_row = cell_status.get(key, {})
            for h in col_headers:
                row_cells.append(status_map_for_row.get(h, "-"))
            lines.append("| " + " | ".join(row_cells) + " |")

                # Hiçbir ekstra işlem yapmadan ham Markdown'u dön
        md = "\n".join(lines)

        # Debug için ilk 3 satırı logla (istersen bırak, ister kaldır)
        try:
            first_lines = md.splitlines()[:3]
            self.logger.info("[EQUIP-TBL] FIRST3:\n%s", "\n".join(first_lines))
        except Exception as _e:
            self.logger.error(f"[EQUIP-TBL] debug failed: {_e}")

        return md






    # =====================[ HYBRID RAG – Yardımcılar ]=====================

    # Embedding ayarları (ENV ile override edilebilir)
    def _embed_model_name(self) -> str:
        return os.getenv("EMBED_MODEL", "text-embedding-3-large")

    def _embed_dim(self) -> int:
        # text-embedding-3-large → 3072, küçük model kullanırsan değiştir
        try:
            return int(os.getenv("EMBED_DIM", "3072"))
        except:
            return 3072

    def _to_bytes_float32(self, vec: np.ndarray) -> bytes:
        assert vec.dtype == np.float32
        return vec.tobytes()

    def _from_bytes_float32(self, b: bytes) -> np.ndarray:
        return np.frombuffer(b, dtype=np.float32)

    def _cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        return float(np.dot(a, b) / denom) if denom > 0 else 0.0

    def _guess_model_for_query(self, s: str) -> str | None:
        if not s:
            return None
        t = normalize_tr_text(str(s)).lower()

        # 1) Normal cümle içinden (token güvenli)
        for m in ["fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"]:
            # kelime sınırları veya alfasayısal olmayan ayırıcılar
            if re.search(rf"(^|[^a-zçğıöşü]){m}([^a-zçğıöşü]|$)", t):
                return m.upper()

        # 2) TABLO ADLARINDAN (Örn: Imported_KODA_SCALA_MY_20251)
        m2 = re.search(r"koda[_\-](fabia|scala|kamiq|karoq|kodiaq|octavia|superb|enyaq|elroq)", t, re.I)
        if m2:
            return m2.group(1).upper()

        return None


    def _relevant_table_hints(self, query: str) -> list[str]:
        """
        Eski versiyonda tablo adı prefix'leri (PriceList, EquipmentList...) dönüyordu.
        Artık sadece mantıksal grup isimleri döndürüyoruz:
          - 'PRICE' → fiyat / fiyat listesi soruları
          - 'EQUIP' → donanım / opsiyon / paket soruları
          - 'SPEC'  → teknik veri / performans soruları
        Bu gruplar sadece skorlamada küçük bir bonus için kullanılıyor,
        hangi tablonun aranacağını FİLTRELEMİYOR.
        """
        q = (query or "").lower()
        groups: list[str] = []

        if any(k in q for k in ["fiyat", "anahtar teslim", "liste fiyat", "kampanya"]):
            groups.append("PRICE")

        if any(k in q for k in ["donanım", "donanim", "opsiyon", "opsiyonel", "paket", "özellik", "ozellik"]):
            groups.append("EQUIP")

        if any(k in q for k in [
            "teknik özellik", "teknik veri", "teknik veriler", "motor özellik",
            "performans", "0-100", "0 – 100", "0 100", "ivme", "hızlanma",
            "maksimum hız", "maks hiz", "menzil", "range", "tüketim", "tuketim",
            "l/100", "lt/100", "co2", "emisyon", "bagaj", "hacim", "dm3"
        ]):
            groups.append("SPEC")

        # Tekrarsız sırayı koru
        return list(dict.fromkeys(groups))



    def _row_to_text(self, table_name: str, row: dict) -> str:
        t = (table_name or "").lower()

        def add(*keys):
            out = []
            for k in keys:
                if k in row and row[k] not in (None, ""):
                    out.append(str(row[k]).strip())
            return out

        parts = []

        if t.startswith("equipmentlist_"):
            # Donanım tablosu → özellik + trim durumları
            parts.extend(add("Ozellik", "Özellik", "Donanim", "Donanım", "Equipment", "Name", "Title"))
            # Trim kolonlarını tek satıra özetle
            status_chunks = []
            for k, v in row.items():
                if k.lower() in ("id","model"):
                    continue
                if isinstance(v, str) and v.strip():
                    pretty_col = self._pretty_trim_header(k)  # Karoq Premium 1.5 TSI 150 PS DSG gibi
                    status_chunks.append(f"{pretty_col}: {v}")

            if status_chunks:
                parts.append(" | ".join(status_chunks))

        elif t.startswith("pricelist_"):
            # Fiyat tablosu → model + trim + açıklama + fiyatlar
            parts.extend(add("Model", "ModelName"))
            parts.extend(add("Trim", "Variant", "Donanim", "Donanım"))
            parts.extend(add("Aciklama", "Açıklama", "Description"))
            # Fiyat kolonları
            for k, v in row.items():
                lk = k.lower()
                if any(tok in lk for tok in ["fiyat", "price", "anahtar", "net_satis", "net satis"]):
                    if v not in (None, ""):
                        parts.append(f"{k}: {v}")
        elif t.startswith("model_segment_"):
            # Sadece Model + Segment alanlarını kullan
            parts.extend(add("Model"))
            parts.extend(add("Segment"))

        else:
            # Diğer tablolar için eski, genel davranış
            for k, v in row.items():
                if v is None:
                    continue
                s = str(v).strip()
                if s:
                    parts.append(f"{k}: {s}")

        return " | ".join(parts)


    # ------------------- Indexleme: Tablolardan KbVectors’a -------------------

    def _kb_index_one_table(self, table_name: str, limit: int = 10000) -> int:
        """
        Belirtilen tabloyu (örn. EquipmentList_KODA_FABIA_MY_20251) satır satır okuyup
        embedding üretir ve:
          - USE_MSSQL_NATIVE_VECTOR=1 ise → KbVectorsNative_* tablolarına,
          - değilse                        → KbVectors_* tablolarına
        yazar. Her tablo tipi için fiziksel vektör tablosu ayrıdır.
        """
        conn = self._sql_conn()
        cur  = conn.cursor()
        try:
            cur.execute(f"SELECT TOP {limit} * FROM [dbo].[{table_name}] WITH (NOLOCK)")
            cols = [c[0] for c in cur.description] if cur.description else []
            rows = cur.fetchall()
        except Exception as e:
            self.logger.error(f"[KB-IDX] {table_name} okunamadı: {e}")
            with contextlib.suppress(Exception): conn.close()
            return 0

        if not rows:
            with contextlib.suppress(Exception): conn.close()
            return 0

        docs, metas = [], []
        for r in rows:
            d = {cols[i]: r[i] for i in range(len(cols))}

            # ✅ row_key = kaynak tablodaki id
            row_id = d.get("id") if "id" in d else d.get("ID")
            row_key = str(row_id) if row_id is not None else None

            txt = self._row_to_text(table_name, d)
            if len(txt.strip()) < 5:
                continue

            model_slug = (self._guess_model_for_query(table_name) or
                        self._guess_model_for_query(txt) or
                        "GENERIC").upper()
            if len(txt.strip()) < 5:
                continue

            model_slug = (self._guess_model_for_query(table_name) or
                          self._guess_model_for_query(txt) or
                          "GENERIC").upper()

            tbl_lower = table_name.lower()
            if tbl_lower.startswith("pricelist_"):
                table_type = "PRICE"
                imp = 2
            elif tbl_lower.startswith("equipmentlist_"):
                table_type = "EQUIP"
                imp = 3
            elif tbl_lower.startswith("imported_") or "techspecs_" in tbl_lower:
                table_type = "SPEC"
                imp = 2
            else:
                table_type = "OTHER"
                imp = 1
            spec_key = None
            if table_type == "SPEC":
                oz = (
                    d.get("Ozellik") or d.get("Özellik") or d.get("SpecName") or
                    d.get("Name") or d.get("Title") or ""
                )
                spec_key = self._spec_key_from_text(str(oz)) or self._spec_key_from_text(txt)

            docs.append(txt)
            spec_key = None
            if table_type == "SPEC":
                # Satır başlığını yakala (Imported tablolarda genelde Ozellik)
                title = (
                    d.get("Ozellik") or d.get("Özellik") or d.get("SpecName") or
                    d.get("Name") or d.get("Title") or ""
                )
                # En genel: başlığı kanonikleştir (senin mevcut normalize/dedup fonksiyonun!)
                spec_key = self._normalize_spec_key_for_dedup(str(title))

            metas.append({
                "model":      model_slug,
                "src_table":  table_name,
                "row_key":    row_key,
                "table_type": table_type,
                "importance": imp,
                "spec_key":   spec_key,   # ✅ YENİ
            })

        if not docs:
            with contextlib.suppress(Exception): conn.close()
            return 0

        table_map = self._vector_tables_config()
        BATCH = 256
        inserted = 0

        for i in range(0, len(docs), BATCH):
            chunk = docs[i:i+BATCH]
            try:
                em = self.client.embeddings.create(
                    model=self._embed_model_name(),
                    input=chunk
                )
            except Exception as e:
                self.logger.error(f"[KB-IDX] embeddings error: {e}")
                break

            vecs = [np.array(it.embedding, dtype=np.float32) for it in em.data]

            for j, vec in enumerate(vecs):
                m = metas[i + j]
                text = chunk[j]
                logical_type = m["table_type"]
                target_table = table_map.get(logical_type, table_map.get("OTHER"))

                try:
                    if self.USE_MSSQL_NATIVE_VECTOR:
                        # Native VECTOR(…) tablo
                        cur.execute(f"""
                            INSERT INTO dbo.[{target_table}] (model, table_name, row_key, text, embedding)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            m["model"],
                            m["src_table"],
                            m["row_key"],
                            text,
                            vec.tolist(),  # VECTOR kolonu (MSSQL 2022)
                        ))
                    else:
                        # VARBINARY(…) tablo
                        # VARBINARY tabloya insert (spec_key kolonu varsa ekle)
                        has_spec_key_col = (logical_type == "SPEC") and self._sql_has_column(cur, target_table, "spec_key")

                        base_cols = ["model","table_name","row_key","text","dim","embedding","table_type","importance"]
                        base_vals = [
                            m["model"],
                            m["src_table"],
                            m["row_key"],
                            text,
                            int(vec.shape[0]),              # ✅ dim = query embedding dim ile uyumlu
                            self._to_bytes_float32(vec),
                            m["table_type"],
                            m["importance"],
                        ]

                        if has_spec_key_col:
                            base_cols.append("spec_key")
                            base_vals.append(m.get("spec_key"))

                        ph = ", ".join(["?"] * len(base_cols))
                        col_sql = ", ".join(base_cols)

                        cur.execute(
                            f"INSERT INTO dbo.[{target_table}] ({col_sql}) VALUES ({ph})",
                            base_vals
                        )

                    inserted += 1
                except Exception as e:
                    self.logger.error(f"[KB-IDX] insert fail ({table_name} -> {target_table}): {e}")

            conn.commit()

        with contextlib.suppress(Exception): conn.close()
        return inserted



    def _kb_index_all(self) -> dict:
        """
        sys.tables’tan dinamik olarak tüm PriceList_*, EquipmentList_*, Imported_* vb.
        tabloları tarar ve ilgili KbVectors_* tablolarına embedding yazar.
        """
        patterns = [
            r"PriceList\_KODA\_%",
            r"EquipmentList\_KODA\_%",
            r"Imported\_KODA\_%",
            r"Imported\_%",
            r"TechSpecs\_KODA\_%",
            r"MODEL_SEGMENT\_KODA\_%",
        ]
        conn = self._sql_conn()
        cur  = conn.cursor()
        tabs = []
        for pat in patterns:
            cur.execute("""
                SELECT t.name
                FROM sys.tables t
                WHERE t.name LIKE ? ESCAPE '\\'
                ORDER BY t.name
            """, (pat,))
            tabs += [r[0] for r in cur.fetchall()]
        with contextlib.suppress(Exception): conn.close()

        out = {}
        for t in tabs:
            try:
                n = self._kb_index_one_table(t, limit=10000)
                out[t] = n
                self.logger.info(f"[KB-IDX] {t} → {n} vektör")
            except Exception as e:
                self.logger.error(f"[KB-IDX] {t} hata: {e}")
                out[t] = 0
        return out


    # ------------------- Vektör Arama + Cevap -------------------

    def _kb_vector_search(self, query: str, k: int = 12, *, min_score: float | None = None, user_id: str | None = None):
        """
        Çoklu vektör tablosu (Equip / Price / Spec / Other) üzerinden arama yapar.
        - Her tablo için top-k aday alınır
        - Cosine skorlarına göre tek bir listeye birleştirilir
        - İlgili tablo grubu (PRICE/EQUIP/SPEC) için küçük skor bonusu verilir
        """
        # ✅ k parametresini sabit sayısal değişkene çevir
        try:
            k_num = int(float(k))
        except Exception:
            k_num = 12
        if k_num <= 0:
            k_num = 12
        # 1) Sorgu embedding
        try:
            from modules.trace_debug import span

            with span("LLM", "embeddings.create",
                    model=self._embed_model_name(),
                    in_chars=len(query or "")):
                qe = self.client.embeddings.create(
                    model=self._embed_model_name(),
                    input=query
                ).data[0].embedding

        except Exception as e:
            self.logger.error(f"[KB-SEARCH] embed fail: {e}")
            return []
        qv = np.array(qe, dtype=np.float32)
        query_spec_key = self._spec_key_from_query(query)

        # 1) Sorgu embedding
        try:
            from modules.trace_debug import span

            with span("LLM", "embeddings.create",
                    model=self._embed_model_name(),
                    in_chars=len(query or "")):
                qe = self.client.embeddings.create(
                    model=self._embed_model_name(),
                    input=query
                ).data[0].embedding

        except Exception as e:
            self.logger.error(f"[KB-SEARCH] embed fail: {e}")
            return []

        qv = np.array(qe, dtype=np.float32)

        # ✅ CRITICAL: dim'i ENV'den değil, sorgu embedding'inden al
        qdim = int(qv.shape[0])
        # ✅ Kullanıcının hangi teknik satır(lar)ı istediğini çıkar (örn. "Menzil (WLTP)")
        wanted_specs = []
        try:
            wanted_specs = self._find_requested_specs(query) or []
        except Exception:
            wanted_specs = []

        # KbVectors_Spec’te tuttuğumuz spec_key formatına çevir
        wanted_spec_keys = []
        for w in wanted_specs:
            try:
                spec_key_norm = self._normalize_spec_key_for_dedup(w)[:120]  # ✅ k değil

                if spec_key_norm:
                    wanted_spec_keys.append(spec_key_norm)
            except Exception:
                pass

        # tekilleştir
        wanted_spec_keys = list(dict.fromkeys(wanted_spec_keys))

        self.logger.info(f"[KB-SEARCH] embed_model={self._embed_model_name()} qdim={qdim} (ENV_EMBED_DIM={os.getenv('EMBED_DIM')})")

        # 2) Model ipucu
        models_in_q = list(self._extract_models(query))
        models_in_q = [m.upper() for m in models_in_q]

        if not models_in_q and user_id:
            last_models = (self.user_states.get(user_id, {}) or {}).get("last_models", set())
            if last_models:
                models_in_q = [m.upper() for m in last_models]

        model_hint = (self._guess_model_for_query(query) or "").upper()
        if model_hint and model_hint not in models_in_q:
            models_in_q.append(model_hint)

        # 3) Hangi grup daha alakalı?  (sadece bonus için)
        relevant_groups = self._relevant_table_hints(query)
        table_map = self._vector_tables_config()

        results: list[tuple[float, dict]] = []

        # ---------- A) Native MSSQL VECTOR araması ----------
        if getattr(self, "USE_MSSQL_NATIVE_VECTOR", False):
            import json as _json
            q_json = _json.dumps(qv.tolist())
            try:
                conn = self._sql_conn()
                cur  = conn.cursor()

                for group, phys_table in table_map.items():
                    where = []
                    params = []

                    # ✅ DIM filtresi (stabilite)
                    where.append("dim = ?")
                    params.append(self._embed_dim())
                    # ✅ SPEC tablosunda: aranan metrik(ler) belliyse spec_key ile filtrele
                    if group == "SPEC" and wanted_spec_keys and self._sql_has_column(cur, phys_table, "spec_key"):
                        where.append("(" + " OR ".join(["spec_key = ?"] * len(wanted_spec_keys)) + ")")
                        params.extend(wanted_spec_keys)

                    if group == "SPEC" and query_spec_key:
                        where.append("spec_key = ?")
                        params.append(query_spec_key)

                    # ✅ model filtresi
                    if models_in_q:
                        if len(models_in_q) == 1:
                            where.append("model = ?")
                            params.append(models_in_q[0])
                        else:
                            where.append("(" + " OR ".join(["model = ?"] * len(models_in_q)) + ")")
                            params.extend(models_in_q)

                    where_sql = "WHERE " + " AND ".join(where) if where else ""


                    where_sql = "WHERE " + " AND ".join(where) if where else ""

                    sql = f"""
                        DECLARE @q_json NVARCHAR(MAX) = ?;
                        DECLARE @q VECTOR({self.MSSQL_VECTOR_DIM}) =
                            CAST(JSON_VALUE(@q_json, '$') AS VECTOR({self.MSSQL_VECTOR_DIM}));

                        SELECT TOP {k_num}
                            id, model, table_name, text,
                            1.0 - (embedding <-> @q) AS score
                        FROM dbo.[{phys_table}] WITH (NOLOCK)
                        {where_sql}
                        ORDER BY embedding <-> @q;
                        """
                    try:
                        cur.execute(sql, [q_json] + params)
                        rows = cur.fetchall()
                    except Exception as e:
                        self.logger.error(f"[KB-SEARCH] native query failed on {phys_table}: {e}")
                        continue

                    for r in rows:
                        base_score = float(r[4])
                        bonus = 0.03 if group in relevant_groups else 0.0
                        results.append((base_score + bonus, {
                            "id":    r[0],
                            "model": r[1],
                            "table": r[2],
                            "text":  r[3],
                            "group": group,
                        }))

                with contextlib.suppress(Exception): conn.close()
            except Exception as e:
                self.logger.error(f"[KB-SEARCH] native vector search failed, fallback python: {e}")
                # Python cosine fallback aşağıda çalışacak
                results = []

        # ---------- B) VARBINARY (Python cosine) araması ----------
        # ---------- B) VARBINARY (Python cosine) araması ----------
        # ---------- B) VARBINARY (Python cosine) araması ----------
        # ---------- B) VARBINARY (Python cosine) araması ----------
        if not results and not getattr(self, "USE_MSSQL_NATIVE_VECTOR", False):
            conn = self._sql_conn()
            cur  = conn.cursor()
            try:
                SCAN = int(os.getenv("KB_SCAN_LIMIT", "5000"))

                for group, phys_table in table_map.items():
                    where = []
                    params = []

                    # ✅ 1) DIM filtresi (query'nin gerçek dim'i)
                    where.append("dim = ?")
                    params.append(qdim)

                    # ✅ 2) Model filtresi
                    if models_in_q:
                        if len(models_in_q) == 1:
                            where.append("model = ?")
                            params.append(models_in_q[0])
                        else:
                            where.append("(" + " OR ".join(["model = ?"] * len(models_in_q)) + ")")
                            params.extend(models_in_q)

                    where_sql = "WHERE " + " AND ".join(where) if where else ""

                    cur.execute(f"""
                        SELECT TOP {SCAN}
                            id, model, table_name, row_key, text, dim, embedding, table_type, importance
                        FROM dbo.[{phys_table}] WITH (NOLOCK)
                        {where_sql}
                        ORDER BY id DESC
                    """, params)

                    rows = cur.fetchall()
                    self.logger.info(f"[KB-SEARCH] table={phys_table} rows={len(rows)} where={where_sql} params={params}")

                    # ✅ Debug sayaçları (çok işe yarar)
                    skipped_null = 0
                    skipped_dim  = 0
                    used         = 0

                    for r in rows:
                        raw = r[6]
                        if raw is None:
                            skipped_null += 1
                            continue

                        # pyodbc VARBINARY bazen memoryview döner
                        b = raw.tobytes() if hasattr(raw, "tobytes") else bytes(raw)

                        emb = self._from_bytes_float32(b)

                        if emb.size != qdim:
                            skipped_dim += 1
                            continue

                        base_score = self._cosine(qv, emb)
                        bonus = 0.03 if group in relevant_groups else 0.0
                        score = base_score + bonus

                        results.append((score, {
                            "id":         r[0],
                            "model":      r[1],
                            "table":      r[2],
                            "row_key":    r[3],
                            "text":       r[4],
                            "group":      group,
                            "table_type": r[7],
                            "importance": r[8],
                        }))
                        used += 1

                    self.logger.info(
                        f"[KB-SEARCH] table={phys_table} used={used} skipped_null={skipped_null} skipped_dim={skipped_dim} qdim={qdim}"
                    )

            finally:
                with contextlib.suppress(Exception):
                    conn.close()



        if not results:
            return []

        # 4) Skor sıralaması ve eşik
        results.sort(key=lambda x: x[0], reverse=True)
        best = results[0][0]

        kb_floor = float(os.getenv("KB_MIN_SIM", "0.4"))

        if min_score is not None:
            # ✅ relax çağrısında min_score neyse onu kullan
            MIN_SCORE = float(min_score)
        else:
            base_min = kb_floor
            q_norm = (query or "").lower()
            if any(w in q_norm for w in ["tork","güç","guc","beygir","0-100","hız","hiz","menzil","co2","tüketim","tuketim"]):
                base_min += 0.05
            if any(w in q_norm for w in ["karşılaştır","kıyas","vs","vs."]) and len(models_in_q) >= 2:
                base_min -= 0.05
            MIN_SCORE = min(base_min, 0.70)
        # _kb_vector_search içinde, best ve MIN_SCORE hesaplandıktan sonra
        self.logger.info(
            f"[KB-SEARCH] best={best:.3f} MIN_SCORE={MIN_SCORE:.3f} "
            f"results={len(results)} models_in_q={models_in_q} relevant_groups={relevant_groups}"
        )
        from modules.trace_debug import tracer
        tracer().step("VECTOR_BEST",
                    best=round(float(best), 3),
                    min_score=round(float(MIN_SCORE), 3),
                    total=len(results))
        top3 = []
        try:
            top3 = [
                (round(float(s), 3),
                (d.get("group"), d.get("table"), (d.get("text","")[:120] or "")))
                for s, d in results[:3]
            ]
        except Exception:
            pass

        tracer().step("VECTOR_TOP3", hits=top3)

        if best < MIN_SCORE:
            self.logger.info(f"[KB-SEARCH] best_score={best:.3f} < {MIN_SCORE}, boş dönüyorum. q={query!r}")
            return []

        # 5) En iyi k tanesini döndür (tüm tabloları dolaşarak)
        top = []
        q_norm2 = normalize_tr_text(query).lower()
        q_tokens = re.findall(r"[0-9a-zçğıöşü]+", q_norm2)

        # Teknik/metrik sorularda "kısa soru" bypass'ını KAPAT
        is_spec_q = any(w in q_norm2 for w in [
            "menzil","range",
            "tork","güç","guc","beygir","hp","ps","kw",
            "0-100","ivme","hızlanma",
            "maksimum hız","maks hiz","max speed","top speed",
            "tüketim","tuketim","l/100","lt/100","co2","emisyon",
            "bagaj","ağırlık","agirlik"
        ])

        is_generic_equip_list = (
            ("donanim" in q_norm2 or "donanım" in q_norm2)
            and any(w in q_norm2 for w in ["nelerdir", "neler", "listesi", "liste", "hepsi", "tumu", "tümü", "tamami", "tamamı", "öne çıkan", "one cikan"])
        )

        # Sadece fiyat veya genel donanım listesi ise bypass; teknik soruda asla bypass yok
        bypass_safe = self._is_price_intent(query) or is_generic_equip_list

        # Sadece teknik değilse ve çok kısaysa bypass aç
        if (len(q_tokens) <= 3) and (not is_spec_q):
            bypass_safe = True


        is_generic_equip_list = (
            ("donanim" in q_norm2 or "donanım" in q_norm2)
            and any(w in q_norm2 for w in ["nelerdir", "neler", "listesi", "liste", "hepsi", "tumu", "tümü", "tamami", "tamamı", "öne çıkan", "one cikan"])
        )

        bypass_safe = bypass_safe or is_generic_equip_list

        for score, meta in results:
            if score < MIN_SCORE:
                continue

            if (not bypass_safe) and (not self._safe_kb_hit(query, meta["text"])):
                continue

            top.append((score, meta))
            if len(top) >= k_num:

                break

        return top




    def _answer_with_hybrid_rag(self, query: str, user_id: str | None = None, relax_filters: bool = False,
                           force_table_read: bool = False) -> str:        
        if getattr(self, "KB_ONLY", False):
        # KB_ONLY modunda asla kaynak tabloya postfetch yapma
            os.environ["KB_POSTFETCH"] = "0"
        if getattr(self, "STRICT_SQL_ONLY", False):
            return ""

        # 'özet / donanım öne çıkan' gibi sorularda skoru biraz gevşet
        min_score = 0.30 if relax_filters else None
        top_raw = self._kb_vector_search(query, k=30, min_score=min_score, user_id=user_id)
        # _answer_with_hybrid_rag içinde, top_raw boş değilse
        if getattr(self, "KB_ONLY", False) and os.getenv("KB_ONLY_RETURN_RAW", "1") == "1":
            # ✅ LLM'ye bile gitmeden ham kanıtı göster
            lines = []
            seen = set()
            for s, d in top_raw:
                key = (d.get("table"), d.get("row_key"), (d.get("text","")[:120] or ""))
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"- ({s:.3f}) [{d.get('group')}] {d.get('text','')[:400]}")
                if len(lines) >= 8:
                    break
            return "KbVectors eşleşmeleri:\n" + "\n".join(lines)


        if not top_raw:
            # ✅ KB_ONLY ise asistana kaçma
            if getattr(self, "KB_ONLY", False):
                return "KbVectors tablosunda bu soruya karşılık gelen kayıt bulunamadı."
            return self._fallback_via_assistant(user_id, query, reason="KbVectors hit yok / düşük skor")

         # ✅ KB hit'i buldukysa, mümkünse SQL’den satırı geri çekip zengin cevap üret
        try:
            if (not getattr(self, "KB_ONLY", False)) and os.getenv("KB_POSTFETCH", "1") == "1" and top_raw:
                best_score, best = top_raw[0]
                tname = best.get("table")
                rkey  = best.get("row_key")
                grp   = best.get("group")

                # Sadece EQUIP/SPEC/PRICE için postfetch anlamlı
                if grp in {"EQUIP", "SPEC", "PRICE"} and tname and rkey:
                    row = self._kb_postfetch_row(tname, str(rkey))
                    if row:
                        # 1) EQUIP: trim kolonlarından Standart/Opsiyonel/Yok çıkar
                        if grp == "EQUIP":
                            # trim kolonları: id/model/ozellik dışındakiler
                            feat = row.get("Ozellik") or row.get("Özellik") or row.get("Donanim") or row.get("Donanım")
                            trim_cols = [c for c in row.keys() if c not in ("id", "ID", "Model", "Ozellik", "Özellik", "Donanim", "Donanım")]
                            status_map = {c: self._normalize_equipment_status(row.get(c)) for c in trim_cols}
                            # küçük, anlaşılır cevap (istersen tablo+NLG yaparsın)
                            s = self._nlg_equipment_status(
                                model_name=(self._guess_model_for_query(tname) or "").lower(),
                                feature=str(feat or "Sorgulanan donanım"),
                                trims=trim_cols,
                                status_map=status_map,
                            )
                            if s:
                                return s

                        # 2) SPEC: kullanıcı “0-100 / tork / güç …” soruyorsa aynı satırdan trim değerlerini dökebilirsin
                        # (şimdilik fallthrough -> LLM context)
        except Exception as e:
            self.logger.error(f"[KB_POSTFETCH] error: {e}")

        # ⬇⬇⬇ YENİ BLOK: EQUIP yok, PRICE var ise "standart değil" de ⬇⬇⬇
        if top_raw and self._is_equipment_presence_question(query):
            has_equip = any(d.get("group") == "EQUIP" for _, d in top_raw)
            has_price = any(d.get("group") == "PRICE" for _, d in top_raw)

            # Donanım tablosunda hiçbir hit yok ama fiyat tablosunda var
            if (not has_equip) and has_price:
                model = None
                try:
                    model = self._current_model(user_id, query)
                except Exception:
                    pass
                if not model:
                    model = (self._guess_model_for_query(query) or "").lower() or None

                if model:
                    prefix = f"{model.title()} modelinde "
                else:
                    prefix = ""

                return (
                    f"{prefix}sorduğunuz bu özellik standart donanım listesinde görünmüyor. "
                    "Ancak fiyat / opsiyon listesinde geçtiği için, standart değil; "
                    "opsiyonel bir ekipman olarak sunuluyor diyebilirim. "
                    "Yani aracı alırken ilgili opsiyon/ paket seçeneğini işaretlemeniz gerekir."
                )


        adjusted = []
        for score, d in top_raw:
            imp = d.get("importance", 1)
            bonus = 0.02 * (imp - 1)
            adjusted.append((score + bonus, d))
        adjusted.sort(key=lambda x: x[0], reverse=True)

        q_norm = normalize_tr_text(query).lower()

        if relax_filters or "segment" in q_norm:
            # Güvenlik filtresi kapalı: tüm top-k bağlamı kullan
            top = adjusted
        else:
            top = [(s, d) for (s, d) in adjusted
                if self._safe_kb_hit(query, d["text"])]

        if not top:
            return "Üzgünüm araçla ilgili bilgiyi bulamadım. Dilerseniz başka bir konuda yardımcı olabilirim."

        # ✅ ratio ~0.5 ise: KB hit'lerinin içinden tablo yakala ve en öne koy
        tables_blob = ""
        if force_table_read:
            try:
                tables = []
                for s, d in top:
                    txt = d.get("text") or ""
                    for t in self.extract_tables_any(txt):
                        if t.get("text"):
                            tables.append(t)

                qn = normalize_tr_text(query).lower()
                wanted_kind = None
                if ("opsiyon" in qn) or self._is_price_intent(query):
                    wanted_kind = "optional"
                elif ("donan" in qn) or self._is_equipment_presence_question(query):
                    wanted_kind = "standard"

                picked = None
                if wanted_kind:
                    cand = [x["text"] for x in tables if x.get("kind") == wanted_kind]
                    if cand:
                        picked = cand[0]

                if not picked and tables:
                    picked = tables[0]["text"]

                if picked:
                    if self._approx_tokens(picked) > 2500:
                        picked = "\n".join(picked.splitlines()[:60])

                    tables_blob = (
                        "\n\n[FOUND_TABLE]\n"
                        "Aşağıdaki tabloyu mutlaka okuyup cevap üret:\n"
                        f"{picked}\n"
                    )
            except Exception as e:
                self.logger.error(f"[RAG-TABLE] table extraction failed: {e}")
                tables_blob = ""

        # Aşağıdaki kısım aynen kalsın (context oluşturma + chat.completions)
        context = "\n".join([f"- [{round(s,3)}] {d['text']}" for s, d in top])
        if tables_blob:
            context = tables_blob + "\n\n[OTHER_CONTEXT]\n" + context


        sys = (
            "You are a Turkish digital automotive sales consultant working for Škoda Türkiye. "
            "Her zaman akıcı TÜRKÇE cevap ver. "
            "Cevapların bir showroom veya dijital satış görüşmesindeymiş gibi sıcak, güven verici "
            "ve ikna edici olsun. "
            "Ancak SOMUT BİLGİLERİ sadece aşağıdaki bağlamdan al; bağlamda yer almayan yeni teknik "
            "özellik, donanım veya rakam UYDURMA.\n\n"
            "Kurallar:\n"
            "- Önce soruyu net bir şekilde yanıtla (var/yok, hangi versiyonda geçerli vb.).\n"
            "- Ardından bu özelliğin veya bilginin günlük kullanımda müşteriye ne hissettireceğini, "
            "hangi ihtiyacı çözdüğünü 1–3 cümle ile anlat.\n"
            "- Bağlamda geçen sayı ve birimleri aynen koru; değiştirme.\n"
            "- Eğer bağlamda ilgili bilgi yoksa, kibarca 'veritabanında karşılığı bulunamadı' de.\n"
            "- Cevabı 2–4 cümle aralığında tut ve son cümleyi kısa, doğal bir soruyla bitir "
            "(örn. 'Sizin kullanımınız için böyle bir özellik ne kadar önemli olurdu?')."
        )

        usr = (
            f"Kullanıcı sorusu: {query}\n\n"
            "Aşağıda, SQL tabanlı bilgi kaynağından gelen bağlam yer alıyor. "
            "Lütfen sadece bu bağlama dayanarak cevap üret:\n"
            f"{context}"
        )

        try:
            resp = self.client.chat.completions.create(
                model=os.getenv("GEN_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": usr},
                ],
                temperature=0.4,
                max_tokens=220,
            )
            text = (resp.choices[0].message.content or "").strip()
            return text
        except Exception as e:
            self.logger.error(f"[KB-ANS] chat fail: {e}")
            return ""


        

     

    def _sql_conn(self):
        """
        MSSQL'e güvenli bağlantı açar. Öncelik: SQLSERVER_CONN_STR env var.
        Dönüş: pyodbc.Connection
        """
        if pyodbc is None:
            raise RuntimeError("pyodbc yüklü değil. `pip install pyodbc` ile kurun.")

        cs = os.getenv("SQLSERVER_CONN_STR", "").strip()
        if not cs:
            # (Geliştirici ortamı için güvenli olmayan fallback – PROD'da .env kullanın)
            cs = (
                "DRIVER={ODBC Driver 17 for SQL Server};"
                "SERVER=10.0.0.20\\SQLYC;"
                "DATABASE=SkodaBot;"
                "UID=skodabot;"
                "PWD=Skodabot.2024;"
            )
        from modules.trace_debug import traced_sql_conn
        conn = pyodbc.connect(cs)
        return traced_sql_conn(conn)

    # --- SQL'den KB tablolarını topla
    def _fetch_kb_tables_from_sql(self) -> dict[str, list[dict]]:
        """
        Yeni: sadece EquipmentList_, Imported_ ve PriceList_ tablolarını okur.
        """
        tables = [
            "EquipmentList_KODA_FABIA_MY_20251",
            "EquipmentList_KODA_KAMIQ_MY_20251",
            "EquipmentList_KODA_KAROQ_MY_20251",
            "EquipmentList_KODA_KODIAQ_MY_20251",
            "EquipmentList_KODA_OCTAVIA_MY_20251",
            "EquipmentList_KODA_SCALA_MY_20251",
            "EquipmentList_KODA_SUPERB_MY_20251",
            "Imported_Elroq1",
            "Imported_Enyaq1",
            "Imported_KODA_ELROQ_MY_20251",
            "Imported_KODA_ENYAQ__ENYAQ_Coup1",
            "Imported_KODA_FABIA_MY_20251",
            "Imported_KODA_KAMIQ_MY_20251",
            "Imported_KODA_OCTAVIA_MY_20251",
            "Imported_KODA_SCALA_MY_20251",
            "PriceList_KODA_ELROQ_MY_20251",
            "PriceList_KODA_ENYAQ__ENYAQ_Coup1",
            "PriceList_KODA_FABIA_MY_20251",
            "PriceList_KODA_KAMIQ_MY_20251",
            "PriceList_KODA_KAROQ_MY_20251",
            "PriceList_KODA_KODIAQ_MY_20251",
            "PriceList_KODA_OCTAVIA_MY_20251",
            "PriceList_KODA_SCALA_MY_20251",
            "PriceList_KODA_SUPERB_MY_20251",
            "MODEL_SEGMENT_KODA_MY_20251",
        ]

        out: dict[str, list[dict]] = {}
        try:
            conn = self._sql_conn()
            cur = conn.cursor()
            for fqtn in tables:
                try:
                    cur.execute(f"SELECT * FROM {fqtn}")
                    cols = [c[0] for c in cur.description] if cur.description else []
                    rows = cur.fetchall()
                    out[fqtn] = [dict(zip(cols, map(self._safe_cell, r))) for r in rows]
                    self.logger.info(f"[SQL] {fqtn}: {len(out[fqtn])} satır")
                except Exception as e:
                    self.logger.error(f"[SQL] {fqtn} okunamadı: {e}")
                    out[fqtn] = []
        finally:
            with contextlib.suppress(Exception): cur.close()
            with contextlib.suppress(Exception): conn.close()
        return out


    def _safe_cell(self, v):
        """SQL hücresini yazılabilir string'e çevirir (None → '—'; pipes kaçışlanır)."""
        if v is None:
            return "—"
        s = str(v)
        # Markdown boru kaçırma (| → \|)
        return s.replace("|", "\\|")

    # --- Yardımcı: satır listesi → Markdown tablo
    def _rows_to_markdown_table(self, rows: list[dict], *, prefer_cols: list[str] | None = None, chunk: int = 1000) -> str:
        """
        Büyük tabloları parça parça Markdown'a çevirir. prefer_cols başa alınır.
        chunk: satır başına maksimum satır sayısı (büyük veride parçalara böler).
        """
        if not rows:
            return "_(Kayıt bulunamadı)_\n"

        # Kolon sıralaması (model/trim/spec/value gibi alanları öne al)
        cols = list(rows[0].keys())
        prefer = [c for c in (prefer_cols or []) if c in cols]
        rest = [c for c in cols if c not in prefer]
        cols = prefer + rest

        def render_block(block_rows: list[dict]) -> str:
            header = "| " + " | ".join(cols) + " |"
            sep    = "|" + "|".join(["---"] * len(cols)) + "|"
            body   = []
            for r in block_rows:
                body.append("| " + " | ".join(self._safe_cell(r.get(c, "—")) for c in cols) + " |")
            return "\n".join([header, sep] + body)

        md_parts = []
        for i in range(0, len(rows), chunk):
            part = rows[i:i+chunk]
            md_parts.append(render_block(part))
        return "\n\n".join(md_parts) + "\n"

    # --- SQL verisini alan adı başlıklarıyla bölümlere ayırıp Markdown üret
    def _export_openai_kb_from_sql(self) -> list[str]:
        """
        _fetch_kb_tables_from_sql() ile çekilen:
        - EquipmentList_*
        - Imported_*
        - PriceList_*
        tablolarını Markdown'a çevirip /static/kb altına yazar.

        Dönüş: Üretilen dosyaların tam yol listesi.
        """
        import os
        import re

        data = self._fetch_kb_tables_from_sql()
        out_dir = os.path.join(self.app.static_folder, "kb")
        os.makedirs(out_dir, exist_ok=True)

        file_paths: list[str] = []

        # ---- Yardımcılar ---------------------------------------------------------
        def _classify(tbl_name: str) -> str:
            """Tablo adından tip çıkar (equipment/price/imported/other)."""
            t = (tbl_name or "").lower()
            if t.startswith("equipmentlist_"):
                return "equipment"
            if t.startswith("pricelist_"):
                return "price"
            if t.startswith("imported_"):
                return "imported"
            return "other"

        def _human_title(tbl_name: str) -> str:
            """Markdown başlığı için okunur bir başlık üret."""
            cls = _classify(tbl_name)
            prefix = {
                "equipment": "Donanım Listesi",
                "price": "Fiyat Listesi",
                "imported": "İthal/Ürün Aktarım",
                "other": "Tablo",
            }.get(cls, "Tablo")
            pretty = tbl_name.replace("__", "_").replace("_", " ").strip()
            return f"{prefix} — {pretty}"

        def _prefer_cols_for(tbl_name: str, cols: list[str]) -> list[str]:
            """
            Kolon sırası: tablo tipine göre anlamlı kolonları öne al,
            diğerlerini orijinal adlarıyla sona ekle.
            """
            low_to_orig = {c.lower(): c for c in cols}

            def _resolve(order: list[str]) -> list[str]:
                ordered, seen = [], set()
                for want in order:
                    key = want.lower()
                    if key in low_to_orig and low_to_orig[key] not in seen:
                        ordered.append(low_to_orig[key])
                        seen.add(low_to_orig[key])
                for c in cols:
                    if c not in seen:
                        ordered.append(c)
                        seen.add(c)
                return ordered

            common = ["Model", "ModelName", "Trim", "Variant", "Name", "Title", "Description"]

            cls = _classify(tbl_name)
            if cls == "equipment":
                prefer = [
                    "Model", "ModelName", "Trim", "Variant",
                    "Equipment", "Donanim", "Name", "Title",
                    "Status", "StdOps", "Value", "Code", "Description",
                ]
            elif cls == "price":
                prefer = [
                    "Model", "ModelName", "Trim", "Variant",
                    "Body", "Fuel", "Powertrain",
                    "Price", "ListPrice", "AnahtarTeslim", "Currency",
                    "EffectiveDate",
                ]
            elif cls == "imported":
                prefer = [
                    "Model", "ModelName", "Trim", "Variant",
                    "Attribute", "Name", "Title",
                    "Value", "Unit", "Code", "Description",
                ]
            else:
                prefer = common + ["Value", "Unit", "Price"]

            return _resolve(prefer)

        # ---- Markdown üretimi -----------------------------------------------------
        for tbl_name, rows in (data or {}).items():
            if not rows:
                self.logger.warning(f"[SQL→MD] {tbl_name}: boş/okunamadı, atlandı.")
                continue

            cols = list(rows[0].keys()) if isinstance(rows[0], dict) else []
            prefer_cols = _prefer_cols_for(tbl_name, cols)

            title = f"# {_human_title(tbl_name)}\n\n"
            md = title + self._rows_to_markdown_table(rows, prefer_cols=prefer_cols, chunk=1200)

            # Dosya adı güvenli hale getir
            safe_file = re.sub(r"[^0-9A-Za-z_.-]+", "_", f"{tbl_name}.sql.md")
            out_path = os.path.join(out_dir, safe_file)

            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(md)
                file_paths.append(out_path)
                self.logger.info(f"[SQL→MD] yazıldı: {out_path} (rows={len(rows)})")
            except Exception as e:
                self.logger.error(f"[SQL→MD] {tbl_name} yazılamadı: {e}")

        # Hiç dosya oluşmadıysa bilgilendirici placeholder
        if not file_paths:
            placeholder = os.path.join(out_dir, "KB_EMPTY.sql.md")
            with open(placeholder, "w", encoding="utf-8") as f:
                f.write("# SQL Çıktısı Boş\n\nSeçili tablolar okunamadı veya satır getirmedi.\n")
            file_paths.append(placeholder)
            self.logger.warning("[SQL→MD] kayıt yok, KB_EMPTY.sql.md üretildi.")

        self.logger.info(f"[SQL→MD] Toplam {len(file_paths)} dosya üretildi.")
        return file_paths

    def _is_image_intent_local(self, text: str) -> bool:
        """
        Görsel niyetini yerelde tespit eder (utils.is_image_request'e ek destek).
        - Eşanlamlılar (görsel/resim/foto/fotograf/fotoğraf...) varsa True
        - Veya 'göster / nasıl görün...' fiilleri + bir model adı birlikte geçiyorsa True
        """
        t = normalize_tr_text(text or "").lower()
        if self.IMAGE_SYNONYM_RE.search(t):
            return True

        has_verb = (
            re.search(r"\bg[öo]ster(?:ir|)\b", t) or
            re.search(r"nas[ıi]l\s+g[öo]r[üu]n", t)
        )
        return bool(has_verb and self._extract_models(t))

    def _strip_source_mentions(self, text: str) -> str:
        """
        Yanıtta olabilecek tüm 'kaynak' izlerini temizler:
        - Özel citation token'ları
        - 【...】 biçimli referanslar
        - [1], [1,2] gibi numaralı dipnotlar
        - 'Kaynak:', 'Source:', 'Referans:' ile başlayan satırlar
        - Satır içi '(Kaynak: ...)' parantezleri
        (Tablo, HTML ve normal metinle güvenli şekilde çalışır.)
        """
        import re
        if not text:
            return text

        s = text

        # 1) Özel citation token'ları
        s = re.sub(r"]+", "", s)
        s = re.sub(r"]+", "", s)

        # 2) '【...】' tarzı referans blokları
        s = re.sub(r"【[^】]+】", "", s)

        # 3) 'turn...' gibi çalışma id'leri (gözükürse)
        s = re.sub(r"\bturn\d+\w+\d+\b", "", s)

        # 4) [1], [1,2] vb. numaralı dipnotlar
        s = re.sub(r"\[\s*\d+(?:\s*[-,;]\s*\d+)*\s*\]", "", s)

        # 5) Satır başında 'Kaynak:' / 'Source:' / 'Referans:' / 'Citation:'
        s = re.sub(r"(?im)^(?:kaynak|source|referans|citation)s?\s*:\s*.*$", "", s)

        # 6) Satır içi '(Kaynak: ...)' / '(Source: ...)'
        s = re.sub(r"(?i)\(\s*(?:kaynak|source|referans|citation)s?\s*:\s*[^)]+\)", "", s)

        # 7) Görsel/biçim temizliği
        s = re.sub(r"[ \t]+\n", "\n", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
        s = re.sub(r"[ \t]{2,}", " ", s)
        # .sql.md veya dosya adı geçen köşeli parantez bloklarını kaldır
        s = re.sub(r"\[[^\]]*\.sql\.md[^\]]*\]", "", s)
        # Dosya yolu/uzantı izlerini sadele (ör. PriceList_*.md, .csv, .xlsx vs.)
        s = re.sub(r"\[[^\]]*\.(?:md|csv|xlsx|json|sql)[^\]]*\]", "", s)

        return s.strip()


    def _sanitize_bytes(self, payload) -> bytes:
        if isinstance(payload, (bytes, bytearray)):
            s = payload.decode("utf-8", errors="ignore")
        else:
            s = str(payload or "")

        # ✅ önce bu
        s = self._strip_forbidden_ui_blocks(s)

        if getattr(self, "HIDE_SOURCES", False):
            s = self._strip_source_mentions(s)

        return s.encode("utf-8")


    def _enforce_assertive_tone(self, text: str) -> str:
        """
        Yumuşak/çekingen dili azaltır; kesin yargı tonunu güçlendirir.
        Aşırıya kaçmadan, tipik hedging kalıplarını törpüler.
        """
        if not getattr(self, "ASSERTIVE_MODE", False) or not text:
            return text

        import re
        s = text

        # Yumuşatıcı/çekingen kalıpları azalt
        patterns = [
            (r"\bmuhtemelen\b", ""), 
            (r"\bolabilir\b", "dır"),
            (r"\bolası\b", ""), 
            (r"\bgenellikle\b", ""),
            (r"\bçoğu durumda\b", ""),
            (r"\b(eğer|şayet)\b", ""),  # şartlı açılışları sadeleştir
            (r"\bgibi görünüyor\b", "dır"),
            (r"\bgörece\b", ""),
            (r"\btahmini\b", ""),
        ]
        for pat, repl in patterns:
            s = re.sub(pat, repl, s, flags=re.IGNORECASE)

        # Fazla boşlukları toparla
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n{3,}", "\n\n", s).strip()
        return s

    def _normalize_enyaq_trim(self, t: str) -> str:
        """
        JSONL'den gelen 'trim' değerini kanonik hale getirir.
        Örn: 'es60', 'e sportline 60' -> 'e sportline 60'
            'ces60', 'coupe e sportline 60' -> 'coupe e sportline 60'
        """
        t = (t or "").strip().lower()
        if not t:
            return ""
        # VARIANT_TO_TRIM ve normalize_trim_str proje içinde mevcut
        if t in VARIANT_TO_TRIM:
            return VARIANT_TO_TRIM[t]
        for v in normalize_trim_str(t):
            if v in VARIANT_TO_TRIM:
                return VARIANT_TO_TRIM[v]
        # Enyaq’ın tanımlı trim’leriyle en yakın kanoniği seç
        for canon in (self.MODEL_VALID_TRIMS.get("enyaq", []) or []):
            variants = normalize_trim_str(canon)
            if t in variants or any(v in t or t in v for v in variants):
                return canon
        return t


    def _load_enyaq_ops_from_jsonl(self, path: str) -> dict[str, str]:
        """
        /mnt/data/... JSONL dosyasını okur, her trim için Markdown döndürür.
        Kabul edilen alanlar (satır başına JSON objesi):
        - 'trim' / 'variant' / 'donanim' (trim adı)
        - 'markdown'/'md' (doğrudan md)
        - 'table' (liste-liste; ilk satır başlık)
        - 'features' ( [{'name':..,'status':..}] veya ['Yan perde hava yastığı', ...] )
        - 'items' (['...','...'])
        - Diğer anahtarlar -> Özellik/Değer tablosu
        """
        import json, os
        out: dict[str, str] = {}
        if not path or not os.path.exists(path):
            return out

        def to_md_from_table(rows):
            if not isinstance(rows, list) or not rows:
                return ""
            if isinstance(rows[0], list):
                header = [str(c) for c in rows[0]]
                lines = ["| " + " | ".join(header) + " |",
                        "|" + "|".join(["---"] * len(header)) + "|"]
                for r in rows[1:]:
                    if isinstance(r, list):
                        lines.append("| " + " | ".join(str(c) for c in r) + " |")
                return "\n".join(lines)
            return ""

        def to_md_from_features(feats):
            if not isinstance(feats, list) or not feats:
                return ""
            lines = ["| Özellik | Durum |", "|---|---|"]
            for it in feats:
                if isinstance(it, dict):
                    name = it.get("name") or it.get("feature") or it.get("özellik") or ""
                    status = it.get("status") or it.get("durum") or it.get("state") or ""
                else:
                    name, status = str(it), ""
                lines.append(f"| {name} | {status} |")
            return "\n".join(lines)

        def to_kv_table(d: dict):
            kv = [(k, d[k]) for k in d.keys()]
            lines = ["| Özellik | Değer |", "|---|---|"]
            for k, v in kv:
                lines.append(f"| {k} | {v} |")
            return "\n".join(lines)

        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = (raw or "").strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except Exception:
                    continue

                trim_raw = rec.get("trim") or rec.get("variant") or rec.get("donanim") or rec.get("title") or ""
                trim = self._normalize_enyaq_trim(trim_raw)
                if not trim:
                    # title içinde trim ima ediliyorsa yakala
                    ttr = str(rec.get("title") or "")
                    maybe = extract_trims(ttr.lower())
                    if maybe:
                        trim = self._normalize_enyaq_trim(next(iter(maybe)))
                if not trim:
                    # trim saptanamadıysa bu satırı atla (gruplamayı bozmamak için)
                    continue

                md = rec.get("markdown") or rec.get("md")
                if not md:
                    if rec.get("table"):
                        md = to_md_from_table(rec["table"])
                    elif rec.get("features"):
                        md = to_md_from_features(rec["features"])
                    elif rec.get("items"):
                        md = "\n".join(f"- {str(x)}" for x in rec["items"])
                    else:
                        # meta alanları çıkar, kalanlarla KV tablosu yap
                        ignore = {"model","trim","variant","donanim","title","markdown","md","table","features","items"}
                        payload = {k: v for k, v in rec.items() if k not in ignore}
                        md = to_kv_table(payload) if payload else ""

                if not md:
                    continue

                # Projede mevcut yardımcılar:
                if "|" in md and "\n" in md:
                    md = fix_markdown_table(md)
                else:
                    md = self._coerce_text_to_table_if_possible(md)

                prev = out.get(trim)
                out[trim] = (prev + "\n\n" + md) if prev else md

        return out

    # ChatbotAPI içinde
    def _load_non_skoda_lists(self):
        import json
        base_dir = os.path.join(os.getcwd(), "modules", "data")
        brands_path = os.path.join(base_dir, "non_skoda_brands.json")
        models_path = os.path.join(base_dir, "non_skoda_models.json")

        # Varsayılan (dosya yoksa min. güvenli çekirdek)
        DEFAULT_NON_SKODA_BRANDS = {"bmw","mercedes","mercedes-benz","audi","volkswagen","vw","renault","fiat","ford","toyota","honda","hyundai","kia","peugeot","citroen","opel","nissan","tesla","volvo","porsche","cupra","dacia","mini","seat","jaguar","land rover","lexus","mazda","mitsubishi","subaru","suzuki","jeep","chevrolet","cadillac","buick","gmc","dodge","lincoln","chery","byd","mg","nio","xpeng","geely","haval","togg","ssangyong","kg mobility"}
        DEFAULT_NON_SKODA_MODELS = {"golf","passat","polo","tiguan","fiesta","focus","kuga","corolla","c-hr","yaris","civic","cr-v","juke","qashqai","x-trail","308","3008","208","2008","astra","corsa","megane","clio","egea","tipo","duster","sandero","jogger","model 3","model y","i20","tucson","sportage","e-tron","taycan","x1","x3","x5","a3","a4","a6","c-class","e-class","s-class"}

        def _safe_load(p, fallback):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {normalize_tr_text(x).lower().strip() for x in data if str(x).strip()}
            except Exception as e:
                self.logger.warning(f"[non-skoda] {os.path.basename(p)} yüklenemedi, varsayılan kullanılacak: {e}")
                return set(fallback)

        self.NON_SKODA_BRANDS = _safe_load(brands_path, DEFAULT_NON_SKODA_BRANDS)
        self.NON_SKODA_MODELS = _safe_load(models_path, DEFAULT_NON_SKODA_MODELS)

        # Yaygın takma adlar / yazım varyantları
        BRAND_ALIASES = {
            "mercedes-benz": ["mercedes","merc","mb","mercedes benz"],
            "volkswagen": ["vw","volks wagen"],
            "citroën": ["citroen"],
            "rolls-royce": ["rolls royce"],
            "land rover": ["range rover"],   # halk kullanımı
            "kg mobility": ["ssangyong","ssang-yong"],
        }
        for canon, aliases in BRAND_ALIASES.items():
            for a in aliases:
                self.NON_SKODA_BRANDS.add(normalize_tr_text(a).lower())

        # Motorlu taşıt bağlam ipuçları (seri kodlarını güvenli tetiklemek için)
        self._MOTORING_HINTS_RE = re.compile(r"\b(model|seri|series|class|suv|sedan|hatchback|hb|estate|station|coupe|pickup|van|araba|ara[cç]|otomobil)\b", re.IGNORECASE)

        # Global seri/desen kalıpları (tek başına markasız yazıldığında bile araçla ilgili söylendiğini gösteren durumlar)
        self._SERIES_REGEXES = [
            # Audi
            re.compile(r"\b(a|s|rs)\s?-?\s?\d{1,2}\b"),     # A4, S3, RS6
            re.compile(r"\bq\s?-?\s?\d{1,2}\b"),            # Q3, Q8
            re.compile(r"\be-?tron\b"),

            # BMW
            re.compile(r"\b[1-8]\s?(series|seri|serisi)\b"),# 3 Series / 3 Serisi
            re.compile(r"\bx[1-7]\b"),                      # X3, X5
            re.compile(r"\bm\d{1,3}\b"),                    # M3, M135 vb.
            re.compile(r"\bi(?:3|4|5|7|x)\b"),              # i3, i4, i5, i7, iX

            # Mercedes
            re.compile(r"\b[abcegs]-?\s?class\b"),          # C-Class vs.
            re.compile(r"\bgl[abce]?\b"),                   # GLA/GLB/GLC/GLE
            re.compile(r"\bgls\b|\bg-?class\b|\bamg\s?gt\b"),
            re.compile(r"\beq[abces]\b|\beqs\b"),           # EQ serisi

            # VW ID.* ailesi
            re.compile(r"\bid\.\s?\d\b"),

            # Tesla
            re.compile(r"\bmodel\s?(s|3|x|y)\b"),

            # Volvo/Polestar (kısmi)
            re.compile(r"\bxc\d{2}\b|\bex\d{2}\b|\bpolestar\s?(2|3|4)\b"),
        ]


    def _mentions_non_skoda(self, text: str) -> bool:
        if not text:
            return False
        t = normalize_tr_text(text).lower()
        tokens = re.findall(r"[0-9a-zçğıöşü]+", t, flags=re.IGNORECASE)
        token_set = set(tokens)

        # 1) Doğrudan marka (tek veya çok kelime)
        #    Tek kelimelerde doğrudan token eşleşmesi; çok kelimede regex ile ara
        for b in self.NON_SKODA_BRANDS:
            if " " in b or "-" in b:
                pat = r"(?<!\w)" + re.escape(b).replace(r"\ ", r"(?:\s|-)") + r"(?!\w)"
                if re.search(pat, t):
                    return True
            else:
                if b in token_set:
                    return True

        # 2) Model adı (n-gram taraması, 1..4 kelime)
        for n in (4, 3, 2, 1):
            for i in range(0, max(0, len(tokens) - n + 1)):
                ngram = " ".join(tokens[i:i+n])
                if ngram in self.NON_SKODA_MODELS:
                    return True

        # 3) Seri/kod desenleri (yanında otomotiv bağlam ipucu varsa)
        if self._MOTORING_HINTS_RE.search(t):
            for rx in self._SERIES_REGEXES:
                if rx.search(t):
                    return True

        return False


    def _gate_to_table_or_image(self, text: str) -> bytes | None:
        """
        Yalnızca TABLO veya GÖRSEL olan içerikleri geçirir.
        - KV veya (- * •) madde listelerini tabloya çevirmeyi dener.
        - '›' veya sayılı listeler (1., 2.) tabloya çevrilmez → üst blok bastırılır.
        Dönen: bytes (göster) | None (gösterme).
        """
        if text is None:
            return None

        s = str(text)
        s_md = self.markdown_processor.transform_text_to_markdown(s)

        # Düzgün tabloysa hizasını düzelt
        if self._looks_like_table_or_image(s_md):
            if '|' in s_md and '\n' in s_md:
                s_md = fix_markdown_table(s_md)
            return s_md.encode("utf-8")

        # KV veya (- * •) madde listelerini tabloya çevir (› veya 1. … çevrilmez!)
        coerced = self._coerce_text_to_table_if_possible(s_md)
        if self._looks_like_table_or_image(coerced):
            if '|' in coerced and '\n' in coerced:
                coerced = fix_markdown_table(coerced)
            return coerced.encode("utf-8")

        return None

    def find_equipment_answer(user_message: str, model: str, donanim_md: str) -> str | None:
        return None  # kelime benzerliğine dayalı donanım bulma kaldırıldı

    def _lookup_standart_md(self, model: str) -> str | None:
        import importlib
        try:
            mod = importlib.import_module(f"modules.data.{model}_data")
        except Exception:
            return None

        names = [n for n in dir(mod) if n.endswith("_MD")]
        names.sort(key=lambda n: (
            0 if "DONANIM_LISTESI" in n.upper() else
            1 if ("STANDART" in n.upper() and "OPS" not in n.upper()) else
            2
        ))

        for n in names:
            up = n.upper()
            if ("DONANIM_LISTESI" in up) or ("STANDART" in up and "OPS" not in up):
                val = getattr(mod, n, "")
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return None



    def _expected_standart_md_for_question(self, user_message: str, user_id: str | None = None) -> tuple[str | None, dict]:
        t = normalize_tr_text(user_message or "").lower()

        if not any(kw in t for kw in [
            "standart", "standard", "temel donanım", "donanım listesi",
            "donanımlar neler", "standart donanımlar", "donanım list"
        ]):
            return None, {}

        models = list(self._extract_models(user_message))

        # Model yazılmadıysa: oturumdaki aktif asistandan bağlam al
        if not models and user_id:
            asst_id = self.user_states.get(user_id, {}).get("assistant_id")
            ctx_model = self.ASSISTANT_NAME_MAP.get(asst_id, "")
            if ctx_model:
                models = [ctx_model.lower()]

        if not models:
            return None, {}

        md = self._lookup_standart_md(models[0])
        if md:
            return md, {"source": "standart", "model": models[0]}
        return None, {}
     


    def _collect_all_data_texts(self):
        """
        modules/data içindeki *_MD (ve senin çevirdiğin *_LISTESI_MD) stringlerini tarar ve bellekte saklar.
        self.ALL_DATA_TEXTS = { "<mod>.<var>": {"title":..., "text":...}, ... }
        """
        self.ALL_DATA_TEXTS = {}
        collected = []

        for mod_name, mod in self._iter_modules_data():
            for name, val in vars(mod).items():
                if isinstance(val, str) and (name.endswith("_MD") or name.endswith("_LISTESI_MD")):
                    text = val.strip()
                    if not text:
                        continue
                    key = f"{mod_name}.{name}"
                    self.ALL_DATA_TEXTS[key] = {
                        "title": self._humanize_data_var(mod_name, name),
                        "text": text
                    }
                    collected.append(key)

        # 🔍 Log çıktısı → hangi değişkenler toplandı
        self.logger.info(f"[KB] Collected {len(self.ALL_DATA_TEXTS)} data chunks from modules.data/*.")
        for key in collected:
            self.logger.info(f"[KB-DUMP] {key}")
        for key, obj in self.ALL_DATA_TEXTS.items():
            if "DONANIM_LISTESI" in key.upper():
                self.logger.info(f"[DEBUG-STANDART] {key} -> {len(obj['text'])} karakter")


    def _expected_generic_data_for_question(self, user_message: str) -> tuple[str | None, dict]:
        if not user_message:
            return None, {}
        if not getattr(self, "ALL_DATA_TEXTS", None):
            self._collect_all_data_texts()

        models = list(self._extract_models(user_message))
        t = normalize_tr_text(user_message).lower()

        # Yalnızca ilgili model(ler) ait içerikleri aday havuzuna al
        def _doc_model_from_key(k: str) -> str:
            head = k.split(".", 1)[0] if "." in k else k
            head = head.replace("_data", "").replace("_teknik", "").strip().lower()
            return head

        items = []
        if models:
            allow = set(models)
            for key, obj in self.ALL_DATA_TEXTS.items():
                doc_mod = _doc_model_from_key(key)
                lowtxt = normalize_tr_text(obj["text"]).lower()
                if doc_mod in allow or any(m in lowtxt for m in allow):
                    items.append((key, obj))
        else:
            items = list(self.ALL_DATA_TEXTS.items())

        best_score, best_text, best_key = 0.0, None, None
        for key, obj in items:
            txt = obj["text"]
            score = self._text_similarity_ratio(t, txt)
            # Yumuşak pozitif ayrımcılık: model eşleşmesi zaten filtrede var; ek puan gerekmiyor
            if score > best_score:
                best_score, best_text, best_key = score, txt, key

        if best_text and best_score >= 0.40:
            return best_text, {"source": "data", "key": best_key, "score": round(best_score, 3)}
        return None, {}


    # ChatbotAPI sınıfı içinde:  [YENİ] DATA modül tarayıcıları
    def _iter_modules_data(self):
        """modules.data paketindeki modülleri (görsel/normalize gibi yardımcılar hariç) döndürür."""
        try:
            import pkgutil, importlib
            import modules.data as data_pkg
        except Exception as e:
            self.logger.error(f"[KB] data package not importable: {e}")
            return []

        mods = []
        for m in pkgutil.iter_modules(data_pkg.__path__, data_pkg.__name__ + "."):
            name = m.name.split(".")[-1]
            # İçerik olmayan veya yardımcı modülleri isterseniz dışlayın
            if name in ("text_norm", "__init__"):
                continue
            try:
                mod = importlib.import_module(m.name)
                mods.append((name, mod))
            except Exception as e:
                self.logger.warning(f"[KB] skip {m.name}: {e}")
        return mods

    def _humanize_data_var(self, mod_name: str, var_name: str) -> str:
        """Modül ve değişken adını kullanıcı dostu başlığa çevirir."""
        model = (mod_name.replace("_data", "")
                        .replace("_teknik", "")
                        .replace("_", " ")
                        .title())
        pretty_var = (var_name.replace("_MD", "")
                            .replace("_", " ")
                            .title())
        # Örn: "Scala" — "Premium" gibi
        return f"{model} — {pretty_var}"

    
    def _export_data_sections(self) -> list[str]:
        """Taradığımız tüm *_MD metinlerini SkodaKB.md’ye eklemek üzere bölüm listesi olarak döndürür."""
        if not getattr(self, "ALL_DATA_TEXTS", None):
            self._collect_all_data_texts()

        sections = []
        for obj in self.ALL_DATA_TEXTS.values():
            title = obj["title"]
            txt = obj["text"]
            sections.append(f"# {title}\n\n{txt}\n")
        return sections

    def _export_openai_glossary_text(self) -> str:
        import os, re
        sections = []
        seen_norm_hashes = set()  # [YENİ] aynı içerik tekrarını önlemek için

        def add(title, body):
            if body and str(body).strip():
                # [YENİ] tekrar önleme (normalize edilmiş içerik üzerinden)
                norm = self._norm_for_compare(str(body).strip())
                h = hash(norm)
                if h in seen_norm_hashes:
                    return
                seen_norm_hashes.add(h)
                sections.append(f"# {title}\n\n{str(body).strip()}\n")

        # 1) Teknik tablolar
        for model, md in (self.TECH_SPEC_TABLES or {}).items():
            add(f"{model.title()} — Teknik Özellikler", md)

        # 2) Opsiyonel donanımlar (model x trim)
        for model, trims in (self.MODEL_VALID_TRIMS or {}).items():
            for tr in trims:
                md = self._lookup_opsiyonel_md(model, tr)
                add(f"{model.title()} {tr.title()} — Opsiyonel Donanımlar", md)

        # 3) Fiyat listesi
        try:
            from modules.data.fiyat_data import FIYAT_LISTESI_MD
            add("Güncel Fiyat Listesi", FIYAT_LISTESI_MD)
        except Exception:
            pass

        # 4) EV & Yakıt sözlüğü
        try:
            from modules.data.ev_specs import EV_RANGE_KM, FUEL_SPECS
            if EV_RANGE_KM:
                lines = [f"- {m.title()} (WLTP menzil): {rng} km" for m, rng in EV_RANGE_KM.items()]
                add("EV Menzil", "\n".join(lines))
            if FUEL_SPECS:
                flines = [f"- {k}: {v}" for k, v in FUEL_SPECS.items()]
                add("Yakıt/Depo Sözlüğü", "\n".join(flines))
        except Exception:
            pass

        # 5) Spec eşanlamlıları
        if getattr(self, "SPEC_SYNONYMS", None):
            syn_lines = []
            for canon, pats in self.SPEC_SYNONYMS.items():
                cleaned = [re.sub(r'^\^|\$$', '', p) for p in pats]
                syn_lines.append(f"- {canon}: {', '.join(cleaned)}")
            if syn_lines:
                add("Terim Eşleştirmeleri", "\n".join(syn_lines))

        # 6) Trim eşanlamlıları
        if globals().get("TRIM_VARIANTS"):
            trim_lines = [f"- {base}: {', '.join(vars)}" for base, vars in TRIM_VARIANTS.items()]
            if trim_lines:
                add("Trim Eşanlamlıları", "\n".join(trim_lines))

        # 7) [YENİ] modules/data içindeki TÜM *_MD içeriklerini ekle
        try:
            for sec in self._export_data_sections():
                # add() çağrısındaki tekrar koruması zaten devrede
                title, body = sec.split("\n", 1) if "\n" in sec else (sec.strip(), "")
                # sec "# Başlık\n\nMetin..." biçiminde; doğrudan ekleyelim
                sections.append(sec)
            self.logger.info("[KB] All data.py *_MD sections appended to SkodaKB.md")
        except Exception as e:
            self.logger.error(f"[KB] export data sections failed: {e}")

        out_dir = os.path.join(self.app.static_folder, "kb")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "SkodaKB.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(sections))
        return out_path

 

    def _find_requested_specs(self, text: str) -> list[str]:
        """
        Kullanıcı mesajından hangi tablo satır(lar)ının istendiğini çıkarır.
        Dönüş: normalize ettiğiniz 'kanonik' başlıklar listesi (örn. '0-100 km/h (sn)').
        """
        if not text:
            return []
        t = normalize_tr_text(text).lower()
        out = []
        for canon, patterns in (self._SPEC_INDEX or []):
            if any(p.search(t) for p in patterns) or canon.lower() in t:
                out.append(canon)
        # Tekrarsız ve stabil sırada dön
        return list(dict.fromkeys(out))

    def _get_spec_value_from_dict(self, d: dict[str, str], canon_key: str) -> str | None:
        """
        _parse_teknik_md_to_dict() çıktısından 'canon_key' için değeri döndürür.
        Başlıklar zaten _normalize_spec_key_for_dedup ile normalize ediliyor.
        """
        target = self._normalize_spec_key_for_dedup(canon_key)
        # Doğrudan eşleşme
        for k, v in d.items():
            if self._normalize_spec_key_for_dedup(k) == target:
                return (v or "").strip()
        # Zayıf: en yakın başlık
        import difflib
        best_v, best_r = None, 0.0
        for k, v in d.items():
            r = difflib.SequenceMatcher(None, self._normalize_spec_key_for_dedup(k), target).ratio()
            if r > best_r:
                best_r, best_v = r, (v or "").strip()
        return best_v

    def _answer_teknik_as_qa(self, user_message: str, user_id: str) -> bytes | None:
        requested = self._find_requested_specs(user_message)
        models = list(self._extract_models(user_message))

        # YENİ: cmp_models varsa ve 2 model tutuyorsa, tek-model QA'ya düşme
        cm = (self.user_states.get(user_id, {}) or {}).get("cmp_models", [])
        if not models and len(cm) >= 2:
            return None

        # YENİ: metinde model yoksa ve oturumda >=2 model varsa -> QA'yı atla (üst katmandaki fark/karşılaştırma çalışsın)
        if not models and user_id:
            lm = list((self.user_states.get(user_id, {}) or {}).get("last_models", []))
            if len(lm) >= 2:
                return None
            # sadece 1 model ise onu kullan
            if len(lm) == 1:
                models = lm

        if not models:
            # Asistan bağlamından dene
            asst_id = (self.user_states.get(user_id, {}) or {}).get("assistant_id")
            ctx_model = self.ASSISTANT_NAME_MAP.get(asst_id, "") if asst_id else ""
            if ctx_model:
                models = [ctx_model.lower()]
            else:
                return None

        # 🔒 Her durumda 'model'ı garanti et
        model = models[0]

        # === 1) TEKNİK TABLODAN ARA ===
        if requested:
            md = self._get_teknik_md_for_model(model)
            if md:
                _, d = self._parse_teknik_md_to_dict(md or "")
                pairs = []
                for canon in requested:
                    val = self._get_spec_value_from_dict(d, canon)
                    if val:
                        pairs.append((canon, val))

                if pairs:
                    if len(pairs) == 1:
                        key, val = pairs[0]
                        return self._emit_spec_sentence(model, key, val)
                    else:
                        sent_list = []
                        for k, v in pairs:
                            sent_list.append(self._emit_spec_sentence(model, k, v).decode("utf-8", "ignore"))
                        return (" ".join(sent_list)).encode("utf-8")

        # === 2) DONANIM LİSTESİNDEN ARA ===
         # === 2) STANDART DONANIM LİSTESİNDEN ARA (yalnızca donanım niyeti varsa) ===
        import re
        equip_intent = re.search(r"\b(standart|opsiyonel|var m[ıi]|bulunuyor mu|donan[ıi]m|özellik)\b",
                                 normalize_tr_text(user_message).lower())
        if not equip_intent:
            return None

        md = self.STANDART_DONANIM_TABLES.get(model) or ""
        if not md:
            return None

        # Stopword'leri at; 'fabia ile ilgili bilgi...' gibi genel cümleler eşleşmesin
        stop = {"ve","ile","mi","mı","mu","mü","de","da","bir","bu","şu","o",
                "hakkında","ilgili","bilgi","ver","verir","verebilir","misin",
                "nedir","ne","olan"}
        q_tokens = [t for t in re.findall(r"[0-9a-zçğıöşü]+",
                    normalize_tr_text(user_message).lower()) if t not in stop]
        if not q_tokens:
            return None

        lines = [ln.strip("-• ").strip() for ln in md.splitlines() if "→" in ln]
        matches = [ln for ln in lines if any(tok in normalize_tr_text(ln).lower() for tok in q_tokens)]
        if matches:
            responses = []
            for m in matches[:5]:
                # "→ S" → "standart", "→ Opsiyonel" → "opsiyonel", "→ —" → "bulunmuyor"
                if "→" in m:
                    feature, status = m.split("→", 1)
                    feature = feature.strip()
                    status = status.strip().lower()

                    if status.startswith("s"):
                        responses.append(f"{feature} {model.title()} modelinde standart olarak sunuluyor.")
                    elif "ops" in status:
                        responses.append(f"{feature} {model.title()} modelinde opsiyonel olarak sunuluyor.")
                    else:
                        responses.append(f"{feature} {model.title()} modelinde bulunmuyor.")
                else:
                    responses.append(f"{m} {model.title()} modelinde mevcut.")

            return " ".join(responses).encode("utf-8")




    # === [YENİ] OpenAI ↔ Dosya kıyas katmanı =====================================
    def _has_0_100_pattern(self, text: str) -> bool:
        t = normalize_tr_text(text or "").lower()
        return bool(re.search(r"\b0\s*[-–—]?\s*100\b", t))

    def _norm_for_compare(self, text: str) -> str:
        """Karşılaştırma için metni normalize eder (HTML/LaTeX sil, TR normalize, boşlukları sıkıştır)."""
        if not text:
            return ""
        s = remove_latex_and_formulas(text or "")
        s = re.sub(r"<[^>]*>", " ", s)                           # HTML
        s = normalize_tr_text(s or "").lower()
        # Markdown tablolarında hizayı bozmayalım, ama fazla boşlukları toparlayalım
        # Dikey çizgi içeren satırlarda sadece uç boşluklar:
        lines = []
        for ln in s.splitlines():
            if '|' in ln:
                lines.append(ln.strip())
            else:
                ln = re.sub(r"\s+", " ", ln).strip()
                lines.append(ln)
        s = "\n".join(lines)
        return s.strip()

    def _text_similarity_ratio(self, a: str, b: str) -> float:
        # Sadece birebir eşitse 1.0, aksi halde 0.0
        na, nb = self._norm_for_compare(a), self._norm_for_compare(b)
        return 1.0 if na and nb and na == nb else 0.0


    def _expected_fiyat_md_for_question(self, user_message: str) -> str | None:
        """Sorudan fiyat tablosu (filtreli) üretir. (Dosya: fiyat_data.py)"""
        lower_msg = user_message.lower()
        models = self._extract_models(user_message)
        want_combi = "combi" in lower_msg
        want_coupe = any(k in lower_msg for k in ["coupe", "coupé", "kupe", "kupé"])

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

        return fix_markdown_table(md) if md else None

    def _expected_teknik_md_for_question(self, user_message: str) -> tuple[str | None, dict]:
        """
        Soru 'teknik' içeriyorsa doğru teknik tabloyu (tek model) veya karşılaştırma tablosunu (çoklu) üretir.
        Geri dönüş: (md, meta)  meta: {'source':'teknik', 'models':[...]}
        """
        lower_msg = user_message.lower()
        teknik_keywords = [
            "teknik özellik", "teknik veriler", "teknik veri", "motor özellik",
            "motor donanım", "motor teknik", "teknik tablo", "teknik", "performans"
        ]
        compare_keywords = ["karşılaştır", "karşılaştırma", "kıyas", "kıyasla", "kıyaslama", "vs", "vs."]
        has_teknik = any(kw in lower_msg for kw in teknik_keywords)
        wants_compare = any(ck in lower_msg for ck in compare_keywords)
        if not has_teknik:
            return None, {}

        models_in_msg = list(self._extract_models(user_message))
        pairs_for_order = extract_model_trim_pairs(lower_msg)
        ordered_models = []
        for m, _ in pairs_for_order:
            if m not in ordered_models:
                ordered_models.append(m)
        if len(ordered_models) < len(models_in_msg):
            for m in models_in_msg:
                if m not in ordered_models:
                    ordered_models.append(m)
        valid = [m for m in ordered_models if m in self.TECH_SPEC_TABLES]

        # Çoklu karşılaştırma
        if wants_compare or len(valid) >= 2:
            if len(valid) >= 2:
                md = self._build_teknik_comparison_table(valid)
                return (md or None), {"source":"teknik", "models": valid}
            return None, {}

        # Tek model
        model = None
        if len(models_in_msg) == 1:
            model = models_in_msg[0]
        elif ordered_models:
            model = ordered_models[0]
        if model and model in self.TECH_SPEC_TABLES:
            return (self.TECH_SPEC_TABLES[model] or None), {"source":"teknik", "models":[model]}

        return None, {}

    def _lookup_opsiyonel_md(self, model: str, trim: str) -> str | None:
        """Model + trim'e göre opsiyonel donanım markdown'ını döndürür."""
        if not model or not trim:
            return None
        m, t = (model or "").lower(), (trim or "").lower()

        # Fabia
       # Fabia
        if m == "fabia":
            
            return FABIA_DATA_MD
        # Scala
        if m == "scala":
             
            return SCALA_DATA_MD
        # Kamiq
        if m == "kamiq":
             
            return KAMIQ_DATA_MD
        # Karoq
        if m == "karoq":
             
            return KAROQ_DATA_MD
        # Kodiaq
        if m == "kodiaq":
             
            return KODIAQ_DATA_MD
        # Octavia
        if m == "octavia":
             
            return OCTAVIA_DATA_MD
        # Superb
        if m == "superb":
             
            return SUPERB_DATA_MD
        # Enyaq
        # Enyaq
        if m == "enyaq":
            # JSONL override varsa önce onu dene
             
            return ENYAQ_DATA_MD

        # Elroq
        if m == "elroq":
             
            return ELROQ_DATA_MD

        return None


    def _expected_opsiyonel_md_for_question(self, user_message: str) -> tuple[str | None, dict]:
        """
        Soru 'opsiyonel' içeriyorsa uygun tabloyu döndürür.
        Geri dönüş: (md, meta)  meta: {'source':'opsiyonel','model':..,'trim':..}
        """
        lower_msg = user_message.lower()
        if "opsiyonel" not in lower_msg:
            return None, {}

        models = list(self._extract_models(user_message))
        # İlk model kuralı (sıra duyarlı çıkarım yapalım)
        pairs = extract_model_trim_pairs(lower_msg)
        model = pairs[0][0] if pairs else (models[0] if len(models) == 1 else None)

        trims = extract_trims(lower_msg)
        trim = next(iter(trims)) if len(trims) == 1 else None

        if not model or not trim:
            return None, {}

        md = self._lookup_opsiyonel_md(model, trim)
        if not md:
            return None, {}
        return md, {"source":"opsiyonel", "model":model, "trim":trim}

    def _expected_answer_from_files(self, user_message: str, user_id: str | None = None) -> tuple[str | None, dict]:
        # 0) Standart donanım
        md, meta = self._expected_standart_md_for_question(user_message, user_id=user_id)
        if md:
            return md, meta

        # 1) Fiyat
        if self._is_price_intent(user_message):
            md = self._expected_fiyat_md_for_question(user_message)
            if md:
                return md, {"source":"fiyat"}

        # 2) Teknik
        md, meta = self._expected_teknik_md_for_question(user_message)
        if md:
            return md, meta or {"source":"teknik"}

        # 3) Opsiyonel
        md, meta = self._expected_opsiyonel_md_for_question(user_message)
        if md:
            return md, meta or {"source":"opsiyonel"}

        return None, {}



    def _apply_file_validation_and_route(self, *, user_id: str, user_message: str,
                                     ai_answer_text: str) -> bytes:
        ai_answer_text = self._strip_price_from_any(ai_answer_text)
        ai_answer_text = self._drop_kb_missing_rows_from_any(ai_answer_text)   # ⬅️ EKLE
        expected_text, meta = self._expected_answer_from_files(user_message)

        def _gate_bytes_from_text(txt: str) -> bytes:
            gated = self._gate_to_table_or_image(txt)
            return gated if gated else b" "

        # >>> Yeni: model uyuşmazlığını engelle <<<
        if getattr(self, "STRICT_MODEL_ONLY", False):
            req_models = set(self._extract_models(user_message))
            if req_models:
                ans_models = set(self._count_models_in_text(ai_answer_text).keys())
                # Cevapta model isimleri var ve bunlar istenen kümenin dışına taşıyorsa
                if ans_models and not ans_models.issubset(req_models):
                    # İlgili dosya içeriği varsa ona düş
                    if expected_text:
                        md = self.markdown_processor.transform_text_to_markdown(expected_text or "")
                        if '|' in md and '\n' in md:
                            md = fix_markdown_table(md)
                        else:
                            md = self._coerce_text_to_table_if_possible(md)
                        return _gate_bytes_from_text(md)
                    else:
                        # İçerik yoksa: cevabı model dışı satırları ayıklayarak zorla daralt (son çare)
                        others = (set(self.MODEL_CANONICALS) - req_models)
                        norm_others = {normalize_tr_text(x).lower() for x in others}
                        filtered = "\n".join(
                            ln for ln in ai_answer_text.splitlines()
                            if not any(no in normalize_tr_text(ln).lower() for no in norm_others)
                        )
                        filtered = self._enforce_assertive_tone(filtered)
                        return _gate_bytes_from_text(filtered or " ")

        # Mevcut akış: benzerlik eşiğine göre karar
        ratio = self._text_similarity_ratio(ai_answer_text, expected_text or "")
        lower_q = normalize_tr_text(user_message).lower()
        avoid_table = any(k in lower_q for k in ["görsel","resim","foto","renk"])
        if expected_text and ratio < self.OPENAI_MATCH_THRESHOLD:
            md = self.markdown_processor.transform_text_to_markdown(expected_text or "")
            if '|' in md and '\n' in md:
                md = fix_markdown_table(md)
            else:
                md = self._coerce_text_to_table_if_possible(md)
            return _gate_bytes_from_text(md)

        # Köprü metni ile devam (assertive ton uygulayalım)
        ai_answer_text = self._enforce_assertive_tone(ai_answer_text or "")
        # YENİ: Tablo/görsel yakalayamazsa düz metni ilet
        raw_text = ai_answer_text or ""
        gated = self._gate_to_table_or_image(raw_text)
        return gated if gated else raw_text.encode("utf-8")





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
        md = "\n\n".join(tables)
        return self._strip_price_from_any(md)
        


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
        model_hint: str | None = None,
        strip_price: bool = True,          # ✅ YENİ
    ) -> bytes:
        body = self._strip_forbidden_ui_blocks(body)   # ✅ ekle
        if strip_price:
            body = self._strip_price_from_any(body)
        body = self._drop_kb_missing_rows_from_any(body)

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
        if not text:
            return False
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            return False

        # URL ve saat gibi yanlı tetikleyicileri dışla
        safe = []
        for ln in lines:
            if re.search(r'https?://', ln):   # linkler
                continue
            if re.search(r'\b\d{1,2}:\d{2}\b', ln):  # saat 12:30 vb.
                continue
            safe.append(ln)

        kv_lines = [
            ln for ln in safe
            if re.match(r'^\s*[-*•]?\s*[^\|:\n]{2,}\s*[:：]\s+.+$', ln)
        ]

        # En az 3 satır ve satırların çoğu KV biçiminde olmalı
        return (len(kv_lines) >= 3) and (len(kv_lines) >= int(len(safe) * 0.6))


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
        t = normalize_tr_text(text or "").lower()
        p = normalize_tr_text(phrase or "").lower()
        return p in t  # fuzzy KAPALI


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
    # self.client = OpenAI(api_key=...)
# client = OpenAI()  # ikinci client'a gerek yok, isterseniz silin

    def _vs_api(self):
        """Vector Stores client'ını (yeni: client.vector_stores, eski: client.beta.vector_stores) döndürür."""
        vs = getattr(self.client, "vector_stores", None)
        if vs:
            return vs
        beta = getattr(self.client, "beta", None)
        return getattr(beta, "vector_stores", None) if beta else None

    # Güvenli debug
    

    def __init__(self, logger=None, static_folder='static', template_folder='templates'):
        self.app = Flask(
            __name__,
            static_folder=os.path.join(os.getcwd(), static_folder),
            template_folder=os.path.join(os.getcwd(), template_folder),
            
        )
        self._imported_cache = {}   # { "ELROQ": [ {"ozellik":..., "ePrestige":..., "deger":...}, ... ] }
        self._equip_sem_index = {}
            # Logger'ı en başta kur (ilk self.logger.info() çağrısından önce)
        self.logger = logger if logger else self._setup_logger()
        self.logger.info("ChatbotAPI initializing...")
        # __init__ içinde (ör. self.MODEL_VALID_TRIMS tanımlarının altına)

        # Teknik niyet tetikleyicileri (genel + yaygın alt konular)
        self.TEKNIK_TRIGGERS = [
            "teknik özellik", "teknik veriler", "teknik veri", "motor özellik",
            "motor donanım", "motor teknik", "teknik tablo", "teknik", "performans",
            "hızlanma", "ivme", "ivmelenme", "0-100", "0 – 100", "0 100",
            "maksimum hız", "maks hız", "menzil", "batarya", "şarj",
            "enerji tüketimi", "wltp", "co2", "tork", "güç", "ps", "kw", "beygir",
            "bagaj", "ağırlık", "lastik", "uzunluk", "genişlik", "yükseklik",
            "dingil", "yerden yükseklik", "dönüş çapı", "sürtünme", "güç aktarımı"
        ]

        # Kullanıcı cümlesindeki ifadenin hangi tablo satırını kastettiğini bulmak için
        # (ANAHTAR = Sizin normalize ettiğiniz satır başlığı)
        self.SPEC_SYNONYMS = {
            "0-100 km/h (sn)": [
                r"h[ıi]zlanma", r"ivme(?:lenme)?", r"\b0\s*[-–—]?\s*100\b", r"s[ıi]f[ıi]rdan.*100"
            ],
            
            "Maks. hız (km/h)": [r"maks(?:\.|imum)?\s*h[ıi]z", r"son\s*h[ıi]z"],
            "Maks. güç (kW/PS @ dev/dak)": [r"\bg[üu]ç\b", r"\bbeygir\b|\bhp\b|\bps\b|\bkw\b"],
            "Maks. tork (Nm @ dev/dak)": [r"\btork\b"],
            "Menzil (WLTP)": [r"menzil(?!.*şehir)", r"menzil\s*kombine"],
            "Menzil (WLTP, şehir içi)": [r"şehir\s*içi\s*menzil|sehir\s*ici\s*menzil"],
            "Batarya kapasitesi (brüt kWh)": [r"batarya.*br[üu]t|br[üu]t.*batarya"],
            "Batarya kapasitesi (net kWh)": [r"batarya.*net|net.*batarya"],
            "Enerji Tüketimi (WLTP Kombine)": [r"enerji\s*t[üu]ketimi|wltp.*t[üu]ketim|\bt[üu]ketim\b"],
            "Dahili AC şarj (kW)": [
                r"\bac\b.*şarj(?!.*s[üu]re|.*dakika)",
                r"\bdahili\s*ac(?!.*s[üu]re|.*dakika)"
            ],
            "DC şarj gücü (kW)": [r"\bdc\b.*şarj.*g[üu]c[üu]|h[ıi]zl[ıi]\s*şarj"],
            "DC şarj 10-80% (dk)": [r"dc.*(?:10|%10)\s*[-–—]?\s*80|%10.*%80"],
            "AC 11 kW Şarj Süresi (0% - 100%)": [
                r"ac\s*şarj\s*s[üu]re", r"ac\s*s[üu]resi",
                r"\bac\b.*0.*100.*(s[üu]re|dolum)"
            ],
            "WLTP CO2 Emisyonu (g/km)": [r"\bco2\b|emisyon"],
            "Bagaj hacmi (dm3)": [r"bagaj"],
            "Ağırlık (Sürücü Dahil) (kg)": [r"ağ[ıi]rl[ıi]k"],
            "Lastikler": [r"lastik(ler)?"],
            "Uzunluk/Genişlik/Yükseklik (mm)": [r"uzunluk|geni[şs]lik|y[üu]kseklik"],
            "Dingil mesafesi (mm)": [r"dingil\s*mesafesi"],
            "Yerden yükseklik (mm)": [r"yerden.*y[üu]kseklik|y[üu]kseklik.*yerden"],
            "Dönüş çapı (m)": [r"d[öo]n[üu]ş.*çap"],
            "Sürtünme katsayısı": [r"s[üu]rt[üu]nme\s*katsay"],
            "Güç aktarımı": [r"g[üu]ç\s*aktar[ıi]m[ıi]|çekiş|önden|arkadan|4x4|awd"]
        }
        self._SPEC_KEYWORDS = _SPEC_KEYWORDS

        # derlenmiş regex index’i
        self._SPEC_INDEX = None


        self.MAX_COMPARE_MODELS_PER_TABLE = int(os.getenv("MAX_COMPARE_MODELS_PER_TABLE", "6"))
        self.OPENAI_MATCH_THRESHOLD = float(os.getenv("OPENAI_MATCH_THRESHOLD", "0.80"))
       # self.trace_logger = TraceLogger(base_dir="logs/traces")


        # __init__ içinde (diğer os.getenv okumalarının yanına)
        self.KB_ONLY = os.getenv("KB_ONLY", "1") == "1"

        # file_search'i ENV'den oku (KB_ONLY bunu ezmesin)
        self.USE_OPENAI_FILE_SEARCH = os.getenv("USE_OPENAI_FILE_SEARCH", "0") == "1"
        self.RAG_ONLY = os.getenv("RAG_ONLY", "0") == "1"
        self.RAG_FROM_SQL_ONLY = os.getenv("RAG_FROM_SQL_ONLY", "0") == "1"

        if self.KB_ONLY:
            # KB_ONLY sadece "bridge"i kapatsın; file_search kalsın
            self.DISABLE_BRIDGE = True       # file_search-only gibi modlar kapalı
        self.TDI_MODELS = {"superb", "kodiaq"}   # ✅ sadece bunlarda TDI var
        self.NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
        self.NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
        self.NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
        self.NEO4J_DB = os.getenv("NEO4J_DB", "neo4j")
        

        try:
            self.neo4j_graphrag._tlog = lambda uid, ev, **kw: self._tlog(uid, ev, **kw)
        except Exception:
            pass

        from modules.neo4j_skoda_rag import Neo4jSkodaRAG
        if os.getenv("NEO4J_INGEST_ON_BOOT", "0") == "1":
            kb_path = os.path.join(self.app.static_folder, "kb", "SkodaKB.md")
            if os.path.exists(kb_path):
                with open(kb_path, "r", encoding="utf-8") as f:
                    txt = f.read()
            # reset=True ile bir kere temiz bas
                self.neo4j_graphrag.ingest_text_to_ragchunk(txt, source="SkodaKB", reset=True)

        self.neo4j_rag = Neo4jSkodaRAG(
            neo4j_uri=self.NEO4J_URI,
            neo4j_user=self.NEO4J_USER,
            neo4j_password=self.NEO4J_PASSWORD,
            openai_api_key=os.getenv("OPENAI_API_KEY",""),
            enabled=(os.getenv("ENABLE_NEO4J_SKODA_RAG","1") == "1"),
        )
        # --- NEO4J health cache (çok sık verify_connectivity() çağırmamak için) ---
        self._neo4j_health = {"ok": False, "ts": 0.0}

        # Donanım (EQUIP) için Neo4j fallback açık/kapalı
        self.ENABLE_EQUIP_NEO4J_FALLBACK = os.getenv("ENABLE_EQUIP_NEO4J_FALLBACK", "1") == "1"

        # Neo4j yoksa istersen asistan fallback (default kapalı)
        self.EQUIP_ASSISTANT_IF_NO_NEO4J = os.getenv("EQUIP_ASSISTANT_IF_NO_NEO4J", "0") == "1"

        # 1 kere ingest etmek için (manuel aç/kapat)
        if os.getenv("NEO4J_INGEST_ON_BOOT","0") == "1":
            kb_path = os.path.join(self.app.static_folder, "kb", "SkodaKB.md")
            if os.path.exists(kb_path):
                self.neo4j_rag.ingest_skoda_kb_markdown(kb_path)

        self.neo4j_driver = GraphDatabase.driver(
            self.NEO4J_URI,
            auth=(self.NEO4J_USER, self.NEO4J_PASSWORD)
        )
        self.LONG_DELIVER_WORDS = int(os.getenv("LONG_DELIVER_WORDS", "30"))   # metin için varsayılan: 30 kelime
        self.LONG_TABLE_WORDS   = int(os.getenv("LONG_TABLE_WORDS", "800"))    # tablo/kaynak için kelime eşiği
        self.LONG_TABLE_ROWS    = int(os.getenv("LONG_TABLE_ROWS", "60"))      # tablo satır eşiği
        self.LONG_TOKENS        = int(os.getenv("LONG_TOKENS", "6500"))        # güvenlik tavanı (yaklaşık token)
        self.RAG_ONLY = os.getenv("RAG_ONLY", "0") == "1"
        #self.USE_ANSWER_CACHE = os.getenv("USE_ANSWER_CACHE", "0") == "1"
        self.TEXT_COMPARE_WHEN_NOT_EQUIPMENT = True   # donanım dışı kıyaslarda tablo yerine metin
        self.RAG_FROM_SQL_ONLY = os.getenv("RAG_FROM_SQL_ONLY", "0") == "1"
        self.DISABLE_BRIDGE = os.getenv("DISABLE_BRIDGE", "0") == "1"
        # --- Hybrid RAG bayrakları ---
        self.HYBRID_RAG = os.getenv("HYBRID_RAG", "1") == "1"   # default açık
        self.logger.info(f"[ENV] HYBRID_RAG={self.HYBRID_RAG}, EMBED_MODEL={os.getenv('EMBED_MODEL','text-embedding-3-large')}")
        # Vector Store kısa özetlerini ve RAG metnini yüzeye çıkarma
        self.RAG_SUMMARY_EVERY_ANSWER = os.getenv("RAG_SUMMARY_EVERY_ANSWER", "0") == "1"
        self.PREFER_RAG_TEXT = os.getenv("PREFER_RAG_TEXT", "0") == "1"
        # --- SQL-RAG ayarları ---
        self.SQL_RAG_ALWAYS_ON = os.getenv("SQL_RAG_ALWAYS_ON", "1") == "1"
        self.SQL_RAG_SHORT_CIRCUIT = os.getenv("SQL_RAG_SHORT_CIRCUIT", "1") == "1"
        self.SQL_MD_GLOB = os.getenv("SQL_MD_GLOB", os.path.join("sql_docs", "**", "*.sql.md"))
        # __init__ içinde, ENV okumalarının hemen altına ekleyin:
        self.STRICT_SQL_ONLY = os.getenv("STRICT_SQL_ONLY", "0") == "1"
                # --- Native MSSQL Vector Search ayarları ---
        self.USE_MSSQL_NATIVE_VECTOR = os.getenv("USE_MSSQL_NATIVE_VECTOR", "0") == "1"
        # VECTOR(...) boyutu
        try:
            self.MSSQL_VECTOR_DIM = int(os.getenv("MSSQL_VECTOR_DIM", str(self._embed_dim())))
        except Exception:
            self.MSSQL_VECTOR_DIM = self._embed_dim()

        self.STRICT_MODEL_ONLY = True
        if self.STRICT_SQL_ONLY:
    # 1) Modül içi MD sözlüklerini boşalt
            self.TECH_SPEC_TABLES = {}
            self.STANDART_DONANIM_TABLES = {}
            self.ALL_DATA_TEXTS = {}

            # 2) MD’ye bakan yardımcıları etkisizleştir
            def _return_none(*a, **k): return None
            def _files_off(*a, **k):   return (None, {})   # expected_answer_from_files için

            self._lookup_standart_md = _return_none
            self._lookup_opsiyonel_md = _return_none
            self._expected_answer_from_files = _files_off
            self._collect_all_data_texts = lambda *a, **k: None

            # 3) Vector store’a MD yükleme/üretme yollarını kapat
            self.USE_OPENAI_FILE_SEARCH = False
            self.RAG_SUMMARY_EVERY_ANSWER = False
            self._export_openai_glossary_text = lambda *a, **k: ""
            self._export_openai_kb_from_sql  = lambda *a, **k: []        # .sql.md üretmesin
            self._ensure_vector_store_and_upload = lambda *a, **k: None  # hiç çağırmasın
            self._enable_file_search_on_assistants = lambda *a, **k: None

        #self.sqlrag = SQLRAG(kb_glob=self.SQL_MD_GLOB, db_path=os.getenv("SQL_RAG_DB", "/mnt/data/sql_rag.db"))
        self.USE_SQL_RAG = os.getenv("USE_SQL_RAG", "0") == "1"

        if self.USE_SQL_RAG:
            self.sqlrag = SQLRAG(kb_glob=self.SQL_MD_GLOB, db_path=os.getenv("SQL_RAG_DB", "/mnt/data/sql_rag.db"))
            try:
                self.sqlrag.build_or_update_index()
                self.logger.info(f"[SQL-RAG] Index hazır: {self.SQL_MD_GLOB}")
            except Exception as e:
                self.logger.error(f"[SQL-RAG] indeksleme hatası: {e}") 
        # 🔴 Model+trim kıyaslarında RAG'i zorunlu kıl
        self.RAG_FOR_MODEL_TRIM_COMPARE = os.getenv("RAG_FOR_MODEL_TRIM_COMPARE", "1") == "1"

        # (opsiyonel) ilk açılışta otomatik indexleme
        

        self.logger.info(
            "[ENV] USE_OPENAI_FILE_SEARCH=%s, RAG_ONLY=%s, RAG_FROM_SQL_ONLY=%s, DISABLE_BRIDGE=%s, OPENAI_API_KEY_SET=%s",
            os.getenv("USE_OPENAI_FILE_SEARCH"),
            os.getenv("RAG_ONLY"),
            os.getenv("RAG_FROM_SQL_ONLY"),
            os.getenv("DISABLE_BRIDGE"),
            "yes" if os.getenv("OPENAI_API_KEY") else "no",
        ) 

        self.FIRST_SERVICE_URL   = os.getenv("FIRST_SERVICE_URL", "http://127.0.0.1:5000/api/raw_answer")
        self.FIRST_SHARED_SECRET = os.getenv("FIRST_SHARED_SECRET", "")
        # "test" asistan ID'si: .env yoksa Config'ten 'test' map'ini dene
 
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
        # 1) Teknik tablolar (yalnızca TEKNIK_MD)
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

        # 2) Standart donanım listeleri ayrı dursun
        self.STANDART_DONANIM_TABLES = {
            "fabia":   FABIA_DATA_MD,
            "scala":   SCALA_DATA_MD,
            "kamiq":   KAMIQ_DATA_MD,
            "karoq":   KAROQ_DATA_MD,
            "kodiaq":  KODIAQ_DATA_MD,
            "octavia": OCTAVIA_DATA_MD,
            "superb":  SUPERB_DATA_MD,
            "enyaq":   ENYAQ_DATA_MD,
            "elroq":   ELROQ_DATA_MD,
        }
        # --- Görsel niyeti: eşanlamlılar (diakritik + ekleşme güvenli) ---
        self.IMAGE_SYNONYM_RE = re.compile(
            r"\b(?:"
            r"g[öo]rsel(?:ler(?:i|in)?|eri|er|i|e|ini|de|den)?|"      # görsel / gorsel / görselleri...
            r"resim(?:ler(?:i|in)?|i|e|ini|de|den)?|"                 # resim / resimleri...
            r"foto(?:ğ|g)raf(?:lar(?:ı|ın)?|ı|i|e|ini|de|den)?|"      # fotoğraf / fotograf / fotoğrafları...
            r"foto(?:lar(?:ı|ın)?)?|"                                 # foto / fotolar / fotoları
            r"g[öo]r[üu]nt[üu](?:ler(?:i|in)?|y[üu]|s[üu])?|"        # görüntü / görüntüler...
            r"image(?:s)?|img|photo(?:s)?|pic(?:ture)?(?:s)?"         # İng. varyasyonlar
            r")\b",
            re.IGNORECASE
        )


        #self.logger = logger if logger else self._setup_logger()

        create_tables()
        from modules.trace_debug import traced_openai_client
        self.client = traced_openai_client(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

        # =========================
        # NEO4J INIT (ONE-TIME)
        # =========================
        from modules.neo4j_skoda_graphrag import Neo4jSkodaGraphRAG

        self.neo4j_graphrag = Neo4jSkodaGraphRAG(
            neo4j_uri=os.getenv("NEO4J_URI",""),
            neo4j_user=os.getenv("NEO4J_USER","neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD",""),
            openai_api_key=os.getenv("OPENAI_API_KEY",""),
            enabled=(os.getenv("ENABLE_NEO4J_GRAPHRAG","1") == "1"),
        )
        

        self.neo4j_graphrag._tlog = lambda uid, ev, **kw: self._tlog(uid, ev, **kw)
        # İstersen boot’ta ingest (ilk kurulumda 1 kere)
        if os.getenv("NEO4J_INGEST_ON_BOOT","0") == "1":
            kb_path = os.path.join(self.app.static_folder, "kb", "SkodaKB.md")
            # SkodaKB.md yoksa senin üreten fonksiyonu çağır:
            if not os.path.exists(kb_path):
                try:
                    kb_path = self._export_openai_glossary_text()  # sende var
                except Exception:
                    kb_path = kb_path
            if os.path.exists(kb_path):
                self.neo4j_graphrag.ingest_markdown(kb_path, reset=True)

         #self.client = openai
        self.assistant_runner = AssistantRunner(self.client, logger=self.logger)
        client = OpenAI()
        # ⬅️ BUNU EN BAŞA TAŞI

        # ⬇️ Sonra HYBRID_RAG + KB_REINDEX_ON_BOOT bloğu gelsin
        self.HYBRID_RAG = os.getenv("HYBRID_RAG", "1") == "1"
        if self.HYBRID_RAG and os.getenv("KB_REINDEX_ON_BOOT", "0") == "1":
            try:
                stats = self._kb_index_all()
                self.logger.info(f"[KB-IDX] boot reindex done: {sum(stats.values())} vectors")
            except Exception as e:
                self.logger.error(f"[KB-IDX] boot reindex fail: {e}")
        self.config = Config()
        # ✅ Config'ten asistan map'lerini çek (yoksa boş dict)
        self.ASSISTANT_CONFIG = getattr(self.config, "ASSISTANT_CONFIG", {}) or {}
        self.ASSISTANT_NAME_MAP = getattr(self.config, "ASSISTANT_NAME_MAP", {}) or {}

        # ✅ Model -> assistant_id hızlı map (ASSISTANT_NAME_MAP üzerinden)
        self.MODEL_TO_ASSISTANT_ID = {}
        for asst_id, model_slug in (self.ASSISTANT_NAME_MAP or {}).items():
            m = normalize_tr_text(str(model_slug or "")).lower().strip()
            if m:
                self.MODEL_TO_ASSISTANT_ID[m] = asst_id

        self.utils = Utils()

        self.image_manager = ImageManager(images_folder=os.path.join(static_folder, "images"))
        self.image_manager.load_images()

        self.markdown_processor = MarkdownProcessor()

        # Önemli: Config içindeki ASSISTANT_CONFIG ve ASSISTANT_NAME_MAP
 
        self.user_states = {}

        # Cache tamamen kapalı
        self.fuzzy_cache = {}
        self.fuzzy_cache_queue = None
        self.stop_worker = False
        self.CACHE_EXPIRY_SECONDS = 0
        self.USE_ANSWER_CACHE = False
        
        # === Davranış bayrakları (isteğiniz doğrultusunda) ===
        self.ASSERTIVE_MODE = os.getenv("ASSERTIVE_MODE", "1") == "1"
        self.STRICT_MODEL_ONLY = os.getenv("STRICT_MODEL_ONLY", "1") == "1"

        # Vector Store kısa özetlerini ve RAG metnini yüzeye çıkarma
        self.RAG_SUMMARY_EVERY_ANSWER = os.getenv("RAG_SUMMARY_EVERY_ANSWER", "0") == "1"
        self.PREFER_RAG_TEXT = os.getenv("PREFER_RAG_TEXT", "0") == "1"


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
                # --- Standart donanım / teknik tablo skorlamasında kullanılacak ipuçları ---
        # Standart donanım tablolarında başlık ve satırlarda sık görülen trim/donanım kelimeleri
        self.TRIM_HINTS = [
            "premium", "elite", "prestige", "sportline", "monte carlo", "rs",
            "e prestige 60", "e sportline 60", "e sportline 85x",
            "coupe e sportline 60", "coupe e sportline 85x",
            "l&k crystal", "l n k crystal", "lk crystal",
            "sportline phev"
        ]

        # Teknik tablo olduğunu gösteren kelimeler (özellik tablosuysa bunlar az olsun istiyoruz)
        self.TECH_HINTS = [
            "silindir", "hacmi", "cc", "çap", "strok",
            "maks", "tork", "güç", "hp", "ps", "kw",
            "0-100", "ivme", "hız", "hiz",
            "tüketim", "l/100", "lt/100", "wltp",
            "co2", "emisyon",
            "uzunluk", "genişlik", "yükseklik",
            "dingil mesafesi", "bagaj", "ağırlık", "lastik"
        ]


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
        

        # __init__ sonunda:
        # --- init sonunda ---
        self._compile_spec_index()
        self._collect_all_data_texts()
        # --- Enyaq opsiyonları JSONL ile override ---
        self.ENYAQ_OPS_JSONL_PATH = os.getenv(
            "ENYAQ_OPS_JSONL_PATH",
            "/mnt/data/enyaq_enyaq_coupe_opsiyon_2025.jsonl"
        )
        self.ENYAQ_OPS_FROM_JSONL = {}
        try:
            if os.path.exists(self.ENYAQ_OPS_JSONL_PATH):
                self.ENYAQ_OPS_FROM_JSONL = self._load_enyaq_ops_from_jsonl(self.ENYAQ_OPS_JSONL_PATH)
                self.logger.info(f"[ENYAQ-OPS] JSONL yüklendi: {len(self.ENYAQ_OPS_FROM_JSONL)} trim")
                # Vector Store’a eklenen “ALL_DATA_TEXTS” içinde eski Enyaq opsiyon md'lerini çıkar (çiftlenmeyi önle)
                for k in list(self.ALL_DATA_TEXTS.keys()):
                    if k in {
                        "enyaq_data.ENYAQ_E_PRESTIGE_60_MD",
                        "enyaq_data.ENYAQ_COUPE_E_SPORTLINE_60_MD",
                        "enyaq_data.ENYAQ_COUPE_E_SPORTLINE_85X_MD",
                    }:
                        del self.ALL_DATA_TEXTS[k]
                        self.logger.info(f"[KB] Eski Enyaq opsiyon kaldırıldı: {k}")
        except Exception as e:
            self.logger.error(f"[ENYAQ-OPS] JSONL yükleme hatası: {e}")




        self.USE_OPENAI_FILE_SEARCH = os.getenv("USE_OPENAI_FILE_SEARCH", "0") == "1"
                # --- SQL RAG anahtarları ---
        self.USE_SQL_RAG          = os.getenv("USE_SQL_RAG", "1") == "1"
        self.SQL_RAG_ALWAYS_ON    = os.getenv("SQL_RAG_ALWAYS_ON", "1") == "1"
        self.SQL_RAG_HIDE_QUERY   = os.getenv("SQL_RAG_HIDE_QUERY", "1") == "1"
        self.HIDE_SOURCES         = os.getenv("HIDE_SOURCES", "1") == "1"
        self.VECTOR_STORE_SQL_NAME= os.getenv("VECTOR_STORE_SQL_NAME", "SkodaSQLKB")
        self.VECTOR_STORE_SQL_ID  = os.getenv("VECTOR_STORE_SQL_ID", "")
        self.SQL_RAG_DIRS         = [p.strip() for p in os.getenv(
            "SQL_RAG_DIRS", "modules/sql, sql, docs/sql"
        ).split(",") if p.strip()]
        # Her yanıta Vector Store özet bloğu eklensin mi? (varsayılan: açık)
        self.RAG_SUMMARY_EVERY_ANSWER = os.getenv("RAG_SUMMARY_EVERY_ANSWER", "1") == "1"
        self.logger.info(f"[KB] USE_OPENAI_FILE_SEARCH = {self.USE_OPENAI_FILE_SEARCH}")

        if self.USE_OPENAI_FILE_SEARCH:
            self.logger.info("[KB] Initializing vector store upload...")
            self._ensure_sql_vector_store_and_upload()

         # --- SQL RAG vector store'u hazırla ---
        if self.USE_SQL_RAG:
            self.logger.info("[SQL-RAG] Initializing SQL vector store upload...")
        from modules.trace_debug import traced_openai_client
        self.client = traced_openai_client(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

        self.client = traced_openai_client(self.client)

        # Debug: Hangi vector_stores API yüzeyi mevcut?
        try:
            vs_api = self._vs_api()
            self.logger.info(f"vector_stores available: {bool(vs_api)}")
        except Exception as e:
            # SDK sürümü farklı olabilir; sadece bilgi amaçlı
            self.logger.warning(f"vector_stores availability check failed: {e}")
        # --- Skoda dışı marka/model filtreleri (kelime sınırı ile güvenli) ---
        self.NON_SKODA_BRAND_PAT = re.compile(
            r"(?:\balfa\s*romeo\b|\baudi\b|\bbmw\b|\bmercedes(?:-benz)?\b|\bvolkswagen\b|\bvw\b|\bseat\b|\bcupra\b|"
            r"\bporsche\b|\bfiat\b|\bford\b|\bopel\b|\brenault\b|\bdacia\b|\bpeugeot\b|\bcitroen\b|\btoyota\b|"
            r"\blexus\b|\bhonda\b|\bhyundai\b|\bkia\b|\bnissan\b|\bmazda\b|\bvolvo\b|\bsuzuki\b|\bsubaru\b|"
            r"\bmitsubishi\b|\bjeep\b|\bland\s+rover\b|\brange\s+rover\b|\bjaguar\b|\btesla\b|\bmg\b|\bchery\b|"
            r"\bbyd\b|\btogg\b)",
            re.IGNORECASE
        )
        self.NON_SKODA_MODEL_PAT = re.compile(
            r"(?:\bgolf\b|\bpassat\b|\bpolo\b|\btiguan\b|\bt-?\s?roc\b|\bt-?\s?cross\b|"
            r"\bclio\b|\bm[eé]gane\b|\bfocus\b|\bfiesta\b|\bcivic\b|\bcorolla\b|\byaris\b|"
            r"\b208\b|\b2008\b|\b3008\b|\b308\b|\b508\b|\bcorsa\b|\bastra\b|\begea\b|"
            r"\bqashqai\b|\btucson\b|\bsportage\b|\bx-?trail\b|\bkona\b|\bceed\b|"
            r"\bmazda\s*3\b|\bcx-30\b|\bcx-5\b|\bxc40\b|\bxc60\b|\bmodel\s*(?:3|s|x|y)\b)",
            re.IGNORECASE
        )
        # __init__ sonunda
        self._load_non_skoda_lists()


    def _setup_logger(self):
        logger = logging.getLogger("ChatbotAPI")
        if not logger.handlers:
            handler = logging.StreamHandler()
            fileh = logging.FileHandler("pipeline.log", encoding="utf-8")  # ✅
            fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(fmt)
            fileh.setFormatter(fmt)
            logger.addHandler(handler)
            logger.addHandler(fileh)
        logger.setLevel(logging.INFO)
        return logger
    def _compile_spec_index(self):
            import re
            self._SPEC_INDEX = [
                (canon, [re.compile(pat, re.IGNORECASE) for pat in patterns])
                for canon, patterns in self.SPEC_SYNONYMS.items()
            ]
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
            enabled = maybe_enable_trace_from_payload(request)
            payload = request.get_json(silent=True) or request.form or {}
            if not isinstance(payload, dict):
                payload = {}

            msg = payload.get("question", "")
            uid = payload.get("user_id", username)

            with trace_request(user_id=uid, message=msg, enabled=enabled):
                tracer().route("HTTP", endpoint="/ask/<username>")

                # ✅ EKLE: session history oku ve state'e koy
                hist = session.get("skoda_chat_history", [])
                self.user_states.setdefault(uid, {})["neo4j_chat_history"] = hist

                return self._ask(username)


        @self.app.route("/ask", methods=["POST"])
        def ask_plain():
            enabled = maybe_enable_trace_from_payload(request)

            payload = request.get_json(silent=True) or request.form or {}
            if not isinstance(payload, dict):
                payload = {}

            msg = payload.get("question", "")
            uid = payload.get("user_id", "guest")

            with trace_request(user_id=uid, message=msg, enabled=enabled):
                tracer().route("HTTP", endpoint="/ask")
                # ✅ session history oku (bu kullanıcı için)
                hist = session.get("skoda_chat_history", [])
                # hist format: [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}, ...]

                # ✅ user_state içine koy (Neo4j çağrısında kullanacağız)
                self.user_states.setdefault(uid, {})["neo4j_chat_history"] = hist

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
        @self.app.route("/kb/reindex", methods=["POST"])
        def kb_reindex():
            if not self.HYBRID_RAG:
                return jsonify({"ok": False, "msg":"HYBRID_RAG kapalı"}), 400
            try:
                stats = self._kb_index_all()
                return jsonify({"ok": True, "inserted": stats, "total": int(sum(stats.values()))}), 200
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500
        @self.app.route("/neo4j/reindex", methods=["POST"])
        def neo4j_reindex():
            try:
                kb_path = os.path.join(self.app.static_folder, "kb", "SkodaKB.md")
                if not os.path.exists(kb_path):
                    kb_path = self._export_openai_glossary_text()

                if not getattr(self, "neo4j_graphrag", None) or not self.neo4j_graphrag.enabled:
                    return jsonify({"ok": False, "msg": "Neo4j GraphRAG kapalı"}), 400

                self.neo4j_graphrag.ingest_markdown(kb_path, reset=True)
                return jsonify({"ok": True, "msg": "Neo4j GraphRAG reindex tamam"}), 200
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500
        @self.app.route("/kb/search", methods=["GET"])
        def kb_search():
            q = request.args.get("q","")
            if not q:
                return jsonify({"ok": False, "msg":"q param"}), 400
            top = self._kb_vector_search(q, k=10)
            return jsonify({"ok": True, "items":[{"score":round(s,3),"model":d["model"],"table":d["table"],"text":d["text"][:300]} for s,d in top]})


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
        """
        Diakritik ve yazım varyasyonlarını 'görsel' kanonik sözcüğüne çevirir.
        Örn: 'kamiq gorsel', 'karoq foto', 'scala resimleri' -> '... görsel ...'
        """
        if not user_message:
            return user_message

        def repl(m: re.Match) -> str:
            # Yazının biçemine benzer biçim (BÜYÜK/başlık/küçük) korunsun
            return self._apply_case_like(m.group(0), "görsel")

        return self.IMAGE_SYNONYM_RE.sub(repl, user_message)

    def _correct_trim_typos(self, user_message: str) -> str:
        return user_message  # fuzzy düzeltme kaldırıldı

    

    def _apply_case_like(self, src: str, dst: str) -> str:
        """Kaynağın biçemine benzer biçimde hedefi döndür (BÜYÜK / Başlık / küçük)."""
        if src.isupper():
            return dst.upper()
        if src.istitle():
            return dst.title()
        return dst

    def _correct_model_typos(self, user_message: str) -> str:
        return user_message  # fuzzy düzeltme kaldırıldı

    def _search_in_assistant_cache(self, user_id, assistant_id, new_question, threshold):
        return None, None  # fuzzy cache KAPAL

    def _find_fuzzy_cached_answer(self, user_id: str, new_question: str, assistant_id: str, threshold=0.9):
        return None  # fuzzy cache KAPALI

    def _store_in_fuzzy_cache(self, user_id: str, username: str, question: str,
                              answer_bytes: bytes, assistant_id: str, conversation_id: int):
        if not getattr(self, "USE_ANSWER_CACHE", False):
            return
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
        Metindeki Skoda model adlarını diakritik güvenli şekilde yakalar.
        Örnek: 'Fabia'nın torku nedir?' → {'fabia'}
        """
        if not text:
            return set()

        # Normalize et
        s = normalize_tr_text(text).lower()

        # Model listesi
        MODELS = ["fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"]

        found = set()
        tokens = re.findall(r"[0-9a-zçğıöşü]+", s)
        tokens = [strip_tr_suffixes(t) for t in tokens]  # ✅ elroqun -> elroq
        token_set = set(tokens)
        for m in MODELS:
            if m in token_set:
                found.add(m)
        return found

 
    

     

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
        debug_on = False
        state = self.user_states.setdefault(user_id, {})
        state["_trace_id"] = _make_trace_id()

        self._tlog(
            user_id,
            "QUESTION_RECEIVED",
            username=username,
            question=user_message,
            path=getattr(request, "path", None),
        )

        from modules.trace_debug import tracer

        tracer().step("INPUT", user_id=user_id, q=user_message)

        try:
            debug_on = bool((data or {}).get("debug_trace"))
        except Exception:
            debug_on = False

        ctx = trace_request(user_id=user_id, message=user_message, enabled=debug_on) if debug_on else nullcontext()
        with ctx:
            tracer().route("HTTP", endpoint=getattr(request, "path", "/ask"))
            # ↓↓↓ mevcut _ask içeriğin burada olduğu gibi devam edecek ↓↓↓

        def _return_with_feedback(body: str | bytes):
            return self._respond_one_shot_with_feedback(
                user_id=user_id,
                user_message=user_message,   # orijinal mesaj
                username=name_surname,
                body=body
            )
        state = self.user_states.setdefault(user_id, {})
        # ✅ 0) Smalltalk her zaman kalsın (Skoda bağlamında ve hard intent değilse)
        state = self.user_states.setdefault(user_id, {})
        # ✅ KB_ONLY CS bloğu corrected_message bekliyor -> önce tanımla
        corrected_message = self._correct_all_typos(user_message or "")
        corrected_message = self._resolve_pending(user_id, corrected_message)
        corrected_message = self._rewrite_followup_if_needed(user_id, corrected_message)
        corrected_message, _, _ = self._apply_model_memory(user_id, corrected_message)
        self._tlog(
            user_id,
            "QUESTION_PARSED",
            original=user_message,
            corrected=corrected_message,
            models_now=models_now if "models_now" in locals() else None,
            domain=dom if "dom" in locals() else None,
            slot_models=slot_models if "slot_models" in locals() else None,
            slot_model=slot_model if "slot_model" in locals() else None,
        )

        # ✅✅ NEO4J ONLY: MSSQL'e giden her şeyi KES (EN ÜSTTE OLMALI)
        if os.getenv("NEO4J_ONLY", "0") == "1":
            # ❌ corrected_message (rewrite edilmiş uzun metin) KULLANMA
            neo_msg = self._correct_all_typos(user_message or "")
            neo_msg = self._resolve_pending(user_id, neo_msg)   # istersen kalsın
            # ❌ neo_msg = self._rewrite_followup_if_needed(...)  <-- BUNU YAPMA

            # (İstersen model enjekte de ETME; Neo4j zaten history’den çözecek)
            neo = (self._answer_via_neo4j_only(user_id, neo_msg) or "").strip()

            return self._respond_one_shot_with_feedback(
                user_id=user_id,
                user_message=user_message,
                username=name_surname,
                body=neo if neo else "Bu bilgi Neo4j bilgi tabanında bulunamadı."
            )

        slots = self._resolve_slots(user_id, corrected_message)
        self._tlog(user_id, "SLOTS_RESOLVED", slots=slots)

        domain = slots["domain"]
        slot_model = slots.get("model")
        slot_models = slots.get("models") or []
        # ✅ ZORUNLU: Compare bağlamında SPEC follow-up -> Neo4j (yoksa tek satır mesaj)
        if len(slot_models) >= 2 and self._is_spec_question(corrected_message):
            # 1) Neo4j dene
            neo = (self._answer_via_neo4j_only(user_id, corrected_message) or "").strip()
            if neo and (not self._is_answer_weak_global(corrected_message, neo)):
                return self._respond_one_shot_with_feedback(
                    user_id=user_id,
                    user_message=user_message,
                    username=name_surname,
                    body=neo
                )

            # 2) Neo4j boşsa: SQL/TEKNIK fallback (istersen bunu kapatabilirsin)
            txt = self._answer_multi_model_spec_any(corrected_message, slot_models)
            if txt:
                return self._respond_one_shot_with_feedback(
                    user_id=user_id,
                    user_message=user_message,
                    username=name_surname,
                    body=txt
                )

            # 3) ASLA segment listesi / asistan fallback yok
            return self._respond_one_shot_with_feedback(
                user_id=user_id,
                user_message=user_message,
                username=name_surname,
                body="Bu bilgi Neo4j bilgi tabanında bulunamadı."
            )

        # _ask içinde, multi-model fallback'e girmeden hemen önce:
        if len(slot_models) >= 2:
            # depo/bagaj/agirlik/menzil vs gibi teknik sinyal varsa direkt Neo4j dene
            qn = normalize_tr_text(corrected_message).lower()
            if any(k in qn for k in ["depo", "depo hacmi", "yakıt deposu", "yakit deposu", "tank"]):
                neo = (self._answer_via_neo4j_only(user_id, corrected_message) or "").strip()
                if neo and (not self._is_answer_weak_global(corrected_message, neo)):
                    return self._respond_one_shot_with_feedback(
                        user_id=user_id,
                        user_message=user_message,
                        username=name_surname,
                        body=neo
                    )

        # ✅ 2 model context varsa: model sorma, iki model için cevapla
        if self._needs_model_for_domain(domain) and (not slot_model) and len(slot_models) >= 2:
            # EQUIP multi
            if domain == "EQUIP" or self._is_equipment_presence_question(corrected_message) or self._is_equipment_query_by_evidence(user_id, corrected_message):
                txt = self._answer_equipment_presence_multi_models(user_id, corrected_message, slot_models)
                return self._respond_one_shot_with_feedback(
                    user_id=user_id,
                    user_message=user_message,
                    username=name_surname,
                    body=txt
                )

            # SPEC multi
            if domain == "SPEC" or self._is_spec_question(corrected_message):
                txt = self._answer_multi_model_spec_any(corrected_message, slot_models)
                if txt:
                    return self._respond_one_shot_with_feedback(
                        user_id=user_id,
                        user_message=user_message,
                        username=name_surname,
                        body=txt
                    )
            # SPEC multi
            if domain == "SPEC" or self._is_spec_question(corrected_message):
                txt = self._answer_multi_model_spec_any(corrected_message, slot_models)
                if txt:
                    return self._respond_one_shot_with_feedback(
                        user_id=user_id,
                        user_message=user_message,
                        username=name_surname,
                        body=txt
                    )

                # ✅ YENİ: multi-spec boşsa Neo4j dene
                neo = (self._answer_via_neo4j_only(user_id, corrected_message) or "").strip()
                if neo and (not self._is_answer_weak_global(corrected_message, neo)):
                    return self._respond_one_shot_with_feedback(
                        user_id=user_id,
                        user_message=user_message,
                        username=name_surname,
                        body=neo
                    )

            # PRICE multi (ne kadar / fiyat vb.)
            if domain == "PRICE" or self._is_price_intent(corrected_message):
                html = self._answer_price_multi_models(user_id, corrected_message, slot_models)
                return self._respond_one_shot_with_feedback(
                    user_id=user_id,
                    user_message=user_message,
                    username=name_surname,
                    body=html
                )

            # fallback: iki model var ama domain net değilse
            # fallback: iki model var ama domain net değilse -> PENDING set et
            st = self.user_states.setdefault(user_id, {})
            st["pending"] = {
                "kind": "domain_choice",
                "payload": {
                    "models": slot_models[:2],
                    "base_question": corrected_message,  # asıl soru
                },
                "created_at": time.time(),
                "expires_at": time.time() + 180,
            }

            return self._respond_one_shot_with_feedback(
                user_id=user_id,
                user_message=user_message,
                username=name_surname,
                body="Son iki model bağlamını kullanıyorum. Bu soruyu teknik mi (menzil/ağırlık/0-100/depo) yoksa donanım mı (var mı/standart mı) olarak cevaplayayım?"
            )


        # ✅ Tek model gerekiyorsa ve hiçbir model context yoksa -> eski davranış: model sor
        if self._needs_model_for_domain(domain) and not slot_model and len(slot_models) == 0:
            return self._respond_one_shot_with_feedback(
                user_id=user_id,
                user_message=user_message,
                username=name_surname,
                body="Bunu yanıtlayabilmem için hangi Škoda modeli olduğunu yazar mısınız? (Fabia/Scala/Kamiq/Karoq/Kodiaq/Octavia/Superb/Elroq/Enyaq)"
            )

        # ✅ İç route’larda kullanılacak mesaj:
        route_msg = corrected_message
        if slot_model and self._needs_model_for_domain(domain):
            try:
                if not self._extract_models_all(corrected_message):
                    route_msg = f"{slot_model} {corrected_message}".strip()
            except Exception:
                pass

        # ✅ İç route’larda kullanılacak mesaj:
        # Kullanıcı model yazmadıysa ama model gerekiyorsa, modele göre “route_msg” üret
        route_msg = corrected_message
        if slot_model and self._needs_model_for_domain(domain):
            # sadece kullanıcı mesajında model YOKSA enjekte et
            try:
                if not self._extract_models_all(corrected_message):
                    route_msg = f"{slot_model} {corrected_message}".strip()
            except Exception:
                pass

        # ✅ NEO4J ONLY: başka hiçbir kaynağa gitme
        from modules.trace_debug import tracer
        tracer().step("ENV_FLAGS", NEO4J_ONLY=os.getenv("NEO4J_ONLY",""), KB_ONLY=os.getenv("KB_ONLY",""), HYBRID_RAG=os.getenv("HYBRID_RAG",""))

        if os.getenv("NEO4J_ONLY", "0") == "1":
            tracer().step("ROUTE_DECISION", route="NEO4J_ONLY", reason="NEO4J_ONLY=1")
            out = self._answer_via_neo4j_only(user_id, corrected_message)
            if out:
                return _return_with_feedback(out)
            return _return_with_feedback("Bu bilgi Neo4j bilgi tabanında bulunamadı.")
        
        # ✅ DONANIM "var mı?" soruları: CS/LLM'e ASLA bırakma -> EquipmentList'ten çöz
        # ✅ DONANIM soruları: var mı şart değil (hangi pakette / standart mı / opsiyonel mi dahil)
        try:
            equip_domain = False
            try:
                equip_domain = (self._infer_domain(corrected_message) == "EQUIP")
            except Exception:
                equip_domain = False

            if equip_domain or self._is_equipment_presence_question(corrected_message) or self._is_equipment_query_by_evidence(user_id, corrected_message):
                tracer().step("ROUTE_DECISION", route="EQUIP_PIPELINE", reason="equip_domain/evidence/presence")
                txt = self._answer_equipment_presence_pipeline(user_id, corrected_message)
                return self._respond_one_shot_with_feedback(
                    user_id=user_id,
                    user_message=user_message,
                    username=name_surname,
                    body=txt
                )
        except Exception as e:
            self.logger.error(f"[EQUIP-STRICT] error: {e}")


        # ✅ Trip calc her şeyden önce
        if self._is_trip_calc_question(corrected_message):
            txt = self._answer_trip_calc(user_id, corrected_message)
            return _return_with_feedback(txt)

        det = self._try_deterministic_answer(user_id, corrected_message)
        if det:
            return _return_with_feedback(det)


        route_msg, _, _ = self._apply_model_memory(user_id, corrected_message)
        if self._is_tdi_question(corrected_message):
            txt = self._answer_tdi_rule(corrected_message)
            return _return_with_feedback(txt)
                    
        # ✅ KB_ONLY: ContextSearch / smalltalk / assistant route ASLA çalışmasın
        

        # ✅ önce fiyat/görsel gibi deterministik öncelikler kalsın (istersen kaldırabilirsin)
        price_intent_now = self._is_price_intent(corrected_message)
        is_image_now = (
            self.utils.is_image_request(corrected_message)
            or self._is_image_intent_local(corrected_message)
        )

        # ✅ 2+ model varsa -> direkt asistan
        models_now = self._extract_models_all(corrected_message)
        trims_now = list(extract_trims(corrected_message.lower())) if 'extract_trims' in globals() else []
        try:
            dom = self._infer_domain(corrected_message)
        except Exception:
            dom = "?"

        tracer().step("PARSE_SLOTS", models=models_now, trims=trims_now, domain=dom)
        # ✅ 2+ model + SPEC (ağırlık/menzil/0-100 vb.) => ASLA asistana gitme, SQL'den çöz
        if len(models_now) >= 2 and self._is_spec_question(corrected_message):
            tracer().step("ROUTE_DECISION", route="SPEC_MULTI_SQL", models=models_now, reason="2+models & spec_question")
            txt = self._answer_multi_model_spec_from_sql(corrected_message, models_now)
            if txt:
                return _return_with_feedback(txt)


        # ✅ 2+ model ama PRICE/IMAGE değil ve SPEC değil => eski davranış (asistan) kalsın
        if (len(models_now) >= 2) and (not price_intent_now) and (not is_image_now) and (not self._is_spec_question(corrected_message)):
            asst_id = self._pick_least_busy_assistant()
            if not asst_id:
                asst_id = self._pick_assistant_for_message(user_id, corrected_message)

            if asst_id:
                self.user_states.setdefault(user_id, {})["assistant_id"] = asst_id
                print("*************************************", asst_id)
                multi_model_base_instructions = (
                    "Sen Škoda Türkiye dijital satış danışmanısın.\n"
                    "KURAL: Kullanıcı mesajında birden fazla model geçti.\n"
                    "- Eğer kullanıcı net kıyas istemediyse önce 2-4 cümlelik özet ver, sonra 1 netleştirici soru sor.\n"
                    "- Kullanıcı kıyas istiyorsa (karşılaştır/kıyas/vs/fark) 4-6 cümleyle kısa kıyas yap; yine 1 soru ile bitir.\n"
                    "- Sadece: Fabia, Scala, Kamiq, Karoq, Kodiaq, Octavia, Superb, Elroq, Enyaq.\n"
                )

                out = self._ask_assistant_net(
                    user_id=user_id,
                    assistant_id=asst_id,
                    user_message=corrected_message,   # veya user_message
                    timeout=60.0,
                    ephemeral=True                  # konuşma hafızası istiyorsan False
                ) or ""

                if out.strip():
                    return self.app.response_class(
                        self._deliver_locally(body=out, original_user_message=user_message, user_id=user_id),
                        mimetype="text/html; charset=utf-8",
                    )

        # ✅ KB_ONLY modunda bile CS ratio hesapla ve state'e yaz
        try:
            from .ContextSearch import ContextSearch
            cs = ContextSearch()
            cs_result = cs.classify(route_msg)
            tracer().step("CS_ROUTE", answer_type=answer_type, ratio=r01)

            answer_type = cs_result.get("answer_type", "std")
            ratio = cs_result.get("ratio", 0.0)

            # ratio bazen 0-1 bazen 0-100 gelir → 0-1 normalize
            try:
                r = float(ratio or 0.0)
            except Exception:
                r = 0.0
            r01 = (r / 100.0) if r > 1.0 else r

            state["cs_answer_type"] = answer_type
            state["cs_ratio_raw"] = ratio
            state["cs_ratio_01"] = r01
            # ✅ ratio ~0.5 ise tabloyu özellikle okutma modu
            MINR = float(os.getenv("CS_TABLE_READ_MIN", "0.40"))
            MAXR = float(os.getenv("CS_TABLE_READ_MAX", "0.70"))
            state["force_table_read"] = (MINR <= r01 <= MAXR)

            # ✅ NEW: STD ama ratio orta/düşükse önce KbVectors (Hybrid RAG) dene
           # ✅ İSTEDİĞİN ROUTE:
            # ratio 1.0 değilse -> KbVectors'a hiç girme, direkt beta.threads assistant cevaplasın
            # ✅ Opsiyonel donanım listesi sorusuysa: ratio ne olursa olsun ASİSTANA git
            if answer_type == "std" and self._is_optional_list_intent(corrected_message):
                md = self._price_row_from_pricelist(corrected_message, user_id=user_id)

                # ✅ PriceList bulduysa: SADECE onu dön (asistan yok, KB yok)
                if md:
                    return self.app.response_class(
                        self._deliver_locally(
                            body=md,
                            original_user_message=user_message,
                            user_id=user_id,
                            strip_price=False   # ✅ kritik
                        ),
                        mimetype="text/html; charset=utf-8",
                    )

                # ✅ PriceList’te bulunamadıysa: sadece net soru sor, fallback yapma
                return self.app.response_class(
                    "Opsiyonel donanımları listeleyebilmem için hangi Škoda modeli ve (varsa) hangi donanım seviyesi olduğunu yazar mısınız? "
                    "Örn: 'Kamiq Premium opsiyonel donanımlar'."
                    .encode("utf-8"),
                    mimetype="text/html; charset=utf-8",
                )


            

            self.logger.info(f"[CS-ROUTE] (KB_ONLY) text='{user_message}' → {answer_type.upper()} | ratio={r01:.3f}")

        except Exception as e:
            self.logger.error(f"[ContextSearch ERROR] (KB_ONLY) {e}")
            state["cs_answer_type"] = "std"
            state["cs_ratio_raw"] = 0.0
            state["cs_ratio_01"] = 0.0

        if (
            (not self._assistant_asked_question_recently(user_id))   # ✅ EKLE
            and self._is_skoda_smalltalk_context(route_msg)
            and not self._is_hard_car_intent(route_msg)
        ):
            state["smalltalk_mode"] = True
            smalltalk_bytes = self._answer_smalltalk_via_openai(user_message, user_id)
            return _return_with_feedback(smalltalk_bytes)

        if state.get("smalltalk_mode") and not self._is_hard_car_intent(user_message):
            smalltalk_bytes = self._answer_smalltalk_via_openai(user_message, user_id)
            return _return_with_feedback(smalltalk_bytes)

        # Buraya geldiysek artık “hard car intent” var → smalltalk moddan çık
        state["smalltalk_mode"] = False

        # _ask içinde, user_message/user_id alındıktan hemen sonra:
        if getattr(self, "KB_ONLY", False):
            def gen():
                out = b""
                try:
                    for chunk in self._generate_response(route_msg, user_id, username=name_surname):

                        if not isinstance(chunk, (bytes, bytearray)):
                            chunk = str(chunk).encode("utf-8")

                        # ✅ KRİTİK: her chunk sanitize edilsin (segment listesi / yasak bloklar çıkar)
                        chunk = self._sanitize_bytes(chunk)

                        yield chunk
                        out += chunk

                finally:
                    # db kaydı yine yapılsın istiyorsan:
                    full_answer = out.decode("utf-8", errors="ignore")
                    self.user_states.setdefault(user_id, {})["last_assistant_answer"] = full_answer

                    self._update_active_model_from_answer(user_id, user_message, full_answer)
                    # ✅ pending set: asistan soru sorduyse follow-up bekle
                    try:
                        kind, payload = self._pending_from_assistant_text(full_answer)
                        if kind:
                            self._maybe_set_pending(
                                user_id=user_id,
                                assistant_text=full_answer,
                                context={"pending_kind": kind, "pending_payload": payload}
                            )
                        else:
                            # yeni turda pending kalmasın
                            self.user_states.setdefault(user_id, {})["pending"] = None
                    except Exception as e:
                        self.logger.error(f"[PENDING] set fail: {e}")

                    conversation_id = save_to_db(user_id, user_message, full_answer, username=name_surname)
                    #yield f"\n[CONVERSATION_ID={conversation_id}]".encode("utf-8")
                    yield self._feedback_marker(conversation_id)
                    #yield self._feedback_buttons_html(conversation_id).encode("utf-8")

                    # ✅ UI'ya ratio taşı: gizli marker
                    if os.getenv("SHOW_CS_RATIO", "1") == "1":
                        cs_route = (self.user_states.get(user_id, {}) or {}).get("cs_answer_type", "std")
                        cs_ratio = float((self.user_states.get(user_id, {}) or {}).get("cs_ratio_01", 0.0) or 0.0)
                        yield (
                            f'<span class="cs-marker" data-cs-route="{cs_route}" '
                            f'data-cs-ratio="{cs_ratio:.3f}" style="display:none"></span>'
                        ).encode("utf-8")

            return self.app.response_class(stream_with_context(gen()), mimetype="text/html; charset=utf-8")

        # 1) Yeni mesaj klasik selam / small talk ise → smalltalk_mode başlat
        if (
            state.get("smalltalk_mode")
            and (not self._assistant_asked_question_recently(user_id))  # ✅ EKLE
            and not self._is_hard_car_intent(user_message)
        ):
            smalltalk_bytes = self._answer_smalltalk_via_openai(user_message, user_id)
            return _return_with_feedback(smalltalk_bytes)


        if state.get("smalltalk_mode") and not self._is_hard_car_intent(user_message):
            smalltalk_bytes = self._answer_smalltalk_via_openai(user_message, user_id)
            return self.app.response_class(
                smalltalk_bytes,
                mimetype="text/html; charset=utf-8",
            )

        # 3) Buraya geldiysek artık ciddi bir araç isteği var → smalltalk moddan çık
        state["smalltalk_mode"] = False
        if not user_message:
            return jsonify({"response": "Please enter a question."})

        # 🔹 1) Selam / küçük sohbet ise direkt DSD ile yanıt ver, SQL/ContextSearch'e hiç girme
        if self._is_smalltalk_message(user_message):
            smalltalk_bytes = self._answer_smalltalk_via_openai(user_message, user_id)
            return self.app.response_class(
                smalltalk_bytes,
                mimetype="text/html; charset=utf-8",
            )

        # 🔹 2) Devamında ContextSearch vs. normal akış
        # Session aktivite kontrolü
        if 'last_activity' not in session:
            session['last_activity'] = time.time()
        else:
            session['last_activity'] = time.time()

        # Session aktivite kontrolü
        if 'last_activity' not in session:
            session['last_activity'] = time.time()
        else:
            session['last_activity'] = time.time()

        # --- MESAJI DÜZELT + MODEL BAĞLAMINI ENJEKTE ET ---
        # --- Mesajı düzelt + model hafızasını uygula ---
        corrected_message, user_models_in_msg, lower_corrected = self._apply_model_memory(user_id, user_message)

        price_intent = self._is_price_intent(corrected_message)
        # 💰 1) FİYAT SORULARINI EN BAŞTA KISA DEVRE ET
        if price_intent:
            def price_generator():
                md = self._price_row_from_pricelist(corrected_message, user_id=user_id)
                if md:
                    yield md.encode("utf-8")
                    return
                for chunk in self._yield_fiyat_listesi(corrected_message, user_id=user_id):
                    yield chunk

            wrapped = self._wrap_stream_with_feedback(
                price_generator(),
                user_id=user_id,
                user_message=user_message,
                username=name_surname
            )

            return self.app.response_class(
                stream_with_context(wrapped),
                mimetype="text/html; charset=utf-8",
            )


                # ==========================
        #  CONTEXT SEARCH ROUTING
        # ==========================
        from .ContextSearch import ContextSearch

        try:
            cs = ContextSearch()
            cs_result = cs.classify(route_msg)
            answer_type = cs_result.get("answer_type", "std")
            ratio = cs_result.get("ratio", 0.0)

            self.logger.info(f"[CS-ROUTE] text='{corrected_message}' → {answer_type.upper()} | ratio={ratio}")
            print(f">> ROUTE: '{corrected_message}' → {answer_type.upper()} (ratio={ratio})")
            # ✅ ratio < 40% ise kullanıcıdan tekrar sor (LLM/SQL'e gitme)
            try:
                r = float(ratio or 0.0)
            except Exception:
                r = 0.0

            # ratio bazen 0-1 bazen 0-100 gelebilir -> normalize et
            r01 = (r / 100.0) if r > 1.0 else r
            state["cs_answer_type"] = answer_type
            state["cs_ratio_raw"] = ratio
            state["cs_ratio_01"] = r01
            # ✅ BURAYA EKLE (ratio=0.0 override)
            if r01 <= 0.0001:
                asst_id = self._pick_assistant_for_message(user_id, corrected_message) or self._pick_least_busy_assistant()
                if asst_id:
                    self.user_states.setdefault(user_id, {})["assistant_id"] = asst_id
                    out = self._ask_assistant(
                        user_id=user_id,
                        assistant_id=asst_id,
                        content=corrected_message,
                        timeout=60.0,
                        instructions_override=(
                            "Sen Škoda Türkiye dijital satış danışmanısın. "
                            "Varsayım yapma, fiyat uydurma. 2-6 cümle, sonda 1 kısa soru."
                        ),
                        ephemeral=False
                    ) or ""
                    if out.strip():
                        return self.app.response_class(
                            self._deliver_locally(body=out, original_user_message=user_message, user_id=user_id),
                            mimetype="text/html; charset=utf-8",
                        )
            # ✅ EKLEME BİTTİ
            LOW_GATE = float(os.getenv("CS_LOW_GATE", "0.40"))

            if r01 < LOW_GATE:
                # ✅ Donanım var/yok sorusu veya ✅ teknik/spec sorusu ise DB/SQL akışına izin ver
                if (
                    (self._extract_models(corrected_message) and self._is_equipment_presence_question(corrected_message))
                    or self._is_spec_question(corrected_message)      # ✅ EKLE
                ):
                    self.logger.info("[CS-ROUTE] low ratio ama EQUIP/SPEC → DB/SQL akışına izin verildi")
                else:
                    tracer().step("ROUTE_DECISION", route="ASSISTANT", reason="fallback_via_chat")
                    txt = self._fallback_via_chat(
                        user_id=user_id,
                        user_message=corrected_message,
                        reason=f"CS low confidence r01={r01:.3f}"
                    )
                    return _return_with_feedback(txt)


            # 🔹 Küçük sohbetler / ratio düşük sınıf 'llm' ise → direkt sohbet modu
            if answer_type == "llm":
                print(">> LLM ROUTE ENTERED → smalltalk via OpenAI")
                smalltalk_bytes = self._answer_smalltalk_via_openai(corrected_message, user_id)
                 

                # Burada streaming kullanmıyoruz; tek seferlik kısa cevap yeterli
                return self.app.response_class(
                    smalltalk_bytes,
                    mimetype="text/html; charset=utf-8",
                )

        except Exception as e:
            self.logger.error(f"[ContextSearch ERROR] {e}")



        # ==========================
        #  ROUTE BİTİŞİ (DB MODU)
        # ==========================

        # (DB sadece answer_type == 'std' olduğunda devreye girer)

        # Session aktivite kontrolü
        if 'last_activity' not in session:
            session['last_activity'] = time.time()
        else:
            session['last_activity'] = time.time()

        corrected_message = self._correct_all_typos(user_message)
        lower_corrected = corrected_message.lower().strip()
        user_models_in_msg = self._extract_models(corrected_message)
        # EK: sırayı korumak için
        pairs_for_order = extract_model_trim_pairs(corrected_message.lower())
        ordered_models = []
        for m, _ in pairs_for_order:
            if m not in ordered_models:
                ordered_models.append(m)
        # fallback: sadece set ile yakalandıysa
        if not ordered_models and user_models_in_msg:
            ordered_models = list(user_models_in_msg)

        # === YENİ: iki-model bağlamı (cmp_models) güncelle
        pair = list(state.get("cmp_models", []))   # <-- güvenli

        if len(ordered_models) >= 2:
            pair = ordered_models[:2]  # “son yazılan” iki model bağlam olur
        elif len(ordered_models) == 1:
            m = ordered_models[0]
            if not pair:
                pair = [m]
            elif m not in pair:
                # “yeni model” geldiyse çifti kaydır: eski son + yeni
                # (ör. [fabia, scala] varken kullanıcı “karoq” yazdı → [scala, karoq])
                pair = [pair[-1], m]
        # len==0 ise hiçbir şey yapma (pair aynen kalsın)

        self.user_states[user_id]["cmp_models"] = pair[:2]
        price_intent = self._is_price_intent(corrected_message)
        # _ask veya _generate_response başında, düzeltmelerden sonra:
        if self._mentions_non_skoda(corrected_message):
            return self.app.response_class("Üzgünüm sadece Skoda hakkında bilgi verebilirim.", mimetype="text/plain")

        if user_id not in self.user_states:
            self.user_states[user_id] = {}
         # --- NEW: Bu oturumda önceki kullanıcı sorusunu bağlam olarak kullanacağız
        prev_q = self.user_states.get(user_id, {}).get("last_user_message")
        self.user_states[user_id]["prev_user_message"] = prev_q
        prev_ans = (self.user_states.get(user_id, {}) or {}).get("last_assistant_answer")
        self.user_states[user_id]["prev_assistant_answer"] = prev_ans

        # Gevşek model yakalama: kullanıcı yeni bir model yazmaya çalışıyorsa 'last_models' enjekte ETME
        loose_models_now = self._extract_models_loose(corrected_message) | self._extract_models_spaced(corrected_message)
        if not user_models_in_msg and loose_models_now:
            user_models_in_msg = loose_models_now  # yeni/gevşek model yakalandı
            # NOT: corrected_message'a eski modeli EKLEME!

        last_models = self.user_states[user_id].get("last_models", set())
        cm = (self.user_states.get(user_id, {}) or {}).get("cmp_models") or []
        if (not user_models_in_msg) and last_models and (len(last_models) == 1) and (len(cm) < 2) and (not price_intent):
            joined_models = " ve ".join(last_models)
            corrected_message = f"{joined_models} {corrected_message}".strip()
            user_models_in_msg = self._extract_models(corrected_message)
            lower_corrected = corrected_message.lower().strip()
        # Sadece hiçbir model sinyali YOKSA ve fiyat niyeti de değilse eski modeli ekle
        if (not user_models_in_msg) and (not loose_models_now) and last_models and (not price_intent):
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

        lower_corrected = corrected_message.lower().strip()
        is_image_req = (
            self.utils.is_image_request(corrected_message)
            or self._is_image_intent_local(corrected_message)
        )
        user_trims_in_msg = extract_trims(lower_corrected)
        old_assistant_id = self.user_states[user_id].get("assistant_id")
        new_assistant_id = None


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
        
                    

        final_answer_parts = []

        def caching_generator():
            try:
                for chunk in self._generate_response(corrected_message, user_id, name_surname):
                    if not isinstance(chunk, (bytes, bytearray)):
                        chunk = str(chunk).encode("utf-8")

                    # (YENİ) Tüm parçalarda kaynak/citation temizliği
                    chunk = self._sanitize_bytes(chunk)

                    final_answer_parts.append(chunk)
                    yield chunk

            except Exception as ex:
                # Hata loglansın ama KULLANICIYA GÖSTERİLME-SİN.
                self.logger.exception("caching_generator hata")
                # Hiçbir şey yield etmeyin; aşağıdaki 'finally' yine çalışacak (kayıt vb.)
                # İsterseniz burada sadece 'pass' bırakabilirsiniz.
                pass
            finally:
                # ➊ Her yanıta Vector Store kısa özeti ekleyin (mümkünse)
                try:
                    for rag_chunk in self._yield_rag_summary_block(
                        user_id=user_id,
                        user_message=corrected_message
                    ):
                        rag_chunk = self._sanitize_bytes(rag_chunk)  # (YENİ)
                        final_answer_parts.append(rag_chunk)
                        yield rag_chunk

                except Exception as _e:
                    self.logger.error(f"[RAG-SUMMARY] streaming failed: {_e}")
                # ➊.b SQL RAG bloğu (ayrı vector store)
                try:
                    for sql_chunk in self._yield_sql_rag_block(
                        user_id=user_id, user_message=corrected_message
                    ):
                        sql_chunk = self._sanitize_bytes(sql_chunk)
                        final_answer_parts.append(sql_chunk)
                        yield sql_chunk
                except Exception as _e:
                    self.logger.error(f"[SQL-RAG] streaming failed: {_e}")
                # ➋ Artık final_answer_parts yalnızca bytes: bu join düşmez
                full_answer = b"".join(final_answer_parts).decode("utf-8", errors="ignore")
                conversation_id = save_to_db(user_id, user_message, full_answer, username=name_surname)
                # ✅ Asistan cevabından aktif modeli güncelle
                self._update_active_model_from_answer(user_id, user_message, full_answer)

                self.user_states[user_id]["last_conversation_id"] = conversation_id
                self.user_states[user_id]["last_user_message"] = user_message
                self.user_states[user_id]["last_assistant_answer"] = full_answer
                #yield f"\n[CONVERSATION_ID={conversation_id}]".encode("utf-8")
                yield self._feedback_marker(conversation_id)
                #yield self._feedback_buttons_html(conversation_id).encode("utf-8")

                # ✅ Cevabın sonuna CS ratio marker (gizli) ekle
                if os.getenv("SHOW_CS_RATIO", "1") == "1":
                    cs_route = (self.user_states.get(user_id, {}) or {}).get("cs_answer_type", "std")
                    cs_ratio = float((self.user_states.get(user_id, {}) or {}).get("cs_ratio_01", 0.0) or 0.0)
                    yield (
                        f'<span class="cs-marker" data-cs-route="{cs_route}" '
                        f'data-cs-ratio="{cs_ratio:.3f}" style="display:none"></span>'
                    ).encode("utf-8")
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
      
     
    ##############################################################################
# ChatbotAPI._generate_response
##############################################################################
    def _generate_response(self, user_message: str, user_id: str, username: str = ""):
    # ✅ KB_ONLY: hiçbir SQL tablo/MD/bridge/smalltalk yoluna girme
    # ✅ 0) Model hakkında genel bilgi isteği mi? (KB_ONLY'den önce!)
        # ✅ DB-ONLY MODE: kullanıcıya tablo/ham metin YIELD ETME, tek final cevap üret
        # ✅ 1) KB_ONLY her şeyden önce
        # ChatbotAPI._generate_response içinde, en baştaki KB_ONLY bloğu
        # _generate_response başlarında:
        # ✅ TRIP CALC her şeyden önce (KB_ONLY dahil)
        slots = self._resolve_slots(user_id, user_message)
        domain = slots["domain"]
        m = slots["model"]

        route_msg = user_message
        if m and (not self._extract_models_all(user_message)):
            if self._needs_model_for_domain(domain) or self._looks_like_trim_only_reply(user_message) or self._looks_like_followup(user_message):
                route_msg = f"{m} {user_message}".strip()

        # bundan sonra _generate_response içinde user_message yerine route_msg kullan
        user_message = route_msg
        if os.getenv("NEO4J_ONLY", "0") == "1":
            out = self._answer_via_neo4j_only(user_id, user_message)  # ✅ corrected_message değil
            if out:
                yield self._deliver_locally(body=out, original_user_message=user_message, user_id=user_id)
                return
            yield self._deliver_locally(body="Bu bilgi Neo4j bilgi tabanında bulunamadı.", original_user_message=user_message, user_id=user_id)
            return

        try:
            if self._is_trip_calc_question(user_message):
                txt = self._answer_trip_calc(user_id, user_message)
                yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
                return
        except Exception as e:
            self.logger.error(f"[TRIP] calc failed: {e}")

        msg_norm = normalize_tr_text(user_message or "").lower()
        if any(k in msg_norm for k in ["daha detay", "detaylı", "detay ver", "detayli", "ayrıntı", "ayrinti"]):
            st = self.user_states.get(user_id, {}) or {}
            last = st.get("last_trim_diff")
            if last:
                m = last["model"]; a = last["a"]; b = last["b"]
                txt = self._answer_trim_diff_from_sql(m, a, b, detailed=True)
                yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
                return

        if self._is_tdi_question(user_message):
            txt = self._answer_tdi_rule(user_message)
            yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
            return
        # ✅ KB_ONLY: model önerisi sorusu -> direkt beta threads (asistan) ile cevapla
        if self._is_model_recommendation_intent(user_message):
            txt = self._fallback_via_chat(user_id, user_message, reason="RECO_INTENT_KB_ONLY")
            yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
            return

        if getattr(self, "KB_ONLY", False):
            user_message, _, _ = self._apply_model_memory(user_id, user_message)
            # ✅ (EKLE) FİYAT sorusu ise: önce PriceList_KODA_<MODEL> tablosundan çek
            if self._is_price_intent(user_message):
                self.logger.info(f"[PRICE-KB_ONLY] route to PriceList: {user_message!r}")

                md = self._price_row_from_pricelist(user_message, user_id=user_id)

                # PriceList’te opsiyon satırını bulduysa -> SADECE onu dön
                if md:
                    # ⚠️ strip_price=False önemli, yoksa fiyatları kendin siliyorsun
                    yield self._deliver_locally(
                        body=md,
                        original_user_message=user_message,
                        user_id=user_id,
                        strip_price=False
                    )
                    return

                # Bulamadıysa: en azından genel fiyat listesine düş (istersen burada netleştirici soru da sorabilirsin)
                for chunk in self._yield_fiyat_listesi(user_message, user_id=user_id):
                    yield chunk
                return
                        # ✅ KB_ONLY: Donanım soruları (EQUIP) → KbVectors'a girmeden EquipmentList'ten çöz
            try:
                equip_domain = (self._infer_domain(user_message) == "EQUIP")
            except Exception:
                equip_domain = False

            if equip_domain or self._is_equipment_presence_question(user_message):
                try:
                    txt = self._answer_equipment_presence_strict(user_id, user_message)
                    yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
                    return
                except Exception as e:
                    self.logger.error(f"[KB_ONLY][EQUIP] strict answer failed: {e}")
                    # buradan devam edip KbVectors'a düşmesine izin verebiliriz

            threshold = float(os.getenv("KB_FALLBACK_THRESHOLD", "0.45"))

            # ✅ CS ratio gate (KB_ONLY'de kritik)
            st = (self.user_states.get(user_id, {}) or {})
            try:
                r01 = float(st.get("cs_ratio_01") or 0.0)
            except Exception:
                r01 = 0.0
            ans_type = str(st.get("cs_answer_type") or "").lower()

            # İstersen .env'den ayarla:
            # CS_ASSISTANT_GATE=0.99  -> 1.00 değilse asistana
            CS_ASSISTANT_GATE = float(os.getenv("CS_ASSISTANT_GATE", "0.99"))

            # deterministik intentler (bunlarda asistana kaçma)
            # deterministik intentler (bunlarda asistana kaçma)
            is_price = self._is_price_intent(user_message)

            # ✅ YENİ: Donanım intentini geniş yakala (var mı şart değil)
            try:
                dom = self._infer_domain(user_message)  # "EQUIP" / "SPEC" / "PRICE" / "OTHER"
            except Exception:
                dom = "OTHER"

            is_equip = (dom == "EQUIP")

            # Ek kanıt (özellikle "hangi pakette/donanımda" sorularında)
            if not is_equip:
                try:
                    is_equip = bool(self._is_equipment_query_by_evidence(user_id, user_message))
                except Exception:
                    is_equip = False

            # (İsteğe bağlı ama faydalı) direkt phrase yakalama
            if not is_equip:
                qn = normalize_tr_text(user_message).lower()
                equip_triggers = [
                    "hangi paket", "hangi pakette",
                    "hangi donanım", "hangi donanımda", "hangi donanim", "hangi donanimda",
                    "hangi versiyon", "hangi versiyonda",
                    "standart mı", "opsiyonel mi", "opsiyon mu",
                    "sunuluyor mu", "bulunuyor mu", "mevcut mu", "geliyor mu"
                ]
                if any(k in qn for k in equip_triggers):
                    is_equip = True

            # Teknik intent
            try:
                is_spec = bool(self._spec_key_from_query(user_message))
            except Exception:
                is_spec = False

            # Görsel intent (deterministik)
            is_image = (
                self.utils.is_image_request(user_message)
                or self._is_image_intent_local(user_message)
            )

            # ✅ CS gate: sadece "gerçekten belirsiz" sorularda asistana kaç
            # ✅ CS gate: emin değilsek (ratio düşükse) -> Neo4j’ye düş
            # ✅ 1) KB_ONLY'de ÖNCE KbVectors dene (Hybrid RAG / KbVectors_* tabloları)
            best = self._kb_best_hit(user_message, user_id=user_id)
            if best:
                best_score, best_meta = best
                self.logger.info(
                    f"[KB-FIRST] best_score={best_score:.3f} threshold={threshold:.3f} "
                    f"table={best_meta.get('table')} group={best_meta.get('group')}"
                )

                if best_score >= threshold:
                    # 1) SQL satırına geri dön (en doğru değer için kritik!)
                    row = None
                    try:
                        # ✅ KB hit’inden model yakalayıp active_model’i kilitle
                        m2 = (best_meta.get("model") or "").strip().lower()
                        if m2 in {"fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"}:
                            self._set_active_model(user_id, m2)

                        row = self._kb_postfetch_row(
                            best_meta.get("table"),
                            str(best_meta.get("row_key"))
                        )
                    except Exception:
                        row = None

                    # 2) Postfetch geldiyse facts üret
                    if row:
                        facts = self._facts_from_kb_row(
                            group=best_meta.get("group", "OTHER"),
                            table_name=best_meta.get("table"),
                            row=row,
                            user_message=user_message
                        )

                        # EQUIP ise deterministik cümle
                        if facts.get("kind") == "EQUIP":
                            try:
                                trims = [x["trim_col"] for x in facts.get("status", [])]
                                status_map = {x["trim_col"]: x["status"] for x in facts.get("status", [])}
                                sent = self._nlg_equipment_status(
                                    model_name=(facts.get("model") or "").lower(),
                                    feature=facts.get("title") or "Sorgulanan donanım",
                                    trims=trims,
                                    status_map=status_map
                                )
                                if sent:
                                    yield self._deliver_locally(
                                        body=sent,
                                        original_user_message=user_message,
                                        user_id=user_id
                                    )
                                    return
                            except Exception:
                                pass

                        # SPEC / OTHER: LLM ile satış danışmanı cümlesi (facts tabanlı)
                        txt = self._nlg_sales_from_facts(facts, user_message)
                        if txt:
                            yield self._deliver_locally(
                                body=txt,
                                original_user_message=user_message,
                                user_id=user_id
                            )
                            return

                    # 3) Postfetch yoksa: son çare KB metnini kullan
                    kb_text = (best_meta.get("text") or "").strip()
                    grp = best_meta.get("group")

                    if kb_text:
                        ok = self._verify_answer_fit(
                            user_message,
                            kb_text,
                            group=grp,
                            score=float(best_score),
                            strict=True
                        )
                        if not ok:
                            txt = "KbVectors tablosunda sorunuza uygun bir kayıt bulunamadı."
                            yield self._deliver_locally(
                                body=txt,
                                original_user_message=user_message,
                                user_id=user_id
                            )
                            return

                        yield self._deliver_locally(
                            body=kb_text,
                            original_user_message=user_message,
                            user_id=user_id
                        )
                        return

            # ✅ 2) KbVectors yetmezse / yoksa -> Neo4j (isteğe bağlı gate ile)
            CS_NEO4J_GATE = float(os.getenv("CS_NEO4J_GATE", "0.99"))

            # NOT: ans_type ve r01 yukarıda hesaplanmış olmalı (KB_ONLY içinde zaten var)
            #      is_price / is_equip / is_spec / is_image de yukarıda hesaplanmış olmalı
            if (ans_type == "std") and (r01 < CS_NEO4J_GATE) and (not is_price) and (not is_equip) and (not is_spec) and (not is_image):
                self.logger.info(f"[KB→NEO] no kb hit; going neo4j (r01={r01:.3f} gate={CS_NEO4J_GATE})")

                neo = (self._answer_via_neo4j_only(user_id, user_message) or "").strip()
                if neo and (not self._is_answer_weak_global(user_message, neo)):
                    yield self._deliver_locally(
                        body=neo,
                        original_user_message=user_message,
                        user_id=user_id
                    )
                    return

            # ✅ 3) Hâlâ yoksa: KB_ONLY modunda net mesaj (Assistant'a kaçma)
            yield self._deliver_locally(
                body="KbVectors tablosunda bu soruya karşılık gelen kayıt bulunamadı.",
                original_user_message=user_message,
                user_id=user_id
            )
            #return



    # ... mevcut KB_ONLY akışın devam etsin ...

                # ✅ KB_ONLY + DONANIM "var mı?" soruları: önce EquipmentList'ten deterministik cevap ver
            if self._is_equipment_presence_question(user_message) or self._is_equipment_query_by_evidence(user_id, user_message):
                # modeli yakala (mesajdan ya da state'ten)
                model = None
                try:
                    model = self._current_model(user_id, user_message)
                except Exception:
                    model = None
                if not model:
                    ms = list(self._extract_models(user_message or ""))
                    model = ms[0] if ms else None

                if not model:
                    txt = (
                        "Elektrikli koltuk bilgisini netleştirebilmem için hangi Škoda modelini sorduğunu yazar mısın? "
                        "Örn: 'Karoq elektrikli koltuk var mı?'"
                    )
                    yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
                    return
                self._set_active_model(user_id, model)
                
                trims, status_map, feature_title = self._feature_lookup_any(model, user_message)
                # ✅ ZORUNLU: soru ↔ feature_title uyumlu mu?
                if feature_title:
                    if not self._is_safe_equipment_match(user_message, feature_title):
                        # emin değilsek LLM YES/NO da sor (çok kısa)
                        if not self._llm_verify_hit(user_message, feature_title):
                            trims, status_map, feature_title = [], {}, None
                if trims and status_map:
                    feat = feature_title or "Sorgulanan donanım"

                    sent = self._nlg_equipment_status(
                        model_name=model,
                        feature=feat,
                        trims=trims,
                        status_map=status_map,
                    )

                    body = (sent or "").strip()
                    if not body:
                        body = f"{model.title()} için '{feat}' bilgisini buldum. Hangi donanım seviyesini (Premium/Prestige/Sportline) baz alayım?"

                    yield self._deliver_locally(
                        body=body,
                        original_user_message=user_message,
                        user_id=user_id
                    )
                    return


                # EquipmentList'te net kayıt yoksa: ASLA "evet" deme, sadece netleştir
                txt = "Bu modelde istediğiniz özellik bulunmamaktadır."
                yield self._deliver_locally(
                    body=txt,
                    original_user_message=user_message,
                    user_id=user_id
                )
                return
            # ✅ KB_ONLY + TEKNİK soru (ağırlık, menzil, tork, 0-100, vb.) -> önce SQL’den çek
            spec_key = None
            models_now = self._extract_models_all(user_message or "")
            if len(models_now) >= 2 and self._is_spec_question(user_message):
                txt = self._answer_multi_model_spec_from_sql(user_message, models_now)
                if txt:
                    yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
                    return
                # ✅ YENİ: SQL boşsa Neo4j fallback
            neo = (self._answer_via_neo4j_only(user_id, user_message) or "").strip()
            if neo and (not self._is_answer_weak_global(user_message, neo)):
                yield self._deliver_locally(body=neo, original_user_message=user_message, user_id=user_id)
                return

            try:
                spec_key = self._spec_key_from_query(user_message)  # 'agirlik', 'menzil' vs
            except Exception:
                spec_key = None

            if spec_key:
                model = None
                try:
                    model = self._current_model(user_id, user_message)
                except Exception:
                    model = None
                if not model:
                    ms = list(self._extract_models(user_message or ""))
                    model = ms[0] if ms else None

                # model yoksa bile "asistan" route
                if not model:
                    txt = self._fallback_via_chat(user_id, user_message, reason="KB_ONLY_SPEC_NO_MODEL")
                    yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
                    return
                self._set_active_model(user_id, model)
                val, canon_key, row_md = self._generic_spec_from_sql(model, user_message, return_meta=True)
               

                if val:
                    # ✅ Sadece yazı istendiği için tabloyu asla ekleme
                    text = self._emit_spec_sentence(model, canon_key or "Değer", val).decode("utf-8", "ignore")
                    yield self._deliver_locally(body=text, original_user_message=user_message, user_id=user_id)
                    return
                 # KB_ONLY + TEKNİK soru bloğunda (spec_key bulunduysa)
                # ✅ BURAYA EKLE: SQL’de yoksa Neo4j dene
                neo = (self._answer_via_neo4j_only(user_id, user_message) or "").strip()
                if neo and (not self._is_answer_weak_global(user_message, neo)):
                    yield self._deliver_locally(body=neo, original_user_message=user_message, user_id=user_id)
                    return
                if spec_key in {"guc", "güç"}:
                    # Imported tablodan "güç" satırını tablo halinde getir
                    row_md = self._spec_row_markdown_from_imported(model, "güç")  # veya "guc"
                    if row_md:
                        # Birden fazla motor varsa kullanıcıya tüm kolonları göster (yanlış tek değer yerine)
                        title = f"{model.title()} motor gücü (tablodaki tüm versiyonlar)"
                        out = f"<b>{title}</b><br>\n\n{fix_markdown_table(row_md)}\n"
                        yield out.encode("utf-8")
                        return

                # ✅ SQL’de de yoksa: direkt asistan
                txt = self._fallback_via_chat(user_id, user_message, reason=f"KB_ONLY_SPEC_NOT_FOUND:{spec_key}")
                if self._is_weak_answer(user_message, txt):
                    txt = self._fallback_via_chat(user_id, user_message, reason="WEAK_ANSWER_RETRY")

                yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
                return

            best = self._kb_best_hit(user_message, user_id=user_id)
            if best:
                best_score, best_meta = best
                self.logger.info(f"[KB-GATE] best_score={best_score:.3f} threshold={threshold:.3f}")

                if best_score >= threshold:
                    # 1) SQL satırına geri dön (en doğru değer için kritik!)
                    row = None
                    try:
                            # ✅ KB hit’inden model yakalayıp active_model’i kilitle
                        m2 = (best_meta.get("model") or "").strip().lower()
                        if m2 in {"fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"}:
                            self._set_active_model(user_id, m2)

                        row = self._kb_postfetch_row(best_meta.get("table"), str(best_meta.get("row_key")))
                    except Exception:
                        row = None

                    # 2) EQUIP ise deterministik cümle (LLM'siz) da kullanabilirsin
                    if row:
                        facts = self._facts_from_kb_row(
                            group=best_meta.get("group", "OTHER"),
                            table_name=best_meta.get("table"),
                            row=row,
                            user_message=user_message
                        )

                        # EQUIP için istersen direkt deterministik:
                        if facts.get("kind") == "EQUIP":
                            try:
                                # trims + status_map formatına çevir
                                trims = [x["trim_col"] for x in facts.get("status", [])]
                                status_map = {x["trim_col"]: x["status"] for x in facts.get("status", [])}
                                sent = self._nlg_equipment_status(
                                    model_name=(facts.get("model") or "").lower(),
                                    feature=facts.get("title") or "Sorgulanan donanım",
                                    trims=trims,
                                    status_map=status_map
                                )
                                if sent:
                                    yield self._deliver_locally(body=sent, original_user_message=user_message, user_id=user_id)
                                    return
                            except Exception:
                                pass

                        # SPEC / OTHER: LLM ile satış danışmanı cümlesi
                        txt = self._nlg_sales_from_facts(facts, user_message)
                        if txt:
                            yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
                            return

                    # 3) Postfetch olmazsa: son çare KB metnini kullan
                    kb_text = (best_meta.get("text") or "").strip()
                    grp = best_meta.get("group")

                    if kb_text:
                        ok = self._verify_answer_fit(
                            user_message,
                            kb_text,
                            group=grp,
                            score=float(best_score),
                            strict=True
                        )
                        if not ok:
                            txt = "KbVectors tablosunda sorunuza uygun bir kayıt bulunamadı."
                            yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
                            return

                        yield self._deliver_locally(body=kb_text, original_user_message=user_message, user_id=user_id)
                        return


            txt = self._fallback_via_assistant(
                user_id=user_id,
                user_message=user_message,
                reason=f"KB score < {threshold} or no hit"
            )

            if self._should_fallback_to_assistant(txt):
                txt = (
                    "Hemen yardımcı olayım 😊 Elroq ve Enyaq karşılaştırması için "
                    "önceliğiniz menzil mi, performans mı yoksa iç mekân/donanım mı?"
                )

            yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
            return

            # KB yetmediyse fallback asistan
            txt = self._fallback_via_assistant(
                user_id=user_id,
                user_message=user_message,
                reason=f"KB score < {threshold} or no hit"
            )
            yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
            return






        # ✅ 2) DB_ONLY sonra
        if os.getenv("DB_ONLY_ANSWER", "1") == "1":
            text = self._answer_from_db_only(user_message, user_id=user_id)
            yield self._deliver_locally(body=text, original_user_message=user_message, user_id=user_id)
            return

    # ... geri kalan eski akış (KB_ONLY=0 iken) ...

        q = normalize_tr_text(user_message or "").lower()
        lower_msg = (user_message or "").lower()
        price_intent = self._is_price_intent(user_message)
                # 🔹 0) Model hakkında genel bilgi isteği mi?
        gen_info = self._get_model_general_info(user_message)
        if gen_info:
            yield gen_info.encode("utf-8")
            return

            # 💚 MODEL + "opsiyonlar neler" → doğrudan PriceList tablosunu getir
        try:
            q_norm = q  # zaten normalize_tr_text ile hazırlanmış
            has_model = bool(self._extract_models(user_message))

            opsiyon_full_list_intent = (
                has_model
                and "opsiyon" in q_norm
                and any(w in q_norm for w in [
                    "neler", "nelerdir", "tümü", "tumu",
                    "tamami", "tamamı", "hepsi", "liste"
                ])
            )

            if opsiyon_full_list_intent:
                md = self._price_row_from_pricelist(user_message, user_id=user_id)
                self.logger.info(
                    "[PRICE] opsiyon-full-list intent, md=%s",
                    "OK" if md else "None"
                )
                if md:
                    # Burada sadece PriceList çıktısını verip çıkıyoruz
                    yield md.encode("utf-8")
                    return
        except Exception as e:
            self.logger.error(f"[PRICE] opsiyon-full-list short-circuit error: {e}")

        # --- DİREKSİYON / GÖSTERGE / MULTİMEDYA ÖZEL TABLOSU (Opt_Direksiyon_...) ---
        dgm_keywords = ["direksiyon", "gösterge", "gosterge", "multimedya"]
        is_dgm_query = any(kw in lower_msg for kw in dgm_keywords)

        # Fiyat niyeti varsa bu blok ATLANACAK, PriceList çalışacak
        has_price_word = any(p in lower_msg for p in [
            "fiyat", "ne kadar", "kaç para", "kaça", "kaca"
        ])

        if is_dgm_query and not has_price_word:
            models_dgm = list(self._extract_models(user_message))
            if not models_dgm and user_id:
                last_models = (self.user_states.get(user_id, {}) or {}).get("last_models", set())
                if len(last_models) == 1:
                    models_dgm = list(last_models)

            if models_dgm:
                dgm_model = models_dgm[0]
                dgm_md = self._opt_dgm_table_from_sql(dgm_model, user_text=user_message)
                if dgm_md:
                    if "direksiyon" in q:
                        suffix = " direksiyon simidi seçenekleri"
                    elif "gösterge" in q or "gosterge" in q:
                        suffix = " gösterge paneli seçenekleri"
                    elif "multimedya" in q:
                        suffix = " multimedya sistemi seçenekleri"
                    else:
                        suffix = " direksiyon / gösterge paneli / multimedya seçenekleri"

                    title = f"{dgm_model.title()}{suffix}"
                    yield f"<b>{title}</b><br>\n\n".encode("utf-8")
                    yield dgm_md.encode("utf-8")

                    # 🔹 NLG için sayıları temizle ki imza kontrolüne takılmasın
                    try:
                        narrative = self._nlg_via_openai(
                            model_name=dgm_model.title(),
                            metric="Direksiyon / gösterge paneli / multimedya seçenekleri",
                            value="Tablodaki seçenekler",
                            tone=os.getenv("NLG_TONE", "neutral"),
                            length=os.getenv("NLG_LENGTH", "short"),
                        )
                    except Exception as e:
                        self.logger.error(f"[OPT-DGM NLG] hata: {e}")
                        narrative = ""

                    if narrative:
                        # Tablo tamamen bittikten SONRA ayrı bir paragraf olarak ekle
                        html_narrative = f"<br><br><p>{narrative}</p>"
                        yield html_narrative.encode("utf-8")
                    return


            # Model hiç yoksa: kullanıcıdan model iste
            ask = (
                "Direksiyon simidi / gösterge paneli / multimedya ile ilgili bilgi verebilmem için "
                "hangi Skoda modelini sorduğunuzu belirtir misiniz? "
                "(Fabia, Scala, Kamiq, Karoq, Kodiaq, Octavia, Superb, Enyaq, Elroq)"
            )
            yield ask.encode("utf-8")
            return
                # --- JANT ÖZEL TABLOSU (Opt_Jant_KODA_...) ---
        # 'jant görseli / resmi' gibi görsel isteklerini SQL tablo bloklamasın
        image_words = ["görsel", "resim", "foto", "fotograf", "fotoğraf", "görün"]
        is_jant_query = (
            "jant" in lower_msg
            and not has_price_word
            and not any(w in lower_msg for w in image_words)
        )

        if is_jant_query:
            models_jant = list(self._extract_models(user_message))
            if not models_jant and user_id:
                last_models = (self.user_states.get(user_id, {}) or {}).get("last_models", set())
                if len(last_models) == 1:
                    models_jant = list(last_models)

            if models_jant:
                j_model = models_jant[0]
                j_md = self._opt_jant_table_from_sql(j_model)
                if j_md:
                    title = f"{j_model.title()} jant seçenekleri"
                    # Başlık + tablo
                    yield f"<b>{title}</b><br>\n\n".encode("utf-8")
                    yield j_md.encode("utf-8")

                    # Açıklama TABLONUN ALTINDA gelsin
                    try:
                        narrative = self._nlg_via_openai(
                            model_name=j_model.title(),
                            metric="Jant seçenekleri",
                            value="Tablodaki jant seçenekleri",
                            tone=os.getenv("NLG_TONE", "neutral"),
                            length=os.getenv("NLG_LENGTH", "short"),
                        )
                    except Exception as e:
                        self.logger.error(f"[OPT-JANT NLG] hata: {e}")
                        narrative = ""

                    if narrative:
                        html_narrative = f"<br><br><p>{narrative}</p>"
                        yield html_narrative.encode("utf-8")
                    return

            # Model hiç yoksa: kullanıcıdan model iste
            ask_jant = (
                "Jant seçeneklerini paylaşabilmem için hangi Skoda modelini sorduğunuzu "
                "belirtir misiniz? (Fabia, Scala, Kamiq, Karoq, Kodiaq, Octavia, Superb, Enyaq, Elroq)"
            )
            yield ask_jant.encode("utf-8")
            return



                # --- 0) Özel opsiyon / paket için PriceList satırı dene ---
        # Not: Bu blok _is_price_intent'e bağlı değil; skor düşükse fonksiyon None döner.
                # --- 0) Özel opsiyon / paket için PriceList satırı dene ---
        # Sadece gerçekten FİYAT niyeti varsa çalışsın
         


                # Donanım / özellik / var mı / opsiyonel niyetini erken tespit et
        # Donanım sorusu mu? (genişletilmiş)
        equip_words = [
            "donanım", "donanim",
            "standart", "opsiyonel",
            "özellik", "ozellik",
            "paket",
            # doğrudan donanım isimleri
            "cam tavan", "sunroof",
            "koltuk",
            "far", "jant",
            "gösterge", "gosterge",
            "direksiyon",
        ]
        # 1) basit keyword niyeti
        equip_intent = any(w in lower_msg for w in equip_words)
        if not equip_intent:
            try:
                equip_intent = self._is_equipment_query_by_evidence(user_id, user_message)
            except Exception:
                pass

        # 2) keyword kaçırırsa: '... var mı' + SQL tablosu probesi
        if not equip_intent:
            equip_intent = self._probe_equipment_presence(user_id, user_message)
        if not equip_intent and self._is_equipment_presence_question(user_message):
            equip_intent = True
        # Özellikle: "hangi versiyonlarda var / hangi donanımda var" tipi soruları da
        # donanım intentine çek (cam tavan, koltuk, far vb. ile birlikteyse)
        if not equip_intent:
            if any(kw in lower_msg for kw in [
                "hangi versiyonlarda", "hangi versiyonda",
                "hangi donanımda", "hangi donanimda",
            ]):
                feature_tokens = [
                    "cam tavan", "sunroof",
                    "koltuk",
                    "far", "jant",
                    "gösterge", "gosterge",
                    "direksiyon",
                ]
                if any(ft in lower_msg for ft in feature_tokens):
                    equip_intent = True

        # Teknik / performans metriklerini tespit et (0-100, tork, güç, menzil, vs.)
        requested_specs = self._find_requested_specs(user_message) if hasattr(self, "_find_requested_specs") else []
        has_teknik_trigger = any(
            kw in lower_msg
            for kw in getattr(self, "TEKNIK_TRIGGERS", [])
        )
        is_spec_intent = bool(requested_specs or has_teknik_trigger)
                # Sadece TEK METRİK sorular için (torku, gücü, menzili, 0-100 vs.)
        metric_keywords = [
            "tork", "güç", "guc", "beygir", "hp", "ps", "kw",
            "0-100", "0 – 100", "0 100", "ivme", "hızlanma",
            "maksimum hız", "maks hiz", "maks hız", "max speed", "top speed",
            "menzil", "range",
            "tüketim", "tuketim", "l/100", "lt/100",
            "co2", "emisyon",
            "bagaj", "hacmi", "dm3",
            "ağırlık", "agirlik", "kapı", "kapi", "lastik"
        ]
        has_explicit_metric = bool(requested_specs) or any(k in lower_msg for k in metric_keywords)

        trims_in_msg = extract_trims(lower_msg)
        self.CURRENT_TRIM_HINT = next(iter(trims_in_msg), None)

         

            # ❌ rows boşsa burada HİÇBİR ŞEY deme, aşağıdaki EquipmentList mantığına
            # düşsün (_feature_lookup_any model+özellikten S / O / — çıkaracak)

        # --- Buradan sonrası mevcut akışın devamı ---
        # Donanım tarzı sorular (var mı / donanım / özellik / opsiyonel vs.)
        equip_like_early = any(w in lower_msg for w in [
            "donanım", "donanim", "özellik", "ozellik",
            "var mı", "varmi", "bulunuyor mu", "opsiyonel"
        ])

        # --- TEKNİK / SAYISAL METRİK SORULARI İÇİN SQL BLOĞU ---
        # (donanım sorularını bu bloktan çıkarıyoruz)
        # --- TEKNİK / SAYISAL METRİK SORULARI İÇİN SQL BLOĞU ---
# (donanım sorularını bu bloktan çıkarıyoruz)
        if has_explicit_metric and not equip_like_early:
            models_in_msg = list(self._extract_models(user_message))
            picked_model = models_in_msg[0] if models_in_msg else None

            if picked_model:
                val, canon_key, row_md = self._generic_spec_from_sql(
                    picked_model,
                    q,
                    return_meta=True
                )

                if val:
                    SPEC_TITLE = {
                        "tork": "Tork",
                        "güç": "Güç", "guc": "Güç",
                        "0-100": "0-100",
                        "max_hiz": "Maksimum hız", "maksimum hız": "Maksimum hız",
                        "menzil": "Menzil (WLTP)",
                        "tuketim": "Birleşik tüketim", "yakıt tüketimi": "Birleşik tüketim",
                        "co2": "CO₂",
                        "agirlik": "Ağırlık",
                        "batarya": "Batarya kapasitesi",
                        "sarj": "Şarj",
                    }
                    title = SPEC_TITLE.get(canon_key, canon_key or "Değer")

                    yield self._emit_spec_sentence(picked_model, title, val)
                    return


            else:
                # model yazılmadıysa eski fallback (sadece metin) aynen kalsın
                last_models_ctx = list(self.user_states.get(user_id, {}).get("last_models", []))
                probe_models = last_models_ctx or [
                    "fabia","scala","kamiq","karoq","kodiaq",
                    "octavia","superb","enyaq","elroq"
                ]
                for m in probe_models:
                    val = self._generic_spec_from_sql(m, q)
                    if val:
                        yield self._emit_spec_sentence(m, "Değer", val)
                        self.user_states.setdefault(user_id, {}).setdefault("last_models", set()).add(m)
                        return

        # --- TEKNİK BLOK SONU ---


            # Model yazıldı ama değer bulunamadıysa diğer modellere bakma
       
        

        q = normalize_tr_text(user_message or "").lower()
        models_in_msg0 = list(self._extract_models(user_message))
        model = models_in_msg0[0] if models_in_msg0 else None

        
            # 3) Genel metrik yakalama (tork/güç/0-100/co2/menzil vb.)
        # 3) Genel metrik yakalama (tork, güç, 0-100, menzil vs.)
        val = None

        # SADECE teknik/metrik soruysa SQL-SPEC çalışsın
        if is_spec_intent:
            if model:
                val = self._generic_spec_from_sql(model, q)
                picked_model = model
            else:
                picked_model = None
                for m in ["fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"]:
                    val = self._generic_spec_from_sql(m, q)
                    if val:
                        picked_model = m
                        break

        if val:
            # Sorudan kısa bir başlık çıkaralım
            title = "Değer"
            if "tork" in q:                         title = "Tork"
            elif any(k in q for k in ["güç","guc","beygir","hp","ps","power","kw"]):
                title = "Güç"
            elif re.search(r"\b0\s*[-–—]?\s*100\b", q):
                title = "0-100"
            elif any(k in q for k in ["maks","max speed","top speed","hız","hiz"]):
                title = "Maksimum hız"
            elif "co2" in q or "emisyon" in q:      title = "CO₂"
            elif any(k in q for k in ["tüketim","tuketim","l/100","lt/100"]):
                title = "Birleşik tüketim"
            elif "menzil" in q or "range" in q:     title = "Menzil (WLTP)"

            yield self._emit_spec_sentence(picked_model, title, val)
            return



         
        corrected_message = user_message
        if self._mentions_non_skoda(user_message):
            # Tam olarak istenen cümle (ek link/ekstra metin yok)
            yield "Üzgünüm sadece Skoda hakkında bilgi verebilirim".encode("utf-8")
            return
# ===================================================================

        
        self.logger.info(f"[_generate_response] Kullanıcı ({user_id}): {user_message}")
                # --- AYNI MODELDE BİRDEN FAZLA TRIM KARŞILAŞTIRMASI (SQL) ---
        # _generate_response içinde, _detect_same_model_trim_compare() çağrısından ÖNCE:
        m, a, b = self._detect_same_model_trim_diff(corrected_message)
        if m and a and b:
            # ✅ bu kıyası hatırla
            st = self.user_states.setdefault(user_id, {})
            st["last_trim_diff"] = {"model": m, "a": a, "b": b}

            txt = self._answer_trim_diff_from_sql(m, a, b, detailed=False)
            yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
            return

        cmp_model, cmp_trims = self._detect_same_model_trim_compare(corrected_message)
        self.logger.info(f"[TRIM-CMP] model={cmp_model}, trims={cmp_trims}, msg={corrected_message!r}")

        if cmp_model and cmp_trims and len(cmp_trims) >= 2:
            # Model başına trim listesi
            trims_per_model = {cmp_model: cmp_trims}

            md = self._build_equipment_comparison_table_from_sql(
                models=[cmp_model],
                only_keywords=None,
                trim=None,
                trims_per_model=trims_per_model,
            )

            if md:
                try:
                    md = fix_markdown_table(md)
                except Exception:
                    pass

                title = (
                    f"{cmp_model.title()} "
                    f"{' ve '.join(t.title() for t in cmp_trims)} donanım farkları"
                )
                html = f"<b>{title}</b><br>\n\n{md}\n"
                yield html.encode("utf-8")
                return
            else:
                msg = (
                    f"{cmp_model.title()} için "
                    f"{', '.join(t.title() for t in cmp_trims)} donanımları arasında "
                    "SQL donanım tablosunda satır bulunamadı. "
                    "Bu yüzden otomatik fark tablosu üretemiyorum."
                )
                yield msg.encode("utf-8")
                return
                    # --- FARKLI MODELLER + TRIMLER ARASI DONANIM KARŞILAŞTIRMASI (SQL) ---
        multi_cmp = self._detect_multi_model_trim_compare(corrected_message)
        self.logger.info(f"[MULTI-TRIM-CMP] map={multi_cmp}, msg={corrected_message!r}")

        if multi_cmp:
            models = list(multi_cmp.keys())

            md = self._build_equipment_comparison_table_from_sql(
                models=models,
                only_keywords=None,
                trim=None,
                trims_per_model=multi_cmp,
            )

            if md:
                try:
                    md = fix_markdown_table(md)
                except Exception:
                    pass

                # Başlık: "Fabia Premium vs Scala Premium ve Kamiq Monte Carlo donanım farkları" gibi
                title_parts = []
                for m in models:
                    trims = multi_cmp.get(m, []) or []
                    if trims:
                        trims_txt = ", ".join(t.title() for t in trims)
                        title_parts.append(f"{m.title()} {trims_txt}")
                    else:
                        title_parts.append(m.title())

                title = " vs ".join(title_parts) + " donanım farkları"
                html = f"<b>{title}</b><br>\n\n{md}\n"
                yield html.encode("utf-8")
                return
            else:
                msg = (
                    "SQL donanım tablolarında bu model/trim kombinasyonu için satır "
                    "bulunamadığı için otomatik karşılaştırma tablosu oluşturamıyorum."
                )
                yield msg.encode("utf-8")
                return


    # <<< YENİ: Bu turda RAG cevabı üst blokta gösterildi mi?
        self.user_states.setdefault(user_id, {})["rag_head_delivered"] = False
        if self._is_test_drive_intent(user_message):
            yield self._contact_link_html(
                user_id=user_id,
                model_hint=self._resolve_display_model(user_id)
            ).encode("utf-8")
            # İsterseniz yanında hızlı örnek talepleri de gösterelim:
            return
        if "current_trim" not in self.user_states[user_id]:
            self.user_states[user_id]["current_trim"] = ""

        lower_msg = user_message.lower()
                # ... _generate_response içinde, lower_msg hesaplandıktan SONRA bir yerde:

        # --- AYNI MODELDE FARKLI TRIM DONANIM KARŞILAŞTIRMASI (SQL) ---
        cmp_model, cmp_trims = self._detect_same_model_trim_compare(corrected_message)

        if cmp_model and cmp_trims:
            trims_per_model = {cmp_model: cmp_trims}

            md = self._build_equipment_comparison_table_from_sql(
                models=[cmp_model],
                only_keywords=None,
                trim=None,
                trims_per_model=trims_per_model,
            )

            if md:
                try:
                    md = fix_markdown_table(md)
                except Exception:
                    pass

                title = (
                    f"{cmp_model.title()} "
                    f"{' ve '.join(t.title() for t in cmp_trims)} donanım farkları"
                )

                html = f"<b>{title}</b><br>\n\n{md}\n"
                yield html.encode("utf-8")
                return
            else:
                # Tablo bulunamadıysa da RAG'e düşmeyelim, net bir mesaj verelim
                msg = (
                    f"{cmp_model.title()} için {', '.join(t.title() for t in cmp_trims)} "
                    "donanımları arasında SQL donanım tablosunda satır bulunamadı. "
                    "Bu nedenle bu iki donanım için otomatik fark tablosu üretemiyorum."
                )
                yield msg.encode("utf-8")
                return

         # --- YENİ: Donanım listesi / öne çıkanlar / trim farkı soruları → direkt Hybrid RAG ---
        if (
            self.HYBRID_RAG                      # SQL tabanlı KbVectors aktif
            and not price_intent                 # fiyat sorusu değil
            and not self._is_image_intent_local(user_message)  # görsel isteği değil
            and self._is_kb_rag_description_intent(user_message)
        ):
            try:
                rag_text = (self._answer_with_hybrid_rag(user_message, relax_filters=True) or "").strip()
            except Exception as e:
                self.logger.error(f"[RAG-DESC] hata: {e}")
                rag_text = ""

            if rag_text:
                # Mevcut teslim pipeline'ını kullanalım (markdown + tablo fix vs.)
                out = self._deliver_locally(
                    body=rag_text,
                    original_user_message=user_message,
                    user_id=user_id,
                )
                yield out
                return
            # RAG hiçbir şey bulamazsa normal akışa devam etsin
        # -- Erken: kıyas niyetini hemen hesapla (ilk kullanım bundan sonra!)
        compare_keywords = ["karşılaştır", "karşılaştırma", "kıyas", "kıyasla", "kıyaslama", "vs", "vs."]
        wants_compare = any(ck in lower_msg for ck in compare_keywords)

        is_image_req_early = (
        self.utils.is_image_request(lower_msg) or
        self._is_image_intent_local(lower_msg) or
        ("renk" in lower_msg)  # renk(ler) isteklerini de görsel sayalım
        )
                # ----------------------------------------------
        #  MODEL + "donanımlar"  →  DB donanım tablosu
        #  Örn: "karoq donanımlar"
        # ----------------------------------------------
        simple_eq_match = re.search(
            r"\b(fabia|scala|kamiq|karoq|kodiaq|octavia|superb|enyaq|elroq)\s+donan[ıi]mlar?\b",
            lower_msg
        )

        if simple_eq_match and not price_intent and not is_image_req_early:
            simple_model = simple_eq_match.group(1).lower()

            # Tek model için tüm trimleri içeren donanım karşılaştırma tablosu
            try:
                md = self._build_equipment_comparison_table_from_sql(
                    models=[simple_model],
                    only_keywords=None,
                    trim=None,
                    trims_per_model=None
                )
            except Exception as e:
                self.logger.error(f"[EQUIP-TBL SIMPLE] hata: {e}")
                md = ""

            if md:
                try:
                    md = fix_markdown_table(md)
                except Exception:
                    pass

                title = f"{simple_model.title()} donanımlar"
                html = f"<b>{title}</b><br>\n\n{md}\n"
                yield html.encode("utf-8")
                return
            # md boş ise, normal akış (eski donanım/Hybrid RAG mantığı) devam etsin

        # Yeni mesaj "opsiyonel" demiyorsa opsiyonel bekleme modunu temizle
        if "opsiyonel" not in lower_msg:
            self.user_states.setdefault(user_id, {})["pending_opsiyonel_model"] = None

        price_intent = self._is_price_intent(user_message)
        opt_list_intent = False
        if "opsiyon" in lower_msg and not price_intent:
            has_model = bool(self._extract_models(user_message))
            has_list_word = any(
                w in lower_msg
                for w in ["neler", "nelerdir", "tümü", "tumu", "tamami", "tamamı", "hepsi", "liste"]
            )
            if has_model and has_list_word:
                opt_list_intent = True

        if opt_list_intent:
            # Burada _price_row_from_pricelist içindeki "asks_full_list" branch'ı devreye girip
            # PriceList_KODA_<MODEL> tablosunun TAMAMINI tablo olarak döndürecek.
            md = self._price_row_from_pricelist(user_message, user_id=user_id)
            self.logger.info(f"[PRICE] opt_list_intent=True, md is {'OK' if md else 'None'}")
            if md:
                yield md.encode("utf-8")
                return
        # -- Erken niyet tespiti --
        user_trims_in_msg = extract_trims(lower_msg)
                # 💡 Fiyat kelimesi geçmeden "opsiyonlar neler" tipi sorular → PriceList
        opt_list_intent = False
        if "opsiyon" in lower_msg and not price_intent:
            has_model = bool(self._extract_models(user_message))
            has_list_word = any(
                w in lower_msg
                for w in ["neler", "nelerdir", "tümü", "tumu", "tamami", "tamamı", "hepsi", "liste"]
            )
            if has_model and has_list_word:
                opt_list_intent = True

        if opt_list_intent:
            md = self._price_row_from_pricelist(user_message, user_id=user_id)
            if md:
                yield md.encode("utf-8")
                return
            # trim yakalayıcı (premium, prestige, rs, e sportline 60 vb.)
        pairs_all = extract_model_trim_pairs(lower_msg)         # (model, trim) çiftleri
        pairs_with_trim = [(m, (t or "").strip()) for (m, t) in pairs_all if (t or "").strip()]

        # 🔴 Model+trim kıyası -> RAG öncelikli

        teknik_keywords = [
            "teknik özellik", "teknik veriler", "teknik veri", "motor özellik", "motor donanım", "motor teknik", "teknik tablo", "teknik", "performans"
        ]
                # ✅ Karşılaştırma sinyali (erken hesaplayalım)
        compare_keywords = ["karşılaştır", "karşılaştırma", "kıyas", "kıyasla", "kıyaslama", "vs", "vs."]
        wants_compare = any(ck in lower_msg for ck in compare_keywords)
        models_in_msg2 = list(self._extract_models(user_message))
                # --- [YENİ] Trim + Model birlikteyse tablo göstermeden RAG cevabı getir ---
        models_in_msg = list(self._extract_models(user_message))
        trims_in_msg = extract_trims(user_message)

        has_model_and_trim = bool(models_in_msg and trims_in_msg)
        has_teknik_compare = any(k in lower_msg for k in [
            "karşılaştır", "kıyas", "vs", "vs.", "teknik karşılaştırma"
        ])

        # Gösterge / direksiyon / multimedya / donanım / fiyat / renk gibi
        # özel konularda RAG ONLY'e gitmek istemiyoruz; önce kendi
        # SQL tablolarımız (_opt_dgm_table_from_sql, EquipmentList, Imported vs.)
        # devreye girsin.
        rag_blocker_kw = [
            "direksiyon", "gösterge", "gosterge", "multimedya",
            "donanım", "donanim", "opsiyonel", "standart",
            "renk", "görsel", "resim", "foto",
            "fiyat", "anahtar teslim",
        ]
        block_rag_for_this = any(k in lower_msg for k in rag_blocker_kw)

        # Eğer model + trim birlikteyse, teknik kıyaslama YOKSA ve yukarıdaki
        # özel anahtar kelimeler de YOKSA → baştan RAG-only cevabı dene.
        # (Örnek: "Fabia Premium günlük kullanım yorumu" gibi showroom türü sorular.)
        if (
            has_model_and_trim
            and not has_teknik_compare
            and not block_rag_for_this
            and self.USE_OPENAI_FILE_SEARCH          # <-- eklendi
            and getattr(self, "VECTOR_STORE_ID", "") # <-- eklendi
        ):
            assistant_id = self.user_states[user_id].get("assistant_id")
            if assistant_id:
                rag_bytes = self._answer_via_rag_only(
                    user_id=user_id,
                    assistant_id=assistant_id,
                    user_message=user_message
                )
                if rag_bytes:        # RAG gerçekten cevap ürettiyse kullan
                    yield rag_bytes
                    return


        if price_intent:
            # Önce PriceList_KODA_* içinde opsiyon/paket satırını yakalamaya çalış
            price_md = self._price_row_from_pricelist(user_message, user_id=user_id)
            if price_md:
                yield price_md.encode("utf-8")
                return

            # Opsiyon/paket bulunamazsa eski davranış: genel fiyat listesi (FIYAT_LISTESI_MD)
            yield from self._yield_fiyat_listesi(user_message, user_id=user_id)
            return

        if any(kw in lower_msg for kw in ["teknik özellik", "teknik veriler", "teknik tablo", "teknik"]) \
            or wants_compare:
            # Çoklu model veya açık "karşılaştır" → aşağıdaki karşılaştırma bloğuna bırak
            if wants_compare or len(models_in_msg2) >= 2:
                pass
            else:
                # ---- TEK MODEL: SQL'den DONANIM + TEKNİK TABLO ----
                pairs_for_order = extract_model_trim_pairs(lower_msg)
                found_model = None
                if pairs_for_order:
                    found_model = pairs_for_order[0][0]  # cümlede ilk geçen model
                elif len(models_in_msg2) == 1:
                    found_model = models_in_msg2[0]
                elif assistant_id:
                    found_model = self.ASSISTANT_NAME_MAP.get(assistant_id, "").lower()

                # Son çare: last_models tekse onu kullan
                if (not found_model) and self.user_states.get(user_id, {}).get("last_models"):
                    lm = list(self.user_states[user_id]["last_models"])
                    if len(lm) == 1:
                        found_model = lm[0]

                if found_model:
                    model_slug = found_model.lower()
                    model_title = model_slug.title()

                    # Kullanıcının yazdığı trim(ler)i bul (örn. "karoq premium teknik özellikler")
                    all_trims_for_model = list(self.MODEL_VALID_TRIMS.get(model_slug, []))
                    trims_in_msg_list = list(extract_trims(lower_msg))
                    chosen_trim: str | None = None
                    trims_per_model_single: dict[str, list[str]] | None = None

                    if trims_in_msg_list:
                        valid_trims = [t for t in trims_in_msg_list if t in all_trims_for_model]
                        if len(valid_trims) == 1:
                            chosen_trim = valid_trims[0]               # sadece Premium gibi tek trim
                        elif len(valid_trims) > 1:
                            trims_per_model_single = {model_slug: valid_trims}

                    # --- DONANIM TABLOSU (EquipmentList_KODA_...) ---
                    eq_md = self._build_equipment_comparison_table_from_sql(
                        models=[model_slug],
                        only_keywords=None,
                        trim=chosen_trim,
                        trims_per_model=trims_per_model_single
                    )

                    # --- TEKNİK TABLO (Imported_KODA_...) ---
                    spec_md = self._build_spec_comparison_table_from_sql(
                        models=[model_slug],
                        trim=chosen_trim,
                        trims_per_model=trims_per_model_single
                    )

                    rendered_any = False

                    if eq_md:
                        eq_md = fix_markdown_table(eq_md)
                        yield f"<b>{model_title} Donanım Özeti (SQL)</b><br>".encode("utf-8")
                        yield (eq_md + "\n\n").encode("utf-8")
                        rendered_any = True

                    if spec_md:
                        spec_md = fix_markdown_table(spec_md)
                        yield f"<b>{model_title} Teknik Özellikler (SQL)</b><br>".encode("utf-8")
                        yield (spec_md + "\n\n").encode("utf-8")
                        rendered_any = True

                    # Eğer SQL'den hiçbir şey üretemediysek eski MD fallback'ine düş
                     
                    if rendered_any:
                        return
        
                # --- FIYAT L\u0130STES\u0130 ---
         
        # --- STANDART DONANIM erken dönüş (opsiyonelden ÖNCE çalışmalı) ---
        std_kw = ["standart", "standard", "temel donanım", "donanım listesi", "standart donanımlar", "donanımlar neler"]
        if any(k in lower_msg for k in std_kw):
            models_std = list(self._extract_models(user_message))
            if not models_std:
                # Asistan bağlamından veya last_models'tan düş
                asst_id = (self.user_states.get(user_id, {}) or {}).get("assistant_id")
                ctx_model = (self.ASSISTANT_NAME_MAP.get(asst_id, "") if asst_id else "")
                if ctx_model:
                    models_std = [ctx_model.lower()]
                elif (self.user_states.get(user_id, {}) or {}).get("last_models"):
                    lm = list(self.user_states[user_id]["last_models"])
                    if len(lm) == 1:
                        models_std = [lm[0]]

            if models_std:
                m = models_std[0].lower()
                md = (self.STANDART_DONANIM_TABLES.get(m) or "").strip()
                if md:
                    picked = self.select_table(md, "standard") or md  # alt tablo
                    yield f"<b>{m.title()} Standart Donanımlar</b><br>".encode("utf-8")
                    yield fix_markdown_table(picked).encode("utf-8") if picked.lstrip().startswith("|") else picked.encode("utf-8")
                    return
                else:
                    yield f"{m.title()} için standart donanım tablosu tanımlı değil.<br>".encode("utf-8")
                    return
        # --- STANDART DONANIM sonu ---

        # _generate_response içinde, price/test-drive kontrollerinden SONRA
        # ve teknik/karşılaştırma bloklarına GİRMEDEN hemen önce:
        models_for_cmp = list(self._extract_models(user_message))
        requested_specs = self._find_requested_specs(user_message)
        # YENİ: Mesaj model içermiyorsa cmp_models'ı kullan
        if (not models_for_cmp):
            cm = (self.user_states.get(user_id, {}) or {}).get("cmp_models", [])
            if len(cm) >= 2:
                models_for_cmp = list(cm[:2])

        if requested_specs and len(models_for_cmp) >= 2:
            if len(requested_specs) == 1:
                ans = self._answer_two_model_spec_diff(models_for_cmp, requested_specs[0])
                if ans:
                    yield ans.encode("utf-8"); return
        # Eğer metinde model yok ama oturumda son konuşulan birden fazla model varsa, onu kullan
        if (not models_for_cmp) and self.user_states.get(user_id, {}).get("last_models"):
            lm = list(self.user_states[user_id]["last_models"])
            if len(lm) >= 2:
                models_for_cmp = lm

        if requested_specs and len(models_for_cmp) >= 2:
            if len(requested_specs) == 1:
                ans = self._answer_two_model_spec_diff(models_for_cmp, requested_specs[0])
                if ans:
                    yield ans.encode("utf-8"); return
            # birden fazla metrik istendiyse tablolu kıyas yolu çalışsın

        # >>> bundan SONRA tek-model QA’yı dene
        qa_bytes = self._answer_teknik_as_qa(user_message, user_id)
        if qa_bytes:
            qa_text = qa_bytes.decode("utf-8", errors="ignore").strip()
            gated = self._gate_to_table_or_image(qa_text)
            if gated:
                yield gated
            else:
                # Tablo değilse düz metin olarak ilet
                yield self._deliver_locally(qa_text, original_user_message=user_message, user_id=user_id)
            return
        # *** TEKNİK FARK SORUSU (iki model + tek metrik) ***
        models_for_cmp = list(self._extract_models(user_message))
        requested_specs = self._find_requested_specs(user_message)

        if requested_specs and len(models_for_cmp) >= 2:
            # tek metrik ise (örn. 'hız', '0-100', 'beygir', 'tork' ...)
            if len(requested_specs) == 1:
                ans = self._answer_two_model_spec_diff(models_for_cmp, requested_specs[0])
                if ans:
                    yield ans.encode("utf-8")
                    return
            # birden çok metrik istendiyse eski teknik karşılaştırma tablosuna düş
        # === FULL Imported_* kapsama: kullanıcı özellik/var mı niyeti → tüm tablo içinden ara ===
         

            compact = self._render_feature_hits_compact(rows)
            if "|" in compact and "\n" in compact:
                compact = fix_markdown_table(compact)
            yield compact.encode("utf-8")
            return


        if equip_intent and not wants_compare:
            # 1) Hangi model?  (mesaj + last_models + asistan bağlamı)
            model = self._current_model(user_id, user_message)
            if not model:
                # Hiçbir şekilde model çıkarılamadıysa kullanıcıdan sor
                yield ("Hangi Skoda modelinde bu donanımı merak ediyorsunuz? "
                    "(Fabia, Scala, Kamiq, Karoq, Kodiaq, Octavia, Superb, Enyaq, Elroq)").encode("utf-8")
                return
            # 🔹 DEBUG: Lemma'lı imported aramasını her donanım sorusunda çalıştır
            self._query_all_features_from_imported(model, user_message, topn=1)

            # =========================
            # 1) EQUIPMENTLIST (donanım)
            # =========================
            self._set_active_model(user_id, model)
            trims, status_map, feature_title = self._feature_lookup_any(model, user_message)
            # ✅ ZORUNLU: soru ↔ feature_title uyumlu mu?
            if feature_title:
                if not self._is_safe_equipment_match(user_message, feature_title):
                    # emin değilsek LLM YES/NO da sor (çok kısa)
                    if not self._llm_verify_hit(user_message, feature_title):
                        trims, status_map, feature_title = [], {}, None
            if trims and status_map:
                feat = feature_title or "Sorgulanan donanım"

                sent = self._nlg_equipment_status(
                    model_name=model,
                    feature=feat,
                    trims=trims,
                    status_map=status_map,
                )

                # ✅ SADECE YAZI (TABLO YOK)
                body = (sent or "").strip()
                if not body:
                    body = f"{model.title()} için '{feat}' donanım bilgisini buldum, detay ister misiniz?"

                yield self._deliver_locally(
                    body=body,
                    original_user_message=user_message,
                    user_id=user_id
                )
                return




            # =========================
            # 2) PRICELIST (opsiyon fiyatı)
            # =========================
            if self._is_price_intent(user_message):
                price_md = self._price_row_from_pricelist(user_message, user_id=user_id)
                if price_md:
                    yield price_md.encode("utf-8")
                    return

            # =========================
            # 3) IMPORTED (KAPALI – sadece teknik sorularda kullanılacak)
            # =========================
            # Donanım sorularında Imported_KODA_* + HF-SEM kullanmak istemiyoruz.
            # Bu yüzden burada _query_all_features_from_imported çağrısını kaldırdık.
            # rows = self._query_all_features_from_imported(model, user_message, topn=1)
            rows = []  # donanım mode'unda Imported fallback YOK

            # 🔴 4) HİÇBİR SQL KAYDI YOK → HYBRID RAG'E GİTME
            # 🔴 4) SQL sonucu yoksa -> 2. kez ise kısa sabit mesaj
            if not trims and not status_map:
                st = self.user_states.setdefault(user_id, {})

                # feature key üret (model adı + sorgu normalize)
                feat_key, _ = canonicalize_feature(user_message)  # sende zaten var
                if not feat_key:
                    feat_key = normalize_tr_text(user_message).lower()

                miss_key = f"{model.lower()}::{feat_key}"
                miss_map = st.setdefault("db_miss_counts", {})
                miss_map[miss_key] = miss_map.get(miss_key, 0) + 1

                if miss_map[miss_key] >= 2:
                    yield "Bu modelde istediğiniz özellik bulunmamaktadır.".encode("utf-8")
                else:
                    txt = self._fallback_via_chat(user_id, user_message, reason="EquipmentList/Imported match yok")
                    yield self._deliver_locally(body=txt, original_user_message=user_message, user_id=user_id)
                    return

                return






        
        # Teknik anahtar kelimesi var mı?
        requested_specs = self._find_requested_specs(user_message)  # ← 'hız', '0-100', 'beygir', 'tork' vb. yakalanır
        has_teknik_word = bool(requested_specs) or any(kw in lower_msg for kw in [
            "teknik özellik", "teknik veriler", "teknik veri", "motor özellik",
            "motor donanım", "motor teknik", "teknik tablo", "teknik", "performans",
            "0-100", "0 – 100", "0 100", "ivme", "hız", "maksimum hız", "maks hız",
            "beygir", "hp", "ps", "tork", "kw"
        ])

        models_for_cmp = list(self._extract_models(user_message))
        equip_words = ["donanım","donanim","standart","opsiyonel","özellik","ozellik","paket"]
        equip_intent = any(w in lower_msg for w in equip_words)
        # 🔑 Kural:
        #  - Eğer kullanıcı "karşılaştır/kıyas" dedi VEYA 2+ model yazdıysa
        #  - VE cümlede teknik anahtar kelimesi YOKSA
        #  -> Önce DONANIM kıyasını DB’den dene (donanım kelimesi geçmesi gerekmiyor)
        if ((wants_compare or len(models_for_cmp) >= 2)
            and not has_teknik_word
            and not requested_specs
            and not is_image_req_early):

            pairs_for_order = extract_model_trim_pairs(lower_msg)
            ordered_models = [m for m, _ in pairs_for_order]
            if not ordered_models:
                ordered_models = list(self._extract_models(user_message))
            if len(ordered_models) > 2:
                ordered_models = ordered_models[:2]

            if len(ordered_models) >= 2:
                only = self._detect_equipment_filter_keywords(lower_msg)
                trim_in_msg = next(iter(extract_trims(lower_msg)), None)

                # 🔹 Model başına trim haritası: {'scala':['premium'], 'kamiq':['monte carlo']}
                trims_per_model: dict[str, list[str]] = {}
                for m, seg in pairs_for_order:
                    if m not in ordered_models:
                        continue
                    seg_trims = list(extract_trims(seg))
                    if not seg_trims:
                        continue

                    valid_trims = []
                    for t in seg_trims:
                        if t in (self.MODEL_VALID_TRIMS.get(m, []) or []):
                            valid_trims.append(t)

                    if valid_trims:
                        trims_per_model[m] = valid_trims

                import inspect

                # 0) Bu karşılaştırmada hangi trimler kullanılacak?
                #    - Eğer kullanıcı model başına özel trim yazdıysa (Scala Premium, Kamiq Monte Carlo),
                #      trims_per_model içini kullan.
                #    - Hiç trim yazmadıysa, her model için tüm trimleri (MODEL_VALID_TRIMS) kullan.
                effective_trims_per_model = trims_per_model or {
                    m: list(self.MODEL_VALID_TRIMS.get(m, []))
                    for m in ordered_models
                }

                # 1) Donanım karşılaştırma tablosu
                sig_eq = inspect.signature(self._build_equipment_comparison_table_from_sql).parameters
                params_eq = dict(models=ordered_models, only_keywords=(only or None))

                if "trims_per_model" in sig_eq:
                    params_eq["trims_per_model"] = effective_trims_per_model
                elif "trim" in sig_eq:
                    params_eq["trim"] = trim_in_msg

                md = self._build_equipment_comparison_table_from_sql(**params_eq)
                if not md:
                    return

                title = " vs ".join(m.title() for m in ordered_models)
                md = md.strip()

                # 2) Aynı trim bilgisini teknik tabloya da geçir
                sig_spec = inspect.signature(self._build_spec_comparison_table_from_sql).parameters
                params_spec = dict(models=ordered_models)

                if "trims_per_model" in sig_spec:
                    params_spec["trims_per_model"] = effective_trims_per_model
                elif "trim" in sig_spec:
                    params_spec["trim"] = trim_in_msg   # ortak trim senaryosu

                spec_tbl = self._build_spec_comparison_table_from_sql(**params_spec)
                spec_tbl = (spec_tbl or "").strip()

                # 3) Showroom açıklaması (donanım + teknik tabloya bakarak)
                try:
                    combined_for_nlg = md
                    if spec_tbl:
                        combined_for_nlg = md + "\n\n" + spec_tbl
                    cmp_text = self._nlg_equipment_compare(ordered_models, combined_for_nlg)
                except Exception:
                    cmp_text = ""

                # 4) "Karşılaştırmaya ekle" linkleri
                links_html = ""
                others = [m for m in self.MODEL_VALID_TRIMS.keys() if m not in ordered_models]
                if others:
                    links_html = "<b>Karşılaştırmaya ekle:</b><br>"
                    for m in others:
                        cmd = (" ".join(ordered_models) + f" ve {m} donanım karşılaştırması").strip()
                        safe_cmd = cmd.replace("'", "\\'")
                        links_html += (
                            f"&bull; <a href=\"#\" onclick=\"sendMessage('{safe_cmd}');return false;\">"
                            f"{m.title()}</a><br>"
                        )

                # 5) HER ŞEYİ TEK BLOKTA BİRLEŞTİR → açıklama kesinlikle tabloların ALTINDA
                full_html = f"<b>{title} — Donanım Karşılaştırması (DB)</b><br>\n\n"
                full_html += md + "\n\n"  # donanım tablosu

                if spec_tbl:
                    full_html += "<br><b>Teknik Veriler Karşılaştırması (SQL)</b><br>\n\n"
                    full_html += spec_tbl + "\n\n"  # teknik tablo

                if cmp_text:
                    full_html += cmp_text + "\n\n"

                if links_html:
                    full_html += links_html

                # Tek seferde gönderiyoruz → front-end bunu bir mesaj olarak işliyor
                yield full_html.encode("utf-8")
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
                if has_teknik_word and (wants_compare or len(ordered_models) >= 2):
                    valid = [m for m in ordered_models if m in self.TECH_SPEC_TABLES]
                    if len(valid) >= 2:
                        # Tablo istenmemişse ve “donanım” kıyası değilse → METİN üret
                        if getattr(self, "TEXT_COMPARE_WHEN_NOT_EQUIPMENT", True) and not re.search(r"\bdonan[ıi]m\b", lower_msg):
                            
                            req = self._find_requested_specs(user_message)

                            # ➊ Kullanıcı tek metrik istediyse (örn. 0-100, güç, tork, uzunluk…)
                            if req and len(req) == 1:
                                ans = self._answer_two_model_spec_diff(valid, req[0])
                                if ans:
                                    yield (ans).encode("utf-8"); return

                            # ➋ Birden fazla veya hiç metrik yakalanmadıysa: çekirdek metriklerden 3’lü kısa kıyas
                            core_metrics = [
                                "Maks. güç (kW/PS @ dev/dak)",
                                "Maks. tork (Nm @ dev/dak)",
                                "0-100 km/h (sn)",
                            ]
                            # İsterseniz uzunluk sorularını da destekleyin:
                            if req and any("Uzunluk/Genişlik/Yükseklik" in r for r in req):
                                core_metrics = ["Uzunluk/Genişlik/Yükseklik (mm)"]

                            lines = []
                            for canon in (req or core_metrics):
                                ans = self._answer_two_model_spec_diff(valid, canon)
                                if ans:
                                    lines.append(ans)
                                if len(lines) >= 3:  # metni kısa tut
                                    break

                            if lines:
                                yield (" ".join(lines)).encode("utf-8"); return

                        # ➌ Fallback: hâlâ çıkaramadıysa eski tablo davranışına dön
                        only = self._detect_spec_filter_keywords(lower_msg)
                        md = self._build_teknik_comparison_table(valid, only_keywords=(only or None))
                        if not md:
                            yield "Karşılaştırma için uygun teknik veri bulunamadı.<br>".encode("utf-8"); return
                        title = " vs ".join([m.title() for m in valid])
                        yield f"<b>{title} — Teknik Özellikler Karşılaştırması</b><br>".encode("utf-8")
                        yield (md + "\n\n").encode("utf-8")
                        # 🔽 TEKNİK TABLO SONRASI EK BLOK 🔽
                        spec_tbl = self._build_spec_comparison_table_from_sql(ordered_models)
                        if spec_tbl:  # boş değilse hep ekle
                            yield ("\n\n" + spec_tbl).encode("utf-8")
                        # 🔼 TEKNİK TABLO SONRASI EK BLOK 🔼

                        return


        # 1) Kategori eşleşmesi
        categories_pattern = r"(dijital gösterge paneli|direksiyon simidi|döşeme|jant|multimedya|renkler)"
        cat_match = re.search(
            fr"(fabia|scala|kamiq|karoq|kodiaq|octavia|enyaq|elroq|superb)\s*(premium|monte carlo|elite|prestige|sportline|e prestige 60|coupe e sportline 60|coupe e sportline 85x|e sportline 60|e sportline 85x|rs)?\s*({categories_pattern})",
             lower_msg
        )
        if cat_match:
            #time.sleep(1)
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
            #time.sleep(1)
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
            #time.sleep(1)
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
        # 6) Opsiyonel tablo istekleri
        user_trims_in_msg = extract_trims(lower_msg)
        pending_ops_model = self.user_states[user_id].get("pending_opsiyonel_model")

        if "opsiyonel" in lower_msg:
            # 1) Modeli çöz (mesaj -> asistan bağlamı -> last_models)
            found_model = None
            models_in_msg2 = list(self._extract_models(user_message))
            if len(models_in_msg2) == 1:
                found_model = models_in_msg2[0]
            elif len(models_in_msg2) > 1:
                found_model = models_in_msg2[0]
            if not found_model:
                asst_id = self.user_states.get(user_id, {}).get("assistant_id")
                found_model = (self.ASSISTANT_NAME_MAP.get(asst_id, "").lower() if asst_id else "") or None
            if (not found_model) and self.user_states.get(user_id, {}).get("last_models"):
                lm = list(self.user_states[user_id]["last_models"])
                if len(lm) == 1:
                    found_model = lm[0]

            if not found_model:
                # model yoksa sadece model iste
                yield "Hangi modelin opsiyonel donanımlarını görmek istersiniz?<br>(Fabia, Scala, Kamiq, Karoq, Kodiaq, Octavia, Superb, Enyaq, Elroq)".encode("utf-8")
                return

            # bağlama yaz
            self.user_states[user_id]["pending_opsiyonel_model"] = found_model

            # 2) Trim var mı?
            if len(user_trims_in_msg) == 1:
                found_trim = list(user_trims_in_msg)[0]
                if found_trim not in self.MODEL_VALID_TRIMS.get(found_model, []):
                    yield from self._yield_invalid_trim_message(found_model, found_trim)
                    return
                # doğrudan tabloyu dök
                yield from self._yield_opsiyonel_table(user_id, user_message, found_model, found_trim)
                return

            # 3) Trim yoksa seçenekleri ver
            model = found_model.lower()
            options = {
                "fabia":   ["premium","monte carlo"],
                "scala":   ["elite","premium","monte carlo"],
                "kamiq":   ["elite","premium","monte carlo"],
                "karoq":   ["premium","prestige","sportline"],
                "kodiaq":  ["premium","prestige","sportline","rs"],
                "octavia": ["elite","premium","prestige","sportline","rs"],
                "superb":  ["premium","prestige","l&k crystal","sportline phev"],
                "enyaq":   ["e prestige 60","coupe e sportline 60","coupe e sportline 85x","e sportline 60","e sportline 85x"],
                "elroq":   ["e prestige 60"],
            }
            yield from self._yield_trim_options(model, options.get(model, []))
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
        # === 7.A) GENEL SORU → ÖNCE RAG (Vector Store) İLE YANITLA ===
        generic_info_intent = not (
            price_intent or "opsiyonel" in lower_msg or is_image_req
            or any(kw in lower_msg for kw in ["teknik özellik","teknik veriler","teknik tablo","performans"])
            or wants_compare
        )

        assistant_id = self.user_states[user_id].get("assistant_id")

        # ❗ RAG_ONLY ise AMA gerçekten file_search vector store'u bağlıysa
        # ve asistan id varsa RAG-only çalışsın; aksi durumda bu branch atlanacak.
        if (
            getattr(self, "RAG_ONLY", False)
            and generic_info_intent
            and getattr(self, "USE_OPENAI_FILE_SEARCH", False)
            and getattr(self, "VECTOR_STORE_ID", "")
            and assistant_id
        ):
            yield self._answer_via_rag_only(
                user_id=user_id,
                assistant_id=assistant_id,
                user_message=user_message
            )
            return


        # --- SQL-ONLY muhafaza: hiçbir SQL cevabı bulunamadıysa net mesaj ver ---
        if getattr(self, "STRICT_SQL_ONLY", False):
            try:
                asst_id = (self.user_states.get(user_id, {}) or {}).get("assistant_id")
                if (
                    getattr(self, "USE_OPENAI_FILE_SEARCH", False)
                    and getattr(self, "VECTOR_STORE_ID", "")
                    and asst_id
                ):
                    rag_bytes = self._answer_via_rag_only(
                        user_id=user_id,
                        assistant_id=asst_id,
                        user_message=user_message,
                    )
                    yield rag_bytes
                    return
            except Exception as e:
                self.logger.error(f"[STRICT_SQL_ONLY] RAG fallback failed: {e}")

            # Vektör store da devreye giremediyse son çare eski mesajı ver
            yield b"DB: kayit bulunamadi."
            return

        # === 7.A) GENEL SORU → ÖNCE RAG (Vector Store) İLE YANITLA ===
        # === 7.A) GENEL SORU → ÖNCE RAG (Vector Store) İLE YANITLA ===
        # Yeni:
        if self.USE_OPENAI_FILE_SEARCH and assistant_id and generic_info_intent and self.PREFER_RAG_TEXT:
            rag_out = self.assistant_runner.ask(
                user_states=self.user_states,
                user_id=user_id,
                assistant_id=assistant_id,
                content=user_message,
                timeout=60.0,
                instructions_override=None,
                tool_resources_override=None,
                ephemeral=False
            ) or ""
            if rag_out.strip():
                out_md = self.markdown_processor.transform_text_to_markdown(rag_out)
                resp_bytes = self._deliver_locally(
                    body=out_md,
                    original_user_message=user_message,
                    user_id=user_id
                )
                yield resp_bytes
                self.user_states[user_id]["rag_head_delivered"] = True
                return
        # self.PREFER_RAG_TEXT false ise bu blok atlanır (RAG metni yüzeye çıkmaz)



        # 7.9) KÖPRÜ: Tablo/Görsel akışları haricinde — birinci servisten yanıt al,

        bridge_answer = ""
        bridge_table_md = ""
        bridge_table_html = ""
        bridge_table_title = ""
        bridge_table_flag = False

        if not getattr(self, "DISABLE_BRIDGE", False):
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
            bridge_answer = self._strip_tables_and_images(bridge_answer)
            if '|' in bridge_answer and '\n' in bridge_answer:
                bridge_answer = fix_markdown_table(bridge_answer)
            else:
                bridge_answer = self._coerce_text_to_table_if_possible(bridge_answer)

            # [YENİ] Dosya ile kıyasla ve kararı ver
            out_bytes = self._apply_file_validation_and_route(
                user_id=user_id,
                user_message=user_message,
                ai_answer_text=bridge_answer
            )
            yield out_bytes
            return



        # === Hibrit RAG fallback (file_search yoksa ya da bağlam üretmediyse) ===
                # === Hibrit RAG GLOBAL FALLBACK ===
        # Buraya kadar hiçbir blok net bir yanıt üretemediyse
        # soruyu son bir kez SQL tabanlı Hybrid RAG'e sor.
        # KbVectors'ta yeterince benzer kayıt bulunamazsa
        # _answer_with_hybrid_rag zaten 'kayıt yok' mesajı döner.
        if self.HYBRID_RAG:
            ans = (self._answer_with_hybrid_rag(user_message, user_id=user_id) or "").strip()

            if ans:
                out_md = self.markdown_processor.transform_text_to_markdown(ans)
                if '|' in out_md and '\n' in out_md:
                    out_md = fix_markdown_table(out_md)
                yield self._deliver_locally(
                    out_md,
                    original_user_message=user_message,
                    user_id=user_id
                )
                return



        # (Bridge boş dönerse normal '8) OpenAI API' yerel akışınıza düşsün.)

       # 8) Eğer buraya geldiysek => Assistant (beta threads)
        # 8) Eğer buraya geldiysek => Assistant (beta threads)
        assistant_id = self.user_states[user_id].get("assistant_id", None)
        if not assistant_id:
            yield "Uygun bir asistan bulunamadı.\n".encode("utf-8")
            return

        try:
            # İstersen burada asistanı daha net yapan kısa bir instruction ver
            instructions_override = (
                "Sen Škoda Türkiye dijital satış danışmanısın. "
                "Kısa ve net cevap ver. Uydurma bilgi verme. "
                "Gerekirse tek soru sor."
            )

            out = self.assistant_runner.ask(
                user_states=self.user_states,
                user_id=user_id,
                assistant_id=assistant_id,
                content=user_message,
                timeout=60.0,
                instructions_override=instructions_override,
                tool_resources_override=None,  # file_search / vector_store vs. kullanacaksan burada ver
                ephemeral=False                # konuşma hafızası istiyorsan False
            ) or ""

            out = out.strip()
            if not out:
                yield "Yanıt boş döndü.\n".encode("utf-8")
                return

            content_md = self.markdown_processor.transform_text_to_markdown(out)
            if '|' in content_md and '\n' in content_md:
                content_md = fix_markdown_table(content_md)

            yield content_md.encode("utf-8")
            return

        except Exception as e:
            self.logger.error(f"[BETA-THREADS] error: {e}")
            yield f"Bir hata oluştu: {str(e)}\n".encode("utf-8")
            return



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
        #time.sleep(1)
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
                yield SUPERB_E_SPORTLINE_PHEV_MD.encode("utf-8")
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
        # JSONL içeriği yüklüyse sırasıyla yayınla
        if getattr(self, "ENYAQ_OPS_FROM_JSONL", None):
            order = [
                "e prestige 60",
                "coupe e sportline 60",
                "coupe e sportline 85x",
                "e sportline 60",
                "e sportline 85x",
            ]
            for i, tr in enumerate(order):
                md = self.ENYAQ_OPS_FROM_JSONL.get(tr)
                if not md:
                    continue
                yield f"<b>Enyaq {tr.title()} - Opsiyonel Tablosu</b><br>".encode("utf-8")
                yield md.encode("utf-8")
                if i < len(order) - 1:
                    yield b"<hr style='margin:15px 0;'>"
            return

        # JSONL yoksa eski sabitleri kullan
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
        if hasattr(self, "worker_thread"):
            self.worker_thread.join(5.0)
        try:
            if getattr(self, "neo4j_driver", None):
                self.neo4j_driver.close()
        except Exception:
            pass
        self.logger.info("ChatbotAPI shutdown complete.")