"""The near-full-container population, stated before any feature is tested.

Candidate 3's blocking failure is #501 arriving at the account boundary: a genuine
CONTAINER whose printed line leaves no early break, so line fullness cannot see it.

The decisive population is therefore exactly the boundaries where fullness has no margin
-- slack < 0, the ones reaching Candidate 3's `C5_fullness_join` -- partitioned by the
independent XML oracle:

    NEAR_FULL_CONTAINER  truth SPLIT. Fullness joins them; that is the #501 failure.
                         The two NOAA cases are the decisive controls.
    GENUINE_WRAP         truth JOIN. Fullness joins them correctly, and any new
                         discriminator must not damage them.

Boundaries that C2 (caps) already splits are excluded: they never reach fullness, so a
discriminator firing there can only do harm.

    uv run python docs/research/pdf-heading-identity/nearfull/population.py
"""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "frozen"))
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "confounder"))
import frozen_candidate as FC  # noqa: E402
import candidate3 as C3  # noqa: E402

OUT = Path(__file__).resolve().parent / "population.json"
T = FC.T


def main() -> None:
    rows = []
    for r in C3.resolved:
        for i, t in enumerate(C3.truth(r)):
            if r["texts"][i].rstrip().endswith(FC.WRAP_HYPHENS):
                continue  # C1 owns it
            cu, cl = C3.caps(r, i), C3.caps(r, i + 1)
            if cu is not None and cl is not None and cu >= T and cl < T:
                continue  # C2 already splits it
            sl = FC.slack(r["geoms"][i], r["geoms"][i + 1], r["column_width"])
            if sl is None or sl >= 0.0:
                continue  # not the no-margin population
            gu, gl = r["geoms"][i], r["geoms"][i + 1]
            rows.append({
                "corpus": r["corpus"], "bill": r["bill"], "version": r["version"],
                "page": r["pages"][i], "line": r["lines"][i],
                "upper": r["texts"][i], "lower": r["texts"][i + 1],
                "cls": "NEAR_FULL_CONTAINER" if t == FC.SPLIT else "GENUINE_WRAP",
                "caps_upper": cu, "caps_lower": cl, "slack": round(sl, 2),
                "column_width": r["column_width"],
                "w_upper": round(gu["right"] - gu["left"], 2),
                "w_lower": round(gl["right"] - gl["left"], 2),
                "fill_upper": round((gu["right"] - gu["left"]) / r["column_width"], 4),
            })

    cont = [x for x in rows if x["cls"] == "NEAR_FULL_CONTAINER"]
    wrap = [x for x in rows if x["cls"] == "GENUINE_WRAP"]
    print(f"no-margin population (slack < 0, not split by C1/C2): {len(rows)}")
    print(f"  NEAR_FULL_CONTAINER (truth SPLIT, the #501 class): {len(cont)}")
    print(f"  GENUINE_WRAP        (truth JOIN)                 : {len(wrap)}")
    print(f"  by corpus: {Counter(x['corpus'] for x in rows).most_common()}")
    print(f"  containers by corpus: {Counter(x['corpus'] for x in cont).most_common()}")

    print(f"\n=== every NEAR_FULL_CONTAINER ({len(cont)}) ===")
    for x in cont:
        print(f"  {x['bill']}/{x['version']} p{x['page']}L{x['line']}")
        print(f"     upper {x['upper']!r}")
        print(f"     lower {x['lower']!r}")
        print(f"     caps {x['caps_upper']}/{x['caps_lower']}  slack {x['slack']}  "
              f"w {x['w_upper']}/{x['w_lower']} of {x['column_width']:.1f}  fill {x['fill_upper']}")

    def q(vals, p):
        vals = sorted(vals)
        return vals[min(len(vals) - 1, int(len(vals) * p / 100))]

    print("\n=== upper-line fill fraction, by class ===")
    for name, xs in (("CONTAINER", cont), ("WRAP", wrap)):
        v = [x["fill_upper"] for x in xs]
        print(f"  {name:<10} n={len(v)} min={min(v):.3f} p5={q(v,5):.3f} med={q(v,50):.3f} "
              f"p95={q(v,95):.3f} max={max(v):.3f}")
    print("\n=== caps_per_word(lower), by class ===")
    for name, xs in (("CONTAINER", cont), ("WRAP", wrap)):
        v = [x["caps_lower"] for x in xs if x["caps_lower"] is not None]
        print(f"  {name:<10} n={len(v)} min={min(v):.3f} med={q(v,50):.3f} max={max(v):.3f} "
              f"  distribution={Counter(round(y,2) for y in v).most_common(8)}")

    OUT.write_text(json.dumps({"T": T, "rows": rows}, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
