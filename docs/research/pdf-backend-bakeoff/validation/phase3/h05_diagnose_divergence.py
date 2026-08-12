"""H5 — diagnose the two divergences H3/H4 exposed, without tuning anything.

H4 found ONE word-boundary disagreement in 195,291 cross-engine pairs, and H4's own N8
control found something the pair test could not see: the three engines do not put the same
number of characters into the contract at all. Both are followed to a cause here. Neither
is repaired in place; the diagnosis names which of the review's four categories it is and
what a fix would have to change.

    D1  CONTRACT INSUFFICIENCY -- `font_size` has no defined axis
    D2  ADAPTER BUG -- `pdfium_extended.py` emits PDFium's GENERATED spaces

D1, stated before it is measured. `reconstruct_extended.wants_space` normalises each
advance into 1/1000 em by dividing by `font_size`, and `_normalize_threshold` then buckets
that em value at 400/700/800. So `font_size` does not scale the answer smoothly -- it
selects a divisor. The three engines define it on different axes:

    PDFium    FPDFText_GetFontSize x sqrt(a^2 + b^2)     the HORIZONTAL (advance) scale
    PyMuPDF   |transform_vector((1,0), trm x ctm)|       the HORIZONTAL scale
    pdfminer  LTChar.size = the transformed box HEIGHT    the VERTICAL scale

On isotropic type those are the same number and nothing separates them. GPO condenses
display type -- a text matrix of (12, 0, 0, 13) is real on this corpus -- and there the two
axes differ by 8 %, which is enough to move an advance across a bucket boundary.

This is not an adapter bug: every adapter reports its own engine's own documented size.
It is the CONTRACT that is underspecified, and the ported rule is what makes the
underspecification load-bearing. The shipped `_SPACE_FACTOR x size` rule tolerated it
because it scaled smoothly.

D2, stated before it is measured. `pdfium_extended.py`'s docstring says it

    "never asks whether a character was generated, and never consumes a space the engine
     decided to insert"

The first half is true. The second is not: not asking is not the same as not consuming.
PDFium's text page contains generated space characters, the adapter copies every character
including those, and `reconstruct_extended._line_text` emits `chr(32)` for each one before
the geometric rule ever runs. So on the reconstruction path -- which is what `g05` and
`g06` scored -- the extended design inherits PDFium's word-boundary decision for every
generated space. `g04` is unaffected: it scores ink pairs directly and never walks a space.

THE CORRECTED CONTRACT tested here: a space carries no ink, so no space belongs in a
contract of "marks on the page". `--strict` drops every U+0020 from every backend and lets
the rule decide all boundaries. That is the design the phase-2 docstring describes.

NEGATIVE CONTROLS.

  N9   D1's proposed fix is DERIVED FROM PDFMINER'S OWN API (size x |matrix[0]| /
       |matrix[3]|), not copied from PDFium. It is measured, not applied to phase 2.
  N10  the strict (space-free) run is checked for the failure it could cause -- words
       welded together where an explicit stream space was the only separator. If the
       geometric rule cannot recover those, the strict contract is worse and must say so.
  N11  every table reports the contaminated and the corrected number side by side. No
       phase-2 figure is overwritten.

Read-only. Writes JSON only under `validation/phase3/results/`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
P2 = HERE.parents[0] / "phase2"
PROBES = REPO / "docs/research/pdf-backend-bakeoff/probes"
for _p in (str(HERE), str(P2), str(PROBES), str(PROBES / "backends"), str(REPO / "src"), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pdfium_extended  # noqa: E402
import pdfminer_extended  # noqa: E402
import pymupdf_extended  # noqa: E402
import reconstruct_extended as RE  # noqa: E402
from contract_extended import BASELINE, CP, ORIGIN_X, SIZE, UPRIGHT, ExtPdfPage  # noqa: E402
from probe_failure_headings import CORRUPT, DEFAULT_DOCS, TARGETS, occurrences  # noqa: E402
from probe_failure_headings import pages_for as pages_for_original  # noqa: E402

DOCUMENTS = [
    "tests/corpus/114-hr-2029/4_reported-in-senate.pdf",
    "tests/corpus/118-hr-4366/5_engrossed-amendment-house.pdf",
    "tests/corpus/116-hr-1865/6_enrolled-bill.pdf",
    "tests/corpus/118-s-4795/1_reported-in-senate.pdf",
    "tests/data/CRPT-118srpt198.pdf",
]
PAGES = 24
ORIGIN_TOL = 0.05
BASELINE_TOL = 0.6
BACKENDS = ("pdfium", "pdfminer", "pymupdf")


def _extract(backend: str, path: Path, pages: list[int]):
    if backend == "pdfium":
        out, _ = pdfium_extended.extract(path, limit=max(pages))
        return [p for p in out if p.page_number in pages]
    if backend == "pdfminer":
        return pdfminer_extended.extract(path, pages=pages)[0]
    if backend == "pymupdf":
        return pymupdf_extended.extract(path, pages=pages)[0]
    raise ValueError(backend)


def _drop_spaces(page: ExtPdfPage) -> ExtPdfPage:
    return ExtPdfPage(page.page_number, page.width, page.height, [g for g in page.glyphs if g[CP] != 32])


def _pairs(page: ExtPdfPage) -> dict[tuple, tuple]:
    rows: dict[int, list] = defaultdict(list)
    for g in page.glyphs:
        if not g[UPRIGHT] or g[CP] in (32, 10, 13):
            continue
        rows[round(g[BASELINE] / BASELINE_TOL)].append(g)
    out = {}
    for row in rows.values():
        row.sort(key=lambda g: g[ORIGIN_X])
        for a, b in zip(row, row[1:]):
            out[(a[CP], round(a[ORIGIN_X] / ORIGIN_TOL), round(a[BASELINE] / BASELINE_TOL))] = (a, b)
    return out


# ------------------------------------------------------------------------------- D1


def _pdfminer_axis_corrected(path: Path, pages: list[int]) -> dict[tuple, float]:
    """pdfminer's HORIZONTAL type scale, derived from pdfminer's own matrix.

    N9: `LTChar.size` is the transformed box height, i.e. `fontsize x |matrix[3]|`. The
    advance axis is `fontsize x |matrix[0]|`. Both matrix entries are on the object, so
    the correction never leaves pdfminer.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar

    def walk(o):
        for c in getattr(o, "_objs", []):
            yield c
            yield from walk(c)

    out: dict[tuple, float] = {}
    for idx, layout in enumerate(extract_pages(str(path), laparams=None, page_numbers=[p - 1 for p in pages])):
        pno = pages[idx]
        for o in walk(layout):
            if not isinstance(o, LTChar):
                continue
            a, _b, _c, d, _e, f = o.matrix
            if not d:
                continue
            key = (pno, round(o.x0 / ORIGIN_TOL), round(round(f, 4) / BASELINE_TOL))
            out[key] = o.size * abs(a) / abs(d)
    return out


