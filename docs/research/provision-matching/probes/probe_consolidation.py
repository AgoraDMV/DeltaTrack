"""Hard-case stress test: 119-hr-1 v3 (placed-on-calendar-senate) vs v4 (engrossed-amendment-senate).

This is the Senate rewrite/consolidation: sections renumbered, much text recycled. (The
v4->v5 enrolled step is nearly identical; the churn is at v3->v4, which then carries into v5.)
Because match_path bakes in the section number, renumbering breaks the join -> the current
matcher should show a flood of removed+added, with reconcile_moves (word-overlap >= 0.6)
rescuing only some. We test whether rare-token containment re-pairs the recycled-but-
renumbered sections the current word-overlap rescue misses.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from deltatrack.bill_tree import normalize_bill
from deltatrack.diff_bill import _normalize_text, diff_bills
from deltatrack.similarity import text_similarity

REPO = Path(__file__).resolve().parents[4]
from corpus_roots import merged_root  # noqa: E402
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))
BILLS = merged_root()
_word = re.compile(r"[a-z0-9]+")


def toks(t):
    return _word.findall(t.lower())


# IDF over corpus
df, n_docs = Counter(), 0
for d in sorted(BILLS.iterdir()):
    if not d.is_dir():
        continue
    for xml in d.glob("*.xml"):
        try:
            tr = normalize_bill(xml)
        except Exception:
            continue
        for node in tr.nodes:
            if node.body_text.strip():
                n_docs += 1
                for t in set(toks(node.body_text)):
                    df[t] += 1


def vec(text):
    tf = Counter(toks(text))
    return {t: (1 + math.log(c)) * (math.log((n_docs + 1) / (df.get(t, 0) + 1)) + 1.0) for t, c in tf.items()}


def contain(a, b):
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    ov = sum(min(a[t], b[t]) for t in common)
    dn = min(sum(a.values()), sum(b.values()))
    return ov / dn if dn else 0.0


v4 = normalize_bill(BILLS / "119-hr-1" / "3_placed-on-calendar-senate.xml")
v5 = normalize_bill(BILLS / "119-hr-1" / "4_engrossed-amendment-senate.xml")
print(f"v4 nodes: {len(v4.nodes)}   v5 nodes: {len(v5.nodes)}")

diff = diff_bills(v4, v5)
print(f"\ncurrent diff_bills summary: {diff.summary}")

removed = [c for c in diff.changes if c.change_type == "removed" and (c.old_text or "").strip()]
added = [c for c in diff.changes if c.change_type == "added" and (c.new_text or "").strip()]
moved = [c for c in diff.changes if c.change_type == "moved"]
print(f"removed w/ text: {len(removed)}   added w/ text: {len(added)}   already moved: {len(moved)}")

# Re-pair the removed<->added set. For each removed, find its best added by word-overlap and
# by containment. Count how many high-confidence recycled pairs each measure finds that the
# current move-rescue (word-overlap>=0.6) did NOT already capture (these are removed/added).
print("\n=== re-pairing the unmatched removed<->added set (the renumbered/recycled provisions) ===")
rem_v = [(c, _normalize_text(c.old_text or "")) for c in removed]
add_v = [(c, _normalize_text(c.new_text or "")) for c in added]
rem_vec = [(c, o, vec(o)) for c, o in rem_v]
add_vec = [(c, nw, vec(nw)) for c, nw in add_v]

wr_hits = 0  # best word-overlap >= 0.6 (what reconcile_moves would catch, but these are leftovers)
c_hits = 0  # best containment >= 0.7
c_only = []  # containment finds a strong pair that word-overlap misses (< 0.6)
for rc, ro, rv in rem_vec:
    best_wr = best_c = 0.0
    best_wr_pair = best_c_pair = None
    for ac, ao, av in add_vec:
        wr = text_similarity(ro, ao)
        c = contain(rv, av)
        if wr > best_wr:
            best_wr, best_wr_pair = wr, ac
        if c > best_c:
            best_c, best_c_pair = c, ac
    if best_wr >= 0.6:
        wr_hits += 1
    if best_c >= 0.7:
        c_hits += 1
    if best_c >= 0.7 and best_wr < 0.6:
        c_only.append((rc, best_c, best_wr, best_c_pair))

print(f"leftover removed provisions: {len(rem_vec)}")
print(f"  re-pairable by word-overlap >= 0.6:  {wr_hits}")
print(f"  re-pairable by containment  >= 0.7:  {c_hits}")
print(f"  found by containment but MISSED by word-overlap (<0.6): {len(c_only)}")

# --- fan-in: how many recovered old provisions map to the SAME new section? ---
# A clean 1:1 "move" maps one old -> one new. Many old provisions mapping to one new
# section is either genuine consolidation OR the containment false-keep artifact
# (several short old provisions each containing into one large/short new section via a
# shared statute citation). This grouping is what distinguishes the two counts; the
# metric alone cannot tell them apart, so we report the split, not a "recovered" total.
by_target = Counter()
reverse_dir = 0  # new section SHORTER than old provision -> short-new-in-long-old, artifact-prone
for rc, bc, bwr, ac in c_only:
    by_target[tuple(ac.match_path)] += 1
    if len((ac.new_text or "")) < len((rc.old_text or "")):
        reverse_dir += 1
distinct_targets = len(by_target)
one_to_one = sum(1 for v in by_target.values() if v == 1)
many_to_one_targets = sum(1 for v in by_target.values() if v > 1)
absorbed = sum(v for v in by_target.values() if v > 1)
max_fan_in = max(by_target.values()) if by_target else 0
print(f"\n  fan-in of the {len(c_only)} containment recoveries:")
print(f"    distinct new sections they map to:        {distinct_targets}")
print(f"    clean one-to-one (one old -> one new):    {one_to_one}")
print(f"    many-to-one target sections:              {many_to_one_targets}")
print(f"    old provisions inside a many-to-one group: {absorbed} ({absorbed / len(c_only):.0%} of recoveries)")
print(f"    largest fan-in (old provisions -> 1 new):  {max_fan_in}")
print(f"    reverse-direction (new shorter than old, artifact-prone): {reverse_dir}")

print("\n  sample recycled pairs containment recovers that word-overlap misses:")
for rc, bc, bwr, ac in sorted(c_only, key=lambda x: -x[1])[:12]:
    r_tail = rc.match_path[-1] if rc.match_path else "?"
    a_tail = ac.match_path[-1] if ac and ac.match_path else "?"
    print(f"    {r_tail} -> {a_tail}   containment={bc:.3f}  word-overlap={bwr:.3f}")
    print(f"        OLD: {(rc.old_text or '')[:80]}")
    print(f"        NEW: {(ac.new_text or '')[:80] if ac else ''}")
