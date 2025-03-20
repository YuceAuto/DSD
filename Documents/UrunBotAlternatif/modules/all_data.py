# modules/fabia_data.py

FABIA_PREMIUM_MD = """\
| Parça Kodu | ŠKODA FABIA PREMIUM OPSİYONEL DONANIMLAR                                                      | MY 2024 Yetkili Satıcı Net Satış Fiyatı (TL) | MY 2024 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) |
|------------|------------------------------------------------------------------------------------------------|----------------------------------------------|--------------------------------------------------------------|
| Exc        | Exclusive Renkler                                                                             | 13,889                                       | 30,000                                                       |
| Met        | Metalik Renkler                                                                               | 9,259                                        | 20,000                                                       |
| 9S0        | 10,25" Dijital Gösterge Paneli                                                                | 13,889                                       | 30,000                                                       |
| PE4        | Sürücü Diz Hava Yastığı & Arka Yan Hava Yastıkları                                            | 16,204                                       | 35,000                                                       |
| PJ9        | 17" Procyon Mat Gri Zeminli Aero Kapaklı Alüminyum Alaşımlı Jantlar                           | 11,574                                       | 25,000                                                       |
| PJF        | 18" Libra Siyah Zeminli Alüminyum Alaşımlı Jantlar                                           | 23,148                                       | 50,000                                                       |
| PLC        | F1 Şanzıman                                                                                   | 4,630                                        | 10,000                                                       |
| PU2        | Şarj Paketi (5 adet USB-C Girişi + Kablosuz Şarj Ünitesi)                                     | 4,630                                        | 10,000                                                       |
| PUF        | Sürüş Asistan Paketi Exclusive (Akıllı Adaptif Hız Sabitleyici & Şerit Değiştirme Asistanı & Şeritte Tutma Asistanı)  | 27,778  | 60,000 |
| PUN        | Görüş Paketi (Uzun Far Asistanı & AFS Özellikli Full LED Ön Far Grubu)                        | 27,778                                       | 60,000                                                       |
| WQ8        | Dynamic İç Döşeme Paketi                                                                      | 16,204                                       | 35,000                                                       |
"""

FABIA_MONTE_CARLO_MD = """\
| Parça Kodu | ŠKODA FABIA MONTE CARLO OPSİYONEL DONANIMLAR                                                  | MY 2024 Yetkili Satıcı Net Satış Fiyatı (TL) | MY 2024 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) |
|------------|----------------------------------------------------------------------------------------------|----------------------------------------------|--------------------------------------------------------------|
| Exc        | Exclusive Renkler                                                                            | 13,889                                       | 30,000                                                       |
| Met        | Metalik Renkler                                                                              | 9,259                                        | 20,000                                                       |
| PE4        | Sürücü Diz Hava Yastığı & Arka Yan Hava Yastıkları                                           | 16,204                                       | 35,000                                                       |
| PJF        | 18" Libra Siyah Zeminli Alüminyum Alaşım Jantlar                                            | 11,574                                       | 25,000                                                       |
| PLM        | 3 Kollu, Fonksiyonel, Isıtmalı Spor Deri Direksiyon Simidi (F1 Şanzıman ile)                 | 3,531                                        | 7,500                                                        |
| PU3        | Sürüş Asistan Paketi Exclusive (Akıllı Adaptif Hız Sabitleyici & Şerit Değiştirme Asistanı & Şeritte Tutma Asistanı) | 27,778 | 60,000 |
| PUC        | Otomatik Park Pilotu                                                                         | 9,259                                        | 20,000                                                       |
| PUH        | Kış Paketi Exclusive (Isıtmalı Ön Koltuklar & Seviye Sensörlü 3 Litrelik Cam Suyu Deposu)<br><br>(**Not**: PLM - Isıtmalı Deri Direksiyon Simidi ile birlikte alınmalıdır.) | 20,833 | 45,000 |
"""


