"""Concern D: performance, under a protocol that can declare its own run void.

PRE-REGISTRATION-CONFIRMATORY.md, "Concern D -- performance".

The exploratory gate-9 verdict for pdfminer did not reproduce: 37.9 s on first measurement,
69.2 s on re-run, against a 60 s ceiling, and the published figure turned out to be the
outlier. Nothing about that was visible from the number itself, which is why the machine
state is now part of the measurement rather than context for it.

Frozen conditions, each of which can VOID the run rather than degrade it quietly:

  * load average < 1.0 at start, recorded with the result
  * minimum of 5 trials; the MINIMUM is the estimator, not the mean
  * CPU time recorded beside wall time; material divergence means contention
  * one backend at a time, never concurrently

A candidate whose min-of-5 straddles the 60 s ceiling is UNRESOLVED, never rounded to a
pass or a fail. That is the state pdfminer is in today and this protocol exists to keep it
honestly there rather than resolve it by luck.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/confirm_perf.py
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import statistics
import sys
import time
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]

LOAD_CEILING = 1.0
TRIALS = 5
GATE_D1_SECONDS = 60.0
GATE_D2_MULTIPLE = 3.0
LARGEST = REPO / "tests/corpus/119-hr-1/1_reported-in-house.pdf"


def load_average() -> tuple[float, float, float]:
    return os.getloadavg()


def native_trial(backend: str, pdf: Path) -> dict:
    """One extraction, wall and CPU time. CPU is children-inclusive: the JS backends run
    in a subprocess, and charging only this process's CPU would report ~0 for them."""
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    self_before = resource.getrusage(resource.RUSAGE_SELF)
    t0 = time.perf_counter()
    from contract import run_backend

    pages, _summary = run_backend(backend, pdf)
    wall = time.perf_counter() - t0
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    self_after = resource.getrusage(resource.RUSAGE_SELF)
    cpu = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
    cpu += (self_after.ru_utime - self_before.ru_utime) + (self_after.ru_stime - self_before.ru_stime)
    return {"wall_s": round(wall, 3), "cpu_s": round(cpu, 3), "n_pages": len(pages)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO / "docs/research/pdf-backend-bakeoff/results/confirm_perf.json")
    ap.add_argument("--trials", type=int, default=TRIALS)
    ap.add_argument("--backends", default="pdfium-native,pdfium-wasm,pdfminer")
    args = ap.parse_args()

    sys.path.insert(0, str(PROBES))

    load_start = load_average()
    voided = load_start[0] >= LOAD_CEILING
    print(f"load average at start: {load_start[0]:.2f} (ceiling {LOAD_CEILING})", file=sys.stderr)
    if voided:
        print("  -> RUN IS VOID by the frozen idle-machine condition.", file=sys.stderr)
        print("     Measuring anyway, and publishing it as VOID rather than as a result.", file=sys.stderr)

    results: dict = {
        "document": str(LARGEST.relative_to(REPO)),
        "load_average_start": list(load_start),
        "load_ceiling": LOAD_CEILING,
        "trials": args.trials,
        "estimator": "minimum of trials",
        "void": voided,
        "void_reason": "load average at start >= 1.0" if voided else None,
        "gates": {"D1_seconds": GATE_D1_SECONDS, "D2_multiple_of_incumbent": GATE_D2_MULTIPLE},
        "backends": {},
    }

    for backend in args.backends.split(","):
        trials = []
        for i in range(args.trials):
            try:
                t = native_trial(backend, LARGEST)
            except Exception as exc:  # noqa: BLE001
                trials.append({"error": f"{type(exc).__name__}: {exc}"})
                print(f"  {backend} trial {i + 1}: ERROR {exc}", file=sys.stderr)
                continue
            trials.append(t)
            print(
                f"  {backend:14} trial {i + 1}/{args.trials}: wall={t['wall_s']:7.2f}s cpu={t['cpu_s']:7.2f}s",
                file=sys.stderr,
            )
        walls = [t["wall_s"] for t in trials if "wall_s" in t]
        cpus = [t["cpu_s"] for t in trials if "cpu_s" in t]
        if not walls:
            results["backends"][backend] = {"trials": trials, "error": "no successful trial"}
            continue
        entry = {
            "trials": trials,
            "min_s": min(walls),
            "median_s": round(statistics.median(walls), 3),
            "max_s": max(walls),
            "spread_s": round(max(walls) - min(walls), 3),
            "min_cpu_s": min(cpus) if cpus else None,
            "cpu_wall_ratio_at_min": round(min(cpus) / min(walls), 2) if cpus and min(walls) else None,
        }
        results["backends"][backend] = entry

    inc = results["backends"].get("pdfium-native", {}).get("min_s")
    results["load_average_end"] = list(load_average())
    for backend, entry in results["backends"].items():
        if "min_s" not in entry:
            continue
        d1 = entry["min_s"] < GATE_D1_SECONDS
        straddles = entry["min_s"] < GATE_D1_SECONDS <= entry.get("max_s", entry["min_s"])
        entry["D1"] = "UNRESOLVED (min-of-N straddles the ceiling)" if straddles else ("pass" if d1 else "fail")
        if inc:
            entry["D2_ratio_to_incumbent"] = round(entry["min_s"] / inc, 2)
            entry["D2"] = "pass" if entry["min_s"] <= GATE_D2_MULTIPLE * inc else "fail"
        if voided:
            entry["D1"] = f"VOID -- {entry['D1']}"
            entry["D2"] = f"VOID -- {entry.get('D2', 'n/a')}"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1))

    print(f"\n{'backend':16} {'min':>8} {'median':>8} {'max':>8} {'spread':>8} {'cpu/wall':>9}  D1 / D2")
    for backend, e in results["backends"].items():
        if "min_s" not in e:
            print(f"{backend:16} {e.get('error')}")
            continue
        print(
            f"{backend:16} {e['min_s']:8.2f} {e['median_s']:8.2f} {e['max_s']:8.2f} "
            f"{e['spread_s']:8.2f} {e['cpu_wall_ratio_at_min'] or 0:9.2f}  {e['D1']} / {e.get('D2', 'n/a')}"
        )
    print(f"\nload average: start {load_start[0]:.2f} -> end {results['load_average_end'][0]:.2f}")
    if voided:
        print("VOID: this run does not satisfy the frozen idle-machine condition.")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
