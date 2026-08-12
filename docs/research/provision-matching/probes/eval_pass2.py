"""Skeletal evaluator for the Pass 2 anchor dataset -- the executable form of the data contract.

`pass2-protocol.md` §2.4 promised this file and it did not exist. Round 1 listed it as non-blocking
on the reasoning that metrics are needed after labeling, not before. Round 2's challenge to that
holds: the risk is not that the metrics are late, it is that the SCHEMA cannot produce them, and
the only way to find out is to compute them.

Round 3 then found that computing them is not the same as computing them VALIDLY. v1 of this file
printed YES for all five targets while three of the five were consuming truth that could not
support their arithmetic. So the design changed from "compute each metric over the records" to
"compute each metric over the records whose oracle can establish the proposition that metric
assumes, and say out loud which records were refused and why".

What "skeletal" still means: every promised metric is computed and its population is enforced.
Deliberately absent: confidence intervals, per-stratum breakdowns, inter-rater agreement, held-out
execution, weighting, and report formatting. Those are reporting concerns and can follow the labels.
The contract cannot.

THE TARGETS and the truth each one needs. The requirement is DATA, in
`pass2_schema.METRIC_TRUTH_REQUIREMENTS`, not prose here -- so that enforcement is testable and a
future metric cannot be added without declaring what it assumes.

  1 candidate recall   needs `complete-in-document`. The denominator is "counterparts that exist",
                       and an oracle that searched one region cannot enumerate it. Note the bias
                       runs by SELECTION rather than by a wrong label: an anchor whose counterpart
                       was never findable is dropped from the population, and those are exactly the
                       anchors retrieval failed on, so an incomplete oracle inflates recall.
  2 ranking            needs `affirmed-positive` only. Where the true counterpart ranked does not
                       depend on whether a second one exists elsewhere. This is the one target the
                       cheap oracle genuinely supports.
  3a per-anchor        needs `complete-in-document`. Did the system assign exactly THIS anchor's
     assignment       true counterpart set? A per-anchor question, answerable from a target-side
                       sweep alone, making no claim about other anchors.
  3b collision         needs `complete-source-side` -- a REVERSE sweep, the opposite direction.
     resolution        ** DEFERRED FROM STUDY 2 ** and excluded from `contract_check`: tiers A/B/C
                       collect no reverse sweeps, so it reports NOT MEASURABLE on a real dataset
                       and is not a condition for starting them. The machinery is retained and is
                       explicitly NOT fully validated; see `collision_resolution`.
  4 diff correctness   needs `complete-in-document`. `removed` vs `moved` IS the question of whether
                       a counterpart exists elsewhere in the document.
  5 failure modes      per stratum: an existence claim needs a positive, an absence claim needs
                       completeness. The stratum declares it in `challenge_requires`.

Run (no corpus needed; defaults to the synthetic contract fixture):
    .venv/bin/python docs/research/provision-matching/probes/eval_pass2.py
    .venv/bin/python docs/research/provision-matching/probes/eval_pass2.py path/to/labels.json
"""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pass2_schema import (  # noqa: E402
    METRIC_TRUTH_REQUIREMENTS,
    establishes,
    mark_verified_universes,
    observation_id,
    validate_dataset,
)

FIXTURE = Path(__file__).parent / "fixtures" / "eval_contract_synthetic.json"

#: Relations that assert a counterpart exists. `uncertain` is excluded from every metric that
#: needs a right answer, and counted separately, so it can never be silently read as `none`.
POSITIVE = ("one-to-one", "one-to-many", "many-to-one")


def _key(ref: dict) -> tuple:
    """Node identity for joining truth against candidates and against the system's output.

    `(source_sha256, parser_commit, node_ordinal)` -- an OBSERVATION identity, not a content hash.
    (`element_id` is recorded for traceability and is deliberately NOT part of the key: its
    uniqueness is a regularity of GPO markup, while an ordinal is unique by construction.)

    v1 joined on `(bill, version, text_sha256)`. Rejecting `match_path` was right (it is the
    unstable key this program exists because of), but the replacement assumed body text identifies
    a node, and R9 measured that it does not: 33% of documents in this corpus contain at least one
    body shared by two or more provisions, up to 12 copies of one text, reaching every version of
    all four answer-key bills. A content-hash join collapses them, and it fails OPTIMISTICALLY -- a
    recall miss against provision X scores as a hit whenever any boilerplate twin is in the
    candidate set.
    """
    return observation_id(ref)


