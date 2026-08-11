"""Generate every table in RESULTS-HYBRID.md from the raw result JSON.

Same splice-between-markers discipline as fill_results.py and fill_confirmatory.py: no
number in the published document is transcribed by hand. A table that is not generated
here does not belong in the document.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/fill_hybrid.py
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
BAKEOFF = REPO / "docs/research/pdf-backend-bakeoff"
RESULTS = BAKEOFF / "results"
DOC = BAKEOFF / "RESULTS-HYBRID.md"

PATHS = ("glyph", "hybrid", "pdfminer")
TARGETS = ("FAMILY HOUSING", "NAVY AND", "ARMY NATIONAL", "AMERICAN BATTLE")


def load(name: str):
    p = RESULTS / name
    return json.loads(p.read_text()) if p.exists() else None


def splice(text: str, marker: str, block: str) -> str:
    start, end = f"<!-- {marker} -->", f"<!-- /{marker} -->"
    if start not in text:
        return text
    head, rest = text.split(start, 1)
    tail = rest.split(end, 1)[1] if end in rest else rest
    return f"{head}{start}\n\n{block}\n\n{end}{tail}"


def missing(what: str) -> str:
    return f"_(not generated: `{what}` is absent from `results/`. Run the probe, then re-run `fill_hybrid.py`.)_"


# ---------- the four named headings -------------------------------------------


def headings_table(data: dict) -> str:
    out = [
        "| document | heading | production | glyph | **hybrid** | pdfminer |",
        "|---|---|---|---|---|---|",
    ]
    for doc, per in data.items():
        for target in TARGETS:
            cells = []
            for path in ("production", "glyph", "hybrid", "pdfminer"):
                o = per.get(target, {}).get(path)
                if o is None:
                    cells.append("—")
                    continue
                cell = f"{o['correct']} ok"
                if o["corrupted"]:
                    cell = f"**{o['correct']} ok / {o['corrupted']} malformed**"
                cells.append(cell)
            out.append(f"| `{doc}` | {target} | " + " | ".join(cells) + " |")
    tot = {p: [0, 0] for p in ("production", "glyph", "hybrid", "pdfminer")}
    for per in data.values():
        for target in TARGETS:
            for path, o in per.get(target, {}).items():
                tot[path][0] += o["correct"]
                tot[path][1] += o["corrupted"]
    out.append(
        "| **all** | **all four** | "
        + " | ".join(
            f"{v[0]} ok / {v[1]} malformed" for v in (tot[p] for p in ("production", "glyph", "hybrid", "pdfminer"))
        )
        + " |"
    )
    return "\n".join(out)


# ---------- separability ------------------------------------------------------


def separability_table(data: dict) -> str:
    out = [
        "| document | word boundaries | intra-word | boundary gap/size min | intra-word max | separable | "
        "best threshold, errors | shipped 0.25, errors |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for path, s in data.items():
        if s is None:
            continue
        name = "**POOLED**" if path == "__pooled__" else f"`{Path(path).name}`"
        out.append(
            f"| {name} | {s['word_boundaries']} | {s['intra_word']} | {s['boundary_ratio_min']} | "
            f"{s['intra_ratio_max']} | **{'yes' if s['separable'] else 'NO'}** | "
            f"{s['best_threshold']}, {s['best_threshold_errors']} | "
            f"{s['shipped_0.25_missed_spaces']} missed + {s['shipped_0.25_spurious_spaces']} spurious |"
        )
    return "\n".join(out)


# ---------- corpus parity -----------------------------------------------------


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.mean(vals), 5) if vals else None


def corpus_table(data: dict) -> str:
    docs = [d for d in data["documents"] if "vs_production" in d]
    scored = [d for d in docs if not d.get("production_declined")]
    heading_docs = [d for d in scored if any(r["H2_labels_reference"] > 0 for r in d["vs_production"].values())]
    rows = []
    for path in PATHS:
        e = [d["vs_production"][path] for d in scored if path in d["vs_production"]]
        h = [d["vs_production"][path] for d in heading_docs if path in d["vs_production"]]
        rows.append(
            {
                "path": path,
                "n": len(e),
                "text_identical": sum(1 for r in e if r["H1_text_identical"]),
                "text_f1": _mean([r["H1_token_f1"] for r in e]),
                "n_head": len(h),
                "labels_exact": sum(1 for r in h if r["H2_labels_exact"]),
                "labels_absent": sum(r["H2_absent_from_reference"] for r in h),
                "labels_missed": sum(r["H2_missed_from_reference"] for r in h),
                "breadcrumb": _mean([r["H3_breadcrumb_accuracy"] for r in h]),
                "lines_identical": sum(1 for r in e if r["H4_line_numbers_identical"]),
                "lines_jaccard": _mean([r["H4_line_numbers_jaccard"] for r in e]),
                "assoc": _mean([r["H5_assoc_accuracy"] for r in h]),
            }
        )
    out = [
        f"Reference is **production** (`extract_clean_pages`) on the {len(scored)} corpus documents "
        f"production accepts. Heading metrics (H2/H3/H5) are over the {rows[0]['n_head']} of those "
        "that carry any heading; the rest cannot discriminate.",
        "",
        "| metric | " + " | ".join(f"**{p}**" if p == "hybrid" else p for p in PATHS) + " |",
        "|---|" + "---|" * len(PATHS),
    ]

    def row(label, key, fmt="{}"):
        return f"| {label} | " + " | ".join(fmt.format(r[key]) for r in rows) + " |"

    out += [
        "| H1 full text digest identical | " + " | ".join(f"{r['text_identical']}/{r['n']}" for r in rows) + " |",
        row("H1 mean token F1 vs production", "text_f1"),
        "| H2 heading-label set exact | " + " | ".join(f"{r['labels_exact']}/{r['n_head']}" for r in rows) + " |",
        row("H2 labels production does NOT produce", "labels_absent"),
        row("H2 production labels missed", "labels_missed"),
        row("H3 breadcrumb (parent) agreement", "breadcrumb"),
        "| H4 line-number set identical | " + " | ".join(f"{r['lines_identical']}/{r['n']}" for r in rows) + " |",
        row("H4 mean line-number Jaccard", "lines_jaccard"),
        row("H5 amount→heading agreement", "assoc"),
    ]
    return "\n".join(out)


def accuracy_table(data: dict) -> str:
    """The same paths against XML, so parity is not mistaken for correctness.

    Reported in TWO STRATA, and the split is not cosmetic. `RESULTS-CONFIRMATORY.md`
    recorded that every corpus document where the paths' heading recovery differs carries a
    `<quoted-block>`, which the DeltaTrack#11 parser defect drops from the XML reference.
    Excluding those documents therefore removes exactly the documents that can
    discriminate, and one pooled figure over the remainder reads as "all paths are
    equivalent" when what it says is "these documents cannot tell them apart."

    Each stratum carries a generated `can this stratum discriminate?` row, derived from
    whether any path differs from production on labels inside it. A stratum answering NO is
    published and is not evidence.
    """
    cols = ("production",) + PATHS
    accepted = [d for d in data["documents"] if "vs_xml" in d and not d.get("production_declined")]
    strata = (
        ("primary — no `<quoted-block>`", [d for d in accepted if not d.get("quoted_block")]),
        ("quoted-block stratum", [d for d in accepted if d.get("quoted_block")]),
    )
    out = [
        "Reference is **XML**. `production` is a fourth column rather than the reference, because "
        "against XML it is a candidate like any other.",
    ]
    for name, docs in strata:
        differs = sum(
            1
            for d in docs
            if any(
                r["H2_absent_from_reference"] or r["H2_missed_from_reference"]
                for r in (d.get("vs_production") or {}).values()
            )
        )
        verdict = (
            f"**YES** — {differs} of {len(docs)} documents separate the paths"
            if differs
            else f"**NO** — no path differs from production anywhere in these {len(docs)}"
        )
        out += [
            "",
            f"**{name}** — {len(docs)} documents. _Can this stratum discriminate?_ {verdict}",
            "",
            "| metric | " + " | ".join(f"**{p}**" if p == "hybrid" else p for p in cols) + " |",
            "|---|" + "---|" * len(cols),
        ]
        for label, metric, field in (
            ("B2 heading-label F1", "B2", "f1"),
            ("B5 amount→heading F1", "B5", "f1"),
            ("B6 parent/child accuracy", "B6", "accuracy"),
        ):
            cells = [
                str(_mean([d["vs_xml"][p][metric].get(field) for d in docs if p in d.get("vs_xml", {})])) for p in cols
            ]
            out.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def pairs_table(data: dict) -> str:
    pairs = [p for p in data["pairs"] if "vs_production" in p]
    out = [
        f"Reference is **production**'s canonical diff over {len(pairs)} consecutive version pairs. "
        "`amounts` is the `Counter[(old, new, kind)]` of `amount_entries` — the money, and the "
        "highest-consequence field. `changes` is the `Counter[(change_type, norm(old), norm(new))]` "
        "signature set, which embeds the line text and therefore cannot be byte-identical for any "
        "path that assembles lines geometrically; its **overlap** is the informative figure and the "
        "identity column is reported only so the distinction is visible.",
        "",
        "| path | amount signatures identical | amount recall | change signatures identical | change recall |",
        "|---|---|---|---|---|",
    ]
    ref_amt = sum(p.get("n_amount_entries_production", 0) for p in pairs)
    ref_chg = sum(p.get("n_changes_production", 0) for p in pairs)
    for path in PATHS:
        e = [p["vs_production"][path] for p in pairs if path in p["vs_production"]]
        if not e:
            continue
        a = sum(1 for r in e if r["H6_amounts_identical"])
        c = sum(1 for r in e if r["H6_changes_identical"])
        ao = sum(r["H6_amount_overlap"] for r in e)
        co = sum(r["H6_change_overlap"] for r in e)
        name = f"**{path}**" if path == "hybrid" else path
        out.append(
            f"| {name} | {a}/{len(e)} | {round(ao / ref_amt, 5) if ref_amt else '—'} ({ao}/{ref_amt}) | "
            f"{c}/{len(e)} | {round(co / ref_chg, 5) if ref_chg else '—'} ({co}/{ref_chg}) |"
        )
    return "\n".join(out)


def signals_table(data: dict) -> str:
    out = [
        "| document | generated chars | with a real box | with a size | with a font name | missing origin | "
        "glyph_size coverage | LineGeom coverage | margin/body font separation |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for path, e in data.items():
        s1, s2, s3 = e["S1"], e["S2"], e["S3"]
        rate = f"{s1['chars_generated']}/{s1['chars_total']} ({s1['generated_rate']:.1%})"
        sep = s3["separation_rate"]
        sep_cell = f"{sep} over {s3['numbered_lines_with_both']} lines" if sep is not None else "—"
        out.append(
            f"| `{Path(path).name}` | {rate} | **{s1['generated_with_real_box']}** | "
            f"**{s1['generated_with_size']}** | **{s1['generated_with_font_name']}** | "
            f"**{s1['generated_missing_origin']}** | {s2['size_coverage']} ({s2['numbered_lines']} lines) | "
            f"{s2['geom_coverage']} | {sep_cell} |"
        )
    return "\n".join(out)


def normalize_raw_scope_table(data: dict) -> str:
    """Where the dangling-hyphen gap lives, over a mixed stratum.

    The point of this table is the dichotomy, not the totals: the mid-line branch either
    barely fires (numbered layouts, where the two paths agree exactly) or fires in the
    thousands (unnumbered layouts, where they diverge). A pooled figure would average the
    two into a middling rate that describes neither.
    """
    out = [
        "The same probe over a **mixed** stratum, to locate the limitation rather than "
        "just measure it. `declined` is production's own unnumbered-layout guard.",
        "",
        "| document | production declines it | mid-line branch fired | trailing-hyphen tokens (prod / hybrid) | "
        "hyphenated tokens only in hybrid |",
        "|---|---|---|---|---|",
    ]
    for r in data["documents"]:
        b, d, dec = r["branch_fired"], r["diff"], r["production_declined"]
        agree = d["trailing_hyphen_production"] == d["trailing_hyphen_hybrid"] and not d["hyphenated_only_in_hybrid"]
        out.append(
            f"| `{r['doc']}` | {'**yes**' if dec else 'no'} | {b['midline_hyphen_lowercase']:,} | "
            f"{d['trailing_hyphen_production']} / {d['trailing_hyphen_hybrid']}"
            f"{' — **identical**' if agree else ''} | {d['hyphenated_only_in_hybrid']} |"
        )
    return "\n".join(out)


def geometry_agreement_table(data: dict) -> str:
    """Do the sidecar VALUES match production's, not merely exist?"""
    out = [
        "Agreement is over the numbered lines both paths recovered, to a 0.05 pt tolerance "
        "(these are floats derived through different call paths, so exact equality would "
        "report noise as disagreement).",
        "",
        "| document | shared numbered lines | `glyph_size` | `content_left` | `content_right` | `first_word_right` |",
        "|---|---|---|---|---|---|",
    ]
    for path, e in data.items():
        s = e.get("S4")
        if not s:
            continue
        out.append(
            f"| `{Path(path).name}` | {s['lines_shared']} | {s['glyph_size_agree']} | "
            f"{s['content_left_agree']} | {s['content_right_agree']} | **{s['first_word_right_agree']}** |"
        )
    return "\n".join(out)


