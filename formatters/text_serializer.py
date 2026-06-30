"""Serialize a normalized BillTree into readable plaintext.

Used to populate the canonical diff JSON's optional `full_text` field so
renderers can run a Word-style tracked-changes diff over the whole
document, not just per-change fragments.

The format is intentionally simple: emit each new display_path segment as
its own heading line on first appearance, then emit the node's body text.
Sibling nodes under a shared parent path share that parent's heading.
"""

from __future__ import annotations

from bill_tree import BillTree
from structure_tree import TreeNode, build_xml_tree


def serialize_tree(tree: BillTree) -> str:
    """Walk the flat node list and emit hierarchical plaintext.

    Thin wrapper over :func:`serialize_tree_with_offsets` — see it for the
    heading-emission rule. Returns just the text for callers that don't need the
    section jump-list.
    """
    return _serialize(tree)[0]


def serialize_tree_for_tree(
    tree: BillTree,
) -> tuple[str, list[dict], dict[str, tuple[int, int]], dict[tuple[str, ...], int]]:
    """Full _serialize output incl. the per-display_path heading-offset map, used
    to attach full_text_spans to the structure tree's interior nodes (#108)."""
    return _serialize(tree)


def serialize_tree_for_diff(tree: BillTree) -> tuple[str, list[dict], dict[str, tuple[int, int]]]:
    """Serialize plus a ``{element_id: (start, end)}`` body-span index (#51).

    Each span is the char range of a node's readable body within the returned text,
    excluding the ``SEC. NN.  `` run-in prefix and any heading lines. The canonical
    producer uses it to anchor a change's inline highlight structurally (the change
    carries the node's ``element_id``), instead of substring-searching the now-readable
    text. Nodes with no ``element_id`` are omitted.
    """
    text, sections, spans, _heading_offsets = _serialize(tree)
    return text, sections, spans


def build_xml_full_text(
    old_tree: BillTree, new_tree: BillTree
) -> tuple[dict[str, str], dict[str, dict], list[dict], dict[str, list[dict]]]:
    """Build the inputs the XML pipeline feeds to ``xml_diff_to_canonical`` (#51, #108).

    Returns ``(full_text, full_text_spans, sections, tree)`` where ``full_text`` is the
    readable per-side text, ``full_text_spans`` is the per-side ``{element_id:
    (start, end)}`` index for structural change anchoring, ``sections`` is the v2
    TOC jump-list, and ``tree`` is the per-side leveled structure tree (#108) as
    canonical JSON nodes, with each node's ``full_text_span`` into ``full_text``.
    Centralizes the idiom shared by the CLI, examples, and servers.
    """
    v1_text, _v1_sections, v1_spans, v1_ho = serialize_tree_for_tree(old_tree)
    v2_text, v2_sections, v2_spans, v2_ho = serialize_tree_for_tree(new_tree)
    tree = {
        "v1": _xml_tree_payload(old_tree, v1_spans, v1_ho),
        "v2": _xml_tree_payload(new_tree, v2_spans, v2_ho),
    }
    return (
        {"v1": v1_text, "v2": v2_text},
        {"v1": v1_spans, "v2": v2_spans},
        v2_sections,
        tree,
    )


def _xml_tree_payload(
    bill: BillTree,
    body_spans: dict[str, tuple[int, int]],
    heading_offsets: dict[tuple[str, ...], int],
) -> list[dict]:
    """Serialize one version's structure tree to canonical JSON nodes (#108).

    A content node takes its body span (by element_id — the exact slice its text
    and own_amounts occupy); a synthesized interior node takes its heading-line
    offset. A container with neither (the synthesized "Front Matter" group, whose
    label is printed nowhere in the bill) spans its children, so the bill's opening
    stays navigable; a node with none of the three gets a null span.
    """

    def node_json(n: TreeNode) -> dict:
        children = [node_json(c) for c in n.children]
        span = None
        element_id = getattr(n.source, "element_id", "") if n.source is not None else ""
        if element_id and element_id in body_spans:
            start, end = body_spans[element_id]
            span = {"start": start, "end": end}
        elif n.display_path in heading_offsets:
            start = heading_offsets[n.display_path]
            span = {"start": start, "end": start + len(n.label)}
        else:
            child_spans = [c["full_text_span"] for c in children if c["full_text_span"]]
            if child_spans:
                span = {"start": min(s["start"] for s in child_spans), "end": max(s["end"] for s in child_spans)}
        return {
            "label": n.label,
            "level": n.level,
            "own_amounts": list(n.own_amounts),
            "full_text_span": span,
            "children": children,
        }

    return [node_json(r) for r in build_xml_tree(bill)]


def serialize_tree_with_offsets(tree: BillTree) -> tuple[str, list[dict]]:
    """Serialize a BillTree to plaintext plus a section jump-list (TOC).

    Thin wrapper over :func:`_serialize` returning just the text and section
    jump-list; see :func:`serialize_tree_for_diff` for the body-span index.
    """
    text, sections, _spans, _ho = _serialize(tree)
    return text, sections


