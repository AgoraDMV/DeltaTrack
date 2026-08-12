"""Negative control: can any committed gate fail on a PDF matching-policy change?

Before a migration can claim behaviour preservation, something has to be able to
notice a behaviour change. This perturbs each of the two PDF matching cutoffs by
±0.05 and reports, per production-accepted pair, whether the emitted change sequence
moves at all — then reads the answer specifically for the pairs the repository's
output-preserving gates actually cover.

**Why a replica rather than monkeypatching the constants.** ``diff_pdf`` binds both
cutoffs into its own module namespace at import, and ``_reconcile_moves`` takes
``MOVE_THRESHOLD`` as a *default argument*, bound at definition. Rebinding either
attribute changes nothing, so a monkeypatched run would report "no change" for every
perturbation and read as a reassuring result. The replica is the same one
``pdf_stage_census`` asserts equal to production, and this probe re-asserts that
equality at the baseline on each pair before trusting any perturbed run.

    uv run python docs/research/pdf-matching-convergence/probes/pdf_threshold_sensitivity.py
"""

from __future__ import annotations

import difflib
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import accepted_pdf_pairs, blocks_for, pages_for  # noqa: E402

from deltatrack.diff_bill import match_amounts  # noqa: E402
from deltatrack.diff_pdf import (  # noqa: E402
    PdfHunk,
    _Block,
    _block_key,
    _has_amendment_annotations,
    _hunk_for_added,
    _hunk_for_removed,
    diff_pdfs,
)
from deltatrack.similarity import (  # noqa: E402
    MOVE_THRESHOLD,
    SIMILARITY_THRESHOLD,
    move_candidates,
    text_similarity_at_least,
)

#: The pairs the repository's output-preserving gates cover, and what covers them.
COVERED = {
    "118-hr-8752/1_reported-in-house->2_engrossed-in-house": (
        "examples/hr8752_pdf_diff.html (byte-identical re-render) + the 13-case hand-authored "
        "recall fixture + a test_pipeline_parity band"
    ),
    "118-hr-8774/1_reported-in-house->2_engrossed-in-house": "test_pipeline_parity band (31, 36)",
    "117-hr-4502/1_reported-in-house->2_engrossed-in-house": "test_pipeline_parity band (1430, 1520)",
    "115-hr-5895/1_reported-in-house->2_engrossed-in-house": "test_pipeline_parity band (310, 345)",
}

PERTURBATIONS = (
    ("baseline", SIMILARITY_THRESHOLD, MOVE_THRESHOLD),
    ("similarity +0.05", SIMILARITY_THRESHOLD + 0.05, MOVE_THRESHOLD),
    ("similarity -0.05", SIMILARITY_THRESHOLD - 0.05, MOVE_THRESHOLD),
    ("move +0.05", SIMILARITY_THRESHOLD, MOVE_THRESHOLD + 0.05),
    ("move -0.05", SIMILARITY_THRESHOLD, MOVE_THRESHOLD - 0.05),
)


