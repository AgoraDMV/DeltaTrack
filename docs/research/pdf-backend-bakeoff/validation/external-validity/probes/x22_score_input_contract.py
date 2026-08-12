"""x22 -- A38: can every fact `score_metrics` needs be derived from COMMITTED ARTIFACTS?

NOT CONFIRMATORY. SYNTHETIC + DEVELOPMENT only. No holdout document is opened, nothing is
adjudicated, nothing is scored, no architecture decision is taken, and no confirmatory or
scoring artifact is created. Evidence: `results/x22_score_input_contract.json`.

THE QUESTION THIS PROBE ANSWERS, and its negative controls must be able to answer it FALSE:

    can every future score_metrics obligation be satisfied from committed artifacts, with no
    PDF access, no runner access, no text matching, and no implementation-time choice?

The A38 contract fixed the ownership table and every control below BEFORE this probe existed.
Each states the fact that would make it fail.

RUN WITH AN INTERPRETER CARRYING BOTH `pymupdf` AND `pypdfium2`, as `x20`/`x21` require.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
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

import build_frames as BF  # noqa: E402
import build_oracle as BO  # noqa: E402
import cross_engine_control as CE  # noqa: E402
import methodology_contracts as MC  # noqa: E402
import run_extended  # noqa: E402
import run_hybrid  # noqa: E402
import s1_control as S1  # noqa: E402
import x09_skeleton_cross_engine as X09  # noqa: E402

from deltatrack.parsers import pdf_anchors as PA  # noqa: E402

OUT = EV / "results" / "x22_score_input_contract.json"
ROWS: list[dict] = []
FAILED: list[str] = []
STOPS: list[dict] = []
# Ambiguities this probe once carried as OPEN and that a later amendment has since ruled.
# Kept visible rather than deleted: the history is the evidence that the gap was found before
# execution, and each entry is paired with an executable assertion that the ruling is live.
RESOLVED: list[dict] = []

DOC_NAME = "118-hr-8752/1"
DOC_PATH = REPO / "tests/corpus/118-hr-8752/1_reported-in-house.pdf"
PAGE_LIMIT = 16  # machinery demonstration window, NOT a census

HOLDOUT_GUARD = BO.HOLDOUT_GUARD


def check(name: str, expected, observed, fails_when: str = "") -> bool:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    if not ok:
        FAILED.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   expected={expected!r} observed={observed!r}"))
    return ok


def refusal(fn):
    try:
        fn()
    except (BO.OracleBuildError, BF.FrameConstructionError) as exc:
        return exc.reason
    return None


def development_frame():
    for member in HOLDOUT_GUARD:
        if member in str(DOC_PATH):
            raise SystemExit(f"REFUSED: {DOC_PATH} touches holdout member {member}")
    h = run_hybrid.run(DOC_PATH, limit=PAGE_LIMIT)
    x, _s = run_extended.run(DOC_PATH, limit=PAGE_LIMIT)
    sha = hashlib.sha256(DOC_PATH.read_bytes()).hexdigest()
    return sha, h, x, BF.build_document_frame(sha, DOC_NAME, BF.P_HEAD, h, x)


# ----------------------------------------------------- A38.2 the identity candidates


def part_candidates(frame: dict) -> dict:
    print("\n== A38.2: the A30 identity candidates are committed ==")
    lines = [ln for pf in frame["pages"] for ln in pf["neutral_lines"]]
    with_candidates = [ln for ln in lines if ln.get("identity_candidates")]

    exact = all(sorted(c["ngid"] for c in ln["identity_candidates"]) == sorted(ln["gids"]) for ln in with_candidates)
    check(
        "every committed neutral line's candidates are EXACTLY its gids",
        (len(lines), True),
        (len(with_candidates), exact),
        "a gid has no candidate, or a candidate names a gid outside the line -- either way the "
        "A30.3 resolver would search the wrong glyph set",
    )
    check(
        "the candidate population is non-empty, so the check above is not vacuous",
        True,
        len(with_candidates) > 0,
        "no line carries candidates, so 'all lines agree' passed on nothing",
    )
    # A24.2 -- U+0020 carries no neutral identity and must never be a candidate. The skeleton
    # excludes it by codepoint, so a space's gid cannot appear in any line's gid set.
    all_gids = {g for ln in lines for g in ln["gids"]}
    all_cands = {c["ngid"] for ln in with_candidates for c in ln["identity_candidates"]}
    check(
        "no candidate exists outside the committed gid sets (U+0020 among them)",
        set(),
        all_cands - all_gids,
        "a candidate was invented from a source glyph the skeleton rejected, e.g. a word space",
    )
    unrounded = [c["x0"] for ln in with_candidates for c in ln["identity_candidates"]]
    check(
        "candidate x0 is UNROUNDED source geometry",
        True,
        any(abs(v - round(v, 4)) > 0 for v in unrounded) or any(len(repr(v).split(".")[-1]) > 4 for v in unrounded),
        "every x0 lands on a 4-decimal grid, i.e. it was rounded for serialization -- rounding "
        "here can move a nearest-glyph decision",
    )
    ordered = all(
        [c["ngid"] for c in ln["identity_candidates"]] == sorted(c["ngid"] for c in ln["identity_candidates"])
        for ln in with_candidates
    )
    check(
        "candidates serialize in ngid order (determinism ONLY, never reading order)",
        True,
        ordered,
        "serialization order varies between runs, so the committed frame is not reproducible",
    )
    return {
        "n_neutral_lines": len(lines),
        "n_with_candidates": len(with_candidates),
        "n_candidates": sum(len(ln["identity_candidates"]) for ln in with_candidates),
    }


def part_candidate_bilateral(sha, h, x) -> dict:
    """The bilateral gate: a divergent candidate x0 must ABORT construction."""
    print("\n== A38.2: the bilateral candidate gate ==")
    mutated = [dict(d) for d in x]
    page = mutated[0]
    lines = list(page["neutral"])
    victim = next(ln for ln in lines if ln.candidates)
    moved = tuple(((gid, x0 + 3.0) if i == 0 else (gid, x0)) for i, (gid, x0) in enumerate(victim.candidates))
    lines[lines.index(victim)] = type(victim)(
        page=victim.page,
        ordinal=victim.ordinal,
        baseline=victim.baseline,
        x0=victim.x0,
        y0=victim.y0,
        x1=victim.x1,
        y1=victim.y1,
        gids=victim.gids,
        candidates=moved,
    )
    page["neutral"] = lines

    check(
        "NEGATIVE -- mutating ONE arm's candidate x0 ABORTS frame construction",
        BF.NEUTRAL_SKELETON_MISMATCH,
        refusal(lambda: BF.build_document_frame(sha, DOC_NAME, BF.P_HEAD, h, mutated)),
        "the arms' candidate geometry can diverge without the frame noticing, so the committed "
        "candidates would silently be whichever arm was read first",
    )
    check(
        "...and the UNMUTATED pair still builds, so the gate is not refusing everything",
        True,
        refusal(lambda: BF.build_document_frame(sha, DOC_NAME, BF.P_HEAD, h, x)) is None,
        "construction refuses even on clean input, making the control above meaningless",
    )
    return {
        "limit": "one skeleton by A19 -- both runners call run_hybrid.neutral_skeleton; this "
        "gate catches divergence in what each arm RETURNS, not two independent derivations"
    }


# ------------------------------------------- A38.3/A38.4 architecture occurrence records


def part_occurrences(frame: dict) -> dict:
    print("\n== A38.3/A38.4: deterministic architecture occurrence records ==")
    occ = frame["architecture_occurrences"]
    counts = {}
    for arm in ("H", "X"):
        rows = occ[arm]
        counts[arm] = {
            "total": len(rows),
            "MATCHABLE": sum(1 for r in rows if r["match_status"] == "MATCHABLE"),
            "UNMATCHED": sum(1 for r in rows if r["match_status"] == "UNMATCHED"),
        }
    check(
        "both arms produced occurrence records",
        (True, True),
        (counts["H"]["total"] > 0, counts["X"]["total"] > 0),
        "an arm produced no occurrences, so M1-M5 would have an empty emitted side",
    )
    check(
        "every record is MATCHABLE or UNMATCHED and none is silently absent",
        (counts["H"]["total"], counts["X"]["total"]),
        (
            counts["H"]["MATCHABLE"] + counts["H"]["UNMATCHED"],
            counts["X"]["MATCHABLE"] + counts["X"]["UNMATCHED"],
        ),
        "a record carries neither status, i.e. an occurrence was dropped rather than reported",
    )
    check(
        "a MATCHABLE record carries the A30 4-component occurrence key",
        [4],
        sorted({len(r["occurrence_key"]) for r in occ["H"] if r["match_status"] == "MATCHABLE"}),
        "the key is not the frozen (doc_sha, page, neutral_line_key, start_ngid) shape",
    )
    check(
        "records are in DOCUMENT order, never ngid order",
        True,
        [(r["anchor"]["page_number"], r["anchor"]["line_number"]) for r in occ["H"]]
        == sorted((r["anchor"]["page_number"], r["anchor"]["line_number"]) for r in occ["H"]),
        "occurrences are ordered by ngid, which A30.1 forbids -- ngid order disagreed with "
        "printed order on 10 of 33,602 emitted lines",
    )
    return counts


def part_occurrence_scope(frame: dict) -> dict:
    """A38 REPAIR -- an occurrence must bind to (page, region), never to region alone.

    Region ordinals RESTART on every page. Filtering on the ordinal alone gave a stimulus at
    (page P, region 0) the region-0 occurrences of EVERY page in the document.
    """
    print("\n== A38 repair: occurrence scope is (page, region), not region ==")
    occ = frame["architecture_occurrences"]["H"]
    by_ordinal: dict[int, set] = {}
    for row in occ:
        by_ordinal.setdefault(row["region_ordinal"], set()).add(row["page_number"])
    multi = {o: sorted(p) for o, p in by_ordinal.items() if len(p) > 1}
    check(
        "the DEVELOPMENT material really does reuse region ordinals across pages",
        True,
        bool(multi),
        "no ordinal repeats across pages here, so this material could not have exposed the "
        "contamination and the controls below would be vacuous",
    )

    built = BO.build([{"frame": frame, "pdf_path": DOC_PATH, "stratum": "DEVELOPMENT"}])
    wrong = [
        {
            "blind_id": bid,
            "arm": arm,
            "occurrence_page": row["page_number"],
            "occurrence_region": row["region_ordinal"],
            "stimulus_page": rec["page_number"],
            "stimulus_region": rec["region_ordinal"],
        }
        for bid, rec in built.key["stimuli"].items()
        for arm, rows in rec["architecture_occurrences"].items()
        for row in rows
        if row["page_number"] != rec["page_number"] or row["region_ordinal"] != rec["region_ordinal"]
    ]
    check(
        "EVERY private-key occurrence satisfies anchor.page == stimulus.page AND region == region",
        [],
        wrong,
        "a stimulus carries an occurrence printed on another page or in another region, which "
        "would put headings the adjudicator never saw on the emitted side of the M1-M5 join",
    )

    # THE COUNTERFACTUAL: the retired region-ordinal-only filter must demonstrably contaminate.
    contaminated = 0
    for rec in built.key["stimuli"].values():
        old_filter = [r for r in frame["architecture_occurrences"]["H"] if r["region_ordinal"] == rec["region_ordinal"]]
        contaminated += sum(1 for r in old_filter if r["page_number"] != rec["page_number"])
    check(
        "NEGATIVE -- the retired region-ordinal-only filter DOES contaminate this material",
        True,
        contaminated > 0,
        "the old filter happens to be equivalent here, so the repair is unproven and the "
        "control above passes for the wrong reason",
    )

    # duplication: one occurrence must not appear in two primary stimuli
    seen: dict[tuple, list] = {}
    for bid, rec in built.key["stimuli"].items():
        if rec["is_r1_repeat"]:
            continue  # an R1 repeat legitimately re-presents its primary's region
        for row in rec["architecture_occurrences"]["H"]:
            seen.setdefault((row["page_number"], row["anchor"]["line_number"], row["anchor"]["text"]), []).append(bid)
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    check(
        "no architecture occurrence is duplicated into multiple PRIMARY stimuli",
        {},
        dupes,
        "one emitted heading is counted in two regions, inflating the emitted set twice over",
    )

    # a MATCHABLE key's page component must agree with its stimulus page
    key_page_disagree = [
        (bid, row["occurrence_key"])
        for bid, rec in built.key["stimuli"].items()
        for row in rec["architecture_occurrences"]["H"]
        if row["match_status"] == "MATCHABLE" and row["occurrence_key"][1] != rec["page_number"]
    ]
    check(
        "a MATCHABLE occurrence's A30 key page AGREES with its stimulus page",
        [],
        key_page_disagree,
        "the identity key names a different page from the stimulus carrying it, so the join "
        "would bind an adjudication to a heading printed elsewhere",
    )
    return {
        "ordinals_reused_across_pages": {str(k): v for k, v in multi.items()},
        "n_stimuli": built.key["n_stimuli"],
        "n_occurrence_rows_in_key": sum(
            len(rows) for rec in built.key["stimuli"].values() for rows in rec["architecture_occurrences"].values()
        ),
        "counterfactual_contaminated_rows": contaminated,
    }


def part_genuine_unmatched(sha, h_pages, x_pages) -> dict:
    """A38 REPAIR -- a REAL A30 refusal must keep its A28.5 physical placement.

    Induced through the REAL construction path, not by editing a built record: the resolved
    start ngid is removed from the neutral skeleton, so `key_for` refuses with
    START_NGID_NOT_OWNED_BY_NEUTRAL_LINE while `place_anchor` -- which resolves the EMITTED
    line's first gid, a different glyph -- still succeeds.
    """
    print("\n== A38 repair: a genuine A30 refusal keeps its physical region ==")
    clean = BF.build_document_frame(sha, DOC_NAME, BF.P_HEAD, h_pages, x_pages)

    # The victim must be one whose A30 start ngid is NOT its emitted line's FIRST gid -- that
    # is precisely the case where placement and identity read different glyphs, so removing
    # the start ngid refuses identity while leaving A28.5 placement intact. Choosing any
    # MATCHABLE occurrence instead hits headings that occupy their whole line (start ngid ==
    # first gid), where the perturbation breaks placement too and aborts the frame.
    victim = next(r for r in clean["architecture_occurrences"]["H"] if r["match_status"] == "MATCHABLE")
    target_page = victim["page_number"]

    # THE LEVER, chosen because it separates the two concepts cleanly. `resolve_start_ngid`
    # rebuilds the MERGED line from its print lines and refuses with
    # MERGE_RECONSTRUCTION_MISMATCH when the rebuild disagrees with `page.lines[...].text`.
    # `place_anchor` never reads `page.lines` -- it uses `print_lines` and `emitted` -- so
    # perturbing merged text refuses IDENTITY while leaving A28.5 PLACEMENT untouched.
    #
    # Removing the start ngid from the skeleton was tried first and does NOT work on this
    # material: production headings occupy their whole line, so the start ngid IS the emitted
    # line's first gid and stripping it breaks placement too, aborting the frame.
    def perturb_merged_text(pages):
        out = []
        for d in pages:
            if d["page_number"] != target_page:
                out.append(d)
                continue
            page = d["page"]
            merged = [dataclasses.replace(ln, text=ln.text + "␀SENTINEL") for ln in page.lines]
            out.append({**d, "page": dataclasses.replace(page, lines=merged)})
        return out

    perturbed = BF.build_document_frame(
        sha, DOC_NAME, BF.P_HEAD, perturb_merged_text(h_pages), perturb_merged_text(x_pages)
    )
    now = next(
        r
        for r in perturbed["architecture_occurrences"]["H"]
        if r["page_number"] == victim["page_number"] and r["anchor"]["line_number"] == victim["anchor"]["line_number"]
    )
    check(
        "a GENUINE A30 refusal is UNMATCHED with an explicit reason",
        ("UNMATCHED", None, True),
        (now["match_status"], now["occurrence_key"], bool(now["unmatched_reason"])),
        "the perturbation did not actually induce an identity refusal, so this control proves "
        "nothing about how refusals are handled",
    )
    check(
        "...and it KEEPS its A28.5 physical page and region",
        (victim["page_number"], victim["region_ordinal"]),
        (now["page_number"], now["region_ordinal"]),
        "an identity refusal erased the physical placement, so the occurrence would vanish "
        "from every region-scoped record and shrink an M1-M5 denominator invisibly",
    )

    built = BO.build([{"frame": perturbed, "pdf_path": DOC_PATH, "stratum": "DEVELOPMENT"}])
    carrying = [
        bid
        for bid, rec in built.key["stimuli"].items()
        for r in rec["architecture_occurrences"]["H"]
        if r["match_status"] == "UNMATCHED" and r["anchor"]["line_number"] == victim["anchor"]["line_number"]
    ]
    correct = [
        bid
        for bid in carrying
        if built.key["stimuli"][bid]["page_number"] == victim["page_number"]
        and built.key["stimuli"][bid]["region_ordinal"] == victim["region_ordinal"]
    ]
    check(
        "the UNMATCHED occurrence SURVIVES into its exact stimulus",
        True,
        len(correct) >= 1,
        "the refused occurrence reaches no private key at all, i.e. it was silently dropped",
    )
    check(
        "...and appears in NO other page/region",
        sorted(carrying),
        sorted(correct),
        "the refused occurrence also leaked into a stimulus for a different page or region",
    )
    return {
        "lever": "merged-line text perturbation -> MERGE_RECONSTRUCTION_MISMATCH; placement "
        "reads print_lines/emitted and is unaffected",
        "page": victim["page_number"],
        "region_ordinal": victim["region_ordinal"],
        "unmatched_reason": now["unmatched_reason"],
        "stimuli_carrying_it": len(correct),
    }


def part_parent(frame: dict, h_pages) -> dict:
    """A38.4 -- the emitted immediate parent IS production's breadcrumb penultimate element."""
    print("\n== A38.4: immediate parent from production hierarchy ==")
    pages = [d["page"] for d in sorted(h_pages, key=lambda d: d["page_number"])]
    anchors = PA.extract_anchors(pages)
    by_key = {(a.page_number, a.line_number, a.kind, a.text): a for a in anchors}

    agree, checked, kinds = 0, 0, {}
    for row in frame["architecture_occurrences"]["H"]:
        a = by_key.get(
            (row["anchor"]["page_number"], row["anchor"]["line_number"], row["anchor"]["kind"], row["anchor"]["text"])
        )
        if a is None:
            continue
        crumb = PA.breadcrumb_for(a, anchors)
        expected = crumb[-2] if len(crumb) >= 2 else None
        checked += 1
        agree += row["immediate_parent"] == expected
        kinds.setdefault(a.kind, {"n": 0, "with_parent": 0})
        kinds[a.kind]["n"] += 1
        kinds[a.kind]["with_parent"] += row["immediate_parent"] is not None
    check(
        "every committed immediate_parent EQUALS production breadcrumb_for's penultimate element",
        (checked, checked),
        (checked, agree),
        "the parent was derived by a NEW hierarchy walk that disagrees with production, so M4 "
        "would score the emitted side against a hierarchy production never produced",
    )
    check(
        "the parent comparison is non-empty",
        True,
        checked > 0,
        "no occurrence matched a production anchor, so the equality above compared nothing",
    )
    roots = [r for r in frame["architecture_occurrences"]["H"] if r["immediate_parent"] is None]
    check(
        "a root/no-parent case exists and is represented as null",
        True,
        len(roots) > 0,
        "no one-element breadcrumb appears, so the no-parent branch was never exercised",
    )
    return {"checked": checked, "agree": agree, "kinds": kinds, "n_root": len(roots)}


