"""Shared test helpers."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import respx


def _empty_zip_bytes() -> bytes:
    """Return structurally valid ZIP bytes with zero members."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w"):
        pass
    return buffer.getvalue()


EMPTY_ZIP_BYTES = _empty_zip_bytes()


def assert_files(folder: Path, files: set[str] | list[str]) -> None:
    """Assert the folder contains exactly the given filenames."""
    __tracebackhide__ = True
    actual = {path.name for path in folder.iterdir()}
    if actual != set(files):
        raise AssertionError(f"""
        Unexpected file contents in folder {folder}:
        expected {files}
        got {actual}
        """)


def mock_http_requests(
    url: re.Pattern[str] = re.compile(".*"),
    status_code: int = 200,
    content: bytes = b"",
    **kwargs,
) -> None:
    """Mock matching GET requests with one response."""
    respx.get(url).respond(status_code, content=content, **kwargs)
