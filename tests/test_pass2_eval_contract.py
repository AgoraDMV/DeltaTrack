"""The Pass 2 data contract: prove the schema can produce VALID metrics before humans label.

Five review rounds have each moved the bar for what "can produce" means:

* **R1** called the evaluator non-blocking. **R2** showed the risk is that the SCHEMA cannot produce
  the metrics, which is only discoverable by computing them.
* **R3** showed that computing them is not computing them VALIDLY: a region-local NONE and a
  suggestion-list NONE were both certifying the matcher's ``removed`` as correct, and nodes were
  joined on body text, which 33% of real documents share between two provisions.
* **R4** showed the strongest oracle could be satisfied by EFFORT rather than COVERAGE — a reviewer
  who searched a document and found nothing was granted "the counterpart set is complete".
* **R5** showed coverage was still proven by a COUNT rather than a SET (review node 42 twice, skip
  node 117, record 161/161), and that assignment was scored with truth collected in only one
  direction — a target-side sweep enumerates one anchor's counterparts and says nothing about which
  *other* old provisions claim the same node.

So the tests below pin two things. First, each metric's value on the synthetic fixture, which
contains at least one success and one failure of every shape so no metric can pass by being
vacuously 1.0. Second — the part that matters — each guard is shown to CHANGE THE ANSWER, by
re-running the metric with the guard removed or with the superseded rule restored. A guard that has
never moved a number cannot be distinguished from one that is not wired up.

These are contract tests, not result tests. Nothing here asserts a research finding.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import random
import shutil

import pytest

from tests.corpus_paths import PROJECT_ROOT

PROBES = PROJECT_ROOT / "docs" / "research" / "provision-matching" / "probes"
FIXTURE = PROBES / "fixtures" / "eval_contract_synthetic.json"


def _mod(name: str):
    spec = importlib.util.spec_from_file_location(f"_probe_{name}", PROBES / f"{name}.py")
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def evaluator():
    return _mod("eval_pass2")


@pytest.fixture(scope="module")
def schema():
    return _mod("pass2_schema")


@pytest.fixture(scope="module")
def frame():
    return _mod("study2_frame")


@pytest.fixture
def doc():
    return copy.deepcopy(json.loads(FIXTURE.read_text()))


@pytest.fixture
def records(doc):
    return doc["records"]


@pytest.fixture
def verifier(evaluator, doc):
    """The universe verifier the contract fixture stands in for a corpus with.

    Round 6: `set(reviewed) == set(eligible)` compares two lists inside one record and cannot tell a
    real universe from a fabricated one. Completeness now requires the universe to be re-derived
    from the frozen parse, so every evaluation that expects completeness must supply one of these.
    """
    return evaluator._synthetic_verifier(doc)


def _find(records, anchor_id):
    return next(r for r in records if r["anchor_id"] == anchor_id)


# --------------------------------------------------------------------------------------------
# the fixture itself
# --------------------------------------------------------------------------------------------


def test_fixture_validates(schema, records):
    schema.validate_dataset(records)


def test_fixture_covers_every_shape_the_design_must_handle(records):
    """A contract fixture that omits a shape proves nothing about that shape."""
    ids = {r["anchor_id"] for r in records}
    for shape in (
        "a1-one-to-one",
        "a2-none-global",
        "a3-one-to-many-outside-region",
        "a4-candidate-miss",
        "a5-ranking-miss",
        "a6-collision-winner",
        "a7-collision-loser",
        "a8-suggested-only",
        "a9-uncertain",
        "a10-challenge-absence",
        "a11-region-only-none",
        "a12-cross-region-escape",
        "a13-suggestion-list-none",
        "a14-duplicate-text-wrong-node",
        "a15-duplicate-text-right-node",
        "a16-incomplete-document-sweep",
        "a17-pairwise-false-keep",
        # round 5
        "a18-count-matches-set-does-not",
        "a19-target-complete-source-unknown",
    ):
        assert shape in ids, f"the contract fixture no longer covers {shape}"


def test_all_metrics_are_computable_and_non_degenerate(evaluator, records, verifier):
    r = evaluator.evaluate(records, verifier)

    cr = r["candidate_recall"]
    assert (cr["counterparts_found"], cr["counterparts_total"]) == (6, 10)
    assert cr["anchors_eligible"] == 9

    assert r["ranking"]["n"] == 6
    assert r["ranking"]["top1"] == pytest.approx(2 / 3)

    assert r["assignment_per_anchor"]["n"] == 12
    assert r["assignment_per_anchor"]["accuracy"] == pytest.approx(0.5)

    assert r["diff_correctness"]["n"] == 12
    assert r["diff_correctness"]["accuracy"] == pytest.approx(7 / 12)

    strata = r["failure_modes"]["strata"]
    assert strata["no-counterpart-anywhere"]["requires"] == "complete-in-document"
    assert strata["high-containment-pairwise"]["requires"] == "affirmed-negative"


# --------------------------------------------------------------------------------------------
# round 5: completeness is membership, not cardinality
# --------------------------------------------------------------------------------------------


def test_equal_counts_do_not_grant_completeness(evaluator, schema, records, verifier):
    """R5's central case. a18 reviews as many nodes as the universe holds, but reviews one twice
    and never reaches another. Under v3's `reviewed >= eligible_total` it was certified complete."""
    a18 = _find(records, "a18-count-matches-set-does-not")
    cov = a18["truth"]["coverage"]
    assert len(cov["reviewed_ordinals"]) == len(cov["eligible_ordinals"]), (
        "the adversarial case only tests anything if the CARDINALITIES match"
    )
    assert set(cov["reviewed_ordinals"]) != set(cov["eligible_ordinals"])
    assert not schema.establishes(a18["truth"], "complete-in-document")

    r = evaluator.evaluate(records, verifier)
    for metric in ("candidate_recall", "assignment_per_anchor", "diff_correctness"):
        refused = {a["anchor_id"] for a in r[metric]["refused"]["anchors"]}
        assert "a18-count-matches-set-does-not" in refused, metric


