import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from bill_tree import (
    BillNode,
    _extract_appropriations_text,
    _extract_section_text,
    build_title_label,
    extract_display_text,
    extract_text_content,
    find_bill_body,
    get_header_text,
    normalize_bill,
    normalize_division_title,
    normalize_header,
    title_match_header,
    walk_body_sections,
    walk_title,
)


def _content(tree):
    """Content nodes only, dropping the front-matter prefix (#48) so structure
    assertions stay focused on the bill body."""
    return [n for n in tree.nodes if n.tag != "front-matter"]


class TestTitleLabel:
    """Title enum handling (#50): TITLE I—<header> for display, header-only for match."""

    def test_label_with_enum_and_header(self):
        title = ET.fromstring("<title><enum>I</enum><header>DEPARTMENTAL MANAGEMENT</header></title>")
        assert build_title_label(title) == "TITLE I—DEPARTMENTAL MANAGEMENT"

    def test_label_headerless_division_title(self):
        """Division bills carry bare title enums; the label is just TITLE <enum>."""
        title = ET.fromstring("<title><enum>I</enum></title>")
        assert build_title_label(title) == "TITLE I"

    def test_label_enumless_falls_back_to_header(self):
        title = ET.fromstring("<title><header>GENERAL PROVISIONS</header></title>")
        assert build_title_label(title) == "GENERAL PROVISIONS"

    def test_match_header_recovers_plain_header(self):
        assert title_match_header("TITLE I—DEPARTMENTAL MANAGEMENT") == "DEPARTMENTAL MANAGEMENT"

    def test_match_header_bare_enum_is_empty(self):
        """A bare TITLE enum contributes no match segment (preserves division-bill keys)."""
        assert title_match_header("TITLE I") == ""

    def test_match_header_passes_through_non_title(self):
        assert title_match_header("GENERAL PROVISIONS") == "GENERAL PROVISIONS"


_SEC105_XML = """
<section id="S105"><enum>105.</enum>
<subsection display-inline="yes-display-inline" id="a"><enum>(a)</enum>
<text display-inline="yes-display-inline">The Under Secretary shall brief the Committees
on subsection (a) matters during the preceding quarter.</text></subsection>
<subsection id="b"><enum>(b)</enum>
<text>For each such program, the briefing described in subsection (a) shall include—</text>
<paragraph id="b1"><enum>(1)</enum><text>a description of the purpose of the program;</text></paragraph>
<paragraph id="b2"><enum>(2)</enum><text>the total number of units to be acquired;</text></paragraph>
<paragraph id="b3"><enum>(3)</enum><text>the Acquisition Review Board status, including—</text>
<subparagraph id="b3A"><enum>(A)</enum><text>the current acquisition phase;</text></subparagraph>
</paragraph></subsection></section>
"""

_SEC102_XML = (
    '<section id="S102"><enum>102.</enum>'
    '<text display-inline="yes-display-inline">Not later than 30 days after the last day '
    "of each month, the Chief Financial Officer shall submit a report.</text></section>"
)


class TestExtractDisplayText:
    """Readable multi-line rendering for the full-bill view (#51): space after
    every enum, list items on their own lines indented by structural level."""

    def test_inline_only_section_is_single_line(self):
        el = ET.fromstring(_SEC102_XML)
        out = extract_display_text(el)
        assert "\n" not in out
        assert out.startswith("Not later than 30 days")

    def test_space_after_parenthetical_enum(self):
        el = ET.fromstring(_SEC105_XML)
        out = extract_display_text(el)
        assert "(a) The Under Secretary" in out
        assert "(b) For each such program" in out
        assert "(1) a description" in out

    def test_in_text_cross_reference_keeps_its_space(self):
        el = ET.fromstring(_SEC105_XML)
        out = extract_display_text(el)
        # An in-text "subsection (a)" reference is display text, not a list marker.
        assert "subsection (a)" in out

    def test_list_items_on_their_own_lines(self):
        el = ET.fromstring(_SEC105_XML)
        lines = extract_display_text(el).split("\n")
        starts = [ln.strip()[:4] for ln in lines]
        assert any(s.startswith("(b)") for s in starts)
        assert any(s.startswith("(1)") for s in starts)
        assert any(s.startswith("(2)") for s in starts)
        assert any(s.startswith("(3)") for s in starts)
        assert any(s.startswith("(A)") for s in starts)

    def test_run_in_subsection_shares_first_line(self):
        # (a) is display-inline, so it is NOT on its own line; (b) is.
        el = ET.fromstring(_SEC105_XML)
        first = extract_display_text(el).split("\n")[0]
        assert first.startswith("(a) ")

    def test_indent_ladder_by_structural_level(self):
        el = ET.fromstring(_SEC105_XML)
        by_marker = {}
        for ln in extract_display_text(el).split("\n"):
            m = ln.strip()[:4]
            indent = len(ln) - len(ln.lstrip(" "))
            if m.startswith("(b)"):
                by_marker["b"] = indent
            elif m.startswith("(1)"):
                by_marker["1"] = indent
            elif m.startswith("(A)"):
                by_marker["A"] = indent
        # subsection rank 0, paragraph rank 1 (4sp), subparagraph rank 2 (8sp).
        assert by_marker["b"] == 0
        assert by_marker["1"] == 4
        assert by_marker["A"] == 8


_HR8752_V1 = Path("bills/118-hr-8752/1_reported-in-house.xml")


@pytest.mark.slow
@pytest.mark.skipif(not _HR8752_V1.exists(), reason="bill corpus not present (fetch_bills.py)")
def test_real_bill_body_nodes_have_display_text():
    """Guards the serializer's ``display_text or body_text`` fallback from silently
    masking a walker bug: every content node parsed from a real bill must carry a
    non-empty display_text (front matter is exempt — its body is already readable)."""
    tree = normalize_bill(_HR8752_V1)
    empty = [n for n in tree.nodes if n.tag != "front-matter" and n.body_text and not n.display_text]
    assert empty == []


# 115-hr-5895 enrolled has BOTH <division> children and top-level <title> children
# directly under <legis-body> — the structural shape that exposed the normalize_bill
# div+title drop (#146). It is the conservation/regression fixture for that fix.
_HR5895_ENROLLED = Path("bills/115-hr-5895/5_enrolled-bill.xml")


@pytest.mark.slow
@pytest.mark.skipif(not _HR5895_ENROLLED.exists(), reason="bill corpus not present (fetch_bills.py)")
def test_divisions_and_top_level_titles_both_walked():
    """Regression for #146: a bill with both <division> children and top-level
    <title> siblings under <legis-body> must walk both. normalize_bill used to
    early-return after the divisions, silently dropping the 4 top-level titles
    (Department of Veterans Affairs, Related Agencies, Overseas Contingency
    Operations, General Provisions) and ~16% of the bill's dollar amounts."""
    from collections import Counter

    from diff_bill import extract_amounts

    root = ET.parse(_HR5895_ENROLLED).getroot()
    body = find_bill_body(root)
    # Precondition: this fixture really has the both-shapes structure.
    assert len(body.findall("division")) > 0
    assert len(body.findall("title")) > 0

    tree = normalize_bill(_HR5895_ENROLLED)
    node_amounts: Counter[int] = Counter()
    for n in tree.nodes:
        node_amounts.update(extract_amounts(n.display_text or n.body_text or ""))
    raw_amounts = Counter(extract_amounts(extract_text_content(body)))

    # Financial conservation: every amount in the independent raw-XML body is
    # accounted for by the union of per-node amounts (no drops).
    dropped = raw_amounts - node_amounts
    assert sum(dropped.values()) == 0, f"dropped amounts: {dict(dropped)}"


