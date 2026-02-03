
"""
trace_debug.py
==============
Amaç:
- Kullanıcı bir cevap alırken sistemin adım adım hangi yollardan geçtiğini
  (route), hangi SQL/Cypher sorgularının çalıştığını, hangi RAG/embedding/LLM
  çağrılarının yapıldığını "tek bir request trace" içinde toplamak.
- Hem log'a yazmak hem de istenirse kullanıcıya HTML/JSON olarak göstermek.

Kullanım:
- ChatbotAPI._ask(...) içinde en başta:
    from modules.trace_debug import trace_request, tracer, maybe_enable_trace_from_payload
    enabled = maybe_enable_trace_from_payload(request)
    with trace_request(user_id=user_id, message=user_message, enabled=enabled):
        ... mevcut akış ...

- _sql_conn() dönüşünü trace'li yapmak:
    from modules.trace_debug import traced_sql_conn
    return traced_sql_conn(pyodbc.connect(cs))

- Neo4jSkodaGraphRAG.__init__ içinde driver/graph wrapper:
    from modules.trace_debug import traced_neo4j_driver, traced_neo4jgraph
    self.driver = traced_neo4j_driver(self.driver)
    self.graph  = traced_neo4jgraph(self.graph)

- OpenAI client wrapper:
    from modules.trace_debug import traced_openai_client
    self.client = traced_openai_client(self.client)

Not:
- TRACE varsayılan kapalı. Açmak için:
    1) Request payload: {"debug_trace": true}
    2) veya querystring: ?debug=1
    3) veya env: TRACE_MODE=1
"""

from __future__ import annotations

import contextvars
import dataclasses
import json
import os
import time
import traceback
import typing as t
import html as _html

# ------------------------------
# Core: Trace collector
# ------------------------------

_TRACE_VAR: contextvars.ContextVar["TraceCollector|None"] = contextvars.ContextVar("TRACE_COLLECTOR", default=None)

@dataclasses.dataclass
class TraceEvent:
    ts: float
    kind: str                  # e.g. "ROUTE", "SQL", "NEO4J", "OPENAI", "STEP", "ERROR"
    name: str                  # short label
    ms: float | None = None    # duration in ms (optional)
    data: dict[str, t.Any] = dataclasses.field(default_factory=dict)
import time
import json
from contextlib import contextmanager

# Eğer sende zaten span/tracer varsa bunları tekrar yazma.
# Aşağıdaki kod tracer() ve span() fonksiyonlarını kullanır varsayıyorum.

def _short_sql(sql: str, limit: int = 700) -> str:
    s = " ".join((sql or "").split())
    return (s[:limit] + "…") if len(s) > limit else s

def _mask_params(params):
    if params is None:
        return None
    try:
        # dict params
        if isinstance(params, dict):
            out = {}
            for k, v in params.items():
                out[k] = _mask_params(v)
            return out
        # tuple/list
        if isinstance(params, (list, tuple)):
            return [_mask_params(x) for x in params]
        # primitives
        if isinstance(params, (int, float, bool)) or params is None:
            return params
        # strings & other objects -> mask
        s = str(params)
        if len(s) <= 2:
            return "***"
        return "***"
    except Exception:
        return "***"

class _CursorProxy:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=None):
        q = _short_sql(sql)
        p = _mask_params(params)
        t0 = time.time()
        try:
            with span("SQL", "execute", sql=q, params=p):
                if params is None:
                    r = self._cur.execute(sql)
                else:
                    r = self._cur.execute(sql, params)
            return r
        finally:
            dt = (time.time() - t0) * 1000
            try:
                tracer().step("SQL_EXEC_DONE", ms=round(dt, 2), rowcount=getattr(self._cur, "rowcount", None))
            except Exception:
                pass

    def executemany(self, sql, seq_of_params):
        q = _short_sql(sql)
        t0 = time.time()
        try:
            with span("SQL", "executemany", sql=q, batch=len(seq_of_params) if seq_of_params else 0):
                return self._cur.executemany(sql, seq_of_params)
        finally:
            dt = (time.time() - t0) * 1000
            try:
                tracer().step("SQL_MANY_DONE", ms=round(dt, 2))
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._cur, name)

class _ConnProxy:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *a, **k):
        return _CursorProxy(self._conn.cursor(*a, **k))

    def __getattr__(self, name):
        return getattr(self._conn, name)

def traced_sql_conn(conn):
    return _ConnProxy(conn)