def test_the_superseded_count_rule_would_have_admitted_it(records):
    """Prove the guard changes the answer, by running the rule it replaced."""
    cov = _find(records, "a18-count-matches-set-does-not")["truth"]["coverage"]
    v3_complete = len(cov["reviewed_ordinals"]) >= len(cov["eligible_ordinals"])
    v4_complete = set(cov["reviewed_ordinals"]) == set(cov["eligible_ordinals"])
    assert v3_complete and not v4_complete, (
        "if the count rule no longer admits this record, the membership guard is untested"
    )


def test_duplicates_cannot_inflate_coverage(evaluator, schema, records, verifier):
    """`reviewed` longer than `eligible` through repetition must not grant completeness either."""
    bad = copy.deepcopy(records)
    cov = _find(bad, "a1-one-to-one")["truth"]["coverage"]
    cov["reviewed_ordinals"] = [cov["eligible_ordinals"][0]] * (len(cov["eligible_ordinals"]) + 5)
    assert not schema.establishes(_find(bad, "a1-one-to-one")["truth"], "complete-in-document")
    r = evaluator.evaluate(bad, verifier)
    assert "a1-one-to-one" in {a["anchor_id"] for a in r["diff_correctness"]["refused"]["anchors"]}


def test_reviewing_something_outside_the_universe_is_rejected(schema, records):
    """A review of a node the rule does not admit cannot count toward covering what it does."""
    bad = copy.deepcopy(records)
    _find(bad, "a1-one-to-one")["truth"]["coverage"]["reviewed_ordinals"].append(99999)
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "outside the eligible universe" in str(exc.value)


def test_coverage_must_name_the_parse_it_was_derived_from(schema, records):
    """A coverage set from one document must not certify completeness over another."""
    bad = copy.deepcopy(records)
    del _find(bad, "a1-one-to-one")["truth"]["coverage"]["target_source_sha256"]
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "target_source_sha256" in str(exc.value)


def test_exact_set_coverage_grants_completeness(evaluator, records, verifier):
    """The mirror: the guards are about membership and provenance, not about disliking records.

    Asserted through `evaluate` rather than `establishes` directly, because completeness now needs
    the universe stamped by verification -- which is the point of round 6.
    """
    a1 = _find(records, "a1-one-to-one")
    cov = a1["truth"]["coverage"]
    assert set(cov["reviewed_ordinals"]) == set(cov["eligible_ordinals"])
    r = evaluator.evaluate(records, verifier)
    refused = {a["anchor_id"] for a in r["diff_correctness"]["refused"]["anchors"]}
    assert "a1-one-to-one" not in refused


# --------------------------------------------------------------------------------------------
# round 5: assignment truth has a direction
# --------------------------------------------------------------------------------------------


