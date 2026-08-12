"""P3: does the pipeline DECLINE what it cannot read, or answer it confidently and wrongly?

PRE-REGISTRATION-CONFIRMATORY.md, "P3 -- non-corpus robustness probes" and "Safe failure is
a first-class gate".

Three outcomes per fixture, and only one of them is a failure:

    DECLINES            production raises UnsupportedLayoutError -- the safe outcome
    ANSWERS             a diff with anchors
    ANSWERS ANCHORLESS  a diff with ZERO anchors -- a confident wrong answer

Gate S-1: no fixture may land in ANSWERS ANCHORLESS. The exploratory run produced exactly
that state once, reporting 3,468 amount entries against the XML's 0 on an enrolled pair
reached by bypassing the guard, which is why this is a gate and not an observation.

The population is deliberately mixed, and each class is labelled because they license
different claims:

    P3a real, non-corpus GPO   the 12 existing fixtures + a real committee print
    P3b synthetic degradations SAFE FAILURE ONLY, never accuracy -- an image-only PDF
                               (a GPO page rasterized, so no text layer at all) and a
                               non-GPO producer PDF (CoreGraphics via cupsfilter)

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/confirm_safe_failure.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from contract import run_backend  # noqa: E402
from reconstruct import reconstruct  # noqa: E402

from deltatrack.compare.pdf import _is_unnumbered_layout  # noqa: E402
from deltatrack.parsers.pdf_anchors import extract_anchors  # noqa: E402

BACKENDS = ("pdfium-wasm", "pdfminer")


# Every fixture is REQUIRED, and the count is pinned. This list used to be assembled with
# `if path.exists()`, which meant a tree missing `p3/imageonly.pdf` and `p3/nongpo.pdf`
# scored the remaining thirteen, found no violation and reported gate S-1 as PASSING -- on
# a population that no longer contained the two fixtures that fail it. A gate whose
# negative evidence can silently leave the population is not a gate.
_REQUIRED = (
    ("P3a real non-corpus GPO", "CRPT-118srpt198.pdf"),
    ("P3a real non-corpus GPO", "BILLS-118s4795rs.pdf"),
    ("P3a real committee print (markup)", "p3/CPRT-119HPRT63305.pdf"),
    ("P3b synthetic: image-only", "p3/imageonly.pdf"),
    ("P3b synthetic: non-GPO producer", "p3/nongpo.pdf"),
)
_N_SUBCOMMITTEE = 10  # tests/data/subcommittee/*.pdf, as scored in confirm_safe_failure.json


def fixtures() -> list[tuple[str, str, Path]]:
    d = REPO / "tests/data"
    sub = sorted((d / "subcommittee").glob("*.pdf"))

    # Order matches confirm_safe_failure.json: the two named GPO documents, the
    # subcommittee prints, then the committee print and the two synthetic degradations.
    named = [(k, d / rel) for k, rel in _REQUIRED]
    ordered = named[:2] + [("P3a real non-corpus GPO", p) for p in sub] + named[2:]

    missing = [str(p.relative_to(d)) for _, p in named if not p.exists()]
    if missing:
        raise SystemExit(f"required P3 fixtures missing under tests/data: {', '.join(missing)}")
    if len(sub) != _N_SUBCOMMITTEE:
        raise SystemExit(
            f"tests/data/subcommittee holds {len(sub)} PDFs, expected {_N_SUBCOMMITTEE}; "
            "the P3a population has changed and confirm_safe_failure.json is no longer comparable"
        )
    return [(k, p.name, p) for k, p in ordered]


def classify(pdf: Path, backend: str) -> dict:
    try:
        raw, summary = run_backend(backend, pdf)
    except Exception as exc:  # noqa: BLE001
        return {"outcome": "EXTRACTION ERROR", "error": f"{type(exc).__name__}: {exc}"}
    try:
        pages, _ = reconstruct(raw, repaired=True)
    except Exception as exc:  # noqa: BLE001
        return {"outcome": "RECONSTRUCT ERROR", "error": f"{type(exc).__name__}: {exc}"}
    declined = _is_unnumbered_layout(pages)
    anchors = extract_anchors(pages)
    n_glyphs = sum(len(p.glyphs) for p in raw)
    if declined:
        outcome = "DECLINES"
    elif anchors:
        outcome = "ANSWERS"
    else:
        outcome = "ANSWERS ANCHORLESS"
    return {
        "outcome": outcome,
        "n_pages": len(pages),
        "n_glyphs": n_glyphs,
        "n_anchors": len(anchors),
        "empty_font_names": (summary or {}).get("empty_font_names"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out", type=Path, default=REPO / "docs/research/pdf-backend-bakeoff/results/confirm_safe_failure.json"
    )
    args = ap.parse_args()

    fx = fixtures()
    print(f"{len(fx)} fixtures", file=sys.stderr)
    rows = []
    for klass, name, pdf in fx:
        entry = {"class": klass, "fixture": name, "backends": {}}
        for b in BACKENDS:
            entry["backends"][b] = classify(pdf, b)
        rows.append(entry)
        marks = " ".join(f"{b}={entry['backends'][b]['outcome']}" for b in BACKENDS)
        print(f"  {name:34} {klass[:28]:28} {marks}", file=sys.stderr)

    unsafe = [(r["fixture"], b) for r in rows for b in BACKENDS if r["backends"][b]["outcome"] == "ANSWERS ANCHORLESS"]
    result = {
        "gate_S1": "no fixture may land in ANSWERS ANCHORLESS",
        "violations": unsafe,
        "S1_passes": not unsafe,
        "conference_report": (
            "NOT OBTAINED -- no package in the govinfo CRPT collection from 2015 onward carries "
            "'conference report' in its title across 800 records checked; modern practice uses "
            "amendments between the houses instead. Logged as a protocol deviation."
        ),
        "fixtures": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1))

    print("\n| fixture | class | " + " | ".join(BACKENDS) + " |")
    print("|---|---|" + "---|" * len(BACKENDS))
    for r in rows:
        print(
            f"| `{r['fixture']}` | {r['class']} | " + " | ".join(r["backends"][b]["outcome"] for b in BACKENDS) + " |"
        )
    print(f"\nGate S-1: {'PASS' if not unsafe else 'FAIL -- ' + str(unsafe)}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
