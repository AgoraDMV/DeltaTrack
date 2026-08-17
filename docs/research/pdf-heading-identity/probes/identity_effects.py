"""What a stable heading identity does downstream, measured two ways that must stay apart.

DISPLAY: substitute the run identity into the label comparison
``formatters/canonical._pdf_move`` already makes, and report how the canonical
``move.kind`` changes over every production-accepted pair.

RETRIEVAL: substitute it into ``_block_key`` -- **in this probe only** -- and report
whether the ADR 0020 stage outputs move. Nothing under ``src/`` is edited; the patch is
applied and reverted around each pair.

Also: is the identity unique per block? If one printed heading yields two anchors, and
so two blocks, then it is not a key and using it as one merges two observations.

    uv run python docs/research/pdf-heading-identity/probes/identity_effects.py
"""

from __future__ import annotations

import difflib
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "docs" / "research" / "pdf-matching-convergence" / "probes"))

from corpus import accepted_pdf_pairs, pages_for  # noqa: E402

import deltatrack.diff_pdf as DP  # noqa: E402
from deltatrack.formatters.canonical import pdf_diff_to_canonical  # noqa: E402
from deltatrack.parsers.pdf_anchors import (  # noqa: E402
    _ENUM_PREFIX,
    _SIZE_EPS,
    _is_parenthetical,
    _is_uppercase_heading,
    derive_size_bands,
    extract_anchors,
)
from deltatrack.parsers.pdf_blocks import _flatten, _group_into_blocks  # noqa: E402
from deltatrack.pdf_observations import PdfObservationRegistry, observation_closure, pdf_parser_revision  # noqa: E402
from deltatrack.similarity import MOVE_THRESHOLD, SIMILARITY_THRESHOLD  # noqa: E402

WRAP_HYPHENS = ("-", "‐", "‑")
ORIGINAL_BLOCK_KEY = DP._block_key

#: Files perturbed to show what the ADR 0019 parser revision is and is not sensitive to.
PERTURB = [
    "src/deltatrack/parsers/pdf_anchors.py",
    "src/deltatrack/parsers/pdf_text.py",
    "src/deltatrack/parsers/pdf_blocks.py",
    "src/deltatrack/amounts.py",
    "src/deltatrack/formatters/canonical.py",
    "src/deltatrack/diff_pdf.py",
    "src/deltatrack/similarity.py",
]

STAGE_FIELDS = [
    "dup_keys_v1",
    "dup_keys_v2",
    "opcodes",
    "considered",
    "candidates",
    "post_revocation",
    "round2_unmatched",
    "n_moves_round2",
    "summary",
    "canonical",
]


def band_run_index(pages) -> dict[tuple[int, int], str]:
    """``(page, line) -> the joined text of the in-band heading run containing it``.

    The run is delimited by body prose on both sides, so it is invariant to where the
    typesetter broke the lines inside it -- which is the property a re-typeset version
    needs and a single printed line does not have.
    """
    bands = derive_size_bands(pages)
    if bands is None:
        return {}
    flat = [(page.page_number, line) for page in pages for line in page.lines]

    def is_candidate(line) -> bool:
        return (
            line.line_number is not None
            and line.glyph_size is not None
            and bands.heading_lo - _SIZE_EPS <= line.glyph_size <= bands.heading_hi + _SIZE_EPS
            and _is_uppercase_heading(line.text)
            and not _ENUM_PREFIX.match(line.text)
            and not _is_parenthetical(line.text)
        )

    index: dict[tuple[int, int], str] = {}
    i, n = 0, len(flat)
    while i < n:
        if not is_candidate(flat[i][1]):
            i += 1
            continue
        j, members = i, []
        while j < n:
            page_no, line = flat[j]
            if is_candidate(line):
                members.append((page_no, line))
                j += 1
                continue
            if not line.text.strip() or _is_parenthetical(line.text):
                j += 1
                continue
            break
        text = members[0][1].text.strip()
        for _p, line in members[1:]:
            seg = line.text.strip()
            text = text[:-1] + seg if text.endswith(WRAP_HYPHENS) else f"{text} {seg}"
        for page_no, line in members:
            index[(page_no, line.line_number)] = text
        i = j
    return index


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


