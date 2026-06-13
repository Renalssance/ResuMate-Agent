from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

import fitz
from fastapi import UploadFile
from docx import Document

from backend.services.pdf_ocr import extract_pdf_text_with_ocr


DOCUMENT_DIR = Path(__file__).resolve().parents[2] / "data" / "documents"
MAX_DOCUMENT_SIZE = int(os.getenv("MAX_DOCUMENT_SIZE", str(10 * 1024 * 1024)))
UPLOAD_CHUNK_SIZE = 64 * 1024
PDF_OCR_HARD_MAX_PAGES = int(os.getenv("PDF_OCR_HARD_MAX_PAGES", "100"))
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CLOCK$",
    "CONIN$",
    "CONOUT$",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
WINDOWS_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SUPERSCRIPT_DIGITS = str.maketrans(
    {"¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9"}
)


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class StoredDocument:
    filename: str
    path: Path
    size: int
    raw_text: str
    pages: list[PageText]


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    run_id: str
    candidate_id: str
    document_type: str
    filename: str
    page_number: int
    section: str
    chunk_index: int
    text: str
    metadata: dict


class UnsupportedDocumentError(ValueError):
    pass


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def _safe_filename(filename: str) -> str:
    safe_name = os.path.basename(filename.replace("\\", "/"))
    path = Path(safe_name)
    device_name = safe_name.split(".", 1)[0].translate(SUPERSCRIPT_DIGITS).upper()
    if (
        not safe_name
        or safe_name in {".", ".."}
        or safe_name.startswith(".")
        or safe_name.endswith((" ", "."))
        or path.stem.endswith((" ", "."))
        or WINDOWS_UNSAFE_RE.search(safe_name)
        or device_name in WINDOWS_RESERVED_NAMES
    ):
        raise UnsupportedDocumentError("Invalid document filename")
    if _extension(safe_name) not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentError(f"Unsupported file type: {safe_name}")
    return safe_name


def _open_exclusive_storage_file(directory: Path, filename: str):
    counter = 1
    candidate = directory / filename
    while True:
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_BINARY"):
                flags |= os.O_BINARY
            fd = os.open(candidate, flags, 0o600)
            return candidate, candidate.name, os.fdopen(fd, "wb")
        except FileExistsError:
            stored_name = f"{Path(filename).stem}_{counter}{Path(filename).suffix}"
            candidate = directory / stored_name
            counter += 1


async def _write_upload_chunks(file: UploadFile, stream, filename: str) -> int:
    total = 0
    read_size = min(UPLOAD_CHUNK_SIZE, MAX_DOCUMENT_SIZE + 1)
    while chunk := await file.read(read_size):
        total += len(chunk)
        if total > MAX_DOCUMENT_SIZE:
            raise UnsupportedDocumentError(
                f"{filename} exceeds maximum size of {MAX_DOCUMENT_SIZE} bytes"
            )
        stream.write(chunk)
    if not total:
        raise UnsupportedDocumentError(f"{filename} is empty")
    return total


async def store_and_extract_upload(
    file: UploadFile,
    storage_root: str | Path = DOCUMENT_DIR,
) -> StoredDocument:
    filename = _safe_filename(file.filename or "")
    directory = Path(storage_root)
    directory.mkdir(parents=True, exist_ok=True)
    path: Path | None = None
    try:
        path, stored_filename, stream = _open_exclusive_storage_file(directory, filename)
        with stream:
            size = await _write_upload_chunks(file, stream, stored_filename)
        pages = extract_stored_pages(path, stored_filename)
        raw_text = "\n".join(page.text for page in pages).strip()
        _ensure_text(raw_text, stored_filename)
        return StoredDocument(
            filename=stored_filename,
            path=path,
            size=size,
            raw_text=raw_text,
            pages=pages,
        )
    except Exception:
        _best_effort_delete(path)
        raise


