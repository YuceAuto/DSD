# modules/kamiq_data.py

"""
Bu dosyada, Kamiq ile ilgili opsiyonel donanım tabloları ve
MY 2024 donanım listesi + teknik veriler gibi bilgileri
Markdown formatında tutuyoruz.

Kullanıcı "kamiq opsiyonel" dediğinde chatbot.py -> 
yield KAMIQ_ELITE_MD (veya PREMIUM vb.) gönderebilir.

Geniş "SKODA KAMIQ MY 2024 DONANIM LİSTESİ" ve "Teknik Veriler" 
metinlerini, KAMIQ_DONANIM_LISTESI gibi bir değişkende 
saklayabiliriz (opsiyonel).
"""

# ------------------------------------------------------------------
# (1) KAMIQ ELITE OPSİYONEL TABLOSU
# ------------------------------------------------------------------
KAMIQ_ELITE_MD = """\
**ŠKODA KAMIQ ELITE OPSİYONEL DONANIMLAR**

| Kod  | Açıklama                                                                                                                                                                                                                                                                         | MY 2024 Yetkili Satıcı Net Satış Fiyatı (TL) | MY 2024 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) |
|------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------|------------------------------------------------------------|
| Exc  | Exclusive Renkler                                                                                                                                                                                                                                                               | 13,889                                      | 30,000                                                     |
| Met  | Metalik Renkler                                                                                                                                                                                                                                                                 | 9,259                                       | 20,000                                                     |
| PI1  | Akıllı Çözümler Paketi (Bagaj bölmesindeki sabitleme montaj aparatı, Bagaj altında file ve çok fonksiyonlu cep, Kapı koruyucu, Çöp Kutusu, Bagaj filesi, Bagaj bölmesi paspası çift taraflı (kauçuk/kumaş), Bagaj tarafında 12 volt priz, Kül tablası, Multimedya tutucusu, Braket, Saklama bölmesi paketi) | 11,574 | 25,000 |
| PJ7  | 16" Montado Siyah Zeminli Aero Kapaklı Alüminyum Alaşımlı Jantlar                                                                                                                                                                                                               | 9,259                                       | 20,000                                                     |
| PJG  | 17" Kajam Aero gümüş zeminli alüminyum alaşım jantlar                                                                                                                                                                                                                           | 13,889                                      | 30,000                                                     |
| PJP  | 17'' Stratos Alüminyum Alaşım Jantlar                                                                                                                                                                                                                                           | 13,889                                      | 30,000                                                     |
| WIC  | Kış Paketi (Isıtmalı Ön Koltuklar & Seviye Sensörlü 3 Litrelik Cam Suyu Deposu)                                                                                                                                                                                                  | 16,204                                      | 35,000                                                     |
"""

