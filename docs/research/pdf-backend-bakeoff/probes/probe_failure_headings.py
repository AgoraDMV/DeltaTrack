"""The four named failure headings, on all four paths, at the line where they are set.

`RESULTS-CONFIRMATORY.md` names `FAMILYHOUSING`, `NAVYAND`, `ARMYNATIONAL` and
`AMERICANBATTLE` as malformed labels the neutral glyph layer produces and production does
not. This probe compares the four paths on the exact printed lines those labels come from,
so the comparison is at the character level rather than at the aggregate.

The comparison is deliberately made on the RECONSTRUCTED PRINTED LINE, not on the anchor
label. An anchor label is the product of the heading detector, which merges stacked lines
and can mask or manufacture a difference that did not originate in extraction.

Run:
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/probe_failure_headings.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(PROBES / "backends"), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pdfium_hybrid  # noqa: E402
import reconstruct_hybrid as RH  # noqa: E402
from contract import run_backend  # noqa: E402
from reconstruct import reconstruct as reconstruct_glyph  # noqa: E402

from deltatrack.parsers.pdf_text import extract_clean_pages  # noqa: E402

# The GPO-printed forms. A path is correct on a line when it reproduces the spelling GPO
# set, which is the standard the request names and which no pipeline's output defines.
TARGETS = ("FAMILY HOUSING", "NAVY AND", "ARMY NATIONAL", "AMERICAN BATTLE")
# The corrupted forms the confirmatory run reported, i.e. the same text with the word
# space lost. Matched separately so a path that produces neither is not scored as correct.
CORRUPT = {t: t.replace(" ", "", 1) for t in TARGETS}

DEFAULT_DOCS = (
    "114-hr-2029/4_reported-in-senate",
    "118-hr-4366/5_engrossed-amendment-house",
    "116-hr-1865/6_enrolled-bill",
)


def pages_for(path: str, pdf: Path):
    if path == "production":
        return extract_clean_pages(pdf)
    if path == "hybrid":
        raw, _ = pdfium_hybrid.extract(pdf)
        return RH.reconstruct(raw)[0]
    backend = "pdfium-native" if path == "glyph" else "pdfminer"
    raw, _ = run_backend(backend, pdf)
    return reconstruct_glyph(raw, repaired=True)[0]


def occurrences(pages, target: str, corrupt: str) -> dict:
    """Count printed lines carrying the correct form and the corrupted form."""
    ok, bad, samples = 0, 0, []
    for page in pages:
        for ln in page.print_lines:
            if target in ln.text:
                ok += 1
            elif corrupt in ln.text:
                bad += 1
                if len(samples) < 3:
                    samples.append(f"p{page.page_number} L{ln.line_number}: {ln.text[:64]}")
    return {"correct": ok, "corrupted": bad, "samples": samples}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", nargs="*", default=list(DEFAULT_DOCS))
    ap.add_argument("--paths", nargs="*", default=["production", "glyph", "hybrid", "pdfminer"])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    results: dict = {}
    for doc in args.docs:
        pdf = REPO / "tests" / "corpus" / f"{doc}.pdf"
        if not pdf.exists():
            print(f"SKIP {doc}: not in corpus", file=sys.stderr)
            continue
        print(f"\n## {doc}")
        header = f"  {'heading':<16} " + " ".join(f"{p:>22}" for p in args.paths)
        print(header)
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
                    cells.append(f"{'ERROR':>22}")
                    continue
                o = occurrences(page_sets[path], target, CORRUPT[target])
                doc_res.setdefault(target, {})[path] = o
                cells.append(f"{o['correct']:>10} ok {o['corrupted']:>7} bad")
            print(f"  {target:<16} " + " ".join(cells))
        results[doc] = doc_res
        for target, per in doc_res.items():
            for path, o in per.items():
                for s in o["samples"]:
                    print(f"     [{path}] {target}: {s}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=1))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
