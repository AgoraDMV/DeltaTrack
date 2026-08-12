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
from deltatrack.matching import (
    NEW,
    OLD,
    CandidateSet,
    Correspondence,
    CorrespondenceEvidence,
    CorrespondenceSet,
    ObservationRef,
    RetrieverInvocation,
)
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
    # Step 1: Sub-group by division.
    #
    # Deliberately NOT also by body_index (#434), though nodes now carry one. A document
    # with two top-level bodies makes every section collide with its counterpart in the
    # other text, so partitioning on the body looks like the matching fix. It is not:
    # body_index is a node's POSITION IN ITS OWN DOCUMENT, and the same position does not
    # mean the same text across versions.
    #
    # A reported bill holds the base text at body[0] and the committee substitute at
    # body[1]. When the substitute is adopted, the NEXT version is a single body holding
    # that substitute -- at index 0, because it is now the only body. Partitioning on the
    # index pairs old body[0] (the base, superseded) with it and reports old body[1] (the
    # text that actually survived) as removed. 114-hr-2029 is exactly this: v5 scores
    # 0.809 similarity to v4's body[1] and 0.532 to body[0], and the partition inverted
    # that pairing on a committed corpus pair.
    #
    # Similarity already resolves both directions without the constraint, because it
    # compares text rather than position: going one body to two, the unchanged base text
    # wins its pairing on being identical, and the substitute is left over as added. So
    # the constraint was not earning the direction it was added for, while breaking the
    # other one. division_key is safe here in a way body_index is not -- a division's key
    # is its header text, which is a name that travels with the content across versions.
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
    for group_key in all_divs:
        div_old = old_by_div.get(group_key, [])
        div_new = new_by_div.get(group_key, [])

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


#: The assignment rounds this pipeline runs, in order. Round 1 is ``match_nodes`` followed by
#: :func:`apply_similarity_assignment_rule`; its retrieval and its other assignment acts (the
#: unique-path direct selection, ``_similarity_pair``'s greedy claim) are still fused inside
#: ``match_nodes``. Round 2 is the move pass below. These are provenance carried on a
#: :class:`SettledCorrespondence` so classification can reproduce the legacy record order and
#: label a move — not a ranking, and not a quality signal.
PATH_ROUND = 1
MOVE_ROUND = 2

#: Word-level overlap of two normalized bodies. Carried by BOTH rounds' correspondence evidence,
#: because it is one quantity by one measure: ``text_similarity`` is
#: ``SequenceMatcher(None, a.split(), b.split()).ratio()``, and ``move_candidates`` documents that
#: its tuples are identical to computing ``text_similarity`` for every pair. One name for one
#: signal; two names would invite a reader to think the scales differ.
#:
#: In round 2 it is a *promoted retrieval score*: a retrieval score is not evidence until it is
#: named as a signal (ADR 0020), which :func:`move_correspondence_evidence` is the sole place to
#: do, and assignment reads the signal and never ``Proposal.score``. In round 1 there is no
#: retrieval score to promote -- the ratio is computed for the express purpose of deciding the
#: pairing -- so it is natively evidence.
WORD_OVERLAP = "word_overlap"

#: Whether the two normalized bodies have an empty word-level diff. A description of the texts,
#: not a verdict on them: it reports what ``diff_text`` produced, and
#: :func:`_similarity_rule_keeps` is what reads it as grounds to keep a pairing. ADR 0020 uses the
#: same name for the same quantity where it carves out what classification may legitimately ask.
BODY_UNCHANGED = "body_unchanged"


@dataclass(frozen=True)
class Observation:
    """One parsed node together with its run-local ADR 0019 address.

    The address is source-agnostic and lives in ``deltatrack.matching``; binding an address to
    an XML ``BillNode`` is specific to this pipeline and so lives here. That split is what lets
    ``matching`` stay free of engine imports, which is how the contracts survive an unsettled
    PDF observation representation.
    """

    ref: ObservationRef
    node: BillNode


