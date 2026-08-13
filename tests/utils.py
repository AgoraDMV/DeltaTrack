"""Shared test helpers."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import respx

# Validation


def assert_files(folder: Path, files: set[str] | list[str]) -> None:
    """Assert the folder contains exactly the given filenames."""
    __tracebackhide__ = True
    actual = {path.name for path in folder.iterdir()}
    expected = set(files)
    if actual != expected:
        extra = actual - expected
        missing = expected - actual
        raise AssertionError(
            "\n".join(
                filter(
                    None,
                    [
                        f"Unexpected file contents in folder {folder}:",
                        f"expected: {expected}",
                        f"actual: {actual}",
                        f"extra: {extra}" if extra else None,
                        f"missing: {missing}" if missing else None,
                    ],
                )
            )
        )


# HTTP Mocking
def mock_http_requests(
    url: re.Pattern[str] = re.compile(".*"),
    status_code: int = 200,
    content: bytes = b"",
    **kwargs,
) -> None:
    """Mock matching GET requests with one response."""
    return respx.get(url).respond(status_code, content=content, **kwargs)


# Zip File Mocking
def archive_bytes(members: dict[str, bytes] = {}) -> Path:
    """Write a well-formed ZIP named ``{name}.zip`` into source."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for member, body in members.items():
            zf.writestr(member, body)
    return buf.getvalue()


EMPTY_ZIP_BYTES = archive_bytes()


def write_archive(source: Path, name: str, members: dict[str, bytes] | None = None) -> Path:
    """Write a well-formed ZIP named ``{name}.zip`` into source."""
    path = source / name
    path.write_bytes(archive_bytes(name, members))
