"""Unit tests for the XML structure tree (#108, step 1).

Synthetic BillNode fixtures exercise the construction rules in isolation; the
slow real-bill tests guard against drift and assert tree-level conservation
(every flat node appears as exactly one content node — the structural analog of
the money gate). Orphan-title attribution is NOT tested here: it lives upstream
in normalize_bill (#154), so by the time build_xml_tree sees a node its
display_path already carries the right division prefix.
"""

import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest

from bill_tree import (
    BillNode,
    BillTree,
    extract_text_content,
    find_bill_body,
    normalize_bill,
)
from diff_bill import extract_amounts
from parsers.pdf_anchors import Anchor
from structure_tree import TreeNode, build_pdf_tree, build_xml_tree


def _node(display_path: tuple[str, ...], tag: str = "appropriations-small") -> BillNode:
    """A minimal content BillNode keyed only by display_path + tag (the two
    inputs build_xml_tree reads). Other fields are placeholders."""
    return BillNode(
        match_path=display_path,
        display_path=display_path,
        tag=tag,
        element_id=f"id-{'/'.join(display_path)}",
        header_text="",
        body_text="",
        section_number="",
        division_label=display_path[0] if display_path else "",
        display_text="",
    )


def _bill(nodes: list[BillNode]) -> BillTree:
    return BillTree(118, "hr", 1, "reported-in-house", nodes)


def _content_nodes(roots: list[TreeNode]) -> list[TreeNode]:
    """All tree nodes carrying a source, regardless of whether they also have
    children (an account that holds sub-accounts is both content and container)."""
    out: list[TreeNode] = []

    def walk(n: TreeNode) -> None:
        if n.source is not None:
            out.append(n)
        for c in n.children:
            walk(c)

    for r in roots:
        walk(r)
    return out


class TestPrefixNesting:
    def test_empty_node_list_returns_empty(self):
        assert build_xml_tree(_bill([])) == []

    def test_leading_empty_path_nodes_group_under_front_matter(self):
        # Front-matter / preamble / leading "Sec. 1" carry display_path=(); the
        # leading run is grouped under a synthesized "Front Matter" container so the
        # bill's opening is navigable (#161). The node is conserved as its child.
        roots = build_xml_tree(_bill([_node((), tag="front-matter")]))
        assert len(roots) == 1
        assert roots[0].label == "Front Matter"
        assert roots[0].level == "preamble"
        assert roots[0].source is None  # a synthesized container, not content
        assert [c.source is not None for c in roots[0].children] == [True]  # node conserved

    def test_nested_path_creates_interior_chain(self):
        dp = ("TITLE I", "AGRICULTURAL PROGRAMS", "Office of the Secretary", "Salaries")
        roots = build_xml_tree(_bill([_node(dp)]))
        assert [r.label for r in roots] == ["TITLE I"]
        content = _content_nodes(roots)
        assert len(content) == 1
        assert content[0].display_path == dp

    def test_siblings_share_one_interior_parent(self):
        a = _node(("TITLE I", "AGRICULTURAL PROGRAMS", "Office of the Secretary", "Salaries"))
        b = _node(("TITLE I", "AGRICULTURAL PROGRAMS", "Office of the Secretary", "Rent"))
        roots = build_xml_tree(_bill([a, b]))
        agency = roots[0].children[0].children[0]
        assert agency.label == "Office of the Secretary"
        assert agency.source is None
        assert len(agency.children) == 2

    def test_synthesized_interior_has_no_source(self):
        roots = build_xml_tree(_bill([_node(("TITLE I", "Bureau", "Account"))]))
        assert roots[0].source is None  # TITLE I
        assert roots[0].children[0].source is None  # Bureau

    def test_document_order_preserved_among_siblings(self):
        nodes = [_node(("TITLE I", x)) for x in ("Zeta", "Alpha", "Mu")]
        roots = build_xml_tree(_bill(nodes))
        assert [c.label for c in roots[0].children] == ["Zeta", "Alpha", "Mu"]