def diagnose_d1(rel: str, pages: list[int], glyphs: dict[str, list[ExtPdfPage]]) -> dict:
    corrected = _pdfminer_axis_corrected(REPO / rel, pages)
    by_page = {b: {p.page_number: p for p in glyphs[b]} for b in BACKENDS}

    anis = Counter()
    size_disagree = Counter()
    fixed = Counter()
    examples = []
    for pno in pages:
        pf = _pairs(by_page["pdfium"][pno])
        pm = _pairs(by_page["pdfminer"][pno])
        for k, (a_f, b_f) in pf.items():
            hit = pm.get(k)
            if hit is None:
                continue
            a_m, b_m = hit
            if b_m[CP] != b_f[CP]:
                continue
            anis["compared"] += 1
            if abs(a_m[SIZE] - a_f[SIZE]) > 0.01 or abs(b_m[SIZE] - b_f[SIZE]) > 0.01:
                anis["size_differs"] += 1
            d_f = RE.wants_space(a_f, b_f)
            d_m = RE.wants_space(a_m, b_m)
            if d_f != d_m:
                size_disagree["as_built"] += 1
                # rebuild pdfminer's glyphs with the axis-corrected size
                ca = corrected.get((pno, round(a_m[ORIGIN_X] / ORIGIN_TOL), round(a_m[BASELINE] / BASELINE_TOL)))
                cb = corrected.get((pno, round(b_m[ORIGIN_X] / ORIGIN_TOL), round(b_m[BASELINE] / BASELINE_TOL)))
                if ca and cb:
                    a2 = tuple(ca if i == SIZE else v for i, v in enumerate(a_m))
                    b2 = tuple(cb if i == SIZE else v for i, v in enumerate(b_m))
                    if RE.wants_space(a2, b2) == d_f:
                        fixed["resolved_by_axis_correction"] += 1
                    else:
                        fixed["still_disagrees"] += 1
                else:
                    fixed["correction_unavailable"] += 1
                if len(examples) < 10:
                    examples.append(
                        {
                            "page": pno,
                            "chars": f"{chr(a_f[CP])}|{chr(b_f[CP])}",
                            "pdfium_size": (a_f[SIZE], b_f[SIZE]),
                            "pdfminer_size": (a_m[SIZE], b_m[SIZE]),
                            "pdfminer_size_axis_corrected": (ca, cb),
                            "pdfium_says": d_f,
                            "pdfminer_says": d_m,
                        }
                    )
    # D1 closed at the OUTPUT, not only at the pair: rebuild every pdfminer glyph with the
    # axis-corrected size and compare the reconstructed text with PDFium's. A pair-level
    # fix that did not reach the text would not be a fix.
    fixed_pages = []
    for pno in pages:
        pg = by_page["pdfminer"][pno]
        rebuilt = []
        for g in pg.glyphs:
            c = corrected.get((pno, round(g[ORIGIN_X] / ORIGIN_TOL), round(g[BASELINE] / BASELINE_TOL)))
            rebuilt.append(g if c is None else tuple(c if i == SIZE else v for i, v in enumerate(g)))
        fixed_pages.append(ExtPdfPage(pno, pg.width, pg.height, rebuilt))
    t_fixed = RE.full_text(RE.reconstruct(fixed_pages, repaired=True)[0])
    t_pdfium = RE.full_text(RE.reconstruct([by_page["pdfium"][p] for p in pages], repaired=True)[0])
    t_asbuilt = RE.full_text(RE.reconstruct([by_page["pdfminer"][p] for p in pages], repaired=True)[0])

    return {
        "pairs_compared": anis["compared"],
        "pairs_where_font_size_differs_between_engines": anis["size_differs"],
        "boundary_disagreements_as_built": size_disagree["as_built"],
        "N9_after_axis_correction": dict(fixed),
        "text_identical_to_pdfium": {"as_built": t_asbuilt == t_pdfium, "axis_corrected": t_fixed == t_pdfium},
        "examples": examples,
    }


