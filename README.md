# AduanaIA Local

Sistema RAG + agentes LangGraph para apoyo al análisis preliminar de mercancías aduaneras (restringidas, prohibidas, inmovilizadas). Ejecución 100% local en GPU NVIDIA, sin APIs pagadas.

> **Estado actual:** MVP en construcción — Fase 1 (entorno) y Fase 2 (RAG normativo básico).
> Las fases 3–5 (agentes de evaluación, clasificación de riesgo, informe exportable) están en el roadmap pero no implementadas todavía.

## Documentación del proyecto

| Si quieres... | Lee |
|---|---|
| **Instalar desde cero en una PC nueva** | [SETUP.md](SETUP.md) — guía paso a paso (~2-4 h) |
| **Usar el sistema día a día** (PC reiniciada, abrir app) | [DAILY.md](DAILY.md) — rutina de 1-2 min |
| **Comandos operativos** (ingesta, queries, troubleshooting, Milvus/Attu) | [GUIA_OPERATIVA.md](GUIA_OPERATIVA.md) |
| **Diseño técnico y alcance funcional completo** | [DOCUMENTO TÉCNICO DEL PROYECTO.txt](DOCUMENTO%20T%C3%89CNICO%20DEL%20PROYECTO.txt) |

## Stack

| Capa             | Tecnología                                       |
|------------------|--------------------------------------------------|
| Backend          | FastAPI + Pydantic 2                             |
| Orquestación IA  | LangGraph + LangChain                            |
| LLM local        | Qwen3 8B Instruct (Q4_K_M) vía Ollama, GPU       |
| Embeddings       | BGE-M3 vía sentence-transformers, GPU            |
| Vector store     | Milvus Standalone (Docker)                       |
| Base relacional  | PostgreSQL 16                                    |
| Extracción PDF   | PyMuPDF + pdfplumber + Tesseract (OCR fallback)  |
| UI               | Streamlit                                        |

## Requisitos de hardware

- GPU NVIDIA con ≥ 10 GB VRAM (target: RTX 3080 10 GB).
- CPU moderno (target: i7-10700K).
- RAM ≥ 32 GB recomendado.
- SSD/NVMe con ≥ 100 GB libres.

## Setup

Hay dos documentos según en qué momento estés:

- **Primera vez instalando todo en una PC nueva** → [SETUP.md](SETUP.md) (paso a paso completo, ~2-4 h).
- **Día a día tras el primer setup** (abrir app, hacer cambios, agregar PDFs) → [DAILY.md](DAILY.md) (rutina de 1-2 min).

Para operaciones específicas (re-ingestar con OCR, queries SQL, troubleshooting, usar Attu para inspeccionar Milvus, etc.) ver [GUIA_OPERATIVA.md](GUIA_OPERATIVA.md).

## Estructura del repo

```
app/        # Backend FastAPI
  api/      # Endpoints HTTP
  core/     # RAG, extracción, chunking, embeddings, vectorstore, LLM, grafo
  db/       # SQLAlchemy models + sesión
  prompts/  # Prompts del sistema
  utils/    # PDF helpers, logging
ui/         # Streamlit
scripts/    # init_db, ingest_docs
data/       # Cache local, modelos
docs/       # Corpus normativo (VUCE, SUNAT)
tests/      # Smoke tests
reports/    # Informes generados (Fase 5)
```

## Limitaciones del MVP

Según §8 del documento técnico, este sistema **NO**:

- emite decisiones legales definitivas;
- reemplaza al funcionario aduanero;
- inventa normativa cuando no encuentra sustento (debe decirlo explícitamente);
- recomienda levante, comiso o sanción sin advertencia de revisión humana obligatoria.

Toda respuesta del sistema incluye una advertencia explícita de que la decisión final corresponde al funcionario competente.