class ObservationRegistry:
    """The complete parser-emitted sequence for each side, and the address of every node.

    ADR 0019's ``ordinal`` indexes the **complete** emitted sequence, so this is built straight
    from ``enumerate(tree.nodes)`` and is the only authority for turning an
    :class:`~deltatrack.matching.ObservationRef` back into a node. Classification resolves every
    settled correspondence through it rather than through a filtered-list position or an
    ``element_id`` — both of which are addresses that look valid while pointing at the wrong node,
    which is the hazard ADR 0019 names.

    ``match_nodes`` returns node objects rather than ordinals, so recovering an address means
    locating the node in the complete sequence. That is done by live object identity, which is
    valid only because both trees hold every node alive for the whole comparison (#590 established
    this, and it is a run-local mechanism, never persistent identity). Totality and injectivity are
    asserted rather than assumed: a repeated node object would collapse two addresses onto one, and
    a foreign node would yield none — both silently.
    """

    def __init__(self, old_nodes: list[BillNode], new_nodes: list[BillNode]) -> None:
        self._nodes: dict[str, tuple[BillNode, ...]] = {OLD: tuple(old_nodes), NEW: tuple(new_nodes)}
        self._ordinals: dict[str, dict[int, int]] = {}
        for side, nodes in self._nodes.items():
            ordinals: dict[int, int] = {}
            for ordinal, node in enumerate(nodes):
                if id(node) in ordinals:
                    raise ValueError(
                        f"the {side} parse lists one node object at ordinals {ordinals[id(node)]} and "
                        f"{ordinal}; two observations would collapse onto one address"
                    )
                ordinals[id(node)] = ordinal
            self._ordinals[side] = ordinals

    def ref(self, side: str, node: BillNode) -> ObservationRef:
        """The address of ``node``, refusing one the parse never emitted."""
        ordinal = self._ordinals[side].get(id(node))
        if ordinal is None:
            raise ValueError(
                f"a {side}-side pairing names a node absent from that side's complete parser "
                f"sequence ({node.element_id!r}); its address cannot be recovered"
            )
        return ObservationRef(side, ordinal)

    def node(self, ref: ObservationRef) -> BillNode:
        """The node ``ref`` addresses."""
        return self._nodes[ref.side][ref.ordinal]

    def observation(self, side: str, node: BillNode) -> Observation:
        """``node`` paired with its address."""
        return Observation(self.ref(side, node), node)


@dataclass(frozen=True)
class UnmatchedPopulation:
    """Round 2's retrieval population: each side's unmatched observations, in stream order.

    **The index into ``old``/``new`` is the legacy ``(ri, ai)``.** That is the whole reason this
    is an ordered tuple rather than a set or a mapping keyed by address. Production sorts round-2
    candidates on ``(similarity, ri, ai)``, where those are positions in the filtered
    removal/addition lists, and #590 measured that substituting ADR 0019 ordinals for them changes
    the selected correspondence on 3 of the 27 committed corpus pairs — a symmetric difference of
    20 links.

    So the two solve different problems and are kept apart structurally rather than by comment:
    ``ObservationRef`` is the architectural address and is a field on :class:`Observation`, while
    ``(ri, ai)`` is legacy assignment ordering policy and exists only as a position in these
    tuples, recomputed where needed and stored nowhere.

    Text-free observations are present and occupy positions even though they can never produce a
    candidate (#357). Dropping them would renumber every position after the first one.
    """

    old: tuple[Observation, ...]
    new: tuple[Observation, ...]


@dataclass(frozen=True)
class SettledCorrespondence:
    """One settled correspondence and the assignment round that selected it.

    The round is carried rather than re-derived because ``moved`` is currently *defined* by
    provenance. A round-1 pairing and a round-2 move are both 1:1 correspondences of one old and
    one new observation, and nothing about the two observations distinguishes them. The tempting
    derivation is ``old.match_path != new.match_path``, which agrees across the whole committed
    corpus — 0 of 496 selected moves link observations sharing a match path, while all 14,707
    surviving round-1 pairings do. It is still not the rule production applies, and half that
    agreement is structural rather than measured (round-1 pairing only ever happens inside one
    match-path group), so a Phase-1 extraction adopting it would be changing policy while claiming
    to move it. Whether classification should later derive it is a Phase-2 question that now has
    the measurement.
    """

    correspondence: Correspondence
    round: int


def observation_registry(old: BillTree, new: BillTree) -> ObservationRegistry:
    """The complete observation sequences for one comparison."""
    return ObservationRegistry(old.nodes, new.nodes)


