"""Mandatory parameter-sensitivity sweep: does a lead survive the layer's own constants?

PRE-REGISTRATION-CONFIRMATORY.md, "Mandatory parameter-sensitivity tests". Frozen rules,
none of which are tunable here:

    5-setting parameter   the leader must lead at >= 4 of 5
    4-setting parameter   >= 3 of 4
    binary parameter      the ranking must not reverse between the two settings

    a metric that moves by > 0.05 across a parameter's sweep is PARAMETER-FRAGILE on that
    metric, and that is reported next to its score

    a lead that exists only at the default is reported as "leads at the default
    parameterization only", never as a lead

This exists because the audit found `_SPACE_FACTOR = 0.25` inherited from PDFium-tuned
production. The confirmatory run then found the constant biting in the OPPOSITE direction
to what the audit anticipated: at a GPO small-caps word boundary the inter-word gap is
~4.3pt against a threshold of exactly 0.25 x 14.0 = 3.50, and the two backends resolve the
small-cap size differently (pdfium 11.2pt, pdfminer 10.5pt), so they land on opposite sides
of the same knife-edge. PDFium loses word spaces inside heading labels -- FAMILYHOUSING,
NAVYAND, ARMYNATIONAL -- which is most of its B2 deficit.

Whether that is a PDFium defect or an artifact of one constant is exactly what this sweep
decides, and it is the difference between "pdfminer reads headings better" and "pdfminer
reads headings better at 0.25".

Extraction is the expensive part and is done ONCE per document per backend; every setting
then re-runs only the reconstruction and scoring.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/confirm_sensitivity.py
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
import reconstruct as R  # noqa: E402
from contract import run_backend  # noqa: E402
from score_phase1 import (  # noqa: E402
    align_to_body,
    corpus_documents,
    normalize_for_text_compare,
    token_f1,
    xml_body_tokens,
)

from deltatrack.compare.pdf import _is_unnumbered_layout  # noqa: E402

CANDIDATES = ("pdfium-wasm", "pdfminer")
FRAGILE = 0.05

SWEEPS = {
    "_SPACE_FACTOR": {"values": [0.15, 0.20, 0.25, 0.30, 0.40], "default": 0.25},
    "_BASELINE_TOL": {"values": [0.1, 0.3, 0.6, 1.2, 2.0], "default": 0.6},
    "_CHROME_SIZE_RATIO": {"values": [0.0, 0.45, 0.55, 0.65], "default": 0.55},
    "repair_mode": {"values": ["strict", "repaired"], "default": "strict"},
}
RULE = {5: 4, 4: 3, 2: None}


def score_one(raw_pages, xml_tokens, ref, repaired: bool) -> dict:
    pages, _ = R.reconstruct(raw_pages, repaired=repaired)
    toks = normalize_for_text_compare("\n".join(p.text for p in pages))
    aligned, _ = align_to_body(xml_tokens, toks)
    st = M.pdf_structure(pages)
    return {
        "B1": token_f1(xml_tokens, aligned)["f1"],
        "B2": M.b2_heading_labels(st, ref)["f1"],
        "B5": (M.b5_amount_association(st, ref) or {}).get("f1"),
        "B6": (M.b6_parent_child(st, ref) or {}).get("accuracy"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out", type=Path, default=REPO / "docs/research/pdf-backend-bakeoff/results/confirm_sensitivity.json"
    )
    ap.add_argument("--limit-docs", type=int, default=None)
    ap.add_argument("--docs", default=None, help="comma-separated bill/version keys, for validating the sweep")
    args = ap.parse_args()

    docs = corpus_documents()
    if args.docs:
        want = set(args.docs.split(","))
        docs = [d for d in docs if f"{d[0]}/{d[1]}" in want]
    if args.limit_docs:
        docs = docs[: args.limit_docs]

    cache: list[dict] = []
    for i, (bill, version, pdf, xml) in enumerate(docs, 1):
        try:
            raw = {b: run_backend(b, pdf)[0] for b in CANDIDATES}
            pages, _ = R.reconstruct(raw["pdfium-wasm"], repaired=True)
            if _is_unnumbered_layout(pages):
                print(f"  [{i}/{len(docs)}] {bill}/{version} declined", file=sys.stderr)
                continue
            cache.append(
                {
                    "key": f"{bill}/{version}",
                    "raw": raw,
                    "xml_tokens": xml_body_tokens(xml),
                    "ref": M.xml_reference(xml),
                    "quoted_block": M.xml_has_quoted_block(xml),
                }
            )
            print(f"  [{i}/{len(docs)}] {bill}/{version} cached", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i}/{len(docs)}] {bill}/{version} ERROR {exc}", file=sys.stderr)
    print(f"swept over {len(cache)} production-accepted documents", file=sys.stderr)

    out: dict = {"n_documents": len(cache), "fragile_threshold": FRAGILE, "sweeps": {}}

    for param, spec in SWEEPS.items():
        rows: dict = {}
        for value in spec["values"]:
            saved = (R._SPACE_FACTOR, R._BASELINE_TOL, R._CHROME_SIZE_RATIO)
            repaired = False
            if param == "_SPACE_FACTOR":
                R._SPACE_FACTOR = value
            elif param == "_BASELINE_TOL":
                R._BASELINE_TOL = value
            elif param == "_CHROME_SIZE_RATIO":
                R._CHROME_SIZE_RATIO = value
            elif param == "repair_mode":
                repaired = value == "repaired"
            try:
                per_backend: dict = {}
                for b in CANDIDATES:
                    acc: dict[str, list[float]] = {"B1": [], "B2": [], "B5": [], "B6": []}
                    for entry in cache:
                        s = score_one(entry["raw"][b], entry["xml_tokens"], entry["ref"], repaired)
                        for m, v in s.items():
                            if v is not None:
                                acc[m].append(v)
                    per_backend[b] = {m: round(statistics.mean(v), 5) if v else None for m, v in acc.items()}
                rows[str(value)] = per_backend
            finally:
                R._SPACE_FACTOR, R._BASELINE_TOL, R._CHROME_SIZE_RATIO = saved
            print(
                f"  {param}={value}: " + " ".join(f"{b}.B2={rows[str(value)][b]['B2']}" for b in CANDIDATES),
                file=sys.stderr,
            )

        verdicts = {}
        for metric in ("B1", "B2", "B5", "B6"):
            wins = {b: 0 for b in CANDIDATES}
            spread = {b: [] for b in CANDIDATES}
            for value in spec["values"]:
                r = rows[str(value)]
                vals = {b: r[b][metric] for b in CANDIDATES if r[b][metric] is not None}
                if len(vals) < 2:
                    continue
                leader = max(vals, key=lambda b: vals[b])
                if abs(vals[CANDIDATES[0]] - vals[CANDIDATES[1]]) > 1e-9:
                    wins[leader] += 1
                for b, v in vals.items():
                    spread[b].append(v)
            n = len(spec["values"])
            need = RULE.get(n)
            leader = max(wins, key=lambda b: wins[b])
            if n == 2:
                held = wins[leader] == sum(wins.values()) or sum(wins.values()) == 0
                rule_text = "ranking does not reverse" if held else "RANKING REVERSES"
            else:
                held = wins[leader] >= (need or n)
                rule_text = f"{wins[leader]}/{n} (needs {need})"
            frag = {b: round(max(v) - min(v), 5) if v else None for b, v in spread.items()}
            verdicts[metric] = {
                "wins": wins,
                "leader": leader if wins[leader] else None,
                "rule": rule_text,
                "lead_holds": bool(held and wins[leader]),
                "sweep_spread": frag,
                "parameter_fragile": {b: (f is not None and f > FRAGILE) for b, f in frag.items()},
            }
        out["sweeps"][param] = {"default": spec["default"], "rows": rows, "verdicts": verdicts}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))

    for param, blk in out["sweeps"].items():
        print(f"\n=== {param} (default {blk['default']}) ===")
        for metric, v in blk["verdicts"].items():
            frag = ", ".join(
                f"{b} spread {v['sweep_spread'][b]}" for b in CANDIDATES if v["sweep_spread"][b] is not None
            )
            fragile = [b for b, f in v["parameter_fragile"].items() if f]
            tag = f"  PARAMETER-FRAGILE: {', '.join(fragile)}" if fragile else ""
            print(
                f"  {metric:4} leader={v['leader'] or '-':12} {v['rule']:22} lead_holds={v['lead_holds']}  {frag}{tag}"
            )
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
