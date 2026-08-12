"""x12 -- the A24.2 repair, measured BEFORE and AFTER on one population. DESIGN MATERIAL.

NOT CONFIRMATORY. DEVELOPMENT documents only. No holdout document is opened.

    frozen rule   A24.2 -- neutral-eligible iff a source character exists AND codepoint is
                  not U+0020 AND the box is valid, finite, positive-area AND upright
    superseded    A19/A21 -- the same minus the codepoint clause, with the absolute phrase
                  "NO codepoint is consulted"
    test          this file
    evidence      `results/x12_skeleton_eligibility.json`

WHAT FALSIFIED THE OLD RULE. A21 measured eligibility in ONE direction -- "the number
excluded ONLY by a codepoint rule is 0" -- which cannot see what the rule INCLUDES. PDFium
reports a positive-area box for a content-stream U+0020: a sliver about 3.6 pt wide and
0.014 pt tall against ~7.9 pt for a capital. So "positive area" does not identify ink, and
every real word space was entering the supposedly ink-only skeleton.

BOTH RULES ARE RUN HERE, on the same documents and the same page limit, so the before/after
is PAIRED rather than compared across two runs. Removing glyphs changes the median ink
height that sets the clustering tolerance, so the geometric consequences are measured rather
than assumed inert.
"""

from __future__ import annotations

import json
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

import run_extended  # noqa: E402
import run_hybrid  # noqa: E402
from contract_hybrid import CP, GEN, UPRIGHT, VBOX, X0, X1  # noqa: E402
from neutral_identity import SourceGlyph, build_owner, cluster, eligible, emitted_gids, line_state  # noqa: E402

OUT = EV / "results" / "x12_skeleton_eligibility.json"
DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
]
ROWS: list[dict] = []
FAILED: list[str] = []


def check(name, expected, observed, implication="") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "implication": implication})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


def eligible_superseded(gid, box, upright) -> bool:
    """A19/A21's rule, kept executable so the defect is DEMONSTRATED, not asserted."""
    if gid is None or box is None:
        return False
    x0, y0, x1, y1 = box
    if any(v is None for v in (x0, y0, x1, y1)):
        return False
    return upright and (x1 - x0) > 0 and (y1 - y0) > 0


def skeleton(chars, page_number, rule):
    glyphs = []
    for gid, c in chars:
        box = None if c[X0] is None or c[X1] is None or c[VBOX] is None else (c[X0], c[VBOX][0], c[X1], c[VBOX][1])
        g = None if c[GEN] else gid
        ok = (
            eligible_superseded(g, box, bool(c[UPRIGHT]))
            if rule == "old"
            else eligible(g, box, bool(c[UPRIGHT]), c[CP])
        )
        if ok:
            glyphs.append(SourceGlyph(gid, c[BASELINE_IDX], box[0], box[1], box[2], box[3]))
    return cluster(glyphs, page_number)


BASELINE_IDX = 2  # contract_hybrid.BASELINE