def blocks_for(pages):
    return _group_into_blocks(_flatten(pages), extract_anchors(pages))


def stage_snapshot(v1_blocks, v2_blocks, key_fn):
    """Every ADR 0020 stage output, under a given block key."""
    registry = PdfObservationRegistry(v1_blocks, v2_blocks)
    a = [key_fn(b) for b in v1_blocks]
    b = [key_fn(b) for b in v2_blocks]
    opcodes = difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()

    DP._block_key = key_fn
    try:
        round1 = DP.pdf_round1_with_stage_outputs(
            v1_blocks, v2_blocks, registry, threshold=SIMILARITY_THRESHOLD, move_threshold=MOVE_THRESHOLD
        )
        pairings = list(round1.pairings)
        population = DP.pdf_unmatched_population(pairings, registry)
        evidence = DP.pdf_move_evidence(DP.retrieve_pdf_move_candidates(population, bound=MOVE_THRESHOLD))
        moves = DP.assign_pdf_moves(population, evidence, threshold=MOVE_THRESHOLD)
        settled = DP.settle_pdf_correspondences(
            pairings, registry, moves, round1_evidence=round1.evidence, round1_move_bases=round1.move_bases
        )
        diff = DP.PdfDiff(hunks=tuple(DP.classify_pdf(settled, registry)))
    finally:
        DP._block_key = ORIGINAL_BLOCK_KEY

    def refs(stream):
        return [
            (registry.ref(DP.OLD, p.old).ordinal, registry.ref(DP.NEW, p.new).ordinal)
            for p in stream
            if p.old is not None and p.new is not None
        ]

    return {
        "dup_keys_v1": len(a) - len(set(a)),
        "dup_keys_v2": len(b) - len(set(b)),
        "opcodes": digest([tuple(o) for o in opcodes]),
        "considered": digest(refs(round1.provisional)),
        "candidates": digest(sorted((c.old.ordinal, c.new.ordinal) for c in round1.candidates.candidates())),
        "post_revocation": digest(refs(pairings)),
        "round2_unmatched": (len(population.old), len(population.new)),
        "n_moves_round2": len(moves),
        "summary": dict(Counter(h.change_type for h in diff.hunks)),
        "canonical": digest(pdf_diff_to_canonical(diff, bill_type="hr", bill_number=1, congress=118)["changes"]),
    }


def parser_revision_sensitivity() -> None:
    print("=== ADR 0019 observation closure ===")
    for module, path in sorted(observation_closure().items()):
        print(f"    {module:<34} {path.relative_to(PROJECT_ROOT)}")
    baseline = pdf_parser_revision()
    print("\n=== does editing each file move pdf_parser_revision()? ===")
    for rel in PERTURB:
        source = PROJECT_ROOT / rel
        original = source.read_bytes()
        try:
            source.write_bytes(original + b"\n# probe perturbation\n")
            moved = pdf_parser_revision() != baseline
        finally:
            source.write_bytes(original)
        assert pdf_parser_revision() == baseline, f"failed to restore {rel}"
        print(f"    {rel:<46} {'MOVES' if moved else 'no change'}")


