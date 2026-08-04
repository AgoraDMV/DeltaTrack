"""Compare two bill versions and produce a structured diff.

No shebang since #398: executing a file inside a package puts the package's OWN
directory on `sys.path` rather than its parent, so `python src/deltatrack/diff_bill.py`
dies on `No module named 'deltatrack'`. The `__main__` block below is still live and
supports `python -m deltatrack.diff_bill`; `./diff_bill.py` at the repo root is the
documented invocation and wraps this module.
"""

import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from deltatrack.bill_tree import BillNode, BillTree, amount_text, normalize_bill
from deltatrack.similarity import (
    MOVE_THRESHOLD,
    SIMILARITY_THRESHOLD,
    move_candidates,
    text_similarity,
)
from deltatrack.version_stems import (
    label_from_stem,
    local_versions,
    resolve_version_file,
    version_number_from_stem,
)

# --- Financial amount extraction ---

# A comma-grouped amount must use groups of exactly three digits, so a trailing
# run of digits (e.g. a percentage abutting with no space: "$17,40022%") falls
# outside the match instead of merging into it (#34). The no-comma alternative
# preserves amounts written without thousands separators ("$5000000").
_DOLLAR_RE = re.compile(r"\$\d{1,3}(?:,\d{3})+|\$\d+")
_AMENDMENT_RE = re.compile(r"\((?:increased|reduced|decreased) by\s+\$[\d,]+\)")


def extract_amounts(text: str) -> tuple[int, ...]:
    """Find all dollar amounts in text.

    Returns tuple of integer values in document order. $0 is kept: it is real
    budget data (e.g. a rescinded or zeroed line), and an unchanged $0 produces
    no diff noise (multiset equality), so keeping it only surfaces $0 when it
    actually changes (#60). Strips floor amendment annotations like
    (increased by $X) before scanning.
    """
    text = _AMENDMENT_RE.sub("", text)
    results = []
    for match in _DOLLAR_RE.finditer(text):
        value = int(match.group().replace("$", "").replace(",", ""))
        results.append(value)
    return tuple(results)


def _extract_word_amounts(words: list[str]) -> list[tuple[int, int]]:
    """Find dollar amounts in a word list, returning (word_index, value) pairs.

    Keeps $0 (see extract_amounts, #60). Assumes amendment annotations already stripped.
    """
    results = []
    for i, word in enumerate(words):
        m = _DOLLAR_RE.search(word)
        if m:
            value = int(m.group().replace("$", "").replace(",", ""))
            results.append((i, value))
    return results


def match_amounts(
    old_text: str | None,
    new_text: str | None,
) -> list[tuple[int | None, int | None]]:
    """Pair dollar amounts across old/new text using word-level diff alignment.

    Returns list of (old_value, new_value) pairs where:
    - (old, new): matched pair (same or changed amount in same context)
    - (old, None): removed amount
    - (None, new): added amount

    Uses SequenceMatcher to align old/new words, then traces dollar amounts
    through the diff opcodes to determine pairing.
    """
    old_clean = _AMENDMENT_RE.sub("", old_text) if old_text else ""
    new_clean = _AMENDMENT_RE.sub("", new_text) if new_text else ""
    old_words = old_clean.split()
    new_words = new_clean.split()

    old_amounts = _extract_word_amounts(old_words)
    new_amounts = _extract_word_amounts(new_words)

    if not old_amounts and not new_amounts:
        return []

    # Handle one side empty (added/removed sections)
    if not old_words:
        return [(None, val) for _, val in new_amounts]
    if not new_words:
        return [(val, None) for _, val in old_amounts]

    sm = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)
    pairs: list[tuple[int | None, int | None]] = []

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        old_in_range = [(idx, val) for idx, val in old_amounts if i1 <= idx < i2]
        new_in_range = [(idx, val) for idx, val in new_amounts if j1 <= idx < j2]

        if op == "equal":
            # Equal blocks: amounts should match 1:1
            for (_, ov), (_, nv) in zip(old_in_range, new_in_range):
                pairs.append((ov, nv))
        elif op == "delete":
            for _, ov in old_in_range:
                pairs.append((ov, None))
        elif op == "insert":
            for _, nv in new_in_range:
                pairs.append((None, nv))
        elif op == "replace":
            # Positional pairing is only trustworthy when both sides hold the same
            # number of amounts (a clean value swap). When counts differ, an amount
            # was inserted or removed inside the block and position no longer tracks
            # meaning, so pairing positionally fabricates a plausible-but-wrong delta
            # (e.g. old [$100,$200] vs new [$150,<inserted>,$250] mispairs $200->$250).
            # We have no trustworthy correspondence, so report each amount as an
            # explicit add/remove rather than guess (#60).
            if len(old_in_range) == len(new_in_range):
                for (_, ov), (_, nv) in zip(old_in_range, new_in_range):
                    pairs.append((ov, nv))
            else:
                for _, ov in old_in_range:
                    pairs.append((ov, None))
                for _, nv in new_in_range:
                    pairs.append((None, nv))

    return pairs


