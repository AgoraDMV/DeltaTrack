"""Size-based heading detection: band derivation + position classification (#89).

These use SYNTHETIC glyph sizes to exercise the classifier/position logic in
isolation. They are NOT the proof that real PDFs produce the bands (that is
tests/test_pdf_text.py::TestPageGlyphSizes) nor the end-to-end fix (that is the
FEDERAL PROTECTIVE SERVICE test in test_pdf_anchor_golden.py). Body text is
deliberately non-"For necessary expenses" so detection cannot fall through to the
legacy trigger — only the size path can satisfy these.
"""

from __future__ import annotations

import pytest

from parsers.pdf_anchors import SizeBands, derive_size_bands, extract_anchors
from parsers.pdf_text import Line, Page

BODY = 14.0
HEAD = 11.2


def _page(page_number: int, rows: list[tuple[int | None, str, float | None]]) -> Page:
    return Page(page_number, tuple(Line(ln, txt, sz) for ln, txt, sz in rows))


class TestDeriveSizeBands:
    def test_bimodal_returns_bands(self):
        pages = [
            _page(
                1,
                [
                    (1, "OPERATIONS AND SUPPORT", HEAD),
                    (2, "the body prose runs here at body size", BODY),
                    (3, "PROCUREMENT AND IMPROVEMENTS", HEAD),
                    (4, "more body prose at the body size", BODY),
                ],
            )
        ]
        bands = derive_size_bands(pages)
        assert bands is not None
        assert bands.body == BODY
        assert bands.heading_lo <= HEAD <= bands.heading_hi

    def test_flat_returns_none(self):
        pages = [_page(1, [(1, "all body prose one size", BODY), (2, "more prose", BODY)])]
        assert derive_size_bands(pages) is None

    def test_trimodal_returns_none(self):
        # Reconciliation-style mixed heading sizes (e.g. 119-hr-1: 10 / 11.2 / 12).
        pages = [
            _page(
                1,
                [
                    (1, "HEADING A", 10.0),
                    (2, "HEADING B", 11.2),
                    (3, "HEADING C", 12.0),
                    (4, "body prose at body size here", BODY),
                    (5, "ALT HEADING A", 10.0),
                    (6, "ALT HEADING C", 12.0),
                    (7, "more body prose here now", BODY),
                ],
            )
        ]
        assert derive_size_bands(pages) is None

    def test_no_lowercase_returns_none(self):
        pages = [_page(1, [(1, "ALL CAPS NO BODY", HEAD), (2, "STILL ALL CAPS", HEAD)])]
        assert derive_size_bands(pages) is None

    def test_insufficient_separation_returns_none(self):
        # body 14.0, heading 13.5: gap 0.5 <= 2*eps (0.6) -> not disjoint -> None.
        pages = [_page(1, [(1, "HEADING NEAR BODY", 13.5), (2, "body prose at body size", BODY)])]
        assert derive_size_bands(pages) is None


def _accounts(anchors):
    return [a for a in anchors if a.kind == "account"]