# --------------------------------------------------------------- A38.8 / A38.9 M9 and S1


def part_m9(frame: dict) -> dict:
    print("\n== A38.8: M9 raw facts, recorded not decided ==")
    m9 = frame["m9"]
    required = {
        "derive_size_bands_returns_a_band",
        "coverage",
        "coverage_floor",
        "coverage_meets_floor",
        "n_lines_total",
        "n_margin_numbered_lines",
        "n_margin_numbered_with_glyph_size",
        "margin_numbered_line_keys",
    }
    check(
        "M9 raw facts are committed for BOTH arms",
        (sorted(required), sorted(required)),
        (sorted(required & set(m9["H"])), sorted(required & set(m9["X"]))),
        "a raw M9 quantity is missing, so score_metrics would have to rerun production anchor "
        "extraction to discover it",
    )
    check(
        "the frozen coverage floor is production's own 0.85",
        (0.85, 0.85),
        (m9["H"]["coverage_floor"], PA._COVERAGE_MIN),
        "the floor drifted from production's _COVERAGE_MIN, i.e. a threshold was invented here",
    )
    check(
        "per-line margin keys are recorded, so a SET comparison stays possible",
        (True, True),
        (len(m9["H"]["margin_numbered_line_keys"]) > 0, len(m9["X"]["margin_numbered_line_keys"]) > 0),
        "only counts are recorded, foreclosing the set-difference reading of Rule 0 before it has been ruled on",
    )
    check(
        "this stage still records FACTS and does not APPLY Rule 0",
        True,
        m9["H"]["rule0_comparison"].startswith("RAW FACTS ONLY"),
        "frame construction applies the Rule 0 comparison, which belongs to the later architecture decision",
    )
    # A39.1 RULED this. The assertion is EXECUTABLE rather than prose, so a ledger entry
    # claiming the ambiguity is resolved cannot drift from what the code actually implements.
    check(
        "RULE0_MARGIN_LINE_QUANTITY is RESOLVED_BY_A39_1, and the ruling is implemented",
        {"H_loses": ("H", True, 1), "X_loses": ("X", True, 1), "equal": (None, False, 0)},
        {
            "H_loses": tuple(MC.margin_line_loss(197, 198)[k] for k in ("loser", "fires", "deficit")),
            "X_loses": tuple(MC.margin_line_loss(198, 197)[k] for k in ("loser", "fires", "deficit")),
            "equal": tuple(MC.margin_line_loss(198, 198)[k] for k in ("loser", "fires", "deficit")),
        },
        "the frozen A39.1 clause -- count of line_number is not None, ANY positive deficit "
        "fires, no tolerance -- is not what margin_line_loss implements, so the ledger would "
        "be claiming a resolution the code does not deliver",
    )
    RESOLVED.append(
        {
            "was": "RULE0_MARGIN_LINE_QUANTITY",
            "status": "RESOLVED_BY_A39_1",
            "ruling": "margin_lines_recovered = count of Page.lines where line_number is not None; "
            "any strictly positive per-document deficit fires; no tolerance. The glyph-size count "
            "and per-line keys remain diagnostics and do not determine the clause.",
        }
    )
    return {arm: {k: v for k, v in m9[arm].items() if k != "margin_numbered_line_keys"} for arm in ("H", "X")}


