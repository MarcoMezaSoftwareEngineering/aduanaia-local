# Guía operativa de AduanaIA Local

Documento práctico de uso diario: cómo arrancar, cómo procesar documentos, cómo inspeccionar el sistema, cómo solucionar problemas comunes. Para detalles técnicos de arquitectura ver [DOCUMENTO TÉCNICO DEL PROYECTO.txt](DOCUMENTO%20T%C3%89CNICO%20DEL%20PROYECTO.txt) y [README.md](README.md).

---

## 1. Entorno de trabajo

### 1.1 Activar el entorno virtual

Cada vez que abras una terminal nueva para trabajar con el proyecto:

```powershell
cd F:\PROGRAMACION\ia_test_langgraph
.\.venv\Scripts\Activate.ps1
```

Verás el prefijo `(.venv)` en el prompt cuando esté activo. **Todos los comandos `python` y `streamlit` de esta guía asumen que el venv está activado.**

Si PowerShell bloquea el script de activación la primera vez, ejecuta una vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Para salir del venv: `deactivate`.

### 1.2 Verificar que todo el stack está vivo

```powershell
# GPU (debe listar la RTX 3080)
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader

# Ollama corriendo + modelo descargado
ollama ps

# Containers de Milvus + Attu
docker compose ps

# Postgres responde
$env:PGPASSWORD = 'aduanaia'
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U aduanaia -h 127.0.0.1 -p 5433 -d aduanaia -c "SELECT 'ok' AS pg;"
```

Todo lo de Milvus debe estar en `(healthy)`. Si algo no responde, salta a la sección 9 (Troubleshooting).

### 1.3 Levantar / bajar los containers

```powershell
# Levantar todo el stack (etcd + minio + milvus + attu)
docker compose up -d

# Ver estado
docker compose ps

# Apagar todo (conserva los datos en volumes/)
docker compose down

# Apagar y BORRAR todos los datos vectoriales (¡cuidado!)
docker compose down -v

# Ver logs en vivo de un servicio
docker compose logs -f milvus
```

---

## 2. Ingesta de documentos

El script [scripts/ingest_docs.py](scripts/ingest_docs.py) es la puerta de entrada para procesar PDFs. Es **idempotente por hash SHA-256**: si vuelves a correrlo, salta los que ya están indexados.

### 2.1 Ingesta normal (uso del día a día)

Recorre `docs/vuce/` y `docs/sunat/` y procesa solo los nuevos:

```powershell
python scripts\ingest_docs.py
```

### 2.2 Reprocesar todo desde cero

Útil cuando cambiaste el chunker, el modelo de embeddings, o quieres regenerar todo:

```powershell
python scripts\ingest_docs.py --force
```

Borra chunks/vectores viejos y los regenera para los 18 PDFs.

### 2.3 Forzar OCR (saltarse el texto embebido)

Para PDFs cuyo texto está corrupto (mojibake) — como nos pasó con Ley 28008 y Reglamento LGA:

```powershell
python scripts\ingest_docs.py --force --force-ocr
```

**Lento**: cada página debe ser rasterizada y procesada por Tesseract (~10-20s por página). Para 18 PDFs son 30-60 minutos.

### 2.4 Procesar un archivo específico

```powershell
# Un solo PDF
python scripts\ingest_docs.py docs\sunat\Ley-28008-Delitos-Aduaneros.pdf

# Con OCR forzado
python scripts\ingest_docs.py --force --force-ocr docs\sunat\Ley-28008-Delitos-Aduaneros.pdf

# Una carpeta específica
python scripts\ingest_docs.py docs\sunat
```

### 2.5 Guardar log de la ingesta

```powershell
python scripts\ingest_docs.py --force 2>&1 | Tee-Object -FilePath ingesta.log
```

Verás la salida en pantalla y queda guardada en `ingesta.log`.

### 2.6 Verificar el resultado de una ingesta

Justo después de ingestar:

