"""G5 — the four named heading failure cases, with the extended-glyph path added.

Same probe as `probes/probe_failure_headings.py`, same targets, same documents, same
"count on the printed line, not on the anchor label" rule. The only change is a fifth
column. Nothing in the original probe is modified; it is imported where possible so the
four existing columns cannot drift from the numbers `RESULTS-HYBRID.md` §3 publishes.

`116-hr-1865/6` is retained as the negative control it was: a document where the glyph
path does NOT fail, so a path cannot score well merely by being run on an easy population.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
PROBES = REPO / "docs/research/pdf-backend-bakeoff/probes"
for p in (str(HERE), str(PROBES), str(PROBES / "backends"), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pdfium_extended  # noqa: E402
import reconstruct_extended as RE  # noqa: E402
from probe_failure_headings import CORRUPT, DEFAULT_DOCS, TARGETS, occurrences  # noqa: E402
from probe_failure_headings import pages_for as pages_for_original  # noqa: E402


def pages_for(path: str, pdf: Path):
    if path == "extended":
        raw, _ = pdfium_extended.extract(pdf)
        return RE.reconstruct(raw, repaired=True)[0]
    return pages_for_original(path, pdf)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", nargs="*", default=list(DEFAULT_DOCS))
    ap.add_argument("--paths", nargs="*", default=["production", "glyph", "hybrid", "extended", "pdfminer"])
    ap.add_argument("--out", type=Path, default=HERE / "results" / "g05_failure_headings.json")
    args = ap.parse_args()

    results: dict = {}
    totals: dict[str, dict[str, int]] = {p: {"correct": 0, "corrupted": 0} for p in args.paths}
    for doc in args.docs:
        pdf = REPO / "tests" / "corpus" / f"{doc}.pdf"
        if not pdf.exists():
            print(f"SKIP {doc}", file=sys.stderr)
            continue
        print(f"\n## {doc}")
        print(f"  {'heading':<16} " + " ".join(f"{p:>20}" for p in args.paths))
        page_sets = {}
        for path in args.paths:
            try:
                page_sets[path] = pages_for(path, pdf)
            except Exception as exc:  # noqa: BLE001
                print(f"  {path} FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        doc_res: dict = {}
        for target in TARGETS:
            cells = []
            for path in args.paths:
                if path not in page_sets:
                    cells.append(f"{'ERROR':>20}")
                    continue
                o = occurrences(page_sets[path], target, CORRUPT[target])
                doc_res.setdefault(target, {})[path] = o
                totals[path]["correct"] += o["correct"]
                totals[path]["corrupted"] += o["corrupted"]
                cells.append(f"{o['correct']:>8} ok {o['corrupted']:>5} bad")
            print(f"  {target:<16} " + " ".join(cells))
        results[doc] = doc_res

    print("\n## all documents, all four headings")
    print("  " + " ".join(f"{p:>20}" for p in args.paths))
    print("  " + " ".join(f"{totals[p]['correct']:>8} ok {totals[p]['corrupted']:>5} bad" for p in args.paths))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"per_document": results, "totals": totals}, indent=1))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