class TraceCollector:
    """
    Request-scope event store.
    - thread-safe for typical flask usage via contextvars
    - supports HTML and JSON rendering
    """
    def __init__(self, *, enabled: bool, user_id: str | None = None, message: str | None = None):
        self.enabled = bool(enabled)
        self.user_id = user_id
        self.message = (message or "")
        self.started_at = time.time()
        self.events: list[TraceEvent] = []
        self._max_events = int(os.getenv("TRACE_MAX_EVENTS", "250"))
        self._max_field_len = int(os.getenv("TRACE_MAX_FIELD_LEN", "1200"))

    def _trim(self, v: t.Any) -> t.Any:
        try:
            s = str(v)
        except Exception:
            return v
        if len(s) > self._max_field_len:
            return s[: self._max_field_len] + "…(truncated)"
        return v

    def add(self, kind: str, name: str, *, ms: float | None = None, **data: t.Any) -> None:
        if not self.enabled:
            return
        if len(self.events) >= self._max_events:
            # once: record overflow and stop collecting more
            if len(self.events) == self._max_events:
                self.events.append(TraceEvent(time.time(), "TRACE", "overflow", data={"note": "max_events reached"}))
            return

        safe = {k: self._trim(v) for k, v in (data or {}).items()}
        self.events.append(TraceEvent(time.time(), kind, name, ms=ms, data=safe))

    def step(self, name: str, **data: t.Any) -> None:
        self.add("STEP", name, **data)

    def route(self, name: str, **data: t.Any) -> None:
        self.add("ROUTE", name, **data)

    def error(self, name: str, exc: BaseException | None = None, **data: t.Any) -> None:
        if exc is not None:
            data = dict(data or {})
            data["exc_type"] = type(exc).__name__
            data["exc"] = str(exc)
            data["traceback"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:]
        self.add("ERROR", name, **data)

    def to_dict(self) -> dict[str, t.Any]:
        return {
            "enabled": self.enabled,
            "user_id": self.user_id,
            "message": self.message[:500],
            "started_at": self.started_at,
            "elapsed_ms": round((time.time() - self.started_at) * 1000, 2),
            "events": [
                {
                    "ts": e.ts,
                    "kind": e.kind,
                    "name": e.name,
                    "ms": e.ms,
                    "data": e.data,
                }
                for e in self.events
            ],
        }
    def summary_dict(self) -> dict:
        evs = self.events or []

        def last_step(name: str) -> dict:
            for e in reversed(evs):
                if e.kind == "STEP" and e.name == name:
                    return e.data or {}
            return {}

        flags = last_step("ENV_FLAGS")
        route = last_step("ROUTE_DECISION")

        sql_exec = [e for e in evs if e.kind == "SQL" and e.name == "execute"]
        neo4j = [e for e in evs if e.kind == "NEO4J"]
        openai = [e for e in evs if e.kind in ("OPENAI", "LLM")]

        # Top 3 SQL "imza" (tablo ismi + operasyon)
        top_sql = []
        for e in sql_exec[:3]:
            sql = (e.data or {}).get("sql", "")
            top_sql.append(_sql_sig(str(sql)))

        return {
            "elapsed_ms": round((time.time() - self.started_at) * 1000, 2),
            "route": route,
            "flags": flags,
            "counts": {
                "events": len(evs),
                "sql_exec": len(sql_exec),
                "neo4j": len(neo4j),
                "openai": len(openai),
            },
            "sql_top3": top_sql,
        }

    def summary_text(self) -> str:
        s = self.summary_dict()
        c = s["counts"]
        flags = s.get("flags") or {}
        route = s.get("route") or {}

        lines = []
        lines.append(f"[TRACE] elapsed={s['elapsed_ms']}ms | events={c['events']}")
        if flags:
            lines.append(f"[FLAGS] NEO4J_ONLY={flags.get('NEO4J_ONLY')} KB_ONLY={flags.get('KB_ONLY')} HYBRID_RAG={flags.get('HYBRID_RAG')}")
        if route:
            lines.append(f"[ROUTE] {route.get('route')} ({route.get('reason','')})")
        lines.append(f"[CALLS] SQL={c['sql_exec']} | NEO4J={c['neo4j']} | OPENAI={c['openai']}")
        if s["sql_top3"]:
            lines.append("[SQL top3]")
            for i, x in enumerate(s["sql_top3"], 1):
                if x:
                    lines.append(f"  {i}) {x}")
        return "\n".join(lines)
    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_html(self) -> str:
        """
        Collapsible HTML (safe escaped) suitable to append to your chat response.
        """
        if not self.enabled:
            return ""

        d = self.to_dict()
        esc = _html.escape

        rows = []
        for i, e in enumerate(d["events"]):
            ms = "" if e.get("ms") is None else f'{e["ms"]:.1f} ms'
            data = e.get("data") or {}
            # small JSON
            try:
                js = json.dumps(data, ensure_ascii=False)
            except Exception:
                js = str(data)
            rows.append(
                "<tr>"
                f"<td style='white-space:nowrap'>{i}</td>"
                f"<td style='white-space:nowrap'>{esc(str(e.get('kind')))}</td>"
                f"<td style='white-space:nowrap'>{esc(str(e.get('name')))}</td>"
                f"<td style='white-space:nowrap'>{esc(ms)}</td>"
                f"<td><code style='white-space:pre-wrap'>{esc(js)}</code></td>"
                "</tr>"
            )
        summary = _html.escape(self.summary_text())
        summary_html = f"""
        <div style='margin-top:10px; border:1px solid #eee; padding:8px; font-size:12px'>
        <b>Trace Özeti</b>
        <pre style="margin:6px 0 0 0; white-space:pre-wrap">{summary}</pre>
        </div>
        """

        header = (
            f"<div style='margin-top:12px'>"
            f"<details class='trace-details'>"
            f"<summary style='cursor:pointer'><b>Debug Trace</b> "
            f"(events: {len(d['events'])}, elapsed: {d['elapsed_ms']} ms)</summary>"
            f"<div style='margin-top:10px; overflow:auto; max-height:360px; border:1px solid #eee; padding:8px'>"
            f"<table style='width:100%; border-collapse:collapse; font-size:12px'>"
            f"<thead><tr>"
            f"<th style='text-align:left; border-bottom:1px solid #ddd; padding:4px'>#</th>"
            f"<th style='text-align:left; border-bottom:1px solid #ddd; padding:4px'>kind</th>"
            f"<th style='text-align:left; border-bottom:1px solid #ddd; padding:4px'>name</th>"
            f"<th style='text-align:left; border-bottom:1px solid #ddd; padding:4px'>duration</th>"
            f"<th style='text-align:left; border-bottom:1px solid #ddd; padding:4px'>data</th>"
            f"</tr></thead><tbody>"
        )
        footer = "</tbody></table></div></details></div>"
        return header + "".join(rows) + footer