```powershell
# Conteo de docs y chunks en Postgres
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U aduanaia -h 127.0.0.1 -p 5433 -d aduanaia -c "SELECT (SELECT count(*) FROM documents) AS docs, (SELECT count(*) FROM chunks) AS chunks;"

# Conteo de vectores en Milvus
python -c "from app.core.vectorstore import get_client; c=get_client(); c.flush('aduana_normativa_chunks'); print(c.get_collection_stats('aduana_normativa_chunks'))"
```

Los dos números deben coincidir.

---

## 3. Lanzar la aplicación

### 3.1 UI Streamlit (lo normal)

```powershell
streamlit run ui\streamlit_app.py
```

Abre http://localhost:8501.

Para silenciar el warning de `torch.classes` que sale en consola:

```powershell
streamlit run ui\streamlit_app.py --server.fileWatcherType=poll
```

### 3.2 API FastAPI (para integración o scripting)

```powershell
uvicorn app.main:app --reload
```

Abre http://localhost:8000/docs — Swagger interactivo. Endpoints:

| Método | Ruta | Para |
|---|---|---|
| `GET` | `/health` | Smoke test |
| `GET` | `/documents` | Listar documentos indexados |
| `POST` | `/documents/upload` | Subir un PDF nuevo |
| `POST` | `/documents/index` | Re-procesar todos los pendientes |
| `DELETE` | `/documents/{id}` | Borrar un documento |
| `POST` | `/query` | Hacer una consulta normativa |

### 3.3 Ejemplo de query a la API con curl

```powershell
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{\"question\": \"Que es el contrabando?\"}'
```

---

## 4. Milvus — operaciones e inspección

### 4.1 Qué es y por qué importa

Milvus es la **base de datos vectorial** donde se guardan los embeddings de cada chunk. Cuando haces una pregunta, el sistema embebe la pregunta y busca los vectores más cercanos por similitud coseno.

- Colección actual: `aduana_normativa_chunks`
- Dimensión: 1024 (BGE-M3)
- Métrica: COSINE
- Índice: IVF_FLAT con nlist=128

Para conceptos a fondo (qué es flush, índice, schema, métrica), ver el chat o la documentación oficial en https://milvus.io/docs.

### 4.2 Attu — la UI web de Milvus

Attu es la interfaz oficial. Ya viene incluida en [docker-compose.yml](docker-compose.yml).

**Acceso:** http://localhost:8200

**Conexión inicial:** la primera vez te pide el host de Milvus. Pon:
- Milvus Address: `milvus:19530`
- Database: `default`
- Click "Connect"

**Qué puedes hacer en Attu:**

1. **Ver colecciones** — sidebar izquierdo, "Collections". Verás `aduana_normativa_chunks` con la cuenta de entities.

2. **Inspeccionar el schema** — clic en la colección → "Schema". Muestra todos los campos, tipos, índices.

3. **Query manual** — pestaña "Data Query":
   - Filter: `document_type == "ley"` → lista chunks que son de leyes
   - Output fields: `text, page_number, entity`
   - Click "Query" → tabla con los resultados

4. **Vector search manual** — pestaña "Data Query" → "Vector Search":
   - Puedes pegar un vector de 1024 dims y ver los top-k. Útil para debugging.

5. **Ver estadísticas y rendimiento** — pestaña "Overview" del lado izquierdo. Métricas globales del nodo.

6. **Operaciones de mantenimiento** — desde Attu puedes hacer flush, load/release, hasta drop de colección. **Cuidado con drop**, borra todo.

### 4.3 Comandos rápidos desde Python

```powershell
# Conteo real (forzando flush primero)
python -c "from app.core.vectorstore import get_client; c=get_client(); c.flush('aduana_normativa_chunks'); print(c.get_collection_stats('aduana_normativa_chunks'))"

# Ver primeros 3 vectores con metadata
python -c "
from app.core.vectorstore import get_client
c = get_client()
res = c.query(collection_name='aduana_normativa_chunks', filter='', limit=3, output_fields=['chunk_id','document_id','page_number','document_type'])
for r in res: print(r)
"

# Buscar manualmente con un texto
python -c "
from app.core import embeddings, vectorstore
v = embeddings.embed_query('contrabando').tolist()
for h in vectorstore.search(v, top_k=5):
    print(f'{h.score:.3f} p.{h.page_number} | {h.text[:120]}')
"
```

