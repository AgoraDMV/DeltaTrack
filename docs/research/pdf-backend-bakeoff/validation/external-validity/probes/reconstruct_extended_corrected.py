"""X's word segmentation: the ported geometric rule, carrying provenance. RESULT-BEARING.

    frozen rule        PRE-REGISTRATION 3.3 -- line clustering, chrome stripping,
                       margin-number parsing and `_merge_print_lines` are the SAME CODE on
                       both arms, so a metric difference is attributable to the seam and to
                       nothing else. A21/A23 -- emitted unit is `Page.print_lines`, cells
                       carry gids, inserted spaces carry `gid=None`.
    executable here    a minimal edit of `validation/phase2/reconstruct_extended.py`: the
                       spacing rule is byte-identical, the cells carry gids, and every space
                       this module inserts is marked `gid=None` because X's contract carries
                       no U+0020 at all.
    test               `x13_x_arm.py`, `x2_verify.py`
    evidence           `results/x13_x_arm.json`, `results/x2_contract_assertions.json`

THE ONE THING THAT DIFFERS FROM H, which is the entire experiment: H takes the word spaces
PDFium already decided (including the ones it SYNTHESISED); X re-derives every boundary from
pen origins and font advance widths, by a port of PDFium's own `GenerateSpace` /
`NormalizeThreshold`. That port is DeltaTrack's to own and maintain -- upstream may change
it, the constants 400/700/800 are unexplained in the source, and a bug in it is DeltaTrack's
bug. That cost is stated in phase 2's findings and is not re-argued here.

WHY EVERY INSERTED SPACE HAS `gid=None`. X's contract carries no U+0020, so a space in X's
output is never a source glyph -- it is always X's own decision. Marking it `None` is what
keeps the seam visible through Model G projection and what keeps a spacing decision out of
the reconstruction signature.
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

_here = Path(__file__).resolve()
_src = _here.parents[5] / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from neutral_identity import Cell, EmittedLine  # noqa: E402
from pdfium_extended_corrected import ADVANCE, CP, ORIGIN_X, SCI, SIZE, UPRIGHT, X0, X1  # noqa: E402
from pdfium_extended_corrected import BASELINE as EBASELINE  # noqa: E402

from deltatrack.parsers.pdf_text import Line, LineGeom, Page, _merge_print_lines  # noqa: E402

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


def _cells(cluster: list, decider=None) -> list[Cell]:
    """One printed line as an ordered `Cell` stream.

    Ordering is by PEN ORIGIN, not by ink left edge: on tight settings the two agree, they
    diverge on unusual side bearings, and the pen order is the one the rule's arithmetic
    assumes. Every space here is INSERTED by the rule, so it carries `ngid=None`.

    `decider` is the WORD-BOUNDARY DECISION FUNCTION. It defaults to `wants_space`, so
    ordinary X is byte-for-byte what it was; nothing about the scoring path changes. The
    parameter exists so `x2_verify` can build the A25 counterfactual X-prime -- ordinary X
    plus PDFium's generated-boundary decisions -- WITHOUT injecting generated characters
    into X's contract, which is the object X's architecture deliberately excludes. The
    boundary layer is the only place the counterfactual differs.
    """
    want = decider or wants_space
    items = sorted(cluster, key=lambda g: g[ORIGIN_X])
    out: list[Cell] = []
    prev = None
    for g in items:
        if prev is not None and want(prev, g):
            # X INVENTED this space: no provenance and no neutral identity.
            out.append(Cell(ngid=None, char=" ", sci=None))
        # X's contract carries no U+0020 at all, so every glyph here is neutral ink and
        # its provenance and its identity coincide.
        out.append(Cell(ngid=g[SCI], char=chr(g[CP]), sci=g[SCI]))
        prev = g
    # collapse space runs and strip ends, exactly as the frozen module's
    # `re.sub(r" +", " ", ...).strip()` does, but cell-wise so identities survive
    collapsed: list[Cell] = []
    for cell in out:
        if cell.char == " " and collapsed and collapsed[-1].char == " ":
            continue
        collapsed.append(cell)
    while collapsed and collapsed[0].char == " ":
        collapsed.pop(0)
    while collapsed and collapsed[-1].char == " ":
        collapsed.pop()
    return collapsed


def _line_text(cluster: list, decider=None) -> str:
    return "".join(c.char for c in _cells(cluster, decider))


def cluster_lines(page) -> list[list]:
    """Baseline clustering. HELD IDENTICAL to H by PRE-REGISTRATION 3.3."""
    kept = [g for g in page.glyphs if g[SIZE] > _SIZE_FLOOR and g[UPRIGHT]]
    if not kept:
        return []
    rows: list[list] = []
    current: list = []
    anchor: float | None = None
    for g in sorted(kept, key=lambda g: -g[EBASELINE]):
        if anchor is None or abs(g[EBASELINE] - anchor) <= _BASELINE_TOL:
            current.append(g)
            if anchor is None:
                anchor = g[EBASELINE]
        else:
            rows.append(current)
            current = [g]
            anchor = g[EBASELINE]
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


def reconstruct_page(page, decider=None) -> tuple[Page, list[EmittedLine], dict]:
    """Production's `Page` AND the provenance-carrying emitted printed lines, together.

    Both come from ONE pass, so the emitted lines cannot drift from the Page that anchors
    and amounts are read off.
    """
    rows = cluster_lines(page)
    body_size = _dominant_size(rows)

    print_lines: list[Line] = []
    emitted: list[EmittedLine] = []
    line_sizes: dict[int, tuple[float, LineGeom]] = {}
    ambiguous: set[int] = set()
    n_chrome = n_numbered = n_unnamed = n_no_adv = 0

    for row in rows:
        ordered = sorted(row, key=lambda g: g[ORIGIN_X])
        n_no_adv += sum(1 for g in ordered if g[ADVANCE] is None)
        cells = _cells(ordered, decider)
        text = "".join(c.char for c in cells)
        if is_chrome(text, ordered, body_size):
            n_chrome += 1
            continue
        n_unnamed += text.count("�")

        m = _NUMBERED_LINE.match(text)
        if not m:
            print_lines.append(Line(None, text))
            emitted.append(EmittedLine(cells=cells, lid=(page.page_number, len(emitted))))
            continue

        n_numbered += 1
        line_number = int(m.group(1))
        print_lines.append(Line(line_number, m.group(2)))
        emitted.append(EmittedLine(cells=cells[len(m.group(1)) + 1 :], lid=(page.page_number, len(emitted))))

        n_margin = len(m.group(1))
        content_glyphs = ordered[n_margin:]
        printed = [g for g in content_glyphs if g[CP] != 32]
        if not printed:
            continue
        sizes = [g[SIZE] for g in printed]
        fwr = _first_word_right(content_glyphs, decider)
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
        "glyphs_without_an_advance": n_no_adv,
    }
    return Page(page.page_number, tuple(merged), tuple(print_lines), tuple(ranges)), emitted, diag


def _first_word_right(content_glyphs: list, decider=None) -> float | None:
    """Right x-edge of the first word. Same two-test shape as the frozen module, new rule."""
    want = decider or wants_space
    first_word_right: float | None = None
    prev = None
    for g in content_glyphs:
        if g[CP] == 32:
            if first_word_right is None:
                continue
            break
        if prev is not None and want(prev, g):
            break
        first_word_right = g[X1]
        prev = g
    return first_word_right
