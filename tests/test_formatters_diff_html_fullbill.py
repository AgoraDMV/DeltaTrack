"""Tests for the full-bill tracked-changes view + Changes/Full toggle.

The view is driven by the canonical dict passed alongside the DiffView (PDF
path). Without a canonical (XML path), the report is unchanged — no toggle,
no embed — which the backward-compat test pins.
"""

from __future__ import annotations

import json
import re

from formatters.diff_html import _LLM_PROMPTS, format_diff_html
from formatters.view_model import DiffView


def _view(**overrides) -> DiffView:
    base = dict(
        bill_type="hr",
        bill_number=4366,
        congress=118,
        v1_label="Reported",
        v2_label="Engrossed",
        v1_version_number=None,
        v2_version_number=None,
        summary={"added": 1, "removed": 1, "modified": 1, "moved": 0},
        changes=(),
    )
    base.update(overrides)
    return DiffView(**base)


def _canonical() -> dict:
    # full_text mirrors pdf_full_text output: each line is "{num:>5}  {content}"
    # (five-space pad when unnumbered), pages joined by a blank line. Content
    # char spans for the single-page v2 below:
    #   line 1 "ADD0" -> 7..11   line 2 "MOD1" -> 19..23   line 3 "KEEP" -> 31..35
    v2 = "    1  ADD0\n    2  MOD1\n    3  KEEP"
    v1 = "    1  OLD0\n    2  OLD1\n    3  GONE"  # "GONE" content at 31..35
    return {
        "schema_version": "1.2",
        "full_text": {"v1": v1, "v2": v2},
        "changes": [
            {
                "id": "c-1",
                "change_type": "added",
                "text": {"old": None, "new": "ADD0"},
                "path": {"v1": None, "v2": ["TITLE I"]},
                "full_text_span": {"v1": None, "v2": {"start": 7, "end": 11}},
            },
            {
                "id": "c-2",
                "change_type": "modified",
                "text": {"old": "old1", "new": "MOD1"},
                "path": {"v1": ["TITLE I"], "v2": ["TITLE I"]},
                "full_text_span": {"v1": {"start": 7, "end": 11}, "v2": {"start": 19, "end": 23}},
            },
            {
                "id": "c-3",
                "change_type": "removed",
                "text": {"old": "GONE", "new": None},
                "path": {"v1": ["TITLE I", "SEC 2"], "v2": None},
                "full_text_span": {"v1": {"start": 31, "end": 35}, "v2": None},
            },
        ],
    }


def test_no_toggle_without_canonical():
    """XML path (no canonical) is unchanged: no toggle markup, no embed.

    Note the shared stylesheet always carries the .view-toggle CSS (inert when
    unused, as with other pipeline-specific selectors), so assert on the toggle
    *markup* (data-view, only emitted on the buttons), not the bare substring.
    """
    html = format_diff_html(_view())
    assert "data-view=" not in html
    assert 'id="diff-data"' not in html
    assert 'class="view view-full"' not in html


def test_toggle_and_both_views_present():
    html = format_diff_html(_view(), _canonical())
    assert 'class="view-toggle"' in html
    assert 'data-view="changes"' in html
    assert 'data-view="full"' in html
    assert 'class="view view-changes"' in html
    assert 'class="view view-full"' in html


def test_action_bar_has_nav_controls_and_counter():
    html = format_diff_html(_view(), _canonical())
    assert 'class="action-bar"' in html
    assert 'class="nav-controls"' in html
    assert 'id="nav-counter"' in html
    assert 'id="btn-prev"' in html
    assert 'id="btn-next"' in html
    # The old fixed bottom-right box is gone.
    assert 'class="nav-buttons"' not in html


def test_no_nav_controls_without_canonical():
    html = format_diff_html(_view())
    assert 'class="nav-controls"' not in html
    assert 'id="nav-counter"' not in html


def test_find_bar_present():
    html = format_diff_html(_view(), _canonical())
    assert 'id="find-input"' in html
    assert 'id="find-counter"' in html
    assert 'id="find-prev"' in html
    assert 'id="find-next"' in html
    # The sidebar search box is gone.
    assert 'id="sidebar-filter"' not in html


def test_no_find_bar_without_canonical():
    html = format_diff_html(_view())
    assert 'id="find-input"' not in html


def test_full_bill_toc_links():
    # section start 0 lands on the first display row ("ADD0"), which gets id="sec-0".
    sections = [{"label": "TITLE I", "kind": "title", "start": 0}]
    html = format_diff_html(_view(), _canonical(), sections=sections)
    assert 'class="sidebar-toc"' in html
    assert 'href="#sec-0"' in html
    assert 'id="sec-0"' in html
    assert "TITLE I" in html


