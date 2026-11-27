"""The file formats that can be uploaded as documents (used by services and extraction)."""

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# Allowed file extensions and the MIME type each one stands for. A MIME type is the
# standard name of a file format ("application/pdf"); browsers use it to decide what to
# do with a download.
ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".docx": DOCX_MIME_TYPE,
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

# "Magic bytes": the first bytes of a file tell its real format, whatever its name says.
# Renaming virus.exe to cv.pdf does not change its first bytes.
MAGIC_BYTES = {
    "application/pdf": b"%PDF-",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    DOCX_MIME_TYPE: b"PK\x03\x04",  # a .docx is a ZIP archive (check_upload looks inside it)
}