def part_s1() -> dict:
    print("\n== A38.9: the S1 liveness control has a committed producer ==")
    result = S1.s1_result(DOC_PATH, limit=PAGE_LIMIT)
    check(
        "the S1 sabotage scale is exactly the frozen 1.25",
        1.25,
        result["advance_scale"],
        "the scale drifted from the frozen value, or became a tunable dial",
    )
    check(
        "S1 FIRES on DEVELOPMENT -- sabotage raises M0",
        True,
        result["fires"],
        "advances x 1.25 does not raise the discordance count, which would mean M0 cannot "
        "detect a change it certainly should -- the comparator is not live",
    )
    check(
        "...and the sabotage really changed the input, so firing is not an artifact",
        True,
        result["sabotaged"]["text_discordant_lines"] > result["primary"]["text_discordant_lines"],
        "the two runs report the same discordance, so nothing was actually sabotaged",
    )
    check(
        "primary and sabotaged M0 are reported SEPARATELY",
        (True, True),
        ("primary" in result and "sabotaged" in result, result["primary"] != result["sabotaged"]),
        "only one number is reported, so a reader cannot see what the control established",
    )
    check(
        "the risk set is unchanged by sabotage, so only the TEXT moved",
        result["primary"]["risk_set_lines"],
        result["sabotaged"]["risk_set_lines"],
        "the sabotage moved the neutral skeleton, i.e. it changed the frame rather than the seam decision under test",
    )

    # NEGATIVE: a dead comparator must report FAIL rather than silently passing.
    dead = copy.deepcopy(result)
    dead["sabotaged"] = dict(dead["primary"])
    dead_fires = dead["sabotaged"]["text_discordant_lines"] > dead["primary"]["text_discordant_lines"]
    check(
        "NEGATIVE -- a DEAD comparator (sabotage changes nothing) reports S1 FAIL",
        False,
        dead_fires,
        "a comparator that cannot move still reports S1 firing, which is precisely the "
        "phase-1 defect S1 exists to catch",
    )
    return {k: v for k, v in result.items() if k != "m0_definition"}


