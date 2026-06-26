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


def serialize_tree(tree: BillTree) -> str:
    """Walk the flat node list and emit hierarchical plaintext.

    Thin wrapper over :func:`serialize_tree_with_offsets` — see it for the
    heading-emission rule. Returns just the text for callers that don't need the
    section jump-list.
    """
    return _serialize(tree)[0]


def serialize_tree_for_diff(tree: BillTree) -> tuple[str, list[dict], dict[str, tuple[int, int]]]:
    """Serialize plus a ``{element_id: (start, end)}`` body-span index (#51).

    Each span is the char range of a node's readable body within the returned text,
    excluding the ``SEC. NN.  `` run-in prefix and any heading lines. The canonical
    producer uses it to anchor a change's inline highlight structurally (the change
    carries the node's ``element_id``), instead of substring-searching the now-readable
    text. Nodes with no ``element_id`` are omitted.
    """
    return _serialize(tree)


def build_xml_full_text(old_tree: BillTree, new_tree: BillTree) -> tuple[dict[str, str], dict[str, dict], list[dict]]:
    """Build the inputs the XML pipeline feeds to ``xml_diff_to_canonical`` (#51).

    Returns ``(full_text, full_text_spans, sections)`` where ``full_text`` is the
    readable per-side text, ``full_text_spans`` is the per-side ``{element_id:
    (start, end)}`` index for structural change anchoring, and ``sections`` is the v2
    TOC jump-list. Centralizes the idiom shared by the CLI, examples, and servers.
    """
    v1_text, _v1_sections, v1_spans = serialize_tree_for_diff(old_tree)
    v2_text, v2_sections, v2_spans = serialize_tree_for_diff(new_tree)
    return {"v1": v1_text, "v2": v2_text}, {"v1": v1_spans, "v2": v2_spans}, v2_sections


def serialize_tree_with_offsets(tree: BillTree) -> tuple[str, list[dict]]:
    """Serialize a BillTree to plaintext plus a section jump-list (TOC).

    Thin wrapper over :func:`_serialize` returning just the text and section
    jump-list; see :func:`serialize_tree_for_diff` for the body-span index.
    """
    text, sections, _spans = _serialize(tree)
    return text, sections


def _serialize(tree: BillTree) -> tuple[str, list[dict], dict[str, tuple[int, int]]]:
    """Serialize a BillTree to plaintext, a section jump-list, and a body-span index.

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
    return text, sections, spans