@dataclass(frozen=True)
class FinancialChange:
    """Financial analysis of a single NodeDiff."""

    old_amounts: tuple[int, ...]
    new_amounts: tuple[int, ...]
    amounts_changed: bool
    paired_amounts: tuple[tuple[int | None, int | None], ...]
    has_amendment_annotations: bool = False


def compute_financial_change(
    old_text: str | None,
    new_text: str | None,
) -> FinancialChange | None:
    """Compare dollar amounts between old and new text.

    Returns None if no amounts on either side (non-financial section).
    """
    has_annotations = bool(
        (old_text and _AMENDMENT_RE.search(old_text)) or (new_text and _AMENDMENT_RE.search(new_text))
    )

    old_amounts = extract_amounts(old_text) if old_text else ()
    new_amounts = extract_amounts(new_text) if new_text else ()

    if not old_amounts and not new_amounts:
        return None

    paired = match_amounts(old_text, new_text)
    return FinancialChange(
        old_amounts=old_amounts,
        new_amounts=new_amounts,
        amounts_changed=Counter(old_amounts) != Counter(new_amounts),
        paired_amounts=tuple(paired),
        has_amendment_annotations=has_annotations,
    )


def financial_change_to_dict(fc: FinancialChange) -> dict:
    """Serialize a FinancialChange for JSON output."""
    return {
        "old_amounts": list(fc.old_amounts),
        "new_amounts": list(fc.new_amounts),
        "amounts_changed": fc.amounts_changed,
        "paired_amounts": [list(pair) for pair in fc.paired_amounts],
        "has_amendment_annotations": fc.has_amendment_annotations,
    }


def _similarity_pair(
    old_nodes: list[BillNode],
    new_nodes: list[BillNode],
) -> list[tuple[BillNode | None, BillNode | None]]:
    """Greedy best-match pairing by text similarity within a group."""
    if not old_nodes and not new_nodes:
        return []
    if not old_nodes:
        return [(None, n) for n in new_nodes]
    if not new_nodes:
        return [(o, None) for o in old_nodes]
    if len(old_nodes) == 1 and len(new_nodes) == 1:
        return [(old_nodes[0], new_nodes[0])]

    # Compute all pairwise similarities
    candidates: list[tuple[float, int, int]] = []
    for oi, o in enumerate(old_nodes):
        o_norm = _normalize_text(o.body_text)
        for ni, n in enumerate(new_nodes):
            n_norm = _normalize_text(n.body_text)
            sim = text_similarity(o_norm, n_norm)
            candidates.append((sim, oi, ni))

    # Greedy: highest similarity first
    candidates.sort(reverse=True)
    claimed_old: set[int] = set()
    claimed_new: set[int] = set()
    pairs: list[tuple[BillNode | None, BillNode | None]] = []

    for _sim, oi, ni in candidates:
        if oi in claimed_old or ni in claimed_new:
            continue
        claimed_old.add(oi)
        claimed_new.add(ni)
        pairs.append((old_nodes[oi], new_nodes[ni]))

    # Leftovers
    for oi, o in enumerate(old_nodes):
        if oi not in claimed_old:
            pairs.append((o, None))
    for ni, n in enumerate(new_nodes):
        if ni not in claimed_new:
            pairs.append((None, n))

    return pairs


