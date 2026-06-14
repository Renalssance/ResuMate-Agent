import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PdfOcrResult:
    text: str
    page_count: int
    ocr_page_count: int
    source: str = "ocr"
    pages: list["OcrPageResult"] | None = None


@dataclass(frozen=True)
class OcrLine:
    text: str
    bbox: list | None = None
    confidence: float | None = None
    page_number: int = 0


@dataclass(frozen=True)
class OcrPageResult:
    page_number: int
    raw_text: str
    normalized_text: str
    lines: list[OcrLine]
    ambiguities: list[dict]


@dataclass(frozen=True)
class NormalizedOcrText:
    raw_text: str
    normalized_text: str
    ambiguities: list[dict]


SUSPICIOUS_OCR_PATTERNS = (
    re.compile(r"引I入"),
    re.compile(r"(?<![A-Za-z])Al(?![A-Za-z])"),
    re.compile(r"(?<=[A-Za-z])0(?=[A-Za-z])|(?<=[A-Za-z])O(?=\d)|(?<=\d)O(?=[A-Za-z])"),
)


def normalize_ocr_text(text: str) -> NormalizedOcrText:
    raw_text = text or ""
    lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    merged: list[str] = []
    for line in lines:
        clean = unicodedata.normalize("NFKC", line).strip()
        if not clean:
            if merged and merged[-1] != "":
                merged.append("")
            continue
        if (
            merged
            and len(merged[-1]) == 1
            and _is_cjk(merged[-1])
            and _is_cjk(clean[0])
        ):
            merged[-1] = f"{merged[-1]}{clean}"
        else:
            merged.append(clean)
    normalized = "\n".join(merged)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    ambiguities: list[dict] = []
    for pattern in SUSPICIOUS_OCR_PATTERNS:
        for match in pattern.finditer(normalized):
            ambiguities.append(
                {
                    "type": "ocr_suspicious_token",
                    "text": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    return NormalizedOcrText(
        raw_text=raw_text,
        normalized_text=normalized,
        ambiguities=ambiguities,
    )


def _is_cjk(value: str) -> bool:
    return bool(value) and "\u4e00" <= value[0] <= "\u9fff"


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


def _line_confidence(item) -> float | None:
    if not isinstance(item, (list, tuple)) or len(item) < 3:
        return None
    try:
        return float(item[2])
    except (TypeError, ValueError):
        return None


def _line_bbox(item) -> list | None:
    if not isinstance(item, (list, tuple)) or not item:
        return None
    bbox = item[0]
    return bbox if isinstance(bbox, list) else None


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
        page_results: list[OcrPageResult] = []
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

            line_items = [
                OcrLine(
                    text=_line_text(item),
                    bbox=_line_bbox(item),
                    confidence=_line_confidence(item),
                    page_number=page_index + 1,
                )
                for item in result or []
                if _line_text(item)
            ]
            page_text = "\n".join(line.text for line in line_items if line.text)
            if page_text:
                normalized = normalize_ocr_text(page_text)
                page_results.append(
                    OcrPageResult(
                        page_number=page_index + 1,
                        raw_text=normalized.raw_text,
                        normalized_text=normalized.normalized_text,
                        lines=line_items,
                        ambiguities=normalized.ambiguities,
                    )
                )
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
    return PdfOcrResult(
        text=text,
        page_count=page_count,
        ocr_page_count=len(page_texts),
        pages=page_results,
    )


def looks_like_scanned_pdf(extracted_text: str, *, min_chars: int | None = None) -> bool:
    """Treat a PDF as scanned/image-based when normal extraction returns too little text."""

    min_chars = min_chars or int(os.getenv("PDF_TEXT_MIN_CHARS", "30"))
    return len((extracted_text or "").strip()) < min_chars
