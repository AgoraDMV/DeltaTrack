"""x07 -- test the neutral ink-line skeleton. DESIGN MATERIAL for the A17 resolution.

NOT CONFIRMATORY. Synthetic fixtures plus DEVELOPMENT documents. No holdout is opened.

Part 1: synthetic adversarial fixtures for the clustering, identity and projection rules.
Part 2: the geometry-only C-frame predicate measured on development documents, with a
        sensitivity sweep over the two derived parameters.

Every synthetic fixture is (baseline, x0, y0, x1, y1) tuples -- geometry only, exactly what
`neutral_geometry` is allowed to see. Building them by hand rather than from a PDF is
deliberate: it proves the rule's behaviour without any engine in the loop.
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

from neutral_geometry import (  # noqa: E402
    body_height_and_enriched,
    centred_narrow_lines,
    cluster_page,
    project,
    project_by_glyphs,
    regions,
)

OUT = EV / "results" / "x07_neutral_geometry.json"
ROWS: list[dict] = []
FAILED: list[str] = []


def check(name: str, expected, observed, implication: str) -> None:
    ok = expected == observed
    ROWS.append(
        {
            "test": name,
            "expected": expected,
            "observed": observed,
            "pass": ok,
            "implication": implication,
        }
    )
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  expected={expected!r} observed={observed!r}")
    if not ok:
        FAILED.append(name)


def g(baseline: float, x0: float, x1: float, h: float = 10.0):
    """One ink glyph: baseline, box. Height h, sitting on the baseline."""
    return (baseline, x0, baseline, x1, baseline + h)


# --------------------------------------------------------------- part 1: synthetic
def synthetic() -> None:
    # two ordinary adjacent lines (GPO body leading is ~12 pt for 10 pt type)
    two = [g(700, 72, 200), g(700, 205, 300), g(688, 72, 250)]
    check("two ordinary adjacent lines", 2, len(cluster_page(two, 1)), "ordinary leading separates")

    # very close baselines: 2 pt apart on 10 pt type -> tol is 5 pt -> ONE line.
    close = [g(700, 72, 200), g(698, 210, 300)]
    check(
        "two lines 2pt apart merge (tol=5pt)",
        1,
        len(cluster_page(close, 1)),
        "sub-tolerance baselines are one physical line; this is the documented limit",
    )

    # superscript: +3 pt, smaller box -> rides with the body line
    sup = [g(700, 72, 200), (703.0, 201, 703.0, 205, 709.0), g(688, 72, 250)]
    check(
        "superscript rides with its body line", 2, len(cluster_page(sup, 1)), "footnote markers do not fabricate a line"
    )

    # subscript: -3 pt -> rides with the body line
    sub = [g(700, 72, 200), (697.0, 201, 697.0, 205, 703.0), g(688, 72, 250)]
    check("subscript rides with its body line", 2, len(cluster_page(sub, 1)), "same, downward")

    # large heading (18 pt) then body (10 pt): median height 10, tol 5, 20 pt gap -> 2 lines
    head = [g(700, 72, 300, h=18.0), g(680, 72, 250, h=10.0)]
    check("large heading then body", 2, len(cluster_page(head, 1)), "display type does not swallow body")

    # letter-spaced display heading: many separate glyphs, one baseline -> ONE line
    spaced = [g(700, 72 + i * 14, 78 + i * 14, h=14.0) for i in range(8)]
    check(
        "letter-spaced display heading is one line",
        1,
        len(cluster_page(spaced, 1)),
        "the C O N T E N T S case does not become 8 lines",
    )

    # margin line number on the same baseline as its body line -> ONE line
    margin = [g(700, 50, 60), g(700, 72, 300)]
    check(
        "margin line number joins its body line",
        1,
        len(cluster_page(margin, 1)),
        "GPO sets the number on the body baseline",
    )

    # same physical line split across PDF text objects -> still ONE line
    split_objs = [g(700, 72, 140), g(700, 141, 210), g(700, 211, 300)]
    check(
        "one physical line from 3 text objects",
        1,
        len(cluster_page(split_objs, 1)),
        "text-object boundaries are invisible to the skeleton",
    )

    # two-column page: both columns share baselines -> merges. KNOWN LIMIT, asserted so it
    # is a recorded property rather than a surprise at execution time.
    two_col = [g(700, 72, 250), g(700, 320, 500), g(688, 72, 250), g(688, 320, 500)]
    check(
        "two-column page MERGES columns (known limit)",
        2,
        len(cluster_page(two_col, 1)),
        "single-column GPO bills are unaffected; report tables are not, and A17-N records it",
    )

    # table row of fragments on one baseline -> one line
    table = [g(700, 72, 120), g(700, 200, 240), g(700, 380, 430)]
    check(
        "table row of fragments is one line",
        1,
        len(cluster_page(table, 1)),
        "column fragments on a shared baseline are one neutral row",
    )

    # ---- identity stability ----
    base = [g(700, 72, 200), g(688, 72, 250), g(676, 72, 250)]
    ids = [ln.key for ln in cluster_page(base, 7)]
    check(
        "neutral ids are (page, ordinal) top-to-bottom",
        [(7, 0), (7, 1), (7, 2)],
        ids,
        "identity is a pure function of geometry",
    )
    # identical visible text repeated cannot collide: identity never reads text at all
    check(
        "identity is stable when glyph ORDER is shuffled",
        ids,
        [ln.key for ln in cluster_page(list(reversed(base)), 7)],
        "input order cannot change identity",
    )

    # ---- projection: A17.4 ----
    lines = cluster_page(base, 1)
    check("H line projects onto its neutral line", 1, project(lines, 688.0), "geometric projection, no text similarity")
    check(
        "X line at a 1pt offset still projects to the same neutral line",
        1,
        project(lines, 689.0),
        "sub-tolerance jitter does not move the slot",
    )
    check(
        "a line far from any neutral baseline projects to None",
        None,
        project(lines, 400.0),
        "fails closed rather than snapping to the nearest",
    )
    # H merges two neutral lines. Baseline-proximity projection FAILS here: 694 is 6 pt from
    # both 700 and 688 while the tolerance is 5 pt, so it returns None and the comparison
    # unit vanishes for exactly the merge case the D-frame exists to detect.
    check(
        "baseline-proximity projection LOSES a merged line",
        None,
        project(lines, 694.0),
        "why membership projection replaces it",
    )
    check(
        "membership projection puts a merged line on one slot",
        0,
        project_by_glyphs(lines, [700.0, 700.0, 688.0]),
        "plurality of glyphs; ties to the lowest ordinal",
    )
    check(
        "membership projection handles a SPLIT line",
        1,
        project_by_glyphs(lines, [688.0]),
        "a split half lands on its own neutral line",
    )
    check(
        "membership projection with no glyphs is None",
        None,
        project_by_glyphs(lines, []),
        "fails closed",
    )

    # A justified body line spans the measure; a paragraph tail is narrow but LEFT-aligned;
    # a GPO account heading is narrow and CENTRED.
    # A realistic page: 10 justified body lines reaching the measure, one left-aligned
    # paragraph tail, one centred heading. Percentile margins need a real population.
    page = [g(700 - 12 * i, 72, 500) for i in range(10)]
    page += [g(700 - 12 * 10, 72, 300), g(700 - 12 * 11, 220, 350)]
    check(
        "centred-narrow flags the centred line only",
        1,
        len(centred_narrow_lines(cluster_page(page, 1))),
        "separates a heading from body prose and from a left-aligned paragraph tail",
    )

    # ---- regions ----
    many = [g(700 - 12 * i, 72, 250) for i in range(20)]
    regs = regions(cluster_page(many, 1), size=8)
    check("20 neutral lines -> 3 non-overlapping regions", 3, len(regs), "aligned to page start")
    check(
        "regions partition the lines exactly once",
        20,
        sum(r["n_lines"] for r in regs),
        "no line is dropped or double-counted",
    )
    check(
        "the short trailing region is kept",
        4,
        regs[-1]["n_lines"],
        "page bottoms carry continuation text and must not be silently dropped",
    )


# ----------------------------------------------------- part 2: development documents
def development(limit: int = 20) -> list[dict]:
    import pdfium_hybrid

    docs = [
        ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
        ("118-hr-4366/5", REPO / "tests/corpus/118-hr-4366/5_engrossed-amendment-house.pdf"),
        ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
        ("CRPT-118srpt198", REPO / "tests/data/CRPT-118srpt198.pdf"),
    ]
    from contract_hybrid import BASELINE, CP, SIZE, UPRIGHT, VBOX, X0, X1

    out = []
    for name, path in docs:
        if not path.exists():
            print(f"  MISSING {path}", file=sys.stderr)
            continue
        pages, _ = pdfium_hybrid.extract(path, limit=limit)
        all_lines = []
        for p in pages:
            glyphs = []
            for c in p.chars:
                # INK ONLY: an engine-generated space has no box. Excluding them is what
                # makes the skeleton identical under H and under X.
                if c[X0] is None or c[X1] is None or c[VBOX] is None or not c[UPRIGHT]:
                    continue
                if c[CP] in (10, 13, 32):
                    continue
                if c[SIZE] is None or c[SIZE] <= 1.0:
                    continue
                all_lines.append((c[BASELINE], c[X0], c[VBOX][0], c[X1], c[VBOX][1], p.page_number))
            del glyphs
        by_page: dict[int, list] = {}
        for b, x0, y0, x1, y1, pg in all_lines:
            by_page.setdefault(pg, []).append((b, x0, y0, x1, y1))
        lines = []
        for pg in sorted(by_page):
            lines.extend(cluster_page(by_page[pg], pg))

        # CENTRED-NARROW enrichment, and a VALIDATION of it against hybrid's own anchors.
        # Using H's headings to VALIDATE a neutral predicate is legitimate; using them to
        # DEFINE the frame is not, and the predicate itself never sees them.
        centred_ids = centred_narrow_lines(lines)
        centred_lines = [ln for ln in lines if id(ln) in centred_ids]
        centred_pages = {ln.page for ln in centred_lines}

        import reconstruct_hybrid
        from deltatrack.parsers.pdf_anchors import extract_anchors

        recon, _ = reconstruct_hybrid.reconstruct(pages)
        anchor_pages = {a.page_number for a in extract_anchors(recon) if a.kind in ("account", "agency")}
        n_pages = max(len(by_page), 1)
        validation = {
            "pages_with_a_hybrid_account_or_agency_anchor": len(anchor_pages),
            "pages_flagged_by_centred_narrow": len(centred_pages),
            "overlap": len(anchor_pages & centred_pages),
            "recall_of_anchor_pages": round(len(anchor_pages & centred_pages) / len(anchor_pages), 3)
            if anchor_pages
            else None,
            "share_of_all_pages_flagged": round(len(centred_pages) / n_pages, 3),
        }

        sweep = {}
        for quantum in (0.25, 0.5, 1.0):
            body, enriched = body_height_and_enriched(lines, quantum=quantum)
            sweep[str(quantum)] = {"body_height": body, "pages_enriched": len(enriched)}
        body, enriched = body_height_and_enriched(lines, quantum=0.5)
        rec = {
            "document": name,
            "pages": len(by_page),
            "neutral_lines": len(lines),
            "lines_per_page_median": round(len(lines) / max(len(by_page), 1), 1),
            "body_height_q0.5": body,
            "pages_enriched_q0.5": len(enriched),
            "pages_enriched_share": round(len(enriched) / max(len(by_page), 1), 3),
            "quantum_sensitivity": sweep,
            "centred_narrow_lines": len(centred_lines),
            "centred_narrow_validation": validation,
        }
        out.append(rec)
        print(
            f"  {name:16} pages={rec['pages']:3} lines={rec['neutral_lines']:5} "
            f"lines/page={rec['lines_per_page_median']:5} body_h={body:5} "
            f"height-enriched={rec['pages_enriched_q0.5']:3} ({rec['pages_enriched_share']}) "
            f"| centred: pages={validation['pages_flagged_by_centred_narrow']:3} "
            f"share={validation['share_of_all_pages_flagged']} "
            f"recall_of_anchor_pages={validation['recall_of_anchor_pages']}"
        )
    return out


def main() -> int:
    print("== part 1: synthetic adversarial fixtures ==")
    synthetic()
    print("\n== part 2: development documents ==")
    dev = development()

    doc = {
        "population": "SYNTHETIC + DEVELOPMENT -- no holdout opened",
        "purpose": "test the neutral ink-line skeleton proposed to resolve A17.2-A17.4",
        "rule": {
            "neutral_facts": ["baseline (pen origin y)", "glyph box x0/y0/x1/y1", "page number"],
            "forbidden": [
                "codepoint",
                "font name",
                "word spacing",
                "case",
                "heading label",
                "architecture line ordinal",
            ],
            "tolerance": "0.5 * median ink height on the page (derived, not a constant)",
            "ordering": "descending baseline = top-to-bottom; ordinal is the index",
            "anchor": "first glyph of the cluster, so drift cannot walk a cluster down the page",
            "regions": "non-overlapping windows of 8 neutral lines, aligned to page start, short tail kept",
            "projection": "nearest neutral baseline within tolerance; no text similarity",
        },
        "synthetic_tests": ROWS,
        "synthetic_failures": FAILED,
        "development": dev,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} synthetic tests pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
