"""Is PDF's legacy positional tiebreak policy, the way XML's is?

Prompted by a second independent review, which flagged that "a common assignment
implementation can reproduce thresholds and still choose different partners if tie
behavior differs." That is a real hazard and the README's §5.3 originally argued past
it rather than measuring it.

The question that matters is not local-vs-absolute indexing. It is that PDF breaks ties
on a position in the **emitted hunk list** — which interleaves hunks from five producers —
while XML breaks them on a position in the unmatched-**observation** stream. #590 measured
that substituting ADR 0019 ordinals for XML's `(ri, ai)` moves the selected correspondence
on 3 of 27 pairs, so on XML the legacy key is policy. This asks the same of PDF.

Two things are measured:

1. **Selection equivalence.** Run round-2 greedy selection under both keys and compare the
   chosen links as `(old_block_ordinal, new_block_ordinal)` sets.
2. **Whether any equivalence is structural.** Check, per side, whether hunk-list order is
   already block-ordinal order. If it is, the two keys induce the same total order by
   construction and result 1 is not a corpus coincidence — which is the difference between
   a finding that generalises and one that holds until the next bill.

    uv run python docs/research/pdf-matching-convergence/probes/pdf_tiebreak_equivalence.py
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import accepted_pdf_pairs, blocks_for, pages_for  # noqa: E402

from deltatrack.diff_pdf import (  # noqa: E402
    PdfHunk,
    _block_key,
    _hunk_for_added,
    _hunk_for_paired_blocks,
    _hunk_for_removed,
    _reconcile_moves,
    diff_pdfs,
)
from deltatrack.similarity import (  # noqa: E402
    MOVE_THRESHOLD,
    SIMILARITY_THRESHOLD,
    move_candidates,
    text_similarity_at_least,
)


def hunks_with_block_origin(v1_pages, v2_pages) -> tuple[list[PdfHunk], list[tuple[int | None, int | None]]]:
    """The pre-reconcile hunk list, plus each hunk's source block index on each side.

    Production discards that provenance, which is exactly why the question here cannot be
    answered without rebuilding the walk. The caller asserts the result against
    ``diff_pdfs`` before using it.
    """
    v1_blocks, v2_blocks = blocks_for(v1_pages), blocks_for(v2_pages)
    matcher = difflib.SequenceMatcher(
        a=[_block_key(b) for b in v1_blocks], b=[_block_key(b) for b in v2_blocks], autojunk=False
    )
    hunks: list[PdfHunk] = []
    origin: list[tuple[int | None, int | None]] = []

    def emit_pair(i: int, j: int) -> None:
        a, b = v1_blocks[i], v2_blocks[j]
        if a.text == b.text:
            if a.anchor and b.anchor and a.anchor.text != b.anchor.text:
                hunks.append(_hunk_for_paired_blocks(a, b, similarity=1.0))
                origin.append((i, j))
            return
        sim = text_similarity_at_least(a.text, b.text, SIMILARITY_THRESHOLD)
        if sim < SIMILARITY_THRESHOLD:
            hunks.append(_hunk_for_removed(a))
            origin.append((i, None))
            hunks.append(_hunk_for_added(b))
            origin.append((None, j))
        else:
            hunks.append(_hunk_for_paired_blocks(a, b, similarity=sim))
            origin.append((i, j))

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for off in range(min(i2 - i1, j2 - j1)):
                emit_pair(i1 + off, j1 + off)
        elif op == "delete":
            for i in range(i1, i2):
                hunks.append(_hunk_for_removed(v1_blocks[i]))
                origin.append((i, None))
        elif op == "insert":
            for j in range(j1, j2):
                hunks.append(_hunk_for_added(v2_blocks[j]))
                origin.append((None, j))
        else:
            n1, n2 = i2 - i1, j2 - j1
            for k in range(max(n1, n2)):
                if k < n1 and k < n2:
                    emit_pair(i1 + k, j1 + k)
                elif k < n1:
                    hunks.append(_hunk_for_removed(v1_blocks[i1 + k]))
                    origin.append((i1 + k, None))
                else:
                    hunks.append(_hunk_for_added(v2_blocks[j1 + k]))
                    origin.append((None, j1 + k))
    return hunks, origin


def greedy(candidates, key) -> list[tuple[int, int]]:
    """The legacy exclusive claim under an arbitrary sort key, descending."""
    claimed_old: set[int] = set()
    claimed_new: set[int] = set()
    selected: list[tuple[int, int]] = []
    for _score, ri, ai in sorted(candidates, key=key, reverse=True):
        if ri in claimed_old or ai in claimed_new:
            continue
        claimed_old.add(ri)
        claimed_new.add(ai)
        selected.append((ri, ai))
    return selected


def main() -> None:
    pairs = accepted_pdf_pairs()
    print(f"{len(pairs)} production-accepted adjacent PDF pairs\n")
    rows = []
    totals = {"legacy": 0, "ordinal": 0, "symmetric_difference": 0, "ties": 0}
    monotonic_ok = monotonic_checked = 0

    for bill, old, new in pairs:
        old_pages, new_pages = pages_for(old), pages_for(new)
        hunks, origin = hunks_with_block_origin(old_pages, new_pages)
        assert list(diff_pdfs(old_pages, new_pages).hunks) == _reconcile_moves(list(hunks)), (
            f"the rebuilt walk diverged from diff_pdfs on {bill} {old.stem}->{new.stem}"
        )

        removed_idx = [i for i, h in enumerate(hunks) if h.change_type == "removed"]
        added_idx = [i for i, h in enumerate(hunks) if h.change_type == "added"]

        # Structural question: is hunk-list order already block-ordinal order, per side?
        for side, change_type in ((0, "removed"), (1, "added")):
            sequence = [origin[i][side] for i, h in enumerate(hunks) if h.change_type == change_type]
            if not sequence:
                continue
            monotonic_checked += 1
            monotonic_ok += sequence == sorted(sequence)

        if not removed_idx or not added_idx:
            continue
        candidates = [
            (score, removed_idx[r], added_idx[a])
            for score, r, a in move_candidates(
                [hunks[r].v1_text for r in removed_idx], [hunks[a].v2_text for a in added_idx], MOVE_THRESHOLD
            )
        ]
        if not candidates:
            continue

        scores = [s for s, _, _ in candidates]
        ties = len(scores) - len(set(scores))
        old_ordinal = {i: origin[i][0] for i in removed_idx}
        new_ordinal = {i: origin[i][1] for i in added_idx}

        legacy = greedy(candidates, key=lambda c: (c[0], c[1], c[2]))
        ordinal = greedy(candidates, key=lambda c: (c[0], old_ordinal[c[1]], new_ordinal[c[2]]))

        def as_blocks(selection):
            return {(old_ordinal[ri], new_ordinal[ai]) for ri, ai in selection}

        legacy_links, ordinal_links = as_blocks(legacy), as_blocks(ordinal)
        symmetric = len(legacy_links ^ ordinal_links)
        totals["legacy"] += len(legacy_links)
        totals["ordinal"] += len(ordinal_links)
        totals["symmetric_difference"] += symmetric
        totals["ties"] += ties
        rows.append(
            {
                "bill": bill,
                "pair": f"{old.stem}->{new.stem}",
                "candidates": len(candidates),
                "ties": ties,
                "legacy_links": len(legacy_links),
                "ordinal_links": len(ordinal_links),
                "symmetric_difference": symmetric,
            }
        )
        print(
            f"  {bill:14s} {old.stem[:24]:24s}->{new.stem[:24]:24s} "
            f"candidates={len(candidates):4d} ties={ties:3d} legacy={len(legacy_links):3d} "
            f"ordinal={len(ordinal_links):3d} symdiff={symmetric}" + ("   <-- DIFFERS" if symmetric else "")
        )

    print(
        f"\nTOTAL legacy={totals['legacy']} ordinal={totals['ordinal']} "
        f"symmetric difference={totals['symmetric_difference']} over {totals['ties']} score ties"
    )
    print(f"side-sequences already in block-ordinal order: {monotonic_ok}/{monotonic_checked}")
    if totals["symmetric_difference"] == 0 and monotonic_ok == monotonic_checked:
        print(
            "\nRESULT: the two tiebreaks select identical links, and structurally so — hunk-list\n"
            "position and block ordinal induce the same total order. Unlike XML (#590), PDF's\n"
            "legacy positional key is NOT policy."
        )
    elif totals["symmetric_difference"] == 0:
        print("\nRESULT: identical on this corpus, but NOT structurally. Treat the legacy key as policy.")
    else:
        print("\nRESULT: the keys DIFFER. The legacy hunk-index tiebreak is policy and must be preserved.")

    out = Path(__file__).resolve().parent.parent / "results" / "tiebreak-equivalence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"pairs": rows, "totals": totals, "monotonic": {"ok": monotonic_ok, "checked": monotonic_checked}},
            indent=2,
        )
        + "\n"
    )
    print(f"\nwrote {out.relative_to(PROJECT_ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
