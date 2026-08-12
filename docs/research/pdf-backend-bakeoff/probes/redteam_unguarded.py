"""Red-team: score the two pairs the production guard declines, WITHOUT the guard.

The published Phase 2 table is 13 of 15 pairs. Excluding pairs after seeing results is
exactly the kind of move that can manufacture a parity result, so the excluded pairs are
scored here explicitly and reported alongside, rather than only argued about.

If PDFium-WASM's parity with the incumbent holds on the declined pairs too, the exclusion
cannot be what produced it.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from contract import ALL_BACKENDS, run_backend  # noqa: E402
from reconstruct import reconstruct  # noqa: E402
from score_phase2 import amount_triples, change_signatures, prf, xml_canonical  # noqa: E402

from deltatrack.diff_pdf import diff_pdfs  # noqa: E402
from deltatrack.formatters.canonical import pdf_diff_to_canonical  # noqa: E402
from deltatrack.parsers.pdf_text import pdf_full_text  # noqa: E402

DECLINED = [
    ("115-hr-5895", "4_engrossed-amendment-senate", "5_enrolled-bill"),
    ("118-hr-4366", "5_engrossed-amendment-house", "6_enrolled-bill"),
]


def main() -> None:
    out: dict = {"note": "guard DISABLED; these are the pairs production declines", "pairs": {}}
    for bill, a, b in DECLINED:
        key = f"{bill}/{a}->{b}"
        out["pairs"][key] = {}
        xml_canon = xml_canonical(REPO / f"tests/corpus/{bill}/{a}.xml", REPO / f"tests/corpus/{bill}/{b}.xml")
        inc = None
        for backend in [b_ for b_ in ALL_BACKENDS]:
            try:
                pages = {}
                for side, stem in (("v1", a), ("v2", b)):
                    raw, _ = run_backend(backend, REPO / f"tests/corpus/{bill}/{stem}.pdf")
                    pages[side], _ = reconstruct(raw, repaired=True)
                diff = diff_pdfs(pages["v1"], pages["v2"])  # NO GUARD, deliberately
                t1, o1 = pdf_full_text(pages["v1"])
                t2, o2 = pdf_full_text(pages["v2"])
                congress, chamber, number = bill.split("-")
                canon = pdf_diff_to_canonical(
                    diff,
                    bill_type=chamber,
                    bill_number=number,
                    congress=congress,
                    full_text={"v1": t1, "v2": t2},
                    line_offsets={"v1": o1, "v2": o2},
                )
                if backend == "pdfium-native":
                    inc = canon
                entry = {
                    "vs_xml_amounts": prf(amount_triples(xml_canon), amount_triples(canon)),
                    "n_changes": len(canon.get("changes") or []),
                }
                if inc is not None and backend != "pdfium-native":
                    entry["identical_amounts"] = amount_triples(inc) == amount_triples(canon)
                    entry["identical_changes"] = change_signatures(inc) == change_signatures(canon)
                    entry["vs_incumbent_amounts"] = prf(amount_triples(inc), amount_triples(canon))
                out["pairs"][key][backend] = entry
                print(f"  {key:<40} {backend:<15} {json.dumps(entry)[:150]}", flush=True)
            except Exception as exc:
                out["pairs"][key][backend] = {"error": f"{type(exc).__name__}: {exc}"}
                print(f"  {key:<40} {backend:<15} ERROR {exc}", flush=True)
                traceback.print_exc()
    dest = REPO / "docs/research/pdf-backend-bakeoff/results/redteam_unguarded.json"
    dest.write_text(json.dumps(out, indent=1, default=str))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
