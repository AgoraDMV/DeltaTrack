"""Hybrid reconstruction: engine-ordered characters + geometry -> DeltaTrack `Page`.

Deliberately a minimal edit of `reconstruct.py`, so that a difference in results is
attributable to the one thing that changed. Identical here: the margin-number regex, the
chrome patterns, the chrome size ratio, the baseline tolerance, the geometry sidecar, the
merge, and the reuse of production's `_merge_print_lines` / `rejoin_soft_hyphens`.

THE ONE THING THAT CHANGED, and the whole hypothesis:

    reconstruct.py  sorts a line's glyphs by x and RE-DERIVES the word spaces from
                    x-gaps, using one global constant (`_SPACE_FACTOR`).
    this module     takes the line's characters in the engine's own order and uses the
                    word spaces the engine already decided, including the ones it
                    SYNTHESISED rather than read from the page.

Line assignment stays geometric (cluster on baseline), not stream-order, and that split
is the point of the design rather than a compromise. The two failure modes are different
and they live at different scales:

  * BETWEEN lines, PDFium's reading order is unreliable on GPO pages -- it floats the
    running header to the top of the page. Geometry fixes that, and `pdf_text.py`'s
    `strip_page_chrome` exists because the string pipeline cannot.
  * WITHIN a line, geometry is not sufficient -- see `probe_space_separability.py`: the
    gap/size ratio at real word boundaries overlaps the ratio inside words, so no single
    threshold separates them. The engine's decision is.

So each layer is used where it is actually the better source, rather than one being
declared authoritative for everything.

WHAT THIS LAYER DOES NOT NEED, and why that is a finding
--------------------------------------------------------
Against `reconstruct.py` it drops the x-gap word-space rule and the "unnamed ink,
line-final" hyphen heuristic. Against `parsers/pdf_text.py` it additionally drops
`normalize_raw` in full: the U+FFFE-plus-glued-margin-number rewrite, the glued-chrome
rewrite, the mid-line hyphen join and the trailing-space strip are all repairs of damage
that only exists in a page-wide text BLOB, and none of it exists once the characters are
addressed by index with their geometry attached.
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

_here = Path(__file__).resolve()
if len(_here.parents) > 3:
    _src = _here.parents[3] / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

from contract_hybrid import BASELINE, CP, FONT, GEN, SIZE, UPRIGHT, X0, X1, HybridPage  # noqa: E402

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
_SOFT_HYPHEN = "­"

# Byte-for-byte the patterns in reconstruct.py. Chrome identification is GPO knowledge,
# not PDF-layout knowledge, so it is exactly the part that should NOT move to the engine.
_CHROME_PATTERNS = (
    re.compile(r"^\d{1,4}$"),
    re.compile(r"^•\s*(?:HR|S|H|HRES|SRES|HJRES|SJRES|HCONRES|SCONRES)\b.*$"),
    re.compile(r"^(?:H|S|HR|HRES|SRES|HJRES|SJRES|HCONRES|SCONRES)\s+\d+\s+[A-Z]{2,4}$"),
    re.compile(r"^VerDate\b"),
    re.compile(r"\bon DSK\S*\s*(?:PROD|with)\b"),
    re.compile(r"^\S+ on DSK"),
)
_CHROME_SIZE_RATIO = 0.55


def cluster_lines(page: HybridPage) -> list[list]:
    """Group a page's characters into printed lines by baseline, top of page first.

    Order WITHIN each returned line is the engine's char order, preserved. Only the
    assignment of a character to a line is geometric.

    Generated characters are kept: their baseline is real (measured -- it is the one
    geometric fact `FPDFText_GetCharOrigin` supplies for them) and they carry the word
    spacing this layer exists to use. They are exempt from the size floor and the upright
    test, both of which read fields a generated char does not have.
    """
    kept = [
        (i, c)
        for i, c in enumerate(page.chars)
        if c[BASELINE] is not None and (c[GEN] or (c[SIZE] is not None and c[SIZE] > _SIZE_FLOOR and c[UPRIGHT]))
    ]
    if not kept:
        return []
    rows: list[list] = []
    current: list = []
    anchor: float | None = None
    # Descending baseline puts the top of the page first. Sorting by baseline is ONLY a
    # way to decide which line a character belongs to; it must not be allowed to decide
    # the order WITHIN a line, because origins on one printed line differ by float noise.
    # Measured: a heading's full-size initial letter reports a baseline 0.003 pt above the
    # small caps that follow it, which is enough for a baseline sort to hoist it to the
    # front of the line and render `MILITARY` as `M6 ILITARY`. Each row is therefore
    # restored to engine order before it is read.
    for item in sorted(kept, key=lambda t: (-t[1][BASELINE], t[0])):
        c = item[1]
        if anchor is None or abs(c[BASELINE] - anchor) <= _BASELINE_TOL:
            current.append(item)
            if anchor is None:
                anchor = c[BASELINE]
        else:
            rows.append(current)
            current = [item]
            anchor = c[BASELINE]
    if current:
        rows.append(current)
    return [[c for _i, c in sorted(row, key=lambda t: t[0])] for row in rows]


def _line_text(row: list) -> str:
    """Join a printed line's characters in engine order. No spacing rule is applied.

    Line-break characters PDFium generates at the end of a row are dropped; the row IS
    the line. A soft hyphen is rendered as an ASCII hyphen so production's
    `_merge_print_lines` and `rejoin_soft_hyphens` see the boundary they already know.
    """
    out = []
    for c in row:
        ch = chr(c[CP])
        if ch in ("\r", "\n"):
            continue
        out.append("-" if ch == _SOFT_HYPHEN else ch)
    return re.sub(r" +", " ", "".join(out)).strip()


def _dominant_size(rows: list[list]) -> float:
    sizes = [c[SIZE] for row in rows for c in row if c[SIZE] is not None]
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
    sizes = [c[SIZE] for c in row if c[SIZE] is not None]
    if not sizes:
        return True
    return bool(body_size) and statistics.median(sizes) < _CHROME_SIZE_RATIO * body_size


def _first_word_right(content: list) -> float | None:
    """Right x-edge of the first word among a line's content characters.

    Simpler than either predecessor, and for a reason worth recording: a word boundary
    here is just "a space character", with no x-gap fallback, because the engine emits a
    space at every boundary -- generated where the content stream has none. The fallback
    the other two implementations need exists only to cover boundaries the engine already
    marked.
    """
    first_right: float | None = None
    for c in content:
        if c[CP] == 32:
            if first_right is None:
                continue
            break
        if c[X1] is not None:
            first_right = c[X1]
    return first_right


def reconstruct_page(page: HybridPage) -> tuple[Page, dict]:
    rows = cluster_lines(page)
    body_size = _dominant_size(rows)

    print_lines: list[Line] = []
    line_sizes: dict[int, tuple[float, LineGeom]] = {}
    ambiguous: set[int] = set()
    n_chrome = n_numbered = n_unnamed = 0
    n_out_of_order = 0

    for row in rows:
        # Diagnostic only, never a correction: how often engine order disagrees with
        # left-to-right x order on a printed line. If this were large the design would be
        # unsound, so it is counted rather than assumed away.
        xs = [c[X0] for c in row if c[X0] is not None]
        if any(b < a for a, b in zip(xs, xs[1:])):
            n_out_of_order += 1

        text = _line_text(row)
        if is_chrome(text, row, body_size):
            n_chrome += 1
            continue
        n_unnamed += text.count("�")

        m = _NUMBERED_LINE.match(text)
        if not m:
            print_lines.append(Line(None, text))
            continue

        n_numbered += 1
        line_number = int(m.group(1))
        print_lines.append(Line(line_number, m.group(2)))

        # Geometry sidecar, keyed by margin line number exactly as production does.
        # The margin number is skipped by counting its characters in the same stream the
        # text was read from, so the two cannot drift apart.
        ink = [c for c in row if chr(c[CP]) not in ("\r", "\n")]
        content = ink[len(m.group(1)) :]
        printed = [c for c in content if c[CP] != 32 and c[X0] is not None]
        if not printed:
            continue
        fwr = _first_word_right(content)
        if fwr is None:
            continue
        geom = LineGeom(printed[0][X0], max(c[X1] for c in printed), fwr)
        sizes = [c[SIZE] for c in printed if c[SIZE] is not None]
        if not sizes:
            continue
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
        "out_of_order_lines": n_out_of_order,
    }
    return Page(page.page_number, tuple(merged), tuple(print_lines), tuple(ranges)), diag


def reconstruct(pages: list[HybridPage]) -> tuple[list[Page], dict]:
    out: list[Page] = []
    agg = {
        "visual_lines": 0,
        "chrome_lines": 0,
        "numbered_lines": 0,
        "ambiguous_numbers": 0,
        "unnamed_glyphs": 0,
        "out_of_order_lines": 0,
    }
    for p in pages:
        page, diag = reconstruct_page(p)
        out.append(page)
        for k, v in diag.items():
            agg[k] += v
    return out, agg


def full_text(pages: list[Page]) -> str:
    return rejoin_soft_hyphens("\n".join(p.text for p in pages))


__all__ = ["cluster_lines", "full_text", "is_chrome", "reconstruct", "reconstruct_page", "FONT"]
