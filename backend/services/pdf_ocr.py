import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PdfOcrResult:
    text: str
    page_count: int
    ocr_page_count: int
    source: str = "ocr"


_ocr_engine = None


def ocr_enabled() -> bool:
    return os.getenv("PDF_OCR_ENABLED", "true").lower() != "false"


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def _line_text(item) -> str:
    if not isinstance(item, (list, tuple)) or len(item) < 2:
        return ""
    return str(item[1] or "").strip()


def extract_pdf_text_with_ocr(
    file_path: str | Path,
    *,
    max_pages: int | None = None,
    render_scale: float | None = None,
) -> PdfOcrResult:
    """Render a PDF to page images and OCR the pages."""

    if not ocr_enabled():
        return PdfOcrResult(text="", page_count=0, ocr_page_count=0)

    import pypdfium2 as pdfium

    path = Path(file_path)
    max_pages = max_pages or int(os.getenv("PDF_OCR_MAX_PAGES", "8"))
    render_scale = render_scale or float(os.getenv("PDF_OCR_RENDER_SCALE", "2.5"))

    doc = pdfium.PdfDocument(str(path))
    try:
        page_count = len(doc)
        page_texts: list[str] = []
        engine = _get_ocr_engine()

        for page_index in range(min(page_count, max_pages)):
            page = doc[page_index]
            bitmap = page.render(scale=render_scale)
            try:
                image = bitmap.to_numpy()
                result, _ = engine(image)
            finally:
                bitmap.close()
                page.close()

            lines = [_line_text(item) for item in result or []]
            page_text = "\n".join(line for line in lines if line)
            if page_text:
                page_texts.append(f"--- OCR Page {page_index + 1} ---\n{page_text}")
    finally:
        doc.close()

    text = "\n\n".join(page_texts).strip()
    logger.info(
        "PDF OCR finished: file=%s pages=%s ocr_pages=%s chars=%s",
        path.name,
        page_count,
        len(page_texts),
        len(text),
    )
    return PdfOcrResult(text=text, page_count=page_count, ocr_page_count=len(page_texts))


def looks_like_scanned_pdf(extracted_text: str, *, min_chars: int | None = None) -> bool:
    """Treat a PDF as scanned/image-based when normal extraction returns too little text."""

    min_chars = min_chars or int(os.getenv("PDF_TEXT_MIN_CHARS", "30"))
    return len((extracted_text or "").strip()) < min_chars
