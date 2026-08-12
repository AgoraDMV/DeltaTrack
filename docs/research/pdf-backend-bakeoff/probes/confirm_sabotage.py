"""B0 -- per-metric sabotage controls. A metric that cannot fail cannot rank anything.

PRE-REGISTRATION-CONFIRMATORY.md, "B0 -- harness sensitivity controls".

One uniform glyph dropout is not a sufficient control. It garbles text (so B1 falls) but
barely disturbs where a heading sits (so B5 need not move), and a metric that survives it
may be blind rather than robust -- voiding it on that evidence would be its own false
negative. So each metric gets a sabotage that injects the specific fault that metric
claims to catch, applied to a candidate's glyph stream with seed 20260805.

  S1  B1   delete 5% of glyphs, uniformly at random
  S2  B2   collapse the small-caps size band on heading lines
  S3  B3a  delete the margin-number glyph run on 5% of numbered lines
  S4  B5   move heading lines down one line-height -- text intact, attachment wrong
  S5  B6   delete agency headings only, so their children reparent
  SA1 A1   perturb one digit of one amount
  SA2 A2   delete one printed line's glyphs
  SA3 A4   delete a single glyph

S4 and S5 carry SEPARABILITY requirements, and those are the point rather than
decoration. S4 leaves every heading label intact and only moves where it sits: if B2
falls as far as B5 does, B2 and B5 are measuring the same thing and the association
metric adds nothing. Same for S5 against B6. That verdict -- "not separable" -- is a
different finding from either metric being blind, and must not be written as one.
"""

from __future__ import annotations

import random
import re
import statistics
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import reconstruct as R  # noqa: E402
from contract import BASELINE, CP, SIZE, X0, Y0, Y1, PdfPage  # noqa: E402

SEED = 20260805
_NUMBERED = re.compile(r"^(\d{1,2}) ")


def _clone(pages: list[PdfPage]) -> list[PdfPage]:
    return [PdfPage(page_number=p.page_number, width=p.width, height=p.height, glyphs=list(p.glyphs)) for p in pages]


def _rows(page: PdfPage) -> list[list]:
    """Baseline-clustered rows, memoized ON the page object.

    Cached as an attribute rather than in a module dict keyed by id(): a freed page's id
    can be reused by a later one, which would silently serve another document's rows. The
    attribute lives and dies with the object it describes. Every sabotage clusters the
    same pages, and clustering is O(n log n) over ~3M glyphs on the largest bill.
    """
    cached = getattr(page, "_rows_cache", None)
    if cached is not None and cached[0] == len(page.glyphs):
        return cached[1]
    rows = R.cluster_lines(page)
    page._rows_cache = (len(page.glyphs), rows)
    return rows


_SMALLCAPS_LO, _SMALLCAPS_HI = 0.70, 0.90


def _heading_rows(page: PdfPage) -> list[list]:
    """Rows carrying GPO's faux small-caps signal: two sizes inside ONE printed line.

    Measured, not assumed. On 118-hr-4366 the body face is 14pt and an account heading is
    14pt initials with an 11.2pt body -- a ratio of exactly 0.800 -- and those heading
    lines are the only non-chrome rows on their page carrying more than one size.

    An earlier version of this function looked for a size step UP against the page's
    dominant size, which is backwards: the heading's small caps are SMALLER than the body
    face, so it matched nothing, S2/S4 silently became no-ops, and their metrics would
    have been declared void on a harness bug rather than on a blind metric. That is the
    exact failure B0 exists to catch, and here it caught the control itself.
    """
    rows = _rows(page)
    if not rows:
        return []
    body = R._dominant_size(rows)
    out = []
    for row in rows:
        sizes = sorted({round(g[SIZE], 1) for g in row})
        if len(sizes) < 2:
            continue
        if not (_SMALLCAPS_LO <= sizes[0] / sizes[-1] <= _SMALLCAPS_HI):
            continue
        if R.is_chrome(R._line_text(row), row, body):
            continue
        out.append(row)
    return out


def _line_height(page: PdfPage) -> float:
    rows = _rows(page)
    baselines = sorted({round(row[0][BASELINE], 2) for row in rows if row}, reverse=True)
    gaps = [a - b for a, b in zip(baselines, baselines[1:], strict=False) if 4.0 < a - b < 30.0]
    return statistics.median(gaps) if gaps else 12.0


# ---------- Concern B sabotages ----------------------------------------------