def _similarity_signals(old_node: BillNode, new_node: BillNode) -> dict[str, bool | float]:
    """The two signals the similarity rule reads. Describes; decides nothing.

    **The legacy short-circuit is preserved exactly, and that is the point of the shape.**
    Production computes the word-level diff first and computes the similarity ratio ONLY when
    that diff is non-empty. Over the committed corpus that skips the ratio on 13,866 of 15,034
    path-matched pairings. Computing it unconditionally would be tidier, would cost a measured
    +21% on ``diff_bills``, and would be a behaviour change dressed as a refactor: the set of
    ``text_similarity`` calls the engine makes would differ from the set it makes today.

    So ``word_overlap`` is **absent** rather than ``None`` when the bodies are unchanged.
    :data:`~deltatrack.matching.Scalar` admits ``None``, which would make "not computed" and
    "computed as null" indistinguishable through ``CorrespondenceEvidence.get``; omitting the
    name keeps them distinguishable through ``.names``.

    Registry-free on purpose: turning signals into addressed evidence is
    :func:`similarity_correspondence_evidence`'s job, and keeping the measurement separable from
    the addressing is what lets a test check one without the other.
    """
    old_normalized = _normalize_text(old_node.body_text)
    new_normalized = _normalize_text(new_node.body_text)
    if not diff_text(old_normalized, new_normalized):
        return {BODY_UNCHANGED: True}
    return {
        BODY_UNCHANGED: False,
        WORD_OVERLAP: text_similarity(old_normalized, new_normalized),
    }


def similarity_correspondence_evidence(
    pairs: list[tuple[BillNode | None, BillNode | None]],
    registry: ObservationRegistry,
) -> tuple[CorrespondenceEvidence, ...]:
    """CORRESPONDENCE EVIDENCE for the similarity rule: one record per 1:1 pairing.

    Named for the one rule these signals feed, not for round 1. ``match_nodes`` also decides
    correspondence -- ``_similarity_pair``'s unthresholded greedy claim and the unique-path
    direct selection are both assignment acts under ADR 0020 invariant 6 -- and neither produces
    evidence here. A name like ``round1_correspondence_evidence`` would claim coverage this does
    not have.

    **Every 1:1 pairing gets a record, including the ones the rule will revoke.** That is ADR
    0020 invariant 8: evidence for candidates that reach assignment stays retained and
    inspectable. A revoked pairing's record is not attached to any ``Correspondence`` -- no
    correspondence was selected -- but it stays in this tuple for the life of the comparison,
    exactly as round 2's rejected candidates stay in ``move_correspondence_evidence``'s output.
    Retained and unattached, never discarded.

    Unmatched pairings carry no record: a ``(node, None)`` names no pair, so there is nothing for
    evidence to describe.
    """
    evidence: list[CorrespondenceEvidence] = []
    for old_node, new_node in pairs:
        if old_node is None or new_node is None:
            continue
        evidence.append(
            CorrespondenceEvidence.of(
                registry.ref(OLD, old_node),
                registry.ref(NEW, new_node),
                **_similarity_signals(old_node, new_node),
            )
        )
    return tuple(evidence)


def _evidence_by_link(
    evidence: tuple[CorrespondenceEvidence, ...],
) -> dict[tuple[ObservationRef, ObservationRef], CorrespondenceEvidence]:
    """Evidence addressed by ADR 0019 observation pair, refusing a duplicated link.

    Keyed by ``(old_ref, new_ref)`` and never by position in this tuple. The tuple is shorter
    than the pairing stream -- only 1:1 pairings carry a record -- so a positional read would
    misalign rather than silently mispair, and that property is worth keeping rather than
    engineering around.

    A repeated link is refused instead of resolved: two records for one pair leave no answer to
    "which one selected it", which is the question the attached evidence exists to answer.
    """
    by_link: dict[tuple[ObservationRef, ObservationRef], CorrespondenceEvidence] = {}
    for item in evidence:
        if item.link in by_link:
            raise ValueError(
                f"two evidence records for the pairing {item.old}->{item.new}; the evidence that "
                "selected a link is singular"
            )
        by_link[item.link] = item
    return by_link


def _similarity_rule_keeps(evidence: CorrespondenceEvidence, threshold: float) -> bool:
    """ASSIGNMENT: whether the similarity rule keeps this pairing. Owns the threshold.

    Reads only the evidence. The transcribed rule, in the positive:

        if not diff_text(...):                        -> kept   (body_unchanged)
        elif text_similarity(...) < THRESHOLD:        -> revoked
        else:                                         -> kept

    **Malformed evidence raises; it never silently revokes.** A missing or wrongly typed signal
    means the evidence stage and this rule disagree about the vocabulary, and the safe-looking
    reading of that -- treat it as "not similar enough", revoke -- would split a provision on the
    strength of a bug and report it as a removal plus an addition. ``bool`` is checked before
    ``float`` because ``isinstance(True, int)`` is true in Python and a bool must not be read as
    a score. Mirrors ``move_correspondence_evidence``'s existing strictness about a
    non-``float`` score.
    """
    if BODY_UNCHANGED not in evidence.names:
        raise ValueError(f"evidence for {evidence.old}->{evidence.new} carries no {BODY_UNCHANGED} signal")
    body_unchanged = evidence.get(BODY_UNCHANGED)
    if not isinstance(body_unchanged, bool):
        raise ValueError(
            f"evidence for {evidence.old}->{evidence.new} carries a non-bool {BODY_UNCHANGED}: {body_unchanged!r}"
        )
    if body_unchanged:
        return True
    if WORD_OVERLAP not in evidence.names:
        raise ValueError(
            f"evidence for {evidence.old}->{evidence.new} has {BODY_UNCHANGED}=False and no "
            f"{WORD_OVERLAP} signal; the rule cannot decide and must not guess"
        )
    word_overlap = evidence.get(WORD_OVERLAP)
    if not isinstance(word_overlap, float):
        raise ValueError(
            f"evidence for {evidence.old}->{evidence.new} carries a non-float {WORD_OVERLAP}: {word_overlap!r}"
        )
    return word_overlap >= threshold


