"""Tests for formatters.text_serializer.serialize_tree.

The serializer flattens a BillTree's normalized node list into readable
plaintext. New display_path segments become headings (one per line, with
blank-line separation); body_text follows. Used to populate the canonical
JSON's optional `full_text` field for full-document tracked-changes views.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bill_tree import BillNode, BillTree, bill_title, normalize_bill
from formatters.text_serializer import serialize_tree, serialize_tree_with_offsets


def _node(
    *, path: tuple[str, ...] = (), header: str = "", body: str = "", tag: str = "section", sec: str = ""
) -> BillNode:
    return BillNode(
        match_path=tuple(p.lower() for p in path),
        display_path=path,
        tag=tag,
        element_id="",
        header_text=header,
        body_text=body,
        section_number=sec,
        division_label="",
    )


def _tree(nodes: list[BillNode]) -> BillTree:
    return BillTree(congress=118, bill_type="hr", bill_number=1, version="reported", nodes=nodes)


def test_empty_tree_serializes_to_empty_string():
    assert serialize_tree(_tree([])) == ""


def test_single_node_emits_header_and_body():
    tree = _tree([_node(path=("TITLE I", "Sec. 101"), header="Sec. 101", body="For necessary expenses, $5,000,000.")])
    out = serialize_tree(tree)
    assert "TITLE I" in out
    assert "Sec. 101" in out
    assert "For necessary expenses, $5,000,000." in out


def test_new_path_segments_become_headings_only_once():
    """Two sibling sections under the same TITLE share the parent heading,
    so the serializer should emit 'TITLE I' once, not twice."""
    nodes = [
        _node(path=("TITLE I", "Sec. 101"), body="body 101"),
        _node(path=("TITLE I", "Sec. 102"), body="body 102"),
    ]
    out = serialize_tree(_tree(nodes))
    assert out.count("TITLE I") == 1
    assert "Sec. 101" in out
    assert "Sec. 102" in out
    assert "body 101" in out
    assert "body 102" in out


def test_path_change_emits_new_segments():
    nodes = [
        _node(path=("TITLE I", "Sec. 101"), body="a"),
        _node(path=("TITLE II", "Sec. 201"), body="b"),
    ]
    out = serialize_tree(_tree(nodes))
    assert "TITLE I" in out
    assert "TITLE II" in out
    assert out.index("TITLE I") < out.index("TITLE II")


def test_node_with_empty_path_emits_only_body():
    """Some nodes (like the enacting clause) have no display_path. Emit body
    text without a heading."""
    out = serialize_tree(_tree([_node(path=(), header="", body="Be it enacted by the Senate and House…")]))
    assert "Be it enacted" in out


def test_node_with_empty_path_but_header_emits_header():
    out = serialize_tree(_tree([_node(path=(), header="ENACTING CLAUSE", body="...")]))
    assert "ENACTING CLAUSE" in out


def test_headings_are_separated_by_blank_lines():
    out = serialize_tree(
        _tree(
            [
                _node(path=("TITLE I", "Sec. 101"), body="alpha"),
                _node(path=("TITLE I", "Sec. 102"), body="beta"),
            ]
        )
    )
    # alpha and beta should each be on their own paragraph with at least one blank line between them.
    assert "alpha\n\nSec. 102" in out or "alpha\n\n" in out and "beta" in out


def test_section_node_emits_uppercased_run_in_heading():
    """Section nodes get a `SEC. N.  ` run-in heading (bill convention),
    using the section_number from the node. The redundant trailing path
    segment (lowercased "sec. 101") is suppressed so it doesn't appear
    twice."""
    nodes = [
        _node(
            path=("DEPARTMENT OF DEFENSE", "Administrative provisions", "sec. 101"),
            body="None of the funds made available...",
            tag="section",
        )
    ]
    nodes[0] = BillNode(
        match_path=("department of defense", "administrative provisions", "sec. 101"),
        display_path=("DEPARTMENT OF DEFENSE", "Administrative provisions", "sec. 101"),
        tag="section",
        element_id="",
        header_text="",
        body_text="None of the funds made available...",
        section_number="Sec. 101",
        division_label="",
    )
    out = serialize_tree(_tree(nodes))
    assert "SEC. 101." in out
    # The lowercased redundant path segment must not appear.
    assert "sec. 101" not in out
    # Body follows the run-in heading on the same line.
    assert "SEC. 101.  None of the funds" in out


# --- serialize_tree_with_offsets (TOC sections) ----------------------------


def _toc_tree() -> BillTree:
    return _tree(
        [
            _node(path=("TITLE I", "DEPARTMENT OF DEFENSE"), body="Funds for defense."),
            _node(
                path=("TITLE I", "DEPARTMENT OF DEFENSE", "sec. 101"),
                sec="Sec. 101",
                body="None of the funds made available...",
            ),
        ]
    )


def test_with_offsets_text_is_byte_identical_to_serialize_tree():
    tree = _toc_tree()
    text, _ = serialize_tree_with_offsets(tree)
    assert text == serialize_tree(tree)


def test_sections_carry_label_kind_and_offset_on_the_heading_line():
    text, sections = serialize_tree_with_offsets(_toc_tree())
    by_label = {s["label"]: s for s in sections}

    assert by_label["TITLE I"]["kind"] == "title"
    assert by_label["DEPARTMENT OF DEFENSE"]["kind"] == "account"
    assert by_label["Sec. 101"]["kind"] == "section"

    # Each offset lands exactly on its heading row (the bug we're guarding against
    # is offsets drifting off the line start).
    assert text[by_label["TITLE I"]["start"] :].startswith("TITLE I")
    assert text[by_label["DEPARTMENT OF DEFENSE"]["start"] :].startswith("DEPARTMENT OF DEFENSE")
    assert text[by_label["Sec. 101"]["start"] :].startswith("SEC. 101.")


def test_title_section_gets_account_descriptor():
    _, sections = serialize_tree_with_offsets(_toc_tree())
    title = next(s for s in sections if s["kind"] == "title")
    assert title.get("descriptor") == "DEPARTMENT OF DEFENSE"


def test_combined_title_label_gets_no_duplicate_descriptor():
    """An XML "TITLE I—<header>" label already carries the header, so it must not
    also pull the next account in as a descriptor (the em-dash guard, #50)."""
    nodes = [
        _node(path=("TITLE I—DEPARTMENTAL MANAGEMENT", "Office of the Secretary"), body="x"),
    ]
    text, sections = serialize_tree_with_offsets(_tree(nodes))
    title = next(s for s in sections if s["kind"] == "title")
    assert title["label"] == "TITLE I—DEPARTMENTAL MANAGEMENT"
    assert "descriptor" not in title
    # The title line still appears in the full-bill text.
    assert "TITLE I—DEPARTMENTAL MANAGEMENT" in text


def test_sections_are_in_document_order():
    _, sections = serialize_tree_with_offsets(_toc_tree())
    starts = [s["start"] for s in sections]
    assert starts == sorted(starts)


# --- bill_title heading -----------------------------------------------------


def test_bill_title_formats_designator_and_official_title():
    tree = BillTree(
        congress=118,
        bill_type="hr",
        bill_number=4366,
        version="reported",
        nodes=[],
        official_title="Making appropriations.",
    )
    assert bill_title(tree) == "H.R. 4366 — Making appropriations."


def test_bill_title_without_official_title_is_just_the_designator():
    tree = BillTree(congress=118, bill_type="s", bill_number=12, version="reported", nodes=[])
    assert bill_title(tree) == "S. 12"


_HR4366_V1 = Path("bills/118-hr-4366/1_reported-in-house.xml")


@pytest.mark.slow
@pytest.mark.skipif(
    not _HR4366_V1.exists(),
    reason="Real bill corpus not present; download with fetch_bills.py (see README)",
)
def test_real_bill_serializes_without_error_and_contains_known_text():
    """Smoke test: the HR4366 reported XML has 165 nodes; the serializer
    must produce non-trivial output containing recognizable strings.

    Marked `slow` because it depends on the real bill corpus, which CI
    doesn't check out (matches the pattern documented in pyproject.toml).
    """
    tree = normalize_bill(_HR4366_V1)
    out = serialize_tree(tree)
    assert len(out) > 1000
    assert "DEPARTMENT OF DEFENSE" in out
    assert "military construction" in out.lower()
