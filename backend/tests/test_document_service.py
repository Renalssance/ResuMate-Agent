from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import fitz
import pytest
from fastapi import UploadFile
from docx import Document

from backend.services import documents
from backend.services.documents import (
    PageText,
    UnsupportedDocumentError,
    delete_stored_file,
    extract_stored_pages,
    store_upload,
    store_and_extract_upload,
)
from backend.services.pdf_ocr import PdfOcrResult


def _upload(filename: str, payload: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(payload))


def _pdf_bytes(text: str = "", *additional_pages: str) -> bytes:
    doc = fitz.open()
    for page_text in (text, *additional_pages):
        page = doc.new_page()
        if page_text:
            page.insert_text((72, 72), page_text)
    payload = doc.tobytes()
    doc.close()
    return payload


def _pdf_bytes_with_image_pages(page_texts: list[str], image_pages: set[int]) -> bytes:
    doc = fitz.open()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2, 2), False)
    pixmap.clear_with(255)
    image = pixmap.tobytes("png")
    for page_number, page_text in enumerate(page_texts, start=1):
        page = doc.new_page()
        if page_text:
            page.insert_text((72, 72), page_text)
        if page_number in image_pages:
            page.insert_image(fitz.Rect(72, 100, 144, 172), stream=image)
    payload = doc.tobytes()
    doc.close()
    return payload