def _match_collision_group(
    old_nodes: list[BillNode],
    new_nodes: list[BillNode],
) -> list[tuple[BillNode | None, BillNode | None]]:
    """Resolve a collision group (multiple nodes sharing one match_path).

    Uses each node's division key to sub-group, then text similarity as fallback.

    The key is carried on the node (#468). It used to be recovered from the division's
    display label by splitting on ``":"``, which tied matching to a presentation choice:
    the GPO form #66 asks for has no colon, so every division collapsed into one bucket
    and nodes silently paired across divisions.
    """
    # Step 1: Sub-group by division
    old_by_div: dict[str, list[BillNode]] = defaultdict(list)
    new_by_div: dict[str, list[BillNode]] = defaultdict(list)
    for node in old_nodes:
        old_by_div[node.division_key].append(node)
    for node in new_nodes:
        new_by_div[node.division_key].append(node)

    pairs: list[tuple[BillNode | None, BillNode | None]] = []
    unmatched_old: list[BillNode] = []
    unmatched_new: list[BillNode] = []

    all_divs = dict.fromkeys(list(old_by_div.keys()) + list(new_by_div.keys()))

    # Step 2: Pair within each division sub-group
    for div_title in all_divs:
        div_old = old_by_div.get(div_title, [])
        div_new = new_by_div.get(div_title, [])

        if not div_old:
            unmatched_new.extend(div_new)
        elif not div_new:
            unmatched_old.extend(div_old)
        else:
            sub_pairs = _similarity_pair(div_old, div_new)
            for o, n in sub_pairs:
                if o is None:
                    unmatched_new.append(n)
                elif n is None:
                    unmatched_old.append(o)
                else:
                    pairs.append((o, n))

    # Step 3-4: Cross-division similarity fallback for leftovers
    if unmatched_old and unmatched_new:
        cross_pairs = _similarity_pair(unmatched_old, unmatched_new)
        leftover_old = []
        leftover_new = []
        for o, n in cross_pairs:
            if o is None:
                leftover_new.append(n)
            elif n is None:
                leftover_old.append(o)
            else:
                pairs.append((o, n))
        unmatched_old = leftover_old
        unmatched_new = leftover_new

    # Step 5: True leftovers
    for o in unmatched_old:
        pairs.append((o, None))
    for n in unmatched_new:
        pairs.append((None, n))

    return pairs


def match_nodes(
    old: BillTree,
    new: BillTree,
) -> list[tuple[BillNode | None, BillNode | None]]:
    """Match nodes across two bill versions by match_path.

    Returns list of (old_node, new_node) tuples where one side may be None:
    - (old, new): matched pair
    - (old, None): removed (only in old)
    - (None, new): added (only in new)

    For unique match_paths, pairs directly (fast path). For collision groups
    (multiple nodes sharing one match_path), uses division-aware sub-grouping
    with text similarity fallback.
    """
    # Group nodes by match_path
    old_groups: dict[tuple[str, ...], list[BillNode]] = defaultdict(list)
    new_groups: dict[tuple[str, ...], list[BillNode]] = defaultdict(list)

    for node in old.nodes:
        old_groups[node.match_path].append(node)
    for node in new.nodes:
        new_groups[node.match_path].append(node)

    all_paths = dict.fromkeys(list(old_groups.keys()) + list(new_groups.keys()))

    pairs: list[tuple[BillNode | None, BillNode | None]] = []

    for path in all_paths:
        old_nodes = old_groups.get(path, [])
        new_nodes = new_groups.get(path, [])

        if len(old_nodes) <= 1 and len(new_nodes) <= 1:
            # Fast path: no collision, preserve current behavior
            pairs.append(
                (
                    old_nodes[0] if old_nodes else None,
                    new_nodes[0] if new_nodes else None,
                )
            )
        else:
            pairs.extend(_match_collision_group(old_nodes, new_nodes))

    return pairs


def diff_text(old_text: str, new_text: str) -> list[str]:
    """Produce unified diff lines between two text blocks.

    Returns empty list if texts are identical.
    """
    if old_text == new_text:
        return []

    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="old",
            tofile="new",
            lineterm="",
        )
    )
    # Strip trailing whitespace from each line
    return [line.rstrip() for line in diff_lines]


