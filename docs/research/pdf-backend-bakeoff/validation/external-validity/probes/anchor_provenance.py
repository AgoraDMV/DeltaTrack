"""A30 -- absolute source identity for a heading occurrence. NOT a harness component.

Pure encodings of the A30 rulings, written executably so they can be tested before any
result-bearing component consumes them. Nothing here scores anything, opens the holdout,
or decides an outcome. `x16_occurrence_identity.py` is the test.

    A30.1  the occurrence key's fourth component is `start_ngid` -- an ABSOLUTE source
           identity, never an ordinal among emitted anchors
    A30.2  the provenance derivation, study-locally instrumented, with explicit refusals
    A30.3  the oracle's geometric occurrence position, resolved to the same identity

WHY AN ORDINAL COULD NOT SURVIVE. Production emits a `section` and an inline `subsection`
at the SAME (page, margin line) -- `pdf_anchors._anchors_from_page` calls this a deliberate
physical collision. An ordinal among the anchors an arm emitted renumbers the later
occurrence whenever the earlier one is missing:

    H: A, B  ->  B is ordinal 1
    X:    B  ->  B is ordinal 0        the same physical occurrence, two keys

`start_ngid` cannot do that. It names the first physical ink mark of the occurrence, and
A24.2 makes that identity one both arms give the same number -- a U+0020 carries no `ngid`,
so the arms may disagree about spacing freely without moving it.

NGID IS AN IDENTITY, NOT A READING-ORDER KEY. It is used only for equality. Measured on
DEVELOPMENT material, ngid order agrees with printed order on 33,592 of 33,602 emitted
lines; the residue is single adjacent transpositions in PDFium's text-page order. Ordering
by ngid would inherit that residue for no benefit, so nothing here sorts by it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from deltatrack.parsers import pdf_anchors as PA

# --------------------------------------------------------------------- refusal classes
#
# Every failure in the chain is an explicit, tested state that yields UNMATCHED. Nothing
# guesses, and no fallback consults text, kind, or emission order.

PAGE_HAS_NO_PRINT_LINE_PROVENANCE = "PAGE_HAS_NO_PRINT_LINE_PROVENANCE"
PRINT_LINE_INDEX_UNRESOLVED = "PRINT_LINE_INDEX_UNRESOLVED"
MERGE_RECONSTRUCTION_MISMATCH = "MERGE_RECONSTRUCTION_MISMATCH"
OFFSET_PAST_END_OF_LINE = "OFFSET_PAST_END_OF_LINE"
CELLS_NOT_ALIGNED_WITH_PRINT_TEXT = "CELLS_NOT_ALIGNED_WITH_PRINT_TEXT"
NO_NEUTRAL_INK_AT_OR_AFTER_START = "NO_NEUTRAL_INK_AT_OR_AFTER_START"
START_NGID_NOT_OWNED_BY_NEUTRAL_LINE = "START_NGID_NOT_OWNED_BY_NEUTRAL_LINE"
NO_NEUTRAL_INK_ON_LINE = "NO_NEUTRAL_INK_ON_LINE"
AMBIGUOUS_SOURCE_POSITION = "AMBIGUOUS_SOURCE_POSITION"

UNMATCHED = "UNMATCHED"


@dataclass(frozen=True)
class Occurrence:
    """A production anchor plus the provenance needed to name its first ink mark.

    `merged_index` and `start_offset` are coordinates in the arm's OWN emitted text, so
    they legitimately differ between H and X. They are inputs to the derivation, never the
    identity: only the resolved `start_ngid` is compared across arms.
    """

    anchor: PA.Anchor
    page_number: int
    merged_index: int
    start_offset: int


# ------------------------------------------------------- A30.2 instrumented extraction
#
# THE FIDELITY CONTRACT. Only the small per-page pass is transcribed, because only it needs
# an exact within-line match position. The size path is CALLED, not copied, and its
# occurrences are located positionally -- an account/grouping/agency/major anchor is emitted
# from `line.text.strip()`, so its first ink character is the line's first non-space.
# Copying less logic is what keeps the mirror from drifting; `strip_to_production` plus the
# equality assertion in x16 is what proves it has not.


def _first_non_space(text: str) -> int:
    return len(text) - len(text.lstrip())


def _locate_merged_line(page, line_number: int):
    """The unique index in `page.lines` carrying this margin number, or a refusal."""
    hits = [i for i, ln in enumerate(page.lines) if ln.line_number == line_number]
    if len(hits) != 1:
        return None, PRINT_LINE_INDEX_UNRESOLVED
    return hits[0], None


def _instrumented_from_page(page) -> list[Occurrence]:
    """Mirror of `pdf_anchors._anchors_from_page`, carrying each anchor's start offset.

    Transcribed branch for branch. Any drift is caught by `strip_to_production`.
    """
    import re

    out: list[Occurrence] = []
    lines = page.lines
    for idx, line in enumerate(lines):
        if line.line_number is None:
            continue
        title_match = PA._TITLE_PATTERN.match(line.text)
        if title_match:
            anchor = PA.Anchor(page.page_number, line.line_number, "title", f"TITLE {title_match.group(1)}")
            out.append(Occurrence(anchor, page.page_number, idx, title_match.start()))
            continue
        next_texts = [ln.text for ln in lines[idx + 1 :]]
        section_match = PA._SECTION_PATTERN.match(line.text)
        if section_match:
            canonical = re.sub(r"\s+", " ", section_match.group(1))
            anchor = PA.Anchor(page.page_number, line.line_number, "section", canonical)
            out.append(Occurrence(anchor, page.page_number, idx, section_match.start()))
            remainder = re.match(r"^\.?\s*(\(.*)$", line.text[section_match.end() :])
            if remainder is not None:
                sub = PA._match_runin_subsection(remainder.group(1), next_texts)
                if sub is not None:
                    # the '(' that opens the run-in subsection -- the collision's second member
                    start = section_match.end() + remainder.start(1)
                    sub_anchor = PA.Anchor(page.page_number, line.line_number, "subsection", sub)
                    out.append(Occurrence(sub_anchor, page.page_number, idx, start))
            continue
        sub = PA._match_runin_subsection(line.text, next_texts)
        if sub is not None:
            anchor = PA.Anchor(page.page_number, line.line_number, "subsection", sub)
            out.append(Occurrence(anchor, page.page_number, idx, _first_non_space(line.text)))
    return out


def instrumented_extract_anchors(pages) -> tuple[list[Occurrence], list[str]]:
    """`pdf_anchors.extract_anchors` with occurrence-start provenance attached.

    Returns (occurrences, location_refusals). The occurrence list is in production order.
    """
    rows: list[Occurrence] = []
    refusals: list[str] = []
    by_page = {p.page_number: p for p in pages}

    for page in pages:
        rows.extend(_instrumented_from_page(page))

    bands = PA.derive_size_bands(pages)
    if bands is not None and PA._coverage(pages) >= PA._COVERAGE_MIN:
        size_path = list(PA._account_anchors_by_size(pages, bands)) + list(PA._major_anchors_by_size(pages, bands))
        for anchor in size_path:
            page = by_page.get(anchor.page_number)
            if page is None:
                refusals.append(PRINT_LINE_INDEX_UNRESOLVED)
                continue
            idx, reason = _locate_merged_line(page, anchor.line_number)
            if reason:
                refusals.append(reason)
                continue
            rows.append(Occurrence(anchor, anchor.page_number, idx, _first_non_space(page.lines[idx].text)))

    # the SAME stable sort production applies, over the same append order
    rows.sort(key=lambda r: (r.anchor.page_number, r.anchor.line_number))

    # division is a display field production assigns last; mirror it so the stripped
    # output is comparable field for field, division included
    flat = PA._flatten(pages)
    divisioned = PA._assign_divisions([r.anchor for r in rows], flat)
    rows = [replace(r, anchor=a) for r, a in zip(rows, divisioned)]
    return rows, refusals


def strip_to_production(occurrences: list[Occurrence]) -> list[PA.Anchor]:
    """Remove the instrumentation. This must equal `extract_anchors` element for element."""
    return [o.anchor for o in occurrences]


# ---------------------------------------------------------- A30.2 provenance resolution


def _merged_offset_map(print_lines, span):
    """merged offset -> (print-line index, offset in that print line), plus the rebuilt text.

    Rebuilt rather than computed, so the soft-hyphen merge is reproduced exactly and a
    mismatch is loud instead of silently shifting every offset on the line.
    """
    s, e = span
    text = print_lines[s].text
    mapping = [(s, i) for i in range(len(text))]
    for j in range(s + 1, e):
        text = text[:-1]  # the merge drops the trailing soft hyphen
        mapping = mapping[:-1]
        nxt = print_lines[j].text
        text = text + nxt
        mapping = mapping + [(j, i) for i in range(len(nxt))]
    return mapping, text


def resolve_start_ngid(page, emitted, merged_index: int, start_offset: int):
    """The ngid of the occurrence's first neutral-ink character, or (None, reason).

    Chain: merged line -> Page.merge_ranges -> originating print line + offset ->
    emitted[print_line].cells -> first cell at/after the start carrying an `ngid`.
    """
    if not page.print_lines or not page.merge_ranges:
        return None, PAGE_HAS_NO_PRINT_LINE_PROVENANCE
    if merged_index >= len(page.merge_ranges) or merged_index >= len(page.lines):
        return None, PRINT_LINE_INDEX_UNRESOLVED
    mapping, rebuilt = _merged_offset_map(page.print_lines, page.merge_ranges[merged_index])
    if rebuilt != page.lines[merged_index].text:
        return None, MERGE_RECONSTRUCTION_MISMATCH
    if start_offset >= len(mapping):
        return None, OFFSET_PAST_END_OF_LINE
    print_index, offset = mapping[start_offset]
    if print_index >= len(emitted):
        return None, PRINT_LINE_INDEX_UNRESOLVED
    cells = emitted[print_index].cells
    if len(cells) != len(page.print_lines[print_index].text):
        return None, CELLS_NOT_ALIGNED_WITH_PRINT_TEXT
    for k in range(offset, len(cells)):
        if cells[k].ngid is not None:
            return cells[k].ngid, None
    return None, NO_NEUTRAL_INK_AT_OR_AFTER_START


def occurrence_key(document_sha256: str, page_number: int, start_neutral_line_key, start_ngid: int):
    """A30.1 -- the occurrence identity. The fourth component is absolute, not an ordinal."""
    return (document_sha256, page_number, tuple(start_neutral_line_key), start_ngid)


def key_for(document_sha256: str, occurrence: Occurrence, page, emitted, owner):
    """Full derivation for one occurrence: (key, None) or (None, refusal)."""
    ngid, reason = resolve_start_ngid(page, emitted, occurrence.merged_index, occurrence.start_offset)
    if reason:
        return None, reason
    line_key = owner.get(ngid)
    if line_key is None:
        return None, START_NGID_NOT_OWNED_BY_NEUTRAL_LINE
    return occurrence_key(document_sha256, occurrence.page_number, line_key, ngid), None


# ------------------------------------------------ A30.3 the oracle's geometric position


def image_x_to_pdf_x(start_x_px: int, bbox_x0: float, bbox_x1: float, image_width_px: int):
    """Adjudicated pixel column -> page PDF x, using only committed render facts.

    No architecture output participates: the region bbox is committed by `build_oracle`
    before adjudication, and the image width is a property of the frozen DPI and that bbox.
    """
    if image_width_px <= 0:
        return None, AMBIGUOUS_SOURCE_POSITION
    return bbox_x0 + (float(start_x_px) / float(image_width_px)) * (bbox_x1 - bbox_x0), None


def expected_image_width(bbox_x0: float, bbox_x1: float, dpi: int) -> int:
    """The width the renderer must produce for a bbox at the frozen DPI (72 pt per inch)."""
    return int(round((bbox_x1 - bbox_x0) / 72.0 * dpi))


def resolve_oracle_start_ngid(candidates, target_pdf_x: float):
    """The neutral ink glyph nearest the adjudicated start, or (None, reason).

    `candidates` is [(ngid, x0), ...] for the neutral ink of the ONE physical line the
    adjudicator reported. Nearest by absolute distance, with NO tolerance: a tolerance would
    silently accept a wrong glyph, and there is no principled width to choose. An exact tie
    refuses rather than breaking it by ngid, kind, order or text -- each of those is a
    rejected shortcut, and a tie means the stimulus genuinely does not determine the answer.

    The skeleton supplies IDENTITY only. It never supplies heading truth: what the heading
    says, what role it plays and who its parent is remain independently adjudicated.
    """
    if not candidates:
        return None, NO_NEUTRAL_INK_ON_LINE
    scored = [(abs(x0 - target_pdf_x), ngid) for ngid, x0 in candidates]
    best = min(d for d, _ in scored)
    winners = [ngid for d, ngid in scored if d == best]
    if len(winners) != 1:
        return None, AMBIGUOUS_SOURCE_POSITION
    return winners[0], None


def oracle_occurrence_key(
    document_sha256: str,
    page_number: int,
    neutral_line,
    candidates,
    start_x_px: int,
    bbox_x0: float,
    bbox_x1: float,
    image_width_px: int,
):
    """Adjudicated (physical line, start_x_px) -> the same A30.1 key the arms produce."""
    target, reason = image_x_to_pdf_x(start_x_px, bbox_x0, bbox_x1, image_width_px)
    if reason:
        return None, reason
    ngid, reason = resolve_oracle_start_ngid(candidates, target)
    if reason:
        return None, reason
    if ngid not in neutral_line.gids:
        return None, START_NGID_NOT_OWNED_BY_NEUTRAL_LINE
    return occurrence_key(document_sha256, page_number, neutral_line.key, ngid), None
