"""Unified HTML renderer for both XML and PDF bill diffs.

Consumes a DiffView produced by an adapter (formatters.adapters.xml_dict_to_view
or .pdf_diff_to_view). The renderer does not branch on which pipeline produced
the view — pipeline-specific data (citations, degraded styling, section
numbers) is rendered when present and omitted when absent.

The HTML output and CSS are deliberately shared across both pipelines so
staffers see one consistent product regardless of source format.
"""

from __future__ import annotations

import json
from html import escape

from formatters._text import fmt_dollar, word_diff
from formatters.view_model import ChangeView, DiffView

__all__ = ["format_diff_html"]


_SUMMARY_ORDER = ("modified", "added", "removed", "moved")


def _embed_canonical(canonical: dict) -> str:
    """Inline the canonical diff JSON so the report is self-contained.

    The standalone report opens in a new tab with no server round-trip
    available (the service is stateless), so the full-bill view and the
    export download both read this embedded payload client-side. ``</`` is
    neutralized so the JSON can't terminate the surrounding <script> tag.
    """
    payload = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    return f'<script type="application/json" id="diff-data">{payload}</script>'


def _build_card(change: ChangeView, index: int) -> str:
    """Render one ChangeView as a complete <div class="change-card">.

    Renders pipeline-specific features when their corresponding view-model
    fields are populated:
    - section_number → <span class="section-number"> inside the header
    - citation_html → emitted between header and body
    - degraded → adds "unanchored" to the card class and "degraded" to the h3
    - move_info_html → emitted at the top of a moved card's body region
    """
    extra_card_class = " unanchored" if change.degraded else ""
    h3_class = ' class="degraded"' if change.degraded else ""
    # Defensive escape: change_type is a Literal in the view model, but the XML
    # adapter pulls it from a dict that ultimately reflects upstream parser
    # output. Escape so a stray value can't break attribute quoting.
    ct = escape(change.change_type)

    parts = [f'<div class="change-card {ct}{extra_card_class}" id="change-{index}">']
    parts.append('<div class="change-header">')
    parts.append(f'<span class="badge badge-{ct}">{ct}</span>')
    parts.append(f"<h3{h3_class}>{change.heading_html}</h3>")
    if change.section_number:
        parts.append(f'<span class="section-number">{escape(change.section_number)}</span>')
    parts.append("</div>")

    if change.citation_html:
        parts.append(change.citation_html)

    body = _card_body_html(change)
    if body:
        parts.append(body)

    callout = _build_callout(change)
    if callout:
        parts.append(callout)

    parts.append("</div>")
    return "\n".join(parts)


def _card_body_html(change: ChangeView) -> str:
    """Render the body region of a card. Excludes header, citation, callout.

    Returns "" for any unrecognized change_type so a card surfaces only as a
    header + section reference. The four known types each get their own body
    shape.
    """
    if change.change_type == "added":
        return f'<div class="change-body added-text">{escape(change.new_text)}</div>'
    if change.change_type == "removed":
        return f'<div class="change-body removed-text">{escape(change.old_text)}</div>'
    if change.change_type == "moved":
        return _moved_body_html(change)
    if change.change_type == "modified":
        return _prose_body_html(change.old_text, change.new_text)
    return ""


def _prose_body_html(old_text: str, new_text: str) -> str:
    """Render a prose diff: inline word-diff when similar enough, stacked otherwise.

    Used as the body for `modified` changes and as the fallback for `moved`
    changes whose texts differ — keeping the "old vs new" comparison
    consistent regardless of change type.
    """
    inline = word_diff(old_text, new_text) if (old_text and new_text) else None
    if inline is not None:
        return f'<div class="change-body diff-inline">{inline}</div>'
    return (
        '<div class="change-body">\n'
        f'<div class="old-text">{escape(old_text)}</div>\n'
        f'<div class="new-text">{escape(new_text)}</div>\n'
        "</div>"
    )


def _moved_body_html(change: ChangeView) -> str:
    """Moved-card body: move-info div, then the prose diff (or single body when texts match)."""
    parts: list[str] = []
    if change.move_info_html:
        parts.append(change.move_info_html)
    if change.old_text == change.new_text:
        # Identical text — single body div with the (one) text. Prefer new_text;
        # fall back to old_text when new_text is empty (only possible if both are "").
        body = change.new_text or change.old_text
        parts.append(f'<div class="change-body">{escape(body)}</div>')
    else:
        parts.append(_prose_body_html(change.old_text, change.new_text))
    return "\n".join(parts)


