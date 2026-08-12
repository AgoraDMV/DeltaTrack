"""x23 -- A39.3 / A40: the N-A/N-B/N-C source fixtures, their manifest, and the G6 validator.

NOT CONFIRMATORY. DEVELOPMENT + SYNTHETIC only. No holdout material appears anywhere in the
fixture chain, nothing is adjudicated or scored, and no canonical confirmatory artifact is
created. Evidence: `results/x23_control_fixtures.json`.

The A40 contract fixed every rule and control below BEFORE this probe existed. Each control
states the fact that would make it fail, and every G6 negative independently mutates a VALID
manifest -- so a validator that silently accepted anything would be caught rather than flattered.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

import control_fixtures as CF  # noqa: E402
import methodology_contracts as MC  # noqa: E402

OUT = EV / "results" / "x23_control_fixtures.json"
ROWS: list[dict] = []
FAILED: list[str] = []


NA_EXPECTED = CF.NA_TOTAL

#: A40.13 -- half a point of slack, so a rendered box coinciding with the region edge is not
#: rejected by float noise. Far smaller than a line, so it cannot admit a neighbouring line.
REGION_EDGE_TOLERANCE = 0.5


def region_occupancy(pdf_path, record: dict, region_bbox=None) -> dict:
    """Whole-line occurrences of the before/after headings, split by TARGET REGION membership.

    A40.13 -- the frozen contract is about the selected physical OCCURRENCE, not the page. GPO
    legitimately repeats a heading elsewhere on the same page, and such a duplicate is a different
    occurrence the adjudicator never sees; gating on it made a correct fixture fail.
    `region_bbox` is injectable so the negatives can move the crop without fabricating a PDF.
    """
    import xml_sources as XS

    rb = region_bbox or record["region_bbox_pdf_points"]
    height = record["page_height"]
    lines = [ln for ln in XS.physical_lines(pdf_path) if ln["page_number"] == record["page_number"]]

    def inside(ln):
        y0, y1 = height - ln["bbox_topleft"][3], height - ln["bbox_topleft"][1]
        return y0 >= rb[1] - REGION_EDGE_TOLERANCE and y1 <= rb[3] + REGION_EDGE_TOLERANCE

    out = {}
    for key, text in (("before", record["expected_before"]), ("after", record["expected_after"])):
        hits = [ln for ln in lines if XS.stripped_line(ln) == text.upper()]
        out[f"{key}_in_region"] = sum(1 for ln in hits if inside(ln))
        out[f"{key}_elsewhere_on_page"] = sum(1 for ln in hits if not inside(ln))
    return out


def check(name: str, expected, observed, fails_when: str = "") -> bool:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    if not ok:
        FAILED.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   expected={expected!r} observed={observed!r}"))
    return ok


def reasons(defects) -> list[str]:
    return sorted({d["reason"] for d in defects})


def part_mutations() -> dict:
    """A40.2/A40.4/A40.5 -- the three classes, proven structurally on synthetic strings."""
    print("\n== A40: the three mutation classes are LIVE ==")
    before = "SALARIES AND EXPENSES"
    d_after, _ = CF.delete_one_word(before)
    w_after, _ = CF.weld_two_words(before)
    s_after, _ = CF.split_one_word(before)

    d = CF.mutation_evidence(before, d_after, CF.DELETE_ONE_WORD)
    w = CF.mutation_evidence(before, w_after, CF.WELD_TWO_WORDS)
    s = CF.mutation_evidence(before, s_after, CF.SPLIT_ONE_WORD)

    check(
        "DELETE changes the NON-SPACE character sequence",
        (True, False),
        (d["live"], d["non_space_unchanged"]),
        "deleting a word leaves the non-space sequence intact, i.e. nothing was removed",
    )
    check(
        "WELD leaves non-space identical and removes exactly ONE boundary (1 -> 0)",
        (True, True, [[1, 0]]),
        (w["live"], w["non_space_unchanged"], w["boundary_transitions"]),
        "weld changed a character, or moved more than one boundary -- it would then be a "
        "content corruption rather than the missing-boundary class M3 distinguishes",
    )
    check(
        "SPLIT leaves non-space identical and inserts exactly ONE boundary (0 -> 1)",
        (True, True, [[0, 1]]),
        (s["live"], s["non_space_unchanged"], s["boundary_transitions"]),
        "split changed a character, or moved more than one boundary",
    )
    check(
        "SPLIT is the exact complement of WELD",
        ([[0, 1]], [[1, 0]]),
        (s["boundary_transitions"], w["boundary_transitions"]),
        "the two classes are not complementary, so N-A no longer spans both M3 directions",
    )
    check(
        "the SPLIT example matches the A40.2 illustration",
        "SALA RIES AND EXPENSES",
        s_after,
        "the frozen floor(len/2) target produces a different string than A40.2 specifies",
    )
    dead = CF.mutation_evidence(before, before, CF.SPLIT_ONE_WORD)
    check(
        "NEGATIVE -- a DEAD mutation (before == after) is not live",
        (False, False),
        (dead["live"], dead["changed"]),
        "an unchanged string is accepted as a mutation, which is exactly the A39.3 failure "
        "the size control was retired for",
    )
    check(
        "NEGATIVE -- the RETIRED size variant can never be live",
        False,
        CF.mutation_evidence(before, before, CF.RETIRED_VARIANT)["live"],
        "PULL_HEADING_TO_BODY_SIZE is still treated as a valid mutation class",
    )
    check(
        "both SPLIT pieces are at least 3 characters",
        True,
        all(len(p) >= CF.MIN_SPLIT_PIECE for p in CF.split_one_word(before)[1]["pieces"]),
        "a split leaves a 1-2 character fragment, which is a different failure mode",
    )
    return {"before": before, "delete": d_after, "weld": w_after, "split": s_after}


def _alt_delete(text):
    """A DIFFERENT valid deletion: the first token the FROZEN rule would NOT have chosen.

    Picking "the last token" is not enough -- in `RESEARCH AND DEVELOPMENT` the longest token IS
    the last one, so the "alternative" reproduced the canonical target exactly and the negative
    silently tested nothing. Selecting relative to the frozen target keeps it a real alternative
    whatever the heading looks like.
    """
    spans = CF._token_spans(text)
    canonical = max(spans, key=lambda sp: (len(sp[2]), -sp[0]))
    other = next((sp for sp in reversed(spans) if sp != canonical), None)
    if other is None:
        return None, None
    start, end, token = other
    after = CF.normalize_text(text[:start] + " " + text[end:])
    return after, {"variant": CF.DELETE_ONE_WORD, "target_token": token, "target_span": [start, end]}


def _alt_weld(text):
    """A DIFFERENT valid weld: the LAST adjacent whitespace-separated pair rather than the first."""
    spans = CF._token_spans(text)
    for (s0, e0, t0), (s1, _e1, t1) in reversed(list(zip(spans, spans[1:]))):
        gap = text[e0:s1]
        if gap and gap.isspace():
            return text[:e0] + text[s1:], {
                "variant": CF.WELD_TWO_WORDS,
                "target_pair": [t0, t1],
                "removed_gap_span": [e0, s1],
            }
    return None, None


def _alt_split(text):
    """A DIFFERENT valid split: another eligible token, or another legal cut in the same one."""
    spans = [sp for sp in CF._token_spans(text) if len(sp[2]) >= CF.MIN_SPLIT_TOKEN]
    chosen, cut = None, None
    if len(spans) > 1:
        chosen = spans[-1]
        cut = len(chosen[2]) // 2
    else:
        chosen = spans[0]
        for candidate in range(len(chosen[2]) // 2 + 1, len(chosen[2]) - CF.MIN_SPLIT_PIECE + 1):
            if candidate >= CF.MIN_SPLIT_PIECE:
                cut = candidate
                break
    if chosen is None or cut is None:
        return None, None
    start, _end, token = chosen
    after = text[: start + cut] + " " + text[start + cut :]
    return after, {
        "variant": CF.SPLIT_ONE_WORD,
        "target_token": token,
        "split_after_chars": cut,
        "pieces": [token[:cut], token[cut:]],
    }


def part_g6_falsifications(manifest: dict) -> dict:
    """The three falsifications that each caught a REAL false green during A40 freeze verification.

    They were run ad hoc at the time and are committed here so that reintroducing any of the three
    defects turns the suite red automatically. REGRESSION COVERAGE ONLY -- nothing below changes a
    methodology rule, a population, a fixture or a gate's contract; every assertion calls the
    authoritative validator directly and no new artifact is produced.
    """
    print("\n== A40 freeze-verification falsifications, preserved ==")
    import build_oracle as BO
    import run_extended
    import run_hybrid

    from deltatrack.parsers import pdf_anchors as PA

    def boom(*_a, **_k):
        raise AssertionError("architecture path used inside the result-bearing G6 validation")

    out: dict = {}
    saved = (run_hybrid.run, run_extended.run, PA.extract_anchors)
    try:
        # ---------- 1a. the cache CAN mask the sabotage, which is why clearing it is load-bearing.
        # Warm the cache first, then sabotage WITHOUT clearing: a cached population is returned and
        # no architecture path is touched. Asserting this proves the `.clear()` below is doing real
        # work rather than being ceremonial -- without it the whole sabotage control is vacuous.
        CF.replay_source_selection()
        run_hybrid.run, run_extended.run, PA.extract_anchors = boom, boom, boom
        masked = True
        try:
            CF.replay_source_selection()
        except AssertionError:
            masked = False
        check(
            "a WARM replay cache would mask the sabotage entirely",
            True,
            masked,
            "the cache does not short-circuit the replay, so this control no longer explains why "
            "the cache must be invalidated -- re-derive the sabotage control before trusting it",
        )

        # ---------- 1b. the real thing: invalidate, then run the ACTUAL G6 validator.
        CF._REPLAY_CACHE.clear()
        defects = sorted({d["reason"] for d in CF.validate_manifest(manifest)})
        replay = CF.replay_source_selection()
        expectations = CF.replay_na_expectations()
        allocation = {v: sum(1 for e in expectations if e["variant"] == v) for v in CF.NA_VARIANTS}
        observed = (
            defects,
            len(replay["population"]),
            len(replay["na_eligible"]),
            len(replay["nb_eligible"]),
            len(replay["na_selected"]),
            len(replay["nb_selected"]),
            allocation,
        )
        check(
            "G6 validates with run_hybrid/run_extended/extract_anchors ALL raising",
            ([], 96, 83, 96, 8, 8, CF.NA_EXPECTED_ALLOCATION),
            observed,
            "an H, X or pdf_anchors dependency has entered the result-bearing G6 replay path, so "
            "control source truth would be derived from the architectures under test",
        )
        out["sabotaged_g6"] = {"defects": defects, "allocation": allocation}

        # ---------- 1c. each patch is live, or the two checks above prove nothing.
        live = {}
        for label, fn in (
            ("run_hybrid.run", run_hybrid.run),
            ("run_extended.run", run_extended.run),
            ("pdf_anchors.extract_anchors", PA.extract_anchors),
        ):
            try:
                fn(None)
                live[label] = False
            except AssertionError:
                live[label] = True
        check(
            "every sabotaged entrypoint really raises when called",
            {k: True for k in live},
            live,
            "a monkeypatch did not take, so the sabotage control passed because nothing was disabled",
        )
        out["sabotage_live"] = live
    finally:
        run_hybrid.run, run_extended.run, PA.extract_anchors = saved
        CF._REPLAY_CACHE.clear()

    # ---------- 2 + 3. the two x26 protections, proven SEPARATELY so neither masks the other.
    #
    # The mutation is a well-formed swap of private truth between two valid N-B controls: both
    # records stay individually complete, the manifest stays valid, and nothing is malformed. That
    # matters -- a negative that fails on a missing file or bad JSON would prove nothing.
    mutated = copy.deepcopy(manifest)
    nb = sorted(
        [f for f in mutated["fixtures"] if f["control_kind"] == "N-B"], key=lambda f: f["schedule_index"]
    )
    a, b = nb[0], nb[1]
    a["expected_adjudicated_headings"], b["expected_adjudicated_headings"] = (
        b["expected_adjudicated_headings"],
        a["expected_adjudicated_headings"],
    )
    check(
        "the mutated control state is still WELL-FORMED (so the negatives cannot pass for the wrong reason)",
        (True, True, True),
        (
            bool(a["expected_adjudicated_headings"]) and bool(b["expected_adjudicated_headings"]),
            all(bool(f.get("canonical_identity")) for f in (a, b)),
            len(mutated["fixtures"]) == len(manifest["fixtures"]),
        ),
        "the mutation broke a record's structure, so a rejection would demonstrate malformedness "
        "rather than the binding invariant under test",
    )

    evidence_path = CF.ORACLE_INTEGRATION_EVIDENCE
    original_evidence = evidence_path.read_bytes()
    try:
        # ---------- 2. the committed x26 evidence is now STALE for this state and must not certify it.
        CF._REPLAY_CACHE.clear()
        stale = sorted({d["reason"] for d in CF.validate_manifest(mutated)})
        check(
            "a valid-but-different control state is REJECTED while the old x26 evidence still says failures==[]",
            True,
            CF.ORACLE_EVIDENCE_STALE in stale,
            "x26 evidence certifies a control/oracle state it was not produced for, which is the "
            "exact false green A40.16 closed -- the evidence would only be certifying itself",
        )
        check(
            "...and the untouched x26 artifact really did still report success",
            [],
            json.loads(original_evidence)["failures"],
            "the committed evidence already reported failures, so the staleness negative above is "
            "not isolating the input binding",
        )
        out["stale_x26"] = stale

        # ---------- 3. make the evidence CURRENT for the mutated state; the second protection must
        # still fire. Only the binding digest is recomputed -- re-rendering 20 controls is not
        # needed to establish that the evidence is no longer stale.
        refreshed = json.loads(original_evidence)
        refreshed["control_oracle_input_digest"] = BO.control_oracle_input_digest(mutated)
        evidence_path.write_text(json.dumps(refreshed, indent=1))
        CF._REPLAY_CACHE.clear()
        fresh = sorted({d["reason"] for d in CF.validate_manifest(mutated)})
        check(
            "even CURRENT x26 evidence cannot certify wrong N-B truth",
            (True, False),
            (CF.MUTATION_INPUT_MISMATCH in fresh, CF.ORACLE_EVIDENCE_STALE in fresh),
            "N-B expected truth is not independently replayed from source, so a manifest and its "
            "evidence can agree with each other while both disagree with the actual source",
        )
        out["fresh_x26_wrong_truth"] = fresh
    finally:
        evidence_path.write_bytes(original_evidence)
        CF._REPLAY_CACHE.clear()

    check(
        "the x26 evidence file is byte-restored",
        hashlib.sha256(original_evidence).hexdigest(),
        hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "the regression left the committed evidence modified, which would dirty the tree",
    )
    check(
        "and the authoritative state still validates cleanly",
        [],
        CF.validate_manifest(manifest),
        "the regression did not restore the state it mutated",
    )
    return out


def part_pdf_id(manifest: dict) -> dict:
    """A40.14 section 1 -- the trailer /ID is deterministic, unique, and NON-SEMANTIC.

    Deterministic and unique matter for byte stability. Non-semantic matters more: a value that
    nothing consumes cannot silently become an identity. The check is a real counterfactual --
    the same PDF bytes under a different NAME get a different /ID by construction, and the
    independently replayed source selection must not move.
    """
    print("\n== A40.14: the deterministic trailer /ID is non-semantic ==")
    import pymupdf

    ids = {}
    for f in manifest["fixtures"]:
        if not f.get("generated_path"):
            continue
        doc = pymupdf.open(str(EV / f["generated_path"]))
        try:
            ids[Path(f["generated_path"]).name] = doc.xref_get_key(-1, "ID")[1]
        finally:
            doc.close()
    check(
        "every generated fixture carries the id its own basename determines",
        {n: CF.deterministic_pdf_id(n) for n in ids},
        ids,
        "a generated fixture's trailer id is not the deterministic one, so its bytes are not "
        "reproducible from the committed inputs",
    )
    check(
        "all generated trailer ids are DISTINCT",
        len(ids),
        len(set(ids.values())),
        "two fixtures share a PDF identity",
    )

    # THE COUNTERFACTUAL: identical bytes, different name -> different /ID. Source selection and
    # the control identities must not notice, because neither consumes the trailer.
    before = [MC.canonical(CF.source_identity(r)) for r in CF.replay_source_selection()["na_selected"]]
    identities_before = sorted(f["canonical_identity"] for f in manifest["fixtures"])
    scratch = EV / "control_fixtures" / "_idprobe_renamed.pdf"
    victim = next(f for f in manifest["fixtures"] if f.get("generated_path"))
    try:
        shutil.copyfile(EV / victim["generated_path"], scratch)
        renamed_id = CF.deterministic_pdf_id(scratch.name)
        CF._REPLAY_CACHE.clear()
        after = [MC.canonical(CF.source_identity(r)) for r in CF.replay_source_selection()["na_selected"]]
    finally:
        scratch.unlink(missing_ok=True)
        CF._REPLAY_CACHE.clear()
    check(
        "a renamed copy would carry a DIFFERENT id (so the counterfactual is real)",
        True,
        renamed_id != CF.deterministic_pdf_id(Path(victim["generated_path"]).name),
        "the rename does not change the id, so this proves nothing about /ID being ignored",
    )
    check(
        "...and neither source selection nor control identity moves",
        (before, identities_before),
        (after, sorted(f["canonical_identity"] for f in manifest["fixtures"])),
        "a PDF trailer id reached source selection or control identity, which would make "
        "provenance depend on a filename rather than on committed source/SHA identity",
    )
    return {"ids": ids, "selection_stable_under_rename": before == after}


def part_replay(manifest: dict) -> dict:
    """A40 F3/F4 -- the manifest cannot be coherent-but-wrong and still pass."""
    print("\n== A40 F3/F4: independent replay, and what defeats it ==")
    replay = CF.replay_source_selection()
    expectations = CF.replay_na_expectations()

    check(
        "F3 -- the committed manifest AGREES with a full independent source replay",
        [],
        [d["reason"] for d in CF.validate_manifest(manifest)],
        "the committed selection cannot be reproduced from the committed XML/PDF and the frozen "
        "constants, so either the manifest or the deterministic chain is wrong",
    )
    check(
        "F4 -- every N-A variant is derived from the frozen schedule, not read from the manifest",
        [CF.NA_SCHEDULE[i % 3] for i in range(CF.NA_TOTAL)],
        [e["variant"] for e in expectations],
        "the replay takes the variant from the record it is checking, so a re-scheduled manifest "
        "would validate against itself",
    )

    def injected_reasons(mutate) -> list[str]:
        broken = copy.deepcopy(manifest)
        mutate(broken)
        return reasons(CF.validate_manifest(broken))

    selected_na = {MC.canonical(CF.source_identity(r)) for r in replay["na_selected"]}
    selected_nb = {MC.canonical(CF.source_identity(r)) for r in replay["nb_selected"]}
    spare_na = next(r for r in replay["na_eligible"] if MC.canonical(CF.source_identity(r)) not in selected_na)
    spare_nb = next(r for r in replay["nb_eligible"] if MC.canonical(CF.source_identity(r)) not in selected_nb)

    def swap_source(f, row):
        f["source_canonical_identity"] = MC.canonical(CF.source_identity(row))
        f["element_id"] = row["element_id"]
        f["physical_line_index"] = row["line_index"]

    def sub_na(m):
        swap_source(next(f for f in m["fixtures"] if f["control_kind"] == "N-A" and f["schedule_index"] == 0), spare_na)

    def sub_nb(m):
        swap_source(next(f for f in m["fixtures"] if f["control_kind"] == "N-B" and f["schedule_index"] == 0), spare_nb)

    def wrong_xml_identity(m):
        f = next(f for f in m["fixtures"] if f["control_kind"] == "N-A" and f["schedule_index"] == 0)
        f["element_id"] = "H" + "0" * 31

    def wrong_physical(m):
        f = next(f for f in m["fixtures"] if f["control_kind"] == "N-A" and f["schedule_index"] == 0)
        f["physical_line_index"] = int(f["physical_line_index"]) + 1

    def reordered(m):
        rows = sorted([f for f in m["fixtures"] if f["control_kind"] == "N-A"], key=lambda f: f["schedule_index"])
        a, b = rows[0], rows[1]
        for k in ("source_canonical_identity", "element_id", "physical_line_index"):
            a[k], b[k] = b[k], a[k]

    f3 = {
        "A selected N-A replaced by another ELIGIBLE N-A": (sub_na, CF.SOURCE_SELECTION_MISMATCH),
        "B selected N-B replaced by another ELIGIBLE N-B": (sub_nb, CF.SOURCE_SELECTION_MISMATCH),
        "C same text, wrong XML structural identity": (wrong_xml_identity, CF.SOURCE_IDENTITY_MISMATCH),
        "D same text, wrong physical occurrence": (wrong_physical, CF.PHYSICAL_SOURCE_MISMATCH),
        "E 8/8 counts kept, one source substituted": (sub_na, CF.SOURCE_SELECTION_MISMATCH),
        "F right members, deterministic order broken": (reordered, CF.SOURCE_SELECTION_ORDER_MISMATCH),
    }
    got = {k: (v[1] in injected_reasons(v[0])) for k, v in f3.items()}
    check(
        "F3 NEGATIVES -- every deterministically wrong manifest FAILS with its own reason",
        {k: True for k in f3},
        got,
        "a coherent but deterministically wrong manifest validates, which is exactly the "
        "false green F3 exists to remove",
    )

    # ---- F4 alternative-live negatives. Each alternative must itself be a LIVE mutation, or the
    # negative proves nothing: rejecting a DEAD mutation is already covered elsewhere.
    alt = {CF.DELETE_ONE_WORD: _alt_delete, CF.WELD_TWO_WORDS: _alt_weld, CF.SPLIT_ONE_WORD: _alt_split}
    liveness, rejected = {}, {}
    for variant, builder in alt.items():
        src = next(e for e in expectations if e["variant"] == variant)
        after, recipe = builder(src["expected_before"])
        evidence = CF.mutation_evidence(src["expected_before"], after, variant)
        liveness[variant] = bool(after) and evidence["live"] and after != src["expected_after"]

        def mutate(m, idx=src["schedule_index"], after=after, recipe=recipe):
            f = next(f for f in m["fixtures"] if f["control_kind"] == "N-A" and f["schedule_index"] == idx)
            f["expected_after"] = after
            f["mutation_recipe"] = recipe
            f["mutation_evidence"] = CF.mutation_evidence(f["expected_before"], after, f["variant"])

        rejected[variant] = CF.MUTATION_TARGET_MISMATCH in injected_reasons(mutate)
    check(
        "each ALTERNATIVE mutation is itself LIVE (else the negative proves nothing)",
        {v: True for v in alt},
        liveness,
        "the alternative is dead, so its rejection shows only that dead mutations fail -- which is a different control",
    )
    check(
        "F4 NEGATIVES -- a live but non-deterministic target is REJECTED",
        {v: True for v in alt},
        rejected,
        "a different-but-live mutation passes, so the deterministic target rule is not enforced",
    )

    def recipe_only(m):
        f = next(f for f in m["fixtures"] if f["control_kind"] == "N-A" and f["schedule_index"] == 0)
        f["mutation_recipe"] = {**f["mutation_recipe"], "target_token": "TAMPERED"}

    def rewritten_before(m):
        """The decisive one: before/after/recipe all rewritten CONSISTENTLY with each other."""
        f = next(f for f in m["fixtures"] if f["control_kind"] == "N-A" and f["schedule_index"] == 0)
        forged = "TOTALLY DIFFERENT HEADING TEXT"
        after, recipe = CF.MUTATORS[f["variant"]](forged)
        f["expected_before"] = forged
        f["expected_after"] = after
        f["mutation_recipe"] = recipe
        f["mutation_evidence"] = CF.mutation_evidence(forged, after, f["variant"])

    check(
        "F4 NEGATIVE -- recipe metadata altered while expected_after stays correct is REJECTED",
        True,
        CF.MUTATION_RECIPE_MISMATCH in injected_reasons(recipe_only),
        "the recipe is not compared, so the committed target rule is unverifiable",
    )
    check(
        "F4 NEGATIVE -- a SELF-CONSISTENT rewrite of before/after/recipe is REJECTED",
        True,
        CF.MUTATION_INPUT_MISMATCH in injected_reasons(rewritten_before),
        "the replay takes expected_before from the manifest, so a record that rewrites its own "
        "input and recomputes everything from it validates against itself -- F4 would be "
        "self-validating rather than independent",
    )
    return {
        "population": len(replay["population"]),
        "na_eligible": len(replay["na_eligible"]),
        "nb_eligible": len(replay["nb_eligible"]),
        "expectations": [
            {k: e[k] for k in ("schedule_index", "variant", "expected_before", "expected_after")} for e in expectations
        ],
        "f3_negatives": got,
        "f4_alternative_live": liveness,
        "f4_rejected": rejected,
    }


def part_manifest(manifest: dict) -> dict:
    """The realized fixtures, and what the generated PDFs actually print."""
    print("\n== A39.3/A40: the realized fixture set ==")
    na = [f for f in manifest["fixtures"] if f["control_kind"] == "N-A"]
    nb = [f for f in manifest["fixtures"] if f["control_kind"] == "N-B"]
    nc = [f for f in manifest["fixtures"] if f["control_kind"] == "N-C"]

    check(
        "the manifest holds exactly 8 N-A, 8 N-B, 4 N-C",
        {"N-A": 8, "N-B": 8, "N-C": 4},
        manifest["counts"],
        "a control class is under- or over-populated, so a Rule 3 blocker is not satisfied",
    )
    allocation = {v: sum(1 for f in na if f["variant"] == v) for v in CF.NA_VARIANTS}
    check(
        "N-A realizes the frozen 3 / 3 / 2 allocation",
        CF.NA_EXPECTED_ALLOCATION,
        allocation,
        "the index-mod-3 schedule was not applied, so the three M3 directions are not balanced as A40.1 freezes them",
    )
    check(
        "every N-A mutation is LIVE on the realized fixtures",
        (8, True),
        (len(na), all(f["mutation_evidence"]["live"] for f in na)),
        "a realized control cannot fire, so it reports coverage the study does not have",
    )
    check(
        "the RETIRED variant appears nowhere in the realized set",
        [],
        [f["canonical_identity"] for f in na if f["variant"] == CF.RETIRED_VARIANT],
        "PULL_HEADING_TO_BODY_SIZE survived the A40 retirement",
    )
    check(
        "every N-C expects EXACTLY no headings",
        [[] for _ in nc],
        [f["expected_adjudicated_headings"] for f in nc],
        "a constructionally heading-free region expects a heading, so the over-triggering control could never fail",
    )
    check(
        "every N-A and N-B carries paired GPO XML corroboration",
        (16, 16),
        (len(na) + len(nb), sum(1 for f in na + nb if f.get("xml_evidence") and f.get("xml_sha256"))),
        "a control's truth rests on something other than the independent source -- in the "
        "worst case on H or X's own output",
    )
    check(
        "all 20 control identities are unique",
        20,
        len({f["canonical_identity"] for f in manifest["fixtures"]}),
        "two controls share an identity, so one would silently overwrite the other",
    )

    # WHAT THE GENERATED PDF PRINTS IN THE CROP THE ADJUDICATOR SEES. The recipe is truth, but a
    # fixture whose rendering did not land in the region would show the adjudicator nothing.
    occupancy = [region_occupancy(EV / f["generated_path"], f) for f in na]
    check(
        "every generated N-A prints its mutation in the TARGET REGION exactly once",
        [1] * NA_EXPECTED,
        [o["after_in_region"] for o in occupancy],
        "the mutation did not reach the adjudicated region, so the stimulus would not contain "
        "the alteration the control exists to test",
    )
    check(
        "...and the ORIGINAL heading is absent from that TARGET REGION",
        [0] * NA_EXPECTED,
        [o["before_in_region"] for o in occupancy],
        "the unmutated heading survives inside the crop, so the region shows both and the "
        "control cannot distinguish an oracle that saw the alteration",
    )
    check(
        "DIAGNOSTIC -- some N-A pages legitimately repeat the original heading OUTSIDE the crop",
        True,
        any(o["before_elsewhere_on_page"] > 0 for o in occupancy),
        "no fixture exercises the duplicate-elsewhere case, so the occurrence-scoped rule is "
        "indistinguishable from the page-scoped one it replaced",
    )
    # The three scope controls. A40.13 -- prove the new rule is LIVE rather than merely weaker.
    victim = next(f for f, o in zip(na, occupancy) if o["before_elsewhere_on_page"] > 0)
    wide = region_occupancy(EV / victim["generated_path"], victim, region_bbox=[0.0, 0.0, 1e4, victim["page_height"]])
    check(
        "NEGATIVE A -- an original heading INSIDE the target region is detected",
        True,
        wide["before_in_region"] > 0,
        "an unmutated heading inside the crop goes unnoticed, so the region rule cannot fail",
    )
    check(
        "NEGATIVE B -- a mutation absent from the target region is detected",
        0,
        region_occupancy(EV / victim["generated_path"], victim, region_bbox=[0.0, 0.0, 1e4, 1.0])["after_in_region"],
        "the mutation counts even when it lies outside the crop, so the rule would pass a "
        "stimulus that shows the adjudicator nothing",
    )
    same = region_occupancy(EV / victim["generated_path"], victim)
    check(
        "POSITIVE -- a fixture whose original repeats ELSEWHERE on the page still passes",
        (1, 0, True),
        (same["after_in_region"], same["before_in_region"], same["before_elsewhere_on_page"] > 0),
        "the rule still gates on an unrelated duplicate outside the selected region, which is "
        "the scope error A40.13 corrects",
    )
    return {
        "counts": manifest["counts"],
        "allocation": allocation,
        "eligible_population": manifest["eligible_population"],
        "na": [
            {
                "index": f["schedule_index"],
                "variant": f["variant"],
                "source": f["source_document"],
                "page": f["page_number"],
                "before": f["expected_before"],
                "after": f["expected_after"],
                "boundary_transitions": f["mutation_evidence"]["boundary_transitions"],
                "non_space_unchanged": f["mutation_evidence"]["non_space_unchanged"],
                "generated_sha256": f["generated_sha256"][:16],
            }
            for f in na
        ],
        "nb": [
            {
                "index": f["schedule_index"],
                "source": f["source_document"],
                "page": f["page_number"],
                "expected_text": f["expected_adjudicated_headings"][0]["text"],
                "xml_path": f["xml_path"],
                "xml_sha256": f["xml_sha256"][:16],
            }
            for f in nb
        ],
        "nc": [
            {"index": f["schedule_index"], "generated_sha256": f["generated_sha256"][:16], "expected": []} for f in nc
        ],
    }


def part_nc_rendered(manifest: dict) -> dict:
    """F8 -- N-C distinctness measured through the REAL oracle renderer, not container SHAs.

    The previous fixtures had four different container SHA-256 values and rendered to ONE
    identical PNG, because the generator ignored its index. The adjudicator sees the render,
    so the render is what has to differ.
    """
    print("\n== F8: the four N-C controls are distinct AS RENDERED ==")
    import build_oracle as BO
    import pymupdf

    nc = [f for f in manifest["fixtures"] if f["control_kind"] == "N-C"]
    png_hashes, container_hashes = [], []
    for f in nc:
        path = EV / f["generated_path"]
        container_hashes.append(CF.sha256_file(path))
        doc = pymupdf.open(str(path))
        try:
            page = doc[0]
            x0, y0, x1, y1 = f["region_bbox_pdf_points"]
            png, _w, _h = BO.render_region(page, (x0, y0, x1, y1), 300)
        finally:
            doc.close()
        png_hashes.append(hashlib.sha256(png).hexdigest())

    check(
        "the four N-C controls render to FOUR DISTINCT PNG hashes",
        4,
        len(set(png_hashes)),
        "two heading-free controls are the same image, so the four-item N-C denominator is "
        "really fewer -- and container SHA uniqueness would have hidden it",
    )
    check(
        "...through the REAL build_oracle.render_region at the frozen primary DPI",
        (4, True),
        (len(png_hashes), all(len(h) == 64 for h in png_hashes)),
        "the distinctness was measured by some other path than the one that will render the actual stimulus",
    )
    check(
        "container SHAs are distinct too, but are NOT the evidence",
        4,
        len(set(container_hashes)),
        "the generated files are byte-identical, which is a different defect",
    )
    return {
        "rendered_png_sha256": png_hashes,
        "container_sha256": [h[:16] for h in container_hashes],
        "distinct_rendered": len(set(png_hashes)),
    }


def part_reproducible(manifest: dict) -> dict:
    """The fixtures must REBUILD to identical bytes, or the committed hashes are worthless.

    pymupdf writes a RANDOM trailer `/ID` on every save, so an unmodified fixture rebuilt from
    identical inputs used to produce different bytes each run -- the manifest SHA went stale
    immediately and G6 flipped red after any `x23`. A hash that cannot survive a rebuild
    certifies nothing.
    """
    print("\n== fixture bytes are REPRODUCIBLE ==")
    committed = {f["generated_path"]: f["generated_sha256"] for f in manifest["fixtures"] if f.get("generated_path")}
    before = {Path(p).name: h for p, h in committed.items()}
    # Rebuild into a SCRATCH directory rather than over the committed fixtures. Doing it in
    # place made this control ORDER-DEPENDENT: a later section that merely OPENS the generated
    # PDFs perturbed the next rebuild, so it reported a reproducibility failure that
    # back-to-back builds provably do not have. Comparing a clean rebuild against the committed
    # hashes tests the property that matters -- same inputs, same bytes -- and cannot be
    # disturbed by the rest of the probe.
    scratch = CF.GENERATED_DIR / "_verify"
    try:
        rebuilt = CF.build_manifest(generated_dir=scratch)
        after = {
            Path(f["generated_path"]).name: f["generated_sha256"]
            for f in rebuilt["fixtures"]
            if f.get("generated_path")
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    check(
        "a clean rebuild reproduces IDENTICAL bytes for every generated fixture",
        before,
        after,
        "a rebuild from identical inputs produces different bytes, so every committed hash "
        "goes stale on the next run and G6 cannot stay green",
    )
    check(
        "the fixtures actually carry a canonicalised PDF /ID",
        (12, True),
        (len(committed), all(CF._PDF_ID.search((EV / p).read_bytes()) for p in committed)),
        "a generated PDF has no /ID array, so the canonicalisation silently did nothing and "
        "reproducibility would depend on luck",
    )
    return {"n_generated": len(before)}


def part_holdout_identity(manifest: dict) -> dict:
    """F7 -- holdout exclusion by SOURCE IDENTITY, not just by name."""
    print("\n== F7: holdout exclusion is identity-based ==")
    shas = CF.holdout_source_sha256()
    check(
        "the authoritative holdout SHA set is non-empty",
        True,
        len(shas) >= 17,
        "the membership manifest yielded no source hashes, so the identity guard would be "
        "vacuous and every control would pass it trivially",
    )
    check(
        "no committed control carries a holdout source identity",
        [],
        [
            f["canonical_identity"]
            for f in manifest["fixtures"]
            if {f.get("source_sha256"), f.get("parent_sha256"), f.get("generated_sha256")} & shas
        ],
        "a control's bytes are a confirmatory source",
    )
    # THE COUNTERFACTUAL the name scan cannot catch: innocuous naming, holdout bytes.
    smuggled = copy.deepcopy(manifest)
    victim = smuggled["fixtures"][0]
    victim["source_document"] = "118-hr-8752/1"
    victim["source_path"] = "tests/corpus/118-hr-8752/1_reported-in-house.pdf"
    victim["source_sha256"] = sorted(shas)[0]
    got = reasons(CF.validate_manifest(smuggled))
    check(
        "NEGATIVE -- a DEVELOPMENT-looking record carrying a holdout SHA is REJECTED",
        True,
        "HOLDOUT_SOURCE_IDENTITY" in got,
        "confirmatory bytes copied in under an innocuous document id and path pass the gate, "
        "because nothing about the bytes has to change to defeat a name-based scan",
    )
    check(
        "...and the name-based scan alone would NOT have caught it",
        False,
        "HOLDOUT_PROVENANCE" in got,
        "the name scan happens to catch this case, so the identity check is not what is being "
        "demonstrated and the control proves less than it claims",
    )
    return {"n_holdout_source_sha256": len(shas), "counterfactual_reasons": got}


def part_g6(manifest: dict) -> dict:
    """A39.4 -- G6's validator, with every required negative independently injected."""
    print("\n== A39.4: G6 validation, positive and negative ==")
    # A40.12 -- G6 is deliberately RED until F3/F4 land, so the assertion is that the ONLY
    # defects are the two declared-outstanding replay flags. Asserting the exact set rather than
    # "at least these" is what stops a real defect hiding behind the known-outstanding ones.
    check(
        "the realized manifest carries NO defect except the declared-outstanding replays",
        sorted(CF.OUTSTANDING_REPLAY_DEFECTS),
        sorted({d["reason"] for d in CF.validate_manifest(manifest)}),
        "either the validator rejects a correctly built fixture set, or a real defect is hiding "
        "among the outstanding-replay markers",
    )
    check(
        "G6 is green ONLY because both replays are actually implemented and pass",
        (True, True, True),
        (
            CF.SOURCE_SELECTION_REPLAY_IMPLEMENTED,
            CF.MUTATION_TARGET_REPLAY_IMPLEMENTED,
            CF.validate_manifest(manifest) == [],
        ),
        "either a replay is switched off while G6 still reports PASS -- the semantic false green "
        "A40.12 removed -- or the manifest no longer satisfies a replay that is switched on",
    )

    def injected(mutate) -> list[str]:
        broken = copy.deepcopy(manifest)
        mutate(broken)
        return reasons(CF.validate_manifest(broken))

    def first_na(m):
        return next(f for f in m["fixtures"] if f["control_kind"] == "N-A")

    def drop(kind):
        def go(m):
            for i, f in enumerate(m["fixtures"]):
                if f["control_kind"] == kind:
                    del m["fixtures"][i]
                    m["counts"][kind] -= 1
                    return

        return go

    negatives = {
        "N-A count wrong": (drop("N-A"), "WRONG_CONTROL_COUNT"),
        "N-B count wrong": (drop("N-B"), "WRONG_CONTROL_COUNT"),
        "N-C count wrong": (drop("N-C"), "WRONG_CONTROL_COUNT"),
        "N-A allocation wrong": (
            lambda m: first_na(m).update(variant=CF.WELD_TWO_WORDS),
            "WRONG_NA_ALLOCATION",
        ),
        "RETIRED size variant reintroduced": (
            lambda m: first_na(m).update(variant=CF.RETIRED_VARIANT),
            "RETIRED_VARIANT_PRESENT",
        ),
        "N-A mutation before == after": (
            lambda m: first_na(m).update(expected_after=first_na(m)["expected_before"]),
            "DEAD_OR_MISCLASSIFIED_MUTATION",
        ),
        "WELD changes non-space characters": (
            lambda m: _set_variant(m, CF.WELD_TWO_WORDS, lambda f: f.update(expected_after="TOTALLY DIFFERENT TEXT")),
            "DEAD_OR_MISCLASSIFIED_MUTATION",
        ),
        "SPLIT changes non-space characters": (
            lambda m: _set_variant(m, CF.SPLIT_ONE_WORD, lambda f: f.update(expected_after="TOTALLY DIFFERENT TEXT")),
            "DEAD_OR_MISCLASSIFIED_MUTATION",
        ),
        "WELD moves more than one boundary": (
            lambda m: _set_variant(
                m, CF.WELD_TWO_WORDS, lambda f: f.update(expected_after=f["expected_before"].replace(" ", ""))
            ),
            "DEAD_OR_MISCLASSIFIED_MUTATION",
        ),
        "SPLIT moves a boundary the wrong way": (
            lambda m: _set_variant(
                m, CF.SPLIT_ONE_WORD, lambda f: f.update(expected_after=f["expected_before"].replace(" ", "", 1))
            ),
            "DEAD_OR_MISCLASSIFIED_MUTATION",
        ),
        "stale source SHA": (lambda m: first_na(m).update(source_sha256="0" * 64), "STALE_SHA256"),
        "stale generated PDF SHA": (lambda m: first_na(m).update(generated_sha256="0" * 64), "STALE_SHA256"),
        "duplicate control identity": (
            lambda m: m["fixtures"][1].update(canonical_identity=m["fixtures"][0]["canonical_identity"]),
            "DUPLICATE_CONTROL_IDENTITY",
        ),
        "missing expected truth": (
            lambda m: first_na(m).update(expected_adjudicated_headings=[]),
            "MISSING_EXPECTED_TRUTH",
        ),
        "N-B missing XML corroboration": (
            lambda m: _set_kind(m, "N-B", lambda f: f.update(xml_evidence=None, xml_sha256=None)),
            "MISSING_XML_CORROBORATION",
        ),
        "N-C expected headings non-empty": (
            lambda m: _set_kind(m, "N-C", lambda f: f.update(expected_adjudicated_headings=[{"text": "X"}])),
            "NC_EXPECTED_HEADINGS_NOT_EMPTY",
        ),
        "holdout provenance in the chain": (
            lambda m: first_na(m).update(source_document="116-hr-7611/1"),
            "HOLDOUT_PROVENANCE",
        ),
        "mutation recipe disagrees with variant": (
            lambda m: first_na(m).update(mutation_recipe={"variant": CF.SPLIT_ONE_WORD}),
            "MUTATION_RECIPE_VARIANT_MISMATCH",
        ),
    }
    results = {}
    for label, (mutate, expected_reason) in negatives.items():
        got = injected(mutate)
        results[label] = {"expected": expected_reason, "fired": expected_reason in got, "reasons": got}
    check(
        "EVERY injected defect makes G6 FAIL with its own reason",
        {k: True for k in negatives},
        {k: v["fired"] for k, v in results.items()},
        "an injected defect passes validation -- a green G6 would then certify a fixture set "
        "that cannot satisfy its Rule 3 blockers",
    )

    # the stale-hash negatives must react to real BYTES, not just a changed string
    on_disk = copy.deepcopy(manifest)
    target = next(f for f in on_disk["fixtures"] if f["control_kind"] == "N-A")
    generated = EV / target["generated_path"]
    original_bytes = generated.read_bytes()
    try:
        generated.write_bytes(original_bytes + b"\n% mutated after the manifest was written\n")
        byte_defects = reasons(CF.validate_manifest(on_disk))
    finally:
        generated.write_bytes(original_bytes)
    check(
        "NEGATIVE -- changing the generated PDF BYTES with a stale manifest hash FAILS",
        True,
        "STALE_SHA256" in byte_defects,
        "the validator compares recorded strings rather than recomputing from the file, so a "
        "silently edited fixture would keep certifying",
    )
    check(
        "...and restoring the bytes clears the byte defect (only the outstanding replays remain)",
        sorted(CF.OUTSTANDING_REPLAY_DEFECTS),
        sorted({d["reason"] for d in CF.validate_manifest(on_disk)}),
        "the byte-level control left the fixture set permanently invalid",
    )
    return {"negatives": {k: {"expected": v["expected"], "fired": v["fired"]} for k, v in results.items()}}


