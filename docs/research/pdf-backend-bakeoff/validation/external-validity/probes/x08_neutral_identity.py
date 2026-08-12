"""x08 -- test the literal source-glyph identity contract. DESIGN MATERIAL.

NOT CONFIRMATORY. Synthetic fixtures plus DEVELOPMENT documents (hybrid only). No holdout
document is opened.

Part 1  the old projection defect, demonstrated then shown repaired
Part 2  cardinality: 1->1, 1->many, many->1, 50/50, reversed order, duplicate, unowned
Part 3  Model P (plurality) vs Model G (source-glyph partition)
Part 4  spacing preservation under partition
Part 5  D-frame symmetry under H/X swap, and NON-VACUOUSLY so
Part 6  eligibility is geometric, measured on DEVELOPMENT documents
Part 7  identity diagnostics carrying H reconstruction on DEVELOPMENT documents

The discordance semantics themselves (reconstruction signature, the three predicates, M0's
components) are exercised in `x10_reconstruction_signature.py`; this file keeps the
identity/projection evidence A21 rests on.
"""

from __future__ import annotations

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

from neutral_geometry import cluster_page, project_by_glyphs  # noqa: E402
from neutral_identity import (  # noqa: E402
    EmittedLine,
    SourceGlyph,
    build_owner,
    cluster,
    contribution,
    eligible,
    line_discordance,
    line_state,
)

OUT = EV / "results" / "x08_neutral_identity.json"
ROWS: list[dict] = []
FAILED: list[str] = []


def check(name: str, expected, observed, implication: str = "") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "implication": implication})
    print(
        f"[{'PASS' if ok else 'FAIL'}] {name}\n        expected={expected!r}\n        observed={observed!r}"
        if not ok
        else f"[PASS] {name}"
    )
    if not ok:
        FAILED.append(name)


def sg(gid, baseline, x0, x1, h=10.0):
    return SourceGlyph(gid, baseline, x0, baseline, x1, baseline + h)


# Two neutral lines: gids 0-2 on baseline 700, gids 3-5 on baseline 688.
GLYPHS = [
    sg(0, 700, 72, 90),
    sg(1, 700, 92, 110),
    sg(2, 700, 112, 130),
    sg(3, 688, 72, 90),
    sg(4, 688, 92, 110),
    sg(5, 688, 112, 130),
]
LINES = cluster(GLYPHS, 1)
OWNER = build_owner(LINES)


def part1_defect() -> None:
    old = cluster_page([(700, 72, 700, 130, 710), (688, 72, 688, 130, 698)], 1)
    check(
        "OLD project_by_glyphs forces a y=-5000 glyph onto a line",
        1,
        project_by_glyphs(old, [-5000.0]),
        "nearest-baseline inference with no maximum distance -- not membership",
    )
    check(
        "NEW membership: a foreign gid contributes nothing",
        "",
        contribution([EmittedLine([(99, "Z")])], LINES[0]),
        "set membership cannot invent ownership",
    )


def part2_cardinality() -> None:
    check("1 neutral -> 1 emitted line", "ABC", contribution([EmittedLine([(0, "A"), (1, "B"), (2, "C")])], LINES[0]))
    check(
        "1 neutral -> 2 emitted lines: the SPLIT is preserved as a line break",
        "A\nBC",
        contribution([EmittedLine([(0, "A")]), EmittedLine([(1, "B"), (2, "C")])], LINES[0]),
        "joining by '' would assert an adjacency the architecture never emitted",
    )
    check(
        "1 neutral -> 3 emitted lines",
        "A\nB\nC",
        contribution([EmittedLine([(0, "A")]), EmittedLine([(1, "B")]), EmittedLine([(2, "C")])], LINES[0]),
    )
    check(
        "emitted-line order REVERSED gives the same contribution",
        "A\nB\nC",
        contribution([EmittedLine([(2, "C")]), EmittedLine([(1, "B")]), EmittedLine([(0, "A")])], LINES[0]),
        "ordering is a function of source identity, not of emission order",
    )
    merged = [EmittedLine([(0, "A"), (1, "B"), (2, "C"), (3, "D"), (4, "E"), (5, "F")])]
    check(
        "many neutral -> 1 merged line: line 0 keeps only its own glyphs",
        "ABC",
        contribution(merged, LINES[0]),
        "MODEL G -- a merge no longer blanks the other line",
    )
    check("many neutral -> 1 merged line: line 1 keeps its own glyphs", "DEF", contribution(merged, LINES[1]))
    fifty = [EmittedLine([(0, "A"), (3, "D")])]
    check(
        "exact 50/50 merge splits by ownership, not by plurality",
        ("A", "D"),
        (contribution(fifty, LINES[0]), contribution(fifty, LINES[1])),
        "no tie-break is needed at all",
    )
    check(
        "duplicate gid is retained in the contribution",
        "AAB",
        contribution([EmittedLine([(0, "A"), (0, "A"), (1, "B")])], LINES[0]),
        "duplication is visible, then flagged as a diagnostic",
    )
    check(
        "unowned glyph contributes nothing",
        "AB",
        contribution([EmittedLine([(0, "A"), (99, "Z"), (1, "B")])], LINES[0]),
    )
    check("lost glyph simply does not appear", "AC", contribution([EmittedLine([(0, "A"), (2, "C")])], LINES[0]))