def replica(v1_pages, v2_pages, *, split: float, move: float) -> list[PdfHunk]:
    v1_blocks, v2_blocks = blocks_for(v1_pages), blocks_for(v2_pages)
    matcher = difflib.SequenceMatcher(
        a=[_block_key(b) for b in v1_blocks], b=[_block_key(b) for b in v2_blocks], autojunk=False
    )
    hunks: list[PdfHunk] = []

    def paired(a: _Block, b: _Block, sim: float) -> PdfHunk:
        renamed = bool(a.anchor and b.anchor and a.anchor.text != b.anchor.text)
        return PdfHunk(
            change_type="moved" if renamed and sim >= move else "modified",
            v1_anchor=a.anchor,
            v2_anchor=b.anchor,
            v1_range=a.page_range,
            v2_range=b.page_range,
            v1_text=a.text,
            v2_text=b.text,
            amount_pairs=tuple(match_amounts(a.text, b.text)),
            has_amendment_annotations=_has_amendment_annotations(a.text, b.text),
        )

    def emit_pair(a: _Block, b: _Block) -> None:
        if a.text == b.text:
            if a.anchor and b.anchor and a.anchor.text != b.anchor.text:
                hunks.append(paired(a, b, 1.0))
            return
        sim = text_similarity_at_least(a.text, b.text, split)
        if sim < split:
            hunks.append(_hunk_for_removed(a))
            hunks.append(_hunk_for_added(b))
        else:
            hunks.append(paired(a, b, sim))

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for a, b in zip(v1_blocks[i1:i2], v2_blocks[j1:j2]):
                emit_pair(a, b)
        elif op == "delete":
            hunks.extend(_hunk_for_removed(a) for a in v1_blocks[i1:i2])
        elif op == "insert":
            hunks.extend(_hunk_for_added(b) for b in v2_blocks[j1:j2])
        else:
            v1s, v2s = v1_blocks[i1:i2], v2_blocks[j1:j2]
            for k in range(max(len(v1s), len(v2s))):
                a = v1s[k] if k < len(v1s) else None
                b = v2s[k] if k < len(v2s) else None
                if a is not None and b is not None:
                    emit_pair(a, b)
                elif a is not None:
                    hunks.append(_hunk_for_removed(a))
                else:
                    hunks.append(_hunk_for_added(b))

    removed_idx = [i for i, h in enumerate(hunks) if h.change_type == "removed"]
    added_idx = [i for i, h in enumerate(hunks) if h.change_type == "added"]
    if not removed_idx or not added_idx:
        return hunks
    local = move_candidates([hunks[r].v1_text for r in removed_idx], [hunks[a].v2_text for a in added_idx], move)
    cands = sorted(((s, removed_idx[r], added_idx[a]) for s, r, a in local), reverse=True)
    if not cands:
        return hunks

    claimed_r: set[int] = set()
    claimed_a: set[int] = set()
    selected: list[tuple[int, int]] = []
    for _, ri, ai in cands:
        if ri in claimed_r or ai in claimed_a:
            continue
        claimed_r.add(ri)
        claimed_a.add(ai)
        selected.append((ri, ai))

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
    return out


def digest(hunks: list[PdfHunk]) -> str:
    """A digest over what the canonical projection reads: type, both ranges, the amounts.

    Not over the whole hunk: the texts are the largest field and carry no decision the
    matcher makes, so including them would make the digest a text-extraction gate wearing
    a matching gate's clothes.
    """
    payload = repr([(h.change_type, h.v1_range, h.v2_range, h.amount_pairs) for h in hunks])
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def main() -> None:
    pairs = accepted_pdf_pairs()
    print(f"{len(pairs)} production-accepted adjacent PDF pairs", file=sys.stderr, flush=True)
    results: dict[str, dict] = {}
    for bill, old, new in pairs:
        key = f"{bill}/{old.stem}->{new.stem}"
        old_pages, new_pages = pages_for(old), pages_for(new)
        assert list(diff_pdfs(old_pages, new_pages).hunks) == replica(
            old_pages, new_pages, split=SIMILARITY_THRESHOLD, move=MOVE_THRESHOLD
        ), f"the replica diverged from diff_pdfs on {key}; no perturbed run from it means anything"
        row = {}
        for name, split, move in PERTURBATIONS:
            hunks = replica(old_pages, new_pages, split=split, move=move)
            row[name] = {
                "digest": digest(hunks),
                "changes": len(hunks),
                "summary": dict(Counter(h.change_type for h in hunks)),
            }
        results[key] = row
        moved = [n for n, _, _ in PERTURBATIONS[1:] if row[n]["digest"] != row["baseline"]["digest"]]
        print(f"  {key[:62]:62s} responds to: {', '.join(moved) if moved else 'NOTHING'}", file=sys.stderr, flush=True)

    print("\n=== how many accepted pairs change output under each perturbation ===")
    for name, _, _ in PERTURBATIONS[1:]:
        n = sum(1 for r in results.values() if r[name]["digest"] != r["baseline"]["digest"])
        print(f"  {name:20s} {n}/{len(results)}")

    print("\n=== the pairs an output-preserving gate actually covers ===")
    for key, gate in COVERED.items():
        row = results.get(key)
        if row is None:
            print(f"  {key}: NOT IN THE ACCEPTED POPULATION")
            continue
        responds = [n for n, _, _ in PERTURBATIONS[1:] if row[n]["digest"] != row["baseline"]["digest"]]
        print(f"  {key}")
        print(f"      covered by: {gate}")
        print(f"      baseline:   {row['baseline']['changes']} changes {row['baseline']['summary']}")
        print(f"      responds to: {', '.join(responds) if responds else 'NOTHING'}")
        for name, _, _ in PERTURBATIONS[1:]:
            print(f"        {name:20s} {row[name]['changes']:5d} changes {row[name]['summary']}")

    out = Path(__file__).resolve().parent.parent / "results" / "threshold-sensitivity.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nwrote {out.relative_to(PROJECT_ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
