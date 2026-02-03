# modules/chat/nlu_config.py

# TÜM SKODA MODELLERİ (normalize edilmiş)
MODEL_LIST = [
    "fabia",
    "scala",
    "kamiq",
    "karoq",
    "kodiaq",
    "octavia",
    "superb",
    "enyaq",
    "elroq"
]

# MODEL → TRIM eşleşmesi
MODEL_TRIMS = {
    "fabia": ["premium", "monte carlo"],
    "scala": ["elite", "premium", "monte carlo"],
    "kamiq": ["elite", "premium", "monte carlo"],
    "karoq": ["premium", "prestige", "sportline"],
    "kodiaq": ["premium", "prestige", "sportline", "rs"],
    "octavia": ["elite", "premium", "prestige", "sportline", "rs"],
    "superb": ["premium", "prestige", "l&k crystal", "sportline phev"],
    "enyaq": ["e prestige 60", "coupe e sportline 60", "coupe e sportline 85x",
              "e sportline 60", "e sportline 85x"],
    "elroq": ["e prestige 60"]
}

# Trim için normalize edilmiş varyant eşleştirmeleri (opsiyonel, çok yararlı)
TRIM_SYNONYMS = {
    "montecarlo": "monte carlo",
    "mc": "monte carlo",
    "sportline": "sportline",
    "rs": "rs",
    "prestige": "prestige",
    "premium": "premium",
    "elite": "elite",
    "e prestige 60": "e prestige 60",
    "ep60": "e prestige 60",
}
TECH_KEYWORDS = [
    "yakıt tipi",
    "batarya kapasitesi",
    "brüt batarya",
    "net batarya",
    "maksimum güç",
    "maksimum hız",
    "wltp menzil",
    "menzil",
    "şarj süresi",
    "enerji tüketimi",
    "batarya tipi",
    "maksimum tork",
    "tork",
    "güç",
    "ivmelenme",
    "0-100",
    "şehir içi menzil",
    "co2",
    "emisyon",
    "uzunluk",
    "genişlik",
    "yükseklik",
    "uzunluk/genişlik/yükseklik",
    "dingil mesafesi",
    "yerden yükseklik",
    "bagaj hacmi",
    "lastik",
    "ağırlık",
    "dönüş çapı",
    "sürtünme katsayısı",
    "güç aktarımı"
]