class TestNormalizeHeader:
    def test_lowercase(self):
        assert normalize_header("DEPARTMENT OF DEFENSE") == "department of defense"

    def test_collapse_whitespace(self):
        assert normalize_header(" Military  construction,\n army ") == "military construction, army"

    def test_empty_string(self):
        assert normalize_header("") == ""

    def test_mixed_case_and_whitespace(self):
        assert normalize_header("  Veterans Health  Administration  ") == "veterans health administration"


class TestExtractTextContent:
    def test_simple_text(self):
        el = ET.fromstring("<text>Hello world</text>")
        assert extract_text_content(el) == "Hello world"

    def test_nested_elements(self):
        el = ET.fromstring("<text>For <short-title>Department of Defense</short-title> purposes</text>")
        assert extract_text_content(el) == "For Department of Defense purposes"

    def test_tail_text(self):
        el = ET.fromstring("<text>Before <emphasis>bold</emphasis> after</text>")
        assert extract_text_content(el) == "Before bold after"

    def test_empty_element(self):
        el = ET.fromstring("<text/>")
        assert extract_text_content(el) == ""

    def test_whitespace_normalized(self):
        el = ET.fromstring("<text>Code— (1)provides  assistance</text>")
        assert extract_text_content(el) == "Code—(1)provides assistance"

    def test_newlines_collapsed(self):
        el = ET.fromstring("<text>first line\n  second line\n  third</text>")
        assert extract_text_content(el) == "first line second line third"

    def test_nested_whitespace_normalized(self):
        el = ET.fromstring("<text>Suicidology.(b) <enum>(1)</enum>None  of the funds</text>")
        assert extract_text_content(el) == "Suicidology.(b)(1)None of the funds"

    def test_list_marker_spacing_normalized(self):
        el = ET.fromstring("<text>and (2)adheres to all</text>")
        assert extract_text_content(el) == "and(2)adheres to all"

    def test_roman_numeral_marker_normalized(self):
        el = ET.fromstring("<text>Code— (iv)the term</text>")
        assert extract_text_content(el) == "Code—(iv)the term"

    def test_uppercase_marker_normalized(self):
        el = ET.fromstring("<text>and (B)the term</text>")
        assert extract_text_content(el) == "and(B)the term"

    def test_acronym_spacing_kept(self):
        el = ET.fromstring("<text>Rural Housing Service (RHS) provides</text>")
        assert extract_text_content(el) == "Rural Housing Service (RHS) provides"

    def test_year_spacing_kept(self):
        el = ET.fromstring("<text>Stat. 4302 (2008) and</text>")
        assert extract_text_content(el) == "Stat. 4302 (2008) and"

    def test_long_parenthetical_spacing_kept(self):
        el = ET.fromstring("<text>the (Comptroller) shall</text>")
        assert extract_text_content(el) == "the (Comptroller) shall"

    def test_block_siblings_separated_by_space(self):
        # Adjacent block-level siblings with no whitespace between them in the
        # source must not run together (#17): header + text -> "date The...".
        el = ET.fromstring(
            "<subsection><enum>(c)</enum><header>Effective date</header><text>The amendments made.</text></subsection>"
        )
        assert extract_text_content(el) == "(c)Effective date The amendments made."

    def test_inline_element_does_not_split_word(self):
        # Inline elements (external-xref, quote, italic, ...) carry continuation
        # text; a separator here would break the word ("subchapter").
        el = ET.fromstring("<text>authorized by sub<external-xref>chapter 59</external-xref> of title 5</text>")
        assert extract_text_content(el) == "authorized by subchapter 59 of title 5"

    def test_inline_after_open_paren_stays_attached(self):
        # No space inserted after "(" before an inline citation.
        el = ET.fromstring("<text>Act of 1978 (<external-xref>Public Law 95-123</external-xref>)</text>")
        assert extract_text_content(el) == "Act of 1978 (Public Law 95-123)"

    def test_enum_marker_stays_attached_to_following_text(self):
        # An enum marker attaches to the text that follows it without a space,
        # matching _LIST_MARKER_RE's convention (no "(1) None").
        el = ET.fromstring("<paragraph><enum>(1)</enum><text>None of the funds.</text></paragraph>")
        assert extract_text_content(el) == "(1)None of the funds."

    def test_punctuation_starting_block_not_pushed_off_anchor(self):
        # A block whose text starts with punctuation does not get a leading
        # space ("(1)." stays "(1).", not "(1) ." or "(1). .").
        el = ET.fromstring("<subsection><text>in subparagraph (1)</text><clause><text>.</text></clause></subsection>")
        assert extract_text_content(el) == "in subparagraph(1)."

    def test_numbered_section_enum_separated_from_header(self):
        # A number-period enum ("1291.") is a section number, not an attaching
        # marker, so it gets a space before the header ("1291.Military" mash ->
        # "1291. Military"). Mirrors the quoted-block payload in 115-hr-880.
        el = ET.fromstring(
            "<section><enum>1291.</enum>"
            "<header>Military and Civilian Partnership</header>"
            "<text>The Secretary shall.</text></section>"
        )
        result = extract_text_content(el)
        assert "1291. Military and Civilian Partnership" in result
        assert "1291.Military" not in result

    def test_roman_part_enum_separated_from_header(self):
        # A bare roman-numeral enum ("I") on a part/title is not an attaching
        # marker either ("IMilitary" mash -> "I Military"). Also from 115-hr-880.
        el = ET.fromstring("<part><enum>I</enum><header>Military and Civilian Partnership</header></part>")
        result = extract_text_content(el)
        assert result == "I Military and Civilian Partnership"
        assert "IMilitary" not in result

    def test_bare_number_enum_separated_from_text(self):
        # A bare-number enum ("110") gets a separator too.
        el = ET.fromstring("<clause><enum>110</enum><text>Definitions apply.</text></clause>")
        assert extract_text_content(el) == "110 Definitions apply."

    def test_linebreak_becomes_a_space(self):
        # Multi-line table cells separate values with an empty <linebreak/> that
        # carries no character, so without handling the lines mash together
        # ("$66,464,000Initial Non-Federal"). A linebreak is whitespace.
        # From the Army Corps project table in 116-hr-133.
        el = ET.fromstring("<entry>Initial Federal: $66,464,000<linebreak/>Initial Non-Federal: $35,789,000</entry>")
        result = extract_text_content(el)
        assert result == "Initial Federal: $66,464,000 Initial Non-Federal: $35,789,000"
        assert "$66,464,000Initial" not in result

    def test_pagebreak_becomes_a_space(self):
        # A <pagebreak/> is likewise a visual break, not part of a word.
        el = ET.fromstring("<text>End of page.<pagebreak/>Next section begins.</text>")
        assert extract_text_content(el) == "End of page. Next section begins."