def test_collision_resolution_needs_source_side_truth(evaluator, records, verifier):
    """a19 is document-complete on the TARGET side and its counterpart is a contested node. That
    does not establish which other OLD provisions claim it, so its group is not scorable."""
    r = evaluator.evaluate(records, verifier)
    cr = r["collision_resolution"]
    assert cr["groups_with_source_side_truth"] == 1
    assert cr["groups_observed_in_dataset_without_source_side_truth"] >= 1
    assert cr["wrong"] == ["a15-duplicate-text-right-node"]


def test_removing_the_reverse_sweep_makes_collision_resolution_unmeasurable(evaluator, records, verifier):
    """Prove the requirement bites: without any `competition_coverage` the metric must report NOT
    MEASURABLE rather than scoring the groups it can see in the dataset."""
    stripped = copy.deepcopy(records)
    for rec in stripped:
        rec["truth"].pop("competition_coverage", None)
        rec["system"].pop("competition_claimants", None)
    after = evaluator.evaluate(stripped, verifier)["collision_resolution"]
    assert after["measurable"] is False
    assert after["accuracy"] is None
    assert "competition_coverage" in after["why_not_measurable"]
    assert after["groups_observed_in_dataset_without_source_side_truth"] >= 2, (
        "contested nodes are still visible in the dataset -- that visibility is exactly what must "
        "NOT be mistaken for evidence that every claimant has been found"
    )


def test_per_anchor_assignment_is_separate_and_still_measurable(evaluator, records, verifier):
    """The per-anchor question needs only target-side truth, so stripping the reverse sweep must
    leave it untouched. If the two moved together they would not be separate estimands."""
    before = evaluator.evaluate(records, verifier)["assignment_per_anchor"]
    stripped = copy.deepcopy(records)
    for rec in stripped:
        rec["truth"].pop("competition_coverage", None)
        rec["system"].pop("competition_claimants", None)
    after = evaluator.evaluate(stripped, verifier)["assignment_per_anchor"]
    assert before["n"] == after["n"] and before["accuracy"] == after["accuracy"]


def test_a_reverse_sweep_must_come_from_the_anchors_own_parse(schema, records):
    bad = copy.deepcopy(records)
    _find(bad, "a15-duplicate-text-right-node")["truth"]["competition_coverage"]["source_source_sha256"] = "f" * 64
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "different parse" in str(exc.value)


def test_a_reverse_sweep_must_record_the_systems_claimants(schema, records):
    """Both sides of the comparison are source-side ordinals. Deriving the system's side from
    whichever anchors happen to be sampled is the defect this replaces."""
    bad = copy.deepcopy(records)
    del _find(bad, "a15-duplicate-text-right-node")["system"]["competition_claimants"]
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "competition_claimants" in str(exc.value)


# --------------------------------------------------------------------------------------------
# node identity (rounds 3-4), re-pinned under v4
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metric, extract",
    [
        ("candidate_recall", lambda r: r["candidate_recall"]["counterparts_found"]),
        ("ranking", lambda r: r["ranking"]["top1"]),
    ],
)
def test_a_content_hash_join_would_corrupt_this_metric(evaluator, schema, records, metric, extract, verifier):
    """Restore the pre-R3 join: the two boilerplate-identical target nodes collapse and the metrics
    move in the OPTIMISTIC direction."""
    real = extract(evaluator.evaluate(records, verifier))
    original = schema.observation_id
    try:
        schema.observation_id = lambda ref: (ref["bill"], ref["version"], ref["text_sha256"])
        evaluator.observation_id = schema.observation_id
        collapsed = extract(evaluator.evaluate(records, verifier))
    finally:
        schema.observation_id = original
        evaluator.observation_id = original
    assert collapsed > real, f"{metric}: a content-hash join must score better on this fixture"


def test_identity_collision_is_caught_even_when_the_text_also_matches(schema, records):
    bad = copy.deepcopy(records)
    a14 = _find(bad, "a14-duplicate-text-wrong-node")
    a15 = _find(bad, "a15-duplicate-text-right-node")
    a15["truth"]["counterparts"][0]["node_ordinal"] = a14["truth"]["counterparts"][0]["node_ordinal"]
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "observation id collision" in str(exc.value)


# --------------------------------------------------------------------------------------------
# round 5: sampling inclusion probabilities
# --------------------------------------------------------------------------------------------