class TestLevelVocabulary:
    """Shared GPO vocabulary (docs/bill-structure.md): leaf from tag, interior
    positional."""

    @pytest.mark.parametrize(
        "tag,expected",
        [
            ("appropriations-major", "major"),
            ("appropriations-intermediate", "agency"),
            ("appropriations-small", "account"),
            ("section", "section"),
            ("front-matter", "preamble"),
        ],
    )
    def test_leaf_level_from_tag(self, tag, expected):
        roots = build_xml_tree(_bill([_node(("TITLE I", "Leaf"), tag=tag)]))
        assert _content_nodes(roots)[0].level == expected

    def test_interior_division_and_title(self):
        roots = build_xml_tree(_bill([_node(("Division A: X", "TITLE I", "Acct"))]))
        assert roots[0].level == "division"
        assert roots[0].children[0].level == "title"

    def test_interior_container_is_heading(self):
        roots = build_xml_tree(_bill([_node(("TITLE I", "Bureau of land management", "Acct"))]))
        assert roots[0].children[0].level == "heading"

    def test_interior_named_division_of_is_not_a_division(self):
        # "Division of Enforcement" is an agency/container, not a bill division —
        # the enum guard (like _TITLE_RE for #155) keeps it a heading.
        roots = build_xml_tree(_bill([_node(("TITLE I", "Division of Enforcement", "Acct"))]))
        assert roots[0].children[0].level == "heading"
        # A real division label still resolves to division.
        roots2 = build_xml_tree(_bill([_node(("Division A: Energy", "TITLE I", "Acct"))]))
        assert roots2[0].level == "division"

    def test_account_named_title_is_not_a_title(self):
        # #155 / #114: an account whose name begins with "Title 17" must stay an
        # account (level from tag), never be elevated to title by its text.
        roots = build_xml_tree(_bill([_node(("Division D: Energy", "TITLE III", "Title 17 loan guarantee program"))]))
        leaf = _content_nodes(roots)[0]
        assert leaf.label.startswith("Title 17")
        assert leaf.level == "account"


class TestGroupingHeaders:
    def test_grouping_header_is_a_standalone_interior_node(self):
        s1 = _node(("TITLE I", "Bureau", "Administrative provisions", "sec. 101"), tag="section")
        s2 = _node(("TITLE I", "Bureau", "Administrative provisions", "sec. 102"), tag="section")
        roots = build_xml_tree(_bill([s1, s2]))
        grouping = roots[0].children[0].children[0]
        assert grouping.label == "Administrative provisions"
        assert grouping.source is None
        assert [c.label for c in grouping.children] == ["sec. 101", "sec. 102"]


class TestContentContainer:
    def test_content_node_can_also_be_a_container(self):
        # An account that holds sub-accounts: it has a source AND children,
        # regardless of which order the nodes arrive in.
        parent = _node(("TITLE II", "CBP"))
        child = _node(("TITLE II", "CBP", "Operations"))
        for order in ([parent, child], [child, parent]):
            roots = build_xml_tree(_bill(order))
            cbp = roots[0].children[0]
            assert cbp.label == "CBP"
            assert cbp.source is not None
            assert [c.label for c in cbp.children] == ["Operations"]


class TestTreeConservation:
    """Every flat node maps to exactly one content node — the structural analog
    of the money conservation gate (build_xml_tree drops/dups nothing)."""

    def test_every_billnode_is_exactly_one_content_node(self):
        nodes = [
            _node((), tag="front-matter"),
            _node(("Division A: X", "TITLE I", "Acct1")),
            _node(("Division A: X", "TITLE I", "Acct2")),
            _node(("Division B: Y", "TITLE V—General provisions", "sec. 1"), tag="section"),
        ]
        content = _content_nodes(build_xml_tree(_bill(nodes)))
        assert {id(c.source) for c in content} == {id(n) for n in nodes}

    def test_duplicate_display_path_becomes_distinct_siblings(self):
        # Genuine cross-division collision (division-stripped match_path): two
        # nodes can share a display_path. Both must survive as content, not merge.
        a = _node(("TITLE I", "Senate"), tag="appropriations-small")
        b = _node(("TITLE I", "Senate"), tag="appropriations-small")
        content = _content_nodes(build_xml_tree(_bill([a, b])))
        assert {id(c.source) for c in content} == {id(a), id(b)}


def _anchor(line: int, kind: str, text: str, division: str = "") -> Anchor:
    return Anchor(page_number=1, line_number=line, kind=kind, text=text, division=division)


