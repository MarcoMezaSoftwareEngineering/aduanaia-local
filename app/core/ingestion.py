"""Pipeline de ingesta: extracción → chunking → embeddings → indexación.

Idempotente por hash SHA-256: si un PDF ya fue indexado (mismo hash), se salta.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.config import settings
from app.core import chunking, embeddings, extraction, vectorstore
from app.db import models
from app.db.session import session_scope
from app.utils.logging import get_logger
from app.utils.pdf import infer_document_type, infer_entity_from_path, sha256_of_file


log = get_logger(__name__)


def _is_already_indexed(hash_value: str) -> models.Document | None:
    with session_scope() as s:
        return (
            s.query(models.Document)
            .filter_by(hash=hash_value, status="indexed")
            .one_or_none()
        )


def _register_document(path: Path, hash_value: str) -> tuple[str, str]:
    """Crea o reusa la fila documents. Devuelve (document_id, status)."""
    with session_scope() as s:
        existing = s.query(models.Document).filter_by(hash=hash_value).one_or_none()
        if existing:
            existing.status = "pending"
            existing.upload_date = datetime.utcnow()
            s.flush()
            return str(existing.id), "reused"
        doc = models.Document(
            id=uuid4(),
            filename=path.name,
            document_type=infer_document_type(path.name),
            source=infer_entity_from_path(path),
            upload_date=datetime.utcnow(),
            hash=hash_value,
            status="pending",
            meta={"path": str(path)},
        )
        s.add(doc)
        s.flush()
        return str(doc.id), "new"


def _persist_chunks(
    document_id: str,
    chunks: list[chunking.TextChunk],
    vectors,
) -> list[dict]:
    """Inserta chunks en Postgres y arma filas para Milvus."""
    doc_type = None
    entity = None
    with session_scope() as s:
        doc = s.get(models.Document, document_id)
        if doc is None:
            raise RuntimeError(f"Documento {document_id} no encontrado.")
        doc_type = doc.document_type
        entity = doc.source

        # limpiar chunks previos por si era reproceso
        s.query(models.Chunk).filter_by(document_id=doc.id).delete()
        s.flush()

        milvus_rows: list[dict] = []
        for idx, (ck, vec) in enumerate(zip(chunks, vectors)):
            chunk_id = uuid4()
            row = models.Chunk(
                id=chunk_id,
                document_id=doc.id,
                chunk_index=idx,
                content=ck.content,
                page_number=ck.page_number,
                meta={"section_marker": ck.section_marker} if ck.section_marker else None,
                milvus_vector_id=str(chunk_id),
            )
            s.add(row)
            milvus_rows.append(
                {
                    "chunk_id": str(chunk_id),
                    "vector": vec.tolist(),
                    "document_id": str(doc.id),
                    "document_type": doc_type or "otro",
                    "entity": entity or "desconocida",
                    "topic": "",
                    "tariff_code": "",
                    "year": 0,
                    "page_number": int(ck.page_number or 0),
                    "text": ck.content[:8000],   # truncar al max_length del schema
                }
            )
        doc.status = "indexed"
    return milvus_rows


def ingest_pdf(path: Path, force: bool = False, force_ocr: bool = False) -> dict:
    """Procesa un PDF y devuelve un resumen. Idempotente salvo `force=True`.

    `force_ocr=True` ignora el texto embebido del PDF y aplica OCR puro. Útil para
    PDFs con fuentes corruptas (mojibake)."""
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    digest = sha256_of_file(path)
    if not force and _is_already_indexed(digest):
        log.info("Saltando %s (ya indexado)", path.name)
        return {"path": str(path), "status": "skipped", "reason": "already_indexed"}

    document_id, reg_status = _register_document(path, digest)
    log.info("Documento registrado id=%s status=%s", document_id, reg_status)

    pages = extraction.extract_pdf(path, force_ocr=force_ocr)
    chunks = chunking.chunk_pages(pages)
    log.info("Chunks generados: %d", len(chunks))

    if not chunks:
        with session_scope() as s:
            doc = s.get(models.Document, document_id)
            if doc:
                doc.status = "failed"
        return {"path": str(path), "status": "failed", "reason": "no_chunks"}

    vectors = embeddings.embed_texts([c.content for c in chunks])
    log.info("Embeddings generados: shape=%s", tuple(vectors.shape))

    vectorstore.ensure_collection()
    # Borrar vectores previos del documento (por si era reproceso).
    vectorstore.delete_by_document(document_id)
    milvus_rows = _persist_chunks(document_id, chunks, vectors)
    vectorstore.insert_chunks(milvus_rows)

    return {
        "path": str(path),
        "status": "indexed",
        "document_id": document_id,
        "chunks": len(chunks),
    }


def ingest_directory(root: Path, force: bool = False, force_ocr: bool = False) -> list[dict]:
    """Recorre recursivamente y procesa todos los .pdf."""
    root = root.resolve()
    if not root.exists():
        log.warning("Directorio inexistente: %s", root)
        return []
    pdfs = sorted(root.rglob("*.pdf"))
    log.info("%d PDFs encontrados en %s", len(pdfs), root)
    results: list[dict] = []
    for pdf in pdfs:
        try:
            results.append(ingest_pdf(pdf, force=force, force_ocr=force_ocr))
        except Exception as exc:
            log.exception("Falló ingesta de %s", pdf)
            results.append({"path": str(pdf), "status": "error", "reason": str(exc)})
    return results