def test_quota_allocation_is_hand_computable(frame):
    """Equal base share, remainder by seeded shuffle, capped at each bill's supply."""
    rng = random.Random(0)
    q = frame._allocate_quota({"A": 10, "B": 80}, 3, rng)
    assert sum(q.values()) == 3
    assert all(q[b] <= s for b, s in {"A": 10, "B": 80}.items())

    rng = random.Random(0)
    q = frame._allocate_quota({"A": 2, "B": 50, "C": 50}, 9, rng)
    assert sum(q.values()) == 9
    assert q["A"] == 2, "a bill is capped at its supply and the surplus redistributed"


def test_every_bill_can_be_drawn_even_when_fewer_regions_than_bills(frame):
    """R4's draw iterated bills in sorted order, so a 2-region request over 4 bills could only ever
    touch the two alphabetically first. Every stratum must have positive probability."""
    seen = set()
    for seed in range(60):
        q = frame._allocate_quota({"A": 5, "B": 5, "C": 5, "D": 5}, 2, random.Random(seed))
        seen |= {b for b, k in q.items() if k}
    assert seen == {"A", "B", "C", "D"}, f"these bills were never drawable: {{'A','B','C','D'}} - {seen}"


def test_recorded_inclusion_probability_matches_the_realised_quota(frame):
    """P(region in bill b) = quota[b] / drawable[b]. Recorded, and re-derivable from the fields the
    draw persists -- the R4 code recorded one corpus-wide figure that was wrong in both directions."""
    drawn = frame.draw_study2_sample(n_regions=6, seed=3, anchors_per_region=4)
    quota, supply = drawn["quota_by_bill"], drawn["drawable_by_bill"]
    for bill, p in drawn["p_region_given_quota_by_bill"].items():
        assert p == pytest.approx(quota.get(bill, 0) / supply[bill])
    for a in drawn["selected_anchors"]:
        assert a["p_inclusion_given_quota"] == pytest.approx(a["p_region_given_quota"] * a["p_within_region"])
        assert 0 < a["p_inclusion_given_quota"] <= 1


def test_the_old_single_corpus_wide_probability_would_have_been_wrong(frame):
    """The superseded formula, run against the corrected one on the real frame."""
    drawn = frame.draw_study2_sample(n_regions=6, seed=3, anchors_per_region=4)
    old_p = len(drawn["selected_regions"]) / drawn["frame"]["regions_drawable"]
    per_bill = {b: p for b, p in drawn["p_region_given_quota_by_bill"].items() if p > 0}
    assert any(abs(p - old_p) > 1e-9 for p in per_bill.values()), (
        "if every stratum's probability equalled the corpus-wide figure, the fix would be untested"
    )


def test_a_draw_is_reproducible_and_records_its_inputs(frame):
    a = frame.draw_study2_sample(n_regions=4, seed=7, anchors_per_region=5)
    b = frame.draw_study2_sample(n_regions=4, seed=7, anchors_per_region=5)
    assert a["selected_regions"] == b["selected_regions"]
    assert a["selected_anchors"] == b["selected_anchors"]
    assert a["corpus_digest"] and a["seed"] == 7


