import os
import sys
from flask import Flask
from flask_cors import CORS
from modules.chatbot import ChatbotAPI
from modules.utils import Utils

def create_app():
    app = Flask(__name__)
    CORS(app)

    logger = Utils.setup_logger()

    # ChatbotAPI: Çok parçalı çıktı, veritabanına kayıt, tablo-parçalama vb.
    chatbot = ChatbotAPI(
        logger=logger,
        static_folder="static",
        template_folder="templates"
    )

    # chatbot.app => asıl Flask instance
    return chatbot.app

if __name__ == "__main__":
    my_app = create_app()
    my_app.run(debug=True)
