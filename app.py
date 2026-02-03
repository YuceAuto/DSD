import os
import sys
import json
import re

from flask import Flask, request, g
from flask_cors import CORS

from modules.chat.chatbot import ChatbotAPI
from modules.utils import Utils

# (Opsiyonel) KB parçalama örneği - kullanmıyorsan kaldırabilirsin
from modules.kb_repo import MSSQLKb
from modules.model_detect import detect_model

KB = MSSQLKb()


def get_kb_context(user_text: str) -> str:
    model_hint = detect_model(user_text)  # None olabilir
    hits = KB.search_chunks(user_text, top_k=6, model_hint=model_hint)
    return "\n\n".join(h.get("snippet", "") for h in hits)


# (Opsiyonel) Mevcut LLM fonksiyonuna kb_context ekleme örneği
def answer(user_text: str):
    kb_context = get_kb_context(user_text)
    # Burada kendi LLM fonksiyonuna kb_context'i parametre geç
    # return llm_answer(user_text, kb_context)
    raise NotImplementedError("answer() örnektir; kendi llm_answer fonksiyonuna bağlayın.")


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = " ".join(s.split())
    return s


def _extract_payload_question(data: dict) -> str:
    # Senin sistemde bazen question, bazen message/text gelebiliyor diye
    return (data.get("question") or data.get("message") or data.get("text") or "").strip()


def _tee_stream_for_logging(resp, *, app, uid: str, path: str, max_chars: int = 700):
    """
    Stream response'u bozmadan geçirir, ilk max_chars karakteri biriktirip
    stream bittiğinde [A] loglar.
    """
    it = resp.response
    close_fn = getattr(it, "close", None)

    def gen():
        buf = []
        total = 0
        try:
            for chunk in it:
                # chunk bytes olabilir
                try:
                    s = chunk.decode("utf-8", "ignore") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
                except Exception:
                    s = ""

                if total < max_chars and s:
                    take = s[: (max_chars - total)]
                    buf.append(take)
                    total += len(take)

                yield chunk
        finally:
            # iterator close destekliyorsa kapat
            try:
                if close_fn:
                    close_fn()
            except Exception:
                pass

            # stream bitti -> preview logla
            preview = _strip_html("".join(buf))[:400]
            msg = f"[A] path={path} user_id={uid} status={resp.status_code} | {preview}"
            # print(msg, flush=True)
            app.logger.info(msg)

    # response iterable'ını wrapper ile değiştir
    resp.response = gen()

    # bazı ortamlarda direct_passthrough True olursa wrapper çalışmayabiliyor
    try:
        resp.direct_passthrough = False
    except Exception:
        pass

    return resp

import os, logging
from logging.handlers import RotatingFileHandler

def create_app():
    logger = Utils.setup_logger()
     
    # ChatbotAPI kendi Flask app'ini oluşturuyor (self.app)
    chatbot = ChatbotAPI(
        logger=logger,
        static_folder="static",
        template_folder="templates"
    )

    app = chatbot.app  # ✅ asıl çalışan Flask instance bu

    # CORS'u asıl app'e bağla
    CORS(app)

    # --------------------------
    # 1) Güvenlik header'ları
    # --------------------------
    @app.after_request
    def add_security_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        # Alternatif CSP:
        # response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    # --------------------------
    # 2) /ask* için terminal/log Q/A
    # --------------------------
    @app.before_request
    def _log_question_any_ask():
        # CORS preflight gürültüsünü alma
        if request.method == "OPTIONS":
            return

        if request.path.startswith("/ask"):
            data = request.get_json(silent=True)

            # JSON gelmezse raw body'den dene
            if not isinstance(data, dict):
                raw = request.get_data(cache=True, as_text=True) or ""
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {}

            q = _extract_payload_question(data)
            uid = str(data.get("user_id") or data.get("username") or "guest").strip()

            # after_request’te kullanmak için sakla
            g._trace_uid = uid
            g._trace_q = q

            if q:
                msg = f"[Q] path={request.path} user_id={uid} | {q}"
                # print(msg, flush=True)
                app.logger.info(msg)

    @app.after_request
    def _log_answer_any_ask(resp):
        try:
            if request.method == "OPTIONS":
                return resp

            if request.path.startswith("/ask"):
                uid = getattr(g, "_trace_uid", "guest")

                # Stream response ise -> stream’i bozmadan tee yap, stream sonunda preview logla
                if getattr(resp, "is_streamed", False):
                    return _tee_stream_for_logging(resp, app=app, uid=uid, path=request.path)

                # Stream değilse body okunabilir
                body = resp.get_data(as_text=True) or ""
                preview = _strip_html(body)[:400]
                msg = f"[A] path={request.path} user_id={uid} status={resp.status_code} | {preview}"
                # print(msg, flush=True)
                app.logger.info(msg)

        except Exception as e:
            app.logger.exception(f"[TRACE] after_request failed: {e}")

        return resp

    return app


if __name__ == "__main__":
    my_app = create_app()

    crt_path = os.path.join("certs", "wildcard.skoda.com.tr.crt")
    key_path = os.path.join("certs", "wildcard.skoda.com.tr.key")

    my_app.run(
        debug=True,
        host="0.0.0.0",
        port=8000,
        ssl_context=(crt_path, key_path)
    )