@dataclass(frozen=True)
class NodeDiff:
    """Diff result for a single node."""

    display_path_old: tuple[str, ...] | None
    display_path_new: tuple[str, ...] | None
    match_path: tuple[str, ...]
    change_type: str  # "added" | "removed" | "modified" | "unchanged"
    old_text: str | None
    new_text: str | None
    text_diff: list[str] | None
    section_number: str
    element_id_old: str
    element_id_new: str
    # --- Amount-extraction source (#365, #422) ---------------------------------
    # The text each money view extracts dollar amounts from. Both views must read the
    # same rendering, or the amount-change table and the leveled money tree can
    # disagree about whether a section's money moved. Pinned by
    # TestAmountSourceCorpusRegression in tests/test_financial_diff.py.
    #
    # A no-op on the current corpus, and kept deliberately: display_text is the more
    # faithful rendering of a section (body_text stays collapsed for matching), and
    # removing these fields lets the two views drift apart again with nothing naming
    # the rule. old_text/new_text stay body_text — they feed matching, text_diff and
    # the JSON payload, which this does not touch. None means "no separate source
    # recorded" (a hand-built NodeDiff); the amount_source_* properties then fall back
    # to old_text/new_text.
    #
    # Why not remove them: see above — the no-op is the pinned agreement, not dead code.
    # History: #365 the two views read different renderings, because body_text was
    # truncated by a "simple lead-in" fast path in bill_tree._extract_section_text;
    # #422 removed that fast path.
    old_amount_text: str | None = None
    new_amount_text: str | None = None

    @property
    def amount_source_old(self) -> str | None:
        """Old-side text that amount extraction should read (#365)."""
        return self.old_amount_text if self.old_amount_text is not None else self.old_text

    @property
    def amount_source_new(self) -> str | None:
        """New-side text that amount extraction should read (#365)."""
        return self.new_amount_text if self.new_amount_text is not None else self.new_text


@dataclass(frozen=True)
class BillDiff:
    """Complete diff between two bill versions."""

    old_version: str
    new_version: str
    congress: int
    bill_type: str
    bill_number: int
    summary: dict
    changes: list[NodeDiff]


def _normalize_text(text: str) -> str:
    """Normalize whitespace for comparison: collapse runs, strip."""
    return " ".join(text.split())


def reconcile_moves(
    changes: list[NodeDiff],
    threshold: float = MOVE_THRESHOLD,
) -> list[NodeDiff]:
    """Re-link removed+added pairs that are actually moved sections.

    Computes pairwise text similarity between removed and added entries.
    Pairs above threshold are greedily matched (highest similarity first)
    and converted to change_type="moved".
    """
    removed = [(i, c) for i, c in enumerate(changes) if c.change_type == "removed"]
    added = [(i, c) for i, c in enumerate(changes) if c.change_type == "added"]

    if not removed or not added:
        return changes

    # Pairwise similarities (gated + matcher-reused; identical result to the
    # naive removed×added double loop, since callers sort by the full tuple).
    candidates = move_candidates(
        [_normalize_text(rc.old_text or "") for _, rc in removed],
        [_normalize_text(ac.new_text or "") for _, ac in added],
        threshold,
    )

    if not candidates:
        return changes

    # Greedy: highest similarity first
    candidates.sort(reverse=True)
    claimed_removed: set[int] = set()
    claimed_added: set[int] = set()
    moved_indices: set[int] = set()  # original indices to remove
    moved_entries: list[NodeDiff] = []

    for sim, ri, ai in candidates:
        if ri in claimed_removed or ai in claimed_added:
            continue
        claimed_removed.add(ri)
        claimed_added.add(ai)

        orig_ri, rc = removed[ri]
        orig_ai, ac = added[ai]
        moved_indices.add(orig_ri)
        moved_indices.add(orig_ai)

        # Compute text_diff if texts differ
        old_norm = _normalize_text(rc.old_text or "")
        new_norm = _normalize_text(ac.new_text or "")
        text_changes = diff_text(old_norm, new_norm) if old_norm != new_norm else None

        moved_entries.append(
            NodeDiff(
                display_path_old=rc.display_path_old,
                display_path_new=ac.display_path_new,
                match_path=rc.match_path,
                change_type="moved",
                old_text=rc.old_text,
                new_text=ac.new_text,
                text_diff=text_changes,
                section_number=ac.section_number or rc.section_number,
                element_id_old=rc.element_id_old,
                element_id_new=ac.element_id_new,
                # Carry each side's amount source across the move, from the same entry
                # the text comes from, so a moved section's amounts stay readable (#365).
                old_amount_text=rc.old_amount_text,
                new_amount_text=ac.new_amount_text,
            )
        )

    # Rebuild: keep non-moved entries in original order, append moved at end
    result = [c for i, c in enumerate(changes) if i not in moved_indices]
    result.extend(moved_entries)
    return result


