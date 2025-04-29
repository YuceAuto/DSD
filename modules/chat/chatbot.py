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

# Karoq tabloları
from modules.data.karoq_data import (
    KAROQ_PREMIUM_MD,
    KAROQ_PRESTIGE_MD,
    KAROQ_SPORTLINE_MD
)

load_dotenv()

def normalize_trim_str(t: str) -> list:
    t = t.lower().strip()
    with_underscore = t.replace(" ", "_")
    no_space = t.replace(" ", "")
    return [t, with_underscore, no_space]

def extract_trims(text: str) -> set:
    text_lower = text.lower()
    possible_trims = ["premium", "monte carlo", "elite", "prestige", "sportline"]
    found_trims = set()

    for t in possible_trims:
        variants = normalize_trim_str(t)
        if any(v in text_lower for v in variants):
            found_trims.add(t)

    return found_trims

def extract_model_trim_pairs(text):
    pattern = r"(fabia|scala|kamiq|karoq)\s*(premium|monte carlo|elite|prestige|sportline)?"
    pairs = []

    # "ve", "&", "ile", "," gibi kelimelere göre parçalıyoruz.
    split_candidates = re.split(r"\b(?:ve|&|ile|,|and)\b", text.lower())

    for piece in split_candidates:
        piece = piece.strip()
        if not piece:
            continue
        matches = re.findall(pattern, piece)
        for m in matches:
            model = m[0].strip()
            trim = m[1].strip() if m[1] else ""
            pairs.append((model, trim))

    return pairs

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

        openai.api_key = os.getenv("OPENAI_API_KEY")
        self.client = openai

        self.config = Config()
        self.utils = Utils()

        self.image_manager = ImageManager(images_folder=os.path.join(static_folder, "images"))
        self.image_manager.load_images()

        self.markdown_processor = MarkdownProcessor()

        self.ASSISTANT_CONFIG = self.config.ASSISTANT_CONFIG
        self.ASSISTANT_NAME_MAP = self.config.ASSISTANT_NAME_MAP

        self.user_states = {}

        self.fuzzy_cache = {}
        self.fuzzy_cache_queue = queue.Queue()

        self.stop_worker = False
        self.worker_thread = threading.Thread(target=self._background_db_writer, daemon=True)
        self.worker_thread.start()

        self.CACHE_EXPIRY_SECONDS = 86400

        self.MODEL_VALID_TRIMS = {
            "fabia": ["premium", "monte carlo"],
            "scala": ["elite", "premium", "monte carlo"],
            "kamiq": ["elite", "premium", "monte carlo"],
            "karoq": ["premium", "prestige", "sportline"]
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
            return render_template("index.html")

        @self.app.route("/ask", methods=["POST"])
        def ask():
            return self._ask()

        @self.app.route("/check_session", methods=["GET"])
        def check_session():
            if 'last_activity' in session:
                now = time.time()
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

    def _correct_all_typos(self, user_message: str) -> str:
        step1 = self._correct_image_keywords(user_message)
        final_corrected = self._correct_trim_typos(step1)
        return final_corrected

    def _correct_image_keywords(self, user_message: str) -> str:
        possible_image_words = [
            "görsel", "görseller", "resim", "resimler", "fotoğraf", "fotoğraflar"
        ]
        splitted = user_message.split()
        corrected_tokens = []

        for token in splitted:
            best = self.utils.fuzzy_find(token, possible_image_words, threshold=0.7)
            if best:
                corrected_tokens.append(best)
            else:
                corrected_tokens.append(token)
        return " ".join(corrected_tokens)

    def _correct_trim_typos(self, user_message: str) -> str:
        known_words = ["premium", "elite", "monte", "carlo", "prestige", "sportline"]
        splitted = user_message.split()
        new_tokens = []
        for token in splitted:
            best = self.utils.fuzzy_find(token, known_words, threshold=0.7)
            if best:
                new_tokens.append(best)
            else:
                new_tokens.append(token)

        # "monte carlo" birleştirme
        combined_tokens = []
        skip_next = False
        for i in range(len(new_tokens)):
            if skip_next:
                skip_next = False
                continue
            if i < len(new_tokens) - 1:
                if (new_tokens[i].lower() == "monte" and new_tokens[i+1].lower() == "carlo"):
                    combined_tokens.append("monte carlo")
                    skip_next = True
                else:
                    combined_tokens.append(new_tokens[i])
            else:
                combined_tokens.append(new_tokens[i])

        return " ".join(combined_tokens)

    def _search_in_assistant_cache(self, user_id, assistant_id, new_question, threshold):
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
        ans, ratio = self._search_in_assistant_cache(user_id, assistant_id, new_question, threshold)
        if ans:
            return ans
        return None

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

        if 'last_activity' not in session:
            session['last_activity'] = time.time()
        else:
            session['last_activity'] = time.time()

        corrected_message = self._correct_all_typos(user_message)
        user_models_in_msg = self._extract_models(corrected_message)

        if user_id not in self.user_states:
            self.user_states[user_id] = {}
            self.user_states[user_id]["threads"] = {}

        last_models = self.user_states[user_id].get("last_models", set())

        # Eğer cümlede model yok ama önceden hatırlanan model varsa cümleye ekleyelim
        if not user_models_in_msg and last_models:
            joined_models = " ve ".join(last_models)
            corrected_message = f"{joined_models} {corrected_message}".strip()
            user_models_in_msg = self._extract_models(corrected_message)
            self.logger.info(f"[MODEL-EKLEME] Önceki modeller eklendi -> {joined_models}")

        if user_models_in_msg:
            self.user_states[user_id]["last_models"] = user_models_in_msg

        word_count = len(corrected_message.strip().split())
        local_threshold = 1.0 if word_count < 5 else 0.8

        lower_corrected = corrected_message.lower().strip()

        old_assistant_id = self.user_states[user_id].get("assistant_id")
        new_assistant_id = None
        if len(user_models_in_msg) == 1:
            found_model = list(user_models_in_msg)[0]
            new_assistant_id = self._assistant_id_from_model_name(found_model)
        elif len(user_models_in_msg) > 1:
            first_model = list(user_models_in_msg)[0]
            new_assistant_id = self._assistant_id_from_model_name(first_model)

        if new_assistant_id is None and old_assistant_id:
            new_assistant_id = old_assistant_id

        if not new_assistant_id:
            new_assistant_id = self._pick_least_busy_assistant()
            if not new_assistant_id:
                save_to_db(user_id, user_message, "Uygun asistan bulunamadı.")
                return self.app.response_class("Uygun bir asistan bulunamadı.\n", mimetype="text/plain")

        self.user_states[user_id]["assistant_id"] = new_assistant_id

        is_image_req = self.utils.is_image_request(corrected_message)

        user_trims_in_msg = set()
        if "premium" in lower_corrected:
            user_trims_in_msg.add("premium")
        if "monte carlo" in lower_corrected:
            user_trims_in_msg.add("monte carlo")
        if "elite" in lower_corrected:
            user_trims_in_msg.add("elite")
        if "prestige" in lower_corrected:
            user_trims_in_msg.add("prestige")
        if "sportline" in lower_corrected:
            user_trims_in_msg.add("sportline")

        cached_answer = None
        if not is_image_req:
            cached_answer = self._find_fuzzy_cached_answer(
                user_id,
                corrected_message,
                new_assistant_id,
                threshold=local_threshold
            )
            if cached_answer:
                answer_text = cached_answer.decode("utf-8")
                models_in_answer = self._extract_models(answer_text)
                if user_models_in_msg and not user_models_in_msg.issubset(models_in_answer):
                    self.logger.info("Model uyuşmazlığı -> cache bypass.")
                    cached_answer = None
                else:
                    trims_in_answer = extract_trims(answer_text)
                    if len(user_trims_in_msg) == 1:
                        single_trim = list(user_trims_in_msg)[0]
                        if (single_trim not in trims_in_answer) or (len(trims_in_answer) > 1):
                            self.logger.info("Trim uyuşmazlığı -> cache bypass.")
                            cached_answer = None
                    elif len(user_trims_in_msg) > 1:
                        if user_trims_in_msg != trims_in_answer:
                            self.logger.info("Trim uyuşmazlığı (çoklu) -> cache bypass.")
                            cached_answer = None

                if cached_answer:
                    self.logger.info("Fuzzy cache match bulundu, önbellekten yanıt.")
                    time.sleep(1)  # 1 sn bekleme (opsiyonel)
                    return self.app.response_class(cached_answer, mimetype="text/plain")

        def caching_generator():
            chunks = []
            for chunk in self._generate_response(corrected_message, user_id):
                chunks.append(chunk)
                yield chunk
            if not is_image_req:
                final_bytes = b"".join(chunks)
                self._store_in_fuzzy_cache(user_id, corrected_message, final_bytes, new_assistant_id)

        return self.app.response_class(caching_generator(), mimetype="text/plain")

    def _extract_models(self, text: str) -> set:
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
        model_name = model_name.lower()
        for asst_id, keywords in self.ASSISTANT_CONFIG.items():
            for kw in keywords:
                if kw.lower() == model_name:
                    return asst_id
        return None

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

    def _show_categories_links(self, model, trim):
        model_title = model.title()
        trim_title = trim.title() if trim else ""
        if trim_title:
            base_cmd = f"{model} {trim}"
            heading = f"<b>{model_title} {trim_title} Kategoriler</b><br>"
        else:
            base_cmd = f"{model}"
            heading = f"<b>{model_title} Kategoriler</b><br>"

        categories = [
            ("Dijital Gösterge Paneli", "dijital gösterge paneli"),
            ("Direksiyon Simidi", "direksiyon simidi"),
            ("Döşeme", "döşeme"),
            ("Jant", "jant"),
            ("Multimedya", "multimedya"),
            ("Renkler", "renkler"),
        ]
        html_snippet = heading
        for label, keyw in categories:
            link_cmd = f"{base_cmd} {keyw}".strip()
            html_snippet += f"""&bull; <a href="#" onclick="sendMessage('{link_cmd}');return false;">{label}</a><br>"""

        return html_snippet

    def _exclude_other_trims(self, image_list, requested_trim):
        requested_trim = requested_trim.lower().strip()
        if not requested_trim:
            return image_list

        all_trims = ["premium", "monte carlo", "elite", "prestige", "sportline"]
        requested_variants = normalize_trim_str(requested_trim)

        filtered = []
        for img_file in image_list:
            lower_img = img_file.lower()

            conflict_found = False
            for other_trim in all_trims:
                other_trim = other_trim.lower().strip()
                if other_trim == requested_trim:
                    continue
                other_variants = normalize_trim_str(other_trim)
                if any(ov in lower_img for ov in other_variants):
                    conflict_found = True
                    break

            if conflict_found:
                continue

            # Trim adının en az bir varyantı resim path'inde geçsin
            if not any(rv in lower_img for rv in requested_variants):
                continue

            filtered.append(img_file)

        return filtered

    def _show_multiple_image_cards(self, pairs):
        html = (
            '<div style="display: flex; flex-wrap: wrap; gap: 20px; '
            'justify-content: space-around;">'
        )
        for (model, trim) in pairs:
            img_html, base_name = self._get_single_random_color_image_html(model, trim)
            friendly_title = self._make_friendly_image_title(model, trim, base_name)

            cat_links_html = self._show_categories_links(model, trim)
            card_block = f"""
            <div style="width: 420px; border: 1px solid #ccc; border-radius: 8px;
                        padding: 10px; text-align: center;">
                <h4 style="margin-bottom:8px;">{model.title()} {trim.title()}</h4>
                <hr style="margin:0 0 10px 0;">
                <p><b>{friendly_title}</b></p>
                <div style="margin-bottom:12px;">
                    {img_html}
                </div>
                <hr>
                {cat_links_html}
            </div>
            """
            html += card_block

        html += "</div>"
        return html

    def _make_friendly_image_title(self, model: str, trim: str, base_name: str) -> str:
        parts = base_name.split("_")
        skip_list = [model.lower(), trim.lower(), "renk"]

        filtered = []
        for p in parts:
            if p.lower() not in skip_list:
                filtered.append(p)

        color_part = " ".join(filtered)
        model_title = model.title()
        trim_title = trim.title() if trim else ""

        if trim:
            return (
                f"İşte aşağıda {model_title} {trim_title}'in "
                f"özel renk paketinden {color_part} görselini bulabilirsin."
            )
        else:
            return (
                f"İşte aşağıda {model_title}'in "
                f"özel renk paketinden {color_part} görselini bulabilirsin."
            )

    # ------------------------------
    # Aşağıdaki fonksiyon:
    #  Fabia/Scala/Kamiq + (jant/direksiyon) → popup_size='smaller'
    #  Diğer her şey normal.
    # ------------------------------
    def _show_single_random_color_image(self, model, trim):
        model_trim_str = f"{model} {trim}".strip().lower()
        all_color_images = []
        found_any = False

        for clr in self.config.KNOWN_COLORS:
            filter_str = f"{model_trim_str} {clr}"
            results = self.image_manager.filter_images_multi_keywords(filter_str)
            if results:
                all_color_images.extend(results)
                found_any = True

        if not found_any:
            for clr in self.config.KNOWN_COLORS:
                fallback_str = f"{model} {clr}"
                results2 = self.image_manager.filter_images_multi_keywords(fallback_str)
                if results2:
                    all_color_images.extend(results2)

        all_color_images = self._exclude_other_trims(all_color_images, trim)

        if not all_color_images:
            yield f"{model.title()} {trim.title()} için renk görseli bulunamadı.<br>".encode("utf-8")
            return

        chosen_image = random.choice(all_color_images)
        img_url = f"/static/images/{chosen_image}"
        base_name = os.path.splitext(os.path.basename(chosen_image))[0]

        # DİKKAT: Jant veya direksiyon kelimesi varsa + model fabia/scala/kamiq → popup_size='smaller'
        popup_size = "normal"
        if model.lower() in ["fabia", "scala", "kamiq"]:
            low_name = base_name.lower()
            if "jant" in low_name or "direksiyon" in low_name:
                popup_size = "smaller"

        friendly_title = self._make_friendly_image_title(model, trim, base_name)

        html_block = f"""
<p><b>{friendly_title}</b></p>
<div style="text-align: center; margin-bottom:20px;">
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}', '{popup_size}')">
    <img src="{img_url}" alt="{base_name}" style="max-width: 350px; cursor:pointer;" />
  </a>
</div>
"""
        yield html_block.encode("utf-8")

    # ------------------------------
    # Aynı mantığı kategori görsellerinde de uyguluyoruz:
    #  Fabia/Scala/Kamiq + (jant/direksiyon) -> popup_size='smaller'
    # ------------------------------
    def _show_category_images(self, model, trim, category):
        model_trim_str = f"{model} {trim}".strip().lower()

        if category in ["renkler", "renk"]:
            found_any = False
            all_color_images = []
            for clr in self.config.KNOWN_COLORS:
                flt = f"{model_trim_str} {clr}"
                results = self.image_manager.filter_images_multi_keywords(flt)
                if results:
                    all_color_images.extend(results)
                    found_any = True

            if not found_any:
                for clr in self.config.KNOWN_COLORS:
                    flt2 = f"{model} {clr}"
                    results2 = self.image_manager.filter_images_multi_keywords(flt2)
                    if results2:
                        all_color_images.extend(results2)

            all_color_images = self._exclude_other_trims(all_color_images, trim)

            heading = f"<b>{model.title()} {trim.title()} - Tüm Renk Görselleri</b><br>"
            yield heading.encode("utf-8")

            if not all_color_images:
                yield f"{model.title()} {trim.title()} için renk görseli bulunamadı.<br>".encode("utf-8")
                return

            yield b'<div style="display: flex; flex-wrap: wrap; gap: 20px;">'
            for img_file in all_color_images:
                img_url = f"/static/images/{img_file}"
                just_filename = os.path.basename(img_file)
                base_name = os.path.splitext(just_filename)[0].replace("_", " ")

                # Check popup size
                popup_size = "normal"
                if model.lower() in ["fabia", "scala", "kamiq"]:
                    low_name = base_name.lower()
                    if "jant" in low_name or "direksiyon" in low_name:
                        popup_size = "smaller"

                block_html = f"""
<div style="text-align: center; margin: 5px;">
  <div style="font-weight: bold; margin-bottom: 8px;">{base_name}</div>
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}', '{popup_size}')">
    <img src="{img_url}" alt="{base_name}" style="max-width: 300px; cursor:pointer;" />
  </a>
</div>
"""
                yield block_html.encode("utf-8")
            yield b"</div><br>"
            return

        filter_str = f"{model_trim_str} {category}".strip().lower()
        found_images = self.image_manager.filter_images_multi_keywords(filter_str)

        found_images = self._exclude_other_trims(found_images, trim)

        heading = f"<b>{model.title()} {trim.title()} - {category.title()} Görselleri</b><br>"
        yield heading.encode("utf-8")

        if not found_images:
            yield f"{model.title()} {trim.title()} için '{category}' görseli bulunamadı.<br>".encode("utf-8")
            return

        yield b'<div style="display: flex; flex-wrap: wrap; gap: 20px;">'
        for img_file in found_images:
            img_url = f"/static/images/{img_file}"
            just_filename = os.path.basename(img_file)
            base_name = os.path.splitext(just_filename)[0].replace("_", " ")

            # Check popup size
            popup_size = "normal"
            if model.lower() in ["fabia", "scala", "kamiq"]:
                low_name = base_name.lower()
                if "jant" in low_name or "direksiyon" in low_name:
                    popup_size = "smaller"

            block_html = f"""
<div style="text-align: center; margin: 5px;">
  <div style="font-weight: bold; margin-bottom: 8px;">{base_name}</div>
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}', '{popup_size}')">
    <img src="{img_url}" alt="{base_name}" style="max-width: 300px; cursor:pointer;" />
  </a>
</div>
"""
            yield block_html.encode("utf-8")
        yield b"</div><br>"

    def _generate_response(self, user_message, user_id):
        self.logger.info(f"[_generate_response] Kullanıcı ({user_id}): {user_message}")
        assistant_id = self.user_states[user_id].get("assistant_id", None)
        lower_msg = user_message.lower()

        if "current_trim" not in self.user_states[user_id]:
            self.user_states[user_id]["current_trim"] = ""

        pairs = extract_model_trim_pairs(lower_msg)
        is_image_req = self.utils.is_image_request(lower_msg)

        # (A) Birden fazla model + görsel isteği
        if len(pairs) >= 2 and is_image_req:
            time.sleep(2)
            for (model, trim) in pairs:
                yield f"<b>{model.title()} Görselleri</b>".encode("utf-8")
                yield from self._show_single_random_color_image(model, trim)
                cat_links_html = self._show_categories_links(model, trim)
                yield cat_links_html.encode("utf-8")

            save_to_db(user_id, user_message, f"Çoklu görsel talebi: {pairs}")
            return

        # (B) Tekli "model + trim + görsel" pattern
        model_trim_image_pattern = (
            r"(fabia|scala|kamiq|karoq)"
            r"(?:\s+(premium|monte carlo|elite|prestige|sportline))?\s+"
            r"(?:görsel(?:er)?|resim(?:ler)?|foto(?:ğ|g)raf(?:lar)?)"
        )
        match = re.search(model_trim_image_pattern, lower_msg)
        if match:
            time.sleep(2)
            matched_model = match.group(1)
            matched_trim = match.group(2) or ""

            if matched_trim and (matched_trim not in self.MODEL_VALID_TRIMS[matched_model]):
                yield from self._yield_invalid_trim_message(matched_model, matched_trim)
                return

            self.user_states[user_id]["current_trim"] = matched_trim
            yield from self._show_single_random_color_image(matched_model, matched_trim)
            cat_links_html = self._show_categories_links(matched_model, matched_trim)
            yield cat_links_html.encode("utf-8")

            save_to_db(user_id, user_message,
                       f"{matched_model.title()} {matched_trim.title()} -> tek renk + linkler")
            return

        # (C) "model + trim + kategori" pattern
        categories_pattern = r"(dijital gösterge paneli|direksiyon simidi|döşeme|jant|multimedya|renkler)"
        cat_match = re.search(
            fr"(fabia|scala|kamiq|karoq)\s*(premium|monte carlo|elite|prestige|sportline)?\s*({categories_pattern})",
            lower_msg
        )
        if cat_match:
            time.sleep(2)
            matched_model = cat_match.group(1)
            matched_trim = cat_match.group(2) or ""
            matched_category = cat_match.group(3)

            if matched_trim and (matched_trim not in self.MODEL_VALID_TRIMS[matched_model]):
                yield from self._yield_invalid_trim_message(matched_model, matched_trim)
                return

            self.user_states[user_id]["current_trim"] = matched_trim
            yield from self._show_category_images(matched_model, matched_trim, matched_category)
            cat_links_html = self._show_categories_links(matched_model, matched_trim)
            yield cat_links_html.encode("utf-8")

            save_to_db(user_id, user_message,
                       f"{matched_model.title()} {matched_trim} -> kategori: {matched_category}")
            return

        # (D) Opsiyonel tablo istekleri
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
            user_models_in_msg2 = self._extract_models(user_message)
            if len(user_models_in_msg2) == 1:
                found_model = list(user_models_in_msg2)[0]
            elif len(user_models_in_msg2) > 1:
                found_model = list(user_models_in_msg2)[0]

            if not found_model and assistant_id:
                found_model = self.ASSISTANT_NAME_MAP.get(assistant_id, "").lower()

            if not found_model:
                yield "Hangi modelin opsiyonel donanımlarını görmek istersiniz?".encode("utf-8")
                return
            else:
                self.user_states[user_id]["pending_opsiyonel_model"] = found_model
                # Tek trim yakalandıysa doğrudan tabloyu göster
                if len(user_trims_in_msg) == 1:
                    found_trim = list(user_trims_in_msg)[0]
                    if found_trim not in self.MODEL_VALID_TRIMS.get(found_model, []):
                        yield from self._yield_invalid_trim_message(found_model, found_trim)
                        return

                    time.sleep(2)
                    save_to_db(user_id, user_message,
                               f"{found_model.title()} {found_trim.title()} opsiyonel tablosu.")
                    yield from self._yield_opsiyonel_table(user_id, user_message, found_model, found_trim)
                    return
                else:
                    # Kullanıcıya tıklanabilir linklerle donanım seçeneklerini göster
                    if found_model == "fabia":
                        yield from self._yield_trim_options("fabia", ["premium", "monte carlo"])
                        return
                    elif found_model == "scala":
                        yield from self._yield_trim_options("scala", ["elite", "premium", "monte carlo"])
                        return
                    elif found_model == "kamiq":
                        yield from self._yield_trim_options("kamiq", ["elite", "premium", "monte carlo"])
                        return
                    elif found_model == "karoq":
                        yield from self._yield_trim_options("karoq", ["premium", "prestige", "sportline"])
                        return
                    else:
                        yield f"'{found_model}' modeli için opsiyonel donanım listesi tanımlanmamış.\n".encode("utf-8")
                        return

        if pending_ops_model:
            # Kullanıcı, opsiyonel model seçimini yapmış ama trim belirtmeden geldiyse...
            if user_trims_in_msg:
                if len(user_trims_in_msg) == 1:
                    found_trim = list(user_trims_in_msg)[0]
                    if found_trim not in self.MODEL_VALID_TRIMS.get(pending_ops_model, []):
                        yield from self._yield_invalid_trim_message(pending_ops_model, found_trim)
                        return

                    time.sleep(2)
                    save_to_db(user_id, user_message,
                               f"{pending_ops_model.title()} {found_trim.title()} opsiyonel tablosu.")
                    yield from self._yield_opsiyonel_table(user_id, user_message, pending_ops_model, found_trim)
                    return
                else:
                    # Birden çok trim yakalanmış -> Seçim yapması gerekiyor
                    if pending_ops_model.lower() == "fabia":
                        yield from self._yield_trim_options("fabia", ["premium", "monte carlo"])
                        return
                    elif pending_ops_model.lower() == "scala":
                        yield from self._yield_trim_options("scala", ["elite", "premium", "monte carlo"])
                        return
                    elif pending_ops_model.lower() == "kamiq":
                        yield from self._yield_trim_options("kamiq", ["elite", "premium", "monte carlo"])
                        return
                    elif pending_ops_model.lower() == "karoq":
                        yield from self._yield_trim_options("karoq", ["premium", "prestige", "sportline"])
                        return
                    else:
                        yield f"'{pending_ops_model}' modeli için opsiyonel donanım listesi tanımlanmamış.\n".encode("utf-8")
                        return
            else:
                # Hiç trim söylenmedi -> linklerle soralım
                if pending_ops_model.lower() == "fabia":
                    yield from self._yield_trim_options("fabia", ["premium", "monte carlo"])
                    return
                elif pending_ops_model.lower() == "scala":
                    yield from self._yield_trim_options("scala", ["elite", "premium", "monte carlo"])
                    return
                elif pending_ops_model.lower() == "kamiq":
                    yield from self._yield_trim_options("kamiq", ["elite", "premium", "monte carlo"])
                    return
                elif pending_ops_model.lower() == "karoq":
                    yield from self._yield_trim_options("karoq", ["premium", "prestige", "sportline"])
                    return
                else:
                    yield f"'{pending_ops_model}' modeli için opsiyonel donanım listesi tanımlanmamış.\n".encode("utf-8")
                    return

        # (F) Fallback eklendi: Kullanıcı görsel istiyor ama
        # yukarıdaki (A)-(D) hiçbir koşula uymadıysa buraya düşer:
        if is_image_req:
            user_models_in_msg2 = self._extract_models(user_message)
            if not user_models_in_msg2 and "last_models" in self.user_states[user_id]:
                user_models_in_msg2 = self.user_states[user_id]["last_models"]

            if user_models_in_msg2:
                if len(user_models_in_msg2) > 1:
                    yield "Birden fazla model algılandı, rastgele görseller paylaşıyorum...<br>".encode("utf-8")
                    for m in user_models_in_msg2:
                        yield f"<b>{m.title()} Görselleri</b><br>".encode("utf-8")
                        yield from self._show_single_random_color_image(m, "")
                        cat_links_html = self._show_categories_links(m, "")
                        yield cat_links_html.encode("utf-8")
                    save_to_db(user_id, user_message, f"Birden çok model fallback: {user_models_in_msg2}")
                    return
                else:
                    single_model = list(user_models_in_msg2)[0]
                    yield f"<b>{single_model.title()} için rastgele görseller</b><br>".encode("utf-8")
                    yield from self._show_single_random_color_image(single_model, "")
                    cat_links_html = self._show_categories_links(single_model, "")
                    yield cat_links_html.encode("utf-8")

                    save_to_db(user_id, user_message, f"{single_model.title()} fallback görselleri")
                    return
            else:
                yield "Hangi modelin görsellerine bakmak istersiniz? (Fabia, Kamiq, Scala, Karoq vb.)<br>".encode("utf-8")
                save_to_db(user_id, user_message, "Model belirtilmediği için fallback sorusu")
                return

        # (E) Normal Chat (OpenAI) ...
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

        except Exception as e:
            self.logger.error(f"Yanıt oluşturma hatası: {str(e)}")
            save_to_db(user_id, user_message, f"Hata: {str(e)}")
            yield f"Bir hata oluştu: {str(e)}\n".encode("utf-8")

    def _yield_invalid_trim_message(self, model, invalid_trim):
        msg = f"{model.title()} {invalid_trim.title()} modelimiz bulunmamaktadır.<br>"
        msg += (f"{model.title()} {invalid_trim.title()} modelimiz yok. Aşağıdaki donanımlarımızı inceleyebilirsiniz:"
                f"<br><br>")
        yield msg.encode("utf-8")

        valid_trims = self.MODEL_VALID_TRIMS.get(model, [])
        for vt in valid_trims:
            cmd_str = f"{model} {vt} görsel"
            link_label = f"{model.title()} {vt.title()}"
            link_html = f"""&bull; <a href="#" onclick="sendMessage('{cmd_str}');return false;">{link_label}</a><br>"""
            yield link_html.encode("utf-8")

    def _yield_opsiyonel_table(self, user_id, user_message, model_name, trim_name):
        time.sleep(2)

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

    def _yield_trim_options(self, model: str, trim_list: list):
        model_title = model.title()
        msg = f"Hangi donanımı görmek istersiniz?<br><br>"

        for trim in trim_list:
            trim_title = trim.title()
            command_text = f"{model} {trim} opsiyonel"
            link_label = f"{model_title} {trim_title}"
            msg += f"""&bull; <a href="#" onclick="sendMessage('{command_text}');return false;">{link_label}</a><br>"""

        yield msg.encode("utf-8")

    def run(self, debug=True):
        self.app.run(debug=debug)

    def shutdown(self):
        self.stop_worker = True
        self.worker_thread.join(5.0)
        self.logger.info("ChatbotAPI shutdown complete.")
