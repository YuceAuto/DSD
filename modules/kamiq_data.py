# modules/kamiq_data.py

KAMIQ_ELITE_MD = """\
| Parça Kodu | ŠKODA KAMIQ ELITE OPSİYONEL DONANIMLAR                                                                                          | MY 2024 Yetkili Satıcı Net Satış Fiyatı (TL) | MY 2024 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) |
|------------|--------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------|--------------------------------------------------------------|
| Exc        | Exclusive Renkler                                                                                                              | 13,889                                       | 30,000                                                       |
| Met        | Metalik Renkler                                                                                                                | 9,259                                        | 20,000                                                       |
| P1         | Akıllı Çözümler Paketi (Bagaj bölmesindeki sabitleme montaj aparatı, Bagaj altında file ve çok fonksiyonlu cep, Kapı koruyucu,<br>Çöp Kutusu, Bagaj filesi, Bagaj bölmesi paspası) | 11,574 | 25,000 |
| PJ7        | 16" Montado Siyah Zeminli Aero Kapaklı Alüminyum Alaşımlı Jantlar                                                              | 9,259                                        | 20,000                                                       |
| PJG        | 17" Kajam Aero gümüş zeminli alüminyum alaşım jantlar                                                                          | 13,889                                       | 30,000                                                       |
| PJP        | 17" Stratos Alüminyum Alaşım Jantlar                                                                                           | 11,574                                       | 25,000                                                       |
| WIC        | Kış Paketi (Isıtmalı Ön Koltuklar & Seviye Sensörlü 3 Litrelik Cam Suyu Deposu)                                                | 16,204                                       | 35,000                                                       |
"""

KAMIQ_PREMIUM_MD = """\
| Parça Kodu | ŠKODA KAMIQ PREMIUM OPSİYONEL DONANIMLAR                                                                                       | MY 2024 Yetkili Satıcı Net Satış Fiyatı (TL) | MY 2024 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) |
|------------|-------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------|--------------------------------------------------------------|
| Exc        | Exclusive Renkler                                                                                                            | 13,889                                       | 30,000                                                       |
| Met        | Metalik Renkler                                                                                                              | 9,259                                        | 20,000                                                       |
| P13        | Akıllı Çözümler Paketi (Bagaj bölmesindeki sabitleme montaj aparatı, Bagaj altında file ve çok fonksiyonlu cep, Kapı koruyucu,<br>Çöp Kutusu, Bagaj filesi, Bagaj bölmesi paspası) | 11,574 | 25,000 |
| PIA        | Sürüş Asistan Paketi (Akıllı Adaptif Hız Sabitleyici & Şeritte Tutma Asistanı)                                               | 27,778                                       | 60,000                                                       |
| PJN        | 18" Fornax Alüminyum Alaşım Jantlar                                                                                           | 11,574                                       | 25,000                                                       |
| PJP        | 17" Stratos Alüminyum Alaşım Jantlar                                                                                         | 11,574                                       | 25,000                                                       |
| PLG        | 2 kollu, ısıtmalı, deri direksiyon simidi (F1 şanzıman ile)                                                                  | 3,472                                        | 7,500                                                        |
| WI2        | Kış Paketi Exclusive (Isıtmalı Ön Koltuklar & Seviye Sensörlü 3 Litrelik Cam Suyu Deposu)<br><br>(**Not**: PLG – Isıtmalı Deri Direksiyon Simidi ile birlikte alınmalıdır.) | 16,204 | 35,000 |
| WIN        | Teknoloji Plus Paketi (Elektrikli Bagaj Kapağı & Sanal Pedal & 10.25" Dijital Gösterge Paneli)                               | 30,093                                       | 65,000                                                       |
| WIV        | Panoramik Cam Tavan                                                                                                          | 32,407                                       | 70,000                                                       |
| WIX        | Sürücü Diz Hava Yastığı & Arka Yan Hava Yastıkları                                                                           | 16,204                                       | 35,000                                                       |
| WY7        | Suite Black Paketi (Süedia Döşeme + Isıtmalı Ön Koltuk ve Isıtmalı Ön Cam Suyu Püskürtücü + Elektrikli Sürücü Koltuğu<br>ve Elektrikli Bel Desteği) | 46,296 | 100,000 |
| WY1        | FULL LED Matrix Ön Far Grubu                                                                                                  | 30,093                                       | 65,000                                                       |
"""

KAMIQ_MONTE_CARLO_MD = """\
| Parça Kodu | ŠKODA KAMIQ MONTE CARLO OPSİYONEL DONANIMLAR                                                                                  | MY 2024 Yetkili Satıcı Net Satış Fiyatı (TL) | MY 2024 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) |
|------------|------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------|--------------------------------------------------------------|
| Exc        | Exclusive Renkler                                                                                                           | 13,889                                       | 30,000                                                       |
| Met        | Metalik Renkler                                                                                                             | 9,259                                        | 20,000                                                       |
| P13        | Akıllı Çözümler Paketi (Bagaj bölmesindeki sabitleme montaj aparatı, Bagaj altında file ve çok fonksiyonlu cep,<br>Kapı koruyucu, Çöp Kutusu, Bagaj filesi, Bagaj bölmesi paspası) | 9,259 | 20,000 |
| PIB        | Sürüş Asistan Paketi Exclusive (Akıllı Adaptif Hız Sabitleyici & Şerit Değiştirme Asistanı & Şeritte Tutma Asistanı)         | 27,778                                       | 60,000                                                       |
| PLT        | 3 kollu, Monte Carlo logolu, perforé deri, ısıtmalı, spor direksiyon simidi (F1 şanzıman ile)                               | 3,472                                        | 7,500                                                        |
| PWA        | Elektrikli Sürücü Koltuğu & Elektrikli Bel Desteği                                                                          | 16,204                                       | 35,000                                                       |
| WI2        | Kış Paketi Exclusive (Isıtmalı Ön Koltuklar & Seviye Sensörlü 3 Litrelik Cam Suyu Deposu)<br><br>(**Not**: PLT – Isıtmalı Deri Direksiyon Simidi ile birlikte alınmalıdır.) | 16,204 | 35,000 |
| WIX        | Sürücü Diz Hava Yastığı & Arka Yan Hava Yastıkları                                                                          | 16,204                                       | 35,000                                                       |
"""
