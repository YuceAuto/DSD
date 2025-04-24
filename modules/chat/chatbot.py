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

def extract_model_trim_pairs(text):
    """
    Kullanıcı metninden birden fazla (model, trim) çiftini yakalar.
    Örnek: "fabia premium ve scala elite görsel" -> [("fabia","premium"), ("scala","elite")]
    """
    pattern = r"(fabia|scala|kamiq|karoq)\s*(premium|monte carlo|elite|prestige|sportline)?"
    pairs = []

    # "ve", "&", "ile", "," gibi kelimelere göre parçalıyoruz.
    split_candidates = re.split(r"\b(?:ve|&|ile|,|and)\b", text.lower())

    for piece in split_candidates:
        piece = piece.strip()
        if not piece:
            continue
        match = re.search(pattern, piece)
        if match:
            model = match.group(1).strip()
            trim  = match.group(2).strip() if match.group(2) else ""
            pairs.append((model, trim))

    return pairs

def normalize_trim_str(t: str) -> list:
    """
    Bir trim ifadesinin ("monte carlo" vb.) birkaç farklı yazılış varyasyonunu döndürür.
    Örn: "monte carlo" -> ["monte carlo", "monte_carlo", "montecarlo"]
    """
    t = t.lower().strip()
    with_underscore = t.replace(" ", "_")
    no_space = t.replace(" ", "")
    return [t, with_underscore, no_space]

