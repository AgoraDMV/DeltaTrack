"""Derived sidecar tree for the leveled bill structure (#108).

Both pipelines keep emitting their flat lists (XML ``BillNode`` via
``bill_tree.normalize_bill``; PDF ``Anchor`` via ``parsers.pdf_anchors``). This
module reconstructs a navigable parent/child ``TreeNode`` tree FROM those flat
lists — the diff engine is untouched (it still matches per-node by
``match_path``). A tree-aware diff backbone is deferred; this tree + its tests +
the conservation gate are that future refactor's de-risking spec (ADR 0005/0006).

Structure is recovered from **division-qualified ``display_path`` prefix-nesting**:
interior levels (division, department, agency, grouping header) are not emitted as
their own nodes in the corpus — they exist only as ``display_path`` strings — so
each path prefix becomes a synthesized interior ``TreeNode`` and the path's flat
node becomes a content node. The leaf's typed ``tag`` refines only the leaf level;
interior levels are positional (#108 locked decision 1). Orphan titles are already
attributed to their division upstream in ``normalize_bill`` (their ``display_path``
carries the division prefix), so the builder needs no special orphan logic.

``level`` uses the shared GPO-grounded vocabulary documented in
``docs/bill-structure.md`` (division / title / major / agency / account / section /
grouping / preamble), so the canonical contract speaks one language both pipelines
map into (ADR 0006/0007 — no pipeline branch in the renderer).

Steps 1-2: the ``TreeNode`` type + the XML and PDF builders, sharing one trie
core. Per-block ``own_amounts`` + canonical ``tree`` spans (steps 3-4) land later.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from bill_tree import BillNode, BillTree
from parsers.pdf_anchors import Anchor, breadcrumb_for

# Leaf level from the XML tag — typed and reliable (docs/bill-structure.md glossary).
_LEAF_LEVEL: dict[str, str] = {
    "appropriations-major": "major",  # department / large org unit
    "appropriations-intermediate": "agency",  # bureau / agency
    "appropriations-small": "account",  # the budget account that holds money
    "section": "section",  # general-provisions SEC.
    "front-matter": "preamble",  # bill front matter
}

# A real title heading is "TITLE <roman>" / "TITLE <roman>—<header>". Requiring a
# roman numeral (not just the word "Title") avoids misreading an account named
# "Title 17 ..." as a title-level heading (#155 / #114 — text triggers must not
# drive structure; here they can't, since this only labels already-interior nodes).
_TITLE_RE = re.compile(r"^TITLE\s+[IVXLCDM]+\b", re.IGNORECASE)


def _leaf_level(tag: str) -> str:
    return _LEAF_LEVEL.get(tag, "account")


def _interior_level(label: str) -> str:
    if label.startswith("Division "):
        return "division"
    if _TITLE_RE.match(label):
        return "title"
    return "heading"  # department / agency / grouping container — not typed from a string


@dataclass
class TreeNode:
    """One node in the leveled structure tree.

    A node carries content when it wraps a flat ``BillNode`` (``source is not
    None``) and carries structure when it has ``children``. The two are
    independent: a synthesized interior (division/title/agency container) has
    ``source is None``; an account that also holds sub-accounts has both a
    ``source`` and ``children``. ``own_amounts`` and ``full_text_span`` are
    populated in later steps; they are absent here so the type is reviewable now.
    """

    label: str
    """The path component this node represents ("" for an empty-path root)."""

    level: str
    """Shared GPO vocabulary. Leaf: from the source tag. Interior: positional."""

    display_path: tuple[str, ...]
    """Full path identity from the root to this node."""

    children: list[TreeNode] = field(default_factory=list)
    source: BillNode | Anchor | None = None
    """The flat node when this path carries content; ``None`` for a pure container."""


def _build_tree(items: Iterable[tuple[tuple[str, ...], str, object]]) -> list[TreeNode]:
    """Shared trie builder over ``(path, level, source)`` items in document order.

    Each path prefix that has no item of its own becomes a synthesized interior
    node (``source is None``, positional level). An item whose path was already
    synthesized as an interior is adopted as that node's content — so a node can
    be both content and container (an account holding sub-accounts; a PDF
    title/agency anchor that scopes deeper accounts). Duplicate paths (genuine
    cross-division collisions) become distinct content siblings, never merged, so
    every item is conserved as exactly one content node.
    """
    roots: list[TreeNode] = []
    by_path: dict[tuple[str, ...], TreeNode] = {}

    def ensure_interior(path: tuple[str, ...]) -> TreeNode:
        node = by_path.get(path)
        if node is not None:
            return node
        node = TreeNode(label=path[-1], level=_interior_level(path[-1]), display_path=path)
        by_path[path] = node
        if len(path) == 1:
            roots.append(node)
        else:
            ensure_interior(path[:-1]).children.append(node)
        return node

    for path, level, source in items:
        if not path:
            # Empty-path content (front matter, body-level "Sec. 1"): a top-level leaf.
            roots.append(TreeNode(label="", level=level, display_path=path, source=source))
            continue

        existing = by_path.get(path)
        if existing is not None and existing.source is None:
            existing.source = source
            existing.level = level
            continue

        leaf = TreeNode(label=path[-1], level=level, display_path=path, source=source)
        if len(path) == 1:
            roots.append(leaf)
        else:
            ensure_interior(path[:-1]).children.append(leaf)
        # Register the first occurrence so deeper nodes nest under it; a later
        # item at the same path is a genuine duplicate -> distinct sibling (above).
        by_path.setdefault(path, leaf)

    return roots


def build_xml_tree(bill: BillTree) -> list[TreeNode]:
    """Reconstruct the leveled structure tree for one XML bill version.

    Returns the ordered top-level nodes (divisions, or bare titles for a
    no-division bill, plus any empty-path front-matter/preamble leaves). Leaf
    level comes from the XML tag; interior structure from display_path nesting.
    """
    return _build_tree((n.display_path, _leaf_level(n.tag), n) for n in bill.nodes)


def build_pdf_tree(anchors: Iterable[Anchor]) -> list[TreeNode]:
    """Reconstruct the leveled structure tree for one PDF bill version.

    Built from ``breadcrumb_for`` paths over the anchor stream. PDF emits its
    interior levels as typed anchors (title/major/agency/grouping), so those
    nodes carry both a source and children with a precise ``level`` (the anchor
    kind) — unlike XML, where interior levels are synthesized strings. Breadcrumb
    DEPTH is detection-path dependent: a degraded/legacy bill yields shallower
    chains (title→account, no major/agency), so the tree is correspondingly
    shallow. An empty anchor list yields an empty tree.
    """
    anchors = list(anchors)
    return _build_tree((breadcrumb_for(a, anchors), a.kind, a) for a in anchors)
