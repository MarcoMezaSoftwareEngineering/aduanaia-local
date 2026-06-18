"""Pipeline RAG: retrieve → format → generate → log.

En Fase 2 es un solo paso; el StateGraph de [graph.py] envuelve esto en un
único nodo para dejar lista la estructura del Fase 4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.config import settings
from app.core import embeddings, llm, query_expansion, vectorstore
from app.db import models
from app.db.session import session_scope
from app.utils.logging import get_logger


log = get_logger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


@dataclass(slots=True)
class SourceRef:
    index: int                     # 1-based, lo que la cita [doc:N] referencia
    chunk_id: str
    document_id: str
    document_filename: str | None
    page_number: int | None
    score: float
    text: str


@dataclass(slots=True)
class RagResponse:
    query_id: UUID
    question: str
    answer: str
    sources: list[SourceRef] = field(default_factory=list)


def _build_prompt(question: str, sources: list[SourceRef]) -> str:
    if not sources:
        return (
            f"Pregunta del usuario:\n{question}\n\n"
            "FUENTES RECUPERADAS: (ninguna)\n\n"
            "Indica explícitamente que no encuentras información suficiente."
        )
    blocks = []
    for s in sources:
        page = f"p.{s.page_number}" if s.page_number else "p.s/n"
        header = f"[doc:{s.index}] {s.document_filename or s.document_id} — {page}"
        blocks.append(f"{header}\n{s.text}")
    sources_block = "\n\n---\n\n".join(blocks)
    return (
        f"Pregunta del usuario:\n{question}\n\n"
        "FUENTES RECUPERADAS:\n"
        f"{sources_block}\n\n"
        "Responde siguiendo las REGLAS DE CITACIÓN del sistema. "
        "Cierra con una advertencia de revisión humana obligatoria."
    )


def _resolve_document_filenames(doc_ids: list[str]) -> dict[str, str]:
    if not doc_ids:
        return {}
    out: dict[str, str] = {}
    with session_scope() as s:
        rows = s.query(models.Document.id, models.Document.filename).filter(
            models.Document.id.in_(doc_ids)
        ).all()
        for row_id, name in rows:
            out[str(row_id)] = name
    return out


def retrieve(question: str) -> list[SourceRef]:
    """Embebe la pregunta, busca top_k en Milvus, filtra por score, devuelve top_k_final.

    La pregunta se expande con [query_expansion.expand_query] antes del embedding para
    mejorar el recall cuando contiene códigos legales (ej. 'N° 184-2020/SUNAT').
    """
    expanded = query_expansion.expand_query(question)
    if expanded != question:
        log.info("Query expandida: %r -> %r", question[:80], expanded[:200])
    vec = embeddings.embed_query(expanded)
    raw_hits = vectorstore.search(vec.tolist(), top_k=settings.rag_top_k)
    filtered = [h for h in raw_hits if h.score >= settings.rag_min_score]
    filtered = filtered[: settings.rag_top_k_final]

    doc_ids = list({h.document_id for h in filtered if h.document_id})
    filenames = _resolve_document_filenames(doc_ids)

    sources: list[SourceRef] = []
    for i, h in enumerate(filtered, start=1):
        sources.append(
            SourceRef(
                index=i,
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                document_filename=filenames.get(h.document_id),
                page_number=h.page_number,
                score=h.score,
                text=h.text,
            )
        )
    log.info(
        "Retrieve: %d hits brutos -> %d tras score>=%.2f -> top_k_final=%d",
        len(raw_hits), len([h for h in raw_hits if h.score >= settings.rag_min_score]),
        settings.rag_min_score, len(sources),
    )
    return sources


def _persist(question: str, answer: str, sources: list[SourceRef]) -> UUID:
    query_id = uuid4()
    with session_scope() as s:
        q = models.Query(
            id=query_id,
            user_query=question,
            response=answer,
            model_used=settings.llm_model,
        )
        s.add(q)
        for src in sources:
            s.add(
                models.RetrievedSource(
                    query_id=query_id,
                    document_id=UUID(src.document_id) if src.document_id else None,
                    chunk_id=UUID(src.chunk_id) if _is_uuid(src.chunk_id) else None,
                    score=src.score,
                    content=src.text,
                    page_number=src.page_number,
                )
            )
    return query_id


def _is_uuid(value: Any) -> bool:
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


def answer(question: str) -> RagResponse:
    """Pipeline RAG end-to-end. Punto de entrada principal."""
    sources = retrieve(question)
    prompt = _build_prompt(question, sources)
    text = llm.ask(prompt, system=_SYSTEM_PROMPT)
    query_id = _persist(question, text, sources)
    return RagResponse(query_id=query_id, question=question, answer=text, sources=sources)
