"""G6 — H1-H5 with the extended-glyph path added. MIGRATION PARITY, not correctness.

Reuses `probes/score_hybrid.py` unmodified and adds one path to it, so the four existing
columns are computed by exactly the code that produced `RESULTS-HYBRID.md` §5 and cannot
drift from it. The scorer is imported and its `PATHS` and `build_pages` are extended in
place rather than copied.

WHAT THIS TABLE IS. The reference is production's own output. It answers "would moving the
adapter change what a staffer sees today", which is a question about RISK. It is not
evidence about correctness, and phase 1 established that the accuracy half of §6 has no
valid oracle (the XML reference drops `<quoted-block>`, DeltaTrack#11). `score_hybrid`
computes its `vs_xml` block anyway because it is the same function; **those numbers are
not used here and must not be used to decide between the two designs.**

Correctness for this phase lives in `g04_score_boundaries.py`, against the independently
adjudicated sample, and in `g05_failure_headings.py`, against GPO's printing.

SCOPE. A document subset, named explicitly below rather than "the first N", chosen before
the run to include: the two documents where the glyph seam's heading defect is worst, the
negative control where it does not fire, a Senate bill, a House bill at a different stage,
and two documents production DECLINES (unnumbered layouts). The full 52-document run is
~90 minutes for four paths and was not repeated for five.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
PROBES = REPO / "docs/research/pdf-backend-bakeoff/probes"
for p in (str(HERE), str(PROBES), str(PROBES / "backends"), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pdfium_extended  # noqa: E402
import reconstruct_extended as RE  # noqa: E402
import score_hybrid as SH  # noqa: E402

# `corpus_documents()` yields (bill, version_number, pdf, xml) with version as an INT, so
# the key is "<bill>/<n>" and not the full version slug. The first run of this probe used
# slugs, matched nothing, scored zero documents and still printed "wrote ..." -- a silent
# vacuous pass. The assertion below exists so that cannot recur.
DOCS = (
    "114-hr-2029/4",  # reported in senate; glyph defect present
    "118-hr-4366/5",  # engrossed amendment house; glyph defect worst
    "116-hr-1865/6",  # enrolled; the negative control, and production declines it
    "118-s-4795/1",  # Senate bill, reported
    "118-hr-4366/1",  # same bill, different stage
    "118-hr-2882/5",  # carries the COUPS D'ETAT diacritic case
    "115-hr-5895/2",
    "113-hr-3547/6",  # enrolled; production declines it
)

_original_build = SH.build_pages


def build_pages(path: str, pdf: Path):
    if path == "extended":
        raw, summary = pdfium_extended.extract(pdf)
        pages, diag = RE.reconstruct(raw, repaired=True)
        return pages, {**summary, **diag}
    return _original_build(path, pdf)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=HERE / "results" / "g06_corpus_parity.json")
    ap.add_argument("--docs", nargs="*", default=list(DOCS))
    args = ap.parse_args()

    SH.PATHS = ("production", "glyph", "hybrid", "extended", "pdfminer")
    SH.build_pages = build_pages

    wanted = set(args.docs)
    original = SH.corpus_documents

    def filtered():
        sel = [d for d in original() if f"{d[0]}/{d[1]}" in wanted]
        found = {f"{d[0]}/{d[1]}" for d in sel}
        assert found == wanted, f"document filter matched {sorted(found)}, wanted {sorted(wanted)}"
        return sel

    SH.corpus_documents = filtered
    args.out.parent.mkdir(parents=True, exist_ok=True)
    SH.score_documents(args.out, None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