# ------------------------------------------------------------------------------- D2


def diagnose_d2(rel: str, pages: list[int], glyphs: dict[str, list[ExtPdfPage]]) -> dict:
    counts = {b: Counter() for b in BACKENDS}
    for b in BACKENDS:
        for p in glyphs[b]:
            counts[b]["glyphs"] += len(p.glyphs)
            counts[b]["space_glyphs"] += sum(1 for g in p.glyphs if g[CP] == 32)

    # How many of PDFium's spaces did the ENGINE invent? Asked of PDFium's own flag, used
    # here only as a diagnostic -- the extended design must not consume it.
    import ctypes  # noqa: F401

    import pypdfium2 as pdfium
    import pypdfium2.raw as R

    doc = pdfium.PdfDocument(str(REPO / rel))
    gen = exp = 0
    try:
        for pno in pages:
            pg = doc[pno - 1]
            tp = pg.get_textpage()
            raw = tp.raw
            for i in range(max(R.FPDFText_CountChars(raw), 0)):
                if R.FPDFText_GetUnicode(raw, i) == 32:
                    if R.FPDFText_IsGenerated(raw, i) == 1:
                        gen += 1
                    else:
                        exp += 1
            tp.close()
            pg.close()
    finally:
        doc.close()

    # The corrected contract: no spaces anywhere, all boundaries decided by the rule.
    texts_loose, texts_strict = {}, {}
    for b in BACKENDS:
        loose, _ = RE.reconstruct(glyphs[b], repaired=True)
        strict, _ = RE.reconstruct([_drop_spaces(p) for p in glyphs[b]], repaired=True)
        texts_loose[b] = RE.full_text(loose)
        texts_strict[b] = RE.full_text(strict)

    def f1(x: str, y: str) -> float | None:
        tx, ty = x.split(), y.split()
        common = Counter(tx) & Counter(ty)
        n = sum(common.values())
        return round(2 * n / (len(tx) + len(ty)), 6) if (tx or ty) else None

    # N10: does dropping stream spaces WELD words together? Measured as the change in
    # token count against the loose run of the same engine.
    weld = {
        b: {
            "tokens_loose": len(texts_loose[b].split()),
            "tokens_strict": len(texts_strict[b].split()),
            "delta": len(texts_strict[b].split()) - len(texts_loose[b].split()),
        }
        for b in BACKENDS
    }

    return {
        "glyphs": {b: counts[b]["glyphs"] for b in BACKENDS},
        "space_glyphs_in_the_contract": {b: counts[b]["space_glyphs"] for b in BACKENDS},
        "pdfium_spaces_by_provenance": {"generated_by_the_engine": gen, "explicit_in_the_stream": exp},
        "cross_engine_text": {
            "loose_as_phase2_built_it": {
                "pdfium_vs_pdfminer_token_f1": f1(texts_loose["pdfium"], texts_loose["pdfminer"]),
                "pdfium_vs_pymupdf_token_f1": f1(texts_loose["pdfium"], texts_loose["pymupdf"]),
                "pdfminer_vs_pymupdf_identical": texts_loose["pdfminer"] == texts_loose["pymupdf"],
            },
            "strict_no_space_glyphs": {
                "pdfium_vs_pdfminer_token_f1": f1(texts_strict["pdfium"], texts_strict["pdfminer"]),
                "pdfium_vs_pymupdf_token_f1": f1(texts_strict["pdfium"], texts_strict["pymupdf"]),
                "pdfium_vs_pdfminer_identical": texts_strict["pdfium"] == texts_strict["pdfminer"],
                "pdfium_vs_pymupdf_identical": texts_strict["pdfium"] == texts_strict["pymupdf"],
                "pdfminer_vs_pymupdf_identical": texts_strict["pdfminer"] == texts_strict["pymupdf"],
            },
        },
        "N10_word_welding": weld,
    }


