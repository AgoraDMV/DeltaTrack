"""Unit tests for PDF anchor extraction.

Anchors are landmark labels (`TITLE`, `SEC.`, account headings) that the PDF
reliably carries and the diff layer attaches to hunks as a "where am I" label.
"""

from __future__ import annotations

from deltatrack.parsers.pdf_anchors import Anchor, _scan_anchors_in_page, breadcrumb_for


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
    """Raw text alone never yields an account anchor (#114).

    These cases used to assert the opposite: an all-caps heading within three lines
    above a `For necessary expenses of` line became an ``account``. That made an
    appropriations-specific English phrase load-bearing for structure, which #114
    rules out — text triggers may interpret dollar amounts, never name accounts.
    Account detection is now glyph-size based, and `_scan_anchors_in_page` builds
    pages from raw text with no sizes attached, so no size-based account can arise
    here. These are not vacuous, though: reintroducing a text trigger would make
    them fail immediately, which is exactly how the superseded versions of these
    cases used to pass.

    What still emits from raw text is the universal grammar — TITLE, SEC., and
    enumerator-derived run-in subsections. Positive account assertions live in
    test_pdf_size_detection.py (sized synthetic pages) and test_pdf_anchor_golden.py
    (real PDFs).
    """

    def test_for_necessary_expenses_does_not_name_an_account(self):
        # The exact GPO shape the retired backwalk keyed on: heading, then the
        # trigger phrase within its 3-line reach.
        text = (
            "11 OFFICE OF THE SECRETARY AND EXECUTIVE\n"
            "12 MANAGEMENT\n"
            "13 OPERATIONS AND SUPPORT\n"
            "14 For necessary expenses of the Office of the Secretary"
        )
        anchors = _scan_anchors_in_page(2, text)
        assert not any(a.kind == "account" for a in anchors)

    def test_no_account_from_bare_uppercase_headings(self):
        # Uppercase lines may be titles or other display headings; without a size
        # signal nothing classifies them as accounts.
        text = "7 TITLE I\n8 DEPARTMENTAL MANAGEMENT, INTEL-\n9 LIGENCE"
        anchors = _scan_anchors_in_page(2, text)
        assert not any(a.kind == "account" for a in anchors)

    def test_section_break_still_yields_its_section_anchor(self):
        # Losing the account level must not cost the universal SEC. token beside it
        # (#114 category D) — that is the whole point of degrading rather than
        # guessing: TITLE/SEC./enumerator-derived structure survives, the
        # appropriations-specific guess does not.
        text = (
            "5 SEC. 101. Short title.\n"
            "6 U.S. CUSTOMS AND BORDER PROTECTION\n"
            "7 OPERATIONS AND SUPPORT\n"
            "8 For necessary expenses of U.S. Customs and Border Protection"
        )
        anchors = _scan_anchors_in_page(11, text)
        assert not any(a.kind == "account" for a in anchors)
        assert [a.text for a in anchors if a.kind == "section"] == ["SEC. 101"]


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


