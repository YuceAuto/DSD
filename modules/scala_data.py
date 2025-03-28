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

