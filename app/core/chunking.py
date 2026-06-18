"""Chunking que respeta fronteras de artículos / numerales en normativa peruana.

Estrategia (§18 paso 4):
  1. Para cada página, intentamos detectar markers de inicio de unidad legal
     (Artículo N°, Numeral, ANEXO, CAPÍTULO...).
  2. Si encontramos markers, cortamos en ellos. Si la unidad legal resultante
     es muy grande, la subdividimos con overlap.
  3. Si no hay markers (FAQ, manual, boletín), recurrimos a chunking por tamaño
     con overlap fijo.

Tamaños van en caracteres (no tokens) para evitar cargar un tokenizer aquí; el
ratio caracteres↔tokens en español normativo es ~4:1, por lo que rag_chunk_size
en tokens lo multiplicamos por 4 para obtener tamaño en caracteres aproximado.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings
from app.core.extraction import PageText


_ARTICLE_MARKERS = re.compile(
    r"""(
        ^\s*Art[íi]culo\s+\d+[°º]?[.\-:\s]   |
        ^\s*ANEXO\s+[A-Z0-9]+                 |
        ^\s*CAP[ÍI]TULO\s+[IVXLCDM0-9]+       |
        ^\s*T[ÍI]TULO\s+[IVXLCDM0-9]+         |
        ^\s*Numeral\s+\d+[.\)]                |
        ^\s*\d+\.\d+(\.\d+)?\s
    )""",
    re.MULTILINE | re.VERBOSE | re.IGNORECASE,
)


_CHAR_PER_TOKEN = 4  # heurística para español


def _max_chars() -> int:
    return settings.rag_chunk_size * _CHAR_PER_TOKEN


def _overlap_chars() -> int:
    return settings.rag_chunk_overlap * _CHAR_PER_TOKEN


@dataclass(slots=True)
class TextChunk:
    content: str
    page_number: int
    section_marker: str | None     # ej. "Artículo 12" si lo detectamos


def _split_by_size(text: str, page_number: int, marker: str | None) -> list[TextChunk]:
    """Sliding window con overlap cuando un bloque excede max_chars."""
    out: list[TextChunk] = []
    max_c = _max_chars()
    overlap = _overlap_chars()
    if len(text) <= max_c:
        return [TextChunk(text.strip(), page_number, marker)]
    step = max_c - overlap
    if step <= 0:
        step = max_c
    start = 0
    while start < len(text):
        end = min(start + max_c, len(text))
        # intentar terminar en final de oración cercano
        if end < len(text):
            window = text[start:end]
            last_dot = max(window.rfind(". "), window.rfind(".\n"), window.rfind("\n\n"))
            if last_dot > max_c // 2:
                end = start + last_dot + 1
        piece = text[start:end].strip()
        if piece:
            out.append(TextChunk(piece, page_number, marker))
        if end >= len(text):
            break
        start = end - overlap
    return out


def _chunk_page(page: PageText) -> list[TextChunk]:
    if not page.text.strip():
        return []
    matches = list(_ARTICLE_MARKERS.finditer(page.text))
    if not matches:
        return _split_by_size(page.text, page.page_number, marker=None)

    # Hay markers: cortamos por ellos.
    chunks: list[TextChunk] = []
    # texto antes del primer marker (suele ser cabecera)
    prefix_end = matches[0].start()
    prefix = page.text[:prefix_end].strip()
    if len(prefix) > 60:  # ignorar cabeceras minúsculas
        chunks.extend(_split_by_size(prefix, page.page_number, marker=None))
    # bloques entre markers consecutivos
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(page.text)
        block = page.text[start:end].strip()
        if not block:
            continue
        marker = block.splitlines()[0][:80].strip()
        chunks.extend(_split_by_size(block, page.page_number, marker))
    return chunks


def chunk_pages(pages: list[PageText]) -> list[TextChunk]:
    """Aplica el chunker a cada página y devuelve la lista plana."""
    out: list[TextChunk] = []
    for page in pages:
        out.extend(_chunk_page(page))
    return out