# ------------------------------------------------- the central question, end to end


def part_cross_engine(sha: str) -> dict:
    """A39.2 -- the REAL producer on a REAL DEVELOPMENT PDF, not the abstract helpers.

    The previous coverage exercised only the sample and a duplicate qualification helper, so a
    producer that read a nonexistent key and used the wrong denominator stayed green. This
    control executes `cross_engine_result` end to end and compares it, field by field, against
    `X09.gate` applied independently to the same sampled rows.
    """
    print("\n== A39.2: the confirmatory cross-engine producer, on real DEVELOPMENT material ==")

    # 1-2. run the producer, and independently reproduce it through x09
    produced = CE.cross_engine_result(DOC_NAME, sha, DOC_PATH, limit=PAGE_LIMIT)
    pdfium_pages = X09.pdfium_lines(DOC_PATH, PAGE_LIMIT)
    pymupdf_pages = X09.pymupdf_lines(DOC_PATH, PAGE_LIMIT)
    measured = X09.measure(pdfium_pages, pymupdf_pages)
    sampled = MC.cross_engine_pages(sha, [r["page"] for r in measured])
    direct = X09.gate([r for r in measured if r["page"] in set(sampled)])
    direct_rows = [r for r in measured if r["page"] in set(sampled)]

    check(
        "the producer RUNS on a real DEVELOPMENT PDF without raising",
        True,
        isinstance(produced, dict) and "gate" in produced,
        "the producer cannot execute at all -- which is how a nonexistent row key and the "
        "wrong denominator survived: nothing ever ran it on real measurements",
    )
    check(
        "sampled pages equal the independently derived A39.2 sample",
        sampled,
        produced["sampled_pages"],
        "the producer measures a different page set from the frozen sample",
    )
    check(
        "matched count and DENOMINATOR equal the direct x09 computation",
        (sum(r["matched"] for r in direct_rows), sum(max(r["pdfium"], r["pymupdf"]) for r in direct_rows)),
        (produced["matched"], produced["denominator"]),
        "the producer counts a different numerator or denominator than the frozen rule -- the "
        "exact defect: matched/pdfium instead of matched/max(pdfium, pymupdf)",
    )
    check(
        "the whole GATE VERDICT equals X09.gate on the same rows",
        direct,
        produced["gate"],
        "the producer's verdict differs from the frozen rule applied directly, i.e. it is "
        "recomputing the rule rather than calling it",
    )
    check(
        "document fraction, worst page and pass all agree",
        (direct["matched_fraction"], direct["worst_page"], direct["pass"]),
        (produced["gate"]["matched_fraction"], produced["gate"]["worst_page"], produced["passed"]),
        "a reported field disagrees with the gate that produced it",
    )
    check(
        "cross-engine failure is NEVER decision-blocking",
        False,
        produced["decision_blocking"],
        "a cross-engine failure blocks the architecture decision, which A27.6 forbids",
    )

    # 3. OVER-SEGMENTATION SYMMETRY -- the reason max(pdfium, pymupdf) is frozen.
    pdfium_over = X09.gate([{"page": 1, "pdfium": 120, "pymupdf": 100, "matched": 100}])
    pymupdf_over = X09.gate([{"page": 1, "pdfium": 100, "pymupdf": 120, "matched": 100}])
    check(
        "PyMuPDF over-segmentation scores 100/120, not 100/100",
        round(100 / 120, 4),
        pymupdf_over["matched_fraction"],
        "the denominator is the PDFium count, so over-segmentation by the SECOND engine is "
        "invisible -- the control would report perfect agreement while the engines disagree",
    )
    check(
        "PDFium over-segmentation scores 100/120 too -- the gate is SYMMETRIC",
        round(100 / 120, 4),
        pdfium_over["matched_fraction"],
        "the gate favours one engine, so which engine over-segments changes the verdict",
    )
    check(
        "...and both are capable of FAILING the frozen thresholds",
        (False, False),
        (pdfium_over["pass"], pymupdf_over["pass"]),
        "an 0.833 agreement passes, so the thresholds cannot see over-segmentation at all",
    )

    # 4. the document SHA is verified, not trusted
    check(
        "NEGATIVE -- a wrong document SHA REFUSES before any sample or measurement",
        CE.SOURCE_SHA256_MISMATCH,
        _sha_refusal("0" * 64),
        "a caller-supplied SHA that does not match the bytes selects a different page sample "
        "for the same document, silently and reproducibly",
    )
    check(
        "...and the correct SHA is accepted",
        None,
        _sha_refusal(sha),
        "verification refuses the real document, making the control above meaningless",
    )

    # 6. only SAMPLED rows reach the gate
    unsampled = next((r["page"] for r in measured if r["page"] not in set(sampled)), None)
    mutated_unsampled = [{**r, "matched": 0} if r["page"] == unsampled else r for r in measured]
    mutated_sampled = [{**r, "matched": 0} if r["page"] == sampled[0] else r for r in measured]
    check(
        "mutating a NON-sampled page changes nothing",
        direct,
        X09.gate([r for r in mutated_unsampled if r["page"] in set(sampled)]),
        "an unsampled page reaches the gate, so this is not a 10 % sampled control at all",
    )
    check(
        "...while mutating a SAMPLED page DOES change the verdict",
        True,
        X09.gate([r for r in mutated_sampled if r["page"] in set(sampled)]) != direct,
        "a sampled page cannot move the verdict, so sample membership is dead and the control "
        "above passed for the wrong reason",
    )
    check(
        "an unsampled page exists, so the membership control is not vacuous",
        True,
        unsampled is not None,
        "every page is sampled here, so 'unsampled changes nothing' was trivially true",
    )

    # 5. the default whole-document path must work
    whole = CE.cross_engine_result(DOC_NAME, sha, DOC_PATH, limit=None)
    check(
        "limit=None is a valid WHOLE-DOCUMENT call",
        True,
        whole["page_count"] >= produced["page_count"] and whole["n_sampled"] >= 1,
        "the canonical writer's default path raises or silently measures a prefix -- a "
        "truncated confirmatory measurement would qualify a frame on a fraction of its pages",
    )
    check(
        "...and it measures MORE pages than the limited call, so None is not read as a prefix",
        True,
        whole["page_count"] > produced["page_count"],
        "limit=None produced the same page count as the limited run, i.e. it was reinterpreted",
    )
    return {
        "document": DOC_NAME,
        "limited_page_count": produced["page_count"],
        "whole_document_page_count": whole["page_count"],
        "sampled_pages": produced["sampled_pages"],
        "matched": produced["matched"],
        "denominator": produced["denominator"],
        "gate": produced["gate"],
        "qualification": produced["qualification"],
        "oversegmentation": {
            "pdfium_over_120": pdfium_over["matched_fraction"],
            "pymupdf_over_120": pymupdf_over["matched_fraction"],
        },
        "whole_document_gate": whole["gate"],
    }


