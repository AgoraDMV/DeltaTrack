"""What a PDF observation would be, and whether it can carry an ADR 0019 address.

Answers four questions the observation contract turns on, over every committed PDF:

1. **Is emission deterministic?** ADR 0019 open question 2 records this as measured on
   the XML pipeline only. Checked by extracting each document twice and comparing the
   *whole* emitted sequence — lines, anchors and blocks — element by element. A digest
   over the node *set* would be blind to a reordering, which is the one fault an
   ordinal-based identity exists to catch.
2. **Is the block sequence complete?** ``_group_into_blocks`` drops empty blocks, so an
   ordinal over its output indexes a filtered view — the hazard ADR 0019 names by name.
   Counted here, and cross-checked against the anchor coordinate collisions the code
   says cause them.
3. **Is the alignment key discriminating?** ``_block_key`` is the unit the whole first
   retrieval round is built on. Duplicate keys mean two observations are
   indistinguishable to it.
4. **Does ``breadcrumb_for``'s value-equality invariant hold?** It resolves an anchor's
   position with ``.index()``, so two value-equal anchors would mis-nest the tree.

    uv run python docs/research/pdf-matching-convergence/probes/pdf_observation_census.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import CACHE_DIR, blocks_for, corpus_pdfs  # noqa: E402

from deltatrack.compare.pdf import _is_unnumbered_layout  # noqa: E402
from deltatrack.diff_pdf import _block_key, _flatten  # noqa: E402
from deltatrack.parsers.pdf_anchors import extract_anchors  # noqa: E402
from deltatrack.parsers.pdf_text import extract_clean_pages  # noqa: E402


def _blocks_before_the_empty_filter(indexed, anchors) -> int:
    """How many blocks ``_group_into_blocks`` forms before it drops the empty ones.

    Re-derived the way that function derives it — first-occurrence ``(page, line)``
    index, anchors that resolve to no surviving line skipped — rather than by counting
    anchors, which would over-count by exactly the skipped ones and attribute their
    absence to the empty filter.
    """
    first_at: dict[tuple[int, int | None], int] = {}
    for i, line in enumerate(indexed):
        first_at.setdefault((line.page_number, line.line_number), i)
    resolved = [first_at[(a.page_number, a.line_number)] for a in anchors if (a.page_number, a.line_number) in first_at]
    if not resolved:
        return 1 if indexed else 0
    return len(resolved) + (1 if resolved[0] > 0 else 0)


def main() -> None:
    pdfs = corpus_pdfs()
    print(f"{len(pdfs)} committed PDFs", file=sys.stderr, flush=True)
    rows = []
    for n, pdf in enumerate(pdfs, 1):
        print(f"[{n}/{len(pdfs)}] {pdf.parent.name}/{pdf.stem}", file=sys.stderr, flush=True)
        # Deliberately NOT the cache: the question is whether extraction repeats itself,
        # so both runs must be real extractions.
        first, second = extract_clean_pages(pdf), extract_clean_pages(pdf)
        lines_a, lines_b = _flatten(first), _flatten(second)
        anchors_a, anchors_b = extract_anchors(first), extract_anchors(second)
        blocks_a, blocks_b = blocks_for(first), blocks_for(second)

        key_demand = Counter(_block_key(b) for b in blocks_a)
        coord_demand = Counter((a.page_number, a.line_number) for a in anchors_a)
        value_demand = Counter(anchors_a)

        rows.append(
            {
                "bill": pdf.parent.name,
                "version": pdf.stem,
                "pages": len(first),
                "lines": len(lines_a),
                "declined_by_production": _is_unnumbered_layout(first),
                "anchors": len(anchors_a),
                "anchor_kinds": dict(Counter(a.kind for a in anchors_a)),
                "value_equal_duplicate_anchors": sum(n - 1 for n in value_demand.values() if n > 1),
                "anchor_coord_collisions": sum(n - 1 for n in coord_demand.values() if n > 1),
                "blocks": len(blocks_a),
                "blocks_dropped_empty": _blocks_before_the_empty_filter(lines_a, anchors_a) - len(blocks_a),
                "block_key_collisions": sum(n - 1 for n in key_demand.values() if n > 1),
                "blocks_sharing_a_key": sum(n for n in key_demand.values() if n > 1),
                "deterministic_lines": lines_a == lines_b,
                "deterministic_anchors": anchors_a == anchors_b,
                "deterministic_blocks": blocks_a == blocks_b,
            }
        )

    print("\n=== determinism (re-extract, compare the complete emitted sequence) ===")
    for field in ("deterministic_lines", "deterministic_anchors", "deterministic_blocks"):
        failures = [f"{r['bill']}/{r['version']}" for r in rows if not r[field]]
        print(f"  {field:24s} {sum(r[field] for r in rows)}/{len(rows)}  failures: {failures or 'none'}")

    print("\n=== observation sequence ===")
    for field in (
        "anchors",
        "blocks",
        "blocks_dropped_empty",
        "anchor_coord_collisions",
        "value_equal_duplicate_anchors",
        "block_key_collisions",
        "blocks_sharing_a_key",
    ):
        print(f"  {field:32s} {sum(r[field] for r in rows):,}")
    print(f"  {'declined_by_production':32s} {sum(r['declined_by_production'] for r in rows)}")

    kinds: Counter = Counter()
    for r in rows:
        kinds.update(r["anchor_kinds"])
    print(f"\n  anchor kinds: {dict(kinds.most_common())}")

    print("\n=== documents whose alignment key is least discriminating ===")
    for r in sorted(rows, key=lambda r: -r["block_key_collisions"])[:8]:
        if r["block_key_collisions"]:
            print(
                f"  {r['bill']:14s} {r['version'][:30]:30s} blocks={r['blocks']:5,d} "
                f"duplicate keys={r['block_key_collisions']:4d} blocks affected={r['blocks_sharing_a_key']:4d}"
            )

    out = Path(__file__).resolve().parent.parent / "results" / "observation-census.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2) + "\n")
    print(f"\nwrote {out.relative_to(PROJECT_ROOT)} (cache: {CACHE_DIR.relative_to(PROJECT_ROOT)})", file=sys.stderr)


if __name__ == "__main__":
    main()
