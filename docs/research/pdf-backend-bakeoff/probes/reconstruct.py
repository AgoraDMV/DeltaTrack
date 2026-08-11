"""Neutral reconstruction: `PdfPage` glyph facts -> the `Page`/`Line` structures DeltaTrack consumes.

This is the layer the spec calls for in "the seam must be glyph facts, not PDFium-shaped
text". Every backend is graded through this one implementation, so no backend can win by
imitating the incumbent's text-API conventions.

WHAT THIS LAYER DOES NOT NEED, and why that matters
---------------------------------------------------
`parsers/pdf_text.normalize_raw` has no counterpart here, and that is the point. Every
transformation it performs exists to undo damage PDFium's *text API* does:

  * the U+FFFE soft-hyphen glyph with the next margin number glued inline
  * footer chrome dragged onto a line by a page-boundary hyphen
  * trailing spaces PDFium keeps on nearly every line
  * a scrambled reading order that floats running headers to the top of the page

None of those exist in the glyph stream. At glyph level GPO renders an ordinary
hyphen-minus at a syllable break, chrome sits where it is printed, and reading order is
whatever we choose -- here, strictly top-to-bottom by baseline. So the neutral path is
SHORTER than the incumbent's, not longer, and it is a genuine finding of this spike that
~40% of `pdf_text.py`'s regex surface is backend-repair rather than domain logic.

WHAT IT REUSES
--------------
`_merge_print_lines`, `_parse_print_lines` and `rejoin_soft_hyphens` are imported from
production unchanged: they operate on already-assembled lines and carry no PDFium
assumption. `_line_text` and `_first_word_right` are reimplemented here only because the
production versions take a fixed 5-tuple; the logic (gap-based spacing, space-glyph word
boundary) is identical and is exercised against the incumbent by the calibration gate.

`_cluster_baselines` is deliberately NOT reused. It clusters on the char-box bottom with
a tolerance of 0.5x the page-median glyph size, which is correct for its own purpose (a
margin-number -> geometry sidecar, where a descender-only fragment simply fails the
line-number match and is dropped) but wrong for text reconstruction: on a 14pt body line
the descender drop is ~8.4pt against a 7pt tolerance, so `heading` splits into `headin`
plus a stray `g`. The contract carries the text-matrix origin instead, which every
candidate backend exposes and which is exact.
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

# Locate the engine relative to this file when running from the checkout. Under Pyodide
# the probes live in a flat VFS with no repo above them and `deltatrack` is already on
# sys.path, so the derivation is guarded rather than assumed -- an unguarded parents[3]
# raises IndexError there and takes every browser backend down with it.
_here = Path(__file__).resolve()
if len(_here.parents) > 3:
    _src = _here.parents[3] / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

from contract import BASELINE, CP, SIZE, UPRIGHT, X0, X1, PdfPage  # noqa: E402

from deltatrack.parsers.pdf_text import (  # noqa: E402
    Line,
    LineGeom,
    Page,
    _merge_print_lines,
    rejoin_soft_hyphens,
)

_NUMBERED_LINE = re.compile(r"^(\d{1,2}) (.*)$")
_SIZE_FLOOR = 1.0  # points; drop degenerate/zero-scale glyphs (clip/invisible)
_SPACE_FACTOR = 0.25  # x-gap > factor x glyph size => insert a word space
_BASELINE_TOL = 0.6  # points; baselines within this are the same printed line

# Page chrome, matched against a RECONSTRUCTED VISUAL LINE (not a scrambled text blob),
# so each pattern anchors the whole line rather than hunting inside a page-wide string.
_CHROME_PATTERNS = (
    re.compile(r"^\d{1,4}$"),  # page-number header
    re.compile(r"^•\s*(?:HR|S|H|HRES|SRES|HJRES|SJRES|HCONRES|SCONRES)\b.*$"),
    re.compile(r"^(?:H|S|HR|HRES|SRES|HJRES|SJRES|HCONRES|SCONRES)\s+\d+\s+[A-Z]{2,4}$"),
    re.compile(r"^VerDate\b"),
    re.compile(r"\bon DSK\S*\s*(?:PROD|with)\b"),
    re.compile(r"^\S+ on DSK"),
)
# The rotated left-gutter watermark is set in a small face and breaks into 2-4 glyph
# fragments ('ORP', 'N32', 'Dn'). It is caught by size, not by pattern: no printed body
# line on a GPO bill page is set below this fraction of the page's dominant body size.
_CHROME_SIZE_RATIO = 0.55


def _line_text(cluster: list) -> str:
    """Reconstruct a visual line's text, inserting a space where the x-gap to the next
    glyph exceeds SPACE_FACTOR x its size.

    Backend-neutral in both directions: PDFium emits real space glyphs and needs the gap
    rule only between the margin number and the body, while PDF.js loses inter-word
    spaces at font boundaries (`Providedfurther,That`) and needs the gap rule everywhere.
    One rule serves both, which is why the seam is geometry rather than text.
    """
    items = sorted(cluster, key=lambda g: g[X0])
    out: list[str] = []
    prev_right: float | None = None
    for g in items:
        if prev_right is not None and g[X0] - prev_right > _SPACE_FACTOR * g[SIZE]:
            out.append(" ")
        out.append(chr(g[CP]))
        prev_right = g[X1]
    return re.sub(r" +", " ", "".join(out)).strip()


def _first_word_right(content_glyphs: list) -> float | None:
    """Right x-edge of the first word in a line's content glyphs, or None if empty.

    Same two-test rule as production: a real space glyph ends the first word, and a wide
    x-gap is the fallback for backends that emit no space glyph.
    """
    first_word_right: float | None = None
    prev_right: float | None = None
    for g in content_glyphs:
        if g[CP] == 32:
            if first_word_right is None:
                continue
            break
        if prev_right is not None and g[X0] - prev_right > _SPACE_FACTOR * g[SIZE]:
            break
        first_word_right = g[X1]
        prev_right = g[X1]
    return first_word_right


def cluster_lines(page: PdfPage) -> list[list]:
    """Group a page's glyphs into printed lines by baseline, top of page first.

    Tolerance is a small absolute value rather than a fraction of glyph size: the
    contract's baseline is the text-matrix origin, which is exact and shared across a
    printed line regardless of the glyph sizes on it, so no size-derived slack is needed.
    A fractional tolerance would merge a small chrome line into an adjacent body line on
    pages where the two sit close together.
    """
    # Rotated glyphs are excluded outright. GPO sets a vertical watermark down the left
    # gutter; for rotated text the matrix origin is not a horizontal baseline, so those
    # glyphs land on arbitrary y values and collide with body lines (measured: a stray
    # rotated glyph destroyed the margin-number match on printed lines 24 and 25). They
    # are page chrome in every case, so dropping them loses nothing.
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
    """The page's dominant printed-body glyph size, used as the chrome size threshold."""
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
    """Rewrite a trailing unnamed glyph (U+FFFD) as a hyphen.

    THE POSITION RULE, and why it is neutral. A backend that cannot name a glyph still
    reports that there is ink there. When that ink is the LAST thing on a printed line,
    the only thing GPO sets in that position is a syllable-break hyphen, so the identity
    is recoverable from position alone. The rule never inspects a backend-specific
    codepoint (PDFium's 0x02, pdfminer's "(cid:N)"), only "unnamed ink, line-final", so
    it is available to every backend equally and is a no-op for the four that already
    resolve the character.

    It is applied in `repaired` mode ONLY. Scoring runs both ways and reports the gap,
    because the size of that gap IS the measurement of a backend's glyph-naming deficit,
    and folding the repair in by default would hide exactly the difference the bake-off
    exists to find.
    """
    if text.endswith("�"):
        return text[:-1] + "-", True
    return text, False


