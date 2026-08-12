"""Concern B statistics: paired cluster bootstrap by bill, thresholds, and the B0 rows.

PRE-REGISTRATION-CONFIRMATORY.md, "Statistics: paired cluster bootstrap by bill" and
"Practical-effect thresholds".

  Delta = score(pdfminer) - score(pdfium-wasm), paired per document, defined once here and
  never inverted. Positive Delta favours pdfminer.

  Resampling unit is the BILL, with replacement, all of a sampled bill's documents
  travelling together. The statistic is the per-bill mean of the paired per-document
  Delta, then the unweighted mean over sampled bills, so one 6-document bill cannot
  dominate 30 clusters. Document-weighted aggregation is reported as a sensitivity check.

  A backend LEADS only if the 95% CI excludes zero AND |Delta| reaches the metric's
  practical threshold. Overlapping independent CIs are not evidence and are not computed.

A metric whose deciding sabotage does not move it past its own threshold is VOID: its
Delta is printed but marked, and it may not be cited as evidence. That check runs first,
because a Delta table without its B0 row is not reviewable.

Run:
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/report_confirmatory.py \
      --results docs/research/pdf-backend-bakeoff/results/confirm_p1.json
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import confirm_sabotage as SAB  # noqa: E402

SEED = 20260805
RESAMPLES = 10_000

# Frozen before any confirmatory result was visible. See the preregistration for the
# per-metric justification; these are not tunable here.
THRESHOLDS = {"B1": 0.010, "B2": 0.020, "B3a": 0.005, "B5": 0.010, "B6": 0.020}

# (metric -> how to pull its scalar out of a scored document)
FIELD = {
    "B1": ("B1", "f1"),
    "B2": ("B2", "f1"),
    "B3a": ("B3a", "score"),
    "B5": ("B5", "f1"),
    "B6": ("B6", "accuracy"),
}

CANDIDATES = ("pdfium-wasm", "pdfminer")


def scalar(doc_results: dict, backend: str, mode: str, metric: str) -> float | None:
    entry = doc_results.get(backend, {}).get(mode)
    if not entry or "error" in entry:
        return None
    block, field = FIELD[metric]
    val = entry.get(block, {}).get(field)
    return None if val is None else float(val)


def paired_deltas(docs: dict, mode: str, metric: str, keys: list[str]) -> dict[str, list[float]]:
    """{bill: [per-document Delta]} for documents where BOTH candidates scored."""
    by_bill: dict[str, list[float]] = {}
    for key in keys:
        entry = docs[key]
        res = entry.get("results") or {}
        a = scalar(res, "pdfminer", mode, metric)
        b = scalar(res, "pdfium-wasm", mode, metric)
        if a is None or b is None:
            continue
        by_bill.setdefault(entry["bill"], []).append(a - b)
    return by_bill


def cluster_bootstrap(by_bill: dict[str, list[float]]) -> dict:
    bills = sorted(by_bill)
    if len(bills) < 2:
        return {"point": None, "ci": None, "n_bills": len(bills), "n_documents": sum(len(v) for v in by_bill.values())}
    per_bill = {b: statistics.mean(by_bill[b]) for b in bills}
    point = statistics.mean(per_bill[b] for b in bills)

    rng = random.Random(SEED)
    draws = []
    n = len(bills)
    for _ in range(RESAMPLES):
        sample = [per_bill[bills[rng.randrange(n)]] for _ in range(n)]
        draws.append(sum(sample) / n)
    draws.sort()
    lo = draws[int(0.025 * RESAMPLES)]
    hi = draws[int(0.975 * RESAMPLES) - 1]

    flat = [d for v in by_bill.values() for d in v]
    n_differing = sum(1 for d in flat if abs(d) > 1e-9)
    return {
        "point": round(point, 5),
        "ci": [round(lo, 5), round(hi, 5)],
        "excludes_zero": bool(lo > 0 or hi < 0),
        "n_bills": n,
        "n_documents": len(flat),
        "n_documents_differing": n_differing,
        # A [0, 0] interval means NO DOCUMENT DIFFERED, which is a different statement from
        # "the differences cancelled out" and must not be read as the latter. Where it also
        # holds that every document capable of differing was excluded by a stratum rule, the
        # metric had no chance to discriminate and "indistinguishable" is not evidence of
        # similarity -- see the B2 note in RESULTS-CONFIRMATORY.md.
        "degenerate_all_zero": n_differing == 0,
        "doc_weighted_point": round(statistics.mean(flat), 5),
    }


def verdict(stat: dict, metric: str, void: bool) -> str:
    if void:
        return "VOID (control did not fire)"
    if stat["point"] is None:
        return "insufficient data"
    th = THRESHOLDS[metric]
    sig = stat["excludes_zero"]
    prac = abs(stat["point"]) >= th
    who = "pdfminer" if stat["point"] > 0 else "pdfium-wasm"
    if sig and prac:
        return f"{who} LEADS"
    if sig and not prac:
        return "statistically distinguishable, practically indistinguishable"
    if not sig and prac:
        return "practically large but CI includes zero -- not established"
    if stat.get("degenerate_all_zero"):
        return "identical on every document (not merely indistinguishable)"
    return "indistinguishable"


def b0_rows(docs: dict, mode: str, keys: list[str]) -> dict:
    """Did each deciding control move its own metric past that metric's threshold?"""
    out = {}
    for metric, sid in SAB.DECIDING.items():
        deltas, others = [], []
        for key in keys:
            res = docs[key].get("results") or {}
            base = scalar(res, "pdfium-wasm", mode, metric)
            sab = scalar(res, sid, mode, metric)
            if base is None or sab is None:
                continue
            deltas.append(base - sab)
            b2b = scalar(res, "pdfium-wasm", mode, "B2")
            b2s = scalar(res, sid, mode, "B2")
            if b2b is not None and b2s is not None:
                others.append(b2b - b2s)
        if not deltas:
            out[metric] = {"control": sid, "delta": None, "fires": False, "n": 0}
            continue
        d = statistics.mean(deltas)
        out[metric] = {
            "control": sid,
            "delta": round(d, 5),
            "threshold": THRESHOLDS[metric],
            "fires": bool(d >= THRESHOLDS[metric]),
            "n": len(deltas),
            "b2_delta": round(statistics.mean(others), 5) if others else None,
        }
    return out