# ------------------------------------------------------------------
# (3) GENİŞ "DONANIM LİSTESİ" + "TEKNİK VERİLER" vb.
# ------------------------------------------------------------------
FABIA_DONANIM_LISTESI = """\
## ŠKODA FABIA MY 2024 DONANIM LİSTESİ (48. Üretim Haftası İtibariyle)

### PREMIUM / MONTE CARLO

#### Güvenlik
- Sürücü ve ön yolcu hava yastıkları → S, S
- Sürücü ve ön yolcu yan ve perde hava yastıkları → S, S
- Ön yolcu hava yastığı iptali → S, S
- Arkada üç noktadan bağlı emniyet kemerleri (Üç yolcu için) → S, S
- Sürücü ve ön yolcu için emniyet kemeri uyarısı → S, S
- Ön / arka disk frenler → S, S
- Yaya algılama özellikli ön bölge frenleme asistanı → S, S
- Şerit takip sistemi → S, S
- Sürücü yorgunluk tespit sistemi → S, S
- Çoklu çarpışma freni → S, S
- E-Call - Acil durum çağrı sistemi → S, S
- Yokuş kalkış sistemi → S, S
- Elektronik stabilite kontrol sistemi (ESC) → S, S
- Direksiyon yönlendirme tavsiyesi (DSR) → S, S
- Kaza sırasında yakıt akışını kesme sistemi → S, S
- Lastik basınç kontrol sistemi → S, S
- ISOFIX - çocuk koltuğu sabitleme özelliği → S, S
- Ön sis farları → -, S
- Köşe dönüş özellikli ön sis farları → S, -
- Bi-LED ön far grubu → S, -
- AFS özellikli Full LED ön far grubu → -, S
- Uzun far asistanı → -, S

#### Konfor ve Teknoloji
- Start & Stop sistemi → S, S
- Anahtarsız giriş ve çalıştırma sistemi (KESSY FULL) → S, S
- Hız sınırlayıcı → S, S
- Hız sabitleyici → S, S
- Geri görüş kamerası → S, S
- Görsel destekli ön ve arka park mesafe sensörü → S, S
- Manevra frenleme fonksiyonu → S, S
- 8'' Dijital gösterge paneli → S, -
- 10,25'' Dijital gösterge paneli → -, S
- 8.25" Dokunmatik multimedya sistemi → S, S
- Kablosuz SmartLink (Apple CarPlay & Android Auto) → S, S
- 2 adet USB-C girişi (önde) → S, -
- 5 adet USB-C girişi (2 önde, 2 arkada, 1 dikiz aynasında) → -, S
- Kablosuz şarj ünitesi → -, S
- ŠKODA Surround ses sistemi (6 hoparlör) → S, S
- Bluetooth → S, S
- Sürüş modu yönetimi → S, S
- Far sensörü (Eve geliş, evden çıkış, tünele giriş, gündüz lambası) → S, S
- Yağmur sensörü → S, S
- Elektrikli, ısıtmalı, otomatik katlanabilen yan aynalar → S, S
- Otomatik kararan iç dikiz aynası → S, S
- Aircare özellikli çift bölgeli tam otomatik klima → S, S
- Arka havalandırma çıkışları → S, S
- Uzaktan kumandalı merkezi kilit sistemi → S, S
- Elektro-mekanik takviyeli, çok fonksiyonlu direksiyon simidi → S, S
- 2 kollu, deri direksiyon simidi → S, -
- 3 kollu, Monte Carlo logolu, perfore deri, spor direksiyon simidi → -, S
- F1 şanzıman → -, S
- Deri kaplı vites topuzu ve el freni → S, S
- Ön kol dayama ünitesi → S, S
- Kumaş koltuk döşemeleri → S, -
- Monte Carlo kırmızı ve gri dikişli, karbon fiber detaylı spor koltuk döşemeleri → -, S
- Yükseklik ayarlı sürücü ve ön yolcu koltuğu → S, S
- Bel destek ayarlı sürücü ve ön yolcu koltuğu → S, S
- Asimetrik katlanabilen arka koltuk sırtlıkları → S, S
- Yer tasarruflu stepne → S, S
- Gözlük saklama kabı → S, S
- Buz kazıyıcı → S, S
- Sürücü kapısı içinde şemsiye → S, S

#### Tasarım
- 16'' Proxima gümüş renkli alüminyum alaşımlı jantlar → S, -
- 17'' Procyon siyah zeminli alüminyum alaşımlı jantlar → -, S
- LED gündüz sürüş farları → S, S
- LED arka aydınlatma grubu → S, S
- Karartılmış arka camlar → S, S
- Ambiyans aydınlatma (Kırmızı ve beyaz renk) → S, S
- Krom cam çerçeveleri → S, -
- Siyah cam çerçeveleri → -, S
- Krom çerçeveli ön ızgara → S, -
- Siyah çerçeveli ön ızgara → -, S
- Gövde renginde dış dikiz aynaları → S, -
- Siyah renkli dış dikiz aynaları → -, S
- Krom kaplama iç kapı açma kolları → S, S
- Siyah tavan döşemesi → -, S
- Siyah spoiler → -, S
- Bagaj kapağında krom "Škoda" ve "Fabia" yazısı → S, -
- Bagaj kapağında siyah "Škoda" ve "Fabia" yazısı → -, S
- Siyah arka tampon difüzörü → -, S
- Çelik pedallar → -, S

---

### STANDART VE OPSİYONEL JANT SEÇENEKLERİ
- **PJ4 - PROXIMA 6J x 16" (195/55/16)**  
  Premium için standart alüminyum jant seçeneği

- **PJ9 - PROCYON AERO 6J x 17" (215/45/17), Mat Gri Zeminli**  
  Premium için opsiyonel alüminyum jant seçeneği

- **PJE - PROCYON 7J x 17" (215/45/17), Siyah Zeminli, Elmas Kesim**  
  Monte Carlo için standart alüminyum jant seçeneği

- **PJF - LIBRA 7J x 18" (215/40/18), Siyah Zeminli, Elmas Kesim**  
  Premium ve Monte Carlo için opsiyonel alüminyum jant seçeneği

---

### RENK SEÇENEKLERİ

**PREMIUM RENKLER**  
- **METALİK**: Phoenix Turuncu (2X2X), Yarış Mavisi (8X8X), Gümüş (8E8E), Büyülü Siyah (1Z1Z), Graphite Gri (5X5X)  
- **EXCLUSIVE**: Kadife Kırmızısı (K1K1), Ay Beyazı (2Y2Y)

**MONTE CARLO RENKLER**  
- Aynı metalik / exclusive renkler + siyah tavan (örnek kodlar 2X1Z, 2Y1Z, K11Z, vb.)

---

### MULTİMEDYA SİSTEMİ
- 8.25" Multimedya Sistemi (Tüm donanım seviyeleri için standart)

### DİREKSİYON SEÇENEKLERİ
- 2 kollu deri direksiyon (Premium için standart)
- 3 kollu, Monte Carlo logolu, perfore deri, spor direksiyon (Monte Carlo için standart)

### GÖSTERGE PANELLERİ
- 8'' Dijital Gösterge Paneli (Premium için standart)
- 10,25'' Dijital Gösterge Paneli (Monte Carlo için standart)

---

## TEKNİK VERİLER

| Özellik                                         | Fabia Premium 1.0 TSI 115 PS DSG | Fabia Monte Carlo 1.5 TSI 150 PS DSG |
|-------------------------------------------------|----------------------------------|--------------------------------------|
| Silindir Sayısı                                 | 3                                | 4                                    |
| Silindir Hacmi (cc)                             | 999                              | 1498                                 |
| Çap / Strok (mm)                                | 74,5 x 76,4                      | 74,5 x 85,9                          |
| Maks. güç [kW (PS) / dev/dak]                   | 85 (115) / 5.500                 | 110 (150) / 5.000 - 6.000            |
| Maks. tork [Nm / dev/dak]                       | 200 / 2.000 - 3.500             | 250 / 1.500 - 3.500                  |
| Maks. hız (km/h)                                | 202                              | 222                                  |
| İvmelenme (0-100 km/h)                          | 9.7                              | 8.0                                  |
| Düşük Faz (lt / 100 km)                         | 6.8                              | 7.4                                  |
| Orta Faz (lt / 100 km)                          | 5.1                              | 5.6                                  |
| Yüksek Faz (lt / 100 km)                        | 4.5                              | 4.7                                  |
| Ekstra Yüksek Faz (lt / 100 km)                 | 5.4                              | 5.6                                  |
| Birleşik (lt / 100 km)                          | 5,2 - 5,7                        | 5,4 - 5,8                            |
| CO2 Emisyonu (g/km)                             | 118 - 125                        | 123 - 132                            |
| Uzunluk / Genişlik / Yükseklik (mm)             | 4108 / 1780 / 1463               | 4125 / 1780 / 1464                   |
| Dingil mesafesi (mm)                            | 2552                             | 2551                                 |
| Bagaj hacmi (dm3)                               | 380 / 1190                       | 380 / 1190                           |
| Lastikler                                       | 195/55 R16                       | 215 / 45 R17                         |
| Ağırlık (Sürücü Dahil) (kg)                     | 1195 - 1336                      | 1238 - 1364                          |

---
"""