TECH_SYNONYMS = {
   # === MENZİL ===
    "kaç km gider": "menzil",
    "kaç km yol": "menzil",
    "kaç km menzil": "menzil",
    "ne kadar gider": "menzil",
    "bir şarj kaç km": "menzil",
    "tek şarj kaç km": "menzil",
    "full şarj kaç km": "menzil",
    "tam şarj kaç km": "menzil",
    "şarj başına menzil": "menzil",
    "range": "menzil",
    "range nedir": "menzil",
    "menzil nedir": "menzil",
    "menzil kaç km": "menzil",
    "şehir dışı menzil": "menzil",
    "uzun yol menzili": "menzil",
    "yazın menzil": "menzil",
    "kışın menzil": "menzil",
    "menzili": "menzil",
    "400 km gider mi": "menzil",
    "500 km gider mi": "menzil",

    # === WLTP MENZİL ===
    "wltp": "wltp menzil",
    "wltp kaç km": "wltp menzil",
    "wltp range": "wltp menzil",
    "menzil kombine": "wltp menzil",
    "karma menzil": "wltp menzil",
    "kombine menzil": "wltp menzil",

    # === ŞEHİR İÇİ MENZİL ===
    "şehir içi menzil": "şehir içi menzil",
    "şehir içi kaç km": "şehir içi menzil",
    "şehir içi range": "şehir içi menzil",
    "şehir içi gider mi": "şehir içi menzil",
    "şehir içi kullanım menzili": "şehir içi menzil",
    "şehir içi ortalama": "şehir içi menzil",
    "şehir içi sürüş menzili": "şehir içi menzil",

    # === ŞARJ SÜRESİ ===
    "şarj süresi": "şarj süresi",
    "kaç saat şarj": "şarj süresi",
    "şarj kaç saat": "şarj süresi",
    "şarj kaç dakika": "şarj süresi",
    "şarj kaç dk": "şarj süresi",
    "%10 %80": "şarj süresi",
    "10-80": "şarj süresi",
    "10 80": "şarj süresi",
    "80e kadar kaç dk": "şarj süresi",
    "dc şarj": "şarj süresi",
    "ac şarj": "şarj süresi",
    "hızlı şarj": "şarj süresi",
    "supercharger": "şarj süresi",
    "evde şarj": "şarj süresi",
    "11kw şarj": "şarj süresi",
    "3.7kw şarj": "şarj süresi",

    # === BATARYA ===
    "batarya kapasitesi": "batarya kapasitesi",
    "kaç kwh": "batarya kapasitesi",
    "kwh": "batarya kapasitesi",
    "batarya kaç kwh": "batarya kapasitesi",
    "net batarya": "net batarya",
    "brüt batarya": "brüt batarya",
    "battery": "batarya kapasitesi",
    "battery capacity": "batarya kapasitesi",
    "akü": "batarya kapasitesi",
    "batarya tipi": "batarya tipi",

    # === 0-100 ===
    "0 100": "0-100",
    "0-100 hızlanma": "0-100",
    "0-100 kaç sn": "0-100",
    "0-100 kaç saniye": "0-100",
    "kaç saniyede hızlanıyor": "0-100",
    "ivme": "ivmelenme",
    "ivmesi": "ivmelenme",
    "ivmelenmesi": "ivmelenme",
    "hızlanması": "ivmelenme",

    # === MAKSİMUM HIZ ===
    "top speed": "maksimum hız",
    "maks hız": "maksimum hız",
    "en yüksek hız": "maksimum hız",
    "son hız": "maksimum hız",
    "kaç km hız": "maksimum hız",
    "max speed": "maksimum hız",
    "max kmh": "maksimum hız",

    # === GÜÇ (PS / HP / KW) ===
    "ps": "maksimum güç",
    "hp": "maksimum güç",
    "bg": "maksimum güç",
    "beygir": "maksimum güç",
    "kw": "maksimum güç",
    "motor gücü": "maksimum güç",
    "gücü kaç": "maksimum güç",
    "güç değeri": "maksimum güç",

    # === TORK ===
    "nm": "maksimum tork",
    "torku": "maksimum tork",
    "tork değeri": "maksimum tork",
    "kaç tork": "maksimum tork",

    # === BOYUTLAR ===
    "araç ölçüleri": "uzunluk/genişlik/yükseklik",
    "ölçüler": "uzunluk/genişlik/yükseklik",
    "ölçüleri": "uzunluk/genişlik/yükseklik",
    "boyutları": "uzunluk/genişlik/yükseklik",
    "uzunluğu": "uzunluk",
    "genişliği": "genişlik",
    "yüksekliği": "yükseklik",

    # === BAGAJ HACMİ ===
    "bagaj kaç litre": "bagaj hacmi",
    "kaç litre bagaj": "bagaj hacmi",
    "bagaj kapasitesi": "bagaj hacmi",
    "bagaj lt": "bagaj hacmi",
    "bagaj büyük mü": "bagaj hacmi",

    # === AĞIRLIK ===
    "kaç kilo": "ağırlık",
    "araç kaç kilo": "ağırlık",
    "kaç kg": "ağırlık",
    "boş ağırlık": "ağırlık",
    "dolu ağırlık": "ağırlık",

    # === DÖNÜŞ ÇAPI ===
    "dönüş çapı": "dönüş çapı",
    "manevra çapı": "dönüş çapı",
    "manevra yeteneği": "dönüş çapı",

    # === LASTİK / JANT ===
    "lastik ölçüsü": "lastik",
    "kaç inç lastik": "lastik",
    "jant ebatı": "lastik",

    # === CO2 ===
    "co2 emisyonu": "co2",
    "kaç co2": "co2",
    "emisyon nedir": "co2",

    # === GÜÇ AKTARIMI ===
    "çekiş sistemi": "güç aktarımı",
    "4x4": "güç aktarımı",
    "4wd": "güç aktarımı",
    "fwd": "güç aktarımı",
    "awd": "güç aktarımı",
}
EQUIP_SYNONYMS = {

    # -----------------------
    # HAVA YASTIĞI & EMNİYET
    # -----------------------
    "airbag": "hava yastıkları",
    "hava yastığı": "hava yastıkları",
    "hava yastiklari": "hava yastıkları",
    "ön hava yastığı": "hava yastıkları",
    "sürücü hava yastığı": "hava yastıkları",
    "yan hava yastığı": "yan hava yastıkları",
    "arka yan hava yastığı": "arka yan hava yastıkları",
    "perde hava yastığı": "perde hava yastıkları",
    "merkez hava yastığı": "merkez hava yastığı",
    "diz airbag": "diz hava yastığı",
    "yolcu airbag iptali": "ön yolcu hava yastığı iptali",
    "airbag kapama": "ön yolcu hava yastığı iptali",

    "emniyet kemeri uyarısı": "emniyet kemeri uyarısı",
    "kemer uyarısı": "emniyet kemeri uyarısı",

    "isofix": "isofix",
    "isofix bağlantısı": "isofix",
    "çocuk koltuğu sabitleme": "isofix",

    # -----------------------
    # SÜRÜŞ DESTEK SİSTEMLERİ
    # -----------------------
    "şerit takip": "şerit takip asistanı",
    "lane assist": "şerit takip asistanı",
    "şerit değiştir": "şerit değiştirme asistanı",
    "blind spot": "şerit değiştirme asistanı",
    "arka trafik uyarı": "arka trafik uyarı sistemi",
    "rear traffic alert": "arka trafik uyarı sistemi",
    "trafik asistanı": "trafik sıkışıklığı asistanı",
    "traffic jam": "trafik sıkışıklığı asistanı",

    "front assist": "ön bölge frenleme asistanı",
    "çarpışma önleme": "ön bölge frenleme asistanı",
    "yaya algılama": "ön bölge frenleme asistanı",

    "proaktif güvenlik": "genişletilmiş güvenlik sistemi",
    "acil durum yardım": "proaktif acil durum yardım sistemi",
    "yorgunluk tespit": "sürücü yorgunluk tespit sistemi",
    "dikkat uyarı": "sürücü yorgunluk tespit sistemi",

    "abs": "anti blokaj fren sistemi",
    "esp": "elektronik stabilite kontrol sistemi",
    "asr": "elektronik patinaj önleme sistemi",
    "edl": "elektronik diferansiyel kilidi",
    "xds": "elektronik diferansiyel dağıtıcısı",

    "multi collision": "çoklu çarpışma freni",
    "çarpışma freni": "çoklu çarpışma freni",

    "e-call": "acil çağrı sistemi",
    "acil çağrı": "acil çağrı sistemi",

    # -----------------------
    # AYDINLATMA & FARLAR
    # -----------------------
    "matrix far": "full led matrix ön far grubu",
    "led far": "full led matrix ön far grubu",
    "full led": "full led matrix ön far grubu",
    "led matrix": "full led matrix ön far grubu",
    "uzun far asistanı": "uzun far asistanı",
    "far asistanı": "dinamik far asistanı",

    "sis farı": "ön sis farları",
    "led gündüz farı": "led gündüz sürüş aydınlatmaları",
    "gündüz farı": "led gündüz sürüş aydınlatmaları",
    "dinamik sinyal": "3d dinamik arka sinyal lambaları",

    # -----------------------
    # MULTİMEDYA & EKRAN
    # -----------------------
    "multimedya": "bilgi eğlence sistemi",
    "ekran": "bilgi eğlence sistemi",
    "display": "bilgi eğlence sistemi",
    "carplay": "kablosuz smartlink",
    "android auto": "kablosuz smartlink",
    "smartlink": "kablosuz smartlink",
    "bluetooth": "bluetooth",
    "hoparlör": "hoparlör sistemi",
    "ses sistemi": "hoparlör sistemi",
    "canton": "canton ses sistemi",
    "hud": "head-up display",
    "head up": "head-up display",

    "geri görüş kamerası": "geri görüş kamerası",
    "arka kamera": "geri görüş kamerası",
    "360 kamera": "360 çevre görüş kamerası",

    # -----------------------
    # DİREKSİYON / KOLTUKLAR
    # -----------------------
    "ısıtmalı direksiyon": "ısıtmalı direksiyon simidi",
    "deri direksiyon": "deri direksiyon simidi",

    "koltuk ısıtma": "ısıtmalı ön koltuklar",
    "ısıtmalı koltuk": "ısıtmalı ön koltuklar",
    "arka koltuk ısıtma": "ısıtmalı arka koltuklar",

    "elektrikli koltuk": "elektrikli sürücü koltuğu",
    "elektrikli yolcu koltuğu": "elektrikli ön yolcu koltuğu",
    "hafızalı koltuk": "elektrikli sürücü koltuğu",

    "bel destek": "bel destek ayarlı ön koltuklar",
    "koltuk bel desteği": "bel destek ayarlı ön koltuklar",
    "masaj koltuk": "masaj fonksiyonlu ön koltuklar",

    "arka kol dayama": "arka kol dayama ünitesi",
    "ön kol dayama": "ön kol dayama ünitesi",

    # -----------------------
    # KONFOR & KLİMA
    # -----------------------
    "çift bölgeli klima": "çift bölgeli tam otomatik klima",
    "klimatronik": "çift bölgeli tam otomatik klima",
    "üç bölgeli klima": "üç bölgeli tam otomatik klima",
    "hava kalite sensörü": "aircare tam otomatik klima",
    "arka havalandırma": "arka havalandırma çıkışları",

    # -----------------------
    # BAGAJ / KAPAK / DEPOLAMA
    # -----------------------
    "elektrikli bagaj": "elektrikli bagaj kapağı",
    "sanal pedal": "sanal pedal",
    "bagaj aydınlatması": "bagaj bölmesi aydınlatması",
    "bagaj örtüsü": "bagaj bölmesi örtüsü",
    "bagaj bölmesi": "bagaj depolama bölmeleri",

    # -----------------------
    # KAPILAR & AYNALAR
    # -----------------------
    "katlanır ayna": "otomatik katlanabilir yan aynalar",
    "ısıtmalı ayna": "ısıtmalı yan aynalar",
    "elektrikli ayna": "elektrikli ayarlanabilir yan aynalar",

    "aydınlatmalı makyaj aynası": "makyaj aynalı güneşlik",
    "güneşlik ışığı": "makyaj aynalı güneşlik",

    # -----------------------
    # FAR & YAĞMUR SENSÖRLERİ
    # -----------------------
    "far sensörü": "far sensörü",
    "yağmur sensörü": "yağmur sensörü",

    # -----------------------
    # JANTLAR & DIŞ TASARIM
    # -----------------------
    "jant": "jantlar",
    "jantlar": "jantlar",
    "alaşım jant": "jantlar",
    "alüminyum jant": "jantlar",

    "spoiler": "arka spoiler",
    "arka spoyler": "arka spoiler",
    "krom detay": "krom detaylar",
    "siyah detay": "parlak siyah dış detaylar",

    # -----------------------
    # PARK & SENSÖRLER
    # -----------------------
    "park sensörü": "park mesafe sensörü",
    "ön park sensörü": "ön park sensörü",
    "arka park sensörü": "arka park sensörü",
    "otomatik park": "otomatik park pilotu",

    "manevra freni": "manevra frenleme fonksiyonu",

    # -----------------------
    # ŞARJ & KABLO
    # -----------------------
    "şarj kablosu": "şarj kablosu", 
    "ac şarj kablosu": "ac şarj kablosu",
    "dc kablo": "şarj kablosu",

    # -----------------------
    # SES & HOPARLÖR
    # -----------------------
    "hoparlör": "hoparlör sistemi",
    "ses sistemi": "hoparlör sistemi",
    "bass": "hoparlör sistemi",

}
