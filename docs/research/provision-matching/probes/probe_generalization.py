"""Generalization probe — directly addresses the overfitting concern.

Two honest tests, harder than leave-one-pair-out:

 1. LEAVE-ONE-BILL-OUT: hold out ALL pairs from one bill, fit the two thresholds on the
    other three bills' pairs, test on the held-out bill. This simulates "a new bill we've
    never labeled". 4 folds (114-hr-2029, 115-hr-5895, 118-hr-4366, 119-hr-1).

 2. IDF TRANSFER: rebuild the IDF corpus EXCLUDING the held-out bill's own family, so the
    rare-token weights can't have "seen" that bill. Does containment still separate its pairs?

 3. BY-BILL-TYPE separation: containment distribution on the reconciliation bill (119-hr-1,
    the structurally-degraded outlier) vs the appropriations bills. Tests whether the measure
    is appropriations-specific.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from itertools import product
from pathlib import Path

from deltatrack.bill_tree import normalize_bill
from deltatrack.diff_bill import _normalize_text
from deltatrack.similarity import text_similarity

REPO = Path(__file__).resolve().parents[4]
from corpus_roots import merged_root  # noqa: E402
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))
BILLS = merged_root()
FIXTURE = REPO / "tests" / "data" / "similarity_labels.json"
_word = re.compile(r"[a-z0-9]+")


def toks(t):
    return _word.findall(t.lower())


def build_idf(exclude_bill: str | None = None):
    df, n = Counter(), 0
    for d in sorted(BILLS.iterdir()):
        if not d.is_dir() or d.name == exclude_bill:
            continue
        for xml in d.glob("*.xml"):
            try:
                tr = normalize_bill(xml)
            except Exception:
                continue
            for node in tr.nodes:
                if node.body_text.strip():
                    n += 1
                    for t in set(toks(node.body_text)):
                        df[t] += 1
    return df, n


def vec(text, df, n):
    tf = Counter(toks(text))
    return {t: (1 + math.log(c)) * (math.log((n + 1) / (df.get(t, 0) + 1)) + 1.0) for t, c in tf.items()}


def contain(a, b):
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    ov = sum(min(a[t], b[t]) for t in common)
    dn = min(sum(a.values()), sum(b.values()))
    return ov / dn if dn else 0.0


pairs = json.loads(FIXTURE.read_text())["pairs"]
full_df, full_n = build_idf()


def sig(p, df, n):
    o, nw = _normalize_text(p["text_old"]), _normalize_text(p["text_new"])
    return text_similarity(o, nw), contain(vec(o, df, n), vec(nw, df, n))


def keep(wr, c, decision, W, C):
    return c >= C if decision == "move" else (wr >= W or c >= C)


# --- Test 1+2: leave-one-BILL-out, with IDF also excluding that bill ---
print("=== LEAVE-ONE-BILL-OUT (fit thresholds on other bills, IDF excludes held-out bill) ===")
gridW = [i / 100 for i in range(40, 71, 5)]
gridC = [i / 100 for i in range(50, 91, 5)]
bills = sorted({p["bill"] for p in pairs})
loo_correct, loo_total = 0, 0
for held in bills:
    train = [p for p in pairs if p["bill"] != held]
    test = [p for p in pairs if p["bill"] == held]
    # IDF excluding the held-out bill entirely (transfer test)
    df_x, n_x = build_idf(exclude_bill=held)
    # fit thresholds on train (using full IDF for train signals is fine; they're not held out)
    best, bestacc = (0.5, 0.7), -1
    for W, C in product(gridW, gridC):
        acc = sum(("same" if keep(*sig(p, full_df, full_n), p["decision"], W, C) else "different") == p["label"] for p in train)
        if acc > bestacc:
            best, bestacc = (W, C), acc
    W, C = best
    fold_ok = 0
    for p in test:
        wr, c = sig(p, df_x, n_x)  # test signals use IDF that never saw this bill
        pred = "same" if keep(wr, c, p["decision"], W, C) else "different"
        ok = pred == p["label"]
        fold_ok += ok
        loo_correct += ok
        loo_total += 1
        print(f"  [{held}] {p['id']:<24} truth={p['label']:<10} wr={wr:.3f} c={c:.3f} pred={pred:<10} {'OK' if ok else 'XX'}")
    print(f"    -> fold thresholds W={W:.2f} C={C:.2f}, {fold_ok}/{len(test)} correct\n")
print(f"LEAVE-ONE-BILL-OUT total: {loo_correct}/{loo_total}")

# --- Test 3: containment separation by bill type ---
print("\n=== containment on the held-out-IDF signals, grouped by bill ===")
for b in bills:
    ps = [p for p in pairs if p["bill"] == b]
    df_x, n_x = build_idf(exclude_bill=b)
    same_c = [round(sig(p, df_x, n_x)[1], 2) for p in ps if p["label"] == "same"]
    diff_c = [round(sig(p, df_x, n_x)[1], 2) for p in ps if p["label"] == "different"]
    kind = "reconciliation" if b == "119-hr-1" else "appropriations"
    print(f"  {b:<14} ({kind:<15}) same-pairs c={sorted(same_c, reverse=True)}  diff-pairs c={sorted(diff_c, reverse=True)}")