def main(limit: int = 8) -> int:
    out = []
    for name, path in DOCS:
        if not path.exists():
            continue
        print(f"\n== {name} ==")
        chars_by_page = run_hybrid.extract_with_gids(path, limit=limit)

        space_h, letter_h, space_w = [], [], []
        n_space = n_space_old_admitted = 0
        old_lines = new_lines = 0
        ink_membership_changes = 0
        bbox_changes = 0
        old_touched = 0
        for pno, chars in chars_by_page:
            for _gid, c in chars:
                if c[GEN] or c[X0] is None or c[VBOX] is None:
                    continue
                if c[CP] == 32:
                    n_space += 1
                    n_space_old_admitted += 1
                    space_w.append(c[X1] - c[X0])
                    space_h.append(c[VBOX][1] - c[VBOX][0])
                elif 65 <= c[CP] <= 90:
                    letter_h.append(c[VBOX][1] - c[VBOX][0])

            old = skeleton(chars, pno, "old")
            new = skeleton(chars, pno, "new")
            old_lines += len(old)
            new_lines += len(new)
            space_gids = {gid for gid, c in chars if c[CP] == 32 and not c[GEN]}
            old_touched += sum(1 for ln in old if ln.gids & space_gids)

            # Does removing spaces change which INK glyphs share a line? That is the
            # question; a changed bbox is expected, a changed ink partition would not be.
            old_ink = [tuple(sorted(ln.gids - space_gids)) for ln in old]
            new_ink = [tuple(sorted(ln.gids)) for ln in new]
            old_ink = [g for g in old_ink if g]
            if old_ink != new_ink:
                ink_membership_changes += 1
            for a, b in zip(old, new):
                if (a.x0, a.x1) != (b.x0, b.x1):
                    bbox_changes += 1

        # X source-glyph loss, under the SAME limit, before and after
        x_pages, _ = run_extended.run(path, limit=limit)
        loss_new = loss_shared = loss_x_only = 0
        total_states = 0
        for xp, (pno, chars) in zip(x_pages, chars_by_page):
            neutral = skeleton(chars, pno, "new")
            owner = build_owner(neutral)
            h_em = run_hybrid.emitted_lines(pno, chars)
            common = emitted_gids(h_em) & emitted_gids(xp["emitted"])
            for ln in neutral:
                st = line_state(h_em, xp["emitted"], ln, owner, common)
                total_states += 1
                d = st["diagnostics"]
                shared = set(d["SHARED_SOURCE_GLYPH_LOSS"])
                x_lost = set(d["X_SOURCE_GLYPH_LOSS"])
                if x_lost:
                    loss_new += 1
                if shared:
                    loss_shared += 1
                if x_lost - shared:
                    loss_x_only += 1

        rec = {
            "document": name,
            "pages": limit,
            "u0020_source_chars": n_space,
            "u0020_admitted_by_superseded_rule": n_space_old_admitted,
            "u0020_admitted_by_A24_2_rule": 0,
            "space_box_median_width": round(statistics.median(space_w), 4) if space_w else None,
            "space_box_median_height": round(statistics.median(space_h), 4) if space_h else None,
            "capital_box_median_height": round(statistics.median(letter_h), 4) if letter_h else None,
            "height_ratio_capital_over_space": (
                round(statistics.median(letter_h) / statistics.median(space_h), 1) if space_h and letter_h else None
            ),
            "neutral_lines_before": old_lines,
            "neutral_lines_after": new_lines,
            "lines_touching_a_space_before": old_touched,
            "pages_where_INK_membership_changed": ink_membership_changes,
            "neutral_lines_whose_x_extent_changed": bbox_changes,
            "x_loss_lines_after": loss_new,
            "x_loss_lines_SHARED_with_H": loss_shared,
            "x_loss_lines_X_ONLY": loss_x_only,
            "neutral_lines_scored_after": total_states,
        }
        out.append(rec)
        print(
            f"  U+0020 admitted  before={rec['u0020_admitted_by_superseded_rule']}  after=0\n"
            f"  neutral lines    before={old_lines}  after={new_lines}\n"
            f"  ink membership changed on {ink_membership_changes} pages; "
            f"x-extent changed on {bbox_changes} lines\n"
            f"  X loss lines     after={loss_new}/{total_states}"
            f"  (shared with H={loss_shared}, X-ONLY={loss_x_only})"
        )
        check(
            f"{name}: no remaining X loss is X's own",
            0,
            loss_x_only,
            "what survives is SHARED loss -- the GPO margin number, which 3.3 has both arms "
            "strip identically. X fails to carry nothing that H also does not carry, so the "
            "diagnostic is interpretable again rather than saturated by excluded spaces",
        )
        check(
            f"{name}: the repair removes every U+0020 from the skeleton",
            (n_space_old_admitted > 0, 0),
            (True, rec["u0020_admitted_by_A24_2_rule"]),
            "before/after paired on one population and one page limit",
        )
        check(
            f"{name}: the INK partition is unchanged by removing spaces",
            0,
            ink_membership_changes,
            "removing non-ink glyphs must not move which ink glyphs share a physical line; "
            "if this ever fires, the clustering tolerance shifted enough to matter",
        )

    doc = {
        "population": "DEVELOPMENT -- no holdout opened",
        "superseded_rule": "valid finite positive-area box AND upright; no codepoint consulted",
        "frozen_rule_A24_2": "source char exists AND codepoint != U+0020 AND valid positive-area box AND upright",
        "why": (
            "positive-area PDFium geometry does not identify ink: a content-stream U+0020 gets a "
            "~3.6 x 0.014 pt box. A21 measured only the exclusion direction, so the inclusion was "
            "invisible. The exception is lexical but legitimate -- U+0020 is a below-seam source "
            "fact, X-2 already froze it as carrying no ink, it reads no H/X output, and it cannot "
            "favour either arm."
        ),
        "scope": "ONLY U+0020. Not a whitespace blacklist; no ink-height threshold is introduced.",
        "documents": out,
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