def _count_changes(changes: list[NodeDiff]) -> dict:
    """Compute summary counts from the final changes list."""
    counts = Counter(c.change_type for c in changes)
    return {t: counts.get(t, 0) for t in ("added", "removed", "modified", "unchanged", "moved")}


def diff_bills(old: BillTree, new: BillTree) -> BillDiff:
    """Compare two bill versions and produce a structured diff."""
    pairs = match_nodes(old, new)
    changes: list[NodeDiff] = []

    for old_node, new_node in pairs:
        if old_node is None and new_node is not None:
            changes.append(
                NodeDiff(
                    display_path_old=None,
                    display_path_new=new_node.display_path,
                    match_path=new_node.match_path,
                    change_type="added",
                    old_text=None,
                    new_text=new_node.body_text,
                    text_diff=None,
                    section_number=new_node.section_number,
                    element_id_old="",
                    element_id_new=new_node.element_id,
                    new_amount_text=amount_text(new_node),
                )
            )

        elif old_node is not None and new_node is None:
            changes.append(
                NodeDiff(
                    display_path_old=old_node.display_path,
                    display_path_new=None,
                    match_path=old_node.match_path,
                    change_type="removed",
                    old_text=old_node.body_text,
                    new_text=None,
                    text_diff=None,
                    section_number=old_node.section_number,
                    element_id_old=old_node.element_id,
                    element_id_new="",
                    old_amount_text=amount_text(old_node),
                )
            )

        elif old_node is not None and new_node is not None:
            old_normalized = _normalize_text(old_node.body_text)
            new_normalized = _normalize_text(new_node.body_text)
            text_changes = diff_text(old_normalized, new_normalized)
            if not text_changes:
                changes.append(
                    NodeDiff(
                        display_path_old=old_node.display_path,
                        display_path_new=new_node.display_path,
                        match_path=old_node.match_path,
                        change_type="unchanged",
                        old_text=old_node.body_text,
                        new_text=new_node.body_text,
                        text_diff=None,
                        section_number=new_node.section_number or old_node.section_number,
                        element_id_old=old_node.element_id,
                        element_id_new=new_node.element_id,
                        old_amount_text=amount_text(old_node),
                        new_amount_text=amount_text(new_node),
                    )
                )
            elif text_similarity(old_normalized, new_normalized) < SIMILARITY_THRESHOLD:
                # Texts too different: false match (e.g., reused section number).
                changes.append(
                    NodeDiff(
                        display_path_old=old_node.display_path,
                        display_path_new=None,
                        match_path=old_node.match_path,
                        change_type="removed",
                        old_text=old_node.body_text,
                        new_text=None,
                        text_diff=None,
                        section_number=old_node.section_number,
                        element_id_old=old_node.element_id,
                        element_id_new="",
                        old_amount_text=amount_text(old_node),
                    )
                )
                changes.append(
                    NodeDiff(
                        display_path_old=None,
                        display_path_new=new_node.display_path,
                        match_path=new_node.match_path,
                        change_type="added",
                        old_text=None,
                        new_text=new_node.body_text,
                        text_diff=None,
                        section_number=new_node.section_number,
                        element_id_old="",
                        element_id_new=new_node.element_id,
                        new_amount_text=amount_text(new_node),
                    )
                )
            else:
                changes.append(
                    NodeDiff(
                        display_path_old=old_node.display_path,
                        display_path_new=new_node.display_path,
                        match_path=old_node.match_path,
                        change_type="modified",
                        old_text=old_node.body_text,
                        new_text=new_node.body_text,
                        text_diff=text_changes,
                        section_number=new_node.section_number or old_node.section_number,
                        element_id_old=old_node.element_id,
                        element_id_new=new_node.element_id,
                        old_amount_text=amount_text(old_node),
                        new_amount_text=amount_text(new_node),
                    )
                )

    changes = reconcile_moves(changes)

    return BillDiff(
        old_version=old.version,
        new_version=new.version,
        congress=old.congress,
        bill_type=old.bill_type,
        bill_number=old.bill_number,
        summary=_count_changes(changes),
        changes=changes,
    )


