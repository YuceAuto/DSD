# modules/bot_service.py

import time
import difflib
import re
import random
import queue
import threading
import logging

from flask import request, session, jsonify
from modules.db import create_tables, save_to_db, send_email, get_db_connection, update_customer_answer
from modules.utils import Utils

# Orijinal kodda tabloları import ediyordun:
from modules.data.scala_data import SCALA_ELITE_MD, SCALA_PREMIUM_MD, SCALA_MONTE_CARLO_MD
from modules.data.kamiq_data import KAMIQ_ELITE_MD, KAMIQ_PREMIUM_MD, KAMIQ_MONTE_CARLO_MD
from modules.data.fabia_data import FABIA_PREMIUM_MD, FABIA_MONTE_CARLO_MD

class BotService:
    """
    Chat/iş mantığının büyük kısmını yürüten sınıf.
    """

    def __init__(self, logger, config, utils, image_manager, markdown_processor, openai_client):
        self.logger = logger
        self.config = config
        self.utils = utils

        self.image_manager = image_manager
        self.markdown_processor = markdown_processor
        self.client = openai_client

        # MSSQL tablo oluşturmayı istersek buradan da yapabiliriz 
        create_tables()  

        # Kullanıcı bazlı state (model, asistan, vb.)
        self.user_states = {}

        # Fuzzy Cache
        self.fuzzy_cache = {}
        self.fuzzy_cache_queue = queue.Queue()

        # Arka plan thread’i durdurma bayrağı
        self.stop_worker = False

        # Önbellekteki cevabın geçerli kalma süresi
        self.CACHE_EXPIRY_SECONDS = 86400  # 1 gün

        # Asistan konfigleri (Config içerisinden)
        self.ASSISTANT_CONFIG = self.config.ASSISTANT_CONFIG
        self.ASSISTANT_NAME_MAP = self.config.ASSISTANT_NAME_MAP

        # Arka plan thread
        self.worker_thread = threading.Thread(target=self._background_db_writer, daemon=True)
        self.worker_thread.start()

    # -------------------------------------------------------------
    # 1) /ask endpoint'inde çağrılacak ana fonksiyon
    # -------------------------------------------------------------
    def handle_ask(self):
        """
        request.get_json() -> user_message, user_id çek.
        Metinsel veya görsel istekleri ayrıştır, cache vs.
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

        # Yazım hatası düzeltme
        corrected_message = self._correct_typos(user_message)

        # Fuzzy threshold (örnek mantık)
        word_count = len(corrected_message.strip().split())
        local_threshold = 1.0 if word_count < 5 else 0.8

        # Asistan belirleme
        assistant_id = self._determine_assistant_id(user_id, corrected_message)
        if not assistant_id:
            save_to_db(user_id, user_message, "Uygun asistan bulunamadı.")
            # Plain text olarak döndürüyoruz
            return "Uygun bir asistan bulunamadı.\n", 200

        # Görsel isteği mi? -> Cache devre dışı
        is_image_req = self.utils.is_image_request(corrected_message)
        cached_answer = None
        if not is_image_req:
            cached_answer = self._find_fuzzy_cached_answer(
                user_id, corrected_message, assistant_id, threshold=local_threshold
            )

        if cached_answer and not is_image_req:
            # Basit bir model uyuşmazlık kontrolü (örnek)
            # Orijinal koddaki “_extract_models()” benzeri
            user_models_in_msg = self._extract_models(corrected_message)
            answer_text = cached_answer.decode("utf-8")
            models_in_answer = self._extract_models(answer_text)

            if user_models_in_msg and not user_models_in_msg.issubset(models_in_answer):
                # Model uyuşmuyorsa cache bypass
                self.logger.info("[Cache] Model uyuşmazlığı nedeniyle bypass.")
            else:
                # Tek model varsa vs...
                self.logger.info("Fuzzy cache match bulundu, önbellekten yanıt.")
                # Bir saniye bekletme
                time.sleep(1)
                return cached_answer.decode("utf-8"), 200

        # Cache yok veya bypass -> Gerçek akış
        def caching_generator():
            chunks = []
            for chunk in self._generate_response(corrected_message, user_id):
                chunks.append(chunk)
                yield chunk

            if not is_image_req:
                # Bütün chunk'ları birleştirip memory'e al
                final_bytes = b"".join(chunks)
                self._store_in_fuzzy_cache(user_id, corrected_message, final_bytes, assistant_id)

        return caching_generator()

    # -------------------------------------------------------------
    # 2) /like endpoint’i (beğeni butonu)
    # -------------------------------------------------------------
    def handle_like(self):
        data = request.get_json()
        conv_id = data.get("conversation_id")
        if not conv_id:
            return jsonify({"error": "No conversation_id provided"}), 400
        try:
            update_customer_answer(conv_id, 1)
            return jsonify({"status": "ok"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # -------------------------------------------------------------
    # 3) Arkaplan thread (cache kaydını DB'ye yazma)
    # -------------------------------------------------------------
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

    # -------------------------------------------------------------
    # 4) BotService kapatılırken thread’i durdur
    # -------------------------------------------------------------
    def shutdown(self):
        self.stop_worker = True
        self.worker_thread.join(5.0)
        self.logger.info("BotService shutdown complete.")

    # -------------------------------------------------------------
    # 5) _generate_response: asıl iş mantığı (tablo, görsel, OpenAI vb.)
    # -------------------------------------------------------------
    def _generate_response(self, user_message, user_id):
        """
        Orijinal kodda _ask() içinde yaptığın gibi
        satır satır yield ederek cevap dönülen kısım.
        """
        self.logger.info(f"[_generate_response] Kullanıcı ({user_id}): {user_message}")

        # Hangi asistan?
        assistant_id = self.user_states[user_id].get("assistant_id", None)
        assistant_name = self.ASSISTANT_NAME_MAP.get(assistant_id, "")

        # user_states üzerinde "current_trim" yoksa varsayılan
        if "current_trim" not in self.user_states[user_id]:
            self.user_states[user_id]["current_trim"] = ""

        lower_msg = user_message.lower()

        # Tüm orijinal mantığı koruyoruz:
        #  - Görsel istekleri (dış, iç, renk, jant vs.)
        #  - Opsiyonel tablo istekleri
        #  - Normal chat (OpenAI)...

        # --------------------------------------------------------
        # Örnek: model + görsel pattern
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
        # Dış görsel istekleri (örnek)
        # --------------------------------------------------------
        if any(kw in lower_msg for kw in ["dış ", " dış", "dıs", "dis", "diş"]):
            if self.utils.is_image_request(user_message):
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
        # İç görsel istekleri (örnek)
        # --------------------------------------------------------
        pattern_ic = r"\b(iç|ic)\b"
        if re.search(pattern_ic, lower_msg) and self.utils.is_image_request(user_message):
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
        # Evet/hayır cevapları (örnek)
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
        # Opsiyonel donanım tabloları
        # --------------------------------------------------------
        user_models_in_msg = self._extract_models(user_message)
        user_trims_in_msg = set()
        if "premium" in lower_msg:
            user_trims_in_msg.add("premium")
        if "monte carlo" in lower_msg:
            user_trims_in_msg.add("monte carlo")
        if "elite" in lower_msg:
            user_trims_in_msg.add("elite")

        pending_ops_model = self.user_states[user_id].get("pending_opsiyonel_model", None)

        if "opsiyonel" in lower_msg:
            found_model = None
            if len(user_models_in_msg) == 1:
                found_model = list(user_models_in_msg)[0]
            elif len(user_models_in_msg) == 0 and assistant_id:
                fallback_model = self.ASSISTANT_NAME_MAP.get(assistant_id, "").lower()
                if fallback_model:
                    found_model = fallback_model

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
                    else:
                        yield "Hangi donanımı görmek istersiniz? (Elite / Premium / Monte Carlo)\n".encode("utf-8")
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
                    else:
                        yield "Birden fazla donanım tespit ettim, lütfen birini seçin. (Elite / Premium / Monte Carlo)\n".encode("utf-8")
                    return
            else:
                if pending_ops_model.lower() == "fabia":
                    yield "Hangi donanımı görmek istersiniz? (Premium / Monte Carlo)\n".encode("utf-8")
                else:
                    yield "Hangi donanımı görmek istersiniz? (Elite / Premium / Monte Carlo)\n".encode("utf-8")
                return

        # --------------------------------------------------------
        # Diğer durum: Normal Chat (OpenAI)
        # --------------------------------------------------------
        if not assistant_id:
            save_to_db(user_id, user_message, "Uygun asistan bulunamadı.")
            yield "Uygun bir asistan bulunamadı.\n".encode("utf-8")
            return

        try:
            # Burada OpenAI thread mantığı (orijinalde beta.threads) vs. yer alıyordu
            # Biz basitleştirmek için tek shot:
            # openai.Completion.create(...) benzeri

            # Örnek: Sadece sabit "dummy" yanıt:
            dummy_response = f"[Asistan={assistant_id}] Yanıt oluşturuluyor...\n"
            # DB'ye kaydet
            conversation_id = save_to_db(user_id, user_message, dummy_response)
            yield dummy_response.encode("utf-8")
            yield f"[CONVERSATION_ID={conversation_id}]".encode("utf-8")

        except Exception as e:
            self.logger.error(f"Yanıt oluşturma hatası: {str(e)}")
            save_to_db(user_id, user_message, f"Hata: {str(e)}")
            yield f"Bir hata oluştu: {str(e)}\n".encode("utf-8")

    # -------------------------------------------------------------
    # 6) Görseli side-by-side basan fonksiyon
    # -------------------------------------------------------------
    def _render_side_by_side_images(self, images, context="model"):
        if not images:
            yield "Bu kriterlere ait görsel bulunamadı.\n".encode("utf-8")
            return

        # Orijinal koddaki HTML taktiği
        # "Monte Carlo Standart" ve "Premium Opsiyonel" vs. ayırma
        mc_std = [img for img in images if "monte" in img.lower() and "carlo" in img.lower() and "standart" in img.lower()]
        pm_ops = [img for img in images if "premium" in img.lower() and "opsiyonel" in img.lower()]
        others = [img for img in images if img not in mc_std and img not in pm_ops]

        yield """
