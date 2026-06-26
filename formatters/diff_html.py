"""Unified HTML renderer for both XML and PDF bill diffs.

Consumes a DiffView produced by formatters.canonical.view_from_canonical. The
renderer does not branch on which pipeline produced the view — pipeline-specific
data (citations, degraded styling, section numbers) is rendered when present and
omitted when absent.

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
    data_financial = "1" if change.amount_pairs else "0"

    parts = [
        f'<div class="change-card {ct}{extra_card_class}" id="change-{index}"'
        f' data-type="{ct}" data-financial="{data_financial}">'
    ]
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
    fin = "1" if change.amount_pairs else "0"
    return (
        f'<li class="{nav_class}" data-type="{ct}" data-financial="{fin}">'
        f'<a href="#change-{index}">'
        f'<span class="badge badge-{ct}">{ct}</span> '
        f"{label}"
        f"</a></li>"
    )


def _build_change_groups(view: DiffView) -> str:
    """Group nav items under collapsible section headers (collapsed by default).

    Insertion-ordered by first appearance; an empty `group_label` collects into a
    trailing "Uncategorized" group. `_build_nav_item`'s <li> is unchanged — only
    the wrapping differs. Returns "<ul></ul>" when there are no changes.
    """
    groups: dict[str, list[str]] = {}
    for i, c in enumerate(view.changes):
        groups.setdefault(c.group_label or "Uncategorized", []).append(_build_nav_item(c, i))
    if not groups:
        return "<ul></ul>"
    # Insertion order, but "Uncategorized" always trails the real sections.
    labels = [label for label in groups if label != "Uncategorized"]
    if "Uncategorized" in groups:
        labels.append("Uncategorized")
    blocks = [
        f'<details class="nav-group"><summary>{escape(label)}'
        f' <span class="nav-group__count">({len(groups[label])})</span></summary>'
        f"<ul>{''.join(groups[label])}</ul></details>"
        for label in labels
    ]
    return "".join(blocks)


def _build_toc(sections: list[dict]) -> str:
    """Full-bill section navigation: each TITLE (labelled with its descriptor) is
    a collapsible group; its sections/accounts nest beneath and link to their row.
    Collapsed by default; clicking a title expands it and jumps to it."""
    if not sections:
        return '<p class="toc-empty">No sections detected.</p>'

    def child_li(i: int, s: dict) -> str:
        return f'<li class="toc-child"><a href="#sec-{i}">{escape(s["label"])}</a></li>'

    pre: list[str] = []  # any sections before the first title (uncommon)
    groups: list[tuple[str, list[str]]] = []  # (title summary, child <li>s)
    for i, s in enumerate(sections):
        if s.get("kind") == "title":
            desc = s.get("descriptor") or ""
            label = escape(s["label"]) + (f" &mdash; {escape(desc)}" if desc else "")
            groups.append((f'<summary><a href="#sec-{i}">{label}</a></summary>', []))
        elif groups:
            groups[-1][1].append(child_li(i, s))
        else:
            pre.append(child_li(i, s))

    blocks: list[str] = []
    if pre:
        blocks.append(f'<ul class="toc">{"".join(pre)}</ul>')
    blocks.extend(
        f'<details class="toc-group">{summary}<ul class="toc">{"".join(children)}</ul></details>'
        for summary, children in groups
    )
    return f'<div class="toc__title">Sections</div>{"".join(blocks)}'


def _build_sidebar(view: DiffView, sections: list[dict] | None = None) -> str:
    """Render the sidebar with both view variants inside one ``<nav>``.

    ``.sidebar-changes`` (filters + changes grouped by section) is shown in the
    Changes view; ``.sidebar-toc`` (full-bill section jump list) in the Full bill
    view — the JS view toggle swaps them. The TOC variant is rendered only when
    ``sections`` is provided (the PDF/full-bill path); ``None`` (XML/no full bill)
    renders just the changes variant and the swap no-ops.
    """
    changes_pane = (
        '<div class="sidebar-changes">\n'
        '<div class="filters">\n'
        '<div class="filters__title">Filter changes</div>\n'
        '<label class="filter-row"><input type="radio" name="change-filter" value="all" checked> All</label>\n'
        '<label class="filter-row"><input type="radio" name="change-filter" value="financial"> Financial</label>\n'
        '<label class="filter-row"><input type="radio" name="change-filter" value="structural"> Structural</label>\n'
        "</div>\n"
        f"{_build_change_groups(view)}\n"
        "</div>"
    )
    toc_pane = "" if sections is None else f'<div class="sidebar-toc" hidden>{_build_toc(sections)}</div>'
    return f'<nav class="sidebar">\n{changes_pane}\n{toc_pane}\n</nav>'


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
    line = f"{v1} &rarr; {v2}"
    congress = str(view.congress).strip()
    if congress:  # omit the suffix entirely when unknown, not "· th Congress"
        line += f" · {escape(congress)}th Congress"
    return line


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


def _full_text_is_guttered(canonical: dict) -> bool:
    """Whether full_text lines carry the PDF line-number gutter.

    ``pdf_full_text`` emits each line as a fixed 7-char gutter (``{num:>5}  ``)
    plus content; the XML pipeline serialises plain paragraph text with no gutter.
    Default to guttered (the PDF path that built this view); only an explicit
    ``xml`` v2 source switches the parser to gutterless paragraph flow.
    """
    src = ((canonical.get("versions") or {}).get("v2") or {}).get("source")
    return src != "xml"


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


def _move_note(change: dict) -> str:
    """Tooltip text for a moved span: a relocation note, with renumbering if known."""
    move = change.get("move") or {}
    if move.get("kind") == "renumbered":
        return (
            f"moved here (renumbered {escape(str(move.get('old_label', '')))}"
            f" → {escape(str(move.get('new_label', '')))})"
        )
    return "moved here"


def _wrap_mark(change: dict, slice_text: str, emitted_ids: set[str]) -> str:
    """Wrap one line's slice of a placed change with the right tracked-change mark.

    A change can span several source lines; this is called once per line it
    touches, marking the *new* (v2) text. The ``id`` anchor is emitted only on
    the change's first piece (tracked via ``emitted_ids``) so multi-line changes
    stay valid HTML. Modified spans are highlighted in place rather than shown
    with their old text inline — the precise old→new wording lives in the
    Changes cards, which keeps this reading view compact (PDF hunks can run to
    hundreds of lines, and the old text is often just a re-wrap of the new).
    """
    cid = escape(str(change.get("id", "")))
    ct = change.get("change_type")
    id_attr = ""
    if cid and cid not in emitted_ids:
        id_attr = f' id="attr-{cid}"'
        emitted_ids.add(cid)
    esc = escape(slice_text)
    if ct == "added":
        return f'<ins class="diff-add"{id_attr}>{esc}</ins>'
    if ct == "modified":
        return f'<span class="diff-mod"{id_attr} title="modified — see Changes for the old text">{esc}</span>'
    if ct == "moved":
        return f'<span class="moved-mark"{id_attr} title="{_move_note(change)}">{esc}</span>'
    return f'<del class="diff-del">{esc}</del>'


def _parse_full_bill_lines(text: str, *, guttered: bool = True) -> list[dict]:
    """Split full_text into per-source-line display rows.

    PDF path (``guttered=True``): each rendered line is ``{number:>5}  {content}``
    (five spaces of padding when the source line was unnumbered) and pages are
    separated by a single empty line. Returns rows carrying the page number, the
    source line number, and the char span of the *content* alone (the gutter
    prefix excluded) so change marks land on the text, not the line-number column.

    XML path (``guttered=False``): lines are plain paragraph text starting at
    column 0 with no line numbers or pages. Each non-blank line is one row whose
    span is the whole line; a blank line marks a paragraph break, recorded as
    ``para`` on the following row so the renderer can space blocks apart. Stripping
    a 7-char gutter here would chop the first word off every line.

    Blank-content lines are dropped either way to avoid stray vertical gaps.
    """
    rows: list[dict] = []
    page = 1
    pos = 0
    prev_blank = False
    for raw in text.split("\n"):
        start = pos
        pos += len(raw) + 1  # +1 for the newline join() consumed
        if raw == "":
            if guttered:
                page += 1  # the blank line between pages
            else:
                prev_blank = True  # paragraph break in gutterless text
            continue
        if not guttered:
            rows.append(
                {
                    "page": None,
                    "line": None,
                    "raw_start": start,
                    "start": start,
                    "end": start + len(raw),
                    "para": prev_blank,
                }
            )
            prev_blank = False
            continue
        content = raw[7:]
        if content == "":
            continue
        prefix = raw[:5].strip()
        rows.append(
            {
                "page": page,
                "line": int(prefix) if prefix.isdigit() else None,
                "raw_start": start,  # line start incl. gutter prefix (matches section offsets)
                "start": start + 7,
                "end": start + len(raw),
            }
        )
    return rows


def _render_fb_row_body(text: str, row: dict, marks: list[dict], emitted_ids: set[str]) -> str:
    """Render one row's content, wrapping any change spans that overlap it.

    ``marks`` is sorted by start and non-overlapping, so a single forward scan
    over the row's content range produces correctly ordered output. A change that
    spans multiple rows is clamped to this row's range here and re-wrapped on each
    row it covers.
    """
    cs, ce = row["start"], row["end"]
    out: list[str] = []
    p = cs
    for mark in marks:
        s, e = mark["start"], mark["end"]
        if e <= cs or s >= ce:
            continue
        a, b = max(s, cs), min(e, ce)
        if a > p:
            out.append(escape(text[p:a]))
        out.append(_wrap_mark(mark["change"], text[a:b], emitted_ids))
        p = b
    if p < ce:
        out.append(escape(text[p:ce]))
    return "".join(out)


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


def _full_bill_html(canonical: dict, sections: list[dict] | None = None) -> str:
    """Project the change set inline onto the end-version full text.

    Mirrors the canonical full-text view: end-version text with each change's
    span wrapped as a tracked change, removals collected in an appendix, and a
    meta line accounting for any change whose span couldn't be placed.

    ``sections`` (when given) carries each heading's char offset into the same
    text; the row at that offset is given an ``id="sec-{i}"`` so the sidebar TOC
    can jump to it.
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

    marks: list[dict] = []
    cursor = 0
    for change in placed_changes:
        start = change["full_text_span"]["v2"]["start"]
        end = change["full_text_span"]["v2"]["end"]
        if start < cursor:
            continue  # overlapping span; first placement wins
        marks.append({"start": start, "end": end, "change": change})
        cursor = end
    placed = len(marks)

    # Heading char offset -> TOC index, so the heading's row gets id="sec-{i}".
    sec_starts = {s["start"]: i for i, s in enumerate(sections or [])}

    guttered = _full_text_is_guttered(canonical)
    emitted_ids: set[str] = set()
    parts: list[str] = []
    seen_page = 0
    for row in _parse_full_bill_lines(v2_text, guttered=guttered):
        if guttered and row["page"] != seen_page:
            seen_page = row["page"]
            parts.append(f'<div class="fb-page">p. {seen_page}</div>')
        body = _render_fb_row_body(v2_text, row, marks, emitted_ids)
        sid = sec_starts.get(row["raw_start"])
        row_id = f' id="sec-{sid}"' if sid is not None else ""
        if guttered:
            gutter = str(row["line"]) if row["line"] is not None else ""
            parts.append(
                f'<div class="fb-row"{row_id}><span class="fb-gutter">{gutter}</span>'
                f'<span class="fb-text">{body}</span></div>'
            )
        else:
            row_cls = "fb-row fb-row--para" if row.get("para") else "fb-row"
            parts.append(f'<div class="{row_cls}"{row_id}><span class="fb-text">{body}</span></div>')

    meta = _full_bill_meta_html(
        total=len(canonical.get("changes", [])),
        placed=placed,
        removed=len(removed),
        unplaced=unplaced,
    )
    appendix = _removed_appendix_html(removed, v1_text) if removed else ""
    fb_cls = "full-bill" if guttered else "full-bill full-bill--no-gutter"
    return f'{meta}<div class="{fb_cls}">{"".join(parts)}</div>{appendix}'


