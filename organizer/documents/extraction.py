"""Read what is inside uploaded documents: their text (for search and future AI) and their
number of pages.

Best effort: a broken, scanned or password-protected file simply gives no text and no
page count. Reading must never stop an upload, so every error is caught and logged here.

Page counts:
  - PDF:   exact (a PDF has fixed pages).
  - Word:  the number Word wrote into the file when it was last saved. A .docx has no
           fixed pages: they depend on fonts, margins and printer, and Word computes them
           while showing the document. Files made by other programs may have no number
           (→ unknown) or an outdated one.
  - Image: 1.
"""

import logging
import re
import zipfile
from dataclasses import dataclass
from typing import IO

import docx
from pypdf import PdfReader

from .file_types import DOCX_MIME_TYPE

logger = logging.getLogger(__name__)

# A safety limit: a 10 MB file can't produce a sensible amount of text beyond this.
MAX_TEXT_LENGTH = 1_000_000  # characters

# <Pages>4</Pages> in a Word file's docProps/app.xml. A tiny regular expression instead of
# an XML parser: we need one number, and parsing untrusted XML has its own risks.
WORD_PAGES = re.compile(rb"<(?:\w+:)?Pages>\s*(\d+)\s*</")


@dataclass(frozen=True)
class FileContents:
    text: str = ""
    page_count: int | None = None  # None = unknown


def read_contents(file: IO[bytes], mime_type: str) -> FileContents:
    """The file's text and number of pages, as far as they can be read."""
    file.seek(0)
    try:
        if mime_type == "application/pdf":
            contents = _read_pdf(file)
        elif mime_type == DOCX_MIME_TYPE:
            contents = _read_docx(file)
        elif mime_type.startswith("image/"):
            contents = FileContents(page_count=1)
        else:
            contents = FileContents()
    # Catching every Exception is usually a bad idea, but here it is the point: the files
    # come from outside, and parsers of complex formats can fail in many different ways.
    # logger.exception writes the error and its traceback to the log for debugging.
    except Exception:
        logger.exception("Could not read the contents of a %s file", mime_type)
        contents = FileContents()
    finally:
        file.seek(0)  # rewind, so the file can still be saved after this
    return FileContents(_clean(contents.text), contents.page_count)


def _read_pdf(file: IO[bytes]) -> FileContents:
    reader = PdfReader(file)
    # Many PDFs are "encrypted" with an empty password (only to stop editing or printing);
    # those can still be read. A PDF that needs a real password can't be opened at all.
    if reader.is_encrypted and not reader.decrypt(""):
        return FileContents()
    text = "\n\n".join(page.extract_text() for page in reader.pages)
    return FileContents(text, len(reader.pages))


def _read_docx(file: IO[bytes]) -> FileContents:
    document = docx.Document(file)
    parts = [paragraph.text for paragraph in document.paragraphs]
    # CVs often put skills or dates in tables; their text is not part of .paragraphs.
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells if cell.text))
    return FileContents("\n".join(parts), _word_page_count(file))


def _word_page_count(file: IO[bytes]) -> int | None:
    file.seek(0)
    with zipfile.ZipFile(file) as archive:
        try:
            metadata = archive.read("docProps/app.xml")
        except KeyError:  # no metadata file in this .docx
            return None
    match = WORD_PAGES.search(metadata)
    pages = int(match.group(1)) if match else 0
    return pages or None  # 0 is not a real page count either


def _clean(text: str) -> str:
    # NUL characters ("\x00") appear in some PDFs; PostgreSQL refuses them in text columns.
    text = text.replace("\x00", "")
    # Drop empty lines and spaces at the line ends: easier to read and to search.
    lines = (line.rstrip() for line in text.splitlines())
    return "\n".join(line for line in lines if line.strip())[:MAX_TEXT_LENGTH]