### 4.4 Borrar y recrear la colección entera

Si quieres empezar de cero solo en Milvus (sin tocar Postgres):

```powershell
python -c "
from app.core.vectorstore import get_client
from app.config import settings
c = get_client()
if c.has_collection(settings.milvus_collection):
    c.drop_collection(settings.milvus_collection)
    print('Colección eliminada.')
"
# Luego reingestar con --force para repoblarla
python scripts\ingest_docs.py --force
```

### 4.5 Filtros híbridos (vector + metadata)

Esta es la feature más potente de Milvus para casos como el nuestro. Puedes restringir la búsqueda a un subconjunto:

```python
# Solo en leyes
vectorstore.search(vec, top_k=12, filter_expr='document_type == "ley"')

# Solo en SUNAT
vectorstore.search(vec, top_k=12, filter_expr='entity == "SUNAT"')

# Combinado
vectorstore.search(vec, top_k=12, filter_expr='entity == "VUCE" && page_number < 10')
```

Sintaxis completa de filtros: https://milvus.io/docs/boolean.md

---

## 5. PostgreSQL — operaciones e inspección

Postgres guarda la metadata: documentos, chunks (texto plano), consultas, fuentes recuperadas.

### 5.1 Conectarse al cliente psql

```powershell
$env:PGPASSWORD = 'aduanaia'
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U aduanaia -h 127.0.0.1 -p 5433 -d aduanaia
```

Comandos útiles dentro de psql:
- `\dt` — listar tablas
- `\d documents` — describir una tabla
- `\q` — salir
- `\x` — toggle modo expanded (mejor para queries con texto largo)

### 5.2 Queries de inspección útiles

Lista de documentos con su estado:

```sql
SELECT filename, document_type, source, status,
       (SELECT count(*) FROM chunks WHERE document_id = d.id) AS chunks
FROM documents d
ORDER BY upload_date DESC;
```

Ver el texto de los primeros chunks de un documento:

```sql
SELECT chunk_index, page_number, substring(content, 1, 200) AS preview
FROM chunks
WHERE document_id = (SELECT id FROM documents WHERE filename = 'Ley-28008-Delitos-Aduaneros.pdf')
ORDER BY chunk_index
LIMIT 10;
```

Historial de queries con sus fuentes:

```sql
SELECT q.created_at,
       q.user_query,
       (SELECT count(*) FROM retrieved_sources WHERE query_id = q.id) AS fuentes
FROM queries q
ORDER BY created_at DESC
LIMIT 20;
```

Ver las fuentes citadas de una query específica:

```sql
SELECT score, page_number, substring(content, 1, 200) AS preview
FROM retrieved_sources
WHERE query_id = (SELECT id FROM queries ORDER BY created_at DESC LIMIT 1)
ORDER BY score DESC;
```

### 5.3 Borrar documentos

Borrar un documento específico (cascade a chunks):

```sql
DELETE FROM documents WHERE filename = 'Boletin-Anual-MR-2024.pdf';
```

**Atención:** esto NO borra los vectores en Milvus. Para borrar también en Milvus, usa el endpoint API `DELETE /documents/{id}` o el script:

```powershell
python -c "
from app.core.vectorstore import delete_by_document
delete_by_document('UUID-DEL-DOCUMENTO')
"
```

### 5.4 Reset total de Postgres

```powershell
# DROP de toda la BD y recreación (¡borra todo!)
$env:PGPASSWORD = 'contra'  # password del superusuario
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5433 -d postgres -c "DROP DATABASE aduanaia; CREATE DATABASE aduanaia OWNER aduanaia;"

# Recrear tablas
python scripts\init_db.py
```

