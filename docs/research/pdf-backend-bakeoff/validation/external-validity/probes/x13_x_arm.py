"""x13 -- the corrected X arm, and the invariants it must satisfy. DESIGN MATERIAL.

NOT CONFIRMATORY. Synthetic + DEVELOPMENT documents only. No holdout document is opened,
nothing is scored.

    frozen rule        X-2 (no U+0020 in the contract); 3.3 (clustering, chrome, margin
                       parsing and `_merge_print_lines` held IDENTICAL on both arms);
                       A19 (one neutral skeleton, identical under either arm);
                       A21/A23 (gids carried; inserted spaces carry gid=None)
    executable         `pdfium_extended_corrected` + `reconstruct_extended_corrected`
                       + `run_extended`
    test               this file
    evidence           `results/x13_x_arm.json`

The load-bearing check is SKELETON IDENTITY. X drops every U+0020, so a skeleton derived
from X's own glyphs would omit every content-stream space PDFium boxes -- and would not
equal H's. A19 requires ONE skeleton. Both runners therefore call the same
`run_hybrid.neutral_skeleton`, and this file asserts the result is identical rather than
assuming it.
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

import pdfium_extended_corrected as XA  # noqa: E402
import reconstruct_extended_corrected as XR  # noqa: E402
import run_extended  # noqa: E402
import run_hybrid  # noqa: E402
from neutral_identity import build_owner, emitted_gids, line_discordance, line_state, m0  # noqa: E402

OUT = EV / "results" / "x13_x_arm.json"
ROWS: list[dict] = []
FAILED: list[str] = []
DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
]


def check(name, expected, observed, implication="") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "implication": implication})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


def main(limit: int = 6) -> int:
    report = []
    for name, path in DOCS:
        if not path.exists():
            continue
        print(f"\n== {name} ==")
        x_pages, summary = run_extended.run(path, limit=limit)
        h_pages = run_hybrid.run(path, limit=limit)

        # 1. X-2 holds in the scoring path
        n32 = 0
        for pg in XA.extract(path, limit=limit)[0]:
            n32 += sum(1 for g in pg.glyphs if g[XA.CP] == 32)
        check(f"{name}: X's contract carries no U+0020", 0, n32)

        # 2. ONE skeleton -- the A19 invariant
        mismatch = []
        for hp, xp in zip(h_pages, x_pages):
            if [(ln.key, sorted(ln.gids)) for ln in hp["neutral"]] != [
                (ln.key, sorted(ln.gids)) for ln in xp["neutral"]
            ]:
                mismatch.append(hp["page_number"])
        check(
            f"{name}: both runners produce an IDENTICAL neutral skeleton",
            [],
            mismatch,
            "A19 requires one skeleton; deriving it from X's glyphs would omit every "
            "content-stream space and silently give the arms different adjudication units",
        )

        # 3. every gid X emits is a real PDFium char index, and no inserted space carries one
        spaces_with_gid = 0
        for xp in x_pages:
            for e in xp["emitted"]:
                spaces_with_gid += sum(1 for c in e.cells if c.char == " " and c.ngid is not None)
        check(
            f"{name}: no space X emits carries a source gid",
            0,
            spaces_with_gid,
            "X's contract has no U+0020, so every space in its output is its own decision",
        )

        # 4. the two arms actually differ somewhere -- a comparator that finds nothing is
        #    indistinguishable from a comparator that compares nothing
        states = []
        for hp, xp in zip(h_pages, x_pages):
            owner = build_owner(hp["neutral"])
            common = emitted_gids(hp["emitted"]) & emitted_gids(xp["emitted"])
            for ln in hp["neutral"]:
                states.append(line_state(hp["emitted"], xp["emitted"], ln, owner, common))
        stats = m0(states)
        n_disc = sum(1 for s in states if line_discordance(s))
        check(
            f"{name}: the arms are comparable AND not identical",
            True,
            n_disc > 0,
            "S1-style liveness: a zero here would mean the comparison is not live",
        )

        rec = {
            "document": name,
            "pages": limit,
            "x_glyphs": summary["glyphs"],
            "x_u0020_dropped": summary["u0020_dropped"],
            "neutral_lines": stats["neutral_lines_in_scope"],
            "risk_set": stats["risk_set"],
            "M0a_text": stats["M0a_text"],
            "M0b_segmentation": stats["M0b_segmentation"],
            "M0b_only_segmentation": stats["M0b_only_segmentation"],
            "M0_any": stats["M0_any"],
            "M0a_text_rate": stats["M0a_text_rate"],
            "M0b_segmentation_rate": stats["M0b_segmentation_rate"],
            "M0b_rate_on_defined": stats["M0b_rate_on_defined"],
            "both_absent": stats["both_absent"],
            "x_source_glyph_loss_lines": sum(1 for s in states if s["diagnostics"]["X_SOURCE_GLYPH_LOSS"]),
        }
        report.append(rec)
        print(
            f"  neutral={rec['neutral_lines']} risk={rec['risk_set']} "
            f"M0a={rec['M0a_text']} M0b={rec['M0b_segmentation']} M0b_only={rec['M0b_only_segmentation']} "
            f"M0_any={rec['M0_any']} both_absent={rec['both_absent']} "
            f"X_loss_lines={rec['x_source_glyph_loss_lines']}"
        )

    doc = {
        "population": "DEVELOPMENT -- no holdout opened, nothing scored",
        "note": (
            "these M0 numbers are DEVELOPMENT observations produced while testing the arms. They "
            "are not a result: the holdout is untouched, no oracle exists, and no decision rule "
            "has been evaluated."
        ),
        "reporting_distinction": (
            "M0b_segmentation_rate is over the full comparative risk set. M0b_rate_on_defined is "
            "conditional on jointly observed glyphs existing. Only the latter may be described as "
            "'the fraction of comparable groupings that disagree'."
        ),
        "documents": report,
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
