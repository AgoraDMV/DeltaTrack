"""Oracle + typography + tracking for the second holdout. Same modules as before."""
from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "probes"))
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "nearfull"))
import heading_runs as HR  # noqa: E402
import line_typography as LT  # noqa: E402
import tracking as TR  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402
from deltatrack.parsers import pdf_text as PT  # noqa: E402

HOLDOUT = ROOT / "bills" / "_holdout524b"
OUT = Path(__file__).resolve().parents[1] / "results"


def docs():
    for d in sorted(HOLDOUT.iterdir()):
        if not d.is_dir():
            continue
        for pdf in sorted(d.glob("*.pdf")):
            if pdf.with_suffix(".xml").exists():
                yield d.name, pdf, pdf.with_suffix(".xml")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    runs, skipped = [], []
    for bill, pdf, xml in docs():
        try:
            seqs, cw = HR.runs_for(pdf)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"bill": bill, "version": pdf.stem, "reason": f"error:{type(exc).__name__}"}); continue
        if seqs is None:
            skipped.append({"bill": bill, "version": pdf.stem, "reason": "no_size_bands"}); continue
        av, cv = HR.xml_vocabs(xml)
        res = 0
        for seq in seqs:
            texts = [ln.text.strip() for _p, ln in seq]
            seg, status = HR.correct_segmentation(texts, av, cv)
            res += status == "resolved"
            runs.append({"bill": bill, "version": pdf.stem,
                         "column_width": round(cw, 3) if cw else None,
                         "pages": [p for p, _l in seq], "lines": [ln.line_number for _p, ln in seq],
                         "texts": texts, "sizes": [ln.glyph_size for _p, ln in seq],
                         "geoms": [HR._geom(ln) for _p, ln in seq], "truth": seg, "status": status})
        print(f"  oracle {bill}/{pdf.stem}: runs={len(seqs)} resolved={res}")
    (OUT / "holdout2-runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in runs))
    (OUT / "holdout2-skipped.json").write_text(json.dumps(skipped, indent=2))

    typo, track, checked, bad = [], [], 0, 0
    for bill, pdf, _x in docs():
        doc = pdfium.PdfDocument(str(pdf))
        try:
            for pi in range(len(doc)):
                page = doc[pi]; tp = page.get_textpage()
                try:
                    raw = tp.get_text_range()
                    mt = LT.page_profiles(tp, raw)
                    tk = TR.page_tracking(tp, raw)
                    prod = PT._page_glyph_sizes(tp, raw)
                finally:
                    tp.close(); page.close()
                checked += 1
                if set(mt) != set(prod) or set(tk) != set(prod):
                    bad += 1
                for ln, v in mt.items():
                    typo.append({"bill": bill, "version": pdf.stem, "page": pi + 1, "line": ln, "hist": v["hist"]})
                for ln, v in tk.items():
                    track.append({"bill": bill, "version": pdf.stem, "page": pi + 1, "line": ln,
                                  "tracking_mean": v["tracking_mean"], "n_gaps": v["n_gaps"]})
        finally:
            doc.close()
        print(f"  glyphs {bill}/{pdf.stem}: typo={len(typo)} track={len(track)}")
    print(f"\nCONTRACT CHECK: pages={checked} mismatched={bad}")
    if bad:
        raise SystemExit("glyph walks diverged from production; measurements void")
    (OUT / "holdout2-typography.jsonl").write_text("".join(json.dumps(r) + "\n" for r in typo))
    (OUT / "holdout2-tracking.jsonl").write_text("".join(json.dumps(r) + "\n" for r in track))

    multi = [r for r in runs if len(r["texts"]) > 1]
    print(f"\nruns={len(runs)} multi-line={len(multi)} "
          f"boundaries={sum(len(r['texts']) - 1 for r in multi)}")
    print("status:", Counter(r["status"] for r in multi).most_common())
    print(f"documents excluded: {len(skipped)}")
    for s in skipped:
        print(f"   {s['bill']}/{s['version']}: {s['reason']}")


if __name__ == "__main__":
    main()