---

## 6. Smoke tests — verificar que el pipeline funciona

### 6.1 Test del LLM (Qwen3 8B en GPU)

```powershell
python -c "from app.core import llm; print(llm.ask('Responde solo: OK', system='Eres conciso.'))"
```

Debe responder "OK" en pocos segundos (la primera vez tarda más por la carga inicial en GPU).

### 6.2 Test de embeddings (BGE-M3 en GPU)

```powershell
python -c "from app.core import embeddings; v = embeddings.embed_query('Hola mundo'); print('dim:', len(v), 'norm:', sum(x*x for x in v)**0.5)"
```

Debe imprimir `dim: 1024 norm: 1.0...` (los embeddings están normalizados).

### 6.3 Test end-to-end de RAG

```powershell
python -c "
from app.core import rag
r = rag.answer('Que es el contrabando segun la Ley 28008?')
print('ANSWER:'); print(r.answer[:500])
print('\nSOURCES:')
for s in r.sources:
    print(f'  [{s.index}] score={s.score:.3f} p.{s.page_number} | {s.document_filename}')
"
```

### 6.4 Test automatizado (pytest)

```powershell
pytest tests/test_smoke.py -v -s
```

El test puro de chunking corre siempre; el test end-to-end se salta automáticamente si Ollama/Postgres/Milvus no están arriba.

---

## 7. Cambiar configuración

Toda la configuración vive en [.env](.env). Algunos cambios útiles:

| Variable | Para qué | Cuándo cambiarla |
|---|---|---|
| `RAG_MIN_SCORE` | Umbral mínimo de score para incluir una fuente | Si tus queries no encuentran nada, bájalo (ej. 0.35) |
| `RAG_TOP_K` | Vectores candidatos iniciales en Milvus | Subir a 20 si quieres más cobertura |
| `RAG_TOP_K_FINAL` | Fuentes que efectivamente van al prompt del LLM | Bajar a 3 para respuestas más concisas |
| `LLM_TEMPERATURE` | Creatividad del LLM | Bajar a 0.1 para más determinismo |
| `LLM_MAX_TOKENS` | Longitud máxima de respuesta | Subir para respuestas largas |
| `LLM_CONTEXT_TOKENS` | Tamaño de contexto del LLM | 8192 es seguro en RTX 3080; subir requiere más VRAM |
| `EMBEDDING_BATCH_SIZE` | Tamaño de batch al ingestar | Bajar a 8 si te quedas sin VRAM durante ingesta |

**Importante:** después de cambiar `.env` debes **reiniciar** Streamlit (Ctrl+C y volver a lanzar). El archivo se lee una sola vez al iniciar la app.

---

## 8. Operaciones avanzadas

### 8.1 Exportar el texto extraído de un PDF (para revisión)

```powershell
python -c "
from app.db.session import session_scope
from app.db import models
filename = 'Ley-28008-Delitos-Aduaneros.pdf'
with session_scope() as s:
    doc = s.query(models.Document).filter_by(filename=filename).one()
    chunks = s.query(models.Chunk).filter_by(document_id=doc.id).order_by(models.Chunk.chunk_index).all()
    with open(f'{filename}.txt', 'w', encoding='utf-8') as f:
        for c in chunks:
            f.write(f'=== Chunk {c.chunk_index} (p.{c.page_number}) ===\n')
            f.write(c.content + '\n\n')
print('Listo:', filename + '.txt')
"
```

### 8.2 Re-procesar solo los documentos que están en estado fallido

```powershell
python -c "
from app.db.session import session_scope
from app.db import models
from app.core import ingestion
from pathlib import Path
with session_scope() as s:
    failed = s.query(models.Document).filter_by(status='failed').all()
    paths = [Path(d.meta['path']) for d in failed if d.meta and 'path' in d.meta]
for p in paths:
    ingestion.ingest_pdf(p, force=True)
"
```

### 8.3 Backup de los volúmenes Docker