class TestPdfTree:
    """PDF builds the same tree from breadcrumb_for paths. Unlike XML, PDF emits
    interior levels as typed anchors, so those nodes carry a precise level."""

    def test_empty_anchor_list_returns_empty(self):
        assert build_pdf_tree([]) == []

    def test_title_account_two_levels(self):
        roots = build_pdf_tree([_anchor(1, "title", "TITLE I"), _anchor(2, "account", "OPERATIONS AND SUPPORT")])
        assert [r.label for r in roots] == ["TITLE I"]
        assert roots[0].level == "title"
        assert roots[0].source is not None  # title anchor is content AND container
        assert [c.label for c in roots[0].children] == ["OPERATIONS AND SUPPORT"]
        assert roots[0].children[0].level == "account"

    def test_full_four_level_chain_carries_precise_levels(self):
        roots = build_pdf_tree(
            [
                _anchor(1, "title", "TITLE I"),
                _anchor(2, "major", "DEPARTMENTAL MANAGEMENT"),
                _anchor(3, "agency", "OFFICE OF THE SECRETARY"),
                _anchor(4, "account", "OPERATIONS AND SUPPORT"),
            ]
        )
        levels = []
        n: TreeNode | None = roots[0]
        while n is not None:
            levels.append(n.level)
            n = n.children[0] if n.children else None
        assert levels == ["title", "major", "agency", "account"]

    def test_division_is_a_synthesized_root(self):
        roots = build_pdf_tree(
            [
                _anchor(1, "title", "TITLE I", division="Division A: ENERGY"),
                _anchor(2, "account", "CORPS OF ENGINEERS", division="Division A: ENERGY"),
            ]
        )
        assert [r.label for r in roots] == ["Division A: ENERGY"]
        assert roots[0].level == "division"
        assert roots[0].source is None  # no anchor of its own — a display segment
        assert roots[0].children[0].label == "TITLE I"

    def test_agency_scopes_account_and_is_a_content_container(self):
        # In document order (the only valid PDF input — breadcrumb_for resolves
        # position by list index, so a later agency can't scope an earlier
        # account), the agency anchor becomes a content node that is ALSO the
        # account's parent container.
        roots = build_pdf_tree(
            [
                _anchor(1, "title", "TITLE I"),
                _anchor(2, "agency", "MANAGEMENT DIRECTORATE"),
                _anchor(3, "account", "OPERATIONS AND SUPPORT"),
            ]
        )
        agency = roots[0].children[0]
        assert agency.label == "MANAGEMENT DIRECTORATE"
        assert agency.level == "agency"
        assert agency.source is not None  # content AND container
        assert [c.label for c in agency.children] == ["OPERATIONS AND SUPPORT"]

    def test_pdf_conservation_every_anchor_is_one_content_node(self):
        anchors = [
            _anchor(1, "title", "TITLE I"),
            _anchor(2, "agency", "AGENCY A"),
            _anchor(3, "account", "ACCT 1"),
            _anchor(4, "account", "ACCT 2"),
            _anchor(5, "section", "SEC. 101"),
        ]
        content = _content_nodes(build_pdf_tree(anchors))
        assert {id(c.source) for c in content} == {id(a) for a in anchors}


# --- Real-bill drift + conservation guards (slow; skip when corpus absent) ---

_CLEAN = Path("bills/118-hr-8752/1_reported-in-house.xml")
_CLEAN_PDF = Path("bills/118-hr-8752/1_reported-in-house.pdf")
_OMNIBUS = Path("bills/113-hr-3547/6_enrolled-bill.xml")
_BOTH_SHAPES = Path("bills/115-hr-5895/5_enrolled-bill.xml")


@pytest.mark.slow
@pytest.mark.skipif(not _CLEAN.exists(), reason="bill corpus not present (fetch_bills.py)")
def test_clean_bill_every_node_maps_to_one_content_node():
    bill = normalize_bill(_CLEAN)
    content = _content_nodes(build_xml_tree(bill))
    assert {id(c.source) for c in content} == {id(n) for n in bill.nodes}


@pytest.mark.slow
@pytest.mark.skipif(not _OMNIBUS.exists(), reason="bill corpus not present (fetch_bills.py)")
def test_omnibus_every_node_maps_to_one_content_node():
    bill = normalize_bill(_OMNIBUS)
    content = _content_nodes(build_xml_tree(bill))
    assert {id(c.source) for c in content} == {id(n) for n in bill.nodes}


