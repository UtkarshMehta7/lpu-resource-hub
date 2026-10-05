"""The upload rules, tested without a database or a request.

These are the rules every uploading feature shares, so they are a pure
function of the bytes. The point of most of these cases is that the NAME and
the declared type are not evidence: only the content is.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.modules.uploads import validation

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(64)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + bytes(64)
RAR4 = b"Rar!\x1a\x07\x00" + bytes(64)
RAR5 = b"Rar!\x1a\x07\x01\x00" + bytes(64)


def _zip_containing(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, "x")
    return buffer.getvalue()


def _docx() -> bytes:
    return _zip_containing("[Content_Types].xml", "word/document.xml")


# ------------------------------------------------------------------ detection


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (PDF, validation.PDF),
        (PNG, validation.PNG),
        (JPEG, validation.JPEG),
        (RAR4, validation.RAR),
        (RAR5, validation.RAR),
        (_docx(), validation.DOCX),
        (_zip_containing("notes.txt"), validation.ZIP),
    ],
)
def test_the_type_comes_from_the_bytes(data: bytes, expected: validation.FileKind) -> None:
    assert validation.detect(data) is expected


def test_a_docx_is_told_from_a_plain_zip_by_its_contents() -> None:
    """A .docx IS a zip, so the signature cannot separate them and the table
    of contents has to."""
    assert validation.detect(_docx()) is validation.DOCX
    assert validation.detect(_zip_containing("word/notes.txt")) is validation.ZIP


@pytest.mark.parametrize(
    "data",
    [
        b"MZ\x90\x00\x03",  # a Windows executable
        b"#!/bin/sh\nrm -rf /",  # a shell script
        b"<html><script>alert(1)</script>",  # the one that matters most
        b"\x7fELF\x02\x01\x01",  # a Linux binary
        b"plain text, which is not on the list",
    ],
)
def test_anything_not_on_the_list_is_refused(data: bytes) -> None:
    with pytest.raises(validation.UnsupportedFileTypeError):
        validation.detect(data)


def test_a_zip_that_will_not_open_is_not_a_docx() -> None:
    """Truncated after the signature: treated as a zip, never as a Word file,
    and certainly not crashed on."""
    assert validation.detect(b"PK\x03\x04" + bytes(8)) is validation.ZIP


# ----------------------------------------------------------------- size limits


def test_size_is_checked_before_type() -> None:
    with pytest.raises(validation.FileTooLargeError) as caught:
        validation.validate(PDF + bytes(2048), max_bytes=1024)
    assert caught.value.limit == 1024


def test_an_empty_file_is_refused() -> None:
    with pytest.raises(validation.EmptyFileError):
        validation.validate(b"", max_bytes=1024)


def test_a_file_exactly_at_the_limit_is_accepted() -> None:
    """The boundary, stated once so it cannot drift: the limit is inclusive."""
    data = PDF + bytes(1024 - len(PDF))
    assert validation.validate(data, max_bytes=1024) is validation.PDF


# -------------------------------------------------------------------- naming


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Soil survey 2026.pdf", "Soil survey 2026.pdf"),
        # A name is never a path.
        ("../../../etc/passwd", "passwd.pdf"),
        ("/absolute/report.pdf", "report.pdf"),
        ("C:\\Users\\me\\report.pdf", "report.pdf"),
        # Nothing that could be read as a quote or a header parameter
        # survives, so the name cannot break out of Content-Disposition.
        ('ev"il; filename=other.pdf', "ev_il_ filename_other.pdf"),
        # Nothing left to use.
        ("", "attachment.pdf"),
        ("...", "attachment.pdf"),
    ],
)
def test_a_filename_is_a_label_not_a_path(raw: str, expected: str) -> None:
    assert validation.safe_filename(raw, validation.PDF) == expected


def test_the_extension_follows_the_bytes_not_the_claim() -> None:
    """The case this exists for: an archive called report.pdf is stored,
    served and labelled as an archive. Handing a browser a file under the
    extension it is not is how an upload becomes something else."""
    assert validation.safe_filename("report.pdf", validation.RAR) == "report.rar"


def test_a_very_long_name_is_truncated_but_keeps_its_extension() -> None:
    stored = validation.safe_filename("a" * 500 + ".pdf", validation.PDF)
    assert stored.endswith(".pdf")
    assert len(stored) <= validation.MAX_FILENAME_LENGTH + len(".pdf")
