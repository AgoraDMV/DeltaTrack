"""ADVERSARIAL REVIEW: false-positive rate of containment>=0.7 for SHORT provisions.

Design: pair SHORT provisions (<=200 chars) from one bill against LONG provisions
(>=800 chars) drawn from a DIFFERENT bill. Cross-bill + different length class means
the overwhelming majority are genuinely DIFFERENT provisions (no shared identity).
If containment>=0.7 fires often on these random cross-bill pairs, the metric is
trivially gameable on the short side.

We report:
  - the base rate of containment>=0.7 among random short/long cross-bill pairs
  - the same for word_ratio>=0.5 (baseline) as a comparison
  - a stratified view by whether the short side carries a statute citation
    ("Section ... of the ... Act", "U.S.C.") -- the paper's own rare-token driver
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter
from pathlib import Path

from deltatrack.bill_tree import normalize_bill
from deltatrack.diff_bill import _normalize_text
from deltatrack.similarity import text_similarity

REPO = Path(__file__).resolve().parents[4]
from corpus_roots import merged_root  # noqa: E402
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))
BILLS = merged_root()
_word = re.compile(r"[a-z0-9]+")
_cite = re.compile(r"u\.s\.c\.|\bsection\s+\d|\bact of \d{4}|\bpublic law", re.I)


def toks(t):
    return _word.findall(t.lower())


doc_freq = Counter()
n_docs = 0
# collect bodies keyed by bill
short_by_bill: dict[str, list[str]] = {}
long_by_bill: dict[str, list[str]] = {}
for d in sorted(BILLS.iterdir()):
    if not d.is_dir():
        continue
    seen = set()
    for xml in d.glob("*.xml"):
        try:
            tr = normalize_bill(xml)
        except Exception:
            continue
        for node in tr.nodes:
            b = node.body_text.strip()
            if not b:
                continue
            n_docs += 1
            for t in set(toks(b)):
                doc_freq[t] += 1
            nb = _normalize_text(b)
            if nb in seen:
                continue
            seen.add(nb)
            L = len(nb)
            if L <= 200:
                short_by_bill.setdefault(d.name, []).append(nb)
            elif L >= 800:
                long_by_bill.setdefault(d.name, []).append(nb)


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


bills = sorted(set(short_by_bill) & set(long_by_bill))
random.seed(42)
N = 4000
c_ge_07 = 0
wr_ge_05 = 0
c_ge_07_cited = 0
n_cited = 0
best_examples = []
n = 0
for _ in range(N):
    ba = random.choice([b for b in short_by_bill if short_by_bill[b]])
    bb = random.choice([b for b in long_by_bill if b != ba])
    if not bb:
        continue
    s = random.choice(short_by_bill[ba])
    lg = random.choice(long_by_bill[bb])
    c = contain(vec(s), vec(lg))
    wr = text_similarity(s, lg)
    n += 1
    cited = bool(_cite.search(s))
    if cited:
        n_cited += 1
    if c >= 0.7:
        c_ge_07 += 1
        if cited:
            c_ge_07_cited += 1
        if len(best_examples) < 12:
            best_examples.append((round(c, 3), round(wr, 3), ba, bb, s[:90], lg[:90]))
    if wr >= 0.5:
        wr_ge_05 += 1

print(
    f"corpus: {n_docs} bodies; {sum(len(v) for v in short_by_bill.values())} short(<=200), "
    f"{sum(len(v) for v in long_by_bill.values())} long(>=800)"
)
print(f"random CROSS-BILL short/long pairs sampled: {n}  ({n_cited} have a statute citation on the short side)\n")
print(f"  containment >= 0.70 (the paper's keep bar):  {c_ge_07}/{n} = {c_ge_07 / n:.1%}")
print(f"     of those, short side had a statute citation: {c_ge_07_cited}/{c_ge_07 if c_ge_07 else 1}")
_pct = c_ge_07_cited / max(n_cited, 1)
print(f"  containment>=0.70 | short side is a citation:  {c_ge_07_cited}/{n_cited} = {_pct:.1%}")
print(f"  word_ratio  >= 0.50 (baseline keep bar):     {wr_ge_05}/{n} = {wr_ge_05 / n:.1%}")
print("\n  sample spurious cross-bill high-containment pairs (DIFFERENT provisions):")
for c, wr, ba, bb, s, lg in sorted(best_examples, reverse=True):
    print(f"    c={c} wr={wr}  [{ba} short] x [{bb} long]")
    print(f"        SHORT: {s}")
    print(f"        LONG:  {lg}")
