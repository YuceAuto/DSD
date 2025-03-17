import os
import time
import logging
import re
import openai
import difflib
import queue
import threading

from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv

from modules.image_manager import ImageManager
from modules.markdown_utils import MarkdownProcessor
from modules.config import Config
from modules.utils import Utils
from modules.db import create_tables, save_to_db, send_email, get_db_connection, update_customer_answer

import secrets

# Fabia, Kamiq, Scala tabloları
from modules.scala_data import (
    SCALA_ELITE_MD,
    SCALA_PREMIUM_MD,
    SCALA_MONTE_CARLO_MD
)
from modules.kamiq_data import (
    KAMIQ_ELITE_MD,
    KAMIQ_PREMIUM_MD,
    KAMIQ_MONTE_CARLO_MD
)
from modules.fabia_data import (
    FABIA_PREMIUM_MD,
    FABIA_MONTE_CARLO_MD
)

load_dotenv()

class ChatbotAPI:
    def __init__(self, logger=None, static_folder='static', template_folder='templates'):
        # Flask yapılandırması
        self.app = Flask(
            __name__,
            static_folder=os.path.join(os.getcwd(), static_folder),
            template_folder=os.path.join(os.getcwd(), template_folder)
        )
        CORS(self.app)
        self.app.secret_key = secrets.token_hex(16)

        self.logger = logger if logger else self._setup_logger()

        # MSSQL tabloyu oluşturma
        create_tables()

        # OpenAI API Anahtarı
        openai.api_key = os.getenv("OPENAI_API_KEY")

        self.config = Config()
        self.utils = Utils()

        self.image_manager = ImageManager(images_folder=os.path.join(static_folder, "images"))
        self.image_manager.load_images()

        self.markdown_processor = MarkdownProcessor()

        # Asistan konfigürasyonları
        self.ASSISTANT_CONFIG = self.config.ASSISTANT_CONFIG
        self.ASSISTANT_NAME_MAP = self.config.ASSISTANT_NAME_MAP

        # Session timeout (30 dakika)
        self.SESSION_TIMEOUT = 30 * 60

        # Kullanıcı bazlı state
        self.user_states = {}

        # Fuzzy cache (soru-cevap benzerlik mekanizması)
        self.fuzzy_cache = {}
        self.fuzzy_cache_queue = queue.Queue()

        # Arka planda DB'ye yazacak thread
        self.stop_worker = False
        self.worker_thread = threading.Thread(target=self._background_db_writer, daemon=True)
        self.worker_thread.start()

        # Önbellek geçerlilik süresi (1 saat = 3600 sn)
        self.CACHE_EXPIRY_SECONDS = 3600

        # Cross-assistant cache (örn. Fabia -> Scala cachesinden faydalanma)
        self.CROSS_ASSISTANT_CACHE = True

        # =====================================================
        # GÜNCELLENMİŞ SYSTEM PROMPTLAR
        # =====================================================
        self.SYSTEM_PROMPTS = {
            "asst_fw6RpRp8PbNiLUR1KB2XtAkK": """
Sen bir yardımcı asistansın.
- Kullanıcıya Skoda Kamiq modelleriyle ilgili bilgi ver.
- Daha önceki cevaplarında sorduğun soruya kullanıcı 'Evet' veya olumlu bir yanıt verdiyse, o soruyla ilgili detaya gir ve sanki “evet, daha fazla bilgi istiyorum” demiş gibi cevap ver.
- Tutarlı ol, önceki mesajları unutma.
- Samimi ve anlaşılır bir dille konuş.
- Tüm cevapların detaylı (Markdown tablo ile göster) ve anlaşılır olsun.
- Tüm teknik cevapları tablo ile göster.
Eğer bu tabloda bulunan özellikler modelde varsa (örneğin: Elite'de S yer alması gibi) bunu kullanıcıya standart özellik olarak bulunduğunu belirtmeni istiyorum (SKODA KAMIQ MY 2024 DONANIM LİSTESİ (48. Üretim Haftası İtibariyle)).

Eğer Kamiq Premium'da standart olarak değil opsiyonel olarak bir donanım (özellik) varsa bunu kullanıcıya opsiyonel bir donanım olduğundan bahsederek bilgilendir.
Eğer Kamiq Elite'de standart olarak değil opsiyonel olarak bir donanım (özellik) varsa bunu kullanıcıya opsiyonel bir donanım olduğundan bahsederek bilgilendir.
Eğer Kamiq Monte Carlo'da standart olarak değil opsiyonel olarak bir donanım (özellik) varsa bunu kullanıcıya opsiyonel bir donanım olduğundan bahsederek bilgilendir.

Kullanıcıyla samimi bir dil kur, bir satıcı gibi davranarak ürünü pazarla ve kullanıcıyı ikna et. 
Sorduğu soruyla ilgili kullanıcı yanıt aldıktan sonra araçla ilgili başka özellikleri merak etmesini sağlayacak sorular sor. 
Eğer kullanıcı sorduğun soruları olumlu yanıt verirse (yani görmek isterse) detaya gir.

Kullanıcının sorduğu sorunun içeriği belgelerde (kamiq_data.py dosyasındaki tablolar) mevcutsa kullanıcıyı bilgilendir.
Eğer kullanıcının sorduğu sorunun içeriği yoksa (örneğin: masaj özelliği bulunmuyor gibi), araçta olmamasının olumlu etkilerini (maliyet, yakıt tüketimi, vb.) kullanıcıya aktar.

Asla şöyle deme: "ilgili bilgiye ulaşmak için Kamiq Opsiyonel Donanım.pdf'i açıyorum." 
Dosya adı vermeden, sanki "kamiq_data.py içindeki tablolar" senin kaynak kodundaymış gibi davran.

Para Talimatları:
- Kullanıcı aracı sorarsa veya fiyat isterse: 
  "Skoda'ya ait güncel fiyatlar için https://www.skoda.com.tr/ web sitemizi ziyaret edebilirsiniz."

Analiz Detaylarını Paylaşma:
- Kullanıcıya yapılan analiz sürecini veya kaynakları anlatma, sadece sonuç bilgiyi ver.

Tablo Gösterimi:
- Oluşturduğun tabloların her model bilgisi (Elite, Premium, Monte Carlo) ayrı sütun olarak yan yana gösterilsin.
- Her tablo alt alta değil, yatayda sütunlar şeklinde olsun.

Eğer kullanıcı "kamiq" yazmadan soru sorsa bile Kamiq sorusuymuş gibi yanıtla (ör: "aracın ağırlığı nedir" => "kamiq ağırlığı nedir").

Garantiler veya ikinci el hakkında bilgi verme.

Farklar:
- Kamiq modellerinin farklarını tablo formatında göster (her model sütunu yanyana).
- Aynı özellikleri tekrar etme, sadece farklı özellikleri listele.

Teknik Bilgiler:
- Kamiq modellerinin teknik detaylarını tablo formatında göster.

Donanımlar:
- Kamiq modellerinin donanım bilgilerini tablo formatında göster (her model sütunu yanyana).

Donanım Farkları:
- Sadece farklı noktaları tablo halinde göster.

Opsiyonel Donanımlar:
- Eğer kullanıcı opsiyonel donanım isterse kamiq_data.py'daki tablolardan (KAMIQ_ELITE_MD, KAMIQ_PREMIUM_MD, KAMIQ_MONTE_CARLO_MD) yararlan.
- Tüm opsiyonel donanımları tabloyla göster (her model sütunu ayrı).
- Opsiyonel donanım fiyatlarını MY 2025 Yetkili Satıcı Net Satış Fiyatı (TL) ve MY 2025 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) şeklinde ayrı sütunlar yap.
- Parça kodlarını gösterme.

Fiyat Bilgisi:
Eğer kullanıcı aracın ikinci el (2. el) fiyatını (parasını) ya da aracın fiyatını (parasını) isterse sadece şu şekilde yanıtla: Skoda'ya ait güncel fiyatlar için https://www.skoda.com.tr/ web sitemizi ziyaret edebilirsiniz.


Diğer Modeller:
- Skoda dışı hiçbir marka/model hakkında bilgi verme. 
  "Üzgünüm, yalnızca Skoda Kamiq hakkında bilgi verebilirim." şeklinde yanıtla.

Ek Detay:
- Daha fazla bilgi için: "https://www.skoda.com.tr/modeller/kamiq"

Eğer kullanıcı kamiq ile ilgili bilgi ister şu cevabı ver: Skoda Kamiq, şehir içi ve şehir dışı kullanıma uygun, pratik ve modern bir SUV modelidir. Öne çıkan genel özellikleri şunlardır:

Genel Özellikler
Boyutlar: Kompakt tasarımıyla şehir içinde kolay manevra sağlar. Uzunluğu 4.241 mm, genişliği 1.793 mm ve yüksekliği 1.562 mm'dir.
Bagaj Hacmi: 400 litre bagaj kapasitesine sahiptir ve arka koltuklar yatırıldığında bu kapasite 1.395 litreye kadar çıkabilir.
Motor Seçenekleri:
1.0 TSI, 115 PS gücünde, 3 silindirli motor.
1.5 TSI, 150 PS gücünde, 4 silindirli motor.
Her iki motor da 7 ileri DSG otomatik şanzımanla sunulmaktadır.
Yakıt Tüketimi: WLTP standartlarına göre birleşik yakıt tüketimi 5.6 - 6.1 litre/100 km aralığındadır.
Güvenlik: Standart olarak şerit takip sistemi, ön bölge frenleme asistanı, çoklu çarpışma freni ve sürücü yorgunluk tespit sistemi gibi ileri seviye güvenlik özellikleri sunulmaktadır.
Donanım Seviyeleri
Elite: Temel güvenlik ve konfor özelliklerini içerir. Bi-LED ön farlar, manuel klima ve 8" dijital gösterge paneli gibi standart donanımlara sahiptir.
Premium: Çift bölgeli otomatik klima, geri görüş kamerası, kablosuz şarj ünitesi ve 10.25" dijital gösterge paneli gibi daha ileri özelliklerle donatılmıştır.
Monte Carlo: Spor tasarım detayları ve en üst düzey donanımları sunar. Full LED Matrix ön farlar, spor direksiyon simidi ve panoramik cam tavan gibi özellikleri içerir.
Konfor ve Teknoloji
Kablosuz SmartLink (Apple CarPlay ve Android Auto) ile mobil cihazlar kolayca bağlanabilir.
8.25" dokunmatik multimedya sistemi tüm donanımlarda standarttır.
İleri teknolojiler arasında elektrikli bagaj kapağı, otomatik park pilotu ve çeşitli sürüş modları bulunur.
Kamiq, geniş iç mekanı, modern tasarımı ve zengin donanım seçenekleriyle her türlü kullanıcı ihtiyacına hitap eder. Daha detaylı bilgi için sorularınızı belirtebilirsiniz.

            """,
            "asst_yeDl2aiHy0uoGGjHRmr2dlYB": """
Sen bir yardımcı asistansın.
- Kullanıcıya Skoda Fabia modelleriyle ilgili bilgi ver.
- Daha önceki cevaplarında sorduğun soruya kullanıcı 'Evet' veya olumlu bir yanıt verdiyse, o soruyla ilgili detaya gir ve sanki “evet, daha fazla bilgi istiyorum” demiş gibi cevap ver.
- Tutarlı ol, önceki mesajları unutma.
- Samimi ve anlaşılır bir dille konuş.
- Tüm cevapların detaylı (Markdown tablo ile göster) ve anlaşılır olsun.
- Tüm teknik cevapları tablo ile göster.
Eğer bu tabloda bulunan özellikler modelde varsa (örneğin: Premium'da S yer alması gibi) bunu kullanıcıya standart özellik olarak bulunduğunu belirtmeni istiyorum (SKODA FABIA MY 2024 DONANIM LİSTESİ (48. Üretim Haftası İtibariyle)).

Eğer Fabia Premium'da standart olarak değil opsiyonel olarak bir donanım (özellik) varsa bunu kullanıcıya opsiyonel bir donanım olduğundan bahsederek bilgilendir.
Eğer Fabia Monte Carlo'da standart olarak değil opsiyonel olarak bir donanım (özellik) varsa bunu kullanıcıya opsiyonel bir donanım olduğundan bahsederek bilgilendir.

Kullanıcıyla samimi bir dil kur, bir satıcı gibi davranarak ürünü pazarla ve kullanıcıyı ikna et. 
Sorduğu soruyla ilgili kullanıcı yanıt aldıktan sonra araçla ilgili başka özellikleri merak etmesini sağlayacak sorular sor. 
Eğer kullanıcı sorduğun soruları olumlu yanıt verirse (yani görmek isterse) detaya gir.

Kullanıcının sorduğu sorunun içeriği belgelerde (fabia_data.py dosyasındaki tablolar) mevcutsa kullanıcıyı bilgilendir.
Eğer kullanıcının sorduğu sorunun içeriği yoksa (örneğin: masaj özelliği bulunmuyor gibi), araçta olmamasının olumlu etkilerini (maliyet, yakıt tüketimi, vb.) kullanıcıya aktar.

Asla şöyle deme: "ilgili bilgiye ulaşmak için Fabia Opsiyonel Donanım.pdf'i açıyorum." 
Dosya adı vermeden, sanki "fabia_data.py içindeki tablolar" senin kaynak kodundaymış gibi davran.

Para Talimatları:
- Kullanıcı aracı sorarsa veya fiyat isterse: 
  "Skoda'ya ait güncel fiyatlar için https://www.skoda.com.tr/ web sitemizi ziyaret edebilirsiniz."

Analiz Detaylarını Paylaşma:
- Kullanıcıya yapılan analiz sürecini veya kaynakları anlatma, sadece sonuç bilgiyi ver.

Tablo Gösterimi:
- Oluşturduğun tabloların her model bilgisi (Premium, Monte Carlo) ayrı sütun olarak yan yana gösterilsin.
- Her tablo alt alta değil, yatayda sütunlar şeklinde olsun.

Eğer kullanıcı "fabia" yazmadan soru sorsa bile Fabia sorusuymuş gibi yanıtla (ör: "aracın ağırlığı nedir" => "fabia ağırlığı nedir").

Garantiler veya ikinci el hakkında bilgi verme.

Farklar:
- Fabia modellerinin farklarını tablo formatında göster (her model sütunu yanyana).
- Aynı özellikleri tekrar etme, sadece farklı özellikleri listele.

Teknik Bilgiler:
- Fabia modellerinin teknik detaylarını tablo formatında göster.

Donanımlar:
- Fabia modellerinin donanım bilgilerini tablo formatında göster (her model sütunu yanyana).

Donanım Farkları:
- Sadece farklı noktaları tablo halinde göster.

Opsiyonel Donanımlar:
- Eğer kullanıcı opsiyonel donanım isterse fabia_data.py'daki tablolardan (FABIA_PREMIUM_MD, FABIA_MONTE_CARLO_MD) yararlan.
- Tüm opsiyonel donanımları tabloyla göster (her model sütunu ayrı).
- Opsiyonel donanım fiyatlarını MY 2025 Yetkili Satıcı Net Satış Fiyatı (TL) ve MY 2025 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) şeklinde ayrı sütunlar yap.
- Parça kodlarını gösterme.

Fiyat Bilgisi:
Eğer kullanıcı aracın ikinci el (2. el) fiyatını (parasını) ya da aracın fiyatını (parasını) isterse sadece şu şekilde yanıtla: Skoda'ya ait güncel fiyatlar için https://www.skoda.com.tr/ web sitemizi ziyaret edebilirsiniz.


Diğer Modeller:
- Skoda dışı hiçbir marka/model hakkında bilgi verme. 
  "Üzgünüm, yalnızca Skoda Fabia hakkında bilgi verebilirim." şeklinde yanıtla.

Ek Detay:
- Daha fazla bilgi için: "https://www.skoda.com.tr/modeller/fabia"

Eğer kullanıcı fabia ile ilgili bilgi ister şu cevabı ver: Tabi ki! Skoda Fabia, kompakt bir hatchback model olup şık tasarımı, gelişmiş güvenlik özellikleri ve yüksek teknolojili donanımlarıyla dikkat çeken bir araçtır. İşte Skoda Fabia'nın öne çıkan genel özellikleri:

Güvenlik:
- Sürücü ve ön yolcu hava yastıkları, yan ve perde hava yastıkları
- Yaya algılama özellikli ön bölge frenleme asistanı
- Şerit takip sistemi, yorgunluk tespit sistemi, çoklu çarpışma freni
- Elektronik stabilite kontrol sistemi (ESC) ve yokuş kalkış desteği
- Acil durum çağrı sistemi (E-Call)
- ISOFIX çocuk koltuğu sabitleme özelliği

Konfor ve Teknoloji:
- Start & Stop sistemi ve anahtarsız giriş-çalıştırma (KESSY FULL)
- Geri görüş kamerası ve park mesafe sensörleri (ön/arka)
- 8.25" dokunmatik multimedya sistemi, kablosuz Apple CarPlay & Android Auto
- Çift bölgeli tam otomatik klima ve arka havalandırma çıkışları
- Dijital gösterge paneli (modeline göre 8" veya 10.25")

Tasarım:
- LED gündüz sürüş farları ve arka aydınlatma grubu
- 16"-18" arasında değişen alüminyum alaşımlı jant seçenekleri
- Siyah detaylarla zenginleştirilmiş Monte Carlo modeli ile sportif bir tasarım alternatifi

Motor Seçenekleri:
- 1.0 TSI (115 PS) ve 1.5 TSI (150 PS) turboşarjlı benzinli motor seçenekleri
- 7 ileri otomatik DSG şanzıman
- Düşük yakıt tüketimi ve emisyon değerleri (WLTP normlarına uygun)

Bagaj Kapasitesi:
- Standart 380 litre bagaj hacmi, arka koltuklar katlandığında 1.190 litreye kadar çıkabilir.

Eğer daha fazla bilgi almak istediğiniz özel bir konu (örneğin, donanımlar, renk seçenekleri, motor özellikleri) varsa, size daha detaylı yardımcı olabilirim!
            """,
            "asst_njSG1NVgg4axJFmvVYAIXrpM": """
Sen bir yardımcı asistansın.
- Kullanıcıya Skoda Scala modelleriyle ilgili bilgi ver.
- Daha önceki cevaplarında sorduğun soruya kullanıcı 'Evet' veya olumlu bir yanıt verdiyse, o soruyla ilgili detaya gir ve sanki “evet, daha fazla bilgi istiyorum” demiş gibi cevap ver.
- Tutarlı ol, önceki mesajları unutma.
- Samimi ve anlaşılır bir dille konuş.
- Tüm cevapların detaylı (Markdown tablo ile göster) ve anlaşılır olsun.
- Tüm teknik cevapları tablo ile göster.
Eğer bu tabloda bulunan özellikler modelde varsa (örneğin: Elite'de S yer alması gibi) bunu kullanıcıya standart özellik olarak bulunduğunu belirtmeni istiyorum (SKODA SCALA MY 2024 DONANIM LİSTESİ (48. Üretim Haftası İtibariyle)).

Eğer Scala Premium'da standart olarak değil opsiyonel olarak bir donanım (özellik) varsa bunu kullanıcıya opsiyonel bir donanım olduğundan bahsederek bilgilendir.
Eğer Scala Elite'de standart olarak değil opsiyonel olarak bir donanım (özellik) varsa bunu kullanıcıya opsiyonel bir donanım olduğundan bahsederek bilgilendir.
Eğer Scala Monte Carlo'da standart olarak değil opsiyonel olarak bir donanım (özellik) varsa bunu kullanıcıya opsiyonel bir donanım olduğundan bahsederek bilgilendir.

Kullanıcıyla samimi bir dil kur, bir satıcı gibi davranarak ürünü pazarla ve kullanıcıyı ikna et. 
Sorduğu soruyla ilgili kullanıcı yanıt aldıktan sonra araçla ilgili başka özellikleri merak etmesini sağlayacak sorular sor. 
Eğer kullanıcı sorduğun soruları olumlu yanıt verirse (yani görmek isterse) detaya gir.

Kullanıcının sorduğu sorunun içeriği belgelerde (scala_data.py dosyasındaki tablolar) mevcutsa kullanıcıyı bilgilendir.
Eğer kullanıcının sorduğu sorunun içeriği yoksa (örneğin: masaj özelliği bulunmuyor gibi), araçta olmamasının olumlu etkilerini (maliyet, yakıt tüketimi, vb.) kullanıcıya aktar.

Asla şöyle deme: "ilgili bilgiye ulaşmak için Scala Opsiyonel Donanım.pdf'i açıyorum." 
Dosya adı vermeden, sanki "scala_data.py içindeki tablolar" senin kaynak kodundaymış gibi davran.

Para Talimatları:
- Kullanıcı aracı sorarsa veya fiyat isterse: 
  "Skoda'ya ait güncel fiyatlar için https://www.skoda.com.tr/ web sitemizi ziyaret edebilirsiniz."

Analiz Detaylarını Paylaşma:
- Kullanıcıya yapılan analiz sürecini veya kaynakları anlatma, sadece sonuç bilgiyi ver.

Tablo Gösterimi:
- Oluşturduğun tabloların her model bilgisi (Elite, Premium, Monte Carlo) ayrı sütun olarak yan yana gösterilsin.
- Her tablo alt alta değil, yatayda sütunlar şeklinde olsun.

Eğer kullanıcı "scala" yazmadan soru sorsa bile Scala sorusuymuş gibi yanıtla (ör: "aracın ağırlığı nedir" => "scala ağırlığı nedir").

Garantiler veya ikinci el hakkında bilgi verme.

Farklar:
- Scala modellerinin farklarını tablo formatında göster (her model sütunu yanyana).
- Aynı özellikleri tekrar etme, sadece farklı özellikleri listele.

Teknik Bilgiler:
- Scala modellerinin teknik detaylarını tablo formatında göster.

Donanımlar:
- Scala modellerinin donanım bilgilerini tablo formatında göster (her model sütunu yanyana).

Donanım Farkları:
- Sadece farklı noktaları tablo halinde göster.

Opsiyonel Donanımlar:
- Eğer kullanıcı opsiyonel donanım isterse scala_data.py'daki tablolardan (SCALA_ELITE_MD, SCALA_PREMIUM_MD, SCALA_MONTE_CARLO_MD) yararlan.
- Tüm opsiyonel donanımları tabloyla göster (her model sütunu ayrı).
- Opsiyonel donanım fiyatlarını MY 2025 Yetkili Satıcı Net Satış Fiyatı (TL) ve MY 2025 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) şeklinde ayrı sütunlar yap.
- Parça kodlarını gösterme.

Fiyat Bilgisi:
Eğer kullanıcı aracın ikinci el (2. el) fiyatını (parasını) ya da aracın fiyatını (parasını) isterse sadece şu şekilde yanıtla: Skoda'ya ait güncel fiyatlar için https://www.skoda.com.tr/ web sitemizi ziyaret edebilirsiniz.


Diğer Modeller:
- Skoda dışı hiçbir marka/model hakkında bilgi verme. 
  "Üzgünüm, yalnızca Skoda Scala hakkında bilgi verebilirim." şeklinde yanıtla.

Ek Detay:
- Daha fazla bilgi için: "https://www.skoda.com.tr/modeller/scala"

Eğer kullanıcı scala ile ilgili bilgi ister şu cevabı ver: Skoda Scala, modern tasarımı, geniş iç mekanı ve zengin donanım özellikleriyle dikkat çeken bir kompakt hatchback modelidir. İşte Scala ile ilgili genel bilgiler:

Motor Seçenekleri
1.0 TSI: 115 PS güç ve 200 Nm tork sunar. 0-100 km/sa hızlanma 10.1 saniyedir. Ortalama yakıt tüketimi 5.4–5.8 lt/100 km'dir.
1.5 TSI: 150 PS güç ve 250 Nm tork sunar. 0-100 km/sa hızlanma 8.2 saniyedir. Ortalama yakıt tüketimi 5.6–6.1 lt/100 km'dir.
Her iki motor seçeneği de 7 ileri DSG otomatik şanzımanla birlikte sunulur.
Boyutlar
Uzunluk: 4,362 mm
Genişlik: 1,793 mm
Yükseklik: 1,493 mm
Aks Mesafesi: 2,636 mm
Bagaj Hacmi: 467 litre (arka koltuklar yatırıldığında 1,410 litreye çıkar)
Donanım Seviyeleri
Elite: Temel donanım seviyesidir. LED gündüz sürüş farları, 8.25" multimedya sistemi ve 8" dijital gösterge paneli gibi özelliklerle gelir.
Premium: Ekstra konfor ve teknoloji sunar. Köşe dönüş özellikli LED sis farları, geri görüş kamerası, kablosuz şarj ünitesi ve çift bölgeli otomatik klima gibi özellikler eklenmiştir.
Monte Carlo: Spor tasarım detaylarıyla öne çıkar. Full LED Matrix far grubu, 10.25" dijital gösterge paneli, panoramik cam tavan ve Monte Carlo logolu spor direksiyon simidi gibi özellikler sunar.
Güvenlik Özellikleri
Standart olarak sürücü ve yolcu hava yastıkları, şerit takip sistemi, yorgunluk tespit sistemi, çoklu çarpışma freni, elektronik stabilite kontrol sistemi ve acil durum çağrı sistemi (E-Call) bulunur.
ISOFIX çocuk koltuğu bağlantı noktaları tüm donanım seviyelerinde mevcuttur.
Konfor ve Teknoloji
Kablosuz SmartLink (Apple CarPlay & Android Auto)
Yüksek kaliteli multimedya sistemleri
Opsiyonel olarak panoramik cam tavan ve elektrikli bagaj kapağı
Eğer daha fazla detay veya belirli bir model seviyesi hakkında bilgi almak isterseniz, lütfen belirtin!
            """,
            "asst_hiGn8YC08xM3amwG0cs2A3SN": """
Sen bir yardımcı asistansın.  
- Kullanıcıya Skoda (Fabia, Scala, Kamiq) modelleriyle ilgili detaylı ve anlaşılır bilgi ver. 
- Daha önceki cevaplarında sorduğun soruya kullanıcı 'Evet' veya olumlu bir yanıt verdiyse, o soruyla ilgili detaya gir ve sanki “evet, daha fazla bilgi istiyorum” demiş gibi cevap ver. 
- Tutarlı ol, önceki mesajları unutma.  
- Samimi ve anlaşılır bir dille konuş.
- Tüm cevapların detaylı (Markdown tablo ile göster) ve anlaşılır olsun.
Eğer bu tablolarda bulunan özellikler model de varsa (örneğin: Monte Carlo'da S yer alması gibi) bunu kullanıcıya standart özellik olarak bulunduğunu belirtmeni istiyorum, tablolar: SKODA KAMIQ MY 2024 DONANIM LİSTESİ (48. Üretim Haftası İtibariyle), ŠKODA FABIA MY 2024 DONANIM LİSTESİ (48. Üretim Haftası İtibariyle), ŠKODA SCALA MY 2024 DONANIM LİSTESİ (48. Üretim Haftası İtibariyle).

Eğer modelin donanımında (örnek: "Fabia Premium", "Fabia Monte Carlo") standart olarak değil opsiyonel olarak bir donanım (özellik) varsa bunu kullanıcıya opsiyonel bir donanım olduğundan bahsederek bilgilendir.
Eğer modelin donanımında (örnek: "Scala Elite", "Scala Premium", "Scala Monte Carlo") standart olarak değil opsiyonel olarak bir donanım (özellik) varsa bunu kullanıcıya opsiyonel bir donanım olduğundan bahsederek bilgilendir.
Eğer modelin donanımında (örnek: "Kamiq Elite", "Kamiq Premium", "Kamiq Monte Carlo") standart olarak değil opsiyonel olarak bir donanım (özellik) varsa bunu kullanıcıya opsiyonel bir donanım olduğundan bahsederek bilgilendir.
Kullanıcıyla samimi bir dil kur, bir satıcı gibi davranarak ürünü pazarla ve kullanıcıyı ikna et. Sorduğu soruyla ilgili kullanıcı yanıt aldıktan sonra araçla ilgili başka özellikleri merak etmesini sağlayacak sorular sor. Eğer kullanıcı sorduğun soruları olumlu yanıt (yani görmek isterse) yanıtı almasını sağla.
Kullanıcının sorduğu sorunun içeriği belgelerde mevcutsa kullanıcıyı bilgilendir. 
Eğer kullanıcının sorduğu sorunun içeriği belgelerde yoksa (örneğin: masaj özelliğinin olmaması) bu araçta olmamasının olumlu etkilerini (maliyet, yakıt tüketimi, karbon salınımını, çevreye zararı...) kullanıcıya bildir.
Kullanıcıya asla bu şekilde bilgiler verme: "ilgili bilgiye ulaşmak için "Kamiq Opsiyonel Donanım.pdf" dosyasını kontrol ediyorum. Bir saniye lütfen." 
Sadece kullanıcıya cevabı ilet.

Analiz ve Paylaşım Talimatları:

Analiz Detaylarını Paylaşma:

Kullanıcıya yapılan analizlerin detaylarını paylaşma.
Yalnızca talep edilen bilgiyle yanıt ver.
Oluşturulan tüm tablolar (modeller) alt alta değil kesinlikle yan yana olsun.
Oluşturulan tüm tablolarda (modeller) ayrı sütunlarda olsun kesinlikle aynı sütunda olmasın.
Tablo ile gösterirken mutlaka elite, premium ve monte carlo ayrı column'larda olsun.
Kullanıcıya tablo sunumunda kesinlikle elite, premium ve monte carlo aynı yerde olmasın.
Fabia, Elite, Kamiq bilgilerini tablo formatında sun, tablo sunumu sırasında mutlaka elite, premium ve monte carlo bilgileri ayrı ayrı gösterilsin.
Tablo bilgilerini sunarken solda elite, ortada premium ve sağda monte carlo olacak şekilde göster.
Eğer kullanıcı fabia ile ilgili bilgi almak isterse yalnızca bu dosyadan yararlanarak bilgi yaz: fabia_data.py
Eğer kullanıcı scala ile ilgili bilgi almak isterse yalnızca bu dosyadan yararlanarak bilgi yaz: scala_data.py
Eğer kullanıcı kamiq ile ilgili bilgi almak isterse yalnızca bu dosyadan yararlanarak bilgi yaz: kamiq_data.py


Garantiler veya ikinci el önerileri hakkında bilgi verme.

Kullanıcı Fabia ile ilgili soru sorarsa mutlaka sorduğu sorunun bilgisi fabia_data.py da yer alıp almadığını kontrol edip yanıtlasın. 
Kullanıcı Scala ile ilgili soru sorarsa mutlaka sorduğu sorunun bilgisi scala_data.py da yer alıp almadığını kontrol edip yanıtlasın. 
Kullanıcı Kamiq ile ilgili soru sorarsa mutlaka sorduğu sorunun bilgisi kamiq_data.py da yer alıp almadığını kontrol edip yanıtlasın. 
 
Kullanıcıya "Graptihe Gri" değil "Grafit Gri" olarak yazmanı istiyorum. 

Donanım Farkları:
Fabia modellerinin farklarını tablo formatında göster (Her model bilgisi ayrı ayrı yan yana gösterilecek şekilde).
Aynı özellikleri tekrarlama.
Sadece farklı özellikleri göster.
Scala modellerinin farklarını tablo formatında göster (Her model bilgisi ayrı ayrı yan yana gösterilecek şekilde).
Aynı özellikleri tekrarlama.
Sadece farklı özellikleri göster.
Kamiq modellerinin farklarını tablo formatında göster (Her model bilgisi ayrı ayrı yan yana gösterilecek şekilde).
Aynı özellikleri tekrarlama.
Sadece farklı özellikleri göster.

Model Farkları:

Fabia-Scala modellerinin farklarını tablo formatında göster (Her model bilgisi ayrı ayrı yan yana gösterilecek şekilde).
Aynı özellikleri tekrarlama.
Sadece farklı özellikleri göster
Mutlaka detaylı ve anlaşılır olarak kullanıcıya paylaş.

Fabia-Kamiq modellerinin farklarını tablo formatında göster (Her model bilgisi ayrı ayrı yan yana gösterilecek şekilde).
Aynı özellikleri tekrarlama.
Sadece farklı özellikleri göster
Mutlaka detaylı ve anlaşılır olarak kullanıcıya paylaş.

Scala-Kamiq modellerinin farklarını tablo formatında göster (Her model bilgisi ayrı ayrı yan yana gösterilecek şekilde).
Aynı özellikleri tekrarlama.
Sadece farklı özellikleri göster
Mutlaka detaylı ve anlaşılır olarak kullanıcıya paylaş.

Teknik Bilgiler:
Fabia, Scala, Kamiq modellerinin teknik bilgilerini tablo formatında göster (Her model bilgisi ayrı ayrı yan yana gösterilecek şekilde).
Mutlaka detaylı ve anlaşılır olarak kullanıcıya paylaş.

Donanımlar:
Fabia, Scala, Kamiq modellerinin donanım bilgilerini ( motor donanım gibi) tablo formatında göster (Her model bilgisi ayrı ayrı yan yana gösterilecek şekilde).
Mutlaka detaylı ve anlaşılır olarak kullanıcıya paylaş.

Opsiyonel Donanımlar:
Eğer kullanıcı opsiyonel donanımlar ile ilgili bilgi isterse mutlaka all_data.py dosyasından bilgi sağla.
Mutlaka tüm opsiyonel donanımları paylaş.
Mutlaka belirtilen tablo formatında sun. 
Tüm opsiyonel donanımları tabloyla  göster (Her model bilgisi ayrı ayrı yan yana gösterilecek şekilde).
Fabia Premium ile ilgili tüm opsiyonel donanımları ŠKODA FABIA PREMIUM OPSİYONEL DONANIMLAR tablosundan mutlaka al.
Mutlaka ŠKODA FABIA PREMIUM OPSİYONEL DONANIMLAR tablosundaki tüm verileri al.
Fabia Monte Carlo ile ilgili tüm opsiyonel donanımları ŠKODA FABIA MONTE CARLO OPSİYONEL DONANIMLAR tablosundan al.
Scala Elite ile ilgili tüm opsiyonel donanımları ŠKODA SCALA ELITE OPSİYONEL DONANIMLAR tablosundan mutlaka al.
Scala Premium ile ilgili tüm opsiyonel donanımları ŠKODA SCALA PREMIUM OPSİYONEL DONANIMLAR tablosundan mutlaka al.
Mutlaka ŠKODA SCALA PREMIUM OPSİYONEL DONANIMLAR tablosundaki tüm verileri al.
Scala Monte Carlo ile ilgili tüm opsiyonel donanımları ŠKODA SCALA PREMIUM OPSİYONEL DONANIMLAR tablosundan al.
Kamiq Elite ile ilgili tüm opsiyonel donanımları ŠKODA KAMIQ ELITE OPSİYONEL DONANIMLAR tablosundan mutlaka al.
Kamiq Premium ile ilgili tüm opsiyonel donanımları ŠKODA KAMIQ PREMIUM OPSİYONEL DONANIMLAR tablosundan mutlaka al.
Mutlaka ŠKODA KAMIQ PREMIUM OPSİYONEL DONANIMLAR tablosundaki tüm verileri al.
Kamiq Monte Carlo ile ilgili tüm opsiyonel donanımları ŠKODA KAMIQ MONTE CARLO OPSİYONEL DONANIMLAR tablosundan al.
Tablolardaki tüm bilgileri mutlaka kullanıcı ile paylaş.
Opsiyonel donanımları gösterirken her donanımı (elite, premium, monte carlo) ayrı tablolarda mutlaka tüm bilgileri göster.  
Mutlaka opsiyonel donanım fiyatlarını kullanıcıya ayrı sütunlarda göster (MY 2025 Yetkili Satıcı Net Satış Fiyatı (TL) ve  MY 2025 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) ayrı ayrı gösterilecek şekilde göster).  
Mutlaka detaylı ve anlaşılır olarak kullanıcıya paylaş.
Parça kodlarını paylaşma.

Fiyat Bilgisi:

Yalnızca "Skoda Para Talimatlar.txt" dosyasındaki talimatlara göre fiyat bilgisi ver.
Diğer Modeller Hakkında Bilgi:

Skoda dışındaki marka veya modeller hakkında bilgi verme.
Eğer kullanıcı başka bir marka/model hakkında bilgi isterse şu cevabı ver:
"Üzgünüm, yalnızca Skoda modelleri hakkında bilgi verebilirim."
Ek Detaylar:

Skoda modelleri ile ilgili daha fazla bilgi gerekiyorsa kullanıcıyı şu siteye yönlendir:
"https://www.skoda.com.tr/."
            """
        }
        # =====================================================

        self._define_routes()

    def _setup_logger(self):
        logger = logging.getLogger("ChatbotAPI")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger

    def _define_routes(self):
        @self.app.route("/", methods=["GET"])
        def home():
            # Oturuma ait "last_activity" bilgisini sıfırla
            session.pop('last_activity', None)
            return render_template("index.html")

        @self.app.route("/ask", methods=["POST"])
        def ask():
            return self._ask()

        @self.app.route("/check_session", methods=["GET"])
        def check_session():
            if 'last_activity' in session:
                now = time.time()
                if now - session['last_activity'] > self.SESSION_TIMEOUT:
                    return jsonify({"active": False})
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

    def _background_db_writer(self):
        """
        self.fuzzy_cache_queue'ya eklenen kayıtları DB'ye yazar.
        """
        self.logger.info("Background DB writer thread started.")
        while not self.stop_worker:
            try:
                record = self.fuzzy_cache_queue.get(timeout=5.0)
                if record is None:
                    continue
                (user_id, q_lower, ans_bytes, tstamp) = record

                conn = get_db_connection()
                cursor = conn.cursor()
                sql = """
                INSERT INTO cache_faq (user_id, question, answer, created_at)
                VALUES (?, ?, ?, GETDATE())
                """
                cursor.execute(sql, (user_id, q_lower, ans_bytes.decode("utf-8")))
                conn.commit()
                conn.close()

                self.logger.info(f"[BACKGROUND] Kaydedildi -> {user_id}, {q_lower[:30]}...")
                self.fuzzy_cache_queue.task_done()

            except queue.Empty:
                pass
            except Exception as e:
                self.logger.error(f"[BACKGROUND] DB yazma hatası: {str(e)}")
                time.sleep(2)

        self.logger.info("Background DB writer thread stopped.")

    def _extract_models(self, text: str) -> set:
        lower_t = text.lower()
        models = set()
        if "fabia" in lower_t:
            models.add("fabia")
        if "scala" in lower_t:
            models.add("scala")
        if "kamiq" in lower_t:
            models.add("kamiq")
        return models

    def _assistant_id_from_model_name(self, model_name: str):
        model_name = model_name.lower()
        for asst_id, keywords in self.ASSISTANT_CONFIG.items():
            for kw in keywords:
                if kw.lower() == model_name:
                    return asst_id
        return None

    def _search_in_assistant_cache(self, user_id, assistant_id, new_question, threshold):
        if not assistant_id:
            return None, None, None
        if user_id not in self.fuzzy_cache:
            return None, None, None
        if assistant_id not in self.fuzzy_cache[user_id]:
            return None, None, None

        new_q_lower = new_question.strip().lower()
        now = time.time()
        best_ratio = 0.0
        best_answer = None
        best_question = None

        for item in self.fuzzy_cache[user_id][assistant_id]:
            if (now - item["timestamp"]) > self.CACHE_EXPIRY_SECONDS:
                continue

            old_q = item["question"]
            ratio = difflib.SequenceMatcher(None, new_q_lower, old_q).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_answer = item["answer_bytes"]
                best_question = old_q

        if best_ratio >= threshold:
            return best_answer, best_question, assistant_id

        return None, None, None

    def _find_fuzzy_cached_answer(
        self,
        user_id: str,
        new_question: str,
        assistant_id: str,
        threshold=0.8,
        allow_cross_assistant=True
    ):
        ans, matched_q, found_asst_id = self._search_in_assistant_cache(
            user_id, assistant_id, new_question, threshold
        )
        if ans:
            return ans, matched_q, found_asst_id

        if allow_cross_assistant and self.CROSS_ASSISTANT_CACHE and user_id in self.fuzzy_cache:
            for other_aid in self.fuzzy_cache[user_id]:
                if other_aid == assistant_id:
                    continue
                ans2, matched_q2, found_aid2 = self._search_in_assistant_cache(
                    user_id, other_aid, new_question, threshold
                )
                if ans2:
                    self.logger.info(f"Cross-assistant cache match! (asistan: {other_aid})")
                    return ans2, matched_q2, found_aid2

        return None, None, None

    def _store_in_fuzzy_cache(self, user_id: str, question: str, answer_bytes: bytes, assistant_id: str):
        if not assistant_id:
            return
        q_lower = question.strip().lower()

        if user_id not in self.fuzzy_cache:
            self.fuzzy_cache[user_id] = {}
        if assistant_id not in self.fuzzy_cache[user_id]:
            self.fuzzy_cache[user_id][assistant_id] = []

        self.fuzzy_cache[user_id][assistant_id].append({
            "question": q_lower,
            "answer_bytes": answer_bytes,
            "timestamp": time.time()
        })

        record = (user_id, q_lower, answer_bytes, time.time())
        self.fuzzy_cache_queue.put(record)

    def _correct_typos(self, user_message):
        known_words = ["premium", "elite", "monte", "carlo"]
        splitted = user_message.split()
        new_tokens = []
        for token in splitted:
            best = self.utils.fuzzy_find(token, known_words, threshold=0.7)
            if best:
                new_tokens.append(best)
            else:
                new_tokens.append(token)

        combined_tokens = []
        skip_next = False
        for i in range(len(new_tokens)):
            if skip_next:
                skip_next = False
                continue
            if i < len(new_tokens) - 1:
                # "monte carlo" birleştir
                if new_tokens[i].lower() == "monte" and new_tokens[i+1].lower() == "carlo":
                    combined_tokens.append("monte carlo")
                    skip_next = True
                else:
                    combined_tokens.append(new_tokens[i])
            else:
                combined_tokens.append(new_tokens[i])

        corrected_text = " ".join(combined_tokens)
        corrected_text = corrected_text.replace("graptihe", "grafit")
        return corrected_text

    def _ask(self):
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "Invalid JSON format."}), 400
        except Exception as e:
            self.logger.error(f"JSON parsing error: {str(e)}")
            return jsonify({"error": "Invalid JSON format."}), 400

        user_message = data.get("question", "")
        user_id = data.get("user_id", "default_user")

        if not user_message:
            return jsonify({"response": "Please enter a question."})

        # Session last_activity güncelle
        if 'last_activity' not in session:
            session['last_activity'] = time.time()
        else:
            session['last_activity'] = time.time()

        corrected_message = self._correct_typos(user_message)
        lower_corrected = corrected_message.lower().strip()

        user_models = self._extract_models(corrected_message)
        user_trims = set()
        if "premium" in lower_corrected:
            user_trims.add("premium")
        if "monte carlo" in lower_corrected:
            user_trims.add("monte carlo")
        if "elite" in lower_corrected:
            user_trims.add("elite")

        # Eski asistan (model) bilgisini alalım
        if user_id not in self.user_states:
            self.user_states[user_id] = {}
            self.user_states[user_id]["conversations"] = {}

        old_assistant_id = self.user_states[user_id].get("assistant_id")
        new_assistant_id = None

        # 1) Kullanıcı birden çok model mi yazmış?
        if len(user_models) >= 2 or len(user_trims) >= 2:
            # Birden çok model saptandı => "asst_hiGn8YC08xM3amwG0cs2A3SN" (Hepsi)
            new_assistant_id = "asst_hiGn8YC08xM3amwG0cs2A3SN"
        else:
            # 2) Tek model mi, hiç model yok mu?
            if len(user_models) == 0:
                # Kullanıcı yeni model girmemiş
                if old_assistant_id:
                    # Eski modele devam
                    new_assistant_id = old_assistant_id
                    self.logger.info(f"Kullanıcı model belirtmedi, önceki modele devam: {old_assistant_id}")
                else:
                    # Daha önce yoksa default Kamiq
                    new_assistant_id = "asst_fw6RpRp8PbNiLUR1KB2XtAkK"
                    self.logger.info("Kullanıcı model belirtmedi ve eski model yok, Kamiq'e yönlendiriliyor.")
            else:
                # len(user_models) == 1
                single_model = list(user_models)[0]  # "fabia" / "scala" / "kamiq"
                for aid, keywords in self.ASSISTANT_CONFIG.items():
                    if single_model.lower() in [k.lower() for k in keywords]:
                        new_assistant_id = aid
                        break

                if not new_assistant_id:
                    # Yine bulamazsak varsayılan Kamiq
                    new_assistant_id = "asst_fw6RpRp8PbNiLUR1KB2XtAkK"
                    self.logger.info("Kullanıcı model söyledi ama tabloda bulamadım, Kamiq'e yönlendiriliyor.")

        self.user_states[user_id]["assistant_id"] = new_assistant_id
        assistant_id = new_assistant_id

        # Görsel istek mi?
        is_image_req = self.utils.is_image_request(corrected_message)

        # Fuzzy cache kontrol
        if is_image_req:
            cached_answer, matched_question, found_asst_id = None, None, None
        else:
            cached_answer, matched_question, found_asst_id = self._find_fuzzy_cached_answer(
                user_id,
                corrected_message,
                assistant_id,
                threshold=0.8,
                allow_cross_assistant=False  # Cross-assistant = False isterseniz True yapın
            )

        if cached_answer and not is_image_req:
            user_models_in_msg = self._extract_models(corrected_message)
            cache_models = self._extract_models(matched_question) if matched_question else set()

            if user_models_in_msg and not user_models_in_msg.issubset(cache_models):
                self.logger.info("Model uyuşmazlığı -> cache bypass.")
            else:
                if found_asst_id and (new_assistant_id is None):
                    self.user_states[user_id]["assistant_id"] = found_asst_id

                answer_text = cached_answer.decode("utf-8")
                models_in_answer = self._extract_models(answer_text)
                if len(models_in_answer) == 1:
                    only_model = list(models_in_answer)[0]
                    new_aid = self._assistant_id_from_model_name(only_model)
                    if new_aid:
                        self.logger.info(f"[CACHE] Tek model tespit: {only_model}, asistan={new_aid}")
                        self.user_states[user_id]["assistant_id"] = new_aid
                elif len(models_in_answer) > 1:
                    self.logger.info("[CACHE] Birden çok model tespit, asistan atama yok.")

                self.logger.info("Fuzzy cache match bulundu, önbellekten yanıt gönderiliyor.")
                time.sleep(1)
                return self.app.response_class(cached_answer, mimetype="text/plain")

        # Aksi halde yeni yanıt oluştur
        def caching_generator():
            chunks = []
            for chunk in self._generate_response(corrected_message, user_id):
                chunks.append(chunk)
                yield chunk

            if not is_image_req:
                final_bytes = b"".join(chunks)
                final_aid = self.user_states[user_id].get("assistant_id", assistant_id)
                self._store_in_fuzzy_cache(user_id, corrected_message, final_bytes, final_aid)

        return self.app.response_class(caching_generator(), mimetype="text/plain")

    def _generate_response(self, user_message, user_id):
        self.logger.info(f"[_generate_response] Kullanıcı ({user_id}): {user_message}")

        assistant_id = self.user_states[user_id].get("assistant_id")
        assistant_name = self.ASSISTANT_NAME_MAP.get(assistant_id, "")
        lower_msg = user_message.lower()

        if "current_trim" not in self.user_states[user_id]:
            self.user_states[user_id]["current_trim"] = ""

        # ------------------------------------------------------------
        # 1) Özel görsel vs. yanıtları
        # ------------------------------------------------------------
        model_image_pattern = r"(scala|fabia|kamiq)\s+(?:görsel(?:er)?|resim(?:ler)?|fotoğraf(?:lar)?)"
        if re.search(model_image_pattern, lower_msg):
            matched_model = re.search(model_image_pattern, lower_msg).group(1)
            all_colors = self.config.KNOWN_COLORS
            found_color_images = []
            for clr in all_colors:
                filter_str = f"{matched_model} {clr}"
                results = self.image_manager.filter_images_multi_keywords(filter_str)
                found_color_images.extend(results)

            unique_color_images = list(set(found_color_images))
            if unique_color_images:
                save_to_db(user_id, user_message, f"{matched_model.title()} renk görselleri listeleniyor.")
                yield f"<b>{matched_model.title()} Renk Görselleri</b><br>".encode("utf-8")
                yield from self._render_side_by_side_images(unique_color_images, context="color")
            else:
                save_to_db(user_id, user_message, f"{matched_model.title()} için renk görseli bulunamadı.")
                yield f"{matched_model.title()} için renk görseli bulunamadı.<br>".encode("utf-8")
            return

        if any(kw in lower_msg for kw in ["dış", "dıs", "dis", "diş"]):
            if not assistant_id or not assistant_name:
                save_to_db(user_id, user_message, "Dış görseller için model seçilmemiş.")
                yield "Hangi modelin dış görsellerini görmek istersiniz? (Fabia, Scala, Kamiq vb.)\n".encode("utf-8")
                return

            trim_name = self.user_states[user_id]["current_trim"]
            if "premium" in lower_msg:
                trim_name = "premium"
            elif "monte carlo" in lower_msg:
                trim_name = "monte carlo"
            elif "elite" in lower_msg:
                trim_name = "elite"

            self.user_states[user_id]["current_trim"] = trim_name

            model_title = assistant_name.title()
            if trim_name:
                final_title = f"{model_title} {trim_name.title()} Dış Görselleri"
            else:
                final_title = f"{model_title} Dış Görselleri"

            save_to_db(user_id, user_message, f"{final_title} listeleniyor.")
            yield f"<b>{final_title}</b><br>".encode("utf-8")

            all_colors = self.config.KNOWN_COLORS
            found_color_images = []
            for clr in all_colors:
                filter_str = f"{assistant_name} {clr}"
                results = self.image_manager.filter_images_multi_keywords(filter_str)
                found_color_images.extend(results)

            unique_color_images = list(set(found_color_images))
            if unique_color_images:
                yield "<h4>Renk Görselleri</h4>".encode("utf-8")
                yield from self._render_side_by_side_images(unique_color_images, context="color")
                yield "<br>".encode("utf-8")
            else:
                yield "Renk görselleri bulunamadı.<br><br>".encode("utf-8")

            if trim_name:
                filter_jant = f"{assistant_name} {trim_name} jant"
            else:
                filter_jant = f"{assistant_name} jant"

            jant_images = self.image_manager.filter_images_multi_keywords(filter_jant)
            if jant_images:
                yield "<h4>Jant Görselleri (Standart + Opsiyonel)</h4>".encode("utf-8")
                yield from self._render_side_by_side_images(jant_images, context="jant")
            else:
                yield "Jant görselleri bulunamadı.<br><br>".encode("utf-8")
            return

        if any(kw in lower_msg for kw in ["iç", "ic"]):
            if not assistant_id or not assistant_name:
                save_to_db(user_id, user_message, "İç görseller için model seçilmemiş.")
                yield "Hangi modelin iç görsellerini görmek istersiniz? (Fabia, Scala, Kamiq vb.)\n".encode("utf-8")
                return

            trim_name = self.user_states[user_id]["current_trim"]
            if "premium" in lower_msg:
                trim_name = "premium"
            elif "monte carlo" in lower_msg:
                trim_name = "monte carlo"
            elif "elite" in lower_msg:
                trim_name = "elite"

            self.user_states[user_id]["current_trim"] = trim_name

            categories = [
                "direksiyon simidi",
                "döşeme",
                "koltuk",
                "multimedya"
            ]

            model_and_trim_title = assistant_name.title()
            if trim_name:
                model_and_trim_title += f" {trim_name.title()}"
            model_and_trim_title += " İç Görselleri"

            save_to_db(user_id, user_message, f"{model_and_trim_title} listeleniyor.")
            yield f"<b>{model_and_trim_title}</b><br><br>".encode("utf-8")

            any_image_found = False
            for cat in categories:
                if trim_name:
                    full_filter = f"{assistant_name} {trim_name} {cat}"
                else:
                    full_filter = f"{assistant_name} {cat}"

                found_images = self.image_manager.filter_images_multi_keywords(full_filter)
                yield f"<h4>{cat.title()} Görselleri</h4>".encode("utf-8")
                if found_images:
                    any_image_found = True
                    yield from self._render_side_by_side_images(found_images, context="ic")
                    yield "<br>".encode("utf-8")
                else:
                    yield f"{cat.title()} görseli bulunamadı.<br><br>".encode("utf-8")

            if not any_image_found:
                yield "Herhangi bir iç görsel bulunamadı.<br>".encode("utf-8")
            return

        trimmed_msg = user_message.strip().lower()
        if trimmed_msg in ["evet", "evet.", "evet!", "evet?", "evet,"]:
            pending_colors = self.user_states[user_id].get("pending_color_images", [])
            if pending_colors:
                asst_name = assistant_name.lower() if assistant_name else "scala"
                all_found_images = []
                for clr in pending_colors:
                    keywords = f"{asst_name} {clr}"
                    results = self.image_manager.filter_images_multi_keywords(keywords)
                    all_found_images.extend(results)

                if not all_found_images:
                    save_to_db(user_id, user_message, "Bu renklerle ilgili görsel bulunamadı.")
                    yield "Bu renklerle ilgili görsel bulunamadı.\n".encode("utf-8")
                    return

                save_to_db(user_id, user_message, "Renk görselleri listelendi (evet).")
                yield "<b>İşte seçtiğiniz renk görselleri:</b><br>".encode("utf-8")
                yield from self._render_side_by_side_images(all_found_images, context=None)
                self.user_states[user_id]["pending_color_images"] = []
                return

        # Özel örnek: Fabia Premium vs Monte Carlo
        if ("fabia" in lower_msg
            and "premium" in lower_msg
            and "monte carlo" in lower_msg
            and self.utils.is_image_request(user_message)):
            fabia_pairs = [
                ("Fabia_Premium_Ay_Beyazı.png", "Fabia_Monte_Carlo_Ay_Beyazı.png"),
            ]
            save_to_db(user_id, user_message, "Fabia Premium vs Monte Carlo görsel karşılaştırma.")
            yield """
<div style='display: flex; flex-direction: row; gap: 20px;'>
""".encode("utf-8")
            for left_img, right_img in fabia_pairs:
                left_url = f"/static/images/{left_img}"
                right_url = f"/static/images/{right_img}"
                left_title = left_img.replace("_", " ").replace(".png", "")
                right_title = right_img.replace("_", " ").replace(".png", "")

                html_pair = f"""
<div style="display: flex; align-items: center; gap: 10px;">
  <div>
    <div style="font-weight: bold; margin-bottom: 6px;">{left_title}</div>
    <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{left_url}')">
      <img src="{left_url}" alt="{left_title}" style="max-width: 350px;" />
    </a>
  </div>
  <div>
    <div style="font-weight: bold; margin-bottom: 6px;">{right_title}</div>
    <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{right_url}')">
      <img src="{right_url}" alt="{right_title}" style="max-width: 350px;" />
    </a>
  </div>
</div>
"""
                yield html_pair.encode("utf-8")
            yield "</div>".encode("utf-8")
            return

        if self.utils.is_image_request(user_message):
            if not assistant_id:
                save_to_db(user_id, user_message, "Henüz asistan seçilmedi, görsel yok.")
                yield "Henüz bir asistan seçilmediği için görsel gösteremiyorum.\n".encode("utf-8")
                return

            if not assistant_name:
                save_to_db(user_id, user_message, "Asistan adını bulamadım.")
                yield "Asistan adını bulamadım.\n".encode("utf-8")
                return

            trim_name = self.user_states[user_id]["current_trim"]
            if "premium" in lower_msg:
                trim_name = "premium"
            elif "monte carlo" in lower_msg:
                trim_name = "monte carlo"
            elif "elite" in lower_msg:
                trim_name = "elite"
            self.user_states[user_id]["current_trim"] = trim_name

            if any(x in lower_msg for x in ["elite", "premium", "monte carlo"]):
                context = "model"
            elif any(x in lower_msg for x in ["standart", "opsiyonel"]):
                context = "donanim"
            else:
                context = None

            if trim_name:
                keyword = self.utils.extract_image_keyword(user_message, f"{assistant_name} {trim_name}")
                if keyword:
                    full_filter = f"{assistant_name} {trim_name} {keyword}"
                else:
                    full_filter = f"{assistant_name} {trim_name}"
            else:
                keyword = self.utils.extract_image_keyword(user_message, assistant_name)
                if keyword:
                    full_filter = f"{assistant_name} {keyword}"
                else:
                    full_filter = assistant_name

            found_images = self.image_manager.filter_images_multi_keywords(full_filter)
            if not found_images:
                save_to_db(user_id, user_message, f"'{full_filter}' için görsel yok.")
                yield f"'{full_filter}' için uygun bir görsel bulamadım.\n".encode("utf-8")
                return

            save_to_db(user_id, user_message, f"{len(found_images)} görsel bulundu ve listelendi.")
            yield from self._render_side_by_side_images(found_images, context=context)
            return

        # ------------------------------------------------------------
        # Opsiyonel tablolar
        # ------------------------------------------------------------
        user_models_in_msg = self._extract_models(user_message)
        user_trims_in_msg = set()
        if "premium" in lower_msg:
            user_trims_in_msg.add("premium")
        if "elite" in lower_msg:
            user_trims_in_msg.add("elite")
        if "monte carlo" in lower_msg:
            user_trims_in_msg.add("monte carlo")

        if len(user_models_in_msg) >= 2 or len(user_trims_in_msg) >= 2:
            self.logger.info("Birden çok model/donanım tespit edildi. Tekil tabloyu atlıyoruz.")
        else:
            if "fabia" in lower_msg and "opsiyonel" in lower_msg:
                if "premium" in lower_msg:
                    save_to_db(user_id, user_message, "Fabia Premium opsiyonel tablosu.")
                    yield FABIA_PREMIUM_MD.encode("utf-8")
                    return
                elif "monte carlo" in lower_msg:
                    save_to_db(user_id, user_message, "Fabia Monte Carlo opsiyonel tablosu.")
                    yield FABIA_MONTE_CARLO_MD.encode("utf-8")
                    return
                else:
                    yield (
                        "Fabia modelinde hangi donanımın opsiyonel bilgilerini görmek istersiniz? "
                        "(Premium / Monte Carlo)\n"
                    ).encode("utf-8")
                    return

            if "kamiq" in lower_msg and "opsiyonel" in lower_msg:
                if "elite" in lower_msg:
                    save_to_db(user_id, user_message, "Kamiq Elite opsiyonel tablosu.")
                    yield KAMIQ_ELITE_MD.encode("utf-8")
                    return
                elif "premium" in lower_msg:
                    save_to_db(user_id, user_message, "Kamiq Premium opsiyonel tablosu.")
                    yield KAMIQ_PREMIUM_MD.encode("utf-8")
                    return
                elif "monte carlo" in lower_msg:
                    save_to_db(user_id, user_message, "Kamiq Monte Carlo opsiyonel tablosu.")
                    yield KAMIQ_MONTE_CARLO_MD.encode("utf-8")
                    return
                else:
                    yield (
                        "Kamiq modelinde hangi donanımın opsiyonel bilgilerini görmek istersiniz? "
                        "(Elite / Premium / Monte Carlo)\n"
                    ).encode("utf-8")
                    return

            if "scala" in lower_msg and "opsiyonel" in lower_msg:
                if "elite" in lower_msg:
                    save_to_db(user_id, user_message, "Scala Elite opsiyonel tablosu.")
                    yield SCALA_ELITE_MD.encode("utf-8")
                    return
                elif "premium" in lower_msg:
                    save_to_db(user_id, user_message, "Scala Premium opsiyonel tablosu.")
                    yield SCALA_PREMIUM_MD.encode("utf-8")
                    return
                elif "monte carlo" in lower_msg:
                    save_to_db(user_id, user_message, "Scala Monte Carlo opsiyonel tablosu.")
                    yield SCALA_MONTE_CARLO_MD.encode("utf-8")
                    return
                else:
                    yield (
                        "Scala modelinde hangi donanımın opsiyonel bilgilerini görmek istersiniz? "
                        "(Elite / Premium / Monte Carlo)\n"
                    ).encode("utf-8")
                    return

        # ------------------------------------------------------------
        # Normal ChatCompletion (OpenAI)
        # ------------------------------------------------------------
        if not assistant_id:
            save_to_db(user_id, user_message, "Uygun asistan bulunamadı.")
            yield "Üzgünüm, herhangi bir model hakkında yardımcı olamıyorum.\n".encode("utf-8")
            return

        if "conversations" not in self.user_states[user_id]:
            self.user_states[user_id]["conversations"] = {}
        if assistant_id not in self.user_states[user_id]["conversations"]:
            self.user_states[user_id]["conversations"][assistant_id] = []

        conversation_list = self.user_states[user_id]["conversations"][assistant_id]
        conversation_list.append({"role": "user", "content": user_message})

        system_prompt = self.SYSTEM_PROMPTS.get(assistant_id, "Sen bir Škoda asistanısın.")
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",  # veya "gpt-3.5-turbo"
                messages=[
                    {"role": "system", "content": system_prompt}
                ] + conversation_list,
                temperature=0.7,
                stream=True
            )

            assistant_response_str = ""
            for chunk in response:
                if "choices" in chunk and len(chunk["choices"]) > 0:
                    delta = chunk["choices"][0]["delta"]
                    if "content" in delta:
                        text_part = delta["content"]
                        assistant_response_str += text_part
                        yield text_part.encode("utf-8")

            conversation_list.append({"role": "assistant", "content": assistant_response_str})
            conversation_id = save_to_db(user_id, user_message, assistant_response_str)
            yield f"\n[CONVERSATION_ID={conversation_id}]".encode("utf-8")

            if "görsel olarak görmek ister misiniz?" in assistant_response_str.lower():
                detected_colors = self.utils.parse_color_names(assistant_response_str)
                if detected_colors:
                    self.user_states[user_id]["pending_color_images"] = detected_colors

        except Exception as e:
            self.logger.error(f"Yanıt oluşturma hatası: {str(e)}")
            save_to_db(user_id, user_message, f"Hata: {str(e)}")
            yield f"Bir hata oluştu: {str(e)}\n".encode("utf-8")

    def _render_side_by_side_images(self, images, context="model"):
        if not images:
            yield "Bu kriterlere ait görsel bulunamadı.\n".encode("utf-8")
            return

        mc_std = [
            img for img in images
            if "monte" in img.lower()
               and "carlo" in img.lower()
               and "standart" in img.lower()
        ]
        pm_ops = [
            img for img in images
            if "premium" in img.lower()
               and "opsiyonel" in img.lower()
        ]
        others = [img for img in images if img not in mc_std and img not in pm_ops]

        # Ana çerçeve
        yield """
<div style="display: flex; justify-content: space-between; gap: 60px;">
  <!-- SOL SÜTÜN: MONTE CARLO STANDART -->
  <div style="flex:1;">
""".encode("utf-8")

        if mc_std:
            left_title = os.path.splitext(mc_std[0])[0].replace("_", " ")
            yield f"<h3>{left_title}</h3>".encode("utf-8")

            for img_file in mc_std:
                img_url = f"/static/images/{img_file}"
                base_name = os.path.splitext(img_file)[0].replace("_", " ")
                block_html = f"""
<div style="text-align: center; margin-bottom:20px;">
  <div style="font-weight: bold; margin-bottom: 6px;">{base_name}</div>
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}')">
    <img src="{img_url}" alt="{base_name}" style="max-width: 350px; cursor:pointer;" />
  </a>
</div>
"""
                yield block_html.encode("utf-8")
        else:
            yield "<h3>Monte Carlo Standart Görseli Yok</h3>".encode("utf-8")

        yield "</div>".encode("utf-8")

        yield """
  <div style="flex:1;">
""".encode("utf-8")

        if pm_ops:
            right_title = os.path.splitext(pm_ops[0])[0].replace("_", " ")
            yield f"<h3>{right_title}</h3>".encode("utf-8")

            for img_file in pm_ops:
                img_url = f"/static/images/{img_file}"
                base_name = os.path.splitext(img_file)[0].replace("_", " ")
                block_html = f"""
<div style="text-align: center; margin-bottom:20px;">
  <div style="font-weight: bold; margin-bottom: 6px;">{base_name}</div>
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}')">
    <img src="{img_url}" alt="{base_name}" style="max-width: 350px; cursor:pointer;" />
  </a>
</div>
"""
                yield block_html.encode("utf-8")
        else:
            yield "<h3>Premium Opsiyonel Görseli Yok</h3>".encode("utf-8")

        yield """
  </div> <!-- Sağ sütun kapanış -->
</div> <!-- Ana flex kapanış -->
""".encode("utf-8")

        if others:
            yield "<hr><b>Diğer Görseller:</b><br>".encode("utf-8")
            yield '<div style="display: flex; flex-wrap: wrap; gap: 20px;">'.encode("utf-8")
            for img_file in others:
                img_url = f"/static/images/{img_file}"
                base_name = os.path.splitext(img_file)[0].replace("_", " ")
                block_html = f"""
<div style="text-align: center; margin: 5px;">
  <div style="font-weight: bold; margin-bottom: 8px;">{base_name}</div>
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}')">
    <img src="{img_url}" alt="{base_name}" style="max-width: 300px; cursor:pointer;" />
  </a>
</div>
"""
                yield block_html.encode("utf-8")
            yield "</div>".encode("utf-8")

    def run(self, debug=True):
        self.app.run(debug=debug)

    def shutdown(self):
        self.stop_worker = True
        self.worker_thread.join(5.0)
        self.logger.info("ChatbotAPI shutdown complete.")
