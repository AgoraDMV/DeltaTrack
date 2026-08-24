"""How much would carrying unchanged nodes cost the canonical document?

Two ways to let a consumer answer "which nodes did not change":
  A. add unchanged entries to the `changes` array (what --include-unchanged does
     today on the internal dict shape)
  B. give each `tree` node an id and reference it from a change, so unchanged is
     derivable by subtraction

This measures A, and reports what the tree already carries for B.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import bill_diff_to_dict, diff_bills, filter_diff  # noqa: E402
from deltatrack.formatters.canonical import xml_diff_to_canonical  # noqa: E402
from deltatrack.formatters.text_serializer import build_xml_full_text  # noqa: E402

PAIRS = [
    ("118-hr-8752", "1_reported-in-house", "2_engrossed-in-house"),
    ("118-hr-4366", "1_reported-in-house", "6_enrolled-bill"),
]


def count_tree(nodes):
    return sum(1 + count_tree(n.get("children") or []) for n in nodes)


for bill, v1, v2 in PAIRS:
    d = ROOT / "tests" / "corpus" / bill
    old, new = normalize_bill(d / f"{v1}.xml"), normalize_bill(d / f"{v2}.xml")
    raw = diff_bills(old, new)

    changed = filter_diff(raw, include_unchanged=False)
    allnodes = filter_diff(raw, include_unchanged=True)

    full_text, spans, tree = build_xml_full_text(old, new)
    canon = xml_diff_to_canonical(
        bill_diff_to_dict(changed, financial=True), full_text=full_text, full_text_spans=spans, tree=tree
    )
    baseline = len(json.dumps(canon))

    # Option A: what the document would look like carrying unchanged entries too.
    with_unchanged = xml_diff_to_canonical(
        bill_diff_to_dict(allnodes, financial=True), full_text=full_text, full_text_spans=spans, tree=tree
    )
    # xml_diff_to_canonical filters unchanged out, so emulate A by not filtering.
    dict_all = bill_diff_to_dict(allnodes, financial=True)
    n_changed = len(canon["changes"])
    n_all = len(dict_all["changes"])
    n_unchanged = n_all - n_changed

    # Size of the changes array alone, per node, to project option A.
    changes_bytes = len(json.dumps(canon["changes"]))
    per_change = changes_bytes / max(n_changed, 1)
    projected = baseline + per_change * n_unchanged

    tree_nodes = count_tree(tree["v1"]) + count_tree(tree["v2"]) if tree else 0

    print(f"=== {bill}  {v1} -> {v2}")
    print(f"  changes carried today          : {n_changed}")
    print(f"  matched-but-unchanged nodes    : {n_unchanged}")
    print(f"  tree nodes already carried     : {tree_nodes} (both sides)")
    print(f"  canonical size today           : {baseline / 1024:.0f} KB")
    print(f"  changes array alone            : {changes_bytes / 1024:.0f} KB ({per_change:.0f} B/change)")
    print(f"  option A projected size        : {projected / 1024:.0f} KB  (+{(projected / baseline - 1) * 100:.0f}%)")
    print(f"  option B added cost            : ~{tree_nodes * 12 / 1024:.1f} KB (a 12-byte id per tree node)")
    print(f"  (unused var guard: {len(with_unchanged['changes'])} changes after adapter filter)")
    print()