def portability_table(data: dict) -> str:
    out = [
        "| document | raw stream identical | trailing-space divergences | line-break-vs-space | "
        "**unclassified** | **page text digest identical** | line numbers identical | heading labels identical |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for path, e in data.items():
        k = e["stream_diff_kinds"]
        out.append(
            f"| `{Path(path).name}` | {e['stream_identical']} | {k['line_trailing_space']} | "
            f"{k['line_break_vs_space']} | **{k['unclassified']}** | **{e['pages_text_identical']}** | "
            f"{e['pages_line_numbers_identical']} ({e['n_line_numbers']}) | "
            f"{e['pages_labels_identical']} ({e['n_labels']}) |"
        )
    return "\n".join(out)


def wasm_table(data: dict) -> str:
    present = data["entry_points_present"]
    out = [
        f"`@embedpdf/pdfium` **{data['wrapper_version']}**, called for real on a GPO bill page "
        f"({data['count_chars']} characters). Presence is asked of the wrapper object an adapter would "
        "call, and each function is then invoked on every character so an exported stub cannot pass.",
        "",
        "| entry point | exported | exercised |",
        "|---|---|---|",
    ]
    ex = data["exercised"]
    hits = {
        "FPDFText_GetCharBox": ex["charbox"],
        "FPDFText_GetMatrix": ex["matrix"],
        "FPDFText_GetCharOrigin": ex["origin"],
        "FPDFText_IsGenerated": ex["generated"],
        "FPDFText_IsHyphen": ex["hyphen"],
        "FPDFText_GetFontInfo": ex["fontinfo"],
        "FPDFText_HasUnicodeMapError": ex["maperror"],
    }
    for name, ok in present.items():
        n = hits.get(name)
        note = f"{n} non-trivial returns" if n is not None else "called"
        out.append(f"| `{name}` | {'yes' if ok else '**NO**'} | {note} |")
    out.append("")
    out.append(f"**All {len(present)} required entry points present: {data['all_present']}.**")
    return "\n".join(out)


def backend_spacing_table(data: dict) -> str:
    out = [
        f"Probe boundary: `{data['probe_text']}` on `{data['pdf']}` page {data['page']}. The neutral "
        f"glyph layer produces `{data['probe_text'].replace(' ', '')}` here.",
        "",
        "| backend | its own text keeps the space | produces the joined form | how a synthesised character is marked |",
        "|---|---|---|---|",
    ]
    for name, r in data["backends"].items():
        if "error" in r:
            out.append(f"| {name} | — | — | ERROR: {r['error'][:60]} |")
            continue
        out.append(
            f"| {name} | **{r['recovers_space']}** | **{r['produces_joined_form']}** | {r['generated_marker']} |"
        )
    out.append("| **the glyph seam** | **False** | **True** | n/a — the information is discarded before this point |")
    return "\n".join(out)


def adapter_table(data: dict) -> str:
    """Corpus-scale totals from the adapter's own counters.

    These are the claims the contract rests on, each stated as a count that can be
    non-zero: an index skew would mean the char index does not address both the character
    and its geometry; unnamed ink would mean the stream lost a glyph; a unicode map error
    would mean a character PDFium could not name at all.
    """
    keys = (
        ("pages", "pages"),
        ("chars", "characters"),
        ("generated_chars", "engine-generated characters"),
        ("hyphen_chars", "`FPDFText_IsHyphen` characters"),
        ("index_skew_pages", "**pages where CountChars != len(text)**"),
        ("unnamed_ink", "**ink the engine could not name**"),
        ("unicode_map_errors", "**unicode map errors**"),
        # Counted in the non-generated branch only. A generated character has no font name
        # by construction, and folding those in would make the row unreadable.
        ("empty_font_names", "**non-generated characters with an empty font name**"),
    )
    tot = dict.fromkeys((k for k, _ in keys), 0)
    n = 0
    for d in data["documents"]:
        s = (d.get("extract") or {}).get("hybrid")
        if not s:
            continue
        n += 1
        for k in tot:
            tot[k] += s.get(k, 0)
    out = [
        f"Counters from the hybrid adapter itself, aggregated over all {n} corpus documents.",
        "",
        "| | total |",
        "|---|---|",
    ]
    for k, label in keys:
        out.append(f"| {label} | {tot[k]:,} |")
    if tot["chars"]:
        out.append(f"| generated-character rate | {tot['generated_chars'] / tot['chars']:.2%} |")
    return "\n".join(out)


def normalize_raw_table(data: dict) -> str:
    """Whether `normalize_raw`'s branches repair damage the hybrid path still has.

    Each row is a document where the branches fire, with the token-level artifacts the
    branches exist to prevent. Non-zero `hyphen artifacts` on a document where the
    mid-line branch fires would falsify section 8's claim.
    """
    rows = data["documents"]
    out = [
        "Measured on the **production-declined** stratum — the unnumbered layouts, mostly "
        "enrolled bills, which section 5's parity table excludes and which are exactly where "
        "`normalize_raw`'s mid-line soft-hyphen branch exists to act (its docstring names them). "
        "A branch counts as having fired by matching its own pattern against PDFium's raw page "
        "text, so the zeros to its right are only meaningful because the number to its left is "
        "large.",
        "",
        "| document | mid-line branch fired | trailing-hyphen tokens (prod / hybrid) | "
        "soft-hyphen chars in text (prod / hybrid) | hyphenated tokens only in hybrid |",
        "|---|---|---|---|---|",
    ]
    tot = {k: 0 for k in ("fired", "th_p", "th_h", "sh_p", "sh_h", "only_h")}
    for r in rows:
        b, d = r["branch_fired"], r["diff"]
        tot["fired"] += b["midline_hyphen_lowercase"]
        tot["th_p"] += d["trailing_hyphen_production"]
        tot["th_h"] += d["trailing_hyphen_hybrid"]
        tot["sh_p"] += d["soft_hyphen_chars_production"]
        tot["sh_h"] += d["soft_hyphen_chars_hybrid"]
        tot["only_h"] += d["hyphenated_only_in_hybrid"]
        out.append(
            f"| `{r['doc']}` | {b['midline_hyphen_lowercase']:,} | "
            f"{d['trailing_hyphen_production']} / {d['trailing_hyphen_hybrid']} | "
            f"{d['soft_hyphen_chars_production']} / {d['soft_hyphen_chars_hybrid']} | "
            f"**{d['hyphenated_only_in_hybrid']}** |"
        )
    out.append(
        f"| **total** | **{tot['fired']:,}** | {tot['th_p']} / {tot['th_h']} | "
        f"{tot['sh_p']} / {tot['sh_h']} | **{tot['only_h']}** |"
    )
    samples = [s for r in rows for s in r["diff"]["samples_only_in_hybrid"]]
    if samples:
        out += ["", "Hyphenated tokens the hybrid produces and production does not:", ""]
        out += [f"- `{s}`" for s in samples[:20]]
    return "\n".join(out)


def main() -> None:
    text = DOC.read_text()
    jobs = [
        ("H_ADAPTER", "hybrid_docs.json", adapter_table),
        ("H_NORMALIZE_RAW", "probe_normalize_raw.json", normalize_raw_table),
        ("H_NORMALIZE_RAW_SCOPE", "probe_normalize_raw_all.json", normalize_raw_scope_table),
        ("H_BACKEND_SPACING", "probe_backend_spacing.json", backend_spacing_table),
        ("H_HEADINGS", "probe_failure_headings.json", headings_table),
        ("H_SEPARABILITY", "probe_separability.json", separability_table),
        ("H_CORPUS", "hybrid_docs.json", corpus_table),
        ("H_ACCURACY", "hybrid_docs.json", accuracy_table),
        ("H_PAIRS", "hybrid_pairs.json", pairs_table),
        ("H_SIGNALS", "probe_hybrid_signals.json", signals_table),
        ("H_GEOM_AGREE", "probe_hybrid_signals.json", geometry_agreement_table),
        ("H_PORTABILITY", "hybrid_portability.json", portability_table),
        ("H_WASM", "hybrid_wasm_entrypoints.json", wasm_table),
    ]
    for marker, source, fn in jobs:
        data = load(source)
        block = fn(data) if data else missing(source)
        text = splice(text, marker, block)
    DOC.write_text(text)
    print(f"wrote {DOC}")


if __name__ == "__main__":
    main()
