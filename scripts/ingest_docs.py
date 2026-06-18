"""Ingesta batch de los documentos normativos en docs/.

Uso:
    python scripts/ingest_docs.py           # idempotente, salta los ya indexados
    python scripts/ingest_docs.py --force   # reprocesa todo

Procesa docs/vuce/ y docs/sunat/. Si quieres procesar una ruta específica,
edita BASE_DIRS o pásala como argumento posicional.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permitir importar `app.*` cuando se ejecuta desde la raíz del repo.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.core import ingestion
from app.utils.logging import get_logger, setup_logging


setup_logging()
log = get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingesta de PDFs normativos.")
    parser.add_argument(
        "paths", nargs="*", type=Path,
        help="Directorios o PDFs específicos. Default: docs/vuce y docs/sunat.",
    )
    parser.add_argument("--force", action="store_true", help="Reprocesar incluso si ya está indexado.")
    parser.add_argument(
        "--force-ocr", action="store_true",
        help="Ignorar el texto embebido del PDF y aplicar OCR puro (útil para PDFs con fuentes corruptas).",
    )
    args = parser.parse_args()

    if args.paths:
        targets = args.paths
    else:
        base = settings.docs_base_path
        targets = [base / "vuce", base / "sunat"]

    total: list[dict] = []
    for target in targets:
        if target.is_file():
            total.append(ingestion.ingest_pdf(target, force=args.force, force_ocr=args.force_ocr))
        elif target.is_dir():
            total.extend(ingestion.ingest_directory(target, force=args.force, force_ocr=args.force_ocr))
        else:
            log.warning("Saltando ruta inexistente: %s", target)

    # Milvus es eventualmente consistente; forzamos flush para que los inserts queden
    # persistidos y get_collection_stats refleje el row_count real.
    try:
        from app.core.vectorstore import get_client
        get_client().flush(settings.milvus_collection)
        log.info("Flush de Milvus completado.")
    except Exception as exc:
        log.warning("No se pudo hacer flush en Milvus: %s", exc)

    indexed = sum(1 for r in total if r["status"] == "indexed")
    skipped = sum(1 for r in total if r["status"] == "skipped")
    failed = sum(1 for r in total if r["status"] in ("failed", "error"))
    log.info(
        "Ingesta finalizada: total=%d  indexados=%d  saltados=%d  fallidos=%d",
        len(total), indexed, skipped, failed,
    )
    if failed:
        for r in total:
            if r["status"] in ("failed", "error"):
                log.warning("  - %s: %s", r.get("path"), r.get("reason"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