def _views_html(
    view: DiffView,
    canonical: dict | None,
    display_canonical: dict | None = None,
    sections: list[dict] | None = None,
) -> str:
    """Main content: classic cards, or the toggled changes/full-bill pair.

    The full-bill view renders from ``display_canonical`` when given (the
    print-faithful text + spans) and falls back to ``canonical`` otherwise.
    """
    changes_inner = (
        f"{_build_financial_summary(view)}\n<h2>Changes</h2>\n{_cards_section_html(view)}"
        '\n<p class="filter-empty" id="filter-empty" hidden>No changes match this filter.</p>'
    )
    if not _has_full_bill(canonical):
        return changes_inner
    full_bill = _full_bill_html(display_canonical or canonical, sections)
    return f'<div class="view view-changes">{changes_inner}</div><div class="view view-full" hidden>{full_bill}</div>'


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
    return '<button id="export-open" class="export-btn" type="button">Export and Share</button>'


def _nav_controls_html(canonical: dict | None) -> str:
    """Prev / counter / Next change navigation. PDF path only (same gate as the
    view toggle and export). JS wires the buttons, the counter, and the active
    target set per view; see the navigation block in `_JS`."""
    if not _has_full_bill(canonical):
        return ""
    return (
        '<div class="nav-controls" role="group" aria-label="Navigate changes">'
        '<button id="btn-prev" type="button" aria-label="Previous change" disabled>&larr;</button>'
        '<span id="nav-counter" class="nav-counter" aria-live="polite">0 / 0</span>'
        '<button id="btn-next" type="button" aria-label="Next change">&rarr;</button>'
        "</div>"
    )


