"""Endpoint /query — chat normativo (Fase 2)."""
from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core import rag


router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)


class SourcePayload(BaseModel):
    index: int
    chunk_id: str
    document_id: str
    document_filename: str | None
    page_number: int | None
    score: float
    text: str


class QueryResponse(BaseModel):
    query_id: UUID
    question: str
    answer: str
    sources: list[SourcePayload]


@router.post("", response_model=QueryResponse)
def post_query(body: QueryRequest) -> QueryResponse:
    response = rag.answer(body.question)
    return QueryResponse(
        query_id=response.query_id,
        question=response.question,
        answer=response.answer,
        sources=[SourcePayload(**asdict(s)) for s in response.sources],
    )
