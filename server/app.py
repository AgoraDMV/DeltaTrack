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

# The static front-end (webapp/) ships alongside this package and is served by
# the app itself — see the StaticFiles mount at the bottom of the file.
WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"

# Upload guards — this endpoint accepts untrusted public input.
MAX_UPLOAD_BYTES = 150 * 1024 * 1024  # 150 MB per file
CHUNK_SIZE = 1024 * 1024  # 1 MB read granularity for the streaming size guard
PDF_MAGIC = b"%PDF"
MAX_CONCURRENT_DIFFS = 2  # bound CPU; a large diff is heavy
DIFF_TIMEOUT_S = 120

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
    """Redirect http→https when a front proxy signals cleartext via X-Forwarded-Proto.

    Apache .htaccess in webapp/ is not consulted on the proxy-only deploy path; this
    is the in-app backstop. Local dev (no X-Forwarded-Proto) is unaffected."""
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if proto == "http":
        status = 301 if request.method in ("GET", "HEAD") else 308
        return RedirectResponse(_https_redirect_target(request), status_code=status)
    return await call_next(request)


async def _read_pdf(upload: UploadFile, field: str) -> bytes:
    """Read an upload in bounded chunks, aborting the moment it exceeds the size
    cap so an oversized body is never fully buffered in memory, then validate the
    PDF magic bytes before it reaches the diff engine.

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
    if not data.startswith(PDF_MAGIC):
        raise HTTPException(status_code=415, detail=f"{field}: not a PDF (missing %PDF header).")
    return data


def _label_from_filename(name: str | None, fallback: str) -> str:
    """Derive a human label from the uploaded filename, defensively (strip any
    path components a client might send, drop the .pdf extension)."""
    if not name:
        return fallback
    stem = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    stem = stem.strip()
    return stem or fallback


@app.post("/api/compare")
async def compare(
    start_pdf: UploadFile = File(...),
    end_pdf: UploadFile = File(...),
    output: str = Query("html", pattern="^(html|json)$"),
):
    start_bytes = await _read_pdf(start_pdf, "start_pdf")
    end_bytes = await _read_pdf(end_pdf, "end_pdf")

    start_label = _label_from_filename(start_pdf.filename, "Start version")
    end_label = _label_from_filename(end_pdf.filename, "End version")

    compare_fn = compare_pdfs_html if output == "html" else compare_pdfs

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
            detail="Could not diff these files. Are both valid bill-text PDFs?",
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
