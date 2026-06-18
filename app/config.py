"""Configuración central cargada desde .env vía pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # PostgreSQL
    database_url: str = Field(
        default="postgresql+psycopg://aduanaia:aduanaia@localhost:5432/aduanaia"
    )

    # Ollama
    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen3:8b"
    llm_temperature: float = 0.2
    llm_top_p: float = 0.9
    llm_max_tokens: int = 1500
    llm_context_tokens: int = 8192

    # Embeddings
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cuda"
    embedding_batch_size: int = 32
    embedding_dim: int = 1024

    # Milvus
    milvus_uri: str = "http://localhost:19530"
    milvus_collection: str = "aduana_normativa_chunks"

    # RAG (§20 del documento técnico)
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 150
    rag_top_k: int = 12
    rag_top_k_final: int = 5
    rag_min_score: float = 0.55

    # Rutas
    docs_base_path: Path = PROJECT_ROOT / "docs"
    upload_path: Path = PROJECT_ROOT / "docs" / "uploaded"
    processed_path: Path = PROJECT_ROOT / "data" / "processed"
    reports_path: Path = PROJECT_ROOT / "reports"

    # OCR
    tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    tesseract_lang: str = "spa+eng"
    # Si los .traineddata están fuera de la carpeta default de Tesseract
    # (típico cuando no hay permisos en Program Files), apuntar aquí.
    tessdata_prefix: str | None = None

    # Logging
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