def apply_similarity_assignment_rule(
    pairs: list[tuple[BillNode | None, BillNode | None]],
    evidence: tuple[CorrespondenceEvidence, ...],
    registry: ObservationRegistry,
    *,
    threshold: float,
) -> list[tuple[BillNode | None, BillNode | None]]:
    """Replace each revoked pairing with the two unmatched observations it becomes.

    Named for the one rule it applies. It is **not** the whole of round-1 assignment: ``match_nodes``
    still selects a unique-path pairing outright and still runs ``_similarity_pair``'s greedy claim,
    both of which decide correspondence and neither of which this slice touches.

    Input is ``match_nodes`` output; output is the same shape, so no new type is introduced and
    nothing here is an ADR 0020 ``Correspondence``. A ``(old, None)`` or ``(None, new)`` in the
    result is an *unmatched observation*, not a settled 1:0 or 0:1: the move pass may still pair it
    with a different partner.

    **The two replacements are adjacent and in place**, and that is load-bearing rather than
    incidental. Classification emits one record per pairing in order, so emitting the removal and
    the addition at the position the pairing occupied is what keeps the change list identical to the
    pre-refactor one -- which in turn keeps round 2's ``(ri, ai)`` positions, its candidate
    population, its selections and every canonical ``c-XXXX`` identifier where they were. Reversing
    the two, or appending them elsewhere, moves canonical output while leaving every change *count*
    untouched.

    ``threshold`` is a parameter rather than a read of ``SIMILARITY_THRESHOLD``, so a test can move
    it and watch this stage alone respond. A 1:1 pairing with no evidence raises: it means the
    evidence stage and this one disagree about the population, and revoking on that basis would be
    guessing.
    """
    by_link = _evidence_by_link(evidence)
    decided: list[tuple[BillNode | None, BillNode | None]] = []
    for old_node, new_node in pairs:
        if old_node is None or new_node is None:
            decided.append((old_node, new_node))
            continue
        link = (registry.ref(OLD, old_node), registry.ref(NEW, new_node))
        item = by_link.get(link)
        if item is None:
            raise ValueError(f"no correspondence evidence for the 1:1 pairing {link[0]}->{link[1]}")
        if _similarity_rule_keeps(item, threshold):
            decided.append((old_node, new_node))
        else:
            decided.append((old_node, None))
            decided.append((None, new_node))
    return decided


def unmatched_population(
    pairs: list[tuple[BillNode | None, BillNode | None]],
    registry: ObservationRegistry,
) -> UnmatchedPopulation:
    """Round 2's retrieval population, projected from the post-revocation pairing stream.

    Each side keeps the order the stream presents, which is what makes the legacy ``(ri, ai)``
    positions the same ones production computes today. Production derives them by filtering the
    **classified** change list on ``change_type``. Classification emits exactly one record per
    pairing, in order, and the type is a function of the pairing's shape alone, so filtering the
    pairings and filtering the records yield the same sequence element for element. #590 Section E
    measured that equality as ordered ``element_id`` sequences over all 27 corpus pairs (1,207 old
    and 16,321 new observations); deriving the population here from the pairings makes it true by
    construction instead, and the measurement becomes corroboration rather than the argument.

    A pairing naming neither side is refused. It is unreachable from ``match_nodes`` — a tuple is
    emitted only for a ``match_path`` present on at least one side — and the classification it fed
    had no branch for it, so one would silently emit no record and break exactly the positional
    correspondence this projection depends on.
    """
    old_unmatched: list[Observation] = []
    new_unmatched: list[Observation] = []
    for position, (old_node, new_node) in enumerate(pairs):
        if old_node is not None and new_node is not None:
            continue
        if old_node is not None:
            old_unmatched.append(registry.observation(OLD, old_node))
        elif new_node is not None:
            new_unmatched.append(registry.observation(NEW, new_node))
        else:
            raise ValueError(f"pairing {position} names no observation on either side")
    return UnmatchedPopulation(old=tuple(old_unmatched), new=tuple(new_unmatched))