def test_the_sampling_frame_never_imports_the_matcher():
    """R4's second criticism, as a standing gate."""
    tree = ast.parse((PROBES / "study2_frame.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("diff_bill" in m for m in imported), f"study2_frame imports the matcher: {sorted(imported)}"


# --------------------------------------------------------------------------------------------
# carried forward from rounds 3-4
# --------------------------------------------------------------------------------------------


def test_bounded_search_negatives_are_refused_by_the_completeness_metrics(evaluator, records, verifier):
    r = evaluator.evaluate(records, verifier)
    for metric in ("candidate_recall", "assignment_per_anchor", "diff_correctness"):
        refused = {a["anchor_id"] for a in r[metric]["refused"]["anchors"]}
        assert {"a11-region-only-none", "a13-suggestion-list-none"} <= refused, metric


def test_ranking_still_admits_bounded_oracles(evaluator, records, verifier):
    r = evaluator.evaluate(records, verifier)
    assert r["ranking"]["refused"]["count"] == 0
    assert r["ranking"]["refused"]["requires"] == "affirmed-positive"


def test_a_pairwise_false_keep_needs_no_document_completeness(evaluator, schema, records, verifier):
    a17 = _find(records, "a17-pairwise-false-keep")
    assert schema.establishes(a17["truth"], "affirmed-negative")
    assert not schema.establishes(a17["truth"], "complete-in-document")
    stratum = evaluator.evaluate(records, verifier)["failure_modes"]["strata"]["high-containment-pairwise"]
    assert (stratum["mode_occurred"], stratum["n"]) == (1, 1)


def test_forced_choice_cannot_establish_anything(schema, evaluator, records, verifier):
    assert not schema.establishes(
        {"oracles": ["document-exhaustive"], "judgment_mode": "forced-choice"}, "affirmed-positive"
    )
    forced = copy.deepcopy(records)
    for rec in forced:
        rec["truth"]["judgment_mode"] = "forced-choice"
    after = evaluator.evaluate(forced, verifier)
    assert after["ranking"]["n"] == 0
    assert after["candidate_recall"]["counterparts_total"] == 0
    assert after["failure_modes"]["strata"] == {}


def test_a_stratum_may_not_mix_truth_requirements(schema, records):
    bad = copy.deepcopy(records)
    _find(bad, "a17-pairwise-false-keep")["stratum"] = "no-counterpart-anywhere"
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "one claim" in str(exc.value)


@pytest.mark.parametrize(
    "mutate, expect",
    [
        (lambda rec: rec["truth"]["counterparts"][0].pop("found_via"), "found"),
        (lambda rec: rec["truth"].pop("region_id"), "region"),
        (lambda rec: rec["anchor"].pop("source_sha256"), "source_sha256"),
        (lambda rec: rec["anchor"].pop("node_ordinal"), "node_ordinal"),
        (lambda rec: rec["anchor"].update(node_ordinal="x"), "node_ordinal"),
        (lambda rec: rec["candidates"][0].pop("retrievers"), "retriever"),
        (lambda rec: rec["truth"].pop("change_type"), "change_type"),
        (lambda rec: rec["truth"].pop("oracles"), "oracles"),
        (lambda rec: rec["truth"].pop("judgment_mode"), "judgment_mode"),
        (lambda rec: rec["truth"].pop("coverage"), "coverage"),
        (lambda rec: rec["truth"]["coverage"].update(rule="nodes-above-containment-0.3"), "coverage.rule"),
        (lambda rec: rec["truth"]["coverage"].update(eligible_ordinals=[]), "empty"),
    ],
)
def test_schema_rejects_a_record_that_cannot_support_its_metrics(schema, records, mutate, expect):
    bad = copy.deepcopy(records)
    mutate(_find(bad, "a1-one-to-one"))
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert expect in str(exc.value).lower()


def test_provenance_fields_are_present_on_every_node_reference(schema, records):
    for rec in records:
        refs = [
            rec["anchor"],
            *rec["truth"]["counterparts"],
            *rec["truth"].get("rejected", []),
            *rec["candidates"],
            *rec["system"]["assigned"],
        ]
        for ref in refs:
            for field in schema.PROVENANCE_FIELDS:
                assert field in ref, f"{rec['anchor_id']}: node ref missing {field}"


# --------------------------------------------------------------------------------------------
# round 6: the universe must come from the corpus, not from the record
# --------------------------------------------------------------------------------------------


def test_a_fabricated_universe_is_refused(evaluator, records, verifier):
    """R6's central case. a21 declares a one-node universe and reviews that one node, so
    `set(reviewed) == set(eligible)` holds perfectly -- with itself. The real document has 21."""
    a21 = _find(records, "a21-fabricated-universe")
    cov = a21["truth"]["coverage"]
    assert set(cov["reviewed_ordinals"]) == set(cov["eligible_ordinals"]), (
        "the adversarial case only tests anything if the record is internally consistent"
    )
    r = evaluator.evaluate(records, verifier)
    assert "a21-fabricated-universe" in r["universe_verification"]["failed"]
    for metric in ("candidate_recall", "assignment_per_anchor", "diff_correctness"):
        refused = {a["anchor_id"] for a in r[metric]["refused"]["anchors"]}
        assert "a21-fabricated-universe" in refused, metric


def test_set_equality_alone_would_have_admitted_the_fabrication(schema, records):
    """Prove the verification changes the answer, by running the rule it strengthens."""
    cov = _find(records, "a21-fabricated-universe")["truth"]["coverage"]
    assert set(cov["reviewed_ordinals"]) == set(cov["eligible_ordinals"]), (
        "v4's set-equality rule admits this record; if it stops doing so the guard is untested"
    )
    assert cov["rule"] in schema.DOCUMENT_COMPLETENESS_RULES


def test_without_a_verifier_no_record_can_claim_completeness(evaluator, records):
    """The strongest form of the contract: completeness needs the corpus, full stop.

    An evaluation run with no verifier cannot re-derive any universe, so it refuses every
    completeness metric and says why -- rather than trusting each record to describe its own
    universe honestly. Ranking is unaffected, because it needs only an affirmed positive.
    """
    r = evaluator.evaluate(records)
    assert r["universe_verification"]["ran"] is False
    assert "never re-derived" in r["universe_verification"]["note"]
    assert r["candidate_recall"]["counterparts_total"] == 0
    assert r["diff_correctness"]["n"] == 0
    assert r["assignment_per_anchor"]["n"] == 0
    assert r["collision_resolution"]["measurable"] is False
    assert r["ranking"]["n"] == 6, "ranking needs no completeness and must be unaffected"


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda c: c.update(eligible_ordinals=c["eligible_ordinals"][:1], reviewed_ordinals=c["eligible_ordinals"][:1]),
        lambda c: c.update(target_source_sha256="a" * 64),
        lambda c: c.update(target_version="9_nonexistent"),
        lambda c: c.update(rule="all-nodes-with-body"),
    ],
    ids=["truncated-universe", "wrong-source-hash", "unknown-version", "wrong-rule-output"],
)
def test_coverage_corruptions_are_rejected(evaluator, records, verifier, corrupt):
    """R6's required corruption matrix. Each mutation leaves the record internally consistent and
    is caught only by re-deriving the universe from the parse."""
    bad = copy.deepcopy(records)
    corrupt(_find(bad, "a1-one-to-one")["truth"]["coverage"])
    r = evaluator.evaluate(bad, verifier)
    refused = {a["anchor_id"] for a in r["diff_correctness"]["refused"]["anchors"]}
    assert "a1-one-to-one" in refused


