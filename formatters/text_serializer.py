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
    return serialize_tree_with_offsets(tree)[0]


def serialize_tree_with_offsets(tree: BillTree) -> tuple[str, list[dict]]:
    """Serialize a BillTree to plaintext plus a section jump-list (TOC).

    Heading emission rule: when transitioning from one node to the next, diff the
    display_path tuples. Any new trailing segments are emitted as headings (one
    per line), each separated by a blank line. Body text follows on its own
    line(s), then a trailing blank line before the next node.

    The second return value mirrors the PDF path's ``_section_nav`` output: a
    list of ``{"label", "kind", "start", "descriptor"?}`` in document order, where
    ``start`` is the char offset of the heading line in the returned text. Kinds
    use the same vocabulary as the PDF anchors — ``title`` / ``section`` /
    ``account`` — so the renderer's ``_build_toc`` consumes both identically. The
    offsets are computed from the very same line list the text is joined from, so
    a TOC entry always lands on an exact full-bill row start.
    """
    out: list[str] = []
    # (out-index, label, kind) for each heading-worthy line; offsets resolved
    # after the trailing-blank trim, when the final line list is fixed.
    markers: list[tuple[int, str, str]] = []
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
            if node.section_number:
                markers.append((len(out), node.section_number, "section"))
                out.append(f"{node.section_number.upper()}.  {node.body_text}")
            else:
                out.append(node.body_text)
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
    return text, sections