def _find_bar_html(canonical: dict | None) -> str:
    """In-page find: highlights matches in the active view and steps through them
    (Ctrl+F style). PDF path only. JS wires the input, counter, and stepping; see
    the find block in `_JS`."""
    if not _has_full_bill(canonical):
        return ""
    return (
        '<div class="find-bar" role="search">'
        '<input id="find-input" type="search" placeholder="Find in view…" aria-label="Find in view">'
        '<span id="find-counter" class="find-counter" aria-live="polite">0 / 0</span>'
        '<button id="find-prev" type="button" aria-label="Previous match" disabled>&uarr;</button>'
        '<button id="find-next" type="button" aria-label="Next match" disabled>&darr;</button>'
        "</div>"
    )


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
        '<button id="dl-json" class="export-dl" type="button">Download diff.json</button>'
        '<button id="dl-html" class="export-dl" type="button">Download report.html</button>'
        "</div>"
        '<div id="export-prompts" class="export-prompts">'
        "<h3>Ask AI</h3>"
        '<p class="export-prompts__lead">Download the <code>diff.json</code> above, upload it to '
        "your AI assistant, then paste any of these:</p>"
        f'<ul class="prompt-list">{prompts}</ul>'
        "</div>"
        "</div></div>"
    )


def format_diff_html(
    view: DiffView,
    canonical: dict | None = None,
    title: str | None = None,
    *,
    display_canonical: dict | None = None,
    sections: list[dict] | None = None,
) -> str:
    """Assemble a complete standalone HTML report from a DiffView.

    When ``canonical`` is provided (PDF path), the canonical diff JSON is
    embedded so the report can offer the full-bill view and the export
    download client-side. When omitted (XML path), the report is unchanged.

    ``display_canonical``, when given, supplies the print-faithful text + spans
    the on-screen full-bill view renders from (the PDF path passes one built
    from the original printed lines); the embedded/exported ``canonical`` keeps
    the merged whole-word text regardless.

    ``title``, when given, sets the report heading (the PDF path passes a bill
    title derived from the document); otherwise it falls back to the bill
    label, or a generic heading when no label is available.
    """
    bill_label = _bill_label(view)
    if title and title.strip():
        heading = escape(title.strip())
        doc_title = f"{escape(title.strip())} — Diff"
    elif bill_label.strip():
        heading = f"{bill_label} &mdash; Comparison"
        doc_title = f"{bill_label} — Diff"
    else:
        heading = "Bill Comparison"
        doc_title = "Bill Comparison — Diff"
    data_script = _embed_canonical(canonical) if canonical else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{doc_title}</title>
<style>
{_CSS}
</style>
</head>
<body>
<button id="sidebar-toggle" class="sidebar-toggle" aria-label="Toggle sidebar" title="Toggle sidebar">&#9776;</button>
<div class="layout">
{_build_sidebar(view, sections if _has_full_bill(canonical) else None)}
<div class="main">
<div class="report-header">
<h1>{heading}</h1>
<div class="versions">{_versions_html(view)}</div>
<div class="summary-bar">{_summary_bar_html(view.summary)}</div>
</div>
<div class="action-bar">
<div class="action-bar__left">
{_view_toggle_html(canonical)}
{_find_bar_html(canonical)}
</div>
<div class="action-bar__group">
{_nav_controls_html(canonical)}
{_export_button_html(canonical)}
</div>
</div>
{_views_html(view, canonical, display_canonical, sections)}
</div>
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

