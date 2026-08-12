"""Adversarial checks on the two proposed structural keep/gate rules.

R1 (header-match keep): would keep a matched pair as `modified` when both headers
   are present and match, even if body_sim < 0.40. RISK = false keep: two different
   provisions that merely share a header/catchline. Enumerate matched pairs with
   header match AND body_sim < 0.40 (currently SPLIT). Are they genuine same-provision?

R2 (parent-path move gate): would only rescue removed+added as `moved` when parent
   match_path matches OR header matches. RISK = suppress a genuine cross-subtree move.
   Enumerate current `moved` results whose parent path AND header both differ (the
   gate would demote them back to removed+added). Are any genuine relocations?
"""

from __future__ import annotations

import re
from pathlib import Path

from deltatrack.bill_tree import normalize_bill, normalize_header
from deltatrack.diff_bill import (
    _normalize_text,
    diff_bills,
    match_nodes,
)
from deltatrack.similarity import text_similarity  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
from corpus_roots import merged_root  # noqa: E402
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))
BILLS = merged_root()
ACCOUNT_TAGS = {"appropriations-major", "appropriations-intermediate", "appropriations-small"}
_num = re.compile(r"^(\d+)_")


def version_pairs(bill_dir: Path):
    xmls = sorted(p for p in bill_dir.glob("*.xml") if _num.match(p.stem))
    for a, b in zip(xmls, xmls[1:]):
        if int(_num.match(b.stem).group(1)) == int(_num.match(a.stem).group(1)) + 1:
            yield a, b


def hsim(a, b):
    if not a or not b:
        return 0.0
    return text_similarity(normalize_header(a), normalize_header(b))


r1_false_keep_candidates = []  # header match, body_sim<0.40, section (not account)
r2_gate_demotions = []          # moved but parent!=parent and headers don't match

for bill_dir in sorted(BILLS.iterdir()):
    if not bill_dir.is_dir():
        continue
    for xa, xb in version_pairs(bill_dir):
        try:
            ta, tb = normalize_bill(xa), normalize_bill(xb)
        except Exception:
            continue
        # R1: over matched pairs
        for old, new in match_nodes(ta, tb):
            if old is None or new is None:
                continue
            o, n = _normalize_text(old.body_text), _normalize_text(new.body_text)
            if o == n:
                continue
            sim = text_similarity(o, n)
            if sim >= 0.40:
                continue
            leaf_account = old.tag in ACCOUNT_TAGS and new.tag in ACCOUNT_TAGS
            if leaf_account:
                continue  # account rescue is separately validated (durable identity)
            if old.header_text.strip() and new.header_text.strip() and hsim(old.header_text, new.header_text) >= 0.8:
                r1_false_keep_candidates.append((
                    bill_dir.name, xa.stem[:12], xb.stem[:12], round(sim, 3),
                    old.header_text, "/".join(old.match_path[-2:]),
                    o[:80], n[:80],
                ))
        # R2: over final diff moves
        d = diff_bills(ta, tb)
        # build lookup of node header by (match_path)+role via the moved entries themselves
        for c in d.changes:
            if c.change_type != "moved":
                continue
            po = tuple(c.display_path_old or ())
            pn = tuple(c.display_path_new or ())
            # reconstruct match parent from match_path (leaf dropped)
            parent = c.match_path[:-1]
            # find the old/new nodes to read headers
            # (match on body text)
            def find(t, txt):
                tgt = _normalize_text(txt or "")
                for x in t.nodes:
                    if _normalize_text(x.body_text) == tgt:
                        return x
                return None
            no = find(ta, c.old_text)
            nn = find(tb, c.new_text)
            if no is None or nn is None:
                continue
            parent_equal = no.match_path[:-1] == nn.match_path[:-1]
            header_match = no.header_text.strip() and nn.header_text.strip() and hsim(no.header_text, nn.header_text) >= 0.8
            sim = text_similarity(_normalize_text(c.old_text or ""), _normalize_text(c.new_text or ""))
            if not parent_equal and not header_match:
                r2_gate_demotions.append((
                    bill_dir.name, round(sim, 3),
                    "/".join(no.match_path), "/".join(nn.match_path),
                    no.header_text, nn.header_text,
                    _normalize_text(c.old_text or "")[:70],
                ))

print("=== R1: header-match keeps that would OVERRIDE a split (body_sim<0.40) ===")
print(f"count: {len(r1_false_keep_candidates)}")
for row in sorted(r1_false_keep_candidates, key=lambda r: r[3]):
    print(f"  {row[0]} {row[1]}->{row[2]} sim={row[3]} header={row[4]!r} [{row[5]}]")
    print(f"      OLD: {row[6]}")
    print(f"      NEW: {row[7]}")

print("\n=== R2: current MOVES the parent-path/header gate would DEMOTE to removed+added ===")
print(f"count: {len(r2_gate_demotions)}")
for row in sorted(r2_gate_demotions, key=lambda r: -r[1]):
    print(f"  {row[0]} sim={row[1]}  {row[2]}  ->  {row[3]}")
    print(f"      hdr {row[4]!r} -> {row[5]!r}   old: {row[6]}")