def separability(docs: dict, mode: str, keys: list[str]) -> list[dict]:
    rows = []
    for sid, own_m, other_m, rule, lim in SAB.SEPARABILITY:
        own, other = [], []
        for key in keys:
            res = docs[key].get("results") or {}
            for metric, acc in ((own_m, own), (other_m, other)):
                b = scalar(res, "pdfium-wasm", mode, metric)
                s = scalar(res, sid, mode, metric)
                if b is not None and s is not None:
                    acc.append(b - s)
        if not own or not other:
            rows.append({"control": sid, "verdict": "insufficient data"})
            continue
        a, o = statistics.mean(own), statistics.mean(other)
        ok = (o < lim) if rule == "threshold" else (o < a)
        rows.append(
            {
                "control": sid,
                "own_metric": own_m,
                "own_delta": round(a, 5),
                "other_metric": other_m,
                "other_delta": round(o, 5),
                "rule": rule,
                "limit": lim,
                "verdict": "SEPARABLE" if ok else "NOT SEPARABLE",
            }
        )
    return rows


def repair_delta(docs: dict, keys: list[str]) -> dict:
    out = {}
    for backend in CANDIDATES:
        vals = []
        for key in keys:
            res = docs[key].get("results") or {}
            s = scalar(res, backend, "strict", "B1")
            r = scalar(res, backend, "repaired", "B1")
            if s is not None and r is not None:
                vals.append(r - s)
        out[backend] = round(statistics.mean(vals), 5) if vals else None
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--mode", default="strict", choices=("strict", "repaired"))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    raw = json.loads(args.results.read_text())
    docs = raw["documents"]
    pop = raw["population"]

    def accepted(key: str) -> bool:
        res = docs[key].get("results") or {}
        return res.get("pdfium-wasm", {}).get("production_accepted") is True

    strata = {
        "primary (production-accepted)": [k for k in docs if accepted(k)],
        "production-declined": [k for k in docs if not accepted(k)],
    }
    qb = [k for k in docs if docs[k].get("quoted_block")]
    strata["primary, quoted-block-free (B2/B5/B6)"] = [
        k for k in strata["primary (production-accepted)"] if k not in qb
    ]
    strata["primary, quoted-block (B2/B5/B6)"] = [k for k in strata["primary (production-accepted)"] if k in qb]

    report = {
        "population": pop,
        "source": str(args.results.name),
        "mode": args.mode,
        "seed": SEED,
        "resamples": RESAMPLES,
        "delta_definition": "score(pdfminer) - score(pdfium-wasm); positive favours pdfminer",
        "n_documents": len(docs),
        "strata_sizes": {k: len(v) for k, v in strata.items()},
    }

    primary = strata["primary (production-accepted)"]
    report["B0"] = b0_rows(docs, args.mode, primary)
    report["separability"] = separability(docs, args.mode, primary)
    report["repair_delta_B1"] = repair_delta(docs, primary)

    results = {}
    for metric in FIELD:
        keys = strata["primary, quoted-block-free (B2/B5/B6)"] if metric in ("B2", "B5", "B6") else primary
        stat = cluster_bootstrap(paired_deltas(docs, args.mode, metric, keys))
        void = not report["B0"].get(metric, {}).get("fires", False)
        stat["verdict"] = verdict(stat, metric, void)
        stat["threshold"] = THRESHOLDS[metric]
        stat["stratum"] = "quoted-block-free" if metric in ("B2", "B5", "B6") else "production-accepted"
        results[metric] = stat
    report["delta"] = results

    # The quoted-block stratum for B2/B5/B6, reported because the primary stratum is
    # known to be non-discriminating on this corpus: every P1 document where the two
    # backends' heading recovery differs carries <quoted-block>, and the exclusion that
    # protects B2 from the DeltaTrack#11 reference defect removes all of them. Publishing
    # only "identical on every document" would read as evidence of similarity when the
    # metric in fact had no opportunity to fire.
    secondary = {}
    for metric in ("B2", "B5", "B6"):
        keys = strata["primary, quoted-block (B2/B5/B6)"]
        stat = cluster_bootstrap(paired_deltas(docs, args.mode, metric, keys))
        stat["threshold"] = THRESHOLDS[metric]
        stat["stratum"] = "quoted-block (XML reference carries a known parser drop)"
        stat["caveat"] = (
            "The XML reference under-reports here (DeltaTrack#11), so this is not a clean "
            "accuracy comparison. It is reported because the clean stratum cannot discriminate."
        )
        secondary[metric] = stat
    report["delta_quoted_block_stratum"] = secondary

    # Absolute per-backend means, for context. Never a ranking on their own.
    means = {}
    for backend in CANDIDATES + ("pdfium-native",):
        means[backend] = {}
        for metric in FIELD:
            keys = strata["primary, quoted-block-free (B2/B5/B6)"] if metric in ("B2", "B5", "B6") else primary
            vals = [scalar(docs[k].get("results") or {}, backend, args.mode, metric) for k in keys]
            vals = [v for v in vals if v is not None]
            means[backend][metric] = round(statistics.mean(vals), 5) if vals else None
    report["means"] = means

    print(f"\n=== {pop.upper()} / {args.mode} mode ===")
    print(f"documents {len(docs)}  strata: " + ", ".join(f"{k}={len(v)}" for k, v in strata.items()))

    print("\nB0 -- did each control fire?")
    print(f"  {'metric':6} {'control':6} {'delta':>9} {'threshold':>10}  verdict")
    for m, r in report["B0"].items():
        d = "n/a" if r["delta"] is None else f"{r['delta']:+.4f}"
        fired = "FIRES" if r["fires"] else "DID NOT FIRE -> metric VOID"
        print(f"  {m:6} {r['control']:6} {d:>9} {r.get('threshold', 0):>10}  {fired}")

    print("\nSeparability")
    for r in report["separability"]:
        if r.get("verdict") == "insufficient data":
            print(f"  {r['control']}: insufficient data")
            continue
        print(
            f"  {r['control']}: {r['own_metric']} {r['own_delta']:+.4f} vs "
            f"{r['other_metric']} {r['other_delta']:+.4f} -> {r['verdict']}"
        )

    print(f"\nDelta = pdfminer - pdfium-wasm  ({RESAMPLES} cluster resamples by bill, seed {SEED})")
    print(f"  {'metric':6} {'pdfium':>8} {'pdfmnr':>8} {'delta':>9} {'95% CI':>20} {'thresh':>7}  verdict")
    for m, s in report["delta"].items():
        if s["point"] is None:
            print(f"  {m:6} insufficient data")
            continue
        ci = f"[{s['ci'][0]:+.4f}, {s['ci'][1]:+.4f}]"
        pw = means["pdfium-wasm"][m]
        pm = means["pdfminer"][m]
        a = "     n/a" if pw is None else f"{pw:8.4f}"
        b = "     n/a" if pm is None else f"{pm:8.4f}"
        n = f"{s['n_documents_differing']}/{s['n_documents']}"
        print(f"  {m:6} {a} {b} {s['point']:+9.4f} {ci:>20} {s['threshold']:>7}  {n:>7} differ  {s['verdict']}")

    print("\nB2/B5/B6 on the QUOTED-BLOCK stratum (reference is known-defective there,")
    print("reported because the clean stratum above cannot discriminate at all):")
    for m, s2 in report["delta_quoted_block_stratum"].items():
        if s2["point"] is None:
            print(f"  {m:6} insufficient data")
            continue
        ci = f"[{s2['ci'][0]:+.4f}, {s2['ci'][1]:+.4f}]"
        n = f"{s2['n_documents_differing']}/{s2['n_documents']}"
        print(f"  {m:6} delta={s2['point']:+.4f} {ci:>20} {n:>7} differ")

    print(f"\nrepair delta on B1 (repaired - strict): {report['repair_delta_B1']}")

    dest = args.out or args.results.with_name(args.results.stem + f"_report_{args.mode}.json")
    dest.write_text(json.dumps(report, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