def get_trace() -> TraceCollector | None:
    return _TRACE_VAR.get()

def tracer() -> TraceCollector:
    tr = get_trace()
    if tr is None:
        # disabled default collector (no-op)
        tr = TraceCollector(enabled=False)
        _TRACE_VAR.set(tr)
    return tr

class Span:
    def __init__(self, kind: str, name: str, data: dict[str, t.Any] | None = None):
        self.kind = kind
        self.name = name
        self.data = data or {}
        self.t0 = None

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, exc_type, exc, tb):
        dt = (time.time() - (self.t0 or time.time())) * 1000
        tr = get_trace()
        if tr:
            if exc is None:
                tr.add(self.kind, self.name, ms=dt, **(self.data or {}))
            else:
                tr.error(self.name, exc=exc, **(self.data or {}))
        # do not suppress
        return False

def span(kind: str, name: str, **data: t.Any) -> Span:
    return Span(kind, name, data)

def trace_request(*, user_id: str | None, message: str | None, enabled: bool):
    """
    Context manager: installs TraceCollector for this request.
    """
    class _CM:
        def __enter__(self_cm):
            tr = TraceCollector(enabled=enabled, user_id=user_id, message=message)
            _TRACE_VAR.set(tr)
            # --- console: question at top ---
            if enabled:
                q = (message or "").strip().replace("\n", " ")
                if len(q) > 300:
                    q = q[:300] + "…"
                print(f"\n[Q] user_id={user_id} | {q}\n")

            tr.step("request_start", user_id=user_id)
            return tr

        def __exit__(self_cm, exc_type, exc, tb):
            tr = get_trace()
            if tr:
                if exc is not None:
                    tr.error("request_exception", exc=exc)
                tr.step("request_end")
                try:
                    if tr and tr.enabled and os.getenv("TRACE_PRINT", "1") == "1":
                        print(tr.summary_text(), flush=True)
                except Exception:
                    pass
            # keep collector in context; caller may render at end
            return False
    return _CM()

# ------------------------------
# Enablement helpers
# ------------------------------