def test_a_hand_set_verification_flag_is_rejected(schema, records):
    """The flag is the verifier's output, not an input -- allowing it restores self-certification."""
    bad = copy.deepcopy(records)
    _find(bad, "a1-one-to-one")["truth"]["coverage"]["universe_verified"] = True
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "universe_verified" in str(exc.value)


def test_only_all_nodes_may_establish_global_completeness(schema):
    """R6-3: `all-nodes-with-body` excludes ~8.5% of the document, and the evidence that the
    exclusion is harmless leaned on what the matcher pairs -- the object under evaluation."""
    assert schema.DOCUMENT_COMPLETENESS_RULES == ("all-nodes",)
    assert "all-nodes-with-body" in schema.COVERAGE_RULES, "still valid for region-scoped work"


def test_evaluation_does_not_mutate_the_caller_records(evaluator, schema, records, verifier):
    """Verification stamps a copy. Otherwise a dataset that validates would fail validation after
    being evaluated once, because an authored record may not carry `universe_verified`."""
    evaluator.evaluate(records, verifier)
    schema.validate_dataset(records)


# --------------------------------------------------------------------------------------------
# round 6: collision target identity
# --------------------------------------------------------------------------------------------


def test_a_reverse_sweep_carries_a_full_target_identity(records):
    """R6-4: a bare `target_ordinal` aliases across documents -- ordinal 602 exists in every
    version of every bill."""
    comp = _find(records, "a15-duplicate-text-right-node")["truth"]["competition_coverage"]
    for field in ("target_version", "target_source_sha256", "target_parser_commit", "target_ordinal"):
        assert field in comp, f"competition_coverage must scope its target: missing {field}"
    assert comp["target_source_sha256"] != comp["source_source_sha256"]


def test_a_reverse_sweep_may_not_name_one_document_as_both_sides(schema, records):
    bad = copy.deepcopy(records)
    comp = _find(bad, "a15-duplicate-text-right-node")["truth"]["competition_coverage"]
    comp["target_source_sha256"] = comp["source_source_sha256"]
    comp["target_version"] = comp["source_version"]
    with pytest.raises(schema.SchemaError) as exc:
        schema.validate_dataset(bad)
    assert "same document as both source and target" in str(exc.value)


# --------------------------------------------------------------------------------------------
# round 6: unconditional inclusion probability
# --------------------------------------------------------------------------------------------