def retrieve_move_candidates(population: UnmatchedPopulation, *, bound: float) -> CandidateSet:
    """RETRIEVAL, round 2: which unmatched observation pairs are worth evaluating.

    ``bound`` is retrieval's own control. ADR 0020 permits retrieval to bound consideration and
    requires the control to be explicit and recorded, so it is written into the invocation's
    config and travels with every proposal. It is a **separate parameter** from assignment's
    threshold even though production passes the same constant to both: that is what lets a test
    move the two apart and show each stage reading its own input, rather than inferring it from
    one shared constant that no test can separate.

    Scoring is delegated to ``similarity.move_candidates`` unchanged, so the pairing population,
    the normalization, the empty-text skip (#357) and the numbers are production's own. Text-free
    entries yield no candidate while still occupying their positions.
    """
    candidates = CandidateSet()
    if not population.old or not population.new:
        return candidates

    invocation = RetrieverInvocation.of("unmatched_text_overlap", round=MOVE_ROUND, threshold=bound)
    for score, ri, ai in move_candidates(
        [_normalize_text(observation.node.body_text) for observation in population.old],
        [_normalize_text(observation.node.body_text) for observation in population.new],
        bound,
    ):
        candidates.propose(population.old[ri].ref, population.new[ai].ref, invocation, score=score)
    return candidates


def move_correspondence_evidence(candidates: CandidateSet) -> tuple[CorrespondenceEvidence, ...]:
    """CORRESPONDENCE EVIDENCE, round 2: promote the retrieval score to a named signal.

    ADR 0020 is explicit that a retrieval score is *not* correspondence evidence — it exists for
    observability and for recall and ranking analysis — and equally explicit about what to do when
    one turns out to be informative: name it as an evidence signal, where it can be measured. This
    is that promotion, and the only place it happens. Assignment reads the signal and never
    ``Proposal.score``, so the two can be perturbed independently and the boundary tested rather
    than asserted.

    No verdict, no confidence, no threshold. What the number *means* for correspondence is
    assignment's to decide.
    """
    evidence: list[CorrespondenceEvidence] = []
    for candidate in candidates.candidates():
        if len(candidate.proposals) != 1:
            raise ValueError(
                f"candidate {candidate.ordinal_pair} carries {len(candidate.proposals)} proposals; "
                "round 2 runs exactly one retriever invocation"
            )
        score = candidate.proposals[0].score
        if not isinstance(score, float):
            raise ValueError(f"candidate {candidate.ordinal_pair} was retrieved without a score to promote")
        evidence.append(CorrespondenceEvidence.of(candidate.old, candidate.new, **{WORD_OVERLAP: score}))
    return tuple(evidence)


def _word_overlap(evidence: CorrespondenceEvidence) -> float:
    """The one evidence signal round-2 assignment reads."""
    value = evidence.get(WORD_OVERLAP)
    if not isinstance(value, float):
        raise ValueError(f"evidence for {evidence.old}->{evidence.new} carries no {WORD_OVERLAP} signal")
    return value


def _greedy_move_links(
    population: UnmatchedPopulation,
    evidence: tuple[CorrespondenceEvidence, ...],
    threshold: float,
) -> list[CorrespondenceEvidence]:
    """The legacy competition, kept whole and kept private.

    Production sorts ``(similarity, ri, ai)`` tuples with ``reverse=True``, so a tie on similarity
    breaks on **descending** ``ri`` and then **descending** ``ai``. Sorting on similarity alone and
    leaning on a stable secondary order is a different rule, and #590 measured that replacing
    ``(ri, ai)`` with parser ordinals moves the selected set on 3 corpus pairs — so the key is
    policy, not an incidental tiebreak.

    ``(ri, ai)`` are positions in ``population`` and **never leave this function**. They are legacy
    ordering machinery rather than addresses, and letting them cross the stage boundary is what
    would invite a later reader to mistake one for the other.
    """
    ri_of = {observation.ref: index for index, observation in enumerate(population.old)}
    ai_of = {observation.ref: index for index, observation in enumerate(population.new)}

    eligible = [item for item in evidence if _word_overlap(item) >= threshold]
    ordered = sorted(eligible, key=lambda item: (_word_overlap(item), ri_of[item.old], ai_of[item.new]), reverse=True)

    claimed_old: set[int] = set()
    claimed_new: set[int] = set()
    selected: list[CorrespondenceEvidence] = []
    for item in ordered:
        ri, ai = ri_of[item.old], ai_of[item.new]
        if ri in claimed_old or ai in claimed_new:
            continue
        claimed_old.add(ri)
        claimed_new.add(ai)
        selected.append(item)
    return selected


