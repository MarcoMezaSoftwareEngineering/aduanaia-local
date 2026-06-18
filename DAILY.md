# DAILY — uso día a día

Después del [setup inicial](SETUP.md), esta es la rutina para **abrir el proyecto, probarlo y cerrarlo cada día**. Toma 1–2 minutos.

---

## Modelo mental: qué hay que arrancar

El sistema depende de **4 servicios** corriendo en paralelo. Algunos se inician solos al prender la PC, otros tienes que arrancarlos manualmente:

| Servicio | ¿Se inicia solo al prender la PC? |
|---|---|
| **PostgreSQL** | ✅ Sí (servicio de Windows automático) |
| **Ollama** | ✅ Sí (queda corriendo en bandeja del sistema) |
| **Docker Desktop** | ⚠️ Depende — si lo configuraste para auto-start sí, sino lo abres tú |
| **Containers de Milvus** | ❌ No — `docker compose start` manual cada día |

Y además, **tú** abres:
- El entorno virtual de Python (`.\.venv\Scripts\Activate.ps1`)
- La UI (Streamlit) o la API (FastAPI)

---

## Rutina al inicio del día

### Paso 1 — Abrir Docker Desktop

Si no se abre solo al iniciar Windows, abre **Docker Desktop** desde el menú inicio. Espera 20-30 segundos hasta que el icono en la bandeja diga "Docker Desktop is running".

Verificación rápida:

```powershell
docker ps
```

Si responde con una tabla (aunque sea vacía), el daemon está vivo. Si dice "cannot connect to daemon", Docker aún no terminó de iniciar.

### Paso 2 — Levantar los containers de Milvus

Si tus containers ya existían de ayer (es lo normal), **basta con `start`** (no `up -d` que recrearía cosas):

```powershell
cd F:\PROGRAMACION\aduanaia-local
docker compose start
```

Espera ~30 segundos y verifica:

```powershell
docker compose ps
```

Los 4 servicios (`etcd`, `minio`, `milvus`, `attu`) deben estar en `(healthy)` o al menos `Up`.

> **Diferencia entre `up -d` y `start`**:
> - `up -d` crea los containers (la primera vez) o los recrea si cambiaste `docker-compose.yml`.
> - `start` solo enciende containers ya existentes. **Es el comando del día a día.**

### Paso 3 — Activar el entorno virtual de Python

```powershell
cd F:\PROGRAMACION\aduanaia-local
.\.venv\Scripts\Activate.ps1
```

Verás `(.venv)` al inicio del prompt. Esto es indispensable: sin venv, `python` apunta al global y faltan las dependencias del proyecto.

### Paso 4 — (Opcional) Verificar el stack en 5 segundos

Si quieres confirmar que todo responde antes de lanzar la UI:

```powershell
ollama ps                                          # debe listar qwen3:8b
docker compose ps                                  # debe haber 4 containers healthy
python -c "from app.db.session import engine; engine.connect().close(); print('Postgres OK')"
```