def _build_callout(change: ChangeView) -> str:
    """Render the financial callout for a card.

    Layout: flex rows with semantic .increase / .decrease delta classes for
    color. Returns "" when there are no real amount changes.

    `change.amount_pairs` is already filtered to real changes by the adapters
    (both sides present and differing), so this function does not re-filter —
    every pair becomes a row, and zero deltas can't reach this code.
    """
    if not change.amount_pairs:
        return ""
    parts = ['<div class="financial-callout">']
    for old, new in change.amount_pairs:
        diff = new - old
        if diff > 0:
            delta_str = f"+{fmt_dollar(diff)}"
            delta_class = "increase"
        else:
            # Sign goes outside the dollar formatter so the result is "-$500", not "$-500".
            delta_str = f"-{fmt_dollar(abs(diff))}"
            delta_class = "decrease"
        parts.append(
            f'<div class="row"><span class="label">Amount:</span>'
            f"<span>{fmt_dollar(old)} &rarr; {fmt_dollar(new)}</span>"
            f'<span class="delta {delta_class}">({delta_str})</span></div>'
        )
    parts.append("</div>")
    return "".join(parts)


def _build_nav_item(change: ChangeView, index: int) -> str:
    """Render a single sidebar <li> for a change."""
    nav_class = "nav-item unanchored" if change.degraded else "nav-item"
    label = change.nav_label_html
    if change.section_number:
        label = f"{escape(change.section_number)} — {label}"
    ct = escape(change.change_type)
    return (
        f'<li class="{nav_class}" data-type="{ct}">'
        f'<a href="#change-{index}">'
        f'<span class="badge badge-{ct}">{ct}</span> '
        f"{label}"
        f"</a></li>"
    )


def _build_sidebar(view: DiffView) -> str:
    """Render the sidebar nav. Empty <ul></ul> when there are no changes."""
    items = "".join(_build_nav_item(c, i) for i, c in enumerate(view.changes))
    return (
        '<nav class="sidebar">\n'
        '<input type="text" id="sidebar-filter" placeholder="Filter sections...">\n'
        f"<ul>{items}</ul>\n"
        "</nav>"
    )


def _versions_html(view: DiffView) -> str:
    """Render the versions line.

    Canonical form: "v1: {label} → v2: {label} · {congress}th Congress".
    The "vN: " prefix is dropped when both version numbers are None — PDF
    inputs don't carry a version index, and "v1: Reported" is misleading
    when no such index exists.
    """
    if view.v1_version_number is not None or view.v2_version_number is not None:
        v1 = (
            f"v{view.v1_version_number}: {escape(view.v1_label)}"
            if view.v1_version_number is not None
            else escape(view.v1_label)
        )
        v2 = (
            f"v{view.v2_version_number}: {escape(view.v2_label)}"
            if view.v2_version_number is not None
            else escape(view.v2_label)
        )
    else:
        v1 = escape(view.v1_label)
        v2 = escape(view.v2_label)
    return f"{v1} &rarr; {v2} · {escape(str(view.congress))}th Congress"


def _summary_bar_html(summary: dict[str, int]) -> str:
    """Render the summary bar in canonical order, skipping zero buckets."""
    items: list[str] = []
    for key in _SUMMARY_ORDER:
        count = summary.get(key, 0)
        if count > 0:
            items.append(
                f'<span class="summary-item">'
                f'<span class="badge badge-{key}">{key}</span> '
                f"<strong>{count}</strong>"
                f"</span>"
            )
    return "".join(items)


def _bill_label(view: DiffView) -> str:
    """Pre-escaped "{BILL_TYPE} {N}" string."""
    return f"{escape(str(view.bill_type).upper())} {escape(str(view.bill_number))}"


def _cards_section_html(view: DiffView) -> str:
    """Cards section: stitch built cards together, or show a no-changes message."""
    if not view.changes:
        return '<p class="no-changes">No changes found between these versions.</p>'
    return "\n".join(_build_card(c, i) for i, c in enumerate(view.changes))


