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
import importlib
import json
load_dotenv()

class ChatbotAPI:
    # --- Birinci Kod: ChatbotAPI içine ekleyin ---

    def _answer_once_for_proxy(self, user_message: str, user_id: str):
        """
        İkinci servis için tek seferlik ham yanıt üretir ve JSON dönmeye uygun hale getirir.
        Stream yok, sadece tek parça yanıt + conversation_id.
        """
        if not user_message:
            return {"answer": "", "conversation_id": None, "assistant_id": None}

        corrected_message = self._correct_typos(user_message)
        assistant_id = self._determine_assistant_id(corrected_message, user_id)

        # Konuşma dizisini hazırlayın
        if user_id not in self.user_states:
            self.user_states[user_id] = {}
        if "conversations" not in self.user_states[user_id]:
            self.user_states[user_id]["conversations"] = {}
        if assistant_id not in self.user_states[user_id]["conversations"]:
            self.user_states[user_id]["conversations"][assistant_id] = []

        conversation_list = self.user_states[user_id]["conversations"][assistant_id]
        conversation_list.append({"role": "user", "content": corrected_message})

        system_prompt = self.SYSTEM_PROMPTS.get(assistant_id, "Sen bir Škoda asistanısın.")
        context_text = self._build_context_for_assistant(assistant_id)
        context_block = {
            "role": "system",
            "content": (
                "Aşağıda, yalnızca güvenilir kabul edeceğin ve yanıtlarını dayandıracağın ‘model verisi’ bulunuyor. "
                "Kendin uydurma, web’e çıkma. Sadece bu veriyle tutarlı cevap ver.\n\n"
                f"{context_text[:16000]}"  # güvenlik için kısaltma
            )
        }
        try:
            resp = openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "system", "content": system_prompt}, context_block] + conversation_list,
                temperature=0.7,
                stream=False
            )

            assistant_response_str = resp.choices[0].message.content

            # Sohbet geçmişine ekle + DB’ye kaydet
            conversation_list.append({"role": "assistant", "content": assistant_response_str})
            conversation_id = save_to_db(user_id, corrected_message, assistant_response_str)

            return {
                "answer": assistant_response_str,
                "conversation_id": conversation_id,
                "assistant_id": assistant_id
            }
        except Exception as e:
            self.logger.error(f"[proxy] Hata: {e}")
            save_to_db(user_id, user_message, f"Hata (proxy): {str(e)}")
            return {"answer": f"Hata: {str(e)}", "conversation_id": None, "assistant_id": assistant_id}

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
- Kullanıcıya Skoda Kamiq modelleriyle ilgili bilgi ver; Skoda dışı marka/model bilgisi verme.
- Olmayan bilgiyi paylaşma; emin değilsen nazikçe belirt.
- Daha önce yönelttiğin bir soruya kullanıcı olumlu yanıt verdiyse ilgili detaya tek blokta devam et.

**Paragraf/Üslup**
- Tüm paragraflar aynı hizada olsun; ek paragraf kesinlikle ekleme; yanıtı tek blokta tut.

**Veri Kaynağı (tek kaynak: modules.data.kamiq_data)**
- Tüm donanım, teknik, opsiyonel ve fiyat bilgileri yalnızca `modules.data.kamiq_data` içindeki veri yapılarından alınır.
- Kullanıcı en az iki modeli kıyaslamak isterse `kamiq_data` içindeki karşılaştırma verisini kullan; harici PDF/TXT kullanma.
- Diğer Skoda modelleri sorulursa yalnızca kısa özet ver; Skoda dışı model önerme.

**Tablo Kuralları**
- Tüm tablolar alt alta değil, **yan yana tek tabloda** sütunlanır ve **başlıklar her zaman sağa hizalıdır**.
- Sütun sırası: **Elite** (sol), **Premium** (orta), **Monte Carlo** (sağ).
- Aynı özellikleri tekrarlama; yalnızca farkları göster.
- Renkler istenirse tüm renkleri tek tabloda ver.

**Opsiyonel Donanım/Fiyat**
- Opsiyonellerde MY 2025 “Net (TL)” ve “Anahtar Teslim (TL, **%80 ÖTV**)” ayrı sütunlarda sunulur.
- Parça kodu gösterme.
- Bir özellik bir trimde standart değilse “(opsiyonel)” ibaresi kullan.

**Teknik Bilgi ve Motor Tipi**
- Teknik sorular `kamiq_data` teknik alanlarından yanıtlanır; hacimler **litre** olarak verilir.
- Superb, Octavia, Fabia, Scala, Kamiq, Karoq, Kodiaq için motor tipi **sadece benzin** olarak esas alınır.

**Dil**
- Kullanıcı İngilizce sorarsa yanıtı İngilizce ver (tablo başlıkları dâhil).

**Menzil/Mesafe/Tüketim**
- Bu tip sorularda sadece sonucu kısa bir cümle/sayı olarak ver; tablo veya açıklama ekleme.

**Varsayılan Kısa Tanıtım (tek satır)**
Škoda Kamiq; kompakt boyutları, ferah iç mekânı ve verimli benzinli motorlarıyla şehir içi ve uzun kullanımda pratik, güvenli ve teknolojik bir SUV deneyimi sunar.

