from fastapi import FastAPI, Query
from rag_router import answer

app = FastAPI()

@app.get("/ask")
def ask(q: str = Query(..., min_length=2), render: str = Query("text", pattern="^(text|table|image)$")):
    # Her zaman SQL RAG'e gider
    out = answer(q, render=render)
    return {"ok": True, "render": render, "answer": out}