def maybe_enable_trace_from_payload(request) -> bool:
    """
    Flask request -> bool.
    Enables trace if any of these:
      - env TRACE_MODE=1
      - querystring ?debug=1 or ?trace=1
      - JSON payload includes debug_trace=true
    """
    try:
        if os.getenv("TRACE_MODE", "0") == "1":
            return True
    except Exception:
        pass

    try:
        if hasattr(request, "args"):
            if str(request.args.get("debug", "")).strip() in ("1", "true", "True", "yes"):
                return True
            if str(request.args.get("trace", "")).strip() in ("1", "true", "True", "yes"):
                return True
    except Exception:
        pass

    try:
        data = request.get_json(silent=True) or {}
        if isinstance(data, dict) and bool(data.get("debug_trace")):
            return True
    except Exception:
        pass

    return False

# ------------------------------
# SQL (pyodbc) wrappers
# ------------------------------

class TracedCursor:
    def __init__(self, inner):
        self._c = inner

    def execute(self, sql, params=None):
        if params is None:
            params = ()
        with span("SQL", "execute", sql=_safe_sql(sql), params=_safe_params(params)):
            out = self._c.execute(sql, params) if params != () else self._c.execute(sql)
            # rowcount can be -1 pre-fetch; still useful
            tr = get_trace()
            if tr and tr.enabled:
                tr.add("SQL", "rowcount", rowcount=getattr(self._c, "rowcount", None))
            return out

    def executemany(self, sql, seq_of_params):
        # don't log huge params; just length
        with span("SQL", "executemany", sql=_safe_sql(sql), batch_len=_len_safe(seq_of_params)):
            return self._c.executemany(sql, seq_of_params)

    def fetchone(self):
        return self._c.fetchone()

    def fetchall(self):
        return self._c.fetchall()

    def fetchmany(self, size=None):
        return self._c.fetchmany(size) if size is not None else self._c.fetchmany()

    @property
    def description(self):
        return self._c.description

    @property
    def rowcount(self):
        return getattr(self._c, "rowcount", None)

    def close(self):
        return self._c.close()

    def __getattr__(self, name):
        return getattr(self._c, name)

class TracedConnection:
    def __init__(self, inner):
        self._conn = inner

    def cursor(self, *a, **k):
        return TracedCursor(self._conn.cursor(*a, **k))

    def commit(self):
        with span("SQL", "commit"):
            return self._conn.commit()

    def close(self):
        with span("SQL", "close"):
            return self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        try:
            self.close()
        except Exception:
            pass
        return False

    def __getattr__(self, name):
        return getattr(self._conn, name)

def traced_sql_conn(conn):
    """Wrap a pyodbc connection so all cursor.execute calls are traced."""
    tr = get_trace()
    if tr is None or not tr.enabled:
        return conn
    return TracedConnection(conn)

def _safe_sql(sql: t.Any) -> str:
    s = str(sql or "")
    s = " ".join(s.split())
    return s[:2000] + ("…(truncated)" if len(s) > 2000 else "")

def _safe_params(params: t.Any) -> t.Any:
    try:
        if isinstance(params, (list, tuple)):
            out = []
            for p in params[:30]:
                out.append(str(p)[:200])
            if len(params) > 30:
                out.append("…")
            return out
        return str(params)[:400]
    except Exception:
        return "<unprintable params>"

def _len_safe(x) -> int:
    try:
        return len(x)
    except Exception:
        return -1

# ------------------------------
# Neo4j wrappers (driver + langchain graph)
# ------------------------------

class TracedNeo4jResult:
    def __init__(self, inner):
        self._r = inner
    def data(self, *a, **k):
        return self._r.data(*a, **k)
    def single(self, *a, **k):
        return self._r.single(*a, **k)
    def consume(self, *a, **k):
        return self._r.consume(*a, **k)
    def __iter__(self):
        return iter(self._r)
    def __getattr__(self, name):
        return getattr(self._r, name)

class TracedNeo4jSession:
    def __init__(self, inner):
        self._s = inner

    def run(self, cypher, parameters=None, **kw):
        if parameters is None:
            parameters = {}
        with span("NEO4J", "run", cypher=_safe_sql(cypher), params=_safe_params_dict(parameters)):
            res = self._s.run(cypher, parameters, **kw) if parameters else self._s.run(cypher, **kw)
            return TracedNeo4jResult(res)

    def execute_write(self, *a, **k):
        with span("NEO4J", "execute_write"):
            return self._s.execute_write(*a, **k)

    def execute_read(self, *a, **k):
        with span("NEO4J", "execute_read"):
            return self._s.execute_read(*a, **k)

    def close(self):
        return self._s.close()

    def __enter__(self):
        self._s.__enter__()
        return self

    def __exit__(self, et, ev, tb):
        return self._s.__exit__(et, ev, tb)

    def __getattr__(self, name):
        return getattr(self._s, name)