def assign_moves(
    population: UnmatchedPopulation,
    evidence: tuple[CorrespondenceEvidence, ...],
    *,
    threshold: float,
) -> tuple[Correspondence, ...]:
    """ASSIGNMENT, round 2: which retrieved pairs actually correspond.

    Returns settled 1:1 correspondences in greedy selection order, each carrying the one evidence
    record that selected it. ``threshold`` is assignment's own, because every rule deciding whether
    a candidate *becomes* a correspondence lives here (ADR 0020 invariant 6).

    Production passes the same constant to retrieval's bound and to this, so re-applying it selects
    exactly what it selected before. That is the point rather than an oversight: the bound expresses
    what was worth considering and this expresses what corresponds, and only the second is permitted
    to decide. Give the two different values and this refuses the difference — which is what makes
    the separation testable instead of decorative.
    """
    return tuple(
        Correspondence(old=(item.old,), new=(item.new,), evidence=(item,))
        for item in _greedy_move_links(population, evidence, threshold)
    )


def settle_correspondences(
    pairs: list[tuple[BillNode | None, BillNode | None]],
    registry: ObservationRegistry,
    moves: tuple[Correspondence, ...],
    *,
    round1_evidence: tuple[CorrespondenceEvidence, ...],
) -> tuple[SettledCorrespondence, ...]:
    """Every correspondence settled for one comparison, tagged with the round that selected it.

    **Nothing is settled before this point**, and that is forced rather than preferred:
    ``CorrespondenceSet`` refuses an observation that already corresponds, so settling an unmatched
    observation as a 1:0 and later revising it into a 1:1 move is impossible to express. The
    post-revocation stream is therefore provisional throughout — an ``(old, None)`` in it is an
    unmatched observation, not a settled removal — and round 2 runs before any of it is committed.

    Emission is chronological: round 1 in the order the pairing stream presents it, then round 2 in
    greedy selection order. That is the order assignment produced them and nothing more. Where the
    moved records land in the **output** is classification's policy, and :func:`classify` applies
    it to whatever order this returns.

    The ``CorrespondenceSet`` built here is the exclusivity invariant checked rather than assumed —
    every observation in at most one correspondence — and it is what refuses a premature settlement.

    ``round1_evidence`` is keyword-only and required. It is the whole evidence collection from
    :func:`similarity_correspondence_evidence`, rejected pairings included; this attaches the
    subset that selected a surviving 1:1 and leaves the rest retained but unattached. Required
    rather than defaulting to ``()`` so that every call site says what it means: a caller whose
    pairing stream genuinely holds no 1:1 passes ``()`` deliberately, rather than omitting an
    argument and discovering the difference at the first surviving pairing.
    """
    evidence_by_link = _evidence_by_link(round1_evidence)
    claimed = {ref for move in moves for ref in (*move.old, *move.new)}
    settled: list[SettledCorrespondence] = []

    for position, (old_node, new_node) in enumerate(pairs):
        if old_node is not None and new_node is not None:
            old_ref = registry.ref(OLD, old_node)
            new_ref = registry.ref(NEW, new_node)
            # The exact record the similarity rule read to keep this pairing, carried through to
            # the correspondence it selected. The contract requires exactly one evidence record
            # per selected link; a missing one is refused rather than replaced by an empty record,
            # because the empty record is what this slice exists to remove and a silent fallback
            # would reinstate it wherever the wiring is wrong.
            item = evidence_by_link.get((old_ref, new_ref))
            if item is None:
                raise ValueError(
                    f"the surviving 1:1 pairing {old_ref}->{new_ref} carries no correspondence evidence; "
                    "the evidence that selected a link must travel with it"
                )
            settled.append(
                SettledCorrespondence(
                    Correspondence(old=(old_ref,), new=(new_ref,), evidence=(item,)),
                    PATH_ROUND,
                )
            )
        elif old_node is not None:
            old_ref = registry.ref(OLD, old_node)
            if old_ref not in claimed:
                settled.append(SettledCorrespondence(Correspondence(old=(old_ref,)), PATH_ROUND))
        elif new_node is not None:
            new_ref = registry.ref(NEW, new_node)
            if new_ref not in claimed:
                settled.append(SettledCorrespondence(Correspondence(new=(new_ref,)), PATH_ROUND))
        else:
            raise ValueError(f"pairing {position} names no observation on either side")

    settled.extend(SettledCorrespondence(move, MOVE_ROUND) for move in moves)

    exclusive = CorrespondenceSet()
    for item in settled:
        exclusive.add(item.correspondence)
    return tuple(settled)


