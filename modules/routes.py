from flask import jsonify, request, render_template
from modules.chatbot import ChatbotAPI
from modules.utils import Utils


class Routes:
    @staticmethod
    def define_routes(app, logger):
        """
        Define all routes for the Flask app.
        """
        @app.route("/", methods=["GET"])
        def home():
            return render_template("index.html")

        @app.route("/ask", methods=["POST"])
        def ask():
            try:
                data = request.get_json()
                if not data:
                    return jsonify({"error": "Invalid JSON format."}), 400
                # Add your processing logic here
                return jsonify({"message": "Question received."})
            except Exception as e:
                logger.error(f"Error in /ask: {str(e)}")
                return jsonify({"error": "An error occurred."}), 500

        @app.route("/feedback", methods=["POST"])
        def feedback():
            try:
                data = request.get_json()
                logger.info(f"Feedback received: {data}")
                return jsonify({"message": "Thank you for your feedback!"})
            except Exception as e:
                logger.error(f"Error in /feedback: {str(e)}")
                return jsonify({"error": "An error occurred."}), 500

