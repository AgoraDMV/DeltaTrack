"""X's extraction and reconstruction, carrying source-glyph provenance. RESULT-BEARING.

    frozen rule        A19 -- the neutral skeleton reads facts BOTH arms share and must be
                       IDENTICAL under either; A21/A23 -- gid is the PDFium char index
    executable here    `run` returns, per page, the same neutral skeleton `run_hybrid`
                       returns plus X's emitted printed lines
    test               `x13_x_arm.py`
    evidence           `results/x13_x_arm.json`

THE SKELETON IS NOT BUILT FROM X'S CONTRACT, and that is deliberate. X drops every U+0020
(X-2), so a skeleton derived from X's glyphs would be missing every content-stream space
that PDFium reports with a positive-area box, and would therefore NOT equal the skeleton
H derives. A19 requires one skeleton, identical under both arms. So both runners call
`run_hybrid.neutral_skeleton`, which reads geometry only -- ink box, baseline, upright --
through the single `neutral_identity.eligible` function, and consults no arm's contract.
`x13` asserts the two runners produce identical skeletons rather than assuming it.
"""

from __future__ import annotations

from pathlib import Path

import pdfium_extended_corrected
import reconstruct_extended_corrected
import run_hybrid


def run(pdf_path: Path, limit: int | None = None) -> list[dict]:
    """Per page: the neutral skeleton, X's emitted printed lines, and production's Page."""
    pages, summary = pdfium_extended_corrected.extract(pdf_path, limit=limit)
    hybrid_pages = run_hybrid.extract_with_gids(pdf_path, limit=limit)
    by_page = {pno: chars for pno, chars in hybrid_pages}

    out = []
    for pg in pages:
        page_obj, emitted, diag = reconstruct_extended_corrected.reconstruct_page(pg)
        out.append(
            {
                "page_number": pg.page_number,
                "emitted": emitted,
                "page": page_obj,
                "neutral": run_hybrid.neutral_skeleton(pg.page_number, by_page.get(pg.page_number, [])),
                "diag": diag,
            }
        )
    return out, summary
