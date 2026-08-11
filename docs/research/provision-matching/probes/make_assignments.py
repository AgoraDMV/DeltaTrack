"""Assign candidates to reviewers, in one of two modes (protocol §6/§8, multi-reviewer extension).

SHARED (default) — every reviewer labels every candidate. Agreement is then measurable on the
whole pool rather than on a small designated subset, which is what you want while the open
question is still "do independent people reach the same answer at all". Reviewers work the same
ordered queue and stop wherever they stop; `merge_labels.py` derives its agreement set from the
data (any candidate carrying >= 2 human labels), so a partial pass from a late-joining reviewer
still yields usable agreement. Adding a reviewer is purely ADDITIVE here: nobody's work is taken
away, so a growing team costs nothing.

SPLIT (`--split`) — disjoint shards for throughput, plus a small stratified overlap set everyone
labels for agreement. Use this once agreement is established and volume is the goal. The reviewer
set is fixed at first run in this mode, because the partition was handed out for that set and
changing it strands or orphans work.

In both modes only NEW (unassigned) candidate ids are partitioned, and existing assignments are
preserved, so re-running after miners add examples never reshuffles work already handed out.

Reviewer ids are OPAQUE (`r1`, `r2`, ...), never personal names: the ids travel in
`labels_<id>.json`, in the `labeler` field of every record, and onward into the committed fixture,
so a name here becomes a name in a public repo. Keep the id-to-person mapping outside the
repository.

Run (reviewer ids as args; no default — the id must be chosen deliberately):
    .venv/bin/python docs/research/provision-matching/probes/make_assignments.py r1 r2 r3
    .venv/bin/python docs/research/provision-matching/probes/make_assignments.py --split r1 r2 r3
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).parent
_WORKLIST = _HERE / "worklist.json"
_OUT = _HERE / "assignments.json"
OVERLAP_TARGET = 24  # stratified shared items in --split mode when >=2 reviewers
# Opaque ids only. Not a privacy theatre check — it cannot tell "r1" from "alice" — but it does
# stop the shapes people reach for when they stop thinking about it ("Jane Doe", an email address).
_ID_RE = re.compile(r"[A-Za-z0-9_-]+")


def _h(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest(), 16)


def _write(assignments: dict, reviewers: list[str], *, shared: bool) -> None:
    """Write assignments.json and report the load, for either mode."""
    load: dict[str, int] = defaultdict(int)
    for a in assignments.values():
        for r in a["reviewers"]:
            load[r] += 1
    total_overlap = sum(1 for a in assignments.values() if a.get("overlap"))
    mode = "shared" if shared else "split"
    _OUT.write_text(
        json.dumps(
            {
                "_about": (
                    "Reviewer assignments for Pass 2 labeling. mode=shared: every reviewer labels every "
                    "candidate, and adding a reviewer only ever adds work (never reassigns). mode=split: "
                    "overlap=True items are labeled by all reviewers (agreement set), the rest are "
                    "disjoint, and the reviewer set is fixed at first run. Only new candidate ids are "
                    "assigned on re-run. Reviewer ids are opaque; the mapping to people is not in this "
                    "repository."
                ),
                "mode": mode,
                "reviewers": reviewers,
                "overlap_target": 0 if shared or len(reviewers) < 2 else OVERLAP_TARGET,
                "n_overlap": total_overlap,
                "load_per_reviewer": dict(load),
                "assignments": assignments,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"mode: {mode}  reviewers: {reviewers}  overlap: {total_overlap}  total: {len(assignments)}")
    print(f"load per reviewer: {dict(load)}")
    idle = [r for r in reviewers if load.get(r, 0) == 0]
    if idle:
        print(
            f"!! WARNING: {idle} received 0 items — all ids may already be assigned; add candidates "
            "or delete assignments.json to re-partition for the current reviewer set."
        )


def main() -> None:
    argv = sys.argv[1:]
    shared = "--split" not in argv
    reviewers = sorted(dict.fromkeys(a for a in argv if not a.startswith("--")))
    # No default reviewer id. A bare run used to assign the whole pool to a hardcoded personal
    # name, which is both a silent mis-assignment and a name in a public repo.
    if not reviewers:
        sys.exit("usage: make_assignments.py [--split] <reviewer-id> [<reviewer-id> ...]  (e.g. r1 r2)")
    named = [r for r in reviewers if not _ID_RE.fullmatch(r)]
    if named:
        sys.exit(
            f"reviewer ids must be opaque (letters/digits/-/_, no spaces), got {named}. Ids travel into "
            "labels_<id>.json and the committed fixture — use r1/r2 and keep the mapping out of the repo."
        )
    entries = json.loads(_WORKLIST.read_text(encoding="utf-8"))["entries"]

    prev, prev_reviewers = {}, None
    if _OUT.exists():
        prev_doc = json.loads(_OUT.read_text(encoding="utf-8"))
        prev = prev_doc.get("assignments", {})
        prev_reviewers = prev_doc.get("reviewers")

    dropped = sorted(set(prev_reviewers or []) - set(reviewers))
    if dropped:
        sys.exit(
            f"reviewer(s) {dropped} would be dropped from assignments.json. Removing a reviewer is the "
            "destructive direction (their handed-out work is orphaned) — re-run including them, or "
            "delete assignments.json to start the partition over."
        )
    # In SPLIT mode the partition and overlap set were handed out for one reviewer set, so growing it
    # strands the newcomer (0 items, no agreement set). SHARED mode has no partition to invalidate:
    # a new reviewer simply joins every existing assignment, so it is always safe.
    if not shared and prev_reviewers is not None and sorted(prev_reviewers) != reviewers:
        sys.exit(
            f"reviewer set changed: assignments.json was built for {sorted(prev_reviewers)}, requested "
            f"{reviewers}. Work is already handed out under --split — to re-partition, delete "
            f"assignments.json and re-run (loses in-progress assignments); else re-run the original set."
        )

    if shared:
        # Everyone labels everything: existing assignments gain the new reviewers, unassigned ids go
        # to all of them. Nothing is ever taken away, so this is safe to re-run as the team grows.
        for cid, a in prev.items():
            a["reviewers"] = sorted(set(a["reviewers"]) | set(reviewers))
            a["overlap"] = len(a["reviewers"]) >= 2
        for e in entries:
            if e["id"] not in prev:
                prev[e["id"]] = {
                    "reviewers": list(reviewers),
                    "overlap": len(reviewers) >= 2,
                    "stratum": e["stratum"],
                }
        _write(prev, reviewers, shared=True)
        return

    # group unassigned ids by stratum (deterministic order by id hash)
    by_stratum: dict[str, list[str]] = defaultdict(list)
    strata_of = {}
    for e in entries:
        strata_of[e["id"]] = e["stratum"]
        if e["id"] not in prev:
            by_stratum[e["stratum"]].append(e["id"])
    for s in by_stratum:
        by_stratum[s].sort(key=_h)

    assignments = dict(prev)
    overlap_ids: list[str] = []
    if len(reviewers) >= 2:
        # stratified overlap, but count overlap ALREADY handed out toward the target so re-runs after
        # miner-adds don't balloon the shared agreement set past OVERLAP_TARGET.
        existing_overlap = sum(1 for a in prev.values() if a.get("overlap"))
        budget = max(0, OVERLAP_TARGET - existing_overlap)
        total_new = sum(len(v) for v in by_stratum.values()) or 1
        for s, ids in by_stratum.items():
            if budget <= 0 or not ids:
                continue
            take = min(len(ids), budget, max(1, round(OVERLAP_TARGET * len(ids) / total_new)))
            overlap_ids += ids[:take]
            budget -= take
        for cid in overlap_ids:
            assignments[cid] = {"reviewers": list(reviewers), "overlap": True, "stratum": strata_of[cid]}
    overlap = set(overlap_ids)

    # disjoint remainder: POSITIONAL round-robin over the hash-sorted ids (stable order,
    # but evenly balanced — hash-bucket assignment left one reviewer ~25% heavier). The
    # counter carries across strata so each reviewer gets a balanced mix of all strata.
    rr = 0
    for s, ids in by_stratum.items():
        for cid in ids:
            if cid in overlap:
                continue
            who = reviewers[rr % len(reviewers)]
            assignments[cid] = {"reviewers": [who], "overlap": False, "stratum": strata_of[cid]}
            rr += 1

    _write(assignments, reviewers, shared=False)


if __name__ == "__main__":
    main()