# Canonical brand tokens — mirrored verbatim from BillTrax's src/app/globals.css :root,
# so the block is drop-in and CI can guard drift (BillTrax owns the brand; DeltaTrack
# consumes — see DeltaTrack#37). Names and values match BillTrax exactly, with two
# documented exceptions:
#   - The DeltaTrack-local group (font stacks, shadow) below: fonts use system fallbacks
#     because reports are zero-egress and must not fetch webfonts; BillTrax keeps shadows
#     in its tailwind config rather than :root.
#   - --diff-modified/--diff-moved are new diff-state tokens not yet in BillTrax; the
#     matching addition on the BillTrax side is tracked in DeltaTrack#37.
_DESIGN_TOKENS_CSS = """\
:root {
  --background: #f9f7f5; --foreground: #1c1c3a;
  --card: #ffffff; --card-foreground: #1c1c3a;
  --popover: #ffffff; --popover-foreground: #1c1c3a;
  --primary: #2c2c5c; --primary-foreground: #f9f7f5;
  --secondary: #eef0f8; --secondary-foreground: #2c2c5c;
  --muted: #f2f0ed; --muted-foreground: #686881;
  --accent: #ede8df; --accent-foreground: #2c2c5c;
  --gold: #c9944e; --gold-foreground: #1c1c3a;
  --destructive: #c04040; --destructive-foreground: #f9f7f5;
  --success: #3d9b6d; --success-foreground: #f9f7f5;
  --diff-add: #d3f0e2; --diff-add-foreground: #1a6647;
  --diff-remove: #f5ddd8; --diff-remove-foreground: #8a2828;
  --diff-modified: #f1e6d2; --diff-modified-foreground: #8a6320;
  --diff-moved: #eef0f8; --diff-moved-foreground: #2c2c5c;
  --border: #e3ddd7; --input: #e3ddd7; --ring: #2c2c5c; --chart-5: #3b6fa0;
  --radius: 0.625rem;
  /* DeltaTrack-local (not synced from BillTrax): system font stacks + soft shadow */
  --font-sans: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  --font-serif: ui-serif, Georgia, 'Times New Roman', serif;
  --font-mono: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
  --shadow-soft: 0 1px 2px 0 rgba(28,28,58,0.04), 0 1px 3px 0 rgba(28,28,58,0.06);
}
"""

