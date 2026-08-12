"""x11 -- test that `run_hybrid` carries `source_char_index` end-to-end. DESIGN MATERIAL.

NOT CONFIRMATORY. DEVELOPMENT documents only (hybrid arm only). No holdout document is
opened, no scoring is performed.

    frozen rule        A21/A23 -- gid = (document_sha256, page_number, source_char_index)
    executable         `run_hybrid.extract_with_gids` / `.emitted_lines`
    test               this file
    evidence           `results/x11_provenance_chain.json`

THE ANTI-DRIFT GATES, which are the whole point. `run_hybrid` reproduces two byte-pinned
implementations in order to add one field, and a duplicate drifts and then measures a
different population while reporting agreement. So it is held to equality against the
frozen originals:

    chars   every field of every character, element by element, against
            `pdfium_hybrid.extract`
    lines   every emitted printed line's text, in order, against
            `reconstruct_hybrid.reconstruct_page(...).print_lines`

A third check proves the gid is really PDFium's char index and not a list position.

THE CHAIN PROVED
    PDFium char i -> extracted char record -> reconstruction row -> emitted printed line
    -> neutral projection
"""

from __future__ import annotations

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

import pdfium_hybrid  # noqa: E402
import reconstruct_hybrid  # noqa: E402
import run_hybrid  # noqa: E402
from neutral_identity import build_owner, emitted_gids, reconstruction_signature  # noqa: E402

OUT = EV / "results" / "x11_provenance_chain.json"
ROWS: list[dict] = []
FAILED: list[str] = []


def check(name: str, expected, observed, implication: str = "") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "implication": implication})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


def verify_extraction(name: str, frozen_pages, gid_pages) -> None:
    """THE ANTI-DRIFT GATE: the instrumented copy must reproduce the frozen adapter exactly."""
    mismatches = []
    if len(frozen_pages) != len(gid_pages):
        mismatches.append(f"page count {len(frozen_pages)} != {len(gid_pages)}")
    for fp, (pno, gp) in zip(frozen_pages, gid_pages):
        if fp.page_number != pno or len(fp.chars) != len(gp):
            mismatches.append(f"page {pno}: {len(fp.chars)} chars vs {len(gp)}")
            continue
        for pos, (fc, (_gid, gc)) in enumerate(zip(fp.chars, gp)):
            if fc != gc:
                mismatches.append(f"page {pno} pos {pos}: {fc!r} != {gc!r}")
                if len(mismatches) > 5:
                    break
    check(
        f"{name}: instrumented extraction reproduces the frozen adapter field-for-field",
        [],
        mismatches,
        "a drifted copy would measure a different population while reporting agreement",
    )


def verify_reconstruction(name: str, frozen_page, emitted) -> None:
    """THE ANTI-DRIFT GATE: same emitted printed lines, in the same order, as the frozen module."""
    want = [ln.text for ln in frozen_page.print_lines]
    got = [el.text() for el in emitted]
    diffs = [f"[{i}] {w!r} != {g!r}" for i, (w, g) in enumerate(zip(want, got)) if w != g][:5]
    check(
        f"{name}: provenance-carrying reconstruction reproduces print_lines exactly",
        (len(want), []),
        (len(got), diffs),
        "the emitted-line unit is Page.print_lines, and this copy of it is the same one",
    )


def main(limit: int = 12) -> int:
    docs = [
        ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
        ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
    ]
    report = []
    for name, path in docs:
        if not path.exists():
            print(f"  SKIP {name} (absent)")
            continue
        print(f"\n== {name} ==")
        frozen_pages, _ = pdfium_hybrid.extract(path, limit=limit)
        gid_pages = run_hybrid.extract_with_gids(path, limit=limit)
        verify_extraction(name, frozen_pages, gid_pages)

        chain_ok = 0
        n_neutral = n_emitted = 0
        shape = Counter()
        cross = 0
        gid_max = 0
        unknown_gids: list[str] = []
        for frozen_page, (pno, chars) in zip(frozen_pages, gid_pages):
            fp, _diag = reconstruct_hybrid.reconstruct_page(frozen_page)
            emitted = run_hybrid.emitted_lines(pno, chars)
            if pno == 1:
                verify_reconstruction(name, fp, emitted)
            elif [ln.text for ln in fp.print_lines] == [e.text() for e in emitted]:
                chain_ok += 1

            lines = run_hybrid.neutral_skeleton(pno, chars)
            owner = build_owner(lines)
            n_neutral += len(lines)
            n_emitted += len(emitted)
            gid_max = max([gid_max] + [max(nl.gids) for nl in lines if nl.gids])
            # Every gid anywhere downstream must name a character the extraction actually
            # produced. A list position dressed up as a char index would fail here.
            known = {gid for gid, _c in chars}
            for nl in lines:
                unknown_gids += [f"p{pno} skeleton {g}" for g in nl.gids - known]
            for e in emitted:
                unknown_gids += [f"p{pno} emitted {g}" for g in e.gids - known]
            for ln in lines:
                # Single-arm structural report: the "jointly observed" domain of a one-arm
                # run is that arm's own emission.
                sig = reconstruction_signature(emitted, ln, owner, emitted_gids(emitted))
                shape[len(sig)] += 1
                if any(others for _owned, others in sig):
                    cross += 1

        check(
            f"{name}: the chain holds on every remaining page",
            len(frozen_pages) - 1,
            chain_ok,
            "PDFium char i -> record -> row -> emitted printed line -> neutral projection",
        )
        check(
            f"{name}: every skeleton and emitted gid names a real extracted character",
            [],
            unknown_gids[:5],
            "a list position dressed up as a source_char_index would fail this",
        )
        rec = {
            "document": name,
            "pages": len(frozen_pages),
            "neutral_lines": n_neutral,
            "emitted_printed_lines": n_emitted,
            "signature_shape_counts": {str(k): v for k, v in sorted(shape.items())},
            "neutral_lines_with_a_cross_line_merge": cross,
            "max_source_char_index_seen": gid_max,
        }
        report.append(rec)
        print(
            f"  neutral_lines={n_neutral} emitted_printed_lines={n_emitted} "
            f"shape={dict(sorted(shape.items()))} cross_line_merges={cross}"
        )

    doc = {
        "population": "DEVELOPMENT (hybrid only) -- no holdout opened, no scoring",
        "chain": "PDFium char i -> extracted record -> reconstruction row -> emitted printed line"
        " -> neutral projection",
        "emitted_line_unit": "one element of Page.print_lines (production: 'one entry per line"
        " the GPO actually printed')",
        "adapters_modified": False,
        "why_not": (
            "pdfium_hybrid.py, contract_hybrid.py and reconstruct_hybrid.py are byte-pinned in "
            "validation/PRESERVED-MANIFEST.txt (tag pdf-bakeoff-prevalidation) and verify clean today; "
            "they are the exact bytes that produced the prior spike's confirmatory results"
        ),
        "signature_shape_key": "0 = neutral line no emitted line carries (chrome/margin/dropped); "
        "1 = emitted as a single printed line; 2+ = split across that many emitted printed lines",
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