def reconstruct_page(page: PdfPage, repaired: bool = False) -> tuple[Page, dict]:
    """Turn one `PdfPage` of glyph facts into a DeltaTrack `Page`.

    Returns the page plus a per-page diagnostic dict the scorer aggregates (visual lines
    seen, dropped as chrome, carrying a margin number, and repaired line ends).
    """
    rows = cluster_lines(page)
    body_size = _dominant_size(rows)

    print_lines: list[Line] = []
    line_sizes: dict[int, tuple[float, LineGeom]] = {}
    ambiguous: set[int] = set()
    n_chrome = 0
    n_numbered = 0
    n_repaired = 0
    n_unnamed = 0

    for row in rows:
        ordered = sorted(row, key=lambda g: g[X0])
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
        content = m.group(2)
        print_lines.append(Line(line_number, content))

        # Geometry sidecar, keyed by margin line number exactly as production does, so a
        # duplicate number within a page is dropped as ambiguous rather than overwritten.
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
        else Line(
            ln.line_number,
            ln.text,
            line_sizes[ln.line_number][0],
            line_sizes[ln.line_number][1],
        )
        for ln in merged
    ]
    diag = {
        "visual_lines": len(rows),
        "chrome_lines": n_chrome,
        "numbered_lines": n_numbered,
        "ambiguous_numbers": len(ambiguous),
        "unnamed_glyphs": n_unnamed,
        "repaired_line_ends": n_repaired,
    }
    return Page(page.page_number, tuple(merged), tuple(print_lines), tuple(ranges)), diag


def reconstruct(pages: list[PdfPage], repaired: bool = False) -> tuple[list[Page], dict]:
    out: list[Page] = []
    agg = {
        "visual_lines": 0,
        "chrome_lines": 0,
        "numbered_lines": 0,
        "ambiguous_numbers": 0,
        "unnamed_glyphs": 0,
        "repaired_line_ends": 0,
    }
    for p in pages:
        page, diag = reconstruct_page(p, repaired=repaired)
        out.append(page)
        for k, v in diag.items():
            agg[k] += v
    return out, agg


def full_text(pages: list[Page]) -> str:
    """Whole-document text with cross-page soft hyphens rejoined, for text scoring."""
    return rejoin_soft_hyphens("\n".join(p.text for p in pages))