def part3_models() -> str:
    """Model P (plurality whole-line) vs Model G (source-glyph partition)."""
    merged = [EmittedLine([(0, "F"), (1, "H"), (2, "!"), (3, "P")])]  # 3 glyphs of line0, 1 of line1
    p_line0 = merged[0].text()  # plurality: whole text to line 0
    p_line1 = "ABSENT"  # plurality: line 1 blanked
    g_line0 = contribution(merged, LINES[0])
    g_line1 = contribution(merged, LINES[1])
    rows = [
        {
            "case": "merge 3/1",
            "plurality": [p_line0, p_line1],
            "partition": [g_line0, g_line1],
            "preferred": "G",
            "why": "P attributes line 1's glyph to line 0 AND blanks line 1: one glyph is "
            "double-counted and one physical line vanishes",
        },
        {
            "case": "merge 50/50",
            "plurality": "tie-break decides which line is blanked",
            "partition": [
                contribution([EmittedLine([(0, "A"), (3, "D")])], LINES[0]),
                contribution([EmittedLine([(0, "A"), (3, "D")])], LINES[1]),
            ],
            "preferred": "G",
            "why": "G needs no tie-break; P needs an arbitrary one",
        },
        {
            "case": "split 1->2",
            "plurality": "both emitted lines -> same slot; second is lost or overwrites",
            "partition": "rejoined in source order",
            "preferred": "G",
            "why": "P has no defined aggregation for two emitted lines on one slot",
        },
    ]
    check(
        "MODEL P double-counts a merged glyph",
        True,
        p_line0 == "FH!P" and p_line1 == "ABSENT",
        "whole merged text lands on line 0 while line 1 is blanked",
    )
    check(
        "MODEL G conserves every glyph exactly once",
        sorted("FH!" + "P"),
        sorted(g_line0 + g_line1),
        "partition is lossless; plurality is not",
    )
    return json.dumps(rows)


def part4_spacing() -> None:
    """The skeleton supplies identity and must never supply spacing."""
    gids = [(0, "F"), (1, "H")]
    h_weld = [EmittedLine(list(gids))]
    x_space = [EmittedLine([(0, "F"), (None, " "), (1, "H")])]
    check("same gids, H welds -> no space", "FH", contribution(h_weld, LINES[0]))
    check("same gids, X inserts a space -> space preserved", "F H", contribution(x_space, LINES[0]))
    st = line_state(h_weld, x_space, LINES[0], OWNER)
    check(
        "the weld/space difference is TEXT_DIFFERS",
        "TEXT_DIFFERS",
        st["state"],
        "the seam difference survives projection -- it is not normalised away",
    )
    # letter-spaced display caps, the R E P O R T case
    h_spaced = [EmittedLine([(0, "R"), (None, " "), (1, "E"), (None, " "), (2, "P")])]
    x_tight = [EmittedLine([(0, "R"), (1, "E"), (2, "P")])]
    check("R E P vs REP is TEXT_DIFFERS", "TEXT_DIFFERS", line_state(h_spaced, x_tight, LINES[0], OWNER)["state"])
    # a dropped glyph
    st_drop = line_state(
        [EmittedLine([(0, "A"), (1, "B"), (2, "C")])], [EmittedLine([(0, "A"), (2, "C")])], LINES[0], OWNER
    )
    check("a dropped glyph is TEXT_DIFFERS", "TEXT_DIFFERS", st_drop["state"])
    check("...and is recorded as X source-glyph loss", [1], st_drop["diagnostics"]["X_SOURCE_GLYPH_LOSS"])
    st_dup = line_state(
        [EmittedLine([(0, "A"), (1, "B")])], [EmittedLine([(0, "A"), (0, "A"), (1, "B")])], LINES[0], OWNER
    )
    check("a duplicated glyph is flagged", True, st_dup["diagnostics"]["X_SOURCE_GLYPH_DUPLICATION"])