def _admits(rec: dict, metric: str) -> bool:
    """Can this record's truth support the proposition `metric` assumes?

    `establishes` takes the whole truth block in v3, because `complete-in-document` now depends on
    measured review coverage rather than only on which oracle steps ran.
    """
    need = METRIC_TRUTH_REQUIREMENTS[metric]["requires"]
    if need == "per-stratum":
        need = rec.get("challenge_requires", "affirmed-positive")
    return establishes(rec["truth"], need)


def _partition(records: list[dict], metric: str) -> tuple[list[dict], list[dict]]:
    """(admitted, refused) for one metric. Refusal is reported, never silent."""
    admitted, refused = [], []
    for r in records:
        (admitted if _admits(r, metric) else refused).append(r)
    return admitted, refused


def _refusal_report(refused: list[dict], metric: str) -> dict:
    need = METRIC_TRUTH_REQUIREMENTS[metric]["requires"]
    return {
        "count": len(refused),
        "requires": need,
        "anchors": [
            {"anchor_id": r["anchor_id"], "oracles": r["truth"]["oracles"], "relation": r["truth"]["relation"]}
            for r in refused
        ],
    }


def candidate_recall(records: list[dict]) -> dict:
    """Target 1. Population: truth that can enumerate the counterpart set document-wide."""
    admitted, refused = _partition(records, "candidate_recall")
    eligible = [r for r in admitted if r["truth"]["relation"] in POSITIVE]
    found = total = full_anchor = 0
    missed = []
    for r in eligible:
        cands = {_key(c) for c in r["candidates"]}
        hits = 0
        for cp in r["truth"]["counterparts"]:
            total += 1
            if _key(cp) in cands:
                found += 1
                hits += 1
            else:
                missed.append((r["anchor_id"], cp["found_via"]))
        if hits == len(r["truth"]["counterparts"]):
            full_anchor += 1
    return {
        "counterpart_recall": _rate(found, total),
        "counterparts_found": found,
        "counterparts_total": total,
        "anchors_fully_recalled": _rate(full_anchor, len(eligible)),
        "anchors_eligible": len(eligible),
        "misses": missed,
        "refused": _refusal_report(refused, "candidate_recall"),
    }


def ranking(records: list[dict]) -> dict:
    """Target 2. Over one-to-one anchors whose affirmed counterpart the retrievers DID surface."""
    admitted, refused = _partition(records, "ranking")
    top1 = 0
    rr = 0.0
    n = 0
    for r in admitted:
        t = r["truth"]
        if t["relation"] != "one-to-one":
            continue
        target = _key(t["counterparts"][0])
        keys = [_key(c) for c in sorted(r["candidates"], key=lambda c: c["rank"])]
        if target not in keys:
            continue  # a retrieval miss, already counted in target 1
        n += 1
        pos = keys.index(target) + 1
        top1 += pos == 1
        rr += 1.0 / pos
    return {
        "n": n,
        "top1": _rate(top1, n),
        "mrr": (rr / n) if n else None,
        "refused": _refusal_report(refused, "ranking"),
    }


def assignment_per_anchor(records: list[dict]) -> dict:
    """Target 3a. For THIS anchor, did the system assign exactly its true counterpart set?

    A per-anchor question, answerable from a target-side sweep alone. It makes no claim about other
    anchors, so it does not need to know who else was competing -- which is precisely why it is
    separated from `collision_resolution` below.
    """
    admitted, refused = _partition(records, "assignment_per_anchor")
    correct, wrong = 0, []
    for r in admitted:
        truth_set = {_key(cp) for cp in r["truth"]["counterparts"]}
        sys_set = {_key(a) for a in r["system"]["assigned"]}
        if truth_set == sys_set:
            correct += 1
        else:
            wrong.append(r["anchor_id"])
    return {
        "n": len(admitted),
        "accuracy": _rate(correct, len(admitted)),
        "wrong": wrong,
        "refused": _refusal_report(refused, "assignment_per_anchor"),
    }