class TestRunInSubsection:
    """Run-in subsection anchors (DeltaTrack#96).

    A run-in subsection header (`(a) In general.—`, `(b) DISCRIMINATORY ACTION
    DEFINED.—`) renders inline at body size, so the size path can't see it. A
    dedicated format-grammatical detector emits a `subsection` anchor from the
    parenthesized lower-case enumerator + capitalized catchline + `.—` signature,
    matched over a de-hyphenating continuation window with a stop-rule: two lines join
    unconditionally, and past that a line joins only while it is still title-shaped, so a
    long title is followed but body prose ends the join (#473).
    """

    def _subs(self, page_number, text):
        return [a for a in _scan_anchors_in_page(page_number, text) if a.kind == "subsection"]

    def test_line_start_title_case(self):
        subs = self._subs(1, "1 (a) In general.—The Secretary shall carry out the program.")
        assert subs == [Anchor(1, 1, "subsection", "(a) In general")]

    def test_all_caps_catchline(self):
        # GPO renders the catchline ALL-CAPS in some bills; must not require mixed case.
        subs = self._subs(1, "1 (b) DISCRIMINATORY ACTION DEFINED.—In this section the term.")
        assert subs == [Anchor(1, 1, "subsection", "(b) DISCRIMINATORY ACTION DEFINED")]

    def test_wrapped_catchline_one_line(self):
        # The terminal `.—` wraps onto the next line; a single-line match would drop it.
        text = "3 (c) APPLICABILITY OF CERTAIN\n4 PAY.—The provisions of this subsection."
        subs = self._subs(1, text)
        assert subs == [Anchor(1, 3, "subsection", "(c) APPLICABILITY OF CERTAIN PAY")]

    def test_wrapped_catchline_soft_hyphen(self):
        # A GPO soft-wrap hyphen de-hyphenates across the join (ASSIST- + ANCE -> ASSISTANCE).
        text = "5 (d) EMERGENCY ASSIST-\n6 ANCE.—Funds appropriated under this heading."
        subs = self._subs(1, text)
        assert subs == [Anchor(1, 5, "subsection", "(d) EMERGENCY ASSISTANCE")]

    def test_wrapped_catchline_two_lines(self):
        # A two-continuation wrap: a soft-hyphen join on line 1, a plain space-join on
        # line 2. Two was the matcher's whole budget until #473; see
        # test_wrapped_catchline_five_lines for the long-title case it used to drop.
        text = (
            "7 (a) URBAN AND EMERGING AGRI-\n"
            "8 CULTURAL RESEARCH, EDUCATION, AND\n"
            "9 EXTENSION INITIATIVE.—There is established."
        )
        subs = self._subs(1, text)
        assert subs == [
            Anchor(
                1, 7, "subsection", "(a) URBAN AND EMERGING AGRICULTURAL RESEARCH, EDUCATION, AND EXTENSION INITIATIVE"
            )
        ]

    def test_wrapped_catchline_five_lines(self):
        # A catchline wrapping onto FIVE continuation lines, transcribed from the case
        # that exposed the old two-line budget: 119-hr-1 sec. 112207(b), whose 250-char
        # title put its terminal `.—` out of reach and left a $15,000,000 appropriation
        # with no anchor at all (#473). Long titles are not exotic; they attach to the
        # specific, negotiated provisions, which is why dropping them was expensive.
        text = (
            "1 (b) APPROPRIATION FOR TASK FORCE TO DESIGN A\n"
            "2 BETTER PUBLIC-PRIVATE PARTNERSHIP BETWEEN THE\n"
            "3 IRS AND PRIVATE SECTOR TAX PREPARATION SERVICES\n"
            "4 TO PROVIDE FOR FREE TAX FILING TO REPLACE THE\n"
            "5 EXISTING FREE FILE PROGRAM AND ANY DIRECT\n"
            "6 EFILE TAX RETURN SYSTEM.—Out of any money in the\n"
        )
        subs = self._subs(1, text)
        assert subs == [
            Anchor(
                1,
                1,
                "subsection",
                "(b) APPROPRIATION FOR TASK FORCE TO DESIGN A BETTER PUBLIC-PRIVATE PARTNERSHIP "
                "BETWEEN THE IRS AND PRIVATE SECTOR TAX PREPARATION SERVICES TO PROVIDE FOR FREE "
                "TAX FILING TO REPLACE THE EXISTING FREE FILE PROGRAM AND ANY DIRECT EFILE TAX "
                "RETURN SYSTEM",
            )
        ]

    def test_catchline_less_subsection_does_not_run_into_the_next_section(self):
        # Transcribed from 115-hr-5895 p49 lines 16-21. This subsection has NO catchline:
        # it opens straight into prose. Nothing in it should anchor, but with a pure
        # line-count budget the join walked the prose, crossed the `SEC.` line, and
        # terminated on the FOLLOWING section's `.—`, producing a 295-char anchor labelled
        # "(c) A waiver under subsection (b) … SEC. 307. (a) NEW REGIONAL RESERVES".
        #
        # It is the counterpart to test_wrapped_catchline_five_lines: both need to look
        # more than two lines ahead, and only the case-shape of the continuation tells
        # them apart. A count cannot, which is why one is not enough (#473).
        text = (
            "16 (c) A waiver under subsection (b) shall not be effective\n"
            "17 until 15 days after the date on which the Secretary submits\n"
            "18 to the Committees on Appropriations of both Houses of\n"
            "19 Congress a report on the justification for the waiver.\n"
            "20 SEC. 307. (a) NEW REGIONAL RESERVES.—The Secretary\n"
            "21 shall establish reserves.\n"
        )
        assert [a for a in self._subs(1, text) if a.line_number == 16] == []

    def test_section_heading_ends_the_join_without_an_inline_enumerator(self):
        # A heading is the start of the next provision, so a catchline can never continue
        # through one. "SEC. 142. PURPOSE OF PROGRAMS.—" opens with neither a quote nor a
        # `(a)`, so the older stop-rule clauses let it through, and the all-caps account
        # heading before it is title-shaped — the join reached the heading's own `.—` and
        # labelled this subsection with the NEXT section's title (#473).
        text = (
            "16 (c) A waiver under subsection (b) shall not apply here.\n"
            "17 SECURITY PROGRAMS\n"
            "18 SEC. 142. PURPOSE OF PROGRAMS.—The Secretary shall act.\n"
        )
        assert [a for a in self._subs(1, text) if a.line_number == 16] == []

    def test_a_reference_to_a_section_is_not_a_heading(self):
        # The converse of the guard above: "SECTION 1245" inside a title is ordinary
        # vocabulary (119-hr-1 has a real one), and must not end the join. The heading rule
        # keys on the period after the number, which a cross-reference does not carry.
        text = "1 (b) TREATMENT OF PROPERTY AS\n2 SECTION 1245 PROPERTY.—For purposes of this part.\n"
        assert self._subs(1, text) == [Anchor(1, 1, "subsection", "(b) TREATMENT OF PROPERTY AS SECTION 1245 PROPERTY")]

    def test_an_amount_line_is_not_title_shaped(self):
        # "No lowercase" is satisfied by a line with no letters at all, so an amount or a
        # bare numeral would read as title and let a join walk through it into whatever
        # follows. Title-shape requires positive evidence: at least one capital (#473).
        text = (
            "1 (c) For an additional amount for such purposes,\n"
            "2 $15,000,000\n"
            "3 $27,500,000\n"
            "4 GENERAL PROVISIONS.—The following applies.\n"
        )
        assert [a for a in self._subs(1, text) if a.line_number == 1] == []

    def test_an_abbreviation_dash_is_not_a_terminator(self):
        # "U.S.–E.U." puts a period next to a dash mid-prose, which looks exactly like the
        # `.—` that ends a catchline. Judging the line on the three characters before it
        # ("U.S") would call plain prose a title. The same fabrication mode is documented
        # on the XML side of this parser for 113-hr-83 sec. 415(a).
        text = (
            "1 (a) NOTHING IN THIS SECTION SHALL\n"
            "2 BE CONSTRUED TO LIMIT ANY\n"
            "3 U.S.–E.U. trade obligations shall be impaired by this\n"
            "4 subsection or any other.—Provided further, that funds.\n"
        )
        assert [a for a in self._subs(1, text) if a.line_number == 1] == []

    def test_catchline_beyond_the_window_is_abandoned(self):
        # The window is a bound, not an invitation: a catchline still running after
        # `_RUNIN_MAX_CONTINUATIONS` continuations yields NO anchor rather than an
        # ever-longer join. Without this, an unbounded matcher would let a subsection
        # with no catchline reach forward indefinitely for an unrelated `.—`.
        body = "".join(f"{i} WORDS THAT KEEP RUNNING ON AND ON AND ON\n" for i in range(2, 2 + 8))
        text = "1 (b) A TITLE THAT NEVER TERMINATES\n" + body + "10 AT LAST.—The body begins here."
        assert self._subs(1, text) == []

    def test_same_line_after_sec_collision(self):
        # A SEC. line can carry an inline (a) run-in: emit BOTH a section and a
        # subsection at the same (page, line), section appended FIRST so it sorts
        # before the subsection (block-ownership order, load-bearing for Seam #2).
        anchors = _scan_anchors_in_page(2, "5 SEC. 547. (a) In general.—The Secretary shall act.")
        collided = [a for a in anchors if a.page_number == 2 and a.line_number == 5]
        assert collided == [
            Anchor(2, 5, "section", "SEC. 547"),
            Anchor(2, 5, "subsection", "(a) In general"),
        ]

    def test_abbreviation_period_not_truncated(self):
        # The non-greedy `.*?[.]` backtracks past abbreviation periods to the real
        # terminal `.—`, so `U.S.` does not truncate the catchline at "U.".
        subs = self._subs(1, "1 (a) U.S. citizens.—A citizen of the United States.")
        assert subs == [Anchor(1, 1, "subsection", "(a) U.S. citizens")]

    def test_doubled_two_letter_enumerator(self):
        subs = self._subs(1, "1 (aa) Special rule.—Notwithstanding any other provision.")
        assert subs == [Anchor(1, 1, "subsection", "(aa) Special rule")]

    # ---- negatives -------------------------------------------------------------

    def test_no_em_dash_is_not_a_subsection(self):
        # `(a) the term "x" means…` is definitional prose, not a run-in header.
        assert self._subs(1, '1 (a) the term "covered entity" means an entity described.') == []

    def test_paragraph_enumerator_out_of_scope(self):
        # Numeric `(1)` is paragraph-level, deliberately out of subsection scope.
        assert self._subs(1, "1 (1) In general.—The paragraph applies to.") == []

    def test_quoted_amendment_block_self_excludes(self):
        # A quoted amendment target opens with GPO's `‘‘`, so `^\(` never matches.
        assert self._subs(1, "1 ‘‘(a) IN GENERAL.—Amounts made available under.") == []

    def test_roman_lookalike_enumerators_rejected(self):
        # (i)/(v)/(x) singles and non-doubled/`ii` two-letter combos are clause-level
        # romans, rejected to avoid mis-nesting them as section children.
        assert self._subs(1, "1 (i) Foo.—Bar.") == []
        assert self._subs(1, "1 (ii) Foo.—Bar.") == []
        assert self._subs(1, "1 (iv) Foo.—Bar.") == []
        assert self._subs(1, "1 (v) Foo.—Bar.") == []
        assert self._subs(1, "1 (x) Foo.—Bar.") == []

    def test_stop_rule_rejects_quoted_continuation(self):
        # An unconditional join would pull a quoted catchline into the window; the
        # stop-rule (`^‘`) blocks it. Uses a VALID enumerator so the reject is the
        # stop-rule, not the roman filter.
        text = "1 (c) by striking subsection (b) and inserting\n2 ‘‘(A) IN GENERAL.—the following new."
        assert self._subs(1, text) == []

    def test_stop_rule_rejects_sibling_enumerator_continuation(self):
        # A bare enumerator line whose own catchline had no `.—` must NOT swallow the
        # NEXT enumerator's catchline into a fabricated anchor. Line 1 emits nothing;
        # line 2 is a legitimate subsection header on its own.
        text = "1 (b) imposes a fee on that alien.\n2 (b) FEE SPECIFIED.—The fee is."
        subs = self._subs(1, text)
        # The false join `(b) imposes a fee on that alien. (b) FEE SPECIFIED` is absent;
        # only line 2's genuine header survives.
        assert not any("imposes a fee" in a.text for a in subs)
        assert [(a.line_number, a.text) for a in subs] == [(2, "(b) FEE SPECIFIED")]

    def test_breadcrumb_nests_subsection_under_section(self):
        text = "1 TITLE I\n2 SEC. 547. General provisions.\n3 (a) In general.—The Secretary shall carry out."
        anchors = _scan_anchors_in_page(1, text)
        sub = _by(anchors, "subsection", "(a) In general")
        assert breadcrumb_for(sub, anchors) == ("TITLE I", "SEC. 547", "(a) In general")

    def test_breadcrumb_degrades_without_a_section(self):
        # A subsection with no preceding section before the title degrades to itself.
        text = "1 TITLE I\n2 (a) In general.—The Secretary shall carry out."
        anchors = _scan_anchors_in_page(1, text)
        sub = _by(anchors, "subsection", "(a) In general")
        assert breadcrumb_for(sub, anchors) == ("(a) In general",)


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
