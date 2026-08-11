"""H8 — is MuPDF's single-precision path the mechanism, or only a consistent pattern?

`h06` established that **every** PyMuPDF advance in the compared population is exactly
representable in float32, while only 2.6–16.3 % of PDFium's and pdfminer's are, and that
PyMuPDF's raw deltas against PDFium sit at about 1e-5. Phase 3 then wrote that
single-precision storage in MuPDF "is the entire residue".

That sentence claims a cause. What h06 measured is a pattern: all observed values are
float32-representable. A pattern of that strength is good evidence, and it is not the same
statement, so this probe tries to close the gap cheaply rather than leaving the stronger
wording unsupported.

TWO LINKS ARE NEEDED, and both are checkable without leaving PyMuPDF.

  1. **The code path.** `jm_trace_text_span` in the installed `pymupdf/__init__.py` builds
     the value `h06` reads:

         adv = fz_advance_glyph(span.font(), gid, wmode);  adv *= fsize
         char_orig = fz_transform_point(fz_make_point(items[i].x, items[i].y), ctm)
         x0 = char_orig.x;   x1 = x0 + adv
         char_bbox = fz_transform_rect(fz_make_rect(x0, y0, x1, y1), m1)

     so what reaches Python is `fz_rect.x1 - fz_point.x`: a difference of two values that
     have been stored in MuPDF geometry structs.

  2. **The storage width of those structs.** This is the link h06 could not speak to, and
     it is directly testable: push a double through `fz_make_point`, `fz_make_rect` and
     `fz_make_matrix` and read it back. If the value returns quantised to float32, the
     structs are single precision and the observed residue follows.

WHAT THIS DOES AND DOES NOT ESTABLISH. It establishes that the origin and the advance box
are **stored** in single precision before Python sees them, which accounts for a residue at
exactly the observed scale. It is not an end-to-end numerical proof that no other rounding
contributes anywhere in the pipeline, and the findings text says so.

NEGATIVE CONTROL. The same round trip is run through a value that IS exactly representable
in float32 (0.5). A struct that quantised everything would be indistinguishable from one
that quantised nothing if only exactly-representable inputs were tried, so the probe uses
both and asserts they behave differently.

Read-only. Writes JSON only under `validation/phase3/results/`.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _f32(v: float) -> float:
    return struct.unpack("f", struct.pack("f", v))[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=HERE / "results" / "h08_mupdf_precision_path.json")
    args = ap.parse_args()

    import pymupdf
    from pymupdf import mupdf

    # 0.1 is not representable in binary32; 0.5 is exactly representable in both widths.
    NOT_REPRESENTABLE = 0.1
    REPRESENTABLE = 0.5

    def probe(v: float) -> dict:
        pt = mupdf.fz_make_point(v, v)
        rect = mupdf.fz_make_rect(v, v, v, v)
        mat = mupdf.fz_make_matrix(v, 0.0, 0.0, v, v, v)
        return {
            "input_double": repr(v),
            "float32_of_input": repr(_f32(v)),
            "fz_point.x": repr(pt.x),
            "fz_rect.x0": repr(rect.x0),
            "fz_matrix.a": repr(mat.a),
            "point_equals_float32": pt.x == _f32(v),
            "rect_equals_float32": rect.x0 == _f32(v),
            "matrix_equals_float32": mat.a == _f32(v),
            "point_equals_input_double": pt.x == v,
        }

    quantised = probe(NOT_REPRESENTABLE)
    control = probe(REPRESENTABLE)

    # The control has to behave DIFFERENTLY, or the test cannot tell a single-precision
    # struct from a double one.
    discriminating = (not quantised["point_equals_input_double"]) and control["point_equals_input_double"]

    out = {
        "question": "are the MuPDF geometry structs that carry get_texttrace()'s origin and box single precision?",
        "versions": {
            "pymupdf": list(pymupdf.version),
            "mupdf_module": getattr(mupdf, "__file__", "(extension)"),
        },
        "code_path": (
            "jm_trace_text_span: adv = fz_advance_glyph(font, gid, wmode) * fsize; "
            "char_orig = fz_transform_point(fz_make_point(...), ctm); x1 = char_orig.x + adv; "
            "char_bbox = fz_transform_rect(fz_make_rect(x0, y0, x1, y1), m1). "
            "get_texttrace() returns char_orig and char_bbox, so the advance h06 reads is "
            "fz_rect.x1 - fz_point.x."
        ),
        "storage_round_trip": {
            "not_representable_in_float32_0.1": quantised,
            "NEGATIVE_CONTROL_representable_0.5": control,
            "test_is_discriminating": discriminating,
        },
        "verdict": None,
    }

    single = all(quantised[k] for k in ("point_equals_float32", "rect_equals_float32", "matrix_equals_float32"))
    out["verdict"] = (
        "MuPDF geometry structs are SINGLE PRECISION: a double pushed through fz_point, fz_rect and "
        "fz_matrix returns quantised to float32. Combined with the code path above, the origin and the "
        "advance box reach Python already rounded to binary32, which accounts for a residue at the "
        "observed ~1e-5 pt scale. This does not prove no other rounding contributes elsewhere."
        if single and discriminating
        else "INCONCLUSIVE -- do not carry the causal wording; narrow the prose to the observed pattern"
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
