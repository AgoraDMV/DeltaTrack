"""B1: rare-token (TF-IDF) similarity vs the raw word-ratio baseline.

Hypothesis (the #171 direction): unrelated provisions that share only appropriations
boilerplate ("None of the funds...", "is amended by striking") are pushed apart by
IDF weighting, while genuinely-same provisions that share rare, specific tokens
(statute citations, program names) stay together. And stub->expanded pairs need
*containment* (is the short doc's weighted content inside the long doc?) not cosine.

We build an IDF model over every provision body in the corpus, then score the 12
answer-key pairs + the two corpus false-split risks (Sec.8144, Sec.253) with:
  - word_ratio      : difflib SequenceMatcher word ratio (current baseline)
  - tfidf_cosine    : cosine of IDF-weighted token vectors (symmetric)
  - tfidf_contain   : IDF-weighted overlap / min-side mass (asymmetric, stub-friendly)
"""

from __future__ import annotations

import json
import math
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
FIXTURE = REPO / "tests" / "data" / "similarity_labels.json"

_word = re.compile(r"[a-z0-9]+")


def toks(text: str) -> list[str]:
    return _word.findall(text.lower())


# --- Build IDF over every provision body in the corpus ------------------------
doc_freq: Counter[str] = Counter()
n_docs = 0
for bill_dir in sorted(BILLS.iterdir()):
    if not bill_dir.is_dir():
        continue
    for xml in bill_dir.glob("*.xml"):
        try:
            tree = normalize_bill(xml)
        except Exception:
            continue
        for node in tree.nodes:
            body = node.body_text.strip()
            if not body:
                continue
            n_docs += 1
            for t in set(toks(body)):
                doc_freq[t] += 1


def idf(t: str) -> float:
    # smoothed idf; unseen token gets max idf
    return math.log((n_docs + 1) / (doc_freq.get(t, 0) + 1)) + 1.0


def tfidf_vec(text: str) -> dict[str, float]:
    tf = Counter(toks(text))
    return {t: (1 + math.log(c)) * idf(t) for t, c in tf.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def containment(a: dict[str, float], b: dict[str, float]) -> float:
    """IDF-weighted overlap normalized by the *smaller* side's mass.
    ~1.0 when the lighter document's weighted content sits inside the heavier one
    (the stub->expanded signature)."""
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    overlap = sum(min(a[t], b[t]) for t in common)
    mass_a = sum(a.values())
    mass_b = sum(b.values())
    denom = min(mass_a, mass_b)
    return overlap / denom if denom else 0.0


def score(t_old: str, t_new: str) -> dict:
    o, n = _normalize_text(t_old), _normalize_text(t_new)
    va, vb = tfidf_vec(o), tfidf_vec(n)
    return {
        "word_ratio": round(text_similarity(o, n), 3),
        "tfidf_cosine": round(cosine(va, vb), 3),
        "tfidf_contain": round(containment(va, vb), 3),
    }


print(f"IDF corpus: {n_docs} provision bodies, {len(doc_freq)} distinct tokens\n")

pairs = json.loads(FIXTURE.read_text())["pairs"]
print(f"{'id':<26} {'label':<10} {'dec':<6} {'word':>6} {'cos':>6} {'contain':>8}")
print("-" * 70)
for p in pairs:
    s = score(p["text_old"], p["text_new"])
    print(f"{p['id']:<26} {p['label']:<10} {p['decision']:<6} "
          f"{s['word_ratio']:>6} {s['tfidf_cosine']:>6} {s['tfidf_contain']:>8}")

# The two corpus false-split risks (genuine edits raw ratio + a 0.60 floor would split)
print("\n--- corpus genuine-edit risk cases (should score SAME/high) ---")
extra = [
    ("118-hr-8774 Sec.8144", "1_reported-in-house", "2_engrossed-in-house", "general provisions", "Sec. 8144"),
    ("118-hr-4366 Sec.253", "3_placed-on-calendar-senate", "4_engrossed-amendment-senate", "administrative provisions", "Sec. 253"),
]
def pick(bill, ver, path_needle, secnum):
    t = normalize_bill(BILLS / bill / f"{ver}.xml")
    for x in t.nodes:
        if x.section_number == secnum and path_needle in " ".join(x.match_path).lower():
            return x.body_text
    return ""
for name, va, vb, pn, sn in extra:
    bill = "118-hr-8774" if "8774" in name else "118-hr-4366"
    o = pick(bill, va, pn, sn)
    n = pick(bill, vb, pn, sn)
    s = score(o, n)
    print(f"{name:<26} {'same?':<10} {'split':<6} {s['word_ratio']:>6} {s['tfidf_cosine']:>6} {s['tfidf_contain']:>8}")
