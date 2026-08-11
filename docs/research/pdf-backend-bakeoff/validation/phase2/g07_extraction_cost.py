"""G7 — what the extended-glyph path costs to extract, against the hybrid path.

RECONSTRUCTED 2026-08-07. `results/g07_extraction_cost.json` was committed but this script
was not, while `validation/README.md` and `FINDINGS-EXTENDED-GLYPH.md` both say "probes are
`g01`-`g07`" and the findings cite its output three times (the "1.01-1.13x" extraction-cost
figure in the comparison table and twice in the prose). That left one load-bearing number in
phase 2 with no committed probe behind it, against the study's own stated rule that every
number is computed by a named probe and none is transcribed. This file closes that gap. It
is NOT a new measurement and it does not revise a phase-2 conclusion.

HOW THE PAGE LIMIT WAS ARRIVED AT. The frozen JSON carries two deterministic fields per
document -- `extended_no_advance` and `extended_zero_advance` -- which are pure counts over
the extracted characters and do not depend on the machine. A sweep of
`pdfium_extended.extract(limit=N)` over N = 1..60 reproduces BOTH counts on ALL THREE
documents at exactly N = 40, and at no other N in that range (N = 41 overshoots every one).
Forty pages is also the limit `probe_hybrid_signals.py` and `probe_hybrid_portability.py`
take.

State the status of that precisely: N = 40 is **uniquely reconstructed from the frozen
outputs within the tested range**, on six exact matches. It is not a recovered fact. Nothing
in the tree records what the original run was invoked with, the sweep was bounded at 60, and
agreement on these two counts is agreement on the OUTPUTS -- another configuration that
produced identical counts would be indistinguishable here. What the reconstruction licenses
is that this probe regenerates the committed numbers, which is what the missing-probe defect
required; it does not license a claim about the original invocation.

WHAT WILL NOT REPRODUCE, and it is the reason `--verify` checks what it checks.
`hybrid_ms`, `extended_ms` and `ratio` are wall-clock on one machine. The committed values
are from the original run (macOS 15 / arm64, per `probes/README.md`); a re-run on other
hardware, or alongside other work, will differ and that is not a defect. Only the two
counts are asserted. This is also why the probe does not overwrite the frozen file unless
asked: re-running it would replace an original measurement with a fresh timing.

WHAT THE COMPARISON MEANS. Both paths walk the same PDFium text page; the extended path
additionally resolves a font handle and a glyph width per character, cached per
(font, codepoint). The question is whether that chain is affordable, and the answer phase 2
published is that it is -- the overhead is single-digit to low-double-digit percent, not a
multiple. `extended_no_advance` is the count of characters that reached the contract with
`advance=None`, and `extended_zero_advance` the subset where `FPDFFont_GetGlyphWidth`
returned TRUE with a width of 0, which is the failed reverse map documented in
`pdfium_extended.py`, not a zero-width glyph.

    .venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase2/g07_extraction_cost.py --verify
    .venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase2/g07_extraction_cost.py --out <path>
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
import pdfium_hybrid  # noqa: E402

FROZEN = HERE / "results" / "g07_extraction_cost.json"

# The three documents in the frozen file, in its order: the omnibus where the glyph seam's
# heading defect is present, the enrolled negative control, and the committee report, which
# is the only non-bill layout the corpus carries.
DOCUMENTS = (
    "tests/corpus/114-hr-2029/4_reported-in-senate.pdf",
    "tests/corpus/116-hr-1865/6_enrolled-bill.pdf",
    "tests/data/CRPT-118srpt198.pdf",
)
PAGE_LIMIT = 40

DETERMINISTIC = ("extended_no_advance", "extended_zero_advance")


def measure(limit: int) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for rel in DOCUMENTS:
        pdf = REPO / rel
        if not pdf.exists():
            raise SystemExit(f"missing document: {rel}")
        _, hybrid = pdfium_hybrid.extract(pdf, limit=limit)
        _, extended = pdfium_extended.extract(pdf, limit=limit)
        out[rel] = {
            "hybrid_ms": hybrid["extract_ms"],
            "extended_ms": extended["extract_ms"],
            "ratio": round(extended["extract_ms"] / hybrid["extract_ms"], 2),
            "extended_no_advance": extended["glyphs_without_an_advance"],
            "extended_zero_advance": extended["zero_advance_reverse_map_failures"],
        }
        r = out[rel]
        print(
            f"  {rel:<52} hybrid {r['hybrid_ms']:>6} ms  extended {r['extended_ms']:>6} ms  ratio {r['ratio']:.2f}",
            file=sys.stderr,
        )
    return out


def verify(fresh: dict[str, dict]) -> int:
    """Compare only the machine-independent counts against the committed file."""
    frozen = json.loads(FROZEN.read_text())
    problems = []
    if set(frozen) != set(fresh):
        problems.append(f"document set differs: frozen {sorted(frozen)}, fresh {sorted(fresh)}")
    for rel in sorted(set(frozen) & set(fresh)):
        for field in DETERMINISTIC:
            a, b = frozen[rel][field], fresh[rel][field]
            status = "OK" if a == b else "MISMATCH"
            print(f"  {status:<8} {rel} {field}: frozen {a}, fresh {b}")
            if a != b:
                problems.append(f"{rel} {field}: frozen {a}, fresh {b}")

    ratios = [v["ratio"] for v in fresh.values()]
    print(
        f"\nfresh extraction-cost ratios: {min(ratios):.2f}-{max(ratios):.2f}x "
        f"(published range 1.01-1.13x; timings are machine-dependent and are not asserted)"
    )
    if problems:
        print(f"\n{len(problems)} MISMATCH(ES) -- the extended adapter no longer produces phase 2's counts:")
        for p in problems:
            print(f"  {p}")
        return 1
    print("\nVERIFIED: every machine-independent count matches the frozen file")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=PAGE_LIMIT)
    ap.add_argument(
        "--verify",
        action="store_true",
        help="re-measure and compare the deterministic counts against the committed file; write nothing",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"write results here. Omit to write nothing; pass {FROZEN.name}'s path to replace "
        "the original measurement, which discards its timings",
    )
    args = ap.parse_args()

    print(f"measuring {len(DOCUMENTS)} documents at {args.limit} pages", file=sys.stderr)
    fresh = measure(args.limit)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(fresh, indent=1))
        print(f"wrote {args.out}", file=sys.stderr)
    if args.verify:
        return verify(fresh)
    if not args.out:
        print(json.dumps(fresh, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