def _build_financial_summary(view: DiffView) -> str:
    """Render the top-of-page Financial Summary table.

    Includes only changes whose pre-filtered amount_pairs is non-empty. Each
    pair becomes a row; pairs from the same change share a section cell via
    rowspan when there are multiple. Each row carries a data-group index so
    the JS column sort keeps multi-pair groups together.

    Returns "" when no change has any real amount changes.
    """
    rows: list[tuple[int, ChangeView]] = [(i, c) for i, c in enumerate(view.changes) if c.amount_pairs]
    if not rows:
        return ""

    lines = [
        "<h2>Financial Summary</h2>",
        '<table class="financial-table">',
        "<thead><tr>",
        "<th>Section</th>",
        "<th>Old Amount</th>",
        "<th>New Amount</th>",
        "<th>Change ($)</th>",
        "<th>Change (%)</th>",
        "</tr></thead>",
        "<tbody>",
    ]

    for group_idx, (change_index, change) in enumerate(rows):
        pairs = change.amount_pairs
        section_label = change.heading_html or change.nav_label_html
        for pair_idx, (old, new) in enumerate(pairs):
            diff = new - old
            if diff > 0:
                change_dollar = f"+{fmt_dollar(diff)}"
                row_class = "increase"
            else:
                # _real_changes drops zero-deltas, so diff < 0 here.
                change_dollar = f"-{fmt_dollar(abs(diff))}"
                row_class = "decrease"
            if old != 0:
                pct_value = diff / old * 100
                pct_sign = "+" if pct_value >= 0 else ""
                change_pct = f"{pct_sign}{pct_value:.1f}%"
            else:
                change_pct = "—"

            if pair_idx == 0:
                rowspan_attr = f' rowspan="{len(pairs)}"' if len(pairs) > 1 else ""
                section_cell = f'<td{rowspan_attr}><a href="#change-{change_index}">{section_label}</a></td>'
            else:
                section_cell = ""

            lines.append(
                f'<tr class="{row_class}" data-group="{group_idx}">'
                f"{section_cell}"
                f'<td class="amount">{fmt_dollar(old)}</td>'
                f'<td class="amount">{fmt_dollar(new)}</td>'
                f'<td class="amount change-amount">{change_dollar}</td>'
                f'<td class="amount change-amount">{change_pct}</td>'
                f"</tr>"
            )

    lines.append("</tbody></table>")
    return "\n".join(lines)


def _has_full_bill(canonical: dict | None) -> bool:
    """Full-bill view is available only when the canonical carries v2 full text."""
    return bool(canonical and (canonical.get("full_text") or {}).get("v2"))


def _view_toggle_html(canonical: dict | None) -> str:
    """Changes/Full segmented control. Empty when there's no full text to show."""
    if not _has_full_bill(canonical):
        return ""
    return (
        '<div class="view-toggle" role="tablist" aria-label="View mode">'
        '<button class="view-toggle__btn is-active" data-view="changes" role="tab"'
        ' aria-selected="true">Changes</button>'
        '<button class="view-toggle__btn" data-view="full" role="tab"'
        ' aria-selected="false">Full bill</button>'
        "</div>"
    )


def _render_v2_mark(change: dict, v2_slice: str) -> str:
    """Wrap a placed change's v2 text slice with the right tracked-change mark."""
    cid = escape(str(change.get("id", "")))
    ct = change.get("change_type")
    if ct == "added":
        return f'<ins class="diff-add" id="attr-{cid}">{escape(v2_slice)}</ins>'
    if ct == "modified":
        old = (change.get("text") or {}).get("old") or ""
        return (
            f'<del class="diff-del">{escape(old)}</del><ins class="diff-add" id="attr-{cid}">{escape(v2_slice)}</ins>'
        )
    if ct == "moved":
        move = change.get("move") or {}
        if move.get("kind") == "renumbered":
            note = (
                f"moved here (renumbered {escape(str(move.get('old_label', '')))}"
                f" → {escape(str(move.get('new_label', '')))})"
            )
        else:
            note = "moved here"
        return f'<span class="moved-mark" id="attr-{cid}" title="{note}">{escape(v2_slice)}</span>'
    return f'<del class="diff-del">{escape(v2_slice)}</del>'


