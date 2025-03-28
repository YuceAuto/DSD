import os
import time
import logging
import re
import openai  # OpenAI 1.0.0+ kütüphanesi
import difflib
import queue
import threading

from flask import Flask, request, jsonify, render_template, session, Response
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
        self.app = Flask(
            __name__,
            static_folder=os.path.join(os.getcwd(), static_folder),
            template_folder=os.path.join(os.getcwd(), template_folder)
        )
        CORS(self.app)
        self.app.secret_key = secrets.token_hex(16)

        self.logger = logger if logger else self._setup_logger()

        create_tables()

        # OpenAI API Anahtarı
        openai.api_key = os.getenv("OPENAI_API_KEY")

        self.config = Config()
        self.utils = Utils()

        self.image_manager = ImageManager(images_folder=os.path.join(static_folder, "images"))
        self.image_manager.load_images()

        self.markdown_processor = MarkdownProcessor()

        self.ASSISTANT_CONFIG = self.config.ASSISTANT_CONFIG
        self.ASSISTANT_NAME_MAP = self.config.ASSISTANT_NAME_MAP

        self.SESSION_TIMEOUT = 30 * 60

        self.user_states = {}

        self.fuzzy_cache = {}
        self.fuzzy_cache_queue = queue.Queue()

        self.stop_worker = False
        self.worker_thread = threading.Thread(target=self._background_db_writer, daemon=True)
        self.worker_thread.start()

        self.CACHE_EXPIRY_SECONDS = 3600
        self.CROSS_ASSISTANT_CACHE = True

        # Burada system promptlarınızı tanımlıyorsunuz.
        self.SYSTEM_PROMPTS = {
            "asst_fw6RpRp8PbNiLUR1KB2XtAkK": """(Sen bir yardımcı asistansın.
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
Kamiq, geniş iç mekanı, modern tasarımı ve zengin donanım seçenekleriyle her türlü kullanıcı ihtiyacına hitap eder. Daha detaylı bilgi için sorularınızı belirtebilirsiniz.)""",
            "asst_yeDl2aiHy0uoGGjHRmr2dlYB": """(Sen bir yardımcı asistansın.
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

Eğer daha fazla bilgi almak istediğiniz özel bir konu (örneğin, donanımlar, renk seçenekleri, motor özellikleri) varsa, size daha detaylı yardımcı olabilirim!)""",
            "asst_njSG1NVgg4axJFmvVYAIXrpM": """(Sen bir yardımcı asistansın.
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
)""",
            "asst_hiGn8YC08xM3amwG0cs2A3SN": """(All Models ile ilgili sistem prompt)"""
        }

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
            session.pop('last_activity', None)
            return render_template("index.html")

        @self.app.route("/ask", methods=["POST"])
        def ask():
            """
            Burada response'u stream halinde döndürürüz.
            """
            try:
                data = request.get_json()
            except Exception as e:
                self.logger.error(f"JSON parse error: {e}")
                return jsonify({"error": "Invalid JSON"}), 400

            user_message = data.get("question", "")
            user_id = data.get("user_id", "default_user")

            # Normalde `_ask` içinde parse + _find_fuzzy_cached_answer + model tespiti vs. yapardınız.
            # Ama tüm mantığı `_ask` yerine `_generate_streamed_response`'e de koyabilirsiniz.
            # Örnek olarak, mantığı burada "manüel" tutalım:
            # 1) Session last_activity
            if 'last_activity' not in session:
                session['last_activity'] = time.time()
            else:
                session['last_activity'] = time.time()

            if not user_message:
                return jsonify({"response": "Please enter a question."})

            # Tek seferde, tıpkı eskisi gibi user_message'ı process ediyoruz
            corrected_message = self._correct_typos(user_message)

            def streaming_generator():
                """
                Bu generator, chunk chunk yanıt üretecek.
                """
                # Yine model tespiti, conversation list, system prompt vs:
                assistant_id = self._determine_assistant_id(corrected_message, user_id)
                is_image_req = self.utils.is_image_request(corrected_message)

                # Fuzzy cache var mı yok mu? (Metin akışı vs. karmaşık, isterseniz kapatabilirsiniz.)
                # Biz bu örnekte direk stream'e geçiyoruz:
                yield from self._generate_response_stream(corrected_message, user_id, assistant_id, is_image_req)

            # Flask'ta chunked response:
            return Response(streaming_generator(), mimetype="text/plain")

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
                return jsonify({"error": "No conversation_id"}), 400
            try:
                update_customer_answer(conv_id, 1)
                return jsonify({"status": "ok"}), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500

    def _background_db_writer(self):
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

                self.logger.info(f"[BG] Kaydedildi -> {user_id}, {q_lower[:30]}...")
                self.fuzzy_cache_queue.task_done()

            except queue.Empty:
                pass
            except Exception as e:
                self.logger.error(f"[BG] DB write error: {e}")
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

    def _determine_assistant_id(self, corrected_message, user_id):
        """
        Eskiden _ask'ta yaptığınız 'model tespiti' mantığını buraya taşıdık.
        """
        user_models = self._extract_models(corrected_message)
        user_trims = set()
        msg_lower = corrected_message.lower()
        if "premium" in msg_lower:
            user_trims.add("premium")
        if "monte carlo" in msg_lower:
            user_trims.add("monte carlo")
        if "elite" in msg_lower:
            user_trims.add("elite")

        old_assistant_id = self.user_states.get(user_id, {}).get("assistant_id")
        new_assistant_id = None

        if len(user_models) >= 2 or len(user_trims) >= 2:
            new_assistant_id = "asst_hiGn8YC08xM3amwG0cs2A3SN"  # All Models
        else:
            if len(user_models) == 0:
                if old_assistant_id:
                    new_assistant_id = old_assistant_id
                else:
                    new_assistant_id = "asst_fw6RpRp8PbNiLUR1KB2XtAkK"  # default Kamiq
            else:
                single_model = list(user_models)[0]
                for aid, keywords in self.ASSISTANT_CONFIG.items():
                    if single_model.lower() in [k.lower() for k in keywords]:
                        new_assistant_id = aid
                        break
                if not new_assistant_id:
                    new_assistant_id = "asst_fw6RpRp8PbNiLUR1KB2XtAkK"

        # Save in user_states
        if user_id not in self.user_states:
            self.user_states[user_id] = {}
        self.user_states[user_id]["assistant_id"] = new_assistant_id

        return new_assistant_id

    def _generate_response_stream(self, user_message, user_id, assistant_id, is_image_req=False):
        """
        Bu fonksiyon, OpenAI API'ye `stream=True` diyerek bağlanır,
        chunk chunk gelen veriyi yield eder.

        Not: is_image_req vs. burada devre dışı bıraktık; isterseniz ek kontrol ekleyebilirsiniz.
        """
        self.logger.info(f"[_generate_response_stream] User({user_id}) => {user_message}")

        if not assistant_id:
            # yield error
            yield "Üzgünüm, herhangi bir model hakkında yardımcı olamıyorum.\n"
            return

        # Konuşma dizisi
        if user_id not in self.user_states:
            self.user_states[user_id] = {}
        if "conversations" not in self.user_states[user_id]:
            self.user_states[user_id]["conversations"] = {}
        if assistant_id not in self.user_states[user_id]["conversations"]:
            self.user_states[user_id]["conversations"][assistant_id] = []

        conversation_list = self.user_states[user_id]["conversations"][assistant_id]
        conversation_list.append({"role": "user", "content": user_message})

        system_prompt = self.SYSTEM_PROMPTS.get(assistant_id, "Sen bir Škoda asistanısın.")

        partial_text = ""  # gelen chunk'ları biriktirip DB'ye kaydedebilmek için

        try:
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "system", "content": system_prompt}] + conversation_list,
                temperature=0.7,
                stream=True  # <-- ÖNEMLİ
            )

            # Her chunk geldiğinde yield ediyoruz
            for chunk in response:
                if not chunk or not chunk.choices or len(chunk.choices) == 0:
                    continue
                delta = chunk.choices[0].delta
                if hasattr(delta, "content"):
                    text_chunk = delta.content
                    partial_text += text_chunk
                    yield text_chunk  # anlık ekrana yolluyoruz

            # Stream bitti => Tüm metin partial_text'te
            conversation_list.append({"role": "assistant", "content": partial_text})
            conversation_id = save_to_db(user_id, user_message, partial_text)

            # Ek olarak, chunk sonunda "CONVERSATION_ID" eklemek isterseniz:
            yield f"\n[CONVERSATION_ID={conversation_id}]"

        except Exception as e:
            err_msg = f"Bir hata oluştu: {str(e)}\n"
            self.logger.error(f"Stream error: {err_msg}")
            save_to_db(user_id, user_message, f"Hata: {str(e)}")
            yield err_msg

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
        # vb. kelime düzeltmeleri
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
        """
        Flask "/ask" endpoint metodu.
        Burada stream=False ile tek seferde yanıt döndürüyoruz.
        """
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

        # Session last_activity
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

        if user_id not in self.user_states:
            self.user_states[user_id] = {}
            self.user_states[user_id]["conversations"] = {}

        old_assistant_id = self.user_states[user_id].get("assistant_id")
        new_assistant_id = None

        # Model tespiti
        if len(user_models) >= 2 or len(user_trims) >= 2:
            new_assistant_id = "asst_hiGn8YC08xM3amwG0cs2A3SN"
        else:
            if len(user_models) == 0:
                if old_assistant_id:
                    new_assistant_id = old_assistant_id
                else:
                    new_assistant_id = "asst_fw6RpRp8PbNiLUR1KB2XtAkK"  # default Kamiq
            else:
                # 1 model
                single_model = list(user_models)[0]
                for aid, keywords in self.ASSISTANT_CONFIG.items():
                    if single_model.lower() in [k.lower() for k in keywords]:
                        new_assistant_id = aid
                        break
                if not new_assistant_id:
                    new_assistant_id = "asst_fw6RpRp8PbNiLUR1KB2XtAkK"

        self.user_states[user_id]["assistant_id"] = new_assistant_id
        assistant_id = new_assistant_id

        # Görsel istek mi?
        is_image_req = self.utils.is_image_request(corrected_message)

        # Fuzzy cache
        cached_answer, matched_question, found_asst_id = (None, None, None)
        if not is_image_req:
            cached_answer, matched_question, found_asst_id = self._find_fuzzy_cached_answer(
                user_id,
                corrected_message,
                assistant_id,
                threshold=0.8,
                allow_cross_assistant=False
            )

        if cached_answer and not is_image_req:
            # Direkt cache
            answer_text = cached_answer.decode("utf-8")
            return self.app.response_class(cached_answer, mimetype="text/plain")

        # Eğer görsel vs. istekler varsa, _render_side_by_side_images(...)
        # ...
        # Yoksa ChatCompletion'a gidiyoruz:
        final_bytes = self._generate_response(corrected_message, user_id)

        # Cache
        if not is_image_req:
            self._store_in_fuzzy_cache(user_id, corrected_message, final_bytes, assistant_id)

        return self.app.response_class(final_bytes, mimetype="text/plain")

    def _generate_response(self, user_message, user_id):
        """
        Asıl OpenAI çağrısı 'stream=False'.
        """
        self.logger.info(f"[_generate_response] Kullanıcı ({user_id}): {user_message}")

        assistant_id = self.user_states[user_id].get("assistant_id")
        assistant_name = self.ASSISTANT_NAME_MAP.get(assistant_id, "")

        if not assistant_id:
            save_to_db(user_id, user_message, "Uygun asistan bulunamadı.")
            return "Üzgünüm, herhangi bir model hakkında yardımcı olamıyorum.\n".encode("utf-8")

        if "conversations" not in self.user_states[user_id]:
            self.user_states[user_id]["conversations"] = {}
        if assistant_id not in self.user_states[user_id]["conversations"]:
            self.user_states[user_id]["conversations"][assistant_id] = []

        conversation_list = self.user_states[user_id]["conversations"][assistant_id]
        conversation_list.append({"role": "user", "content": user_message})

        system_prompt = self.SYSTEM_PROMPTS.get(assistant_id, "Sen bir Škoda asistanısın.")
        try:
            # OpenAI 1.0.0+ API
            response = openai.chat.completions.create(
                model="gpt-4",  # veya "gpt-3.5-turbo"
                messages=[{"role": "system", "content": system_prompt}] + conversation_list,
                temperature=0.7,
                stream=False  # Tek parçada dön
            )

            assistant_response_str = response["choices"][0]["message"]["content"]

            # Sohbet geçmişine ekle
            conversation_list.append({"role": "assistant", "content": assistant_response_str})

            # DB'ye kaydet
            conversation_id = save_to_db(user_id, user_message, assistant_response_str)

            final_text = assistant_response_str + f"\n[CONVERSATION_ID={conversation_id}]"
            return final_text.encode("utf-8")

        except Exception as e:
            self.logger.error(f"Yanıt oluşturma hatası: {str(e)}")
            save_to_db(user_id, user_message, f"Hata: {str(e)}")
            return f"Bir hata oluştu: {str(e)}\n".encode("utf-8")

    def _render_side_by_side_images(self, images, context="model"):
        """
        Görsel istekleri işleyerek HTML döndüren fonksiyon (kısaltılmış).
        """
        if not images:
            yield "Bu kriterlere ait görsel bulunamadı.\n".encode("utf-8")
            return

        # Örnek 2 sütun + "others"
        # ...

    

    def run(self, debug=True):
        self.app.run(debug=debug)

    def shutdown(self):
        self.stop_worker = True
        self.worker_thread.join(5.0)
        self.logger.info("ChatbotAPI shutdown complete.")

