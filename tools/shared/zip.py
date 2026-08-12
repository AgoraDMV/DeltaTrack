"""Shared ZIP helpers."""

from __future__ import annotations

import fnmatch
import re
import stat
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, NamedTuple

import httpx

@dataclass
class ArchiveFile:
    zip_path: str | Path
    file_path: str | Path

    def __str__(self) -> str:
        return f"{self.zip_path}/{self.file_path}"

    def __repr__(self) -> str:
        return f"ArchiveFile({self})"


class ExtractArchiveDetails(NamedTuple):
    files_extracted: list[Path]
    files_skipped: list[Path]
    errors: dict[Path, Exception]


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    """Return True when ``info`` is a Unix symlink entry."""
    if info.create_system != 3:  # 3 == Unix
        return False
    return stat.S_ISLNK(info.external_attr >> 16)


def _ensure_within_destination(out_dir: Path, dest: Path) -> None:
    """Raise ValueError if ``dest`` is malformed or resolves outside ``out_dir``."""
    if "\x00" in dest.as_posix() or "\x00" in out_dir.as_posix():
        raise ValueError(f"Malformed zip member path: {dest}")

    out_resolved = out_dir.resolve()
    dest_resolved = dest.resolve()
    if not dest_resolved.is_relative_to(out_resolved):
        raise ValueError(f"Zip member escapes destination directory: {dest}")


def _ensure_symlink_within_destination(
    out_dir: Path, dest: Path, link_target: str
) -> None:
    """Raise ValueError if a zip symlink's target resolves outside ``out_dir``."""
    if "\x00" in link_target:
        raise ValueError(f"Malformed zip symlink target: {link_target!r}")
    target = Path(link_target)
    resolved_target = target.resolve() if target.is_absolute() else (dest.parent / target).resolve()
    out_resolved = out_dir.resolve()
    if not resolved_target.is_relative_to(out_resolved):
        raise ValueError(
            f"Zip symlink escapes destination directory: {dest} -> {link_target}"
        )


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
) -> tuple[int, ExtractArchiveDetails]:
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
        ``(count, details)`` where ``count`` is how many files were written and
        ``details`` has ``files_extracted``, ``files_skipped``, and ``errors``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files_extracted: list[Path] = []
    files_skipped: list[Path] = []
    errors: dict[Path, Exception] = {}

    for index, (name, zf) in enumerate(iterate_archive(Path(archive_path), files)):
        member_path = Path(name)
        try:
            if name.endswith("/"):
                files_skipped.append(member_path)
                continue
            dest_rel = file_handler(name, index, zf) if file_handler else None
            if dest_rel is None:
                files_skipped.append(member_path)
                continue
            if "\x00" in str(dest_rel) or "\x00" in name:
                raise ValueError(f"Malformed zip member path: {name!r}")
            dest = out_dir / dest_rel
            _ensure_within_destination(out_dir, dest)
            if dest.exists() and not overwrite_existing:
                files_skipped.append(dest)
                continue
            data = file_content_handler(zf.read(name), name, index, zf) if file_content_handler else None
            if data is None:
                files_skipped.append(dest)
                continue
            info = zf.getinfo(name)
            if _is_zip_symlink(info):
                _ensure_symlink_within_destination(
                    out_dir, dest, data.decode("utf-8", errors="surrogateescape")
                )
            dest.parent.mkdir(parents=True, exist_ok=True)
            _ensure_within_destination(out_dir, dest)
            dest.write_bytes(data)
            files_extracted.append(dest)
        except ValueError:
            raise
        except Exception as exc:
            errors[member_path] = exc

    return len(files_extracted), ExtractArchiveDetails(
        files_extracted, files_skipped, errors
    )