def _full_bill_meta_html(*, total: int, placed: int, removed: int, unplaced: int) -> str:
    bits = [f"{placed} of {total} changes shown inline"]
    if removed:
        bits.append(f"{removed} removed below")
    if unplaced:
        bits.append(f"{unplaced} not placed (see Changes)")
    return f'<div class="full-bill-meta">{" &middot; ".join(bits)}</div>'


def _removed_appendix_html(removed: list[dict], v1_text: str) -> str:
    """List removals (which have no v2 home) below the projected v2 text."""
    blocks: list[str] = []
    for change in removed:
        span = change["full_text_span"]["v1"]
        text = v1_text[span["start"] : span["end"]]
        path = " &gt; ".join(escape(p) for p in ((change.get("path") or {}).get("v1") or []))
        heading = path or "<em>(unknown location)</em>"
        cid = escape(str(change.get("id", "")))
        blocks.append(
            f'<article class="removed-block" id="attr-{cid}">'
            f'<div class="removed-block__head">{heading}</div>'
            f'<del class="diff-del">{escape(text)}</del></article>'
        )
    return (
        '<section class="removed-appendix">'
        "<h3>Removed in end version</h3>"
        '<p class="removed-appendix__note">These sections existed in the start version and have '
        "no corresponding location in the end version.</p>"
        f"{''.join(blocks)}</section>"
    )


def _full_bill_html(canonical: dict) -> str:
    """Project the change set inline onto the end-version full text.

    Mirrors the canonical full-text view: end-version text with each change's
    span wrapped as a tracked change, removals collected in an appendix, and a
    meta line accounting for any change whose span couldn't be placed.
    """
    full_text = canonical.get("full_text") or {}
    v2_text = full_text.get("v2") or ""
    v1_text = full_text.get("v1") or ""

    placed_changes: list[dict] = []
    removed: list[dict] = []
    unplaced = 0
    for change in canonical.get("changes", []):
        span = change.get("full_text_span") or {}
        if span.get("v2"):
            placed_changes.append(change)
        elif change.get("change_type") == "removed" and span.get("v1"):
            removed.append(change)
        else:
            unplaced += 1
    placed_changes.sort(key=lambda c: c["full_text_span"]["v2"]["start"])

    parts: list[str] = []
    cursor = 0
    placed = 0
    for change in placed_changes:
        start = change["full_text_span"]["v2"]["start"]
        end = change["full_text_span"]["v2"]["end"]
        if start < cursor:
            continue  # overlapping span; first placement wins
        if start > cursor:
            parts.append(escape(v2_text[cursor:start]))
        parts.append(_render_v2_mark(change, v2_text[start:end]))
        cursor = end
        placed += 1
    if cursor < len(v2_text):
        parts.append(escape(v2_text[cursor:]))

    meta = _full_bill_meta_html(
        total=len(canonical.get("changes", [])),
        placed=placed,
        removed=len(removed),
        unplaced=unplaced,
    )
    appendix = _removed_appendix_html(removed, v1_text) if removed else ""
    return f'{meta}<div class="full-bill">{"".join(parts)}</div>{appendix}'


def _views_html(view: DiffView, canonical: dict | None) -> str:
    """Main content: classic cards, or the toggled changes/full-bill pair."""
    changes_inner = f"{_build_financial_summary(view)}\n<h2>Changes</h2>\n{_cards_section_html(view)}"
    if not _has_full_bill(canonical):
        return changes_inner
    return (
        f'<div class="view view-changes">{changes_inner}</div>'
        f'<div class="view view-full" hidden>{_full_bill_html(canonical)}</div>'
    )


# Ready-made questions a staffer can paste into an LLM alongside the diff.json.
# Tailored to the canonical schema (sections, amounts) and appropriations bills.
_LLM_PROMPTS = (
    "Summarize the most significant changes between these two versions of the bill in plain English.",
    "Which programs or accounts had their funding increased or decreased, and by how much? Put it in a table.",
    "List every section that was added or removed between the two versions.",
    "Beyond dollar amounts, are there any policy, legal, or eligibility changes I should be aware of?",
    "Explain what changed in a specific section (give me the section number) and why it might matter.",
)


