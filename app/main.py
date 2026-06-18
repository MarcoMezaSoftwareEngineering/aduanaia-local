"""Entrypoint FastAPI."""
from __future__ import annotations

from fastapi import FastAPI

from app.api import documents, query
from app.utils.logging import setup_logging


setup_logging()

app = FastAPI(
    title="AduanaIA Local",
    description=(
        "Asistente local para análisis preliminar aduanero. "
        "RAG + agentes LangGraph sobre Qwen3 8B en GPU. "
        "Las respuestas son orientativas y requieren revisión humana."
    ),
    version="0.2.0",
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(documents.router)
app.include_router(query.router)