def _serialize(
    tree: BillTree,
) -> tuple[str, list[dict], dict[str, tuple[int, int]], dict[tuple[str, ...], int]]:
    """Serialize a BillTree to plaintext, a section jump-list, a body-span index,
    and a per-display_path heading-offset map.

    Heading emission rule: when transitioning from one node to the next, diff the
    display_path tuples. Any new trailing segments are emitted as headings (one
    per line), each separated by a blank line. The node's readable ``display_text``
    (falling back to ``body_text``) follows on its own line(s), then a trailing blank
    line before the next node.

    The section jump-list mirrors the PDF path's ``_section_nav`` output: a list of
    ``{"label", "kind", "start", "descriptor"?}`` in document order, where ``start`` is
    the char offset of the heading line. Kinds use the PDF anchor vocabulary —
    ``title`` / ``section`` / ``account`` — so ``_build_toc`` consumes both identically.

    The body-span index maps ``element_id -> (start, end)`` covering each node's body
    (excluding the ``SEC. NN.  `` run-in prefix), for structural change anchoring (#51).
    All offsets are computed from the very same line list the text is joined from.
    """
    out: list[str] = []
    # (out-index, label, kind) for each heading-worthy line; offsets resolved
    # after the trailing-blank trim, when the final line list is fixed.
    markers: list[tuple[int, str, str]] = []
    # (out-index, full display_path prefix) for each heading line — lets the
    # structure tree attach a full_text_span to its synthesized interior nodes,
    # keyed by display_path. First occurrence wins (mirrors the tree's nesting).
    heading_markers: list[tuple[int, tuple[str, ...]]] = []
    # (out-index, element_id, prefix_len, body_len) for each body block.
    body_markers: list[tuple[int, str, int, int]] = []
    prev_path: tuple[str, ...] = ()
    for node in tree.nodes:
        new_path = tuple(node.display_path)
        # For section nodes, the trailing display_path segment is a lowercased
        # copy of section_number ("sec. 101"). Drop it from the heading run so
        # we can emit a bill-style "SEC. 101." run-in heading on the body line.
        heading_path = new_path[:-1] if node.section_number and new_path else new_path
        # Find the longest common prefix between previous and new path.
        common = 0
        while common < len(prev_path) and common < len(heading_path) and prev_path[common] == heading_path[common]:
            common += 1
        # Emit any newly entered path segments as headings. The top-level segment
        # (absolute index 0) is the title/division heading — in XML that's the
        # title's header text ("DEPARTMENT OF DEFENSE"), not a literal "TITLE I" —
        # so the TOC nests its accounts beneath it. Deeper segments are accounts.
        for offset, seg in enumerate(heading_path[common:]):
            if out and out[-1] != "":
                out.append("")
            abs_index = common + offset
            kind = "title" if abs_index == 0 or seg.upper().startswith("TITLE ") else "account"
            markers.append((len(out), seg, kind))
            heading_markers.append((len(out), tuple(heading_path[: abs_index + 1])))
            out.append(seg)
        # Some nodes carry a header_text that isn't already the last path
        # segment (e.g., enacting clause has empty path but a header).
        if not new_path and node.header_text:
            out.append(node.header_text)
        # Body: section nodes get "SEC. NN." prefixed as a run-in heading;
        # everything else just emits body_text on its own.
        if node.body_text:
            if out and out[-1] != "":
                out.append("")
            display = node.display_text or node.body_text
            idx = len(out)
            if node.section_number:
                markers.append((idx, node.section_number, "section"))
                prefix = f"{node.section_number.upper()}.  "
                out.append(f"{prefix}{display}")
                prefix_len = len(prefix)
            else:
                out.append(display)
                prefix_len = 0
            if node.element_id:
                body_markers.append((idx, node.element_id, prefix_len, len(display)))
            out.append("")
        prev_path = heading_path
    # Trim trailing blank lines.
    while out and out[-1] == "":
        out.pop()
    text = "\n".join(out)

    # Resolve out-indices to char offsets via a prefix sum over the final lines.
    line_starts: list[int] = []
    pos = 0
    for line in out:
        line_starts.append(pos)
        pos += len(line) + 1  # +1 for the newline join() inserts
    sections: list[dict] = [
        {"label": label, "kind": kind, "start": line_starts[idx]}
        for idx, label, kind in markers
        if idx < len(out)  # a heading can never be a trimmed trailing blank, but stay safe
    ]
    # Heading offsets: each interior path's heading line start (first occurrence),
    # so the structure tree can locate its synthesized nodes in full_text.
    heading_offsets: dict[tuple[str, ...], int] = {}
    for idx, path in heading_markers:
        if idx < len(out) and path not in heading_offsets:
            heading_offsets[path] = line_starts[idx]
    # Body spans: the readable body sits at line_starts[idx] + prefix_len and runs
    # body_len chars (display may span several lines; len() counts the newlines).
    spans: dict[str, tuple[int, int]] = {}
    for idx, element_id, prefix_len, body_len in body_markers:
        if idx < len(out):
            start = line_starts[idx] + prefix_len
            spans[element_id] = (start, start + body_len)
    # Descriptor: only for a bare "TITLE I"-style enum (PDF carries these as the
    # title text), labelled with the account heading directly below it, mirroring
    # PDF `_title_descriptor`. XML title labels are now "TITLE I—<header>" (#50),
    # which already carry the descriptive header inline — the em-dash distinguishes
    # them from a bare PDF enum, so they get no (duplicate) descriptor.
    for i, entry in enumerate(sections):
        if (
            entry["kind"] == "title"
            and entry["label"].upper().startswith("TITLE ")
            and "—" not in entry["label"]
            and i + 1 < len(sections)
            and sections[i + 1]["kind"] == "account"
        ):
            entry["descriptor"] = sections[i + 1]["label"]
    return text, sections, spans, heading_offsets
