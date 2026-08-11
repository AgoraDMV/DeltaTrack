"""Probe: the 119-hr-1 Alien SNAP / Emergency food collision, end-to-end.

reported-in-house -> engrossed-in-house. Committee on Agriculture > Nutrition
holds two distinct Sec. 10012 sharing a match_path. Engrossed renumbers the
Emergency-food one to 10013. We (1) show the current collision-group resolution
and the inverted similarity, (2) show current diff_bills output for these nodes,
(3) show that header equality picks the correct pairing.
"""

from __future__ import annotations

from pathlib import Path

from deltatrack.bill_tree import normalize_bill, normalize_header
from deltatrack.diff_bill import _match_collision_group, _normalize_text, diff_bills
from deltatrack.similarity import text_similarity

REPO = Path(__file__).resolve().parents[4]
ta = normalize_bill(REPO / "bills/119-hr-1/1_reported-in-house.xml")
tb = normalize_bill(REPO / "bills/119-hr-1/2_engrossed-in-house.xml")

# Find nutrition sections around 10012/10013
def nutrition_secs(t, nums):
    out = []
    for n in t.nodes:
        if "nutrition" in " ".join(n.match_path).lower() and n.section_number in nums:
            out.append(n)
    return out

nums = {"Sec. 10012", "Sec. 10013"}
old_secs = nutrition_secs(ta, nums)
new_secs = nutrition_secs(tb, nums)

print("=== OLD (reported) Nutrition sections 10012/10013 ===")
for n in old_secs:
    print(f"  {n.section_number}  header={n.header_text!r}  mp={list(n.match_path)}  len={len(n.body_text)}")
print("=== NEW (engrossed) Nutrition sections 10012/10013 ===")
for n in new_secs:
    print(f"  {n.section_number}  header={n.header_text!r}  mp={list(n.match_path)}  len={len(n.body_text)}")

# The collision: nodes sharing match_path ['committee on agriculture','nutrition','sec. 10012']
mp10012 = ("committee on agriculture", "nutrition", "sec. 10012")
old_coll = [n for n in ta.nodes if n.match_path == mp10012]
new_coll = [n for n in tb.nodes if n.match_path == mp10012]
print(f"\nold nodes @ sec.10012 path: {len(old_coll)}  |  new nodes @ sec.10012 path: {len(new_coll)}")

print("\n=== pairwise body similarity within the collision candidates (old x new@10012 + new@10013) ===")
new_cands = new_secs  # both 10012 and 10013 in engrossed are candidates for the old 10012s
for o in old_coll:
    for n in new_cands:
        sim = text_similarity(_normalize_text(o.body_text), _normalize_text(n.body_text))
        hdr = text_similarity(normalize_header(o.header_text), normalize_header(n.header_text)) if (o.header_text and n.header_text) else 0.0
        print(f"  OLD[{o.header_text!r}] x NEW[{n.section_number} {n.header_text!r}]  body_sim={sim:.3f}  hdr_sim={hdr:.3f}")

print("\n=== current _match_collision_group result (body-similarity only) ===")
pairs = _match_collision_group(old_coll, new_coll)
for o, n in pairs:
    print(f"  {o.header_text if o else None!r} -> {n.header_text if n else None!r}")

print("\n=== header-based pairing (proposed) ===")
# Greedy by header equality
def header_pair(olds, news):
    used=set(); res=[]
    for o in olds:
        match=None
        for i,n in enumerate(news):
            if i in used: continue
            if normalize_header(o.header_text)==normalize_header(n.header_text) and o.header_text:
                match=(i,n); break
        if match:
            used.add(match[0]); res.append((o,match[1]))
        else:
            res.append((o,None))
    return res
for o,n in header_pair(old_coll, new_secs):
    print(f"  {o.header_text!r} -> {(n.section_number, n.header_text) if n else None}")

print("\n=== current diff_bills change_type for these provisions ===")
d = diff_bills(ta, tb)
for c in d.changes:
    tail = c.match_path[-1] if c.match_path else ""
    if tail in ("sec. 10012", "sec. 10013") and "nutrition" in " ".join(c.match_path).lower():
        print(f"  {c.change_type:<10} mp={list(c.match_path)}  old_len={len(c.old_text or '')} new_len={len(c.new_text or '')}")
