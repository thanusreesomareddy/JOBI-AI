from pathlib import Path

import fitz  # PyMuPDF


def extract_text_from_pdf(file_path: Path) -> str:
    """Extract plain text from a PDF resume."""
    doc = fitz.open(file_path)
    try:
        parts: list[str] = []
        for page in doc:
            parts.append(page.get_text())
        text = "\n".join(parts).strip()
    finally:
        doc.close()

    if not text:
        raise ValueError("No text extracted from PDF. Scanned images need OCR (Textract) — not implemented yet.")
    return text
