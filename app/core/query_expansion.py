"""Expansión de query para mejorar recall del RAG en queries con códigos.

Los embeddings semánticos (BGE-M3) son fuertes con conceptos pero débiles con
identificadores exactos: códigos legales, números de resolución, subpartidas
arancelarias. Una query como "N° 184-2020/SUNAT" pierde la mayor parte de su
señal porque "184" y "2020" no son palabras semánticamente ricas.

Este módulo detecta patrones comunes de normativa peruana aduanera y enriquece
la query con contexto semántico antes de pasarla al embedder. La query original
se conserva para mostrar al usuario y guardar en logs.
"""
from __future__ import annotations

import re

from app.utils.logging import get_logger


log = get_logger(__name__)


# Cada patrón mapea a la "frase de contexto" que se concatena a la query original.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Resoluciones de Superintendencia SUNAT: "N° 184-2020/SUNAT", "RS 000184-2020/SUNAT"
    (
        re.compile(
            r"(?:RS|Res(?:oluci[óo]n)?\.?\s*(?:de\s*Superintendencia)?\s*)?N[°º.]?\s*0*\d{2,}\s*[-/]\s*\d{4}\s*/?\s*SUNAT",
            re.IGNORECASE,
        ),
        "Resolución de Superintendencia SUNAT, normativa aduanera, procedimiento",
    ),
    # Decretos Supremos: "DS 192-2020-EF", "D.S. 192-2020-EF", "Decreto Supremo 192-2020-EF"
    (
        re.compile(
            r"(?:DS|D\.?\s*S\.?|Decreto\s+Supremo)\s*N?[°º.]?\s*\d{2,}\s*-\s*\d{4}\s*-\s*[A-Z]+",
            re.IGNORECASE,
        ),
        "Decreto Supremo, reglamento, normativa peruana",
    ),
    # Decretos Legislativos: "DLeg 1542", "DLeg-1542", "Decreto Legislativo 1542"
    (
        re.compile(
            r"(?:DLeg|D\.?\s*Leg\.?|Decreto\s+Legislativo)\s*N?[°º.]?\s*\d{3,}",
            re.IGNORECASE,
        ),
        "Decreto Legislativo, ley, normativa aduanera peruana",
    ),
    # Leyes: "Ley N° 28008", "Ley 28008"
    (
        re.compile(r"\bLey\s+N?[°º.]?\s*\d{4,}", re.IGNORECASE),
        "Ley peruana, normativa, delitos aduaneros",
    ),
    # Procedimientos DESPA: "DESPA-PG.28", "DESPA PG 28"
    (
        re.compile(r"DESPA[-\s]?PG[.\-\s]?\s*\d+", re.IGNORECASE),
        "procedimiento general aduanero, DESPA, SUNAT",
    ),
    # Subpartidas arancelarias: "1234.56.78.00" (puede tener 6 a 10 dígitos en bloques)
    (
        re.compile(r"\b\d{4}\.\d{2}\.\d{2}(?:\.\d{2})?\b"),
        "subpartida arancelaria, clasificación arancelaria",
    ),
    # Régimen EER: "EER", "envíos de entrega rápida"
    (
        re.compile(r"\bEER\b", re.IGNORECASE),
        "Envíos de Entrega Rápida, régimen aduanero especial, courier",
    ),
    # VUCE
    (
        re.compile(r"\bVUCE\b", re.IGNORECASE),
        "Ventanilla Única de Comercio Exterior, mercancías restringidas, autorización sectorial",
    ),
]


def expand_query(query: str) -> str:
    """Detecta códigos legales/aduaneros y enriquece la query con contexto semántico.

    Si no detecta ningún patrón, devuelve la query original sin cambios.
    Si detecta uno o más, concatena las frases de contexto al final.

    Examples:
        >>> expand_query("N° 184-2020/SUNAT")
        'N° 184-2020/SUNAT. Resolución de Superintendencia SUNAT, normativa aduanera, procedimiento'

        >>> expand_query("contrabando según Ley 28008")
        'contrabando según Ley 28008. Ley peruana, normativa, delitos aduaneros'

        >>> expand_query("¿qué dice el reglamento general?")
        '¿qué dice el reglamento general?'
    """
    additions: list[str] = []
    seen: set[str] = set()
    for pattern, context in _PATTERNS:
        if pattern.search(query) and context not in seen:
            additions.append(context)
            seen.add(context)
    if not additions:
        return query
    expanded = f"{query}. {'. '.join(additions)}"
    return expanded