class TestExtractSectionText:
    def test_simple_lead_in_only(self):
        # A plain <text> section with no payload returns just that line.
        section = ET.fromstring(
            "<section><enum>1.</enum><header>Short title</header>"
            "<text>This Act may be cited as the Example Act.</text></section>"
        )
        assert _extract_section_text(section) == "This Act may be cited as the Example Act."

    def test_quoted_block_payload_included(self):
        # "Amend ... by adding the following" sections carry the substantive
        # text inside <quoted-block>, whose subsections are nested (not direct
        # children). The lead-in <text> must not short-circuit past it. (#11)
        section = ET.fromstring(
            "<section><enum>2.</enum>"
            "<text>Title XII is amended by adding at the end the following:</text>"
            "<quoted-block>"
            "<subsection><enum>(a)</enum><text>$20,000,000 is authorized.</text></subsection>"
            "<subsection><enum>(b)</enum><text>Rule of construction applies.</text></subsection>"
            "</quoted-block></section>"
        )
        result = _extract_section_text(section)
        assert "$20,000,000 is authorized." in result
        assert "Rule of construction applies." in result
        assert "amended by adding" in result

    def test_sibling_parts_joined_with_space(self):
        # Adjacent non-marker parts must not run together (#17): the join keeps a
        # word boundary while still stripping the space before list markers.
        section = ET.fromstring(
            "<section><enum>3.</enum>"
            "<text>available until September 30, 2028:</text>"
            "<subsection><text>Military Construction, Army, $25,000,000.</text></subsection>"
            "</section>"
        )
        result = _extract_section_text(section)
        assert "2028: Military Construction" in result
        assert "2028:Military" not in result

    def test_list_marker_space_still_stripped(self):
        # The space before a parenthetical list marker stays stripped after the
        # space-preserving join, so output does not churn for the common case.
        section = ET.fromstring(
            "<section><enum>4.</enum>"
            "<text>None of the funds may be used.</text>"
            "<subsection><enum>(b)</enum><text>Whoever violates this section.</text></subsection>"
            "</section>"
        )
        result = _extract_section_text(section)
        assert "used.(b)Whoever" in result


class TestGetHeaderText:
    def test_with_header(self):
        el = ET.fromstring(
            "<appropriations-intermediate>"
            "<header>Military construction, army</header>"
            "<text>Some text</text>"
            "</appropriations-intermediate>"
        )
        assert get_header_text(el) == "Military construction, army"

    def test_without_header(self):
        el = ET.fromstring("<appropriations-intermediate><text>Some text</text></appropriations-intermediate>")
        assert get_header_text(el) == ""

    def test_header_with_nested_elements(self):
        el = ET.fromstring(
            "<appropriations-major>"
            "<header>Department of <short-title>Veterans Affairs</short-title></header>"
            "</appropriations-major>"
        )
        assert get_header_text(el) == "Department of Veterans Affairs"


class TestExtractAppropriationsText:
    def test_text_with_paragraphs(self):
        """Element with <text> and <paragraph> children captures all content."""
        el = ET.fromstring(
            "<appropriations-intermediate>"
            "<header>Office of the Attending Physician</header>"
            "<text>For medical supplies, including:</text>"
            "<paragraph><enum>(1)</enum><text>$9,120 per annum</text></paragraph>"
            "<paragraph><enum>(2)</enum><text>$2,800,000 for reimbursement</text></paragraph>"
            "</appropriations-intermediate>"
        )
        result = _extract_appropriations_text(el)
        assert "For medical supplies, including:" in result
        assert "$9,120" in result
        assert "$2,800,000" in result

    def test_text_only(self):
        """Element with only <text> child returns same as extract_text_content."""
        el = ET.fromstring(
            "<appropriations-intermediate>"
            "<header>Medical services</header>"
            "<text>For necessary expenses, $60,000,000.</text>"
            "</appropriations-intermediate>"
        )
        result = _extract_appropriations_text(el)
        assert result == "For necessary expenses, $60,000,000."

    def test_paragraphs_only(self):
        """Element with only <paragraph> children still returns content."""
        el = ET.fromstring(
            "<appropriations-intermediate>"
            "<header>Some heading</header>"
            "<paragraph><enum>(1)</enum><text>First item $1,000</text></paragraph>"
            "<paragraph><enum>(2)</enum><text>Second item $2,000</text></paragraph>"
            "</appropriations-intermediate>"
        )
        result = _extract_appropriations_text(el)
        assert "$1,000" in result
        assert "$2,000" in result

    def test_empty_element(self):
        """Element with only a header returns empty string."""
        el = ET.fromstring("<appropriations-major><header>Department of Defense</header></appropriations-major>")
        result = _extract_appropriations_text(el)
        assert result == ""

    def test_excludes_enum_and_header(self):
        """Top-level enum and header are excluded from output."""
        el = ET.fromstring(
            "<appropriations-small>"
            "<enum>A</enum>"
            "<header>Salaries</header>"
            "<text>For expenses, $500,000.</text>"
            "</appropriations-small>"
        )
        result = _extract_appropriations_text(el)
        assert result == "For expenses, $500,000."
        assert "Salaries" not in result


class TestFindBillBody:
    def test_bill_with_legis_body(self):
        root = ET.fromstring(
            '<bill bill-stage="Enrolled-Bill"><legis-body><section><text>Content</text></section></legis-body></bill>'
        )
        body = find_bill_body(root)
        assert body.tag == "legis-body"
        assert body.find("section") is not None

    def test_amendment_doc(self):
        root = ET.fromstring(
            '<amendment-doc amend-type="engrossed-amendment">'
            "<engrossed-amendment-body>"
            "<amendment>"
            '<amendment-block style="OLC">'
            "<section><text>Content</text></section>"
            "</amendment-block>"
            "</amendment>"
            "</engrossed-amendment-body>"
            "</amendment-doc>"
        )
        body = find_bill_body(root)
        assert body.tag == "amendment-block"
        assert body.find("section") is not None

    def test_amendment_block_with_nested_legis_body(self):
        """Amendment-block containing legis-body should return the legis-body."""
        root = ET.fromstring(
            '<amendment-doc amend-type="engrossed-amendment">'
            "<engrossed-amendment-body>"
            "<amendment>"
            '<amendment-block style="OLC">'
            "<legis-body><section><text>Content</text></section></legis-body>"
            "</amendment-block>"
            "</amendment>"
            "</engrossed-amendment-body>"
            "</amendment-doc>"
        )
        body = find_bill_body(root)
        assert body.find("section") is not None

    def test_amendment_doc_115_hr_244_v5_produces_nodes(self):
        """Real bill 115-hr-244 v5 should produce nodes (was 0 before fix)."""
        xml_path = Path("bills/115-hr-244/5_engrossed-amendment-house.xml")
        if not xml_path.exists():
            pytest.skip("Bill XML not available locally")
        tree = normalize_bill(xml_path)
        assert len(tree.nodes) >= 5

    def test_missing_body_raises(self):
        root = ET.fromstring("<bill><metadata/></bill>")
        with pytest.raises(ValueError, match="Could not find bill body"):
            find_bill_body(root)


