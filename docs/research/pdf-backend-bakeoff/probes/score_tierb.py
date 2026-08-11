"""Tier B (partial): robustness on non-canonical documents with NO XML reference.

WHAT THIS IS, AND WHAT IT IS NOT. The spec's Tier B asks for pre-publication material --
committee prints, chair's marks, discussion drafts. **The repository contains none, and
this probe does not manufacture any.** What it covers is the nearest available material:

  * `tests/data/CRPT-118srpt198.pdf`   a watermarked COMMITTEE REPORT, a genuinely
                                       different document class from a bill
  * `tests/data/BILLS-118s4795rs.pdf`  a watermarked Senate bill
  * `tests/data/subcommittee/*.pdf`    nine GPO-published House-reported prints, which
                                       the spec correctly classifies as additional TIER A
                                       print-class variety rather than Tier B

So this closes the spec's explicit request to include the watermarked Senate document and
the committee report, and it widens print-class coverage. It does NOT close the Tier B
gap, and the results must not be read as if it did.

THE METRIC. There is no XML for any of these, so PDF-vs-XML is unavailable. The measure
is backend-vs-incumbent through the identical downstream pipeline, which is the same
structure-free instrument Phase 2 calls T4: the entire pipeline is held fixed and only
the glyph source varies, so any difference is attributable to the backend and needs no
adjudication.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_tierb.py \
       --out docs/research/pdf-backend-bakeoff/results/tierb.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from contract import ALL_BACKENDS, run_backend  # noqa: E402
from reconstruct import reconstruct  # noqa: E402

from deltatrack.parsers.pdf_anchors import breadcrumb_for, extract_anchors  # noqa: E402

INCUMBENT = "pdfium-native"


def documents() -> list[Path]:
    out = [REPO / "tests/data/CRPT-118srpt198.pdf", REPO / "tests/data/BILLS-118s4795rs.pdf"]
    out += sorted((REPO / "tests/data/subcommittee").glob("*.pdf"))
    return [p for p in out if p.exists()]


def profile(pdf: Path, backend: str) -> dict:
    t0 = time.perf_counter()
    raw, summary = run_backend(backend, pdf)
    extract_s = time.perf_counter() - t0
    pages, diag = reconstruct(raw, repaired=True)
    anchors = extract_anchors(pages)
    return {
        "extract_s": round(extract_s, 3),
        "n_pages": len(pages),
        "reconstruction": diag,
        "text": "\n".join(p.text for p in pages),
        "line_numbers": sorted(
            (p.page_number, ln.line_number) for p in pages for ln in p.print_lines if ln.line_number is not None
        ),
        "n_anchors": len(anchors),
        "anchor_kinds": dict(Counter(a.kind for a in anchors)),
        "breadcrumbs": [tuple(breadcrumb_for(a, anchors)) for a in anchors],
        "glyphs": summary.get("glyphs"),
        "undecodable_glyphs": summary.get("undecodable_glyphs", 0),
    }


def compare(ref: dict, cand: dict) -> dict:
    rl, cl = set(ref["line_numbers"]), set(cand["line_numbers"])
    rb, cb = Counter(ref["breadcrumbs"]), Counter(cand["breadcrumbs"])
    return {
        "text_identical": ref["text"] == cand["text"],
        "line_numbers_identical": rl == cl,
        "line_number_recall": round(len(rl & cl) / len(rl), 5) if rl else None,
        "anchors_ref": ref["n_anchors"],
        "anchors_cand": cand["n_anchors"],
        "breadcrumb_agreement": (round(sum((rb & cb).values()) / sum(rb.values()), 5) if sum(rb.values()) else None),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    docs = documents()
    print(f"{len(docs)} non-corpus documents x {len(ALL_BACKENDS)} backends", file=sys.stderr)
    out: dict = {"documents": {}, "n_documents": len(docs), "note": __doc__.split("\n\n")[1]}
    args.out.parent.mkdir(parents=True, exist_ok=True)

    for i, pdf in enumerate(docs, 1):
        key = pdf.relative_to(REPO).as_posix()
        out["documents"][key] = {}
        ref = None
        for backend in [INCUMBENT] + [b for b in ALL_BACKENDS if b != INCUMBENT]:
            try:
                prof = profile(pdf, backend)
                if backend == INCUMBENT:
                    ref = prof
                entry = {k: v for k, v in prof.items() if k not in ("text", "line_numbers", "breadcrumbs")}
                entry["vs_incumbent"] = None if backend == INCUMBENT else compare(ref, prof)
                out["documents"][key][backend] = entry
                note = (
                    f"pages={prof['n_pages']} anchors={prof['n_anchors']}"
                    if backend == INCUMBENT
                    else f"text_identical={entry['vs_incumbent']['text_identical']} "
                    f"crumbs={entry['vs_incumbent']['breadcrumb_agreement']}"
                )
            except Exception as exc:
                out["documents"][key][backend] = {"error": f"{type(exc).__name__}: {exc}"}
                out["documents"][key][backend]["traceback"] = traceback.format_exc()[-800:]
                note = "ERROR"
            print(f"  [{i}/{len(docs)}] {key:<44} {backend:<14} {note}", file=sys.stderr)
        args.out.write_text(json.dumps(out, indent=1, default=str))

    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
