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

import secrets
 # tüm metodları göster
ASSISTANT_NAMES = {
    "fabia", "scala", "kamiq", "karoq", "kodiaq",
    "octavia", "superb", "elroq", "enyaq"
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
def normalize_tr_text(txt):
    import re, unicodedata
    # ... mevcut dönüşümler ...
    txt = re.sub(r"\s+", " ", txt.strip().lower())

    # Yeni: ek temizleme
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


class ChatbotAPI:
    import difflib
    import re
    import re, unicodedata
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
            Tek bir donanım için (örn. DCC Pro) trim bazlı S/O/Yok durumlarını
            satış-dili bir paragraf haline getirir.
            Ör: Premium: Yok; Prestige: Yok; Sportline: Standart; RS: Standart
            """
            if not trims or not status_map:
                return ""

            # S/O/— -> okunur metin
            def pretty_status(code: str | None) -> str:
                if code == "S":
                    return "Standart"
                if code == "O":
                    return "Opsiyonel"
                return "Yok"

            # Trim durum özetini tek satır string yap
            parts = []
            for t in trims:
                code = status_map.get(t)
                parts.append(f"{t.title()}: {pretty_status(code)}")
            value_str = "; ".join(parts)

            # Var olan NLG jeneratörünü kullan
            return self._nlg_via_openai(
                model_name=model_name,
                metric=f"Donanım: {feature}",
                value=value_str,
                tone=tone or os.getenv("NLG_TONE", "neutral"),
                length=length,
            )

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
            for i, c in enumerate(cols):
                if trim_pref.lower().replace(" ", "_") in c.lower():
                    cell = str(row[i] or "").strip()
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

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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

        # anahtar seti: tokenlar + bigramlar + TR→EN eşlemler + bilinen kısaltmalar
        tokens = [w for w in re.findall(r"[0-9a-zçğıöşü]+", q_norm) if len(w) >= 2]
        bigrams = [" ".join([tokens[i], tokens[i+1]]) for i in range(len(tokens)-1)]
        terms = set(tokens + bigrams)
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
            oz = nrm(row.get("ozellik"))
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
                "ozellik": (row.get("ozellik") or "").strip(),
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

    def _feature_lookup_any(self, model: str, user_text: str) -> tuple[list[str], dict]:
        """
        HIZLI YOL: SP/alias yok. Kullanıcı ifadesini varyantlara genişlet,
        doğrudan EquipmentList_* tablosunda LIKE ile ara ve S/O/— döndür.
        """
        import re
        if not model or not user_text:
            return [], {}

        q = self._norm_alias(user_text)

        # 1) çekirdek ipuçları (kritikler)
        QUICK_HINTS = {
            "park asistan": ["park asistan", "park assist", "otomatik park"],
            "cam tavan": ["cam tavan", "panoramik cam tavan", "açılır cam tavan", "sunroof", "glass roof"],
            "matrix": ["matrix", "matrix led", "dla", "dynamic light assist"],
            "geri görüş": ["geri görüş kamera", "rear view camera", "reverse camera"],
            "360": ["360 kamera", "area view", "top view camera"],
        }
        needles = set()
        for k, lst in QUICK_HINTS.items():
            if k in q:
                needles.update(lst)

        # 2) TR→EN eşlemeler ve token/bigramlar
        needles.update(self._to_english_terms(user_text))
        toks = [t for t in re.findall(r"[0-9a-zçğıöşü]+", q) if len(t) >= 2]
        bigrams = [" ".join([toks[i], toks[i+1]]) for i in range(len(toks)-1)]
        needles.update(toks)
        needles.update(bigrams)

        # 3) gereksizleri at, sıralı tekilleştir
        needles = [n for n in dict.fromkeys([self._norm_alias(x) for x in needles]) if len(n) >= 2]

        # 4) doğrudan EquipmentList LIKE
        trims, status_map = self._feature_status_from_equipment(model, feature_keywords=needles)
        return trims, status_map

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

    def _feature_status_from_equipment(self, model: str, feature_keywords: list[str]) -> tuple[list[str], dict]:
        """
        Modelin en güncel EquipmentList tablosunda verilen anahtarları (LIKE) arar.
        Dönüş:
        trims: trim kolonları (bulunanlar)
        status_map: {trim: 'S'|'O'|'—'}  (ilk eşleşen satır baz alınır)
        """
        import re, contextlib
        m = (model or "").strip().upper()
        if not m or not feature_keywords:
            return [], {}

        # 1) En güncel tablo
        tname = self._latest_equipment_table_for(model)
        if not tname:
            return [], {}

        conn = self._sql_conn(); cur = conn.cursor()
        try:
            # 2) Kolonları çek
            cur.execute(f"SELECT TOP 0 * FROM [dbo].[{tname}] WITH (NOLOCK)")
            cols = [c[0] for c in cur.description] if cur.description else []
            if not cols:
                return [], {}

            # Özellik/isim kolonu
            name_candidates = ["Equipment","Donanim","Donanım","Ozellik","Özellik","Name","Title","Attribute","Feature"]
            feat_col = next((c for c in name_candidates if c in cols), None)
            if not feat_col:
                # heuristik
                feat_col = next((c for c in cols if re.search(r"(equip|donan|özellik|ozellik|name|title|attr)", c, re.I)), None)
            if not feat_col:
                return [], {}

            # Trim kolonları
            known_trims = ["premium","elite","prestige","sportline","monte carlo","rs",
                        "l&k crystal","sportline phev","e prestige 60","e sportline 60",
                        "coupe e sportline 60","e sportline 85x","coupe e sportline 85x"]
            trim_cols = []
            low2orig = {c.lower(): c for c in cols}
            for t in known_trims:
                if t in low2orig:
                    trim_cols.append(low2orig[t])
            if not trim_cols:
                # fallback: adında trim çağrışımı olan tüm kolonlar
                trim_cols = [c for c in cols if re.search(r"(premium|elite|prestige|sportline|monte|rs|crystal|phev|e\s*sportline|e\s*prestige)", c, re.I)]
            if not trim_cols:
                return [], {}

            # 3) LIKE filtresi
            coll = os.getenv("SQL_CI_COLLATE", "Turkish_100_CI_AI")
            use_ft_env = os.getenv("USE_MSSQL_FULLTEXT", "0") == "1"
            use_ft = False
            try:
                use_ft = use_ft_env and self._has_fulltext(conn, tname, feat_col)
            except Exception:
                use_ft = False

            where_sql, params = self._make_where_for_keywords(feat_col, feature_keywords, use_ft, coll)
            sql = f"SELECT TOP 30 [{feat_col}], {', '.join(f'[{c}]' for c in trim_cols)} FROM [dbo].[{tname}] WITH (NOLOCK) WHERE {where_sql}"
            cur.execute(sql, params)

            rows = cur.fetchall()
            if not rows:
                return [], {}

            # 4) İlk eşleşen satır(lar)dan statü çıkar
            status_map = {}
            for r in rows:
                rec = { ([feat_col] + trim_cols)[i]: r[i] for i in range(1+len(trim_cols)) }
                for tc in trim_cols:
                    raw = rec.get(tc)
                    status_map[tc] = self._normalize_equipment_status(raw)

            # 5) Trim başlık sırası
            trims_pretty = [tc for tc in trim_cols]
            return trims_pretty, status_map

        finally:
            with contextlib.suppress(Exception): cur.close()
            with contextlib.suppress(Exception): conn.close()

    # ChatbotAPI sınıfına ekleyin
    _SPEC_KEYWORDS = {
        # norm_key            : (ad_kolonunda aranan terimler, md'de aranan başlık)
        "tork":               (["%tork%", "%torque%"],                          "Maks. tork (Nm @ dev/dak)"),
        "güç":                (["%güç%", "%guc%", "%power%", "%ps%", "%hp%"],   "Maks. güç (kW/PS @ dev/dak)"),
        "beygir":             (["%beygir%", "%ps%", "%hp%", "%power%"],         "Maks. güç (kW/PS @ dev/dak)"),
        "maksimum hız":       (["%maks%hız%", "%max%speed%", "%top%speed%"],    "Maks. hız (km/h)"),
        "0-100":              (["%0%100%", "%0-100%", "%ivme%", "%accel%"],     "0-100 km/h (sn)"),
        "0 100":              (["%0%100%", "%0-100%", "%ivme%", "%accel%"],     "0-100 km/h (sn)"),
        "co2":                (["%co2%", "%emisyon%"],                          "CO2 Emisyonu (g/km)"),
        "yakıt tüketimi":     (["%tüketim%", "%l/100%", "%consumption%"],       "Birleşik (l/100 km)"),
        "menzil":             (["%menzil%", "%range%"],                         "Menzil (WLTP)"),
    }

    def _generic_spec_from_sql(self, model_slug: str, want: str) -> str | None:
        import re, contextlib
        m = (model_slug or "").strip().upper()
        if not m or not want:
            return None

        self.logger.info(f"[SQL-SPEC] Checking model={m}, want={want}, STRICT={getattr(self,'STRICT_MODEL_ONLY',False)}")

        # 1) İstekten anahtar TERİM(ler)i çıkar (tork, 0-100, güç, menzil, co2, tüketim, max hız …)
        want_norm_all = normalize_tr_text(want).lower()

        # (a) doğrudan sözlük eşlemesi
        key_hits = []
        for canon, (like_terms, _) in (self._SPEC_KEYWORDS or {}).items():
            key_low = normalize_tr_text(canon).lower()
            if key_low in want_norm_all:
                key_hits.append(canon)
        # (b) düzenli ifade eşleşmeleri (0-100 vb.)
        if re.search(r"\b0\s*[-–—]?\s*100\b", want_norm_all):
            if "0-100" not in key_hits:
                key_hits.append("0-100")
        # (c) kelime bazlı sezgisel tarama
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
        }
        for w, k in word_map.items():
            if w in want_norm_all and k not in key_hits:
                key_hits.append(k)

        # Bu fonksiyon, LIKE’a vereceği terimleri burada hesaplar:
        def terms_for(canon_key: str) -> list[str]:
            # _SPEC_KEYWORDS içindeki LIKE kalıpları (ör: %tork% / %torque% / %0%100% …)
            like_terms, _ = self._SPEC_KEYWORDS.get(canon_key, ([], None))
            if like_terms:
                return like_terms[:]
            # sözlükte yoksa, güvenli fallback: canon kendisi
            return [f"%{normalize_tr_text(canon_key).lower()}%"]

        # Nihai arama terimleri (ör. “tork” seçildiyse: ["%tork%","%torque%"])
                # Nihai arama terimleri (ör. “tork” seçildiyse: ["%tork%","%torque%"])
        final_like_terms: list[str] = []
        for k in key_hits:
            final_like_terms.extend(terms_for(k))

        # ❗ Hiçbir metrik anahtarı bulunamadıysa bu fonksiyonu pas geç.
        # Örn: "kodiaq elektrikli motora sahip mi" gibi sorular donanım /
        # var-yok sorusudur, teknik metrik değildir; burada işlem yapmak istemiyoruz.
        if not key_hits:
            return None

        conn = self._sql_conn(); cur = conn.cursor()
        try:
            patterns = [
                f"Imported\\_KODA\\_{m}\\_MY\\_%",
                f"Imported\\_{m}%",
                f"TechSpecs\\_KODA\\_{m}\\_MY\\_%",
                f"EquipmentList\\_KODA\\_{m}\\_MY\\_%",
                f"PriceList\\_KODA\\_{m}\\_MY\\_%",
                f"%{m}%",  # ← ek (adın başına/sonuna bakmadan)

            ]
            collate = os.getenv("SQL_CI_COLLATE", "Turkish_100_CI_AI")

            for p in patterns:
                self.logger.info(f"[SQL-SPEC] scanning pattern={p}")
                cur.execute("SELECT name FROM sys.tables WHERE name LIKE ? ESCAPE '\\' ORDER BY name DESC", (p,))
                for (tname,) in cur.fetchall():
                    if getattr(self, "STRICT_MODEL_ONLY", False):
                        T = tname.upper()
                        if not (f"_{m}_" in T or T.endswith(f"_{m}") or T.startswith(f"{m}_")):
                            continue
                    try:
                        cur.execute(f"SELECT TOP 0 * FROM [{tname}]")
                        cols = [c[0] for c in cur.description]
                        val_cols = [c for c in cols if re.search(
                            r"(deger|değer|value|val|content|desc|description|açıklama|aciklama|icerik|içerik|spec|specval|spec_value|unit|birim|data|veri|number|num)",
                            c, re.I
                        )]
                        if not val_cols:
                            val_cols = [c for c in cols if c.lower() not in ('id','model','ozellik','özellik')]

                        # 2) İsim/başlık kolonları (Description/Desc buradan çıkarıldı)
                        name_cols = [c for c in cols if re.search(
                            r"(ozellik|özellik|name|title|attribute|specname|featurename)",
                            c, re.I
                        ) and c not in val_cols]
                        if not name_cols and not val_cols:
                            continue

                        # 2) LIKE WHERE: anahtar terimler için geniş OR kurgula
                        where_parts, params = [], []
                        target_cols = (name_cols + val_cols)
                        for nc in target_cols:
                            for lt in final_like_terms:
                                where_parts.append(f"LOWER(CONVERT(NVARCHAR(4000),[{nc}])) COLLATE {collate} LIKE ?")
                                params.append(lt)

                        if not where_parts:
                            continue

                        # 1) Değer kolonlarını bir araya getir (boşsa en azından '')
                        vblob_expr = " + ' ' + ".join([f"CONVERT(NVARCHAR(4000),[{c}])" for c in val_cols]) if val_cols else "''"

                        # 2) Değer içeren satırları öne al: önce rakam var mı, sonra uzunluk
                        sql = (
                            f"SELECT TOP 20 {', '.join(target_cols)}, ({vblob_expr}) AS _vblob "
                            f"FROM [{tname}] WITH (NOLOCK) WHERE " + " OR ".join(where_parts) + " "
                            f"ORDER BY CASE WHEN ({vblob_expr}) LIKE '%[0-9]%' THEN 0 ELSE 1 END, "
                            f"LEN(({vblob_expr})) DESC"
                        )
                        cur.execute(sql, params)
                        row = cur.fetchone()

                        if row:
                            # Kolon listeleri
                            cols = target_cols  # SELECT sırasında kullandığımız birleşik liste
                            # İsim kolonlarını ayrı tut
                            name_cols_set = set(name_cols)

                            # ❶ Önce “değer” benzeri kolonlardan en iyi hücreyi çek
                            val_blob = self._best_value_from_row(cols, row, name_cols_set)

                            # _generic_spec_from_sql içinde, val_blob üretiminden HEMEN SONRA ekle:
                            import re

                            def _pick_metric_from_row_blob(metric_key: str, row_text: str) -> str | None:
                                txt = (row_text or "").lower().replace(",", ".")
                                # Temel metrik regex’leri
                                patterns = {
                                    "tork":        r"(\d{2,4}(?:\.\d+)?)\s*nm\b",
                                    "güç":         r"(\d{2,4}(?:\.\d+)?)\s*(ps|hp|kw)\b",
                                    "0-100":       r"(\d{1,2}(?:\.\d+)?)\s*(sn|s)\b",
                                    "maksimum hız":r"(\d{2,3}(?:\.\d+)?)\s*km/?h\b",
                                    "co2":         r"(\d{2,3}(?:\.\d+)?)\s*g/?km\b",
                                    "yakıt tüketimi": r"(\d(?:\.\d+)?)\s*l/100\s*km\b",
                                    "menzil":      r"(\d{2,4})\s*km\b",
                                }
                                # anahtar normalizasyonu
                                key = "tork" if "tork" in metric_key else \
                                    "güç" if any(k in metric_key for k in ("güç","beygir","hp","ps","power","kw")) else \
                                    "0-100" if re.search(r"\b0\s*[-–—]?\s*100\b", metric_key) else \
                                    "maksimum hız" if "hız" in metric_key or "hiz" in metric_key else \
                                    "co2" if "co2" in metric_key or "emisyon" in metric_key else \
                                    "yakıt tüketimi" if "tüketim" in metric_key or "l/100" in metric_key else \
                                    "menzil" if "menzil" in metric_key or "range" in metric_key else None
                                if not key or key not in patterns: 
                                    return None
                                m = re.search(patterns[key], txt)
                                if not m:
                                    return None
                                # birim üretimi
                                if key == "tork":        return f"{m.group(1)} Nm"
                                if key == "güç":         return f"{m.group(1)} {m.group(2).upper()}"
                                if key == "0-100":       return f"{m.group(1)} sn"
                                if key == "maksimum hız":return f"{m.group(1)} km/h"
                                if key == "co2":         return f"{m.group(1)} g/km"
                                if key == "yakıt tüketimi": return f"{m.group(1)} l/100 km"
                                if key == "menzil":      return f"{m.group(1)} km"
                                return None

                            # … val_blob seçiminin ALTINA:
                            if not re.search(r"\d", val_blob or ""):
                                row_blob = " ".join(str(row[cols.index(c)] or "") for c in cols)
                                picked = _pick_metric_from_row_blob(want_norm_all, row_blob)
                                if picked:
                                    self.logger.info(f"[SQL-SPEC] ROW-BLOB pick -> {picked}")
                                    return picked


                            # ❷ Hâlâ boşsa, tüm value-type kolonları birleştir (eski davranış)
                            if not val_blob:
                                val_blob = " ".join(
                                    str(row[cols.index(c)] or "").strip()
                                    for c in cols
                                    if re.search(r"(deger|değer|value|val|content|desc|açıklama|aciklama|icerik|içerik|spec|specval|spec_value|unit|birim|data|veri|number|num)", c, re.I)
                                ).strip()

                            # ❸ Yine boşsa, satırdaki isim + ilk dolu komşu hücreyi kullan (son çare)
                            if not val_blob:
                                names_join = " ".join(str(row[cols.index(c)] or "").strip() for c in name_cols)
                                others = [str(row[i] or "").strip() for i, c in enumerate(cols) if c not in name_cols_set and str(row[i] or "").strip()]
                                val_blob = (others[0] if others else names_join).strip()

                            self.logger.info(f"[SQL-SPEC] HIT {tname} -> {val_blob[:160]}")
                            return val_blob or None
                    except Exception as e:
                        self.logger.warning(f"[SQL-SPEC] table read failed: {tname}, err: {e}")
                        continue
            
                    # === patterns döngüsünden SONRA ve henüz return edilmediyse: geniş wildcard tarama ===
            if getattr(self, "STRICT_MODEL_ONLY", False):
                try:
                    wild = f"%{m}%"  # KODIAQ
                    # Tablolar
                    cur.execute("SELECT name FROM sys.tables WHERE UPPER(name) LIKE ? ORDER BY name DESC", (wild,))
                    table_names = [r[0] for r in cur.fetchall()]

                    # View'lar
                    cur.execute("SELECT name FROM sys.views WHERE UPPER(name) LIKE ? ORDER BY name DESC", (wild,))
                    view_names = [r[0] for r in cur.fetchall()]

                    for tname in (table_names + view_names):
                        try:
                            cur.execute(f"SELECT TOP 0 * FROM [{tname}]")
                            cols = [c[0] for c in cur.description]
                            # 1) Değer benzeri kolonları önce seç
                            val_cols = [c for c in cols if re.search(
                                r"(deger|değer|value|val|content|desc|description|açıklama|aciklama|icerik|içerik|spec|specval|spec_value|unit|birim|data|veri|number|num)",
                                c, re.I
                            )]

                            # 2) İsim/başlık kolonları (Description/Desc buradan çıkarıldı)
                            name_cols = [c for c in cols if re.search(
                                r"(ozellik|özellik|name|title|attribute|specname|featurename)",
                                c, re.I
                            ) and c not in val_cols]

                            if not name_cols and not val_cols:
                                continue

                            where_parts, params = [], []
                            collate = os.getenv("SQL_CI_COLLATE", "Turkish_100_CI_AI")
                            final_like_terms = final_like_terms or [f"%{normalize_tr_text(want).lower()}%"]
                            for nc in (name_cols + val_cols):
                                for lt in final_like_terms:
                                    where_parts.append(f"LOWER(CONVERT(NVARCHAR(4000),[{nc}])) COLLATE {collate} LIKE ?")
                                    params.append(lt)
                            if not where_parts:
                                continue

                            sql = f"SELECT TOP 1 {', '.join(name_cols + val_cols)} FROM [{tname}] WITH (NOLOCK) WHERE " + " OR ".join(where_parts)
                            cur.execute(sql, params)
                            row = cur.fetchone()
                            if row:
                                cols2 = (name_cols + val_cols)
                                val_blob = self._best_value_from_row(cols2, row, set(name_cols))
                                if not val_blob:
                                    val_blob = " ".join(str(x or "").strip() for x in row if x).strip()
                                self.logger.info(f"[SQL-SPEC] HIT* {tname} -> {val_blob[:160]}")
                                return val_blob or None
                        except Exception:
                            continue
                except Exception:
                    pass

        except Exception as e:
            self.logger.error(f"[SQL-SPEC] generic error: {e}")
        finally:
            with contextlib.suppress(Exception): cur.close()
            with contextlib.suppress(Exception): conn.close()
        # _generic_spec_from_sql sonunda, return None; ÖNCESİNE ekle:
        try:
            # SQL başarısızsa teknik tablo fallback
            model_low = (model_slug or "").lower()
            md = self._get_teknik_md_for_model(model_low)
            if md:
                _, d = self._parse_teknik_md_to_dict(md)
                # Seçilecek anahtar (ör: 'Maks. tork (Nm @ dev/dak)')
                key_guess = None
                if "tork" in want_norm_all: key_guess = "Maks. tork (Nm @ dev/dak)"
                elif any(k in want_norm_all for k in ["güç","beygir","hp","ps","power","kw"]):
                    key_guess = "Maks. güç (kW/PS @ dev/dak)"
                elif re.search(r"\b0\s*[-–—]?\s*100\b", want_norm_all):
                    key_guess = "0-100 km/h (sn)"
                elif any(k in want_norm_all for k in ["hız","hiz","max speed","top speed","maks"]):
                    key_guess = "Maks. hız (km/h)"
                elif "co2" in want_norm_all or "emisyon" in want_norm_all:
                    key_guess = "CO2 Emisyonu (g/km)"
                elif any(k in want_norm_all for k in ["tüketim","l/100"]):
                    key_guess = "Birleşik (l/100 km)"
                elif "menzil" in want_norm_all or "range" in want_norm_all:
                    key_guess = "Menzil (WLTP)"
                if key_guess:
                    v = self._get_spec_value_from_dict(d, key_guess)
                    if v and re.search(r"\d", v):
                        self.logger.info(f"[SQL-SPEC] FALLBACK Teknik MD -> {v}")
                        return v
        except Exception as _e:
            self.logger.warning(f"[SQL-SPEC] teknik MD fallback err: {_e}")

        return None
        


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
    def _answer_with_sql_rag(self, user_message: str, user_id: str) -> bytes | None:
        # 1) DB vektörlerinden bağlamı çek
        top = self._kb_vector_search(user_message, k=15)

        if not top:
            # Bağlam yoksa boş dönmeyelim; üst akışta RAG_ONLY=1 olduğu için direkt duracağız.
            return b"SQL RAG: kayit bulunamadi."

        ctx = "\n".join([f"- [{round(s,3)}] {d['text']}" for s, d in top])

        instruction = (
            "Yalnızca AŞAĞIDAKİ SQL BAĞLAMI'na dayanarak cevap ver. "
            "Bağlam dışı bilgi ekleme. Tablo/anahtar-değer varsa Markdown TABLO yap. "
            "SQL sorgusu/kaynak id yazma. Türkçe ve net yaz.\n\n"
            f"=== SQL BAĞLAM BAŞLANGIÇ ===\n{ctx}\n=== SQL BAĞLAM BİTİŞ ==="
        )

        out = self._ask_assistant(
            user_id=user_id,
            assistant_id=self.user_states.get(user_id, {}).get("assistant_id") or self._pick_least_busy_assistant(),
            content=user_message,
            timeout=45.0,
            instructions_override=instruction,
            ephemeral=True
        ) or ""

        out_md = self.markdown_processor.transform_text_to_markdown(out)
        if '|' in out_md and '\n' in out_md:
            out_md = fix_markdown_table(out_md)
        else:
            out_md = self._coerce_text_to_table_if_possible(out_md)

        return out_md.encode("utf-8")
 

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

    def _answer_via_rag_compare(
        self,
        user_id: str,
        assistant_id: str,
        user_message: str,
        pairs: list[tuple[str, str]]
    ) -> bytes:
        """
        Model+trim karşılaştırmalarında öncelikli RAG cevabı.
        1) Varsa OpenAI File Search (vector_store) ile -> kesinlikle dosya kanıtına dayalı
        2) Yoksa HYBRID RAG (SQL vektörleri) fallback
        """
        # 1) OpenAI File Search ile (tercihli)
        if getattr(self, "USE_OPENAI_FILE_SEARCH", False) and getattr(self, "VECTOR_STORE_ID", "") and assistant_id:
            # Sütun başlıkları için insan-okur biçim
            items = []
            for m, t in (pairs or []):
                m2 = (m or "").strip().title()
                t2 = (t or "").strip().title()
                items.append((f"{m2} {t2}".strip()))
            # Çıktı talimatı (dosya-dışı bilgi yasak, tablo şart)
            instructions = (
                "Cevabı YALNIZCA bağlı dosya araması (file_search) sonuçlarına dayanarak hazırla. "
                "Görev: Kullanıcının belirttiği model+trim çiftlerini karşılaştır. "
                "Önce 2–5 maddelik kısa ve net bir özet yaz. "
                "Ardından iyi biçimlendirilmiş bir Markdown tablo ver: "
                "Sütunlar -> her bir model+trim (sırayı koru). Satırlar -> önemli özellikler/sayısal veriler. "
                "Kanıt bulunmayan alanlar için hücreye 'KB’de yok' yaz. "
                "Varsayım yapma, dosya dışı bilgi ekleme."
            )
            rag_out = self._ask_assistant(
                user_id=user_id,
                assistant_id=assistant_id,
                content=user_message,
                timeout=60.0,
                instructions_override=instructions,
                ephemeral=True
            ) or ""

            out_md = self.markdown_processor.transform_text_to_markdown(rag_out)
            if '|' in out_md and '\n' in out_md:
                out_md = fix_markdown_table(out_md)
            return self._deliver_locally(
                body=out_md,
                original_user_message=user_message,
                user_id=user_id
            )

        # 2) Fallback: Hybrid RAG (SQL vektörleri)
        if getattr(self, "HYBRID_RAG", False):
            text = self._answer_with_hybrid_rag(user_message) or "Bilgi tabanında karşılık bulunamadı."
            return self._deliver_locally(
                body=text,
                original_user_message=user_message,
                user_id=user_id
            )

        return "Bilgi tabanına (RAG) erişilemiyor.".encode("utf-8")

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
        TRIM_COL_KEYS = ["premium","elite","prestige","sportline","monte carlo","monte_carlo","rs","l&k crystal","l n k crystal","lk crystal","sportline phev","e prestige 60","coupe e sportline 60","coupe e sportline 85x","e sportline 60","e sportline 85x"]
        present_trims = [low2orig[k] for k in TRIM_COL_KEYS if k in low2orig]
        pick_key = norm(os.getenv("EQUIP_BASE_TRIM", "") or (preferred_trim or ""))
        chosen_trim_col = low2orig.get(pick_key, present_trims[0] if present_trims else None)

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
        trim: str | None = None
    ) -> str:
        models = [m.lower() for m in models if m]
        if len(models) < 2: return ""

        preferred_trim = trim or os.getenv("EQUIP_BASE_TRIM", "premium")

        order_for, status_for, display_for = {}, {}, {}
        valid_models = []
        for m in models:
            tname = self._latest_equipment_table_for(m)
            if not tname: continue
            order_keys, smap, dmap = self._equipment_dict_from_table(tname, preferred_trim=preferred_trim)
            if not smap: continue
            order_for[m], status_for[m], display_for[m] = order_keys, smap, dmap
            valid_models.append(m)

        if len(valid_models) < 2:
            return ""

        # Birleşik anahtar kümesi (ilk görülen sırayı koru)
        all_keys, seen = [], set()
        for m in valid_models:
            for k in order_for[m]:
                if k not in seen:
                    seen.add(k); all_keys.append(k)

        # Opsiyonel filtre: kanonik anahtar ve gösterim adına göre
        if only_keywords:
            kw = [normalize_tr_text(x).lower() for x in only_keywords]
            def hit(k):
                name = display_for[valid_models[0]].get(k, k)
                n = normalize_tr_text(name).lower()
                return any(w in n or w in k for w in kw)
            filtered = [k for k in all_keys if hit(k)]
            if filtered: all_keys = filtered

        # (İsteğe bağlı) Gruplama/sıralama: Feature tablosundaki priority/group_name ile sıralayabilirsiniz.
        # Şimdilik mevcut sıra korunuyor.

        # Durum sembolleri okunaklı olsun
        def pretty(s): return "✓" if s == "S" else ("○" if s == "O" else "—")

        header = ["Özellik"] + [x.title() for x in valid_models]
        lines  = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"]*len(header)) + "|"]

        # Gösterim adı modeli: ilk modeldeki display_map’tan al, yoksa diğerlerinden
        def show_name(key):
            for m in valid_models:
                name = display_for[m].get(key)
                if name: return name
            return key  # son çare

        for key in all_keys:
            row = [show_name(key)]
            for m in valid_models:
                st = status_for[m].get(key, "—")
                row.append(pretty(st))
            lines.append("| " + " | ".join(row) + " |")

        md = fix_markdown_table("\n".join(lines))
        return self._strip_price_from_any(md) 



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
        q = (query or "").lower()
        hints = []
        if any(k in q for k in ["fiyat","anahtar teslim","ötv","price","liste"]):
            hints.append("PriceList")
        if any(k in q for k in ["donanım","özellik","paket","equipment"]):
            hints.append("EquipmentList")

        # >>> YENİ: teknik & bagaj ipuçları
        if any(k in q for k in ["bagaj","hacim","dm3","bagaj hacmi","bagaj hacmı"]):
            hints += ["TechSpecs", "Imported"]
        if any(k in q for k in ["menzil","batarya","şarj","kwh","co2","0-100","hız","tork","güç","ps","kw"]):
            hints += ["TechSpecs", "Imported"]

        # >>> YENİ: Boşsa artık default verme (tüm KbVectors havuzuna bak)
        return list(dict.fromkeys(hints))


    def _row_to_text(self, table_name: str, row: dict) -> str:
        parts = [f"Tablo={table_name}"]
        for k, v in row.items():
            if v is None: 
                continue
            s = str(v).strip()
            if s:
                parts.append(f"{k}: {s}")
        return " | ".join(parts)

    # ------------------- Indexleme: Tablolardan KbVectors’a -------------------

    def _kb_index_one_table(self, table_name: str, limit: int = 10000) -> int:
        conn = self._sql_conn()
        cur  = conn.cursor()
        try:
            cur.execute(f"SELECT TOP {limit} * FROM [dbo].[{table_name}] WITH (NOLOCK)")
            cols = [c[0] for c in cur.description] if cur.description else []
            rows = cur.fetchall()
        except Exception as e:
            self.logger.error(f"[KB-IDX] {table_name} okunamadı: {e}")
            conn.close()
            return 0

        if not rows:
            conn.close()
            return 0

        # Satırları metne çevir
        docs, metas = [], []
        for r in rows:
            d = {cols[i]: r[i] for i in range(len(cols))}
            txt = self._row_to_text(table_name, d)
            if len(txt) >= 5:
                docs.append(txt)
                metas.append({
                    "model": (self._guess_model_for_query(table_name) or self._guess_model_for_query(txt) or "GENERIC").upper(),
                    "table_name": table_name,
                    "row_key": None
                })

        if not docs:
            conn.close()
            return 0

        # Embedding üret (batched)
        BATCH = 256
        inserted = 0
        for i in range(0, len(docs), BATCH):
            chunk = docs[i:i+BATCH]
            try:
                em = self.client.embeddings.create(model=self._embed_model_name(), input=chunk)
            except Exception as e:
                self.logger.error(f"[KB-IDX] embeddings error: {e}")
                break
            vecs = [np.array(it.embedding, dtype=np.float32) for it in em.data]

            for j, vec in enumerate(vecs):
                m = metas[i+j]
                try:
                    cur.execute("""
                        INSERT INTO dbo.KbVectors (model, table_name, row_key, text, dim, embedding)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (m["model"], m["table_name"], m["row_key"], chunk[j], self._embed_dim(), self._to_bytes_float32(vec)))
                    inserted += 1
                except Exception as e:
                    self.logger.error(f"[KB-IDX] insert fail: {e}")
            conn.commit()

        conn.close()
        return inserted

    def _kb_index_all(self) -> dict:
        """
        sys.tables’tan dinamik olarak tüm PriceList_%1 ve EquipmentList_%1 tablolarını tarar,
        KbVectors’a embedding yazar. (Tek tuş ReIndex için)
        """
        patterns = [
            r"PriceList\_KODA\_%",        # fiyat
            r"EquipmentList\_KODA\_%",    # donanım
            r"Imported\_KODA\_%",         # ithal/karma (KODA_*)
            r"Imported\_%",               # bazıları KODA_ içermiyor (Imported_Enyaq1 gibi)
            r"TechSpecs\_KODA\_%",        # varsa teknik spesifikasyon tablolarınız
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
        conn.close()

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

    def _kb_vector_search(self, query: str, k: int = 12) -> list[tuple[float, dict]]:
        # 1) query embedding
        try:
            qe = self.client.embeddings.create(model=self._embed_model_name(), input=query).data[0].embedding
        except Exception as e:
            self.logger.error(f"[KB-SEARCH] embed fail: {e}")
            return []
        qv = np.array(qe, dtype=np.float32)

        # 2) ön filtre (model ve tablo ipuçları)
        model_hint  = (self._guess_model_for_query(query) or "").upper()
        table_hints = self._relevant_table_hints(query)

        where = []
        params = []
        if model_hint:
            where.append("model = ?")
            params.append(model_hint)
        if table_hints:
            where.append("(" + " OR ".join(["table_name LIKE ?"]*len(table_hints)) + ")")
            params += [h + "%" for h in table_hints]
        where_sql = "WHERE " + " AND ".join(where) if where else ""

        conn = self._sql_conn()
        cur  = conn.cursor()
        cur.execute(f"""
            SELECT TOP 1000 id, model, table_name, text, dim, embedding
            FROM dbo.KbVectors WITH (NOLOCK)
            {where_sql}
            ORDER BY id DESC
        """, params)
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return []

        scored = []
        for r in rows:
            emb = self._from_bytes_float32(r[5])
            score = self._cosine(qv, emb)
            scored.append((score, dict(id=r[0], model=r[1], table=r[2], text=r[3])))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:k]

    def _answer_with_hybrid_rag(self, query: str) -> str:
        """
        KbVectors’tan top-k bağlamı getir, OpenAI’ye 'sadece bu bağlamla' yanıt üret.
        """
        if getattr(self, "STRICT_SQL_ONLY", False):
            return ""

        top = self._kb_vector_search(query, k=15)
        context = "\n".join([f"- [{round(s,3)}] {d['text']}" for s,d in top])

        sys = ("Sadece verilen bağlamdaki bilgilere dayanarak yanıt ver. "
            "Bağlamda yoksa 'veritabanında karşılığı bulunamadı' de. "
            "Kıyas gerekiyorsa rakamları net yaz.")
        usr = f"Kullanıcı sorusu: {query}\n\nBağlam (SQL kaynaklı kayıtlar):\n{context}"

        try:
            resp = self.client.chat.completions.create(
                model=os.getenv("GEN_MODEL", "gpt-4o-mini"),
                messages=[{"role":"system","content":sys},
                        {"role":"user","content":usr}],
                temperature=0.2
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            self.logger.error(f"[KB-ANS] chat fail: {e}")
            return ""

    def _answer_via_rag_only(self, user_id: str, assistant_id: str, user_message: str) -> bytes:
        """
        Yalnızca vector store (file_search) kaynaklarından cevap üretir.
        Hiçbir sonuç yoksa 'KB’de yok' der ve genel bilgiye düşmez.
        """
        if not (self.USE_OPENAI_FILE_SEARCH and self.VECTOR_STORE_ID and assistant_id):
            return "Bilgi tabanına (RAG) erişilemiyor.".encode("utf-8")

        instructions = (
            "Cevabı YALNIZCA bağlı dosya araması (file_search) sonuçlarına dayanarak ver. "
            "Genel bilgi kullanma, varsayım yapma. "
            "Eğer dosya araması içinde ilgili kanıt/bölüm bulamazsan "
            "kısa ve net şekilde 'Bu konuda SQL tabanlı bilgi tabanımda kayıt yok.' de. "
            "Tablo gerekiyorsa düzgün Markdown tablo kullan, aksi halde düz metin ver. "
            "Kaynak/URL/kimlik yazma."
        )
        out = self._ask_assistant(
            user_id=user_id,
            assistant_id=assistant_id,
            content=user_message,
            timeout=60.0,
            instructions_override=instructions,
            ephemeral=True  # Her çağrıda temiz thread
        ) or ""

        out_md = self.markdown_processor.transform_text_to_markdown(out)
        if '|' in out_md and '\n' in out_md:
            out_md = fix_markdown_table(out_md)
        resp = self._deliver_locally(out_md, original_user_message=user_message, user_id=user_id)
        return resp

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
        return pyodbc.connect(cs)

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
        """
        Bayrağa göre (HIDE_SOURCES) metinden kaynak/citation izlerini temizleyip bytes döner.
        Tüm dışarı giden parçalara uygulanır.
        """
        if isinstance(payload, (bytes, bytearray)):
            s = payload.decode("utf-8", errors="ignore")
        else:
            s = str(payload or "")
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


    def _ensure_vector_store_and_upload(self):
        self.logger.info("[KB] ensure_vector_store_and_upload CALLED")

        if not getattr(self, "USE_OPENAI_FILE_SEARCH", False):
            self.logger.info("[KB] File search kapalı, çıkılıyor.")
            return

        vs_api = self._vs_api()
        if not vs_api:
            self.logger.warning("[KB] Vector Stores API bu SDK sürümünde yok; atlanıyor.")
            return

        try:
            self.VECTOR_STORE_NAME = os.getenv("VECTOR_STORE_NAME", "SkodaKB")
            self.VECTOR_STORE_ID = os.getenv("VECTOR_STORE_ID", "")

            # 1) Vector store yoksa oluştur
            if not self.VECTOR_STORE_ID:
                vs = vs_api.create(name=self.VECTOR_STORE_NAME)
                self.VECTOR_STORE_ID = vs.id

            # 2) Kaynak dosyaları hazırla
            file_paths = []
            if getattr(self, "RAG_FROM_SQL_ONLY", False):
                # >>> SADECE MSSQL'den üretilen markdown dosyaları <<<
                file_paths = self._export_openai_kb_from_sql()
            else:
                # Karışık kaynak (mevcut davranış)
                kb_path = self._export_openai_glossary_text()
                file_paths = [kb_path]

            if not file_paths:
                self.logger.warning("[KB] Yüklenecek dosya yok.")
                return

            # 3) Her dosyayı OpenAI Files'a yükle ve vector store'a iliştir
            uploaded_ids = []
            for p in file_paths:
                with open(p, "rb") as f:
                    file_obj = self.client.files.create(file=f, purpose="assistants")
                    uploaded_ids.append(file_obj.id)

            files_api = getattr(vs_api, "files", None)
            batches_api = getattr(vs_api, "file_batches", None)

            if batches_api and hasattr(batches_api, "upload_and_poll"):
                # Tek seferde toplu yükleme (destekliyse)
                with open(file_paths[0], "rb") as f0:  # API imzası dosya objesi isterse dummy açılış
                    batches_api.upload_and_poll(
                        vector_store_id=self.VECTOR_STORE_ID,
                        files=[open(p, "rb") for p in file_paths]
                    )
            elif files_api and hasattr(files_api, "create_and_poll"):
                for fid in uploaded_ids:
                    files_api.create_and_poll(
                        vector_store_id=self.VECTOR_STORE_ID,
                        file_id=fid
                    )
            else:
                # Basit iliştirme
                for fid in uploaded_ids:
                    files_api.create(vector_store_id=self.VECTOR_STORE_ID, file_id=fid)

            self.logger.info(f"[KB] Uploaded {len(uploaded_ids)} files to vector store: {self.VECTOR_STORE_ID}")

        except Exception as e:
            self.logger.error(f"[KB] Vector store init skipped: {e}")


    def _enable_file_search_on_assistants(self):
        if not getattr(self, "USE_OPENAI_FILE_SEARCH", False):
            return
        if not getattr(self, "VECTOR_STORE_ID", ""):
            return

        ids = set(list(self.ASSISTANT_CONFIG.keys()) + ([self.TEST_ASSISTANT_ID] if self.TEST_ASSISTANT_ID else []))
        for asst_id in ids:
            if not asst_id:
                continue
            try:
                # RAG_ONLY ise araçları 'sadece file_search' yap
                tools = [{"type": "file_search"}] if getattr(self, "RAG_ONLY", False) else []
                a = self.client.beta.assistants.retrieve(asst_id)
                if not tools:
                    # RAG_ONLY değilse mevcut araçlara file_search ekle
                    tools = []
                    for t in (a.tools or []):
                        t_type = getattr(t, "type", None) or (t.get("type") if isinstance(t, dict) else None)
                        if t_type:
                            tools.append({"type": t_type})
                    if not any(t["type"] == "file_search" for t in tools):
                        tools.append({"type": "file_search"})

                self.client.beta.assistants.update(
                    assistant_id=asst_id,
                    tools=tools,
                    tool_resources={"file_search": {"vector_store_ids": [self.VECTOR_STORE_ID]}},
                )
                self.logger.info(f"[KB] file_search enabled on {asst_id} (RAG_ONLY={self.RAG_ONLY})")
            except Exception as e:
                self.logger.error(f"[KB] assistant update failed for {asst_id}: {e}")


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
        model_hint: str | None = None
    ) -> bytes:
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
                    "Veri eksikse hücreyi ‘—’ ile doldur; özür/uyarı ekleme. "
                    "Kesinlikle kaynak/citation/dosya adı/URL veya belge kimliği yazma."
                ),
                ephemeral=True   # <-- NEW
            ) or ""

            # Markdown post‑process: hizalama + son çare tabloya çevirme
            out_md = self.markdown_processor.transform_text_to_markdown(out)
            
            if '|' in out_md and '\n' in out_md: 
                out_md = fix_markdown_table(out_md)
            
                out_md = self._strip_price_from_any(out_md)  # ⬅️ EKLE
                out_md = self._drop_kb_missing_rows_from_any(out_md)
                resp_bytes = out_md.encode("utf-8")
            #if '|' in out_md and '\n' in out_md:
             #   out_md = fix_markdown_table(out_md)
                
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
                    out_md = self._strip_price_from_any(out_md)  # ⬅️ EKLE
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
                "veri yetersizse ‘—’; özür/ret metni yazma. "
                "Kesinlikle kaynak/citation/dosya adı/URL veya belge kimliği yazma."
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
        t = normalize_tr_text(text or "").lower()
        p = normalize_tr_text(phrase or "").lower()
        return p in t  # fuzzy KAPALI



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

        # derlenmiş regex index’i
        self._SPEC_INDEX = None


        self.MAX_COMPARE_MODELS_PER_TABLE = int(os.getenv("MAX_COMPARE_MODELS_PER_TABLE", "6"))
        self.OPENAI_MATCH_THRESHOLD = float(os.getenv("OPENAI_MATCH_THRESHOLD", "0.80"))


        # __init__ içinde (diğer os.getenv okumalarının yanına)
        self.LONG_DELIVER_WORDS = int(os.getenv("LONG_DELIVER_WORDS", "30"))   # metin için varsayılan: 30 kelime
        self.LONG_TABLE_WORDS   = int(os.getenv("LONG_TABLE_WORDS", "800"))    # tablo/kaynak için kelime eşiği
        self.LONG_TABLE_ROWS    = int(os.getenv("LONG_TABLE_ROWS", "60"))      # tablo satır eşiği
        self.LONG_TOKENS        = int(os.getenv("LONG_TOKENS", "6500"))        # güvenlik tavanı (yaklaşık token)
        self.RAG_ONLY = os.getenv("RAG_ONLY", "0") == "1"
        self.USE_ANSWER_CACHE = os.getenv("USE_ANSWER_CACHE", "0") == "1"
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
        if self.HYBRID_RAG and os.getenv("KB_REINDEX_ON_BOOT", "0") == "1":
            try:
                stats = self._kb_index_all()
                self.logger.info(f"[KB-IDX] boot reindex done: {sum(stats.values())} vectors")
            except Exception as e:
                self.logger.error(f"[KB-IDX] boot reindex fail: {e}")

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

        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        #self.client = openai
        client = OpenAI()

        print(dir(client.beta))           # içinde 'vector_stores' var mı?
        print(dir(client.vector_stores)) 
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
        if self.USE_ANSWER_CACHE:
            self.worker_thread = threading.Thread(target=self._background_db_writer, daemon=True)
            self.worker_thread.start()

        self.CACHE_EXPIRY_SECONDS = 43200
        
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
            self._ensure_vector_store_and_upload()
            self._enable_file_search_on_assistants()
        # --- SQL RAG vector store'u hazırla ---
        if self.USE_SQL_RAG:
            self.logger.info("[SQL-RAG] Initializing SQL vector store upload...")
            self._ensure_sql_vector_store_and_upload()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
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
        @self.app.route("/kb/reindex", methods=["POST"])
        def kb_reindex():
            if not self.HYBRID_RAG:
                return jsonify({"ok": False, "msg":"HYBRID_RAG kapalı"}), 400
            try:
                stats = self._kb_index_all()
                return jsonify({"ok": True, "inserted": stats, "total": int(sum(stats.values()))}), 200
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
        for m in MODELS:
            # ✅ kelime sınırlarıyla tam eşleşme (ör. fabia'nın, fabia’da)
            if re.search(rf"\b{m}\b", s):
                found.add(m)
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
        # BUNU _ask içinde, user_message/user_id alındıktan hemen sonra ekle:
        state = self.user_states.setdefault(user_id, {})
        state.setdefault("threads", {})
        state.setdefault("cmp_models", [])   # yeni: iki-model bağlamı

        
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
            self.user_states[user_id]["threads"] = {}
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

        word_count = len(corrected_message.strip().split())
        local_threshold = 1.0 if word_count < 5 else 0.9

        lower_corrected = corrected_message.lower().strip()
        is_image_req = (
            self.utils.is_image_request(corrected_message)
            or self._is_image_intent_local(corrected_message)
        )
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
            if self.USE_ANSWER_CACHE and not is_image_req and not skip_cache_for_price_all and not skip_cache_for_kac:
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
                        #time.sleep(1)
                        ans_bytes = cached_answer
                        if self._should_attach_site_link(corrected_message):
                            ans_bytes = self._with_site_link_appended(ans_bytes)

                        ans_bytes = self._sanitize_bytes(ans_bytes)  # (YENİ)
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
                    #time.sleep(1)
                    ans_bytes = cached_answer
                    if self._should_attach_site_link(corrected_message):
                        ans_bytes = self._with_site_link_appended(ans_bytes)

                    ans_bytes = self._sanitize_bytes(ans_bytes)  # (YENİ)
                    return self.app.response_class(ans_bytes, mimetype="text/plain")

                    

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

                self.user_states[user_id]["last_conversation_id"] = conversation_id
                self.user_states[user_id]["last_user_message"] = user_message
                self.user_states[user_id]["last_assistant_answer"] = full_answer
                if self.USE_ANSWER_CACHE and (not is_image_req and not is_non_sentence_short_reply(corrected_message) and not skip_cache_for_kac):
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
    

        
    def _ensure_thread(self, user_id: str, assistant_id: str, tool_resources: dict | None = None) -> str:
        threads = self.user_states[user_id].setdefault("threads", {})
        thread_id = threads.get(assistant_id)

        if not thread_id:
            if tool_resources:
                t = self.client.beta.threads.create(tool_resources=tool_resources)
            else:
                t = self.client.beta.threads.create()
            thread_id = t.id
            threads[assistant_id] = thread_id
        return thread_id
    def _yield_sql_rag_block(self, *, user_id: str, user_message: str):
        if getattr(self, "STRICT_SQL_ONLY", False):
            return

        """Her cevabın SONUNA 'SQL RAG' kısa bloğu ekler."""
        if not (self.USE_SQL_RAG and self.SQL_RAG_ALWAYS_ON):
            return
        if not getattr(self, "VECTOR_STORE_SQL_ID", ""):
            yield "\n<small>SQL RAG: kaynak havuzu bağlı değil.</small>".encode("utf-8")
            return
        assistant_id = (self.user_states.get(user_id, {}) or {}).get("assistant_id")
        if not assistant_id:
            return
        try:
            tr = {"file_search": {"vector_store_ids": [self.VECTOR_STORE_SQL_ID]}}
            hide_query = getattr(self, "SQL_RAG_HIDE_QUERY", True)
            instructions = (
                "Yalnızca file_search sonuçlarını kullan. "
                "ÇIKTI: 'SQL RAG' için 1–3 maddelik çok kısa özet ver. "
                "SQL sorgusunu YAZMA, kod bloğu KULLANMA. "
                "Kaynak adı/ID yazma."
            )
            if not hide_query:
                instructions = (
                    "Yalnızca file_search sonuçlarını kullan. "
                    "ÇIKTI: 1–3 maddelik kısa özet ve tek bir ```sql``` kod bloğu. "
                    "Kaynak adı/ID yazma."
                )
            rag_text = self._ask_assistant(
                user_id=user_id,
                assistant_id=assistant_id,
                content=user_message,
                timeout=35.0,
                instructions_override=instructions,
                ephemeral=True,
                tool_resources_override=tr
            ) or ""
            rag_text = rag_text.strip()
            if not rag_text:
                yield "\n<small>SQL RAG: bu soruyla eşleşen kayıt bulunamadı.</small>".encode("utf-8")
                return
            # Basit başlık ekleyip iletelim
            
                    # Sorguyu ve kaynak izlerini gizle
            if hide_query:
                rag_text = self._strip_code_fences(rag_text)
                rag_text = self._strip_source_mentions(rag_text)
            # Başlık + temiz metin
            yield ("\n\n<b>SQL RAG</b>\n" + rag_text + "\n").encode("utf-8")
        except Exception as e:
            self.logger.error(f"[SQL-RAG] summary failed: {e}")
            yield "\n<small>SQL RAG: hata oluştu.</small>".encode("utf-8")  
    def _ask_assistant(
        self,
        user_id: str,
        assistant_id: str,
        content: str,
        timeout: float = 60.0,
        instructions_override: str | None = None,
        ephemeral: bool = False,
        tool_resources_override: dict | None = None
        ) -> str:
        # File Search tool kaynaklarını belirle
        tr = tool_resources_override
        if tr is None and getattr(self, "USE_OPENAI_FILE_SEARCH", False) and getattr(self, "VECTOR_STORE_ID", ""):
            tr = {"file_search": {"vector_store_ids": [self.VECTOR_STORE_ID]}}

        # Thread seçimi
        if ephemeral:
            t = self.client.beta.threads.create(tool_resources=tr) if tr else self.client.beta.threads.create()
            thread_id = t.id
        else:
            thread_id = self._ensure_thread(user_id, assistant_id, tool_resources=tr)

        # Mesajı ekle
        self.client.beta.threads.messages.create(thread_id=thread_id, role="user", content=content)

        # Run oluştur
        run_kwargs = {"thread_id": thread_id, "assistant_id": assistant_id}
        if instructions_override:
            run_kwargs["instructions"] = instructions_override

        run = self.client.beta.threads.runs.create(**run_kwargs)

        # Bekleme
        start = time.time()
        while time.time() - start < timeout:
            run = self.client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run.status == "completed":
                break
            if run.status == "failed":
                raise RuntimeError(run.last_error["message"])
            #time.sleep(0.5)

        # Son mesajı al
        msgs = self.client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=5)
        for m in msgs.data:
            if m.role == "assistant":
                return m.content[0].text.value
        return "Yanıt bulunamadı."
    def _yield_rag_summary_block(self, user_id: str, user_message: str):
            """
            Her yanıta eklenen kısa 'Vector Store özeti' bloğunu üretir ve yield eder.
            Koşullar: RAG_SUMMARY_EVERY_ANSWER=1, USE_OPENAI_FILE_SEARCH=1, vector store & asistan mevcut.
            """
            if not getattr(self, "RAG_SUMMARY_EVERY_ANSWER", False):
                return
            try:
                if (self.user_states.get(user_id, {}) or {}).get("rag_head_delivered"):
                    return

                if not getattr(self, "RAG_SUMMARY_EVERY_ANSWER", False):
                    return
                if not getattr(self, "USE_OPENAI_FILE_SEARCH", False):
                    return
                if not getattr(self, "VECTOR_STORE_ID", ""):
                    return
                assistant_id = (self.user_states.get(user_id, {}) or {}).get("assistant_id")
                if not assistant_id:
                    return

                # Ephemeral thread -> her çağrıda file_search tool_resources garanti
                rag_text = self._ask_assistant(
                    user_id=user_id,
                    assistant_id=assistant_id,
                    content=user_message,
                    timeout=45.0,
                    instructions_override=(
                        "Yalnızca bağlı dosya araması (file_search) sonuçlarına dayanarak, "
                        "kullanıcının sorusunu 3–6 maddelik kısa bir özet halinde açıkla. "
                        "Madde biçimi: '- ' ile başlayan sade Markdown listesi. "
                        "Varsayım yapma; emin değilsen kısaca belirt. "
                        "Tablo, görsel veya kod bloğu üretme; sadece kısa özet yaz. "
                        "Türkçe yaz. "
                        "Kesinlikle kaynak/citation/dosya adı/URL veya belge kimliği yazma."
                    ),
                    ephemeral=True
                ) or ""

                out_md = self.markdown_processor.transform_text_to_markdown(rag_text)
                if '|' in out_md and '\n' in out_md:
                    out_md = fix_markdown_table(out_md)
                block = "\n\n\n\n" + out_md.strip() + "\n"
                yield block.encode("utf-8")
            except Exception as e:
                self.logger.error(f"[RAG-SUMMARY] failed: {e}")
                return
    ##############################################################################
