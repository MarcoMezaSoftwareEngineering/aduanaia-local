# SETUP — instalación desde cero

Guía paso a paso para dejar el proyecto **AduanaIA Local** corriendo en una PC con **Windows 11 nativo + NVIDIA RTX 3080 10 GB**. Es para el **primer día** que instalas todo. Para el día a día tras el setup, ver [DAILY.md](DAILY.md).

Tiempo estimado total: **2–4 horas** (mayormente esperando descargas e instaladores).

---

## Índice

1. [Pre-requisitos del sistema (instaladores GUI)](#1-pre-requisitos-del-sistema-instaladores-gui)
2. [Bajar Qwen3 8B con Ollama](#2-bajar-qwen3-8b-con-ollama)
3. [Crear la base de datos en PostgreSQL](#3-crear-la-base-de-datos-en-postgresql)
4. [Configurar Tesseract con paquete de español](#4-configurar-tesseract-con-paquete-de-español)
5. [Clonar el repositorio](#5-clonar-el-repositorio)
6. [Crear el entorno virtual de Python](#6-crear-el-entorno-virtual-de-python)
7. [Instalar PyTorch con CUDA](#7-instalar-pytorch-con-cuda)
8. [Instalar el resto de dependencias](#8-instalar-el-resto-de-dependencias)
9. [Crear el archivo `.env`](#9-crear-el-archivo-env)
10. [Levantar Milvus con Docker](#10-levantar-milvus-con-docker)
11. [Inicializar tablas y colección](#11-inicializar-tablas-y-colección)
12. [Ingestar los documentos normativos](#12-ingestar-los-documentos-normativos)
13. [Lanzar la app y probar](#13-lanzar-la-app-y-probar)
14. [Verificación final](#14-verificación-final)

---

## 1. Pre-requisitos del sistema (instaladores GUI)

Estos son los componentes a nivel del SO. Cada uno se instala UNA SOLA VEZ y queda en el sistema permanentemente.

### 1.1 Drivers NVIDIA actualizados

**¿Por qué?** El LLM y el modelo de embeddings corren en GPU. Si los drivers son viejos, PyTorch/CUDA no pueden usar la tarjeta.

1. Abre PowerShell y ejecuta:
   ```powershell
   nvidia-smi
   ```
2. Si dice "command not found" o "Driver Version: 4xx", actualiza desde:
   https://www.nvidia.com/Download/index.aspx → busca tu modelo (GeForce RTX 3080) → descarga el driver más reciente.
3. Vuelve a verificar:
   ```powershell
   nvidia-smi
   ```
   Debe mostrar tu GPU y "CUDA Version: 12.x" o superior.

### 1.2 Python 3.11

**¿Por qué?** Las librerías clave (`torch`, `sentence-transformers`, `pymilvus`) todavía no están al 100% en 3.13/3.14. 3.11 es la versión estable más probada.

1. Descarga el instalador desde https://www.python.org/downloads/release/python-3119/
2. Elige **"Windows installer (64-bit)"**.
3. Durante la instalación marca **"Add python.exe to PATH"**.
4. Verifica:
   ```powershell
   py -3.11 --version
   ```
   Debe decir `Python 3.11.x`.

> Si ya tienes otras versiones de Python (3.12, 3.13, 3.14), no las desinstales. El `py launcher` permite tener varias y elegir cuál usar con `py -3.11`.

### 1.3 Git for Windows

**¿Por qué?** Para clonar el repo desde GitHub.

```powershell
winget install --id Git.Git -e --source winget
```

Verifica:
```powershell
git --version
```

### 1.4 Ollama for Windows

**¿Por qué?** Es el "servidor" que mantiene cargado el modelo de lenguaje (Qwen3 8B) en la GPU y expone una API HTTP local para que el código lo consulte.

1. Descarga desde https://ollama.com/download/windows
2. Ejecuta el instalador. Al terminar, Ollama queda corriendo como **servicio en background** (icono en la bandeja del sistema, esquina inferior derecha).
3. Verifica:
   ```powershell
   ollama --version
   ```

### 1.5 PostgreSQL 16

**¿Por qué?** Guarda la metadata del sistema: lista de documentos, chunks (texto plano), historial de consultas, fuentes recuperadas por cada query. Es la "memoria de trazabilidad".

1. Descarga el instalador EDB desde https://www.enterprisedb.com/downloads/postgres-postgresql-downloads → versión 16.x → Windows x86-64.
2. Durante la instalación:
   - **Puerto**: acepta el default `5432` o cambia a `5433` si ya tienes otro Postgres en `5432`.
   - **Password del usuario `postgres`**: anótala. La usarás solo una vez (en el paso 3) para crear el usuario del proyecto.
   - **Stack Builder**: desmárcalo al final, no lo necesitas.

### 1.6 Tesseract OCR

**¿Por qué?** Algunos PDFs (los escaneados o los que tienen fuentes corruptas como vimos en el corpus aduanero) requieren reconocimiento óptico de caracteres para extraer texto legible. Tesseract es el motor OCR.

1. Descarga el instalador desde https://github.com/UB-Mannheim/tesseract/wiki
2. Durante la instalación:
   - En **"Additional language data"** marca **"Spanish"** (y deja "English" marcado por default).
   - Anota la ruta de instalación (default: `C:\Program Files\Tesseract-OCR`).
3. Verifica:
   ```powershell
   & "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
   & "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
   ```
   El segundo comando debe listar **`spa`** y **`eng`**.

> Si olvidaste marcar Spanish, descarga manualmente [spa.traineddata](https://github.com/tesseract-ocr/tessdata/raw/main/spa.traineddata) y cópialo a `C:\Program Files\Tesseract-OCR\tessdata\` (necesita permisos de administrador). Como alternativa, ponlo en una carpeta de tu usuario (`C:\Users\TU_USUARIO\tessdata\`) y configurarás `TESSDATA_PREFIX` en el paso 9.

### 1.7 Docker Desktop

**¿Por qué?** Milvus (la base de datos vectorial) corre en containers. Docker Desktop es el runtime más común en Windows. Las alternativas (Podman Desktop, Rancher Desktop) también funcionan, pero el resto de la guía asume Docker.

1. Descarga desde https://www.docker.com/products/docker-desktop/
2. Instala (te pedirá habilitar WSL2 si no lo está; déjalo hacer).
3. Al terminar, abre **Docker Desktop** desde el menú de inicio. Espera a que el icono diga "Docker Desktop is running".
4. Verifica:
   ```powershell
   docker --version
   docker ps
   ```
   El segundo comando debe mostrar una tabla vacía (sin error de "daemon no responde").

---

## 2. Bajar Qwen3 8B con Ollama

**¿Por qué?** Aunque Ollama está instalado, el modelo de lenguaje no viene incluido. Hay que descargarlo aparte (5 GB).

```powershell
ollama pull qwen3:8b
```

Verifica:

```powershell
ollama list
```

Debe aparecer `qwen3:8b` con tamaño ~5 GB. Prueba que carga en GPU:

```powershell
ollama run qwen3:8b "Responde solo: OK"
```

Debe responder "OK" en pocos segundos. La primera vez tarda más porque carga el modelo en VRAM. En otra terminal:

```powershell
ollama ps
```

Debe listar `qwen3:8b` con `PROCESSOR: 100% GPU`.

---

## 3. Crear la base de datos en PostgreSQL

**¿Por qué?** El proyecto necesita un usuario y una BD propios (`aduanaia` / `aduanaia`) para no mezclarse con otras BDs que tengas.

Abre psql como superusuario (te pedirá la password de `postgres` que pusiste en 1.5):

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432
```

> Si elegiste puerto 5433, cambia `5432` por `5433` aquí y en todos los comandos siguientes.

Dentro de psql, ejecuta:

```sql
CREATE USER aduanaia WITH PASSWORD 'aduanaia';
CREATE DATABASE aduanaia OWNER aduanaia;
\q
```

Verifica conexión con el usuario nuevo:

```powershell
$env:PGPASSWORD = 'aduanaia'
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U aduanaia -h 127.0.0.1 -p 5432 -d aduanaia -c "SELECT current_user, current_database();"
```

Debe imprimir `aduanaia | aduanaia`.

---

## 4. Configurar Tesseract con paquete de español

Si en el paso 1.6 marcaste "Spanish", **salta este paso**. Si lo olvidaste, hazlo ahora:

```powershell
$dst = "C:\Users\$env:USERNAME\tessdata"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Invoke-WebRequest -Uri "https://github.com/tesseract-ocr/tessdata/raw/main/spa.traineddata" -OutFile "$dst\spa.traineddata"
Copy-Item "C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata" "$dst\eng.traineddata"
$env:TESSDATA_PREFIX = $dst
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

Debe listar `spa` y `eng`. Recuerda la ruta `$dst` — la configuraremos en `.env` en el paso 9.

---

## 5. Clonar el repositorio

**¿Por qué?** Bajar el código del proyecto desde GitHub.

Elige la carpeta padre donde quieres que viva el proyecto (ej. `F:\PROGRAMACION`). Abre PowerShell ahí:

```powershell
cd F:\PROGRAMACION
git clone https://github.com/MarcoMezaSoftwareEngineering/aduanaia-local.git
cd aduanaia-local
```

Verifica que estás en la raíz correcta:

```powershell
ls
```

Debes ver `app/`, `docs/`, `scripts/`, `requirements.txt`, `README.md`, etc.

---

## 6. Crear el entorno virtual de Python

**¿Por qué?** Para aislar las dependencias del proyecto del Python global. Si actualizas algo en este venv, no rompe otros proyectos.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Después del segundo comando verás el prefijo `(.venv)` en el prompt — eso significa que el venv está activo.

> **Si PowerShell bloquea el script de activación** con un error tipo "execution policy", ejecuta una vez:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```
> y vuelve a ejecutar `Activate.ps1`.

Verifica que pip apunta al venv (no al Python global):

```powershell
python -m pip --version
```

La ruta debe contener `\.venv\`.

Actualiza pip a su versión más reciente:

```powershell
python -m pip install --upgrade pip
```

---

## 7. Instalar PyTorch con CUDA

**¿Por qué?** PyTorch tiene wheels distintos según la versión de CUDA que use tu GPU. **No puedes instalarlo desde el `requirements.txt` normal** — hay que apuntar a un índice especial. Esto es lo que más confunde la primera vez.

Tu driver NVIDIA soporta CUDA hasta 13.x (compatible hacia atrás). El wheel `cu124` (CUDA 12.4) funciona perfecto:

```powershell
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124
```

La descarga son ~3 GB, tarda 3-10 minutos.

**Verificación obligatoria**:

```powershell
python -c "import torch; print('CUDA disponible:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"
```

Debe imprimir:
```
CUDA disponible: True
GPU: NVIDIA GeForce RTX 3080
```

Si dice `CUDA disponible: False`:
- Revisa que `nvidia-smi` siga funcionando (paso 1.1).
- Reinstala asegurando el índice `cu124` (no es lo mismo que el wheel CPU).

---

## 8. Instalar el resto de dependencias

```powershell
pip install -r requirements.txt
```

Tarda 5-10 minutos. Instala FastAPI, LangChain, LangGraph, pymilvus, sentence-transformers, Streamlit y más (110+ paquetes).

**Fix de compatibilidad necesario** — pymilvus 2.5 todavía usa `pkg_resources`, que setuptools 81+ eliminó. Ejecuta:

```powershell
pip install "setuptools<81"
```

Verifica importaciones críticas:

```powershell
python -c "import fastapi, langgraph, pymilvus, sentence_transformers, streamlit; print('OK: imports clave funcionan')"
```

---

## 9. Crear el archivo `.env`

**¿Por qué?** Aquí van las credenciales reales y rutas que el código necesita. **Nunca se sube a GitHub** (está en `.gitignore`).

```powershell
Copy-Item .env.example .env
notepad .env
```

Edita en el Notepad:

| Variable | Valor que debes ajustar |
|---|---|
| `DATABASE_URL` | Si tu Postgres está en puerto 5433 cambia `5432` por `5433`. Si pusiste otra password al usuario aduanaia, cámbiala también. |
| `TESSERACT_CMD` | Verifica que la ruta exista en tu máquina (`C:\Program Files\Tesseract-OCR\tesseract.exe` es lo default). |
| `TESSDATA_PREFIX` | Solo si descargaste `spa.traineddata` en una ruta custom (paso 4). Si Tesseract ya tiene español en su carpeta default, **deja esta variable vacía** o coméntala con `#`. |

Las demás variables (modelo LLM, embeddings, parámetros RAG) ya vienen con valores razonables. Guarda y cierra el Notepad.

---

## 10. Levantar Milvus con Docker

**¿Por qué?** Milvus es la base de datos vectorial. Junto con sus dependencias (etcd para metadata interna, MinIO para almacenamiento) corre en 3 containers + 1 opcional (Attu = UI web).

Asegúrate de que **Docker Desktop está abierto y corriendo** (icono activo en la bandeja).

```powershell
docker compose up -d
```

Esto baja las imágenes (~2 GB la primera vez) y arranca los containers. Tarda 2-5 minutos.

Verifica:

```powershell
docker compose ps
```

Debe haber 4 contenedores en estado `(healthy)`:
- `aduanaia-etcd`
- `aduanaia-minio`
- `aduanaia-milvus`
- `aduanaia-attu`

Si Milvus dice `health: starting`, espera 30 segundos más y vuelve a consultar.

Verifica que Milvus responde:

```powershell
curl http://localhost:9091/healthz
```

Y que Attu (la UI web) carga: abre en el navegador http://localhost:8200

---

## 11. Inicializar tablas y colección

**¿Por qué?** Las tablas en Postgres y la colección en Milvus no se crean solas. El script `init_db.py` las crea con el schema correcto. Es **idempotente** (puedes correrlo varias veces sin problema).

```powershell
python scripts\init_db.py
```

Esperado:

```
[INFO] Tablas Postgres listas.
[INFO] Colección 'aduana_normativa_chunks' creada e indexada.
[INFO] LLM responde: 'OK'
[INFO] init_db.py completado.
```

Si el "smoke test del LLM" tarda mucho la primera vez (>30s), es normal: Ollama está cargando Qwen3 a la VRAM. Verifica con `ollama ps` que la GPU se está usando.

---

## 12. Ingestar los documentos normativos

**¿Por qué?** El sistema no puede responder sobre normativa que no haya leído. Este script lee los 18 PDFs en `docs/vuce` y `docs/sunat`, los chunkea, genera embeddings con BGE-M3 (que se descarga la primera vez, ~2.3 GB) y los indexa en Milvus.

```powershell
python scripts\ingest_docs.py
```

La primera ejecución tarda **10-20 minutos**:
1. Descarga BGE-M3 desde Hugging Face (una sola vez, queda cacheado).
2. Procesa los 18 PDFs uno por uno.

Esperado al final:

```
[INFO] Ingesta finalizada: total=18  indexados=16  saltados=0  fallidos=2
```

> **Es esperado que 2 PDFs fallen** la primera vez (Ley 28008 y Reglamento LGA). Tienen un texto digital corrupto. Repróceslos con OCR forzado:
>
> ```powershell
> python scripts\ingest_docs.py --force --force-ocr docs\sunat\Ley-28008-Delitos-Aduaneros.pdf docs\sunat\DS-010-2009-EF-Reglamento-LGA.pdf
> ```
>
> Esto tarda otros ~5 minutos (Tesseract es lento pero produce texto legible).

Confirma el conteo final:

```powershell
python -c "from app.core.vectorstore import get_client; c=get_client(); c.flush('aduana_normativa_chunks'); print(c.get_collection_stats('aduana_normativa_chunks'))"
```

Debe decir aproximadamente `{'row_count': 3300+}`.

---

## 13. Lanzar la app y probar

```powershell
streamlit run ui\streamlit_app.py
```

Esto abre tu navegador en http://localhost:8501.

Prueba con una pregunta tipo:

> *¿Qué establece la Ley General de Aduanas sobre el régimen de envíos de entrega rápida?*

Debes ver:
- Una respuesta con citas `[doc:1, p.X]`.
- Una sección "Fuentes recuperadas" con 3-5 chunks expandibles, cada uno con su score.
- Una advertencia explícita de que la decisión final corresponde al funcionario competente.

---

## 14. Verificación final

Si llegaste aquí y todo respondió, el sistema está completamente operativo. Para confirmar de forma programática:

```powershell
pytest tests\test_smoke.py -v -s
```

Debe pasar al menos el test puro `test_chunking_respects_articles`. Si Postgres + Milvus + Ollama están vivos también pasará `test_end_to_end_query_returns_sources`.

---

## ¿Qué hago a partir de mañana?

El setup de arriba es **una sola vez**. Para el día a día (PC reiniciada, quiero abrir la app, hacer cambios, etc.) ver [DAILY.md](DAILY.md).

---

## Problemas comunes durante el setup

| Síntoma | Causa probable | Solución |
|---|---|---|
| `nvidia-smi` no se reconoce | Drivers no instalados o PATH incompleto | Instalar drivers desde nvidia.com y reiniciar |
| `py -3.11` dice "no encontrado" | Python 3.11 no instalado | Volver al paso 1.2 |
| `torch.cuda.is_available()` = False | Wheel CPU instalado por error | `pip uninstall torch` y reinstalar con `--index-url https://download.pytorch.org/whl/cu124` |
| `pip install` falla con "Microsoft Visual C++ required" | Falta Build Tools | Instalar [Build Tools de Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/) marcando "Desktop development with C++" |
| `docker compose up` dice "Cannot connect to daemon" | Docker Desktop no abierto | Abrir Docker Desktop desde menú inicio y esperar 30s |
| `init_db.py` falla con `pkg_resources not found` | setuptools 81+ | `pip install "setuptools<81"` |
| `init_db.py` falla con `connection refused` a Postgres | Postgres no corriendo | Abrir "Servicios" de Windows, iniciar `postgresql-x64-16` |
| Streamlit abre pero el chat dice "no encuentro información" | Threshold muy alto o no hay vectores | Verificar `python -c "from app.core.vectorstore import get_client; print(get_client().get_collection_stats('aduana_normativa_chunks'))"`. Si es 0, ejecutar `python scripts\ingest_docs.py` |
| Mojibake (`Llma` en vez de `Lima`) en respuestas | PDF con fuente corrupta | `python scripts\ingest_docs.py --force --force-ocr docs\sunat\NOMBRE_PDF.pdf` |

Para más troubleshooting, ver la sección 9 de [GUIA_OPERATIVA.md](GUIA_OPERATIVA.md).