class TestWalkTitle:
    """Test walk_title with inline XML mimicking real bill structure."""

    def test_basic_intermediate_with_text(self):
        """An intermediate with header and text produces one BillNode."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPARTMENT OF DEFENSE</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Military construction, army</header>"
            '<text display-inline="no-display-inline">'
            "For acquisition, construction, $1,876,875,000, to remain available."
            "</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "DEPARTMENT OF DEFENSE", "")
        assert len(nodes) == 1
        node = nodes[0]
        assert node.match_path == ("department of defense", "military construction, army")
        assert node.display_path == ("DEPARTMENT OF DEFENSE", "Military construction, army")
        assert node.tag == "appropriations-intermediate"
        assert node.element_id == "AI1"
        assert node.header_text == "Military construction, army"
        assert "$1,876,875,000" in node.body_text
        assert node.section_number == ""

    def test_major_sets_context_for_intermediate(self):
        """Major without text sets context; intermediate inherits it in match_path."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>II</enum>"
            "<header>VETERANS AFFAIRS</header>"
            '<appropriations-major id="AM1">'
            "<header>Veterans Health Administration</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI1">'
            "<header>Medical services</header>"
            "<text>For necessary expenses, $60,000,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "VETERANS AFFAIRS", "")
        assert len(nodes) == 1
        node = nodes[0]
        assert node.match_path == (
            "veterans affairs",
            "veterans health administration",
            "medical services",
        )
        assert node.display_path == (
            "VETERANS AFFAIRS",
            "Veterans Health Administration",
            "Medical services",
        )

    def test_major_with_text_produces_node(self):
        """A major with a text child produces its own node."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-major id="AM1">'
            "<header>Big Agency</header>"
            "<text>For expenses, $500,000.</text>"
            "</appropriations-major>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 1
        assert nodes[0].match_path == ("dept", "big agency")
        assert nodes[0].header_text == "Big Agency"

    def test_context_only_element_no_node(self):
        """A major with no text child sets context but produces no node."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-major id="AM1">'
            "<header>Context Only</header>"
            "</appropriations-major>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 0

    def test_parenthetical_header_inherits_previous(self):
        """Parenthetical header like (INCLUDING TRANSFER) uses previous sibling name."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Regular Account</header>"
            "<text>For expenses, $100,000.</text>"
            "</appropriations-intermediate>"
            '<appropriations-intermediate id="AI2">'
            "<header>(INCLUDING TRANSFER OF FUNDS)</header>"
            "<text>Of the funds, not more than $50,000 may transfer.</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 2
        # Second node inherits previous sibling's header for matching
        assert nodes[1].match_path == ("dept", "regular account")
        assert nodes[1].header_text == "(INCLUDING TRANSFER OF FUNDS)"

    def test_empty_intermediate_header_does_not_clobber_prev_name(self):
        """Empty header on intermediate should not clobber prev_name for parenthetical siblings."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Real Account</header>"
            "<text>For expenses, $100,000.</text>"
            "</appropriations-intermediate>"
            '<appropriations-intermediate id="AI2">'
            "<header></header>"
            "<text>Additional amount, $200,000.</text>"
            "</appropriations-intermediate>"
            '<appropriations-intermediate id="AI3">'
            "<header>(INCLUDING TRANSFER OF FUNDS)</header>"
            "<text>Of the funds, not more than $50,000 may transfer.</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 3
        # Third node is parenthetical; should inherit "Real Account" from first,
        # not empty string from second
        assert nodes[2].match_path == ("dept", "real account")

    def test_section_with_enum(self):
        """A section produces a node with section_number in the path."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Admin Provisions</header>"
            "</appropriations-intermediate>"
            '<section id="S1">'
            "<enum>124.</enum>"
            "<header>Limitation on funds</header>"
            "<text>None of the funds may be used for bonuses.</text>"
            "</section>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 1
        node = nodes[0]
        assert node.section_number == "Sec. 124"
        assert node.match_path == ("dept", "admin provisions", "sec. 124")
        assert "bonuses" in node.body_text

    def test_division_label_in_display_path(self):
        """When division_label is provided, it prefixes the display_path."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Account</header>"
            "<text>For expenses, $1,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "Division A: MilCon-VA")
        assert len(nodes) == 1
        assert nodes[0].display_path == ("Division A: MilCon-VA", "DEPT", "Account")
        # match_path never includes division
        assert nodes[0].match_path == ("dept", "account")

    def test_small_under_intermediate_context(self):
        """A small element uses the current intermediate context in its path."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Sub-Agency</header>"
            "</appropriations-intermediate>"
            '<appropriations-small id="AS1">'
            "<header>Tiny Program</header>"
            "<text>For grants, $10,000.</text>"
            "</appropriations-small>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 1
        assert nodes[0].match_path == ("dept", "sub-agency", "tiny program")

    def test_section_with_subsections_no_direct_text(self):
        """Sections with subsections but no direct <text> should still produce a node."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<section id="S1">'
            "<enum>2.</enum>"
            "<header>Sanctions</header>"
            "<subsection>"
            "<text>The President shall impose sanctions.</text>"
            "</subsection>"
            "</section>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 1
        assert "President shall impose sanctions" in nodes[0].body_text

    def test_major_resets_intermediate(self):
        """A new major clears intermediate context."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-major id="AM1">'
            "<header>Agency A</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI1">'
            "<header>Sub A</header>"
            "<text>Text A $100.</text>"
            "</appropriations-intermediate>"
            '<appropriations-major id="AM2">'
            "<header>Agency B</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI2">'
            "<header>Sub B</header>"
            "<text>Text B $200.</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 2
        assert nodes[0].match_path == ("dept", "agency a", "sub a")
        assert nodes[1].match_path == ("dept", "agency b", "sub b")

    def test_intermediate_with_paragraph_children(self):
        """An intermediate with <text> + <paragraph> children captures all content."""
        title = ET.fromstring(
            '<title id="T1">'
            "<header>JOINT ITEMS</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Office of the Attending Physician</header>"
            "<text>For medical supplies, including:</text>"
            "<paragraph><enum>(1)</enum>"
            "<text>$9,120 per annum for the Attending Physician</text>"
            "</paragraph>"
            "<paragraph><enum>(2)</enum>"
            "<text>$2,800,000 for reimbursement, $3,868,000 total</text>"
            "</paragraph>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "JOINT ITEMS", "")
        assert len(nodes) == 1
        node = nodes[0]
        assert "For medical supplies, including:" in node.body_text
        assert "$9,120" in node.body_text
        assert "$3,868,000" in node.body_text

    def test_section_wrapping_appropriations(self):
        """Section containing appropriations-* children produces individual nodes."""
        title = ET.fromstring(
            '<title id="T1">'
            "<header>LEGISLATIVE BRANCH</header>"
            '<section id="S101">'
            "<enum>101.</enum>"
            "<text>The following sums are appropriated.</text>"
            '<appropriations-major id="AM1">'
            "<header>House of Representatives</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI1">'
            "<header>Salaries and Expenses</header>"
            "<text>For expenses, $1,200,000,000.</text>"
            "</appropriations-intermediate>"
            '<appropriations-intermediate id="AI2">'
            "<header>House Leadership Offices</header>"
            "<text>For offices, $22,000,000.</text>"
            "</appropriations-intermediate>"
            "</section>"
            "</title>"
        )
        nodes = walk_title(title, "LEGISLATIVE BRANCH", "")
        # Should produce: 1 section node + 2 intermediate nodes (major has no text)
        assert len(nodes) == 3
        assert nodes[0].tag == "section"
        assert nodes[0].body_text == "The following sums are appropriated."
        assert nodes[1].tag == "appropriations-intermediate"
        assert nodes[1].match_path == (
            "legislative branch",
            "house of representatives",
            "salaries and expenses",
        )
        assert "$1,200,000,000" in nodes[1].body_text
        assert nodes[2].match_path == (
            "legislative branch",
            "house of representatives",
            "house leadership offices",
        )

    def test_section_with_text_and_appropriations(self):
        """Section with own text AND appropriations produces both types of nodes."""
        title = ET.fromstring(
            '<title id="T1">'
            "<header>DEPT</header>"
            '<section id="S1">'
            "<enum>1.</enum>"
            "<text>General provision text.</text>"
            '<appropriations-intermediate id="AI1">'
            "<header>Sub Agency</header>"
            "<text>For expenses, $500,000.</text>"
            "</appropriations-intermediate>"
            "</section>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 2
        assert nodes[0].tag == "section"
        assert nodes[0].body_text == "General provision text."
        assert nodes[1].tag == "appropriations-intermediate"
        assert "$500,000" in nodes[1].body_text

    def test_section_without_appropriations_unchanged(self):
        """Regular sections without appropriations children behave as before."""
        title = ET.fromstring(
            '<title id="T1">'
            "<header>DEPT</header>"
            '<section id="S1">'
            "<enum>101.</enum>"
            "<text>No funds may be used for X.</text>"
            "</section>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 1
        assert nodes[0].tag == "section"
        assert nodes[0].body_text == "No funds may be used for X."

    def test_section_wrapping_scopes_context(self):
        """Context from section-wrapped appropriations does not leak to siblings."""
        title = ET.fromstring(
            '<title id="T1">'
            "<header>LEG BRANCH</header>"
            '<appropriations-major id="AM0">'
            "<header>Senate</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI0">'
            "<header>Senate salaries</header>"
            "<text>For salaries, $100,000.</text>"
            "</appropriations-intermediate>"
            '<section id="S101">'
            "<enum>101.</enum>"
            "<text>Sums appropriated.</text>"
            '<appropriations-major id="AM1">'
            "<header>House of Representatives</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI1">'
            "<header>House salaries</header>"
            "<text>For salaries, $200,000.</text>"
            "</appropriations-intermediate>"
            "</section>"
            '<appropriations-intermediate id="AI2">'
            "<header>Senate office</header>"
            "<text>For offices, $300,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "LEG BRANCH", "")
        # Pre-section: intermediate under Senate context
        assert nodes[0].match_path == ("leg branch", "senate", "senate salaries")
        # Section node
        assert nodes[1].tag == "section"
        # Inside section: intermediate under House context
        assert nodes[2].match_path == (
            "leg branch",
            "house of representatives",
            "house salaries",
        )
        # After section: context reverts to Senate (not House)
        assert nodes[3].match_path == ("leg branch", "senate", "senate office")

    def test_subtitle_with_sections(self):
        """Subtitles containing sections should be walked, with subtitle header in path."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>POLICY PROVISIONS</header>"
            '<subtitle id="ST1">'
            "<enum>A</enum>"
            "<header>Tax Relief</header>"
            '<section id="S101">'
            "<enum>101.</enum>"
            "<header>Extension of credits</header>"
            "<text>The tax credit under section 45 is extended through 2025.</text>"
            "</section>"
            '<section id="S102">'
            "<enum>102.</enum>"
            "<header>Deduction increase</header>"
            "<text>The standard deduction is increased to $15,000.</text>"
            "</section>"
            "</subtitle>"
            "</title>"
        )
        nodes = walk_title(title, "POLICY PROVISIONS", "")
        assert len(nodes) == 2
        assert nodes[0].section_number == "Sec. 101"
        assert nodes[0].match_path == ("policy provisions", "tax relief", "sec. 101")
        assert "extended" in nodes[0].body_text
        assert nodes[1].section_number == "Sec. 102"
        assert nodes[1].match_path == ("policy provisions", "tax relief", "sec. 102")

    def test_subtitle_with_nested_part(self):
        """Sections inside a part inside a subtitle should include both headers in path."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>EXTENSIONS</header>"
            '<subtitle id="ST1">'
            "<enum>A</enum>"
            "<header>Health Programs</header>"
            '<part id="P1">'
            "<enum>I</enum>"
            "<header>Medicare</header>"
            '<section id="S101">'
            "<enum>101.</enum>"
            "<text>The Medicare program is extended through 2025.</text>"
            "</section>"
            '<section id="S102">'
            "<enum>102.</enum>"
            "<text>Reimbursement rates are adjusted.</text>"
            "</section>"
            "</part>"
            "</subtitle>"
            "</title>"
        )
        nodes = walk_title(title, "EXTENSIONS", "")
        assert len(nodes) == 2
        # Path should include both subtitle and part headers
        assert nodes[0].match_path == ("extensions", "health programs", "medicare", "sec. 101")
        assert nodes[1].match_path == ("extensions", "health programs", "medicare", "sec. 102")

    def test_subtitle_context_does_not_leak(self):
        """Subtitle context should not leak back to title-level siblings."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-major id="AM1">'
            "<header>Agency A</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI1">'
            "<header>Sub Agency</header>"
            "<text>For expenses, $100,000.</text>"
            "</appropriations-intermediate>"
            '<subtitle id="ST1">'
            "<enum>A</enum>"
            "<header>Tax Provisions</header>"
            '<section id="S101">'
            "<enum>101.</enum>"
            "<text>The tax credit is extended.</text>"
            "</section>"
            "</subtitle>"
            '<appropriations-intermediate id="AI2">'
            "<header>Another Sub Agency</header>"
            "<text>For operations, $200,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 3
        # First node: Sub Agency under Agency A
        assert nodes[0].match_path == ("dept", "agency a", "sub agency")
        # Second node: section inside subtitle
        assert nodes[1].match_path == ("dept", "tax provisions", "sec. 101")
        # Third node: should be back under Agency A, not Tax Provisions
        assert nodes[2].match_path == ("dept", "agency a", "another sub agency")