# ChatbotAPI._generate_response
##############################################################################
    def _generate_response(self, user_message: str, user_id: str, username: str = ""):
    # ------------------------------------------------------------------
    #  ROTA / MESAFE SORGUSU
    # ------------------------------------------------------------------
        # ---  YAKIT (benzin/dizel) SORUSU  ------------------------------------
        # === SKODA-ONLY GUARD ==============================================
        # _ask veya _generate_response başında, düzeltmelerden sonra:
        #if self._mentions_non_skoda(corrected_message):
         #   return self.app.response_class("Üzgünüm sadece Skoda hakkında bilgi verebilirim.", mimetype="text/plain")
        # --- SQL-RAG: her soruda devrede ---
        # --- normalize & basit çıkarımlar (ilk satırlara koy) ---
        # --- normalize & çıkarımlar ---
    # --- normalize & çıkarımlar (EN BAŞTA) ---
        q = normalize_tr_text(user_message or "").lower()
        lower_msg = (user_message or "").lower()
                # Donanım / özellik / var mı / opsiyonel niyetini erken tespit et
        equip_words = [
            "donanım", "donanim",
            "standart", "opsiyonel",
            "özellik", "ozellik",
            "paket", "var mı", "varmi", "bulunuyor mu"
        ]
        equip_intent = any(w in lower_msg for w in equip_words)

        # Teknik / performans metriklerini tespit et (0-100, tork, güç, menzil, vs.)
        requested_specs = self._find_requested_specs(user_message) if hasattr(self, "_find_requested_specs") else []
        has_teknik_trigger = any(
            kw in lower_msg
            for kw in getattr(self, "TEKNIK_TRIGGERS", [])
        )
        is_spec_intent = bool(requested_specs or has_teknik_trigger)

        trims_in_msg = extract_trims(lower_msg)
        self.CURRENT_TRIM_HINT = next(iter(trims_in_msg), None)

        # 🔹 1) Modeli bul
        models_in_msg0 = list(self._extract_models(user_message))
        model_for_equip = models_in_msg0[0] if models_in_msg0 else None

        # 🔹 2) Donanım niyeti (var mı / donanım / özellik / opsiyonel)
        equip_like_strict = any(w in lower_msg for w in [
            "donanım", "donanim",
            "özellik", "ozellik",
            "var mı", "varmi",
            "bulunuyor mu",
            "opsiyonel"
        ])

        if equip_like_strict and model_for_equip and not trims_in_msg:
            rows = self._query_all_features_from_imported(model_for_equip, user_message, topn=1)

            if rows:
                compact = self._render_feature_hits_compact(rows)
                if "|" in compact and "\n" in compact:
                    compact = fix_markdown_table(compact)
                yield compact.encode("utf-8")
                return   # ✅ Imported_* içinde net eşleşme varsa erken çık

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
        if is_spec_intent and not equip_like_early:
            models_in_msg = list(self._extract_models(user_message))
            picked_model = models_in_msg[0] if models_in_msg else None
            


            # 1) Önce kullanıcının yazdığı model
            if picked_model:
                val = self._generic_spec_from_sql(picked_model, q)
                if val:
                    title = "Değer"
                    if "tork" in q: title = "Tork"
                    elif any(k in q for k in ["güç","guc","beygir","hp","ps","power","kw"]): title = "Güç"
                    elif re.search(r"\b0\s*[-–—]?\s*100\b", q): title = "0-100"
                    elif any(k in q for k in ["maks","max speed","top speed","hız","hiz"]): title = "Maksimum hız"
                    elif "co2" in q or "emisyon" in q: title = "CO₂"
                    elif any(k in q for k in ["tüketim","tuketim","l/100","lt/100"]): title = "Birleşik tüketim"
                    elif "menzil" in q or "range" in q: title = "Menzil (WLTP)"

                    yield self._emit_spec_sentence(picked_model, title, val)
                    return

                # Bu soru teknik, ama bu model için değer yok → başka modele bakma
                # (donanım soruları zaten equip bloğuna düşüyor)
                # Teknik için hiç değer bulunmadıysa buradan sessizce devam etsin
            else:
                # 2) Hiç model yazılmadıysa: önce bağlamdaki model(ler), sonra tüm modeller
                last_models_ctx = list(self.user_states.get(user_id, {}).get("last_models", []))
                probe_models = last_models_ctx or [
                    "fabia","scala","kamiq","karoq","kodiaq",
                    "octavia","superb","enyaq","elroq"
                ]
                for m in probe_models:
                    val = self._generic_spec_from_sql(m, q)
                    if val:
                        yield self._emit_spec_sentence(m, "Değer", val)
                        # bağlam güncelle
                        self.user_states.setdefault(user_id, {}).setdefault("last_models", set()).add(m)
                        return
        # --- TEKNİK BLOK SONU ---


            # Model yazıldı ama değer bulunamadıysa diğer modellere bakma
            yield f"{picked_model.title()} için bu metrik veritabanında bulunamadı.".encode("utf-8")
            return
        if is_spec_intent:
        # 🚨 Eğer kullanıcı model yazmadıysa o zaman fallback devreye girsin
            last_models = list(self.user_states.get(user_id, {}).get("last_models", []))
            probe_models = last_models or ["fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"]
            for m in probe_models:
                val = self._generic_spec_from_sql(m, q)
                if val:
                    yield self._emit_spec_sentence(m, "Değer", val)
                    return

            yield "Bu metrik için veri bulunamadı."
            return
        

        q = normalize_tr_text(user_message or "").lower()
        models_in_msg0 = list(self._extract_models(user_message))
        model = models_in_msg0[0] if models_in_msg0 else None

        
            # 3) Genel metrik yakalama (tork/güç/0-100/co2/menzil vb.)
        val = None
        if model:
            val = self._generic_spec_from_sql(model, q)
            if val:
                picked_model = model
        else:
            for m in ["fabia","scala","kamiq","karoq","kodiaq","octavia","superb","enyaq","elroq"]:
                val = self._generic_spec_from_sql(m, q)
                if val:
                    picked_model = m
                    break
        if val:
            # Sorudan kısa bir başlık çıkaralım
            title = "Değer"
            if "tork" in q: title = "Tork"
            elif "güç" in q or "beygir" in q or "power" in q: title = "Güç"
            elif "0-100" in q or re.search(r"\b0\s*[-–—]?\s*100\b", q): title = "0-100"
            elif "maks" in q and "hız" in q: title = "Maksimum hız"
            elif "co2" in q: title = "CO₂"
            elif "tüketim" in q or "l/100" in q: title = "Birleşik tüketim"
            elif "menzil" in q: title = "Menzil (WLTP)"

            yield self._emit_spec_sentence(model, title, val)
            return


        if getattr(self, "SQL_RAG_ALWAYS_ON", False):
            rag_bytes = self._answer_with_sql_rag(user_message, user_id)
            if rag_bytes:
                # İsterseniz RAG'i ÖNCE gösterip sonra eski görsel/teknik akışa devam etmek için
                # aşağıdaki 'return'ı kaldırın. Her durumda "her yanıtta RAG" şartı sağlanmış olur.
                if self.SQL_RAG_SHORT_CIRCUIT:
                    yield rag_bytes
                    return
                else:
                    # yine de ekranda göstermek istiyorsan göster; ama akış devam etsin
                    yield rag_bytes
        corrected_message = user_message
        if self._mentions_non_skoda(user_message):
            # Tam olarak istenen cümle (ek link/ekstra metin yok)
            yield "Üzgünüm sadece Skoda hakkında bilgi verebilirim".encode("utf-8")
            return
