"""Probe: corpus-wide stability of structural signals + the raised-floor risk.

For every adjacent XML version pair in bills/, run production match_nodes and,
for each MATCHED pair (both sides present), record structural signals. We answer:

A. Header availability by leaf tag: how often is header_text even present?
B. match_path collisions: how many match_paths hold >1 node in a version?
C. match_path stability across a matched pair (renumber rate).
D. THE RAISED-FLOOR RISK: matched section pairs with no structural keep signal
   (bare section, both headers empty, match_path equal) that are currently KEPT
   (body_sim in [0.40, HIGH_KEEP)). Raising the split floor to HIGH_KEEP would
   flip these modified->split. Histogram + samples for eyeball adjudication.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from deltatrack.bill_tree import normalize_bill
from deltatrack.diff_bill import _normalize_text, match_nodes
from deltatrack.similarity import text_similarity

REPO = Path(__file__).resolve().parents[4]
from corpus_roots import merged_root  # noqa: E402
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))
BILLS = merged_root()
ACCOUNT_TAGS = {"appropriations-major", "appropriations-intermediate", "appropriations-small"}
SPLIT_FLOOR = 0.40
HIGH_KEEP = 0.60

_num = re.compile(r"^(\d+)_")


def version_pairs(bill_dir: Path):
    xmls = sorted(p for p in bill_dir.glob("*.xml") if _num.match(p.stem))
    for a, b in zip(xmls, xmls[1:]):
        na = int(_num.match(a.stem).group(1))
        nb = int(_num.match(b.stem).group(1))
        if nb == na + 1:
            yield a, b


# accumulators
hdr_present = Counter()      # tag -> present count
hdr_total = Counter()        # tag -> total
collision_versions = 0
collision_paths_total = 0
version_count = 0
matched_total = 0
matched_modified = 0          # currently kept (body_sim >= 0.40, text differs)
renumbered = 0                # matched but match_path differs (shouldn't happen: match keys on path)
raised_floor_flips = []       # section, no-header, mp-equal, body_sim in [0.40,0.60)
account_lowsim_rescued = []   # account pairs kept below 0.40 by structure (tanker-like)

bills_seen = 0
for bill_dir in sorted(BILLS.iterdir()):
    if not bill_dir.is_dir():
        continue
    pairs = list(version_pairs(bill_dir))
    if not pairs:
        continue
    bills_seen += 1
    for xa, xb in pairs:
        try:
            ta, tb = normalize_bill(xa), normalize_bill(xb)
        except Exception as e:
            print(f"  parse fail {xa.parent.name} {xa.stem}->{xb.stem}: {e}")
            continue
        version_count += 1
        # A. header availability (count over new version nodes)
        for n in tb.nodes:
            hdr_total[n.tag] += 1
            if n.header_text.strip():
                hdr_present[n.tag] += 1
        # B. collisions in new version
        by_path = defaultdict(int)
        for n in tb.nodes:
            by_path[n.match_path] += 1
        ncoll = sum(1 for c in by_path.values() if c > 1)
        if ncoll:
            collision_versions += 1
            collision_paths_total += ncoll
        # C/D. matched pairs
        for old, new in match_nodes(ta, tb):
            if old is None or new is None:
                continue
            matched_total += 1
            o_norm, n_norm = _normalize_text(old.body_text), _normalize_text(new.body_text)
            if o_norm == n_norm:
                continue
            body_sim = text_similarity(o_norm, n_norm)
            if old.match_path != new.match_path:
                renumbered += 1
            if body_sim >= SPLIT_FLOOR:
                matched_modified += 1
            leaf_account = old.tag in ACCOUNT_TAGS and new.tag in ACCOUNT_TAGS
            headers_present = bool(old.header_text.strip()) and bool(new.header_text.strip())
            mp_equal = old.match_path == new.match_path
            # D: raised-floor flips (currently kept, would split at 0.60, no struct signal)
            if (not leaf_account and not headers_present and mp_equal
                    and SPLIT_FLOOR <= body_sim < HIGH_KEEP):
                raised_floor_flips.append((
                    bill_dir.name, xa.stem, xb.stem, round(body_sim, 3),
                    old.tag, "/".join(old.match_path[-2:]),
                    o_norm[:90], n_norm[:90],
                ))
            # account pairs rescued below the current floor (structure keeps them)
            if leaf_account and mp_equal and body_sim < SPLIT_FLOOR:
                account_lowsim_rescued.append((
                    bill_dir.name, round(body_sim, 3), "/".join(old.match_path[-2:]),
                ))

print(f"bills with >=2 adjacent versions: {bills_seen}")
print(f"adjacent version pairs analyzed:  {version_count}")
print(f"total matched pairs:              {matched_total}")
print(f"matched & currently modified:     {matched_modified}")
print(f"matched pairs w/ changed path:    {renumbered}")
print(f"versions with >=1 collision path: {collision_versions}")
print(f"total colliding paths:            {collision_paths_total}")

print("\n=== A. header availability by leaf tag ===")
for tag in sorted(hdr_total, key=lambda t: -hdr_total[t]):
    tot, pres = hdr_total[tag], hdr_present[tag]
    print(f"  {tag:<28} {pres:>6}/{tot:<6} ({pres/tot*100:5.1f}% have a header)")

print(f"\n=== D. RAISED-FLOOR RISK: section pairs currently KEPT that 0.60 floor would SPLIT ===")
print(f"count: {len(raised_floor_flips)}")
# histogram
buckets = Counter()
for row in raised_floor_flips:
    b = int(row[3] * 20) / 20  # 0.05 buckets
    buckets[b] += 1
for b in sorted(buckets):
    print(f"  body_sim [{b:.2f},{b+0.05:.2f}): {'#'*buckets[b]} {buckets[b]}")
print("  --- samples (bill, v_old, v_new, sim, tag, path-tail, old90, new90) ---")
for row in sorted(raised_floor_flips, key=lambda r: r[3])[:25]:
    print(f"  {row[0]} {row[1][:14]}->{row[2][:14]} sim={row[3]} {row[4]} [{row[5]}]")
    print(f"      OLD: {row[6]}")
    print(f"      NEW: {row[7]}")

print(f"\n=== account pairs kept below 0.40 by structure (tanker-like rescues) ===")
print(f"count: {len(account_lowsim_rescued)}")
for row in sorted(account_lowsim_rescued, key=lambda r: r[1])[:15]:
    print(f"  {row[0]} sim={row[1]} [{row[2]}]")
