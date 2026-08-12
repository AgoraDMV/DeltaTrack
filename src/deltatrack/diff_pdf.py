"""Block-level diff for PDF bill versions, parallel to diff_bill.py for XML.

No shebang since #398 -- see `diff_bill`'s module docstring for why a module inside a
package cannot be executed directly. `./diff_pdf.py` at the repo root wraps this.

A bill is grouped into anchor-delimited blocks (TITLE / SEC. / account heading)
on each side, then aligned section-by-section. Lines before the first anchor
form a preamble block. The block is the natural unit of comparison — it mirrors
how `diff_bill.match_nodes` operates on BillTree nodes for XML and avoids the
SequenceMatcher line-level fragmentation that produced over-counted hunks and
missed added/moved sections.

**The blocks themselves are produced by `parsers.pdf_blocks`, not here.** That module
owns observation production — flattening, cross-page hyphen rejoin, anchor-delimited
grouping, heading-chrome stripping — and this one owns matching and classification
policy. The split is ADR 0020 slice 1, and it is what lets an ADR 0019 PDF parser
revision be derived without hashing the matcher; see that module's docstring. This
module consumes those blocks and must remain downstream of them.

Within matched blocks, the renderer applies word-level diff against the joined
block text. The classifier produces:

- `added` — block present only in v2
- `removed` — block present only in v1
- `moved` — block bodies similar but anchors differ (renumbered SEC.)
- `modified` — paired blocks with different bodies

Reuses amount matching (`match_amounts`) from diff_bill.py and text similarity
(`text_similarity_at_least`, `move_candidates`) plus both cutoffs from similarity.py.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from deltatrack.diff_bill import match_amounts
from deltatrack.parsers.pdf_anchors import Anchor, extract_anchors
from deltatrack.parsers.pdf_blocks import (
    PageLineRange,
    _Block,
    _flatten,
    _group_into_blocks,
    _with_front_matter,
)
from deltatrack.parsers.pdf_text import Page
from deltatrack.similarity import (
    MOVE_THRESHOLD,
    SIMILARITY_THRESHOLD,
    move_candidates,
    text_similarity_at_least,
)
from deltatrack.version_stems import label_from_stem

ChangeType = Literal["added", "removed", "modified", "moved"]

_AMENDMENT_RE_DETAIL = re.compile(r"\((increased|reduced|decreased) by\s+\$([\d,]+)\)")

# What the two shared cutoffs mean HERE (they are defined in deltatrack.similarity,
# #492, and were re-declared in this module until then — two copies kept in step by a
# comment saying they were, which is not a mechanism).
#
# MOVE_THRESHOLD: body similarity needed to call a block-pair "moved" rather than
# "modified", and to reconcile a removed+added pair as moved.
#
# SIMILARITY_THRESHOLD: below it, two blocks paired by alignment aren't really a
# modified pair — they're an unrelated removal + addition that happen to share an
# anchor (e.g. v1 SEC. 413 = H-2A waiver, v2 SEC. 413 = Asylum Fee renumbered from
# SEC. 414). Split them so reconcile_moves can pair v1 SEC. 414 with v2 SEC. 413 by
# body similarity.


@dataclass(frozen=True)
class PdfHunk:
    change_type: ChangeType
    v1_anchor: Anchor | None
    v2_anchor: Anchor | None
    v1_range: PageLineRange | None
    v2_range: PageLineRange | None
    v1_text: str
    v2_text: str
    amount_pairs: tuple[tuple[int | None, int | None], ...] = ()
    has_amendment_annotations: bool = False  # mirrors FinancialChange field for XML parity


@dataclass(frozen=True)
class PdfDiff:
    hunks: tuple[PdfHunk, ...]
    v1_anchors: tuple[Anchor, ...] = ()
    v2_anchors: tuple[Anchor, ...] = ()

    @property
    def summary(self) -> dict[str, int]:
        return dict(Counter(h.change_type for h in self.hunks))


# ---- Internal helpers --------------------------------------------------------


def _block_key(block: _Block) -> str:
    """Alignment key for SequenceMatcher.

    Combines anchor text (e.g. "SEC. 101", "OPERATIONS AND SUPPORT") with the
    first ~80 chars of the block's body to disambiguate non-unique account
    headings while staying stable to amendment annotations appearing later
    in the body.
    """
    anchor_text = block.anchor.text if block.anchor else "(preamble)"
    body_preview = block.text[:80].strip()
    return f"{anchor_text}::{body_preview}"


def _extract_amount_pairs(v1_text: str, v2_text: str) -> tuple[tuple[int | None, int | None], ...]:
    """All amount pairs from match_amounts as a tuple, including unchanged pairs.

    The full pair list (changed / added / removed / unchanged) is carried on the
    hunk. The canonical producer categorizes it into `amount_entries` — the export's
    only money field since v2.0 (#274) — dropping unchanged (`old == new`) pairs
    there (`formatters/canonical.py:_amount_entries`). Preserving the unchanged
    pairs here keeps this function a lossless view of match_amounts.
    """
    return tuple(match_amounts(v1_text, v2_text))


def _has_amendment_annotations(v1_text: str, v2_text: str) -> bool:
    """True if either side carries a floor amendment annotation.

    Mirrors `FinancialChange.has_amendment_annotations` in diff_bill.py.
    """
    return bool(_AMENDMENT_RE_DETAIL.search(v1_text) or _AMENDMENT_RE_DETAIL.search(v2_text))


def _hunk_for_paired_blocks(v1_block: _Block, v2_block: _Block, similarity: float) -> PdfHunk:
    """Emit a hunk for two blocks paired by alignment.

    Classifies as `moved` when anchors differ and bodies are highly similar
    (renumbered SEC.), else `modified`. Caller has already confirmed v1 and v2
    block texts differ AND has computed `similarity` (the
    `text_similarity` between the two block texts) to decide split-vs-pair.
    """
    v1_text = v1_block.text
    v2_text = v2_block.text
    v1_anchor = v1_block.anchor
    v2_anchor = v2_block.anchor
    if v1_anchor and v2_anchor and v1_anchor.text != v2_anchor.text and similarity >= MOVE_THRESHOLD:
        change_type: ChangeType = "moved"
    else:
        change_type = "modified"
    return PdfHunk(
        change_type=change_type,
        v1_anchor=v1_anchor,
        v2_anchor=v2_anchor,
        v1_range=v1_block.page_range,
        v2_range=v2_block.page_range,
        v1_text=v1_text,
        v2_text=v2_text,
        amount_pairs=_extract_amount_pairs(v1_text, v2_text),
        has_amendment_annotations=_has_amendment_annotations(v1_text, v2_text),
    )


def _hunk_for_added(v2_block: _Block) -> PdfHunk:
    # A whole account added on the PDF side carries real dollars; match against the
    # empty other side so they surface as `added` amount entries (#86). Previously
    # hardcoded to (), leaving PDF added/removed hunks silent on the money axis.
    return PdfHunk(
        change_type="added",
        v1_anchor=None,
        v2_anchor=v2_block.anchor,
        v1_range=None,
        v2_range=v2_block.page_range,
        v1_text="",
        v2_text=v2_block.text,
        amount_pairs=tuple(match_amounts("", v2_block.text)),
        has_amendment_annotations=_has_amendment_annotations("", v2_block.text),
    )


def _hunk_for_removed(v1_block: _Block) -> PdfHunk:
    # Mirror of _hunk_for_added: a whole account removed surfaces its dollars as
    # `removed` entries (#86).
    return PdfHunk(
        change_type="removed",
        v1_anchor=v1_block.anchor,
        v2_anchor=None,
        v1_range=v1_block.page_range,
        v2_range=None,
        v1_text=v1_block.text,
        v2_text="",
        amount_pairs=tuple(match_amounts(v1_block.text, "")),
        has_amendment_annotations=_has_amendment_annotations(v1_block.text, ""),
    )


def _reconcile_moves(hunks: list[PdfHunk], threshold: float = MOVE_THRESHOLD) -> list[PdfHunk]:
    """Pair `removed`+`added` hunks whose bodies are highly similar into `moved` hunks.

    Catches renumbered sections (e.g. SEC. 414 in v1 → SEC. 413 in v2) when block
    keys diverge enough that SequenceMatcher emitted them as separate insert
    and delete rather than aligning them. Mirrors `diff_bill.reconcile_moves`.
    """
    removed_idx = [i for i, h in enumerate(hunks) if h.change_type == "removed"]
    added_idx = [i for i, h in enumerate(hunks) if h.change_type == "added"]
    if not removed_idx or not added_idx:
        return hunks

    # Gated + matcher-reused pairwise similarity; move_candidates returns local
    # indices, so map them back to absolute hunk indices. Identical result to the
    # naive removed×added loop for every pair with text on both sides (same tuples;
    # the sort below is what orders them).
    #
    # Text-free hunks yield no candidate, so they are never paired here (#357). That
    # rule was added for the XML side, where a section whose subsections all became
    # their own nodes keeps the SEC. heading and an empty body (#188); difflib scores
    # two empty sequences as a perfect 1.0, so such pairs used to be claimed as moves
    # on no evidence. Blocks here do not reach that state today -- `_strip_heading_lines`
    # returns the lines untouched rather than empty a body -- and no committed PDF pair
    # produces a text-free hunk, so this path is unchanged in practice. The rule is kept
    # uniform across both callers because a hunk with no text carries no evidence of
    # having moved anywhere either way.
    local = move_candidates(
        [hunks[ri].v1_text for ri in removed_idx],
        [hunks[ai].v2_text for ai in added_idx],
        threshold,
    )
    candidates = [(sim, removed_idx[r], added_idx[a]) for sim, r, a in local]
    if not candidates:
        return hunks

    candidates.sort(reverse=True)
    claimed_r: set[int] = set()
    claimed_a: set[int] = set()
    moved_pairs: list[tuple[int, int]] = []
    for _, ri, ai in candidates:
        if ri in claimed_r or ai in claimed_a:
            continue
        claimed_r.add(ri)
        claimed_a.add(ai)
        moved_pairs.append((ri, ai))

    consumed = claimed_r | claimed_a
    moved_lookup = {ri: ai for ri, ai in moved_pairs}
    result: list[PdfHunk] = []
    for i, h in enumerate(hunks):
        if i in moved_lookup:
            removed = h
            added = hunks[moved_lookup[i]]
            result.append(
                PdfHunk(
                    change_type="moved",
                    v1_anchor=removed.v1_anchor,
                    v2_anchor=added.v2_anchor,
                    v1_range=removed.v1_range,
                    v2_range=added.v2_range,
                    v1_text=removed.v1_text,
                    v2_text=added.v2_text,
                    amount_pairs=_extract_amount_pairs(removed.v1_text, added.v2_text),
                    has_amendment_annotations=_has_amendment_annotations(removed.v1_text, added.v2_text),
                )
            )
        elif i in consumed:
            continue
        else:
            result.append(h)
    return result


# ---- Public entry point ------------------------------------------------------


def _emit_pair(v1_b: _Block, v2_b: _Block, sink: list[PdfHunk]) -> None:
    """Emit a paired-block hunk into `sink`, or split into removed+added.

    When v1/v2 block texts are very dissimilar, treat the pair as an unrelated
    removal and addition that happen to share alignment — emit two hunks so
    `_reconcile_moves` can later pair them with the right counterparts.
    """
    if v1_b.text == v2_b.text:
        # Stripping headings from the body (#56) can equalize two blocks that
        # differ only by a renamed anchor (an account renamed with otherwise
        # identical prose). With the heading gone from the body, that rename
        # would vanish; surface it as a moved/renamed hunk instead.
        if v1_b.anchor and v2_b.anchor and v1_b.anchor.text != v2_b.anchor.text:
            sink.append(_hunk_for_paired_blocks(v1_b, v2_b, similarity=1.0))
        return
    # Gate at the lower (split) threshold: at or above it the exact ratio is
    # needed downstream for the MOVE_THRESHOLD moved/modified split in _hunk_for_paired_blocks.
    sim = text_similarity_at_least(v1_b.text, v2_b.text, SIMILARITY_THRESHOLD)
    if sim < SIMILARITY_THRESHOLD:
        sink.append(_hunk_for_removed(v1_b))
        sink.append(_hunk_for_added(v2_b))
    else:
        sink.append(_hunk_for_paired_blocks(v1_b, v2_b, similarity=sim))


def diff_pdfs(v1_pages: list[Page], v2_pages: list[Page]) -> PdfDiff:
    """Block-level diff of two extracted PDF page sequences."""
    v1_indexed = _flatten(v1_pages)
    v2_indexed = _flatten(v2_pages)
    v1_anchors = extract_anchors(v1_pages)
    v2_anchors = extract_anchors(v2_pages)

    v1_blocks = _group_into_blocks(v1_indexed, v1_anchors)
    v2_blocks = _group_into_blocks(v2_indexed, v2_anchors)

    # Surface the front-matter anchor synthesized per-block (issue #33) into the
    # anchor lists so the full-bill section TOC links to it like any other anchor.
    v1_anchors = _with_front_matter(v1_blocks, v1_anchors)
    v2_anchors = _with_front_matter(v2_blocks, v2_anchors)

    matcher = difflib.SequenceMatcher(
        a=[_block_key(b) for b in v1_blocks],
        b=[_block_key(b) for b in v2_blocks],
        autojunk=False,
    )

    hunks: list[PdfHunk] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            # Block keys match. Bodies might still differ (e.g. amendment
            # annotations appearing past the 80-char preview).
            for v1_b, v2_b in zip(v1_blocks[i1:i2], v2_blocks[j1:j2]):
                _emit_pair(v1_b, v2_b, hunks)
        elif op == "delete":
            for v1_b in v1_blocks[i1:i2]:
                hunks.append(_hunk_for_removed(v1_b))
        elif op == "insert":
            for v2_b in v2_blocks[j1:j2]:
                hunks.append(_hunk_for_added(v2_b))
        else:  # replace
            v1_slice = v1_blocks[i1:i2]
            v2_slice = v2_blocks[j1:j2]
            # Pair positionally; surplus on either side becomes added/removed.
            for k in range(max(len(v1_slice), len(v2_slice))):
                v1_b = v1_slice[k] if k < len(v1_slice) else None
                v2_b = v2_slice[k] if k < len(v2_slice) else None
                if v1_b is not None and v2_b is not None:
                    _emit_pair(v1_b, v2_b, hunks)
                elif v1_b is not None:
                    hunks.append(_hunk_for_removed(v1_b))
                else:
                    assert v2_b is not None
                    hunks.append(_hunk_for_added(v2_b))

    return PdfDiff(
        hunks=tuple(_reconcile_moves(hunks)),
        v1_anchors=tuple(v1_anchors),
        v2_anchors=tuple(v2_anchors),
    )


# ---- CLI ---------------------------------------------------------------------


def render_pdf_diff_html(
    v1_pdf: Path,
    v2_pdf: Path,
    *,
    v1_label: str | None = None,
    v2_label: str | None = None,
) -> str:
    """Render an HTML diff page for two PDF paths.

    Delegates to ``compare.pdf.compare_pdfs_html`` — the same pipeline
    the web app uses — so the report carries the full-bill text view, in-page
    search, section TOC, and embedded export. Title and Congress are derived
    from the PDF front matter; labels default to the (de-prefixed) filename
    stems. Imported lazily to avoid a circular import (compare.pdf imports
    diff_pdf).
    """
    from deltatrack.compare.pdf import compare_pdfs_html

    return compare_pdfs_html(
        v1_pdf.read_bytes(),
        v2_pdf.read_bytes(),
        start_label=v1_label if v1_label is not None else label_from_stem(v1_pdf.stem),
        end_label=v2_label if v2_label is not None else label_from_stem(v2_pdf.stem),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diff two PDF bill versions and produce an HTML diff page "
        "(full-bill view, search, and export included).",
    )
    parser.add_argument("v1_pdf", type=Path, help="Path to the older PDF")
    parser.add_argument("v2_pdf", type=Path, help="Path to the newer PDF")
    parser.add_argument("-o", "--output", type=Path, help="Output HTML file (default: stdout)")
    parser.add_argument("--v1-label", help="Label for the older version (default: filename stem)")
    parser.add_argument("--v2-label", help="Label for the newer version (default: filename stem)")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    html = render_pdf_diff_html(
        args.v1_pdf,
        args.v2_pdf,
        v1_label=args.v1_label,
        v2_label=args.v2_label,
    )
    if args.output:
        args.output.write_text(html)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(html)


if __name__ == "__main__":
    main()