# Bu dosyayı opsiyonel tabloları Markdown olarak tutmak için ekliyoruz.
# Aşağıdaki üç değişken (SCALA_ELITE_MD, SCALA_PREMIUM_MD, SCALA_MONTE_CARLO_MD)
# Kod içinde chatbot, kullanıcıdan gelen "scala opsiyonel ... elite/premium/monte carlo" 
# anahtar kelimelerinde yakalayıp direkt bu string'leri döndürür.

SCALA_ELITE_MD = """\
| Parça Kodu | ŠKODA SCALA ELITE OPSİYONEL DONANIMLAR                                                           | MY 2024 Yetkili Satıcı Net Satış Fiyatı (TL) | MY 2024 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) |
|------------|---------------------------------------------------------------------------------------------------|----------------------------------------------|--------------------------------------------------------------|
| Exc        | Exclusive Renkler                                                                                | 13,889                                       | 30,000                                                       |
| Met        | Metalik Renkler                                                                                  | 9,259                                        | 20,000                                                       |
| P11        | Akıllı Çözümler Paketi (Bagaj bölmesindeki sabitleme montaj aparatı, vs...)                      | 11,574                                       | 25,000                                                       |
| PJ7        | 16" Montado Aero Siyah Zeminli Alüminyum Alaşımlı Jantlar                                       | 9,259                                        | 20,000                                                       |
| PJG        | 17" Kajam Aero Kapaklı Alüminyum Alaşım Jantlar                                                 | 13,889                                       | 30,000                                                       |
| PJP        | 17" Stratos Alüminyum Alaşım Jantlar                                                            | 11,574                                       | 25,000                                                       |
| WIC        | Kış Paketi (Isıtmalı Ön Koltuklar & Seviye Sensörlü 3 Litrelik Cam Suyu Deposu)                  | 16,204                                       | 35,000                                                       |
| WIH        | Konfor Paketi (Otomatik Kararan İç Dikiz Aynası & Otomatik Katlanabilen Yan Aynalar & ... )      | 25,463                                       | 55,000                                                       |
"""