def bill_diff_to_dict(diff: BillDiff, *, financial: bool = False) -> dict:
    """Serialize a BillDiff to a JSON-compatible dict."""
    changes_list = []
    financial_change_count = 0

    for c in diff.changes:
        entry = {
            "display_path_old": list(c.display_path_old) if c.display_path_old else None,
            "display_path_new": list(c.display_path_new) if c.display_path_new else None,
            "match_path": list(c.match_path),
            "change_type": c.change_type,
            "old_text": c.old_text,
            "new_text": c.new_text,
            "text_diff": c.text_diff,
            "section_number": c.section_number,
            "element_id_old": c.element_id_old,
            "element_id_new": c.element_id_new,
        }
        if financial:
            # Amounts come from the display rendering, not body_text (#365).
            fc = compute_financial_change(c.amount_source_old, c.amount_source_new)
            if fc is not None:
                entry["financial"] = financial_change_to_dict(fc)
                if fc.amounts_changed:
                    financial_change_count += 1
        changes_list.append(entry)

    result = {
        "old_version": diff.old_version,
        "new_version": diff.new_version,
        "congress": diff.congress,
        "bill_type": diff.bill_type,
        "bill_number": diff.bill_number,
        "summary": diff.summary,
        "changes": changes_list,
    }
    if financial:
        result["financial_summary"] = {
            "sections_with_financial_changes": financial_change_count,
        }
    return result


# --- CLI ---


def filter_diff(
    diff: BillDiff,
    *,
    include_unchanged: bool = False,
    filter_text: str | None = None,
    financial_only: bool = False,
) -> BillDiff:
    """Apply filters to a BillDiff, returning a new BillDiff with filtered changes."""
    changes = list(diff.changes)

    if not include_unchanged:
        changes = [c for c in changes if c.change_type != "unchanged"]

    if filter_text:
        filter_lower = filter_text.lower()
        changes = [c for c in changes if filter_lower in " ".join(c.match_path)]

    if financial_only:
        changes = [
            c
            for c in changes
            if (fc := compute_financial_change(c.amount_source_old, c.amount_source_new)) is not None
            and fc.amounts_changed
        ]

    return BillDiff(
        old_version=diff.old_version,
        new_version=diff.new_version,
        congress=diff.congress,
        bill_type=diff.bill_type,
        bill_number=diff.bill_number,
        summary=_count_changes(changes),
        changes=changes,
    )


_COMPARE_USAGE = (
    "compare takes two file paths (compare <old.xml> <new.xml>), a bill slug with two "
    "version ordinals (compare <slug> <n_old> <n_new>), or a bare slug to list that "
    "bill's local versions"
)


def _format_version_listing(bills_dir: Path, slug: str, versions: list[tuple[int, str]]) -> str:
    """The bill's local versions, numbered, as both an answer and an error message.

    A bare slug asks which versions exist; a bad ordinal asks the same question without
    knowing it. Both get this text, so a version's meaning is one command away rather
    than one directory listing away (#152) — the ordinals are per-bill (ADR 0013), so
    "version 3" means nothing until you have seen this list.

    Takes the versions rather than reading them, so a caller that has to branch on
    whether there are any does not look at the directory twice.
    """
    if not versions:
        return (
            f"No local versions for {slug} in {bills_dir / slug}. "
            "Download them with: ./tools/fetch_bills.py download <congress> <type> <number>"
        )
    lines = [f"{slug} has {len(versions)} local version{'' if len(versions) == 1 else 's'}:"]
    lines += [f"  {number}  {label}" for number, label in versions]
    lines.append(f"Pick two: compare {slug} <old> <new>")
    return "\n".join(lines)


def _resolve_version_arg(bills_dir: Path, slug: str, ordinal: str) -> Path:
    """One ``<slug> <n>`` pair to the file it addresses, or exit with the version list.

    A non-numeric ordinal and an out-of-range one are the same mistake with the same
    remedy, so they get the same answer rather than separate diagnostics.

    ``isdecimal`` rather than ``isdigit``: the latter also accepts superscripts and other
    numeric-looking characters that ``int()`` then refuses, turning a typo into a
    ValueError traceback instead of this listing.
    """
    resolved = resolve_version_file(bills_dir, slug, int(ordinal)) if ordinal.isdecimal() else None
    if resolved is None:
        listing = _format_version_listing(bills_dir, slug, local_versions(bills_dir, slug))
        raise SystemExit(f"No version {ordinal} for {slug}.\n{listing}")
    return resolved