def main() -> None:
    parser_revision_sensitivity()

    print("\n\n=== DISPLAY: canonical move.kind under a run identity ===")
    label_change: Counter = Counter()
    kinds: Counter = Counter()
    flips = defaultdict(list)
    seen_pages = {}
    for bill, old, new in accepted_pdf_pairs():
        old_pages, new_pages = pages_for(old), pages_for(new)
        seen_pages[old] = old_pages
        seen_pages[new] = new_pages
        old_index, new_index = band_run_index(old_pages), band_run_index(new_pages)
        for hunk in DP.diff_pdfs(old_pages, new_pages).hunks:
            if hunk.change_type != "moved":
                continue
            a1, a2 = hunk.v1_anchor, hunk.v2_anchor
            kinds[(a1.kind if a1 else None, a2.kind if a2 else None)] += 1
            raw_differ = bool(a1 and a2 and a1.text != a2.text)
            id1 = old_index.get((a1.page_number, a1.line_number)) if a1 else None
            id2 = new_index.get((a2.page_number, a2.line_number)) if a2 else None
            eff1 = id1 if id1 is not None else (a1.text if a1 else None)
            eff2 = id2 if id2 is not None else (a2.text if a2 else None)
            id_differ = bool(eff1 is not None and eff2 is not None and eff1 != eff2)
            before = "renumbered" if raw_differ else "relocated"
            after = "renumbered" if id_differ else "relocated"
            label_change[(before, after)] += 1
            if before != after:
                flips[(bill, f"{old.stem}->{new.stem}")].append((a1.text, a2.text, eff1))
    print("  moved rows by (v1 kind, v2 kind):")
    for key, count in kinds.most_common():
        print(f"    {str(key):<42}{count:>5}")
    print("  canonical move.kind, today -> under run identity:")
    for key, count in sorted(label_change.items(), key=lambda kv: -kv[1]):
        print(f"    {key[0]:<12} -> {key[1]:<12}{count:>5}")
    print("\n  the rows whose label changes (every one a wrap artifact):")
    for key, rows in sorted(flips.items()):
        print(f"    {key[0]} {key[1]}")
        for t1, t2, ident in rows:
            print(f"       raw {t1!r} -> {t2!r}")
            print(f"       run {ident!r}")

    print("\n\n=== is a run identity unique per BLOCK? ===")
    totals: Counter = Counter()
    for path, pages in seen_pages.items():
        index = band_run_index(pages)
        by_label = defaultdict(list)
        for block in blocks_for(pages):
            if block.anchor is None:
                continue
            label = index.get((block.anchor.page_number, block.anchor.line_number))
            if label is not None:
                by_label[label].append(block.anchor)
        totals["labels"] += len(by_label)
        totals["colliding"] += sum(1 for v in by_label.values() if len(v) > 1)
        totals["blocks_in_collisions"] += sum(len(v) for v in by_label.values() if len(v) > 1)
    print(
        f"    labels={totals['labels']} carried by >1 block={totals['colliding']} "
        f"blocks inside a collision={totals['blocks_in_collisions']}"
    )
    print("    a label is therefore NOT an observation key.")

    print("\n\n=== RETRIEVAL: the same identity substituted into _block_key ===")
    changed: Counter = Counter()
    pairs = 0
    for bill, old, new in accepted_pdf_pairs():
        old_pages, new_pages = pages_for(old), pages_for(new)
        v1_blocks, v2_blocks = blocks_for(old_pages), blocks_for(new_pages)
        old_index, new_index = band_run_index(old_pages), band_run_index(new_pages)
        v1_ids = set(map(id, v1_blocks))

        def runid_key(block, _o=old_index, _n=new_index, _v1=v1_ids):
            index = _o if id(block) in _v1 else _n
            anchor = block.anchor
            label = "(preamble)"
            if anchor is not None:
                label = index.get((anchor.page_number, anchor.line_number), anchor.text)
            return f"{label}::{block.text[:80].strip()}"

        base = stage_snapshot(v1_blocks, v2_blocks, ORIGINAL_BLOCK_KEY)
        alt = stage_snapshot(v1_blocks, v2_blocks, runid_key)
        pairs += 1
        moved_fields = [f for f in STAGE_FIELDS if base[f] != alt[f]]
        for field in moved_fields:
            changed[field] += 1
        print(f"  {bill} {old.stem}->{new.stem}: {moved_fields or 'no stage output changes'}")
    print(f"\n  across {pairs} accepted pairs, how many changed per stage output:")
    for field in STAGE_FIELDS:
        print(f"    {field:<20}{changed[field]:>4}")
    print("  a non-zero row below `opcodes` is a matching-policy change (#170), not a label change.")


if __name__ == "__main__":
    main()
