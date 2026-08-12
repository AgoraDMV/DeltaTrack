"""If a zero-content block is not an observation, what becomes unaddressable?

`_group_into_blocks` drops blocks whose line slice is empty. An earlier draft of the README
concluded those were absent observations and that the filter should be lifted into retrieval
so the ordinal could index a complete pre-filter sequence. A second review rejected that:
ADR 0019 says the ordinal indexes the parser's *complete emitted sequence*, and says nothing
about intermediate objects built while deriving it. Which objects the parser emits is the
question, and assuming the pre-filter list is the answer begs it.

This is the falsification the review asked for. For every dropped block, check whether the
anchor it would have carried stays reachable three independent ways:

  1. in ``extract_anchors``' output — the anchor stream ``PdfDiff`` carries;
  2. as a node in the canonical structure tree (``build_pdf_tree``);
  3. via a breadcrumb that names it.

If all three hold for every dropped block, nothing becomes unaddressable and the emitted
sequence may legitimately exclude them.

**Cache misses extract rather than skip.** A miss that skipped the document would report
unanimous addressability over whatever subset happened to be warm — a vacuous pass, and the
exact shape this study's own gate analysis warns about.

    uv run python docs/research/pdf-matching-convergence/probes/pdf_dropped_block_addressability.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import corpus_pdfs, pages_for  # noqa: E402

from deltatrack.diff_pdf import _flatten, _group_into_blocks  # noqa: E402
from deltatrack.parsers.pdf_anchors import breadcrumb_for, extract_anchors  # noqa: E402
from deltatrack.structure_tree import TreeNode, build_pdf_tree  # noqa: E402


def dropped_anchors(indexed, anchors):
    """The anchors whose block ``_group_into_blocks`` would build empty and discard.

    Derived the way that function derives it — first-occurrence ``(page, line)`` index,
    anchors resolving to no surviving line skipped — so this names the same blocks rather
    than an approximation of them.
    """
    first_at: dict[tuple[int, int | None], int] = {}
    for i, line in enumerate(indexed):
        first_at.setdefault((line.page_number, line.line_number), i)
    resolved = [
        (a, first_at[(a.page_number, a.line_number)]) for a in anchors if (a.page_number, a.line_number) in first_at
    ]
    out = []
    for j, (anchor, pos) in enumerate(resolved):
        end = resolved[j + 1][1] if j + 1 < len(resolved) else len(indexed)
        if end <= pos:
            out.append(anchor)
    return out


def sourced_node_ids(nodes: list[TreeNode], seen: set[int]) -> set[int]:
    for node in nodes:
        if node.source is not None:
            seen.add(id(node.source))
        sourced_node_ids(node.children, seen)
    return seen


def main() -> None:
    pdfs = corpus_pdfs()
    print(f"{len(pdfs)} committed PDFs", file=sys.stderr, flush=True)
    total = 0
    kinds: Counter = Counter()
    reachable = {"anchor_stream": 0, "structure_tree": 0, "breadcrumb": 0}
    per_doc = []

    for n, pdf in enumerate(pdfs, 1):
        print(f"[{n}/{len(pdfs)}] {pdf.parent.name}/{pdf.stem}", file=sys.stderr, flush=True)
        pages = pages_for(pdf)
        indexed = _flatten(pages)
        anchors = extract_anchors(pages)
        dropped = dropped_anchors(indexed, anchors)
        if not dropped:
            continue
        # Sanity: the count must agree with what the block builder actually discards.
        rebuilt = len(dropped_anchors(indexed, anchors))
        assert rebuilt == len(dropped)
        in_tree = sourced_node_ids(build_pdf_tree(anchors), set())

        for anchor in dropped:
            total += 1
            kinds[anchor.kind] += 1
            reachable["anchor_stream"] += anchor in anchors
            reachable["structure_tree"] += id(anchor) in in_tree
            crumb = breadcrumb_for(anchor, anchors)
            reachable["breadcrumb"] += bool(crumb) and crumb[-1] == anchor.text
        per_doc.append({"bill": pdf.parent.name, "version": pdf.stem, "dropped": len(dropped)})

    print(f"\ndropped (zero-content) blocks: {total}")
    print(f"  anchor kinds: {dict(kinds)}")
    for label, count in reachable.items():
        print(f"  still reachable via {label:16s} {count}/{total}")

    unanimous = total and all(count == total for count in reachable.values())
    print(
        "\nRESULT: nothing becomes unaddressable — the emitted sequence may exclude them."
        if unanimous
        else "\nRESULT: at least one dropped block is NOT otherwise addressable. It must be emitted."
    )

    out = Path(__file__).resolve().parent.parent / "results" / "dropped-block-addressability.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"total": total, "kinds": dict(kinds), "reachable": reachable, "per_doc": per_doc}, indent=2) + "\n"
    )
    print(f"wrote {out.relative_to(PROJECT_ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