<div style="display: flex; justify-content: space-between; gap: 60px;">
  <div style="flex:1;">
""".encode("utf-8")

        if mc_std:
            left_title = mc_std[0].replace("_", " ")
            yield f"<h3>{left_title}</h3>".encode("utf-8")

            for img_file in mc_std:
                img_url = f"/static/images/{img_file}"
                base_name = img_file.replace("_", " ")
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
            right_title = pm_ops[0].replace("_", " ")
            yield f"<h3>{right_title}</h3>".encode("utf-8")

            for img_file in pm_ops:
                img_url = f"/static/images/{img_file}"
                base_name = img_file.replace("_", " ")
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
  </div>
</div>
""".encode("utf-8")

        if others:
            yield "<hr><b>Diğer Görseller:</b><br>".encode("utf-8")
            yield '<div style="display: flex; flex-wrap: wrap; gap: 20px;">'.encode("utf-8")
            for img_file in others:
                img_url = f"/static/images/{img_file}"
                base_name = img_file.replace("_", " ")
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

    # -------------------------------------------------------------
    # 7) Opsiyonel tabloyu döndüren fonksiyon
    # -------------------------------------------------------------
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
        else:
            yield f"'{model_name}' modeli için opsiyonel tablo bulunamadı.\n".encode("utf-8")

        if table_yielded:
            # Diğer donanım linklerini ekleyelim (özel HTML)
            if model_name == "fabia":
                all_trims = ["premium", "monte carlo"]
            elif model_name == "scala":
                all_trims = ["elite", "premium", "monte carlo"]
            elif model_name == "kamiq":
                all_trims = ["elite", "premium", "monte carlo"]
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

    # -------------------------------------------------------------
    # 8) Asistan ID seçme fonksiyonu
    # -------------------------------------------------------------
    def _determine_assistant_id(self, user_id, message):
        old_assistant_id = self.user_states.get(user_id, {}).get("assistant_id")
        msg_lower = message.lower()
        new_assistant_id = None

        # Asistan konfiginde tanımlı kelimelere göre
        for asst_id, keywords in self.ASSISTANT_CONFIG.items():
            if any(k.lower() in msg_lower for k in keywords):
                new_assistant_id = asst_id
                break

        if user_id not in self.user_states:
            self.user_states[user_id] = {}
            self.user_states[user_id]["threads"] = {}

        if new_assistant_id:
            assistant_id = new_assistant_id
        else:
            assistant_id = old_assistant_id

        # Eğer hâlâ yoksa "en az meşgul asistan" mantığı
        if not assistant_id:
            assistant_id = self._pick_least_busy_assistant()
            if assistant_id:
                self.logger.info(f"Rastgele en az meşgul asistan atandı: {assistant_id}")
            else:
                return None

        self.user_states[user_id]["assistant_id"] = assistant_id
        return assistant_id

    # -------------------------------------------------------------
    # 9) "En az meşgul asistan" seçen fonksiyon
    # -------------------------------------------------------------
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

    # -------------------------------------------------------------
    # 10) Fuzzy cache arama ve ekleme
    # -------------------------------------------------------------
    def _find_fuzzy_cached_answer(self, user_id, new_question, assistant_id, threshold=0.8):
        # Sadece tek asistan ID’de bak
        if not assistant_id:
            return None
        if user_id not in self.fuzzy_cache:
            return None
        if assistant_id not in self.fuzzy_cache[user_id]:
            return None

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
            return best_answer

        return None

    def _store_in_fuzzy_cache(self, user_id, question, answer_bytes, assistant_id):
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

    # -------------------------------------------------------------
    # 11) Kullanıcı mesajından "fabia", "scala", "kamiq" yakalama
    # -------------------------------------------------------------
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

    # -------------------------------------------------------------
    # 12) Yazım hatalarını düzeltme
    # -------------------------------------------------------------
    def _correct_typos(self, user_message):
        known_words = ["premium", "elite", "monte", "carlo"]
        splitted = user_message.split()
        new_tokens = []
        for token in splitted:
            best = self.utils.fuzzy_find(token, known_words, threshold=0.7)
            new_tokens.append(best if best else token)

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
