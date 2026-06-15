"""Tests for the full-bill tracked-changes view + Changes/Full toggle.

The view is driven by the canonical dict passed alongside the DiffView (PDF
path). Without a canonical (XML path), the report is unchanged — no toggle,
no embed — which the backward-compat test pins.
"""

from __future__ import annotations

import json
import re

from formatters.diff_html import format_diff_html
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
    # v2 text indices:  ADD0(0-4) MOD1(5-9) KEEP(10-14)
    return {
        "schema_version": "1.2",
        "full_text": {"v1": "OLD0 OLD1 GONE", "v2": "ADD0 MOD1 KEEP"},
        "changes": [
            {
                "id": "c-1",
                "change_type": "added",
                "text": {"old": None, "new": "ADD0"},
                "path": {"v1": None, "v2": ["TITLE I"]},
                "full_text_span": {"v1": None, "v2": {"start": 0, "end": 4}},
            },
            {
                "id": "c-2",
                "change_type": "modified",
                "text": {"old": "old1", "new": "MOD1"},
                "path": {"v1": ["TITLE I"], "v2": ["TITLE I"]},
                "full_text_span": {"v1": {"start": 0, "end": 4}, "v2": {"start": 5, "end": 9}},
            },
            {
                "id": "c-3",
                "change_type": "removed",
                "text": {"old": "GONE", "new": None},
                "path": {"v1": ["TITLE I", "SEC 2"], "v2": None},
                "full_text_span": {"v1": {"start": 10, "end": 14}, "v2": None},
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


def test_added_and_modified_marks_projected():
    html = format_diff_html(_view(), _canonical())
    # Added: just an <ins> around the v2 slice.
    assert '<ins class="diff-add" id="attr-c-1">ADD0</ins>' in html
    # Modified: old struck through, new inserted.
    assert '<del class="diff-del">old1</del><ins class="diff-add" id="attr-c-2">MOD1</ins>' in html
    # Untouched tail text remains.
    assert "KEEP" in html


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


def test_canonical_json_embedded_and_valid():
    html = format_diff_html(_view(), _canonical())
    m = re.search(r'<script type="application/json" id="diff-data">(.*?)</script>', html, re.DOTALL)
    assert m, "embed missing"
    data = json.loads(m.group(1).replace("<\\/", "</"))
    assert data["schema_version"] == "1.2"
    assert len(data["changes"]) == 3
