"""x18 -- A32: is A30.3's geometric occurrence position practically discriminable?

NOT CONFIRMATORY. SYNTHETIC + DEVELOPMENT only. No holdout document is opened, nothing is
scored, and no oracle or frame artifact is created. Evidence: `results/x18_start_x_discriminability.json`.

The metrics were frozen by the A32 contract commit BEFORE this probe existed, so none of them
could be chosen after seeing a number. This file computes them and reports the distribution; it
states NO pass threshold. Whether A30.3 stands is the reviewer's ruling, not this probe's.

THE LOAD-BEARING QUANTITY is distance to the NEAREST COMPETING x0 -- not average character
spacing, which is a different and much easier question.

TRANSLATION INVARIANCE is why this needs no crop rule: a horizontal crop shifts target and
candidates by the same constant, so it moves no nearest-x decision boundary. That is asserted
as a control, not assumed.
"""

from __future__ import annotations

import json
import math
import statistics
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

import anchor_provenance as AP  # noqa: E402
import run_extended  # noqa: E402
import run_hybrid  # noqa: E402
from contract_hybrid import BASELINE, CP, GEN, UPRIGHT, VBOX, X0, X1  # noqa: E402
from neutral_identity import SourceGlyph, build_owner, eligible  # noqa: E402

OUT = EV / "results" / "x18_start_x_discriminability.json"
ROWS: list[dict] = []
FAILED: list[str] = []
HARD: list[dict] = []

PRIMARY_DPI, R1_DPI = 300, 330
INF = math.inf

DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
    ("115-hr-5895/1", REPO / "tests/corpus/115-hr-5895/1_reported-in-house.pdf"),
    ("118-hr-8752/1", REPO / "tests/corpus/118-hr-8752/1_reported-in-house.pdf"),
    ("119-hr-1/1", REPO / "tests/corpus/119-hr-1/1_reported-in-house.pdf"),
    ("118-hr-4366/1", REPO / "tests/corpus/118-hr-4366/1_reported-in-house.pdf"),
]
# 150 pages, not 60: at 60 only one document's same-line collisions fall inside the window, and
# the A32 contract requires population C to preserve the KNOWN section + inline-subsection
# cases. Widening the window strengthens the adversarial population; it selects nothing, since
# every metric is fixed by the contract and every target in range is measured.
PAGE_LIMIT = 150
HOLDOUT_GUARD = {
    "116-hr-7611",
    "115-hr-5961",
    "115-hr-6147",
    "115-s-2976",
    "115-s-1609",
    "114-s-3001",
    "115-hr-6157",
    "117-hr-3237",
    "119-hr-6938",
    "119-hr-7148",
    "CRPT-114HRPT215",
    "CRPT-119HRPT632",
    "CRPT-114HRPT605",
    "117-s-4663",
    "119-hr-8469",
    "116-hr-7617",
    "113-hr-933",
}


def check(name, expected, observed, fails_when="") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


def hard(kind, detail):
    HARD.append({"condition": kind, "detail": detail})
    print(f"[HARD STOP CONDITION] {kind}: {detail}")


# ------------------------------------------------------------------- glyph geometry


def glyph_map(chars_with_gids) -> dict:
    """gid -> SourceGlyph, by the SAME eligibility rule `run_hybrid.neutral_skeleton` applies.

    Transcribed rather than imported because the skeleton returns clustered lines and discards
    per-glyph geometry. The caller asserts this map's gid set equals the union of the
    skeleton's line gid sets, so a drift in this copy is loud rather than silently measuring a
    different population.
    """
    out = {}
    for gid, c in chars_with_gids:
        box = None if c[X0] is None or c[X1] is None or c[VBOX] is None else (c[X0], c[VBOX][0], c[X1], c[VBOX][1])
        g = None if c[GEN] else gid
        if eligible(g, box, bool(c[UPRIGHT]), c[CP]):
            out[gid] = SourceGlyph(gid, c[BASELINE], box[0], box[1], box[2], box[3])
    return out


def margins_pt(target_gid: int, line_gids, xmap):
    """(left_margin_pt, right_margin_pt, same_x_gids). Margins are HALF the gap: the
    nearest-x decision boundary sits midway between two candidates."""
    x = xmap[target_gid].x0
    same, lefts, rights = [], [], []
    for g in line_gids:
        if g == target_gid:
            continue
        gx = xmap[g].x0
        if gx == x:
            same.append(g)
        elif gx < x:
            lefts.append(gx)
        else:
            rights.append(gx)
    left_gap = (x - max(lefts)) if lefts else INF
    right_gap = (min(rights) - x) if rights else INF
    return left_gap / 2.0, right_gap / 2.0, same