def s1_drop_glyphs(pages: list[PdfPage], rate: float = 0.05) -> list[PdfPage]:
    """S1 (targets B1): uniform glyph dropout. Garbles tokens; leaves layout alone."""
    rng = random.Random(SEED)
    out = _clone(pages)
    for page in out:
        page.glyphs = [g for g in page.glyphs if rng.random() >= rate]
    return out


def s2_collapse_size_band(pages: list[PdfPage]) -> list[PdfPage]:
    """S2 (targets B2): flatten every heading line to one size.

    This is the real PDF.js failure mode, not an invented one: `getTextContent()` merges
    the alternating 14pt/11.2pt runs of a small-caps heading and reports a single size, so
    the band ADR 0012's heading recovery reads collapses. Reproducing it deliberately is
    what proves B2 can see it.
    """
    out = _clone(pages)
    for page in out:
        med = {}
        for row in _heading_rows(page):
            m = statistics.median([g[SIZE] for g in row])
            for g in row:
                med[id(g)] = m
        if not med:
            continue
        page.glyphs = [(g[:SIZE] + (med[id(g)],) + g[SIZE + 1 :]) if id(g) in med else g for g in page.glyphs]
    return out


def s3_drop_margin_numbers(pages: list[PdfPage], rate: float = 0.05) -> list[PdfPage]:
    """S3 (targets B3a): delete the leading margin-number glyphs on some numbered lines."""
    rng = random.Random(SEED)
    out = _clone(pages)
    for page in out:
        drop: set[int] = set()
        for row in _rows(page):
            text = R._line_text(row)
            if not _NUMBERED.match(text):
                continue
            if rng.random() >= rate:
                continue
            ordered = sorted(row, key=lambda g: g[X0])
            for g in ordered:
                if chr(g[CP]).isdigit():
                    drop.add(id(g))
                elif drop:
                    break
        if drop:
            page.glyphs = [g for g in page.glyphs if id(g) not in drop]
    return out


def s4_rotate_heading_slots(pages: list[PdfPage]) -> list[PdfPage]:
    """S4 (targets B5): give each heading the NEXT heading's slot, cyclically.

    The purest attachment-only fault available. Every heading keeps its exact glyphs, and
    every heading still lands where a heading was, so detection is untouched; all that
    changes is which block each one precedes. B5 must fall; B2 should barely move.

    Two earlier designs are recorded because each failed for a reason worth keeping:

      * shift heading lines down one line-height -- drops them into the next line's
        baseline cluster and garbles both lines. B1 fell 0.108 and B2 0.443 against B5's
        0.461: it corrupted the document rather than its structure.
      * swap each heading with the row below it -- cleaner, but the row below is usually
        a body line of the heading's OWN block, so the heading lands mid-sentence and
        stops being detected. B2 moved 0.053 against a 0.020 separability rule.

    This is the last revision of S4. If separability still fails over the population, the
    verdict is NOT SEPARABLE and it is reported as such rather than tuned away.
    """
    out = _clone(pages)
    slots: list[tuple[int, float, list]] = []
    for pi, page in enumerate(out):
        for row in _heading_rows(page):
            if row:
                slots.append((pi, row[0][BASELINE], row))
    if len(slots) < 2:
        return out

    moves: list[tuple[int, float, list]] = []
    for i, (_pi, base, row) in enumerate(slots):
        tpi, tbase, _ = slots[(i + 1) % len(slots)]
        moves.append((tpi, tbase - base, row))

    victims = {id(g) for _t, _d, row in moves for g in row}
    for page in out:
        page.glyphs = [g for g in page.glyphs if id(g) not in victims]
    for tpi, delta, row in moves:
        out[tpi].glyphs.extend(
            g[:Y0] + (g[Y0] + delta, g[Y0 + 1], g[Y1] + delta, g[BASELINE] + delta) + g[BASELINE + 1 :] for g in row
        )
    return out


def s2b_delete_heading_lines(pages: list[PdfPage], rate: float = 0.20) -> list[PdfPage]:
    """S2b (targets B2): delete a fraction of heading lines outright.

    The direct injection of the fault B2 names -- "this backend did not recover the
    heading label". S2's size-band collapse is kept alongside it because its RESULT is
    informative (see its docstring), but a metric must be controlled against the fault it
    claims to catch, not only against one mechanism that could cause it.
    """
    rng = random.Random(SEED)
    out = _clone(pages)
    for page in out:
        drop: set[int] = set()
        for row in _heading_rows(page):
            if rng.random() < rate:
                drop.update(id(g) for g in row)
        if drop:
            page.glyphs = [g for g in page.glyphs if id(g) not in drop]
    return out


