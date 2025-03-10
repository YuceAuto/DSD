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
from modules.db import create_tables, save_to_db, send_email, get_db_connection

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

        # Session timeout (30 dakika)
        self.SESSION_TIMEOUT = 30 * 60

        # Kullanıcı bazlı state
        self.user_states = {}

        # ----- Fuzzy Cache ve Queue -----
        self.fuzzy_cache = {}
        self.fuzzy_cache_queue = queue.Queue()

        self.stop_worker = False
        self.worker_thread = threading.Thread(target=self._background_db_writer, daemon=True)
        self.worker_thread.start()

        # Önbellekteki cevabın geçerli kalma süresi (1 saat)
        self.CACHE_EXPIRY_SECONDS = 3600

        # Cross-assistant cache devrede
        self.CROSS_ASSISTANT_CACHE = True

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
                if now - session['last_activity'] > self.SESSION_TIMEOUT:
                    return jsonify({"active": False})
            return jsonify({"active": True})

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
        (Opsiyonel) DB'den son X kaydı çekip self.fuzzy_cache'e doldurabilirsiniz.
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
        Kullanıcı mesajındaki 'fabia', 'scala', 'kamiq' kelimelerini yakalar.
        """
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

        # Cross assistant cache
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

    def _ask(self):
        """
        Kullanıcıdan POST isteği ile gelen veriyi işleyerek yanıt oluşturur.
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

        # Session güncelleme
        if 'last_activity' not in session:
            session['last_activity'] = time.time()
        else:
            session['last_activity'] = time.time()

        corrected_message = self._correct_typos(user_message)
        lower_corrected = corrected_message.lower().strip()

        # Kullanıcının mesajında kaç model/donanım var?
        user_models = self._extract_models(corrected_message)
        user_trims = set()
        if "premium" in lower_corrected:
            user_trims.add("premium")
        if "monte carlo" in lower_corrected:
            user_trims.add("monte carlo")
        if "elite" in lower_corrected:
            user_trims.add("elite")

        new_assistant_id = None
        # 2+ model veya 2+ donanım -> All Models Bot
        if len(user_models) >= 2 or len(user_trims) >= 2:
            new_assistant_id = "asst_hiGn8YC08xM3amwG0cs2A3SN"

        old_assistant_id = None
        if user_id in self.user_states:
            old_assistant_id = self.user_states[user_id].get("assistant_id")

        # Eğer yukarıda 2+ modeli/donanımı yakalayamazsak, eski mantığa göre asistan seç
        if not new_assistant_id:
            for aid, keywords in self.ASSISTANT_CONFIG.items():
                if any(k.lower() in lower_corrected for k in keywords):
                    new_assistant_id = aid
                    break

        if user_id not in self.user_states:
            self.user_states[user_id] = {}
            self.user_states[user_id]["threads"] = {}

        if new_assistant_id:
            assistant_id = new_assistant_id
            allow_cross = False
        else:
            assistant_id = old_assistant_id
            allow_cross = False

        self.user_states[user_id]["assistant_id"] = assistant_id

        # Görsel isteği mi?
        is_image_req = self.utils.is_image_request(user_message)

        # Görsel isteklerinde cache kullanma
        if is_image_req:
            cached_answer, matched_question, found_asst_id = None, None, None
        else:
            cached_answer, matched_question, found_asst_id = self._find_fuzzy_cached_answer(
                user_id,
                corrected_message,
                assistant_id,
                threshold=0.8,
                allow_cross_assistant=allow_cross
            )

        if cached_answer and not is_image_req:
            # Model uyuşmazlığı kontrolü
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

                self.logger.info("Fuzzy cache match bulundu, önbellekten yanıt.")
                time.sleep(1)
                return self.app.response_class(cached_answer, mimetype="text/plain")

        def caching_generator():
            chunks = []
            for chunk in self._generate_response(corrected_message, user_id):
                chunks.append(chunk)
                yield chunk

            # Görsel isteği değilse yanıtı cache'e yaz
            if not is_image_req:
                final_bytes = b"".join(chunks)
                final_aid = self.user_states[user_id].get("assistant_id", assistant_id)
                self._store_in_fuzzy_cache(user_id, corrected_message, final_bytes, final_aid)

        return self.app.response_class(caching_generator(), mimetype="text/plain")

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

    def _render_side_by_side_images(self, images, context="model"):
        """
        Basit örnek: Görselleri yatay veya grid şekilde sıralama.
        """
        # Monte Carlo standart
        mc_std = [
            img for img in images
            if "monte" in img.lower()
               and "carlo" in img.lower()
               and "standart" in img.lower()
        ]
        # Premium opsiyonel
        pm_ops = [
            img for img in images
            if "premium" in img.lower()
               and "opsiyonel" in img.lower()
        ]
        others = [img for img in images if img not in mc_std and img not in pm_ops]

        if not images:
            yield "Bu kriterlere ait görsel bulunamadı.\n".encode("utf-8")
            return

        # 1) Sol sütun (Monte Carlo)
        yield """
<div style="display: flex; justify-content: space-between; gap: 60px;">
  <!-- SOL SÜTUN: MONTE CARLO STANDART -->
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

        # 2) Sağ sütun (Premium opsiyonel)
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

        # 3) Kalan (others)
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

    def _generate_response(self, user_message, user_id):
        self.logger.info(f"[_generate_response] Kullanıcı ({user_id}): {user_message}")

        assistant_id = self.user_states[user_id].get("assistant_id", None)
        assistant_name = self.ASSISTANT_NAME_MAP.get(assistant_id, "")
        lower_msg = user_message.lower()

        if "current_trim" not in self.user_states[user_id]:
            self.user_states[user_id]["current_trim"] = ""

        # --------------------------------------------------------
        # 1) MODEL + "görsel" -> renk (genel)
        # --------------------------------------------------------
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

        # --------------------------------------------------------
        # 2) Dış görsel istekleri
        # --------------------------------------------------------
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

        # --------------------------------------------------------
        # 3) İç görsel istekleri
        # --------------------------------------------------------
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

        # --------------------------------------------------------
        # 4) "Evet" kontrolü (renk seçimi vs.)
        # --------------------------------------------------------
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

        # --------------------------------------------------------
        # 5) Özel karşılaştırma (Fabia Premium vs Monte Carlo)
        # --------------------------------------------------------
        if ("fabia" in lower_msg
            and "premium" in lower_msg
            and "monte carlo" in lower_msg
            and self.utils.is_image_request(user_message)):
            fabia_pairs = [
                ("Fabia_Premium_Ay_Beyazı.png", "Fabia_Monte_Carlo_Ay_Beyazı.png"),
            ]
            save_to_db(user_id, user_message, "Fabia Premium vs Monte Carlo görsel karşılaştırma.")
            yield "<div style='display: flex; flex-direction: row; gap: 20px;'>".encode("utf-8")
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

        # --------------------------------------------------------
        # 6) Genel "görsel" isteği mi?
        # --------------------------------------------------------
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

        # --------------------------------------------------------
        # 7) Opsiyonel tablolar
        # --------------------------------------------------------
        # Eğer 2+ model veya 2+ donanım geçiyorsa tekil tablo bypass
        user_models_in_msg = self._extract_models(user_message)
        user_trims_in_msg = set()
        if "premium" in lower_msg:
            user_trims_in_msg.add("premium")
        if "elite" in lower_msg:
            user_trims_in_msg.add("elite")
        if "monte carlo" in lower_msg:
            user_trims_in_msg.add("monte carlo")

        if len(user_models_in_msg) >= 2 or len(user_trims_in_msg) >= 2:
            self.logger.info("Birden çok model veya donanım tespit edildi. Tekil tabloyu atlıyoruz.")
            # Direkt #8'e geçsin.
        else:
            # Tekil tablo (yalnızca 1 model + 1 donanım)
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

        # --------------------------------------------------------
        # 8) Normal Chat (OpenAI vb.)
        # --------------------------------------------------------
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

            save_to_db(user_id, user_message, assistant_response)

            # Renk ismi tespiti
            if "görsel olarak görmek ister misiniz?" in assistant_response.lower():
                detected_colors = self.utils.parse_color_names(assistant_response)
                if detected_colors:
                    self.user_states[user_id]["pending_color_images"] = detected_colors

        except Exception as e:
            self.logger.error(f"Yanıt oluşturma hatası: {str(e)}")
            save_to_db(user_id, user_message, f"Hata: {str(e)}")
            yield f"Bir hata oluştu: {str(e)}\n".encode("utf-8")

    def run(self, debug=True):
        self.app.run(debug=debug)

    def shutdown(self):
        self.stop_worker = True
        self.worker_thread.join(5.0)
        self.logger.info("ChatbotAPI shutdown complete.")