SCALA_PREMIUM_MD = """\
| Parça Kodu | ŠKODA SCALA PREMIUM OPSİYONEL DONANIMLAR                                                         | MY 2024 Yetkili Satıcı Net Satış Fiyatı (TL) | MY 2024 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) |
|------------|-------------------------------------------------------------------------------------------------|----------------------------------------------|--------------------------------------------------------------|
| Exc        | Exclusive Renkler                                                                              | 13,889                                       | 30,000                                                       |
| Met        | Metalik Renkler                                                                                | 9,259                                        | 20,000                                                       |
| P13        | Akıllı Çözümler Paketi (... )                                                                  | 11,574                                       | 25,000                                                       |
| PIA        | Sürüş Asistan Paketi (Akıllı Adaptif Hız Sabitleyici & Şeritte Tutma Asistanı)                 | 27,778                                       | 60,000                                                       |
| PJ7        | 16" Montado Siyah Zeminli Aero Kapaklı Alüminyum Alaşımlı Jantlar                              | 9,259                                        | 20,000                                                       |
| PJG        | 17" Kajam Aero Gümüş Zeminli Alüminyum Alaşım Jantlar                                         | 13,889                                       | 30,000                                                       |
| PJN        | 18" Fornax Alüminyum Alaşım Jantlar                                                            | 11,574                                       | 25,000                                                       |
| PLG        | 2 kollu, ısıtmalı, deri direksiyon simidi (F1 şanzıman ile)                                    | 3,472                                        | 7,500                                                        |
| WI2        | Kış Paketi Exclusive (Isıtmalı Ön Koltuklar & Seviye Sensörlü 3 Litrelik Cam Suyu Deposu)      | 16,204                                       | 35,000                                                       |
| WIN        | Teknoloji Plus Paketi (Elektrikli Bagaj Kapağı & Sanal Pedal & 10.25" Dijital Gösterge Paneli) | 16,204                                       | 35,000                                                       |
| WIV        | Panoramik Cam Tavan                                                                            | 32,407                                       | 70,000                                                       |
| WIX        | Sürücü Diz Hava Yastığı & Arka Yan Hava Yastıkları                                             | 16,204                                       | 35,000                                                       |
| WV7        | Suite Black Paketi (Süet/Alcantara Döşeme & ... )                                             | 46,296                                       | 100,000                                                      |
| WY1        | FULL LED Matrix Ön Far Grubu                                                                    | 30,093                                       | 65,000                                                       |
"""

