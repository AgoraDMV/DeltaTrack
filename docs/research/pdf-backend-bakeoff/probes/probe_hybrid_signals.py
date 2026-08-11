"""Does the hybrid contract still carry every geometry/style signal DeltaTrack needs?

The hybrid stream adds characters that carry no geometry. That is a real cost and this
probe prices it, rather than letting the heading-recovery win stand in for the answer.

Three questions:

  S1  How much of the stream is generated, and is the "generated chars have no usable
      geometry" claim exactly true or merely mostly true? Reported as rates over every
      generated char, because a single generated char with a REAL box would mean the
      contract's `None` fields are throwing away information.

  S2  Do the signals the engine actually consumes survive? `glyph_size` (ADR 0012 heading
      levels) and `LineGeom` (the major detector's line-fullness split) are computed only
      from non-generated characters, so the test is whether enough non-generated
      characters remain on each printed line to compute them.

  S3  Does FONT ROLE separation survive? `docs/source-signal-inventory.md` records font
      name as the highest-value unadopted PDF signal -- margin line numbers are a
      different font from the body on 99.9% of numbered lines. Scored as role separation
      (margin vs body vs chrome), never as name-string equality, since names are
      print-class dependent. The empty-font-name rate is reported per stream because the
      inventory's guard depends on it.

Run:
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/probe_hybrid_signals.py \
      tests/corpus/114-hr-2029/4_reported-in-senate.pdf --limit 40
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(PROBES / "backends"), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pdfium_hybrid  # noqa: E402
import reconstruct_hybrid as RH  # noqa: E402
from contract_hybrid import CP, FONT, GEN, SIZE, X0, X1  # noqa: E402

_NUMBERED = re.compile(r"^(\d{1,2}) (.*)$")


def s1_generated(pages) -> dict:
    tot = gen = 0
    no_origin = real_box = non_identity_size = named_font = 0
    for pg in pages:
        for c in pg.chars:
            tot += 1
            if not c[GEN]:
                continue
            gen += 1
            if c[2] is None:  # baseline / origin
                no_origin += 1
            if c[X0] is not None and c[X1] is not None and c[X1] - c[X0] > 0:
                real_box += 1
            if c[SIZE] is not None:
                non_identity_size += 1
            if c[FONT]:
                named_font += 1
    return {
        "chars_total": tot,
        "chars_generated": gen,
        "generated_rate": round(gen / tot, 5) if tot else None,
        "generated_missing_origin": no_origin,
        "generated_with_real_box": real_box,
        "generated_with_size": non_identity_size,
        "generated_with_font_name": named_font,
        "claim_generated_carry_only_origin": (no_origin == 0 and real_box == 0 and non_identity_size == 0),
    }


def s2_signals(pages) -> dict:
    """Every numbered printed line must still yield a size and a full LineGeom."""
    lines = with_size = with_geom = 0
    for pg in pages:
        for row in RH.cluster_lines(pg):
            text = RH._line_text(row)
            m = _NUMBERED.match(text)
            if not m:
                continue
            lines += 1
            ink = [c for c in row if chr(c[CP]) not in ("\r", "\n")]
            content = ink[len(m.group(1)) :]
            printed = [c for c in content if c[CP] != 32 and c[X0] is not None]
            if printed and [c[SIZE] for c in printed if c[SIZE] is not None]:
                with_size += 1
            if printed and RH._first_word_right(content) is not None:
                with_geom += 1
    return {
        "numbered_lines": lines,
        "with_glyph_size": with_size,
        "with_line_geom": with_geom,
        "size_coverage": round(with_size / lines, 5) if lines else None,
        "geom_coverage": round(with_geom / lines, 5) if lines else None,
    }


def s3_font_roles(pages) -> dict:
    """Margin-number font vs body font, over numbered printed lines.

    Keyed on role, not on a literal name: the margin font is whatever font the margin
    digits are set in on this document, and the test is whether it DIFFERS from the font
    of the body text on the same line.
    """
    margin_fonts: Counter = Counter()
    body_fonts: Counter = Counter()
    separated = lines = 0
    empty_named = named_total = 0
    for pg in pages:
        for row in RH.cluster_lines(pg):
            text = RH._line_text(row)
            m = _NUMBERED.match(text)
            if not m:
                continue
            ink = [c for c in row if chr(c[CP]) not in ("\r", "\n")]
            n_margin = len(m.group(1))
            mf = {c[FONT] for c in ink[:n_margin] if not c[GEN]}
            bf = {c[FONT] for c in ink[n_margin:] if not c[GEN] and c[CP] != 32}
            for c in ink:
                if c[GEN]:
                    continue
                named_total += 1
                if not c[FONT]:
                    empty_named += 1
            if not mf or not bf:
                continue
            lines += 1
            margin_fonts.update(mf)
            body_fonts.update(bf)
            if not (mf & bf):
                separated += 1
    return {
        "numbered_lines_with_both": lines,
        "margin_font_differs_from_body": separated,
        "separation_rate": round(separated / lines, 5) if lines else None,
        "margin_fonts": margin_fonts.most_common(4),
        "body_fonts": body_fonts.most_common(4),
        "non_generated_chars": named_total,
        "non_generated_empty_font_name": empty_named,
        "empty_font_name_rate": round(empty_named / named_total, 6) if named_total else None,
    }


def s4_geometry_agreement(pdf: Path, limit: int | None) -> dict:
    """Do the sidecar VALUES agree with production's, not merely exist?

    S2 asks whether a `glyph_size` and a `LineGeom` could be computed. That is coverage,
    and coverage is compatible with computing the wrong number everywhere. The heading
    detector consumes these values directly -- `glyph_size` drives ADR 0012's size bands
    and `first_word_right` drives the major detector's stacked-vs-wrapped split -- so the
    stronger question is whether they match what production derives for the same line.

    Compared per (page, margin line number), which is the key production itself uses, over
    the lines both paths recovered. Tolerance is 0.05 pt: these are floats derived through
    different call paths, and an exact-equality test would report float noise as
    disagreement.
    """
    import reconstruct_hybrid as R

    from deltatrack.parsers.pdf_text import extract_clean_pages

    prod = extract_clean_pages(pdf)
    hy, _ = R.reconstruct(pdfium_hybrid.extract(pdf, limit)[0])
    if limit:
        prod = prod[:limit]

    def index(pages):
        out = {}
        for pg in pages:
            for ln in pg.lines:
                if ln.line_number is not None and ln.geom is not None:
                    out[(pg.page_number, ln.line_number)] = (ln.glyph_size, ln.geom)
        return out

    p, h = index(prod), index(hy)
    shared = p.keys() & h.keys()
    tol = 0.05
    size_ok = left_ok = right_ok = fwr_ok = 0
    samples = []
    for k in shared:
        (ps, pg_), (hs, hg) = p[k], h[k]
        if ps is not None and hs is not None and abs(ps - hs) <= tol:
            size_ok += 1
        if abs(pg_.content_left - hg.content_left) <= tol:
            left_ok += 1
        if abs(pg_.content_right - hg.content_right) <= tol:
            right_ok += 1
        if abs(pg_.first_word_right - hg.first_word_right) <= tol:
            fwr_ok += 1
        elif len(samples) < 4:
            samples.append(f"p{k[0]} L{k[1]}: production={pg_.first_word_right:.2f} hybrid={hg.first_word_right:.2f}")
    n = len(shared) or 1
    return {
        "lines_production": len(p),
        "lines_hybrid": len(h),
        "lines_shared": len(shared),
        "glyph_size_agree": round(size_ok / n, 5),
        "content_left_agree": round(left_ok / n, 5),
        "content_right_agree": round(right_ok / n, 5),
        "first_word_right_agree": round(fwr_ok / n, 5),
        "first_word_right_disagreements": samples,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    out = {}
    for path in args.pdfs:
        pages, summary = pdfium_hybrid.extract(Path(path), args.limit)
        entry = {
            "summary": summary,
            "S1": s1_generated(pages),
            "S2": s2_signals(pages),
            "S3": s3_font_roles(pages),
            "S4": s4_geometry_agreement(Path(path), args.limit),
        }
        out[path] = entry
        print(f"\n## {path}")
        s1, s2, s3 = entry["S1"], entry["S2"], entry["S3"]
        print(f"  S1 generated {s1['chars_generated']}/{s1['chars_total']} ({s1['generated_rate']:.1%})")
        print(
            f"     of those: missing origin={s1['generated_missing_origin']}  real box={s1['generated_with_real_box']}"
            f"  size={s1['generated_with_size']}  font name={s1['generated_with_font_name']}"
        )
        print(f"     'generated chars carry origin ONLY' holds exactly: {s1['claim_generated_carry_only_origin']}")
        print(f"  S2 numbered lines {s2['numbered_lines']}: size {s2['size_coverage']}, geom {s2['geom_coverage']}")
        print(f"  S3 margin/body font separation {s3['separation_rate']} over {s3['numbered_lines_with_both']} lines")
        print(f"     margin={s3['margin_fonts']}  body={s3['body_fonts']}")
        print(f"     empty font-name rate on real chars: {s3['empty_font_name_rate']}")
        s4 = entry["S4"]
        print(f"  S4 sidecar VALUES vs production over {s4['lines_shared']} shared numbered lines:")
        print(
            f"     glyph_size={s4['glyph_size_agree']}  content_left={s4['content_left_agree']}  "
            f"content_right={s4['content_right_agree']}  first_word_right={s4['first_word_right_agree']}"
        )
        for s in s4["first_word_right_disagreements"]:
            print(f"     disagreement {s}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, indent=1))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
