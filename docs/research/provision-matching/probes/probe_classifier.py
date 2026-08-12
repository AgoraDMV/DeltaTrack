"""Prototype STRUCTURAL classifier, measured against the 12-pair #8 answer key.

Candidate rule set (structure primary, text as one signal among several):

 SPLIT decision (a matched same-slot pair -> keep as `modified`, or tear into
 removed+added):
   keep if  body_sim >= HIGH_KEEP                       (clearly one edited block)
        or  (leaf is a money account AND match_path leaf equal)  (durable account id)
        or  (both headers present AND header_sim >= HDR)         (titled section, same catchline)
   else split.

 MOVE decision (rescue a removed+added as `moved`):
   legit if body_sim >= MOVE_SIM AND (parent match_path equal OR header match)
   else leave as removed+added.

We compare this to the current baseline (single 0.40 split floor / 0.60 move floor)
over all 12 labeled pairs and print both confusion matrices.
"""

from __future__ import annotations

import json
from pathlib import Path

from deltatrack.bill_tree import BillNode, BillTree, normalize_bill, normalize_header
from deltatrack.diff_bill import (
    _normalize_text,
)
from deltatrack.similarity import MOVE_THRESHOLD, SIMILARITY_THRESHOLD, text_similarity  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
from corpus_roots import merged_root  # noqa: E402
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))
BILLS = merged_root()
FIXTURE = REPO / "tests" / "data" / "similarity_labels.json"

HIGH_KEEP = 0.6   # raised text keep-floor (was 0.40); structure rescues low-sim keeps
HDR = 0.8         # header-similarity keep threshold
MOVE_SIM = 0.6    # unchanged move text floor
ACCOUNT_TAGS = {"appropriations-major", "appropriations-intermediate", "appropriations-small"}

_cache: dict[str, BillTree] = {}


def load(bill: str, version: str) -> BillTree:
    k = f"{bill}/{version}"
    if k not in _cache:
        _cache[k] = normalize_bill(BILLS / bill / f"{version}.xml")
    return _cache[k]


def find_node(tree: BillTree, target: str) -> BillNode | None:
    tgt = _normalize_text(target)
    for n in tree.nodes:
        if _normalize_text(n.body_text) == tgt:
            return n
    best, bs = None, 0.0
    for n in tree.nodes:
        s = text_similarity(_normalize_text(n.body_text), tgt)
        if s > bs:
            best, bs = n, s
    return best if bs > 0.95 else None


def hdr_sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return text_similarity(normalize_header(a), normalize_header(b))


def baseline_pred(p: dict, body_sim: float) -> str:
    thr = SIMILARITY_THRESHOLD if p["decision"] == "split" else MOVE_THRESHOLD
    return "same" if body_sim >= thr else "different"


def structural_pred(p: dict, no: BillNode, nn: BillNode, body_sim: float) -> str:
    if p["decision"] == "split":
        leaf_account = no.tag in ACCOUNT_TAGS and nn.tag in ACCOUNT_TAGS
        mp_equal = no.match_path == nn.match_path
        headers_present = bool(no.header_text) and bool(nn.header_text)
        keep = (
            body_sim >= HIGH_KEEP
            or (leaf_account and mp_equal)
            or (headers_present and hdr_sim(no.header_text, nn.header_text) >= HDR)
        )
        return "same" if keep else "different"
    else:  # move
        parent_equal = no.match_path[:-1] == nn.match_path[:-1] and len(no.match_path) > 0
        header_match = bool(no.header_text) and bool(nn.header_text) and hdr_sim(no.header_text, nn.header_text) >= HDR
        legit = body_sim >= MOVE_SIM and (parent_equal or header_match)
        return "same" if legit else "different"


pairs = json.loads(FIXTURE.read_text())["pairs"]
results = []
for p in pairs:
    to, tn = load(p["bill"], p["version_old"]), load(p["bill"], p["version_new"])
    no, nn = find_node(to, p["text_old"]), find_node(tn, p["text_new"])
    body_sim = text_similarity(_normalize_text(p["text_old"]), _normalize_text(p["text_new"]))
    base = baseline_pred(p, body_sim)
    struct = structural_pred(p, no, nn, body_sim)
    results.append({
        "id": p["id"], "label": p["label"], "decision": p["decision"],
        "body_sim": round(body_sim, 3), "tag_old": no.tag, "tag_new": nn.tag,
        "base": base, "struct": struct,
        "base_ok": base == p["label"], "struct_ok": struct == p["label"],
    })

print(f"{'id':<26} {'label':<10} {'dec':<6} {'sim':>6} {'leaf':<24} {'base':<10} {'struct':<10}")
print("-" * 104)
for r in results:
    b = "OK " if r["base_ok"] else "XX "
    s = "OK " if r["struct_ok"] else "XX "
    print(f"{r['id']:<26} {r['label']:<10} {r['decision']:<6} {r['body_sim']:>6} "
          f"{r['tag_old']:<24} {b}{r['base']:<7} {s}{r['struct']:<7}")

base_correct = sum(r["base_ok"] for r in results)
struct_correct = sum(r["struct_ok"] for r in results)
print("-" * 104)
print(f"baseline correct:   {base_correct}/12")
print(f"structural correct: {struct_correct}/12")


def confusion(preds_key: str, decision: str):
    tp = fp = fn = tn = 0
    for r in results:
        if r["decision"] != decision:
            continue
        ps = r[preds_key] == "same"
        ls = r["label"] == "same"
        if ps and ls: tp += 1
        elif ps and not ls: fp += 1
        elif not ps and ls: fn += 1
        else: tn += 1
    prec = tp / (tp + fp) if (tp + fp) else float("nan")
    rec = tp / (tp + fn) if (tp + fn) else float("nan")
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=round(prec, 3), recall=round(rec, 3))


print("\nSPLIT decision:")
print(f"  baseline:   {confusion('base','split')}")
print(f"  structural: {confusion('struct','split')}")
print("MOVE decision:")
print(f"  baseline:   {confusion('base','move')}")
print(f"  structural: {confusion('struct','move')}")