def part5_symmetry() -> None:
    """Symmetry, and -- the point A21's version missed -- symmetry that is not vacuous.

    The previous test asserted only `D(H,X) == D(X,H)`. `False == False` satisfies that,
    so it passed on the merge/split case even while the merge/split disagreement was being
    erased entirely. Every case below therefore carries its EXPECTED membership too.
    """
    cases = {
        # name: (H, X, expected D-frame membership on the lines it touches)
        "both present, same": ([EmittedLine([(0, "A")])], [EmittedLine([(0, "A")])], False),
        "both present, differ": ([EmittedLine([(0, "A")])], [EmittedLine([(0, "B")])], True),
        "H only": ([EmittedLine([(0, "A")])], [], True),
        "X only": ([], [EmittedLine([(0, "A")])], True),
        "neither": ([], [], False),
        "merge vs split": (
            [EmittedLine([(0, "A"), (3, "D")])],
            [EmittedLine([(0, "A")]), EmittedLine([(3, "D")])],
            True,
        ),
    }
    asym = []
    wrong = []
    for name, (h, x, expected) in cases.items():
        for ln in LINES:
            fwd = line_discordance(line_state(h, x, ln, OWNER))
            rev = line_discordance(line_state(x, h, ln, OWNER))
            if fwd != rev:
                asym.append(f"{name}@{ln.key}")
            # the touched line is line 0 for every case here; line 1 is touched only by the
            # merge/split case, where it must also fire.
            touched = ln.key == (1, 0) or name == "merge vs split"
            if touched and fwd != expected:
                wrong.append(f"{name}@{ln.key} expected={expected} observed={fwd}")
    check(
        "D-frame membership is invariant under swapping H and X",
        [],
        asym,
        "D(H,X) == D(X,H) for every cardinality case",
    )
    check(
        "...and each case has the EXPECTED membership, so symmetry is not vacuous",
        [],
        wrong,
        "False == False no longer passes for a case that must be True",
    )
    mirror = line_state([EmittedLine([(0, "A")])], [], LINES[0], OWNER)["state"]
    mirror_rev = line_state([], [EmittedLine([(0, "A")])], LINES[0], OWNER)["state"]
    check("the asymmetric states are explicit mirrors", ("X_ABSENT", "H_ABSENT"), (mirror, mirror_rev))


def part6_eligibility() -> None:
    A = ord("A")
    check("generated space (gid None) is ineligible", False, eligible(None, (1, 1, 2, 2), True, 32))
    check("missing box is ineligible", False, eligible(5, None, True, A))
    check("zero-area box is ineligible", False, eligible(5, (10, 10, 10, 10), True, A))
    check("zero-width box is ineligible", False, eligible(5, (10, 10, 10, 20), True, A))
    check("non-upright glyph is ineligible", False, eligible(5, (10, 10, 20, 20), False, A))
    check("a real ink mark is eligible", True, eligible(5, (10, 10, 20, 20), True, A))
    check("None coordinate is ineligible", False, eligible(5, (10, None, 20, 20), True, A))
    check(
        "A24.2: a content-stream U+0020 with a positive-area box is INELIGIBLE",
        False,
        eligible(5, (10, 10, 13.6, 10.014), True, 32),
        "the box PDFium reports for a real space is 3.6 x 0.014 pt and clears 'positive "
        "area'; geometry alone cannot express the ink/non-ink distinction",
    )
    check(
        "...while the same geometry with an ink codepoint stays eligible",
        True,
        eligible(5, (10, 10, 13.6, 10.014), True, A),
        "the exclusion is exactly U+0020, not a size threshold",
    )

    # The FROZEN invariant is "present, finite, positive-area, upright, codepoint != U+0020".
    # `finite` needs its own controls: NaN defeats a positive-area test silently, because
    # every comparison with NaN is False, and an infinite coordinate would pass the test and
    # then poison the median ink height that sets the page's clustering tolerance.
    nan, inf = float("nan"), float("inf")
    matrix = [
        ("normal ink", (10, 10, 20, 20), A, True),
        ("U+0020, ordinary finite positive box", (10, 10, 20, 20), 32, False),
        ("x0 NaN", (nan, 10, 20, 20), A, False),
        ("x1 NaN", (10, 10, nan, 20), A, False),
        ("y0 NaN", (10, nan, 20, 20), A, False),
        ("y1 NaN", (10, 10, 20, nan), A, False),
        ("x0 +inf", (inf, 10, 20, 20), A, False),
        ("x1 +inf", (10, 10, inf, 20), A, False),
        ("y0 -inf", (10, -inf, 20, 20), A, False),
        ("y1 -inf", (10, 10, 20, -inf), A, False),
        ("zero width", (10, 10, 10, 20), A, False),
        ("zero height", (10, 10, 20, 10), A, False),
        ("negative width", (20, 10, 10, 20), A, False),
        ("negative height", (10, 20, 20, 10), A, False),
    ]
    bad = []
    seen = set()
    for label, box, cp, want in matrix:
        got = eligible(5, box, True, cp)
        seen.add(got)
        if got != want:
            bad.append(f"{label}: expected {want} observed {got}")
    check("adversarial geometry matrix matches the frozen invariant exactly", [], bad)
    check(
        "...and the predicate returns BOTH answers across it",
        [False, True],
        sorted(seen),
        "a matrix that only ever returns False would pass while proving nothing",
    )