def _export_button_html(canonical: dict | None) -> str:
    """The Export button that opens the download/prompts modal. PDF path only."""
    if not _has_full_bill(canonical):
        return ""
    return '<button id="export-open" class="export-btn" type="button">Export &amp; ask AI</button>'


def _export_modal_html(canonical: dict | None) -> str:
    """Modal: download diff.json / report.html, then reveal the AI prompts.

    Built entirely client-side from the embedded canonical + the page's own
    HTML — no server round-trip, consistent with the stateless report.
    """
    if not _has_full_bill(canonical):
        return ""
    prompts = "".join(
        f'<li class="prompt-item">'
        f'<button class="prompt-copy" type="button">Copy</button>'
        f'<span class="prompt-text">{escape(p)}</span></li>'
        for p in _LLM_PROMPTS
    )
    return (
        '<div id="export-modal" class="export-modal" hidden>'
        '<div class="export-modal__backdrop" data-close></div>'
        '<div class="export-modal__panel" role="dialog" aria-modal="true" aria-label="Export">'
        '<button class="export-modal__close" data-close aria-label="Close">&times;</button>'
        "<h2>Export this comparison</h2>"
        '<p class="export-modal__lead">Download the data, then ask an AI assistant to explain it.</p>'
        '<div class="export-downloads">'
        '<button id="dl-json" class="export-dl export-dl--primary" type="button">Download diff.json</button>'
        '<button id="dl-html" class="export-dl" type="button">Download report.html</button>'
        "</div>"
        '<div id="export-prompts" class="export-prompts" hidden>'
        "<h3>Ask ChatGPT, Claude, or Copilot</h3>"
        '<p class="export-prompts__lead">Upload the <code>diff.json</code> you just downloaded, '
        "then paste any of these:</p>"
        f'<ul class="prompt-list">{prompts}</ul>'
        "</div>"
        "</div></div>"
    )


def format_diff_html(view: DiffView, canonical: dict | None = None) -> str:
    """Assemble a complete standalone HTML report from a DiffView.

    When ``canonical`` is provided (PDF path), the canonical diff JSON is
    embedded so the report can offer the full-bill view and the export
    download client-side. When omitted (XML path), the report is unchanged.
    """
    bill_label = _bill_label(view)
    data_script = _embed_canonical(canonical) if canonical else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{bill_label} — Diff</title>
<style>
{_CSS}
</style>
</head>
<body>
<div class="layout">
{_build_sidebar(view)}
<div class="main">
<div class="report-header">
<h1>{bill_label} &mdash; Comparison</h1>
<div class="versions">{_versions_html(view)}</div>
<div class="summary-bar">{_summary_bar_html(view.summary)}</div>
{_view_toggle_html(canonical)}
{_export_button_html(canonical)}
</div>
{_views_html(view, canonical)}
</div>
</div>
<div class="nav-buttons">
<button id="btn-prev">&larr; Prev</button>
<button id="btn-next">Next &rarr;</button>
</div>
{_export_modal_html(canonical)}
{data_script}
<script>
{_JS}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# CSS for the unified report. Includes selectors that only fire for one
# pipeline (.citation, .change-card.unanchored, .section-number) — they are
# inert when their classes aren't applied, so both pipelines share one stylesheet.
# ---------------------------------------------------------------------------

_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Georgia, 'Times New Roman', serif; color: #222; line-height: 1.6; }
.layout { display: flex; min-height: 100vh; }

