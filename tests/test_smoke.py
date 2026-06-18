"""Smoke tests del pipeline.

Estos tests son end-to-end: requieren Ollama, Postgres y Milvus corriendo.
Se saltan automáticamente si esas dependencias no están disponibles.

Uso:
    pytest tests/test_smoke.py -v -s
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"


def _ollama_up() -> bool:
    import httpx
    try:
        r = httpx.get(f"{settings.ollama_host}/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _postgres_up() -> bool:
    try:
        from app.db.session import engine
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        return False


def _milvus_up() -> bool:
    try:
        from app.core.vectorstore import get_client
        get_client().list_collections()
        return True
    except Exception:
        return False


needs_stack = pytest.mark.skipif(
    not (_ollama_up() and _postgres_up() and _milvus_up()),
    reason="Requiere Ollama + Postgres + Milvus corriendo (ver README).",
)


def test_chunking_respects_articles():
    """Test puro: no requiere servicios."""
    from app.core.chunking import chunk_pages
    from app.core.extraction import PageText

    fake = PageText(
        page_number=3,
        text=(
            "Cabecera irrelevante.\n\n"
            "Artículo 1.- Definiciones. Para los efectos de la presente Ley...\n"
            "Texto del artículo uno con suficiente contenido para validar.\n\n"
            "Artículo 2.- Ámbito de aplicación. Esta Ley se aplica a...\n"
            "Más texto del artículo dos.\n"
        ),
        extraction_quality="alta",
        method="pymupdf",
    )
    chunks = chunk_pages([fake])
    assert len(chunks) >= 2
    markers = [c.section_marker for c in chunks if c.section_marker]
    assert any("Artículo 1" in (m or "") for m in markers)
    assert any("Artículo 2" in (m or "") for m in markers)


@needs_stack
def test_end_to_end_query_returns_sources():
    """Ingiere 1 PDF chico, hace 1 query, verifica que devuelve fuentes con score > min."""
    from app.core import ingestion, rag, vectorstore

    # Tomamos el PDF más liviano del corpus para no demorar el test.
    candidates = sorted(DOCS_DIR.rglob("*.pdf"), key=lambda p: p.stat().st_size)
    assert candidates, "No hay PDFs en docs/ para el smoke test."
    pdf = candidates[0]

    vectorstore.ensure_collection()
    result = ingestion.ingest_pdf(pdf, force=True)
    assert result["status"] == "indexed", result

    # Una query muy genérica que debería pegar algo
    response = rag.answer("¿De qué trata este documento?")
    assert response.answer, "El LLM debe devolver una respuesta no vacía."
    # Para PDFs reales del corpus aduanero, esperamos al menos una fuente.
    assert response.sources, "Se esperaba al menos 1 fuente recuperada."
    assert response.sources[0].score >= settings.rag_min_score