class TestWalkBodySections:
    """Test walk_body_sections for bills with no titles (e.g., HR 2882 v1-3)."""

    def test_sections_from_body(self):
        body = ET.fromstring(
            "<legis-body>"
            '<section id="S1">'
            "<enum>1.</enum>"
            "<header>Short title</header>"
            "<text>This Act may be cited as the Udall Foundation Act.</text>"
            "</section>"
            '<section id="S2">'
            "<enum>2.</enum>"
            "<header>Reauthorization</header>"
            "<text>Section 12 is amended to read as follows.</text>"
            "</section>"
            "</legis-body>"
        )
        nodes = walk_body_sections(body)
        assert len(nodes) == 2
        assert nodes[0].match_path == ("sec. 1",)
        assert nodes[0].section_number == "Sec. 1"
        assert nodes[0].header_text == "Short title"
        assert "Udall Foundation" in nodes[0].body_text
        assert nodes[1].match_path == ("sec. 2",)

    def test_empty_body(self):
        body = ET.fromstring("<legis-body/>")
        nodes = walk_body_sections(body)
        assert len(nodes) == 0

    def test_non_section_children_skipped(self):
        body = ET.fromstring(
            "<legis-body>"
            "<pagebreak/>"
            '<section id="S1">'
            "<enum>1.</enum>"
            "<header>Title</header>"
            "<text>Content here.</text>"
            "</section>"
            "</legis-body>"
        )
        nodes = walk_body_sections(body)
        assert len(nodes) == 1

    def test_section_with_subsections(self):
        """Sections with subsections but no direct <text> should still be captured."""
        body = ET.fromstring(
            "<legis-body>"
            '<section id="S2">'
            "<enum>2.</enum>"
            "<header>Sanctions</header>"
            "<subsection>"
            "<header>In general</header>"
            "<text>The President shall impose sanctions.</text>"
            "</subsection>"
            "<subsection>"
            "<header>Penalties</header>"
            "<text>A person that violates shall be fined.</text>"
            "</subsection>"
            "</section>"
            "</legis-body>"
        )
        nodes = walk_body_sections(body)
        assert len(nodes) == 1
        node = nodes[0]
        assert node.match_path == ("sec. 2",)
        assert node.header_text == "Sanctions"
        assert "President shall impose sanctions" in node.body_text
        assert "person that violates" in node.body_text

    def test_section_with_text_and_subsections(self):
        """Sections with both <text> and <subsection> should capture all content."""
        body = ET.fromstring(
            "<legis-body>"
            '<section id="S1">'
            "<enum>1.</enum>"
            "<header>Reporting</header>"
            "<text>The agency shall submit a report that includes:</text>"
            "<subsection>"
            "<enum>(a)</enum>"
            "<text>a description of total expenditures of $5,000,000</text>"
            "</subsection>"
            "<subsection>"
            "<enum>(b)</enum>"
            "<text>an assessment of program effectiveness</text>"
            "</subsection>"
            "</section>"
            "</legis-body>"
        )
        nodes = walk_body_sections(body)
        assert len(nodes) == 1
        node = nodes[0]
        assert "shall submit a report" in node.body_text
        assert "$5,000,000" in node.body_text
        assert "program effectiveness" in node.body_text

    def test_section_without_text_or_subsections(self):
        """Sections with nothing extractable are skipped."""
        body = ET.fromstring(
            '<legis-body><section id="S1"><enum>1.</enum><header>Short title</header></section></legis-body>'
        )
        nodes = walk_body_sections(body)
        assert len(nodes) == 0


