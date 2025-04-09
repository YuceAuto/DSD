import os
import time
import logging
import re
import openai
import difflib
import queue
import threading
import random

from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv

from modules.managers.image_manager import ImageManager
from modules.managers.markdown_utils import MarkdownProcessor
from modules.config import Config
from modules.utils import Utils
from modules.db import create_tables, save_to_db, send_email, get_db_connection, update_customer_answer

import secrets

# Fabia, Kamiq, Scala tabloları
from modules.data.scala_data import (
    SCALA_ELITE_MD,
    SCALA_PREMIUM_MD,
    SCALA_MONTE_CARLO_MD
)
from modules.data.kamiq_data import (
    KAMIQ_ELITE_MD,
    KAMIQ_PREMIUM_MD,
    KAMIQ_MONTE_CARLO_MD
)
from modules.data.fabia_data import (
    FABIA_PREMIUM_MD,
    FABIA_MONTE_CARLO_MD
)

# Karoq tabloları (EKLENDİ)
from modules.data.karoq_data import (
    KAROQ_PREMIUM_MD,
    KAROQ_PRESTIGE_MD,
    KAROQ_SPORTLINE_MD
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

        # OpenAI
        openai.api_key = os.getenv("OPENAI_API_KEY")
        self.client = openai

        self.config = Config()
        self.utils = Utils()

        self.image_manager = ImageManager(images_folder=os.path.join(static_folder, "images"))
        self.image_manager.load_images()

        self.markdown_processor = MarkdownProcessor()

        # Asistan konfigürasyonları
        self.ASSISTANT_CONFIG = self.config.ASSISTANT_CONFIG
        self.ASSISTANT_NAME_MAP = self.config.ASSISTANT_NAME_MAP

        # Kullanıcı bazlı state
        self.user_states = {}

        # Fuzzy Cache & Queue
        self.fuzzy_cache = {}
        self.fuzzy_cache_queue = queue.Queue()

        self.stop_worker = False
        self.worker_thread = threading.Thread(target=self._background_db_writer, daemon=True)
        self.worker_thread.start()

        # Önbellekteki cevabın geçerli kalma süresi (1 gün = 86400 sn)
        self.CACHE_EXPIRY_SECONDS = 86400

        # Flask route tanımları
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
            return self._ask()

        @self.app.route("/check_session", methods=["GET"])
        def check_session():
            if 'last_activity' in session:
                now = time.time()
                # Session timeout vb. kontrol edilebilir
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

    # ----------------------------------------------------------------
    # ARKA PLANDA DB'YE YAZAN THREAD
    # ----------------------------------------------------------------
    def _background_db_writer(self):
        """Queue'ya eklenen cache kayıtlarını DB'ye yazar."""
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

    def _load_cache_from_db(self):
        """
        Opsiyonel: DB'den son X kaydı çekerek self.fuzzy_cache'e doldurabilirsiniz.
        """
        self.logger.info("[_load_cache_from_db] Cache verileri DB'den yükleniyor...")

        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
        SELECT TOP 1000 user_id, question, answer
        FROM cache_faq
        ORDER BY id DESC
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            user_id = row[0]
            q_lower = row[1]
            ans_txt = row[2]
            ans_bytes = ans_txt.encode("utf-8")
            assistant_id = "default"

            if user_id not in self.fuzzy_cache:
                self.fuzzy_cache[user_id] = {}
            if assistant_id not in self.fuzzy_cache[user_id]:
                self.fuzzy_cache[user_id][assistant_id] = []

            self.fuzzy_cache[user_id][assistant_id].append({
                "question": q_lower,
                "answer_bytes": ans_bytes,
                "timestamp": time.time()
            })

        self.logger.info("[_load_cache_from_db] Tamamlandı.")

    def _extract_models(self, text: str) -> set:
        """
        Kullanıcı mesajındaki 'fabia', 'scala', 'kamiq', 'karoq' kelimelerini yakalar.
        """
        lower_t = text.lower()
        models = set()
        if "fabia" in lower_t:
            models.add("fabia")
        if "scala" in lower_t:
            models.add("scala")
        if "kamiq" in lower_t:
            models.add("kamiq")
        if "karoq" in lower_t:
            models.add("karoq")
        return models

    def _assistant_id_from_model_name(self, model_name: str):
        """
        Model adına göre asistan ID döndürür.
        """
        model_name = model_name.lower()
        for asst_id, keywords in self.ASSISTANT_CONFIG.items():
            for kw in keywords:
                if kw.lower() == model_name:
                    return asst_id
        return None

    def _search_in_assistant_cache(self, user_id, assistant_id, new_question, threshold):
        """
        Belirli bir asistan ID altındaki önbellekte fuzzy arama yapar.
        """
        if not assistant_id:
            return None, None
        if user_id not in self.fuzzy_cache:
            return None, None
        if assistant_id not in self.fuzzy_cache[user_id]:
            return None, None

        new_q_lower = new_question.strip().lower()
        now = time.time()
        best_ratio = 0.0
        best_answer = None

        for item in self.fuzzy_cache[user_id][assistant_id]:
            if (now - item["timestamp"]) > self.CACHE_EXPIRY_SECONDS:
                continue

            old_q = item["question"]
            ratio = difflib.SequenceMatcher(None, new_q_lower, old_q).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_answer = item["answer_bytes"]

        if best_ratio >= threshold:
            return best_answer, best_ratio

        return None, None

    def _find_fuzzy_cached_answer(self, user_id: str, new_question: str, assistant_id: str, threshold=0.8):
        """
        Fuzzy cache araması (tek asistan için).
        """
        ans, ratio = self._search_in_assistant_cache(user_id, assistant_id, new_question, threshold)
        if ans:
            return ans
        return None

    def _store_in_fuzzy_cache(self, user_id: str, question: str, answer_bytes: bytes, assistant_id: str):
        """
        Yeni bir Soru-Cevabı bellek içi ve DB queue'suna kaydeder.
        """
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

    def _ask(self):
        """
        Kullanıcıdan gelen message (POST /ask) -> Chat yanıtı stream.
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

        # Session zaman damgası
        if 'last_activity' not in session:
            session['last_activity'] = time.time()
        else:
            session['last_activity'] = time.time()

        corrected_message = self._correct_typos(user_message)

        # Yeni mesajdaki modelleri tespit et
        user_models_in_msg = self._extract_models(corrected_message)

        # Mevcut user_state ve last_models
        if user_id not in self.user_states:
            self.user_states[user_id] = {}
            self.user_states[user_id]["threads"] = {}

        last_models = self.user_states[user_id].get("last_models", set())

        # Eğer yeni mesajda model yok ve last_models dolu ise, soruya ekleyelim
        if not user_models_in_msg and last_models:
            joined_models = " ve ".join(last_models)  # fabia ve scala gibi
            corrected_message = f"{joined_models} {corrected_message}".strip()
            # Tekrar modelleri tespit et
            user_models_in_msg = self._extract_models(corrected_message)
            self.logger.info(f"[MODEL-EKLEME] Önceki modeller eklendi -> {joined_models}")

        # Eğer bu mesajda model(ler) tespit edildiyse last_models'i güncelle
        if user_models_in_msg:
            self.user_states[user_id]["last_models"] = user_models_in_msg

        # Kelime sayısına göre threshold
        word_count = len(corrected_message.strip().split())
        if word_count < 5:
            local_threshold = 1.0
        else:
            local_threshold = 0.8

        lower_corrected = corrected_message.lower().strip()

        # Asistan ID (önceki ya da yeni)
        old_assistant_id = self.user_states[user_id].get("assistant_id")
        old_assistant_name = None
        if old_assistant_id:
            old_assistant_name = self.ASSISTANT_NAME_MAP.get(old_assistant_id, "")

        # Kullanıcı cümlesinden model yakalama
        new_assistant_id = None
        if len(user_models_in_msg) == 1:
            # Tek model
            found_model = list(user_models_in_msg)[0]
            new_assistant_id = self._assistant_id_from_model_name(found_model)
        elif len(user_models_in_msg) > 1:
            # Birden fazla model -> basitçe ilk bulduğumuzu asistan olarak alacağız
            first_model = list(user_models_in_msg)[0]
            new_assistant_id = self._assistant_id_from_model_name(first_model)

        if new_assistant_id is None and old_assistant_id:
            # Yeni model yok -> eski asistanla devam
            new_assistant_id = old_assistant_id

        if not new_assistant_id:
            # Hâlâ yoksa -> en az meşgul asistan
            new_assistant_id = self._pick_least_busy_assistant()
            if not new_assistant_id:
                save_to_db(user_id, user_message, "Uygun asistan bulunamadı.")
                return self.app.response_class("Uygun bir asistan bulunamadı.\n", mimetype="text/plain")

        # Son karar
        self.user_states[user_id]["assistant_id"] = new_assistant_id
        assistant_name = self.ASSISTANT_NAME_MAP.get(new_assistant_id, "")

        # Görsel isteği?
        is_image_req = self.utils.is_image_request(user_message)

        # Eğer birden fazla model varsa ve görsel talebi geldiyse:
        if len(user_models_in_msg) > 1 and is_image_req:
            def multi_model_generator():
                chunks = []
                for chunk in self._handle_multiple_models_image_requests(user_id, corrected_message, user_models_in_msg):
                    chunks.append(chunk)
                    yield chunk
                # Önbellek
                final_bytes = b"".join(chunks)
                self._store_in_fuzzy_cache(user_id, corrected_message, final_bytes, new_assistant_id)
            return self.app.response_class(multi_model_generator(), mimetype="text/plain")

        # Cache kontrolü (sadece görsel isteği değilse):
        cached_answer = None
        if not is_image_req:
            cached_answer = self._find_fuzzy_cached_answer(
                user_id,
                corrected_message,
                new_assistant_id,
                threshold=local_threshold
            )

        if cached_answer and not is_image_req:
            answer_text = cached_answer.decode("utf-8")
            models_in_answer = self._extract_models(answer_text)
            # Model uyuşmazlığı kontrolü:
            if user_models_in_msg and not user_models_in_msg.issubset(models_in_answer):
                self.logger.info("Model uyuşmazlığı -> cache bypass.")
            else:
                self.logger.info("Fuzzy cache match bulundu, önbellekten yanıt.")
                time.sleep(1)
                return self.app.response_class(cached_answer, mimetype="text/plain")

        # Streaming response
        def caching_generator():
            chunks = []
            for chunk in self._generate_response(corrected_message, user_id):
                chunks.append(chunk)
                yield chunk

            if not is_image_req:
                final_bytes = b"".join(chunks)
                self._store_in_fuzzy_cache(user_id, corrected_message, final_bytes, new_assistant_id)

        return self.app.response_class(caching_generator(), mimetype="text/plain")

    def _pick_least_busy_assistant(self):
        if not self.ASSISTANT_CONFIG:
            return None

        assistant_thread_counts = {}
        for asst_id in self.ASSISTANT_CONFIG.keys():
            count = 0
            for uid, state_dict in self.user_states.items():
                threads = state_dict.get("threads", {})
                if asst_id in threads:
                    count += 1
            assistant_thread_counts[asst_id] = count

        min_count = min(assistant_thread_counts.values())
        candidates = [aid for aid, c in assistant_thread_counts.items() if c == min_count]
        if not candidates:
            return None
        return random.choice(candidates)

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
        return " ".join(combined_tokens)

    def _generate_response(self, user_message, user_id):
        """
        Asıl iş mantığı - satır satır yield edilerek frontend'e iletiliyor.
        """
        self.logger.info(f"[_generate_response] Kullanıcı ({user_id}): {user_message}")

        assistant_id = self.user_states[user_id].get("assistant_id", None)
        assistant_name = self.ASSISTANT_NAME_MAP.get(assistant_id, "")
        lower_msg = user_message.lower()

        if "current_trim" not in self.user_states[user_id]:
            self.user_states[user_id]["current_trim"] = ""

        # --------------------------------------------------------------------
        # (1) Genişletilmiş Regex: Model + Opsiyonel Trim + Görsel isteği
        # --------------------------------------------------------------------
        model_trim_image_pattern = (
            r"(scala|fabia|kamiq|karoq)"
            r"(?:\s+(premium|monte carlo|elite|prestige|sportline))?"
            r"\s+(?:görsel(?:er)?|resim(?:ler)?|fotoğraf(?:lar)?)"
        )
        match = re.search(model_trim_image_pattern, lower_msg)
        if match:
            matched_model = match.group(1)
            matched_trim = match.group(2)

            filter_str = matched_model
            if matched_trim:
                filter_str += f" {matched_trim}"

            found_images = self.image_manager.filter_images_multi_keywords(filter_str)
            if found_images:
                yield f"<b>{matched_model.title()}".encode("utf-8")
                if matched_trim:
                    yield f" {matched_trim.title()}".encode("utf-8")
                yield f" Görselleri</b><br>".encode("utf-8")
                for chunk in self._render_side_by_side_images(found_images, context="model+trim"):
                    yield chunk
            else:
                no_img_msg = f"{matched_model.title()}"
                if matched_trim:
                    no_img_msg += f" {matched_trim.title()}"
                no_img_msg += " için görsel bulunamadı.<br>"
                yield no_img_msg.encode("utf-8")

            return

        # (2) "dış" görsel istekleri
        if any(kw in lower_msg for kw in ["dış ", " dış", "dıs", "dis", "diş"]):
            if self.utils.is_image_request(user_message):
                if not assistant_name:
                    save_to_db(user_id, user_message, "Dış görseller için model seçilmemiş.")
                    yield "Uygun model bulunamadı.\n".encode("utf-8")
                    return

                trim_name = self.user_states[user_id]["current_trim"]
                if "premium" in lower_msg:
                    trim_name = "premium"
                elif "monte carlo" in lower_msg:
                    trim_name = "monte carlo"
                elif "elite" in lower_msg:
                    trim_name = "elite"
                elif "prestige" in lower_msg:
                    trim_name = "prestige"
                elif "sportline" in lower_msg:
                    trim_name = "sportline"

                self.user_states[user_id]["current_trim"] = trim_name

                model_title = assistant_name.title()
                if trim_name:
                    final_title = f"{model_title} {trim_name.title()} Dış Görselleri"
                else:
                    final_title = f"{model_title} Dış Görselleri"

                save_to_db(user_id, user_message, f"{final_title} listeleniyor.")
                yield f"<b>{final_title}</b><br>".encode("utf-8")

                # Renk görselleri
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

                # Jant görselleri
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

        # (3) "iç" görsel istekleri
        pattern_interior = r"\b(iç|ic|direksiyon simidi|direksiyon|koltuk|döşeme|multimedya)\b"
        if re.search(pattern_interior, lower_msg) and self.utils.is_image_request(user_message):
            if not assistant_name:
                save_to_db(user_id, user_message, "İç mekan görselleri için model seçilmemiş.")
                yield "Uygun model bulunamadı.\n".encode("utf-8")
                return

            trim_name = self.user_states[user_id]["current_trim"]
            if "premium" in lower_msg:
                trim_name = "premium"
            elif "monte carlo" in lower_msg:
                trim_name = "monte carlo"
            elif "elite" in lower_msg:
                trim_name = "elite"
            elif "prestige" in lower_msg:
                trim_name = "prestige"
            elif "sportline" in lower_msg:
                trim_name = "sportline"
            self.user_states[user_id]["current_trim"] = trim_name

            possible_parts = ["direksiyon simidi", "direksiyon", "koltuk", "döşeme", "multimedya"]
            user_requested_parts = []
            for p in possible_parts:
                if p in lower_msg:
                    user_requested_parts.append(p)

            # “direksiyon simidi” varsa “direksiyon” kelimesini çıkar
            if "direksiyon simidi" in user_requested_parts and "direksiyon" in user_requested_parts:
                user_requested_parts.remove("direksiyon")

            is_general_interior = ("iç" in lower_msg or "ic" in lower_msg)
            if is_general_interior and not user_requested_parts:
                categories = ["direksiyon simidi", "döşeme", "koltuk", "multimedya"]
            else:
                if user_requested_parts:
                    categories = user_requested_parts
                else:
                    categories = ["direksiyon simidi", "döşeme", "koltuk", "multimedya"]

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
                    for chunk in self._render_side_by_side_images(found_images, context="ic"):
                        yield chunk
                    yield "<br>".encode("utf-8")
                else:
                    yield f"{cat.title()} görseli bulunamadı.<br><br>".encode("utf-8")

            if not any_image_found:
                yield "Herhangi bir iç görsel bulunamadı.<br>".encode("utf-8")
            return

        # (4) "Evet" kontrolü (renk seçimi vs.)
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
                for chunk in self._render_side_by_side_images(all_found_images, context=None):
                    yield chunk
                self.user_states[user_id]["pending_color_images"] = []
                return

        # (5) Opsiyonel donanım tabloları
        user_trims_in_msg = set()
        if "premium" in lower_msg:
            user_trims_in_msg.add("premium")
        if "monte carlo" in lower_msg:
            user_trims_in_msg.add("monte carlo")
        if "elite" in lower_msg:
            user_trims_in_msg.add("elite")
        if "prestige" in lower_msg:
            user_trims_in_msg.add("prestige")
        if "sportline" in lower_msg:
            user_trims_in_msg.add("sportline")

        pending_ops_model = self.user_states[user_id].get("pending_opsiyonel_model", None)

        if "opsiyonel" in lower_msg:
            found_model = None
            # Eğer user mesajında model geçiyorsa -> bul
            user_models_in_msg = self._extract_models(user_message)
            if len(user_models_in_msg) == 1:
                found_model = list(user_models_in_msg)[0]
            elif len(user_models_in_msg) > 1:
                found_model = list(user_models_in_msg)[0]  # Basit mantık

            if not found_model and assistant_name:
                found_model = assistant_name.lower()

            if not found_model:
                yield "Hangi modelin opsiyonel donanımlarını görmek istersiniz?".encode("utf-8")
                return
            else:
                self.user_states[user_id]["pending_opsiyonel_model"] = found_model
                if len(user_trims_in_msg) == 1:
                    found_trim = list(user_trims_in_msg)[0]
                    save_to_db(user_id, user_message, f"{found_model.title()} {found_trim.title()} opsiyonel tablosu.")
                    yield from self._yield_opsiyonel_table(user_id, user_message, found_model, found_trim)
                    return
                else:
                    if found_model == "fabia":
                        yield "Hangi donanımı görmek istersiniz? (Premium / Monte Carlo)\n".encode("utf-8")
                    elif found_model == "scala":
                        yield "Hangi donanımı görmek istersiniz? (Elite / Premium / Monte Carlo)\n".encode("utf-8")
                    elif found_model == "kamiq":
                        yield "Hangi donanımı görmek istersiniz? (Elite / Premium / Monte Carlo)\n".encode("utf-8")
                    elif found_model == "karoq":
                        yield "Hangi donanımı görmek istersiniz? (Premium / Prestige / Sportline)\n".encode("utf-8")
                    else:
                        yield f"'{found_model}' modeli için opsiyonel donanım listesi tanımlanmamış.\n".encode("utf-8")
                    return

        if pending_ops_model:
            if user_trims_in_msg:
                if len(user_trims_in_msg) == 1:
                    found_trim = list(user_trims_in_msg)[0]
                    save_to_db(user_id, user_message, f"{pending_ops_model.title()} {found_trim.title()} opsiyonel tablosu.")
                    yield from self._yield_opsiyonel_table(user_id, user_message, pending_ops_model, found_trim)
                    return
                else:
                    if pending_ops_model.lower() == "fabia":
                        yield "Birden fazla donanım tespit ettim, lütfen birini seçin. (Premium / Monte Carlo)\n".encode("utf-8")
                    elif pending_ops_model.lower() == "scala":
                        yield "Birden fazla donanım tespit ettim, lütfen birini seçin. (Elite / Premium / Monte Carlo)\n".encode("utf-8")
                    elif pending_ops_model.lower() == "kamiq":
                        yield "Birden fazla donanım tespit ettim, lütfen birini seçin. (Elite / Premium / Monte Carlo)\n".encode("utf-8")
                    elif pending_ops_model.lower() == "karoq":
                        yield "Birden fazla donanım tespit ettim, lütfen birini seçin. (Premium / Prestige / Sportline)\n".encode("utf-8")
                    else:
                        yield f"'{pending_ops_model}' modeli için opsiyonel donanım listesi tanımlanmamış.\n".encode("utf-8")
                    return
            else:
                # Hiç trim yoksa
                if pending_ops_model.lower() == "fabia":
                    yield "Hangi donanımı görmek istersiniz? (Premium / Monte Carlo)\n".encode("utf-8")
                elif pending_ops_model.lower() == "scala":
                    yield "Hangi donanımı görmek istersiniz? (Elite / Premium / Monte Carlo)\n".encode("utf-8")
                elif pending_ops_model.lower() == "kamiq":
                    yield "Hangi donanımı görmek istersiniz? (Elite / Premium / Monte Carlo)\n".encode("utf-8")
                elif pending_ops_model.lower() == "karoq":
                    yield "Hangi donanımı görmek istersiniz? (Premium / Prestige / Sportline)\n".encode("utf-8")
                else:
                    yield f"'{pending_ops_model}' modeli için opsiyonel donanım listesi tanımlanmamış.\n".encode("utf-8")
                return

        # (6) Normal Chat (OpenAI vb.)
        if not assistant_id:
            save_to_db(user_id, user_message, "Uygun asistan bulunamadı.")
            yield "Uygun bir asistan bulunamadı.\n".encode("utf-8")
            return

        try:
            threads_dict = self.user_states[user_id].get("threads", {})
            thread_id = threads_dict.get(assistant_id)

            if not thread_id:
                new_thread = self.client.beta.threads.create(
                    messages=[{"role": "user", "content": user_message}]
                )
                thread_id = new_thread.id
                threads_dict[assistant_id] = thread_id
                self.user_states[user_id]["threads"] = threads_dict
            else:
                self.client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=user_message
                )

            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )

            start_time = time.time()
            timeout = 30
            assistant_response = ""

            while time.time() - start_time < timeout:
                run = self.client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                if run.status == "completed":
                    msg_response = self.client.beta.threads.messages.list(thread_id=thread_id)
                    for msg in msg_response.data:
                        if msg.role == "assistant":
                            content = str(msg.content)
                            content_md = self.markdown_processor.transform_text_to_markdown(content)
                            assistant_response = content
                            yield content_md.encode("utf-8")
                    break
                elif run.status == "failed":
                    save_to_db(user_id, user_message, "Yanıt oluşturulamadı.")
                    yield "Yanıt oluşturulamadı.\n".encode("utf-8")
                    return
                time.sleep(0.5)

            if not assistant_response:
                save_to_db(user_id, user_message, "Zaman aşımı.")
                yield "Yanıt alma zaman aşımına uğradı.\n".encode("utf-8")
                return

            conversation_id = save_to_db(user_id, user_message, assistant_response)
            yield f"\n[CONVERSATION_ID={conversation_id}]".encode("utf-8")

            # Renk ismi tespiti (opsiyonel örnek)
            if "görsel olarak görmek ister misiniz?" in assistant_response.lower():
                detected_colors = self.utils.parse_color_names(assistant_response)
                if detected_colors:
                    self.user_states[user_id]["pending_color_images"] = detected_colors

        except Exception as e:
            self.logger.error(f"Yanıt oluşturma hatası: {str(e)}")
            save_to_db(user_id, user_message, f"Hata: {str(e)}")
            yield f"Bir hata oluştu: {str(e)}\n".encode("utf-8")

    def _handle_multiple_models_image_requests(self, user_id, user_message, models):
        """
        Örnek: aynı anda 2+ model için “görsel” isteğinde bulunulmuşsa,
        her model için trim/donanım ve renk görsellerini sırasıyla döndürür.
        """
        lower_msg = user_message.lower()
        # Donanım yakalama
        trim_keywords = []
        if "premium" in lower_msg:
            trim_keywords.append("premium")
        if "monte carlo" in lower_msg:
            trim_keywords.append("monte carlo")
        if "elite" in lower_msg:
            trim_keywords.append("elite")
        if "prestige" in lower_msg:
            trim_keywords.append("prestige")
        if "sportline" in lower_msg:
            trim_keywords.append("sportline")

        # Renkleri de isteyebilirsiniz
        all_colors = self.config.KNOWN_COLORS

        for model_name in models:
            title_text = f"<b>{model_name.title()} Görselleri</b><br>"
            yield title_text.encode("utf-8")

            if trim_keywords:
                # Her trim için arayalım
                for trim in trim_keywords:
                    filter_str = f"{model_name} {trim}"
                    found_images = self.image_manager.filter_images_multi_keywords(filter_str)
                    if found_images:
                        yield f"{model_name.title()} {trim.title()} görselleri:<br>".encode("utf-8")
                        yield from self._render_side_by_side_images(found_images, context="multi")
                    else:
                        yield f"{model_name.title()} {trim.title()} için görsel bulunamadı.<br>".encode("utf-8")
            else:
                # Trim yoksa model bazında arayabilir veya renkleri ekleyebilirsiniz
                found_model_images = self.image_manager.filter_images_multi_keywords(model_name)
                if found_model_images:
                    yield from self._render_side_by_side_images(found_model_images, context="no-trim")
                else:
                    yield f"{model_name.title()} için genel görsel bulunamadı.<br>".encode("utf-8")

            # Opsiyonel: Renkleri listelemek isterseniz
            color_images = []
            for clr in all_colors:
                fstr = f"{model_name} {clr}"
                results = self.image_manager.filter_images_multi_keywords(fstr)
                color_images.extend(results)

            unique_color_images = list(set(color_images))
            if unique_color_images:
                yield f"<br><i>{model_name.title()} Renk Görselleri:</i><br>".encode("utf-8")
                yield from self._render_side_by_side_images(unique_color_images, context="color")

            yield b"<hr>"

        summary_text = f"{', '.join(models)} modelleri için görseller listelendi.<br>"
        save_to_db(user_id, user_message, summary_text)
        yield summary_text.encode("utf-8")

    def _render_side_by_side_images(self, images, context="model"):
        """
        Görselleri belli bir düzenle ekrana basan yardımcı fonksiyon.
        """
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

        yield b"""
<div style="display: flex; justify-content: space-between; gap: 60px;">
  <div style="flex:1;">
"""

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

        yield b"</div>"

        yield b"""
  <div style="flex:1;">
"""

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

        yield b"""
  </div>
</div>
"""

        if others:
            yield "<hr><b>Diğer Görseller:</b><br>".encode("utf-8")
            yield b'<div style="display: flex; flex-wrap: wrap; gap: 20px;">'
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
            yield b"</div>"

    def _yield_opsiyonel_table(self, user_id, user_message, model_name, trim_name):
        """
        Seçilen model + trim için opsiyonel donanım tablosunu döndürür.
        """
        table_yielded = False

        if model_name == "fabia":
            if "premium" in trim_name:
                yield FABIA_PREMIUM_MD.encode("utf-8")
                table_yielded = True
            elif "monte" in trim_name:
                yield FABIA_MONTE_CARLO_MD.encode("utf-8")
                table_yielded = True
            else:
                yield "Fabia için geçerli donanımlar: Premium / Monte Carlo\n".encode("utf-8")

        elif model_name == "scala":
            if "premium" in trim_name:
                yield SCALA_PREMIUM_MD.encode("utf-8")
                table_yielded = True
            elif "monte" in trim_name:
                yield SCALA_MONTE_CARLO_MD.encode("utf-8")
                table_yielded = True
            elif "elite" in trim_name:
                yield SCALA_ELITE_MD.encode("utf-8")
                table_yielded = True
            else:
                yield "Scala için geçerli donanımlar: Premium / Monte Carlo / Elite\n".encode("utf-8")

        elif model_name == "kamiq":
            if "elite" in trim_name:
                yield KAMIQ_ELITE_MD.encode("utf-8")
                table_yielded = True
            elif "premium" in trim_name:
                yield KAMIQ_PREMIUM_MD.encode("utf-8")
                table_yielded = True
            elif "monte" in trim_name:
                yield KAMIQ_MONTE_CARLO_MD.encode("utf-8")
                table_yielded = True
            else:
                yield "Kamiq için geçerli donanımlar: Elite / Premium / Monte Carlo\n".encode("utf-8")

        elif model_name == "karoq":
            if "premium" in trim_name:
                yield KAROQ_PREMIUM_MD.encode("utf-8")
                table_yielded = True
            elif "prestige" in trim_name:
                yield KAROQ_PRESTIGE_MD.encode("utf-8")
                table_yielded = True
            elif "sportline" in trim_name:
                yield KAROQ_SPORTLINE_MD.encode("utf-8")
                table_yielded = True
            else:
                yield "Karoq için geçerli donanımlar: Premium / Prestige / Sportline\n".encode("utf-8")

        else:
            yield f"'{model_name}' modeli için opsiyonel tablo bulunamadı.\n".encode("utf-8")

        if table_yielded:
            # Diğer donanım linkleri
            if model_name == "fabia":
                all_trims = ["premium", "monte carlo"]
            elif model_name == "scala":
                all_trims = ["elite", "premium", "monte carlo"]
            elif model_name == "kamiq":
                all_trims = ["elite", "premium", "monte carlo"]
            elif model_name == "karoq":
                all_trims = ["premium", "prestige", "sportline"]
            else:
                all_trims = []

            normalized_current = trim_name.lower().strip()
            other_trims = [t for t in all_trims if t not in normalized_current]

            if other_trims:
                html_snippet = """
<br><br>
<div style="margin-top:10px;">
  <b>Diğer donanımlarımıza ait opsiyonel donanımları görmek için donanıma tıklamanız yeterli:</b>
  <ul>
"""
                for ot in other_trims:
                    command_text = f"{model_name} {ot} opsiyonel"
                    display_text = ot.title()
                    html_snippet += f"""    <li>
      <a href="#" onclick="sendMessage('{command_text}'); return false;">{display_text}</a>
    </li>
"""

                html_snippet += "  </ul>\n</div>\n"
                yield html_snippet.encode("utf-8")

        self.user_states[user_id]["pending_opsiyonel_model"] = None

    def run(self, debug=True):
        self.app.run(debug=debug)

    def shutdown(self):
        self.stop_worker = True
        self.worker_thread.join(5.0)
        self.logger.info("ChatbotAPI shutdown complete.")
