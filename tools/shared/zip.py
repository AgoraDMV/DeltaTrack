"""Shared ZIP helpers."""

from __future__ import annotations

import fnmatch
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import httpx

@dataclass
class ArchiveFile:
    zip_path: str | Path
    file_path: str | Path

    def __str__(self) -> str:
        return f"{self.zip_path}/{self.file_path}"

    def __repr__(self) -> str:
        return f"ArchiveFile({self})"

def verify_archive_complete(path: Path) -> None:
    """Raise unless ``path`` is a readable ZIP archive.

    A content-length check is the completeness signal only when the server sends
    that header; a chunked response legitimately omits it, and then a truncated
    body is indistinguishable from a whole one by byte count alone. The archive's
    own end-of-central-directory record is the fallback signal: it is written
    last, so a short read loses it and the file no longer opens.

    Emptiness is deliberately not checked: a zero-member ZIP is structurally
    valid, and truncation always destroys the end-of-central-directory record, so
    a short read can only ever produce "does not open", never "opens with zero
    members".
    """
    try:
        with zipfile.ZipFile(path):
            pass
    except (zipfile.BadZipFile, OSError) as exc:
        raise httpx.HTTPError(f"Incomplete download: {path.name} is not a readable ZIP archive ({exc})") from exc


def iterate_archive(
    path: Path, pattern: str | re.Pattern[str] = "*"
) -> Iterator[tuple[str, zipfile.ZipFile]]:
    """Yield ``(path, zip_handle)`` for each archive file or directory matching  ``pattern``.

    A string matching pattern uses a shell-style glob with simplified regex semantics. 
    A pattern of type re.Pattern uses full regex matching.
    For example, pattern = "*.xml" is equivalent to pattern = re.compile(r"\.xml") and pattern = re.compile(r"^.*\.xml$")
    """
    with zipfile.ZipFile(path) as zf:
        def _matches(name: str) -> bool:
            if isinstance(pattern, re.Pattern):
                return pattern.match(Path(name).name) is not None
            return fnmatch.fnmatch(name, pattern)
        files = [name for name in zf.namelist() if _matches(name)]
        yield from [(name, zf) for name in files]


def extract_archive(
    archive_path: Path | str,
    *,
    out_dir: Path | str,
    files: str | re.Pattern[str] = '*',
    overwrite_existing: bool = False,
    file_handler: Callable[[str, int, zipfile.ZipFile], str | Path | None] = lambda filename, index, zf: filename,
    file_content_handler: Callable[[bytes, str, int, zipfile.ZipFile], bytes | None] = lambda data, filename, index, zf: data,
) -> int:
    """Extract matching ZIP members into ``out_dir``.

    Args:
        archive_path: ZIP file to read.
        out_dir: Destination root for extracted files.
        files: Glob string or compiled regex selecting archive members.
        overwrite_existing: When false, skip members whose destination already exists.
        file_handler: Maps archive member path to a path relative to ``out_dir`` to allow the file structure to be reordered.
            Return ``None`` to skip the member (the member is not opened).
        file_content_handler: Transforms or analyzes file contents before writing.

    Returns:
        Number of files written.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    for index, (name, zf) in enumerate(iterate_archive(Path(archive_path), files)):
        if name.endswith("/"):
            continue
        dest_rel = file_handler(name, index, zf) if file_handler else None
        if dest_rel is None:
            continue
        dest = out_dir / dest_rel
        if dest.exists() and not overwrite_existing:
            continue
        data = file_content_handler(zf.read(name), name, index, zf) if file_content_handler else None
        if data is None:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        written += 1
    return written