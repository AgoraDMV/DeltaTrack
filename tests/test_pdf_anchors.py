"""Unit tests for PDF anchor extraction.

Anchors are landmark labels (`TITLE`, `SEC.`, account headings) that the PDF
reliably carries and the diff layer attaches to hunks as a "where am I" label.
"""

from __future__ import annotations

from parsers.pdf_anchors import Anchor, _scan_anchors_in_page, breadcrumb_for


class TestTitleAnchor:
    def test_simple_title(self):
        text = "1 some preamble\n7 TITLE I\n8 DEPARTMENTAL MANAGEMENT"
        anchors = _scan_anchors_in_page(2, text)
        assert Anchor(2, 7, "title", "TITLE I") in anchors

    def test_title_with_higher_numerals(self):
        text = "3 TITLE IV\n4 RESEARCH AND DEVELOPMENT"
        anchors = _scan_anchors_in_page(40, text)
        titles = [a for a in anchors if a.kind == "title"]
        assert titles == [Anchor(40, 3, "title", "TITLE IV")]

    def test_title_must_be_at_line_start(self):
        text = "1 within the TITLE I provisions, certain things apply"
        anchors = _scan_anchors_in_page(5, text)
        assert not any(a.kind == "title" for a in anchors)


class TestSectionAnchor:
    def test_three_digit_section(self):
        text = "5 SEC. 406. Notwithstanding the numerical limitation"
        anchors = _scan_anchors_in_page(61, text)
        sections = [a for a in anchors if a.kind == "section"]
        assert sections == [Anchor(61, 5, "section", "SEC. 406")]

    def test_section_word_form(self):
        text = "1 SECTION 1. Short title"
        anchors = _scan_anchors_in_page(1, text)
        sections = [a for a in anchors if a.kind == "section"]
        assert sections == [Anchor(1, 1, "section", "SECTION 1")]

    def test_section_must_be_at_line_start(self):
        # `section 287(g)` mid-paragraph is a citation, not a heading.
        text = "12 the delegation of law enforcement authority provided by section 287(g)"
        anchors = _scan_anchors_in_page(15, text)
        assert not any(a.kind == "section" for a in anchors)


class TestAccountAnchor:
    def test_uppercase_heading_before_for_necessary_expenses(self):
        # A common GPO pattern: an all-caps account heading followed within
        # a few lines by `For necessary expenses of …`.
        text = (
            "11 OFFICE OF THE SECRETARY AND EXECUTIVE\n"
            "12 MANAGEMENT\n"
            "13 OPERATIONS AND SUPPORT\n"
            "14 For necessary expenses of the Office of the Secretary"
        )
        anchors = _scan_anchors_in_page(2, text)
        accounts = [a for a in anchors if a.kind == "account"]
        # The heading immediately preceding `For necessary expenses of` is the
        # closest account label. The plan accepts misses; require at least one
        # uppercase heading line is found and stored as an account.
        assert any(a.text == "OPERATIONS AND SUPPORT" for a in accounts)

    def test_no_account_when_no_for_necessary_expenses(self):
        # Without the trigger phrase, uppercase lines may be titles or other
        # display headings; the heuristic should not produce account anchors.
        text = "7 TITLE I\n8 DEPARTMENTAL MANAGEMENT, INTEL-\n9 LIGENCE"
        anchors = _scan_anchors_in_page(2, text)
        assert not any(a.kind == "account" for a in anchors)

    def test_account_heading_below_section_break(self):
        text = (
            "5 SEC. 101. Short title.\n"
            "6 U.S. CUSTOMS AND BORDER PROTECTION\n"
            "7 OPERATIONS AND SUPPORT\n"
            "8 For necessary expenses of U.S. Customs and Border Protection"
        )
        anchors = _scan_anchors_in_page(11, text)
        accounts = [a for a in anchors if a.kind == "account"]
        assert any(a.text == "OPERATIONS AND SUPPORT" for a in accounts)