def _compare_targets(args: argparse.Namespace) -> tuple[Path, Path]:
    """The two XML files ``compare`` should diff, from its positional arguments.

    Dispatch is on the positional COUNT, never on the shape of a value: two paths are
    the legacy invocation and must stay unreachable from any slug regex or ``.xml``
    sniffing, so that adding the version-addressable form cannot re-read an existing
    command as something else (#152). The one shape check below (a lone positional that
    is an existing file or directory) only picks the ERROR WORDING; the count still
    decides the outcome, so it cannot re-read a working command. That holds only because
    the check runs AFTER the version listing has been tried and come back empty -- ahead
    of it, the same check chooses between success and failure, which is the bug #426's
    review caught.

    A bare slug is a question rather than a failure, so it answers on stdout and exits
    0; every other unresolvable case is an error whose message is the same listing.
    """
    targets = args.targets
    if len(targets) == 2:
        return Path(targets[0]), Path(targets[1])
    if len(targets) == 3:
        slug, n_old, n_new = targets
        return (
            _resolve_version_arg(args.bills_dir, slug, n_old),
            _resolve_version_arg(args.bills_dir, slug, n_new),
        )
    if len(targets) == 1:
        target = targets[0]
        # The listing is tried FIRST so that the shape check below only ever picks
        # between two failures. Checking the shape first let it pick between success and
        # failure instead: `cd bills && compare --bills-dir . 118-hr-4366` names both a
        # resolvable slug and an existing directory, and the check turned that working
        # command into "the second path is missing" (#426 review).
        versions = local_versions(args.bills_dir, target)
        if versions:
            print(_format_version_listing(args.bills_dir, target, versions))
            raise SystemExit(0)
        if Path(target).is_file() or Path(target).is_dir():
            # One real path, no versions under it, and nothing else: `compare "$OLD"
            # "$NEW"` with $NEW unset, or a lone directory from shell completion. The
            # answer is the missing second path, not a version listing for a "slug"
            # that is plainly a path -- the listing doubled it ("in bills/bills/...")
            # and advised downloading a bill the user already has on disk.
            raise SystemExit(f"compare takes two file paths; the second path is missing (got only {target}).")
        # An empty listing is a failure, not an answer. `compare "$OLD" "$NEW"` with
        # an unset variable collapses to one argument, which the two-positional
        # parser rejected outright — a wrapper reading the exit status has to keep
        # seeing that, rather than a clean exit and a message about a bill nobody
        # asked for.
        raise SystemExit(_format_version_listing(args.bills_dir, target, versions))
    # argparse rejected these arities with exit 2 (a usage error); a wrapper keying on
    # the exit status has to keep seeing 2, not the 1 a bare SystemExit(message) gives.
    print(f"{_COMPARE_USAGE} — got {len(targets)}.", file=sys.stderr)
    raise SystemExit(2)


