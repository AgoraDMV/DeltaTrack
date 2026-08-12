"""Where the PDF pipeline actually decides correspondence, and how often.

Reconstructs ``diff_pdf.diff_pdfs`` stage by stage with a counter at every decision
site, then **asserts the reconstruction's hunks are element-for-element identical to
production's** before recording a single number. Without that assertion this would be
a measurement of a copy: a skipped branch or a moved filter would produce a plausible
census of a pipeline that is not the one shipping. The assertion is per pair, so a
drift names the bill it happened on.

Reported over ``accepted_pdf_pairs()`` — the pairs the product answers for.

    uv run python docs/research/pdf-matching-convergence/probes/pdf_stage_census.py
"""

from __future__ import annotations

import difflib
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import accepted_pdf_pairs, blocks_for, pages_for  # noqa: E402

from deltatrack.diff_bill import extract_amounts, match_amounts  # noqa: E402
from deltatrack.diff_pdf import (  # noqa: E402
    PdfHunk,
    _Block,
    _block_key,
    _has_amendment_annotations,
    _hunk_for_added,
    _hunk_for_paired_blocks,
    _hunk_for_removed,
    diff_pdfs,
)
from deltatrack.similarity import (  # noqa: E402
    MOVE_THRESHOLD,
    SIMILARITY_THRESHOLD,
    move_candidates,
    text_similarity_at_least,
)

# How close to a cutoff a pair has to sit to count as boundary-adjacent. Not a policy
# number: it is the width of the perturbation the sensitivity probe applies, so the two
# read the same population.
_NEAR = 0.05

COUNTERS = (
    "blocks_v1",
    "blocks_v2",
    # retrieval: what the block-key alignment offered
    "op_equal_pairs",
    "op_replace_pairs",
    "op_replace_surplus_removed",
    "op_replace_surplus_added",
    "op_delete_blocks",
    "op_insert_blocks",
    # assignment + classification fused inside _emit_pair
    "pair_identical_suppressed",
    "pair_identical_renamed_moved",
    "pair_split_below_similarity",
    "pair_split_with_amounts_both_sides",
    "pair_kept",
    "pair_kept_moved",
    "pair_kept_modified",
    "pair_near_similarity_cutoff",
    "pair_near_move_cutoff",
    # round 2
    "rec_removed_in",
    "rec_added_in",
    "rec_pair_space",
    "rec_candidates",
    "rec_selected",
    "rec_contested_removed",
    "rec_contested_added",
    "rec_score_ties",
)