Los datos de Milvus persisten en `volumes/etcd/`, `volumes/minio/`, `volumes/milvus/`. Para hacer un backup:

```powershell
docker compose stop
Compress-Archive -Path volumes -DestinationPath ".\backup_milvus_$(Get-Date -Format yyyy-MM-dd).zip"
docker compose start
```

Para restaurar:

```powershell
docker compose down
Expand-Archive backup_milvus_2026-06-12.zip -DestinationPath .
docker compose up -d
```

---

## 9. Troubleshooting

| Síntoma | Diagnóstico | Solución |
|---|---|---|
| Streamlit no recupera fuentes | Threshold muy alto o chunks corruptos | Bajar `RAG_MIN_SCORE` en `.env` y reiniciar Streamlit |
| Query devuelve "no encuentro información" | El corpus no cubre el tema, o threshold alto | Probar `RAG_MIN_SCORE=0.35`, o verificar que el PDF relevante esté ingestado |
| Postgres `connection refused` | Servicio caído | Iniciar PostgreSQL desde "Services" de Windows |
| Milvus `connection refused` | Container caído | `docker compose up -d` |
| `pkg_resources is deprecated` | Setuptools 81+ | Pin a `setuptools<81` (ya está en requirements) |
| `cuda: False` en torch | Driver desactualizado o wheel CPU instalado | Reinstalar `torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124` |
| OOM durante ingesta | Embedder + LLM cargados en VRAM | Bajar `EMBEDDING_BATCH_SIZE` en `.env`, o cerrar Ollama mientras ingesta |
| Mojibake en chunks ("Llma" en vez de "Lima") | PDF con fuente custom defectuosa | Reingestar con `--force --force-ocr` |
| Ollama responde lento | Modelo se descargó pero no está cargado en GPU | `ollama ps` debe mostrar GPU; reiniciar Ollama Desktop |
| Streamlit warning `torch.classes` | Bug conocido Streamlit + PyTorch | Cosmético, ignorar — o usar `--server.fileWatcherType=poll` |
| `row_count: 0` después de ingesta | Falta flush en Milvus | `python -c "from app.core.vectorstore import get_client; get_client().flush('aduana_normativa_chunks')"` |

---

## 10. Referencias rápidas

| Recurso | URL local |
|---|---|
| UI principal Streamlit | http://localhost:8501 |
| API FastAPI + Swagger | http://localhost:8000/docs |
| Attu (UI Milvus) | http://localhost:8200 |
| Milvus healthcheck | http://localhost:9091/healthz |

| Documentación externa | URL |
|---|---|
| Documento técnico del proyecto | [DOCUMENTO TÉCNICO DEL PROYECTO.txt](DOCUMENTO%20T%C3%89CNICO%20DEL%20PROYECTO.txt) |
| Setup inicial paso a paso | [README.md](README.md) |
| Milvus docs | https://milvus.io/docs |
| LangGraph docs | https://langchain-ai.github.io/langgraph/ |
| BGE-M3 model card | https://huggingface.co/BAAI/bge-m3 |
| Ollama docs | https://github.com/ollama/ollama |

---

## 11. Flujo de trabajo típico de una sesión

```powershell
# 1. Abrir terminal y activar venv
cd F:\PROGRAMACION\ia_test_langgraph
.\.venv\Scripts\Activate.ps1

# 2. Verificar que el stack está vivo
docker compose ps
ollama ps

# 3. Si agregaste PDFs nuevos a docs/, ingestar
python scripts\ingest_docs.py

# 4. Lanzar la UI en una terminal
streamlit run ui\streamlit_app.py

# 5. (Opcional) En otra terminal, abrir Attu para inspeccionar Milvus
# Solo abrir el navegador en http://localhost:8200

# 6. Al terminar
#    - Cerrar Streamlit con Ctrl+C
#    - Si vas a apagar la PC: docker compose stop  (no down, no -v)
```

Al volver al día siguiente, solo: `docker compose start`, activar venv, lanzar Streamlit.
