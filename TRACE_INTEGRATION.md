
# Debug Trace Entegrasyonu (adım adım sorgu & cevap akışı)

Bu paket 3 şeyi otomatik yakalar:

1) **SQL** (pyodbc) → `cursor.execute/executemany`, süre, params (kısaltılmış), rowcount  
2) **Neo4j** → `driver.session().run(...)` + LangChain `Neo4jGraph.query(...)` çağrıları  
3) **OpenAI** → `embeddings.create` + `chat.completions.create` çağrıları (model, input uzunluğu, usage/preview)

Ayrıca siz isterseniz route/intent gibi adımları da manuel olarak tek satırla ekleyebilirsiniz.

---

## 1) Dosyayı projeye ekle

`modules/trace_debug.py` olarak kaydedin.

---

## 2) ChatbotAPI._ask içinde request trace başlat

En başa import ekleyin:

```python
from modules.trace_debug import trace_request, maybe_enable_trace_from_payload, tracer, trace_footer_bytes
```

`_ask()` içinde JSON parse ettikten hemen sonra:

```python
enabled = maybe_enable_trace_from_payload(request)
with trace_request(user_id=user_id, message=user_message, enabled=enabled):
    tracer().step("parsed_input", username=username)
    # ... mevcut akış aynen ...
```

Route kararlarını birer satırla raporlamak isterseniz:

```python
tracer().route("CS", answer_type=answer_type, ratio=r01)
tracer().route("PRICE", intent=True)
tracer().route("EQUIP", intent=True, model=model)
```

---

## 3) Streaming sonunda trace’i kullanıcıya bas

Sizde iki farklı yerde cevap finalize ediliyor:

### A) `_wrap_stream_with_feedback` içinde (en doğrusu)
`finally:` bloğunda `yield self._feedback_marker(conv_id)` satırından **önce** ekleyin:

```python
# Debug trace'i en sonda bas (isteğe bağlı)
try:
    yield trace_footer_bytes()
except Exception:
    pass
```

### B) `_respond_one_shot_with_feedback` içinde
`gen()` generator’ının en sonuna:

```python
yield trace_footer_bytes()
```

> Not: Trace HTML’i `<details>` içinde collapsible olarak gelir. İsterseniz JS ile
> özel bir panelde de gösterebilirsiniz.

---

## 4) SQL connection’ı trace’le

ChatbotAPI._sql_conn fonksiyonunda:

```python
from modules.trace_debug import traced_sql_conn
conn = pyodbc.connect(cs)
return traced_sql_conn(conn)
```

---

## 5) Neo4jSkodaGraphRAG içinde driver/graph wrapper

`Neo4jSkodaGraphRAG.__init__` sonunda (driver/graph oluşturduktan hemen sonra):

```python
from modules.trace_debug import traced_neo4j_driver, traced_neo4jgraph
self.driver = traced_neo4j_driver(self.driver)
self.graph  = traced_neo4jgraph(self.graph)
```

---

## 6) OpenAI client wrapper

ChatbotAPI.__init__ içinde `self.client = OpenAI(...)` satırından hemen sonra:

```python
from modules.trace_debug import traced_openai_client
self.client = traced_openai_client(self.client)
```

---

## Trace’i nasıl açarım?

- Query string: `POST /ask?debug=1`
- veya JSON payload: `{ "question": "...", "user_id": "...", "debug_trace": true }`
- veya env: `TRACE_MODE=1`

---

## Güvenlik / performans

- Varsayılan kapalıdır.
- Event sayısı `TRACE_MAX_EVENTS` (varsayılan 250) ile sınırlı.
- Parametreler ve SQL metinleri kısaltılır (PII sızmasın diye).
