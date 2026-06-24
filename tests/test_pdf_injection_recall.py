"""Synthetic-injection recall: does sneaked-in language get detected AND shown?

The threat model is someone slipping new text into a bill at the last minute (a
rider, earmark, or clause). This test turns the structural guarantee of the diff
engine into an executable check: we start from a real v1 (HR 8752 reported), inject
uniquely-tokenized phrases at distinct locations to build a synthetic v2, run
`diff_pdfs`, and assert each sentinel surfaces in two places:

  1. Detection: some hunk carries the sentinel in its changed-side text.
  2. Display: the sentinel appears in the rendered HTML.

The sentinels are nonsense tokens (`ZZQ...`) so they can't collide with real bill
text and survive HTML escaping unchanged. All scenarios are expected to pass; a
failure is a real detection-or-display gap, to be documented in
plans/pdf-text-diff-findings.md rather than worked around.
"""

from __future__ import annotations

import pytest
from recall_text import normalize_for_recall

from diff_pdf import PdfDiff, diff_pdfs
from formatters.canonical import pdf_diff_to_canonical, view_from_canonical
from formatters.diff_html import format_diff_html
from parsers.pdf_anchors import extract_anchors
from parsers.pdf_text import Line, Page


def pdf_diff_to_view(diff: PdfDiff, **meta):
    """Route the PdfDiff through canonical -> view, the sole production path."""
    return view_from_canonical(pdf_diff_to_canonical(diff, **meta))


# ---- Injection helpers (operate on the frozen Page/Line dataclasses) ---------


def _page_line_index(pages: list[Page], page_number: int, line_number: int) -> int:
    """Index of the line with `line_number` within page `page_number`'s tuple."""
    page = next(p for p in pages if p.page_number == page_number)
    for i, ln in enumerate(page.lines):
        if ln.line_number == line_number:
            return i
    raise ValueError(f"line {line_number} not found on page {page_number}")


def _inject(pages: list[Page], page_number: int, at_index: int, new_lines: list[Line]) -> list[Page]:
    """Return a new page list with `new_lines` spliced into `page_number` at `at_index`."""
    out: list[Page] = []
    for p in pages:
        if p.page_number == page_number:
            lines = list(p.lines)
            lines[at_index:at_index] = new_lines
            p = Page(p.page_number, tuple(lines))
        out.append(p)
    return out


def _append_page(pages: list[Page], page_number: int, lines: list[Line]) -> list[Page]:
    return [*pages, Page(page_number, tuple(lines))]


def _insert_page_before(pages: list[Page], before_page_number: int, page_number: int, lines: list[Line]) -> list[Page]:
    """Insert a new page into the list immediately before `before_page_number`.

    A standalone page keeps the injected `SEC.` anchor's (page, line) key unique
    and its document order correct (anchors are sorted by line number *within* a
    page, so a high synthetic line number on a real page would sort wrong).
    """
    idx = next(i for i, p in enumerate(pages) if p.page_number == before_page_number)
    return [*pages[:idx], Page(page_number, tuple(lines)), *pages[idx:]]


# ---- Scenario builders -------------------------------------------------------


def _build_synthetic_v2(v1_pages: list[Page]) -> list[Page]:
    """Apply all injection scenarios to a copy of v1, returning synthetic v2 pages.

    Each scenario plants one nonsense sentinel at a distinct location, exercising
    a different code path in diff_pdf. Injections are keyed by (page, line) lookup
    on the current page list, so they're order-independent.
    """
    pages = list(v1_pages)
    anchors = extract_anchors(pages)
    sections = [a for a in anchors if a.kind == "section"]
    proc = next(a for a in anchors if a.kind == "account" and a.text.startswith("PROCUREMENT"))
    last_page_no = max(p.page_number for p in pages)

    # Scenario 1 — new section appended at the end of the document (clean `added`).
    pages = _append_page(
        pages,
        last_page_no + 1,
        [
            Line(1, "SEC. 999. None of the funds made available by this Act may be"),
            Line(2, "used for the ZZQALPHA demonstration program described in this"),
            Line(3, "section."),
        ],
    )

    # Scenario 2 — new section inserted mid-document, on its own page, just before
    # the first existing SEC. anchor. New anchor key => `added` hunk.
    pages = _insert_page_before(
        pages,
        sections[0].page_number,
        900,
        [
            Line(1, "SEC. 998. None of the funds appropriated by this Act may be used"),
            Line(2, "to implement the ZZQBRAVO initiative without prior approval of the"),
            Line(3, "Committees on Appropriations."),
        ],
    )

    # Scenario 3 — small clause inserted into an existing section body (stays well
    # above the 0.4 similarity floor => `modified`, with the sentinel inline).
    sec102 = sections[1]
    idx = _page_line_index(pages, sec102.page_number, sec102.line_number)
    pages = _inject(
        pages,
        sec102.page_number,
        idx + 1,
        [Line(None, "Provided further, That $1 shall be available for the ZZQCHARLIE program: ")],
    )

    # Scenario 4 — large insertion into a small account block, enough to drop the
    # block below the 0.4 split threshold and exercise the removed+added split path.
    idx = _page_line_index(pages, proc.page_number, proc.line_number)
    bulk = [
        Line(
            None, f"Provided further, That additional ZZQDELTA appropriations are made available under paragraph {n}: "
        )
        for n in range(60)
    ]
    pages = _inject(pages, proc.page_number, idx + 1, bulk)

    # Scenario 5 — insertion into the preamble (before the first anchor) => the
    # preamble block is `modified` and carries the sentinel.
    pages = _inject(
        pages,
        1,
        1,
        [Line(None, "Be it enacted that the ZZQECHO clause is hereby inserted into this measure. ")],
    )

    return pages


