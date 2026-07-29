"""What the PDF extraction cache key must distinguish (#393).

`tests/pdf_corpus.cached_pages` persists extracted PDF text to disk so repeat runs
skip extraction. A cache entry is only safe to reuse when both halves of what produced
it are unchanged: the PDF, and the extractor. Keying on the PDF alone (path + mtime)
left the second half unchecked, so editing `parsers/pdf_text.py` did not invalidate
anything and the suites reading the cache asserted against pre-change text.

That failure mode is silent by construction: the tests do not skip, they pass. It hit
hardest in `test_pdf_anchor_golden.py`, which exists to go red on exactly this drift.

These tests use a throwaway file rather than a real PDF: `_cache_file` only stats the
path, so nothing here needs the corpus or an extraction.
"""

from __future__ import annotations

import hashlib
import os
from importlib.metadata import version
from pathlib import Path

import deltatrack.parsers.pdf_text
from tests import pdf_corpus


def _touch(dir_path: Path, name: str = "bill.pdf", content: bytes = b"%PDF-1.7\n") -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    p = dir_path / name
    p.write_bytes(content)
    return p


def test_fingerprint_tracks_extractor_source_and_engine():
    """The fingerprint must be derived from the extractor's own bytes plus the engine
    version. Recomputed here from those inputs directly, so dropping either one from
    `_extractor_fingerprint` fails here instead of silently widening what a stale entry
    can survive."""
    extractor_src = Path(deltatrack.parsers.pdf_text.__file__).read_bytes()
    expected = hashlib.sha1(extractor_src + version("pypdfium2").encode()).hexdigest()[:12]
    assert pdf_corpus._extractor_fingerprint() == expected


def test_key_changes_when_the_extractor_changes(tmp_path, monkeypatch):
    """The #393 defect: an extractor edit left the key identical, so the stale entry
    was read back and the golden suites asserted against pre-change text."""
    pdf = _touch(tmp_path)
    before = pdf_corpus._cache_file(pdf)

    monkeypatch.setattr(pdf_corpus, "_extractor_fingerprint", lambda: "0" * 12)
    after = pdf_corpus._cache_file(pdf)

    assert before != after


def test_key_changes_when_the_pdf_changes(tmp_path):
    """The guarantee that already held, pinned so the #393 fix does not trade it away."""
    pdf = _touch(tmp_path)
    before = pdf_corpus._cache_file(pdf)

    os.utime(pdf, ns=(0, 12345))
    assert pdf_corpus._cache_file(pdf) != before


def test_key_is_stable_when_nothing_changed(tmp_path):
    """Completeness floor for the two tests above. A key that varied every call would
    satisfy both of them while never hitting, quietly removing the speedup the cache
    exists for (#348, duplicated PDF extraction across xdist workers)."""
    pdf = _touch(tmp_path)
    assert pdf_corpus._cache_file(pdf) == pdf_corpus._cache_file(pdf)


def test_key_distinguishes_two_pdfs(tmp_path):
    """Same stem in different directories must not collide: the key carries the resolved
    path, not just the filename the entry is named after."""
    a = _touch(tmp_path / "v1", "bill.pdf")
    b = _touch(tmp_path / "v2", "bill.pdf")
    assert pdf_corpus._cache_file(a) != pdf_corpus._cache_file(b)
