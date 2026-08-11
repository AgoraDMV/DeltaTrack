"""The boundary this slice creates: classification classifies, and decides nothing.

One architectural property became true in ``diff_bill``:

    Classification no longer thresholds or revokes a provisional ``(old, new)`` pairing.

Two tests carry that, and they are not interchangeable.

**The behavioural one is the contract.** ``test_classification_preserves_the_shape_it_
receives`` says classification is a length-preserving, order-preserving, side-preserving
map from decided pairings to change records. That single statement refuses all five ways
classification could touch correspondence -- splitting one pairing into two and joining two
into one both move the length, while dropping a side, inventing one and substituting a
different observation each surface as a mismatch at the pairing's own index. It stays true
however the code is later reorganised, which is what makes it the durable one.

**The source-level one is a tripwire, not a proof.** ``test_classification_body_names_no_
correspondence_cutoff`` catches exactly one regression: someone re-inlining the cutoff into
``diff_bills``. A future classification could call some other helper that changes
correspondence and satisfy it. It is kept because it names the offending line, and because
it costs nothing -- not because it establishes the architecture.

**Why an apparently duplicated rule lives here.** ``legacy_pairing_was_revoked`` is a
transcription of the pre-refactor decision, taken from ``diff_bill.diff_bills`` as it stood
at ``97f91ba`` (the classification loop's ``diff_text`` / ``SIMILARITY_THRESHOLD``
branch). It exists to disagree with production. An oracle that asked the extracted helper
what the rule is could not detect that the extraction changed it, which is the one failure
this slice can actually have -- so this must never be replaced by a call to
``pairing_survives_similarity_rule``, and production must never import it. It composes the
same primitives (``_normalize_text``, ``diff_text``, ``text_similarity``,
``SIMILARITY_THRESHOLD``) deliberately: what it guards is the *composition* -- an inverted
comparison, a dropped gate, a reordered branch, the wrong constant. The primitives have
their own tests, and the canonical baseline covers the composite.

**Element identity is checked here by ``element_id``**, which is traceability information
and not ADR 0019 observation identity. It is used only to ask "is this the same node the
pairing named", within one run, where the parse on both sides is the same object graph.
Nothing is stored, and no ordinal is derived from it.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from deltatrack import diff_bill
from deltatrack.bill_tree import BillNode, normalize_bill
from deltatrack.diff_bill import (
    NodeDiff,
    apply_similarity_revocation,
    diff_bills,
    diff_text,
    match_nodes,
    pairing_survives_similarity_rule,
)
from deltatrack.similarity import SIMILARITY_THRESHOLD, text_similarity

_DIFF_BILL_SOURCE = Path(diff_bill.__file__)


# --- The oracle: the rule as it stood before the extraction --------------------------


def legacy_pairing_was_revoked(old_node: BillNode, new_node: BillNode) -> bool:
    """Whether the PRE-REFACTOR ``diff_bills`` would have split this pairing.

    Transcribed from ``src/deltatrack/diff_bill.py`` at ``97f91ba``, where the classification
    loop read:

        text_changes = diff_text(old_normalized, new_normalized)
        if not text_changes:                                  -> unchanged (kept)
        elif text_similarity(...) < SIMILARITY_THRESHOLD:     -> removed + added (revoked)
        else:                                                 -> modified (kept)

    Independent by construction: it must not call ``pairing_survives_similarity_rule``, and
    production must not import this. See the module docstring for why the duplication is
    the point rather than an oversight.
    """
    old_normalized = " ".join(old_node.body_text.split())
    new_normalized = " ".join(new_node.body_text.split())
    if not diff_text(old_normalized, new_normalized):
        return False
    return text_similarity(old_normalized, new_normalized) < SIMILARITY_THRESHOLD


# --- The shape invariant, as a checker so a caller can prove it rejects ---------------


def shape_violations(decided: list, changes: list) -> list[str]:
    """Ways ``changes`` fails to be the classification of ``decided``, in order.

    Returns rather than asserts, so a test can hand it a deliberately broken result and
    require a complaint. A checker that has never rejected anything cannot be told apart
    from one that accepts everything.
    """
    if len(changes) != len(decided):
        return [f"classification emitted {len(changes)} records for {len(decided)} decided pairings"]
    problems = []
    for index, ((old_node, new_node), change) in enumerate(zip(decided, changes)):
        expected_old = "" if old_node is None else old_node.element_id
        expected_new = "" if new_node is None else new_node.element_id
        if change.element_id_old != expected_old or change.element_id_new != expected_new:
            problems.append(
                f"index {index}: classified sides {change.element_id_old!r}/{change.element_id_new!r} "
                f"but the decided pairing was {expected_old!r}/{expected_new!r}"
            )
    return problems


def threshold_references_in(source: str, function_name: str) -> list[str]:
    """Correspondence-cutoff names read directly inside one function's body."""
    watched = {"SIMILARITY_THRESHOLD", "text_similarity"}
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return sorted({child.id for child in ast.walk(node) if isinstance(child, ast.Name) and child.id in watched})
    raise AssertionError(f"no function named {function_name} in the given source")


