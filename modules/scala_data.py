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
