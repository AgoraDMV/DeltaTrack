"""x10 -- reconstruction segmentation as a FIRST-CLASS discordance. DESIGN MATERIAL.

NOT CONFIRMATORY. Synthetic fixtures only. No holdout document is opened, no architecture
is run.

THE DEFECT THIS PROBE EXISTS TO REPRODUCE AND CLOSE

A21's Model G normalises architecture output onto neutral physical lines by source-glyph
partition. That is correct for IDENTITY -- each neutral line gets back exactly its own
glyphs -- and it is precisely why it can erase the thing A17.4 existed to observe:

    neutral N0 = ABC        H emits one line:  ABCDEF        X emits two:  ABC
    neutral N1 = DEF                                                       DEF

    partition gives   N0: H=ABC X=ABC      N1: H=DEF X=DEF      -> both SAME

H performed a cross-line merge and X did not, and the comparison reported no difference at
all, because `differs()` read only `state["state"]` while `H_CROSS_LINE_MERGE` travelled
as a diagnostic that entered nothing.

Part 1  the defect, reproduced under the superseded rule, in both directions
Part 2  the adversarial case matrix, with expected AND observed for each predicate
Part 3  non-vacuous symmetry: D(H,X) == D(X,H) AND the expected membership
Part 4  M3 is preserved -- text correctness and segmentation stay separate concepts
Part 5  M0's components on a mixed population, raw counts preserved
Part 6  negative controls: every predicate is shown capable of BOTH answers
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))

from m3_boundaries import HeadingOutcome, decompose, heading_outcome  # noqa: E402
from neutral_identity import (  # noqa: E402
    Cell,
    EmittedLine,
    SourceGlyph,
    build_owner,
    cluster,
    contribution,
    line_discordance,
    line_state,
    m0,
    reconstruction_signature,
    region_discordance,
    segmentation_discordance,
    text_discordance,
)

OUT = EV / "results" / "x10_reconstruction_signature.json"
ROWS: list[dict] = []
FAILED: list[str] = []


def check(name: str, expected, observed, implication: str = "") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "implication": implication})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


def sg(gid, baseline, x0, x1, h=10.0):
    return SourceGlyph(gid, baseline, x0, baseline, x1, baseline + h)


# Three neutral lines, 12 pt apart, tolerance 0.5 x 10 = 5.0 -> three distinct clusters.
#   N0 = gids 0,1,2 = A B C      N1 = gids 3,4,5 = D E F      N2 = gids 6,7,8 = G H I
TEXTS = "ABCDEFGHI"
GLYPHS = [sg(i, 700 - 12 * (i // 3), 72 + 20 * (i % 3), 90 + 20 * (i % 3)) for i in range(9)]
LINES = cluster(GLYPHS, 1)
OWNER = build_owner(LINES)

N0, N1, N2 = (ln.key for ln in LINES)


def el(*gids, insert_after=None, sub=None) -> EmittedLine:
    """Build one emitted printed line from source gids, in source order.

    `insert_after` puts an ARCHITECTURE-INSERTED space (gid None) after that gid -- a word
    space the arm decided on. `sub` replaces one gid's character, to make a text difference
    that carries no segmentation difference.
    """
    cells: list[tuple[int | None, str]] = []
    for g in gids:
        cells.append((g, sub[1] if sub and g == sub[0] else TEXTS[g]))
        if insert_after is not None and g == insert_after:
            cells.append((None, " "))
    return EmittedLine(cells)


def old_differs(state: dict) -> bool:
    """The SUPERSEDED A21 rule, kept executable so the defect is demonstrated, not asserted."""
    return state["state"] != "SAME"


# --------------------------------------------------------------------------- part 1


def part1_defect() -> list[dict]:
    scenarios = [
        ("H merges N0+N1, X emits them separately", [el(0, 1, 2, 3, 4, 5)], [el(0, 1, 2), el(3, 4, 5)]),
        ("the inverse: H separate, X merges", [el(0, 1, 2), el(3, 4, 5)], [el(0, 1, 2, 3, 4, 5)]),
        ("pure within-line split of N0, rejoined in source order", [el(0, 1, 2)], [el(0), el(1, 2)]),
    ]
    out = []
    for title, h, x in scenarios:
        print(f"\n  -- {title}")
        rec = {"scenario": title, "lines": []}
        for ln in (LINES[0], LINES[1]):
            st = line_state(h, x, ln, OWNER)
            d = st["diagnostics"]
            print(f"     line {ln.ordinal} text state:            {st['state']}")
            print(f"     line {ln.ordinal} H_CROSS_LINE_MERGE:    {d['H_CROSS_LINE_MERGE']}")
            print(f"     line {ln.ordinal} X_CROSS_LINE_MERGE:    {d['X_CROSS_LINE_MERGE']}")
            print(f"     line {ln.ordinal} SUPERSEDED D-frame:    {old_differs(st)}")
            print(f"     line {ln.ordinal} NEW D-frame:           {line_discordance(st)}")
            rec["lines"].append(
                {
                    "line": ln.key,
                    "state": st["state"],
                    "h_text": st["h_text"],
                    "x_text": st["x_text"],
                    "H_CROSS_LINE_MERGE": d["H_CROSS_LINE_MERGE"],
                    "X_CROSS_LINE_MERGE": d["X_CROSS_LINE_MERGE"],
                    "superseded_d_frame": old_differs(st),
                    "new_d_frame": line_discordance(st),
                }
            )
        out.append(rec)

    merge_h, merge_x = [el(0, 1, 2, 3, 4, 5)], [el(0, 1, 2), el(3, 4, 5)]
    st0 = line_state(merge_h, merge_x, LINES[0], OWNER)
    st1 = line_state(merge_h, merge_x, LINES[1], OWNER)
    check(
        "REPRODUCED: a cross-line merge/split leaves both text states SAME",
        ("SAME", "SAME"),
        (st0["state"], st1["state"]),
        "partition hands each neutral line back its own glyphs, so the text cannot differ",
    )
    check(
        "REPRODUCED: the superseded rule therefore drops it from the D-frame",
        (False, False),
        (old_differs(st0), old_differs(st1)),
        "the merge/split disagreement A17.4 exists to observe was erased",
    )
    check(
        "...while the merge WAS visible all along, as a diagnostic that entered nothing",
        (True, False),
        (st0["diagnostics"]["H_CROSS_LINE_MERGE"], st0["diagnostics"]["X_CROSS_LINE_MERGE"]),
    )
    check(
        "CLOSED: the new rule puts both neutral lines in the D-frame",
        (True, True),
        (line_discordance(st0), line_discordance(st1)),
    )

    # The second defect: agreement scored as discordance.
    empty = line_state([], [], LINES[0], OWNER)
    check(
        "REPRODUCED: a line NEITHER arm emits was in the D-frame under the superseded rule",
        (True, "BOTH_ABSENT"),
        (old_differs(empty), empty["state"]),
        "every running head, page number and VerDate stamp both arms correctly drop as "
        "chrome entered a census frame as discordance",
    )
    check(
        "CLOSED: a shared drop is not a comparative discordance",
        False,
        line_discordance(empty),
        "PRE-REGISTRATION 5.8: the D-frame 'cannot see a failure both architectures share. "
        "That is exactly why the C-frame exists'",
    )
    return out


# --------------------------------------------------------------------------- part 2


def m3_reads_same(a: str, b: str) -> bool:
    """Would M3 see these two projections as the same heading? Its own frozen decomposition."""
    return decompose(a) == decompose(b)


CASES = [
    # name, H, X, {line: (expect_text, expect_segmentation)}
    (
        "H merge / X split",
        [el(0, 1, 2, 3, 4, 5)],
        [el(0, 1, 2), el(3, 4, 5)],
        {N0: (False, True), N1: (False, True), N2: (False, False)},
    ),
    (
        "H split / X merge",
        [el(0, 1, 2), el(3, 4, 5)],
        [el(0, 1, 2, 3, 4, 5)],
        {N0: (False, True), N1: (False, True), N2: (False, False)},
    ),
    (
        "same merge on both arms",
        [el(0, 1, 2, 3, 4, 5)],
        [el(0, 1, 2, 3, 4, 5)],
        {N0: (False, False), N1: (False, False), N2: (False, False)},
    ),
    (
        "different merge spans (H: N0+N1, X: N1+N2)",
        [el(0, 1, 2, 3, 4, 5), el(6, 7, 8)],
        [el(0, 1, 2), el(3, 4, 5, 6, 7, 8)],
        {N0: (False, True), N1: (False, True), N2: (False, True)},
    ),
    (
        "same glyphs / different emitted-line cardinality",
        [el(0, 1, 2)],
        [el(0), el(1, 2)],
        {N0: (True, True), N1: (False, False), N2: (False, False)},
    ),
    (
        "different text / same cardinality",
        [el(0, 1, 2)],
        [EmittedLine([(0, "A"), (1, "B"), (2, "Z")])],
        {N0: (True, False), N1: (False, False), N2: (False, False)},
    ),
    (
        "same text / same cardinality",
        [el(0, 1, 2)],
        [el(0, 1, 2)],
        {N0: (False, False), N1: (False, False), N2: (False, False)},
    ),
    (
        "merge WITH a spacing difference",
        [el(0, 1, 2, 3, 4, 5)],
        [el(0, 1, 2, insert_after=0), el(3, 4, 5)],
        {N0: (True, True), N1: (False, True), N2: (False, False)},
    ),
    (
        "split WITHOUT a spacing difference",
        [el(0, 1, 2)],
        [el(0, 1), el(2)],
        {N0: (True, True), N1: (False, False), N2: (False, False)},
    ),
]


def part2_matrix() -> list[dict]:
    rows = []
    bad = []
    for name, h, x, expect in CASES:
        states = [line_state(h, x, ln, OWNER) for ln in LINES]
        in_d = region_discordance(states)
        for ln, st in zip(LINES, states):
            et, es = expect[ln.key]
            ot, os_ = text_discordance(st), segmentation_discordance(st)
            rows.append(
                {
                    "case": name,
                    "line": list(ln.key),
                    "h_text": st["h_text"],
                    "x_text": st["x_text"],
                    "expected_text_discordance": et,
                    "observed_text_discordance": ot,
                    "expected_segmentation_discordance": es,
                    "observed_segmentation_discordance": os_,
                    "in_d_frame": line_discordance(st),
                    "m3_reads_same": m3_reads_same(st["h_text"], st["x_text"]),
                }
            )
            if (et, es) != (ot, os_):
                bad.append(f"{name}@{ln.ordinal} expected=({et},{es}) observed=({ot},{os_})")
        rows.append({"case": name, "REGION_IN_D_FRAME": in_d})
    check(
        "every adversarial case matches its expected text/segmentation verdict",
        [],
        bad,
        "the two predicates are independent and each fires only where it should",
    )
    expected_regions = [True, True, False, True, True, True, False, True, True]
    observed_regions = [region_discordance([line_state(h, x, ln, OWNER) for ln in LINES]) for _, h, x, _ in CASES]
    check("region-level D-frame membership matches the frozen expectation", expected_regions, observed_regions)
    return rows


# --------------------------------------------------------------------------- part 3


def part3_symmetry() -> None:
    asym, wrong = [], []
    for name, h, x, expect in CASES:
        for ln in LINES:
            fwd = line_discordance(line_state(h, x, ln, OWNER))
            rev = line_discordance(line_state(x, h, ln, OWNER))
            if fwd != rev:
                asym.append(f"{name}@{ln.ordinal}")
            want = expect[ln.key][0] or expect[ln.key][1]
            if fwd != want:
                wrong.append(f"{name}@{ln.ordinal} expected={want} observed={fwd}")
    check("D(H,X) == D(X,H) on every adversarial case", [], asym)
    check(
        "...and the membership is the EXPECTED one, so symmetry is not vacuous",
        [],
        wrong,
        "the prior test passed on False == False while the disagreement was being erased",
    )
    # the single case the prior suite got wrong, stated in the form the review asked for
    h, x = [el(0, 1, 2, 3, 4, 5)], [el(0, 1, 2), el(3, 4, 5)]
    check(
        "merge/split: D(H,X) and D(X,H) are both TRUE, not merely equal",
        (True, True),
        (
            line_discordance(line_state(h, x, LINES[0], OWNER)),
            line_discordance(line_state(x, h, LINES[0], OWNER)),
        ),
    )


# --------------------------------------------------------------------------- part 4

# One neutral line carrying a 13-glyph heading; the space between the words is INSERTED by
# the architecture (gid None), never a source glyph, exactly as a generated space is.
HEAD_TEXT = "FAMILYHOUSING"
HEAD_GLYPHS = [SourceGlyph(i, 500.0, 72.0 + 8 * i, 500.0, 79.0 + 8 * i, 510.0) for i in range(13)]
HEAD_LINES = cluster(HEAD_GLYPHS, 2)
HEAD_OWNER = build_owner(HEAD_LINES)
HEAD = HEAD_LINES[0]
ORACLE = "FAMILY HOUSING"


def head_line(*groups) -> list[EmittedLine]:
    """Emitted lines for the heading; each group is (gids, space_after_gid_or_None)."""
    out = []
    for gids, space_after in groups:
        cells: list[tuple[int | None, str]] = []
        for g in gids:
            cells.append((g, HEAD_TEXT[g]))
            if space_after is not None and g == space_after:
                cells.append((None, " "))
        out.append(EmittedLine(cells))
    return out


def part4_m3_preserved() -> None:
    all_g = list(range(13))
    # (a) same physical glyphs, H welds the two words, X spaces them -> a real M3 defect
    h_weld = head_line((all_g, None))
    x_space = head_line((all_g, 5))
    st = line_state(h_weld, x_space, HEAD, HEAD_OWNER)
    check("weld vs space is TEXT_DIFFERS", "TEXT_DIFFERS", st["state"])
    check("...and carries NO segmentation discordance", False, segmentation_discordance(st))
    outcome, hs, xs = heading_outcome(ORACLE, st["h_text"], st["x_text"])
    check("...and reaches M3 as X_CORRECTS", HeadingOutcome.X_CORRECTS, outcome)
    check("...with H scoring exactly one weld", (1, 0), (hs.weld, hs.split))
    check("...and X clean", True, xs.clean)

    # (b) same projected heading text, different emitted-line grouping -> segmentation only
    h_one = head_line((all_g, 5))
    x_two = head_line((list(range(6)), None), (list(range(6, 13)), None))
    st2 = line_state(h_one, x_two, HEAD, HEAD_OWNER)
    check("a split heading IS a segmentation discordance", True, segmentation_discordance(st2))
    check("...and enters the D-frame", True, line_discordance(st2))
    outcome2, hs2, xs2 = heading_outcome(ORACLE, st2["h_text"], st2["x_text"])
    check(
        "...but fabricates NO M3 word-boundary error",
        (HeadingOutcome.BOTH_CLEAN, 0, 0),
        (outcome2, xs2.weld, xs2.split),
        "the '\\n' join is read as a word boundary by m3_boundaries.decompose, so a split "
        "at a word boundary costs nothing -- joining by '' would have scored a false weld",
    )
    check("...and both arms stay clean against the oracle", (True, True), (hs2.clean, xs2.clean))

    # (c) a split MID-WORD is a real boundary defect and must still be caught
    x_midword = head_line((list(range(3)), None), (list(range(3, 13)), 5))
    st3 = line_state(h_one, x_midword, HEAD, HEAD_OWNER)
    _, _, xs3 = heading_outcome(ORACLE, st3["h_text"], st3["x_text"])
    check(
        "a split MID-WORD still scores a real M3 split",
        1,
        xs3.split,
        "the arm genuinely broke FAMILY across two printed lines",
    )

    # (d) X DROPS a character -> a text defect, and NOT a segmentation-derived one
    x_drop = head_line(([g for g in all_g if g != 5], 4))
    st4 = line_state(h_one, x_drop, HEAD, HEAD_OWNER)
    outcome4, hs4, xs4 = heading_outcome(ORACLE, st4["h_text"], st4["x_text"])
    check(
        "a dropped character is TEXT discordance with NO segmentation discordance",
        (True, False),
        (text_discordance(st4), segmentation_discordance(st4)),
    )
    check(
        "...and reaches M3 as a dirty X against a clean H",
        (HeadingOutcome.X_REGRESSES, True, False),
        (outcome4, hs4.clean, xs4.clean),
        "M3 consumes text and oracle evidence, never an M0b label",
    )
    check("...scored as a text error, not a boundary error", (1, 0, 0), (xs4.text_error, xs4.weld, xs4.split))

    # (e) X DUPLICATES a character -> likewise a text defect only
    x_dup_cells = list(head_line((all_g, 5))[0].cells)
    x_dup = [EmittedLine(x_dup_cells[:2] + [x_dup_cells[1]] + x_dup_cells[2:])]
    st5 = line_state(h_one, x_dup, HEAD, HEAD_OWNER)
    outcome5, _hs5, xs5 = heading_outcome(ORACLE, st5["h_text"], st5["x_text"])
    check(
        "a duplicated character is TEXT discordance with NO segmentation discordance",
        (True, False),
        (text_discordance(st5), segmentation_discordance(st5)),
        "EmittedLine.gids is a set, so a repeated gid cannot reach the signature",
    )
    check(
        "...and reaches M3 as a dirty X",
        (HeadingOutcome.X_REGRESSES, False),
        (outcome5, xs5.clean),
    )


# --------------------------------------------------------------------------- part 5


def part5_m0() -> dict:
    """M0 on a mixed synthetic population, so every component has a nonzero member."""
    population = [
        line_state([el(0, 1, 2)], [el(0, 1, 2)], LINES[0], OWNER),  # agreement
        line_state([el(0, 1, 2)], [EmittedLine([(0, "A"), (1, "B"), (2, "Z")])], LINES[0], OWNER),  # text only
        line_state([el(0, 1, 2, 3, 4, 5)], [el(0, 1, 2), el(3, 4, 5)], LINES[0], OWNER),  # segmentation only
        line_state([el(0, 1, 2, 3, 4, 5)], [el(0, 1, 2, insert_after=0), el(3, 4, 5)], LINES[0], OWNER),  # both
        line_state([], [], LINES[2], OWNER),  # shared drop
    ]
    got = m0(population)
    check(
        "M0's components decompose the population exactly",
        {
            "in_scope": 5,
            "risk_set": 4,
            "M0a_text": 2,
            "M0b_segmentation": 2,
            "M0_any": 3,
            "M0b_only": 1,
            "M0a_only": 1,
            "both_absent": 1,
        },
        {
            "in_scope": got["neutral_lines_in_scope"],
            "risk_set": got["risk_set"],
            "M0a_text": got["M0a_text"],
            "M0b_segmentation": got["M0b_segmentation"],
            "M0_any": got["M0_any"],
            "M0b_only": got["M0b_only_segmentation"],
            "M0a_only": got["M0a_only_text"],
            "both_absent": got["both_absent"],
        },
        "M0b_only is the count that was structurally unreachable under the superseded rule",
    )
    check("M0_any is the UNION, never a sum", True, got["M0_any"] < got["M0a_text"] + got["M0b_segmentation"])
    check(
        "the risk set excludes BOTH_ABSENT and nothing else",
        (4, 1),
        (got["risk_set"], got["neutral_lines_in_scope"] - got["risk_set"]),
    )
    check(
        "the denominator change RAISES the rate, so it cannot be motivated by the number",
        (0.75, 0.6),
        (got["M0_any_rate"], got["M0_any_rate_ALL_LINES_superseded"]),
        "RQ1 seeks an equivalence statement, so a higher discordance rate makes the "
        "study's own claim harder to support, not easier",
    )
    return got


# --------------------------------------------------------------------------- part 6


def part6_negative_controls() -> None:
    """Every predicate must be shown capable of BOTH answers on this fixture set.

    A gate that has only ever returned one value cannot distinguish 'no defect' from
    'cannot see defects'. These are the paired opposites.
    """
    seen_text = {text_discordance(line_state(h, x, ln, OWNER)) for _, h, x, _ in CASES for ln in LINES}
    seen_seg = {segmentation_discordance(line_state(h, x, ln, OWNER)) for _, h, x, _ in CASES for ln in LINES}
    seen_line = {line_discordance(line_state(h, x, ln, OWNER)) for _, h, x, _ in CASES for ln in LINES}
    check("TEXT_DISCORDANCE returns both True and False on the matrix", [False, True], sorted(seen_text))
    check("SEGMENTATION_DISCORDANCE returns both True and False", [False, True], sorted(seen_seg))
    check("line D-frame membership returns both True and False", [False, True], sorted(seen_line))
    check(
        "ANCHOR_DISCORDANCE returns both",
        [False, True],
        [
            region_discordance([], h_anchors=("ACCOUNT: X",), x_anchors=("ACCOUNT: X",)),
            region_discordance([], h_anchors=("ACCOUNT: X",), x_anchors=()),
        ],
    )
    # the signature itself must be able to distinguish, not merely to be equal. ALL is the
    # jointly observed domain when both arms emitted every glyph, which is the condition
    # under which grouping alone is being varied.
    all_gids = set(range(9))
    sig_merge = reconstruction_signature([el(0, 1, 2, 3, 4, 5)], LINES[0], OWNER, all_gids)
    sig_plain = reconstruction_signature([el(0, 1, 2)], LINES[0], OWNER, all_gids)
    sig_split = reconstruction_signature([el(0), el(1, 2)], LINES[0], OWNER, all_gids)
    check("the signature separates merge, plain and split", 3, len({sig_merge, sig_plain, sig_split}))
    check(
        "the signature is INSENSITIVE to an inserted space",
        reconstruction_signature([el(0, 1, 2)], LINES[0], OWNER, all_gids),
        reconstruction_signature([el(0, 1, 2, insert_after=0)], LINES[0], OWNER, all_gids),
        "a word-space decision must never register as a segmentation difference, or M3 "
        "would see a boundary error that does not exist",
    )
    check(
        "the signature names the merge SPAN, so different spans are distinguishable",
        True,
        reconstruction_signature([el(3, 4, 5, 0, 1, 2)], LINES[1], OWNER, all_gids)
        != reconstruction_signature([el(3, 4, 5, 6, 7, 8)], LINES[1], OWNER, all_gids),
    )
    check(
        "the signature is INSENSITIVE to a repeated gid",
        reconstruction_signature([el(0, 1, 2)], LINES[0], OWNER, all_gids),
        reconstruction_signature([EmittedLine([(0, "A"), (1, "B"), (1, "B"), (2, "C")])], LINES[0], OWNER, all_gids),
        "EmittedLine.gids is a set, so duplication could never move the signature -- "
        "measured, not assumed: duplication was already classified correctly before the "
        "common-domain repair, and only LOSS was mis-classified",
    )


# --------------------------------------------------------------------------- part 7
#
# COVERAGE IS NOT GROUPING. The signature originally read the exact emitted gid subset, so
# pure character LOSS moved it and was reported as a segmentation difference. These cases
# pin the separation in both directions: a coverage defect must not manufacture a topology
# difference, and a coverage defect must not be able to HIDE one either.

# gids 0,1,2 = N0 (ABC); 3,4,5 = N1 (DEF); 6,7,8 = N2 (GHI)
COVERAGE_CASES = [
    # name, H, X, {line: (expect_text, expect_segmentation, expect_diagnostic)}
    (
        "same one-line grouping, X drops a glyph",
        [el(0, 1, 2)],
        [el(0, 2)],
        {N0: (True, False, "X_LOSS")},
    ),
    (
        "same one-line grouping, X duplicates a glyph",
        [el(0, 1, 2)],
        [EmittedLine([(0, "A"), (1, "B"), (1, "B"), (2, "C")])],
        {N0: (True, False, "X_DUP")},
    ),
    (
        "same glyphs, 1 emitted line vs 2",
        [el(0, 1, 2)],
        [el(0), el(1, 2)],
        {N0: (True, True, None)},
    ),
    (
        "H merges N0+N1, X emits separately",
        [el(0, 1, 2, 3, 4, 5)],
        [el(0, 1, 2), el(3, 4, 5)],
        {N0: (False, True, None), N1: (False, True, None)},
    ),
    (
        "H merges N0+N1 AND loses gid 5, X emits separately",
        [el(0, 1, 2, 3, 4)],
        [el(0, 1, 2), el(3, 4, 5)],
        {N0: (False, True, None), N1: (True, True, "H_LOSS")},
    ),
    (
        "both arms lose the same glyph, grouping identical",
        [el(0, 2)],
        [el(0, 2)],
        {N0: (False, False, "SHARED_LOSS")},
    ),
    (
        "both arms merge N0+N1 identically",
        [el(0, 1, 2, 3, 4, 5)],
        [el(0, 1, 2, 3, 4, 5)],
        {N0: (False, False, None), N1: (False, False, None)},
    ),
    (
        "different merge spans (H: N0+N1, X: N1+N2)",
        [el(0, 1, 2, 3, 4, 5), el(6, 7, 8)],
        [el(0, 1, 2), el(3, 4, 5, 6, 7, 8)],
        {N0: (False, True, None), N1: (False, True, None), N2: (False, True, None)},
    ),
    (
        "spacing-only difference",
        [el(0, 1, 2)],
        [el(0, 1, 2, insert_after=0)],
        {N0: (True, False, None)},
    ),
]


def diagnostic_label(st: dict) -> str | None:
    d = st["diagnostics"]
    if d["SHARED_SOURCE_GLYPH_LOSS"]:
        return "SHARED_LOSS"
    if d["H_SOURCE_GLYPH_LOSS"]:
        return "H_LOSS"
    if d["X_SOURCE_GLYPH_LOSS"]:
        return "X_LOSS"
    if d["H_SOURCE_GLYPH_DUPLICATION"]:
        return "H_DUP"
    if d["X_SOURCE_GLYPH_DUPLICATION"]:
        return "X_DUP"
    return None


def part7_coverage_vs_grouping() -> list[dict]:
    rows, bad = [], []
    for name, h, x, expect in COVERAGE_CASES:
        for ln in LINES:
            if ln.key not in expect:
                continue
            st = line_state(h, x, ln, OWNER)
            et, es, ed = expect[ln.key]
            ot, os_, od = text_discordance(st), segmentation_discordance(st), diagnostic_label(st)
            rows.append(
                {
                    "case": name,
                    "line": list(ln.key),
                    "h_text": st["h_text"],
                    "x_text": st["x_text"],
                    "common_gids": st["common_gids"],
                    "expected": {"text": et, "segmentation": es, "diagnostic": ed},
                    "observed": {"text": ot, "segmentation": os_, "diagnostic": od},
                    "in_d_frame": line_discordance(st),
                }
            )
            if (et, es, ed) != (ot, os_, od):
                bad.append(f"{name}@{ln.ordinal} expected=({et},{es},{ed}) observed=({ot},{os_},{od})")
            print(
                f"  {name[:44]:44} line{ln.ordinal} text={ot!s:5} seg={os_!s:5} diag={od!s:12} "
                f"{'OK' if (et, es, ed) == (ot, os_, od) else 'MISMATCH'}"
            )
    check(
        "coverage defects and grouping defects are classified independently",
        [],
        bad,
        "loss and duplication must never move the segmentation metric; a merge must still "
        "be detected when the merging arm ALSO loses a glyph",
    )
    return rows


# --------------------------------------------------------------------------- part 8


def part8_denominator() -> dict:
    """Both denominators on one population, so the estimand choice is visible, not asserted."""
    both_absent = [line_state([], [], ln, OWNER) for ln in LINES]  # page furniture
    discordant = line_state([el(0, 1, 2)], [el(0), el(1, 2)], LINES[0], OWNER)
    agreeing = line_state([el(3, 4, 5)], [el(3, 4, 5)], LINES[1], OWNER)
    pop = [discordant, agreeing] + both_absent
    got = m0(pop)
    out = {
        "population": "1 discordant + 1 agreeing + 3 jointly absent",
        "all_lines_denominator": got["neutral_lines_in_scope"],
        "risk_set_denominator": got["risk_set"],
        "M0_any_rate_risk_set": got["M0_any_rate"],
        "M0_any_rate_all_lines_superseded": got["M0_any_rate_ALL_LINES_superseded"],
    }
    check(
        "the two denominators give materially different rates on the same population",
        (0.5, 0.2),
        (got["M0_any_rate"], got["M0_any_rate_ALL_LINES_superseded"]),
        "3 of 5 lines are page furniture neither arm emitted; counting them as agreements "
        "makes the reported rate a function of how much chrome the document carries",
    )
    check(
        "jointly absent lines are retained as a raw count, not discarded",
        3,
        got["both_absent"],
    )
    return out


# --------------------------------------------------------------------------- part 9


def part9_frame_conditioning() -> dict:
    """Does the neutral frame condition RQ1's numbers, or only RQ2's?

    A22 said RQ1 was "unaffected" by a failed cross-engine control because both arms
    inherit the same frame. That is too strong, and this measures why.

    TESTED FIRST, and it did NOT support the obvious argument: the per-line comparative
    VERDICT proved robust to the partitions tried here -- a merge/split disagreement is
    still detected whether the frame separates the two physical lines or merges them. So
    the conditioning does NOT enter by flipping an individual verdict, and claiming it did
    would have been an argument constructed rather than measured.

    It enters through the DENOMINATOR AND POPULATION. The same architecture outputs, scored
    against two different neutral partitions of the same glyphs, give different M0 rates,
    because the frame decides how many neutral lines exist, which of them are in the risk
    set, and -- through the 8-line region grid -- which regions enter the D-frame and which
    are drawn into the C-frame.
    """
    h = [el(0, 1, 2, 3, 4, 5), el(6, 7, 8)]
    x = [el(0, 1, 2), el(3, 4, 5), el(6, 7, 8)]

    fine = [line_state(h, x, ln, OWNER) for ln in LINES]  # N0, N1, N2
    # a coarser frame: N0 and N1 seen as ONE physical line, exactly A19's recorded
    # two-column limit, with N2 unchanged
    coarse_lines = cluster(
        [sg(i, 700.0 if i < 6 else 676.0, 72 + 20 * (i % 3), 90 + 20 * (i % 3)) for i in range(9)], 1
    )
    coarse_owner = build_owner(coarse_lines)
    coarse = [line_state(h, x, ln, coarse_owner) for ln in coarse_lines]

    m_fine, m_coarse = m0(fine), m0(coarse)
    out = {
        "fine_frame": {"lines": m_fine["risk_set"], "M0_any": m_fine["M0_any"], "rate": m_fine["M0_any_rate"]},
        "coarse_frame": {"lines": m_coarse["risk_set"], "M0_any": m_coarse["M0_any"], "rate": m_coarse["M0_any_rate"]},
    }
    check(
        "identical architecture output scores a DIFFERENT M0 under a different frame",
        True,
        m_fine["M0_any_rate"] != m_coarse["M0_any_rate"],
        "so RQ1's reported numbers are conditional on the PDFium frame, and a failed "
        "cross-engine control must qualify RQ1 as well as RQ2",
    )
    check(
        "...while the per-line comparative verdict itself survived both frames",
        (True, True),
        (
            any(line_discordance(s) for s in fine),
            any(line_discordance(s) for s in coarse),
        ),
        "the conditioning is on denominators and populations, NOT on verdict direction -- "
        "stated precisely rather than overclaimed",
    )
    print(f"  fine frame:   {out['fine_frame']}")
    print(f"  coarse frame: {out['coarse_frame']}")
    return out


# -------------------------------------------------------------------------- part 10
#
# A24.2: PROVENANCE is not NEUTRAL INK IDENTITY. A content-stream space has real provenance
# and no physical ink identity. These cases pin that the split preserves architecture TEXT
# while removing the space from IDENTITY -- the failure mode being that a space, once it
# loses its gid, gets treated as a foreign glyph and erased from the projection.


# One neutral line of ink: gids 0,1,2 = A B C. Spaces never own identity.
def cs_space(sci):
    """A CONTENT-STREAM space: real provenance, no neutral identity."""
    return Cell(ngid=None, char=" ", sci=sci, generated=False)


def gen_space(sci):
    """A PDFium-GENERATED space: provenance if useful, no neutral identity."""
    return Cell(ngid=None, char=" ", sci=sci, generated=True)


def ins_space():
    """An X-INSERTED space: no provenance at all, no neutral identity."""
    return Cell(ngid=None, char=" ", sci=None, generated=False)


def part10_provenance_vs_identity() -> list[dict]:
    rows, bad = [], []

    def case(name, emitted, line, expected):
        got = contribution(emitted, line)
        rows.append({"case": name, "expected": expected, "observed": got})
        if got != expected:
            bad.append(f"{name}: expected {expected!r} observed {got!r}")

    # 1. content-stream space BETWEEN ink of the same neutral line -> KEPT
    case(
        "content-stream space between ink of one neutral line",
        [EmittedLine([Cell(0, "A", 0), cs_space(1), Cell(1, "B", 2)])],
        LINES[0],
        "A B",
    )
    # 2. generated space, same position -> KEPT, identically
    case(
        "generated space between ink of one neutral line",
        [EmittedLine([Cell(0, "A", 0), gen_space(1), Cell(1, "B", 2)])],
        LINES[0],
        "A B",
    )
    # 3. X-inserted space -> KEPT, identically
    case(
        "X-inserted space between ink of one neutral line",
        [EmittedLine([Cell(0, "A", 0), ins_space(), Cell(1, "B", 2)])],
        LINES[0],
        "A B",
    )
    # 4. space between ink of DIFFERENT neutral lines -> dropped from both
    merged = [EmittedLine([Cell(0, "A", 0), cs_space(1), Cell(3, "D", 2)])]
    case("space across two neutral lines, seen from N0", merged, LINES[0], "A")
    case("space across two neutral lines, seen from N1", merged, LINES[1], "D")
    # 5. leading space -> dropped
    case("leading space before the first ink glyph", [EmittedLine([cs_space(9), Cell(0, "A", 0)])], LINES[0], "A")
    # 6. trailing space -> dropped
    case("trailing space after the last ink glyph", [EmittedLine([Cell(0, "A", 0), cs_space(9)])], LINES[0], "A")
    # 7. consecutive spaces -> kept together
    case(
        "consecutive spaces between owned ink",
        [EmittedLine([Cell(0, "A", 0), cs_space(1), ins_space(), Cell(1, "B", 2)])],
        LINES[0],
        "A  B",
    )
    # 8. space between owned ink and a FOREIGN glyph -> dropped
    case(
        "space between owned ink and a foreign glyph",
        [EmittedLine([Cell(0, "A", 0), cs_space(1), Cell(99, "Z", 2)])],
        LINES[0],
        "A",
    )
    check("Model G attachment holds for every space provenance and position", [], bad)

    # a space must never become identity merely because it needs attachment semantics
    el_line = EmittedLine([Cell(0, "A", 0), cs_space(1), Cell(1, "B", 2)])
    check(
        "a content-stream space contributes TEXT but never IDENTITY",
        ([0, 1], "A B"),
        (sorted(el_line.gids), el_line.text()),
        "gids carries neutral ink only; the space is visible in text and absent from identity",
    )
    check(
        "provenance survives on the cell even with no neutral identity",
        (None, 1, False),
        (el_line.cells[1].ngid, el_line.cells[1].sci, el_line.cells[1].generated),
    )
    # spaces cannot move the signature, whatever their provenance
    plain = reconstruction_signature([EmittedLine([Cell(0, "A", 0), Cell(1, "B", 1)])], LINES[0], OWNER, {0, 1, 2})
    check(
        "no space provenance can move the reconstruction signature",
        [plain, plain, plain],
        [
            reconstruction_signature(
                [EmittedLine([Cell(0, "A", 0), cs_space(1), Cell(1, "B", 2)])], LINES[0], OWNER, {0, 1, 2}
            ),
            reconstruction_signature(
                [EmittedLine([Cell(0, "A", 0), gen_space(1), Cell(1, "B", 2)])], LINES[0], OWNER, {0, 1, 2}
            ),
            reconstruction_signature(
                [EmittedLine([Cell(0, "A", 0), ins_space(), Cell(1, "B", 2)])], LINES[0], OWNER, {0, 1, 2}
            ),
        ],
        "segmentation must respond to grouping, never to spacing",
    )
    return rows


# -------------------------------------------------------------------------- part 11


def part11_hr_fixture() -> dict:
    """The `H. R. 2029` disagreement, frozen as a regression fixture.

    A24.1 ruled that X2-b is about PDFium-GENERATED spaces, so X declining to reproduce a
    CONTENT-STREAM space is not a contract violation -- it is a genuine architecture
    disagreement, and deciding who is right is the ORACLE's job, not the gate's.

    This fixture exists so that ruling cannot silently rot: the disagreement must stay
    visible as comparative TEXT discordance and must remain scorable by M3.

    WHAT IT PROVES, exactly: the spacing disagreement survives contract validation and
    reaches M3, and GIVEN A SYNTHETIC ORACLE OF `H. R. 2029` the scoring path classifies it
    as `X_REGRESSES`.

    WHAT IT DOES NOT PROVE: that H's form is the correct one on the real document. The oracle
    here is a fixture chosen to exercise the pipeline, not an adjudication. Whether
    `H. R. 2029` or `H.R.2029` is right on `114-hr-2029/4` is a question for the independent
    oracle, which does not exist yet. This is a PIPELINE test, not a correctness finding.
    """
    # 'H','.','R','.','2','0','2','9' are ink; the two spaces are content-stream.
    glyphs = [SourceGlyph(i, 500.0, 72.0 + 12 * i, 500.0, 80.0 + 12 * i, 512.0) for i in range(8)]
    lines = cluster(glyphs, 1)
    owner = build_owner(lines)
    ln = lines[0]
    chars = "H.R.2029"
    h_cells = []
    for i, ch in enumerate(chars):
        h_cells.append(Cell(i, ch, i))
        if i in (1, 3):  # H. _ R. _ 2029, spaces supplied by the content stream
            h_cells.append(cs_space(100 + i))
    h = [EmittedLine(h_cells)]
    x = [EmittedLine([Cell(i, ch, i) for i, ch in enumerate(chars)])]

    st = line_state(h, x, ln, owner)
    outcome, hs, xs = heading_outcome("H. R. 2029", st["h_text"], st["x_text"])
    check("H.R. fixture: H projects the content-stream spaces", "H. R. 2029", st["h_text"])
    check("H.R. fixture: X projects no space it did not derive", "H.R.2029", st["x_text"])
    check("H.R. fixture: this is TEXT discordance", True, text_discordance(st))
    check(
        "H.R. fixture: and NOT segmentation discordance",
        False,
        segmentation_discordance(st),
        "the arms grouped the same ink identically; only the spacing differs",
    )
    check("H.R. fixture: it enters the D-frame", True, line_discordance(st))
    check(
        "H.R. fixture: it stays scorable by M3 rather than being filtered by the contract",
        (HeadingOutcome.X_REGRESSES, True, False),
        (outcome, hs.clean, xs.clean),
        "the eligibility gate does not decide correctness -- the oracle does",
    )
    return {
        "h_text": st["h_text"],
        "x_text": st["x_text"],
        "text_discordance": text_discordance(st),
        "segmentation_discordance": segmentation_discordance(st),
        "m3_outcome": str(outcome),
        "m3_x_weld": xs.weld,
        "m3_x_split": xs.split,
    }


def main() -> int:
    print("== part 1: the defect, reproduced under the superseded rule ==")
    defect = part1_defect()
    print("\n== part 2: adversarial case matrix ==")
    matrix = part2_matrix()
    print("\n== part 3: non-vacuous symmetry ==")
    part3_symmetry()
    print("\n== part 4: M3 is preserved ==")
    part4_m3_preserved()
    print("\n== part 5: M0 components ==")
    m0_out = part5_m0()
    print("\n== part 6: negative controls ==")
    part6_negative_controls()
    print("\n== part 7: coverage is not grouping ==")
    coverage = part7_coverage_vs_grouping()
    print("\n== part 8: M0's denominator ==")
    denom = part8_denominator()
    print("\n== part 9: does the frame condition RQ1? ==")
    framing = part9_frame_conditioning()
    print("\n== part 10: provenance is not neutral ink identity ==")
    provenance = part10_provenance_vs_identity()
    print("\n== part 11: the H. R. 2029 fixture ==")
    hr = part11_hr_fixture()

    doc = {
        "population": "SYNTHETIC only -- no holdout opened, no architecture run",
        "supersedes": "A21's D-frame membership rule (any line not SAME); A22's gid-subset signature",
        "defect": defect,
        "matrix": matrix,
        "coverage_vs_grouping": coverage,
        "denominator": denom,
        "frame_conditioning": framing,
        "provenance_vs_identity": provenance,
        "hr_fixture": hr,
        "m0": m0_out,
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