# ===================================================================

        
        self.logger.info(f"[_generate_response] Kullanıcı ({user_id}): {user_message}")
    # <<< YENİ: Bu turda RAG cevabı üst blokta gösterildi mi?
        self.user_states.setdefault(user_id, {})["rag_head_delivered"] = False
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
        # -- Erken: kıyas niyetini hemen hesapla (ilk kullanım bundan sonra!)
        compare_keywords = ["karşılaştır", "karşılaştırma", "kıyas", "kıyasla", "kıyaslama", "vs", "vs."]
        wants_compare = any(ck in lower_msg for ck in compare_keywords)

        is_image_req_early = (
        self.utils.is_image_request(lower_msg) or
        self._is_image_intent_local(lower_msg) or
        ("renk" in lower_msg)  # renk(ler) isteklerini de görsel sayalım
        )
        # Yeni mesaj "opsiyonel" demiyorsa opsiyonel bekleme modunu temizle
        if "opsiyonel" not in lower_msg:
            self.user_states.setdefault(user_id, {})["pending_opsiyonel_model"] = None

        price_intent = self._is_price_intent(user_message)
        # -- Erken niyet tespiti --
        user_trims_in_msg = extract_trims(lower_msg)            # trim yakalayıcı (premium, prestige, rs, e sportline 60 vb.)
        pairs_all = extract_model_trim_pairs(lower_msg)         # (model, trim) çiftleri
        pairs_with_trim = [(m, (t or "").strip()) for (m, t) in pairs_all if (t or "").strip()]

        # 🔴 Model+trim kıyası -> RAG öncelikli
        if getattr(self, "RAG_FOR_MODEL_TRIM_COMPARE", True) and wants_compare:
            # A) Metinde en az iki adet (model,trim) çifti varsa
            if len(pairs_with_trim) >= 2:
                yield self._answer_via_rag_compare(
                    user_id=user_id,
                    assistant_id=assistant_id,
                    user_message=user_message,
                    pairs=pairs_with_trim
                )
                # opsiyon: RAG başlık bayrağı
                self.user_states[user_id]["rag_head_delivered"] = True
                return

            # B) Tek model adı + en az iki trim yazılmışsa (örn. "Octavia Premium ve Prestige")
            models_in_msg = list(self._extract_models(user_message))
            if len(models_in_msg) == 1 and len(user_trims_in_msg) >= 2:
                pairs_alt = [(models_in_msg[0], t) for t in user_trims_in_msg]
                yield self._answer_via_rag_compare(
                    user_id=user_id,
                    assistant_id=assistant_id,
                    user_message=user_message,
                    pairs=pairs_alt
                )
                self.user_states[user_id]["rag_head_delivered"] = True
                return

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

        # Eğer model + trim birlikteyse ve teknik kıyaslama değilse tablo gösterme → RAG cevabı getir
        if has_model_and_trim and not has_teknik_compare:
            assistant_id = self.user_states[user_id].get("assistant_id")
            if assistant_id:
                yield self._answer_via_rag_only(
                    user_id=user_id,
                    assistant_id=assistant_id,
                    user_message=user_message
                )
                return

        if price_intent:  # ← ESKİ: if "fiyat" in lower_msg:
            yield from self._yield_fiyat_listesi(user_message, user_id=user_id)
            return

        if any(kw in lower_msg for kw in ["teknik özellik", "teknik veriler", "teknik tablo", "teknik"]) \
            or wants_compare:
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
            # Örnek: "Kodiaq head up display var mı?"
            models = list(self._extract_models(user_message))
            model = models[0] if models else self._resolve_display_model(user_id).lower()
            trims, status_map = self._feature_lookup_any(model, user_message)

            if trims and status_map:
                # Trim sütunlarında dönen S/O/— kodlarını okunur hale getir
                def pretty_status(code: str | None) -> str:
                    if code == "S":
                        return "Standart"
                    if code == "O":
                        return "Opsiyonel"
                    return "Yok"

                #feature_name = self._norm_alias(user_message).title()
                canon_key, disp = canonicalize_feature(user_message)
                norm_q    = normalize_tr_text(user_message).lower().strip()
                norm_disp = normalize_tr_text(disp).lower().strip()

                if (not disp) or (norm_disp == norm_q):
                    # Eşleştiremediysek generic isim ver (soru asla yazılmasın)
                    feature_name = "Sorgulanan donanım"
                else:
                    feature_name = disp
                header = ["Donanım"] + [t.title() for t in trims]
                lines = [
                    "| " + " | ".join(header) + " |",
                    "|" + "|".join(["---"] * len(header)) + "|",
                    "| " + feature_name + " | " + " | ".join(pretty_status(status_map.get(t)) for t in trims) + " |",
                ]
                md = "\n".join(lines)
                md = fix_markdown_table(md)

                # 1) Tabloyu gönder
                #yield md.encode("utf-8")
                yield (md + "\n\n<br><br>").encode("utf-8")
                # 2) Altına OpenAI cümlesi ekle
                try:
                    sent = self._nlg_equipment_status(
                        model_name=model,
                        feature=feature_name,
                        trims=trims,
                        status_map=status_map,
                    )
                except Exception:
                    sent = ""

                if sent:
                    # Tablo ile cümle arasında biraz boşluk bırak
                    yield (sent + "\n").encode("utf-8")

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
                              # <- donanım niyeti şart
            and not has_teknik_word 
            and not requested_specs 
            and not is_image_req_early):
            # Sıralı model listesi (cümlede geçtiği sıraya göre)
            pairs_for_order = extract_model_trim_pairs(lower_msg)
            ordered_models = [m for m, _ in pairs_for_order]

            # Eğer extract_model_trim_pairs() hiçbir şey bulamadıysa, fallback olarak doğrudan extract_models() çıktısını kullan
            if not ordered_models:
                ordered_models = list(self._extract_models(user_message))

            # Son kontrol: 2'den fazla model varsa ilk ikiyi al (Fabia & Kamiq gibi)
            if len(ordered_models) > 2:
                ordered_models = ordered_models[:2]

            import inspect, logging
            f = self._build_equipment_comparison_table_from_sql
            logging.warning("EQUIP builder signature: %s | from: %s",
                            inspect.signature(f),
                            f.__code__.co_filename)

            # 2+ model varsa kıyasla
            if len(ordered_models) >= 2:
                only = self._detect_equipment_filter_keywords(lower_msg)  # "sadece jant, far" gibi
                trim_in_msg = next(iter(extract_trims(lower_msg)), None)
                import inspect  # dosyanın en üstünde varsa tekrar eklemene gerek yok

                params = dict(models=ordered_models, only_keywords=(only or None))
                if "trim" in inspect.signature(self._build_equipment_comparison_table_from_sql).parameters:
                    params["trim"] = trim_in_msg

                md = self._build_equipment_comparison_table_from_sql(**params)

                if md:
                    title = " vs ".join([m.title() for m in ordered_models])
                    yield f"<b>{title} — Donanım Karşılaştırması (DB)</b><br>".encode("utf-8")
                    yield (md + "\n\n").encode("utf-8")

                    # Kullanıcı deneyimi: hızlı ekleme linkleri
                    others = [m for m in self.MODEL_VALID_TRIMS.keys() if m not in ordered_models]
                    if others:
                        links = "<b>Karşılaştırmaya ekle:</b><br>"
                        for m in others:
                            cmd = (" ".join(ordered_models) + f" ve {m} donanım karşılaştırması").strip()
                            safe_cmd = cmd.replace("'", "\\'")
                            links += f"""&bull; <a href="#" onclick="sendMessage('{safe_cmd}');return false;">{m.title()}</a><br>"""
                        yield links.encode("utf-8")
                    return
                else:
                    yield "Karşılaştırma için uygun donanım tablosu veritabanında bulunamadı.<br>".encode("utf-8")
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
        if getattr(self, "RAG_ONLY", False) and generic_info_intent:
            assistant_id = self.user_states[user_id].get("assistant_id")
            yield self._answer_via_rag_only(user_id=user_id, assistant_id=assistant_id, user_message=user_message)
            return

        # --- SQL-ONLY muhafaza: hiçbir SQL cevabı bulunamadıysa net mesaj ver ---
        if getattr(self, "STRICT_SQL_ONLY", False):
            yield b"DB: kayit bulunamadi."
            return

        # === 7.A) GENEL SORU → ÖNCE RAG (Vector Store) İLE YANITLA ===
        # === 7.A) GENEL SORU → ÖNCE RAG (Vector Store) İLE YANITLA ===
        # Yeni:
        if self.USE_OPENAI_FILE_SEARCH and assistant_id and generic_info_intent and self.PREFER_RAG_TEXT:
            rag_out = self._ask_assistant(
                user_id=user_id,
                assistant_id=assistant_id,
                content=user_message,
                timeout=60.0,
                instructions_override=(
                    "Cevabı yalnızca bağlı dosya araması (file_search) kaynaklarına dayanarak hazırla. "
                    "ÖZET YAZMA. Detaylı ve tutarlı, kesin ifadeler kullan. Kararsız/örtülü dil kullanma. "
                    "Sadece ilgili model(ler) için yaz; başka modelleri dahil etme."
                ),
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
        if self.HYBRID_RAG:
            # Teknik/opsiyonel/fiyat/görsel olmayan "genel" sorularda kullan
            generic_info_intent = not (
                price_intent or "opsiyonel" in lower_msg or is_image_req
                or any(kw in lower_msg for kw in ["teknik özellik","teknik veriler","teknik tablo","performans"])
                or wants_compare
            )
            if generic_info_intent:
                ans = self._answer_with_hybrid_rag(user_message)
                if ans:
                    # güvenli teslim (tabloysa hizala)
                    out_md = self.markdown_processor.transform_text_to_markdown(ans)
                    if '|' in out_md and '\n' in out_md:
                        out_md = fix_markdown_table(out_md)
                    yield self._deliver_locally(out_md, original_user_message=user_message, user_id=user_id)
                    return


        # (Bridge boş dönerse normal '8) OpenAI API' yerel akışınıza düşsün.)

        # 8) Eğer buraya geldiysek => OpenAI API'ye gidilecek
        # 8) Eğer buraya geldiysek => OpenAI API'ye gidilecek
        if getattr(self, "RAG_ONLY", False):
            # RAG_ONLY modunda generik OpenAI yanıtı devre dışı
            yield self._with_site_link_appended("Bu konuda SQL tabanlı bilgi tabanımda kayıt yok.\n")
            return

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
                    # [YENİ] Teslim etmeden önce dosya ile kıyas + karar
                    final_bytes = self._apply_file_validation_and_route(
                        user_id=user_id,
                        user_message=user_message,
                        ai_answer_text=content_md
                    )
                    yield final_bytes
                    break

                elif run.status == "failed":
                    yield self._with_site_link_appended("Yanıt oluşturulamadı.\n")
                    return
                #time.sleep(0.5)

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
        self.logger.info("ChatbotAPI shutdown complete.")  