def _pdf_bytes_with_drawing(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    page.draw_rect(fitz.Rect(72, 100, 144, 172), color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
    payload = doc.tobytes()
    doc.close()
    return payload


def _docx_bytes(text: str) -> bytes:
    stream = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(stream)
    return stream.getvalue()


@pytest.mark.asyncio
async def test_store_and_extract_upload_persists_real_upload_bytes(tmp_path: Path) -> None:
    payload = b"Real candidate experience from the uploaded file."

    stored = await store_and_extract_upload(_upload("resume.txt", payload), storage_root=tmp_path)

    assert stored.filename == "resume.txt"
    assert stored.path.read_bytes() == payload
    assert stored.size == len(payload)
    assert stored.raw_text == payload.decode()
    assert stored.pages == [PageText(page_number=1, text=payload.decode())]


@pytest.mark.asyncio
async def test_store_upload_persists_bytes_without_extracting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents, "extract_stored_pages", Mock(side_effect=AssertionError("must not extract")))
    payload = b"Real candidate experience from the uploaded file."

    stored = await store_upload(_upload("resume.txt", payload), storage_root=tmp_path)

    assert stored.filename == "resume.txt"
    assert stored.path.read_bytes() == payload
    assert stored.size == len(payload)


def test_extract_stored_pages_reports_real_pdf_page_progress(tmp_path: Path) -> None:
    path = tmp_path / "resume.pdf"
    path.write_bytes(
        _pdf_bytes(
            "Candidate experience from page one with enough text.",
            "Candidate project history from page two with enough text.",
        )
    )
    events: list[tuple[int, int]] = []

    pages = extract_stored_pages(
        path,
        "resume.pdf",
        progress_callback=lambda current, total: events.append((current, total)),
    )

    assert [page.page_number for page in pages] == [1, 2]
    assert events == [(1, 2), (2, 2)]


@pytest.mark.asyncio
async def test_store_and_extract_upload_deduplicates_same_filename(tmp_path: Path) -> None:
    first = await store_and_extract_upload(_upload("resume.txt", b"First uploaded resume content."), storage_root=tmp_path)
    second = await store_and_extract_upload(_upload("resume.txt", b"Second uploaded resume content."), storage_root=tmp_path)

    assert first.filename == "resume.txt"
    assert second.filename == "resume_1.txt"
    assert first.path != second.path
    assert first.path.read_bytes() == b"First uploaded resume content."
    assert second.path.read_bytes() == b"Second uploaded resume content."


@pytest.mark.asyncio
async def test_store_and_extract_upload_uses_exclusive_creation_during_name_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    competing = tmp_path / "resume.txt"
    competing.write_bytes(b"Competing request candidate resume content.")
    original_open = documents.os.open
    attempts: list[Path] = []

    def racing_open(path, flags, mode=0o777):
        attempts.append(Path(path))
        if len(attempts) == 1:
            raise FileExistsError
        return original_open(path, flags, mode)

    monkeypatch.setattr(documents.os, "open", racing_open)

    stored = await store_and_extract_upload(
        _upload("resume.txt", b"New request candidate resume content."),
        tmp_path,
    )

    assert attempts == [tmp_path / "resume.txt", tmp_path / "resume_1.txt"]
    assert competing.read_bytes() == b"Competing request candidate resume content."
    assert stored.filename == "resume_1.txt"
    assert stored.path.read_bytes() == b"New request candidate resume content."


@pytest.mark.asyncio
async def test_failed_upload_does_not_delete_file_owned_by_competing_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = tmp_path / "resume.txt"
    existing.write_bytes(b"Existing request candidate resume content.")
    monkeypatch.setattr(documents, "extract_stored_pages", Mock(side_effect=UnsupportedDocumentError("parse failed")))

    with pytest.raises(UnsupportedDocumentError, match="parse failed"):
        await store_and_extract_upload(_upload("resume.txt", b"Failing request candidate resume content."), tmp_path)

    assert existing.read_bytes() == b"Existing request candidate resume content."
    assert not (tmp_path / "resume_1.txt").exists()


class ChunkedUpload:
    def __init__(self, filename: str, payload: bytes) -> None:
        self.filename = filename
        self._stream = BytesIO(payload)
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self._stream.read(size)


@pytest.mark.asyncio
async def test_store_and_extract_upload_reads_in_bounded_chunks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents, "MAX_DOCUMENT_SIZE", documents.UPLOAD_CHUNK_SIZE * 3)
    upload = ChunkedUpload(
        "resume.txt",
        b"Candidate resume content. " * (documents.UPLOAD_CHUNK_SIZE // 20 + 10),
    )

    stored = await store_and_extract_upload(upload, tmp_path)

    assert stored.raw_text.startswith("Candidate resume content.")
    assert upload.read_sizes
    assert len(upload.read_sizes) >= 3
    assert all(0 < size <= documents.UPLOAD_CHUNK_SIZE for size in upload.read_sizes)


@pytest.mark.asyncio
async def test_store_and_extract_upload_rejects_oversized_file_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(documents, "MAX_DOCUMENT_SIZE", 32)
    upload = ChunkedUpload("resume.txt", b"x" * 33)

    with pytest.raises(UnsupportedDocumentError, match="exceeds maximum size"):
        await store_and_extract_upload(upload, tmp_path)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_extract_upload_pages_rejects_oversized_temporary_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents, "MAX_DOCUMENT_SIZE", 32)
    upload = ChunkedUpload("resume.txt", b"x" * 33)

    with pytest.raises(UnsupportedDocumentError, match="exceeds maximum size"):
        await documents.extract_upload_pages(upload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename",
    [
        "",
        ".",
        "..",
        "candidate:secret.txt",
        "CON.txt",
        "con.report.txt",
        "CLOCK$.txt",
        "conin$.md",
        "CONOUT$.txt",
        "com1.resume.txt",
        "LPT9.md",
        "COM¹.txt",
        "COM⁴.txt",
        "lpt².resume.md",
        "lpt⁹.resume.md",
        "com³.txt",
        "resume?.txt",
        "resume .txt",
    ],
)
async def test_store_and_extract_upload_rejects_dangerous_filenames(tmp_path: Path, filename: str) -> None:
    with pytest.raises(UnsupportedDocumentError, match="Invalid document filename"):
        await store_and_extract_upload(_upload(filename, b"Candidate experience text that is long enough."), tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_extract_stored_pages_uses_ocr_fallback_and_preserves_page_numbers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(
        _pdf_bytes_with_image_pages(
            [
                "Native candidate text on page one.",
                "",
                "Native candidate text on page three.",
                "Native candidate text on page four.",
                "",
            ],
            {2, 5},
        )
    )
    monkeypatch.setattr(
        documents,
        "extract_pdf_text_with_ocr",
        lambda _path, **_kwargs: PdfOcrResult(
            text=(
                "--- OCR Page 2 ---\nSecond page candidate experience text\n\n"
                "--- OCR Page 5 ---\nFifth page candidate project text"
            ),
            page_count=5,
            ocr_page_count=2,
        ),
    )

    pages = extract_stored_pages(path, "scan.pdf")

    assert pages == [
        PageText(page_number=1, text="Native candidate text on page one."),
        PageText(page_number=2, text="Second page candidate experience text"),
        PageText(page_number=3, text="Native candidate text on page three."),
        PageText(page_number=4, text="Native candidate text on page four."),
        PageText(page_number=5, text="Fifth page candidate project text"),
    ]


def test_extract_stored_pages_rejects_ocr_text_below_valid_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(_pdf_bytes_with_image_pages([""], {1}))
    monkeypatch.setattr(
        documents,
        "extract_pdf_text_with_ocr",
        lambda _path, **_kwargs: PdfOcrResult(text="--- OCR Page 1 ---\nshort", page_count=1, ocr_page_count=1),
    )

    with pytest.raises(UnsupportedDocumentError, match="no extractable text"):
        extract_stored_pages(path, "scan.pdf")


def test_extract_stored_pages_does_not_run_ocr_for_text_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "text.pdf"
    path.write_bytes(_pdf_bytes("This PDF contains enough directly extractable candidate experience text."))

    def fail_if_called(_path: Path) -> PdfOcrResult:
        raise AssertionError("OCR must not run for a text PDF")

    monkeypatch.setattr(documents, "extract_pdf_text_with_ocr", fail_if_called)

    pages = extract_stored_pages(path, "text.pdf")

    assert len(pages) == 1
    assert "directly extractable candidate experience" in pages[0].text


def test_extract_stored_pages_preserves_short_text_page_without_ocr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "short-page.pdf"
    path.write_bytes(
        _pdf_bytes(
            "Contact",
            "This is a sufficiently long candidate experience page with detailed project history.",
        )
    )

    def fail_if_called(*args, **kwargs) -> PdfOcrResult:
        raise AssertionError("OCR must not run for a valid short native text page")

    monkeypatch.setattr(documents, "extract_pdf_text_with_ocr", fail_if_called)

    pages = extract_stored_pages(path, "short-page.pdf")

    assert pages[0] == PageText(page_number=1, text="Contact")
    assert "detailed project history" in pages[1].text


def test_extract_stored_pages_allows_blank_page_with_valid_body_without_ocr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "blank-page.pdf"
    path.write_bytes(_pdf_bytes("", "This is valid candidate experience body text after a blank cover page."))

    def fail_if_called(*args, **kwargs) -> PdfOcrResult:
        raise AssertionError("OCR must not run for a truly blank page")

    monkeypatch.setattr(documents, "extract_pdf_text_with_ocr", fail_if_called)

    pages = extract_stored_pages(path, "blank-page.pdf")

    assert pages == [
        PageText(page_number=1, text=""),
        PageText(page_number=2, text="This is valid candidate experience body text after a blank cover page."),
    ]


def test_extract_stored_pages_runs_ocr_for_image_page_without_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "image-page.pdf"
    path.write_bytes(
        _pdf_bytes_with_image_pages(
            ["Native candidate experience body text.", ""],
            {2},
        )
    )
    calls: list[int | None] = []

    def image_page_ocr(_path: Path, *, max_pages: int | None = None) -> PdfOcrResult:
        calls.append(max_pages)
        return PdfOcrResult(
            text="--- OCR Page 2 ---\nScanned candidate experience from image page.",
            page_count=2,
            ocr_page_count=1,
        )

    monkeypatch.setattr(documents, "extract_pdf_text_with_ocr", image_page_ocr)

    pages = extract_stored_pages(path, "image-page.pdf")

    assert calls == [2]
    assert pages[1] == PageText(page_number=2, text="Scanned candidate experience from image page.")


def test_extract_stored_pages_merges_low_native_text_with_ocr_on_visual_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "visual-short-text.pdf"
    path.write_bytes(
        _pdf_bytes_with_image_pages(
            ["Email: a@b.co", "Native candidate experience body text on page two."],
            {1},
        )
    )
    calls: list[int | None] = []

    def visual_page_ocr(_path: Path, *, max_pages: int | None = None) -> PdfOcrResult:
        calls.append(max_pages)
        return PdfOcrResult(
            text="--- OCR Page 1 ---\nEmail: a@b.co\nPhone: 123456789",
            page_count=2,
            ocr_page_count=1,
        )

    monkeypatch.setattr(documents, "extract_pdf_text_with_ocr", visual_page_ocr)

    pages = extract_stored_pages(path, "visual-short-text.pdf")

    assert calls == [1]
    assert pages[0].text.count("Email: a@b.co") == 1
    assert "Phone: 123456789" in pages[0].text


def test_extract_stored_pages_keeps_valid_short_native_text_when_visual_page_ocr_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "logo-short-text.pdf"
    path.write_bytes(
        _pdf_bytes_with_image_pages(
            ["Contact", "Native candidate experience body text on page two."],
            {1},
        )
    )
    calls: list[int | None] = []

    def empty_logo_ocr(_path: Path, *, max_pages: int | None = None) -> PdfOcrResult:
        calls.append(max_pages)
        return PdfOcrResult(text="", page_count=2, ocr_page_count=0)

    monkeypatch.setattr(documents, "extract_pdf_text_with_ocr", empty_logo_ocr)

    pages = extract_stored_pages(path, "logo-short-text.pdf")

    assert calls == [1]
    assert pages[0] == PageText(page_number=1, text="Contact")


def test_extract_stored_pages_treats_drawing_as_visual_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "drawing-page.pdf"
    path.write_bytes(_pdf_bytes_with_drawing("Contact"))
    calls: list[int | None] = []

    def drawing_page_ocr(_path: Path, *, max_pages: int | None = None) -> PdfOcrResult:
        calls.append(max_pages)
        return PdfOcrResult(text="--- OCR Page 1 ---\nPhone: 123456789", page_count=1, ocr_page_count=1)

    monkeypatch.setattr(documents, "extract_pdf_text_with_ocr", drawing_page_ocr)

    pages = extract_stored_pages(path, "drawing-page.pdf")

    assert calls == [1]
    assert "Contact" in pages[0].text
    assert "Phone: 123456789" in pages[0].text


def test_extract_stored_pages_merges_native_and_ocr_text_for_mixed_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mixed.pdf"
    path.write_bytes(
        _pdf_bytes_with_image_pages(["Native candidate experience text on page one.", ""], {2})
    )
    monkeypatch.setattr(
        documents,
        "extract_pdf_text_with_ocr",
        lambda _path, **_kwargs: PdfOcrResult(
            text="--- OCR Page 2 ---\nScanned candidate project text on page two.",
            page_count=2,
            ocr_page_count=1,
        ),
    )

    pages = extract_stored_pages(path, "mixed.pdf")

    assert pages == [
        PageText(page_number=1, text="Native candidate experience text on page one."),
        PageText(page_number=2, text="Scanned candidate project text on page two."),
    ]


def test_extract_stored_pages_rejects_too_short_ocr_for_required_image_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mixed-short-ocr.pdf"
    path.write_bytes(
        _pdf_bytes_with_image_pages(
            ["Native candidate experience text on page one.", ""],
            {2},
        )
    )
    monkeypatch.setattr(
        documents,
        "extract_pdf_text_with_ocr",
        lambda _path, **_kwargs: PdfOcrResult(
            text="--- OCR Page 2 ---\nshort",
            page_count=2,
            ocr_page_count=1,
        ),
    )

    with pytest.raises(UnsupportedDocumentError, match="no extractable text"):
        extract_stored_pages(path, "mixed-short-ocr.pdf")


def test_extract_stored_pages_fails_when_ocr_does_not_cover_missing_pdf_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mixed.pdf"
    path.write_bytes(
        _pdf_bytes_with_image_pages(["Native candidate experience text on page one.", ""], {2})
    )
    monkeypatch.setattr(
        documents,
        "extract_pdf_text_with_ocr",
        lambda _path, **_kwargs: PdfOcrResult(text="", page_count=2, ocr_page_count=0),
    )

    with pytest.raises(UnsupportedDocumentError, match="missing page 2"):
        extract_stored_pages(path, "mixed.pdf")


def test_extract_stored_pages_requests_ocr_through_late_missing_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "late-scan.pdf"
    native_pages = [f"Native candidate experience content for page {number}." for number in range(1, 10)]
    path.write_bytes(_pdf_bytes_with_image_pages([*native_pages, ""], {10}))
    calls: list[int | None] = []

    def late_page_ocr(_path: Path, *, max_pages: int | None = None) -> PdfOcrResult:
        calls.append(max_pages)
        return PdfOcrResult(
            text="--- OCR Page 10 ---\nScanned candidate experience content on page ten.",
            page_count=10,
            ocr_page_count=1,
        )

    monkeypatch.setattr(documents, "extract_pdf_text_with_ocr", late_page_ocr)

    pages = extract_stored_pages(path, "late-scan.pdf")

    assert calls == [10]
    assert pages[-1] == PageText(page_number=10, text="Scanned candidate experience content on page ten.")


def test_extract_stored_pages_rejects_ocr_beyond_hard_page_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "too-long.pdf"
    path.write_bytes(_pdf_bytes_with_image_pages(["Native candidate experience content.", ""], {2}))
    monkeypatch.setattr(documents, "PDF_OCR_HARD_MAX_PAGES", 1)

    with pytest.raises(UnsupportedDocumentError, match=r"^too-long\.pdf requires OCR.*exceeds the hard limit"):
        extract_stored_pages(path, "too-long.pdf")


@pytest.mark.parametrize(
    ("filename", "payload", "expected"),
    [
        ("resume.txt", b"Candidate text content for txt parsing.", "Candidate text content"),
        ("resume.md", b"# Candidate\nMarkdown resume experience.", "Markdown resume experience"),
        ("resume.docx", _docx_bytes("Candidate experience from a real docx file."), "real docx file"),
        (
            "resume.pdf",
            _pdf_bytes("Candidate experience from a real text PDF document."),
            "real text PDF document",
        ),
    ],
    ids=["txt", "md", "docx", "pdf"],
)
def test_extract_stored_pages_supports_lightweight_real_format_branches(
    tmp_path: Path, filename: str, payload: bytes, expected: str
) -> None:
    path = tmp_path / filename
    path.write_bytes(payload)

    pages = extract_stored_pages(path, filename)

    assert expected in "\n".join(page.text for page in pages)


def test_extract_stored_pages_uses_partition_doc_for_legacy_doc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "resume.doc"
    path.write_bytes(b"legacy word bytes")
    calls: list[str] = []

    class Element:
        def __init__(self, text: str) -> None:
            self.text = text

        def __str__(self) -> str:
            return self.text

    def stub_partition_doc(*, filename: str) -> list[Element]:
        calls.append(filename)
        return [
            Element("Legacy Word candidate experience content."),
            Element("Additional legacy Word project details."),
        ]

    monkeypatch.setattr(documents, "partition_doc", stub_partition_doc)

    pages = extract_stored_pages(path, "resume.doc")

    assert calls == [str(path)]
    assert pages == [
        PageText(
            page_number=1,
            text="Legacy Word candidate experience content.\nAdditional legacy Word project details.",
        ),
    ]


def test_extract_stored_pages_reports_unsupported_legacy_doc_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "resume.doc"
    path.write_bytes(b"legacy word bytes")

    def failing_partition_doc(*, filename: str) -> list:
        raise RuntimeError("LibreOffice is not installed")

    monkeypatch.setattr(documents, "partition_doc", failing_partition_doc)

    with pytest.raises(UnsupportedDocumentError, match="LibreOffice is not installed"):
        extract_stored_pages(path, "resume.doc")


def test_extract_stored_pages_reports_missing_legacy_doc_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "resume.doc"
    path.write_bytes(b"legacy word bytes")

    def missing_parser(_module: str):
        raise ModuleNotFoundError("unstructured.partition.doc is unavailable")

    monkeypatch.setattr(documents, "import_module", missing_parser)

    with pytest.raises(UnsupportedDocumentError, match="unstructured.partition.doc is unavailable"):
        extract_stored_pages(path, "resume.doc")


@pytest.mark.asyncio
async def test_store_and_extract_upload_removes_file_when_extraction_fails(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedDocumentError, match="no extractable text"):
        await store_and_extract_upload(_upload("empty.txt", b"   \n"), storage_root=tmp_path)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_replace_original_extraction_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(documents, "extract_stored_pages", Mock(side_effect=UnsupportedDocumentError("original parse error")))
    monkeypatch.setattr(documents.Path, "unlink", Mock(side_effect=OSError("cleanup failed")))

    with pytest.raises(UnsupportedDocumentError, match="original parse error"):
        await store_and_extract_upload(_upload("resume.txt", b"Candidate content that fails during parsing."), tmp_path)


def test_extract_stored_pages_fails_clearly_when_ocr_has_no_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(_pdf_bytes_with_image_pages([""], {1}))
    monkeypatch.setattr(
        documents,
        "extract_pdf_text_with_ocr",
        lambda _path, **_kwargs: PdfOcrResult(text="", page_count=1, ocr_page_count=0),
    )

    with pytest.raises(UnsupportedDocumentError, match="OCR produced no extractable text"):
        extract_stored_pages(path, "scan.pdf")


def test_delete_stored_file_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "resume.txt"
    path.write_text("candidate data")

    delete_stored_file(path)
    delete_stored_file(path)
    delete_stored_file("")
    delete_stored_file(None)

    assert not path.exists()