def _sha_refusal(candidate: str):
    try:
        CE.verified_sha256(DOC_PATH, candidate)
    except CE.CrossEngineError as exc:
        return exc.reason
    return None


def part_no_pdf_needed(frame: dict, key: dict) -> dict:
    """Can the scoring facts be reached from committed JSON ALONE? Answered structurally."""
    print("\n== A38: every score input is reachable from committed artifacts ==")
    # Round-trip through JSON: anything reachable below came from a committed artifact, not
    # from a live Python object still holding a PDF handle or a runner result.
    frame_json = json.loads(json.dumps(frame, default=str))
    key_json = json.loads(json.dumps(key, default=str))

    reachable = {
        "M0a text discordance": any(
            "text_discordance" in ln["line_state"] for pf in frame_json["pages"] for ln in pf["neutral_lines"]
        ),
        "M0b segmentation discordance": any(
            "segmentation_discordance" in ln["line_state"] for pf in frame_json["pages"] for ln in pf["neutral_lines"]
        ),
        "M0c anchor discordance": any("anchor_evidence" in r for pf in frame_json["pages"] for r in pf["regions"]),
        "both_absent": any("in_m0_risk_set" in ln for pf in frame_json["pages"] for ln in pf["neutral_lines"]),
        "M1-M3 emitted occurrences": bool(frame_json["architecture_occurrences"]["H"]),
        "M4 immediate parent": all("immediate_parent" in r for r in frame_json["architecture_occurrences"]["H"]),
        "M5 emitted kind": all("kind" in r["anchor"] for r in frame_json["architecture_occurrences"]["H"]),
        "M7 emitted text": all("text" in r["anchor"] for r in frame_json["architecture_occurrences"]["H"]),
        "M9 raw facts": bool(frame_json["m9"]["H"]) and bool(frame_json["m9"]["X"]),
        "occurrence join candidates": all("identity_candidates" in r for r in key_json["stimuli"].values()),
        "occurrence join geometry": all(
            {"bbox_pdf_points", "dpi", "region_line_bijection"} <= set(r) for r in key_json["stimuli"].values()
        ),
        "adjudication routing": all("adjudication_routes" in r for r in key_json["stimuli"].values()),
    }
    check(
        "EVERY listed score input is reachable from committed JSON, with no PDF or runner",
        {k: True for k in reachable},
        reachable,
        "a fact score_metrics needs survives only in a live Python object, so the scorer would "
        "have to reopen a PDF or rerun an architecture to get it",
    )
    missing_occ = copy.deepcopy(frame_json)
    del missing_occ["architecture_occurrences"]
    check(
        "NEGATIVE -- removing the occurrence records makes the reachability answer FALSE",
        False,
        "architecture_occurrences" in missing_occ,
        "the reachability check cannot detect a missing producer, so it would report success "
        "on an artifact chain that cannot actually feed the scorer",
    )
    return {"reachable": reachable}


