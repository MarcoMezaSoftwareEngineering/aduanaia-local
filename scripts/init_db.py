"""Inicializa esquema Postgres + colección Milvus.

Idempotente: corre todas las veces que quieras; crea solo lo que falte.

Uso:
    python scripts/init_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permitir importar `app.*` cuando se ejecuta desde la raíz del repo.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core import llm, vectorstore
from app.db import models
from app.db.session import engine
from app.utils.logging import get_logger, setup_logging


setup_logging()
log = get_logger(__name__)


def init_postgres() -> None:
    log.info("Creando tablas Postgres si no existen...")
    models.Base.metadata.create_all(bind=engine)
    log.info("Tablas Postgres listas.")


def init_milvus() -> None:
    log.info("Inicializando colección Milvus...")
    vectorstore.ensure_collection()
    log.info("Milvus listo.")


def smoke_test_llm() -> None:
    log.info("Smoke test del LLM (puede tardar la primera vez en cargar el modelo en GPU)...")
    try:
        response = llm.ask("Responde solo: OK", system="Eres conciso.")
        log.info("LLM responde: %r", response.strip()[:200])
    except Exception as exc:
        log.warning("LLM no respondió (¿Ollama corriendo? ¿modelo descargado?): %s", exc)


def main() -> int:
    init_postgres()
    init_milvus()
    smoke_test_llm()
    log.info("init_db.py completado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