# ------------------------------------------------------------------
# (2) KAMIQ PREMIUM OPSİYONEL TABLOSU
# ------------------------------------------------------------------
KAMIQ_PREMIUM_MD = """\
**ŠKODA KAMIQ PREMIUM OPSİYONEL DONANIMLAR**

| Kod  | Açıklama                                                                                                                                                                                                                                            | MY 2024 Yetkili Satıcı Net Satış Fiyatı (TL) | MY 2024 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) |
|------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------|------------------------------------------------------------|
| Exc  | Exclusive Renkler                                                                                                                                                                                                                                   | 13,889                                      | 30,000                                                     |
| Met  | Metalik Renkler                                                                                                                                                                                                                                     | 9,259                                       | 20,000                                                     |
| PI3  | Akıllı Çözümler Paketi (Bagaj bölmesindeki sabitleme montaj aparatı, Bagaj altında file ve çok fonksiyonlu cep, Kapı koruyucu, Çöp Kutusu, Bagaj filesi, Bagaj bölmesi paspası çift taraflı (kauçuk/kumaş), Bagaj tarafında 12 volt priz, Kül tablası, Multimedya tutucusu, Braket, Saklama bölmesi paketi) | 11,574 | 25,000 |
| PIA  | Sürüş Asistan Paketi (Akıllı Adaptif Hız Sabitleyici & Şeritte Tutma Asistanı)                                                                                                                                                                     | 27,778                                      | 60,000                                                     |
| PJN  | 18'' Fornax Alüminyum Alaşım Jantlar                                                                                                                                                                                                                | 11,574                                      | 25,000                                                     |
| PJP  | 17'' Stratos Alüminyum Alaşım Jantlar                                                                                                                                                                                                               | -                                           | -                                                          |
| PLG  | 2 kollu, ısıtmalı, deri direksiyon simidi (F1 şanzıman ile)                                                                                                                                                                                         | 3,472                                       | 7,500                                                      |
| WI2  | Kış Paketi Exclusive (Isıtmalı Ön Koltuklar & Seviye Sensörlü 3 Litrelik Cam Suyu Deposu) (**Not**: PLG - Isıtmalı Deri Direksiyon Simidi ile birlikte alınmalıdır.)                                                                                 | 16,204                                      | 35,000                                                     |
| WIN  | Teknoloji Plus Paketi (Elektrikli Bagaj Kapağı & Sanal Pedal & 10.25'' Dijital Gösterge Paneli)                                                                                                                                                     | 30,093                                      | 65,000                                                     |
| WIW  | Panoramik Cam Tavan                                                                                                                                                                                                                                 | 32,407                                      | 70,000                                                     |
| WIX  | Sürücü Diz Hava Yastığı & Arka Yan Hava Yastıkları                                                                                                                                                                                                  | 16,204                                      | 35,000                                                     |
| WQ7  | Suite Black Paketi (Suedia Döşeme + Isıtmalı Ön Koltuk ve Isıtmalı Ön Cam Suyu Püskürtücü + Elektrikli Sürücü Koltuğu ve Elektrikli Bel Desteği)                                                                                                     | 46,296                                      | 100,000                                                    |
| WYI  | FULL LED Matrix Ön Far Grubu                                                                                                                                                                                                                        | 30,093                                      | 65,000                                                     |
"""

# ------------------------------------------------------------------
# (3) KAMIQ MONTE CARLO OPSİYONEL TABLOSU
# ------------------------------------------------------------------
KAMIQ_MONTE_CARLO_MD = """\
**ŠKODA KAMIQ MONTE CARLO OPSİYONEL DONANIMLAR**

| Kod  | Açıklama                                                                                                                                                                                                                                                      | MY 2024 Yetkili Satıcı Net Satış Fiyatı (TL) | MY 2024 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) |
|------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------|------------------------------------------------------------|
| Exc  | Exclusive Renkler                                                                                                                                                                                                                                             | 13,889                                      | 30,000                                                     |
| Met  | Metalik Renkler                                                                                                                                                                                                                                               | 9,259                                       | 20,000                                                     |
| PI3  | Akıllı Çözümler Paketi (Bagaj bölmesindeki sabitleme montaj aparatı, Bagaj altında file ve çok fonksiyonlu cep, Kapı koruyucu, Çöp Kutusu, Bagaj filesi, Bagaj bölmesi paspası çift taraflı (kauçuk/kumaş), Bagaj tarafında 12 volt priz, Kül tablası, Multimedya tutucusu, Braket, Saklama bölmesi paketi) | 11,574 | 25,000 |
| PIB  | Sürüş Asistan Paketi Exclusive (Akıllı Adaptif Hız Sabitleyici & Şerit Değiştirme Asistanı & Şeritte Tutma Asistanı)                                                                                                                                          | 27,778                                      | 60,000                                                     |
| PLT  | 3 kollu, Monte Carlo logolu, perfore deri, ısıtmalı, spor direksiyon simidi (F1 şanzıman ile)                                                                                                                                                                | 3,472                                       | 7,500                                                      |
| PWA  | Elektrikli Sürücü Koltuğu & Elektrikli Bel Desteği                                                                                                                                                                                                           | 16,204                                      | 35,000                                                     |
| WI2  | Kış Paketi Exclusive (Isıtmalı Ön Koltuklar & Seviye Sensörlü 3 Litrelik Cam Suyu Deposu) (**Not**: PLT - Isıtmalı Deri Direksiyon Simidi ile birlikte alınmalıdır.)                                                                                          | 16,204                                      | 35,000                                                     |
| WIX  | Sürücü Diz Hava Yastığı & Arka Yan Hava Yastıkları                                                                                                                                                                                                           | 16,204                                      | 35,000                                                     |
"""