Si alguno falla, ve a la sección [Troubleshooting](#troubleshooting) abajo.

### Paso 5 — Lanzar la UI

```powershell
streamlit run ui\streamlit_app.py
```

Se abre automáticamente en http://localhost:8501. **Deja esta terminal corriendo** — si la cierras se cierra la app.

Para silenciar el warning cosmético de `torch.classes`:

```powershell
streamlit run ui\streamlit_app.py --server.fileWatcherType=poll
```

---

## Variantes según lo que quieras hacer

### Solo hacer consultas → Streamlit (lo normal)

Es lo del paso 5. Listo.

### Probar la API REST (sin UI) → FastAPI

En la misma terminal (con venv activo):

```powershell
uvicorn app.main:app --reload
```

Abre http://localhost:8000/docs — Swagger interactivo donde puedes probar endpoints con clicks.

### Inspeccionar Milvus (ver vectores indexados) → Attu

Solo abrir en el navegador: http://localhost:8200

La primera vez te pide conectarte:
- Milvus Address: `milvus:19530`
- Database: `default`
- Click "Connect"

Después puedes navegar la colección `aduana_normativa_chunks`, hacer queries manuales, ver el schema y los índices.

### Inspeccionar Postgres → psql

```powershell
$env:PGPASSWORD = 'aduanaia'
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U aduanaia -h 127.0.0.1 -p 5432 -d aduanaia
```

> Si tu Postgres está en puerto 5433, cambia `5432` por `5433`.

Dentro, comandos útiles:
```sql
\dt                                       -- listar tablas
SELECT count(*) FROM documents;           -- cuántos docs hay
SELECT count(*) FROM chunks;              -- cuántos chunks
SELECT * FROM queries ORDER BY created_at DESC LIMIT 5;   -- últimas consultas
\q                                         -- salir
```

Para más queries útiles ver la sección 5.2 de [GUIA_OPERATIVA.md](GUIA_OPERATIVA.md).

---

## Cuando agregues PDFs nuevos

1. Copia los PDFs a `docs\vuce\` o `docs\sunat\` (o crea una carpeta propia bajo `docs\`).
2. Con el venv activo:
   ```powershell
   python scripts\ingest_docs.py
   ```
3. La ingesta es **idempotente** — los PDFs ya indexados se saltan automáticamente (detección por SHA-256). Solo procesa los nuevos.

Si necesitas re-procesar todo (porque cambiaste algo en el chunker o quieres limpiar): `--force`.
Si un PDF tiene texto corrupto: `--force --force-ocr <ruta>`.

Para detalles, ver la sección 2 de [GUIA_OPERATIVA.md](GUIA_OPERATIVA.md).

---

## Rutina al final del día

### Opción A — Vas a apagar la PC

No hace falta hacer nada especial. Cuando Windows se apague:
- Postgres se cierra solo.
- Ollama se cierra solo.
- Docker Desktop cierra los containers (no los borra, los apaga).

Mañana, al prender la PC, solo repite los pasos 1-5 de arriba.

### Opción B — Solo dejas de trabajar pero la PC sigue prendida

En la terminal de Streamlit: `Ctrl+C` (cierra la app pero NO los containers).

Si quieres liberar RAM y VRAM mientras no usas el sistema:

```powershell
# Apaga los containers (conserva los datos)
docker compose stop

# Si quieres descargar Qwen3 de la VRAM:
ollama stop qwen3:8b
```

Al volver, simplemente: `docker compose start` y `ollama` se carga solo al primer uso.

### Opción C — Quieres que TODO siga corriendo

No hagas nada. Streamlit se queda escuchando, los containers siguen vivos, el modelo en VRAM. Consume RAM/VRAM pero las consultas son instantáneas.

---

## Cómo saber si algo está mal

Si la UI carga pero las respuestas dicen *"no encuentro información suficiente"* repetidamente, en **cada** consulta (incluso con queries que antes funcionaban):

```powershell
# 1. ¿Hay vectores indexados?
python -c "from app.core.vectorstore import get_client; c=get_client(); c.flush('aduana_normativa_chunks'); print(c.get_collection_stats('aduana_normativa_chunks'))"
# Si row_count = 0, vuelve a correr ingest_docs.py

# 2. ¿Postgres tiene datos?
$env:PGPASSWORD = 'aduanaia'
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U aduanaia -h 127.0.0.1 -p 5432 -d aduanaia -c "SELECT count(*) FROM chunks;"
# Si es 0, mismo: re-ingestar

# 3. ¿El LLM responde?
python -c "from app.core import llm; print(llm.ask('Di OK', system='Sé conciso.'))"

# 4. ¿GPU disponible?
python -c "import torch; print('CUDA:', torch.cuda.is_available())"
```

---

## Troubleshooting

| Problema | Solución |
|---|---|
| `docker ps` dice "Cannot connect to daemon" | Docker Desktop no abierto. Ábrelo y espera 30s |
| `docker compose start` dice "no such service" | Estás en la carpeta equivocada. `cd` a la raíz del repo |
| Activar venv falla con "execution policy" | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y reintenta |
| Streamlit no abre el navegador | Abre manual http://localhost:8501 |
| Streamlit dice "port 8501 already in use" | Otra instancia corriendo. `Ctrl+C` en la otra terminal, o usa `--server.port 8502` |
| El chat tarda >30s en responder | Primera consulta del día: BGE-M3 + Qwen3 se cargan en GPU. Las siguientes son rápidas |
| `ollama ps` no lista qwen3:8b | Ollama no inició. Abre Ollama desde menú inicio, o `ollama run qwen3:8b` para forzar la carga |
| Postgres no conecta | Abre "Servicios" de Windows, busca `postgresql-x64-16`, click derecho → Iniciar |

Para troubleshooting completo, ver sección 9 de [GUIA_OPERATIVA.md](GUIA_OPERATIVA.md).

---

## Resumen visual: comandos del día

```powershell
# === AL INICIO DEL DÍA ===
cd F:\PROGRAMACION\aduanaia-local
docker compose start            # arranca containers (10-30s)
.\.venv\Scripts\Activate.ps1    # activa venv
streamlit run ui\streamlit_app.py    # lanza UI

# === DURANTE EL DÍA, EN OTRA TERMINAL (opcional) ===
.\.venv\Scripts\Activate.ps1    # cada terminal nueva requiere su propia activación
python scripts\ingest_docs.py   # si agregaste PDFs

# === AL FINAL DEL DÍA (opcional) ===
# Ctrl+C en la terminal de Streamlit
docker compose stop             # apaga containers conservando datos
```

Tres comandos para arrancar, tres para cerrar (si quieres liberar recursos). Eso es todo.
