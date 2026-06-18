"""Cliente Milvus Standalone — colección `aduana_normativa_chunks` (§17 del doc)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Sequence

from pymilvus import DataType, MilvusClient

from app.config import settings
from app.utils.logging import get_logger


log = get_logger(__name__)


@dataclass(slots=True)
class SearchHit:
    chunk_id: str
    document_id: str
    text: str
    page_number: int | None
    score: float
    document_type: str | None
    entity: str | None


@lru_cache(maxsize=1)
def get_client() -> MilvusClient:
    """Singleton para reutilizar la conexión gRPC."""
    log.info("Conectando a Milvus en %s", settings.milvus_uri)
    return MilvusClient(uri=settings.milvus_uri)


def ensure_collection() -> None:
    """Crea la colección si no existe. Idempotente."""
    client = get_client()
    name = settings.milvus_collection
    if client.has_collection(name):
        log.info("Colección Milvus '%s' ya existe.", name)
        return

    log.info("Creando colección Milvus '%s' (dim=%d).", name, settings.embedding_dim)
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("chunk_id", DataType.VARCHAR, max_length=64, is_primary=True)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=settings.embedding_dim)
    schema.add_field("document_id", DataType.VARCHAR, max_length=64)
    schema.add_field("document_type", DataType.VARCHAR, max_length=64)
    schema.add_field("entity", DataType.VARCHAR, max_length=64)
    schema.add_field("topic", DataType.VARCHAR, max_length=128)
    schema.add_field("tariff_code", DataType.VARCHAR, max_length=32)
    schema.add_field("year", DataType.INT16)
    schema.add_field("page_number", DataType.INT32)
    schema.add_field("text", DataType.VARCHAR, max_length=8192)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_type="IVF_FLAT",
        metric_type="COSINE",
        params={"nlist": 128},
    )

    client.create_collection(
        collection_name=name,
        schema=schema,
        index_params=index_params,
    )
    client.load_collection(name)
    log.info("Colección '%s' creada e indexada.", name)


def insert_chunks(rows: Sequence[dict[str, Any]]) -> None:
    """Inserta un batch. Cada row debe tener todos los campos del schema."""
    if not rows:
        return
    client = get_client()
    client.insert(collection_name=settings.milvus_collection, data=list(rows))


def search(
    query_vector: Sequence[float],
    top_k: int | None = None,
    filter_expr: str | None = None,
) -> list[SearchHit]:
    """Búsqueda semántica. `filter_expr` es una expresión Milvus opcional."""
    client = get_client()
    k = top_k or settings.rag_top_k
    results = client.search(
        collection_name=settings.milvus_collection,
        data=[list(query_vector)],
        limit=k,
        search_params={"metric_type": "COSINE", "params": {"nprobe": 16}},
        output_fields=[
            "chunk_id", "document_id", "text", "page_number",
            "document_type", "entity",
        ],
        filter=filter_expr or "",
    )
    if not results or not results[0]:
        return []
    # pymilvus 2.5: cada hit es dict con "id", "distance" y "entity": {output_fields}.
    hits: list[SearchHit] = []
    for raw in results[0]:
        fields = raw.get("entity", {}) if isinstance(raw, dict) else {}
        hits.append(
            SearchHit(
                chunk_id=str(fields.get("chunk_id") or raw.get("id", "")),
                document_id=str(fields.get("document_id", "")),
                text=str(fields.get("text", "")),
                page_number=fields.get("page_number"),
                score=float(raw.get("distance", 0.0)),
                document_type=fields.get("document_type"),
                entity=fields.get("entity"),
            )
        )
    return hits


def delete_by_document(document_id: str) -> None:
    client = get_client()
    client.delete(
        collection_name=settings.milvus_collection,
        filter=f'document_id == "{document_id}"',
    )


def count() -> int:
    client = get_client()
    stats = client.get_collection_stats(settings.milvus_collection)
    return int(stats.get("row_count", 0))
