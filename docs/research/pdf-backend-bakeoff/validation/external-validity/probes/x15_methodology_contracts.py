"""x15 -- test the frozen methodology contracts. DESIGN MATERIAL.

NOT CONFIRMATORY. Synthetic only. No PDF is opened, no architecture is run, nothing scored.

    A28.1/A28.2  the 4.5 adequacy count and state machine, every branch
    A28.3        canonical pre-blinding stimulus identity; sampling must NOT depend on
                 blind ids
    A28.4        frozen renderer scale, 300 dpi primary / 330 dpi R1 repeat
    A27.7        domain-separated deterministic ranking
    A30.4        the P-head adequacy restriction, executable rather than a caller obligation
    A30.5        blind-ID uniqueness over the REALIZED stimulus set, with collision injection
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))

import methodology_contracts as MC  # noqa: E402

OUT = EV / "results" / "x15_methodology_contracts.json"
ROWS: list[dict] = []
FAILED: list[str] = []


def check(name, expected, observed, implication="") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "implication": implication})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


def key(doc, page, line, start_ngid):
    """An A27.1 source-position occurrence key, as amended by A30.1.

    The fourth component is the ABSOLUTE `start_ngid`, never an ordinal among the anchors an
    arm emitted. `x16_occurrence_identity.py` proves the derivation through the production
    path; here it only has to be an opaque distinct value.
    """
    return (doc, page, (page, line), start_ngid)


def part_adequacy() -> None:
    # --- the state machine, every branch, thresholds unchanged
    cases = [
        ("4 strata, 5000 occurrences", 4, 5000, "INADEQUATE"),
        ("5 strata, 299 occurrences  (the overlap the table left undecided)", 5, 299, "INADEQUATE"),
        ("6 strata, 299 occurrences", 6, 299, "INADEQUATE"),
        ("8 strata, 299 occurrences", 8, 299, "INADEQUATE"),
        ("7 strata, 300 occurrences  (matched NO row before)", 7, 300, "LIMITED"),
        ("8 strata, 799 occurrences  (matched NO row before)", 8, 799, "LIMITED"),
        ("5 strata, 800 occurrences", 5, 800, "LIMITED"),
        ("6 strata, 5000 occurrences", 6, 5000, "LIMITED"),
        ("7 strata, 800 occurrences", 7, 800, "GENERALISABLE"),
        ("8 strata, 5000 occurrences", 8, 5000, "GENERALISABLE"),
    ]
    bad = [f"{n}: expected {w} got {MC.adequacy(s, o)}" for n, s, o, w in cases if MC.adequacy(s, o) != w]
    check("4.5 state machine matches the frozen rows on every branch", [], bad)
    seen = sorted({MC.adequacy(s, o) for _n, s, o, _w in cases})
    check("...and all three states are reachable", ["GENERALISABLE", "INADEQUATE", "LIMITED"], seen)

    # --- the space is TOTAL: no (strata, occurrences) pair falls through
    holes = [
        (s, o)
        for s in range(0, 9)
        for o in (0, 299, 300, 799, 800, 5000)
        if MC.adequacy(s, o) not in ("INADEQUATE", "LIMITED", "GENERALISABLE")
    ]
    check("no (strata, occurrences) pair is unclassified", [], holes)

    # --- the union count
    a, b, c = key("d", 1, 3, 0), key("d", 1, 9, 0), key("d", 2, 4, 0)
    check("one physical occurrence emitted by BOTH arms counts once", 1, MC.adequacy_occurrences([a], [a]))
    check("an occurrence emitted by ONE arm still counts", 2, MC.adequacy_occurrences([a], [b]))
    check(
        "one arm missing an occurrence cannot remove the other arm's key",
        MC.adequacy_occurrences([a, b, c], [a, b, c]),
        MC.adequacy_occurrences([a, b, c], []),
        "an arm's own failure must never shrink the adequacy denominator",
    )
    # two occurrences on ONE neutral line: the real measured pair from 114-hr-2029 p66:12,
    # a `section` at ngid 617 and its inline `subsection` at ngid 627
    check(
        "two occurrences on ONE neutral line stay distinct",
        2,
        MC.adequacy_occurrences([key("d", 1, 3, 617), key("d", 1, 3, 627)], []),
    )
    # --- kind AND population restriction (A30.4)
    keyed = [
        (key("d", 1, 1, 10), "account", "P-head"),
        (key("d", 1, 2, 20), "agency", "P-head"),
        (key("d", 1, 3, 30), "grouping", "P-head"),
        (key("d", 1, 4, 40), "title", "P-head"),
        (key("d", 1, 5, 50), "section", "P-head"),
        (key("d", 1, 6, 60), "subsection", "P-head"),
    ]
    check(
        "only account/agency/grouping contribute to adequacy",
        3,
        len(MC.filter_keys(keyed)),
        "title/section/division must not inflate the denominator the frozen quantity is compared against",
    )

    # --- A30.4 NEGATIVE CONTROL: P-robust adequacy-kind keys must not move the count.
    # Before A30.4 `filter_keys` filtered on kind alone, so every one of these would have
    # been counted and the denominator would have grown silently.
    baseline_keys = MC.filter_keys(keyed)
    baseline = MC.adequacy_occurrences(baseline_keys, [])
    intruders = [
        (key("robust", 9, i, 700 + i), kind, "P-robust")
        for i, kind in enumerate(["account", "agency", "grouping"] * 40)
    ]
    polluted = MC.filter_keys(keyed + intruders)
    check(
        "adding 120 P-robust account/agency/grouping keys does not change adequacy_occurrences",
        baseline,
        MC.adequacy_occurrences(polluted, []),
        "the frozen P-head clause is now a gate rather than a caller obligation",
    )
    check(
        "...and the intruders really were adequacy-KIND keys, so the control is not vacuous",
        120,
        len({k for k, kind, _pop in intruders if kind in MC.ADEQUACY_KINDS}),
    )
    check(
        "a P-robust key is excluded even when it is the ONLY input",
        0,
        len(MC.filter_keys([(key("robust", 9, 1, 5), "account", "P-robust")])),
    )


def part_determinism() -> None:
    regions = [MC.base_stimulus_identity(f"sha{d}", p, r) for d in range(2) for p in range(1, 4) for r in range(3)]

    # --- reproducible and order-independent
    check("selection is reproducible", MC.select("cframe-select", regions, 5), MC.select("cframe-select", regions, 5))
    check(
        "selection does not depend on input listing order",
        MC.select("cframe-select", regions, 5),
        MC.select("cframe-select", list(reversed(regions)), 5),
    )
    # --- domain separation
    check(
        "different purposes select differently",
        True,
        MC.select("cframe-audit", regions, 5) != MC.select("r1-repeat", regions, 5),
        "domain separation, so one namespace's draw cannot leak into another's",
    )
    # --- canonical serialization: a tuple and a list are the same identity
    check(
        "canonical form is stable across tuple/list spelling",
        MC.rank_key("p", ("region", "sha", 1, 2)),
        MC.rank_key("p", ["region", "sha", 1, 2]),
    )

    # --- THE NEGATIVE CONTROL: sampling must not depend on the blind-id scheme.
    finals = [MC.r1_repeat_identity(r) for r in regions[:4]] + regions
    before = {
        "audit": MC.select("cframe-audit", regions, 4),
        "r1": MC.select("r1-repeat", regions, 3),
        "order": MC.order("blind-order", finals),
    }
    real_blind = MC.blind_id
    try:
        MC.blind_id = lambda ident: "SCHEME2-" + real_blind(ident)[::-1]  # a totally different alias scheme
        after = {
            "audit": MC.select("cframe-audit", regions, 4),
            "r1": MC.select("r1-repeat", regions, 3),
            "order": MC.order("blind-order", finals),
        }
    finally:
        MC.blind_id = real_blind
    check(
        "changing the blind-ID scheme changes NO selection and NO presentation rank",
        before,
        after,
        "sampling ranks canonical pre-blinding identities; the blind id is an alias only",
    )
    check(
        "...and the alias itself did change, so the control is not vacuous",
        True,
        real_blind(regions[0]) != ("SCHEME2-" + real_blind(regions[0])[::-1]),
    )
    check("blind ids are unique across distinct stimuli", len(finals), len({real_blind(f) for f in finals}))

    # --- A30.5: uniqueness over the REALIZED set, and a collision must ABORT the build.
    check(
        "the realized-set check passes on a clean stimulus set",
        len(finals),
        len(MC.assert_realized_blind_ids_unique(finals)),
    )

    def raised(fn):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - the class IS the assertion
            return type(exc).__name__
        return None

    # COLLISION INJECTION. Without this the check has never once produced a positive
    # result, so a green run could not distinguish "no collision" from "cannot detect one".
    collided = MC.blind_id
    try:
        MC.blind_id = lambda ident: "CONSTANT"
        outcome = raised(lambda: MC.assert_realized_blind_ids_unique(finals))
    finally:
        MC.blind_id = collided
    check(
        "an injected blind-ID collision aborts the build",
        "BlindIdCollision",
        outcome,
        "no overwrite, merge, last-write-wins, salt or re-roll is permitted",
    )
    check(
        "a duplicated stimulus identity aborts the build",
        "DuplicateStimulusIdentity",
        raised(lambda: MC.assert_realized_blind_ids_unique([finals[0], finals[0]])),
    )
    check(
        "...and the collision injection did not leak past its scope",
        len(finals),
        len(MC.assert_realized_blind_ids_unique(finals)),
    )


def part_dpi() -> None:
    check("primary stimuli render at exactly 300 dpi", 300, MC.required_dpi(False))
    check("R1 repeats render at exactly 330 dpi", 330, MC.required_dpi(True))
    check("the R1 scale is the frozen 300 x 1.10", 330, int(round(300 * 1.10)))
    check(
        "primary and repeat scales differ, so R1 is a re-render and not a cache hit",
        True,
        MC.required_dpi(True) != MC.required_dpi(False),
    )


def refusal(fn):
    """The refusal class a callable raises, or None if it returned. Never swallows the reason."""
    try:
        fn()
    except MC.BootstrapInputError as exc:
        return exc.reason
    return None


def unsorted_resample(statistic_id, records, replicate):
    """The A37.2 COUNTERFACTUAL: the identical draw WITHOUT canonical sorting.

    Deliberately a separate implementation rather than a monkeypatch, so control 19 exercises
    an independent counterfactual instead of asking the production helper about itself. This is
    what withdrawn A29 measured as defective.
    """
    n = len(records)
    return [records[MC.bootstrap_draw_index(statistic_id, replicate, d, n)] for d in range(n)]


def part_bootstrap() -> dict:
    """A37 -- the supplementary document bootstrap. SYNTHETIC only, and non-gating."""
    docs = [(f"doc-{i}", i % 3 == 0) for i in range(9)]  # 3 of 9 events
    reversed_docs = list(reversed(docs))
    permutations = [
        docs,
        reversed_docs,
        [docs[i] for i in (4, 0, 8, 2, 6, 1, 7, 3, 5)],
        [docs[i] for i in (7, 3, 1, 8, 0, 5, 2, 6, 4)],
    ]

    base = MC.section8_document_bootstrap(docs)
    again = MC.section8_document_bootstrap(docs)
    check(
        "1. identical inputs reproduce resample 0 exactly",
        MC.bootstrap_resample(MC.SECTION8_DOCUMENT_DISCORDANCE, MC.canonical_document_vector(docs), 0),
        MC.bootstrap_resample(MC.SECTION8_DOCUMENT_DISCORDANCE, MC.canonical_document_vector(docs), 0),
        "the draw consults something other than the committed identity and the two ordinals",
    )
    check(
        "2. identical inputs reproduce the WHOLE result",
        base,
        again,
        "two runs of the same committed inputs print different intervals",
    )
    check(
        "3. REVERSED input order reproduces every resample",
        [
            MC.bootstrap_resample(MC.SECTION8_DOCUMENT_DISCORDANCE, MC.canonical_document_vector(docs), r)
            for r in range(5)
        ],
        [
            MC.bootstrap_resample(MC.SECTION8_DOCUMENT_DISCORDANCE, MC.canonical_document_vector(reversed_docs), r)
            for r in range(5)
        ],
        "canonical sorting is missing or ineffective, so the caller's listing order selects "
        "different documents -- the defect withdrawn A29 measured",
    )
    intervals = [MC.section8_document_bootstrap(p)["interval"] for p in permutations]
    check(
        "4. several permuted input orders give the IDENTICAL interval",
        [intervals[0]] * len(permutations),
        intervals,
        "the reported interval depends on how the caller happened to list its documents",
    )

    # 5. the statistic must be LIVE -- a different event pattern must be able to move it.
    all_events = [(f"doc-{i}", True) for i in range(9)]
    other = MC.section8_document_bootstrap(all_events)
    check(
        "5. a different event pattern CHANGES the interval, so the statistic is live",
        True,
        other["interval"] != base["interval"],
        "the interval is constant across event patterns, so it measures nothing and every "
        "reproducibility control above would pass on a dead quantity",
    )

    # 6. domain separation must be live too.
    vector = MC.canonical_document_vector(docs)
    other_id = ("section8", "document-heading-discordance", "P-robust")
    draws_frozen = [
        MC.bootstrap_draw_index(MC.SECTION8_DOCUMENT_DISCORDANCE, r, d, len(vector))
        for r in range(20)
        for d in range(len(vector))
    ]
    draws_other = [MC.bootstrap_draw_index(other_id, r, d, len(vector)) for r in range(20) for d in range(len(vector))]
    check(
        "6. changing the statistic identity CHANGES the draws, so domain separation is live",
        True,
        draws_frozen != draws_other,
        "two different statistics share a draw sequence, so the population component of the "
        "identity is decorative and a P-robust variant could silently reuse P-head's draws",
    )

    # 7 + 8 + 9 + 17. input refusals.
    check(
        "7. NEGATIVE -- a duplicate document identity REFUSES",
        MC.DUPLICATE_DOCUMENT_IDENTITY,
        refusal(lambda: MC.section8_document_bootstrap(docs + [("doc-3", True)])),
        "a repeated document is silently weighted twice, though the document is the "
        "independent unit (8.3, red-team #7)",
    )
    check(
        "8. NEGATIVE -- an empty document set REFUSES",
        MC.EMPTY_DOCUMENT_SET,
        refusal(lambda: MC.section8_document_bootstrap([])),
        "N = 0 produces a division by zero or a vacuous interval instead of refusing",
    )
    check(
        "9. NEGATIVE -- a non-boolean event REFUSES",
        MC.NON_BOOLEAN_EVENT,
        refusal(lambda: MC.section8_document_bootstrap([("doc-a", 1), ("doc-b", 0)])),
        "a bare 0/1 is accepted -- it would work silently in sum() because bool subclasses "
        "int, so the wrong type would never be seen",
    )
    headings = [(f"doc-{i // 4}", i % 5 == 0) for i in range(12)]  # 3 documents, 4 headings each
    check(
        "17. NEGATIVE -- a HEADINGS-as-rows table cannot be passed as documents",
        MC.DUPLICATE_DOCUMENT_IDENTITY,
        refusal(lambda: MC.section8_document_bootstrap(headings)),
        "headings enter as independent observations, which is exactly the per-heading "
        "probability 8.3 forbids (8.1 measured 0.1926 vs 0.00498, a 39x ratio)",
    )

    # 10 + 11. zero events.
    zero = MC.section8_document_bootstrap([(f"doc-{i}", False) for i in range(14)])
    check(
        "10. zero events REFUSE the bootstrap",
        (False, MC.ZERO_EVENTS_BOOTSTRAP_REFUSED),
        (zero["reported"], zero["reason"]),
        "a bootstrap is reported at zero events, where 8.1 measured every resample degenerate",
    )
    check(
        "11. ...and no [0, 0] interval is emitted",
        True,
        "interval" not in zero,
        "a degenerate [0.0, 0.0] is emitted and would read as a real confidence interval",
    )
    check(
        "...and the zero-event branch still yields the frozen closed form 1 - 0.05**(1/N)",
        1 - 0.05 ** (1 / 14),
        zero["clopper_pearson_upper_bound"],
        "the licensed number is missing, leaving only an absence where 8.3 specifies a bound",
    )

    # 12 + 13 + 14. the resampling itself.
    seen_replicates, seen_sizes, repeated_within = set(), set(), 0
    real_resample = MC.bootstrap_resample
    try:

        def counting(statistic_id, vec, replicate):
            out = real_resample(statistic_id, vec, replicate)
            seen_replicates.add(replicate)
            seen_sizes.add(len(out))
            return out

        MC.bootstrap_resample = counting
        counted = MC.section8_document_bootstrap(docs)
    finally:
        MC.bootstrap_resample = real_resample
    for r in range(200):
        picks = [d for d, _e in real_resample(MC.SECTION8_DOCUMENT_DISCORDANCE, vector, r)]
        if len(set(picks)) < len(picks):
            repeated_within += 1
    check(
        "12. a non-zero statistic executes ALL 10,000 replicates",
        MC.BOOTSTRAP_RESAMPLES,
        len(seen_replicates),
        "fewer replicates run than the frozen B, so the interval is computed on a smaller "
        "resample set than the amendment states",
    )
    check(
        "13. every replicate draws EXACTLY N documents",
        [len(docs)],
        sorted(seen_sizes),
        "a replicate draws a different number of documents than the vector holds",
    )
    check(
        "14. replacement is REAL -- documents repeat within a replicate",
        True,
        repeated_within > 0,
        "no replicate ever picks a document twice in 200 tries, which would mean the draw is "
        "a permutation rather than sampling with replacement",
    )
    check(
        "...and the counted run agrees with the uninstrumented one",
        base,
        counted,
        "instrumenting the resample changed the result, so control 12 measured a different run",
    )

    # 15 + 16. the endpoint rule.
    check(
        "15. the endpoint ranks are exactly 249 and 9749 at B = 10,000",
        (249, 9749),
        MC.percentile_indices(10_000),
        "the order statistics move, so the interval is not the one A37.6 froze",
    )
    achievable = {k / len(docs) for k in range(len(docs) + 1)}
    check(
        "16. the endpoints are OBSERVED replicate values -- no interpolation",
        (True, True),
        (base["interval"][0] in achievable, base["interval"][1] in achievable),
        "an endpoint lies between two achievable k/N rates, i.e. a library interpolated it "
        "(NumPy's percentile default would) and the value was never actually resampled",
    )
    check(
        "...and the reported endpoint indices are the frozen ones",
        [249, 9749],
        base["endpoint_indices"],
        "the result reports different indices from the ones it used",
    )

    # 18. non-gating, structurally.
    check(
        "18. the gate vector is exactly A27.6's nine decision-blocking conditions",
        (
            "R1",
            "N-A",
            "N-B",
            "N-C",
            "S1",
            "confirmatory X2-a",
            "confirmatory X2-b",
            "M9 evaluability",
            "4.5 adequacy",
        ),
        MC.GATE_VECTOR,
        "a condition was added to or removed from the decision gate",
    )
    check(
        "18b. NO bootstrap field appears anywhere in the gate vector",
        [],
        [g for g in MC.GATE_VECTOR if "bootstrap" in g.lower() or "interval" in g.lower()],
        "the bootstrap became a decision-blocking condition, promoting a supplementary number into evidence",
    )
    check(
        "18c. ...and no key of the bootstrap result is a gate input",
        [],
        sorted(set(base) & set(MC.GATE_VECTOR)),
        "a field the bootstrap emits is consumed by the architecture decision",
    )
    check(
        "18d. ...and both branches declare themselves non-gating",
        (False, False),
        (base["gating"], zero["gating"]),
        "a result does not carry gating: False, so a downstream reader could treat it as evidence",
    )

    # 19. canonical sorting is load-bearing -- an INDEPENDENT counterfactual.
    cf_a = [unsorted_resample(MC.SECTION8_DOCUMENT_DISCORDANCE, docs, r) for r in range(5)]
    cf_b = [unsorted_resample(MC.SECTION8_DOCUMENT_DISCORDANCE, reversed_docs, r) for r in range(5)]
    check(
        "19. WITHOUT canonical sorting the same set in another order resamples DIFFERENTLY",
        True,
        cf_a != cf_b,
        "the unsorted counterfactual is also order-independent, which would mean control 3 "
        "passes for some other reason and proves nothing about the sorting",
    )
    return {
        "statistic_identity": list(MC.SECTION8_DOCUMENT_DISCORDANCE),
        "namespace": MC.BOOTSTRAP_NAMESPACE,
        "resamples": MC.BOOTSTRAP_RESAMPLES,
        "endpoint_indices": list(MC.percentile_indices()),
        "gate_vector": list(MC.GATE_VECTOR),
        "fixture_n_documents": len(docs),
        "fixture_events": sum(1 for _d, e in docs if e),
        "interval": base["interval"],
        "replicates_with_a_repeated_document_in_200": repeated_within,
        "zero_event_branch": zero,
    }


def part_rule0_margin() -> dict:
    """A39.1 -- the Rule 0 margin-line clause. No tolerance anywhere."""
    print("\n== A39.1 Rule 0 margin-line clause ==")
    check(
        "H recovering FEWER margin lines makes H the loser",
        ("H", True, 1),
        tuple(MC.margin_line_loss(197, 198)[k] for k in ("loser", "fires", "deficit")),
        "a one-line deficit does not fire, i.e. a tolerance was invented where the frozen "
        "text says 'loses', not 'loses more than N'",
    )
    check(
        "X recovering FEWER margin lines makes X the loser",
        ("X", True, 1),
        tuple(MC.margin_line_loss(198, 197)[k] for k in ("loser", "fires", "deficit")),
        "the clause is not symmetric between the two architectures",
    )
    check(
        "EQUAL counts do not fire the margin-line clause",
        (None, False, 0),
        tuple(MC.margin_line_loss(198, 198)[k] for k in ("loser", "fires", "deficit")),
        "equality fires, so every document would carry a Rule 0 margin loss",
    )
    check(
        "a LARGE deficit fires exactly as a one-line deficit does",
        (True, True),
        (MC.margin_line_loss(10, 198)["fires"], MC.margin_line_loss(197, 198)["fires"]),
        "the clause is graded by severity, which the frozen text does not license",
    )
    check(
        "zero recovered on BOTH sides is still not a comparative loss",
        False,
        MC.margin_line_loss(0, 0)["fires"],
        "a document where neither architecture recovers a margin line is reported as one "
        "architecture losing to the other",
    )
    return {"rule": "count of Page.lines where line_number is not None; any positive deficit fires"}


def part_cross_engine() -> dict:
    """A39.2 -- the frozen 10 % cross-engine page sample."""
    print("\n== A39.2 cross-engine page sampling ==")
    sha_a = "a" * 64
    sha_b = "b" * 64
    pages_40 = list(range(1, 41))

    forward = MC.cross_engine_pages(sha_a, pages_40)
    reversed_ = MC.cross_engine_pages(sha_a, list(reversed(pages_40)))
    shuffled = MC.cross_engine_pages(sha_a, [pages_40[i] for i in (7, 3, 39, 0, 21, *range(1, 39))])
    check(
        "the same inputs select the same pages",
        forward,
        MC.cross_engine_pages(sha_a, pages_40),
        "selection is not reproducible from committed inputs",
    )
    check(
        "input page PERMUTATION changes nothing",
        (forward, forward),
        (reversed_, shuffled),
        "the sample depends on the order the caller happened to list pages in",
    )
    check(
        "changing the document SHA changes the ranking",
        True,
        MC.cross_engine_pages(sha_b, pages_40) != forward,
        "two documents share a page sample, so the identity component is not consumed",
    )
    real_ns = MC.CROSS_ENGINE_NAMESPACE
    try:
        MC.CROSS_ENGINE_NAMESPACE = "some-other-namespace"
        other_ns = MC.cross_engine_pages(sha_a, pages_40)
    finally:
        MC.CROSS_ENGINE_NAMESPACE = real_ns
    check(
        "changing the NAMESPACE changes the ranking",
        True,
        other_ns != forward,
        "domain separation is not live, so another purpose could reuse this draw sequence",
    )
    sizes = {n: len(MC.cross_engine_pages(sha_a, list(range(1, n + 1)))) for n in (1, 5, 9, 10, 11, 20, 21)}
    check(
        "k = max(1, ceil(0.10 * page_count)) on every boundary",
        {1: 1, 5: 1, 9: 1, 10: 1, 11: 2, 20: 2, 21: 3},
        sizes,
        "a short document selects ZERO pages and silently escapes the control, or a boundary rounds the wrong way",
    )
    check(
        "every document gets at least one sampled page",
        True,
        all(v >= 1 for v in sizes.values()),
        "the per-document consequence could attach to a document with no sampled page",
    )
    check(
        "an empty page set selects nothing rather than inventing a page",
        [],
        MC.cross_engine_pages(sha_a, []),
        "a document with no pages yields a sampled page that does not exist",
    )

    # NO THRESHOLD CONTROLS HERE, deliberately. This module owns the SAMPLE only; the gate --
    # the max(pdfium, pymupdf) denominator and both thresholds -- belongs to X09.gate and is
    # exercised against the real producer in x22. A duplicate qualification helper lived here
    # briefly and is deleted: keeping the rule executable in two places is what let the
    # confirmatory producer drift to `matched / pdfium` while these controls stayed green.
    check(
        "this module exposes NO cross-engine gate of its own",
        [],
        [n for n in ("cross_engine_qualification", "CROSS_ENGINE_DOC_MIN", "CROSS_ENGINE_PAGE_MIN") if hasattr(MC, n)],
        "a second executable copy of the gate exists here, so it can drift from X09.gate without any control noticing",
    )
    return {
        "namespace": MC.CROSS_ENGINE_NAMESPACE,
        "fraction": MC.CROSS_ENGINE_FRACTION,
        "gate_owner": "x09_skeleton_cross_engine.gate -- not duplicated here",
        "k_by_page_count": sizes,
        "sample_40_pages": forward,
    }


def main() -> int:
    print("== 4.5 adequacy ==")
    part_adequacy()
    print("\n== A27.7 / A28.3 determinism ==")
    part_determinism()
    print("\n== A28.4 renderer scale ==")
    part_dpi()
    print("\n== A37 supplementary document bootstrap (NON-GATING) ==")
    bootstrap = part_bootstrap()
    rule0 = part_rule0_margin()
    cross_engine = part_cross_engine()
    doc = {
        "population": "SYNTHETIC only -- no PDF opened, no architecture run, nothing scored",
        "adequacy_kinds": sorted(MC.ADEQUACY_KINDS),
        "selection_seed": MC.SELECTION_SEED,
        "primary_dpi": MC.PRIMARY_DPI,
        "r1_repeat_dpi": MC.R1_REPEAT_DPI,
        "a37_bootstrap": bootstrap,
        "a39_rule0_margin": rule0,
        "a39_cross_engine": cross_engine,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} tests pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