class TestPageChromeIgnored:
    def test_top_of_page_number_does_not_become_anchor(self):
        # Standalone page number at top
        text = "63\n1 SEC. 414. None of the funds"
        anchors = _scan_anchors_in_page(63, text)
        # Only the SEC. anchor; no spurious title/account from the bare "63"
        assert anchors == [Anchor(63, 1, "section", "SEC. 414")]

    def test_footer_chrome_does_not_become_anchor(self):
        text = "5 SEC. 200. text\n•HR 8752 RH\nVerDate Sep 11 2014 23:10 Jun 14, 2024 Jkt 049200"
        anchors = _scan_anchors_in_page(20, text)
        # The SEC. anchor is found; •HR/VerDate lines yield nothing.
        assert anchors == [Anchor(20, 5, "section", "SEC. 200")]


class TestBreadcrumb:
    def test_preamble_anchor_is_top_level_front_matter(self):
        # A synthesized front-matter anchor (issue #33) is top-level like TITLE:
        # its breadcrumb is just itself, with no parent walk-back.
        preamble = Anchor(1, 1, "preamble", "Front Matter")
        section = Anchor(2, 5, "section", "SEC. 101")
        assert breadcrumb_for(preamble, (preamble, section)) == ("Front Matter",)


def _by(anchors, kind, text):
    """The single anchor of (kind, text), for readable assertions."""
    hits = [a for a in anchors if a.kind == kind and a.text == text]
    assert len(hits) == 1, f"expected one {kind} {text!r}, got {hits}"
    return hits[0]


