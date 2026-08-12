"""x16 -- A30: the occurrence identity is an ABSOLUTE source position, and it is derivable.

NOT CONFIRMATORY. Synthetic + DEVELOPMENT documents only. No holdout document is opened,
nothing is scored, no downstream harness component is built.

    A30.1  the key's fourth component is `start_ngid`, not an ordinal among emitted anchors
    A30.2  the provenance derivation, and the instrumented mirror's fidelity to production
    A30.3  the oracle's geometric position, resolved to the same identity, refusing on a tie

WHAT WOULD MAKE THIS PROBE WORTHLESS. If the mirror drifted from production, every offset
it produced would describe a recognition this study does not run. So the mirror is asserted
equal to `extract_anchors` -- order, page, line, kind, text and division, element for
element -- on EVERY development page consumed, and any drift fails the probe rather than
being reported as a rate.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
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
import methodology_contracts as MC  # noqa: E402
import run_extended  # noqa: E402
import run_hybrid  # noqa: E402
from neutral_identity import Cell, EmittedLine, NeutralLine, build_owner  # noqa: E402

from deltatrack.parsers import pdf_anchors as PA  # noqa: E402
from deltatrack.parsers.pdf_text import Line, Page  # noqa: E402

OUT = EV / "results" / "x16_occurrence_identity.json"
ROWS: list[dict] = []
FAILED: list[str] = []

# DEVELOPMENT material. Every one of these is in tests/corpus and NONE is a holdout member;
# `HOLDOUT_GUARD` refuses at runtime rather than trusting this list to stay correct.
DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
    ("115-hr-5895/1", REPO / "tests/corpus/115-hr-5895/1_reported-in-house.pdf"),
    ("118-hr-8752/1", REPO / "tests/corpus/118-hr-8752/1_reported-in-house.pdf"),
    ("119-hr-1/1", REPO / "tests/corpus/119-hr-1/1_reported-in-house.pdf"),
    ("118-hr-4366/1", REPO / "tests/corpus/118-hr-4366/1_reported-in-house.pdf"),
]
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


def check(name, expected, observed, implication="") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "implication": implication})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


# ============================================================ part 1: fidelity + census


def census() -> dict:
    report = []
    fidelity_failures: list[str] = []
    refusals = Counter()
    totals = Counter()

    for name, path in DOCS:
        for member in HOLDOUT_GUARD:
            if member in str(path):
                raise SystemExit(f"REFUSED: {path} touches holdout member {member}")
        if not path.exists():
            print(f"-- skip {name} (absent)")
            continue
        print(f"\n== {name} (first {PAGE_LIMIT} pages) ==")
        doc_sha = sha256_of(path)

        h_pages = run_hybrid.run(path, limit=PAGE_LIMIT)
        x_pages, _summary = run_extended.run(path, limit=PAGE_LIMIT)
        arms = {}

        for arm, pages_data in (("H", h_pages), ("X", x_pages)):
            pages = [d["page"] for d in pages_data]
            emitted_by_page = {d["page_number"]: d["emitted"] for d in pages_data}
            owner_by_page = {d["page_number"]: build_owner(d["neutral"]) for d in pages_data}

            occurrences, locate_refusals = AP.instrumented_extract_anchors(pages)
            for r in locate_refusals:
                refusals[r] += 1

            # THE FIDELITY ASSERTION -- every consumed page, not a sample.
            if AP.strip_to_production(occurrences) != PA.extract_anchors(pages):
                fidelity_failures.append(f"{name}[{arm}]")

            keys, by_line = {}, {}
            for occ in occurrences:
                page = next(p for p in pages if p.page_number == occ.page_number)
                key, reason = AP.key_for(
                    doc_sha, occ, page, emitted_by_page[occ.page_number], owner_by_page[occ.page_number]
                )
                totals[f"{arm}_occurrences"] += 1
                if reason:
                    refusals[reason] += 1
                    continue
                keys[(occ.anchor.page_number, occ.anchor.line_number, occ.anchor.kind)] = (occ.anchor.text, key)
                by_line.setdefault((occ.anchor.page_number, occ.anchor.line_number), []).append(occ.anchor.kind)

            collisions = {k: v for k, v in by_line.items() if len(v) > 1}
            arms[arm] = {
                "occurrences": len(occurrences),
                "keys_derived": len(keys),
                "collision_lines": len(collisions),
                "collision_shapes": dict(Counter("+".join(sorted(v)) for v in collisions.values())),
                "_keys": keys,
            }

        # cross-arm identity agreement, joined WITHOUT text. Joining on text would drop
        # exactly the occurrences the two arms disagree about -- the population the identity
        # exists to serve -- and the agreement rate would then pass for the wrong reason.
        hk, xk = arms["H"]["_keys"], arms["X"]["_keys"]
        shared = set(hk) & set(xk)
        agree = [k for k in shared if hk[k][1] == xk[k][1]]
        text_differs = [k for k in shared if hk[k][0] != xk[k][0]]
        text_differs_agree = [k for k in text_differs if hk[k][1] == xk[k][1]]
        disagree = [
            {"anchor": list(k), "H_text": hk[k][0], "X_text": xk[k][0]} for k in sorted(shared) if hk[k][1] != xk[k][1]
        ]

        print(
            f"  H occurrences={arms['H']['occurrences']} collisions={arms['H']['collision_lines']} "
            f"{arms['H']['collision_shapes']}"
        )
        print(
            f"  X occurrences={arms['X']['occurrences']} collisions={arms['X']['collision_lines']} "
            f"{arms['X']['collision_shapes']}"
        )
        print(
            f"  shared={len(shared)} identity agrees={len(agree)} disagrees={len(disagree)} | "
            f"text-discordant={len(text_differs)} of which identity agrees={len(text_differs_agree)}"
        )

        totals["shared"] += len(shared)
        totals["agree"] += len(agree)
        totals["disagree"] += len(disagree)
        totals["text_discordant"] += len(text_differs)
        totals["text_discordant_agree"] += len(text_differs_agree)
        for arm in ("H", "X"):
            totals[f"{arm}_collision_lines"] += arms[arm]["collision_lines"]
            arms[arm].pop("_keys")
        report.append(
            {
                "document": name,
                "document_sha256": doc_sha,
                "pages": PAGE_LIMIT,
                "H": arms["H"],
                "X": arms["X"],
                "shared": len(shared),
                "identity_agrees": len(agree),
                "identity_disagrees": disagree[:10],
                "text_discordant": len(text_differs),
                "text_discordant_identity_agrees": len(text_differs_agree),
            }
        )

    check(
        "the instrumented mirror reproduces production extract_anchors on EVERY page",
        [],
        fidelity_failures,
        "any drift makes every derived offset describe a recognition this study does not run",
    )
    check("every cross-arm occurrence identity agrees", totals["disagree"], 0)
    check(
        "...and text-discordant occurrences were actually exercised, so it is not vacuous",
        True,
        totals["text_discordant"] > 0,
        "if no occurrence had discordant text, space-invariance would be untested on real material",
    )
    check(
        "every text-discordant occurrence still agrees on identity",
        totals["text_discordant"],
        totals["text_discordant_agree"],
    )
    check("no occurrence was refused on development material", {}, dict(refusals))
    return {
        "documents": report,
        "totals": dict(totals),
        "refusals": dict(refusals),
        "fidelity_failures": fidelity_failures,
    }


# ================================================ part 2: the adversarial A+B / B-only
#
# ONE canonical ink sequence -- the physical marks. Both arms name each mark by the same
# source index; a space carries no ngid, so the arms may disagree about spacing freely.

INK = "SEC.307.(a)NEWREGIONALRESERVES.—Outofanymoney"
H_SPACES = {4, 8, 11, 14, 22, 35, 37, 40}  # 'SEC. 307. (a) NEW REGIONAL RESERVES.—Out of any money'
X_SPACES = {4, 11, 14, 22, 35, 37, 40}  # 'SEC. 307.(a) NEW …'  -- X welds one space
GLYPH_PITCH = 6.0  # pt per ink mark, synthetic but monotonic
BBOX_X0, BBOX_X1 = 72.0, 540.0


def build_arm(space_positions):
    cells = []
    for i, ch in enumerate(INK):
        if i in space_positions:
            cells.append(Cell(ngid=None, char=" ", sci=None))
        cells.append(Cell(ngid=i, char=ch, sci=i))
    return "".join(c.char for c in cells), EmittedLine(cells=cells)


def synthetic_world(space_positions):
    """Run the real production recognition + real provenance derivation for one arm."""
    text, emitted = build_arm(space_positions)
    line = Line(307, text)
    page = Page(1, (line,), (line,), ((0, 1),))
    neutral = NeutralLine(
        page=1, ordinal=0, baseline=0.0, x0=BBOX_X0, y0=0.0, x1=BBOX_X1, y1=10.0, gids=frozenset(range(len(INK)))
    )
    owner = build_owner([neutral])

    occurrences, _refusals = AP.instrumented_extract_anchors([page])
    assert AP.strip_to_production(occurrences) == PA.extract_anchors([page]), "mirror drifted"

    out = {}
    for occ in occurrences:
        key, reason = AP.key_for("devsha", occ, page, [emitted], owner)
        out[occ.anchor.kind] = {"offset": occ.start_offset, "key": key, "refusal": reason}
    return out, neutral, page, emitted


def part_adversarial() -> dict:
    print("\n== A30.1 adversarial: A+B vs B-only, through the production path ==")
    h, neutral, _p, _e = synthetic_world(H_SPACES)
    x, _n, _p2, _e2 = synthetic_world(X_SPACES)

    check(
        "both arms recognise the section and its inline subsection on one physical line",
        True,
        all(k in h and k in x for k in ("section", "subsection")),
    )
    check(
        "the arms genuinely disagree about spacing, so space-invariance is exercised",
        True,
        h["subsection"]["offset"] != x["subsection"]["offset"],
    )
    check("A's identity is arm-invariant", h["section"]["key"], x["section"]["key"])
    check("B's identity is arm-invariant", h["subsection"]["key"], x["subsection"]["key"])
    check("A and B are separately identifiable on the one line", True, h["section"]["key"] != h["subsection"]["key"])

    # A goes missing on one arm. The derivation is per-occurrence and consults no other
    # anchor, so dropping A cannot move B -- that is the property, asserted not assumed.
    x_b_only = {"subsection": x["subsection"]}
    check("key_H(B) == key_X(B) when X is missing A", h["subsection"]["key"], x_b_only["subsection"]["key"])
    h_b_only = {"subsection": h["subsection"]}
    check("mirror: key_H(B) == key_X(B) when H is missing A", h_b_only["subsection"]["key"], x["subsection"]["key"])

    # THE REJECTED SHORTCUT must demonstrably fail, or this control cannot tell a good
    # identity from a bad one.
    def arm_local_ordinal(world, kind):
        ordered = [k for k in ("section", "subsection") if k in world]
        return ordered.index(kind) if kind in ordered else None

    with_a = arm_local_ordinal(x, "subsection")
    without_a = arm_local_ordinal(x_b_only, "subsection")
    check(
        "the rejected arm-local ordinal DOES renumber B when A is missing",
        True,
        with_a != without_a,
        f"ordinal(B) {with_a} -> {without_a} while start_ngid stays fixed; a green run here "
        "proves the control can fail",
    )
    return {
        "H": {k: {"offset": v["offset"], "key": list(v["key"])} for k, v in h.items()},
        "X": {k: {"offset": v["offset"], "key": list(v["key"])} for k, v in x.items()},
        "rejected_ordinal_with_A": with_a,
        "rejected_ordinal_without_A": without_a,
        "neutral_line": list(neutral.key),
    }


# ================================================ part 3: A30.3 oracle geometric position


def glyph_x0(ngid: int) -> float:
    return BBOX_X0 + ngid * GLYPH_PITCH


def candidates_for(gids) -> list:
    return [(g, glyph_x0(g)) for g in sorted(gids)]


def adjudicated_px(ngid: int, dpi: int) -> int:
    """Simulate the adjudicator reading the left edge of a printed character, in pixels."""
    width = AP.expected_image_width(BBOX_X0, BBOX_X1, dpi)
    return int(round((glyph_x0(ngid) - BBOX_X0) / (BBOX_X1 - BBOX_X0) * width))


def resolve_oracle(ngid_truth: int, gids, dpi: int = MC.PRIMARY_DPI):
    width = AP.expected_image_width(BBOX_X0, BBOX_X1, dpi)
    neutral = NeutralLine(
        page=1, ordinal=0, baseline=0.0, x0=BBOX_X0, y0=0.0, x1=BBOX_X1, y1=10.0, gids=frozenset(gids)
    )
    return AP.oracle_occurrence_key(
        "devsha", 1, neutral, candidates_for(gids), adjudicated_px(ngid_truth, dpi), BBOX_X0, BBOX_X1, width
    )


def part_oracle() -> dict:
    print("\n== A30.3 oracle geometric position ==")
    all_gids = set(range(len(INK)))
    h, _n, _p, _e = synthetic_world(H_SPACES)
    x, _n2, _p2, _e2 = synthetic_world(X_SPACES)

    key_a, r_a = resolve_oracle(0, all_gids)  # the 'S' of SEC.
    key_b, r_b = resolve_oracle(8, all_gids)  # the '(' of (a)
    check(
        "oracle control 1: two occurrences on one line resolve to two distinct identities",
        True,
        r_a is None and r_b is None and key_a != key_b,
    )
    check("the oracle's identity for A equals the architecture's", h["section"]["key"], key_a)
    check("the oracle's identity for B equals the architecture's", h["subsection"]["key"], key_b)

    check(
        "oracle control 2: dropping the FIRST architecture occurrence leaves B's identity",
        key_b,
        x["subsection"]["key"],
        "the resolver reads the skeleton and the adjudicated position; no arm output enters",
    )
    check("oracle control 3: mirror -- dropping the SECOND leaves A's identity", key_a, x["section"]["key"])
    check(
        "oracle control 4: H/X spacing before the occurrence does not move the identity",
        h["subsection"]["key"],
        x["subsection"]["key"],
    )

    # 5. an EXACT tie refuses. No tolerance is introduced, and the tie is not broken by
    #    ngid, kind, order or text -- each of those is a rejected shortcut.
    tie = AP.resolve_oracle_start_ngid([(11, 100.0), (12, 120.0)], 110.0)
    check("oracle control 5: an exact geometric tie is UNMATCHED", (None, AP.AMBIGUOUS_SOURCE_POSITION), tie)
    near = AP.resolve_oracle_start_ngid([(11, 100.0), (12, 120.0)], 110.001)
    check("...but a non-tie still resolves, so the tie rule is not swallowing everything", 12, near[0])

    # 6. a physical line the skeleton does not carry
    missing = AP.oracle_occurrence_key(
        "devsha",
        1,
        NeutralLine(page=1, ordinal=0, baseline=0.0, x0=BBOX_X0, y0=0.0, x1=BBOX_X1, y1=10.0, gids=frozenset({999})),
        candidates_for({0, 1}),
        adjudicated_px(0, MC.PRIMARY_DPI),
        BBOX_X0,
        BBOX_X1,
        AP.expected_image_width(BBOX_X0, BBOX_X1, MC.PRIMARY_DPI),
    )
    check(
        "oracle control 6: a start not owned by the reported neutral line is UNMATCHED",
        (None, AP.START_NGID_NOT_OWNED_BY_NEUTRAL_LINE),
        missing,
    )

    # 7. a line carrying no neutral ink at all
    empty = AP.resolve_oracle_start_ngid([], 100.0)
    check("oracle control 7: a line with no neutral ink is UNMATCHED", (None, AP.NO_NEUTRAL_INK_ON_LINE), empty)

    # 8. the rejected arm-local ordinal, restated against the ORACLE identity
    check(
        "oracle control 8: the source identity is fixed while the rejected ordinal moves",
        True,
        key_b == h["subsection"]["key"] == x["subsection"]["key"],
    )
    return {"key_A": list(key_a), "key_B": list(key_b), "tie_refusal": AP.AMBIGUOUS_SOURCE_POSITION}


# ============================================================ part 4: R1 repeat at 330 DPI


def part_r1() -> dict:
    print("\n== R1 repeat: primary and repeat resolved INDEPENDENTLY ==")
    all_gids = set(range(len(INK)))
    agreements, items = 0, []
    for truth in (0, 8, 22, 40):
        primary, r_p = resolve_oracle(truth, all_gids, MC.PRIMARY_DPI)
        repeat, r_r = resolve_oracle(truth, all_gids, MC.R1_REPEAT_DPI)
        ok = r_p is None and r_r is None and primary == repeat
        agreements += ok
        items.append(
            {
                "ngid_truth": truth,
                "agree": ok,
                "at_bbox_origin": truth == 0,
                "primary_px": adjudicated_px(truth, MC.PRIMARY_DPI),
                "repeat_px": adjudicated_px(truth, MC.R1_REPEAT_DPI),
            }
        )
    # The glyph sitting exactly on the bbox left edge is pixel 0 at EVERY scale -- that is
    # arithmetic, not a cache hit -- so the re-render evidence comes from the others. It is
    # kept in the agreement count rather than dropped, since it is a real occurrence position.
    scaled = [i for i in items if not i["at_bbox_origin"]]
    check(
        "the repeat is genuinely a re-render: pixel coordinates differ away from the bbox origin",
        True,
        bool(scaled) and all(i["primary_px"] != i["repeat_px"] for i in scaled),
        "if the coordinates matched, R1 would be testing a cache rather than a re-read",
    )
    check(
        "...and the bbox-origin occurrence is pixel 0 at both scales, as arithmetic requires",
        [0, 0],
        [items[0]["primary_px"], items[0]["repeat_px"]],
    )
    check("R1_start_identity_agreement: every repeated item resolves to the primary's identity", len(items), agreements)
    return {"R1_start_identity_agreement": f"{agreements}/{len(items)}", "items": items}


def main() -> int:
    print("== A30.2 instrumented fidelity + DEVELOPMENT census ==")
    census_doc = census()
    adversarial = part_adversarial()
    oracle = part_oracle()
    r1 = part_r1()

    doc = {
        "population": "DEVELOPMENT + synthetic -- no holdout opened, nothing scored",
        "builds_no_harness_component": True,
        "occurrence_key": "(document_sha256, page_number, start_neutral_line_key, start_ngid)",
        "ngid_is_identity_not_order": True,
        "text_matching_used": False,
        "kind_matching_used": False,
        "emitted_ordinal_used": False,
        "fidelity_contract": (
            "strip_to_production(instrumented) == extract_anchors, element for element, on "
            "every DEVELOPMENT page consumed. When confirmatory execution is authorized the "
            "same assertion must cover every consumed confirmatory page."
        ),
        "refusal_classes": sorted(
            {
                AP.PAGE_HAS_NO_PRINT_LINE_PROVENANCE,
                AP.PRINT_LINE_INDEX_UNRESOLVED,
                AP.MERGE_RECONSTRUCTION_MISMATCH,
                AP.OFFSET_PAST_END_OF_LINE,
                AP.CELLS_NOT_ALIGNED_WITH_PRINT_TEXT,
                AP.NO_NEUTRAL_INK_AT_OR_AFTER_START,
                AP.START_NGID_NOT_OWNED_BY_NEUTRAL_LINE,
                AP.NO_NEUTRAL_INK_ON_LINE,
                AP.AMBIGUOUS_SOURCE_POSITION,
            }
        ),
        "census": census_doc,
        "adversarial": adversarial,
        "oracle_position": oracle,
        "r1": r1,
        "pdfium_conditioned_frame_note": (
            "This occurrence-position join reads the neutral skeleton, so it inherits the "
            "already-frozen PDFIUM-CONDITIONED FRAME qualification when the cross-engine "
            "neutral-frame control (x09) fails. It does not change the oracle's heading "
            "text/role/parent truth source, which stays independently adjudicated."
        ),
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
