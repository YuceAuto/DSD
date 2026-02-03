import os
from modules.chat.chatbot import ChatbotAPI  # ikinci kodunuzun ana dosya/modül yolu

if __name__ == "__main__":
    api = ChatbotAPI()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5002"))
    api.run(host=host, port=port, debug=True)
