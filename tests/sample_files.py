"""Small but real test files (PDF, Word, images), built in memory.

No binary files are checked into the repository: each test builds exactly the file it
needs, and the test shows what is inside.
"""

import io
import re
import zipfile

import docx

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def make_pdf(*pages: str) -> bytes:
    """A valid PDF with one page per text, e.g. make_pdf("Page one", "Page two").

    A PDF is a list of numbered "objects" (catalog, pages, fonts, page contents) plus a
    table at the end (the "xref") that says at which byte each object starts.
    """
    page_count = len(pages)
    font = 3 + 2 * page_count  # object numbers: 1 catalog, 2 page list, then pages
    page_refs = " ".join(f"{3 + 2 * i} 0 R" for i in range(page_count))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{page_refs}] /Count {page_count} >>".encode(),
    ]
    for i, text in enumerate(pages):
        content = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n%s\nendobj\n" % (number, body))
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1))
    out.write(b"startxref\n%d\n%%%%EOF\n" % xref)
    return out.getvalue()


def make_docx(
    *paragraphs: str, table: list[list[str]] | None = None, pages: int | None = 1
) -> bytes:
    """A real Word file (made with python-docx) with these paragraphs and an optional table.

    pages: the page count written into the file's metadata (docProps/app.xml), as Word does
    when it saves. None removes that metadata file, as some other programs do.
    """
    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    if table:
        word_table = document.add_table(rows=len(table), cols=len(table[0]))
        for row, values in zip(word_table.rows, table, strict=True):
            for cell, value in zip(row.cells, values, strict=True):
                cell.text = value
    out = io.BytesIO()
    document.save(out)
    return _set_word_pages(out.getvalue(), pages)


def _set_word_pages(content: bytes, pages: int | None) -> bytes:
    """Copy the ZIP with another <Pages> value (or without docProps/app.xml).

    Removing the metadata file also removes the two places that point to it (the list of
    parts in [Content_Types].xml and the relationship in _rels/.rels); otherwise the file
    would be broken and python-docx would refuse to open it.
    """
    source = zipfile.ZipFile(io.BytesIO(content))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "docProps/app.xml":
                if pages is None:
                    continue
                data = re.sub(rb"<Pages>\d+</Pages>", b"<Pages>%d</Pages>" % pages, data)
            elif pages is None and item.filename in {"[Content_Types].xml", "_rels/.rels"}:
                # Drop the XML element that mentions docProps/app.xml.
                data = re.sub(rb"<[^<>]*docProps/app\.xml[^<>]*/>", b"", data)
            target.writestr(item, data)
    return out.getvalue()


def make_zip(*names: str) -> bytes:
    """A ZIP archive that contains (empty) files with these names."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, "<xml/>")
    return buffer.getvalue()
