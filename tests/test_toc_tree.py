"""Leveled full-bill TOC built from the canonical structure tree (#108, commit B).

The renderer's `_build_toc_from_tree` replaces the flat 2-level `sections` TOC with
arbitrary-depth nesting straight from the contract's `tree`. These assert on the
CONSUMED output (the rendered HTML), per measure-at-consumed-output:
  - the leveled TOC reproduces every heading the flat `sections` list carried
    (a superset — no coverage regression), and
  - the #155 fix is now VISIBLE: an account named "Title 17 …" nests as a leaf
    under its agency instead of being promoted to a title group.
"""

import re
from pathlib import Path

import pytest

from formatters.diff_html import _build_toc_from_tree, _node_anchor_offset, _walk_tree

_V1 = Path("bills/118-hr-8752/1_reported-in-house.xml")
_V2 = Path("bills/118-hr-8752/2_engrossed-in-house.xml")

pytestmark = pytest.mark.skipif(not _V1.exists(), reason="bill corpus not present (fetch_bills.py)")


def _node(label: str, level: str, start: int, children=()) -> dict:
    return {
        "label": label,
        "level": level,
        "own_amounts": [],
        "full_text_span": {"start": start, "end": start + len(label)},
        "children": list(children),
    }


def test_toc_from_tree_nests_to_arbitrary_depth():
    # division > title > agency > account renders as nested <details>, with the
    # leaf account as a plain link (toc-child), not a collapsible group.
    text = "\n".join(["Division A", "TITLE I", "DEPARTMENT OF ENERGY", "OPERATIONS"])
    tree = [
        _node(
            "Division A",
            "division",
            0,
            [
                _node(
                    "TITLE I",
                    "title",
                    11,
                    [
                        _node(
                            "DEPARTMENT OF ENERGY",
                            "agency",
                            19,
                            [
                                _node("OPERATIONS", "account", 40),
                            ],
                        ),
                    ],
                ),
            ],
        ),
    ]
    html = _build_toc_from_tree(tree, text)
    # three nested groups (division/title/agency each have children) + one leaf
    assert html.count('<details class="toc-group">') == 3
    assert html.count('<li class="toc-child">') == 1
    summaries = re.findall(r"<summary>(.*?)</summary>", html)
    assert any("DEPARTMENT OF ENERGY" in s for s in summaries)  # interior → group
    assert not any("OPERATIONS" in s for s in summaries)  # leaf → not a group


def test_account_named_title_is_not_promoted_to_a_toc_group():
    # #155 made visible: the flat TOC keyed group/leaf off a "TITLE "-prefix text
    # heuristic, so an account literally named "Title 17 …" became a title GROUP.
    # The tree types it as an account (tag-derived level), so it renders as a leaf.
    label = "Title 17 Innovative Technology Loan Guarantee Program"
    text = "\n".join(["TITLE III", "DEPARTMENT OF ENERGY", label])
    tree = [
        _node(
            "TITLE III",
            "title",
            0,
            [
                _node("DEPARTMENT OF ENERGY", "agency", 10, [_node(label, "account", 31)]),
            ],
        ),
    ]
    html = _build_toc_from_tree(tree, text)
    summaries = re.findall(r"<summary>(.*?)</summary>", html)
    assert not any("Title 17" in s for s in summaries), "Title 17 account wrongly rendered as a TOC group (#155)"
    leaves = re.findall(r'<li class="toc-child">(.*?)</li>', html)
    assert any("Title 17 Innovative" in leaf for leaf in leaves)


@pytest.mark.slow
def test_tree_toc_covers_every_flat_section_heading():
    # Superset / no coverage regression: every heading offset the flat `sections`
    # jump-list carried is reachable as a tree node's anchor offset. (Asserts the
    # DATA reproduces the old TOC's reach — NOT new-TOC-HTML == old-flat-HTML.)
    from bill_tree import normalize_bill
    from formatters.text_serializer import build_xml_full_text

    v1, v2 = normalize_bill(_V1), normalize_bill(_V2)
    full_text, _spans, sections, tree = build_xml_full_text(v1, v2)
    ft_v2 = full_text["v2"]
    node_offsets = {_node_anchor_offset(ft_v2, n) for n in _walk_tree(tree["v2"]) if n["full_text_span"] is not None}
    section_starts = {s["start"] for s in sections}
    missing = section_starts - node_offsets
    assert not missing, f"leveled TOC dropped {len(missing)} heading(s) the flat sections list reached"


def test_unlabeled_nodes_are_not_rendered_as_blank_toc_rows():
    # XML front-matter placeholders (masthead, enacting clause) carry empty labels;
    # they must not surface as blank, clickable TOC rows. Children of an unlabeled
    # node are hoisted so the subtree stays reachable.
    text = "\n".join(["", "TITLE I", "OPERATIONS"])
    tree = [
        _node("", "preamble", 0),  # unlabeled leaf -> dropped
        _node("", "division", 1, [_node("OPERATIONS", "account", 9)]),  # unlabeled group -> hoisted
        _node("TITLE I", "title", 1, [_node("OPERATIONS", "account", 9)]),
    ]
    html = _build_toc_from_tree(tree, text)
    leaves = re.findall(r'<li class="toc-child">(.*?)</li>', html)
    assert leaves, "expected real TOC entries"
    assert all(re.sub(r"<[^>]+>", "", leaf).strip() for leaf in leaves), "blank TOC row rendered"
    assert "OPERATIONS" in html  # hoisted child of the unlabeled group survived


@pytest.mark.slow
def test_real_xml_toc_has_no_blank_rows():
    from server.xml_compare import compare_xml_html

    html = compare_xml_html(_V1.read_bytes(), _V2.read_bytes(), start_label="v1", end_label="v2")
    toc = re.search(r'<div class="sidebar-toc".*?</nav>', html, re.S).group(0)
    leaves = re.findall(r'<li class="toc-child">(.*?)</li>', toc, re.S)
    blank = [leaf for leaf in leaves if not re.sub(r"<[^>]+>", "", leaf).strip()]
    assert not blank, f"{len(blank)} blank TOC rows in the rendered XML report"


@pytest.mark.slow
def test_tree_toc_links_all_resolve_to_full_bill_rows():
    # Every TOC link (#fb-off-N) has a matching id in the full-bill view — no
    # dangling anchors after the offset-based rewrite.
    from server.xml_compare import compare_xml_html

    html = compare_xml_html(_V1.read_bytes(), _V2.read_bytes(), start_label="v1", end_label="v2")
    targets = set(re.findall(r'href="#(fb-off-\d+)"', html))
    ids = set(re.findall(r'id="(fb-off-\d+)"', html))
    assert targets, "expected leveled TOC links in the rendered report"
    dangling = targets - ids
    assert not dangling, f"{len(dangling)} TOC links resolve to no full-bill row: {sorted(dangling)[:5]}"