# ---- Fixture: build synthetic v2 once and diff it ----------------------------


@pytest.fixture(scope="module")
def injected_diff(hr8752_v1_pages) -> PdfDiff:
    v2 = _build_synthetic_v2(hr8752_v1_pages)
    return diff_pdfs(hr8752_v1_pages, v2)


@pytest.fixture(scope="module")
def injected_html(injected_diff: PdfDiff) -> str:
    view = pdf_diff_to_view(injected_diff, bill_type="hr", bill_number=8752, congress=118)
    return format_diff_html(view)


# ---- Cases: (sentinel, allowed change types) ---------------------------------

_CASES = [
    pytest.param("ZZQALPHA", {"added"}, id="new-section-end"),
    pytest.param("ZZQBRAVO", {"added"}, id="new-section-mid"),
    pytest.param("ZZQCHARLIE", {"modified"}, id="small-clause"),
    # Large insertion lands as `added` after the split, or `modified` if the block
    # stays above 0.4 — the sentinel surfacing is what matters, not which side.
    pytest.param("ZZQDELTA", {"added", "modified"}, id="large-insertion-split"),
    pytest.param("ZZQECHO", {"modified"}, id="preamble"),
]


def _hunks_with_sentinel(diff: PdfDiff, sentinel: str) -> list:
    """Hunks whose changed-side text contains the sentinel (normalized)."""
    norm = normalize_for_recall(sentinel)
    out = []
    for h in diff.hunks:
        side = normalize_for_recall(h.v2_text) if h.v2_text else ""
        if norm in side:
            out.append(h)
    return out


@pytest.mark.parametrize("sentinel,allowed_types", _CASES)
class TestInjectionRecall:
    def test_detected_in_a_hunk(self, sentinel: str, allowed_types: set[str], injected_diff: PdfDiff):
        hits = _hunks_with_sentinel(injected_diff, sentinel)
        assert hits, f"{sentinel}: not found in any hunk's changed text — injection went undetected"
        types = {h.change_type for h in hits}
        assert types & allowed_types, f"{sentinel}: found in hunks of type {types}, expected one of {allowed_types}"

    def test_shown_in_html(self, sentinel: str, allowed_types: set[str], injected_html: str):
        assert sentinel in injected_html, f"{sentinel}: detected but not rendered in HTML — change would be hidden"


# ---- Case #8 (issue #58): amount moved between accounts, and clause deletion -----------
#
# The scenarios above prove sneaked-in language surfaces. Two sneak shapes they do NOT
# cover: an amount MOVED from one account to another (the value is still *present*
# somewhere, so an amount-recall-by-presence check passes blind — exactly the kind of
# shift that nets to zero on a naive total), and an outright DELETION. Both must surface
# as visible, located changes, not be silently absorbed.

from types import SimpleNamespace  # noqa: E402

from diff_bill import extract_amounts  # noqa: E402

# Distinctive (non-round) amounts so the deletion check can assert the value is genuinely
# gone from v2 without colliding with a real figure in the bill. The ZZQ sentinel words
# make each injected line uniquely findable; the amount is what a presence check sees.
_MOVE_SENTINEL = "ZZQMOVE"
_MOVE_AMOUNT = 13_570_313
_MOVE_LINE = Line(
    None, f"Provided further, That ${_MOVE_AMOUNT:,} shall be available for the {_MOVE_SENTINEL} program: "
)

_DEL_SENTINEL = "ZZQGONE"
_DEL_AMOUNT = 17_936_271
_DEL_LINE = Line(None, f"Provided further, That ${_DEL_AMOUNT:,} shall be available for the {_DEL_SENTINEL} program: ")


def _full_text(pages: list[Page]) -> str:
    return "\n".join(p.text for p in pages)