@pytest.mark.slow
@pytest.mark.skipif(not _OMNIBUS.exists(), reason="bill corpus not present (fetch_bills.py)")
def test_omnibus_divisions_are_top_level_nodes():
    roots = build_xml_tree(normalize_bill(_OMNIBUS))
    division_roots = [r for r in roots if r.label.startswith("Division ")]
    assert len(division_roots) >= 3


@pytest.mark.slow
@pytest.mark.skipif(not _BOTH_SHAPES.exists(), reason="bill corpus not present (fetch_bills.py)")
def test_orphan_titles_absorbed_no_bare_title_roots():
    # normalize_bill (#154) attributes orphan titles to their division, so no
    # bare "TITLE ..." node survives at the top level of a division bill.
    roots = build_xml_tree(normalize_bill(_BOTH_SHAPES))
    bare_title_roots = [r for r in roots if r.label.upper().startswith("TITLE ")]
    assert bare_title_roots == []


@pytest.mark.slow
@pytest.mark.skipif(not _CLEAN_PDF.exists(), reason="bill corpus not present (fetch_bills.py)")
def test_pdf_real_bill_conserves_and_is_leveled():
    from parsers.pdf_anchors import extract_anchors
    from parsers.pdf_text import extract_clean_pages

    anchors = extract_anchors(extract_clean_pages(_CLEAN_PDF))
    content = _content_nodes(build_pdf_tree(anchors))
    # Conservation: every anchor maps to exactly one content node.
    assert {id(c.source) for c in content} == {id(a) for a in anchors}
    # The clean bill resolves the full leveled depth via typed anchors.
    levels_seen = {c.level for c in content}
    assert {"title", "major", "agency", "account"} <= levels_seen


# --- The money conservation gate (XML, strong): the union of per-node own_amounts
# measured against the INDEPENDENT raw-XML body (not the derived full_text, which
# is built from the same nodes — feedback_measure_at_consumed_output). over==0
# everywhere proves no parent/child double-count; dropped is exact on clean bills
# and a documented tolerant residue on the hard amendment/omnibus shapes
# (feedback_validate_against_hard_fixture). PDF has no independent ground truth, so
# its span-coverage check rides on step 4's offsets, not this gate. ---

_HR83_AMEND = Path("bills/113-hr-83/6_engrossed-amendment-house.xml")

# (path, max_dropped, why)
_CONSERVATION_FIXTURES = [
    (_CLEAN, 0, "clean bill — exact"),
    (_BOTH_SHAPES, 0, "both-shapes enrolled (#146 fix) — exact"),
    (_OMNIBUS, 1, "omnibus — 1 documented residue; cross-division same-name agencies must not double-count"),
    (_HR83_AMEND, 4, "amendment doc — 4 documented residue (deeply nested clause edge)"),
]


def _tree_own_amount_counter(roots: list[TreeNode]) -> Counter:
    c: Counter = Counter()

    def walk(n: TreeNode) -> None:
        c.update(n.own_amounts)
        for ch in n.children:
            walk(ch)

    for r in roots:
        walk(r)
    return c


def _raw_body_amount_counter(xml_path: Path) -> Counter:
    """Independent reference: amounts in the raw XML body, parsed directly — NOT
    via the tree's nodes — so the gate can't tautologically pass over dropped money."""
    body = find_bill_body(ET.parse(xml_path).getroot())
    return Counter(extract_amounts(extract_text_content(body)))


@pytest.mark.slow
@pytest.mark.parametrize(
    "path,max_dropped,why",
    _CONSERVATION_FIXTURES,
    ids=[p.parent.name for p, _, _ in _CONSERVATION_FIXTURES],
)
def test_money_conservation_no_overcount_bounded_drops(path: Path, max_dropped: int, why: str):
    if not path.exists():
        pytest.skip("bill corpus not present (fetch_bills.py)")
    tree_amounts = _tree_own_amount_counter(build_xml_tree(normalize_bill(path)))
    raw_amounts = _raw_body_amount_counter(path)

    over = sum((tree_amounts - raw_amounts).values())
    dropped = sum((raw_amounts - tree_amounts).values())

    # Strong invariant everywhere: the tree never over-counts (no node attaches an
    # amount twice; appropriations-* are flat siblings, so no parent/child sum).
    assert over == 0, f"{why}: tree over-counts {over} amount(s) — double-count"
    # Exact on clean bills; tolerant documented floor on hard shapes.
    assert dropped <= max_dropped, f"{why}: dropped {dropped} > documented {max_dropped}"