class TestNormalizeBill:
    """Test normalize_bill with inline XML written to temp files."""

    def test_with_divisions(self, tmp_path):
        """Bill with divisions: walks titles within each division."""
        xml = (
            '<bill bill-stage="Enrolled-Bill">'
            "<form>"
            "<congress>One Hundred Eighteenth Congress</congress>"
            "<legis-num>H. R. 4366</legis-num>"
            "</form>"
            '<legis-body style="OLC">'
            '<division id="D1">'
            "<enum>A</enum>"
            "<header>Military Construction</header>"
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPARTMENT OF DEFENSE</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Military construction, army</header>"
            "<text>For acquisition, $1,000,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
            "</division>"
            '<division id="D2">'
            "<enum>B</enum>"
            "<header>Agriculture</header>"
            '<title id="T2">'
            "<enum>I</enum>"
            "<header>AGRICULTURE PROGRAMS</header>"
            '<appropriations-intermediate id="AI2">'
            "<header>Farm loans</header>"
            "<text>For loans, $500,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
            "</division>"
            "</legis-body>"
            "</bill>"
        )
        xml_path = tmp_path / "1_enrolled-bill.xml"
        xml_path.write_text(xml)

        tree = normalize_bill(xml_path)
        assert tree.congress == 118
        assert tree.bill_type == "hr"
        assert tree.bill_number == 4366
        assert tree.version == "enrolled-bill"
        content = _content(tree)
        assert len(content) == 2
        assert content[0].match_path == ("department of defense", "military construction, army")
        assert content[0].display_path[0] == "Division A: Military Construction"
        assert content[1].match_path == ("agriculture programs", "farm loans")
        assert content[1].display_path[0] == "Division B: Agriculture"

    def test_no_divisions_with_titles(self, tmp_path):
        """Bill without divisions: walks titles directly from body."""
        xml = (
            '<bill bill-stage="Reported-in-House">'
            "<form>"
            "<congress>118th CONGRESS</congress>"
            "<legis-num>H. R. 4366</legis-num>"
            "</form>"
            '<legis-body style="appropriations">'
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPARTMENT OF DEFENSE</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Military construction, army</header>"
            "<text>For acquisition, $1,876,875,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
            "</legis-body>"
            "</bill>"
        )
        xml_path = tmp_path / "1_reported-in-house.xml"
        xml_path.write_text(xml)

        tree = normalize_bill(xml_path)
        assert tree.congress == 118
        assert tree.version == "reported-in-house"
        content = _content(tree)
        assert len(content) == 1
        assert content[0].match_path == ("department of defense", "military construction, army")
        # display_path keeps the title's enum (#50); match_path stays header-only.
        assert content[0].display_path == ("TITLE I—DEPARTMENT OF DEFENSE", "Military construction, army")

    def test_official_title_parsed_from_form(self, tmp_path):
        """The long <official-title> is captured for the report heading."""
        xml = (
            '<bill bill-stage="Reported-in-House">'
            "<form>"
            "<congress>118th CONGRESS</congress>"
            "<legis-num>H. R. 4366</legis-num>"
            "<official-title>Making appropriations for military construction, "
            "and for other purposes.</official-title>"
            "</form>"
            '<legis-body style="appropriations">'
            '<title id="T1"><enum>I</enum><header>DEPARTMENT OF DEFENSE</header>'
            '<appropriations-intermediate id="AI1"><header>Military construction, army</header>'
            "<text>For acquisition, $1.</text></appropriations-intermediate></title>"
            "</legis-body></bill>"
        )
        xml_path = tmp_path / "1_reported-in-house.xml"
        xml_path.write_text(xml)

        tree = normalize_bill(xml_path)
        assert tree.official_title == "Making appropriations for military construction, and for other purposes."

    def test_no_titles_sections_only(self, tmp_path):
        """Bill with just sections under body (e.g., HR 2882 v1)."""
        xml = (
            '<bill bill-stage="Introduced-in-House">'
            "<form>"
            "<congress>118th CONGRESS</congress>"
            "<legis-num>H. R. 2882</legis-num>"
            "</form>"
            '<legis-body style="OLC">'
            '<section id="S1">'
            "<enum>1.</enum>"
            "<header>Short title</header>"
            "<text>This Act may be cited as the Udall Foundation Act.</text>"
            "</section>"
            "</legis-body>"
            "</bill>"
        )
        xml_path = tmp_path / "1_introduced-in-house.xml"
        xml_path.write_text(xml)

        tree = normalize_bill(xml_path)
        assert tree.bill_type == "hr"
        assert tree.bill_number == 2882
        content = _content(tree)
        assert len(content) == 1
        assert content[0].match_path == ("sec. 1",)

    def test_version_from_filename(self, tmp_path):
        xml = (
            '<bill bill-stage="Engrossed-in-House">'
            "<form>"
            "<congress>118th CONGRESS</congress>"
            "<legis-num>H. R. 100</legis-num>"
            "</form>"
            '<legis-body style="OLC">'
            '<section id="S1"><enum>1.</enum><text>Text.</text></section>'
            "</legis-body>"
            "</bill>"
        )
        xml_path = tmp_path / "2_engrossed-in-house.xml"
        xml_path.write_text(xml)

        tree = normalize_bill(xml_path)
        assert tree.version == "engrossed-in-house"

    def test_divisions_with_sibling_sections(self, tmp_path):
        """Preamble sections alongside divisions should be captured."""
        xml = (
            '<bill bill-stage="Enrolled-Bill">'
            "<form>"
            "<congress>One Hundred Eighteenth Congress</congress>"
            "<legis-num>H. R. 4366</legis-num>"
            "</form>"
            '<legis-body style="OLC">'
            '<section id="S1">'
            "<enum>1.</enum>"
            "<header>Short title</header>"
            "<text>This Act may be cited as the Example Act.</text>"
            "</section>"
            '<section id="S2">'
            "<enum>2.</enum>"
            "<header>References</header>"
            "<text>Except as stated, this Act refers to title 42.</text>"
            "</section>"
            '<division id="D1">'
            "<enum>A</enum>"
            "<header>Military Construction</header>"
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPARTMENT OF DEFENSE</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Military construction, army</header>"
            "<text>For acquisition, $1,000,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
            "</division>"
            "</legis-body>"
            "</bill>"
        )
        xml_path = tmp_path / "6_enrolled-bill.xml"
        xml_path.write_text(xml)

        tree = normalize_bill(xml_path)
        content = _content(tree)
        assert len(content) == 3
        # Preamble sections come first
        assert content[0].tag == "section"
        assert content[0].match_path == ("sec. 1",)
        assert content[0].division_label == ""
        assert content[1].tag == "section"
        assert content[1].match_path == ("sec. 2",)
        # Division node follows
        assert content[2].match_path == ("department of defense", "military construction, army")
        assert content[2].division_label.startswith("Division A")

    def test_titles_with_sibling_sections(self, tmp_path):
        """Preamble sections alongside titles should be captured."""
        xml = (
            '<bill bill-stage="Reported-in-House">'
            "<form>"
            "<congress>118th CONGRESS</congress>"
            "<legis-num>H. R. 4366</legis-num>"
            "</form>"
            '<legis-body style="appropriations">'
            '<section id="S1">'
            "<enum>1.</enum>"
            "<header>Short title</header>"
            "<text>This Act may be cited as the Example Act.</text>"
            "</section>"
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPARTMENT OF DEFENSE</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Military construction, army</header>"
            "<text>For acquisition, $1,876,875,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
            "</legis-body>"
            "</bill>"
        )
        xml_path = tmp_path / "1_reported-in-house.xml"
        xml_path.write_text(xml)

        tree = normalize_bill(xml_path)
        content = _content(tree)
        assert len(content) == 2
        assert content[0].tag == "section"
        assert content[0].match_path == ("sec. 1",)
        assert content[1].match_path == ("department of defense", "military construction, army")


