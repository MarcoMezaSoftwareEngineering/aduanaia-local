"""Modelos SQLAlchemy según §16.1 del documento técnico."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str | None] = mapped_column(Text)        # ley / decreto / resolucion / catalogo / ...
    source: Mapped[str | None] = mapped_column(Text)               # SUNAT / VUCE / MEF / otro
    upload_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    hash: Mapped[str | None] = mapped_column(Text, unique=True)    # SHA-256 del archivo
    status: Mapped[str] = mapped_column(Text, default="pending")   # pending / indexed / failed
    text_content: Mapped[str | None] = mapped_column(Text)         # texto completo cacheado (opcional)
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    milvus_vector_id: Mapped[str | None] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="chunks")


class Query(Base):
    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    model_used: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(Text)           # se llena en Fase 3+
    confidence_level: Mapped[str | None] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text)

    retrieved_sources: Mapped[list["RetrievedSource"]] = relationship(
        back_populates="query",
        cascade="all, delete-orphan",
    )


class RetrievedSource(Base):
    __tablename__ = "retrieved_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="SET NULL"),
    )
    score: Mapped[float | None] = mapped_column(Float)
    content: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)

    query: Mapped[Query] = relationship(back_populates="retrieved_sources")


class CaseAnalysis(Base):
    """Stub para Fase 3 — análisis de expediente."""
    __tablename__ = "case_analysis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="SET NULL"),
    )
    merchandise_description: Mapped[str | None] = mapped_column(Text)
    tariff_code: Mapped[str | None] = mapped_column(Text)
    country_origin: Mapped[str | None] = mapped_column(Text)
    detected_entity: Mapped[str | None] = mapped_column(Text)
    document_gap: Mapped[bool | None] = mapped_column(Boolean)
    risk_level: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    human_review_status: Mapped[str | None] = mapped_column(Text)
