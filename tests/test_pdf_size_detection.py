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

from parsers.pdf_anchors import SizeBands, breadcrumb_for, derive_size_bands, extract_anchors
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
        "Confirmed NOT closeable by #103 (grouping headers): this input is "
        "structurally identical to test_multiline_section_catchline_continuation_"
        "not_account (SEC.@heading-size / heading-band run / body), so any rule that "
        "emits this account re-emits that false one. #104 (carry-over agencies) does "
        "NOT close it either: the catchline guard suppresses both MANAGEMENT "
        "DIRECTORATE and OPERATIONS AND SUPPORT before agency/account emission, so "
        "the account still never surfaces. Disambiguation needs the leveled tree "
        "(#108). Does not occur in the corpus (catchline wraps appear only in "
        "account-free authorization bills).",
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


def _by_kind(anchors, kind):
    return [a for a in anchors if a.kind == kind]


class TestGroupingHeaders:
    """Slice A of the #54 leveled-heading tree (DeltaTrack#103).

    A heading-band line whose next meaningful line is a `SEC.` section is a
    *grouping header* (ADMINISTRATIVE PROVISIONS, GENERAL PROVISIONS) — a
    header-only intermediate node owning a run of `SEC.` sections, not an account.
    Today the size path mislabels it `account` because in appropriations bills the
    SEC. line carries body prose ("SEC. 101. (a) The Secretary…") and renders at
    BODY size, so the look-ahead reads it as "followed by body."

    These synthetic fixtures mirror the real H.R. 8752 shape verified in the golden:
    a heading-band (HEAD) grouping line immediately followed by a body-size (BODY)
    `SEC.` line.
    """

    def _grouping_page(self):
        # TITLE I / a real account / a grouping header + its sections. TITLE is
        # detected by pattern regardless of size; the account and grouping are
        # heading-band; their following prose / SEC. lines are body-size.
        rows = [
            (1, "TITLE I", BODY),
            (2, "DEPARTMENTAL OPERATIONS", HEAD),  # real account (followed by body)
            (3, "For the salaries of the office, $100.", BODY),
            (4, "ADMINISTRATIVE PROVISIONS", HEAD),  # grouping (followed by SEC.)
            (5, "SEC. 101. (a) The Secretary shall act here.", BODY),
            (6, "continuing body prose for the section here", BODY),
            (7, "SEC. 102. Another provision follows in body.", BODY),
            (8, "more body prose for section 102 runs here", BODY),
        ]
        return _page(1, rows)

    def test_grouping_header_not_classified_as_account(self):
        anchors = extract_anchors([self._grouping_page()])
        account_names = {a.text for a in _by_kind(anchors, "account")}
        grouping_names = {a.text for a in _by_kind(anchors, "grouping")}
        assert "ADMINISTRATIVE PROVISIONS" not in account_names
        assert "ADMINISTRATIVE PROVISIONS" in grouping_names

    def test_grouping_header_sections_nest_under_it(self):
        anchors = extract_anchors([self._grouping_page()])
        sec_101 = next(a for a in anchors if a.kind == "section" and a.text == "SEC. 101")
        assert breadcrumb_for(sec_101, anchors) == ("TITLE I", "ADMINISTRATIVE PROVISIONS", "SEC. 101")
        sec_102 = next(a for a in anchors if a.kind == "section" and a.text == "SEC. 102")
        assert breadcrumb_for(sec_102, anchors) == ("TITLE I", "ADMINISTRATIVE PROVISIONS", "SEC. 102")

    def test_real_account_still_classified_account(self):
        # Regression guard: an in-band heading followed by appropriation prose (not a
        # SEC. line) is still an account, and does NOT pick up a grouping parent.
        anchors = extract_anchors([self._grouping_page()])
        account = next(a for a in anchors if a.kind == "account" and a.text == "DEPARTMENTAL OPERATIONS")
        assert breadcrumb_for(account, anchors) == ("TITLE I", "DEPARTMENTAL OPERATIONS")

    def test_section_without_grouping_keeps_title_only_breadcrumb(self):
        # A SEC. directly under a TITLE (general-provisions title, no grouping header)
        # keeps the 2-level breadcrumb; the grouping level is added only when present.
        rows = [
            (1, "TITLE V", BODY),
            (2, "SEC. 501. No part of any appropriation may be used.", BODY),
            (3, "continuing body prose for the section runs here", BODY),
            (4, "ANOTHER ACCOUNT NAME HERE", HEAD),
            (5, "For necessary prose at body size follows here now", BODY),
        ]
        anchors = extract_anchors([_page(1, rows)])
        sec = next(a for a in anchors if a.kind == "section" and a.text == "SEC. 501")
        assert breadcrumb_for(sec, anchors) == ("TITLE V", "SEC. 501")


