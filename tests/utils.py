"""Shared test helpers."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import httpx
import respx


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


def assert_message_contains_strings(message: str, expected_strings: list[str]) -> None:
    """Assert each expected string appears in message."""
    __tracebackhide__ = True
    for part in expected_strings:
        assert part in message, f"Missing '{part!r}' in message: {message}"


def mock_http_requests(
    url: re.Pattern[str] = re.compile(".*"),
    status_code: int = 200,
    content: bytes | list[bytes] = b"",
    headers: dict[str, str] | None = None,
) -> respx.Route:
    """Mock matching GET requests with one response."""
    return respx.get(url).mock(return_value=httpx.Response(status_code, headers=headers, content=content))


def archive_bytes(members: dict[str, bytes] | None = None) -> bytes:
    """Build a well-formed ZIP archive payload from members."""
    members = members or {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for member, body in members.items():
            zf.writestr(member, body)
    return buf.getvalue()


EMPTY_ZIP_BYTES = archive_bytes()