# ------------------------------------------------------------------
# (4) GENİŞ "DONANIM LİSTESİ" + "TEKNİK VERİLER" vb.
#     (İsteğe bağlı tek büyük Markdown string)
# ------------------------------------------------------------------
KAMIQ_DONANIM_LISTESI = """\
## SKODA KAMIQ MY 2024 DONANIM LİSTESİ (48. Üretim Haftası İtibariyle)

### ELITE / PREMIUM / MONTE CARLO

#### Güvenlik
- Sürücü ve ön yolcu hava yastıkları → S, S, S
- Sürücü ve ön yolcu yan ve perde hava yastıkları → S, S, S
- Ön yolcu hava yastığı iptali → S, S, S
- Arkada üç noktadan bağlı emniyet kemerleri (Üç yolcu için) → S, S, S
- Ön ve arka koltuklar için emniyet kemeri uyarısı → S, S, S
- Ön / arka disk frenler → S, S, S
- Yaya algılama özellikli ön bölge frenleme asistanı → S, S, S
- Şerit takip sistemi → S, S, S
- Sürücü yorgunluk tespit sistemi → S, S, S
- Çoklu çarpışma freni → S, S, S
- E-Call - Acil durum çağrı sistemi → S, S, S
- Yokuş kalkış sistemi → S, S, S
- Elektronik stabilite kontrol sistemi (ESC) → S, S, S
- Direksiyon yönlendirme tavsiyesi (DSR) → S, S, S
- Kaza sırasında yakıt akışını kesme sistemi → S, S, S
- Lastik basınç kontrol sistemi → S, S, S
- ISOFIX - çocuk koltuğu sabitleme özelliği → S, S, S
- Köşe dönüş özellikli LED ön sis farları → S, S, S
- Bi-LED ön far grubu → S, S, -
- Full LED Matrix ön far grubu & Dinamik sinyal lambaları → -, -, S

#### Konfor ve Teknoloji
- Start & Stop sistemi → S, S, S
- Anahtarsız giriş ve çalıştırma sistemi (KESSY FULL) → -, S, S
- Hız sınırlayıcı → S, S, S
- Hız sabitleyici → S, S, S
- Geri görüş kamerası → -, S, S
- Görsel destekli ön park mesafe sensörü → -, S, S
- Görsel destekli arka park mesafe sensörü → S, S, S
- Manevra frenleme fonksiyonu → S, S, S
- Otomatik park pilotu → -, -, S
- 8" Dijital gösterge paneli → S, S, -
- 10.25'' Dijital gösterge paneli → -, -, S
- 8.25" Dokunmatik multimedya sistemi → S, S, S
- Kablosuz SmartLink (Apple CarPlay & Android Auto) → S, S, S
- 4 adet USB-C girişi (2 önde, 2 arkada) → S, -, -
- 5 adet USB-C girişi (2 önde, 2 arkada, 1 dikiz aynasında) → -, S, S
- Kablosuz şarj ünitesi → -, S, S
- 8 adet hoparlör → S, S, S
- Bluetooth → S, S, S
- Sürüş modu yönetimi → -, S, S

#### Diğer Donanımlar
- Elektrikli bagaj kapağı → -, -, S
- Sanal pedal → -, -, S
- Far sensörü (Eve geliş, evden çıkış, tünele giriş, gündüz lambası) → S, S, S
- Yağmur sensörü → S, S, S
- Elektrikli, ısıtmalı, otomatik katlanabilen yan aynalar → S, S, S
- Otomatik kararan iç dikiz aynası → S, S, S
- Klima (manuel) → S, -, -
- Aircare özellikli çift bölgeli tam otomatik klima → -, S, S
- Arka havalandırma çıkışları → S, S, S
- Uzaktan kumandalı merkezi kilit sistemi → S, S, S
- Elektro-mekanik takviyeli, çok fonksiyonlu direksiyon simidi → S, S, S
- 2 kollu, deri direksiyon simidi → S, S, -
- 3 kollu, Monte Carlo logolu, perfore deri, spor direksiyon simidi → -, -, S
- F1 şanzıman → -, S, S
- Deri vites topuzu ve el freni → S, S, S
- Ön kol dayama ünitesi → S, S, S
- Arka kol dayama ünitesi → -, S, S
- Kumaş koltuk döşemeleri → S, -, -
- Kumaş & Suedia koltuk döşemeleri → -, S, -
- Monte Carlo kırmızı ve gri dikişli, karbon fiber detaylı spor koltuk döşemeleri → -, -, S
- Yükseklik ayarlı sürücü ve ön yolcu koltuğu → S, S, S
- Bel destek ayarlı sürücü ve ön yolcu koltuğu → -, S, S
- Asimetrik katlanabilen arka koltuk sırtlıkları → S, S, S
- Yer tasarruflu stepne → S, S, S
- Gözlük saklama kabı (Panoramik cam tavan ile sunulmamaktadır.) → -, S, -
- Buz kazıyıcı → S, S, S
- Şemsiye → S, S, S

#### Tasarım
- 16'' Cortadero Aero alüminyum alaşım jantlar → S, -, -
- 17" Kajam Aero gümüş zeminli alüminyum alaşım jantlar → -, S, -
- 18" Ursa siyah zeminli alüminyum alaşımlı jantlar → -, -, S
- LED gündüz sürüş farları → S, S, S
- TOP LED arka aydınlatma grubu → S, S, S
- 3D dinamik arka sinyal lambaları → S, S, S
- Karartılmış arka camlar → -, S, S
- Ambiyans aydınlatma (Kırmızı ve beyaz renk seçenekleriyle) → -, S, S
- Panoramik cam tavan → -, -, S
- Siyah tavan rayları → S, -, S
- Gümüş tavan rayları → -, S, -
- Krom cam çerçeveleri → -, S, -
- Siyah cam çerçeveleri → S, -, S
- Krom çerçeveli ön ızgara → S, S, -
- Siyah çerçeveli ön ızgara → -, -, S
- Gövde renginde dış dikiz aynaları → S, S, -
- Siyah renkli dış dikiz aynaları → -, -, S
- Krom kaplama iç kapı açma kolları → S, S, S
- Siyah tavan döşemesi (Panoramik cam tavan bulunan araçlarda siyah tavan döşemesi sunulmaktadır.) → -, -, S
- Bagaj kapağında krom "Škoda" ve "Kamiq" yazısı → S, S, -
- Bagaj kapağında siyah "Škoda" ve "Kamiq" yazısı → -, -, S
- Gümüş renkli skid-plate ön ve arka difüzör → -, S, -
- Siyah renkli skid-plate ön ve arka difüzör → S, -, S
- Ön çamurlukta "Monte Carlo" logosu → -, -, S
- Çelik pedallar → -, -, S

---

### STANDART VE OPSİYONEL JANT SEÇENEKLERİ
- **P02 - CORTADERO 6JX16" (205/60/16)**  
  Elite için standart jant seçeneği

- **PJ7 - MONTADO AERO - Siyah Zeminli 6JX16" (205/60/16)**  
  1.0 Elite için opsiyonel jant seçeneği

- **PJP - STRATOS 6,5JX17" (205/55/17)**  
  Elite & Premium için opsiyonel jant

- **PJG - KAJAM AERO - Gümüş Zeminli 6,5JX17" (205/55/17)**  
  Premium için standart / Elite için opsiyonel

- **PJN - FORNAX 7JX18" (215/45/18)**  
  Premium için opsiyonel jant

- **PJI - URSA - Siyah Zeminli 7JX18" (215/45/18)**  
  Monte Carlo için standart jant

---

### RENK SEÇENEKLERİ

**EXCLUSIVE RENKLER**  
- Kadife Kırmızısı (K1K1)
- Ay Beyazı (2Y2Y)

**METALİK RENKLER**  
- Phoenix Turuncu (2X2X)
- Yarış Mavisi (8X8X)
- Gümüş (8E8E)
- Büyülü Siyah (1Z1Z)
- Graptihe Gri (5X5X)  <-- Not: "Graptihe" aslında "Grafit" olarak düzeltilmeli.

---

### MULTİMEDYA SİSTEMİ
- 8.25" Multimedya Sistemi (Tüm donanımlarda standart)

### GÖSTERGE PANELLERİ
- 8" Dijital Gösterge Paneli (Elite & Premium için standart)
- 10.25'' Dijital Gösterge Paneli (Monte Carlo için standart)

---

## TEKNİK VERİLER

| Özellik                                         | Kamiq Elite 1.0 TSI 115 PS DSG | Kamiq Premium 1.0 TSI 115 PS DSG | Kamiq Premium 1.5 TSI 150 PS DSG | Kamiq Monte Carlo 1.5 TSI 150 PS DSG |
|-------------------------------------------------|--------------------------------|----------------------------------|----------------------------------|--------------------------------------|
| Silindir Sayısı                                 | 3                              | 3                                | 4                                | 4                                    |
| Silindir Hacmi (cc)                             | 999                            | 999                              | 1498                             | 1498                                 |
| Maks. güç [PS / dev/dak]                        | 115 / 5500                     | 115 / 5500                       | 150 / 5000 - 6000                | 150 / 5000 - 6000                    |
| Maks. tork [Nm / dev/dak]                       | 200 / 2000 - 3500              | 200 / 2000 - 3500                | 250 / 1500 - 3500                | 250 / 1500 - 3500                    |
| Maks. hız (km/h)                                | 195                            | 195                              | 213                              | 213                                  |
| İvmelenme (0-100 km/h)                          | 10.2                           | 10.2                             | 8.3                               | 8.3                                   |
| Birleşik (l / 100 km)                           | 5,6 - 5,9                      | 5,6 - 5,9                        | 5,7 - 6,1                        | 5,7 - 6,1                            |
| CO2 emisyonu (g/km)                             | 127 - 134                      | 127 - 134                        | 129 - 137                        | 129 - 137                            |
| Uzunluk/Genişlik/Yükseklik (mm)                 | 4241 / 1793 / 1562             | 4241 / 1793 / 1562               | 4241 / 1793 / 1562               | 4241 / 1793 / 1562                   |
| Dingil mesafesi (mm)                            | 2639                           | 2639                             | 2639                             | 2639                                 |
| Bagaj hacmi (dm3)                               | 400 / 1395                     | 400 / 1395                       | 400 / 1395                       | 400 / 1395                           |
| Ağırlık (Sürücü Dahil) (kg)                     | 1254 - 1417                    | 1254 - 1417                      | 1288 - 1443                      | 1288 - 1443                          |

---

### İKİNCİ PDF (KISMI TEKRAR)
**SKODA KAMIQ MY 2024 DONANIM LİSTESİ (48. Üretim Haftası İtibariyle) - İkinci PDF**

(Not: Buradaki veriler birinci PDF ile büyük ölçüde aynıdır, tekrarlanmıştır.)
- Güvenlik, konfor, opsiyonel paketler, teknik veriler vb. ilk tablolarla aynıdır.
"""