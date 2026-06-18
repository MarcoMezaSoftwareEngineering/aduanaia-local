"""Endpoints de administración documental."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core import ingestion, vectorstore
from app.db import models
from app.db.session import get_session


router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    document_type: str | None
    source: str | None
    upload_date: datetime
    status: str
    chunk_count: int


class IngestResultItem(BaseModel):
    path: str
    status: str
    document_id: str | None = None
    chunks: int | None = None
    reason: str | None = None


class IngestResponse(BaseModel):
    total: int
    indexed: int
    skipped: int
    failed: int
    items: list[IngestResultItem]


@router.get("", response_model=list[DocumentOut])
def list_documents(s: Session = Depends(get_session)) -> list[DocumentOut]:
    counts_subq = (
        s.query(models.Chunk.document_id, func.count(models.Chunk.id).label("n"))
        .group_by(models.Chunk.document_id)
        .subquery()
    )
    rows = (
        s.query(models.Document, counts_subq.c.n)
        .outerjoin(counts_subq, counts_subq.c.document_id == models.Document.id)
        .order_by(models.Document.upload_date.desc())
        .all()
    )
    return [
        DocumentOut(
            id=doc.id,
            filename=doc.filename,
            document_type=doc.document_type,
            source=doc.source,
            upload_date=doc.upload_date,
            status=doc.status,
            chunk_count=int(count or 0),
        )
        for doc, count in rows
    ]


@router.post("/upload", response_model=DocumentOut, status_code=201)
def upload_document(
    file: UploadFile = File(...),
    s: Session = Depends(get_session),
) -> DocumentOut:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF.")
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    dest = settings.upload_path / file.filename
    with dest.open("wb") as out:
        out.write(file.file.read())

    # Registrar como pending; el indexado se dispara con POST /documents/index.
    from app.utils.pdf import infer_document_type, infer_entity_from_path, sha256_of_file
    digest = sha256_of_file(dest)
    existing = s.query(models.Document).filter_by(hash=digest).one_or_none()
    if existing:
        return DocumentOut(
            id=existing.id,
            filename=existing.filename,
            document_type=existing.document_type,
            source=existing.source,
            upload_date=existing.upload_date,
            status=existing.status,
            chunk_count=len(existing.chunks),
        )
    doc = models.Document(
        filename=file.filename,
        document_type=infer_document_type(file.filename),
        source=infer_entity_from_path(dest),
        hash=digest,
        status="pending",
        meta={"path": str(dest)},
    )
    s.add(doc)
    s.commit()
    s.refresh(doc)
    return DocumentOut(
        id=doc.id,
        filename=doc.filename,
        document_type=doc.document_type,
        source=doc.source,
        upload_date=doc.upload_date,
        status=doc.status,
        chunk_count=0,
    )


@router.post("/index", response_model=IngestResponse)
def index_documents(
    background: BackgroundTasks,
    force: bool = False,
) -> IngestResponse:
    """Ejecuta el pipeline sobre todo el corpus (síncrono, puede tardar minutos)."""
    base_paths = [settings.docs_base_path, settings.upload_path]
    items: list[ingestion.ingest_pdf] = []
    raw: list[dict] = []
    for base in base_paths:
        path = Path(base)
        if path.exists():
            raw.extend(ingestion.ingest_directory(path, force=force))
    items_out = [IngestResultItem(**r) for r in raw]
    return IngestResponse(
        total=len(items_out),
        indexed=sum(1 for r in items_out if r.status == "indexed"),
        skipped=sum(1 for r in items_out if r.status == "skipped"),
        failed=sum(1 for r in items_out if r.status in ("failed", "error")),
        items=items_out,
    )


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: UUID, s: Session = Depends(get_session)) -> None:
    doc = s.get(models.Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    vectorstore.delete_by_document(str(doc.id))
    s.delete(doc)
    s.commit()
