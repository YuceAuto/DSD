# modules/kodiaq_data.py
# -*- coding: utf-8 -*-
"""
ŠKODA KODIAQ MY2025 — Opsiyonel Donanımlar, Donanım Listesi, Jant/Döşeme/Renk ve Bilgi Eğlence
Bu dosya, Vector Store tarafından kolay taranabilen *tek bir Markdown dizesi* içerir.
- PDF’teki “S” kısaltmaları *tam yazıyla* “Standart” olarak normalleştirildi.
- Tablolar ve başlıklar PDF hiyerarşisiyle uyumludur.
"""

KODIAQ_DATA_MD = """\
# ŠKODA KODIAQ MY 2025

---

## Premium — Opsiyonel Donanımlar (Fiyat)

| Kod | Açıklama | Net Satış (TL) | Anahtar Teslim (%90 ÖTV) | Anahtar Teslim (%100 ÖTV) |
|-----|----------|---------------:|--------------------------:|--------------------------:|
| Met | Metalik Renkler | 20.833 | 47.500 | 50.000 |
| Exc | Exclusive Renkler | 27.778 | 63.333 | 66.667 |
| PAA | Assisted Drive (Adaptif Hız Sabitleyici & Şerit Takip **Plus** & Yarı Otonom Kontrol & Trafik Sıkışıklığı) | 55.556 | 126.667 | 133.333 |
| PJ0 | 18" **Mazeno** alüminyum alaşımlı **aero** jantlar | 0 | 0 | 0 |
| PJ2 | 19" **Rapeto** alüminyum alaşımlı jantlar | 27.778 | 63.333 | 66.667 |
| PJ3 | 19" **Halti** antrasit zeminli alüminyum alaşımlı jantlar | 27.778 | 63.333 | 66.667 |
| PJ4 | 19" **Talgar** alüminyum alaşımlı **aero** jantlar | 27.778 | 63.333 | 66.667 |
| PJ5 | 19" **Lefka** antrasit zeminli alüminyum alaşımlı jantlar | 27.778 | 63.333 | 66.667 |
| PTB | **13" Bilgi Eğlence Sistemi** | 27.778 | 63.333 | 66.667 |
| PVA | 2 kollu, **ısıtmalı**, DSG kontrollü deri direksiyon | 8.333 | 19.000 | 20.000 |
| PVB | 3 kollu, DSG kontrollü **spor** deri direksiyon | 8.333 | 19.000 | 20.000 |
| PVC | 3 kollu, **ısıtmalı** DSG kontrollü **spor** deri direksiyon | 16.667 | 38.000 | 40.000 |
| PWC | **Kış Paketi** (2 kollu ısıtmalı direksiyon & Isıtmalı Ön/Arka Koltuklar) | 41.667 | 95.000 | 100.000 |
| PWD | **Kış Paketi** (3 kollu ısıtmalı direksiyon & Isıtmalı Ön/Arka Koltuklar) | 50.000 | 114.000 | 120.000 |
| PZA | **7 Koltuklu Versiyon** | 46.296 | 105.556 | 111.111 |

---

## Prestige — Opsiyonel Donanımlar (Fiyat)

| Kod | Açıklama | Net Satış (TL) | Anahtar Teslim (%90 ÖTV) | Anahtar Teslim (%100 ÖTV) | Anahtar Teslim (%170 ÖTV) |
|-----|----------|---------------:|--------------------------:|--------------------------:|--------------------------:|
| Met | Metalik Renkler | 20.833 | 47.500 | 50.000 | 67.500 |
| Exc | Exclusive Renkler | 27.778 | 63.333 | 66.667 | 90.000 |
| PA2 | **Ses Yalıtımlı Yan Camlar & Karartılmış Arka Camlar** | 19.676 | 44.861 | 47.222 | 63.750 |
| PAB | **Assisted Drive Plus** (Akıllı Park Asistanı & **360° Çevre Görüş**) | 46.296 | 105.556 | 111.111 | 150.000 |
| PFA | **Simply Clever Paket** (Arka Yan Cam Perdeleri & Arka Yan Hava Yastıkları & Tablet Tutucu & Saklama Bölmeleri & Kapı Kenarı Koruması) | 34.722 | 79.167 | 83.333 | 112.500 |
| PHC | **Uzaktan Bağımsız Isıtıcı** | 57.870 | 131.944 | 138.889 | 187.500 |
| PI3 | **Suite Cognac** İç Döşeme | 0 | 0 | 0 | 0 |
| PJ4 | 19" **Talgar** alüminyum alaşımlı **aero** jantlar | 0 | 0 | 0 | 0 |
| PJ5 | 19" **Lefka** antrasit zeminli alüminyum alaşımlı jantlar | 0 | 0 | 0 | 0 |
| PJ6 | 20" **Rila** antrasit zeminli alüminyum alaşımlı jantlar | 27.778 | 63.333 | 66.667 | 90.000 |
| PK1 | **Adaptörlü Çeki Demiri** *(PAB ile birlikte)* | 41.667 | 95.000 | 100.000 | 135.000 |
| PPP | **Dinamik Şasi Kontrol Sistemi Pro (DCC Pro)** | 46.296 | 105.556 | 111.111 | 150.000 |
| PSC | **Simply Clever Kargo Paket** (bagaj filesi, paspas (kauçuk/kumaş), saklama bölmeleri) | 16.667 | 38.000 | 40.000 | 54.000 |
| PVC | 3 kollu, **ısıtmalı** DSG kontrollü **spor** deri direksiyon | 8.333 | 19.000 | 20.000 | 27.000 |
| PWC | **Kış Paketi** (2 kollu ısıtmalı direksiyon & Isıtmalı Ön/Arka Koltuklar) | 16.667 | 38.000 | 40.000 | 54.000 |
| PWD | **Kış Paketi** (3 kollu ısıtmalı direksiyon & Isıtmalı Ön/Arka Koltuklar) | 25.000 | 57.000 | 60.000 | 81.000 |
| PZA | **7 Koltuklu Versiyon** | 46.296 | 105.556 | 111.111 | 150.000 |
| WCD | **Masaj Fonksiyonlu Ön Koltuklar** | 46.296 | 105.556 | 111.111 | 150.000 |

---

## Sportline — Opsiyonel Donanımlar (Fiyat)

| Kod | Açıklama | Net Satış (TL) | Anahtar Teslim (%90 ÖTV) | Anahtar Teslim (%100 ÖTV) | Anahtar Teslim (%170 ÖTV) |
|-----|----------|---------------:|--------------------------:|--------------------------:|--------------------------:|
| Met | Metalik Renkler | 20.833 | 47.500 | 50.000 | 67.500 |
| Exc | Exclusive Renkler | 27.778 | 63.333 | 66.667 | 90.000 |
| PAB | **Assisted Drive Plus** (Akıllı Park Asistanı & **360° Çevre Görüş**) | 46.296 | 105.556 | 111.111 | 150.000 |
| PFA | **Simply Clever Paket** (Arka Yan Cam Perdeleri & Arka Yan Hava Yastıkları & Tablet Tutucu & Saklama Bölmeleri & Kapı Kenarı Koruması) | 34.722 | 79.167 | 83.333 | 112.500 |
| PHC | **Uzaktan Bağımsız Isıtıcı** | 57.870 | 131.944 | 138.889 | 187.500 |
| PK1 | **Adaptörlü Çeki Demiri** | 41.667 | 95.000 | 100.000 | 135.000 |
| PPP | **DCC Pro** | 46.296 | 105.556 | 111.111 | 150.000 |
| PSC | **Simply Clever Kargo Paket** | 16.667 | 38.000 | 40.000 | 54.000 |
| PZA | **7 Koltuklu Versiyon** | 46.296 | 105.556 | 111.111 | 150.000 |

---

## RS — Opsiyonel Donanımlar (Fiyat)

| Kod | Açıklama | Net Satış (TL) | Anahtar Teslim (%170 ÖTV) |
|-----|----------|---------------:|--------------------------:|
| Met | Metalik Renkler | 20.833 | 67.500 |
| Exc | Exclusive Renkler | 27.778 | 90.000 |
| PFA | **Simply Clever Paket** | 34.722 | 112.500 |
| PHC | **Uzaktan Bağımsız Isıtıcı** | 57.870 | 187.500 |
| PK1 | **Adaptörlü Çeki Demiri** | 41.667 | 135.000 |
| PZA | **7 Koltuklu Versiyon** | 46.296 | 150.000 |

---

## Donanım Listesi — **Tablolu Format (S ⇒ Standart)**

### Güvenlik

| Özellik | Premium | Prestige | Sportline | RS |
|---|---|---|---|---|
| Ön ve arka disk frenler | Standart | Standart | Standart | Standart |
| Sürücü & ön yolcu hava yastıkları | Standart | Standart | Standart | Standart |
| Yan & perde & **merkez** hava yastıkları | Standart | Standart | Standart | Standart |
| ISOFIX çocuk koltuğu sabitleme | Standart | Standart | Standart | Standart |
| Emniyet kemeri uyarısı (ön/arka) | Standart | Standart | Standart | Standart |
| **ESC/ABS/HBA/MSR/ASR/EDL/ESBS/DSR/XDS+** | Standart | Standart | Standart | Standart |
| Servotronic (hıza bağlı direksiyon desteği) | Standart | Standart | Standart | Standart |
| **Progresif direksiyon** | Yok | Yok | Standart | Standart |
| **FULL LED Matrix** ön far grubu + Dinamik Far Asistanı | Standart | Standart | Standart | Standart |

---

### Konfor & Teknoloji

| Özellik | Premium | Prestige | Sportline | RS |
|---|---|---|---|---|
| **10,25" Dijital Gösterge Paneli** | Standart | Standart | Standart | Standart |
| **10" Bilgi Eğlence Sistemi** | Standart | — | — | — |
| **13" Bilgi Eğlence Sistemi** | Opsiyon | Standart | Standart | Standart |
| Geri görüş kamerası | Standart | Standart | Standart | Standart |
| **360° Çevre Görüş** | Yok | Opsiyon | Opsiyon | Standart |
| Akıllı Park Asistanı | Yok | Opsiyon | Opsiyon | Standart |
| **Adaptif Hız Sabitleyici (ACC)** | Opsiyon | Standart | Standart | Standart |
| **DCC Pro (Dinamik Şasi Kontrolü)** | Yok | Opsiyon | Opsiyon | Standart |
| **7 koltuklu versiyon** | Opsiyon | Opsiyon | Opsiyon | Opsiyon |
| Dinamik ses güçlendirme | Yok | Yok | Yok | Standart |

---

### Tasarım

| Özellik | Premium | Prestige | Sportline | RS |
|---|---|---|---|---|
| 18" **Soira** jantlar | Standart | Yok | Yok | Yok |
| 19" **Halti** antrasit jantlar | Opsiyon | Standart | Yok | Yok |
| 20" **Rila** aero jantlar | Yok | Opsiyon | Standart | Yok |
| 20" **Elias** jantlar | Yok | Yok | Yok | Standart |
| Yer tasarruflu stepne | Standart | Standart | Standart | Standart |
| LED gündüz farları, **TOP LED** arka & **3D dinamik sinyal** | Standart | Standart | Standart | Standart |
| Çelik pedallar | Yok | Yok | Standart | Standart |
| Dış ayna gövde rengi / **parlak siyah** | Gövde rengi | Gövde rengi | Parlak siyah | Parlak siyah |
| **Crystal lighting** imzalı ön ızgara | Yok | Standart | Standart | Standart |
| Cam çerçeveleri (**UDC** koyu krom / **parlak siyah**) | UDC | UDC | Parlak siyah | Parlak siyah |

---

## DÖŞEME (Özet)

- **Premium:** **Loft** (kumaş, siyah‑gri) — *Standart*; **Lounge** (suedia, siyah‑gri) — *Opsiyon*
- **Prestige:** **Suite** (deri, siyah) — *Standart*; **Suite Cognac** (deri) — *Opsiyon*
- **Sportline:** **Sportline** (suedia, siyah‑gri) — *Standart*
- **RS:** **RS** (deri, siyah — kırmızı dikişli) — *Standart*

---

## STANDART & OPSİYONEL JANTLAR

- **Soira 7.5J×18" (235/55 R18)** — **Premium Standart**
- **PJ0 — Mazeno 7.5J×18" (235/55 R18)** — **Premium Opsiyonel**
- **PJ3 — Halti 7.5J×19" (235/50 R19)** — **Prestige Standart**, Premium **Opsiyonel**
- **PJ2 — Rapeto 7.5J×19" (235/50 R19)** — **Premium Opsiyonel**
- **PJ4 — Talgar 7.5J×19" (235/50 R19)** — **Premium/Prestige Opsiyonel**
- **PJ5 — Lefka 7.5J×19" (235/50 R19)** — **Premium/Prestige Opsiyonel**
- **PJ6 — Rila 8.0J×20" (235/45 R20)** — **Sportline Standart**, **Prestige Opsiyonel**
- **Elias 8.0J×20" (235/45 R20)** — **RS Standart**

---

## RENK SEÇENEKLERİ

- **Metalik:** Ay Beyazı (2Y2Y), Gümüş (8E8E), Graphite Gri (5X5X), Yarış Mavisi (8X8X), Büyülü Siyah (1Z1Z)
- **Exclusive:** Bronz Altın (P4P4), Kadife Kırmızı (K1K1)
- **Özel:** Çelik Gri (M3M3)

---

## Bilgi‑Eğlence & Dijital Gösterge & Direksiyon (Özet)

- **10,25" Dijital Gösterge Paneli** — Premium/Prestige/Sportline/RS **Standart**
- **10" Bilgi Eğlence** — **Premium Standart**; **13" Bilgi Eğlence** — **Prestige/Sportline/RS Standart**
- **Direksiyon:** Premium & Prestige **2 kollu** (standart); **Sportline 3 kollu** (standart); **RS 3 kollu ısıtmalı** (standart)

"""
__all__ = ["KODIAQ_DATA_MD"]