# --- Fixtures for the fast tests ------------------------------------------------------


def _node(element_id: str, body_text: str) -> BillNode:
    return BillNode(
        match_path=("sec-1",),
        display_path=("SEC. 1.",),
        tag="section",
        element_id=element_id,
        header_text="Heading",
        body_text=body_text,
        section_number="1",
        division_label="",
    )


def _classified(change_type: str, element_id_old: str, element_id_new: str) -> NodeDiff:
    return NodeDiff(
        display_path_old=("SEC. 1.",) if element_id_old else None,
        display_path_new=("SEC. 1.",) if element_id_new else None,
        match_path=("sec-1",),
        change_type=change_type,
        old_text="old" if element_id_old else None,
        new_text="new" if element_id_new else None,
        text_diff=None,
        section_number="1",
        element_id_old=element_id_old,
        element_id_new=element_id_new,
    )


# --- Phase-1 policy pins --------------------------------------------------------------


def test_the_similarity_cutoff_is_pinned_for_phase_1():
    """A LEGACY BEHAVIOUR-PRESERVATION GUARD, not an architectural requirement.

    ADR 0020 deliberately does not prescribe a cutoff value; choosing one is a measurement
    question it defers. This pin exists only because the Phase-1 extraction must not change
    policy, and because the oracle above reads the constant -- so without a direct pin, a
    changed cutoff would move production and oracle together and the agreement test would
    stay green.

    A later, evidence-backed matching-policy change is expected to update or delete this
    knowingly, in the pull request carrying its precision and recall evidence. Doing so is
    not a violation of the architecture; leaving it unpinned during Phase 1 would be.
    """
    assert SIMILARITY_THRESHOLD == 0.4


# --- The behavioural contract, proven able to reject ----------------------------------


def test_the_shape_checker_rejects_a_pairing_split_into_a_removal_and_an_addition():
    """The exact regression this slice removes: classification splitting a live pairing.

    Doctors a classified result back into the pre-refactor shape -- one decided ``(old,
    new)`` emerging as an adjacent removal and addition -- and requires the checker to
    refuse it. Without this, the corpus test could be green because nothing ever splits
    rather than because splitting would be caught.
    """
    old_node, new_node = _node("id-old", "alpha"), _node("id-new", "beta")
    decided = [(old_node, new_node)]
    assert any(o is not None and n is not None for o, n in decided), "control never reached a paired case"

    regained_split = [
        _classified("removed", "id-old", ""),
        _classified("added", "", "id-new"),
    ]
    assert shape_violations(decided, regained_split), "a re-split pairing was accepted as a faithful classification"


def test_the_shape_checker_rejects_a_substituted_observation():
    """A side that names a different node, at the right index and the right length."""
    old_node, new_node = _node("id-old", "alpha"), _node("id-new", "beta")
    faithful = [_classified("modified", "id-old", "id-new")]
    assert not shape_violations([(old_node, new_node)], faithful)

    impostor = [replace(faithful[0], element_id_new="id-somewhere-else")]
    assert shape_violations([(old_node, new_node)], impostor)