def collision_resolution(records: list[dict]) -> dict:
    """Target 3b. Did the global assignment resolve a contested target node correctly?

    ** DEFERRED FROM STUDY 2. ** Tiers A/B/C do not collect reverse sweeps, so on a real Study 2
    dataset this reports NOT MEASURABLE, and it is deliberately NOT a condition for starting the
    other tiers (`contract_check` excludes it). The machinery is retained because it is the only
    correct shape for the question and throwing it away would mean re-deriving it later.

    ** NOT FULLY VALIDATED. ** Stated plainly rather than implied by silence. What is proven: the
    direction argument, the target-identity key, and that a group without source-side truth is
    refused. What is NOT: the reverse-sweep path has never been exercised on real corpus data, and
    its `claiming_ordinals` have no independent check beyond being a subset of the swept universe.
    Do not read a number from this metric as validated.

    THE DIRECTION MATTERS, and v3 got it wrong. A `document-exhaustive` sweep runs per OLD anchor
    over the NEW document: it enumerates that anchor's counterparts. It says nothing about which
    OTHER old provisions claim the same new node. v3 derived collision groups from "whichever
    records happen to be in the dataset" and scored them with target-side truth, so an old
    competitor that was never sampled made a wrong resolution look right.

    Establishing the group needs the reverse sweep -- for one target node, review every old
    provision -- recorded as `truth.competition_coverage` and granting `complete-source-side`.
    """
    proven: dict[tuple, dict] = {}
    for r in records:
        comp = r["truth"].get("competition_coverage")
        if comp and _admits(r, "collision_resolution"):
            # Key on the TARGET's observation identity. The round-6 code keyed on the ANCHOR's
            # source hash plus a bare target ordinal, which scopes the wrong document: ordinal 73
            # exists in every version of every bill, so reverse truth collected for target A:73
            # could be looked up for B:73.
            proven[(comp["target_source_sha256"], comp["target_parser_commit"], comp["target_ordinal"])] = {
                "record": r,
                "claiming": set(comp["claiming_ordinals"]),
            }

    # Contention observed in the dataset, for reporting only -- never as evidence of a group.
    claims: dict[tuple, set[str]] = {}
    for r in records:
        for ref in [*r["truth"]["counterparts"], *r["candidates"]]:
            claims.setdefault(_key(ref), set()).add(r["anchor_id"])
    observed = {k for k, v in claims.items() if len(v) > 1}

    scored, correct, wrong = 0, 0, []
    for _key_tuple, info in proven.items():
        r = info["record"]
        scored += 1
        # BOTH sides of this comparison are OLD-side ordinals. An earlier cut compared the system's
        # assigned TARGET ordinals against the truth's CLAIMING ordinals -- two different documents,
        # and a comparison that could never be right. `system.competition_claimants` is matcher
        # output (which old provisions the system assigned to this target), so recording it costs
        # nothing and it does not depend on which anchors happen to be sampled -- which was the
        # original defect in deriving groups from the dataset.
        sys_claimants = set(r["system"]["competition_claimants"])
        if sys_claimants != info["claiming"]:
            wrong.append(r["anchor_id"])
        else:
            correct += 1
    return {
        "study2_scope": "deferred",
        "validation_status": (
            "not fully validated -- never exercised on real corpus data, and `claiming_ordinals` "
            "have no independent check beyond subset-of-the-swept-universe"
        ),
        "measurable": scored > 0,
        "groups_with_source_side_truth": scored,
        "groups_observed_in_dataset_without_source_side_truth": len(observed) - scored,
        "accuracy": _rate(correct, scored),
        "wrong": wrong,
        "why_not_measurable": (
            None
            if scored
            else "no record carries `competition_coverage`; a contested node observed in the "
            "dataset is not evidence that every old provision claiming it has been found, and "
            "target-side sweeps cannot establish it at any level of thoroughness"
        ),
    }


