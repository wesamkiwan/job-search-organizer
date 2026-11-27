"""Pull plain text out of uploaded documents (PDF and Word), for search and future AI.

Best effort: a broken, scanned or password-protected file simply gives no text. Text
extraction must never stop an upload, so every error is caught and logged here.
Images (PNG, JPEG) give no text; reading text in images (OCR) would be a later feature.
"""

import logging
from typing import IO

import docx
from pypdf import PdfReader

from .file_types import DOCX_MIME_TYPE

logger = logging.getLogger(__name__)

# A safety limit: a 10 MB file can't produce a sensible amount of text beyond this.
MAX_TEXT_LENGTH = 1_000_000  # characters


def extract_text(file: IO[bytes], mime_type: str) -> str:
    """The file's text, or "" if there is none or it can't be read."""
    file.seek(0)
    try:
        if mime_type == "application/pdf":
            text = _pdf_text(file)
        elif mime_type == DOCX_MIME_TYPE:
            text = _docx_text(file)
        else:
            text = ""
    # Catching every Exception is usually a bad idea, but here it is the point: the files
    # come from outside, and parsers of complex formats can fail in many different ways.
    # logger.exception writes the error and its traceback to the log for debugging.
    except Exception:
        logger.exception("Could not extract text from a %s file", mime_type)
        text = ""
    finally:
        file.seek(0)  # rewind, so the file can still be saved after this
    return _clean(text)


def _pdf_text(file: IO[bytes]) -> str:
    reader = PdfReader(file)
    # Many PDFs are "encrypted" with an empty password (only to stop editing or printing);
    # those can still be read. A PDF that needs a real password gives no text.
    if reader.is_encrypted and not reader.decrypt(""):
        return ""
    return "\n\n".join(page.extract_text() for page in reader.pages)


def _docx_text(file: IO[bytes]) -> str:
    document = docx.Document(file)
    parts = [paragraph.text for paragraph in document.paragraphs]
    # CVs often put skills or dates in tables; their text is not part of .paragraphs.
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells if cell.text))
    return "\n".join(parts)


def _clean(text: str) -> str:
    # NUL characters ("\x00") appear in some PDFs; PostgreSQL refuses them in text columns.
    text = text.replace("\x00", "")
    # Drop empty lines and spaces at the line ends: easier to read and to search.
    lines = (line.rstrip() for line in text.splitlines())
    return "\n".join(line for line in lines if line.strip())[:MAX_TEXT_LENGTH]
