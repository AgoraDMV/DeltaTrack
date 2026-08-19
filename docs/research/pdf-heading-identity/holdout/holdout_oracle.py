"""Build the independent XML oracle, and the typography sidecar, over the HOLDOUT.

Reuses the development study's own modules unchanged -- `heading_runs` for the
XML-derived segmentation oracle and `line_typography` for the within-line glyph
profile -- pointed at the ephemeral holdout tree instead of `tests/corpus`.

**The oracle does not consult the candidate.** `heading_runs.correct_segmentation`
searches every contiguous segmentation of a run and keeps it only if each segment's
joined text is an XML heading (last segment account-level, earlier ones
container-level). It never calls the joiner, never reads caps-per-word, never reads
the bootstrapped vocabulary, and never uses PR #639's `_heading_run()`. What the
shipped parser decides is used only to enumerate WHICH runs exist -- the population --
never to decide what is true about them.

Writes `results/holdout-runs.jsonl` and `results/holdout-typography.jsonl`.

    uv run python docs/research/pdf-heading-identity/holdout/holdout_oracle.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "probes"))

import heading_runs as HR  # noqa: E402
import line_typography as LT  # noqa: E402

HOLDOUT = ROOT / "bills" / "_holdout524"
OUT = Path(__file__).resolve().parents[1] / "results"


def documents():
    for bill_dir in sorted(HOLDOUT.iterdir()):
        if not bill_dir.is_dir():
            continue
        for pdf in sorted(bill_dir.glob("*.pdf")):
            xml = pdf.with_suffix(".xml")
            if xml.exists():
                yield bill_dir.name, pdf, xml


def build_runs():
    rows = []
    skipped = []
    for bill, pdf, xml in documents():
        try:
            sequences, column_width = HR.runs_for(pdf)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"bill": bill, "version": pdf.stem, "reason": f"extract_error:{type(exc).__name__}"})
            print(f"  {bill}/{pdf.stem}: ERROR {type(exc).__name__}: {exc}")
            continue
        if sequences is None:
            skipped.append({"bill": bill, "version": pdf.stem, "reason": "no_size_bands"})
            print(f"  {bill}/{pdf.stem}: no size bands (#508/#261 territory) -- excluded")
            continue
        account_vocab, container_vocab = HR.xml_vocabs(xml)
        resolved = 0
        for seq in sequences:
            texts = [line.text.strip() for _p, line in seq]
            segmentation, status = HR.correct_segmentation(texts, account_vocab, container_vocab)
            resolved += status == "resolved"
            rows.append(
                {
                    "bill": bill,
                    "version": pdf.stem,
                    "column_width": round(column_width, 3) if column_width else None,
                    "pages": [p for p, _l in seq],
                    "lines": [line.line_number for _p, line in seq],
                    "texts": texts,
                    "sizes": [line.glyph_size for _p, line in seq],
                    "geoms": [HR._geom(line) for _p, line in seq],
                    "truth": segmentation,
                    "status": status,
                }
            )
        print(
            f"  {bill}/{pdf.stem}: runs={len(sequences)} resolved={resolved} "
            f"acct_vocab={len(account_vocab)} cont_vocab={len(container_vocab)}"
        )
    return rows, skipped


def build_typography():
    import pypdfium2 as pdfium

    from deltatrack.parsers import pdf_text as PT

    rows = []
    checked = bad = 0
    for bill, pdf, _xml in documents():
        doc = pdfium.PdfDocument(str(pdf))
        try:
            for pi in range(len(doc)):
                page = doc[pi]
                tp = page.get_textpage()
                try:
                    raw_text = tp.get_text_range()
                    mine = LT.page_profiles(tp, raw_text)
                    prod = PT._page_glyph_sizes(tp, raw_text)
                finally:
                    tp.close()
                    page.close()
                checked += 1
                if set(mine) != set(prod):
                    bad += 1
                else:
                    for ln, v in mine.items():
                        ps, pg = prod[ln]
                        if v["prod_size"] != ps or v["prod_geom"] != pg:
                            bad += 1
                            break
                for ln, v in mine.items():
                    rows.append(
                        {"bill": bill, "version": pdf.stem, "page": pi + 1, "line": ln, "hist": v["hist"]}
                    )
        finally:
            doc.close()
        print(f"  {bill}/{pdf.stem}: typography rows={len(rows)}")
    print(f"\nCONTRACT CHECK: pages={checked} mismatched={bad}")
    if bad:
        raise SystemExit("typography duplicate diverged from production; measurements void")
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("=== oracle ===")
    rows, skipped = build_runs()
    (OUT / "holdout-runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (OUT / "holdout-skipped.json").write_text(json.dumps(skipped, indent=2))

    print("\n=== typography ===")
    typo = build_typography()
    (OUT / "holdout-typography.jsonl").write_text("".join(json.dumps(r) + "\n" for r in typo))

    multi = [r for r in rows if len(r["texts"]) > 1]
    boundaries = sum(len(r["texts"]) - 1 for r in multi)
    print(f"\nruns={len(rows)} multi-line={len(multi)} boundaries={boundaries}")
    print("run status:", Counter(r["status"] for r in rows).most_common())
    print("multi-line status:", Counter(r["status"] for r in multi).most_common())
    print(f"documents excluded before scoring: {len(skipped)}")
    for s in skipped:
        print(f"   {s['bill']}/{s['version']}: {s['reason']}")

    unresolved = [r for r in multi if r["status"] != "resolved"]
    print(f"\nunresolved multi-line runs: {len(unresolved)}")
    print("  by reason:", Counter(r["status"] for r in unresolved).most_common())
    print("  by run length:", Counter(len(r["texts"]) for r in unresolved).most_common())
    by_doc = Counter(f"{r['bill']}/{r['version']}" for r in unresolved)
    tot = Counter(f"{r['bill']}/{r['version']}" for r in multi)
    print("  concentration (unresolved / multi-line, per document):")
    for doc, n in by_doc.most_common():
        print(f"     {doc:<34} {n:>4} / {tot[doc]:<4} = {n / tot[doc]:.2f}")


if __name__ == "__main__":
    main()
