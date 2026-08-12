"""Shared HTTP helpers."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable, Iterable

import httpx

from shared.zip import verify_archive_complete

BASE_URL = "https://api.congress.gov/v3"
LOG_API_REQUESTS = True


def request_with_retry(
    client: httpx.Client,
    url: str,
    params: dict | None = None,
    *,
    headers: dict | None = None,
    timeout: float | None = None,
    attempts: int = 3,
) -> httpx.Response:
    """GET with retry on 429 and 5xx."""
    if LOG_API_REQUESTS:
        safe_params = {k: v for k, v in (params or {}).items() if k != "api_key"}
        suffix = f" {safe_params}" if safe_params else ""
        print(f"[API]: {url}{suffix}", file=sys.stderr)

    request_kwargs: dict = {}
    if params is not None:
        request_kwargs["params"] = params
    if headers is not None:
        request_kwargs["headers"] = headers
    if timeout is not None:
        request_kwargs["timeout"] = timeout

    last_resp = None
    for attempt in range(attempts):
        last_resp = client.get(url, **request_kwargs)
        if last_resp.status_code == 429:
            print("Rate limited, waiting 60s...", file=sys.stderr)
            time.sleep(60)
            continue
        if last_resp.status_code >= 500:
            time.sleep(2**attempt)
            continue
        last_resp.raise_for_status()
        return last_resp

    last_resp.raise_for_status()
    return last_resp


def api_get(
    client: httpx.Client,
    path: str,
    *,
    api_key: str,
    params: dict | None = None,
) -> dict:
    """GET a congress.gov API v3 JSON endpoint with retries.

    Ensures we always use a fully-qualified URL (avoids relative-URL regressions).
    """
    url = f"{BASE_URL}{path}"
    request_params = dict(params or {})
    request_params["api_key"] = api_key
    resp = request_with_retry(client, url, request_params)
    return resp.json()


def _print_download_progress(downloaded: int, total: int) -> None:
    """Print a single-line download progress update to stderr."""
    mb_done = downloaded / (1024 * 1024)
    if total:
        pct = downloaded * 100 // total
        mb_total = total / (1024 * 1024)
        print(f"\r  {mb_done:.1f}/{mb_total:.1f} MB ({pct}%)", end="", file=sys.stderr, flush=True)
    else:
        print(f"\r  {mb_done:.1f} MB", end="", file=sys.stderr, flush=True)


def path_for_error(path: Path) -> Path:
    """Return the error-marker path associated with ``path``."""
    return path.with_suffix(path.suffix + ".error")


def write_error(error: Exception, path: Path) -> Path:
    """Write an error beside ``path`` and return the marker path."""
    error_path = path_for_error(Path(path))
    error_path.parent.mkdir(parents=True, exist_ok=True)
    error_path.write_text(str(error), encoding="utf-8")
    return error_path

def download_temp_path(destination: Path) -> Path:
    return destination.with_suffix(destination.suffix + ".part")

def cached_file_download(
    client: httpx.Client,
    url: str,
    destination: Path,
    *,
    skip_existing: bool = True,
    verify: Callable[[Path], None] | None = None,
) -> bool:
    """Stream ``url`` to ``destination`` atomically, skipping it if already present.
    Returns True if downloaded and False if skipped. Raises when downloading fails.

    Creates a temporary '.part' file while downloading to ensure atomic downloads.
    """
    error_path = path_for_error(destination)
    if skip_existing and destination.exists():
        error_path.unlink(missing_ok=True)
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = download_temp_path(destination)
    if temp_path.exists():
        temp_path.unlink()

    try:
        with client.stream("GET", url, follow_redirects=True, timeout=300) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0) or 0)
            downloaded = 0
            with temp_path.open("wb") as fh:
                for chunk in response.iter_bytes(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    downloaded += len(chunk)
                    _print_download_progress(downloaded, total)
            print(file=sys.stderr)
            if total and downloaded != total:
                raise httpx.HTTPError(f"Incomplete download: got {downloaded} of {total} bytes")

        # Verify before committing the temp file into place. This preserves the
        # atomicity invariant: a failed download must not leave a destination
        # file behind.
        if verify is not None:
            verify(temp_path)
        temp_path.replace(destination)
        error_path.unlink(missing_ok=True)
        return True
    except Exception as error:
        if temp_path.exists():
            temp_path.unlink()
        write_error(error, destination)
        raise


def download_zip(
    client: httpx.Client,
    url: str,
    destination: Path,
    *,
    skip_existing: bool = True,
) -> bool:
    """Download a ZIP atomically, verifying completeness before committing."""
    return cached_file_download(
        client,
        url,
        destination,
        skip_existing=skip_existing,
        verify=verify_archive_complete,
    )


def download_archives(
    client: httpx.Client,
    urls: Iterable[str],
    destination: Path,
    *,
    url_to_path: Callable[[str, int], Path],
    skip_existing: bool = True,
) -> list[Path]:
    """
    Download many archive URLs into ``destination``, continuing past failures.
    """
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    url_list = list(urls)
    saved: list[Path] = []

    print(f"Downloading {len(url_list)} zip files...", file=sys.stderr)
    for i, url in enumerate(url_list):
        mapped = Path(url_to_path(url, i))
        dest = mapped if mapped.is_absolute() else destination / mapped
        prefix = f"{i + 1}/{len(url_list)}:"
        try:
            downloaded = download_zip(
                client,
                url,
                dest,
                skip_existing=skip_existing,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                print(f"{prefix} no zip (404) for {dest.name}", file=sys.stderr)
            else:
                print(f"{prefix} FAILED {dest.name}: {exc}", file=sys.stderr)
            continue
        except Exception as exc:
            print(f"{prefix} FAILED {dest.name}: {exc}", file=sys.stderr)
            continue

        if downloaded:
            saved.append(dest)
            print(f"{prefix} saved {dest.name} ({url})", file=sys.stderr)
        else:
            print(f"{prefix} skip existing {dest.name}", file=sys.stderr)
    return saved
