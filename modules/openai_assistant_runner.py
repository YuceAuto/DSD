# modules/openai_assistant_runner.py
import time

class AssistantRunner:
    """
    OpenAI Assistants (beta threads) için sağlam çağrı katmanı.
    - Thread yönetimi (ephemeral / kalıcı)
    - Polling + timeout
    - Assistant mesajından text parçalarını birleştirerek okuma
    - instructions / tool_resources override desteği
    """

    def __init__(self, client, logger=None):
        self.client = client
        self.logger = logger

    def _log(self, msg: str):
        if self.logger:
            try:
                self.logger.info(msg)
            except Exception:
                pass

    def _extract_assistant_text(self, msg) -> str:
        """
        msg.content içindeki text parçalarını birleştirir.
        OpenAI SDK sürümlerine göre content elemanlarının yapısı farklı olabilir,
        bu yüzden toleranslı ilerliyoruz.
        """
        parts = []
        content = getattr(msg, "content", None) or []
        for p in content:
            ptype = getattr(p, "type", None)

            # En yaygın: {"type":"text","text":{"value":"..."}}
            if ptype == "text":
                try:
                    parts.append(p.text.value)
                    continue
                except Exception:
                    pass

            # Bazı sürümlerde doğrudan string gibi gelebilir
            try:
                s = str(p)
                if s and s != "None":
                    parts.append(s)
            except Exception:
                pass

        return "\n".join([x for x in parts if x]).strip()

    def _get_or_create_thread_id(self, *, user_states: dict, user_id: str, assistant_id: str, ephemeral: bool) -> str:
        if ephemeral:
            t = self.client.beta.threads.create()
            return t.id

        st = user_states.setdefault(user_id, {})
        threads = st.setdefault("threads", {})
        thread_id = threads.get(assistant_id)

        if not thread_id:
            t = self.client.beta.threads.create()
            thread_id = t.id
            threads[assistant_id] = thread_id

        return thread_id

    def ask(
        self,
        *,
        user_states: dict,
        user_id: str,
        assistant_id: str,
        content: str,
        timeout: float = 60.0,
        instructions_override: str | None = None,
        tool_resources_override: dict | None = None,
        ephemeral: bool = False,
        poll_interval: float = 0.5,
    ) -> str:
        """
        content'i threade yazar, run başlatır, tamamlanınca son asistan metnini döndürür.
        """
        if not assistant_id:
            return ""

        thread_id = self._get_or_create_thread_id(
            user_states=user_states,
            user_id=user_id,
            assistant_id=assistant_id,
            ephemeral=ephemeral
        )

        # 1) kullanıcı mesajını ekle
        self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content
        )

        # 2) run başlat
        run_kwargs = {"thread_id": thread_id, "assistant_id": assistant_id}
        if instructions_override:
            run_kwargs["instructions"] = instructions_override
        if tool_resources_override:
            run_kwargs["tool_resources"] = tool_resources_override

        run = self.client.beta.threads.runs.create(**run_kwargs)

        # 3) poll
        start = time.time()
        while (time.time() - start) < timeout:
            run = self.client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

            status = getattr(run, "status", None)
            if status == "completed":
                break

            if status in ("failed", "cancelled", "expired"):
                # last_error yapısı SDK'ya göre değişebilir
                try:
                    le = getattr(run, "last_error", None) or {}
                    msg = le.get("message") if isinstance(le, dict) else str(le)
                except Exception:
                    msg = "Run failed."
                raise RuntimeError(msg or "Run failed.")

            if status == "requires_action":
                # Tool çağrısı gerektiren akış (function calling vs.)
                # Senin mimaride yoksa burada blokluyoruz.
                raise RuntimeError("Run requires_action: tool çağrısı gerekiyor (bu runner tool handling yapmıyor).")

            time.sleep(poll_interval)

        # timeout
        if getattr(run, "status", None) != "completed":
            return ""

        # 4) Son assistant mesajını al
        msgs = self.client.beta.threads.messages.list(
            thread_id=thread_id,
            order="desc",
            limit=10
        )

        for m in getattr(msgs, "data", []) or []:
            if getattr(m, "role", None) == "assistant":
                txt = self._extract_assistant_text(m)
                if txt:
                    return txt

        return ""