def s5_drop_agency_headings(pages: list[PdfPage]) -> list[PdfPage]:
    """S5 (targets B6): delete agency headings only, so accounts reparent upward.

    Two-pass: reconstruct the clean pages to find which printed lines the product calls
    `agency`, then delete those lines' glyphs from the raw stream. Levels come from the
    product's own detector, so the sabotage removes what B6 is about rather than what a
    heuristic guesses.
    """
    from deltatrack.parsers.pdf_anchors import extract_anchors

    clean, _ = R.reconstruct(pages, repaired=True)
    victims = {
        (a.page_number, a.line_number)
        for a in extract_anchors(clean)
        if a.kind == "agency" and a.line_number is not None
    }
    if not victims:
        return _clone(pages)

    out = _clone(pages)
    for page in out:
        want = {ln for (pn, ln) in victims if pn == page.page_number}
        if not want:
            continue
        # Locate the row by its own printed margin number rather than by a Line.geom
        # baseline: geom is None on ordinary print lines, so a geom-keyed lookup finds
        # nothing and the sabotage silently does nothing.
        drop: set[int] = set()
        for row in _rows(page):
            m = _NUMBERED.match(R._line_text(row))
            if m and int(m.group(1)) in want:
                drop.update(id(g) for g in row)
        if drop:
            page.glyphs = [g for g in page.glyphs if id(g) not in drop]
    return out


# ---------- Concern A sabotages ----------------------------------------------


def sa1_perturb_amount(pages: list[PdfPage]) -> list[PdfPage]:
    """SA1 (targets A1): change one digit of one dollar amount."""
    out = _clone(pages)
    for page in out:
        for row in _rows(page):
            ordered = sorted(row, key=lambda g: g[X0])
            text = "".join(chr(g[CP]) for g in ordered)
            m = re.search(r"\$[\d,]{4,}", text)
            if not m:
                continue
            for i in range(m.start() + 1, m.end()):
                g = ordered[i]
                if chr(g[CP]).isdigit():
                    new_cp = ord("9") if chr(g[CP]) != "9" else ord("1")
                    tgt = id(g)
                    page.glyphs = [(new_cp,) + x[1:] if id(x) == tgt else x for x in page.glyphs]
                    return out
    return out


def sa2_drop_line(pages: list[PdfPage]) -> list[PdfPage]:
    """SA2 (targets A2): delete one printed line's glyphs, mid-document."""
    out = _clone(pages)
    if not out:
        return out
    page = out[len(out) // 2]
    rows = _rows(page)
    body = [r for r in rows if len(r) > 20]
    if not body:
        return out
    victim = {id(g) for g in body[len(body) // 2]}
    page.glyphs = [g for g in page.glyphs if id(g) not in victim]
    return out


def sa3_drop_one_glyph(pages: list[PdfPage]) -> list[PdfPage]:
    """SA3 (targets A4): delete a single glyph. The smallest fault A4 must still catch."""
    out = _clone(pages)
    for page in out:
        if len(page.glyphs) > 100:
            page.glyphs = page.glyphs[:50] + page.glyphs[51:]
            return out
    return out


B_SABOTAGES = {
    "S1": (s1_drop_glyphs, "B1"),
    "S2": (s2_collapse_size_band, "B2"),
    "S2b": (s2b_delete_heading_lines, "B2"),
    "S3": (s3_drop_margin_numbers, "B3a"),
    "S4": (s4_rotate_heading_slots, "B5"),
    "S5": (s5_drop_agency_headings, "B6"),
}

# The control that decides a metric's void verdict. S2 stays in the run because its
# result is informative -- it measures how much the anchor detector actually leans on the
# small-caps size band -- but S2b is the one that injects "heading not recovered", which
# is the fault B2 names.
DECIDING = {"B1": "S1", "B2": "S2b", "B3a": "S3", "B5": "S4", "B6": "S5"}

A_SABOTAGES = {
    "SA1": (sa1_perturb_amount, "A1"),
    "SA2": (sa2_drop_line, "A2"),
    "SA3": (sa3_drop_one_glyph, "A4"),
}

# Separability: (sabotage, its own metric, the metric that must move LESS).
SEPARABILITY = [
    ("S4", "B5", "B2", "threshold", 0.020),
    ("S5", "B6", "B2", "strictly-less", None),
]
