"""Extracción de texto desde PDF: PyMuPDF → pdfplumber → Tesseract OCR (fallbacks)."""
from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image

from app.config import settings
from app.utils.logging import get_logger


log = get_logger(__name__)

# Configurar binario de Tesseract si está fuera del PATH.
if settings.tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

# Si los .traineddata están fuera de la carpeta default, exportar TESSDATA_PREFIX
# antes de que pytesseract invoque a tesseract.
if settings.tessdata_prefix:
    os.environ["TESSDATA_PREFIX"] = settings.tessdata_prefix


_MIN_TEXT_CHARS = 40  # Por debajo de esto consideramos la página "vacía".


def _sanitize(text: str) -> str:
    """Remueve bytes NUL (Postgres no acepta \\x00 en text) y caracteres de control raros."""
    if not text:
        return ""
    # NUL es el bloqueante de Postgres. Otros control chars también pueden molestar.
    cleaned = text.replace("\x00", "")
    # caracteres C0 (excepto \t \n \r) — algunos PDFs los emiten al traducir glifos exóticos
    cleaned = "".join(c for c in cleaned if c >= " " or c in "\t\n\r")
    return cleaned


def _is_mojibake(text: str) -> bool:
    """Heurística: el texto está corrupto si tiene muchos caracteres sustitución/raros.

    Indicadores:
      - Ratio de '\\ufffd' (replacement char) > 1%
      - Ratio de letras conocidas vs total muy bajo (típico mojibake con muchos ¿|¡|°|� mezclados)
    """
    if len(text) < 200:
        return False
    total = len(text)
    replacement = text.count("�")
    if replacement / total > 0.01:
        return True
    # alfabeto español "normal" — letras + dígitos + espacios + puntuación común
    good = sum(1 for c in text if c.isalnum() or c.isspace() or c in ".,;:()-—\"'¿?¡!ñÑáéíóúÁÉÍÓÚüÜ")
    return (good / total) < 0.85


@dataclass(slots=True)
class PageText:
    page_number: int             # 1-based para que coincida con el visor PDF
    text: str
    extraction_quality: str       # "alta" / "media" / "baja"
    method: str                   # "pymupdf" / "pdfplumber" / "ocr"


def _extract_with_pymupdf(path: Path) -> list[PageText]:
    out: list[PageText] = []
    doc = fitz.open(path)
    try:
        for i, page in enumerate(doc, start=1):
            text = _sanitize((page.get_text("text") or "").strip())
            if len(text) >= _MIN_TEXT_CHARS and not _is_mojibake(text):
                out.append(PageText(i, text, "alta", "pymupdf"))
            else:
                # mojibake o vacío -> marcar como vacía para reintentar con pdfplumber/OCR
                out.append(PageText(i, "", "baja", "pymupdf"))
    finally:
        doc.close()
    return out


def _retry_with_pdfplumber(path: Path, pages: list[PageText]) -> list[PageText]:
    needs_retry = [p for p in pages if not p.text]
    if not needs_retry:
        return pages
    target_indices = {p.page_number for p in needs_retry}
    log.info("PyMuPDF dejó %d páginas vacías; reintento con pdfplumber.", len(target_indices))
    with pdfplumber.open(path) as plumb:
        for i, page in enumerate(plumb.pages, start=1):
            if i not in target_indices:
                continue
            text = _sanitize((page.extract_text() or "").strip())
            if len(text) >= _MIN_TEXT_CHARS and not _is_mojibake(text):
                # reemplazar in-place
                pages[i - 1] = PageText(i, text, "media", "pdfplumber")
    return pages


def _retry_with_ocr(path: Path, pages: list[PageText]) -> list[PageText]:
    still_empty = [p for p in pages if not p.text]
    if not still_empty:
        return pages
    target_indices = {p.page_number for p in still_empty}
    log.info("Páginas aún vacías tras pdfplumber: %d; reintento con OCR.", len(target_indices))
    doc = fitz.open(path)
    try:
        for i, page in enumerate(doc, start=1):
            if i not in target_indices:
                continue
            try:
                pix = page.get_pixmap(dpi=200, alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = _sanitize(pytesseract.image_to_string(img, lang=settings.tesseract_lang).strip())
                if text:
                    pages[i - 1] = PageText(i, text, "baja", "ocr")
            except Exception as exc:
                log.warning("OCR falló en página %d de %s: %s", i, path.name, exc)
    finally:
        doc.close()
    return pages


def _ocr_all_pages(path: Path) -> list[PageText]:
    """OCR puro sobre el rasterizado, ignorando texto embebido. Útil para PDFs
    cuyo texto digital está corrupto (mojibake por fuentes custom mal mapeadas)."""
    log.info("Forzando OCR puro sobre %s (ignorando texto embebido).", path.name)
    out: list[PageText] = []
    doc = fitz.open(path)
    try:
        for i, page in enumerate(doc, start=1):
            try:
                pix = page.get_pixmap(dpi=200, alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = _sanitize(pytesseract.image_to_string(img, lang=settings.tesseract_lang).strip())
                out.append(PageText(i, text, "baja", "ocr"))
            except Exception as exc:
                log.warning("OCR falló en página %d de %s: %s", i, path.name, exc)
                out.append(PageText(i, "", "baja", "ocr"))
    finally:
        doc.close()
    return out


def extract_pdf(path: Path, force_ocr: bool = False) -> list[PageText]:
    """Extrae texto página por página con cascada de fallbacks.

    Si `force_ocr=True`, omite PyMuPDF/pdfplumber y va directo a OCR. Útil para PDFs
    con fuentes custom defectuosas que extraen texto "válido" en estructura pero
    ilegible semánticamente.

    Devuelve una entrada por página. Páginas verdaderamente vacías (sin texto ni imagen
    legible) quedan con text="" — el caller debería filtrarlas antes de chunkear.
    """
    log.info("Extrayendo %s%s", path.name, " (OCR forzado)" if force_ocr else "")
    if force_ocr:
        pages = _ocr_all_pages(path)
    else:
        pages = _extract_with_pymupdf(path)
        pages = _retry_with_pdfplumber(path, pages)
        pages = _retry_with_ocr(path, pages)

    extracted = sum(1 for p in pages if p.text)
    log.info(
        "Extracción terminada: %s — %d/%d páginas con texto",
        path.name, extracted, len(pages),
    )
    return pages


def join_pages(pages: Iterable[PageText]) -> str:
    """Texto completo concatenado con marcadores de página."""
    parts = []
    for p in pages:
        if p.text:
            parts.append(f"[[PAGE {p.page_number}]]\n{p.text}")
    return "\n\n".join(parts)