SCALA_MONTE_CARLO_MD = """\
| Parça Kodu | ŠKODA SCALA MONTE CARLO OPSİYONEL DONANIMLAR                                                     | MY 2024 Yetkili Satıcı Net Satış Fiyatı (TL) | MY 2024 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) |
|------------|-------------------------------------------------------------------------------------------------|----------------------------------------------|--------------------------------------------------------------|
| Exc        | Exclusive Renkler                                                                              | 13,889                                       | 30,000                                                       |
| Met        | Metalik Renkler                                                                                | 9,259                                        | 20,000                                                       |
| P13        | Akıllı Çözümler Paketi (... )                                                                  | 9,259                                        | 20,000                                                       |
| PIB        | Sürüş Asistan Paketi Exclusive (Akıllı Adaptif Hız Sabitleyici & Şerit Değiştirme Asistanı)    | 27,778                                       | 60,000                                                       |
| PLT        | 3 kollu, Monte Carlo logolu, perforé deri, ısıtmalı, spor direksiyon simidi (F1 şanzıman ile)  | 34,472                                       | 7,500                                                        |
| PWA        | Elektrikli Sürücü Koltuğu & Elektrikli Bel Desteği                                             | 16,204                                       | 35,000                                                       |
| WI2        | Kış Paketi Exclusive (Isıtmalı Ön Koltuklar & Seviye Sensörlü 3 Litrelik Cam Suyu Deposu)      | 16,204                                       | 35,000                                                       |
| W10        | Otomatik Park Pilotu                                                                           | 9,259                                        | 20,000                                                       |
| WIX        | Sürücü Diz Hava Yastığı & Arka Yan Hava Yastıkları                                             | 16,204                                       | 35,000                                                       |
"""