class TestFrontMatter:
    """Front matter from <form> + enacting clause (#48)."""

    def _bill(self, tmp_path, *, enacting_attr="", legis_type="AN ACT", official=True):
        title_line = (
            "<official-title>Making appropriations, and for other purposes.</official-title>" if official else ""
        )
        xml = (
            '<bill bill-stage="Reported-in-House">'
            "<form>"
            '<distribution-code display="yes">I</distribution-code>'
            "<congress>118th CONGRESS</congress>"
            "<session>2d Session</session>"
            "<legis-num>H. R. 8752</legis-num>"
            f"<legis-type>{legis_type}</legis-type>"
            f"{title_line}"
            "</form>"
            f'<legis-body style="appropriations"{enacting_attr}>'
            '<title id="T1"><enum>I</enum><header>DEPARTMENTAL MANAGEMENT</header>'
            '<appropriations-intermediate id="AI1"><header>Operations</header>'
            "<text>For necessary expenses, $5,000,000.</text></appropriations-intermediate></title>"
            "</legis-body></bill>"
        )
        path = tmp_path / "1_reported-in-house.xml"
        path.write_text(xml)
        return normalize_bill(path)

    def test_front_matter_nodes_in_render_order(self, tmp_path):
        tree = self._bill(tmp_path)
        fm = [n for n in tree.nodes if n.tag == "front-matter"]
        keys = [n.match_path for n in fm]
        assert keys == [
            ("front matter", "masthead"),
            ("front matter", "official title"),
            ("front matter", "enacting clause"),
        ]
        # Front matter renders before any body content.
        assert tree.nodes[: len(fm)] == fm

    def test_front_matter_has_empty_display_path(self, tmp_path):
        """Empty display_path -> the serializer emits the body with no heading."""
        tree = self._bill(tmp_path)
        for n in tree.nodes:
            if n.tag == "front-matter":
                assert n.display_path == ()

    def test_masthead_includes_congress_session_number_and_act(self, tmp_path):
        tree = self._bill(tmp_path)
        masthead = next(n for n in tree.nodes if n.match_path == ("front matter", "masthead"))
        assert masthead.body_text == "118th CONGRESS\n2d Session\nH. R. 8752\nAN ACT"

    def test_distribution_code_dropped(self, tmp_path):
        """GPO renders <distribution-code> as nothing; it must not lead the masthead."""
        tree = self._bill(tmp_path)
        masthead = next(n for n in tree.nodes if n.match_path == ("front matter", "masthead"))
        # The distribution code ("I") is dropped: the masthead starts with the congress.
        assert masthead.body_text.splitlines()[0] == "118th CONGRESS"

    def test_official_title_is_its_own_node(self, tmp_path):
        tree = self._bill(tmp_path)
        title = next(n for n in tree.nodes if n.match_path == ("front matter", "official title"))
        assert title.body_text == "Making appropriations, and for other purposes."

    def test_enacting_clause_synthesized(self, tmp_path):
        tree = self._bill(tmp_path)
        enacting = next(n for n in tree.nodes if n.match_path == ("front matter", "enacting clause"))
        assert enacting.body_text.startswith("Be it enacted by the Senate and House")

    def test_enacting_clause_suppressed_by_attribute(self, tmp_path):
        tree = self._bill(tmp_path, enacting_attr=' display-enacting-clause="no-display-enacting-clause"')
        keys = [n.match_path for n in tree.nodes if n.tag == "front-matter"]
        assert ("front matter", "enacting clause") not in keys

    def test_no_form_yields_no_front_matter(self, tmp_path):
        xml = (
            '<bill bill-stage="Reported-in-House"><legis-body style="OLC">'
            '<section id="S1"><enum>1.</enum><text>Text.</text></section>'
            "</legis-body></bill>"
        )
        path = tmp_path / "1_reported-in-house.xml"
        path.write_text(xml)
        tree = normalize_bill(path)
        assert not [n for n in tree.nodes if n.tag == "front-matter"]


