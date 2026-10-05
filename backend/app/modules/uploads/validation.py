"""What may be uploaded, decided from the bytes and not from the name.

The filename and the Content-Type a browser sends are both chosen by whoever
is uploading, so neither decides anything here. The type comes from the
file's own magic bytes, and the name survives only as a label, after being
stripped of everything that could make it a path.

A file that passes is *stored*, and nothing more. Nothing here decodes an
image, renders a PDF or extracts an archive: decoding untrusted input is the
attack surface this module avoids rather than tries to guard. The one
exception is reading a zip's table of contents, which is how a .docx is told
from any other zip, and even that never touches an entry's data -- so a
bomb has nothing to expand into.

The stored content type is always the sniffed one. A RAR named "report.pdf"
is stored, served and labelled as a RAR, because the alternative is handing
a browser a file it will treat as something it is not.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

#: Long enough for a real paper's filename, short enough to render in a
#: message bubble without pushing the layout around.
MAX_FILENAME_LENGTH = 120


@dataclass(frozen=True, slots=True)
class FileKind:
    """One accepted type: what to call it, what to serve it as, what to
    store it as."""

    label: str
    content_type: str
    extension: str


PDF = FileKind("PDF", "application/pdf", ".pdf")
PNG = FileKind("PNG image", "image/png", ".png")
JPEG = FileKind("JPEG image", "image/jpeg", ".jpg")
DOCX = FileKind(
    "Word document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".docx",
)
RAR = FileKind("RAR archive", "application/vnd.rar", ".rar")
ZIP = FileKind("ZIP archive", "application/zip", ".zip")

#: ZIP rides alongside RAR deliberately. RAR is proprietary, and a recipient
#: on macOS, iOS or Android generally cannot open one without installing
#: something first -- so refusing the format everybody *can* open while
#: accepting the one they cannot would be a strange place to land.
ALLOWED: tuple[FileKind, ...] = (PDF, DOCX, PNG, JPEG, RAR, ZIP)

ALLOWED_LABELS = ", ".join(kind.label for kind in ALLOWED)

_PDF_SIGNATURE = b"%PDF-"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8\xff"
#: Local file header, empty archive, and spanned archive respectively. A
#: .docx written by Word is the first; the others are still zips.
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
#: RAR 4 and RAR 5 differ in the last byte of the signature.
_RAR_SIGNATURES = (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")

#: Everything a filename may keep. Anything else becomes an underscore --
#: slashes, control characters, quotes and the rest -- so the label can never
#: be read as a path or smuggled into a header.
_UNSAFE_IN_NAME = re.compile(r"[^A-Za-z0-9 ._()\[\]-]")


class EmptyFileError(Exception):
    """Nothing was uploaded, or the file has no bytes."""


class FileTooLargeError(Exception):
    """Bigger than the configured cap."""

    def __init__(self, byte_size: int, limit: int) -> None:
        super().__init__(f"{byte_size} bytes exceeds the {limit} byte limit")
        self.byte_size = byte_size
        self.limit = limit


class UnsupportedFileTypeError(Exception):
    """The bytes are not one of ALLOWED, whatever the name claimed."""


def _looks_like_docx(data: bytes) -> bool:
    """A .docx IS a zip, so the container proves nothing and the contents do.

    Only the central directory is read, never an entry's data.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
    except (zipfile.BadZipFile, OSError, ValueError):
        return False
    return "word/document.xml" in names


def detect(data: bytes) -> FileKind:
    """The kind these bytes actually are, or UnsupportedFileTypeError."""
    if data.startswith(_PDF_SIGNATURE):
        return PDF
    if data.startswith(_PNG_SIGNATURE):
        return PNG
    if data.startswith(_JPEG_SIGNATURE):
        return JPEG
    if data.startswith(_RAR_SIGNATURES):
        return RAR
    if data.startswith(_ZIP_SIGNATURES):
        return DOCX if _looks_like_docx(data) else ZIP
    raise UnsupportedFileTypeError


def validate(data: bytes, *, max_bytes: int) -> FileKind:
    """The single entry point: size first, then type.

    Size is checked against the bytes in hand rather than a declared length,
    because the declaration is the part a client controls.
    """
    if not data:
        raise EmptyFileError
    if len(data) > max_bytes:
        raise FileTooLargeError(len(data), max_bytes)
    return detect(data)


def safe_filename(raw: str | None, kind: FileKind) -> str:
    """A label, never a path.

    Keeps the base name only, replaces anything that is not plainly part of a
    name, and always ends with the extension the BYTES earned rather than the
    one the name claimed.
    """
    base = PurePosixPath((raw or "").replace("\\", "/")).name
    cleaned = _UNSAFE_IN_NAME.sub("_", base).strip(" .")
    stem = PurePosixPath(cleaned).stem[:MAX_FILENAME_LENGTH].strip(" ._") or "attachment"
    return f"{stem}{kind.extension}"


__all__ = [
    "ALLOWED",
    "ALLOWED_LABELS",
    "DOCX",
    "JPEG",
    "PDF",
    "PNG",
    "RAR",
    "ZIP",
    "EmptyFileError",
    "FileKind",
    "FileTooLargeError",
    "UnsupportedFileTypeError",
    "detect",
    "safe_filename",
    "validate",
]
