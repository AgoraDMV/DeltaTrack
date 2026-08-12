"""Extended-glyph reconstruction: DeltaTrack decides word boundaries, from geometry.

A deliberate minimal edit of `probes/reconstruct.py`. Identical here: `_BASELINE_TOL`,
`_SIZE_FLOOR`, `_CHROME_SIZE_RATIO`, the chrome patterns, the margin-number regex,
`cluster_lines`, `is_chrome`, `_repair_line_end`, the geometry sidecar, and the reuse of
production's `_merge_print_lines` / `rejoin_soft_hyphens`.

THE ONE THING THAT CHANGED:

    reconstruct.py           inserts a word space when the INK-BOX gap exceeds
                             `_SPACE_FACTOR x size`, one global constant.
    this module              inserts a word space by the rule below, over PEN ORIGINS and
                             FONT ADVANCE WIDTHS.

WHAT THE RULE IS, STATED PLAINLY. It is a **port of PDFium's spacing heuristic**, taken
from `core/fpdftext/cpdf_textpage.cpp` (`GenerateSpace` + `NormalizeThreshold`). It is NOT
a law of PDF geometry, it is NOT engine-neutral in origin, and adopting it means
**DeltaTrack owns and maintains a heuristic Chromium wrote for a different purpose**. That
is a real cost and it belongs in the decision, not in a footnote:

  * upstream may change the heuristic; DeltaTrack's copy will not, so the two will drift
    apart silently and a "matches PDFium" property measured today is not a property that
    holds tomorrow;
  * the constants 400/700/800 and the divisors 2/4/5/6 are unexplained in the source and
    have no derivation this project can appeal to;
  * a bug in it is DeltaTrack's bug, on a corpus DeltaTrack must curate.

Against that, what the port buys is that the DECISION is inspectable, testable and fixable
in this repository, on facts every candidate backend can supply, rather than being an
opaque output of one engine.

The rule reads exactly two facts per character that `contract.Glyph` does not carry:
`origin_x` and `advance`. Everything else it needs is already in the contract.
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

_here = Path(__file__).resolve()
_src = _here.parents[4] / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))
_probes = _here.parents[1].parent / "probes"
if str(_probes) not in sys.path:
    sys.path.insert(0, str(_probes))

from contract_extended import ADVANCE, BASELINE, CP, FONT, ORIGIN_X, SIZE, UPRIGHT, X0, X1, ExtPdfPage  # noqa: E402

from deltatrack.parsers.pdf_text import (  # noqa: E402
    Line,
    LineGeom,
    Page,
    _merge_print_lines,
    rejoin_soft_hyphens,
)

_NUMBERED_LINE = re.compile(r"^(\d{1,2}) (.*)$")
_SIZE_FLOOR = 1.0
_BASELINE_TOL = 0.6
_CHROME_PATTERNS = (
    re.compile(r"^\d{1,4}$"),
    re.compile(r"^•\s*(?:HR|S|H|HRES|SRES|HJRES|SJRES|HCONRES|SCONRES)\b.*$"),
    re.compile(r"^(?:H|S|HR|HRES|SRES|HJRES|SJRES|HCONRES|SCONRES)\s+\d+\s+[A-Z]{2,4}$"),
    re.compile(r"^VerDate\b"),
    re.compile(r"\bon DSK\S*\s*(?:PROD|with)\b"),
    re.compile(r"^\S+ on DSK"),
)
_CHROME_SIZE_RATIO = 0.55

# Fallback for a character whose advance the backend could not supply. Measured on this
# corpus that is only GPO's soft hyphen (see pdfium_extended.py), so the fallback is
# reached rarely -- but it must exist, and it must be a documented number rather than an
# implicit zero, because a zero advance would make every following pair look like a gap.
_ADVANCE_FALLBACK_EM = 0.5


# --------------------------------------------------------------------------- the rule


def _normalize_threshold(t: float, t1: int = 400, t2: int = 700, t3: int = 800) -> float:
    """Port of PDFium's NormalizeThreshold. The constants are upstream's, unexplained."""
    if t < t1:
        return t / 2.0
    if t < t2:
        return t / 4.0
    if t < t3:
        return t / 5.0
    return t / 6.0


def _generate_space(pos_x: float, last_pos: float, this_w: float, last_w: float, threshold: float) -> bool:
    """Port of PDFium's GenerateSpace."""
    if abs(last_pos + last_w - pos_x) <= threshold:
        return False
    threshold_pos = threshold + last_w
    diff = pos_x - last_pos
    if abs(diff) > threshold_pos:
        return True
    if pos_x < 0 and -threshold_pos > diff:
        return True
    return diff > this_w + last_w


def _advance(g) -> float:
    a = g[ADVANCE]
    return a if a is not None else _ADVANCE_FALLBACK_EM * g[SIZE]


def wants_space(prev, cur) -> bool:
    """Should a word space go between these two adjacent glyphs on one printed line?"""
    lw, tw = _advance(prev), _advance(cur)
    n_last = (lw / prev[SIZE] * 1000.0) if prev[SIZE] else 0.0
    n_this = (tw / cur[SIZE] * 1000.0) if cur[SIZE] else 0.0
    thr = _normalize_threshold(max(n_last, n_this))
    thr *= prev[SIZE] if n_last >= n_this else cur[SIZE]
    thr /= 1000.0
    return _generate_space(cur[ORIGIN_X], prev[ORIGIN_X], tw, lw, thr)


# ------------------------------------------------------------------- reconstruction


