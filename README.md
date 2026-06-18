# AduanaIA Local

Sistema RAG + agentes LangGraph para apoyo al análisis preliminar de mercancías aduaneras (restringidas, prohibidas, inmovilizadas). Ejecución 100% local en GPU NVIDIA, sin APIs pagadas.

> **Estado actual:** MVP en construcción — Fase 1 (entorno) y Fase 2 (RAG normativo básico).
> Las fases 3–5 (agentes de evaluación, clasificación de riesgo, informe exportable) están en el roadmap pero no implementadas todavía.

Ver [DOCUMENTO TÉCNICO DEL PROYECTO.txt](DOCUMENTO%20T%C3%89CNICO%20DEL%20PROYECTO.txt) para la especificación completa.

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

## Setup en Windows 11 nativo

### 1. Prerrequisitos del sistema

Instalar manualmente (una sola vez):

1. **Drivers NVIDIA** actualizados — verificar con `nvidia-smi`.
2. **Python 3.11** desde [python.org](https://www.python.org/downloads/).
3. **Ollama for Windows** desde [ollama.com](https://ollama.com/download/windows).
4. **PostgreSQL 16** desde [postgresql.org](https://www.postgresql.org/download/windows/).
5. **Docker Engine** (para Milvus). Sin Docker Desktop: instalar Docker CE.
6. **Tesseract OCR** desde [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) (con paquete de idioma español).
7. **Git for Windows** si no lo tienes.

### 2. Bajar modelos locales

```powershell
ollama pull qwen3:8b
ollama ps    # verificar que el modelo está disponible
```

### 3. Crear base de datos

En `psql` o pgAdmin:

```sql
CREATE USER aduanaia WITH PASSWORD 'aduanaia';
CREATE DATABASE aduanaia OWNER aduanaia;
```

### 4. Levantar Milvus

```powershell
docker compose up -d
docker compose ps    # los 3 servicios deben estar healthy
```

### 5. Entorno Python

```powershell
python -m venv .venv
.\.venv\Scripts\activate

# Torch con CUDA 12.1 (compatible con RTX 3080):
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121

# Resto de dependencias:
pip install -r requirements.txt

# Verificar GPU disponible para PyTorch:
python -c "import torch; print('CUDA:', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0))"
```

### 6. Configuración

```powershell
copy .env.example .env
# Editar .env con la contraseña real de Postgres y la ruta a Tesseract si difiere.
```

### 7. Inicializar bases de datos

```powershell
python scripts/init_db.py
```

### 8. Ingestar los documentos normativos

```powershell
python scripts/ingest_docs.py
```

Esto procesa todos los PDFs en [docs/vuce/](docs/vuce/) y [docs/sunat/](docs/sunat/), genera chunks, embeddings y los indexa en Milvus.

### 9. Lanzar la UI

```powershell
streamlit run ui/streamlit_app.py
```

O para usar la API directamente:

```powershell
uvicorn app.main:app --reload
```

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
