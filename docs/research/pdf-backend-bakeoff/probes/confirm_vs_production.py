"""What Concern A does NOT certify: agreement with PRODUCTION, not with the harness incumbent.

Concern A's reference is native pypdfium2 through the neutral glyph layer. That answers
"does the WASM build match the native build through the same seam?" -- and it is the right
reference for a backend swap. It does NOT answer "does the proposed glyph architecture
match what production returns today", because production does not use the glyph path at
all: `parsers/pdf_text.py` reads PDFium's TEXT API.

Those two are not the same, and the difference is not small. On 114-hr-2029/4 production
recovers 60 heading anchors; pdfminer through the glyph layer recovers the same 60 exactly,
while both PDFium builds recover 75 of which 17 are malformed -- FAMILYHOUSING, NAVYAND,
ARMYNATIONAL -- because the layer's word-space rule loses the space at GPO small-caps
boundaries. Production's text API does not lose it.

So a migration to the glyph architecture carrying PDFium would reproduce the harness
incumbent exactly and REGRESS against production on heading labels, and the exploratory
calibration gate could not have seen it: it compared anchor COUNTS, and the counts are not
what differ.

This probe quantifies that across the production-accepted corpus.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/confirm_vs_production.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import confirm_metrics as M  # noqa: E402
from contract import run_backend  # noqa: E402
from reconstruct import reconstruct  # noqa: E402
from score_phase1 import corpus_documents  # noqa: E402

from deltatrack.compare.pdf import _is_unnumbered_layout  # noqa: E402
from deltatrack.parsers.pdf_anchors import extract_anchors  # noqa: E402
from deltatrack.parsers.pdf_text import extract_clean_pages  # noqa: E402

BACKENDS = ("pdfium-native", "pdfium-wasm", "pdfminer")


def labels(pages) -> set[str]:
    return {M.norm_label(a.text) for a in extract_anchors(pages) if a.kind in M.PDF_HEADING_KINDS and a.text}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out", type=Path, default=REPO / "docs/research/pdf-backend-bakeoff/results/confirm_vs_production.json"
    )
    ap.add_argument("--limit-docs", type=int, default=None)
    args = ap.parse_args()

    docs = corpus_documents()
    if args.limit_docs:
        docs = docs[: args.limit_docs]

    rows = []
    for i, (bill, version, pdf, _xml) in enumerate(docs, 1):
        key = f"{bill}/{version}"
        try:
            prod = labels(extract_clean_pages(pdf))
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i}/{len(docs)}] {key} production ERROR {exc}", file=sys.stderr)
            continue
        entry = {"doc": key, "production_anchors": len(prod), "backends": {}}
        accepted = None
        for b in BACKENDS:
            try:
                raw, _ = run_backend(b, pdf)
                pages, _ = reconstruct(raw, repaired=True)
                if accepted is None:
                    accepted = not _is_unnumbered_layout(pages)
                got = labels(pages)
                entry["backends"][b] = {
                    "anchors": len(got),
                    "match_production": len(got & prod),
                    "absent_from_production": len(got - prod),
                    "missed_from_production": len(prod - got),
                    "exact_set_match": got == prod,
                    "sample_absent": sorted(got - prod)[:3],
                }
            except Exception as exc:  # noqa: BLE001
                entry["backends"][b] = {"error": f"{type(exc).__name__}: {exc}"}
        entry["production_accepted"] = accepted
        rows.append(entry)
        marks = " ".join(
            f"{b.split('-')[-1]}={entry['backends'][b].get('absent_from_production', '?')}" for b in BACKENDS
        )
        print(f"  [{i}/{len(docs)}] {key:<26} prod={len(prod):4}  spurious: {marks}", file=sys.stderr)

    acc = [r for r in rows if r["production_accepted"] and r["production_anchors"] > 0]
    summary = {}
    for b in BACKENDS:
        ok = [r for r in acc if "error" not in r["backends"][b]]
        exact = sum(1 for r in ok if r["backends"][b]["exact_set_match"])
        spur = [r["backends"][b]["absent_from_production"] for r in ok]
        miss = [r["backends"][b]["missed_from_production"] for r in ok]
        summary[b] = {
            "documents": len(ok),
            "exact_set_match": exact,
            "total_labels_absent_from_production": sum(spur),
            "total_labels_missed_from_production": sum(miss),
            "mean_absent_per_doc": round(statistics.mean(spur), 2) if spur else None,
        }
    out = {
        "note": (
            "Production = parsers/pdf_text.extract_clean_pages (the TEXT API path production "
            "ships). Each backend = the neutral GLYPH layer this bake-off built. Concern A's "
            "reference is the harness incumbent, not this."
        ),
        "n_documents_scored": len(acc),
        "summary": summary,
        "documents": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))

    print(f"\nOver {len(acc)} production-accepted documents with headings:")
    print(f"  {'backend':16} {'exact set match':>16} {'labels absent from prod':>24} {'missed':>8}")
    for b, s in summary.items():
        print(
            f"  {b:16} {s['exact_set_match']:>8}/{s['documents']:<7} "
            f"{s['total_labels_absent_from_production']:>24} {s['total_labels_missed_from_production']:>8}"
        )
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