def test_unconditional_probability_matches_exhaustive_enumeration(frame):
    """R6-2. `k_b / n_b` is conditional on the realised quota, and quota allocation is random.

    Enumerated on three bills of two regions each requesting one region: the true unconditional
    probability is 1/6, while the conditional figure is 1/2 for whichever bill won the quota.
    """
    sizes = {"A": 2, "B": 2, "C": 2}
    hits = {f"{b}{i}": 0 for b in sizes for i in range(2)}
    trials = 6000
    for seed in range(trials):
        rng = random.Random(seed)
        quota = frame._allocate_quota(sizes, 1, rng)
        for b, k in quota.items():
            if k:
                for r in rng.sample([f"{b}{i}" for i in range(sizes[b])], k):
                    hits[r] += 1
    for r, c in hits.items():
        assert abs(c / trials - 1 / 6) < 0.02, f"{r}: empirical {c / trials:.4f} is not ~1/6"

    e_quota, method = frame.expected_quota(sizes, 1)
    assert method == "closed-form"
    for b in sizes:
        assert e_quota[b] / sizes[b] == pytest.approx(1 / 6)


def test_capping_uses_exact_enumeration_not_the_closed_form(frame):
    """When a bill can be capped the closed form does not apply, so the expectation is enumerated
    over every permutation of the remainder shuffle rather than approximated."""
    e_quota, method = frame.expected_quota({"A": 2, "B": 50, "C": 50}, 9)
    assert method == "exact-enumeration"
    assert e_quota["A"] == pytest.approx(2.0), "a bill capped at its supply has expectation = supply"
    assert e_quota["B"] == pytest.approx(3.5)


def test_the_draw_records_both_probabilities_and_names_them(frame):
    """Semantic honesty: a conditional probability must not be labelled an inclusion probability."""
    drawn = frame.draw_study2_sample(n_regions=6, seed=3, anchors_per_region=4)
    assert drawn["expected_quota_method"] in ("closed-form", "exact-enumeration")
    for a in drawn["selected_anchors"]:
        assert a["p_inclusion_given_quota"] == pytest.approx(a["p_region_given_quota"] * a["p_within_region"])
        assert a["p_inclusion_unconditional"] == pytest.approx(a["p_region_unconditional"] * a["p_within_region"])


# --------------------------------------------------------------------------------------------
# round 6 follow-up: parser provenance, and the reverse-sweep target key
# --------------------------------------------------------------------------------------------


def test_a_wrong_parser_commit_cannot_establish_completeness(evaluator, records, verifier):
    """The follow-up's central case.

    Same XML, same eligible/reviewed ordinals, only `target_parser_commit` changed to another
    well-formed value. Before the fix this still yielded `universe_verified=True` and the record was
    admitted -- `parser_commit` was a required field whose value nothing compared against anything,
    in a programme whose round-2 finding was that a parser change silently invalidated three
    observations.
    """
    bad = copy.deepcopy(records)
    cov = _find(bad, "a1-one-to-one")["truth"]["coverage"]
    cov["target_parser_commit"] = "b" * 40
    r = evaluator.evaluate(bad, verifier)

    assert "a1-one-to-one" in r["universe_verification"]["failed"]
    assert "parser_commit" in r["universe_verification"]["failed"]["a1-one-to-one"]
    for metric in ("candidate_recall", "assignment_per_anchor", "diff_correctness"):
        refused = {a["anchor_id"] for a in r[metric]["refused"]["anchors"]}
        assert "a1-one-to-one" in refused, metric


