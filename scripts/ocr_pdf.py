import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.pdf_ocr import extract_pdf_text_with_ocr


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR a scanned/image-based PDF and print extracted text.")
    parser.add_argument("pdf", help="Path to the PDF file.")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum pages to OCR.")
    parser.add_argument("--scale", type=float, default=None, help="PDF render scale. Higher is slower but can improve OCR.")
    parser.add_argument("--output", default="", help="Optional output .txt path.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        raise SystemExit(f"PDF not found: {pdf_path}")

    result = extract_pdf_text_with_ocr(pdf_path, max_pages=args.max_pages, render_scale=args.scale)
    print(f"[ok] pages={result.page_count}, ocr_pages={result.ocr_page_count}, chars={len(result.text)}")

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.text, encoding="utf-8")
        print(f"[ok] wrote {output_path}")
    else:
        print(result.text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