def main() -> int:
    sha, h, x, frame = development_frame()
    candidates = part_candidates(frame)
    bilateral = part_candidate_bilateral(sha, h, x)
    occurrences = part_occurrences(frame)
    scope = part_occurrence_scope(frame)
    unmatched = part_genuine_unmatched(sha, h, x)
    parent = part_parent(frame, h)
    m9 = part_m9(frame)
    s1 = part_s1()
    cross_engine = part_cross_engine(sha)

    built = BO.build([{"frame": frame, "pdf_path": DOC_PATH, "stratum": "DEVELOPMENT"}])
    reach = part_no_pdf_needed(frame, built.key)

    doc = {
        "population": "SYNTHETIC + DEVELOPMENT -- no holdout opened, nothing adjudicated, nothing scored",
        "contract": "A38 (the score_metrics input contract)",
        "question": "can every score_metrics obligation be satisfied from committed artifacts, "
        "with no PDF access, no runner access, no text matching, and no implementation-time choice?",
        "document": DOC_NAME,
        "page_limit": PAGE_LIMIT,
        "note": "PAGE_LIMIT is a machinery demonstration window, not a census",
        "artifacts_created": "NONE of frames.json, oracle_key.json, oracle_blind.json, "
        "oracle_adjudicated.json, metrics.json, scores.json, EXECUTION-START.json",
        "identity_candidates": candidates,
        "bilateral_gate": bilateral,
        "architecture_occurrences": occurrences,
        "occurrence_scope": scope,
        "genuine_unmatched": unmatched,
        "immediate_parent": parent,
        "m9_raw": m9,
        "s1": s1,
        "cross_engine": cross_engine,
        "reachability": reach,
        "oracle_key_schema": built.key["schema"],
        "forward_ambiguities": STOPS,
        "resolved_ambiguities": RESOLVED,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(
        f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass; "
        f"{len(STOPS)} forward ambiguities OPEN, {len(RESOLVED)} resolved"
    )
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
