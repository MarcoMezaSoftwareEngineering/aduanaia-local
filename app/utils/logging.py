"""Logging estructurado simple."""
from __future__ import annotations

import logging
import sys

from app.config import settings


_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    # En Windows la consola por defecto usa cp1252 y rompe con caracteres como '→'.
    # Forzamos UTF-8 si la plataforma lo permite.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format=_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Bajar verbosidad de librerías ruidosas.
    for noisy in ("urllib3", "httpx", "httpcore", "pymilvus.client.grpc_handler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