def census(v1_pages, v2_pages) -> tuple[list[PdfHunk], dict]:
    c = dict.fromkeys(COUNTERS, 0)
    v1_blocks, v2_blocks = blocks_for(v1_pages), blocks_for(v2_pages)
    c["blocks_v1"], c["blocks_v2"] = len(v1_blocks), len(v2_blocks)

    matcher = difflib.SequenceMatcher(
        a=[_block_key(b) for b in v1_blocks], b=[_block_key(b) for b in v2_blocks], autojunk=False
    )
    hunks: list[PdfHunk] = []

    def emit_pair(a: _Block, b: _Block) -> None:
        if a.text == b.text:
            if a.anchor and b.anchor and a.anchor.text != b.anchor.text:
                c["pair_identical_renamed_moved"] += 1
                hunks.append(_hunk_for_paired_blocks(a, b, similarity=1.0))
            else:
                c["pair_identical_suppressed"] += 1
            return
        sim = text_similarity_at_least(a.text, b.text, SIMILARITY_THRESHOLD)
        if sim < SIMILARITY_THRESHOLD:
            c["pair_split_below_similarity"] += 1
            if extract_amounts(a.text) and extract_amounts(b.text):
                c["pair_split_with_amounts_both_sides"] += 1
            hunks.append(_hunk_for_removed(a))
            hunks.append(_hunk_for_added(b))
            return
        c["pair_kept"] += 1
        c["pair_near_similarity_cutoff"] += abs(sim - SIMILARITY_THRESHOLD) <= _NEAR
        c["pair_near_move_cutoff"] += abs(sim - MOVE_THRESHOLD) <= _NEAR
        hunk = _hunk_for_paired_blocks(a, b, similarity=sim)
        c["pair_kept_moved" if hunk.change_type == "moved" else "pair_kept_modified"] += 1
        hunks.append(hunk)

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for a, b in zip(v1_blocks[i1:i2], v2_blocks[j1:j2]):
                c["op_equal_pairs"] += 1
                emit_pair(a, b)
        elif op == "delete":
            for a in v1_blocks[i1:i2]:
                c["op_delete_blocks"] += 1
                hunks.append(_hunk_for_removed(a))
        elif op == "insert":
            for b in v2_blocks[j1:j2]:
                c["op_insert_blocks"] += 1
                hunks.append(_hunk_for_added(b))
        else:
            v1s, v2s = v1_blocks[i1:i2], v2_blocks[j1:j2]
            for k in range(max(len(v1s), len(v2s))):
                a = v1s[k] if k < len(v1s) else None
                b = v2s[k] if k < len(v2s) else None
                if a is not None and b is not None:
                    c["op_replace_pairs"] += 1
                    emit_pair(a, b)
                elif a is not None:
                    c["op_replace_surplus_removed"] += 1
                    hunks.append(_hunk_for_removed(a))
                else:
                    c["op_replace_surplus_added"] += 1
                    hunks.append(_hunk_for_added(b))

    removed_idx = [i for i, h in enumerate(hunks) if h.change_type == "removed"]
    added_idx = [i for i, h in enumerate(hunks) if h.change_type == "added"]
    c["rec_removed_in"], c["rec_added_in"] = len(removed_idx), len(added_idx)
    c["rec_pair_space"] = len(removed_idx) * len(added_idx)
    if not removed_idx or not added_idx:
        return hunks, c

    local = move_candidates(
        [hunks[r].v1_text for r in removed_idx], [hunks[a].v2_text for a in added_idx], MOVE_THRESHOLD
    )
    cands = [(s, removed_idx[r], added_idx[a]) for s, r, a in local]
    c["rec_candidates"] = len(cands)
    removed_demand = Counter(ri for _, ri, _ in cands)
    added_demand = Counter(ai for _, _, ai in cands)
    c["rec_contested_removed"] = sum(1 for n in removed_demand.values() if n > 1)
    c["rec_contested_added"] = sum(1 for n in added_demand.values() if n > 1)
    scores = [s for s, _, _ in cands]
    c["rec_score_ties"] = len(scores) - len(set(scores))
    if not cands:
        return hunks, c

    cands.sort(reverse=True)
    claimed_r: set[int] = set()
    claimed_a: set[int] = set()
    selected: list[tuple[int, int]] = []
    for _, ri, ai in cands:
        if ri in claimed_r or ai in claimed_a:
            continue
        claimed_r.add(ri)
        claimed_a.add(ai)
        selected.append((ri, ai))
    c["rec_selected"] = len(selected)

    consumed = claimed_r | claimed_a
    lookup = dict(selected)
    out: list[PdfHunk] = []
    for i, h in enumerate(hunks):
        if i in lookup:
            add = hunks[lookup[i]]
            out.append(
                PdfHunk(
                    change_type="moved",
                    v1_anchor=h.v1_anchor,
                    v2_anchor=add.v2_anchor,
                    v1_range=h.v1_range,
                    v2_range=add.v2_range,
                    v1_text=h.v1_text,
                    v2_text=add.v2_text,
                    amount_pairs=tuple(match_amounts(h.v1_text, add.v2_text)),
                    has_amendment_annotations=_has_amendment_annotations(h.v1_text, add.v2_text),
                )
            )
        elif i not in consumed:
            out.append(h)
    return out, c


def main() -> None:
    pairs = accepted_pdf_pairs()
    print(f"{len(pairs)} production-accepted adjacent PDF pairs", file=sys.stderr, flush=True)
    rows = []
    for n, (bill, old, new) in enumerate(pairs, 1):
        print(f"[{n}/{len(pairs)}] {bill} {old.stem} -> {new.stem}", file=sys.stderr, flush=True)
        old_pages, new_pages = pages_for(old), pages_for(new)
        reference = diff_pdfs(old_pages, new_pages)
        replica, counters = census(old_pages, new_pages)
        assert list(reference.hunks) == replica, (
            f"the census reconstruction diverged from diff_pdfs on {bill} {old.stem}->{new.stem}; "
            "every count below would describe a pipeline that is not the one shipping"
        )
        rows.append({"bill": bill, "pair": f"{old.stem}->{new.stem}", "summary": dict(reference.summary), **counters})

    totals = {k: sum(r[k] for r in rows) for k in COUNTERS}
    print("\n=== totals over the accepted population ===")
    for k in COUNTERS:
        print(f"  {k:38s} {totals[k]:,}")
    print("\n=== moves, by which site produced them ===")
    print(f"  _reconcile_moves (round 2 assignment)       {totals['rec_selected']}")
    print(f"  _hunk_for_paired_blocks (MOVE_THRESHOLD)    {totals['pair_kept_moved']}")
    print(f"  _emit_pair identical-but-renamed            {totals['pair_identical_renamed_moved']}")

    out = Path(__file__).resolve().parent.parent / "results" / "stage-census.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"pairs": rows, "totals": totals}, indent=2) + "\n")
    print(f"\nwrote {out.relative_to(PROJECT_ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
