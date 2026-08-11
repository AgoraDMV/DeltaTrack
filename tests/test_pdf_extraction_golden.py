"""Golden-snapshot regression guard for PDF text extraction.

The amount-recall and diff-recall suites prove extraction *recall* (expected
content survives). They miss a subtler regression: the cleaner silently changing
what it emits — chrome leaking back into the body, a soft-hyphen path breaking,
or a pypdfium2 upgrade altering glyph handling. This pins the cleaned line output
of a curated set of pages, each chosen to exercise one tricky path, so any such
change fails loudly with a readable diff.

Engine note: extraction is pypdfium2 (PDFium). pdfplumber was dropped after a
full-corpus differential check (numbered-line parity ~99.9%, identical per-pair
diff output). That cross-engine comparison cannot run once pdfplumber is gone, so
this golden is the lasting guard against extraction drift.

To regenerate after an INTENTIONAL extraction change, then review the JSON diff:
    UPDATE_GOLDEN=1 uv run pytest tests/test_pdf_extraction_golden.py

Regeneration is ALL-OR-NOTHING (#296): if any fixture is absent it refuses to
write, rather than rebuilding from a partial set and deleting the rest. See
_regenerated_golden.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from deltatrack.parsers.pdf_text import extract_clean_pages
from tests.conftest import assert_manifest_committed
from tests.corpus_paths import DATA_DIR

_ROOT = Path(__file__).parent.parent
_GOLDEN = DATA_DIR / "pdf" / "extraction_golden.json"

# (key, pdf path relative to repo root, 1-based page, path exercised).
_CASES = [
    (
        "hr4366_reported_p5",
        "tests/corpus/118-hr-4366/1_reported-in-house.pdf",
        5,
        "numbered body + soft-hyphen reconstruction across margin lines",
    ),
    (
        "hr4366_pcs_p7",
        "tests/corpus/118-hr-4366/3_placed-on-calendar-senate.pdf",
        7,
        "page-boundary hyphen gluing the VerDate footer onto the last body line",
    ),
    (
        "hr2029_reported_p2",
        "tests/corpus/114-hr-2029/1_reported-in-house.pdf",
        2,
        "page-boundary hyphen gluing the DSK watermark onto the last body line",
    ),
    (
        "hr8752_title_p1",
        "tests/corpus/118-hr-8752/1_reported-in-house.pdf",
        1,
        "title page: soft hyphen joined into one word (no margin numbers)",
    ),
    (
        "crpt198_compare_p220",
        "tests/data/CRPT-118srpt198.pdf",
        220,
        "watermarked committee-report comparison table read forward, not reversed",
    ),
]

# Every case's fixture is committed, so absence is always a fail-closed error (floored by
# test_manifest_fixtures_committed), never a silent skip — the fail-open shape #287 removes.
# The last three were committed by #296: they were held out as "large omnibus PDFs", but the
# pages this module reads are 314-351 KB prints, inside the 240-360 KB band ADR 0015 already
# accepts, and no script fetched them. So those three goldens ran only on machines where
# someone had fetched the bill by hand, and never in CI — three of the five tripwires here
# were dark (epic #288). Committing them costs ~1 MB and turns them on.
_COMMITTED_RELS = frozenset(rel for _, rel, _, _ in _CASES)


def _page_lines(path: Path, page_number: int) -> list[list]:
    """The cleaned page's lines as JSON-friendly [line_number, text] pairs."""
    # Deliberately NOT tests.pdf_corpus.cached_pages: this suite asserts the
    # extractor's output against goldens, so reading a cached pickle would leave
    # it asserting nothing about the code it guards (#348 / epic #288).
    pages = extract_clean_pages(path)
    page = next((p for p in pages if p.page_number == page_number), None)
    assert page is not None, f"{path} has no page {page_number}"
    return [[ln.line_number, ln.text] for ln in page.lines]


def _present(rel: str) -> bool:
    return (_ROOT / rel).exists()


def test_manifest_fixtures_committed():
    """Fail-closed floor (#287, ADR 0015): a plain, always-collected guard, so a missing
    fixture fails HERE naming it, instead of the fail-open shape #287 removes (a case
    silently skipping in CI). Every case is floored, because every fixture is committed
    (#296). The bills/-layout ones are checked via the shared manifest helper;
    CRPT-118srpt198 sits outside the manifest (ADR 0015), so it is floored directly."""
    assert_manifest_committed(sorted(_COMMITTED_RELS), "pdf-extraction-golden")
    absent = sorted(rel for rel in _COMMITTED_RELS if not _present(rel))
    assert not absent, f"committed pdf-extraction-golden fixtures absent from checkout: {absent}"


