"""FastAPI service exposing the DeltaTrack PDF diff engine.

Stateless by design: uploaded PDFs live only for the duration of a request (in a
temp dir deleted immediately by ``compare_pdfs``), nothing is persisted, and the
result is returned to the caller. No analytics, no per-client logging — this
honors the "your session is not tracked" promise shown in the UI.

The single interactive endpoint is ``POST /api/compare``: upload a start PDF and
an end PDF, get back a standalone HTML diff report (default) or canonical JSON
(``?output=json``).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from server.pdf_compare import compare_pdfs, compare_pdfs_html
from server.xml_compare import compare_xml, compare_xml_html

# The static front-end (webapp/) ships alongside this package and is served by
# the app itself — see the StaticFiles mount at the bottom of the file.
WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"

# Upload guards — this endpoint accepts untrusted public input.
MAX_UPLOAD_BYTES = 150 * 1024 * 1024  # 150 MB per file
CHUNK_SIZE = 1024 * 1024  # 1 MB read granularity for the streaming size guard
PDF_MAGIC = b"%PDF"
MAX_CONCURRENT_DIFFS = 2  # bound CPU; a large diff is heavy
DIFF_TIMEOUT_S = 120

# Format → (label-extension, html entry point, json entry point).
_COMPARE = {
    "pdf": (".pdf", compare_pdfs_html, compare_pdfs),
    "xml": (".xml", compare_xml_html, compare_xml),
}

app = FastAPI(
    title="DeltaTrack API",
    # No interactive API docs / schema surface in production.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Limits how many diffs run at once. Paired with a process memory ceiling + the
# per-request timeout below, this keeps one heavy upload from starving the box.
_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DIFFS)


def _forwarded_proto(request: Request) -> str | None:
    """Best-effort client scheme from reverse-proxy headers (None if unknown)."""
    if raw := request.headers.get("x-forwarded-proto"):
        return raw.split(",")[0].strip().lower()

    if request.headers.get("x-forwarded-ssl", "").lower() in ("on", "1", "true"):
        return "https"

    if port := request.headers.get("x-forwarded-port", "").strip():
        if port == "443":
            return "https"
        if port == "80":
            return "http"

    forwarded = request.headers.get("forwarded", "")
    for segment in forwarded.split(","):
        for part in segment.split(";"):
            part = part.strip()
            if part.lower().startswith("proto="):
                return part.split("=", 1)[1].strip().strip('"').lower()

    return None


def _https_redirect_target(request: Request) -> str:
    """Build an absolute https URL from the proxied Host + request path."""
    host = request.headers.get("host") or request.url.netloc
    path = request.url.path
    query = request.url.query
    target = f"https://{host}{path}"
    if query:
        target += f"?{query}"
    return target


@app.middleware("http")
async def force_https_behind_proxy(request: Request, call_next):
    """Redirect http→https when the proxy signals cleartext.

    Primary redirect is Apache ``RewriteRule`` (see docs/https-redirect.md). This
    middleware is a backstop when ``X-Forwarded-Proto: http`` (or port 80) is set.
    Local dev (no forwarded headers) is unaffected."""
    if _forwarded_proto(request) == "http":
        status = 301 if request.method in ("GET", "HEAD") else 308
        return RedirectResponse(_https_redirect_target(request), status_code=status)
    return await call_next(request)


def _looks_like_xml(data: bytes) -> bool:
    """A bill XML starts with the prolog or a root element (after any BOM/space)."""
    head = data.lstrip(b"\xef\xbb\xbf \t\r\n")
    return head[:1] == b"<"


async def _read_upload(upload: UploadFile, field: str, fmt: str) -> bytes:
    """Read an upload in bounded chunks, aborting the moment it exceeds the size
    cap so an oversized body is never fully buffered in memory, then validate the
    format's magic bytes before it reaches the diff engine.

    An upstream request-body limit is the first line of defense in production; this
    is the in-process backstop for any path that doesn't sit behind a proxy."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(CHUNK_SIZE):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"{field}: file exceeds the 150 MB limit.")
        chunks.append(chunk)
    if total == 0:
        raise HTTPException(status_code=400, detail=f"{field}: empty file.")
    data = b"".join(chunks)
    if fmt == "pdf" and not data.startswith(PDF_MAGIC):
        raise HTTPException(status_code=415, detail=f"{field}: not a PDF (missing %PDF header).")
    if fmt == "xml" and not _looks_like_xml(data):
        raise HTTPException(status_code=415, detail=f"{field}: not XML (no leading '<').")
    return data


def _label_from_filename(name: str | None, fallback: str, ext: str) -> str:
    """Derive a human label from the uploaded filename, defensively (strip any
    path components a client might send, drop the format extension)."""
    if not name:
        return fallback
    stem = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if stem.lower().endswith(ext):
        stem = stem[: -len(ext)]
    stem = stem.strip()
    return stem or fallback


@app.post("/api/compare")
async def compare(
    start_file: UploadFile = File(...),
    end_file: UploadFile = File(...),
    output: str = Query("html", pattern="^(html|json)$"),
    fmt: str = Query("pdf", alias="format", pattern="^(pdf|xml)$"),
):
    ext, html_fn, json_fn = _COMPARE[fmt]
    start_bytes = await _read_upload(start_file, "start_file", fmt)
    end_bytes = await _read_upload(end_file, "end_file", fmt)

    start_label = _label_from_filename(start_file.filename, "Start version", ext)
    end_label = _label_from_filename(end_file.filename, "End version", ext)

    compare_fn = html_fn if output == "html" else json_fn

    try:
        async with _semaphore:
            # The diff is CPU-bound and blocking; run it off the event loop so
            # one request can't stall the server, and cap it with a timeout.
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    compare_fn,
                    start_bytes,
                    end_bytes,
                    start_label=start_label,
                    end_label=end_label,
                ),
                timeout=DIFF_TIMEOUT_S,
            )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Diff timed out. Try smaller documents.")
    except HTTPException:
        raise
    except Exception:
        # Never leak engine internals or filesystem paths to the caller.
        raise HTTPException(
            status_code=422,
            detail=f"Could not diff these files. Are both valid bill-text {fmt.upper()} files?",
        )

    if output == "html":
        return HTMLResponse(result, media_type="text/html; charset=utf-8")
    return JSONResponse(result)


# Static front-end, mounted LAST and at "/" so the explicit /api/* routes above
# always match first. With html=True, "/" serves index.html and clean paths like
# "/compare.html" resolve to files. This makes the service self-contained:
# `uvicorn server.app:app` serves the whole site — identical in dev (no proxy) and
# in prod (a reverse proxy just forwards / to here). No docroot copy, no route drift.
app.mount("/", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")