def test_the_shape_checker_rejects_a_dropped_side():
    old_node, new_node = _node("id-old", "alpha"), _node("id-new", "beta")
    dropped = [replace(_classified("modified", "id-old", "id-new"), element_id_new="")]
    assert shape_violations([(old_node, new_node)], dropped)


# --- The source-level tripwire, proven able to fire -----------------------------------


def test_classification_body_names_no_correspondence_cutoff():
    """``diff_bills`` reads neither the cutoff nor the measure. A tripwire, not a proof.

    Scoped to ``diff_bills``' own body, so the sibling ``pairing_survives_similarity_rule``
    -- which is *supposed* to name both -- does not trip it.
    """
    named = threshold_references_in(_DIFF_BILL_SOURCE.read_text(), "diff_bills")
    assert not named, (
        f"diff_bills reads {named} directly. The correspondence decision belongs to "
        "pairing_survives_similarity_rule; classification classifies the shape it is handed."
    )


def test_the_source_tripwire_fires_on_a_reinlined_cutoff():
    """Feeds the checker a doctored source rather than mutating the file."""
    doctored = (
        "def diff_bills(old, new):\n"
        "    for a, b in pairs:\n"
        "        if text_similarity(a, b) < SIMILARITY_THRESHOLD:\n"
        "            pass\n"
    )
    assert threshold_references_in(doctored, "diff_bills") == ["SIMILARITY_THRESHOLD", "text_similarity"]


# --- Corpus gates ---------------------------------------------------------------------


def test_manifest_fixtures_committed():
    """Fail closed if a manifested bill is uncommitted, rather than gating fewer pairs."""
    from tests.conftest import assert_manifest_committed, manifest_version_pairs

    assert_manifest_committed(manifest_version_pairs(), "assignment-classification-boundary")


@pytest.mark.slow
def test_the_extracted_rule_agrees_with_the_pre_refactor_rule():
    """Every path-matched pairing gets the same verdict from production and the oracle."""
    from tests.conftest import manifest_version_pairs

    checked = 0
    revoked = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree = normalize_bill(old_path)
        new_tree = normalize_bill(new_path)
        label = f"{old_path.parent.name} {old_path.stem}->{new_path.stem}"
        for old_node, new_node in match_nodes(old_tree, new_tree):
            if old_node is None or new_node is None:
                continue
            checked += 1
            extracted_keeps = pairing_survives_similarity_rule(old_node, new_node)
            revoked += not extracted_keeps
            assert extracted_keeps == (not legacy_pairing_was_revoked(old_node, new_node)), (
                f"{label}: the extracted rule and the pre-refactor rule disagree on "
                f"{old_node.element_id} -> {new_node.element_id}"
            )

    assert checked, "the agreement measurement ran over zero pairings"
    assert revoked, "no pairing was revoked anywhere in the corpus, so agreement proves nothing"


@pytest.mark.slow
def test_classification_preserves_the_shape_it_receives(monkeypatch):
    """Classification is a length-, order- and side-preserving map from decided pairings.

    ``reconcile_moves`` is stubbed to the identity so ``diff_bills`` returns the change list
    as classification built it. That pass reorders and rebuilds entries by design, which is
    a later slice's business; this one is about what classification does with the shape it
    is given.
    """
    from tests.conftest import manifest_version_pairs

    monkeypatch.setattr(diff_bill, "reconcile_moves", lambda changes, threshold=None: changes)

    checked = 0
    for old_path, new_path in manifest_version_pairs():
        old_tree = normalize_bill(old_path)
        new_tree = normalize_bill(new_path)
        decided = apply_similarity_revocation(match_nodes(old_tree, new_tree))
        problems = shape_violations(decided, diff_bills(old_tree, new_tree).changes)
        label = f"{old_path.parent.name} {old_path.stem}->{new_path.stem}"
        assert not problems, f"{label}: {problems[:4]}"
        checked += 1

    assert checked, "the shape invariant ran over zero version pairs"