class TestCarryoverAgencies:
    """Slice B of the #54 leveled-heading tree (DeltaTrack#104).

    A carry-over agency is a heading-band line (or a wrapped *run* of them) that
    spans >=2 accounts, e.g. ``MANAGEMENT DIRECTORATE`` over OPERATIONS AND SUPPORT
    + PROCUREMENT... These render in the heading band like accounts but are
    followed by *another* heading (the leaf account), not body prose. They are
    currently DROPPED (the size path emits only the leaf), so the XML's agency
    level (carried as the level-2 segment of the 4-level ``display_path``) has no
    PDF counterpart.

    These synthetic fixtures mirror the real H.R. 8752 shape verified in the golden
    (TestCarryoverAgenciesEndToEnd): a heading-band agency line (possibly wrapped
    across two heading lines) immediately followed by a heading-band leaf account
    whose own next line is body prose.
    """

    def test_single_line_agency_emitted_not_dropped(self):
        # MANAGEMENT DIRECTORATE is followed by another heading (the leaf account),
        # so it is an agency, not an account, and must be EMITTED (kind="agency").
        # Complements test_agency_parent_skipped, which only asserts it is not an
        # account; #104 additionally requires it to surface.
        rows = [
            (1, "TITLE I", BODY),
            (2, "MANAGEMENT DIRECTORATE", HEAD),  # agency (followed by a heading)
            (3, "OPERATIONS AND SUPPORT", HEAD),  # leaf account (followed by body)
            (4, "the body prose runs here now", BODY),
        ]
        anchors = extract_anchors([_page(1, rows)])
        agencies = _by_kind(anchors, "agency")
        assert any(a.text == "MANAGEMENT DIRECTORATE" and a.line_number == 2 for a in agencies)
        # the leaf is still an account; the agency did not steal it
        assert "OPERATIONS AND SUPPORT" in {a.text for a in _by_kind(anchors, "account")}
        assert "MANAGEMENT DIRECTORATE" not in {a.text for a in _by_kind(anchors, "account")}

    def test_wrapped_agency_name_joined_into_one_anchor(self):
        # THE wrap case (verified real on H.R. 8752): a long agency name wraps onto
        # a second heading-band line. The naive "heading-followed-by-heading=>agency"
        # rule would emit TWO fragment agencies ("OFFICE OF THE SECRETARY AND
        # EXECUTIVE" and "MANAGEMENT"); the correct result is ONE joined agency. The
        # leaf account is the last heading line of the run (the one before body).
        rows = [
            (1, "TITLE I", BODY),
            (2, "OFFICE OF THE SECRETARY AND EXECUTIVE", HEAD),  # wrap line 1
            (3, "MANAGEMENT", HEAD),  # wrap line 2 (completes the name)
            (4, "OPERATIONS AND SUPPORT", HEAD),  # leaf account
            (5, "the body prose runs here now", BODY),
        ]
        anchors = extract_anchors([_page(1, rows)])
        agencies = _by_kind(anchors, "agency")
        agency_names = {a.text for a in agencies}
        assert agency_names == {"OFFICE OF THE SECRETARY AND EXECUTIVE MANAGEMENT"}
        # neither wrap fragment leaks as its own agency or account
        all_names = {a.text for a in anchors}
        assert "MANAGEMENT" not in all_names
        assert "OFFICE OF THE SECRETARY AND EXECUTIVE" not in all_names
        assert "OPERATIONS AND SUPPORT" in {a.text for a in _by_kind(anchors, "account")}

    def test_agency_breadcrumb_three_levels(self):
        rows = [
            (1, "TITLE I", BODY),
            (2, "MANAGEMENT DIRECTORATE", HEAD),
            (3, "OPERATIONS AND SUPPORT", HEAD),
            (4, "the body prose runs here now", BODY),
        ]
        anchors = extract_anchors([_page(1, rows)])
        account = next(a for a in anchors if a.kind == "account" and a.text == "OPERATIONS AND SUPPORT")
        agency = next(a for a in anchors if a.kind == "agency" and a.text == "MANAGEMENT DIRECTORATE")
        assert breadcrumb_for(account, anchors) == ("TITLE I", "MANAGEMENT DIRECTORATE", "OPERATIONS AND SUPPORT")
        assert breadcrumb_for(agency, anchors) == ("TITLE I", "MANAGEMENT DIRECTORATE")

    def test_carryover_agency_spans_multiple_accounts(self):
        # One agency over two accounts: the agency anchor is emitted ONCE (before
        # the first account); the second account, preceded by body, has no agency
        # line of its own but still inherits the agency via breadcrumb walk-back.
        rows = [
            (1, "TITLE I", BODY),
            (2, "MANAGEMENT DIRECTORATE", HEAD),  # agency
            (3, "OPERATIONS AND SUPPORT", HEAD),  # account A
            (4, "the body prose for account A here", BODY),
            (5, "PROCUREMENT, CONSTRUCTION, AND IMPROVEMENTS", HEAD),  # account B
            (6, "the body prose for account B here", BODY),
        ]
        anchors = extract_anchors([_page(1, rows)])
        assert len(_by_kind(anchors, "agency")) == 1
        account_b = next(a for a in anchors if a.kind == "account" and a.text.startswith("PROCUREMENT"))
        assert breadcrumb_for(account_b, anchors) == (
            "TITLE I",
            "MANAGEMENT DIRECTORATE",
            "PROCUREMENT, CONSTRUCTION, AND IMPROVEMENTS",
        )

    def test_account_without_agency_keeps_two_level_breadcrumb(self):
        # Regression guard: an account directly under a TITLE (no preceding agency
        # heading run) keeps the 2-level chain and emits no agency.
        rows = [
            (1, "TITLE I", BODY),
            (2, "OPERATIONS AND SUPPORT", HEAD),  # account directly under title
            (3, "the body prose runs here now", BODY),
        ]
        anchors = extract_anchors([_page(1, rows)])
        assert _by_kind(anchors, "agency") == []
        account = next(a for a in anchors if a.kind == "account")
        assert breadcrumb_for(account, anchors) == ("TITLE I", "OPERATIONS AND SUPPORT")

    def test_wrapped_account_name_dangling_conjunction_not_emitted_as_agency(self):
        # A long ACCOUNT name that wraps across heading lines, its first line ending
        # on a conjunction ("...COMPLIANCE AND" / "RESTORATION"), must NOT surface as
        # an agency. JOIN cannot fully segment account-name wraps from agencies (that
        # is the #54/#108 tree), but a run that joins into a phrase ending in a
        # coordinating conjunction/preposition is a wrap fragment, never an agency —
        # suppress it. Verified real on 118-s-4795 ("construction and environmental
        # compliance and"). A genuine multi-word agency that does NOT dangle (NASA
        # here) is still emitted.
        rows = [
            (1, "TITLE I", BODY),
            (2, "NATIONAL AERONAUTICS AND SPACE ADMINISTRATION", HEAD),  # real agency
            (3, "OPERATIONS AND SUPPORT", HEAD),  # its leaf account
            (4, "the body prose for operations here now", BODY),
            (5, "CONSTRUCTION AND ENVIRONMENTAL COMPLIANCE AND", HEAD),  # account wrap line 1
            (6, "RESTORATION", HEAD),  # account wrap line 2 (the leaf)
            (7, "the body prose for restoration here now", BODY),
        ]
        anchors = extract_anchors([_page(1, rows)])
        agency_names = {a.text for a in _by_kind(anchors, "agency")}
        assert "NATIONAL AERONAUTICS AND SPACE ADMINISTRATION" in agency_names
        assert "CONSTRUCTION AND ENVIRONMENTAL COMPLIANCE AND" not in agency_names
        assert not any(a.text.rstrip().upper().endswith(" AND") for a in _by_kind(anchors, "agency"))

    def test_agency_scope_resets_at_grouping_boundary(self):
        # Over-attachment guard (fresh-eyes P1/C6): an account that appears AFTER a
        # grouping header's sections must NOT inherit an agency from before the
        # grouping. The breadcrumb walk-back stops at the grouping/section boundary,
        # so this account is title-level, not agency-scoped.
        rows = [
            (1, "TITLE I", BODY),
            (2, "MANAGEMENT DIRECTORATE", HEAD),  # agency
            (3, "OPERATIONS AND SUPPORT", HEAD),  # account under the agency
            (4, "the body prose for the account here", BODY),
            (5, "ADMINISTRATIVE PROVISIONS", HEAD),  # grouping header
            (6, "SEC. 101. (a) The Secretary shall act here.", BODY),
            (7, "more body prose for the section here", BODY),
            (8, "WORKING CAPITAL FUND", HEAD),  # title-level account after the grouping
            (9, "the body prose for the later account", BODY),
        ]
        anchors = extract_anchors([_page(1, rows)])
        later = next(a for a in anchors if a.kind == "account" and a.text == "WORKING CAPITAL FUND")
        assert breadcrumb_for(later, anchors) == ("TITLE I", "WORKING CAPITAL FUND")


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