def _added_record(new_node: BillNode) -> NodeDiff:
    return NodeDiff(
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


def _removed_record(old_node: BillNode) -> NodeDiff:
    return NodeDiff(
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


def _paired_record(old_node: BillNode, new_node: BillNode) -> NodeDiff:
    """A round-1 1:1: ``unchanged`` when the word-level diff is empty, else ``modified``."""
    text_changes = diff_text(_normalize_text(old_node.body_text), _normalize_text(new_node.body_text))
    return NodeDiff(
        display_path_old=old_node.display_path,
        display_path_new=new_node.display_path,
        match_path=old_node.match_path,
        change_type="unchanged" if not text_changes else "modified",
        old_text=old_node.body_text,
        new_text=new_node.body_text,
        text_diff=None if not text_changes else text_changes,
        section_number=new_node.section_number or old_node.section_number,
        element_id_old=old_node.element_id,
        element_id_new=new_node.element_id,
        old_amount_text=amount_text(old_node),
        new_amount_text=amount_text(new_node),
    )


def _moved_record(old_node: BillNode, new_node: BillNode) -> NodeDiff:
    """A round-2 1:1.

    ``text_diff`` is ``None`` rather than ``[]`` when the normalized texts match, which is a
    serialized field and so a canonical byte. ``match_path`` is the OLD node's while
    ``section_number`` prefers the new — both transcribed from the legacy record, not tidied.
    """
    old_normalized = _normalize_text(old_node.body_text)
    new_normalized = _normalize_text(new_node.body_text)
    return NodeDiff(
        display_path_old=old_node.display_path,
        display_path_new=new_node.display_path,
        match_path=old_node.match_path,
        change_type="moved",
        old_text=old_node.body_text,
        new_text=new_node.body_text,
        text_diff=diff_text(old_normalized, new_normalized) if old_normalized != new_normalized else None,
        section_number=new_node.section_number or old_node.section_number,
        element_id_old=old_node.element_id,
        element_id_new=new_node.element_id,
        # Each side's amount source travels with the text it came from, so a moved section's
        # amounts stay readable (#365).
        old_amount_text=amount_text(old_node),
        new_amount_text=amount_text(new_node),
    )


def _classified(item: SettledCorrespondence, registry: ObservationRegistry) -> NodeDiff:
    """One settled correspondence as one change record."""
    correspondence = item.correspondence
    if not correspondence.is_binary:
        raise ValueError(
            f"classification received a {correspondence.shape} correspondence; the canonical contract "
            "is a binary row and ADR 0020 requires a non-binary one to be projected explicitly"
        )
    old_node = registry.node(correspondence.old[0]) if correspondence.old else None
    new_node = registry.node(correspondence.new[0]) if correspondence.new else None

    if old_node is None:
        return _added_record(new_node)
    if new_node is None:
        return _removed_record(old_node)
    if item.round == MOVE_ROUND:
        return _moved_record(old_node, new_node)
    return _paired_record(old_node, new_node)


def classify(
    settled: tuple[SettledCorrespondence, ...],
    registry: ObservationRegistry,
) -> list[NodeDiff]:
    """CLASSIFICATION: what changed, given settled correspondence.

    Decides nothing about correspondence: no threshold is applied to any evidence, no partner is
    changed, and every observation is resolved through the complete :class:`ObservationRegistry`
    rather than through a filtered-list position or an ``element_id``.

    **Record order is this stage's policy, applied here rather than inherited.** The legacy output
    keeps non-moved records in their preserved order and appends the round-2 moved records in greedy
    selection order. That is reproduced by a stable sort on the round alone, so the result depends on
    each round's internal order and not on how assignment happened to interleave the two — an
    output-construction requirement kept out of the stage that decides correspondence.
    """
    return [_classified(item, registry) for item in sorted(settled, key=lambda item: item.round)]


def _count_changes(changes: list[NodeDiff]) -> dict:
    """Compute summary counts from the final changes list."""
    counts = Counter(c.change_type for c in changes)
    return {t: counts.get(t, 0) for t in ("added", "removed", "modified", "unchanged", "moved")}


def diff_bills(old: BillTree, new: BillTree) -> BillDiff:
    """Compare two bill versions and produce a structured diff.

    The body is the ADR 0020 stage sequence, written out so stage ownership reads off the call
    graph rather than off a comment. Both retrieval rounds now run **before** classification,
    which is the rule this slice exists to satisfy: retrieval may run in several rounds and a
    later round may consult earlier matching state, but none of it may run after classification.

    Round 2 stays after :func:`apply_similarity_assignment_rule`, and that ordering is load-bearing
    rather than incidental — 228 of the corpus's 496 selected moves touch an observation that
    exists only because the similarity rule revoked its pairing, and 145 have both sides so
    produced. Post-#591 that is a sequencing constraint inside matching, no longer a dependency
    on classification output.

    What remains fused, said plainly: **round-1 retrieval, and the rest of round-1 assignment.**
    ``match_nodes`` still decides what may be compared (``match_path`` grouping, division
    subgrouping, the cross-division fallback) and still makes two assignment decisions of its own
    in the same pass — it selects a unique-path pairing outright, and ``_similarity_pair`` runs an
    unthresholded greedy claim. Both are assignment under ADR 0020 invariant 6 and both are
    deferred. What this slice moves is the **one** round-1 rule that can revoke a pairing: it now
    reads named evidence and owns its threshold, rather than recomputing both inline.
    """
    registry = observation_registry(old, new)
    pairings = match_nodes(old, new)
    round1_evidence = similarity_correspondence_evidence(pairings, registry)
    pairs = apply_similarity_assignment_rule(pairings, round1_evidence, registry, threshold=SIMILARITY_THRESHOLD)
    population = unmatched_population(pairs, registry)
    candidates = retrieve_move_candidates(population, bound=MOVE_THRESHOLD)
    evidence = move_correspondence_evidence(candidates)
    moves = assign_moves(population, evidence, threshold=MOVE_THRESHOLD)
    settled = settle_correspondences(pairs, registry, moves, round1_evidence=round1_evidence)
    changes = classify(settled, registry)

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


def _reject_bills_dir_conflict(bills_dir_explicit: bool, bills_dir: Path, target: str) -> None:
    """Hard error when an explicit ``--bills-dir`` would be silently overridden.

    ``Path(bills_dir) / target`` discards ``bills_dir`` outright when ``target`` is
    absolute (#454), because that's how ``pathlib`` joins paths. Harmless -- and
    deliberate -- for the bare-absolute-directory listing #426 added, since nobody
    asked for ``--bills-dir`` there. It stops being harmless the moment someone names
    both: the flag looks respected while a different corpus answers instead, with
    nothing in the output to say so. Checked before any resolution is attempted, so the
    conflict is reported instead of a diff that describes the wrong files.
    """
    if bills_dir_explicit and Path(target).is_absolute():
        print(
            f"--bills-dir {bills_dir} was given, but {target!r} is an absolute path and "
            "would silently override it (an absolute path always wins the join). Drop "
            "--bills-dir, or address the bill by a bare slug under it instead.",
            file=sys.stderr,
        )
        raise SystemExit(2)


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
    bills_dir_explicit = args.bills_dir is not None
    bills_dir = args.bills_dir if bills_dir_explicit else Path("bills")
    if len(targets) == 2:
        return Path(targets[0]), Path(targets[1])
    if len(targets) == 3:
        slug, n_old, n_new = targets
        _reject_bills_dir_conflict(bills_dir_explicit, bills_dir, slug)
        return (
            _resolve_version_arg(bills_dir, slug, n_old),
            _resolve_version_arg(bills_dir, slug, n_new),
        )
    if len(targets) == 1:
        target = targets[0]
        _reject_bills_dir_conflict(bills_dir_explicit, bills_dir, target)
        # The listing is tried FIRST so that the shape check below only ever picks
        # between two failures. Checking the shape first let it pick between success and
        # failure instead: `cd bills && compare --bills-dir . 118-hr-4366` names both a
        # resolvable slug and an existing directory, and the check turned that working
        # command into "the second path is missing" (#426 review).
        versions = local_versions(bills_dir, target)
        if versions:
            print(_format_version_listing(bills_dir, target, versions))
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
        raise SystemExit(_format_version_listing(bills_dir, target, versions))
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
        default=None,
        help=(
            "Root holding the per-bill download folders, for the <slug> forms "
            "(default: bills). An absolute <slug>/<TARGET> always wins the path join "
            "and passing both together is a hard error, except for a bare absolute "
            "directory listing (compare <abs-dir>), which doesn't need this flag."
        ),
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
