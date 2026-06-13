from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import fitz
from fastapi import UploadFile
from docx import Document


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


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


async def extract_upload_pages(file: UploadFile) -> list[PageText]:
    filename = file.filename or "upload"
    ext = _extension(filename)
    payload = await file.read()
    if not payload:
        raise UnsupportedDocumentError(f"{filename} is empty")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)

    try:
        if ext == ".pdf":
            return _extract_pdf(tmp_path, filename)
        if ext in {".docx", ".doc"}:
            text = _extract_docx(tmp_path)
            _ensure_text(text, filename)
            return [PageText(page_number=1, text=text)]
        if ext in {".txt", ".md"}:
            text = payload.decode("utf-8", errors="ignore").strip()
            _ensure_text(text, filename)
            return [PageText(page_number=1, text=text)]
        raise UnsupportedDocumentError(f"Unsupported file type: {filename}")
    finally:
        tmp_path.unlink(missing_ok=True)


def _extract_pdf(path: Path, filename: str) -> list[PageText]:
    doc = fitz.open(path)
    pages: list[PageText] = []
    try:
        for index, page in enumerate(doc, start=1):
            text = (page.get_text("text") or "").strip()
            if text:
                pages.append(PageText(page_number=index, text=text))
    finally:
        doc.close()
    combined = "\n".join(page.text for page in pages)
    _ensure_text(combined, filename)
    return pages


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


def _ensure_text(text: str, filename: str) -> None:
    if len(text.strip()) < 20:
        raise UnsupportedDocumentError(f"{filename} has no extractable text; OCR is not supported")


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
