"""UI Streamlit del MVP — Fase 2.

Dos pantallas:
1. Chat normativo — consulta sobre el corpus, con fuentes citadas.
2. Admin documental — lista de documentos indexados + reindexar.

Uso:
    streamlit run ui/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permitir importar `app.*` cuando se ejecuta desde la raíz del repo.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.config import settings
from app.core import ingestion, rag
from app.db import models
from app.db.session import session_scope


st.set_page_config(
    page_title="AduanaIA Local",
    page_icon=":customs:",
    layout="wide",
)


def render_chat() -> None:
    st.title("Consulta normativa aduanera")
    st.caption(
        "Pregunta sobre normativa aduanera local. Las respuestas se sustentan en el "
        "corpus indexado y citan documento + página. **La decisión final corresponde "
        "al funcionario competente.**"
    )

    question = st.text_area(
        "Tu consulta",
        height=120,
        placeholder=(
            "Ej: ¿Qué establece la Ley General de Aduanas sobre el régimen de envíos "
            "de entrega rápida?"
        ),
    )
    run = st.button("Consultar", type="primary", disabled=not question.strip())

    if run:
        with st.spinner("Recuperando normativa y generando respuesta..."):
            response = rag.answer(question.strip())

        st.subheader("Respuesta")
        st.write(response.answer)

        st.subheader(f"Fuentes recuperadas ({len(response.sources)})")
        if not response.sources:
            st.info("No se recuperó normativa con score ≥ %.2f." % settings.rag_min_score)
        for s in response.sources:
            page = s.page_number or "s/n"
            with st.expander(f"[doc:{s.index}] {s.document_filename or s.document_id} — p.{page} (score {s.score:.3f})"):
                st.text(s.text)

        st.caption(f"query_id = `{response.query_id}`")


def render_admin() -> None:
    st.title("Administración documental")
    st.caption(
        "Documentos cargados e indexados. Reindexa cuando agregues PDFs nuevos a "
        f"`{settings.docs_base_path}` o subas archivos via API."
    )

    with session_scope() as s:
        docs = (
            s.query(models.Document)
            .order_by(models.Document.upload_date.desc())
            .all()
        )
        rows = []
        for d in docs:
            rows.append(
                {
                    "filename": d.filename,
                    "type": d.document_type,
                    "source": d.source,
                    "status": d.status,
                    "chunks": len(d.chunks),
                    "uploaded": d.upload_date.strftime("%Y-%m-%d %H:%M") if d.upload_date else "",
                    "id": str(d.id),
                }
            )

    if not rows:
        st.warning("No hay documentos en la base. Corre `python scripts/ingest_docs.py` o usa el botón abajo.")
    else:
        st.dataframe(rows, use_container_width=True)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        force = st.checkbox("Forzar reproceso (reindexa todo)", value=False)
    with col2:
        if st.button("Ingestar/Reindexar corpus", type="primary"):
            base = settings.docs_base_path
            targets = [base / "vuce", base / "sunat", settings.upload_path]
            with st.spinner("Procesando documentos (puede tardar varios minutos)..."):
                results: list[dict] = []
                for t in targets:
                    if t.exists():
                        results.extend(ingestion.ingest_directory(t, force=force))
            indexed = sum(1 for r in results if r["status"] == "indexed")
            skipped = sum(1 for r in results if r["status"] == "skipped")
            failed = sum(1 for r in results if r["status"] in ("failed", "error"))
            st.success(f"Indexados: {indexed} | Saltados: {skipped} | Fallidos: {failed}")
            if failed:
                st.error("Detalle de fallos:")
                for r in results:
                    if r["status"] in ("failed", "error"):
                        st.write(f"- `{r.get('path')}`: {r.get('reason')}")


def main() -> None:
    page = st.sidebar.radio("Navegación", ["Chat normativo", "Admin documental"])
    st.sidebar.divider()
    st.sidebar.caption(
        f"**Modelo:** {settings.llm_model}\n\n"
        f"**Embeddings:** {settings.embedding_model}\n\n"
        f"**top_k:** {settings.rag_top_k} → top_final {settings.rag_top_k_final}\n\n"
        f"**min_score:** {settings.rag_min_score}"
    )
    st.sidebar.warning(
        "Este sistema es un asistente técnico. No reemplaza la decisión del "
        "funcionario aduanero competente."
    )

    if page == "Chat normativo":
        render_chat()
    else:
        render_admin()


main()