_CSS = (
    _DESIGN_TOKENS_CSS
    + """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: var(--font-sans); color: var(--foreground); background: var(--background); line-height: 1.6;
  -webkit-font-smoothing: antialiased; }
h1, h2, h3, h4 { font-family: var(--font-serif); letter-spacing: -0.02em; }
.layout { display: flex; min-height: 100vh; }

/* Sidebar */
.sidebar { width: 280px; position: fixed; top: 0; left: 0; height: 100vh;
  overflow-y: auto; background: var(--card); border-right: 1px solid var(--border); padding: 16px; }
.sidebar input { width: 100%; padding: 7px 10px; margin-bottom: 10px;
  border: 1px solid var(--border); border-radius: var(--radius); font-size: 14px; font-family: var(--font-sans); }
.sidebar ul { list-style: none; }
.sidebar li { margin-bottom: 2px; }
.sidebar a { display: block; padding: 5px 8px; text-decoration: none;
  color: var(--foreground); font-size: 13px; border-radius: var(--radius); }
.sidebar a:hover { background: var(--secondary); }
.sidebar .nav-item.unanchored a { color: var(--muted-foreground); font-style: italic; }

/* Collapsible section groups in the changes sidebar */
.nav-group { margin-bottom: 4px; }
.nav-group > summary { cursor: pointer; padding: 6px 8px; border-radius: var(--radius);
  font-size: 13px; font-weight: 600; color: var(--foreground); list-style: none;
  display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.nav-group > summary::-webkit-details-marker { display: none; }
.nav-group > summary::before { content: "\\25b8"; color: var(--muted-foreground); font-size: 10px; margin-right: 2px; }
.nav-group[open] > summary::before { content: "\\25be"; }
.nav-group > summary:hover { background: var(--secondary); }
.nav-group__count { color: var(--muted-foreground); font-weight: 400; font-variant-numeric: tabular-nums; }
.nav-group ul { margin: 2px 0 6px 10px; }

/* Filters */
.filters { margin-bottom: 16px; }
.filters__title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--muted-foreground); margin-bottom: 8px; font-weight: 600; }
.filter-row { display: flex; align-items: center; gap: 8px; padding: 4px 6px;
  font-size: 13px; cursor: pointer; border-radius: var(--radius); }
.filter-row:hover { background: var(--secondary); }
.filter-row input { width: auto; margin: 0; }
.filter-empty { color: var(--muted-foreground); padding: 16px 2px; font-size: 14px; }
.filter-empty[hidden] { display: none; }

/* Main content */
.main { margin-left: 280px; padding: 28px 36px; max-width: 940px; flex: 1; }

/* Header */
.report-header h1 { font-size: 24px; margin-bottom: 4px; }
.report-header .versions { color: var(--muted-foreground); font-size: 15px; margin-bottom: 16px; }
.summary-bar { display: flex; gap: 10px; margin-bottom: 24px; flex-wrap: wrap; }
.summary-item { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px;
  border-radius: 999px; font-size: 13px; background: var(--secondary); }
.summary-item strong { font-size: 14px; }

/* Badges */
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px;
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
.badge-modified { background: var(--diff-modified); color: var(--diff-modified-foreground); }
.badge-added { background: var(--diff-add); color: var(--diff-add-foreground); }
.badge-removed { background: var(--diff-remove); color: var(--diff-remove-foreground); }
.badge-moved { background: var(--diff-moved); color: var(--diff-moved-foreground); }

/* Financial table */
.financial-table { width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 14px; }
.financial-table th { background: var(--muted); text-align: left; padding: 9px;
  border-bottom: 1px solid var(--border); }
.financial-table td { padding: 7px 9px; border-bottom: 1px solid var(--border); }
.financial-table .amount { text-align: right; font-variant-numeric: tabular-nums; font-family: var(--font-mono); }
.financial-table a { color: var(--primary); text-decoration: none; }
.financial-table a:hover { text-decoration: underline; }
tr.increase .change-amount { color: var(--success); }
tr.decrease .change-amount { color: var(--destructive); }

/* Change cards */
.change-card { border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 14px;
  padding: 16px 18px; background: var(--card); box-shadow: var(--shadow-soft); }
.change-card.added { border-left: 3px solid var(--success); }
.change-card.removed { border-left: 3px solid var(--destructive); }
.change-card.modified { border-left: 3px solid var(--gold); }
.change-card.moved { border-left: 3px solid var(--primary); }
.change-card.unanchored { border-left: 3px solid var(--muted-foreground); background: var(--muted); }
.change-card.unanchored .change-header h3 {
  color: var(--muted-foreground); font-style: italic; font-weight: 400; }
.change-card.unanchored .change-header h3::before { content: "⚠ "; }

.change-header { margin-bottom: 6px; }
.change-header h3 { font-size: 16px; display: inline; margin-left: 8px; font-weight: 600; }
.section-number { display: block; font-size: 13px; color: var(--muted-foreground); margin-top: 2px; }

/* Citation block (page/line) */
.citation { font-family: var(--font-mono); font-size: 12px;
  color: var(--muted-foreground); margin: 4px 0 12px; }
.citation .v1, .citation .v2 { display: inline-block; padding: 1px 6px;
  background: var(--muted); border-radius: 6px; margin-right: 6px; }
.citation .v1::before { content: "v1: "; color: var(--muted-foreground); }
.citation .v2::before { content: "v2: "; color: var(--muted-foreground); }

/* Bodies */
.change-body { font-size: 14px; line-height: 1.7; white-space: pre-wrap; }
.added-text { background: var(--diff-add); color: var(--diff-add-foreground);
  padding: 10px; border-radius: var(--radius); }
.removed-text { background: var(--diff-remove); color: var(--diff-remove-foreground);
  padding: 10px; border-radius: var(--radius); text-decoration: line-through; }
.old-text { background: var(--diff-remove); padding: 8px; border-radius: var(--radius); margin-bottom: 8px; }
.new-text { background: var(--diff-add); padding: 8px; border-radius: var(--radius); }
.move-info { font-size: 13px; color: var(--diff-moved-foreground); margin-bottom: 8px;
  padding: 6px 10px; background: var(--diff-moved); border-radius: var(--radius); }
.move-info code { font-family: var(--font-mono); font-size: 12px; }

/* Inline diff */
del { background: var(--diff-remove); text-decoration: line-through; color: var(--diff-remove-foreground);
  padding: 0 1px; border-radius: 3px; }
ins { background: var(--diff-add); text-decoration: none; color: var(--diff-add-foreground);
  padding: 0 1px; border-radius: 3px; }

/* View toggle (Changes / Full bill) — neutral grey, distinct from action buttons */
/* Sticky action bar: view toggle (left), nav + export (right) */
.action-bar { position: sticky; top: 0; z-index: 30; display: flex; align-items: center;
  justify-content: space-between; gap: 12px; flex-wrap: wrap; background: var(--background);
  border-bottom: 1px solid var(--border); padding: 10px 0; margin-bottom: 16px; }
.action-bar__left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.action-bar__group { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.find-bar { display: inline-flex; align-items: center; gap: 4px; }
.find-bar input { padding: 5px 10px; border: 1px solid var(--border); border-radius: var(--radius);
  font: inherit; font-family: var(--font-sans); font-size: 13px; width: 180px; background: var(--card); }
.find-bar button { padding: 5px 9px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--card); cursor: pointer; font-family: var(--font-sans); font-size: 13px; }
.find-bar button:hover { background: var(--secondary); }
.find-bar button[disabled] { opacity: 0.4; cursor: default; }
.find-counter { font-variant-numeric: tabular-nums; font-size: 12px; color: var(--muted-foreground);
  min-width: 3.5em; text-align: center; }
mark.find-hit { background: var(--accent); color: inherit; border-radius: 2px; scroll-margin-top: 64px; }
mark.find-hit--current { background: var(--gold); color: #fff; }
.nav-controls { display: inline-flex; align-items: center; gap: 4px; }
.nav-controls button { padding: 6px 12px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--card); cursor: pointer; font-family: var(--font-sans); font-size: 14px;
  box-shadow: var(--shadow-soft); }
.nav-controls button:hover { background: var(--secondary); }
.nav-controls button[disabled] { opacity: 0.4; cursor: default; box-shadow: none; }
.nav-counter { font-variant-numeric: tabular-nums; font-size: 13px; color: var(--muted-foreground);
  min-width: 3.5em; text-align: center; }

.view-toggle { display: inline-flex; border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden; }
.view-toggle__btn { padding: 6px 16px; border: 0; background: var(--card); cursor: pointer;
  font: inherit; font-family: var(--font-sans); font-size: 13px; color: var(--foreground); }
.view-toggle__btn + .view-toggle__btn { border-left: 1px solid var(--border); }
.view-toggle__btn.is-active { background: var(--muted-foreground); color: #fff; }
.view[hidden] { display: none; }

/* Full-bill tracked-changes view */
.full-bill-meta { font-size: 13px; color: var(--muted-foreground); margin-bottom: 12px; }
.full-bill { font-size: 14px; line-height: 1.7; }
.fb-row { display: grid; grid-template-columns: 3em 1fr; gap: 14px; align-items: baseline; }
.fb-gutter { font-family: var(--font-mono); font-size: 11px; color: var(--muted-foreground); text-align: right;
  user-select: none; -webkit-user-select: none; }
.fb-text { white-space: pre-wrap; overflow-wrap: anywhere; }
/* XML full_text has no line-number gutter: plain paragraph flow. */
.full-bill--no-gutter .fb-row { display: block; }
.full-bill--no-gutter .fb-row--para { margin-top: 0.9em; }
.full-bill .diff-mod { background: var(--diff-modified); border-bottom: 2px solid var(--gold); }
.fb-page { font-family: var(--font-sans); font-size: 12px; font-weight: 600; color: var(--muted-foreground);
  margin: 18px 0 6px; border-top: 1px dashed var(--border); padding-top: 6px; user-select: none; }
.full-bill > .fb-page:first-child { margin-top: 0; border-top: 0; padding-top: 0; }
.full-bill .moved-mark { background: var(--diff-moved); color: var(--diff-moved-foreground); padding: 0 1px; }
.removed-appendix { margin-top: 28px; border-top: 1px solid var(--border); padding-top: 16px; }
.removed-appendix__note { font-size: 13px; color: var(--muted-foreground); margin-bottom: 12px; }
.removed-block { margin-bottom: 12px; }
.removed-block__head { font-size: 13px; color: var(--muted-foreground); margin-bottom: 4px; font-weight: 600; }
.removed-block .diff-del { white-space: pre-wrap; }

/* Export button + modal */
.export-btn { padding: 6px 16px; border: 1px solid var(--primary);
  border-radius: var(--radius); background: var(--primary); color: var(--primary-foreground); cursor: pointer;
  font: inherit; font-family: var(--font-sans); font-size: 13px; }
.export-btn:hover { filter: brightness(1.25); }
.export-modal { position: fixed; inset: 0; z-index: 50; display: flex;
  align-items: center; justify-content: center; }
.export-modal[hidden] { display: none; }
.export-modal__backdrop { position: absolute; inset: 0; background: rgba(28,28,58,0.45); }
.export-modal__panel { position: relative; background: var(--card); border-radius: var(--radius); padding: 24px 28px;
  max-width: 560px; width: 92%; max-height: 88vh; overflow-y: auto; box-shadow: 0 8px 30px rgba(28,28,58,0.25); }
.export-modal__close { position: absolute; top: 10px; right: 14px; border: 0; background: none;
  font-size: 24px; line-height: 1; cursor: pointer; color: var(--muted-foreground); }
.export-modal__panel h2 { font-size: 18px; margin-bottom: 4px; }
.export-modal__lead { color: var(--muted-foreground); font-size: 14px; margin-bottom: 16px; }
.export-downloads { display: flex; gap: 10px; flex-wrap: wrap; }
.export-dl { padding: 8px 16px; border: 1px solid var(--primary); border-radius: var(--radius);
  background: var(--primary);
  color: var(--primary-foreground); cursor: pointer; font: inherit; font-family: var(--font-sans); font-size: 14px; }
.export-dl:hover { filter: brightness(1.25); }
.export-prompts { margin-top: 20px; border-top: 1px solid var(--border); padding-top: 16px; }
.export-prompts[hidden] { display: none; }
.export-prompts h3 { font-size: 15px; margin-bottom: 4px; }
.export-prompts__lead { font-size: 13px; color: var(--muted-foreground); margin-bottom: 12px; }
.prompt-list { list-style: none; }
.prompt-item { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 8px; font-size: 13px; }
.prompt-copy { flex: none; padding: 3px 10px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--secondary); cursor: pointer; font: inherit; font-family: var(--font-sans); font-size: 12px; }
.prompt-copy:hover { background: var(--accent); }
.prompt-text { line-height: 1.5; }

/* Financial callout (canonical: PDF's flex rows) */
.financial-callout { margin-top: 12px; padding: 10px 14px; background: var(--secondary);
  border: 1px solid var(--border); border-radius: var(--radius); font-size: 13px;
  font-variant-numeric: tabular-nums; }
.financial-callout .row { display: flex; gap: 10px; margin-bottom: 2px; }
.financial-callout .label { color: var(--muted-foreground); min-width: 110px; }
.financial-callout .delta.decrease { color: var(--destructive); font-weight: 600; }
.financial-callout .delta.increase { color: var(--success); font-weight: 600; }

/* Nav targets clear the sticky action bar when scrolled to via Prev/Next */
.change-card, .full-bill [id^="attr-"], .full-bill [id^="sec-"], .removed-block { scroll-margin-top: 64px; }

/* Full-bill section TOC (sidebar variant) */
.sidebar-changes[hidden], .sidebar-toc[hidden] { display: none; }
.toc__title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--muted-foreground); margin-bottom: 8px; font-weight: 600; }
.toc { list-style: none; }
.toc-group { margin-bottom: 2px; }
.toc-group > summary { cursor: pointer; padding: 6px 8px; border-radius: var(--radius);
  font-size: 13px; font-weight: 600; color: var(--foreground); list-style: none;
  display: flex; align-items: baseline; gap: 4px; }
.toc-group > summary::-webkit-details-marker { display: none; }
.toc-group > summary::before { content: "\\25b8"; color: var(--muted-foreground); font-size: 10px; flex: 0 0 auto; }
.toc-group[open] > summary::before { content: "\\25be"; }
.toc-group > summary:hover { background: var(--secondary); }
.toc-group > summary a { color: inherit; text-decoration: none; }
.toc-group ul { margin: 2px 0 6px 14px; }
.toc-child a { display: block; padding: 4px 8px; text-decoration: none; color: var(--muted-foreground);
  font-size: 13px; border-radius: var(--radius); }
.toc-child a:hover { background: var(--secondary); color: var(--foreground); }
.toc-empty { color: var(--muted-foreground); font-size: 13px; padding: 8px; }

/* Collapsible sidebar + responsive layout */
.sidebar { transition: transform 0.2s ease; z-index: 40; padding-top: 56px; }
.main { transition: margin-left 0.2s ease; }
.sidebar-toggle { position: fixed; top: 12px; left: 12px; z-index: 60; width: 38px; height: 38px;
  border: 1px solid var(--border); border-radius: var(--radius); background: var(--card);
  color: var(--foreground); cursor: pointer; font-size: 16px; box-shadow: var(--shadow-soft); }
.sidebar-toggle:hover { background: var(--secondary); }
body.nav-collapsed .sidebar { transform: translateX(-100%); }
body.nav-collapsed .main { margin-left: 0; padding-left: 64px; }
@media (max-width: 820px) {
  .main { margin-left: 0; padding: 64px 18px 24px; }
  body.nav-collapsed .main { padding-left: 18px; }
  .sidebar { box-shadow: 0 8px 24px -8px rgba(28,28,58,0.35); }
  .report-header h1 { font-size: 20px; }
  .summary-bar { gap: 8px; }
  /* Don't pin the top bar over the fixed hamburger; drop nav + find to a
     thumb-reach bottom bar (find row above the change-nav row) and pad the page
     so the last content clears both. */
  .action-bar { position: static; }
  body { padding-bottom: 108px; }
  .nav-controls { position: fixed; left: 0; right: 0; bottom: 0; z-index: 35;
    justify-content: center; gap: 24px; background: var(--card);
    border-top: 1px solid var(--border); box-shadow: 0 -2px 10px rgba(28,28,58,0.12);
    padding: 10px 16px calc(10px + env(safe-area-inset-bottom)); }
  .find-bar { position: fixed; left: 0; right: 0; bottom: 46px; z-index: 35;
    justify-content: center; background: var(--card); border-top: 1px solid var(--border);
    padding: 8px 16px; }
  .find-bar input { flex: 1; max-width: 320px; }
}

/* Print */
@media print {
  .sidebar, .action-bar, .sidebar-toggle { display: none; }
  .main { margin-left: 0; }
  .change-card { break-inside: avoid; }
}
"""
)


