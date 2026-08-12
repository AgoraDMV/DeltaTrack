"""Neutral ink-line skeleton: the architecture-neutral identity A17.2-A17.4 need.

PROTOTYPE FOR A17 RESOLUTION. Not the confirmatory harness.

WHY IT EXISTS. The frozen protocol defines its adjudication unit as "6-10 printed lines"
(PRE-REGISTRATION.md 5.3) and its D-frame as regions "where the two architectures'
reconstructed printed-line text differs" (5.8). Printed lines are produced BY H and BY X,
and the D-frame exists precisely because the two can disagree about line segmentation. So
the comparison unit was defined in terms of the thing under test. This builds the unit
below both seams instead.

WHICH SOURCE FACTS ARE BELOW BOTH SEAMS, stated precisely rather than assumed.

The two architectures differ in exactly one place: who decides WORD SPACES, and whether the
engine's character stream ordering is consumed. They do NOT differ on glyph geometry --
both adapters read the same PDFium calls for it:

    FPDFText_GetCharBox    -> x0, y0, x1, y1     (H: contract_hybrid x0/x1/vbox;
                                                  X: contract_extended X0/Y0/X1/Y1)
    FPDFText_GetCharOrigin -> pen origin          (H: baseline; X: origin_x + baseline)
    FPDFText_GetFontSize   -> size

So INK GLYPH BOXES AND BASELINES ARE COMMON TO BOTH ARMS and are legitimate neutral facts.
This module reads only:

    baseline (origin y), x0, x1, y0, y1, page width/height

It reads NO codepoint, NO font name, NO word spacing, NO case, NO heading label, and no
reconstructed line ordinal from either architecture.

A CAVEAT THAT IS STATED, NOT WAIVED. These facts are still PDFium's. "Common to both arms"
is not the same as "engine-independent": if PDFium mis-boxed a glyph, both arms and the
skeleton would inherit it together. The protocol's own 10 % PyMuPDF cross-check
(5.8) is the control for that, and it is a control on the FRAME, not on either architecture.

GENERATED CHARACTERS ARE EXCLUDED. H's contract carries engine-invented spaces whose
geometry is None; X's contract excludes U+0020 entirely (X-2). A skeleton built from ink
only is therefore identical under both, which is the property that makes it neutral.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

# Tolerance is DERIVED from page geometry rather than fixed: half the page's median ink
# height, which is production's own parameterisation (`_BASELINE_TOL_FACTOR = 0.5 x median
# glyph size` in parsers/pdf_text.py). An absolute constant would be an arbitrary number
# that behaves differently on 8 pt and 14 pt type.
BASELINE_TOL_FACTOR = 0.5


@dataclass(frozen=True)
class NeutralLine:
    """One physical printed line, identified without reference to any architecture."""

    page: int
    ordinal: int  # 0-based, top-to-bottom, deterministic from geometry alone
    baseline: float
    x0: float
    x1: float
    y0: float
    y1: float
    n_glyphs: int
    median_height: float

    @property
    def key(self) -> tuple[int, int]:
        return (self.page, self.ordinal)


def cluster_page(glyphs: list[tuple[float, float, float, float, float]], page: int) -> list[NeutralLine]:
    """Cluster one page's INK glyphs into neutral lines.

    `glyphs` is (baseline, x0, y0, x1, y1) -- geometry only, no codepoints.

    THE RULE, frozen:
      1. tol = 0.5 * median(glyph height) over the page's ink glyphs.
      2. Sort glyphs by DESCENDING baseline (PDF y grows upward, so this is top-to-bottom).
      3. Walk the sorted glyphs, starting a new line when the glyph's baseline differs from
         the CURRENT LINE'S ANCHOR by more than tol. The anchor is the first glyph's
         baseline, not a running mean, so a long gentle drift cannot walk a single cluster
         down the page.
      4. Ordinal is the index in that top-to-bottom order.

    Superscripts and subscripts ride with their body line because their baseline offset is
    typically ~0.3 em, well inside a 0.5 x median-height tolerance. Margin line numbers ride
    with the body line they annotate, because GPO sets them on the same baseline.
    """
    if not glyphs:
        return []
    heights = [max(g[4] - g[2], 0.0) for g in glyphs]
    med_h = statistics.median(heights) or 1.0
    tol = BASELINE_TOL_FACTOR * med_h

    rows: list[list[tuple[float, float, float, float, float]]] = []
    anchor: float | None = None
    for g in sorted(glyphs, key=lambda g: -g[0]):
        if anchor is None or abs(g[0] - anchor) > tol:
            rows.append([g])
            anchor = g[0]
        else:
            rows[-1].append(g)

    out = []
    for i, row in enumerate(rows):
        hs = [max(g[4] - g[2], 0.0) for g in row]
        out.append(
            NeutralLine(
                page=page,
                ordinal=i,
                baseline=round(statistics.median([g[0] for g in row]), 4),
                x0=round(min(g[1] for g in row), 4),
                x1=round(max(g[3] for g in row), 4),
                y0=round(min(g[2] for g in row), 4),
                y1=round(max(g[4] for g in row), 4),
                n_glyphs=len(row),
                median_height=round(statistics.median(hs), 4),
            )
        )
    return out


def project_by_glyphs(lines: list[NeutralLine], glyph_baselines: list[float]) -> int | None:
    """Which neutral line owns an architecture's reconstructed line? BY GLYPH MEMBERSHIP.

    THE PREFERRED RULE, and it replaces baseline-proximity projection because that rule
    FAILED a synthetic test: a reconstructed line that MERGES two neutral lines can carry a
    baseline midway between them, 6 pt from each when the tolerance is 5 pt, and so projected
    to NOTHING -- silently deleting the comparison unit for exactly the merge case the
    D-frame exists to detect.

    Membership needs no tolerance at all. Each reconstructed line is built from specific
    glyphs; each glyph's baseline identifies its neutral line; the reconstructed line belongs
    to the neutral line owning the PLURALITY of its glyphs. Ties go to the lowest ordinal, so
    the result is deterministic. A merge lands on one slot and the other slot records that
    architecture as absent -- which is a reportable difference rather than a lost record.
    """
    if not lines or not glyph_baselines:
        return None
    owner: dict[int, int] = {}
    for b in glyph_baselines:
        near = min(lines, key=lambda ln: (abs(ln.baseline - b), ln.ordinal))
        owner[near.ordinal] = owner.get(near.ordinal, 0) + 1
    return min(owner.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def centred_narrow_lines(lines: list[NeutralLine], width_frac: float = 0.7) -> set[int]:
    """Neutral lines that are NARROW and CENTRED in their page's text column.

    Geometry-only structural signal, offered because the height-based predicate does not
    work (see x07): GPO sets account and agency headings CENTRED, while justified body prose
    spans the full measure and a paragraph's last line is narrow but LEFT-ALIGNED. So
    "narrow AND centred" separates headings from both, using only x-extents.

    Column edges are the modal min-x and max-x over the page's lines, so they are derived
    rather than assumed.
    """
    if not lines:
        return set()
    by_page: dict[int, list[NeutralLine]] = {}
    for ln in lines:
        by_page.setdefault(ln.page, []).append(ln)

    hits: set[int] = set()
    for page, page_lines in by_page.items():
        del page
        # ROBUST PERCENTILES, not medians. The median right edge is dragged inward by every
        # short line on the page, so on a page with several headings the median x1 becomes a
        # heading's own edge and the heading then measures as flush-right -- which is how a
        # first version of this scored zero centred lines. Justified body lines all reach the
        # true measure, so a high percentile finds it; a low percentile finds the left edge.
        xs0 = sorted(ln.x0 for ln in page_lines)
        xs1 = sorted(ln.x1 for ln in page_lines)
        left = xs0[len(xs0) // 10]
        right = xs1[(9 * len(xs1)) // 10]
        measure = right - left
        if measure <= 0:
            continue
        for ln in page_lines:
            extent = ln.x1 - ln.x0
            if extent >= width_frac * measure:
                continue  # spans the measure: body prose
            lead, trail = ln.x0 - left, right - ln.x1
            if lead <= 0 or trail <= 0:
                continue
            # Centred: the two margins are within a third of each other.
            if abs(lead - trail) <= 0.33 * max(lead, trail):
                hits.add(id(ln))
    return hits


def project(lines: list[NeutralLine], baseline: float, tol_factor: float = BASELINE_TOL_FACTOR) -> int | None:
    """Which neutral line does an architecture's reconstructed line belong to?

    BY GEOMETRY ONLY -- the nearest neutral baseline within tolerance. No text similarity is
    consulted, so a spacing or character difference can never move a line to a different
    neutral slot. This is what makes A17.4 disappear: H and X are compared per NEUTRAL line,
    so differing line COUNTS no longer break the alignment. If H merges two neutral lines,
    its one reconstructed line projects onto the nearer of them and the other neutral line
    records H as absent, which is itself a reportable difference rather than a crash.
    """
    if not lines:
        return None
    best = min(lines, key=lambda ln: abs(ln.baseline - baseline))
    if abs(best.baseline - baseline) > tol_factor * (best.median_height or 1.0):
        return None
    return best.ordinal


def regions(lines: list[NeutralLine], size: int = 8) -> list[dict]:
    """Non-overlapping windows of `size` consecutive neutral lines, in reading order.

    NON-OVERLAPPING and ALIGNED TO THE PAGE START, so region identity is a pure function of
    the neutral skeleton: no sampling decision, no dependence on where anything was found.
    A trailing window shorter than `size` is kept -- dropping it would silently delete the
    bottom of every page, and page bottoms are where continuation text lives.
    """
    out = []
    for start in range(0, len(lines), size):
        window = lines[start : start + size]
        out.append(
            {
                "page": window[0].page,
                "region_ordinal": start // size,
                "line_ordinals": [ln.ordinal for ln in window],
                "bbox": [
                    round(min(ln.x0 for ln in window), 4),
                    round(min(ln.y0 for ln in window), 4),
                    round(max(ln.x1 for ln in window), 4),
                    round(max(ln.y1 for ln in window), 4),
                ],
                "n_lines": len(window),
            }
        )
    return out


def body_height_and_enriched(lines: list[NeutralLine], quantum: float = 0.5) -> tuple[float, set[int]]:
    """Geometry-only C-frame predicate: (body height, pages carrying a sub-body cluster).

    The frozen predicate wants pages with a line in the document's "sub-body size cluster"
    but forbids reading character identity, which rules out `derive_size_bands` (it decides
    body size from lines containing LOWERCASE and heading size from UPPERCASE lines).

    This uses line MEDIAN INK HEIGHT only:
      1. quantise every neutral line's median height to `quantum` points;
      2. body height = the MODE of that distribution, weighted by glyph count so a page of
         display type cannot outvote the body text;
      3. a page is enriched if it carries at least one line whose quantised height is
         strictly BELOW body height -- GPO sets account headings in small caps, i.e.
         SMALLER than body, which is why the protocol says "sub-body".

    Its bias is stated, not hidden: it cannot select a page whose headings are set AT body
    height, and it will select pages whose only sub-body lines are footnotes or chrome.
    """
    if not lines:
        return 0.0, set()
    buckets: dict[float, int] = {}
    for ln in lines:
        q = round(ln.median_height / quantum) * quantum
        buckets[q] = buckets.get(q, 0) + ln.n_glyphs
    body = max(buckets.items(), key=lambda kv: (kv[1], kv[0]))[0]
    enriched = {ln.page for ln in lines if round(ln.median_height / quantum) * quantum < body and ln.n_glyphs >= 2}
    return body, enriched