def diff_correctness(records: list[dict]) -> dict:
    """Target 4. The staffer-visible outcome: a confusion matrix over document-complete anchors."""
    admitted, refused = _partition(records, "diff_correctness")
    matrix: Counter[tuple[str, str]] = Counter()
    for r in admitted:
        matrix[(r["truth"]["change_type"], r["system"]["change_type"])] += 1
    correct = sum(v for (t, s), v in matrix.items() if t == s)
    total = sum(matrix.values())
    return {
        "accuracy": _rate(correct, total),
        "n": total,
        "matrix": {f"truth={t} -> system={s}": v for (t, s), v in sorted(matrix.items())},
        "refused": _refusal_report(refused, "diff_correctness"),
    }


def _mode_occurred(rec: dict) -> bool:
    """Did the failure this stratum claims actually happen, for this record?

    The test depends on what the stratum is claiming, which is why `challenge_requires` is data.
    v2 applied one test to every stratum -- "does the system's assignment differ from truth's
    counterpart set" -- which is only correct for the completeness strata, and which silently
    required document-wide truth for a claim that is purely pairwise.
    """
    sys_set = {_key(a) for a in rec["system"]["assigned"]}
    if rec.get("challenge_requires") == "affirmed-negative":
        # "the matcher kept a pair a human ruled DIFFERENT". Purely pairwise: it needs the rejected
        # node and the system's output, and nothing about where the anchor's real counterpart is.
        rejected = {_key(x) for x in rec["truth"].get("rejected", [])}
        return bool(sys_set & rejected)
    return {_key(cp) for cp in rec["truth"]["counterparts"]} != sys_set


def failure_modes(records: list[dict]) -> dict:
    """Target 5. Challenge strata only. A RATE within a rigged population, never a precision."""
    out: dict[str, dict] = {}
    refused_all = []
    for r in records:
        stratum = r.get("stratum")
        if not stratum or not r.get("is_challenge"):
            continue
        if not _admits(r, "failure_modes"):
            refused_all.append(r)
            continue
        b = out.setdefault(stratum, {"n": 0, "mode_occurred": 0, "requires": r.get("challenge_requires")})
        b["n"] += 1
        b["mode_occurred"] += _mode_occurred(r)
    for b in out.values():
        b["rate"] = _rate(b["mode_occurred"], b["n"])
        b["NOT_a_precision"] = "base rate is rigged by construction (protocol §7)"
    return {"strata": out, "refused": _refusal_report(refused_all, "failure_modes")}


def _rate(k: int, n: int) -> float | None:
    return (k / n) if n else None


def evaluate(records: list[dict], verifier=None) -> dict:
    """Compute every target. `verifier` re-derives each coverage universe from the corpus.

    Round 6: without a verifier, NO record can establish `complete-in-document` or
    `complete-source-side`, because set equality between two lists in the same record cannot tell a
    real universe from a fabricated one. The refusal is the enforcement -- an evaluation run with no
    corpus reports the completeness metrics as empty and names the reason, rather than trusting the
    artifact to describe its own universe honestly.
    """
    validate_dataset(records)
    # Stamp a COPY. `mark_verified_universes` writes `universe_verified` into the coverage blocks,
    # and an authored record may not carry that flag -- so mutating the caller's data would make a
    # dataset that validates today fail validation after being evaluated once. Found by a contract
    # test that validated a mutated copy after an evaluation run.
    records = copy.deepcopy(records)
    unverified = mark_verified_universes(records, verifier) if verifier else {}
    uncertain = [r["anchor_id"] for r in records if r["truth"]["relation"] == "uncertain"]
    scored = [r for r in records if r["truth"]["relation"] != "uncertain"]
    return {
        "n_records": len(records),
        "n_uncertain_excluded": len(uncertain),
        "uncertain": uncertain,
        "universe_verification": {
            "ran": verifier is not None,
            "failed": unverified,
            "note": (
                None
                if verifier
                else "no verifier supplied: the eligible universes were never re-derived from the "
                "corpus, so NO record can establish complete-in-document or complete-source-side"
            ),
        },
        "candidate_recall": candidate_recall(scored),
        "ranking": ranking(scored),
        "assignment_per_anchor": assignment_per_anchor(scored),
        "collision_resolution": collision_resolution(scored),
        "diff_correctness": diff_correctness(scored),
        # v3: challenge records see EVERY record, `uncertain` included. The blanket exclusion was
        # right for the four metrics that need to know the anchor's counterpart set and wrong here:
        # a pairwise false-keep claim ("this proposed pair is not the same provision") has a
        # definite answer even when nobody has established where the anchor's real counterpart is.
        # Forcing `relation` to something other than `uncertain` in order to be scored would have
        # made the labeler assert a counterpart set they never determined.
        "failure_modes": failure_modes(records),
    }


