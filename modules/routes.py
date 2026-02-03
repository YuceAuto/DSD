from flask import jsonify, request, render_template, Response, stream_with_context
from modules.chat.chatbot import ChatbotAPI

from modules.trace_debug import (
    trace_request,
    maybe_enable_trace_from_payload,
    tracer,
    trace_footer_html,
)

class Routes:
    @staticmethod
    def define_routes(app, logger):

        @app.route("/", methods=["GET"])
        def home():
            return render_template("index.html")

        @app.route("/ask", methods=["POST"])
        def ask():
            data = request.get_json(silent=True) or {}
            if not isinstance(data, dict):
                return jsonify({"error": "Invalid JSON format."}), 400

            user_message = (data.get("question") or "").strip()
            user_id = str(data.get("user_id") or "guest").strip()
            username = str(data.get("username") or data.get("nam_surnam") or user_id).strip()

            enabled = maybe_enable_trace_from_payload(request)
            # Q: en başta görünsün (terminal + log)
            print(f"[Q] user_id={user_id} | {user_message}", flush=True)
            logger.info(f"[Q] user_id={user_id} | {user_message}")

            # trace içine de yaz
            tracer().step("QUESTION", user_id=user_id, q=user_message[:300])

            # 🔻 ÖNEMLİ: context manager'ı elle kontrol edeceğiz
            cm = trace_request(user_id=user_id, message=user_message, enabled=enabled)
            cm.__enter__()
            tracer().route("HTTP", endpoint="/ask")

            try:
                bot = ChatbotAPI(logger=logger)
                out = bot._ask(username=user_id)  # senin mevcut çağrın

                # --- out Flask Response ise ---
                if hasattr(out, "response") and hasattr(out, "mimetype"):

                    # ✅ STREAM ise: trace'i stream bittikten sonra kapat
                    if getattr(out, "is_streamed", False):
                        def gen():
                            try:
                                for chunk in out.response:
                                    yield chunk
                                # stream bittiğinde A preview
                                preview = "STREAMED_RESPONSE"  # istersen burada buffer’layıp 500 char toplayabiliriz
                                print(f"[A] user_id={user_id} | {preview}", flush=True)
                                logger.info(f"[A] user_id={user_id} | {preview}")
                                tracer().step("ANSWER_PREVIEW", chars=-1, preview=preview)

                            finally:
                                extra = trace_footer_html()
                                if extra:
                                    yield extra.encode("utf-8")
                                # trace'i EN SON kapat
                                cm.__exit__(None, None, None)

                        resp = Response(
                            stream_with_context(gen()),
                            status=getattr(out, "status_code", 200),
                            mimetype=getattr(out, "mimetype", "text/html; charset=utf-8"),
                        )
                        for k, v in out.headers.items():
                            if k.lower() == "content-length":
                                continue
                            resp.headers[k] = v
                        return resp

                    # ✅ Stream değilse: body al, trace ekle, sonra kapat
                    body = out.get_data(as_text=True)
                    if enabled:
                        # Sadece asıl cevabı al (feedback/trace div'lerinden önce)
                        answer_only = (body.split("<div", 1)[0]).strip()
                        answer_only = answer_only.replace("<br>", "\n").replace("&bull;", "•")
                        if len(answer_only) > 600:
                            answer_only = answer_only[:600] + "…"
                        print(f"[A] user_id={user_id} | {answer_only}\n")
                    extra = trace_footer_html()
                    if extra:
                        body += extra
                    cm.__exit__(None, None, None)
                    preview = (body or "").replace("\n", " ")[:500]
                    print(f"[A] user_id={user_id} | {preview}", flush=True)
                    logger.info(f"[A] user_id={user_id} | {preview}")
                    tracer().step("ANSWER_PREVIEW", chars=len(body or ""), preview=preview)

                    return Response(body, status=out.status_code, mimetype=out.mimetype)

                # --- out string/bytes ise ---
                body = out.decode("utf-8", errors="ignore") if isinstance(out, (bytes, bytearray)) else str(out)
                if enabled:
                    # Sadece asıl cevabı al (feedback/trace div'lerinden önce)
                    answer_only = (body.split("<div", 1)[0]).strip()
                    answer_only = answer_only.replace("<br>", "\n").replace("&bull;", "•")
                    if len(answer_only) > 600:
                        answer_only = answer_only[:600] + "…"
                    print(f"[A] user_id={user_id} | {answer_only}\n")
                extra = trace_footer_html()
                if extra:
                    body += extra
                cm.__exit__(None, None, None)
                return Response(body, mimetype="text/html; charset=utf-8")

            except Exception as e:
                logger.error(f"Error in /ask: {str(e)}")
                # hata varsa da trace'i kapat
                try:
                    cm.__exit__(type(e), e, e.__traceback__)
                except Exception:
                    pass
                return jsonify({"error": "An error occurred."}), 500
