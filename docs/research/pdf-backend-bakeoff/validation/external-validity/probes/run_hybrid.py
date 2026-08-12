"""H's extraction and reconstruction, carrying source-glyph provenance. RESULT-BEARING.

    frozen rule        A21/A23 -- gid = (document_sha256, page_number, source_char_index);
                       the emitted line unit is one element of `Page.print_lines`
    executable here    `extract_with_gids` records PDFium's own char index beside every
                       character; `emitted_lines` carries it through clustering, chrome
                       rejection and margin-number stripping onto the emitted printed lines
    test               `x11_provenance_chain.py`
    evidence           `results/x11_provenance_chain.json`

WHY THIS IS A WRAPPER AND NOT AN EDIT TO THE ADAPTER. `probes/backends/pdfium_hybrid.py`,
`probes/contract_hybrid.py` and `probes/reconstruct_hybrid.py` are byte-pinned in
`validation/PRESERVED-MANIFEST.txt` under tag `pdf-bakeoff-prevalidation`, and every `.py`
in that manifest verifies clean. Those are the exact bytes that produced the prior spike's
confirmatory results. This module reproduces their behaviour EXACTLY and adds one field.

THE ANTI-DRIFT OBLIGATION. Instrumenting a frozen implementation means duplicating it, and
a duplicate drifts and then measures a different population while reporting agreement. Both
duplications here are gated by equality against the frozen original, in `x11`:

    chars   every field of every character, element by element, against
            `pdfium_hybrid.extract`
    lines   every emitted printed line's text, in order, against
            `reconstruct_hybrid.reconstruct_page(...).print_lines`

Neither gate may be removed. If either fails, this module is measuring something else.
"""

from __future__ import annotations

import ctypes
import math
import re
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
import pdfium_hybrid
import reconstruct_hybrid
from contract_hybrid import BASELINE, CP, GEN, SIZE, UPRIGHT, VBOX, X0, X1
from neutral_identity import SPACE, Cell, EmittedLine, SourceGlyph, cluster, eligible

_FONT_BUF = 256
_UPRIGHT_EPS = 1e-6
_SOFT_HYPHEN_CP = 0x00AD
_SOFT_HYPHEN = "­"
_NUMBERED_LINE = re.compile(r"^(\d{1,2}) (.*)$")


def extract_with_gids(pdf_path: Path, limit: int | None = None) -> list[tuple[int, list]]:
    """`pdfium_hybrid.extract`, with the PDFium char index recorded beside each record.

    A line-for-line mirror of the frozen adapter's per-character loop. It records `i` and
    changes no decision: the same characters are kept, rejected and flagged, with the same
    values.
    """
    doc = pdfium.PdfDocument(str(pdf_path))
    pages: list[tuple[int, list]] = []
    buf = (ctypes.c_char * _FONT_BUF)()
    flags = ctypes.c_int()
    try:
        n_pages = len(doc) if limit is None else min(limit, len(doc))
        for p in range(n_pages):
            page_obj = doc[p]
            textpage = page_obj.get_textpage()
            try:
                raw = textpage.raw
                n = pdfium_raw.FPDFText_CountChars(raw)
                out: list = []
                for i in range(max(n, 0)):
                    cp = pdfium_raw.FPDFText_GetUnicode(raw, i)
                    generated = pdfium_raw.FPDFText_IsGenerated(raw, i) == 1
                    hyphen = pdfium_raw.FPDFText_IsHyphen(raw, i) == 1
                    if hyphen:
                        cp = _SOFT_HYPHEN_CP
                    elif cp < 0x20 and not generated:
                        cp = 0xFFFD

                    ox, oy = ctypes.c_double(), ctypes.c_double()
                    has_origin = bool(pdfium_raw.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)))
                    left, right, bottom, top = (ctypes.c_double() for _ in range(4))
                    has_box = bool(
                        pdfium_raw.FPDFText_GetCharBox(
                            raw, i, ctypes.byref(left), ctypes.byref(right), ctypes.byref(bottom), ctypes.byref(top)
                        )
                    )
                    mat = pdfium_raw.FS_MATRIX()
                    has_matrix = bool(pdfium_raw.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)))

                    if generated:
                        out.append(
                            (
                                i,
                                (
                                    cp,
                                    True,
                                    oy.value if has_origin else None,
                                    ox.value if has_origin else None,
                                    None,
                                    None,
                                    None,
                                    "",
                                    True,
                                ),
                            )
                        )
                        continue
                    if not (has_box and has_matrix and has_origin):
                        continue
                    size = pdfium_raw.FPDFText_GetFontSize(raw, i) * math.sqrt(mat.a * mat.a + mat.b * mat.b)
                    nfont = pdfium_raw.FPDFText_GetFontInfo(raw, i, buf, _FONT_BUF, ctypes.byref(flags))
                    font = "" if nfont <= 0 else bytes(buf[: max(nfont - 1, 0)]).decode("utf-8", "replace")
                    out.append(
                        (
                            i,
                            (
                                cp,
                                False,
                                oy.value,
                                left.value,
                                right.value,
                                round(size, 4),
                                (bottom.value, top.value),
                                font,
                                abs(mat.b) < _UPRIGHT_EPS and mat.a > 0,
                            ),
                        )
                    )
            finally:
                textpage.close()
                page_obj.close()
            pages.append((p + 1, out))
    finally:
        doc.close()
    return pages