def _inject_after_anchor(pages: list[Page], anchor, new_lines: list[Line]) -> list[Page]:
    """Splice `new_lines` into the body of `anchor`'s block (just after the anchor line)."""
    idx = _page_line_index(pages, anchor.page_number, anchor.line_number)
    return _inject(pages, anchor.page_number, idx + 1, new_lines)


def _two_distinct_accounts(pages: list[Page]):
    """Two account anchors with different headings, to move an amount between them."""
    accounts = [a for a in extract_anchors(pages) if a.kind == "account"]
    src = next(a for a in accounts if a.text.startswith("PROCUREMENT"))
    dst = next(a for a in accounts if a.text.startswith("OPERATIONS"))
    return src, dst


def _has(text: str, sentinel: str) -> bool:
    return normalize_for_recall(sentinel) in normalize_for_recall(text)


@pytest.fixture(scope="module")
def moved(hr8752_v1_pages):
    """An amount present in PROCUREMENT in v1 and in OPERATIONS in v2 (moved, not changed)."""
    src, dst = _two_distinct_accounts(hr8752_v1_pages)
    v1 = _inject_after_anchor(list(hr8752_v1_pages), src, [_MOVE_LINE])
    v2 = _inject_after_anchor(list(hr8752_v1_pages), dst, [_MOVE_LINE])
    return SimpleNamespace(diff=diff_pdfs(v1, v2), v1=v1, v2=v2, src=src, dst=dst)


@pytest.fixture(scope="module")
def deleted(hr8752_v1_pages):
    """A clause present in v1 and removed entirely in v2."""
    src, _ = _two_distinct_accounts(hr8752_v1_pages)
    v1 = _inject_after_anchor(list(hr8752_v1_pages), src, [_DEL_LINE])
    v2 = list(hr8752_v1_pages)  # never injected → the clause is deleted in v2
    return SimpleNamespace(diff=diff_pdfs(v1, v2), v1=v1, v2=v2, src=src)


class TestAmountMovedBetweenAccounts:
    def test_presence_check_alone_would_miss_it(self, moved):
        """Setup validity: the moved amount is in BOTH versions, so a presence-only
        check passes blind. This is what makes localizing the move necessary."""
        assert _MOVE_AMOUNT in extract_amounts(_full_text(moved.v1))
        assert _MOVE_AMOUNT in extract_amounts(_full_text(moved.v2))

    def test_source_account_shows_the_loss(self, moved):
        src_hunks = [
            h for h in moved.diff.hunks if _has(h.v1_text, _MOVE_SENTINEL) and not _has(h.v2_text, _MOVE_SENTINEL)
        ]
        assert src_hunks, "moved amount's source account did not surface the loss"

    def test_destination_account_shows_the_gain(self, moved):
        dst_hunks = [
            h for h in moved.diff.hunks if _has(h.v2_text, _MOVE_SENTINEL) and not _has(h.v1_text, _MOVE_SENTINEL)
        ]
        assert dst_hunks, "moved amount's destination account did not surface the gain"

    def test_loss_and_gain_are_different_accounts(self, moved):
        src = next(
            h for h in moved.diff.hunks if _has(h.v1_text, _MOVE_SENTINEL) and not _has(h.v2_text, _MOVE_SENTINEL)
        )
        dst = next(
            h for h in moved.diff.hunks if _has(h.v2_text, _MOVE_SENTINEL) and not _has(h.v1_text, _MOVE_SENTINEL)
        )
        src_key = (src.v1_anchor.page_number, src.v1_anchor.line_number)
        dst_key = (dst.v2_anchor.page_number, dst.v2_anchor.line_number)
        assert src_key != dst_key, "loss and gain collapsed onto the same account block"

    def test_move_shown_in_html(self, moved):
        view = pdf_diff_to_view(moved.diff, bill_type="hr", bill_number=8752, congress=118)
        html = format_diff_html(view)
        assert _MOVE_SENTINEL in html, "moved amount detected but not rendered in HTML"


class TestClauseDeletion:
    def test_deletion_is_genuine(self, deleted):
        """The amount is in v1 and truly absent from v2 (a real removal, not a move)."""
        assert _DEL_AMOUNT in extract_amounts(_full_text(deleted.v1))
        assert _DEL_AMOUNT not in extract_amounts(_full_text(deleted.v2))

    def test_deletion_surfaces_in_a_hunk(self, deleted):
        hits = [h for h in deleted.diff.hunks if _has(h.v1_text, _DEL_SENTINEL) and not _has(h.v2_text, _DEL_SENTINEL)]
        assert hits, "deleted clause did not surface as a removal in any hunk"

    def test_deletion_shown_in_html(self, deleted):
        view = pdf_diff_to_view(deleted.diff, bill_type="hr", bill_number=8752, congress=118)
        html = format_diff_html(view)
        assert _DEL_SENTINEL in html, "deleted clause detected but not rendered in HTML"