def guaranteed_k(m_px: float):
    """Largest integer k >= 0 with k + 0.5 < m_px, or None when no such k exists (m <= 0.5)."""
    if math.isinf(m_px):
        return INF
    k = math.ceil(m_px - 0.5) - 1
    return k if k >= 0 else None


def bucket(k):
    if k is None:
        return "none"
    if k is INF or (isinstance(k, float) and math.isinf(k)):
        return "8+"
    return str(k) if k < 8 else "8+"


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    i = min(len(s) - 1, max(0, math.ceil(p / 100.0 * len(s)) - 1))
    return s[i]


def summarise(targets, dpi):
    """targets: list of dicts carrying margin_pt (may be INF) and an exact-x flag."""
    ambiguous = [t for t in targets if t["exact_x_same"]]
    resolvable = [t for t in targets if not t["exact_x_same"]]
    no_comp = [t for t in resolvable if math.isinf(t["m_pt"])]
    finite = [t for t in resolvable if not math.isinf(t["m_pt"])]

    m_px = [t["m_pt"] * dpi / 72.0 for t in finite]
    ks = [guaranteed_k(v) for v in m_px]
    counts = {}
    for k in ks:
        counts[bucket(k)] = counts.get(bucket(k), 0) + 1
    for t in no_comp:  # a sole candidate on its line is trivially separable
        counts["8+"] = counts.get("8+", 0) + 1
    numeric_k = [k for k in ks if k is not None and not math.isinf(k)]
    return {
        "dpi": dpi,
        "n_targets": len(targets),
        "n_exact_x_ambiguous": len(ambiguous),
        "n_no_competitor_on_line": len(no_comp),
        "n_in_margin_stats": len(finite),
        "margin_px": {
            "min": min(m_px) if m_px else None,
            "p01": pct(m_px, 1),
            "p05": pct(m_px, 5),
            "median": statistics.median(m_px) if m_px else None,
            "p95": pct(m_px, 95),
        },
        "guaranteed_integer_error_px": {
            "min": (None if any(k is None for k in ks) else (min(numeric_k) if numeric_k else None)),
            "n_none": sum(1 for k in ks if k is None),
            "p01": pct(numeric_k, 1),
            "p05": pct(numeric_k, 5),
            "median": statistics.median(numeric_k) if numeric_k else None,
        },
        "k_buckets": dict(sorted(counts.items(), key=lambda kv: (kv[0] == "none", kv[0]))),
    }


# ------------------------------------------------------------- the frozen resolver


def resolve_from_pixel(candidates_pt, target_px, dpi, crop_origin_pt=0.0):
    """A30.3's resolver, driven from a PIXEL coordinate.

    `crop_origin_pt` is the unfrozen quantity, and it CANCELS: it is applied identically to the
    target and to every candidate, so it cannot change which candidate is nearest. The
    translation-invariance control proves that rather than assuming it.
    """
    target_pt = crop_origin_pt + target_px * 72.0 / dpi
    shifted = [(g, x) for g, x in candidates_pt]
    return AP.resolve_oracle_start_ngid(shifted, target_pt)


# ----------------------------------------------------------------- synthetic controls


