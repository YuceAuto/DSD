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
