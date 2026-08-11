"""B1 validation: does IDF-weighted containment separate same/different on the FULL
corpus, not just the 14 answer-key points? And what are ITS false-keeps?

Over all matched pairs (both sides, text differs) in the corpus we compute word_ratio,
tfidf_cosine, tfidf_contain. Then:

 1. In the raw-ratio DEAD ZONE (word_ratio in [0.35,0.65]) is containment bimodal?
 2. NEW SPLITS: word_ratio >= 0.40 (currently KEPT) but containment < 0.55.
    -> switching to containment would split these. Sample for genuine-different vs false.
 3. NEW KEEPS: word_ratio < 0.40 (currently SPLIT) but containment >= 0.55.
    -> switching would keep these. Sample for genuine-same vs false-keep (containment's
       risk: a short provision whose few weighted tokens coincidentally sit in a longer one).
 4. Report how many decisions change overall and the containment histogram.
"""

from __future__ import annotations

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
_num = re.compile(r"^(\d+)_")
_word = re.compile(r"[a-z0-9]+")
KEEP_C = 0.55  # candidate containment keep threshold


def toks(t):
    return _word.findall(t.lower())


# IDF over corpus
doc_freq = Counter()
n_docs = 0
trees_cache = {}
for d in sorted(BILLS.iterdir()):
    if not d.is_dir():
        continue
    for xml in d.glob("*.xml"):
        try:
            tr = normalize_bill(xml)
        except Exception:
            continue
        trees_cache[str(xml)] = tr
        for node in tr.nodes:
            b = node.body_text.strip()
            if b:
                n_docs += 1
                for t in set(toks(b)):
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
    overlap = sum(min(a[t], b[t]) for t in common)
    denom = min(sum(a.values()), sum(b.values()))
    return overlap / denom if denom else 0.0


def vpairs(d):
    xs = sorted(p for p in d.glob("*.xml") if _num.match(p.stem))
    for a, b in zip(xs, xs[1:]):
        if int(_num.match(b.stem).group(1)) == int(_num.match(a.stem).group(1)) + 1:
            yield a, b


new_splits = []  # kept today, contain<KEEP -> would split
new_keeps = []   # split today, contain>=KEEP -> would keep
deadzone_contain = []
total = 0
for d in sorted(BILLS.iterdir()):
    if not d.is_dir():
        continue
    for xa, xb in vpairs(d):
        ta, tb = trees_cache.get(str(xa)), trees_cache.get(str(xb))
        if ta is None or tb is None:
            continue
        for old, new in match_nodes(ta, tb):
            if old is None or new is None:
                continue
            o, n = _normalize_text(old.body_text), _normalize_text(new.body_text)
            if not o or not n or o == n:
                continue
            total += 1
            wr = text_similarity(o, n)
            c = contain(vec(o), vec(n))
            if 0.35 <= wr <= 0.65:
                deadzone_contain.append(c)
            row = (d.name, xa.stem[:12], xb.stem[:12], round(wr, 3), round(c, 3),
                   "/".join(old.match_path[-2:]), len(o), len(n), o[:70], n[:70])
            if wr >= 0.40 and c < KEEP_C:
                new_splits.append(row)
            if wr < 0.40 and c >= KEEP_C:
                new_keeps.append(row)

print(f"total matched changed pairs: {total}")
print(f"NEW SPLITS (kept today, would split at contain<{KEEP_C}): {len(new_splits)}")
print(f"NEW KEEPS  (split today, would keep at contain>={KEEP_C}): {len(new_keeps)}")

print("\n=== dead-zone (word_ratio 0.35-0.65) containment histogram ===")
h = Counter(int(c * 10) / 10 for c in deadzone_contain)
for b in sorted(h):
    print(f"  contain [{b:.1f},{b+0.1:.1f}): {'#'*h[b]} {h[b]}")
print(f"  (n={len(deadzone_contain)} dead-zone pairs)")

print("\n=== NEW KEEPS — containment's RISK direction (short-side coincidence?) ===")
print("  sample sorted by len(old) ascending (shortest old = highest false-keep risk):")
for r in sorted(new_keeps, key=lambda x: x[6])[:20]:
    print(f"  {r[0]} {r[1]}->{r[2]} wr={r[3]} c={r[4]} [{r[5]}] len {r[6]}->{r[7]}")
    print(f"      OLD: {r[8]}")
    print(f"      NEW: {r[9]}")

print("\n=== NEW SPLITS — sample (should be genuine-different reused slots) ===")
for r in sorted(new_splits, key=lambda x: -x[3])[:12]:
    print(f"  {r[0]} {r[1]}->{r[2]} wr={r[3]} c={r[4]} [{r[5]}] len {r[6]}->{r[7]}")
    print(f"      OLD: {r[8]}")
    print(f"      NEW: {r[9]}")
