"""Fill RESULTS.md's table placeholders from the raw result JSON.

Generated rather than transcribed, so the published tables cannot drift from the runs
that produced them. Idempotent: it replaces the block between each marker and its
closing marker, so it can be re-run after a re-scored phase.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/fill_results.py
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOC = HERE.parent / "RESULTS.md"
RESULTS = HERE.parent / "results"
INCUMBENT = "pdfium-native"
LABEL = {
    "pdfium-native": "pdfium-native *(incumbent)*",
    "pdfium-wasm": "**pdfium-wasm**",
    "pdfminer": "**pdfminer**",
    "pymupdf": "pymupdf *(ceiling)*",
    "pdfjs": "pdfjs",
    "pypdf": "pypdf",
}


def mean(xs):
    return statistics.mean(xs) if xs else float("nan")


def t4_table(data: dict) -> str:
    pairs = data["pairs"]
    backends = data["backends"]
    mode = "repaired"

    def cell(p, b, *keys):
        e = pairs[p].get(f"{b}/{mode}")
        if not e or "error" in e:
            return None
        for k in keys:
            e = e.get(k) if isinstance(e, dict) else None
            if e is None:
                return None
        return e

    scored = [p for p in pairs if cell(p, INCUMBENT, "T2_amount_entries", "f1") is not None]
    declined = [p for p in pairs if p not in scored]

    rows = [
        f"Scored on **{len(scored)} of {data['n_pairs']}** pairs. "
        f"{len(declined)} declined by the production unnumbered-layout guard"
        + (f" ({', '.join(declined)})" if declined else "")
        + ".",
        "",
        "| Backend | amounts identical | changes identical | amount F1 | change F1 |",
        "|---|---|---|---|---|",
    ]
    for b in backends:
        if b == INCUMBENT:
            rows.append(f"| {LABEL[b]} | (reference) | (reference) | — | — |")
            continue
        ai = [x for x in (cell(p, b, "T4_vs_incumbent", "identical_amounts") for p in scored) if x is not None]
        ci = [x for x in (cell(p, b, "T4_vs_incumbent", "identical_changes") for p in scored) if x is not None]
        af = [x for x in (cell(p, b, "T4_vs_incumbent", "amount_entries", "f1") for p in scored) if x is not None]
        cf = [x for x in (cell(p, b, "T4_vs_incumbent", "change_signatures", "f1") for p in scored) if x is not None]
        mark = "**" if ai and sum(ai) == len(ai) else ""
        rows.append(
            f"| {LABEL[b]} | {mark}{sum(ai)}/{len(ai)}{mark} | {sum(ci)}/{len(ci)} | {mean(af):.4f} | {mean(cf):.4f} |"
        )
    return "\n".join(rows)


def t2_table(data: dict) -> str:
    import sys

    sys.path.insert(0, str(HERE))
    from report_phase2 import quoted_block_pairs

    qb = quoted_block_pairs()
    pairs = data["pairs"]
    backends = data["backends"]
    mode = "repaired"

    def cell(p, b, *keys):
        e = pairs[p].get(f"{b}/{mode}")
        if not e or "error" in e:
            return None
        for k in keys:
            e = e.get(k) if isinstance(e, dict) else None
            if e is None:
                return None
        return e

    def stratum(p):
        n_ref = cell(p, INCUMBENT, "T2_amount_entries", "n_reference")
        n_cand = cell(p, INCUMBENT, "T2_amount_entries", "n_candidate")
        if n_ref is None:
            return None
        if not n_ref and not n_cand:
            return "empty_both"
        if not n_ref:
            return "xml_found_none"
        return "substantive_qb" if p in qb else "substantive_clean"

    notes = {
        "substantive_clean": "real amounts, XML reference **sound** — the informative population",
        "substantive_qb": "real amounts, XML reference carries `<quoted-block>` (known parser drop)",
        "xml_found_none": "XML found no amounts; F1 is an empty-denominator artifact",
        "empty_both": "neither side found amounts; F1 trivially 1.0, no information",
    }
    out = []
    for label in ("substantive_clean", "substantive_qb", "xml_found_none", "empty_both"):
        ps = [p for p in pairs if stratum(p) == label]
        if not ps:
            continue
        out.append(f"**`{label}`** (n={len(ps)}) — {notes[label]}")
        out.append("")
        out.append("| Backend | mean F1 | min F1 | perfect |")
        out.append("|---|---|---|---|")
        for b in backends:
            f1 = [x for x in (cell(p, b, "T2_amount_entries", "f1") for p in ps) if x is not None]
            if not f1:
                continue
            out.append(f"| {LABEL[b]} | {mean(f1):.4f} | {min(f1):.4f} | {sum(1 for x in f1 if x == 1.0)}/{len(f1)} |")
        out.append("")
    return "\n".join(out).rstrip()


def tierb_block(data: dict) -> str:
    docs = data["documents"]
    backends = [b for b in next(iter(docs.values())) if b != INCUMBENT]
    out = [
        f"Measured on **{len(docs)}** non-corpus documents with no XML reference: the "
        "watermarked committee report `CRPT-118srpt198`, the watermarked Senate bill "
        "`BILLS-118s4795rs`, and nine House-reported subcommittee prints. The spec asks "
        "for the first two by name; the nine are additional **Tier A** print-class "
        "variety, as the spec itself classifies them.",
        "",
        "| Backend | opened | text identical to incumbent | line numbers identical | mean breadcrumb agreement |",
        "|---|---|---|---|---|",
    ]
    n = len(docs)
    for b in backends:
        ok = [v[b] for v in docs.values() if b in v and "error" not in v[b]]
        ti = sum(1 for r in ok if r["vs_incumbent"] and r["vs_incumbent"]["text_identical"])
        li = sum(1 for r in ok if r["vs_incumbent"] and r["vs_incumbent"]["line_numbers_identical"])
        bc = [
            r["vs_incumbent"]["breadcrumb_agreement"]
            for r in ok
            if r["vs_incumbent"] and r["vs_incumbent"]["breadcrumb_agreement"] is not None
        ]
        out.append(f"| {LABEL.get(b, b)} | {len(ok)}/{n} | {ti}/{len(ok)} | {li}/{len(ok)} | {mean(bc):.4f} |")
    return "\n".join(out)


def splice(text: str, marker: str, block: str) -> str:
    start = f"<!-- {marker} -->"
    end = f"<!-- /{marker} -->"
    if start not in text:
        return text
    head, rest = text.split(start, 1)
    tail = rest.split(end, 1)[1] if end in rest else rest
    return f"{head}{start}\n\n{block}\n\n{end}{tail}"


def main() -> None:
    doc = DOC.read_text()
    p2 = RESULTS / "phase2.json"
    if p2.exists():
        data = json.loads(p2.read_text())
        doc = splice(doc, "T4_TABLE", t4_table(data))
        doc = splice(doc, "T2_TABLE", t2_table(data))
    tb = RESULTS / "tierb.json"
    if tb.exists():
        doc = splice(doc, "TIERB", tierb_block(json.loads(tb.read_text())))
    DOC.write_text(doc)
    print(f"filled {DOC}")


if __name__ == "__main__":
    main()
