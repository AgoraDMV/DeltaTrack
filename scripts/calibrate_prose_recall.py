#!/usr/bin/env python
"""Measure XML-prose-to-PDF recall across the corpus, to calibrate the floors in
tests/test_pdf_xml_prose_recall.py.

Those floors are budgets, and a budget calibrated on a sample is a budget that goes red
on the first unmeasured member. Run this over the whole fixture tree (and
`CORPUS_SWEEP=1` for the wider downloaded corpus) before changing one, and read the
misses: the point of the exercise is to know what the residue IS, not to pick a number
under it.

Results are grouped by print layout, because that is what the floors key on. A layout
whose worst member sits close to its floor is the one to look at, and a NEW layout
appearing in the corpus with a poor score is a defect to investigate rather than a floor
to add.

    uv run python scripts/calibrate_prose_recall.py [--misses N]

Exits non-zero when something needs attention, so it can be used as a check rather than
only read.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests"))

from pdf_corpus import dual_format_versions  # noqa: E402
from test_pdf_xml_prose_recall import (  # noqa: E402
    _LAYOUT_FLOORS,
    MIN_FRAGMENTS,
    RECALL_FLOOR,
    layout_floor,
    prose_recall,
    version_layout,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--misses", type=int, default=3, help="misses to print per version")
    args = parser.parse_args()

    versions = dual_format_versions()
    print(f"{len(versions)} dual-format versions\n")

    by_layout: dict[str, list[tuple[float, str]]] = defaultdict(list)
    breaches: list[str] = []
    total_fragments = 0

    for bill, xml_path, pdf_path in versions:
        fragments, missing = prose_recall(xml_path, pdf_path)
        label = f"{bill}/{xml_path.stem}"
        layout = version_layout(xml_path)
        floor = layout_floor(xml_path)
        total_fragments += len(fragments)

        # Mirror the test's own branching exactly. A script that reports a version the
        # gate would fail as fine is worse than no script: it is consulted precisely
        # when someone is deciding whether a red run is real.
        if not fragments:
            breaches.append(label)
            print(f"{label} [{layout}]: NO FRAGMENTS -- extraction found nothing to compare")
            continue

        if len(fragments) < MIN_FRAGMENTS:
            if floor == RECALL_FLOOR:
                # Healthy layout: the gate demands every fragment, so report that, not a
                # ratio it does not apply.
                status = "SHORT OK" if not missing else "SHORT INCOMPLETE"
                if missing:
                    breaches.append(label)
            else:
                # Degraded layout: the gate still holds these to the layout floor, so
                # score them against it rather than waving them through for being short.
                recall = (len(fragments) - len(missing)) / len(fragments)
                if recall < floor:
                    status = f"SHORT BELOW ITS {floor:.0%} FLOOR ({recall:.1%})"
                    breaches.append(label)
                else:
                    status = f"SHORT OK ({recall:.1%}, degraded layout floor {floor:.0%})"
            print(f"{label} [{layout}]: {status} ({len(fragments)} fragments, {len(missing)} missing)")
            for miss in missing[: args.misses]:
                print(f"    MISS: {miss[:200]}")
            continue

        recall = (len(fragments) - len(missing)) / len(fragments)
        by_layout[layout].append((recall, label))
        if recall < floor:
            flag = f"  <-- BELOW ITS {floor:.0%} FLOOR"
            breaches.append(label)
        elif floor < RECALL_FLOOR:
            flag = f"  (degraded layout, floor {floor:.0%})"
        else:
            flag = ""
        print(f"{label} [{layout}]: {recall:.1%} ({len(missing)}/{len(fragments)} missing){flag}")
        for miss in missing[: args.misses]:
            print(f"    MISS: {miss[:200]}")

    print(f"\n{'layout':<32} {'n':>3}  {'worst':>7}  {'floor':>6}  headroom")
    for layout in sorted(by_layout):
        scores = by_layout[layout]
        worst = min(s for s, _ in scores)
        floor = _LAYOUT_FLOORS.get(layout, RECALL_FLOOR)
        print(f"{layout:<32} {len(scores):>3}  {worst:>7.1%}  {floor:>6.0%}  {worst - floor:+.1%}")

    # A degraded layout whose worst member has climbed past the healthy floor no longer
    # needs its entry; the test asserts this too, so surface it here rather than letting
    # the reader discover it as a failure.
    for layout, floor in _LAYOUT_FLOORS.items():
        scores = by_layout.get(layout)
        if scores and min(s for s, _ in scores) >= RECALL_FLOOR:
            print(f"\n{layout}: every version now clears {RECALL_FLOOR:.0%}; remove its floor entry.")
            breaches.append(f"{layout} (floor no longer needed)")

    print(f"\ntotal prose fragments across the corpus: {total_fragments}")
    print(f"needs attention: {', '.join(breaches) if breaches else 'nothing'}")
    return 1 if breaches else 0


if __name__ == "__main__":
    raise SystemExit(main())