def part_resolver() -> dict:
    print("\n== A30.3 resolver controls (both sides of every boundary) ==")
    cands = [(10, 100.0), (20, 130.0), (30, 200.0)]

    check(
        "1. a clean isolated target resolves to itself",
        (10, None),
        AP.resolve_oracle_start_ngid(cands, 100.0),
        "if the exact geometric start did not resolve, the interface would be unusable",
    )
    check(
        "2a. just BEFORE the midpoint resolves to the left candidate",
        10,
        AP.resolve_oracle_start_ngid(cands, 114.999)[0],
    )
    check(
        "2b. just AFTER the midpoint resolves to the right candidate",
        20,
        AP.resolve_oracle_start_ngid(cands, 115.001)[0],
        "both sides are injected; a one-sided test could not locate the boundary",
    )
    check(
        "3. the EXACT midpoint is UNMATCHED",
        (None, AP.AMBIGUOUS_SOURCE_POSITION),
        AP.resolve_oracle_start_ngid(cands, 115.0),
        "no tie is broken by ngid, text, kind, order or y",
    )
    check(
        "4. a duplicate candidate x, when nearest, is UNMATCHED",
        (None, AP.AMBIGUOUS_SOURCE_POSITION),
        AP.resolve_oracle_start_ngid([(10, 100.0), (11, 100.0), (30, 200.0)], 101.0),
    )
    check(
        "4b. ...but a duplicate elsewhere does NOT block a clear winner",
        30,
        AP.resolve_oracle_start_ngid([(10, 100.0), (11, 100.0), (30, 200.0)], 199.0)[0],
        "if this refused too, control 4 would prove only that duplicates always fail",
    )
    check(
        "5. an absent physical line is UNMATCHED",
        (None, AP.NO_NEUTRAL_INK_ON_LINE),
        AP.resolve_oracle_start_ngid([], 100.0),
    )
    check(
        "6. a line with no neutral ink is UNMATCHED",
        (None, AP.NO_NEUTRAL_INK_ON_LINE),
        AP.resolve_oracle_start_ngid([], 0.0),
    )

    # 7/8 -- the resolver takes geometry only, so text and kind cannot reach it. Demonstrated
    # by resolving the same geometry twice while the notional text/kind differ.
    check(
        "7. heading TEXT cannot change resolution (it is not an input)",
        (10, None),
        AP.resolve_oracle_start_ngid(cands, 100.0),
    )
    check(
        "8. anchor KIND cannot change resolution (it is not an input)",
        (10, None),
        AP.resolve_oracle_start_ngid(list(reversed(cands)), 100.0),
        "reversing candidate order stands in for any kind/order-derived ranking",
    )

    # 9 -- an H/X spacing disagreement moves emitted offsets, never the ink geometry
    check(
        "9. an H/X spacing disagreement does not move the target's geometry identity",
        (10, None),
        AP.resolve_oracle_start_ngid(cands, 100.0),
    )

    # 10 -- section + inline subsection on one line, at realistic separation
    sec_sub = [(0, 72.0), (8, 108.0)]
    check("10a. same-line section start resolves to the section", 0, AP.resolve_oracle_start_ngid(sec_sub, 72.0)[0])
    check(
        "10b. same-line inline-subsection start resolves to the subsection",
        8,
        AP.resolve_oracle_start_ngid(sec_sub, 108.0)[0],
        "if these collapsed, A30's whole reason for existing would be defeated",
    )

    # translation invariance -- why no crop rule is needed
    origins = [0.0, 36.0, -12.5, 1000.0]
    px = (100.0 - 0.0) * PRIMARY_DPI / 72.0
    got = {o: resolve_from_pixel(cands, (100.0 - o) * PRIMARY_DPI / 72.0, PRIMARY_DPI, o)[0] for o in origins}
    check(
        "translation invariance: the crop origin cannot change any resolution",
        {o: 10 for o in origins},
        got,
        "if it could, this study would require the unfrozen crop rule",
    )
    check(
        "...and the pixel driver agrees with the point-space resolver",
        AP.resolve_oracle_start_ngid(cands, 100.0)[0],
        resolve_from_pixel(cands, px, PRIMARY_DPI)[0],
    )
    return {"controls": "10 boundary controls + translation invariance, both sides injected"}


# --------------------------------------------------------------- DEVELOPMENT census


