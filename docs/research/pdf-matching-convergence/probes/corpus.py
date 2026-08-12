"""Shared corpus view for the PDF matching-convergence probes.

Two populations, kept apart on purpose.

``adjacent_pdf_pairs()`` is every adjacent version pair of committed PDFs — what
``tests/test_pdf_corpus_smoke.py`` iterates. ``accepted_pdf_pairs()`` removes the pairs
``compare.pdf`` refuses before diffing, so it is the population the *product* answers
for. Six of the twenty-three differ between them, all with an enrolled (unnumbered)
side, and every count in the README that describes production behaviour is computed
over the accepted population. Reporting one number over the wider set would describe a
path no user can reach.

Extraction is cached under the gitignored ``tests/data/extract_cache`` sibling used by
the test suite's own PDF loader, keyed by path, mtime and the extractor's identity for
the same reason ``tests/pdf_corpus._extractor_fingerprint`` is: editing the extractor
changes what extraction produces but touches no PDF, so an entry keyed on the PDF alone
stays current and serves pre-change text.
"""

from __future__ import annotations

import hashlib
import pickle
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

from deltatrack.compare.pdf import _is_unnumbered_layout
from deltatrack.parsers import pdf_text
from deltatrack.parsers.pdf_anchors import extract_anchors
from deltatrack.parsers.pdf_text import Page, extract_clean_pages

PROJECT_ROOT = Path(__file__).resolve().parents[4]
FIXTURES_DIR = PROJECT_ROOT / "tests" / "corpus"
CACHE_DIR = PROJECT_ROOT / "tests" / "data" / "extract_cache" / "convergence"


@lru_cache(maxsize=1)
def _extractor_fingerprint() -> str:
    """Identity of every module that can change what an observation contains.

    Wider than ``tests/pdf_corpus``'s, which hashes ``pdf_text`` alone: an anchor is
    part of what a block is, so an edit to ``pdf_anchors`` changes the emitted sequence
    too. That the block former itself lives in ``diff_pdf`` — and so would have to be
    hashed here as well for this to be complete — is finding 4 of the README.
    """
    payload = Path(pdf_text.__file__).read_bytes()
    payload += (Path(pdf_text.__file__).parent / "pdf_anchors.py").read_bytes()
    return hashlib.sha1(payload + version("pypdfium2").encode()).hexdigest()[:12]


def pages_for(pdf: Path) -> list[Page]:
    """Cleaned pages for one PDF, cached across runs."""
    key = f"{pdf.resolve()}::{pdf.stat().st_mtime_ns}::{_extractor_fingerprint()}"
    blob = CACHE_DIR / f"{pdf.stem}-{hashlib.sha1(key.encode()).hexdigest()[:16]}.pkl"
    if blob.exists():
        try:
            return pickle.loads(blob.read_bytes())
        except (pickle.PickleError, EOFError, ValueError):
            pass
    pages = extract_clean_pages(pdf)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(pickle.dumps(pages))
    return pages


def corpus_pdfs() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*/*.pdf"))


def adjacent_pdf_pairs() -> list[tuple[str, Path, Path]]:
    """``(bill, old, new)`` for every adjacent committed PDF pair."""
    out: list[tuple[str, Path, Path]] = []
    for bill_dir in sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir()):
        pdfs = sorted(bill_dir.glob("*.pdf"))
        out.extend((bill_dir.name, a, b) for a, b in zip(pdfs, pdfs[1:]))
    return out


def accepted_pdf_pairs() -> list[tuple[str, Path, Path]]:
    """The adjacent pairs ``compare.pdf`` will actually diff.

    The decline is production's own predicate, called rather than restated, so this
    cannot drift from the guard it describes.
    """
    return [
        (bill, a, b)
        for bill, a, b in adjacent_pdf_pairs()
        if not _is_unnumbered_layout(pages_for(a)) and not _is_unnumbered_layout(pages_for(b))
    ]


def blocks_for(pages: list[Page]):
    """The block sequence ``diff_pdfs`` matches over, built exactly as it builds it."""
    from deltatrack.diff_pdf import _flatten, _group_into_blocks

    return _group_into_blocks(_flatten(pages), extract_anchors(pages))
