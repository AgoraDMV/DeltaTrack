"""s1_control -- A38.9: the frozen S1 liveness control, with a committed producer.

    frozen rule   section 6 / A27.6 -- "extended advances x 1.25 must raise M0". A comparator
                  that reports few differences is only meaningful if it CAN report more; S1 is
                  what establishes M0 is live rather than comparing nothing. Phase 1 recorded a
                  comparator that fell from 98 differences to 0 on a flag, which is exactly the
                  failure this exists to detect.
    executable    `s1_result(pdf_path)` returns primary M0, sabotaged M0 and `fires`
    test          `x22_score_input_contract.py`

WHY THIS EXISTS AT ALL. `score_metrics` must be a pure consumer of committed artifacts: it may
not reopen a PDF or re-run an architecture. S1 needs a SECOND, deliberately sabotaged X run, so
somebody upstream has to produce it. That producer is here, and its output is a committed
pre-score artifact.

WHAT IS SABOTAGED, AND WHAT IS NOT. Only X's glyph ADVANCE values are scaled, which is the
input `wants_space` consumes when deciding whether a word space belongs between two glyphs.
Ordinary H and ordinary X are untouched: the sabotage runs on its own extraction, and no
primary artifact, frame, C/D membership or region is built from it.

THE SCALE IS NOT A PARAMETER on the result-bearing path. `S1_ADVANCE_SCALE` is frozen at 1.25.
`_m0_from_arms` takes no threshold and no tuning knob, so there is no dial to turn until S1
fires.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import pdfium_extended_corrected as XPDF  # noqa: E402
import reconstruct_extended_corrected as XREC  # noqa: E402
import run_hybrid  # noqa: E402
from neutral_identity import build_owner, emitted_gids, line_state, text_discordance  # noqa: E402

#: section 6, frozen. NOT a tunable parameter on any result-bearing path.
S1_ADVANCE_SCALE = 1.25

S1_DEAD_COMPARATOR = "S1_DEAD_COMPARATOR"


def scale_advances(page, scale: float = S1_ADVANCE_SCALE):
    """Return a copy of one X page with every glyph ADVANCE scaled. Nothing else moves.

    Geometry (`x0/y0/x1/y1`, `baseline`, `origin_x`) is untouched, so the neutral skeleton --
    which reads geometry only -- is IDENTICAL under sabotage. That is deliberate: A19 requires
    one skeleton, and a sabotage that moved it would be changing the frame rather than the
    seam decision under test.
    """
    glyphs = []
    for g in page.glyphs:
        row = list(g)
        if row[XPDF.ADVANCE] is not None:
            row[XPDF.ADVANCE] = row[XPDF.ADVANCE] * scale
        glyphs.append(tuple(row))
    return XPDF.ExtPdfPageCorrected(page_number=page.page_number, width=page.width, height=page.height, glyphs=glyphs)


def _x_pages(pdf_path: Path, limit: int | None, scale: float | None) -> list[dict]:
    """X's per-page emitted lines, optionally sabotaged. Mirrors `run_extended.run`'s shape."""
    pages, _summary = XPDF.extract(pdf_path, limit=limit)
    hybrid_pages = run_hybrid.extract_with_gids(pdf_path, limit=limit)
    by_page = {pno: chars for pno, chars in hybrid_pages}
    out = []
    for pg in pages:
        source = pg if scale is None else scale_advances(pg, scale)
        _page_obj, emitted, _diag = XREC.reconstruct_page(source)
        out.append(
            {
                "page_number": pg.page_number,
                "emitted": emitted,
                "neutral": run_hybrid.neutral_skeleton(pg.page_number, by_page[pg.page_number]),
            }
        )
    return out


def _m0_from_arms(h_pages: list[dict], x_pages: list[dict]) -> dict:
    """M0 on the SAME definition the primary comparison uses: A22/A23 text discordance.

    Reuses `neutral_identity.line_state` / `text_discordance` -- the exact functions
    `build_frames` calls -- rather than a second notion of "the text differs", so the S1 row
    and the reported M0 cannot drift apart into two incomparable quantities.
    """
    x_by_page = {d["page_number"]: d for d in x_pages}
    risk, discordant = 0, 0
    for h in h_pages:
        x = x_by_page[h["page_number"]]
        owner = build_owner(h["neutral"])
        common = emitted_gids(h["emitted"]) & emitted_gids(x["emitted"])
        for line in h["neutral"]:
            state = line_state(h["emitted"], x["emitted"], line, owner, common)
            if state["state"] == "BOTH_ABSENT":
                continue  # I3 -- outside the comparative risk set
            risk += 1
            if text_discordance(state):
                discordant += 1
    return {
        "risk_set_lines": risk,
        "text_discordant_lines": discordant,
        "m0a_rate": (discordant / risk) if risk else None,
    }


def write_s1_control(documents: list[dict], out_path: Path | None = None) -> dict:
    """A38.9/A39 -- the CANONICAL execution-time S1 artifact. Refuses before a VALID boundary.

    `documents` items: {"document", "pdf_path"}. `s1_result` is the mechanism; this is the
    committed input the future scorer reads, so it is guarded exactly as the oracle key is --
    same four-state authority, same VALID-only rule. A DEVELOPMENT invocation of `s1_result`
    is evidence about the mechanism and is deliberately NOT this artifact.

    The architecture decision is not taken here. `fires` and the gate status are recorded;
    A27.6 owns the consequence.
    """
    import build_oracle as BO

    out_path = Path(out_path) if out_path else (HERE.parents[1] / "results" / "s1_control.json")
    BO.assert_write_permitted(out_path)  # VALID-only; a stray marker unlocks nothing

    per_document = []
    for doc in documents:
        BO.assert_source_permitted(doc["document"], doc.get("pdf_path"))
        result = s1_result(Path(doc["pdf_path"]))
        per_document.append({"document": doc["document"], **result})

    artifact = {
        "schema": "s1_control/1",
        "population": BO.realized_population(
            [{"frame": {"document": d["document"]}, "pdf_path": d.get("pdf_path")} for d in documents]
        ),
        "execution_boundary_state": BO.execution_boundary_state(),
        "advance_scale": S1_ADVANCE_SCALE,
        "sabotaged_arm": "X",
        "per_document": per_document,
        "n_documents": len(per_document),
        "n_firing": sum(1 for d in per_document if d["fires"]),
        # S1 is a GATE INPUT, not a decision: every document must show a live comparator.
        "fires": bool(per_document) and all(d["fires"] for d in per_document),
        "gate": "S1",
        "decision_taken_here": False,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1, default=str))
    return artifact


def s1_result(pdf_path: Path, limit: int | None = None) -> dict:
    """A38.9 -- the committed S1 record for one document. Facts only; no gate applied here.

    `fires` is reported, not enforced: A27.6 owns the consequence (a non-firing S1 blocks the
    decision), and duplicating that judgement here would give it two homes.
    """
    import run_extended

    h_pages = run_hybrid.run(pdf_path, limit=limit)
    primary_x = run_extended.run(pdf_path, limit=limit)[0]
    sabotaged_x = _x_pages(pdf_path, limit, S1_ADVANCE_SCALE)

    primary = _m0_from_arms(h_pages, primary_x)
    sabotaged = _m0_from_arms(h_pages, sabotaged_x)
    fires = (
        primary["m0a_rate"] is not None
        and sabotaged["m0a_rate"] is not None
        and sabotaged["text_discordant_lines"] > primary["text_discordant_lines"]
    )
    return {
        "schema": "s1_control/1",
        "advance_scale": S1_ADVANCE_SCALE,
        "sabotaged_arm": "X",
        "m0_definition": "A22/A23 text discordance over the comparative risk set -- the same "
        "line_state/text_discordance functions build_frames uses",
        "primary": primary,
        "sabotaged": sabotaged,
        "fires": fires,
        "reason": None if fires else S1_DEAD_COMPARATOR,
    }