# YENİ EKLENEN TRIM KONTROLÜ: Cevap içerisindeki trim'leri bulmak için basit fonksiyon
def extract_trims(text: str) -> set:
    text_lower = text.lower()
    possible_trims = ["premium", "monte carlo", "elite", "prestige", "sportline"]
    found_trims = set()

    for t in possible_trims:
        variants = normalize_trim_str(t)  # "monte carlo" => ["monte carlo", "monte_carlo", "montecarlo"]
        if any(v in text_lower for v in variants):
            found_trims.add(t)

    return found_trims


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

        # OpenAI ayarı
        openai.api_key = os.getenv("OPENAI_API_KEY")
        self.client = openai

        self.config = Config()
        self.utils = Utils()

        # ImageManager (alt klasörleri de tarayan sürüm)
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

        # MODEL - TRIM EŞLEŞMELERİ (Geçerli donanımlar)
        self.MODEL_VALID_TRIMS = {
            "fabia": ["premium", "monte carlo"],
            "scala": ["elite", "premium", "monte carlo"],
            "kamiq": ["elite", "premium", "monte carlo"],
            "karoq": ["premium", "prestige", "sportline"]
        }

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
        """Opsiyonel: Cache'i DB'den yükleme fonksiyonu (isterseniz)."""
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

    # -------------------------------------------------------------------------
    # Basit imla düzeltmeleri
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Fuzzy cache arama/kaydetme
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Flask /ask endpoint -> self._ask
    # -------------------------------------------------------------------------
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

        # Session zaman damgası
        if 'last_activity' not in session:
            session['last_activity'] = time.time()
        else:
            session['last_activity'] = time.time()

        # 1) Mesajı fuzzy şekilde düzelt
        corrected_message = self._correct_all_typos(user_message)

        # 2) Modelleri tespit et
        user_models_in_msg = self._extract_models(corrected_message)

        # Kullanıcı state
        if user_id not in self.user_states:
            self.user_states[user_id] = {}
            self.user_states[user_id]["threads"] = {}

        last_models = self.user_states[user_id].get("last_models", set())

        # Önceki modeli ekle (isteğe bağlı)
        if not user_models_in_msg and last_models:
            joined_models = " ve ".join(last_models)
            corrected_message = f"{joined_models} {corrected_message}".strip()
            user_models_in_msg = self._extract_models(corrected_message)
            self.logger.info(f"[MODEL-EKLEME] Önceki modeller eklendi -> {joined_models}")

        if user_models_in_msg:
            self.user_states[user_id]["last_models"] = user_models_in_msg

        # Threshold
        word_count = len(corrected_message.strip().split())
        local_threshold = 1.0 if word_count < 5 else 0.8

        lower_corrected = corrected_message.lower().strip()

        # Asistan ID seçimi
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

        # 3) Görsel isteği mi?
        is_image_req = self.utils.is_image_request(corrected_message)

        # YENİ: Kullanıcının mesajındaki trim’leri bulalım
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

        # 4) Cache kontrolü (görsel talebi değilse)
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

                # Model uyuşmazlığı?
                models_in_answer = self._extract_models(answer_text)
                if user_models_in_msg and not user_models_in_msg.issubset(models_in_answer):
                    self.logger.info("Model uyuşmazlığı -> cache bypass.")
                    cached_answer = None
                else:
                    # YENİ EKLENEN TRIM KONTROLÜ
                    trims_in_answer = extract_trims(answer_text)

                    # Eğer kullanıcı TEK trim istediyse ve cevapta birden fazla trim varsa -> Bypass
                    # Ya da o tek trim hiç yoksa -> Bypass
                    if len(user_trims_in_msg) == 1:
                        single_trim = list(user_trims_in_msg)[0]
                        if (single_trim not in trims_in_answer) or (len(trims_in_answer) > 1):
                            self.logger.info("Trim uyuşmazlığı -> cache bypass.")
                            cached_answer = None
                    elif len(user_trims_in_msg) > 1:
                        # Kullanıcı birden fazla trim sormuşsa,
                        # cevapta bunların TAM karşılığı var mı diye bakabilirsiniz.
                        # Örnek: basit check -> set eşitliği
                        if user_trims_in_msg != trims_in_answer:
                            self.logger.info("Trim uyuşmazlığı (çoklu) -> cache bypass.")
                            cached_answer = None

                if cached_answer:
                    # Geçerli kaldıysa, direkt yanıt
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

    # ===============================================================
    #   Yardımcı fonksiyon: kategori linkleri
    # ===============================================================
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

    # --------------------------------------------------------
    #  TRIM DIŞI KELİMELERİ HARİÇ BIRAKMA FONKSİYONU
    # --------------------------------------------------------
    def _exclude_other_trims(self, image_list, requested_trim):
        """
        Kullanıcı trim belirttiğinde, farklı trim'leri dosya adında barındıranları eler.
        Ör: "premium" istendiyse, "monte carlo" / "elite" / vb. geçen dosya atılmalı.
        Ayrıca requested_trim'in varyasyonlarının da mutlaka dosya adında bulunması sağlanır.
        """
        requested_trim = requested_trim.lower().strip()
        if not requested_trim:
            # Trim yoksa hiçbir şey dışlama.
            return image_list

        # Tüm olası trim'ler:
        all_trims = ["premium", "monte carlo", "elite", "prestige", "sportline"]

        requested_variants = normalize_trim_str(requested_trim)

        filtered = []
        for img_file in image_list:
            lower_img = img_file.lower()

            # 1) Farklı trim var mı diye bak
            conflict_found = False
            for other_trim in all_trims:
                other_trim = other_trim.lower().strip()
                if other_trim == requested_trim:
                    continue  # İstediğimiz trim ise sorun yok

                # "other_trim" için olası yazılış varyasyonları
                other_variants = normalize_trim_str(other_trim)

                # Eğer bu 'other_variants' içinden biri dosya adında bulunuyorsa
                # çatışma var => bu dosya atılmalı
                if any(ov in lower_img for ov in other_variants):
                    conflict_found = True
                    break

            if conflict_found:
                continue

            # 2) İstediğimiz trim mutlaka geçsin
            if not any(rv in lower_img for rv in requested_variants):
                # Dosya adında "monte_carlo" vs. hiç yoksa
                continue

            filtered.append(img_file)

        return filtered

    # ===============================================================
    #   Birden çok görsel kartı (Kategori linkleri + rastgele resim)
    # ===============================================================
    def _show_multiple_image_cards(self, pairs):
        """
        Örneğin pairs = [("fabia","premium"), ("scala","elite")]
        Her bir model/donanım için hem rastgele renk görselini,
        hem de kategori linklerini tek bir "kart" içinde gösterir.
        """
        html = (
            '<div style="display: flex; flex-wrap: wrap; gap: 20px; '
            'justify-content: space-around;">'
        )

        for (model, trim) in pairs:
            img_html, base_name = self._get_single_random_color_image_html(model, trim)
            cat_links_html = self._show_categories_links(model, trim)
            card_block = f"""
            <div style="width: 420px; border: 1px solid #ccc; border-radius: 8px;
                        padding: 10px; text-align: center;">
                <h4 style="margin-bottom:8px;">{model.title()} {trim.title()}</h4>
                <hr style="margin:0 0 10px 0;">
                <p><b>{model.title()} - Rastgele Renk Görseli</b></p>
                <div style="margin-bottom:12px;">
                    <div style="font-weight: bold; margin-bottom: 6px;">{base_name}</div>
                    {img_html}
                </div>
                <hr>
                {cat_links_html}
            </div>
            """
            html += card_block

        html += "</div>"
        return html

    def _get_single_random_color_image_html(self, model, trim):
        """
        (Aynı mantık, sadece HTML döndürür.)
        """
        model_trim_str = f"{model} {trim}".strip().lower()
        all_color_images = []

        for clr in self.config.KNOWN_COLORS:
            filter_str = f"{model_trim_str} {clr}"
            results = self.image_manager.filter_images_multi_keywords(filter_str)
            all_color_images.extend(results)

        # Fallback
        if not all_color_images:
            for clr in self.config.KNOWN_COLORS:
                fallback_str = f"{model} {clr}"
                results2 = self.image_manager.filter_images_multi_keywords(fallback_str)
                all_color_images.extend(results2)

        # Trim dışı kelime içeren dosyaları dışla
        all_color_images = self._exclude_other_trims(all_color_images, trim)

        if not all_color_images:
            msg = f"<p>{model.title()} {trim.title()} görseli bulunamadı.</p>"
            return msg, ""

        chosen_image = random.choice(all_color_images)
        img_url = f"/static/images/{chosen_image}"
        base_name = os.path.splitext(os.path.basename(chosen_image))[0]

        img_html = f"""
        <a href="#" data-toggle="modal" data-target="#imageModal" 
           onclick="showPopupImage('{img_url}')">
          <img src="{img_url}" alt="{base_name}" 
               style="max-width: 350px; cursor:pointer;" />
        </a>
        """
        return img_html, base_name

    # -------------------------------------------------------------------------
    # Asıl yanıt üretme fonksiyonu
    # -------------------------------------------------------------------------
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
                if len(user_trims_in_msg) == 1:
                    found_trim = list(user_trims_in_msg)[0]
                    if found_trim not in self.MODEL_VALID_TRIMS.get(found_model, []):
                        yield from self._yield_invalid_trim_message(found_model, found_trim)
                        return

                    save_to_db(user_id, user_message,
                               f"{found_model.title()} {found_trim.title()} opsiyonel tablosu.")
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
                    if found_trim not in self.MODEL_VALID_TRIMS.get(pending_ops_model, []):
                        yield from self._yield_invalid_trim_message(pending_ops_model, found_trim)
                        return

                    save_to_db(user_id, user_message,
                               f"{pending_ops_model.title()} {found_trim.title()} opsiyonel tablosu.")
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

        # (E) Normal Chat (OpenAI) ...
        if not assistant_id:
            save_to_db(user_id, user_message, "Uygun asistan bulunamadı.")
            yield "Uygun bir asistan bulunamadı.\n".encode("utf-8")
            return

        try:
            threads_dict = self.user_states[user_id].get("threads", {})
            thread_id = threads_dict.get(assistant_id)

            if not thread_id:
                # Varsayımsal "beta.threads" API (OpenAI'nin gerçekte böyle bir endpoint'i olmayabilir)
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

    # ==================================================================
    #  Tekil “invalid trim” ve “tekil kategori görselleri” fonksiyonları
    # ==================================================================
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

    def _show_single_random_color_image(self, model, trim):
        """
        Tekil rastgele renk görseli döndürür.
        """
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

        # Trim dışı kelimeleri dışla
        all_color_images = self._exclude_other_trims(all_color_images, trim)

        if not all_color_images:
            yield f"{model.title()} {trim.title()} için renk görseli bulunamadı.<br>".encode("utf-8")
            return

        chosen_image = random.choice(all_color_images)
        img_url = f"/static/images/{chosen_image}"
        base_name = os.path.splitext(os.path.basename(chosen_image))[0]

        html_block = f"""
<p><b>{model.title()} {trim.title()} - Rastgele Renk Görseli</b></p>
<div style="text-align: center; margin-bottom:20px;">
  <div style="font-weight: bold; margin-bottom: 6px;">{base_name}</div>
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}')">
    <img src="{img_url}" alt="{base_name}" style="max-width: 400px; cursor:pointer;" />
  </a>
</div>
"""
        yield html_block.encode("utf-8")

    def _show_category_images(self, model, trim, category):
        """
        Kullanıcı "fabia premium döşeme" vb. dediğinde çoklu görseli döndürür.
        """
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

            # Trim dışı kelimeleri dışla
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

                block_html = f"""
<div style="text-align: center; margin: 5px;">
  <div style="font-weight: bold; margin-bottom: 8px;">{base_name}</div>
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}')">
    <img src="{img_url}" alt="{base_name}" style="max-width: 300px; cursor:pointer;" />
  </a>
</div>
"""
                yield block_html.encode("utf-8")
            yield b"</div><br>"
            return

        filter_str = f"{model_trim_str} {category}".strip().lower()
        found_images = self.image_manager.filter_images_multi_keywords(filter_str)

        # Trim dışı kelimeleri dışla
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

            block_html = f"""
<div style="text-align: center; margin: 5px;">
  <div style="font-weight: bold; margin-bottom: 8px;">{base_name}</div>
  <a href="#" data-toggle="modal" data-target="#imageModal" onclick="showPopupImage('{img_url}')">
    <img src="{img_url}" alt="{base_name}" style="max-width: 300px; cursor:pointer;" />
  </a>
</div>
"""
            yield block_html.encode("utf-8")
        yield b"</div><br>"

    def _yield_opsiyonel_table(self, user_id, user_message, model_name, trim_name):
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

    def run(self, debug=True):
        self.app.run(debug=debug)

    def shutdown(self):
        self.stop_worker = True
        self.worker_thread.join(5.0)
        self.logger.info("ChatbotAPI shutdown complete.")