def _regenerated_golden() -> dict:
    """The rebuilt golden, or nothing at all (#296).

    The pre-#296 body rebuilt the file from only the cases whose fixture happened to be
    present, and overwrote. On a checkout missing one, regenerating for an unrelated
    reason deleted that case's recorded expectations, and the deletion looked like an
    ordinary diff. A skipped case comes back when someone restores the file; a deleted
    golden entry does not, and the case then fails with "no golden entry" for a reason
    unrelated to what it tests.

    Every fixture is committed (_COMMITTED_RELS), so an absent one means a broken
    checkout rather than an optional case. Refusing to write anything is therefore the
    whole fix: there is no partial set worth writing. This is the fail-closed option
    #296 preferred, available now that no case depends on an unfetchable file.

    Entries for keys no longer in _CASES are dropped, so retiring a case cleans up after
    itself. Output follows _CASES order for a stable, reviewable diff.
    """
    absent = sorted(rel for _, rel, _, _ in _CASES if not _present(rel))
    assert not absent, (
        f"refusing to regenerate: fixtures absent from the checkout: {absent}. "
        "Regenerating without them would delete their recorded entries. "
        "Restore them first (#296)."
    )
    return {key: _page_lines(_ROOT / rel, pg) for key, rel, pg, _ in _CASES}


@pytest.mark.skipif(os.environ.get("UPDATE_GOLDEN") != "1", reason="not in golden-update mode")
def test_regenerate_golden():
    """Rewrite the golden from current extraction. Skipped unless UPDATE_GOLDEN=1."""
    data = _regenerated_golden()
    _GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    _GOLDEN.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def test_golden_file_has_exactly_one_entry_per_case():
    """The committed golden covers every case and nothing else.

    This is the standing check that the file on disk stayed whole — the state the old
    partial rebuild silently broke. A missing key means a case was dropped (or added to
    _CASES without regenerating); an extra key means a retired case left residue behind.
    Asserting against the committed file, rather than a regenerated one, is what gives it
    teeth: a regenerated dict is built from _CASES and so agrees with _CASES by
    construction, which would make the check vacuous."""
    golden = json.loads(_GOLDEN.read_text())
    assert set(golden) == {key for key, *_ in _CASES}, (
        "the committed golden must hold exactly one entry per case; regenerate with "
        "UPDATE_GOLDEN=1 on a complete checkout"
    )


def test_regeneration_refuses_when_a_fixture_is_absent(monkeypatch):
    """#296: an absent fixture is a broken checkout, not an optional case, so regeneration
    must refuse rather than write a partial golden. Simulates the absence rather than
    moving a real PDF, so this runs on any checkout."""
    module = sys.modules[__name__]
    absent_rel = "tests/corpus/118-hr-4366/1_reported-in-house.pdf"
    monkeypatch.setattr(module, "_present", lambda rel: rel != absent_rel)
    monkeypatch.setattr(module, "_page_lines", lambda path, pg: [[1, "regenerated"]])

    with pytest.raises(AssertionError, match="refusing to regenerate"):
        _regenerated_golden()


@pytest.mark.parametrize("key,rel,page,why", _CASES, ids=[c[0] for c in _CASES])
def test_extraction_matches_golden(key, rel, page, why):
    if os.environ.get("UPDATE_GOLDEN") == "1":
        pytest.skip("golden-update mode")
    # Every case runs unconditionally: all five fixtures are committed (#296), so a missing
    # one is a fail-closed error floored by test_manifest_fixtures_committed, never a skip.
    golden = json.loads(_GOLDEN.read_text())
    assert key in golden, f"no golden entry for {key}; regenerate with UPDATE_GOLDEN=1"
    actual = _page_lines(_ROOT / rel, page)
    expected = [[ln, text] for ln, text in golden[key]]
    assert actual == expected, (
        f"extraction drifted for {key} ({why}). If intentional, regenerate the "
        f"golden with UPDATE_GOLDEN=1 and review the diff."
    )
