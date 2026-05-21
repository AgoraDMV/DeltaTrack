"""Corpus-wide smoke tests for the PDF block-level diff.

The PDF analog of the XML corpus smoke in test_diff_validation.py. These check
invariants that should hold for ANY PDF diff, using only the flat structure the
PDF pipeline actually has (page/line ranges, change types) — no XML alignment,
since structural parity between the two pipelines is intentionally not a goal
(see plans/test-coverage-expansion.md). Failures here indicate the diff produced
something incoherent, not that a particular comparison is wrong.

Runs against every adjacent PDF version pair in the corpus. Marked @slow.
"""

from __future__ import annotations

import pytest
from pdf_corpus import adjacent_pdf_pairs, cached_pages

from diff_pdf import PageLineRange, PdfDiff, diff_pdfs

pytestmark = pytest.mark.slow

_VALID_CHANGE_TYPES = {"added", "removed", "modified", "moved"}
_OPEN_END_LINE = 10_000  # unnumbered (-1) end line sorts after any real line

_PAIRS = adjacent_pdf_pairs()


@pytest.fixture(scope="module")
def diff_for(request):
    """Cached PdfDiff per (old_pdf, new_pdf), reusing session-cached page extraction."""
    cache: dict[tuple, PdfDiff] = {}

    def _get(old_pdf, new_pdf) -> PdfDiff:
        key = (old_pdf, new_pdf)
        if key not in cache:
            cache[key] = diff_pdfs(cached_pages(old_pdf), cached_pages(new_pdf))
        return cache[key]

    return _get


def _norm_bounds(rng: PageLineRange) -> tuple[tuple[int, int], tuple[int, int]]:
    """(start, end) as (page, line) tuples, normalizing unnumbered (-1) lines."""
    sp, sl, ep, el = rng
    start = (sp, sl if sl >= 0 else 0)
    end = (ep, el if el >= 0 else _OPEN_END_LINE)
    return start, end


def _page_bounds(pages) -> tuple[int, int]:
    nums = [p.page_number for p in pages]
    return min(nums), max(nums)


@pytest.mark.parametrize(
    "bill,old_pdf,new_pdf",
    _PAIRS,
    ids=[f"{name}/{old.stem}->{new.stem}" for name, old, new in _PAIRS],
)
class TestPdfCorpusSmoke:
    def test_no_crash(self, bill, old_pdf, new_pdf, diff_for):
        diff = diff_for(old_pdf, new_pdf)
        assert isinstance(diff, PdfDiff)
        assert len(diff.hunks) > 0, "diff produced no hunks"

    def test_change_types_valid(self, bill, old_pdf, new_pdf, diff_for):
        diff = diff_for(old_pdf, new_pdf)
        for h in diff.hunks:
            assert h.change_type in _VALID_CHANGE_TYPES, f"bad change_type: {h.change_type!r}"

    def test_every_hunk_has_a_side(self, bill, old_pdf, new_pdf, diff_for):
        """A hunk must reference at least one side; both-None is a malformed hunk."""
        diff = diff_for(old_pdf, new_pdf)
        for h in diff.hunks:
            assert h.v1_range is not None or h.v2_range is not None, (
                f"hunk with no range on either side: {h.change_type}"
            )

    def test_change_type_matches_present_sides(self, bill, old_pdf, new_pdf, diff_for):
        """added => v2 only; removed => v1 only; modified/moved => both sides."""
        diff = diff_for(old_pdf, new_pdf)
        for h in diff.hunks:
            has_v1, has_v2 = h.v1_range is not None, h.v2_range is not None
            if h.change_type == "added":
                assert has_v2 and not has_v1, f"added hunk has v1 side: {h.v1_range}"
            elif h.change_type == "removed":
                assert has_v1 and not has_v2, f"removed hunk has v2 side: {h.v2_range}"
            else:  # modified / moved
                assert has_v1 and has_v2, f"{h.change_type} hunk missing a side"

    def test_ranges_well_formed(self, bill, old_pdf, new_pdf, diff_for):
        """Each present range stays within its document and is positionally ordered."""
        diff = diff_for(old_pdf, new_pdf)
        v1_lo, v1_hi = _page_bounds(cached_pages(old_pdf))
        v2_lo, v2_hi = _page_bounds(cached_pages(new_pdf))
        for h in diff.hunks:
            for rng, lo, hi, side in (
                (h.v1_range, v1_lo, v1_hi, "v1"),
                (h.v2_range, v2_lo, v2_hi, "v2"),
            ):
                if rng is None:
                    continue
                start, end = _norm_bounds(rng)
                assert start <= end, f"{side} range start after end: {rng}"
                assert lo <= rng[0] <= rng[2] <= hi, (
                    f"{side} range pages {rng[0]}-{rng[2]} outside document [{lo},{hi}]"
                )

    def test_no_overlapping_ranges_per_side(self, bill, old_pdf, new_pdf, diff_for):
        """Anchor-delimited blocks partition the lines, so ranges shouldn't overlap.

        Checked only for fully line-numbered ranges; unnumbered (-1) preamble
        blocks are skipped since their bounds are ambiguous.
        """
        diff = diff_for(old_pdf, new_pdf)
        for side in ("v1_range", "v2_range"):
            intervals = []
            for h in diff.hunks:
                rng = getattr(h, side)
                if rng is None or rng[1] < 0 or rng[3] < 0:
                    continue
                intervals.append(_norm_bounds(rng))
            intervals.sort()
            for (s1, e1), (s2, e2) in zip(intervals, intervals[1:]):
                assert s2 >= e1, f"{side} overlap: {(s1, e1)} and {(s2, e2)}"