def _line_text(cluster: list) -> str:
    """Join a printed line, inserting spaces by the ported rule rather than by a constant.

    Ordering is by PEN ORIGIN, not by ink left edge. On tight settings the two agree; they
    diverge on glyphs with unusual side bearings, and the pen order is the one the rule's
    arithmetic assumes.
    """
    items = sorted(cluster, key=lambda g: g[ORIGIN_X])
    out: list[str] = []
    prev = None
    for g in items:
        if prev is not None and wants_space(prev, g):
            out.append(" ")
        out.append(chr(g[CP]))
        prev = g
    return re.sub(r" +", " ", "".join(out)).strip()


def _first_word_right(content_glyphs: list) -> float | None:
    """Right x-edge of the first word. Same two-test shape as reconstruct.py, new rule."""
    first_word_right: float | None = None
    prev = None
    for g in content_glyphs:
        if g[CP] == 32:
            if first_word_right is None:
                continue
            break
        if prev is not None and wants_space(prev, g):
            break
        first_word_right = g[X1]
        prev = g
    return first_word_right


def cluster_lines(page: ExtPdfPage) -> list[list]:
    kept = [g for g in page.glyphs if g[SIZE] > _SIZE_FLOOR and g[UPRIGHT]]
    if not kept:
        return []
    rows: list[list] = []
    current: list = []
    anchor: float | None = None
    for g in sorted(kept, key=lambda g: -g[BASELINE]):
        if anchor is None or abs(g[BASELINE] - anchor) <= _BASELINE_TOL:
            current.append(g)
            if anchor is None:
                anchor = g[BASELINE]
        else:
            rows.append(current)
            current = [g]
            anchor = g[BASELINE]
    if current:
        rows.append(current)
    return rows


def _dominant_size(rows: list[list]) -> float:
    sizes = [g[SIZE] for row in rows for g in row]
    if not sizes:
        return 0.0
    try:
        return statistics.mode([round(s, 1) for s in sizes])
    except statistics.StatisticsError:
        return statistics.median(sizes)


def is_chrome(text: str, row: list, body_size: float) -> bool:
    if not text:
        return True
    for pat in _CHROME_PATTERNS:
        if pat.search(text):
            return True
    row_size = statistics.median([g[SIZE] for g in row])
    return bool(body_size) and row_size < _CHROME_SIZE_RATIO * body_size


def _repair_line_end(text: str) -> tuple[str, bool]:
    if text.endswith("�"):
        return text[:-1] + "-", True
    return text, False


def reconstruct_page(page: ExtPdfPage, repaired: bool = False) -> tuple[Page, dict]:
    rows = cluster_lines(page)
    body_size = _dominant_size(rows)

    print_lines: list[Line] = []
    line_sizes: dict[int, tuple[float, LineGeom]] = {}
    ambiguous: set[int] = set()
    n_chrome = n_numbered = n_repaired = n_unnamed = n_no_adv = 0

    for row in rows:
        ordered = sorted(row, key=lambda g: g[ORIGIN_X])
        n_no_adv += sum(1 for g in ordered if g[ADVANCE] is None)
        text = _line_text(ordered)
        if is_chrome(text, ordered, body_size):
            n_chrome += 1
            continue

        n_unnamed += text.count("�")
        if repaired:
            text, did = _repair_line_end(text)
            n_repaired += did

        m = _NUMBERED_LINE.match(text)
        if not m:
            print_lines.append(Line(None, text))
            continue

        n_numbered += 1
        line_number = int(m.group(1))
        print_lines.append(Line(line_number, m.group(2)))

        n_margin = len(m.group(1))
        content_glyphs = ordered[n_margin:]
        printed = [g for g in content_glyphs if g[CP] != 32]
        if not printed:
            continue
        sizes = [g[SIZE] for g in printed]
        fwr = _first_word_right(content_glyphs)
        if fwr is None:
            continue
        geom = LineGeom(printed[0][X0], max(g[X1] for g in printed), fwr)
        if line_number in line_sizes or line_number in ambiguous:
            ambiguous.add(line_number)
            line_sizes.pop(line_number, None)
            continue
        line_sizes[line_number] = (round(statistics.median(sizes), 1), geom)

    merged, ranges = _merge_print_lines(print_lines)
    merged = [
        ln
        if ln.line_number is None or ln.line_number not in line_sizes
        else Line(ln.line_number, ln.text, line_sizes[ln.line_number][0], line_sizes[ln.line_number][1])
        for ln in merged
    ]
    diag = {
        "visual_lines": len(rows),
        "chrome_lines": n_chrome,
        "numbered_lines": n_numbered,
        "ambiguous_numbers": len(ambiguous),
        "unnamed_glyphs": n_unnamed,
        "repaired_line_ends": n_repaired,
        "glyphs_without_an_advance": n_no_adv,
    }
    return Page(page.page_number, tuple(merged), tuple(print_lines), tuple(ranges)), diag


def reconstruct(pages: list[ExtPdfPage], repaired: bool = False) -> tuple[list[Page], dict]:
    out: list[Page] = []
    agg = {
        "visual_lines": 0,
        "chrome_lines": 0,
        "numbered_lines": 0,
        "ambiguous_numbers": 0,
        "unnamed_glyphs": 0,
        "repaired_line_ends": 0,
        "glyphs_without_an_advance": 0,
    }
    for p in pages:
        page, diag = reconstruct_page(p, repaired=repaired)
        out.append(page)
        for k, v in diag.items():
            agg[k] += v
    return out, agg


def full_text(pages: list[Page]) -> str:
    return rejoin_soft_hyphens("\n".join(p.text for p in pages))


__all__ = ["cluster_lines", "full_text", "is_chrome", "reconstruct", "reconstruct_page", "wants_space", "FONT"]