_JS = """\
document.addEventListener('DOMContentLoaded', function() {
  // View toggle (Changes / Full bill)
  var toggleBtns = document.querySelectorAll('.view-toggle__btn');
  var sidebarChanges = document.querySelector('.sidebar-changes');
  var sidebarToc = document.querySelector('.sidebar-toc');
  function showView(name) {
    toggleBtns.forEach(function(b) {
      var on = b.dataset.view === name;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    document.querySelectorAll('.view').forEach(function(el) {
      el.hidden = !el.classList.contains('view-' + name);
    });
    // Swap the sidebar variant (only when a TOC variant was rendered).
    if (sidebarToc) {
      sidebarToc.hidden = name !== 'full';
      if (sidebarChanges) sidebarChanges.hidden = name === 'full';
    }
  }
  toggleBtns.forEach(function(b) {
    b.addEventListener('click', function() { showView(b.dataset.view); });
  });
  // Change-list anchors (#change-N) live in the changes view; jump back to it
  // first. TOC links (.sidebar-toc a) just scroll within the full-bill view.
  document.querySelectorAll('.sidebar-changes a').forEach(function(a) {
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

    var downloadBlob = function(filename, text, type) {
      var url = URL.createObjectURL(new Blob([text], {type: type}));
      var a = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function() { URL.revokeObjectURL(url); }, 1000);
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

  // Change-type filter: All / Financial / Structural (radios only).
  function applyFilters() {
    var typeEl = document.querySelector('input[name="change-filter"]:checked');
    var mode = typeEl ? typeEl.value : 'all';
    var typeOk = function(el) {
      if (mode === 'financial') return el.dataset.financial === '1';
      if (mode === 'structural') return el.dataset.type !== 'modified';
      return true;
    };
    var visible = 0;
    document.querySelectorAll('.change-card').forEach(function(c) {
      var show = typeOk(c);
      c.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    // Mirror each nav item to its target card's visibility.
    document.querySelectorAll('.sidebar .nav-item').forEach(function(li) {
      var a = li.querySelector('a');
      var card = a ? document.getElementById(a.getAttribute('href').slice(1)) : null;
      li.style.display = (card && card.style.display !== 'none') ? '' : 'none';
    });
    // Update each section group's count and hide groups with no visible items.
    document.querySelectorAll('.nav-group').forEach(function(g) {
      var vis = [].slice.call(g.querySelectorAll('.nav-item')).filter(function(li) {
        return li.style.display !== 'none';
      }).length;
      g.style.display = vis === 0 ? 'none' : '';
      var cnt = g.querySelector('.nav-group__count');
      if (cnt) cnt.textContent = '(' + vis + ')';
    });
    var empty = document.getElementById('filter-empty');
    if (empty) empty.hidden = visible !== 0;
  }
  document.querySelectorAll('input[name="change-filter"]').forEach(function(r) {
    r.addEventListener('change', applyFilters);
  });

  // Collapsible sidebar (and off-canvas on small screens).
  var sidebarToggle = document.getElementById('sidebar-toggle');
  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', function() {
      document.body.classList.toggle('nav-collapsed');
    });
  }
  if (window.innerWidth < 820) document.body.classList.add('nav-collapsed');

  // Prev/next change navigation. View-aware: steps visible cards in the Changes
  // view and the inline highlights in the Full bill view; counter reflects the
  // active filter. Refreshed when the view or filter changes (see refreshNav).
  var prevBtn = document.getElementById('btn-prev');
  var nextBtn = document.getElementById('btn-next');
  var counter = document.getElementById('nav-counter');
  var current = -1;
  function navTargets() {
    var full = document.querySelector('.view-full');
    if (full && !full.hidden) {
      return [].slice.call(full.querySelectorAll('[id^="attr-"], .removed-block'));
    }
    // Changes view: only cards the active filter leaves visible.
    return [].slice.call(document.querySelectorAll('.view-changes .change-card'))
      .filter(function(c) { return c.offsetParent !== null; });
  }
  function refreshNav() {
    var n = navTargets().length;
    if (current >= n) current = n - 1;
    if (counter) counter.textContent = (current + 1) + ' / ' + n;
    if (prevBtn) prevBtn.disabled = current <= 0;
    if (nextBtn) nextBtn.disabled = current >= n - 1;
  }
  function goTo(idx) {
    var targets = navTargets();
    if (idx >= 0 && idx < targets.length) {
      current = idx;
      targets[idx].scrollIntoView({behavior: 'smooth', block: 'start'});
    }
    refreshNav();
  }
  if (prevBtn) prevBtn.addEventListener('click', function() { goTo(current - 1); });
  if (nextBtn) nextBtn.addEventListener('click', function() { goTo(current + 1); });
  // Arrow keys for change-nav, unless the user is typing in a field.
  document.addEventListener('keydown', function(e) {
    if (e.target.tagName === 'INPUT' || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'ArrowRight') { goTo(current + 1); }
    else if (e.key === 'ArrowLeft') { goTo(current - 1); }
  });
  // Recompute targets (and reset position) when the view or filter changes.
  function resetNav() { current = -1; refreshNav(); }
  toggleBtns.forEach(function(b) { b.addEventListener('click', resetNav); });
  document.querySelectorAll('input[name="change-filter"]').forEach(function(r) {
    r.addEventListener('change', resetNav);
  });
  refreshNav();

  // In-page find: highlight matches in the active view and step through them.
  var findInput = document.getElementById('find-input');
  var findCounter = document.getElementById('find-counter');
  var findPrev = document.getElementById('find-prev');
  var findNext = document.getElementById('find-next');
  var findHits = [];
  var findIdx = -1;
  function activeView() {
    var full = document.querySelector('.view-full');
    if (full && !full.hidden) return full;
    return document.querySelector('.view-changes') || document.body;
  }
  function clearFind() {
    var parents = [];
    document.querySelectorAll('mark.find-hit').forEach(function(m) {
      var p = m.parentNode;  // capture before replaceChild detaches m
      p.replaceChild(document.createTextNode(m.textContent), m);
      parents.push(p);
    });
    // Merge the text nodes left behind, else repeated searches fragment the
    // text and matches stop being found within a single node.
    parents.forEach(function(p) { p.normalize(); });
    findHits = [];
    findIdx = -1;
  }
  function updateFindCounter() {
    if (findCounter) findCounter.textContent = (findIdx + 1) + ' / ' + findHits.length;
    if (findPrev) findPrev.disabled = findHits.length === 0;
    if (findNext) findNext.disabled = findHits.length === 0;
  }
  function setCurrentHit(i) {
    if (!findHits.length) { updateFindCounter(); return; }
    if (findHits[findIdx]) findHits[findIdx].classList.remove('find-hit--current');
    findIdx = (i % findHits.length + findHits.length) % findHits.length;
    var cur = findHits[findIdx];
    cur.classList.add('find-hit--current');
    cur.scrollIntoView({behavior: 'smooth', block: 'center'});
    updateFindCounter();
  }
  function runFind() {
    clearFind();
    var q = (findInput ? findInput.value : '').trim();
    if (q.length < 2) { updateFindCounter(); return; }
    var root = activeView();
    var ql = q.toLowerCase();
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function(node) {
        if (!node.nodeValue || node.nodeValue.toLowerCase().indexOf(ql) === -1) return NodeFilter.FILTER_REJECT;
        var el = node.parentElement;  // skip filter-hidden subtrees
        if (!el || (el.offsetParent === null && el.tagName !== 'BODY')) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [];  // snapshot before mutating the tree
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function(node) {
      var text = node.nodeValue, lower = text.toLowerCase();
      // Rebuild the node as [text, <mark>, text, …] in one replaceChild — no
      // splitText juggling, no index invalidation.
      var frag = document.createDocumentFragment();
      var last = 0, at;
      while ((at = lower.indexOf(ql, last)) !== -1) {
        if (at > last) frag.appendChild(document.createTextNode(text.slice(last, at)));
        var mark = document.createElement('mark');
        mark.className = 'find-hit';
        mark.textContent = text.slice(at, at + ql.length);
        frag.appendChild(mark);
        last = at + ql.length;
      }
      if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
    findHits = [].slice.call(root.querySelectorAll('mark.find-hit'));
    findIdx = -1;
    updateFindCounter();
    if (findHits.length) setCurrentHit(0);
  }
  if (findInput) {
    var findTimer;
    findInput.addEventListener('input', function() {
      clearTimeout(findTimer);
      findTimer = setTimeout(runFind, 150);
    });
    findInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') { e.preventDefault(); setCurrentHit(findIdx + (e.shiftKey ? -1 : 1)); }
    });
  }
  if (findPrev) findPrev.addEventListener('click', function() { setCurrentHit(findIdx - 1); });
  if (findNext) findNext.addEventListener('click', function() { setCurrentHit(findIdx + 1); });
  // Re-scope find to whatever's now visible when the view or filter changes.
  toggleBtns.forEach(function(b) { b.addEventListener('click', function() { setTimeout(runFind, 0); }); });
  document.querySelectorAll('input[name="change-filter"]').forEach(function(r) {
    r.addEventListener('change', function() { setTimeout(runFind, 0); });
  });

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
