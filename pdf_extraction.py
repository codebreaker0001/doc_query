import os
import shutil
from io import BytesIO

import pytesseract
import pypdfium2 as pdfium
from pypdf import PdfReader

# Linux (Docker/Render) puts tesseract on PATH automatically; Windows dev
# machines usually don't, so TESSERACT_CMD is an escape hatch for those.
tesseract_cmd = os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def extract_pages_from_pdf(file_bytes: bytes) -> list[str]:
    reader = PdfReader(BytesIO(file_bytes))
    rendered_doc = pdfium.PdfDocument(file_bytes)

    pages = []
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if not text.strip():
            image = rendered_doc[index].render(scale=2).to_pil()
            text = pytesseract.image_to_string(image)
        pages.append(text.replace("\x00", ""))
    return pages