def _cells_for_row(row: list[tuple[int, tuple]]) -> list[tuple[int | None, str]]:
    """`reconstruct_hybrid._line_text`, cell by cell, so each character keeps its gid.

    Mirrors the frozen transformation exactly: drop CR/LF, render the soft hyphen as an
    ASCII hyphen, collapse each run of spaces to its FIRST cell, then strip the ends.
    """
    cells: list[Cell] = []
    for gid, c in row:
        ch = chr(c[CP])
        if ch in ("\r", "\n"):
            continue
        # A24.2: PROVENANCE is always recorded; NEUTRAL IDENTITY only for real ink. A
        # content-stream space keeps its `sci` and loses its `ngid`, which is exactly the
        # state the old single-`gid` representation could not express.
        neutral = None if (c[GEN] or c[CP] == SPACE) else gid
        cells.append(Cell(ngid=neutral, char="-" if ch == _SOFT_HYPHEN else ch, sci=gid, generated=bool(c[GEN])))
    collapsed: list[Cell] = []
    for cell in cells:
        if cell.char == " " and collapsed and collapsed[-1].char == " ":
            continue
        collapsed.append(cell)
    while collapsed and collapsed[0].char == " ":
        collapsed.pop(0)
    while collapsed and collapsed[-1].char == " ":
        collapsed.pop()
    return collapsed


def emitted_lines(page_number: int, chars_with_gids: list[tuple[int, tuple]]) -> list[EmittedLine]:
    """H's EMITTED PRINTED LINES, carrying source-glyph provenance.

    The unit is one element of `Page.print_lines` -- production documents it as "one entry
    per line the GPO actually printed". `Page.lines` is NOT the unit: it is the later
    `_merge_print_lines` soft-hyphen recombination, shared by both arms, spanning several
    physical lines by design.
    """
    kept = [
        (pos, gid, c)
        for pos, (gid, c) in enumerate(chars_with_gids)
        if c[BASELINE] is not None
        and (c[GEN] or (c[SIZE] is not None and c[SIZE] > reconstruct_hybrid._SIZE_FLOOR and c[UPRIGHT]))
    ]
    if not kept:
        return []
    rows: list[list] = []
    current: list = []
    anchor: float | None = None
    for item in sorted(kept, key=lambda t: (-t[2][BASELINE], t[0])):
        c = item[2]
        if anchor is None or abs(c[BASELINE] - anchor) <= reconstruct_hybrid._BASELINE_TOL:
            current.append(item)
            if anchor is None:
                anchor = c[BASELINE]
        else:
            rows.append(current)
            current = [item]
            anchor = c[BASELINE]
    if current:
        rows.append(current)
    rows = [sorted(row, key=lambda t: t[0]) for row in rows]

    body_size = reconstruct_hybrid._dominant_size([[c for _p, _g, c in row] for row in rows])
    out: list[EmittedLine] = []
    for row in rows:
        pairs = [(g, c) for _p, g, c in row]
        cells = _cells_for_row(pairs)
        text = "".join(c.char for c in cells)
        if reconstruct_hybrid.is_chrome(text, [c for _g, c in pairs], body_size):
            continue
        m = _NUMBERED_LINE.match(text)
        if m:
            cells = cells[len(m.group(1)) + 1 :]
        out.append(EmittedLine(cells=cells, lid=(page_number, len(out))))
    return out


def neutral_skeleton(page_number: int, chars_with_gids: list[tuple[int, tuple]]):
    """The neutral ink-line skeleton for one page, from facts BOTH arms share.

    Eligibility is `neutral_identity.eligible` and nothing else -- ONE function, called
    from here and from the X arm's runner, so the skeleton cannot diverge between arms and
    an amendment to eligibility is a one-line change in one place.

    A24.2: eligibility now also excludes U+0020 by codepoint. `x12` measured that PDFium
    reports a positive-area box for a real space -- about 3.6 pt wide and 0.014 pt tall
    against 7.9 pt for a capital -- so "positive area" cannot express the ink/non-ink
    distinction on its own, and the skeleton was admitting every word space.
    """
    glyphs = []
    for gid, c in chars_with_gids:
        box = None if c[X0] is None or c[X1] is None or c[VBOX] is None else (c[X0], c[VBOX][0], c[X1], c[VBOX][1])
        g = None if c[GEN] else gid
        if eligible(g, box, bool(c[UPRIGHT]), c[CP]):
            glyphs.append(SourceGlyph(gid, c[BASELINE], box[0], box[1], box[2], box[3]))
    return cluster(glyphs, page_number)


def run(pdf_path: Path, limit: int | None = None) -> list[dict]:
    """Per page: the neutral skeleton, H's emitted printed lines, and production's Page.

    ADDITIVE ONLY. `page` is appended so the harness can reach `Page.print_lines` and, through
    it, production anchors -- the anchor-to-neutral bridge x14 proves. Every pre-existing key
    is unchanged, and the `Page` is built by the FROZEN `reconstruct_hybrid` from the FROZEN
    adapter, never from this wrapper's copy of either.

    ANTI-DRIFT: the bridge is only sound while `page.print_lines` and `emitted` correspond
    index-for-index. `x14` asserts that over EVERY page it consumes, not one example page.
    """
    out = []
    frozen_pages, _ = pdfium_hybrid.extract(pdf_path, limit=limit)
    by_page = {pg.page_number: pg for pg in frozen_pages}
    for pno, chars in extract_with_gids(pdf_path, limit=limit):
        page_obj, _diag = reconstruct_hybrid.reconstruct_page(by_page[pno])
        out.append(
            {
                "page_number": pno,
                "chars": chars,
                "emitted": emitted_lines(pno, chars),
                "neutral": neutral_skeleton(pno, chars),
                "page": page_obj,
            }
        )
    return out