# ------------------------------------------------------------------
# (4) GENİŞ "DONANIM LİSTESİ" + "TEKNİK VERİLER" vb.
# ------------------------------------------------------------------
SCALA_DONANIM_LISTESI = """\
## ŠKODA SCALA MY 2024 DONANIM LİSTESİ (48. Üretim Haftası İtibariyle)

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
- LED ön sis farları → S, -, -
- Köşe dönüş özellikli LED ön sis farları → -, S, S
- Bi-LED ön far grubu → S, S, -
- Full LED Matrix ön far grubu → -, -, S

#### Konfor ve Teknoloji
- Start & Stop sistemi → S, S, S
- Anahtarsız giriş ve çalıştırma sistemi (KESSY FULL) → -, S, S
- Hız sınırlayıcı → S, S, S
- Hız sabitleyici → S, S, S
- Geri görüş kamerası → -, S, S
- Görsel destekli ön / arka park sensörleri → (Ön: -, S, S) / (Arka: S, S, S)
- Manevra frenleme fonksiyonu → S, S, S
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
- Elektrikli bagaj kapağı & Sanal Pedal → -, -, S
- Far sensörü (Eve geliş, evden çıkış, tünele giriş, gündüz lambası) → S, S, S
- Yağmur sensörü → -, S, S
- Elektrikli, ısıtmalı yan aynalar → S, S, S
- Otomatik katlanabilen yan aynalar → -, S, S
- Otomatik kararan iç dikiz aynası → -, S, S
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
- Monte Carlo kırmızı ve gri dikişli spor koltuk döşemeleri → -, -, S
- Yükseklik ayarlı sürücü ve ön yolcu koltuğu → S, S, S
- Bel destek ayarlı ön koltuklar → -, S, S
- Asimetrik katlanabilen arka koltuk sırtlıkları → S, S, S
- Yer tasarruflu stepne → S, S, S
- Gözlük saklama kabı (Panoramik cam tavan ile sunulmamaktadır.) → -, S, -
- Buz kazıyıcı → S, S, S
- Şemsiye → S, S, S

#### Tasarım
- 16'' Cortadero Aero alüminyum alaşım jantlar → S, S, -
- 18'' Ursa siyah zeminli alüminyum alaşımlı jantlar → -, -, S
- LED gündüz sürüş farları → S, S, S
- LED arka aydınlatma grubu → S, -, -
- TOP LED arka aydınlatma grubu → -, S, S
- 3D dinamik arka sinyal lambaları → -, S, S
- Karartılmış arka camlar → -, S, S
- Ambiyans aydınlatma (Kırmızı & beyaz) → -, S, S
- Panoramik cam tavan → -, -, S
- Uzatılmış arka cam → -, S, S
- Krom çerçeveli ön ızgara → S, S, -
- Siyah çerçeveli ön ızgara → -, -, S
- Gövde renginde dış dikiz aynaları → S, S, -
- Siyah renkli dış dikiz aynaları → -, -, S
- Krom kaplama iç kapı açma kolları → S, S, S
- Siyah tavan döşemesi (Panoramik cam tavan varsa siyah) → -, -, S
- Gövde rengi arka spoyler → -, S, -
- Siyah renkli arka spoyler → -, -, S
- Bagaj kapağında krom "Škoda" ve "Scala" yazısı → S, S, -
- Bagaj kapağında siyah "Škoda" ve "Scala" yazısı → -, -, S
- Ön çamurlukta "Monte Carlo" logosu → -, -, S
- Çelik pedallar → -, -, S

---

### STANDART VE OPSİYONEL JANT SEÇENEKLERİ
- **PJ5 / P02 - CORTADERO 6JX16" (205/55/16)**  
  Elite ve Premium için standart jant

- **PJ7 - MONTADO AERO - Siyah Zeminli 6JX16" (205/55/16)**  
  Elite & 1.0 Premium için opsiyonel

- **PJP - STRATOS 6,5JX17" (205/50/17)**  
  Elite & Premium için opsiyonel

- **PJG - KAJAM AERO - Gümüş Zeminli 6,5JX17" (205/50/17)**  
  Elite & Premium için opsiyonel

- **PJN - FORNAX 7JX18" (205/45/18)**  
  Premium için opsiyonel

- **PJI - URSA - Siyah Zeminli 7JX18" (205/45/18)**  
  Monte Carlo için standart

---

### RENK SEÇENEKLERİ

**EXCLUSIVE RENKLER**  
- Kadife Kırmızısı (K1K1)
- Ay Beyazı (2Y2Y)

**METALİK RENKLER**  
- Yarış Mavisi (8X8X)
- Gümüş (8E8E)
- Çelik Gri (M3M3)
- Büyülü Siyah (1Z1Z)
- Graptihe Gri (5X5X)

---

### MULTİMEDYA SİSTEMİ
- 8.25" Multimedya Sistemi (Tüm donanımlarda standart)

### GÖSTERGE PANELLERİ
- 8" Dijital Gösterge Paneli (Elite & Premium için standart)
- 10.25'' Dijital Gösterge Paneli (Monte Carlo için standart)

### DİREKSİYON SEÇENEKLERİ
- 2 kollu deri direksiyon (Elite & Premium için standart)
- 3 kollu Monte Carlo logolu, perfore deri, ısıtmalı, spor direksiyon (Monte Carlo için standart)

---

## TEKNİK VERİLER

| Özellik                                        | Scala Elite 1.0 TSI 115 PS DSG | Scala Premium 1.0 TSI 115 PS DSG | Scala Premium 1.5 TSI 150 PS DSG | Scala Monte Carlo 1.5 TSI 150 PS DSG |
|------------------------------------------------|--------------------------------|----------------------------------|----------------------------------|--------------------------------------|
| Silindir Sayısı                                | 3                              | 3                                | 4                                | 4                                    |
| Silindir Hacmi (cc)                            | 999                            | 999                              | 1498                             | 1498                                 |
| Maks. güç [PS / dev/dak]                       | 115 / 5500                     | 115 / 5500                       | 150 / 5000 - 6000                | 150 / 5000 - 6000                    |
| Maks. tork [Nm / dev/dak]                      | 200 / 2000 - 3500              | 200 / 2000 - 3500                | 250 / 1500 - 3500                | 250 / 1500 - 3500                    |
| Maks. hız (km/h)                               | 202                            | 202                              | 220                              | 220                                  |
| İvmelenme (0-100 km/h)                         | 10.1                           | 10.1                             | 8.2                               | 8.2                                   |
| Birleşik (l / 100 km)                          | 5,4 - 5,8                      | 5,4 - 5,8                        | 5,6 - 6,1                        | 5,6 - 6,1                            |
| CO2 emisyonu (g/km)                            | 123 - 130                      | 123 - 130                        | 127 - 137                        | 127 - 137                            |
| Uzunluk/Genişlik/Yükseklik (mm)                | 4362 / 1793 / 1493             | 4362 / 1793 / 1493               | 4362 / 1793 / 1494               | 4362 / 1793 / 1494                   |
| Dingil mesafesi (mm)                           | 2636                           | 2636                             | 2636                             | 2636                                 |
| Bagaj hacmi (dm3)                              | 467 / 1410                     | 467 / 1410                       | 467 / 1410                       | 467 / 1410                           |
| Ağırlık (Sürücü Dahil) (kg)                    | 1237 - 1409                    | 1237 - 1409                      | 1271 - 1430                      | 1271 - 1430                          |

---
"""


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