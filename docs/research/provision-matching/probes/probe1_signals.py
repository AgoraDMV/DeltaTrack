"""Probe 1: extract real structural signals for the 12 #8 answer-key pairs.

For each labeled pair we locate the actual BillNode in each version (by matching
normalized body_text against the frozen text_old/text_new), then read the
structural signals the tree/BillNode already expose: match_path, display_path,
division_label, section_number, header_text (the section catchline). We then test
which signal (or combination) classifies each pair the way the human did.

Read-only: uses production normalize_bill; touches no matcher code.
"""

from __future__ import annotations

import json
from pathlib import Path

from deltatrack.bill_tree import BillNode, BillTree, normalize_bill, normalize_header
from deltatrack.diff_bill import _normalize_text
from deltatrack.similarity import text_similarity

REPO = Path(__file__).resolve().parents[4]
from corpus_roots import merged_root  # noqa: E402
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))
BILLS = merged_root()
FIXTURE = REPO / "tests" / "data" / "similarity_labels.json"

_tree_cache: dict[str, BillTree] = {}


def load(bill: str, version: str) -> BillTree:
    key = f"{bill}/{version}"
    if key not in _tree_cache:
        _tree_cache[key] = normalize_bill(BILLS / bill / f"{version}.xml")
    return _tree_cache[key]


def find_node(tree: BillTree, target_text: str) -> BillNode | None:
    """Locate the node whose normalized body_text equals the frozen fixture text."""
    tgt = _normalize_text(target_text)
    # exact match first
    for n in tree.nodes:
        if _normalize_text(n.body_text) == tgt:
            return n
    # fallback: best word-similarity (in case of minor normalization drift)
    best, best_sim = None, 0.0
    for n in tree.nodes:
        sim = text_similarity(_normalize_text(n.body_text), tgt)
        if sim > best_sim:
            best, best_sim = n, sim
    return best if best_sim > 0.95 else None


def header_sim(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return text_similarity(normalize_header(a), normalize_header(b))


pairs = json.loads(FIXTURE.read_text())["pairs"]

rows = []
for p in pairs:
    bill = p["bill"]
    to = load(bill, p["version_old"])
    tn = load(bill, p["version_new"])
    no = find_node(to, p["text_old"])
    nn = find_node(tn, p["text_new"])
    row = {
        "id": p["id"],
        "label": p["label"],
        "decision": p["decision"],
        "xfail": p["expected_misclassified"],
        "body_sim": round(text_similarity(_normalize_text(p["text_old"]), _normalize_text(p["text_new"])), 3),
    }
    if no is None or nn is None:
        row["FOUND"] = f"old={no is not None} new={nn is not None}"
    else:
        row["mp_old"] = list(no.match_path)
        row["mp_new"] = list(nn.match_path)
        row["mp_equal"] = no.match_path == nn.match_path
        row["hdr_old"] = no.header_text
        row["hdr_new"] = nn.header_text
        row["hdr_equal_norm"] = normalize_header(no.header_text) == normalize_header(nn.header_text) if (no.header_text or nn.header_text) else None
        row["hdr_sim"] = round(header_sim(no.header_text, nn.header_text), 3)
        row["div_old"] = no.division_label
        row["div_new"] = nn.division_label
        row["secnum_old"] = no.section_number
        row["secnum_new"] = nn.section_number
    rows.append(row)

# Dump full detail
for r in rows:
    print("=" * 90)
    print(f"{r['id']}  [label={r['label']} decision={r['decision']} xfail={r['xfail']}]  body_sim={r['body_sim']}")
    if "FOUND" not in r:
        print(f"  match_path equal? {r['mp_equal']}")
        print(f"    mp_old: {r['mp_old']}")
        print(f"    mp_new: {r['mp_new']}")
        print(f"  header_old: {r['hdr_old']!r}")
        print(f"  header_new: {r['hdr_new']!r}")
        print(f"  header equal(norm)? {r['hdr_equal_norm']}   header_sim={r['hdr_sim']}")
        print(f"  division_old: {r['div_old']!r}")
        print(f"  division_new: {r['div_new']!r}")
        print(f"  secnum: {r['secnum_old']!r} -> {r['secnum_new']!r}")
    else:
        print(f"  NODE LOOKUP FAILED: {r['FOUND']}")

# JSON for downstream analysis
out = REPO / "scratchpad_probe1.json"
Path("/private/tmp/claude-501/-Users-williamhea-Documents-Code-civictech-appropriations-bills/0e4234d5-c10a-4e30-9cf3-c31f645a6e14/scratchpad/probe1_out.json").write_text(json.dumps(rows, indent=2))
print("\n\nWrote probe1_out.json")