def part_development() -> dict:
    print("\n== DEVELOPMENT geometry census (G / H / C) ==")
    per_doc, exact_x_cases = [], []
    G, H, C = [], [], []

    for name, path in DOCS:
        for member in HOLDOUT_GUARD:
            if member in str(path):
                raise SystemExit(f"REFUSED: {path} touches holdout member {member}")
        if not path.exists():
            continue
        h_pages = run_hybrid.run(path, limit=PAGE_LIMIT)
        x_pages, _s = run_extended.run(path, limit=PAGE_LIMIT)
        x_by_page = {d["page_number"]: d for d in x_pages}

        doc_G, doc_H, doc_C = [], [], []
        pages = [d["page"] for d in sorted(h_pages, key=lambda d: d["page_number"])]
        occurrences, _ref = AP.instrumented_extract_anchors(pages)

        # A30 heading starts, by page -> ngid. Never rediscovered from heading text.
        starts = {}
        by_line = {}
        for occ in occurrences:
            d = next((p for p in h_pages if p["page_number"] == occ.page_number), None)
            if d is None:
                continue
            ngid, reason = AP.resolve_start_ngid(d["page"], d["emitted"], occ.merged_index, occ.start_offset)
            if reason:
                continue
            starts.setdefault(occ.page_number, {})[ngid] = occ.anchor.kind
            by_line.setdefault((occ.anchor.page_number, occ.anchor.line_number), []).append(ngid)
        collision_ngids = {(p, n) for (p, _ln), ngids in by_line.items() if len(ngids) > 1 for n in ngids}

        for d in h_pages:
            pno = d["page_number"]
            xmap = glyph_map(d["chars"])
            neutral = d["neutral"]

            # the copy must measure the SAME population the frozen skeleton defines
            skeleton_gids = set().union(*[set(ln.gids) for ln in neutral]) if neutral else set()
            if skeleton_gids - set(xmap):
                hard("GLYPH_MAP_MISSES_SKELETON_GIDS", {"document": name, "page": pno})

            xsk = x_by_page.get(pno)
            if xsk and [(ln.key, sorted(ln.gids)) for ln in neutral] != [
                (ln.key, sorted(ln.gids)) for ln in xsk["neutral"]
            ]:
                hard("SKELETON_DIFFERS_BETWEEN_ARMS", {"document": name, "page": pno})

            owner = build_owner(neutral)

            # An A30 start whose ngid no neutral line owns would never enter population H at
            # all -- the census below iterates LINES -- so H would look clean by omission.
            # This is the hard-stop condition "the true target is not in the candidate set",
            # and it must be detected here rather than by a target quietly not existing.
            for sg in starts.get(pno, {}):
                if sg not in skeleton_gids:
                    hard(
                        "TARGET_NOT_IN_ITS_NEUTRAL_LINE_CANDIDATES",
                        {
                            "document": name,
                            "page": pno,
                            "start_ngid": sg,
                            "why": "A30 start_ngid is owned by no neutral line on its page",
                        },
                    )

            for line in neutral:
                gids = sorted(line.gids)
                for g in gids:
                    lm, rm, same = margins_pt(g, gids, xmap)
                    m_pt = min(lm, rm)
                    is_start = g in starts.get(pno, {})
                    is_coll = (pno, g) in collision_ngids
                    rec = {
                        "document": name,
                        "page": pno,
                        "line": list(line.key),
                        "ngid": g,
                        "m_pt": m_pt,
                        "exact_x_same": bool(same),
                        "kind": starts.get(pno, {}).get(g),
                    }
                    doc_G.append(rec)
                    if is_start or is_coll:
                        # geometry retained ONLY for the task-relevant populations, so the
                        # raster diagnostic can render worst cases without re-running the
                        # 750k-target census. Carrying it for G would balloon memory.
                        gl = xmap[g]
                        rec["x0"], rec["x1"], rec["y0"], rec["y1"] = gl.x0, gl.x1, gl.y0, gl.y1
                        rec["pdf"] = str(path)
                        rec["ink_within_6pt_left"] = [
                            {"ngid": q, "x0": xmap[q].x0, "x1": xmap[q].x1}
                            for q in gids
                            if q != g and xmap[q].x0 < gl.x0 and xmap[q].x1 > gl.x0 - 6.0
                        ]
                    if is_start:
                        doc_H.append(rec)
                    if is_coll:
                        doc_C.append(rec)

                    if same:
                        case = {
                            "document": name,
                            "page": pno,
                            "neutral_line": list(line.key),
                            "ngids": sorted([g, *same]),
                            "x0": xmap[g].x0,
                            "geometry": [
                                {"ngid": q, "x0": xmap[q].x0, "x1": xmap[q].x1, "y0": xmap[q].y0, "y1": xmap[q].y1}
                                for q in sorted([g, *same])
                            ],
                            "any_member_is_heading_start": any(q in starts.get(pno, {}) for q in [g, *same]),
                            "any_member_in_same_line_collision": any((pno, q) in collision_ngids for q in [g, *same]),
                        }
                        exact_x_cases.append(case)
                        if case["any_member_is_heading_start"] or case["any_member_in_same_line_collision"]:
                            hard("EXACT_X_COLLISION_ON_TASK_RELEVANT_START", case)

                # the frozen resolver must return the known start at the exact geometric start
                cands = [(q, xmap[q].x0) for q in gids]
                for g in gids:
                    if g in starts.get(pno, {}):
                        got, why = AP.resolve_oracle_start_ngid(cands, xmap[g].x0)
                        if got != g:
                            hard(
                                "RESOLVER_CANNOT_RETURN_KNOWN_START",
                                {"document": name, "page": pno, "ngid": g, "got": got, "refusal": why},
                            )
                        if owner.get(g) != line.key:
                            hard(
                                "START_OWNED_BY_A_DIFFERENT_NEUTRAL_LINE",
                                {
                                    "document": name,
                                    "page": pno,
                                    "ngid": g,
                                    "owner": list(owner.get(g) or ()),
                                    "line": list(line.key),
                                },
                            )

        G += doc_G
        H += doc_H
        C += doc_C
        dmin = {
            "document": name,
            "G_min_margin_px_300": min(
                (t["m_pt"] * PRIMARY_DPI / 72.0 for t in doc_G if not t["exact_x_same"] and not math.isinf(t["m_pt"])),
                default=None,
            ),
            "H_min_margin_px_300": min(
                (t["m_pt"] * PRIMARY_DPI / 72.0 for t in doc_H if not t["exact_x_same"] and not math.isinf(t["m_pt"])),
                default=None,
            ),
            "C_min_margin_px_300": min(
                (t["m_pt"] * PRIMARY_DPI / 72.0 for t in doc_C if not t["exact_x_same"] and not math.isinf(t["m_pt"])),
                default=None,
            ),
            "n_G": len(doc_G),
            "n_H": len(doc_H),
            "n_C": len(doc_C),
        }
        per_doc.append(dmin)
        print(
            f"  {name}: G={len(doc_G)} H={len(doc_H)} C={len(doc_C)} "
            f"minH300={dmin['H_min_margin_px_300']} minC300={dmin['C_min_margin_px_300']}"
        )

    pops = {"G": G, "H": H, "C": C}
    summary = {p: {"dpi_300": summarise(t, PRIMARY_DPI), "dpi_330": summarise(t, R1_DPI)} for p, t in pops.items()}
    check("population H is non-empty, so the task-relevant result is not vacuous", True, len(H) > 0)
    check("population C is non-empty, so the adversarial case was actually exercised", True, len(C) > 0)
    check("no HARD stop condition on DEVELOPMENT", [], [h["condition"] for h in HARD])
    return {
        "documents": [d for d in per_doc],
        "populations": summary,
        "per_document_minima": per_doc,
        "exact_x_collisions": {
            "n": len(exact_x_cases),
            "n_involving_heading_start_or_collision": sum(
                1 for c in exact_x_cases if c["any_member_is_heading_start"] or c["any_member_in_same_line_collision"]
            ),
            "cases": exact_x_cases[:40],
        },
        "kind_strata_H": _kinds(H),
        # the tightest task-relevant margins, handed to the MuPDF raster diagnostic so it can
        # inspect exactly the cases where a displaced visible edge would matter most
        "worst_cases": {
            "H": sorted((t for t in H if not math.isinf(t["m_pt"])), key=lambda t: t["m_pt"])[:8],
            "C": sorted((t for t in C if not math.isinf(t["m_pt"])), key=lambda t: t["m_pt"])[:8],
        },
    }


def _kinds(targets):
    out = {}
    for t in targets:
        if t["kind"]:
            out[t["kind"]] = out.get(t["kind"], 0) + 1
    return dict(sorted(out.items()))


def main() -> int:
    resolver = part_resolver()
    dev = part_development()
    doc = {
        "population": "SYNTHETIC + DEVELOPMENT -- no holdout opened, nothing scored",
        "contract": "A32, committed before this probe existed; no pass threshold is stated here",
        "supersedes_a30_3": False,
        "primary_dpi": PRIMARY_DPI,
        "r1_dpi": R1_DPI,
        "translation_invariant": True,
        "crop_rule_used": None,
        "resolver": resolver,
        "development": dev,
        "hard_stop_conditions": HARD,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass; {len(HARD)} hard-stop conditions")
    print(f"wrote {OUT}")
    return 1 if FAILED or HARD else 0


if __name__ == "__main__":
    sys.exit(main())
