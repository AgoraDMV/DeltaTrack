"""Miner: many-to-one CONSOLIDATION candidates (protocol §3, second priority stratum).

The §6.4 "absorbed into" case. On 119-hr-1's Senate rewrite (v3 placed-on-calendar-senate ->
v4 engrossed-amendment-senate) sections are renumbered and text recycled, so the match_path
join shatters: the current matcher shows a flood of removed+added. Rare-token containment
re-pairs many of the renumbered-recycled provisions the word-overlap rescue (>= 0.6) misses.

Each re-paired old-provision -> new-section pair is a candidate the human rules:
  - genuinely-absorbed = the old provision's statutory target substantively appears in the new
    section (a real many-to-one consolidation), OR
  - coincidentally-contained = containment is driven by a shared boilerplate citation with no
    substantive continuation (this is the false-keep positive, §5 label mapping).

So this stratum feeds BOTH the consolidation bucket and the high-containment-different
false-keep test. `fan_in` (how many old provisions map to the same new section) is recorded
as context: fan-in > 1 is the consolidation signature; a shared-citation cluster (§6.4's five
subsections each citing "Section 455(a)") is the coincidental-containment trap.

Held-out limitation (protocol §6): consolidation exists only in 119-hr-1 in the curated pool,
a Pass-1 "seen" bill forced to dev, so this stratum has a dev number but no held-out
counterpart. bills_corpus contains other big-rewrite bills (NDAAs etc.) that may supply a
second consolidation-bearing bill; that is flagged for follow-up, not mined here.

Emits an UNLABELED pool; `measures` is analysis-only and stripped before labeling (§5).

Run (from repo root, repo venv; needs idf_cache.json from mine_idf.py):
    .venv/bin/python docs/research/provision-matching/probes/mine_consolidation.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
from corpus_roots import merged_root  # noqa: E402
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from mine_common import containment, make_candidate, vec, write_pool  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text, diff_bills# noqa: E402
from deltatrack.similarity import text_similarity# noqa: E402

BILL = "119-hr-1"
V_OLD = "3_placed-on-calendar-senate.xml"
V_NEW = "4_engrossed-amendment-senate.xml"
_OUT = Path(__file__).with_name("candidates_consolidation.json")

CONTAIN_KEEP = 0.70  # the paper's keep bar
MOVE_BAR = 0.60  # word-overlap rescue the current matcher already applies
TARGET = 60  # ~2x the §3 quota of 25 so the human can rule down with margin


def main() -> None:
    a = normalize_bill(merged_root() / BILL / V_OLD)
    b = normalize_bill(merged_root() / BILL / V_NEW)
    diff = diff_bills(a, b)

    removed = [c for c in diff.changes if c.change_type == "removed" and (c.old_text or "").strip()]
    added = [c for c in diff.changes if c.change_type == "added" and (c.new_text or "").strip()]

    add_norm = [(c, _normalize_text(c.new_text or "")) for c in added]
    add_vec = [(c, nw, vec(nw)) for c, nw in add_norm]

    # re-pair each removed old provision to its best added section by containment,
    # keeping the renumber-recycled set the word-overlap rescue misses (< MOVE_BAR)
    repaired = []  # (old_change, new_change, containment, word_overlap)
    for rc in removed:
        ro = _normalize_text(rc.old_text or "")
        rv = vec(ro)
        best = None
        for ac, ao, av in add_vec:
            c = containment(rv, av)
            if best is None or c > best[0]:
                best = (c, ac, ao)
        if best is None:
            continue
        c, ac, ao = best
        wr = text_similarity(ro, ao)
        if c >= CONTAIN_KEEP and wr < MOVE_BAR:
            repaired.append((rc, ac, c, wr))

    # fan-in per target new section (the consolidation signature)
    fan_in = Counter(tuple(ac.match_path) for _, ac, _, _ in repaired)

    dropped = {"target_cap": 0}
    candidates = []
    for rc, ac, c, wr in repaired:
        target = tuple(ac.match_path)
        candidates.append(
            make_candidate(
                stratum="consolidation",
                sampling="challenge",
                miner="mine_consolidation",
                bill_old=BILL,
                bill_new=BILL,
                version_old=V_OLD,
                version_new=V_NEW,
                match_path_old=list(rc.match_path),
                match_path_new=list(ac.match_path),
                display_path_old=list(rc.display_path_old or ()),
                display_path_new=list(ac.display_path_new or ()),
                change_type="consolidation-repair",
                text_old=rc.old_text or "",
                text_new=ac.new_text or "",
                extra={
                    "fan_in": fan_in[target],  # >1 => many-to-one consolidation signature
                    "reverse_direction": len(ac.new_text or "") < len(rc.old_text or ""),
                    "target_section": ac.match_path[-1] if ac.match_path else None,
                },
            )
        )

    # keep the many-to-one groups first (the actual consolidation cases), then one-to-one,
    # then apply the target cap loudly
    candidates.sort(key=lambda r: (r["extra"]["fan_in"], r["measures"]["containment"]), reverse=True)
    if len(candidates) > TARGET:
        dropped["target_cap"] = len(candidates) - TARGET
        candidates = candidates[:TARGET]

    n_many = sum(1 for r in candidates if r["extra"]["fan_in"] > 1)
    print(
        f"removed: {len(removed)}  added: {len(added)}  containment-repaired (>= {CONTAIN_KEEP}, "
        f"word-overlap < {MOVE_BAR}): {len(repaired)}"
    )
    print(
        f"distinct target sections: {len(fan_in)}  many-to-one targets: "
        f"{sum(1 for v in fan_in.values() if v > 1)}  max fan-in: {max(fan_in.values()) if fan_in else 0}"
    )
    print(f"candidates kept: {len(candidates)} ({n_many} in many-to-one groups)")
    write_pool(_OUT, candidates, miner="mine_consolidation", stratum="consolidation", dropped=dropped)


if __name__ == "__main__":
    main()