class TracedNeo4jDriver:
    def __init__(self, inner):
        self._d = inner

    def session(self, *a, **k):
        s = self._d.session(*a, **k)
        tr = get_trace()
        if tr is None or not tr.enabled:
            return s
        return TracedNeo4jSession(s)

    def close(self):
        return self._d.close()

    def __getattr__(self, name):
        return getattr(self._d, name)

def traced_neo4j_driver(driver):
    tr = get_trace()
    if tr is None or not tr.enabled:
        return driver
    return TracedNeo4jDriver(driver)

def _safe_params_dict(d: dict) -> dict:
    out = {}
    for k, v in list((d or {}).items())[:30]:
        out[str(k)[:60]] = str(v)[:240]
    if d and len(d) > 30:
        out["…"] = f"{len(d)-30} more"
    return out

def traced_neo4jgraph(graph):
    """
    Wrap LangChain Neo4jGraph.query(...) calls.
    """
    tr = get_trace()
    if tr is None or not tr.enabled:
        return graph

    if hasattr(graph, "query"):
        orig = graph.query

        def _q(cypher, params=None):
            if params is None:
                params = {}
            with span("NEO4J", "graph.query", cypher=_safe_sql(cypher), params=_safe_params_dict(params)):
                return orig(cypher, params)

        graph.query = _q  # type: ignore[attr-defined]
    return graph

# ------------------------------
# OpenAI wrappers (SDK client)
# ------------------------------

class _TracedOpenAIProxy:
    """
    Minimal proxy around OpenAI python SDK client.
    Captures embeddings + chat.completions.create.
    """
    def __init__(self, inner):
        self._c = inner

    @property
    def embeddings(self):
        emb = getattr(self._c, "embeddings")
        return _TracedEmbeddingsProxy(emb)

    @property
    def chat(self):
        chat = getattr(self._c, "chat")
        return _TracedChatProxy(chat)

    @property
    def vector_stores(self):
        # pass through (optional)
        return getattr(self._c, "vector_stores", None)

    @property
    def beta(self):
        return getattr(self._c, "beta", None)

    def __getattr__(self, name):
        return getattr(self._c, name)

class _TracedEmbeddingsProxy:
    def __init__(self, inner):
        self._e = inner

    def create(self, *a, **k):
        model = k.get("model", "")
        inp = k.get("input", None)
        in_len = _approx_len(inp)
        with span("OPENAI", "embeddings.create", model=model, input_len=in_len):
            res = self._e.create(*a, **k)
            # usage field may exist
            try:
                usage = getattr(res, "usage", None) or {}
            except Exception:
                usage = {}
            tr = get_trace()
            if tr and tr.enabled:
                tr.add("OPENAI", "embeddings.result", model=model, usage=str(usage)[:400])
            return res

class _TracedChatProxy:
    def __init__(self, inner):
        self._chat = inner

    @property
    def completions(self):
        return _TracedCompletionsProxy(getattr(self._chat, "completions"))

class _TracedCompletionsProxy:
    def __init__(self, inner):
        self._inner = inner

    def create(self, *a, **k):
        model = k.get("model", "")
        messages = k.get("messages", [])
        msg_len = _approx_len(messages)
        max_tokens = k.get("max_tokens", None)
        temperature = k.get("temperature", None)
        with span("OPENAI", "chat.completions.create", model=model, messages_len=msg_len, max_tokens=max_tokens, temperature=temperature):
            res = self._inner.create(*a, **k)
            # try extract usage and short output
            usage = getattr(res, "usage", None)
            out_preview = ""
            try:
                out_preview = (res.choices[0].message.content or "")[:300]
            except Exception:
                pass
            tr = get_trace()
            if tr and tr.enabled:
                tr.add("OPENAI", "chat.result", model=model, usage=str(usage)[:400] if usage else None, preview=out_preview)
            return res

def traced_openai_client(client):
    tr = get_trace()
    if tr is None or not tr.enabled:
        return client
    return _TracedOpenAIProxy(client)

def _approx_len(x: t.Any) -> int:
    try:
        if x is None:
            return 0
        if isinstance(x, str):
            return len(x)
        if isinstance(x, (list, tuple)):
            return len(x)
        if isinstance(x, dict):
            return len(x)
        return len(str(x))
    except Exception:
        return -1

# ------------------------------
# Rendering helpers for streaming
# ------------------------------

def trace_footer_html() -> str:
    tr = get_trace()
    if not tr or not tr.enabled:
        return ""
    return tr.to_html()

def trace_footer_bytes() -> bytes:
    h = trace_footer_html()
    return h.encode("utf-8") if h else b""
