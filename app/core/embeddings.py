"""Wrapper BGE-M3 vía sentence-transformers (GPU)."""
from __future__ import annotations

from functools import lru_cache
from typing import Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.utils.logging import get_logger


log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    """Carga BGE-M3 en GPU. Singleton para evitar recargar el modelo (~2.3 GB VRAM)."""
    log.info(
        "Cargando modelo de embeddings %s en device=%s",
        settings.embedding_model,
        settings.embedding_device,
    )
    model = SentenceTransformer(settings.embedding_model, device=settings.embedding_device)
    # BGE-M3 produce embeddings de 1024 dim por defecto; verificamos para detectar
    # desalineaciones temprano.
    actual_dim = model.get_sentence_embedding_dimension()
    if actual_dim != settings.embedding_dim:
        log.warning(
            "Dim de embedding del modelo (%d) ≠ EMBEDDING_DIM en settings (%d). "
            "Ajusta EMBEDDING_DIM en .env antes de crear la colección Milvus.",
            actual_dim, settings.embedding_dim,
        )
    return model


def embed_texts(texts: Sequence[str]) -> np.ndarray:
    """Codifica una lista de textos en vectores normalizados (cosine-ready)."""
    if not texts:
        return np.empty((0, settings.embedding_dim), dtype=np.float32)
    model = get_embedder()
    arr = model.encode(
        list(texts),
        batch_size=settings.embedding_batch_size,
        normalize_embeddings=True,         # imprescindible para usar COSINE en Milvus
        convert_to_numpy=True,
        show_progress_bar=len(texts) > 100,
    )
    return arr.astype(np.float32, copy=False)


def embed_query(text: str) -> np.ndarray:
    """Codifica una consulta de búsqueda. BGE-M3 no requiere prefijo de instrucción."""
    return embed_texts([text])[0]