def contract_check(result: dict) -> dict:
    """Can this dataset answer each question over a population adequate for that question?

    Round 3 raised the bar from "the code produced a number" to this. A metric with an empty
    admitted population reports NO -- which is the honest answer, and the one v1 could not give,
    because v1 computed four of the five over every record regardless of oracle.
    """
    # 3b (collision resolution) is DEFERRED from Study 2 and is deliberately absent: tiers A/B/C do
    # not collect reverse sweeps, so gating the study's start on a metric it does not intend to
    # produce would block work for a question nobody is asking yet.
    return {
        "1 candidate recall": result["candidate_recall"]["counterparts_total"] > 0,
        "2 ranking / MRR": result["ranking"]["n"] > 0,
        "3a per-anchor assignment": result["assignment_per_anchor"]["n"] > 0,
        "4 final diff correctness": result["diff_correctness"]["n"] > 0,
        "5 failure-mode rates": bool(result["failure_modes"]["strata"]),
    }


class ProvenanceError(RuntimeError):
    """The corpus or parser provenance could not be established, so nothing may be evaluated."""


def evaluate_study2_dataset(path: Path) -> dict:
    """THE canonical path for a real Study 2 dataset. Fails closed.

    `evaluate(records, verifier=...)` is right for the synthetic contract, but it puts the burden on
    a caller to remember the right callback -- and a caller who forgets gets a silently weaker
    result rather than an error. Real labels must not be consumable that way.

    This wires the one correct chain and refuses to proceed if any link cannot be established:

        dataset -> corpus resolver (corpus_roots) -> verify_coverage_against_corpus -> evaluate

    It raises rather than returning a degraded result when the corpus is absent or the parser
    revision does not match the study's frozen one, because "the metrics came out empty" and "the
    metrics could not be computed" look identical in a report and mean very different things.
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from corpus_roots import bill_versions  # noqa: PLC0415
    from study2_frame import parser_revision, verify_coverage_against_corpus  # noqa: PLC0415

    doc = json.loads(path.read_text())
    records = doc["records"]

    versions = bill_versions()
    if not versions:
        raise ProvenanceError(
            "no corpus is present, so no coverage universe can be re-derived. Completeness metrics "
            "would be silently empty; refusing to evaluate."
        )

    revision = parser_revision()
    declared = {
        b.get(f"{s}_parser_commit")
        for r in records
        for s, b in (
            ("target", r["truth"].get("coverage")),
            ("source", r["truth"].get("competition_coverage")),
        )
        if isinstance(b, dict)
    }
    if declared and declared != {revision}:
        raise ProvenanceError(
            f"dataset declares parser revision(s) {sorted(x[:12] for x in declared if x)} but the "
            f"checked-out parser is {revision[:12]}. Study 2 observations are valid only against "
            "the frozen revision they were produced under; re-derive them or check out that parser."
        )

    def resolve(bill: str, version: str):
        return versions.get(bill, {}).get(version)

    return evaluate(records, verifier=lambda recs: verify_coverage_against_corpus(recs, resolve))


def _synthetic_verifier(doc: dict):
    """A universe verifier for the contract fixture, which has no XML behind it.

    Real datasets use `study2_frame.verify_coverage_against_corpus`, which re-derives the eligible
    set from the frozen parse. The fixture publishes its true universes under `_synthetic_universes`
    and this checks records against THOSE -- so the fixture still cannot certify a universe it made
    up, which is the property under test.
    """
    truth_universes = doc.get("_synthetic_universes", {})
    revision = doc.get("_synthetic_parser_revision")

    def check_side(field, side, block, *, universe: bool) -> str | None:
        known = truth_universes.get(block.get(f"{side}_version"))
        if not known:
            return f"{field}: unknown {side} version"
        if known["source_sha256"] != block.get(f"{side}_source_sha256"):
            return f"{field}: {side}_source_sha256 mismatch"
        if block.get(f"{side}_parser_commit") != revision:
            # The check the round-6 verifier omitted entirely: `parser_commit` was a required field
            # whose value nothing compared against anything.
            return f"{field}: {side}_parser_commit is not the frozen revision"
        if not universe:
            return None
        if block.get("rule") not in known:
            return f"{field}: no universe published for rule {block.get('rule')!r}"
        if set(block.get("eligible_ordinals", [])) != set(known[block["rule"]]):
            return (
                f"{field}: stored universe has {len(set(block['eligible_ordinals']))} node(s), "
                f"the parse has {len(known[block['rule']])}"
            )
        return None

    def verify(records):
        bad = {}
        for rec in records:
            for field, side in (("coverage", "target"), ("competition_coverage", "source")):
                block = rec.get("truth", {}).get(field)
                if not isinstance(block, dict):
                    continue
                reason = check_side(field, side, block, universe=True)
                if reason is None and field == "competition_coverage":
                    # A reverse sweep carries TWO identities. The round-6 verifier checked only the
                    # source universe, leaving the contested target unverified -- which is what let
                    # a bare ordinal alias across documents.
                    reason = check_side(field, "target", block, universe=False)
                if reason:
                    bad[rec["anchor_id"]] = reason
        return bad

    return verify


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else FIXTURE
    doc = json.loads(path.read_text())
    records = doc["records"]
    print(f"dataset: {path}")
    result = evaluate(records, verifier=_synthetic_verifier(doc))
    print(json.dumps(result, indent=2))

    print()
    print("=" * 96)
    print("CONTRACT CHECK -- can each question be answered over an ADEQUATE population?")
    print("=" * 96)
    ok = contract_check(result)
    for k, v in ok.items():
        print(f"  {k:<28} {'YES' if v else 'NO -- no record has truth adequate for it'}")

    print()
    print("  Records refused per metric (truth cannot support what the metric assumes):")
    for metric in ("candidate_recall", "ranking", "assignment_per_anchor", "diff_correctness", "failure_modes"):
        node = result[metric]["refused"]
        if node["count"]:
            ids = ", ".join(a["anchor_id"] for a in node["anchors"])
            print(f"    {metric:<22} needs {node['requires']:<22} refused {node['count']}: {ids}")
    cr = result["collision_resolution"]
    if not cr["measurable"]:
        print()
        print("  COLLISION RESOLUTION IS NOT MEASURABLE on this dataset.")
        print(
            f"    {cr['groups_observed_in_dataset_without_source_side_truth']} contested target "
            "node(s) appear in the records, and none carries source-side competition truth."
        )
        print("    A contested node observed in the dataset is not evidence that every old")
        print("    provision claiming it has been found -- that needs the reverse sweep.")
    print()
    print("  Answering the gate question -- if labels are collected using the frozen sampling and")
    print("  oracle workflow, can every promised metric be computed over a population whose ground")
    print(f"  truth is adequate for that metric? {'YES' if all(ok.values()) else 'NO'}")


if __name__ == "__main__":
    main()