class TestDivision:
    """Division level for omnibus/minibus bills (DeltaTrack#107).

    A division is a top-level grouping (`DIVISION A—…`) that stitches several
    appropriations acts into one omnibus, each with its OWN `TITLE I…`. Without a
    division level the same-numbered titles collapse. Division is a display-only
    FIELD on the anchor (never a matching key), prepended as the leftmost breadcrumb
    segment — mirroring the XML `division_label`.
    """

    def test_division_field_assigned_by_nearest_preceding_banner(self):
        text = (
            "1 DIVISION A—ENERGY AND WATER\n"
            "2 TITLE I\n"
            "3 SEC. 101. Corps of Engineers text.\n"
            "4 DIVISION B—LEGISLATIVE BRANCH\n"
            "5 TITLE I\n"
            "6 SEC. 201. House of Representatives text."
        )
        anchors = _scan_anchors_in_page(1, text)
        assert _by(anchors, "section", "SEC. 101").division == "Division A: ENERGY AND WATER"
        assert _by(anchors, "section", "SEC. 201").division == "Division B: LEGISLATIVE BRANCH"
        # Both TITLE I anchors exist but belong to different divisions.
        titles = [a for a in anchors if a.kind == "title"]
        assert {t.division for t in titles} == {
            "Division A: ENERGY AND WATER",
            "Division B: LEGISLATIVE BRANCH",
        }

    def test_breadcrumb_prepends_division_for_section_and_title(self):
        text = (
            "1 DIVISION A—ENERGY AND WATER\n"
            "2 TITLE I\n"
            "3 SEC. 101. Corps text.\n"
            "4 DIVISION B—LEGISLATIVE BRANCH\n"
            "5 TITLE I\n"
            "6 SEC. 201. House text."
        )
        anchors = _scan_anchors_in_page(1, text)
        sec_101 = _by(anchors, "section", "SEC. 101")
        sec_201 = _by(anchors, "section", "SEC. 201")
        title_a = next(a for a in anchors if a.kind == "title" and a.division.startswith("Division A"))
        assert breadcrumb_for(sec_101, anchors) == ("Division A: ENERGY AND WATER", "TITLE I", "SEC. 101")
        assert breadcrumb_for(sec_201, anchors) == ("Division B: LEGISLATIVE BRANCH", "TITLE I", "SEC. 201")
        # The title early-return path must prepend the division too (fresh-eyes #1).
        assert breadcrumb_for(title_a, anchors) == ("Division A: ENERGY AND WATER", "TITLE I")

    def test_name_recovery_dehyphenates_all_caps_wrap(self):
        # GPO wraps a long all-caps division name with soft hyphens; the continuation
        # is UPPERCASE (so the lowercase-only soft-hyphen rejoin never fires here).
        text = (
            "1 DIVISION A—AGRICULTURE, RURAL DEVELOP-\n"
            "2 MENT, AND RELATED AGENCIES APPROPRIA-\n"
            "3 TIONS ACT, 2024\n"
            "4 TITLE I\n"
            "5 SEC. 101. text."
        )
        anchors = _scan_anchors_in_page(1, text)
        assert (
            _by(anchors, "section", "SEC. 101").division
            == "Division A: AGRICULTURE, RURAL DEVELOPMENT, AND RELATED AGENCIES APPROPRIATIONS ACT, 2024"
        )

    def test_name_recovery_absorbs_year_on_its_own_line(self):
        # The trailing year frequently breaks onto its own line; a digits-only line is
        # not an uppercase heading, so it needs the explicit year-token continuation.
        text = "1 DIVISION B—DEPARTMENT OF DEFENSE APPROPRIATIONS ACT,\n2 2024\n3 TITLE I\n4 SEC. 201. text."
        anchors = _scan_anchors_in_page(1, text)
        assert (
            _by(anchors, "section", "SEC. 201").division == "Division B: DEPARTMENT OF DEFENSE APPROPRIATIONS ACT, 2024"
        )

    def test_table_of_divisions_rows_are_skipped(self):
        # The short-title section lists every division consecutively; a banner whose
        # name-run runs straight into another banner is a contents row, not a real
        # division start. The real banner (followed by content) wins.
        text = (
            "1 SECTION 1. Short title.\n"
            "2 DIVISION A—FIRST ACT\n"
            "3 DIVISION B—SECOND ACT\n"
            "4 DIVISION A—FIRST ACT\n"
            "5 TITLE I\n"
            "6 SEC. 101. A content.\n"
            "7 DIVISION B—SECOND ACT\n"
            "8 TITLE I\n"
            "9 SEC. 201. B content."
        )
        anchors = _scan_anchors_in_page(1, text)
        assert _by(anchors, "section", "SEC. 101").division == "Division A: FIRST ACT"
        assert _by(anchors, "section", "SEC. 201").division == "Division B: SECOND ACT"
        # SECTION 1 (short title) precedes the first real division ⇒ no division.
        assert _by(anchors, "section", "SECTION 1").division == ""

    def test_sentence_division_references_are_not_banners(self):
        # Lowercase / mixed-case `division` in running prose must never be a banner.
        text = (
            "1 TITLE I\n"
            "2 reference to division C of this Act shall be treated\n"
            "3 the Division Engineers and for costs of management\n"
            "4 SEC. 101. text."
        )
        anchors = _scan_anchors_in_page(1, text)
        assert all(a.division == "" for a in anchors)

    def test_single_division_bill_carries_no_division_label(self):
        # No banner ⇒ behavior identical to today (division stays empty everywhere).
        text = "1 TITLE I\n2 SEC. 101. text.\n3 TITLE II\n4 SEC. 201. text."
        anchors = _scan_anchors_in_page(1, text)
        assert all(a.division == "" for a in anchors)


class TestAnchorOrderingWithinPage:
    def test_anchors_returned_in_line_order(self):
        text = (
            "1 TITLE II\n"
            "2 SECURITY, ENFORCEMENT, AND INVESTIGATIONS\n"
            "3 U.S. CUSTOMS AND BORDER PROTECTION\n"
            "4 OPERATIONS AND SUPPORT\n"
            "5 For necessary expenses of U.S. Customs and Border Protection\n"
            "20 SEC. 201. text"
        )
        anchors = _scan_anchors_in_page(11, text)
        line_numbers = [a.line_number for a in anchors]
        assert line_numbers == sorted(line_numbers)
