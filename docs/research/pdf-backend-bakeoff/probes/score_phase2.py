"""Phase 2: the terminal metric -- PDF-derived diff vs XML-derived diff (N=15 pairs).

This is the product. A backend that wins Phase 1 and loses here loses, because the diff
is what a staffer reads.

Both pipelines converge on the canonical JSON contract (ADR 0006), so this is a
structured comparison rather than a text one. Three families of measurement, reported
separately and never merged into one number:

  T1  change-set agreement, PDF vs XML
  T2  amount_entries agreement, PDF vs XML          <- the highest-consequence field
  T4  backend vs incumbent, PDF side only

T4 is an ADDITION to the spec, and it is the sharpest instrument here. T1/T2 compare two
different artifacts of one bill version, so their disagreement mixes three causes the
metric cannot separate (Trap 2). T4 holds the entire downstream pipeline fixed and varies
only the glyph source, so ANY difference is attributable to the backend with no
adjudication required. It answers the question a delivery decision actually turns on:
would swapping the PDF backend change what a staffer sees?

Comparisons are STRUCTURE-FREE by design. PDF-vs-XML output parity is settled-impossible
(the two segment provisions differently -- blocks vs elements), so a differing `modified`
count is not a defect and is reported as context, never as an error. What is comparable
is content: the multiset of money transitions, and the bag of changed text.

Run:
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_phase2.py \
      --out docs/research/pdf-backend-bakeoff/results/phase2.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from contract import ALL_BACKENDS, run_backend  # noqa: E402
from reconstruct import reconstruct  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.compare.pdf import UnsupportedLayoutError, _is_unnumbered_layout  # noqa: E402
from deltatrack.diff_bill import bill_diff_to_dict, diff_bills  # noqa: E402
from deltatrack.diff_pdf import diff_pdfs  # noqa: E402
from deltatrack.formatters.canonical import (  # noqa: E402
    pdf_diff_to_canonical,
    xml_diff_to_canonical,
)
from deltatrack.formatters.text_serializer import build_xml_full_text  # noqa: E402
from deltatrack.parsers.pdf_text import normalize_glyphs, pdf_full_text  # noqa: E402

_WORD = re.compile(r"\S+")
_AMOUNT_TOKEN = re.compile(r"\$[\d,]+(?:\.\d+)?")
# Materiality floor from PRE-REGISTRATION.md clause (c).
_MATERIAL_MIN_CHARS = 20
_SECTION_ID = re.compile(r"\b(?:SEC|SECTION|TITLE|DIVISION)\b\.?\s*[\dIVXLC]+", re.IGNORECASE)


def norm_text(text: str | None) -> str:
    """Typographic normalization, exactly the set PRE-REGISTRATION.md declares non-material.

    Deliberately narrow. Widening it later would inflate agreement, so every rule here
    corresponds to a named non-material class: whitespace runs, the glyph mappings
    `normalize_glyphs` performs, soft hyphens, GPO margin line numbers, and the
    letter-spacing GPO applies inside small-caps headings.
    """
    if not text:
        return ""
    text = normalize_glyphs(text)
    text = text.replace("­", "").replace("�", "")
    text = re.sub(r"^\s*\d{1,2}\s", " ", text, flags=re.MULTILINE)
    return " ".join(_WORD.findall(text))


def prf(reference: Counter, candidate: Counter) -> dict:
    matched = sum((reference & candidate).values())
    n_ref = sum(reference.values())
    n_cand = sum(candidate.values())
    precision = matched / n_cand if n_cand else (1.0 if not n_ref else 0.0)
    recall = matched / n_ref if n_ref else (1.0 if not n_cand else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 5),
        "recall": round(recall, 5),
        "f1": round(f1, 5),
        "matched": matched,
        "n_reference": n_ref,
        "n_candidate": n_cand,
    }


# ---------- structure-free views of a canonical diff --------------------------


def amount_triples(canonical: dict) -> Counter:
    """Multiset of (old, new, kind) money transitions across the whole diff.

    The strongest available oracle for this comparison: money is the highest-consequence
    field, and a transition carries no structural coordinates, so it survives the fact
    that the two pipelines segment provisions differently.
    """
    out: Counter = Counter()
    for change in canonical.get("changes") or []:
        for entry in change.get("amount_entries") or []:
            out[(entry.get("old"), entry.get("new"), entry.get("kind"))] += 1
    return out


def changed_text_tokens(canonical: dict) -> tuple[Counter, Counter]:
    """Bag of tokens appearing on each side of every change.

    Structure-free counterpart to change matching: it asks "did the two pipelines flag
    the same words as having changed", without requiring them to package those words into
    the same number of changes.
    """
    old: Counter = Counter()
    new: Counter = Counter()
    for change in canonical.get("changes") or []:
        text = change.get("text") or {}
        old.update(_WORD.findall(norm_text(text.get("old"))))
        new.update(_WORD.findall(norm_text(text.get("new"))))
    return old, new


def change_signatures(canonical: dict) -> Counter:
    """Multiset of (change_type, normalized old, normalized new) per the pre-registration."""
    return Counter(
        (
            change.get("change_type"),
            norm_text((change.get("text") or {}).get("old")),
            norm_text((change.get("text") or {}).get("new")),
        )
        for change in canonical.get("changes") or []
    )


def is_material(signature: tuple) -> bool:
    """PRE-REGISTRATION.md clause (c): whole-change presence, above a content floor."""
    _kind, old, new = signature
    blob = f"{old} {new}"
    if _AMOUNT_TOKEN.search(blob) or _SECTION_ID.search(blob):
        return True
    return len(blob.replace(" ", "")) >= _MATERIAL_MIN_CHARS


# ---------- pipeline drivers --------------------------------------------------


def xml_canonical(v1_xml: Path, v2_xml: Path) -> dict:
    v1, v2 = normalize_bill(v1_xml), normalize_bill(v2_xml)
    diff_dict = bill_diff_to_dict(diff_bills(v1, v2), financial=True)
    full_text, spans, tree = build_xml_full_text(v1, v2)
    return xml_diff_to_canonical(diff_dict, full_text=full_text, full_text_spans=spans, tree=tree)


def pdf_canonical(backend: str, v1_pdf: Path, v2_pdf: Path, bill: str, mode: str) -> tuple[dict, dict]:
    congress, chamber, number = bill.split("-")
    timings = {}
    pages = {}
    for side, path in (("v1", v1_pdf), ("v2", v2_pdf)):
        t0 = time.perf_counter()
        raw, _summary = run_backend(backend, path)
        timings[f"{side}_extract_s"] = round(time.perf_counter() - t0, 3)
        pages[side], _diag = reconstruct(raw, repaired=(mode == "repaired"))

    # Apply the SAME guard production applies. `compare/pdf.py` declines an unnumbered
    # (enrolled) layout with UnsupportedLayoutError before diffing, because every anchor
    # path gates on a printed line number, so an enrolled bill collapses into one
    # anchorless block and the diff returns a confident wrong answer rather than failing.
    #
    # Calling `diff_pdfs` directly bypasses that guard, and this harness originally did.
    # The result was exactly the failure the guard exists to prevent: on 118-hr-4366/5->6
    # the PDF side reported 3468 amount entries against the XML's 0, and on
    # 115-hr-5895/4->5 it matched only 47 of 164. Both pairs end in an enrolled bill.
    # Scoring a backend on a document the product declines measures nothing about the
    # backend, so those pairs are marked declined rather than silently scored.
    declined = [side for side in ("v1", "v2") if _is_unnumbered_layout(pages[side])]
    if declined:
        raise UnsupportedLayoutError(
            f"unnumbered (enrolled) layout on {'+'.join(declined)}; production declines this pair"
        )

    t0 = time.perf_counter()
    diff = diff_pdfs(pages["v1"], pages["v2"])
    timings["diff_s"] = round(time.perf_counter() - t0, 3)

    text_v1, off_v1 = pdf_full_text(pages["v1"])
    text_v2, off_v2 = pdf_full_text(pages["v2"])
    canonical = pdf_diff_to_canonical(
        diff,
        bill_type=chamber,
        bill_number=number,
        congress=congress,
        full_text={"v1": text_v1, "v2": text_v2},
        line_offsets={"v1": off_v1, "v2": off_v2},
    )
    return canonical, timings


def corpus_pairs() -> list[tuple[str, int, int, Path, Path, Path, Path]]:
    """Consecutive version pairs carrying both formats on both sides (ADR 0015)."""
    out = []
    for d in sorted((REPO / "tests" / "corpus").iterdir()):
        if not d.is_dir():
            continue
        stems: dict[int, dict[str, Path]] = {}
        for f in d.iterdir():
            m = re.match(r"(\d+)_([a-z-]+)\.(pdf|xml)$", f.name)
            if m:
                stems.setdefault(int(m.group(1)), {})[m.group(3)] = f
        both = sorted(n for n, formats in stems.items() if {"pdf", "xml"} <= formats.keys())
        for a, b in zip(both, both[1:]):
            if b == a + 1:
                out.append((d.name, a, b, stems[a]["pdf"], stems[b]["pdf"], stems[a]["xml"], stems[b]["xml"]))
    return out


def compare(pdf_canon: dict, xml_canon: dict) -> dict:
    pdf_amounts, xml_amounts = amount_triples(pdf_canon), amount_triples(xml_canon)
    pdf_sigs, xml_sigs = change_signatures(pdf_canon), change_signatures(xml_canon)
    pdf_old, pdf_new = changed_text_tokens(pdf_canon)
    xml_old, xml_new = changed_text_tokens(xml_canon)

    only_pdf = pdf_sigs - xml_sigs
    only_xml = xml_sigs - pdf_sigs
    material = [s for s in (only_pdf + only_xml) if is_material(s)]

    return {
        "T1_change_signatures": prf(xml_sigs, pdf_sigs),
        "T1b_changed_tokens_old": prf(xml_old, pdf_old),
        "T1b_changed_tokens_new": prf(xml_new, pdf_new),
        "T2_amount_entries": prf(xml_amounts, pdf_amounts),
        "T3_material_disagreements": len(material),
        "T3_sample": [{"kind": s[0], "old": s[1][:180], "new": s[2][:180]} for s in material[:8]],
        "context": {
            "n_changes_pdf": len(pdf_canon.get("changes") or []),
            "n_changes_xml": len(xml_canon.get("changes") or []),
            "n_amount_entries_pdf": sum(pdf_amounts.values()),
            "n_amount_entries_xml": sum(xml_amounts.values()),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--backends", default=",".join(ALL_BACKENDS))
    ap.add_argument("--modes", default="strict,repaired")
    ap.add_argument("--limit-pairs", type=int, default=None)
    args = ap.parse_args()

    backends = args.backends.split(",")
    if backends[0] != "pdfium-native":
        backends = ["pdfium-native"] + [b for b in backends if b != "pdfium-native"]
    modes = args.modes.split(",")

    pairs = corpus_pairs()
    if args.limit_pairs:
        pairs = pairs[: args.limit_pairs]
    print(f"{len(pairs)} pairs x {len(backends)} backends x {len(modes)} modes", file=sys.stderr)

    out: dict = {"pairs": {}, "n_pairs": len(pairs), "backends": backends}
    args.out.parent.mkdir(parents=True, exist_ok=True)

    for i, (bill, a, b, pdf1, pdf2, xml1, xml2) in enumerate(pairs, 1):
        key = f"{bill}/{a}->{b}"
        out["pairs"][key] = {}
        try:
            xml_canon = xml_canonical(xml1, xml2)
        except Exception as exc:
            out["pairs"][key]["_xml_error"] = f"{type(exc).__name__}: {exc}"
            print(f"  [{i}/{len(pairs)}] {key} XML ERROR {exc}", file=sys.stderr)
            args.out.write_text(json.dumps(out, indent=1, default=str))
            continue

        for mode in modes:
            incumbent_canon = None
            for backend in backends:
                slot = f"{backend}/{mode}"
                try:
                    canon, timings = pdf_canonical(backend, pdf1, pdf2, bill, mode)
                    entry = compare(canon, xml_canon)
                    entry["timings"] = timings
                    if backend == "pdfium-native":
                        incumbent_canon = canon
                        entry["T4_vs_incumbent"] = None
                    else:
                        # T4: hold the whole downstream pipeline fixed, vary only glyphs.
                        entry["T4_vs_incumbent"] = {
                            "change_signatures": prf(change_signatures(incumbent_canon), change_signatures(canon)),
                            "amount_entries": prf(amount_triples(incumbent_canon), amount_triples(canon)),
                            "identical_changes": change_signatures(incumbent_canon) == change_signatures(canon),
                            "identical_amounts": amount_triples(incumbent_canon) == amount_triples(canon),
                        }
                    out["pairs"][key][slot] = entry
                    note = (
                        f"amtF1={entry['T2_amount_entries']['f1']:.3f} "
                        f"chgF1={entry['T1_change_signatures']['f1']:.3f} "
                        f"mat={entry['T3_material_disagreements']}"
                    )
                    if entry["T4_vs_incumbent"]:
                        note += (
                            f" | vs_inc amt={entry['T4_vs_incumbent']['identical_amounts']}"
                            f" chg={entry['T4_vs_incumbent']['identical_changes']}"
                        )
                except Exception as exc:
                    out["pairs"][key][slot] = {
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc()[-1200:],
                    }
                    note = "ERROR"
                print(f"  [{i}/{len(pairs)}] {key:<24} {slot:<24} {note}", file=sys.stderr)
        args.out.write_text(json.dumps(out, indent=1, default=str))

    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