def extract_stored_pages(path: str | Path, filename: str) -> list[PageText]:
    document_path = Path(path)
    safe_filename = _safe_filename(filename)
    ext = _extension(safe_filename)
    try:
        if ext == ".pdf":
            return _extract_pdf(document_path, safe_filename)
        if ext == ".docx":
            text = _extract_docx(document_path)
        elif ext == ".doc":
            return _extract_legacy_doc(document_path, safe_filename)
        else:
            text = document_path.read_text(encoding="utf-8", errors="ignore").strip()
    except UnsupportedDocumentError:
        raise
    except Exception as exc:
        raise UnsupportedDocumentError(f"Failed to extract text from {safe_filename}: {exc}") from exc

    _ensure_text(text, safe_filename)
    return [PageText(page_number=1, text=text)]


def delete_stored_file(path: str | Path | None) -> None:
    if not path:
        return
    Path(path).unlink(missing_ok=True)


def _best_effort_delete(path: str | Path | None) -> None:
    try:
        delete_stored_file(path)
    except OSError:
        pass


async def extract_upload_pages(file: UploadFile) -> list[PageText]:
    filename = _safe_filename(file.filename or "")
    ext = _extension(filename)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = Path(tmp.name)
            await _write_upload_chunks(file, tmp, filename)
        return extract_stored_pages(tmp_path, filename)
    finally:
        _best_effort_delete(tmp_path)


def _extract_pdf(path: Path, filename: str) -> list[PageText]:
    doc = fitz.open(path)
    native_pages: dict[int, str] = {}
    visual_pages: set[int] = set()
    page_count = 0
    try:
        for index, page in enumerate(doc, start=1):
            page_count = index
            native_pages[index] = (page.get_text("text") or "").strip()
            if page.get_images(full=True) or page.get_drawings():
                visual_pages.add(index)
    finally:
        doc.close()

    ocr_candidates = {
        page_number
        for page_number, text in native_pages.items()
        if _needs_page_ocr(text, has_visual_content=page_number in visual_pages)
    }
    if not ocr_candidates:
        pages = [PageText(page_number=number, text=text) for number, text in native_pages.items()]
        combined = "\n".join(page.text for page in pages)
        _ensure_text(combined, filename)
        return pages

    last_missing_page = max(ocr_candidates)
    if last_missing_page > PDF_OCR_HARD_MAX_PAGES:
        raise UnsupportedDocumentError(
            f"{filename} requires OCR through page {last_missing_page}, "
            f"which exceeds the hard limit of {PDF_OCR_HARD_MAX_PAGES} pages"
        )
    try:
        ocr_result = extract_pdf_text_with_ocr(path, max_pages=last_missing_page)
    except Exception as exc:
        raise UnsupportedDocumentError(f"{filename} OCR is unavailable or failed: {exc}") from exc
    ocr_pages = {page.page_number: page.text for page in _parse_ocr_pages(ocr_result.text)}
    required_ocr_pages = {
        page_number
        for page_number in ocr_candidates
        if not _has_usable_native_text(native_pages[page_number])
    }
    if not ocr_pages and len(required_ocr_pages) == page_count:
        raise UnsupportedDocumentError(f"{filename} OCR produced no extractable text")
    uncovered = sorted(page_number for page_number in required_ocr_pages if page_number not in ocr_pages)
    if uncovered:
        missing = ", ".join(str(page_number) for page_number in uncovered)
        raise UnsupportedDocumentError(f"{filename} OCR did not cover missing page {missing}")
    for page_number in required_ocr_pages:
        _ensure_text(ocr_pages[page_number], filename)

    pages = [
        PageText(
            page_number=page_number,
            text=_merge_page_text(native_pages[page_number], ocr_pages.get(page_number, ""))
            if page_number in ocr_candidates
            else native_pages[page_number],
        )
        for page_number in range(1, page_count + 1)
    ]
    _ensure_text("\n".join(page.text for page in pages), filename)
    return pages


def _needs_page_ocr(text: str, *, has_visual_content: bool) -> bool:
    stripped = (text or "").strip()
    min_chars = int(os.getenv("PDF_TEXT_MIN_CHARS", "30"))
    return has_visual_content and len(stripped) < min_chars


def _has_usable_native_text(text: str) -> bool:
    return bool(re.search(r"[\w\u4e00-\u9fff]", (text or "").strip()))