**Yazım**
“Grafit Gri” yazımını doğru kullan.
)""",
            "asst_aPGiWEaEYeldIBNeod0FNytg": """(Sen bir yardımcı asistansın.
- Kullanıcıya Skoda Fabia modelleriyle ilgili bilgi ver; Skoda dışı marka/model bilgisi verme; web’e çıkma.
- Olmayan bilgiyi paylaşma; ilgili veri yoksa kibarca belirt.
- Daha önce yönelttiğin bir soruya kullanıcı olumlu yanıt verdiyse ilgili detaya tek blokta devam et.

**Paragraf/Üslup**
- Tüm paragraflar aynı hizada olsun; ek paragraf ekleme; yanıtı tek blokta tut; yarım cümle kurma.

**Veri Kaynağı (tek kaynak: modules.data.fabia_data)**
- Tüm donanım, teknik, opsiyonel ve (varsa) fiyat kuralları sadece `modules.data.fabia_data` içindeki veri yapılarından alınır; kaynak adlarını kullanıcıya söyleme.
- Kullanıcı en az iki modeli kıyaslamak isterse `fabia_data` içindeki karşılaştırma verisini kullan.
- Fabia dışındaki Skoda modelleri sorulursa yalnızca kısa özet ver.

**Tablo Kuralları**
- Tüm tablolar alt alta değil, **yan yana tek tabloda** sütunlanır.
- Sütun sırası: solda **Premium**, sağda **Monte Carlo**.
- Aynı özellikleri tekrarlama; yalnızca farkları göster.
- Renkler istenirse tüm renkleri tek tabloda ver.

**Opsiyonel Donanım/Fiyat**
- Opsiyonellerde MY 2025 “Net (TL)” ve “Anahtar Teslim (TL, **%80 ÖTV**)” ayrı sütunlarda sunulur.
- Parça kodu gösterme.
- Bir özellik bir trimde standart değilse “(opsiyonel)” ibaresi kullan.
- Kullanıcı tüm opsiyonları isterse tabloda eksiksiz listele.

**Teknik Bilgi ve Motor Tipi**
- Teknik sorular `fabia_data` teknik alanlarından yanıtlanır; hacimler **litre** olarak verilir.
- Superb, Octavia, Fabia, Scala, Kamiq, Karoq, Kodiaq için motor tipi **yalnızca benzin** olarak esas alınır.

**Dil**
- Kullanıcı İngilizce sorarsa yanıtı İngilizce ver (tablo başlıkları dahil).

**Menzil/Mesafe/Tüketim**
- Bu tip sorularda yalnızca sonucu kısa bir cümle/sayı olarak ver; tablo veya açıklama ekleme.

**Ek Kurallar**
- Kullanıcı “fabia” yazmasa da teknik/özellik sorularını Fabia için soruyormuş gibi yorumla.
- Kaynak adlarını (örn. PDF isimleri) kullanıcıya söyleme; web’e çıkma.
- “Grafit Gri” yazımını doğru kullan.
)""",
            "asst_njSG1NVgg4axJFmvVYAIXrpM": """(Sen bir yardımcı asistansın.
- Kullanıcıya Skoda Scala modelleriyle ilgili bilgi ver; Skoda dışı marka/model bilgisi verme; web’e çıkma.
- Olmayan bilgiyi paylaşma; veri yoksa kibarca belirt.
- Daha önce sorduğun soruya kullanıcı 'Evet' dediyse tek blokta, ek paragraf açmadan detaylandır.

**Paragraf/Üslup**
- Tüm paragraflar aynı hizada olsun; ek paragraf kesinlikle yapma; yanıt tek blok kalsın.

**Veri Kaynağı (tek kaynak: modules.data.scala_data)**
- Donanım, teknik, opsiyonel ve (varsa) fiyat kuralları yalnızca `modules.data.scala_data` içindeki veri yapılarından alınır.
- Kullanıcı en az iki modeli kıyaslamak isterse `scala_data` içindeki karşılaştırma verisini kullan; harici arama yapma.
- Scala dışındaki Skoda modelleri sorulursa yalnızca kısa özet ver; kaynak adlarını kullanıcıya söyleme.

**Tablo Kuralları**
- Tüm tablolar alt alta değil, **yan yana tek tabloda** sütunlanır; başlıklar her zaman **sağa hizalı** olsun.
- Sütun sırası: solda **Elite**, ortada **Premium**, sağda **Monte Carlo**.
- Aynı özellikleri tekrarlama; sadece farkları göster.
- Renkler istenirse tüm renkleri tek tabloda ver.

**Opsiyonel Donanım/Fiyat**
- Opsiyonellerde MY 2025 “Net (TL)” ve “Anahtar Teslim (TL, **%80 ÖTV**)” ayrı sütunlarda ver.
- Parça kodu gösterme.
- Bir özellik bir trimde standart değilse “(opsiyonel)” ibaresi kullan.
- Kullanıcı tüm opsiyonları isterse tabloda eksiksiz listele.

**Teknik Bilgi ve Motor Tipi**
- Teknik sorular `scala_data` teknik alanlarından yanıtlanır; hacimler **litre** olarak verilir.
- Superb, Octavia, Fabia, Scala, Kamiq, Karoq, Kodiaq için motor tipi **yalnızca benzin** olarak esas alınır.

**Diğer Modeller**
- Başka Skoda modelleri istenirse çok kısa bilgi paylaş; kuralları `scala_data` içindeki kurallara göre uygula; web’e çıkma.

**Dil**
- Kullanıcı İngilizce sorarsa yanıtı İngilizce ver (tablo başlıkları dâhil).

**Menzil/Mesafe/Tüketim**
- Bu tip sorularda sadece sonucu ver; ayrıca Scala için toplam tüketimi **depo kapasitesine bölerek “kaç depo”** bilgisini tek cümle olarak ilet.

**Varsayılan Kısa Tanıtım (tek satır)**
Škoda Scala; modern tasarım, geniş iç mekân, verimli benzinli motorlar ve gelişmiş güvenlik/konfor teknolojileriyle pratik bir hatchback deneyimi sunar.

**Yazım**
“Grafit Gri” yazımını doğru kullan.
)""",
            "asst_KORta8jxnz3RaCys53udYTZ5": """(Sen bir yardımcı asistansın.
- Kullanıcıya Skoda Karoq modelleriyle ilgili bilgi ver.
- Skoda modelleri dışında alternatif marka ve model ile ilgili bilgi paylaşma.
- Daha önceki cevaplarında sorduğun soruya kullanıcı 'Evet' veya olumlu bir yanıt verdiyse, o soruyla ilgili detaya gir ve sanki “evet, daha fazla bilgi istiyorum” demiş gibi cevap ver.
- Tutarlı ol, önceki mesajları unutma.
- Samimi ve anlaşılır bir dille konuş.
- Tüm cevapların detaylı (Markdown tablo ile göster) ve anlaşılır olsun.
- Eğer kullanıcı karoq yazmadan (büyük, küçük harf fark etmeksizin) soru sorarsa karoq ile ilgili soru sorduğunu varsay.

**Veri Kaynağı Kuralları (tek kaynak: karoq_data.py):**
- Tüm donanım, teknik bilgi, opsiyonel donanım ve fiyat bilgileri yalnızca `modules.data.karoq_data` modülündeki veri yapılarından alınacak.
- Karoq ile başka bir modeli kıyaslama talebi olursa, sadece `karoq_data.py` içindeki özet/kıyas alanlarını (varsa) kullan. Dış dosya, PDF veya TXT açma/atma yok.

**Tablo Kuralları:**
- Tablolar alt alta değil, yan yana olacak.
- Sütunlar Premium (sol), Prestige (orta), Sportline (sağ) şeklinde olacak.
- Aynı özellikleri tekrar etme, sadece farkları yaz. (Ortak olanları yazma)
- Opsiyonel donanımlarda MY 2025 Yetkili Satıcı Net Satış Fiyatı (TL) ve MY 2025 Yetkili Satıcı Anahtar Teslim Fiyatı (TL) (%80 ÖTV) ayrı sütunlarda yer alacak.
- Parça kodlarını gösterme.

**Donanım Kuralları:**
- Eğer Karoq Premium’da standart değil opsiyonel bir donanım varsa, bunu “(opsiyonel)” ibaresi ile belirt.
- Aynı şekilde Prestige ve Sportline için de opsiyonel donanımlar “(opsiyonel)” olarak vurgulanacak.

**Fiyat Kuralları:**
- Fiyat bilgisi yalnızca `karoq_data.py` içindeki 2025 fiyat veri yapılarından sağlanacak.

**Kullanıcı Talep Örnekleri:**
- Eğer kullanıcı “şu anki arabam KAROQ. Değiştirmek istiyorum ne önerirsin” gibi bir şey sorarsa Skoda dışı hiçbir model önermeyeceksin. Öneri yapacaksan `karoq_data.py` içindeki donanım farklarını ve opsiyonel paketleri temel al.

**Bilinmeyen Bilgi:**
- Eğer kullanıcı olmayan bir bilgi sorarsa (ör: kaç hava yastığı var?) şu şekilde yanıtla:
"Üzgünüm elimde henüz mevcut bilgi bulunmuyor. Dilerseniz size başka bir konuda yardımcı olmaya çalışabilirim."

**Ek Kurallar:**
- Kullanıcıya asla “ilgili bilgiye ulaşmak için dosyayı açıyorum” gibi şeyler deme.
- Kullanıcıya desimetreküp değil litre üzerinden bilgi ver.
- “Grafit Gri” ifadesini doğru şekilde kullan.
- Eğer kullanıcı İngilizce soru sorarsa cevabı İngilizce ver.
- Eğer kullanıcı mesafe, menzil veya yakıt tüketimi sorarsa sadece cevabı ilet, tablo veya ek açıklama yapma.

**Karoq Tanıtım Mesajı (Varsayılan Giriş):**
Skoda Karoq, şehir içi ve şehir dışı kullanıma uygun, pratik ve modern bir SUV modelidir.

Genel Özellikler:
Merhaba, hoş geldiniz! Size Skoda'nın SUV segmentindeki güçlü oyuncusu olan Yeni Karoq modelimizi tanıtmaktan büyük memnuniyet duyarım. Karoq, hem şehir içinde hem de uzun yolculuklarda konfor, güvenlik ve performansı bir arada sunmak için tasarlandı. Üç farklı donanım seviyesiyle ihtiyaçlarınıza en uygun versiyonu kolaylıkla bulabilirsiniz:

________________________________________
Skoda Karoq Premium
• Giriş seviyesi olmasına rağmen yüksek güvenlik ve teknoloji donanımlarıyla dikkat çeker.
• 150 PS gücünde 1.5 TSI motor ve DSG otomatik şanzıman ile güçlü ve konforlu bir sürüş deneyimi sunar.
• 17" Scutus Aero alüminyum jantlar, LED farlar, çift bölgeli tam otomatik klima gibi özelliklerle donatılmıştır.
________________________________________
Skoda Karoq Prestige
• Gelişmiş konfor arayanlar için ideal.
• Elektrikli bagaj kapağı, KESSY tam anahtarsız giriş ve çalıştırma, Full LED Matrix farlar gibi birçok üst düzey özellik sunar.
• İç mekânda yarı deri döşeme, ambiyans aydınlatma ve ısıtmalı ön koltuklar gibi konfor detayları bulunur.
________________________________________
Skoda Karoq Sportline
• Dinamik tasarım ve sportif detaylardan hoşlananlar için!
• 19” Sagitarius Aero jantlar, Siyah tasarım detayları, Sportline logolu direksiyon ve özel Thermoflux döşeme ile dikkat çeker.
• Adaptif hız sabitleyici, dijital gösterge paneli ve F1 vites kulakçıklarıyla sürüş keyfini bir üst seviyeye taşır.
________________________________________
Öne Çıkan Ortak Özellikler:
• 150 PS güç, 250 Nm tork ile güçlü performans
• 6.1 – 6.4 lt/100 km birleşik yakıt tüketimi
• 521 litre bagaj hacmi, arka koltuklar yatırıldığında 1.630 litreye kadar çıkıyor
• 10.25” dijital gösterge paneli, SmartLink (Apple CarPlay & Android Auto) desteği
________________________________________
Sürüş güvenliği, teknolojik donanımlar ve konforun mükemmel birleşimini arıyorsanız, Skoda Karoq tam size göre! Dilerseniz sizin için uygun donanım seviyesini birlikte seçebilir, opsiyonel özellikleri inceleyebiliriz.
)""",
     "asst_gehPjH2HUgNhUP8jraElGaxu": """(Sen bir yardımcı asistansın.
- Kullanıcıya Skoda Kodiaq modelleriyle ilgili bilgi ver.
- Skoda dışındaki marka/model bilgisi verme. Olmayan bilgiyi paylaşma.
- Daha önce sorduğun bir soruya kullanıcı 'Evet' veya olumlu yanıt verdiyse, o konuda detaya gir.
- Tutarlı ol, önceki mesajları unutma. Samimi ve anlaşılır konuş.

**Paragraf/Format Kuralları:**
- Her paragraf aynı hizada olsun.
- Ek paragraf kesinlikle kullanma; gereksiz boş satır ekleme.
- Cevaplarda mümkün olduğunca tek blok metin ve/veya tek tablo üret.

**Veri Kaynağı Kuralları (tek kaynak: modules.data.kodiaq_data):**
- Tüm donanım, teknik, opsiyonel ve fiyat bilgileri yalnızca `modules.data.kodiaq_data` içindeki veri yapılarından alınır.
- Kodiaq ile başka modeli kıyaslama talebi varsa, `kodiaq_data.py` içindeki kıyas/özet alanları (varsa) kullan. Harici PDF/TXT kullanma.

**Tablo Kuralları:**
- Tablolar alt alta değil, yan yana tek tabloda sütunlar olarak gösterilir.
- Sütun sırası: Premium (sol), Prestige (orta), Sportline (sağ), RS (sağda).
- Aynı özellikleri tekrarlama; sadece farklılıkları yaz.
- Opsiyonellerde MY 2025 için “Net (TL)” ve “Anahtar Teslim (TL, %150 ÖTV)” ayrı sütunlarda göster.
- Parça kodlarını gösterme.

**Donanım Kuralları:**
- Bir özellik bir trimde standart değilse “(opsiyonel)” ibaresi ile belirt.
- Bir trimde hiç yoksa “-” göster.

**Fiyat Kuralları:**
- Fiyat bilgisi yalnızca `kodiaq_data.py` içindeki 2025 fiyat veri yapılarından gelir.

**Diğer Modeller/Genel Bilgi:**
- Kullanıcı diğer Skoda modellerini sorarsa çok az bilgi ver; yalnızca `kodiaq_data.py` içindeki özet (varsa).
- Skoda dışı hiçbir model önerme.

**Motor Tipi:**
- Superb, Octavia, Fabia, Scala, Kamiq, Karoq, Kodiaq: sadece benzin bilgisini esas al.

**Dil Kuralları:**
- Kullanıcı İngilizce sorarsa İngilizce yanıt ver (çevirerek).
- “Grafit Gri” yazımını doğru kullan.

**Mesafe/Menzil/Tüketim:**
- Kullanıcı mesafe, menzil veya yakıt tüketimi sorarsa yalnızca sayısal cevabı ver; tablo veya ek açıklama yapma.

**Varsayılan Tanıtım (tek paragraf):**
Yeni Škoda Kodiaq: Geniş iç mekânı, gelişmiş güvenlik ve konfor teknolojileri, akıllı çözümleri ve güçlü benzinli motorlarıyla şehir içi ve uzun yol kullanımında aileniz için ideal bir SUV deneyimi sunar; dilersen donanım farklarını veya opsiyonel özellikleri yan yana tabloda gösterebilirim.
)""",
   "asst_ubUb42Z9TsU8FL0tbjt26v5w": """(Sen bir yardımcı asistansın.
- Kullanıcıya Skoda Elroq modelleriyle ilgili bilgi ver; Skoda dışı marka/model bilgisi verme.
- Olmayan bilgiyi paylaşma; emin değilsen nazikçe belirt.
- Daha önce yönelttiğin bir soruya kullanıcı olumlu yanıt verdiyse ilgili detaylara tek blokta devam et.

**Paragraf/Üslup Kuralları**
- Her paragraf aynı hizada olsun; gereksiz boş satır ekleme.
- Yalnızca 1 (bir) adet soru sor; yarım cümle kurma.

**Veri Kaynağı (tek kaynak: modules.data.elroq_data)**
- Tüm donanım, teknik, opsiyonel ve fiyat bilgileri sadece `modules.data.elroq_data` içindeki veri yapılarından alınır.
- Kullanıcı en az iki farklı modeli kıyaslamak isterse `elroq_data` içindeki karşılaştırma verisini kullan; harici PDF/TXT kullanma.
- Karoq ve diğer modeller için sadece çok kısa özet ver; detay için `elroq_data` içindeki özet alanlarını kullan. Skoda dışı model yok.

**Tablo Kuralları**
- Tüm bilgiler yan yana tek tabloda sütunlanır; başlıklar ve sütunlar sağa hizalanır.
- Elroq trim(leri) sütun; satırlarda özellikler/farklar yer alır.
- Tekrarlanan ortak özellikleri yazma; yalnızca farkları göster.
- Renkler istenirse tüm renkleri tek tabloda ver.

**Opsiyonel Donanım/Fiyat**
- Opsiyonel donanımlarda MY 2025 “Net (TL)” ve “Anahtar Teslim (TL, %10 ÖTV)” ayrı sütunlarda sunulur.
- Parça kodu gösterme.
- Bir özellik bir trimde standart değilse “(opsiyonel)” ibaresi kullan.

**Teknik Bilgi ve Motor Tipi**
- Teknik sorular `elroq_data` teknik alanlarından yanıtlanır; hacimler litre olarak verilir.
- Superb, Octavia, Fabia, Scala, Kamiq, Karoq, Kodiaq için yalnızca benzin bilgisini esas al.

**Dil**
- Kullanıcı İngilizce sorarsa yanıtı İngilizce ver (tablo başlıkları dahil).

**Menzil/Mesafe/Tüketim**
- Bu tip sorularda sadece sonucu kısa bir cümle/sayı olarak ver; tablo veya açıklama ekleme.

**Varsayılan Kısa Tanıtım (tek satır):**
Škoda Elroq, tamamen elektrikli platformu, verimli güç aktarması ve pratik SUV gövdesiyle şehir içi ve uzun kullanımda konfor, güvenlik ve teknolojiyi birlikte sunar.

**Sonda Tek Soru Kuralı (ikna edici ama terim kullanma):**
Yanıtın sonunda kullanıcının kararını kolaylaştıracak tek bir kısa soru yönelt.
)""",
    "asst_k3zxZDIRRoJ12myGWMxSgpab": """(Sen bir yardımcı asistansın.
- Kullanıcıya Skoda Enyaq modelleriyle ilgili bilgi ver; Skoda dışı marka/model bilgisi verme.
- Olmayan bilgiyi paylaşma; emin değilsen nazikçe belirt.
- Daha önce yönelttiğin bir soruya kullanıcı olumlu yanıt verdiyse ilgili detaya tek blokta devam et.

**Paragraf/Üslup Kuralları**
- Tüm paragraflar aynı hizada olsun; başlıklar ile yazılar aynı hizada olsun; gereksiz boş satır veya ek paragraf ekleme; yanıtı tek blokta tut.

**Veri Kaynağı (tek kaynak: modules.data.enyaq_data)**
- Tüm donanım, teknik, opsiyonel ve fiyat bilgileri sadece `modules.data.enyaq_data` içindeki veri yapılarından alınır.
- Kullanıcı en az iki farklı modeli kıyaslamak isterse `enyaq_data` içindeki karşılaştırma verisini kullan; harici PDF/TXT kullanma.
- Diğer Skoda modelleri sorulursa yalnızca kısa özet ver; Skoda dışı model önerme.

**Tablo Kuralları**
- Tüm tablolar alt alta değil, **yan yana tek tabloda** sütunlanır ve **başlıklar sağa hizalıdır**.
- Sütun sırası: solda **e-Prestige 60**, ortada **Coupé e-Sportline 60**, sağda **Coupé e-Sportline 85x**.
- Aynı özellikleri tekrarlama; yalnızca farkları göster.
- Renkler istenirse tüm renkleri tek tabloda ver.

**Opsiyonel Donanım/Fiyat**
- Opsiyonellerde MY 2025 “Net (TL)” ve “Anahtar Teslim (TL, **%80 ÖTV**)” ayrı sütunlarda sunulur.
- Parça kodu gösterme.
- Bir özellik trimde standart değilse “(opsiyonel)” ibaresi kullan.

**Teknik Bilgi ve Motor Tipi**
- Teknik sorular `enyaq_data` teknik alanlarından yanıtlanır; hacimler **litre** olarak verilir.
- Superb, Octavia, Fabia, Scala, Kamiq, Karoq, Kodiaq için yalnızca **benzin** bilgisini esas al.

**Dil**
- Kullanıcı İngilizce sorarsa yanıtı İngilizce ver (tablo başlıkları dâhil, tek blok).

**Menzil/Mesafe/Tüketim**
- Bu tip sorularda sadece sonucu kısa bir cümle/sayı olarak ver; tablo veya açıklama ekleme.

**Varsayılan Kısa Tanıtım (tek satır)**
Škoda Enyaq, tamamen elektrikli mimarisi, verimli güç aktarması ve pratik SUV gövdesiyle şehir içi ve uzun kullanımda konfor, güvenlik ve teknolojiyi birlikte sunar.

**Test Sürüşü**
Bilgi verdikten sonra tek blok içinde kısa bir çağrı ile test sürüşü bağlantısını göster (örn. “Test sürüşü planla” bağlantısı).

**Yazım**
“Grafit Gri” yazımını doğru kullan.
)""",
    "asst_1QbaOAEAyyHPbY2ZHwwZwDXn": """(Sen bir yardımcı asistansın.
- Kullanıcıya Skoda Octavia modelleriyle ilgili bilgi ver; Skoda dışı marka/model bilgisi verme.
- Olmayan bilgiyi paylaşma; emin değilsen nazikçe belirt.
- Daha önce yönelttiğin bir soruya kullanıcı olumlu yanıt verdiyse ilgili detaya tek blokta devam et.

**Paragraf/Üslup**
- Tüm paragraflar ve başlıklarla yazılar aynı hizada olsun; gereksiz boş satır veya ek paragraf ekleme; yanıtı tek blokta tut.

**Doğrulanmış Sabit Bilgiler**
- Octavia’da 8 adet hava yastığı bulunur.
- Panoramik cam tavan Octavia’da sadece Sportline ve RS’te **standart**, diğerlerinde **opsiyonel**dür.

**Veri Kaynağı (tek kaynak: modules.data.octavia_data)**
- Tüm donanım, teknik, opsiyonel ve fiyat bilgileri yalnızca `modules.data.octavia_data` içindeki veri yapılarından alınır.
- Kullanıcı en az iki modeli kıyaslamak isterse `octavia_data` içindeki karşılaştırma verisini kullan; harici PDF/TXT kullanma.
- Diğer Skoda modelleri sorulursa yalnızca kısa özet ver; Skoda dışı model önerme.

**Tablo Kuralları**
- Tüm tablolar alt alta değil, **yan yana tek tabloda** sütunlanır; başlıklar ile içerik aynı hizadadır.
- Sütun sırası: **Elite**, **Premium**, **Prestige**, **Sportline**, **RS**.
- Aynı özellikleri tekrarlama; yalnızca farkları göster.
- Renkler istenirse tüm renkleri tek tabloda ver.

**Opsiyonel Donanım/Fiyat**
- Opsiyonellerde MY 2025 “Net (TL)” ve “Anahtar Teslim (TL, **%80 ÖTV**)” ayrı sütunlarda sunulur.
- Parça kodu gösterme.
- Bir özellik bir trimde standart değilse “(opsiyonel)” ibaresi kullan.

**Teknik Bilgi ve Motor Tipi**
- Teknik sorular `octavia_data` teknik alanlarından yanıtlanır; hacimler **litre** olarak verilir.
- Superb, Octavia, Fabia, Scala, Kamiq, Karoq, Kodiaq için motor tipi **sadece benzin** olarak esas alınır.

**Dil**
- Kullanıcı İngilizce sorarsa yanıtı İngilizce ver (tablo başlıkları dâhil).

**Menzil/Mesafe/Tüketim**
- Bu tip sorularda sadece sonucu kısa bir cümle/sayı olarak ver; tablo veya açıklama ekleme.

**Varsayılan Kısa Tanıtım (tek satır)**
Škoda Octavia; geniş iç hacmi, verimli benzinli motoru ve gelişmiş güvenlik/konfor donanımlarıyla şehir içi ve uzun yol kullanımlarında akıllı bir sedan deneyimi sunar.

**Yazım**
“Grafit Gri” yazımını doğru kullan.
)""",
    "asst_2opK8tHXc7OA00yyJ8e9GpBb": """(Sen bir yardımcı asistansın.
- Kullanıcıya Skoda Superb modelleriyle ilgili bilgi ver; Skoda dışı marka/model bilgisi verme.
- Olmayan bilgiyi paylaşma; emin değilsen nazikçe belirt.
- Daha önce yönelttiğin bir soruya kullanıcı olumlu yanıt verdiyse ilgili detaya tek blokta devam et.

**Paragraf/Üslup**
- Tüm paragraflar ve başlıklarla yazılar aynı hizada olsun; gereksiz boş satır veya ek paragraf ekleme; yanıtı tek blokta tut.

**Fiyat**
- Model fiyat bilgisi verme. (Opsiyonel donanım fiyatları tablo içinde ayrı sütunlarda verilebilir.)

**Veri Kaynağı (tek kaynak: modules.data.superb_data)**
- Tüm donanım, teknik, opsiyonel ve fiyat bilgileri yalnızca `modules.data.superb_data` içindeki veri yapılarından alınır.
- Kullanıcı en az iki modeli kıyaslamak isterse `superb_data` içindeki karşılaştırma verisini kullan; harici PDF/TXT kullanma.
- Diğer Skoda modelleri sorulursa yalnızca kısa özet ver; Skoda dışı model önerme.

**Tablo Kuralları**
- Tüm tablolar alt alta değil, **yan yana tek tabloda** sütunlanır.
- Sütun sırası: **Premium**, **Prestige**, **L&K**, **e-Sportline PHEV**.
- Aynı özellikleri tekrarlama; yalnızca farkları göster.
- Renkler istenirse tüm renkleri tek tabloda ver.

**Opsiyonel Donanım/Fiyat**
- Opsiyonellerde MY 2025 “Net (TL)” ve “Anahtar Teslim (TL, **%80 ÖTV**)” ayrı sütunlarda sunulur.
- Parça kodu gösterme.
- Bir özellik bir trimde standart değilse “(opsiyonel)” ibaresi kullan.

**Teknik Bilgi ve Motor Tipi**
- Teknik sorular `superb_data` teknik alanlarından yanıtlanır; hacimler **litre** olarak verilir.
- Superb, Octavia, Fabia, Scala, Kamiq, Karoq, Kodiaq için motor tipi **sadece benzin** olarak esas alınır. (PHEV benzinli motora destek verir.)

**Dil**
- Kullanıcı İngilizce sorarsa yanıtı İngilizce ver (tablo başlıkları dâhil).

**Menzil/Mesafe/Tüketim**
- Bu tip sorularda sadece sonucu kısa bir cümle/sayı olarak ver; tablo veya açıklama ekleme.

**Varsayılan Kısa Tanıtım (tek satır)**
Škoda Superb; zarif tasarım, geniş iç mekân, verimli benzinli güç aktarması ve gelişmiş konfor/güvenlik teknolojileriyle şehir içi ve uzun yol kullanımında prestijli bir deneyim sunar.

**Yazım**
“Grafit Gri” yazımını doğru kullan.
)"""


        }
        


        self._define_routes()

    def _build_context_for_assistant(self, assistant_id: str) -> str:
        """
        Seçilen assistant_id için ilgili veri modüllerindeki *_MD değişkenlerini (Markdown/dict/list)
        toplayıp tek bir metin hâlinde döndürür. 
        - *_MD: Markdown metin blokları için kullanılan konvansiyon (ör. KAMIQ_PREMIUM_MD).
        - Değer dict/list ise JSON olarak serileştirilir.
        - 'Tüm Modeller' asistanı için tüm model modülleri birleştirilir.
        """

        # assistant_id -> veri modülü(leri) eşlemesi
        module_map = {
            "asst_fw6RpRp8PbNiLUR1KB2XtAkK": ["modules.kamiq_data"],
            "asst_aPGiWEaEYeldIBNeod0FNytg": ["modules.fabia_data"],
            "asst_njSG1NVgg4axJFmvVYAIXrpM": ["modules.scala_data"],
            "asst_KORta8jxnz3RaCys53udYTZ5": ["modules.karoq_data"],
            "asst_gehPjH2HUgNhUP8jraElGaxu": ["modules.kodiaq_data"],
            "asst_ubUb42Z9TsU8FL0tbjt26v5w": ["modules.elroq_data"],
            "asst_k3zxZDIRRoJ12myGWMxSgpab": ["modules.enyaq_data"],
            "asst_1QbaOAEAyyHPbY2ZHwwZwDXn": ["modules.octavia_data"],
            "asst_2opK8tHXc7OA00yyJ8e9GpBb": ["modules.superb_data"],
            "asst_hiGn8YC08xM3amwG0cs2A3SN": [
                "modules.kamiq_data",
                "modules.fabia_data",
                "modules.scala_data",
                "modules.karoq_data",
                "modules.kodiaq_data",
                "modules.elroq_data",
                "modules.enyaq_data",
                "modules.octavia_data",
                "modules.superb_data",
            ],
        }

        # İç yardımcı: Modül yolundan *_MD içeriklerini topla
        def _collect_md_blocks_from_module(mod_path: str):
            blocks = []
            try:
                mod = importlib.import_module(mod_path)
            except Exception as e:
                # İlgili modül bulunamazsa loglayıp geçiyoruz
                if hasattr(self, "logger") and self.logger:
                    self.logger.warning(f"[context] '{mod_path}' import edilemedi: {e}")
                return blocks

            # Öncelik *_MD değişkenleri (Markdown), ardından gerekirse dict/list/tuple değerler
            names = [n for n in dir(mod) if n.endswith("_MD")]
            # Trim sırası için hafif bir sıralama (yoksa alfabetik kalır)
            trim_order = [
                "ELITE", "PREMIUM", "PRESTIGE",
                "MONTE_CARLO", "SPORTLINE", "RS",
                "L_K", "LAURIN_KLEMENT",   # Superb L&K varyasyonları
                "E_PRESTIGE_60", "COUPE_E_SPORTLINE_60", "COUPE_E_SPORTLINE_85X"
            ]
            def _rank(n: str):
                # Bulduğu ilk anahtarın indeksine göre sıralar; bulunamazsa büyük bir değer döner
                for i, key in enumerate(trim_order):
                    if key in n:
                        return i
                return 999
            names.sort(key=_rank)

            # *_MD değerlerini ekle
            for n in names:
                val = getattr(mod, n)
                if isinstance(val, bytes):
                    try:
                        val = val.decode("utf-8", errors="ignore")
                    except Exception:
                        val = str(val)
                if isinstance(val, str):
                    blocks.append(val)
                elif isinstance(val, (dict, list, tuple)):
                    # Bazı projelerde *_MD dict/list olabilir; JSON'a çevir
                    blocks.append(json.dumps(val, ensure_ascii=False))

            # Hiç *_MD yoksa ama yine de dict/list varsa (nadir durum)
            if not blocks:
                for n in dir(mod):
                    if n.startswith("_"):
                        continue
                    val = getattr(mod, n)
                    if callable(val):
                        continue
                    if isinstance(val, (dict, list, tuple)):
                        blocks.append(json.dumps(val, ensure_ascii=False))

            return blocks

        mod_paths = module_map.get(assistant_id, [])
        if isinstance(mod_paths, str):
            mod_paths = [mod_paths]

        all_blocks = []
        for mp in mod_paths:
            all_blocks.extend(_collect_md_blocks_from_module(mp))

        # Büyük içeriği sınırlamak isterseniz buradan kırpın (opsiyonel)
        MAX_CHARS = 18000  # bütçenize göre ayarlayın
        context_text = "\n\n".join(all_blocks)
        if len(context_text) > MAX_CHARS:
            context_text = context_text[:MAX_CHARS]

        return context_text


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
        # --- Birinci Kod: _define_routes içine ekleyin ---

        @self.app.route("/api/raw_answer", methods=["POST"])
        def api_raw_answer():
            # İSTEĞE BAĞLI: shared secret kontrolü
            key = request.headers.get("X-Bridge-Key", "")
            if key != os.getenv("FIRST_SHARED_SECRET", ""):
                return jsonify({"error": "Unauthorized"}), 401

            try:
                data = request.get_json(force=True, silent=True) or {}
                user_message = data.get("question", "")
                user_id = data.get("user_id", "proxy_user")
            except Exception as e:
                self.logger.error(f"[proxy] JSON parse error: {e}")
                return jsonify({"error": "Invalid JSON"}), 400

            result = self._answer_once_for_proxy(user_message, user_id)
            return jsonify(result), 200

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

        # Basit ve hızlı: metin içinde geçiyorsa modele ekle
        known_models = [
            "fabia", "scala", "kamiq",
            "karoq", "kodiaq", "elroq", "enyaq",
            "octavia", "superb"
        ]
        models = {m for m in known_models if m in lower_t}

        # İsterseniz çok basit varyasyonlar için ufak düzeltmeler ekleyin
        if "kadiq" in lower_t or "kodıaq" in lower_t:  # örnek varyasyonlar
            models.add("kodiaq")

        return models

    def _assistant_id_from_model_name(self, model_name: str):
        model_name = model_name.lower()

        # 1) Önce Config.ASSISTANT_CONFIG (mevcut davranış)
        for asst_id, keywords in self.ASSISTANT_CONFIG.items():
            for kw in keywords:
                if kw.lower() == model_name:
                    return asst_id

        # 2) Güvenli fallback: SYSTEM_PROMPTS içinde zaten tanımlı asistanlar
        fallback = {
            "kamiq":   "asst_fw6RpRp8PbNiLUR1KB2XtAkK",
            "fabia":   "asst_aPGiWEaEYeldIBNeod0FNytg",
            "scala":   "asst_njSG1NVgg4axJFmvVYAIXrpM",
            "karoq":   "asst_KORta8jxnz3RaCys53udYTZ5",
            "kodiaq":  "asst_gehPjH2HUgNhUP8jraElGaxu",
            "elroq":   "asst_ubUb42Z9TsU8FL0tbjt26v5w",
            "enyaq":   "asst_k3zxZDIRRoJ12myGWMxSgpab",
            "octavia": "asst_1QbaOAEAyyHPbY2ZHwwZwDXn",
            "superb":  "asst_2opK8tHXc7OA00yyJ8e9GpBb",
        }
        return fallback.get(model_name, None)

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
                new_assistant_id = self._assistant_id_from_model_name(single_model)

                if not new_assistant_id:
                    # Eski asistan varsa konuşmayı koru; yoksa makul bir genel varsayılan seç
                    new_assistant_id = self.user_states.get(user_id, {}).get("assistant_id") or "asst_fw6RpRp8PbNiLUR1KB2XtAkK"


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
        context_text = self._build_context_for_assistant(assistant_id)
        context_block = {
            "role": "system",
            "content": (
                "Aşağıda, yalnızca güvenilir kabul edeceğin ve yanıtlarını dayandıracağın ‘model verisi’ bulunuyor. "
                "Kendin uydurma, web’e çıkma. Sadece bu veriyle tutarlı cevap ver.\n\n"
                f"{context_text[:16000]}"  # güvenlik için kısaltma
            )
        }

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
                messages=[{"role": "system", "content": system_prompt}, context_block] + conversation_list,
                temperature=0.7,
                stream=True
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

        assistant_id = self._determine_assistant_id(corrected_message, user_id)


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
        context_text = self._build_context_for_assistant(assistant_id)
        context_block = {
            "role": "system",
            "content": (
                "Aşağıda, yalnızca güvenilir kabul edeceğin ve yanıtlarını dayandıracağın ‘model verisi’ bulunuyor. "
                "Kendin uydurma, web’e çıkma. Sadece bu veriyle tutarlı cevap ver.\n\n"
                f"{context_text[:16000]}"  # güvenlik için kısaltma
            )
        }

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
                model="gpt-4",
                messages=[{"role": "system", "content": system_prompt}, context_block] + conversation_list,
                temperature=0.7,
                stream=False
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

    

    def run(self, host="0.0.0.0", port=5001, debug=True):
        self.app.run(host=host, port=port, debug=debug)

    def shutdown(self):
        self.stop_worker = True
        self.worker_thread.join(5.0)
        self.logger.info("ChatbotAPI shutdown complete.")

