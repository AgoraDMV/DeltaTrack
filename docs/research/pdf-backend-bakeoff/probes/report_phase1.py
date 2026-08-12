"""Summarize Phase 1 results: calibration gate first, then per-backend, then per-bill.

Reports the calibration gate before any ranking, because if the incumbent does not land
near ceiling through the neutral layer then nothing else in the file means anything.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

INCUMBENT = "pdfium-native"


def agg(values: list[float]) -> str:
    if not values:
        return "     n/a"
    return f"{statistics.mean(values):.4f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--mode", default="both", choices=["strict", "repaired", "both"])
    args = ap.parse_args()

    data = json.loads(args.results.read_text())
    docs = data["documents"]
    backends = data["backends"]
    modes = ["strict", "repaired"] if args.mode == "both" else [args.mode]

    print(f"N = {len(docs)} documents, {len(backends)} backends\n")

    # ---- Gate 1: did every backend open every document? ----
    print("GATE 1 -- opens the corpus")
    for b in backends:
        errs = [k for k, v in docs.items() if "error" in v.get(b, {})]
        n_ok = sum(1 for v in docs.values() if b in v and "error" not in v[b])
        print(f"  {b:<15} {n_ok}/{len(docs)} opened" + (f"  FAILURES: {errs}" if errs else ""))
    print()

    # ---- Calibration gate (Trap 1) ----
    print("CALIBRATION GATE (Trap 1) -- the incumbent through the neutral layer")
    for mode in modes:
        f1s = [
            v[INCUMBENT][mode]["text_vs_xml"]["f1"]
            for v in docs.values()
            if INCUMBENT in v and "error" not in v[INCUMBENT]
        ]
        cons = [
            v[INCUMBENT][mode]["tree"]["conservation_holds"]
            for v in docs.values()
            if INCUMBENT in v and "error" not in v[INCUMBENT]
        ]
        print(
            f"  {mode:<9} text F1 mean={agg(f1s)} median={statistics.median(f1s):.4f} "
            f"min={min(f1s):.4f} max={max(f1s):.4f} | conservation holds {sum(cons)}/{len(cons)}"
        )
    print("  (ceiling is set by the PDF-vs-XML format gap, not by 1.0 -- see README)\n")

    # ---- Per-backend aggregate ----
    for mode in modes:
        print(f"PER-BACKEND, mode={mode}  (N={len(docs)})")
        header = (
            f"  {'backend':<15} {'textF1':>7} {'ln_recall':>10} {'ln_spur':>8} "
            f"{'crumbs':>7} {'consv':>7} {'fontsep':>8} {'emptyfont':>10} {'extract_s':>10}"
        )
        print(header)
        for b in backends:
            rows = [v[b] for v in docs.values() if b in v and "error" not in v[b]]
            if not rows:
                continue
            f1 = [r[mode]["text_vs_xml"]["f1"] for r in rows]
            lr = [r[mode]["line_numbers"]["recall"] for r in rows if r[mode]["line_numbers"]["recall"] is not None]
            ls = [
                r[mode]["line_numbers"]["spurious_rate"]
                for r in rows
                if r[mode]["line_numbers"]["spurious_rate"] is not None
            ]
            bc = [r[mode]["breadcrumbs"]["agreement"] for r in rows if r[mode]["breadcrumbs"]["agreement"] is not None]
            cs = [r[mode]["tree"]["conservation_holds"] for r in rows]
            fs = [
                r["font_role"]["margin_vs_body_separation"]
                for r in rows
                if r["font_role"]["margin_vs_body_separation"] is not None
            ]
            ef = [
                r["font_role"]["empty_font_name_rate"]
                for r in rows
                if r["font_role"]["empty_font_name_rate"] is not None
            ]
            ex = [r["extract_s"] for r in rows]
            print(
                f"  {b:<15} {agg(f1):>7} {agg(lr):>10} {agg(ls):>8} {agg(bc):>7} "
                f"{sum(cs)}/{len(cs):<5} {agg(fs):>8} {agg(ef):>10} {sum(ex):>9.1f}"
            )
        print()

    # ---- Strict vs repaired gap: the glyph-naming deficit ----
    print("GLYPH-NAMING DEFICIT (repaired F1 - strict F1; >0 means the backend could not")
    print("name a glyph the position rule then recovered)")
    for b in backends:
        rows = [v[b] for v in docs.values() if b in v and "error" not in v[b]]
        gaps = [r["repaired"]["text_vs_xml"]["f1"] - r["strict"]["text_vs_xml"]["f1"] for r in rows]
        unnamed = [r["strict"]["reconstruction"]["unnamed_glyphs"] for r in rows]
        n_affected = sum(1 for g in gaps if g > 1e-9)
        print(
            f"  {b:<15} mean_gap={statistics.mean(gaps):+.4f} max_gap={max(gaps):+.4f} "
            f"docs_affected={n_affected}/{len(gaps)} unnamed_glyphs={sum(unnamed)}"
        )
    print()

    # ---- LCS cross-check: does the multiset substitution change anything? ----
    deltas = []
    for v in docs.values():
        for b in backends:
            r = v.get(b, {})
            if "error" in r:
                continue
            for mode in ("strict", "repaired"):
                lcs = r[mode].get("text_vs_xml_lcs")
                if lcs:
                    deltas.append(abs(lcs["f1"] - r[mode]["text_vs_xml"]["f1"]))
    if deltas:
        print("METRIC AUDIT -- multiset F1 vs order-sensitive LCS F1, where both computable")
        print(
            f"  n={len(deltas)} comparisons, mean |delta|={statistics.mean(deltas):.5f}, max |delta|={max(deltas):.5f}"
        )
        print()

    # ---- Per-bill, so one bill cannot drive the headline ----
    print("PER-BILL text F1 (repaired), so no single bill drives the aggregate")
    by_bill: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for key, v in docs.items():
        bill = key.split("/")[0]
        for b in backends:
            if b in v and "error" not in v[b]:
                by_bill[bill][b].append(v[b]["repaired"]["text_vs_xml"]["f1"])
    print(f"  {'bill':<16} {'n':>3} " + " ".join(f"{b[:11]:>11}" for b in backends))
    for bill in sorted(by_bill):
        n = max(len(by_bill[bill][b]) for b in backends)
        cells = " ".join(
            f"{statistics.mean(by_bill[bill][b]):>11.4f}" if by_bill[bill][b] else f"{'n/a':>11}" for b in backends
        )
        print(f"  {bill:<16} {n:>3} {cells}")


if __name__ == "__main__":
    main()
