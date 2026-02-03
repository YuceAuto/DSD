# modules/openai_responses_runner.py
import os
import time

class ResponsesRunner:
    def __init__(self, client, logger=None):
        self.client = client
        self.logger = logger

    def _log(self, msg: str):
        try:
            if self.logger:
                self.logger.info(msg)
        except Exception:
            pass

    def _used_file_search(self, resp) -> bool:
        """
        SDK sürümlerine toleranslı: response içinde file_search tool call oldu mu?
        """
        try:
            out = getattr(resp, "output", None) or []
            for item in out:
                # bazı SDK'larda tool call objesi farklı alanlarda duruyor
                itype = getattr(item, "type", "") or ""
                if "tool" in itype:
                    name = getattr(item, "name", None) or getattr(item, "tool_name", None) or ""
                    if "file_search" in str(name):
                        return True
                # bazı SDK'larda nested olabilir
                tool = getattr(item, "tool", None)
                if tool and "file_search" in str(tool):
                    return True
        except Exception:
            pass
        return False

    def ask(
        self,
        *,
        user_states: dict,
        user_id: str,
        assistant_id: str | None,
        content: str,
        timeout: float = 60.0,
        instructions_override: str | None = None,
        tool_resources_override: dict | None = None,
        ephemeral: bool = False,
    ) -> str:
        model = os.getenv("RESP_MODEL", os.getenv("GEN_MODEL", "gpt-4.1"))
        use_fs = os.getenv("USE_OPENAI_FILE_SEARCH", "0") == "1"
        file_only = os.getenv("FILE_ONLY_MODE", "0") == "1"

        # Vector store id: override > env
        vs_id = None
        if tool_resources_override:
            vs_id = tool_resources_override.get("vector_store_id")
            if not vs_id:
                lst = tool_resources_override.get("vector_store_ids") or []
                vs_id = lst[0] if lst else None
        if not vs_id:
            vs_id = (os.getenv("VECTOR_STORE_ID", "") or "").strip()

        # ✅ file_only modunda VS yoksa: model çağırma, direkt dön
        if file_only and (not use_fs or not vs_id):
            return "Bu soruyu cevaplayabilmem için bilgi tabanım (dosyalar) bağlı değil."

        tools = []
        if use_fs and vs_id:
            tools.append({"type": "file_search", "vector_store_ids": [vs_id]})

        # ✅ Sıkı talimat: sadece dosyalar
        strict = (
            "KURALLAR (ZORUNLU):\n"
            "- SADECE file_search sonuçlarındaki bilgilere dayan.\n"
            "- file_search sonuçlarında yoksa: 'Bu bilgi bende yok.' yaz.\n"
            "- Kesinlikle tahmin/uydurma yapma.\n"
            "- Web/Internet/harici kaynak KULLANMA.\n"
            "- Kaynak/citation/dosya adı yazma.\n"
        )
        final_instructions = (instructions_override or "").strip()
        final_instructions = (strict + "\n" + final_instructions).strip()

        st = user_states.setdefault(user_id, {}) if isinstance(user_states, dict) else {}
        previous_response_id = None if ephemeral else (st.get("last_response_id") or None)

        t0 = time.time()
        try:
            resp = self.client.responses.create(
                model=model,
                input=content,
                instructions=final_instructions,
                tools=(tools if tools else None),
                previous_response_id=previous_response_id,
            )
        except TypeError:
            resp = self.client.responses.create(
                model=model,
                input=content,
                instructions=final_instructions,
                tools=(tools if tools else None),
            )

        out = (getattr(resp, "output_text", "") or "").strip()

        # ✅ file_only modunda file_search kullanılmadıysa: cevabı KES
        if file_only and use_fs and vs_id:
            if not self._used_file_search(resp):
                return "Bu bilgi bende yok."

        rid = getattr(resp, "id", None)
        if rid and not ephemeral and isinstance(st, dict):
            st["last_response_id"] = rid

        self._log(f"[RESPONSES] model={model} fs={'on' if tools else 'off'} took={time.time()-t0:.2f}s out_len={len(out)}")
        return out or ("Bu bilgi bende yok." if file_only else "")
