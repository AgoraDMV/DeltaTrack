"""Recall test for diff_pdf against the 13-case spec in test_data/pdf/118hr8752-changes.md.

Each fixture case asserts:
  1. A hunk exists whose page+line range covers the case's location(s).
  2. The hunk's change_type matches the fixture's declared type.
  3. For numeric cases (cases 1-8: floor amendment annotations), the hunk
     has has_amendment_annotations=True.
  4. The case's changed prose surfaces as a contiguous run in some hunk — the
     word-level counterpart to the amount-recall tests ("would we see sneaked-in
     language?").

The fixture is the spec; failures here are the things the diff doesn't
yet surface correctly. See the Phase 5 section of
plans/test-coverage-expansion.md for the prose-recall rationale and findings.
"""

from __future__ import annotations

import re

import pytest
from pdf_test_cases import PdfTestCase, load_cases
from recall_text import normalize_for_recall

from diff_pdf import PdfDiff, PdfHunk

# Floor-amendment annotations ("(reduced by $3,000,000)") are financial metadata
# covered by the amount-recall tests, and extraction may reorder a long chain of
# them — so they're stripped before the prose comparison below.
_AMENDMENT_ANNOTATION = re.compile(r"\((?:increased|reduced|decreased) by\s+\$[\d,]+\)")
# Intra-word hyphens are collapsed so the documented soft-hyphen/compound
# ambiguity (extraction emits "pro-mulgations" for "promulgations") can't
# masquerade as a missing word. Recall is about words surviving, not byte fidelity.
_INTRAWORD_HYPHEN = re.compile(r"(?<=\w)-(?=\w)")

# Sentinel for "open-ended" line on an unnumbered (-1) line at end of a hunk
# range. Larger than any realistic per-page line count; small enough that
# tuple comparisons are cheap.
_OPEN_END_LINE = 10_000

try:
    _CASES = load_cases()
except (FileNotFoundError, ValueError):
    # Missing or malformed fixture — emit no parametrized tests rather than
    # failing pytest collection. The session fixture in conftest also skips
    # when the source PDFs are missing.
    _CASES = []


def _location_within_range(
    hunk_range: tuple[int, int, int, int] | None,
    location: tuple[int, int, int, int] | None,
) -> bool:
    """True if `location`'s start falls within `hunk_range`'s [start, end]."""
    if hunk_range is None or location is None:
        return hunk_range is None and location is None
    sp, sl, ep, el = hunk_range
    csp, csl, _, _ = location
    # Treat unnumbered (-1) as 0 for start, _OPEN_END_LINE for end so it's permissive.
    hunk_start = (sp, sl if sl >= 0 else 0)
    hunk_end = (ep, el if el >= 0 else _OPEN_END_LINE)
    return hunk_start <= (csp, csl) <= hunk_end


def _prose(text: str) -> str:
    """Normalize text for prose-recall comparison (annotation- and hyphen-tolerant)."""
    canonical = _AMENDMENT_ANNOTATION.sub("", normalize_for_recall(text))
    return _INTRAWORD_HYPHEN.sub("", re.sub(r"\s+", " ", canonical).strip())


def _prose_surfaces_in_any_hunk(diff: PdfDiff, fixture_text: str, *, removed: bool) -> bool:
    """True if the fixture's prose appears as a contiguous run in some hunk's changed side.

    Searches every hunk, not just the location-covering one: non-unique account
    headings (e.g. "OPERATIONS AND SUPPORT") land at block boundaries, so the
    covering hunk for a location can be an adjacent block. What matters for the
    "would we see sneaked-in language?" question is that the prose surfaces
    *somewhere* in the diff.
    """
    needle = _prose(fixture_text)
    if not needle:
        return False
    return any(needle in _prose(h.v1_text if removed else h.v2_text) for h in diff.hunks)


def _hunk_covering(diff: PdfDiff, case: PdfTestCase) -> PdfHunk | None:
    """Find the hunk whose v1/v2 ranges cover the case's v1/v2 locations.

    A hunk matches a case when each side's "has a range?" lines up with the
    case's "has a location?" — i.e. an added case (v1_location=None) only
    matches an added hunk (v1_range=None), and so on. The location-covers
    check then confirms the present sides line up positionally.
    """
    for h in diff.hunks:
        if (case.v1_location is not None) != (h.v1_range is not None):
            continue
        if (case.v2_location is not None) != (h.v2_range is not None):
            continue
        v1_ok = case.v1_location is None or _location_within_range(h.v1_range, case.v1_location)
        v2_ok = case.v2_location is None or _location_within_range(h.v2_range, case.v2_location)
        if v1_ok and v2_ok:
            return h
    return None


@pytest.mark.parametrize("case", _CASES, ids=lambda c: f"case{c.number}")
class TestRecall:
    def test_hunk_exists_for_case(self, case: PdfTestCase, hr8752_pdf_diff: PdfDiff):
        h = _hunk_covering(hr8752_pdf_diff, case)
        assert h is not None, f"Case {case.number}: no hunk covers v1={case.v1_location} v2={case.v2_location}"

    def test_change_type_matches(self, case: PdfTestCase, hr8752_pdf_diff: PdfDiff):
        h = _hunk_covering(hr8752_pdf_diff, case)
        assert h is not None
        assert h.change_type == case.change_type, (
            f"Case {case.number} ({case.title}): expected change_type={case.change_type!r}, got {h.change_type!r}"
        )

    def test_amendment_annotation_flag_for_numeric_cases(self, case: PdfTestCase, hr8752_pdf_diff: PdfDiff):
        # Cases 1-8 in the fixture are floor amendment additions; the hunk
        # should carry has_amendment_annotations=True. Other cases either
        # have no amendments (9, 10, 11, 13) or have them in long bodies
        # (12) where we still expect the flag.
        if "annotation" not in case.expected_what_changed.lower() and case.expected_net is None:
            pytest.skip("not a financial annotation case")
        h = _hunk_covering(hr8752_pdf_diff, case)
        assert h is not None
        assert h.has_amendment_annotations, (
            f"Case {case.number} ({case.title}): expected has_amendment_annotations=True"
        )

    def test_changed_prose_surfaces_in_a_hunk(self, case: PdfTestCase, hr8752_pdf_diff: PdfDiff):
        # The word-level counterpart to the financial-recall tests: the actual
        # changed prose (not just a hunk at the right location) must appear in the
        # diff. This is what answers "if language was sneaked in, would we see it?"
        removed = case.change_type == "removed"
        fixture = case.v1_text if removed else case.v2_text
        if not fixture:
            pytest.skip("no text on the asserted side (placeholder case)")
        assert _prose_surfaces_in_any_hunk(hr8752_pdf_diff, fixture, removed=removed), (
            f"Case {case.number} ({case.title}): changed prose did not surface in any hunk — a real word-level miss"
        )