@pytest.mark.slow
class TestNormalizeBillIntegration:
    """Integration tests against real bill XML files."""

    def test_reported_in_house_produces_nodes(self, hr4366_v1):
        assert hr4366_v1.congress == 118
        assert hr4366_v1.bill_type == "hr"
        assert hr4366_v1.bill_number == 4366
        assert hr4366_v1.version == "reported-in-house"
        assert len(_content(hr4366_v1)) == 165

    def test_reported_in_house_has_expected_paths(self, hr4366_v1):
        match_paths = [n.match_path for n in hr4366_v1.nodes]
        assert ("department of defense", "military construction, army") in match_paths
        assert ("department of defense", "military construction, navy and marine corps") in match_paths
        assert ("department of veterans affairs", "veterans health administration", "medical services") in match_paths

    def test_enrolled_bill_node_count(self, hr4366_v6):
        assert hr4366_v6.congress == 118
        assert len(_content(hr4366_v6)) == 1095

    def test_enrolled_no_empty_body_text(self, hr4366_v6):
        empty = [n for n in hr4366_v6.nodes if not n.body_text]
        assert empty == [], f"Nodes with empty body_text: {[n.display_path for n in empty[:5]]}"

    def test_enrolled_has_all_seven_divisions(self, hr4366_v6):
        div_labels = sorted(
            set(
                n.display_path[0]
                for n in hr4366_v6.nodes
                if n.display_path and n.display_path[0].startswith("Division")
            )
        )
        assert len(div_labels) == 7
        expected_prefixes = [
            "Division A:",
            "Division B:",
            "Division C:",
            "Division D:",
            "Division E:",
            "Division F:",
            "Division G:",
        ]
        for prefix in expected_prefixes:
            assert any(d.startswith(prefix) for d in div_labels), f"Missing {prefix}"

    def test_enrolled_has_preamble_sections(self, hr4366_v6):
        """Preamble sections (Short Title, etc.) should be captured alongside divisions."""
        sec1 = [n for n in hr4366_v6.nodes if n.section_number == "Sec. 1"]
        assert len(sec1) == 1
        assert "cited as" in sec1[0].body_text.lower()
        assert sec1[0].division_label == ""

    def test_enrolled_division_node_counts(self, hr4366_v6):
        """Each division has an expected number of nodes."""
        counts = {}
        for n in hr4366_v6.nodes:
            div = n.display_path[0] if n.display_path else "unknown"
            counts[div] = counts.get(div, 0) + 1
        by_letter = {}
        for div, count in counts.items():
            letter = div.split(":")[0].replace("Division ", "") if "Division" in div else div
            by_letter[letter] = count
        assert by_letter["A"] == 162
        assert by_letter["B"] == 178
        assert by_letter["C"] == 173
        assert by_letter["D"] == 107
        assert by_letter["E"] == 186
        assert by_letter["F"] == 239
        assert by_letter["G"] == 44

    def test_enrolled_content_matches_path(self, hr4366_v6):
        """Spot-check that node body_text contains content appropriate to its path."""
        nodes_by_path = {n.match_path: n for n in hr4366_v6.nodes}

        army = nodes_by_path[("department of defense", "military construction, army")]
        assert "public works" in army.body_text.lower() or "construction" in army.body_text.lower()

        med = nodes_by_path[("department of veterans affairs", "veterans health administration", "medical services")]
        assert "inpatient" in med.body_text.lower() or "outpatient" in med.body_text.lower()


class TestBillNodeDivisionLabel:
    def test_division_label_field_accessible(self):
        """BillNode should have a division_label field."""
        node = BillNode(
            match_path=("general provisions",),
            display_path=("Division A: Military Construction", "General Provisions"),
            tag="section",
            element_id="id1",
            header_text="General Provisions",
            body_text="Some text",
            section_number="Sec. 501",
            division_label=(
                "Division A: Military Construction, Veterans Affairs, and Related Agencies Appropriations Act, 2024"
            ),
        )
        assert node.division_label == (
            "Division A: Military Construction, Veterans Affairs, and Related Agencies Appropriations Act, 2024"
        )

    @pytest.mark.slow
    def test_normalize_bill_populates_division_label(self, hr4366_v6):
        """normalize_bill should set division_label on nodes from multi-division bills."""
        div_a_nodes = [n for n in hr4366_v6.nodes if n.division_label.startswith("Division A:")]
        assert len(div_a_nodes) > 0
        assert "Military Construction" in div_a_nodes[0].division_label


class TestNormalizeDivisionTitle:
    def test_basic(self):
        assert normalize_division_title("Division A: Military Construction") == "military construction"

    def test_letter_insensitive(self):
        result_a = normalize_division_title("Division A: Military Construction")
        result_c = normalize_division_title("Division C: Military Construction")
        assert result_a == result_c

    def test_long_title(self):
        label = "Division B: Agriculture, Rural Development, Food and Drug Administration, and Related Agencies"
        assert (
            normalize_division_title(label)
            == "agriculture, rural development, food and drug administration, and related agencies"
        )

    def test_empty_string(self):
        assert normalize_division_title("") == ""

    def test_no_colon(self):
        assert normalize_division_title("Division F") == ""

    def test_embedded_newline(self):
        label = "Division B: LEGISLATIVE BRANCH\nAPPROPRIATIONS ACT, 2019"
        assert normalize_division_title(label) == "legislative branch appropriations act, 2019"
