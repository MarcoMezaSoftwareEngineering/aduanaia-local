"""Helpers para PDFs: hashing y clasificación por nombre de archivo."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


_DOC_TYPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^DLeg[-_]?\d+", re.IGNORECASE), "decreto_legislativo"),
    (re.compile(r"^Ley[-_]?\d+", re.IGNORECASE), "ley"),
    (re.compile(r"^DS[-_]?\d+", re.IGNORECASE), "decreto_supremo"),
    (re.compile(r"^RS[-_]?\d+", re.IGNORECASE), "resolucion"),
    (re.compile(r"^Informe[-_]", re.IGNORECASE), "informe"),
    (re.compile(r"^Boletin[-_]", re.IGNORECASE), "boletin"),
    (re.compile(r"^Manual[-_]", re.IGNORECASE), "manual"),
    (re.compile(r"^Consulta[-_]", re.IGNORECASE), "consulta"),
    (re.compile(r"^Preguntas[-_]", re.IGNORECASE), "faq"),
    (re.compile(r"^lista", re.IGNORECASE), "catalogo"),
    (re.compile(r"^arancel", re.IGNORECASE), "arancel"),
    (re.compile(r"^EER", re.IGNORECASE), "procedimiento"),
]


def sha256_of_file(path: Path, chunk_bytes: int = 1024 * 1024) -> str:
    """Hash SHA-256 streaming para evitar cargar el PDF entero en memoria."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_bytes):
            h.update(chunk)
    return h.hexdigest()


def infer_document_type(filename: str) -> str:
    """Infiere el tipo de documento desde el nombre del archivo (heurística §18)."""
    stem = Path(filename).stem
    for pattern, doc_type in _DOC_TYPE_PATTERNS:
        if pattern.search(stem):
            return doc_type
    return "otro"


def infer_entity_from_path(path: Path) -> str:
    """Carpeta padre define entidad (docs/vuce → VUCE, docs/sunat → SUNAT)."""
    parent = path.parent.name.lower()
    mapping = {
        "vuce": "VUCE",
        "sunat": "SUNAT",
        "mef": "MEF",
        "digemid": "DIGEMID",
        "senasa": "SENASA",
        "sucamec": "SUCAMEC",
        "mtc": "MTC",
        "produce": "PRODUCE",
        "minsa": "MINSA",
    }
    return mapping.get(parent, "desconocida")
