import unittest
from unittest.mock import MagicMock
from modules.chatbot import ChatbotAPI

class TestChatbotAPI(unittest.TestCase):
    def setUp(self):
        logger = MagicMock()
        self.chatbot = ChatbotAPI(logger=logger, static_folder="static", template_folder="templates")

    def test_select_assistant(self):
        user_message = "Scala görsel"
        user_id = "test_user"
        gen = self.chatbot._generate_response(user_message, user_id)
        list(gen)  # generator'ı tüket

        self.assertEqual(
            self.chatbot.user_states[user_id]["assistant_id"],
            "asst_njSG1NVgg4axJFmvVYAIXrpM"
        )

    def test_image_request(self):
        user_message = "Bir fotoğraf gösterir misin?"
        user_id = "test_user2"
        gen = self.chatbot._generate_response(user_message, user_id)
        output = "".join([chunk.decode("utf-8") for chunk in gen])
        # Beklenen: "Henüz bir asistan seçilmediği için görsel gösteremiyorum."
        self.assertIn("Henüz bir asistan seçilmediği için görsel gösteremiyorum.", output)