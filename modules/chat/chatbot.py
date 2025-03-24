# modules/chatbot.py

import os
import secrets
import logging
import openai
from flask import Flask, render_template, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv

from modules.db import create_tables
from modules.config import Config
from modules.utils import Utils
from modules.managers.image_manager import ImageManager
from modules.managers.markdown_utils import MarkdownProcessor

# BotService'i import
from modules.chat.bot_service import BotService

load_dotenv()

class ChatbotAPI:
    def __init__(self, logger=None, static_folder='static', template_folder='templates'):
        # Flask app
        self.app = Flask(
            __name__,
            static_folder=os.path.join(os.getcwd(), static_folder),
            template_folder=os.path.join(os.getcwd(), template_folder)
        )
        CORS(self.app)
        self.app.secret_key = secrets.token_hex(16)

        # Logger
        self.logger = logger if logger else self._setup_logger()

        # DB tablo oluşturma
        create_tables()

        # OpenAI
        openai.api_key = os.getenv("OPENAI_API_KEY")

        # Yardımcı sınıflar
        self.config = Config()
        self.utils = Utils()
        self.image_manager = ImageManager(images_folder=os.path.join(static_folder, "images"))
        self.image_manager.load_images()
        self.markdown_processor = MarkdownProcessor()

        # BotService örneği
        self.bot_service = BotService(
            logger=self.logger,
            config=self.config,
            utils=self.utils,
            image_manager=self.image_manager,
            markdown_processor=self.markdown_processor,
            openai_client=openai
        )

        # Route tanımları
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
        # Anasayfa
        @self.app.route("/", methods=["GET"])
        def home():
            session.pop('last_activity', None)
            return render_template("index.html")

        # /ask -> BotService handle_ask
        @self.app.route("/ask", methods=["POST"])
        def ask():
            # BotService’den gelen generator'ı stream olarak döndürüyoruz
            return self.app.response_class(
                self.bot_service.handle_ask(),
                mimetype="text/plain"
            )

        # /like -> BotService handle_like
        @self.app.route("/like", methods=["POST"])
        def like_endpoint():
            return self.bot_service.handle_like()

        @self.app.route("/check_session", methods=["GET"])
        def check_session():
            if 'last_activity' in session:
                pass
            return jsonify({"active": True})

    def run(self, debug=True):
        self.app.run(debug=debug)

    def shutdown(self):
        # Uygulama kapatılırken bot_service'i de durdur
        self.bot_service.shutdown()
        self.logger.info("ChatbotAPI shutdown complete.")