def test_the_parser_revision_is_derived_from_the_code_not_declared(frame, tmp_path, monkeypatch):
    """It must be a function of the parser source, so it cannot be a decorative constant.

    Hashing the transitive `deltatrack.*` imports of `bill_tree` is deliberately over-broad: a
    module that cannot affect node emission may still move the revision. That direction costs a
    re-verification; the other direction silently certifies a universe derived by different code.

    The mutation runs against a COPY of the checkout, never the checkout itself (#686). This test
    used to append the probe line to the live `src/deltatrack/bill_tree.py` and restore it in a
    `finally`, which is unsafe for the same reason `tests/test_pdf_observation_identity.py` keeps
    its own mutations in a `package_copy`: the suite runs under `-n auto`, so another worker can
    read the tree mid-write. That module's `real_source_is_never_mutated` guard did exactly that
    and reddened `fast-tests` on a branch touching no source at all. A worker killed between the
    write and the restore would also leave a probe line in tracked source.

    `parser_revision` resolves modules under `REPO / "src"`, so repointing that one name runs the
    REAL revision walk against a tree this test may edit freely. Nothing here re-implements the
    walk; a test-only replica would prove the replica correct and say nothing about the probe.

    The copy is proved faithful BEFORE it is mutated: a mutation control measuring a different
    tree would report agreement while testing nothing, which is the failure the assertion between
    the copy and the first `!=` exists to prevent.
    """
    rev = frame.parser_revision()
    assert len(rev) == 64 and rev == frame.parser_revision(), "must be a stable content hash"

    checkout = tmp_path / "checkout"
    shutil.copytree(PROJECT_ROOT / "src", checkout / "src", ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(frame, "REPO", checkout)
    assert frame.parser_revision() == rev, (
        "the copied tree does not reproduce the checkout's revision, so every assertion below "
        "would be measuring a different parser than the one under evaluation"
    )

    parser = checkout / "src" / "deltatrack" / "bill_tree.py"
    src = parser.read_bytes()
    try:
        parser.write_bytes(src + b"\n# provenance probe\n")
        assert frame.parser_revision() != rev, "editing the parser must change the revision"
    finally:
        parser.write_bytes(src)
    assert frame.parser_revision() == rev, "restoring the parser must restore the revision"


def test_reverse_truth_for_one_target_cannot_certify_another(evaluator, records, verifier):
    """The aliasing case: document A ordinal 73 and document B ordinal 73 are different nodes.

    The round-6 evaluator keyed proven groups on the ANCHOR's source hash plus a bare target
    ordinal, so reverse truth collected for A:73 was looked up for B:73. The key is now the
    target's own observation identity.
    """
    a15 = _find(records, "a15-duplicate-text-right-node")
    comp = a15["truth"]["competition_coverage"]

    before = evaluator.evaluate(records, verifier)["collision_resolution"]
    assert before["groups_with_source_side_truth"] == 1

    # Point the reverse sweep at a DIFFERENT target document, same ordinal.
    moved = copy.deepcopy(records)
    other = _find(moved, "a15-duplicate-text-right-node")["truth"]["competition_coverage"]
    other["target_source_sha256"] = "c" * 64
    after = evaluator.evaluate(moved, verifier)

    assert "a15-duplicate-text-right-node" in after["universe_verification"]["failed"], (
        "a reverse sweep naming a target document that does not verify must be rejected outright"
    )
    assert after["collision_resolution"]["groups_with_source_side_truth"] == 0, (
        "truth collected for one target must not remain usable once the target identity changes"
    )
    assert comp["target_ordinal"] == other["target_ordinal"], "the ordinal is unchanged; only the document moved"


def test_collision_resolution_is_marked_deferred_and_unvalidated(evaluator, records, verifier):
    """It is out of Study 2 scope, and the output says so rather than implying validation."""
    cr = evaluator.evaluate(records, verifier)["collision_resolution"]
    assert cr["study2_scope"] == "deferred"
    assert "not fully validated" in cr["validation_status"]


def test_collision_resolution_does_not_gate_the_other_tiers(evaluator, records, verifier):
    """Tiers A/B/C collect no reverse sweeps, so gating the study on 3b would block work for a
    question nobody is asking yet."""
    ok = evaluator.contract_check(evaluator.evaluate(records, verifier))
    assert "3b collision resolution" not in ok
    assert set(ok) == {
        "1 candidate recall",
        "2 ranking / MRR",
        "3a per-anchor assignment",
        "4 final diff correctness",
        "5 failure-mode rates",
    }


def test_the_canonical_real_dataset_path_fails_closed(evaluator, tmp_path, doc):
    """Real labels must not be consumable by a caller who forgets the verifier.

    `evaluate_study2_dataset` wires corpus resolver -> verification -> evaluate and RAISES when
    provenance cannot be established, because "the metrics came out empty" and "the metrics could
    not be computed" look identical in a report and mean very different things.
    """
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(evaluator.ProvenanceError) as exc:
        evaluator.evaluate_study2_dataset(path)
    # the synthetic fixture's parser revision is not the checked-out parser's
    assert "parser" in str(exc.value).lower() or "corpus" in str(exc.value).lower()