def _set_variant(manifest, variant, mutate):
    mutate(next(f for f in manifest["fixtures"] if f.get("variant") == variant))


def _set_kind(manifest, kind, mutate):
    mutate(next(f for f in manifest["fixtures"] if f["control_kind"] == kind))


def main() -> int:
    mutations = part_mutations()
    manifest = CF.build_manifest()
    CF.write_manifest(manifest)
    realized = part_manifest(manifest)
    pdf_id = part_pdf_id(manifest)
    replay = part_replay(manifest)
    falsifications = part_g6_falsifications(manifest)
    nc_rendered = part_nc_rendered(manifest)
    reproducible = part_reproducible(manifest)
    holdout = part_holdout_identity(manifest)
    g6 = part_g6(manifest)

    doc = {
        "population": "DEVELOPMENT + SYNTHETIC -- no confirmatory holdout material anywhere",
        "contract": "A39.3 (control sources) as amended by A40 (live boundary control)",
        "manifest": str(CF.MANIFEST_PATH.relative_to(EV)),
        "mutation_classes": mutations,
        "realized": realized,
        "pdf_id": pdf_id,
        "f3_f4_replay": replay,
        "g6_falsifications": falsifications,
        "nc_rendered_distinctness": nc_rendered,
        "reproducibility": reproducible,
        "holdout_identity_guard": holdout,
        "g6": g6,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