def cmd_compare(args: argparse.Namespace) -> None:
    old_path, new_path = _compare_targets(args)
    old_tree = normalize_bill(old_path)
    new_tree = normalize_bill(new_path)
    fmt = getattr(args, "format", "json")

    if fmt == "html":
        # Imported here, not at module scope: compare.xml imports this module.
        # It owns the whole XML → HTML chain (#42), so the CLI, the web app, and
        # render_examples.py cannot drift into rendering the same pair differently.
        from deltatrack.compare.xml import compare_xml_trees_html

        old_stem, new_stem = old_path.stem, new_path.stem
        output = compare_xml_trees_html(
            old_tree,
            new_tree,
            start_label=label_from_stem(old_stem),
            end_label=label_from_stem(new_stem),
            old_version_number=version_number_from_stem(old_stem),
            new_version_number=version_number_from_stem(new_stem),
            include_unchanged=args.include_unchanged,
            filter_text=args.filter,
            financial_only=args.financial,
        )
    else:
        result = filter_diff(
            diff_bills(old_tree, new_tree),
            include_unchanged=args.include_unchanged,
            filter_text=args.filter,
            financial_only=args.financial,
        )
        diff_dict = bill_diff_to_dict(result, financial=args.financial)
        # Extract version numbers from filenames (e.g., "1_reported-in-house.xml" -> 1)
        for key, path in (("old_version_number", old_path), ("new_version_number", new_path)):
            num = version_number_from_stem(path.stem)
            if num is not None:
                diff_dict[key] = num
        output = json.dumps(diff_dict, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
    else:
        print(output)


class _IntermixedSubParser(argparse.ArgumentParser):
    """A subparser whose optionals may sit anywhere among its positionals.

    argparse matches positionals greedily within each run *between* optionals, so a
    variadic positional swallows the whole first run: `compare old.xml --financial
    new.xml` would fail with "unrecognized arguments: new.xml" even though the
    two-required-positional parser this replaced accepted it. Every ordering that puts a
    flag *between* the two paths would have regressed, silently, since flags-first and
    flags-last still work.

    `parse_intermixed_args` is argparse's own answer to that, but it refuses a parser
    holding subparsers, so it cannot be switched on for the top-level parser -- only
    here, where `add_subparsers` hands control to the subcommand. It delegates back into
    `parse_known_args` with the positionals suppressed; the guard lets that inner call
    through, and is inert if a future argparse stops re-entering.

    The re-entry is NOT hypothetical: on CPython 3.12.0 through 3.12.7,
    `parse_known_intermixed_args` calls the public `self.parse_known_args`, so without
    the guard this override recurses into itself until RecursionError -- every `compare`
    invocation fails, legacy two-path form included. CPython 3.12.8 refactored the
    delegation to the private `_parse_known_args2`, so the guard passes through unused
    there. Verified with `inspect.getsource` and by running `build_parser()` on CPython
    3.12.0, 3.12.4, 3.12.7 (re-enter via the public method), 3.12.8, 3.12.12 and
    3.13.14 (call `_parse_known_args2`). `requires-python` is ">=3.12" and Ubuntu
    24.04 ships 3.12.3, so the re-entering band is supported and the guard stays.
    tests/test_diff_bill.py::TestIntermixedSubParserGuard simulates the re-entering
    shape by monkeypatching, so the guard is pinned on every interpreter -- not only
    on the CI floor leg that happens to run an interpreter from that band.

    `add_subparsers(parser_class=...)` binds EVERY subparser of this parser, not only
    `compare`: a future subcommand with a `nargs=REMAINDER` positional raises
    `TypeError: parse_intermixed_args: positional arg with nargs=...` at parse time.
    """

    def parse_known_args(self, args=None, namespace=None):
        if getattr(self, "_intermixing", False):
            return super().parse_known_args(args, namespace)
        self._intermixing = True
        try:
            return self.parse_known_intermixed_args(args, namespace)
        finally:
            self._intermixing = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two bill XML versions and produce a structured diff.",
    )
    subparsers = parser.add_subparsers(dest="command", parser_class=_IntermixedSubParser)

    compare = subparsers.add_parser("compare", help="Compare two bill versions")
    # One variadic positional, dispatched on count in `_compare_targets`. Two separate
    # required positionals cannot express the <slug> <n_old> <n_new> and bare-<slug>
    # forms, and a pair of optional ones would make the arity implicit (#152).
    compare.add_argument(
        "targets",
        nargs="*",
        metavar="TARGET",
        help=(
            "Either two bill XML paths (<old.xml> <new.xml>), or a bill slug and two "
            "version ordinals (<slug> <n_old> <n_new>) resolved under --bills-dir. "
            "A bare <slug> lists that bill's local versions and exits."
        ),
    )
    compare.add_argument(
        "--bills-dir",
        type=Path,
        default=Path("bills"),
        help="Root holding the per-bill download folders, for the <slug> forms (default: %(default)s)",
    )
    compare.add_argument("-o", "--output", help="Output JSON file (default: stdout)")
    compare.add_argument(
        "--include-unchanged",
        action="store_true",
        help="Include unchanged nodes in output",
    )
    compare.add_argument(
        "--filter",
        help="Only include nodes whose match_path contains this substring",
    )
    compare.add_argument(
        "--financial",
        action="store_true",
        help="Only show sections with financial changes; add amount details to output",
    )
    compare.add_argument(
        "--format",
        choices=["json", "html"],
        default="html",
        help="Output format (default: html)",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "compare":
        cmd_compare(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
