"""The bounded confounder population, defined BEFORE any feature is tested.

The isolated failure is: a genuine CONTAINER heading printed in even small caps is
indistinguishable from an ACCOUNT under caps-per-word, so clause D6 (both sides below T)
joins them and fabricates hierarchy.

So the decisive population is exactly the D6 population -- boundaries where BOTH lines
score caps-per-word < T -- partitioned by the independent XML oracle:

    CONFOUNDER   truth SPLIT: a container above an account, both even small caps.
                 These are what D2's document-local vocabulary currently catches and
                 what any replacement discriminator must also catch.
    AT-RISK WRAP truth JOIN: one wrapped account whose two printed lines are both even
                 small caps. These are what a discriminator must NOT damage.

Everything outside the D6 population is out of scope for this round: caps-per-word
already separates it, and a discriminator that fires there can only do harm.

Reported before any feature is measured, so the target cannot drift to fit a signal.

    uv run python docs/research/pdf-heading-identity/confounder/population.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "frozen"))

import frozen_candidate as FC  # noqa: E402
from freeze_check import verify  # noqa: E402

RES = Path(__file__).resolve().parents[1] / "results"
OUT = Path(__file__).resolve().parent / "population.json"


def load():
    runs, typo = [], {}
    for rn, tn, tag in (
        ("heading-runs.jsonl", "within-line-typography.jsonl", "dev"),
        ("holdout-runs.jsonl", "holdout-typography.jsonl", "holdout"),
    ):
        for line in (RES / rn).open():
            r = json.loads(line)
            r["corpus"] = tag
            runs.append(r)
        for line in (RES / tn).open():
            r = json.loads(line)
            typo[(r["bill"], r["version"], r["page"], r["line"])] = r["hist"]
    return runs, typo


def truth_of(run):
    g = {}
    for gi, grp in enumerate(run["truth"]):
        for i in grp:
            g[i] = gi
    return [FC.SPLIT if g[i] != g[i + 1] else FC.JOIN for i in range(len(run["texts"]) - 1)]


def main() -> None:
    digest = verify()
    runs, typo = load()
    resolved = [r for r in runs if r["status"] == "resolved" and len(r["texts"]) > 1]

    rows = []
    for r in resolved:
        b, v = r["bill"], r["version"]
        for i, t in enumerate(truth_of(r)):
            cu = FC.caps_per_word(r["texts"][i], typo.get((b, v, r["pages"][i], r["lines"][i])))
            cl = FC.caps_per_word(r["texts"][i + 1], typo.get((b, v, r["pages"][i + 1], r["lines"][i + 1])))
            if cu is None or cl is None:
                continue
            if not (cu < FC.T and cl < FC.T):
                continue  # caps-per-word already separates this boundary
            if r["texts"][i].rstrip().endswith(FC.WRAP_HYPHENS):
                continue  # D4 owns it; a mid-word break is a wrap by construction
            rows.append(
                {
                    "corpus": r["corpus"],
                    "bill": b,
                    "version": v,
                    "page": r["pages"][i],
                    "line": r["lines"][i],
                    "upper": r["texts"][i],
                    "lower": r["texts"][i + 1],
                    "class": "CONFOUNDER" if t == FC.SPLIT else "AT_RISK_WRAP",
                    "caps_upper": cu,
                    "caps_lower": cl,
                    "run_len": len(r["texts"]),
                    "boundary_index": i,
                }
            )

    conf = [x for x in rows if x["class"] == "CONFOUNDER"]
    wrap = [x for x in rows if x["class"] == "AT_RISK_WRAP"]
    print(f"frozen digest: {digest}\nT = {FC.T}\n")
    print(f"D6 population (both lines even small caps): {len(rows)} boundaries")
    print(f"  CONFOUNDER   (truth SPLIT, container over account): {len(conf)}")
    print(f"  AT_RISK_WRAP (truth JOIN, one wrapped account)     : {len(wrap)}")
    print(f"\nby corpus: {Counter(x['corpus'] for x in rows).most_common()}")
    print(f"confounders by corpus: {Counter(x['corpus'] for x in conf).most_common()}")

    print(f"\n=== every distinct CONFOUNDER container/account pair ({len({(x['upper'], x['lower']) for x in conf})}) ===")
    by_pair = defaultdict(list)
    for x in conf:
        by_pair[(x["upper"], x["lower"])].append(x)
    for (u, low), xs in sorted(by_pair.items(), key=lambda kv: -len(kv[1])):
        bills = sorted({f"{x['bill']}/{x['version']}" for x in xs})
        print(f"\n  x{len(xs)}  {u!r}")
        print(f"        + {low!r}")
        print(f"        caps: upper={xs[0]['caps_upper']:.3f} lower={xs[0]['caps_lower']:.3f}")
        print(f"        in: {', '.join(bills)}")

    print(f"\n=== distinct upper (container) strings in the confounder class ===")
    for u, n in Counter(x["upper"] for x in conf).most_common():
        print(f"   x{n:<4} {u!r}")

    print(f"\n=== comparison set: the same container strings appearing as a genuine ACCOUNT leaf ===")
    conf_uppers = {FC.normalize_text(x["upper"]) for x in conf}
    conf_lowers = {FC.normalize_text(x["lower"]) for x in conf}
    leaf_hits = Counter()
    for r in resolved:
        for g in r["truth"]:
            text = FC.normalize_text(FC.join_lines([r["texts"][i] for i in g]))
            if text in conf_uppers:
                leaf_hits[text] += 1
    print(f"   container strings that ALSO occur as a complete logical heading: {len(leaf_hits)}")
    for t, n in leaf_hits.most_common():
        print(f"      x{n:<4} {t!r}")
    print(f"\n   account strings from the confounder pairs, as complete headings elsewhere:")
    leaf_low = Counter()
    for r in resolved:
        for g in r["truth"]:
            text = FC.normalize_text(FC.join_lines([r["texts"][i] for i in g]))
            if text in conf_lowers:
                leaf_low[text] += 1
    for t, n in leaf_low.most_common():
        print(f"      x{n:<4} {t!r}")

    print(f"\n=== AT_RISK_WRAP sample (15 of {len(wrap)}) ===")
    for x in wrap[:15]:
        print(f"   {x['bill']}/{x['version']} p{x['page']}L{x['line']}  caps {x['caps_upper']:.2f}/{x['caps_lower']:.2f}")
        print(f"      {x['upper']!r} + {x['lower']!r}")

    OUT.write_text(json.dumps({"frozen_digest": digest, "T": FC.T, "rows": rows}, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