class TestSizePositionClassification:
    def test_leaf_account_followed_by_body(self):
        pages = [
            _page(
                1,
                [
                    (1, "OPERATIONS AND SUPPORT", HEAD),
                    (2, "the body prose follows immediately here", BODY),
                ],
            )
        ]
        accounts = _accounts(extract_anchors(pages))
        assert any(a.text == "OPERATIONS AND SUPPORT" and a.line_number == 1 for a in accounts)

    def test_agency_parent_skipped(self):
        # Agency heading (followed by another band heading) is NOT an account;
        # only the leaf (band line immediately before body) is emitted.
        pages = [
            _page(
                1,
                [
                    (1, "MANAGEMENT DIRECTORATE", HEAD),  # agency parent
                    (2, "OPERATIONS AND SUPPORT", HEAD),  # leaf account
                    (3, "the body prose runs here now", BODY),
                ],
            )
        ]
        accounts = _accounts(extract_anchors(pages))
        texts = {a.text for a in accounts}
        assert "OPERATIONS AND SUPPORT" in texts
        assert "MANAGEMENT DIRECTORATE" not in texts

    def test_account_at_page_seam(self):
        # Heading is the last line of page 1; its body opens page 2. The anchor
        # must take page 1 (the heading's own page), found via the flattened stream.
        pages = [
            _page(1, [(20, "FEDERAL PROTECTIVE SERVICE", HEAD)]),
            _page(2, [(1, "the revenues and collections of fees", BODY)]),
        ]
        accounts = _accounts(extract_anchors(pages))
        assert any(
            a.text == "FEDERAL PROTECTIVE SERVICE" and a.page_number == 1 and a.line_number == 20 for a in accounts
        )

    def test_blank_line_between_heading_and_body(self):
        pages = [
            _page(
                1,
                [
                    (1, "OPERATIONS AND SUPPORT", HEAD),
                    (None, "", None),
                    (2, "body prose after a blank line", BODY),
                ],
            )
        ]
        assert any(a.text == "OPERATIONS AND SUPPORT" for a in _accounts(extract_anchors(pages)))

    def test_parenthetical_qualifier_not_account_and_transparent(self):
        # account / (qualifier) / body: the qualifier is a rider, not an account,
        # and must not block the real account (which precedes it) from emission.
        pages = [
            _page(
                1,
                [
                    (1, "OPERATIONS AND SUPPORT", HEAD),
                    (2, "(INCLUDING TRANSFER OF FUNDS)", HEAD),
                    (3, "the body prose runs here now", BODY),
                ],
            )
        ]
        names = {a.text for a in _accounts(extract_anchors(pages))}
        assert "OPERATIONS AND SUPPORT" in names
        assert "(INCLUDING TRANSFER OF FUNDS)" not in names

    def test_section_catchline_continuation_not_account(self):
        # A long SEC. catchline wraps onto a heading-band line that, alone, reads as
        # an uppercase heading followed by body — a false account (#89, repro bills
        # 117-hr-2471 / 118-hr-2882). The continuation belongs to the SEC. line and
        # must emit no anchor; the surrounding real account still must.
        rows = [
            (1, "SEC. 5. ACTIONS TO PROMOTE FREEDOM OF THE PRESS", HEAD),
            (2, "AND ASSEMBLY IN HAITI.", HEAD),
            (3, "body prose of the section follows here", BODY),
            (4, "OPERATIONS AND SUPPORT", HEAD),
            (5, "the real account body prose runs here", BODY),
        ]
        rows += [(n, f"more body prose line {n}", BODY) for n in range(6, 16)]
        names = {a.text for a in _accounts(extract_anchors([_page(1, rows)]))}
        assert "AND ASSEMBLY IN HAITI." not in names
        assert "OPERATIONS AND SUPPORT" in names

    def test_real_heading_after_section_with_body_still_emitted(self):
        # The mechanism that keeps the catchline guard safe (#89): a body line
        # between a SEC. and a later heading STOPS the walk-back, so a real account
        # after a section's body is never mistaken for a catchline continuation.
        # This is the realistic GPO layout — appropriations SECs carry body prose
        # ("SEC. 101. (a) The Secretary...") — so the false-skip cannot reach them.
        rows = [
            (1, "SEC. 5. ACTIONS TO PROMOTE FREEDOM OF THE PRESS", HEAD),
            (2, "AND ASSEMBLY IN HAITI.", HEAD),  # catchline continuation (suppressed)
            (3, "body prose of the section runs here now", BODY),
            (4, "OPERATIONS AND SUPPORT", HEAD),  # real account, separated by body
            (5, "the account body prose follows here", BODY),
        ]
        rows += [(n, f"more body prose line {n}", BODY) for n in range(6, 16)]
        names = {a.text for a in _accounts(extract_anchors([_page(1, rows)]))}
        assert "AND ASSEMBLY IN HAITI." not in names
        assert "OPERATIONS AND SUPPORT" in names

    @pytest.mark.xfail(
        reason="Known #89 residual deferred to #54: a SEC. catchline directly "
        "abutting an agency heading with NO body between false-skips the account. "
        "Needs the leveled tree to disambiguate; does not occur in the corpus "
        "(catchline wraps appear only in account-free authorization bills). This "
        "xfail makes the limitation visible and flips to pass when #54 closes it.",
        strict=True,
    )
    def test_account_directly_after_section_catchline_no_body(self):
        # Pathological, currently-unhandled: SEC. catchline / AGENCY / ACCOUNT / body
        # with no body separating the SEC. from the account chain. The walk-back
        # reaches the SEC. through the AGENCY heading and wrongly suppresses ACCOUNT.
        rows = [
            (1, "SEC. 5. A CATCHLINE WITHOUT A TRAILING SECTION", HEAD),
            (2, "MANAGEMENT DIRECTORATE", HEAD),  # agency heading (no body before it)
            (3, "OPERATIONS AND SUPPORT", HEAD),  # real account, wrongly skipped today
            (4, "the account body prose follows here", BODY),
        ]
        rows += [(n, f"more body prose line {n}", BODY) for n in range(5, 15)]
        names = {a.text for a in _accounts(extract_anchors([_page(1, rows)]))}
        assert "OPERATIONS AND SUPPORT" in names

    def test_multiline_section_catchline_continuation_not_account(self):
        # A catchline wrapping onto two heading-band lines: both continuations must
        # be suppressed, not just the one adjacent to the SEC. line.
        rows = [
            (1, "SEC. 7. A VERY LONG SECTION TITLE THAT WRAPS", HEAD),
            (2, "ACROSS SEVERAL PRINTED HEADING LINES", HEAD),
            (3, "AND KEEPS GOING TO A THIRD LINE.", HEAD),
            (4, "the section body prose begins here now", BODY),
        ]
        rows += [(n, f"more body prose line {n}", BODY) for n in range(5, 15)]
        names = {a.text for a in _accounts(extract_anchors([_page(1, rows)]))}
        assert "ACROSS SEVERAL PRINTED HEADING LINES" not in names
        assert "AND KEEPS GOING TO A THIRD LINE." not in names

    def test_unattached_next_line_treated_as_body(self):
        # A band heading whose following line has no size (join miss) is emitted
        # conservatively as an account (skipping toward the next heading would
        # wrongly drop a leaf).
        # One unattached line among many; document coverage stays above the gate.
        rows = [
            (1, "OPERATIONS AND SUPPORT", HEAD),
            (2, "UNATTACHED LINE NO SIZE", None),
            (3, "body prose at body size here", BODY),
        ]
        rows += [(n, f"more body prose line {n}", BODY) for n in range(4, 14)]
        pages = [_page(1, rows)]
        assert any(a.text == "OPERATIONS AND SUPPORT" for a in _accounts(extract_anchors(pages)))


class TestFallbackWhenNoBands:
    def test_legacy_trigger_used_when_no_sizes(self):
        # No glyph sizes (e.g. a draft/odd PDF): derive_size_bands -> None, so the
        # legacy "For necessary expenses" backwalk still finds the account.
        pages = [
            Page(
                1,
                (
                    Line(1, "OPERATIONS AND SUPPORT"),
                    Line(2, "For necessary expenses of the agency, $1,000."),
                ),
            )
        ]
        assert isinstance(derive_size_bands(pages), (type(None), SizeBands))
        accounts = _accounts(extract_anchors(pages))
        assert any(a.text == "OPERATIONS AND SUPPORT" for a in accounts)