def _merge_page_text(native_text: str, ocr_text: str) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for line in [*native_text.splitlines(), *ocr_text.splitlines()]:
        clean_line = line.strip()
        normalized = re.sub(r"\s+", " ", clean_line).casefold()
        if clean_line and normalized not in seen:
            merged.append(clean_line)
            seen.add(normalized)
    return "\n".join(merged)


OCR_PAGE_RE = re.compile(
    r"^--- OCR Page (\d+) ---\s*\n(.*?)(?=^--- OCR Page \d+ ---|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _parse_ocr_pages(text: str) -> list[PageText]:
    return [
        PageText(page_number=int(match.group(1)), text=match.group(2).strip())
        for match in OCR_PAGE_RE.finditer(text or "")
        if match.group(2).strip()
    ]


def _extract_docx(path: Path) -> str:
    document = Document(str(path))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    table_lines: list[str] = []
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                table_lines.append(" | ".join(cells))
    return "\n".join([*paragraphs, *table_lines]).strip()


def partition_doc(*, filename: str):
    parser = import_module("unstructured.partition.doc").partition_doc
    return parser(filename=filename)


def _extract_legacy_doc(path: Path, filename: str) -> list[PageText]:
    try:
        elements = partition_doc(filename=str(path))
    except Exception as exc:
        raise UnsupportedDocumentError(
            f"Failed to extract legacy Word document {filename}; "
            f"the .doc parser or its external dependencies may be unavailable: {exc}"
        ) from exc

    text = "\n".join(str(element).strip() for element in elements if str(element).strip())
    _ensure_text(text, filename)
    return [PageText(page_number=1, text=text)]


def _ensure_text(text: str, filename: str) -> None:
    if len(text.strip()) < 20:
        raise UnsupportedDocumentError(f"{filename} has no extractable text")


SECTION_RE = re.compile(r"^\s*(#{1,6}\s*)?([\w\u4e00-\u9fff][^:\n：]{0,40})([:：])?\s*$")


def _section_for_line(line: str, current: str) -> str:
    stripped = line.strip()
    if not stripped:
        return current
    if len(stripped) <= 48 and SECTION_RE.match(stripped):
        return stripped.strip("# ：:")
    return current


def chunk_pages(
    *,
    pages: list[PageText],
    run_id: str,
    candidate_id: str,
    document_type: str,
    filename: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    chunk_index = 0
    for page in pages:
        section = "正文"
        paragraphs: list[tuple[str, str]] = []
        for line in page.text.splitlines():
            section = _section_for_line(line, section)
            text = line.strip()
            if text:
                paragraphs.append((section, text))
        if not paragraphs:
            paragraphs = [(section, page.text)]

        buffer = ""
        buffer_section = paragraphs[0][0]
        for para_section, paragraph in paragraphs:
            if len(buffer) + len(paragraph) + 1 <= chunk_size:
                buffer = f"{buffer}\n{paragraph}".strip()
                buffer_section = para_section or buffer_section
                continue
            chunk_index = _append_chunk(
                chunks,
                run_id,
                candidate_id,
                document_type,
                filename,
                page.page_number,
                buffer_section,
                chunk_index,
                buffer,
            )
            tail = buffer[-overlap:] if overlap > 0 else ""
            buffer = f"{tail}\n{paragraph}".strip()
            buffer_section = para_section or buffer_section
        if buffer:
            chunk_index = _append_chunk(
                chunks,
                run_id,
                candidate_id,
                document_type,
                filename,
                page.page_number,
                buffer_section,
                chunk_index,
                buffer,
            )
    return chunks


def _append_chunk(
    chunks: list[DocumentChunk],
    run_id: str,
    candidate_id: str,
    document_type: str,
    filename: str,
    page_number: int,
    section: str,
    chunk_index: int,
    text: str,
) -> int:
    clean_text = text.strip()
    if not clean_text:
        return chunk_index
    chunk_id = f"{run_id}:{candidate_id or 'jd'}:{document_type}:{chunk_index}"
    chunks.append(
        DocumentChunk(
            id=chunk_id,
            run_id=run_id,
            candidate_id=candidate_id,
            document_type=document_type,
            filename=filename,
            page_number=page_number,
            section=section or "正文",
            chunk_index=chunk_index,
            text=clean_text,
            metadata={"text_length": len(clean_text)},
        )
    )
    return chunk_index + 1
