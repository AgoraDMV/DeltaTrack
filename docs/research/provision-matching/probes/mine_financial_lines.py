"""Miner: FINANCIAL-LINE candidates (Pass 2 priority stream — appropriations focus).

Appropriations financial tables are DeltaTrack's primary value: a staffer needs the money
diff to read "$1,000,000 -> $1,200,000 for account X", not "removed $1,000,000 / added
$1,200,000". So matching financial lines correctly across versions is critical, and it is a
DIFFERENT regime from the text-provision strata: on a short account line the only substantive
change is the dollar amount, so word-overlap (not rare-token containment) is the signal that
matters (paper §7), and a large amount swap can drop word-overlap below the split threshold.

Two regimes, both drawn from the curated appropriations bills in `bills/` (every directory with
>= 2 versions — see `_approps_bills()`; the set grows as bills are added), across ALL adjacent
version pairs (the money negotiation happens House->Senate->conference->enrolled, not the first pair):
  - amount-edit-kept   = a `modified` financial node whose amounts changed. The matcher kept
    the pair; the human confirms it is genuinely the SAME account with an amount edit (vs a
    reused line for a different account). Calibrates the amount-edit "same" regime and anchors
    the failure mode #203 §3 lists as "amount-only edit".
  - amount-edit-split  = a removed financial node re-paired to an added financial node by text
    similarity (>= 0.5) with amounts on both sides. Candidate "same account, amount edit,
    WRONGLY split" — the false-split the amount swap causes. The valuable failure case.

`extra` records the amount pairing and whether the edit is amount-only (text identical once
amounts are masked) — the cleanest word-overlap-only regime. Emits an UNLABELED pool;
`measures` is analysis-only, stripped before labeling (§5).

Run (from repo root, repo venv; needs idf_cache.json from mine_idf.py):
    .venv/bin/python docs/research/provision-matching/probes/mine_financial_lines.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
from corpus_roots import merged_root  # noqa: E402
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from mine_common import make_candidate, write_pool  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import (  # noqa: E402
    _normalize_text,
    compute_financial_change,
    diff_bills,
)
from deltatrack.similarity import text_similarity  # noqa: E402

_BILLS = merged_root()
_OUT = Path(__file__).with_name("candidates_financial_lines.json")

SPLIT_SIM = 0.50  # text-similarity floor to re-pair a removed<->added financial line
MAX_KEPT_PER_BILL = 12  # spread anchors across bills; the omnibus bills would swamp otherwise
TARGET = 100  # ~priority-stream MVP; all split candidates kept (rare/valuable)
_amt = re.compile(r"\$[\d,]+")


def _amount_only(old: str, new: str) -> bool:
    """True if old/new are identical once every dollar amount is masked."""
    return _amt.sub("$", _normalize_text(old)) == _amt.sub("$", _normalize_text(new))


def _approps_bills():
    for d in sorted(_BILLS.iterdir()):
        if d.is_dir() and len(list(d.glob("*.xml"))) >= 2:
            yield d


def main() -> None:
    dropped = {"kept_per_bill_cap": 0, "target_cap": 0, "parse_errors": 0}
    kept_cands, split_cands = [], []

    for d in _approps_bills():
        xs = sorted(d.glob("*.xml"))
        kept_here = 0
        for i in range(len(xs) - 1):
            try:
                a = normalize_bill(xs[i])
                b = normalize_bill(xs[i + 1])
                diff = diff_bills(a, b)
            except Exception:
                dropped["parse_errors"] += 1  # count, don't silently swallow — a parse regression shrinks the pool
                continue
            vo, vn = xs[i].name, xs[i + 1].name

            # regime 1: amount-edit-kept (modified financial nodes, amounts changed)
            for c in diff.changes:
                if c.change_type != "modified":
                    continue
                fc = compute_financial_change(c.old_text, c.new_text)
                if not (fc and fc.amounts_changed):
                    continue
                if kept_here >= MAX_KEPT_PER_BILL:
                    dropped["kept_per_bill_cap"] += 1
                    continue
                kept_here += 1
                kept_cands.append(
                    make_candidate(
                        stratum="financial-line",
                        sampling="challenge",
                        miner="mine_financial_lines",
                        bill_old=d.name,
                        bill_new=d.name,
                        version_old=vo,
                        version_new=vn,
                        match_path_old=list(c.match_path),
                        match_path_new=list(c.match_path),
                        display_path_old=list(c.display_path_old or ()),
                        display_path_new=list(c.display_path_new or ()),
                        change_type="modified",
                        text_old=c.old_text or "",
                        text_new=c.new_text or "",
                        extra={
                            "regime": "amount-edit-kept",
                            "old_amounts": list(fc.old_amounts),
                            "new_amounts": list(fc.new_amounts),
                            "amount_only": _amount_only(c.old_text or "", c.new_text or ""),
                        },
                    )
                )

            # regime 2: amount-edit-split (removed financial <-> added financial, similar text)
            rem = [
                c
                for c in diff.changes
                if c.change_type == "removed" and c.old_text and compute_financial_change(c.old_text, None)
            ]
            add = [
                (c, _normalize_text(c.new_text))
                for c in diff.changes
                if c.change_type == "added" and c.new_text and compute_financial_change(None, c.new_text)
            ]
            for rc in rem:
                ro = _normalize_text(rc.old_text)
                best = None
                for ac, an in add:
                    s = text_similarity(ro, an)
                    if s >= SPLIT_SIM and (best is None or s > best[0]):
                        best = (s, ac)
                if best is None:
                    continue
                s, ac = best
                fco = compute_financial_change(rc.old_text, None)
                fcn = compute_financial_change(None, ac.new_text)
                old_amts = list(fco.old_amounts) if fco else []
                new_amts = list(fcn.new_amounts) if fcn else []
                # a split whose amounts are identical is a pure relocation, not an amount edit
                regime = "amount-edit-split" if sorted(old_amts) != sorted(new_amts) else "relocation-split"
                split_cands.append(
                    make_candidate(
                        stratum="financial-line",
                        sampling="challenge",
                        miner="mine_financial_lines",
                        bill_old=d.name,
                        bill_new=d.name,
                        version_old=vo,
                        version_new=vn,
                        match_path_old=list(rc.match_path),
                        match_path_new=list(ac.match_path),
                        display_path_old=list(rc.display_path_old or ()),
                        display_path_new=list(ac.display_path_new or ()),
                        change_type="financial-split-repair",
                        text_old=rc.old_text or "",
                        text_new=ac.new_text or "",
                        extra={
                            "regime": regime,
                            "text_similarity": round(s, 4),
                            "old_amounts": old_amts,
                            "new_amounts": new_amts,
                            "amount_only": _amount_only(rc.old_text or "", ac.new_text or ""),
                        },
                    )
                )

    # split candidates are rare and valuable -> keep all; anchors fill the rest to TARGET
    candidates = list(split_cands)
    room = max(0, TARGET - len(candidates))
    if len(kept_cands) > room:
        dropped["target_cap"] = len(kept_cands) - room
        kept_cands = kept_cands[:room]
    candidates += kept_cands

    by_regime = Counter(c["extra"]["regime"] for c in candidates)
    print(f"candidates by regime: {dict(by_regime)}")
    write_pool(_OUT, candidates, miner="mine_financial_lines", stratum="financial-line", dropped=dropped)


if __name__ == "__main__":
    main()
