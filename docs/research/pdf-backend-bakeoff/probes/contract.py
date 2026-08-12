"""The neutral `PdfPage` contract every backend in the bake-off emits.

This is the seam the spec's "isolate the backend, not the pipeline" section calls for.
Each backend's only job is to produce layout facts; nothing downstream of here knows
which library produced them. In particular, no backend is asked to reproduce PDFium's
text-API conventions (the U+FFFE soft hyphen, trailing spaces, the scrambled reading
order that floats running headers to the top), because `parsers/pdf_text.normalize_raw`
exists specifically to undo those, and asking a challenger to reproduce them would
reintroduce the incumbent as the reference.

A `Glyph` is deliberately the smallest tuple the engine's geometry consumers need:

    unicode     codepoint (int)
    x0,y0,x1,y1 bounding box in PDF page space (points, y up)
    baseline    y of the text-matrix origin -- the TRUE baseline, not the box bottom
    font_size   effective rendered size in points (font size x text-matrix scale)
    font_id     PostScript/base font name, "" when the backend cannot resolve one
    upright     True when the glyph sits on a horizontal baseline

`upright` earns its place because GPO pages carry a ROTATED left-gutter watermark. For
rotated text the matrix origin is not a horizontal baseline, so those glyphs must be
excluded from horizontal line clustering or they collide with body lines: measured on
this corpus, a stray rotated glyph landed on the baseline of printed lines 24 and 25 and
destroyed the margin-number match for both. PDFium happened to escape that because its
rotated glyphs share one text object; pdfminer and PyMuPDF give each its own origin.
Recovering the fact from box geometry alone is not reliable, and every candidate backend
exposes it directly (mat.b, LTChar.upright, span dir, item transform), so it is a fact
the contract should carry rather than a heuristic the layer should guess.

Backends emit JSONL so a Node adapter and a Python adapter are interchangeable: one
object per page, then a final {"summary": {...}} line.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Glyphs are carried as plain tuples on the hot path: a 1000-page bill is ~3M glyphs and
# a dataclass per glyph costs more than the whole extraction. The field order is fixed
# here and is the actual wire format.
GLYPH_FIELDS = (
    "unicode",
    "x0",
    "y0",
    "x1",
    "y1",
    "baseline",
    "font_size",
    "font_id",
    "upright",
)
CP, X0, Y0, X1, Y1, BASELINE, SIZE, FONT, UPRIGHT = range(9)

Glyph = tuple[int, float, float, float, float, float, float, str, bool]


@dataclass
class PdfPage:
    page_number: int  # 1-based
    width: float
    height: float
    glyphs: list[Glyph]


def page_from_json(obj: dict) -> PdfPage:
    return PdfPage(
        page_number=obj["page_number"],
        width=obj["width"],
        height=obj["height"],
        glyphs=[tuple(g) for g in obj["glyphs"]],  # type: ignore[misc]
    )


def page_to_json(page: PdfPage) -> str:
    return json.dumps(
        {
            "page_number": page.page_number,
            "width": page.width,
            "height": page.height,
            "glyphs": page.glyphs,
        }
    )


def emit(pages: Iterator[PdfPage], summary: dict) -> None:
    """Write a page stream plus a trailing summary line to stdout."""
    for page in pages:
        sys.stdout.write(page_to_json(page) + "\n")
    sys.stdout.write(json.dumps({"summary": summary}) + "\n")


def read_stream(lines: Iterator[str]) -> tuple[list[PdfPage], dict]:
    pages: list[PdfPage] = []
    summary: dict = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if "summary" in obj:
            summary = obj["summary"]
        else:
            pages.append(page_from_json(obj))
    return pages, summary


PROBES = Path(__file__).resolve().parent
# Guarded, not assumed: under Pyodide the probes sit in a flat VFS with no repo above
# them, and a bare parents[3] raises IndexError at import time, taking every browser
# backend down before it runs.
REPO = PROBES.parents[3] if len(PROBES.parents) > 3 else PROBES

# Every backend is invoked the same way -- as a subprocess emitting the JSONL contract --
# so a Node backend and a Python backend are indistinguishable to the scorer. Native
# Python backends are also importable directly (see `run_backend`), which avoids the
# subprocess and JSON round-trip when timing them.
NODE_BACKENDS = {
    "pdfium-wasm": PROBES / "js" / "dump_pdfium_wasm.mjs",
    "pdfjs": PROBES / "js" / "dump_pdfjs.mjs",
}
PYTHON_BACKENDS = {
    "pdfium-native": "backends.pdfium_native",
    "pdfminer": "backends.pdfminer_backend",
    "pymupdf": "backends.pymupdf_backend",
    "pypdf": "backends.pypdf_backend",
}
ALL_BACKENDS = list(PYTHON_BACKENDS) + list(NODE_BACKENDS)


def run_backend(backend: str, pdf: Path, limit: int | None = None) -> tuple[list[PdfPage], dict]:
    """Extract `pdf` through `backend`, returning neutral pages plus its summary.

    Python backends are imported and called in-process; Node backends run as a
    subprocess over the JSONL contract. Both return the same types.
    """
    if backend in PYTHON_BACKENDS:
        sys.path.insert(0, str(PROBES))
        mod = __import__(PYTHON_BACKENDS[backend], fromlist=["extract"])
        return mod.extract(pdf, limit)

    script = NODE_BACKENDS[backend]
    cmd = ["node", "--max-old-space-size=8192", str(script), str(Path(pdf).resolve())]
    if limit is not None:
        cmd += ["--limit", str(limit)]
    # Streamed, not captured. A 1000-page enrolled bill is ~3M glyphs; buffering the
    # whole JSONL document as one string before parsing costs hundreds of megabytes on
    # top of the parsed result. Reading page-by-page keeps one page's JSON alive at a
    # time. stderr is drained in a thread so a chatty backend cannot deadlock on a full
    # pipe buffer while we are still reading stdout.
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(script.parent),
        bufsize=1024 * 1024,
    )
    assert proc.stdout is not None and proc.stderr is not None
    errbuf: list[str] = []
    drain = threading.Thread(target=lambda: errbuf.append(proc.stderr.read()))
    drain.start()
    pages, summary = read_stream(proc.stdout)
    proc.stdout.close()
    drain.join()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"{backend} failed on {pdf}: {''.join(errbuf)[-2000:]}")
    return pages, summary