# --------------------------------------------------- the four named heading failure cases


def heading_cases(strict: bool) -> dict:
    totals: dict[str, dict[str, int]] = {}
    per_doc: dict = {}
    paths = ["production", "glyph", "hybrid", "extended", "extended_strict", "pdfminer"]
    for p in paths:
        totals[p] = {"correct": 0, "corrupted": 0}

    def pages_for(path: str, pdf: Path):
        if path in ("extended", "extended_strict"):
            raw, _ = pdfium_extended.extract(pdf)
            if path == "extended_strict":
                raw = [_drop_spaces(p) for p in raw]
            return RE.reconstruct(raw, repaired=True)[0]
        return pages_for_original(path, pdf)

    for doc in DEFAULT_DOCS:
        pdf = REPO / "tests" / "corpus" / f"{doc}.pdf"
        if not pdf.exists():
            continue
        page_sets = {}
        for path in paths:
            try:
                page_sets[path] = pages_for(path, pdf)
            except Exception as exc:  # noqa: BLE001
                print(f"  {doc} {path} FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        d: dict = {}
        for target in TARGETS:
            for path in paths:
                if path not in page_sets:
                    continue
                o = occurrences(page_sets[path], target, CORRUPT[target])
                d.setdefault(target, {})[path] = o
                totals[path]["correct"] += o["correct"]
                totals[path]["corrupted"] += o["corrupted"]
        per_doc[doc] = d
        print(
            f"  {doc:<32} "
            + "  ".join(
                f"{p}={d[TARGETS[0]][p]['correct']}/{d[TARGETS[0]][p]['corrupted']}" for p in paths if p in page_sets
            )
        )
    return {"totals": totals, "per_document": per_doc}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=PAGES)
    ap.add_argument("--skip-headings", action="store_true")
    ap.add_argument("--out", type=Path, default=HERE / "results" / "h05_divergence_diagnosis.json")
    args = ap.parse_args()

    out: dict = {"D1_font_size_axis": {}, "D2_generated_space_contamination": {}}
    pages = list(range(1, args.pages + 1))

    for rel in DOCUMENTS:
        path = REPO / rel
        if not path.exists():
            print(f"  MISSING {rel}")
            continue
        print(f"\n=== {rel}")
        glyphs = {b: _extract(b, path, pages) for b in BACKENDS}

        d1 = diagnose_d1(rel, pages, glyphs)
        out["D1_font_size_axis"][rel] = d1
        print(
            f"  D1  {d1['pairs_where_font_size_differs_between_engines']}/{d1['pairs_compared']} pairs where"
            f" font_size differs;  {d1['boundary_disagreements_as_built']} boundary disagreements"
            f"  -> after axis correction {d1['N9_after_axis_correction']}"
        )
        print(f"      text identical to pdfium: {d1['text_identical_to_pdfium']}")

        d2 = diagnose_d2(rel, pages, glyphs)
        out["D2_generated_space_contamination"][rel] = d2
        print(
            f"  D2  space glyphs in the contract: {d2['space_glyphs_in_the_contract']}"
            f"   pdfium provenance {d2['pdfium_spaces_by_provenance']}"
        )
        print(f"      loose  {d2['cross_engine_text']['loose_as_phase2_built_it']}")
        print(f"      strict {d2['cross_engine_text']['strict_no_space_glyphs']}")
        print(f"      N10 welding {d2['N10_word_welding']}")

    if not args.skip_headings:
        print("\n=== the four named heading failure cases, loose vs strict")
        out["heading_failure_cases"] = heading_cases(strict=True)
        print("\n  totals:")
        for p, t in out["heading_failure_cases"]["totals"].items():
            print(f"    {p:<18} {t['correct']:>4} ok  {t['corrupted']:>4} bad")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