/* Sidebar */
.sidebar { width: 300px; position: fixed; top: 0; left: 0; height: 100vh;
  overflow-y: auto; background: #f7f7f7; border-right: 1px solid #ddd; padding: 12px; }
.sidebar input { width: 100%; padding: 6px 8px; margin-bottom: 8px;
  border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
.sidebar ul { list-style: none; }
.sidebar li { margin-bottom: 2px; }
.sidebar a { display: block; padding: 4px 6px; text-decoration: none;
  color: #333; font-size: 13px; border-radius: 3px; }
.sidebar a:hover { background: #e8e8e8; }
.sidebar .nav-item.unanchored a { color: #6c757d; font-style: italic; }

/* Main content */
.main { margin-left: 300px; padding: 24px 32px; max-width: 900px; flex: 1; }

/* Header */
.report-header h1 { font-size: 22px; margin-bottom: 4px; }
.report-header .versions { color: #666; font-size: 15px; margin-bottom: 16px; }
.summary-bar { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
.summary-item { font-size: 14px; }
.summary-item strong { margin-right: 4px; }

/* Badges */
.badge { display: inline-block; padding: 1px 6px; border-radius: 3px;
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
.badge-modified { background: #fff3cd; color: #856404; }
.badge-added { background: #d4edda; color: #155724; }
.badge-removed { background: #f8d7da; color: #721c24; }
.badge-moved { background: #cce5ff; color: #004085; }

/* Financial table */
.financial-table { width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 14px; }
.financial-table th { background: #f0f0f0; text-align: left; padding: 8px; border-bottom: 2px solid #ccc; }
.financial-table td { padding: 6px 8px; border-bottom: 1px solid #eee; }
.financial-table .amount { text-align: right; font-variant-numeric: tabular-nums; }
.financial-table a { color: #0056b3; text-decoration: none; }
.financial-table a:hover { text-decoration: underline; }
tr.increase .change-amount { color: #155724; }
tr.decrease .change-amount { color: #721c24; }

/* Change cards */
.change-card { border: 1px solid #ddd; border-radius: 6px; margin-bottom: 16px;
  padding: 16px; background: #fff; }
.change-card.added { border-left: 4px solid #28a745; }
.change-card.removed { border-left: 4px solid #dc3545; }
.change-card.modified { border-left: 4px solid #ffc107; }
.change-card.moved { border-left: 4px solid #007bff; }
.change-card.unanchored { border-left: 4px solid #6c757d; background: #fafafa; }
.change-card.unanchored .change-header h3 {
  color: #6c757d; font-style: italic; font-weight: 400; }
.change-card.unanchored .change-header h3::before { content: "⚠ "; }

.change-header { margin-bottom: 6px; }
.change-header h3 { font-size: 16px; display: inline; margin-left: 8px; font-weight: 600; }
.section-number { display: block; font-size: 13px; color: #666; margin-top: 2px; }

/* Citation block (page/line) */
.citation { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px;
  color: #555; margin: 4px 0 12px; }
.citation .v1, .citation .v2 { display: inline-block; padding: 1px 6px;
  background: #f0f0f0; border-radius: 3px; margin-right: 6px; }
.citation .v1::before { content: "v1: "; color: #888; }
.citation .v2::before { content: "v2: "; color: #888; }

/* Bodies */
.change-body { font-size: 14px; line-height: 1.7; white-space: pre-wrap; }
.added-text { background: #e6ffe6; padding: 10px; border-radius: 4px; }
.removed-text { background: #ffe6e6; padding: 10px; border-radius: 4px;
  text-decoration: line-through; color: #666; }
.old-text { background: #ffe6e6; padding: 8px; border-radius: 4px; margin-bottom: 8px; }
.new-text { background: #e6ffe6; padding: 8px; border-radius: 4px; }
.move-info { font-size: 13px; color: #004085; margin-bottom: 8px;
  padding: 6px 10px; background: #e7f1ff; border-radius: 3px; }
.move-info code { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; }

/* Inline diff */
del { background: #fecdd3; text-decoration: line-through; color: #9a3412; padding: 0 1px; }
ins { background: #bbf7d0; text-decoration: none; color: #166534; padding: 0 1px; }

/* View toggle (Changes / Full bill) */
.view-toggle { display: inline-flex; margin-top: 12px; border: 1px solid #ccc;
  border-radius: 6px; overflow: hidden; }
.view-toggle__btn { padding: 6px 16px; border: 0; background: #fff; cursor: pointer;
  font: inherit; font-size: 13px; color: #333; }
.view-toggle__btn + .view-toggle__btn { border-left: 1px solid #ccc; }
.view-toggle__btn.is-active { background: #0056b3; color: #fff; }
.view[hidden] { display: none; }

/* Full-bill tracked-changes view */
.full-bill-meta { font-size: 13px; color: #666; margin-bottom: 12px; }
.full-bill { white-space: pre-wrap; font-size: 14px; line-height: 1.7;
  font-family: 'SF Mono', Menlo, Consolas, monospace; }
.full-bill .moved-mark { background: #cce5ff; color: #004085; padding: 0 1px; }
.removed-appendix { margin-top: 28px; border-top: 1px solid #ddd; padding-top: 16px; }
.removed-appendix__note { font-size: 13px; color: #666; margin-bottom: 12px; }
.removed-block { margin-bottom: 12px; }
.removed-block__head { font-size: 13px; color: #555; margin-bottom: 4px; font-weight: 600; }
.removed-block .diff-del { white-space: pre-wrap; }

/* Export button + modal */
.export-btn { margin-top: 12px; margin-left: 12px; padding: 6px 16px; border: 1px solid #0056b3;
  border-radius: 6px; background: #0056b3; color: #fff; cursor: pointer; font: inherit; font-size: 13px; }
.export-btn:hover { background: #00408a; }
.export-modal { position: fixed; inset: 0; z-index: 50; display: flex;
  align-items: center; justify-content: center; }
.export-modal[hidden] { display: none; }
.export-modal__backdrop { position: absolute; inset: 0; background: rgba(0,0,0,0.45); }
.export-modal__panel { position: relative; background: #fff; border-radius: 8px; padding: 24px 28px;
  max-width: 560px; width: 92%; max-height: 88vh; overflow-y: auto; box-shadow: 0 8px 30px rgba(0,0,0,0.25); }
.export-modal__close { position: absolute; top: 10px; right: 14px; border: 0; background: none;
  font-size: 24px; line-height: 1; cursor: pointer; color: #888; }
.export-modal__panel h2 { font-size: 18px; margin-bottom: 4px; }
.export-modal__lead { color: #666; font-size: 14px; margin-bottom: 16px; }
.export-downloads { display: flex; gap: 10px; flex-wrap: wrap; }
.export-dl { padding: 8px 16px; border: 1px solid #ccc; border-radius: 6px; background: #fff;
  cursor: pointer; font: inherit; font-size: 14px; }
.export-dl--primary { background: #0056b3; color: #fff; border-color: #0056b3; }
.export-dl:hover { filter: brightness(0.95); }
.export-prompts { margin-top: 20px; border-top: 1px solid #eee; padding-top: 16px; }
.export-prompts[hidden] { display: none; }
.export-prompts h3 { font-size: 15px; margin-bottom: 4px; }
.export-prompts__lead { font-size: 13px; color: #666; margin-bottom: 12px; }
.prompt-list { list-style: none; }
.prompt-item { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 8px; font-size: 13px; }
.prompt-copy { flex: none; padding: 3px 10px; border: 1px solid #ccc; border-radius: 4px;
  background: #f7f7f7; cursor: pointer; font: inherit; font-size: 12px; }
.prompt-copy:hover { background: #ececec; }
.prompt-text { line-height: 1.5; }

/* Financial callout (canonical: PDF's flex rows) */
.financial-callout { margin-top: 12px; padding: 10px 14px; background: #f0f7ff;
  border: 1px solid #b6d4fe; border-radius: 4px; font-size: 13px;
  font-variant-numeric: tabular-nums; }
.financial-callout .row { display: flex; gap: 10px; margin-bottom: 2px; }
.financial-callout .label { color: #555; min-width: 110px; }
.financial-callout .delta.decrease { color: #721c24; font-weight: 600; }
.financial-callout .delta.increase { color: #155724; font-weight: 600; }

/* Navigation buttons */
.nav-buttons { position: fixed; bottom: 20px; right: 20px; display: flex; gap: 8px; z-index: 10; }
.nav-buttons button { padding: 8px 14px; border: 1px solid #ccc; border-radius: 4px;
  background: #fff; cursor: pointer; font-size: 13px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.nav-buttons button:hover { background: #f0f0f0; }

/* Print */
@media print {
  .sidebar, .nav-buttons, #sidebar-filter { display: none; }
  .main { margin-left: 0; }
  .change-card { break-inside: avoid; }
}
"""


_JS = """\
document.addEventListener('DOMContentLoaded', function() {
  // View toggle (Changes / Full bill)
  var toggleBtns = document.querySelectorAll('.view-toggle__btn');
  function showView(name) {
    toggleBtns.forEach(function(b) {
      var on = b.dataset.view === name;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    document.querySelectorAll('.view').forEach(function(el) {
      el.hidden = !el.classList.contains('view-' + name);
    });
  }
  toggleBtns.forEach(function(b) {
    b.addEventListener('click', function() { showView(b.dataset.view); });
  });
  // Sidebar anchors (#change-N) live in the changes view; jump back to it first.
  document.querySelectorAll('.sidebar a').forEach(function(a) {
    a.addEventListener('click', function() { showView('changes'); });
  });

  // Export modal: download diff.json / report.html, then reveal AI prompts.
  var exportOpen = document.getElementById('export-open');
  var exportModal = document.getElementById('export-modal');
  if (exportOpen && exportModal) {
    var closeExport = function() { exportModal.hidden = true; };
    exportOpen.addEventListener('click', function() { exportModal.hidden = false; });
    exportModal.querySelectorAll('[data-close]').forEach(function(el) {
      el.addEventListener('click', closeExport);
    });
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && !exportModal.hidden) closeExport();
    });

    var revealPrompts = function() {
      var p = document.getElementById('export-prompts');
      if (p) p.hidden = false;
    };
    var downloadBlob = function(filename, text, type) {
      var url = URL.createObjectURL(new Blob([text], {type: type}));
      var a = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function() { URL.revokeObjectURL(url); }, 1000);
      revealPrompts();
    };
    var dlJson = document.getElementById('dl-json');
    if (dlJson) dlJson.addEventListener('click', function() {
      var raw = document.getElementById('diff-data').textContent;
      downloadBlob('diff.json', JSON.stringify(JSON.parse(raw), null, 2), 'application/json');
    });
    var dlHtml = document.getElementById('dl-html');
    if (dlHtml) dlHtml.addEventListener('click', function() {
      downloadBlob('report.html', '<!DOCTYPE html>\\n' + document.documentElement.outerHTML, 'text/html');
    });
  }
  // Prompt copy buttons
  document.querySelectorAll('.prompt-copy').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var text = btn.parentElement.querySelector('.prompt-text').textContent;
      navigator.clipboard.writeText(text).then(function() {
        var prev = btn.textContent;
        btn.textContent = 'Copied';
        setTimeout(function() { btn.textContent = prev; }, 1200);
      });
    });
  });

  // Sidebar filter
  var filter = document.getElementById('sidebar-filter');
  if (filter) {
    filter.addEventListener('input', function() {
      var q = this.value.toLowerCase();
      document.querySelectorAll('.sidebar li').forEach(function(li) {
        li.style.display = li.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  }

  // Prev/next navigation
  var cards = document.querySelectorAll('.change-card');
  var current = -1;
  function goTo(idx) {
    if (idx >= 0 && idx < cards.length) {
      current = idx;
      cards[idx].scrollIntoView({behavior: 'smooth', block: 'start'});
    }
  }
  var prev = document.getElementById('btn-prev');
  var next = document.getElementById('btn-next');
  if (prev) prev.addEventListener('click', function() { goTo(current - 1); });
  if (next) next.addEventListener('click', function() { goTo(current + 1); });

  // Financial table sort (groups rowspan rows together by data-group)
  document.querySelectorAll('.financial-table th').forEach(function(th, colIdx) {
    th.style.cursor = 'pointer';
    th.addEventListener('click', function() {
      var table = th.closest('table');
      var tbody = table.querySelector('tbody');
      var rows = Array.from(tbody.querySelectorAll('tr'));
      var groups = [];
      var groupMap = {};
      rows.forEach(function(row) {
        var g = row.dataset.group;
        if (!(g in groupMap)) {
          groupMap[g] = groups.length;
          groups.push([]);
        }
        groups[groupMap[g]].push(row);
      });
      var asc = th.dataset.sort !== 'asc';
      th.dataset.sort = asc ? 'asc' : 'desc';
      groups.sort(function(a, b) {
        var aVal = a[0].cells[colIdx] ? a[0].cells[colIdx].textContent.replace(/[^\\d.-]/g, '') : '';
        var bVal = b[0].cells[colIdx] ? b[0].cells[colIdx].textContent.replace(/[^\\d.-]/g, '') : '';
        var aNum = parseFloat(aVal), bNum = parseFloat(bVal);
        if (!isNaN(aNum) && !isNaN(bNum)) return asc ? aNum - bNum : bNum - aNum;
        return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      });
      groups.forEach(function(group) {
        group.forEach(function(row) { tbody.appendChild(row); });
      });
    });
  });
});
"""