def test_full_bill_toc_nests_sections_under_titles():
    # starts 0 / 12 land on display rows 1 ("ADD0") and 2 ("MOD1").
    sections = [
        {"label": "TITLE I", "kind": "title", "start": 0, "descriptor": "DEPARTMENT OF DEFENSE"},
        {"label": "SEC. 101", "kind": "section", "start": 12},
    ]
    html = format_diff_html(_view(), _canonical(), sections=sections)
    assert '<details class="toc-group">' in html
    assert "TITLE I &mdash; DEPARTMENT OF DEFENSE" in html  # descriptor labels the bare title
    assert 'href="#sec-0"' in html  # title is itself a jump target
    assert '<li class="toc-child"><a href="#sec-1">SEC. 101</a></li>' in html  # section nested under it
    assert 'id="sec-0"' in html and 'id="sec-1"' in html


def test_toc_empty_state_when_no_sections():
    html = format_diff_html(_view(), _canonical(), sections=[])
    assert 'class="sidebar-toc"' in html
    assert "No sections detected." in html


def test_no_toc_without_canonical():
    html = format_diff_html(_view())
    assert 'class="sidebar-toc"' not in html


def test_added_and_modified_marks_projected():
    html = format_diff_html(_view(), _canonical())
    # Added: just an <ins> around the v2 slice.
    assert '<ins class="diff-add" id="attr-c-1">ADD0</ins>' in html
    # Modified: new text highlighted in place; old text is not shown inline (it
    # lives in the Changes cards), so "old1" never reaches the full-bill view.
    assert '<span class="diff-mod" id="attr-c-2"' in html
    assert ">MOD1</span>" in html
    assert '<del class="diff-del">old1</del>' not in html  # old text not rendered inline
    assert "fb-del-row" not in html
    # Untouched tail text remains.
    assert "KEEP" in html


def test_full_bill_rows_carry_line_number_gutter():
    """Each source line renders as a row with its line number in the gutter."""
    html = format_diff_html(_view(), _canonical())
    # Page marker precedes the rows; line numbers sit in the gutter column.
    assert '<div class="fb-page">p. 1</div>' in html
    assert '<span class="fb-gutter">1</span>' in html
    assert '<span class="fb-gutter">3</span>' in html
    # The readable text column carries the content without the gutter prefix.
    assert '<span class="fb-text"><ins class="diff-add" id="attr-c-1">ADD0</ins></span>' in html


def test_modified_highlighted_in_place_without_old_text():
    """A modified change highlights its new text in place; the old text stays in
    the Changes cards (not echoed into the full-bill view)."""
    html = format_diff_html(_view(), _canonical())
    assert 'title="modified — see Changes for the old text"' in html
    assert "fb-del-row" not in html
    assert '<del class="diff-del">old1</del>' not in html


def test_removed_appendix_lists_removals():
    html = format_diff_html(_view(), _canonical())
    assert 'class="removed-appendix"' in html
    assert "TITLE I &gt; SEC 2" in html
    # The removed v1 slice is shown struck through.
    assert "GONE" in html


def test_meta_accounts_for_placed_and_removed():
    html = format_diff_html(_view(), _canonical())
    meta = re.search(r'<div class="full-bill-meta">(.*?)</div>', html).group(1)
    assert "2 of 3 changes shown inline" in meta
    assert "1 removed below" in meta


def test_export_button_and_modal_present():
    html = format_diff_html(_view(), _canonical())
    assert 'id="export-open"' in html
    assert 'id="export-modal"' in html
    assert 'id="dl-json"' in html
    assert 'id="dl-html"' in html


def test_export_prompts_shown_immediately():
    html = format_diff_html(_view(), _canonical())
    # Prompts are visible as soon as the modal opens — not gated on a download.
    assert 'id="export-prompts" class="export-prompts"' in html
    assert 'id="export-prompts" class="export-prompts" hidden' not in html
    assert "<h3>Ask AI</h3>" in html
    for prompt in _LLM_PROMPTS:
        assert prompt in html


def test_no_export_without_canonical():
    html = format_diff_html(_view())
    assert 'id="export-open"' not in html
    assert 'id="export-modal"' not in html


def test_canonical_json_embedded_and_valid():
    html = format_diff_html(_view(), _canonical())
    m = re.search(r'<script type="application/json" id="diff-data">(.*?)</script>', html, re.DOTALL)
    assert m, "embed missing"
    data = json.loads(m.group(1).replace("<\\/", "</"))
    assert data["schema_version"] == "1.2"
    assert len(data["changes"]) == 3