def part7_development(limit: int = 12) -> list[dict]:
    """Eligibility measured on DEVELOPMENT documents, hybrid only.

    NOTE on the gid used here: this part counts how many characters the GEOMETRIC rule
    excludes, so it needs a per-character handle, not the study's identity. It uses the
    list position, which is NOT `source_char_index` -- the adapter `continue`s past
    rejected characters. That does not affect the count being reported (each character is
    visited exactly once either way). The real end-to-end identity is carried and checked
    in `x11_provenance_chain.py`.
    """
    import pdfium_hybrid
    from contract_hybrid import CP, GEN, UPRIGHT, VBOX, X0, X1

    docs = [
        ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
        ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
    ]
    out = []
    for name, path in docs:
        if not path.exists():
            continue
        pages, _ = pdfium_hybrid.extract(path, limit=limit)
        tot = gen = ctrl_excluded = ink = 0
        cp_only_exclusions = 0
        for p in pages:
            for i, c in enumerate(p.chars):
                tot += 1
                box = (
                    None
                    if c[X0] is None or c[X1] is None or c[VBOX] is None
                    else (c[X0], c[VBOX][0], c[X1], c[VBOX][1])
                )
                gid = None if c[GEN] else i
                ok = eligible(gid, box, bool(c[UPRIGHT]), c[CP])
                if c[GEN]:
                    gen += 1
                if ok:
                    ink += 1
                else:
                    ctrl_excluded += 1
                    # would a CODEPOINT filter have been needed to exclude it?
                    if not c[GEN] and c[CP] in (10, 13, 32) and box is not None:
                        cp_only_exclusions += 1
        out.append(
            {
                "document": name,
                "pages": len(pages),
                "chars": tot,
                "generated": gen,
                "geometrically_eligible": ink,
                "excluded": ctrl_excluded,
                "excluded_ONLY_by_a_codepoint_rule": cp_only_exclusions,
            }
        )
        print(
            f"  {name:16} chars={tot:6} generated={gen:6} eligible={ink:6} "
            f"excluded={ctrl_excluded:6} needing_a_CP_rule={cp_only_exclusions}"
        )
    return out


def main() -> int:
    print("== part 1: the old defect, and the repair ==")
    part1_defect()
    print("\n== part 2: cardinality ==")
    part2_cardinality()
    print("\n== part 3: model comparison ==")
    models = part3_models()
    print("\n== part 4: spacing preservation ==")
    part4_spacing()
    print("\n== part 5: D-frame symmetry ==")
    part5_symmetry()
    print("\n== part 6: eligibility is geometric ==")
    part6_eligibility()
    print("\n== part 7: development documents ==")
    dev = part7_development()

    doc = {
        "population": "SYNTHETIC + DEVELOPMENT (hybrid only) -- no holdout opened",
        "neutral_glyph_id": "(document_sha256, page_number, source_char_index)",
        "eligibility": "valid finite positive-area ink box AND upright AND gid is not None",
        "projection": "set membership on gids; Model G source-glyph partition",
        "model_comparison": json.loads(models),
        "tests": ROWS,
        "failures": FAILED,
        "development": dev,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} tests pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
