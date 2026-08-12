"""B2: complementary multi-signal text rule vs single-threshold baseline.

Finding from B1: word_ratio and IDF-containment cover each other's blind spots.
  - word_ratio  : high for similar-length edits & amount-only changes; low for stub->expanded
  - containment : ~1.0 for stub->expanded; low for boilerplate-only overlap; but tanks on
                  short amount-only edits, and over-keeps short-in-large coincidences

Candidate rule (SPLIT decision):  keep if  word_ratio >= W  OR  containment >= C   else split.
We evaluate on the 12 #8 labels (ground truth) with leave-one-out, and census the
corpus-wide decision changes vs the current 0.40 word-ratio floor.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from deltatrack.bill_tree import normalize_bill
from deltatrack.diff_bill import _normalize_text, match_nodes
from deltatrack.similarity import text_similarity

REPO = Path(__file__).resolve().parents[4]
from corpus_roots import merged_root  # noqa: E402
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))
BILLS = merged_root()
FIXTURE = REPO / "tests" / "data" / "similarity_labels.json"
_num = re.compile(r"^(\d+)_")
_word = re.compile(r"[a-z0-9]+")
W, C = 0.50, 0.70  # candidate thresholds


def toks(t):
    return _word.findall(t.lower())


doc_freq = Counter()
n_docs = 0
trees = {}
for d in sorted(BILLS.iterdir()):
    if not d.is_dir():
        continue
    for xml in d.glob("*.xml"):
        try:
            tr = normalize_bill(xml)
        except Exception:
            continue
        trees[str(xml)] = tr
        for node in tr.nodes:
            if node.body_text.strip():
                n_docs += 1
                for t in set(toks(node.body_text)):
                    doc_freq[t] += 1


def idf(t):
    return math.log((n_docs + 1) / (doc_freq.get(t, 0) + 1)) + 1.0


def vec(text):
    tf = Counter(toks(text))
    return {t: (1 + math.log(c)) * idf(t) for t, c in tf.items()}


def contain(a, b):
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    ov = sum(min(a[t], b[t]) for t in common)
    dn = min(sum(a.values()), sum(b.values()))
    return ov / dn if dn else 0.0


def signals(o, n):
    o, n = _normalize_text(o), _normalize_text(n)
    return text_similarity(o, n), contain(vec(o), vec(n))


def rule_keep(wr, c, decision="split", w=W, cc=C):
    # SPLIT: word_ratio rescues amount-only short edits; containment catches stub->expanded.
    # MOVE:  containment only — a relocation is genuine only if the boilerplate-discounted
    #        content really matches (word_ratio would be fooled by shared "amended by striking").
    if decision == "move":
        return c >= cc
    return wr >= w or c >= cc


# --- evaluate on the 12 labels ---
pairs = json.loads(FIXTURE.read_text())["pairs"]
print("=== 12 #8 labels: two-signal rule (keep if wr>=%.2f OR contain>=%.2f) ===" % (W, C))
correct = 0
rows = []
for p in pairs:
    wr, c = signals(p["text_old"], p["text_new"])
    pred = "same" if rule_keep(wr, c, p["decision"]) else "different"
    ok = pred == p["label"]
    correct += ok
    rows.append((p["id"], p["label"], p["decision"], round(wr, 3), round(c, 3), pred, ok))
    print(f"  {p['id']:<26} {p['label']:<10} {p['decision']:<6} wr={wr:<6.3f} c={c:<6.3f} -> {pred:<10} {'OK' if ok else 'XX'}")
print(f"  total: {correct}/12")

# --- leave-one-out: re-pick best (W,C) on the other 11, test on held-out ---
print("\n=== leave-one-out robustness (grid search W,C on the other 11) ===")
grid_w = [round(x, 2) for x in [i / 100 for i in range(40, 71, 2)]]
grid_c = [round(x, 2) for x in [i / 100 for i in range(50, 91, 2)]]
loo_correct = 0
for i, held in enumerate(pairs):
    train = [p for j, p in enumerate(pairs) if j != i]
    best, best_acc = (W, C), -1
    for w in grid_w:
        for cc in grid_c:
            acc = sum(("same" if rule_keep(*signals(p["text_old"], p["text_new"]), p["decision"], w, cc) else "different") == p["label"] for p in train)
            if acc > best_acc:
                best, best_acc = (w, cc), acc
    wr, c = signals(held["text_old"], held["text_new"])
    pred = "same" if rule_keep(wr, c, held["decision"], *best) else "different"
    loo_correct += pred == held["label"]
print(f"  leave-one-out accuracy: {loo_correct}/12  (thresholds re-fit on the other 11 each time)")

# --- corpus census: decisions changed vs the 0.40 word-ratio floor ---
def vpairs(d):
    xs = sorted(p for p in d.glob("*.xml") if _num.match(p.stem))
    for a, b in zip(xs, xs[1:]):
        if int(_num.match(b.stem).group(1)) == int(_num.match(a.stem).group(1)) + 1:
            yield a, b


to_split, to_keep = [], []
total = 0
for d in sorted(BILLS.iterdir()):
    if not d.is_dir():
        continue
    for xa, xb in vpairs(d):
        ta, tb = trees.get(str(xa)), trees.get(str(xb))
        if not ta or not tb:
            continue
        for old, new in match_nodes(ta, tb):
            if old is None or new is None:
                continue
            o, n = _normalize_text(old.body_text), _normalize_text(new.body_text)
            if not o or not n or o == n:
                continue
            total += 1
            wr, c = text_similarity(o, n), contain(vec(o), vec(n))
            base_keep = wr >= 0.40
            new_keep = rule_keep(wr, c, "split")
            row = (d.name, round(wr, 3), round(c, 3), "/".join(old.match_path[-2:]), len(o), len(n), o[:75], n[:75])
            if base_keep and not new_keep:
                to_split.append(row)
            elif not base_keep and new_keep:
                to_keep.append(row)
print(f"\n=== corpus census (SPLIT decision vs 0.40 word-ratio floor), {total} matched changed pairs ===")
print(f"  -> now SPLIT (was keep): {len(to_split)}")
print(f"  -> now KEEP  (was split): {len(to_keep)}")
print(f"  net decisions changed:   {len(to_split) + len(to_keep)}")
print("\n--- ALL new SPLITS (was keep -> now split): genuine reused-slot?  ---")
for r in sorted(to_split, key=lambda x: -x[1]):
    print(f"  {r[0]} wr={r[1]} c={r[2]} [{r[3]}] len {r[4]}->{r[5]}")
    print(f"      OLD: {r[6]}\n      NEW: {r[7]}")
print("\n--- ALL new KEEPS (was split -> now keep): genuine same-provision?  ---")
for r in sorted(to_keep, key=lambda x: x[4]):
    print(f"  {r[0]} wr={r[1]} c={r[2]} [{r[3]}] len {r[4]}->{r[5]}")
    print(f"      OLD: {r[6]}\n      NEW: {r[7]}")
