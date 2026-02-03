# modules/elroq_data.py
# -*- coding: utf-8 -*-

"""
ŠKODA ELROQ MY2025 — Opsiyonel Donanımlar, Donanım Listesi ve Teknik Veriler
Bu dosya Vector Store tarafından kolayca taranabilecek düz Markdown biçimindedir.
- Bütün “S” ibareleri “Standart” olarak yazılmıştır.
- Tablo başlıkları ve terimler PDF ile uyumludur.
Kaynak: ELROQ PDF s.1–8. :contentReference[oaicite:5]{index=5} :contentReference[oaicite:6]{index=6} :contentReference[oaicite:7]{index=7} :contentReference[oaicite:8]{index=8} :contentReference[oaicite:9]{index=9}
"""

ELROQ_DATA_MD = """\
# ŠKODA ELROQ MY 2025

---

## e‑Prestige — Opsiyonel Donanımlar (Fiyat)

| Kod | Açıklama | Net Satış (TL) | Anahtar Teslim (%25 ÖTV) |
|-----|----------|---------------:|--------------------------:|
| Met | Metalik Renkler | 26.667 | 40.000 |
| Exc | Exclusive Renkler | 33.333 | 50.000 |
| PJB | 19" **Regulus** antrasit metalik alüminyum **aero** jantlar | 0 | 0 |
| PJV / PJD | 20" **Vega** gümüş metalik alüminyum alaşımlı jantlar | 34.091 | 51.136 |

> Kaynak: Opsiyon listesi, s.2. :contentReference[oaicite:10]{index=10}

---

## Donanım Listesi — **Tablolu Format (S ⇒ Standart)**

### Güvenlik

| Özellik | e‑Prestige |
|---|---|
| Sürücü ve ön yolcu hava yastıkları | Standart |
| Ön/arka yan hava yastıkları | Standart |
| Ön/arka perde hava yastıkları | Standart |
| Merkez hava yastığı | Standart |
| Ön yolcu hava yastığını devre dışı bırakma | Standart |
| Ön bölge frenleme asistanı (yaya & bisiklet, öngörülü) | Standart |
| Proaktif acil durum yardım sistemi (genişletilmiş güvenlik sistemi) | Standart |
| Emniyet kemeri uyarısı (ön/arka) | Standart |
| ISOFIX çocuk koltuğu sabitleme | Standart |
| Çoklu çarpışma freni | Standart |
| Güvenli çıkış uyarı sistemi | Standart |
| Arka trafik uyarı sistemi | Standart |
| Şerit değiştirme asistanı | Standart |
| **Şerit takip asistanı Plus** | Standart |
| Trafik sıkışıklığı asistanı | Standart |
| Yarı otonom araç kontrolü | Standart |
| Gelişmiş sürücü yorgunluk tespiti & dikkat uyarısı | Standart |
| ESC / ABS / HBA / ASR / EDL / ESBS / DSR / **RBS** / **RBC** | Standart |
| Hıza bağlı değişken direksiyon desteği (Servotronic) | Standart |
| **FULL LED Matrix** ön far grubu | Standart |
| Dinamik far asistanı | Standart |
| Viraj/köşe/kötü hava koşulu dinamik far menzili kontrolü | Standart |
| Ön disk frenler | Standart |
| Alarm sistemi | Standart |
| Elektrikli çocuk güvenlik kilidi | Standart |
| Lastik basınç kontrol sistemi & lastik tamir kiti | Standart |
| Acil durum çağrı sistemi **E‑Call+** | Standart |

> Kaynak: Donanım — Güvenlik, s.1. :contentReference[oaicite:11]{index=11}

---

### Konfor & Teknoloji

| Özellik | e‑Prestige |
|---|---|
| **Isı pompası** | Standart |
| **5" Dijital gösterge paneli** | Standart |
| **13" bilgi eğlence sistemi** | Standart |
| **Shift‑by‑wire** vites kontrol ünitesi | Standart |
| Geri görüş kamerası | Standart |
| Sürüş modu yönetimi | Standart |
| Bluetooth telefon arayüzü | Standart |
| **Kablosuz SmartLink** (Apple CarPlay & Android Auto) | Standart |
| 45 W USB‑C girişleri (2 ön + 2 arka) | Standart |
| Sesli kontrol | Standart |
| 8 hoparlörlü ses sistemi | Standart |
| **Kablosuz şarj** (15 W hızlı şarj + soğutma) | Standart |
| Adaptif hız sabitleyici & hız sınırlayıcı | Standart |
| Elektronik park freni | Standart |
| Rejeneratif frenleme ile enerji geri kazanımı | Standart |
| **2 kollu, çok fonksiyonlu, ısıtmalı deri direksiyon** | Standart |
| **Aircare** çift bölgeli tam otomatik klima & arka havalandırma | Standart |
| Otomatik kararan iç dikiz aynası | Standart |
| Otomatik karartmalı, el. ayarlı/katlanır **ısıtmalı** yan aynalar | Standart |
| Aydınlatmalı makyaj aynalı güneşlikler (sürücü/ön yolcu) | Standart |
| Far & yağmur sensörü | Standart |
| Görsel destekli **ön/arka park sensörleri** | Standart |
| Arka manevra frenleme fonksiyonu | Standart |
| **KESSY Advanced** (anahtarsız giriş & çalıştırma) | Standart |
| Otomatik far kontrolü (eve geliş/çıkış, tünele giriş) | Standart |
| Siyah **tam deri** koltuk döşemeleri | Standart |
| Isıtmalı ön koltuklar, yükseklik & bel destek ayarı (ön) | Standart |
| Ön kol dayama; katlanabilir arka koltuklar & arka kol dayama | Standart |
| Isı yalıtımlı **akustik ön camlar** & geliştirilmiş ses izolasyonu | Standart |
| Arka cam sileceği | Standart |
| **Elektrikli bagaj kapağı & Sanal Pedal** | Standart |
| Ön/arka ayak bölmesi & bagaj aydınlatması | Standart |
| Bagajda 12V soket; bagaj depolama bölmeleri | Standart |
| Çeki demiri hazırlığı; halı paspaslar | Standart |
| **11 kW AC şarj kablosu (Mod 3)** | Standart |
| Sürücü kapısı içinde **şemsiye** | Standart |

> Kaynak: Donanım — Konfor & Teknoloji, s.1. :contentReference[oaicite:12]{index=12}

---

### Tasarım

| Özellik | e‑Prestige |
|---|---|
| **19" Proteus** gümüş metalik alüminyum alaşımlı jantlar | Standart |
| Ambiyans aydınlatma | Standart |
| LED gündüz sürüş aydınlatmaları | Standart |
| **TOP LED** arka aydınlatma & **3D dinamik** arka sinyal | Standart |
| Gövde renginde dış dikiz aynaları & **karşılama aydınlatması** | Standart |
| Mat siyah tavan rayları | Standart |
| Karartılmış arka camlar | Standart |
| Bagaj kapağında **UDC** (unique dark chrome) marka/model yazısı | Standart |
| Kaputta **UDC** marka yazısı; ön/arka tampondaki **UDC** detaylar | Standart |
| Arka spoiler | Standart |

> Kaynak: Donanım — Tasarım, s.1. :contentReference[oaicite:13]{index=13}

---

## DÖŞEME

- **e‑Prestige — SUITE (Tam Deri):** Siyah deri döşeme, **Cognac** dikiş detayları — *Standart*.  
  > Kaynak: Döşeme, s.4. :contentReference[oaicite:14]{index=14}

---

## JANT SEÇENEKLERİ

- **Proteus 8.0J×19"** — **Standart**  
- **Regulus 8.0J×19" (antrasit, AERO)** — **Opsiyonel**  
- **Vega 8.0J×20" (gümüş metalik)** — **Opsiyonel**  
> Kaynak: Jant seçenekleri, s.5. :contentReference[oaicite:15]{index=15}

---

## RENK SEÇENEKLERİ

**Exclusive:** Kadife Kırmızı (K1K1)  
**Metalik:** Ay Beyazı (2Y2Y), Yarış Mavisi (8X8X), Gümüş (8E8E), Büyülü Siyah (1Z1Z), Graphite Gri (5X5X)  
**Özel Renk:** Timiano Yeşili (0B0B), Çelik Gri (M3M3)  
> Kaynak: Renk tabloları, s.3. :contentReference[oaicite:16]{index=16}

---

## Multimedya • Gösterge • Direksiyon (Özet)

- **13" Multimedya** — e‑Prestige **Standart**  
- **5" Dijital Gösterge Paneli** — e‑Prestige **Standart**  
- **2 kollu, çok fonksiyonlu, ısıtmalı deri direksiyon** — e‑Prestige **Standart**  
> Kaynak: s.6–7 & s.1. :contentReference[oaicite:17]{index=17} :contentReference[oaicite:18]{index=18}

---

## Teknik Veriler — ELROQ 60 e‑Prestige

| Özellik | Değer |
|---|---|
| Yakıt Tipi | Elektrik |
| Batarya kapasitesi (brüt/net) | 63 kWh / 59 kWh |
| Maksimum güç | 150 kW (204 PS) |
| Maksimum tork | 310 Nm |
| Maksimum hız | 160 km/s |
| İvmelenme (0–100 km/s) | 8,0 sn |
| WLTP menzil (kombine / şehir içi) | **422 km** / **543 km** |
| Enerji tüketimi (WLTP kombine) | **16,1 kWh/100 km** |
| AC 11 kW şarj (0–100%) | 6 saat 30 dk |
| DC 165 kW şarj (10–80%) | 24 dk |
| Güç aktarımı | Arkadan itiş |
| U/G/Y (mm) | 4.488 / 1.884 / 1.632 |
| Dingil mesafesi (mm) | 2.770 |
| Yerden yükseklik (mm) | 186 |
| Bagaj hacmi (L) | 470 – 1.580 |
| Lastikler | 235/55 R19 |
| Ağırlık (sürücü dahil) (kg) | 1.978 – 2.033 |
| Dönüş çapı (m) | 9,3 |
| Sürtünme katsayısı (Cd) | 0,26 |

> Kaynak: Teknik veriler, s.8. :contentReference[oaicite:19]{index=19}
"""

__all__ = ["ELROQ_DATA_MD"]
