"""Phase 1: per-document scoring of every backend through the neutral layer (N=52).

Implements metrics M1-M5 exactly as PRE-REGISTRATION.md defines them. Every backend is
scored on output of the ONE neutral reconstruction layer, so what is measured is
glyph-fact quality, not a library's own text assembly.

The calibration gate (Trap 1) runs first and is reported first: PDFium's glyph facts go
through the same layer, and if the incumbent does not land near ceiling, no other number
here means anything.

Run:
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_phase1.py \
      --out docs/research/pdf-backend-bakeoff/results/phase1.json [--limit-docs N]
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import statistics
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from contract import ALL_BACKENDS, CP, FONT, X0, run_backend  # noqa: E402
from reconstruct import cluster_lines, reconstruct  # noqa: E402

from deltatrack.bill_tree import extract_text_content, find_bill_bodies  # noqa: E402
from deltatrack.formatters.canonical import _pdf_tree_payload  # noqa: E402
from deltatrack.parsers.pdf_anchors import breadcrumb_for, extract_anchors  # noqa: E402
from deltatrack.parsers.pdf_text import normalize_glyphs, pdf_full_text  # noqa: E402

_WORD = re.compile(r"\S+")


# ---------- M1: text recovery ------------------------------------------------


def normalize_for_text_compare(text: str) -> list[str]:
    """Token stream both sides are reduced to before comparison.

    Case is preserved (GPO small-caps headings carry real meaning), whitespace is
    collapsed, and `normalize_glyphs` maps the typographic forms the PDF carries and the
    XML does not. Everything removed here is listed as non-material in the
    pre-registration, so the metric cannot be inflated by widening this function later.
    """
    text = normalize_glyphs(text)
    text = text.replace("­", "").replace("�", "")
    return _WORD.findall(text)


_MIN_ANCHOR_BLOCK = 4
# Alignment only ever trims the ends, so it only ever needs to look at the ends. A GPO
# cover page runs a few hundred tokens; these windows are an order of magnitude larger.
# Bounding them keeps `difflib`'s quadratic matcher off the 180k-token enrolled bills,
# where an unbounded call takes many minutes per document per backend.
_ALIGN_WINDOW_PDF = 4000
_ALIGN_WINDOW_XML = 1500
# Ceiling on the aligned candidate length for the order-sensitive cross-check. Above
# this, difflib's quadratic matcher costs more than the audit is worth.
_LCS_CROSS_CHECK_MAX = 25000


def align_to_body(reference: list[str], candidate: list[str]) -> tuple[list[str], dict]:
    """Trim the PDF's leading and trailing non-body matter before scoring.

    THE ALIGNMENT STEP Trap 1 demands, and it is frozen here before any challenger is
    scored. A GPO PDF prints a cover page (chamber, congress, session, sponsors, referral
    history, calendar number) and often a signature block; `find_bill_bodies` returns
    none of that. Unaligned, those tokens are counted as PDF false positives, which is
    noise on a 94-page bill (precision 0.93) and catastrophic on a 1-page stub
    (precision 0.21) -- so the ranking would be driven by document length rather than by
    backend quality.

    The rule trims EDGES ONLY: find the first and last matching blocks of at least
    `_MIN_ANCHOR_BLOCK` tokens and keep the candidate span between them. Interior
    material is untouched, so a backend that drops, duplicates or garbles body text is
    still fully penalised. That asymmetry is the point -- alignment must not be able to
    hide the defects the bake-off exists to find.
    """
    head_sm = difflib.SequenceMatcher(a=reference[:_ALIGN_WINDOW_XML], b=candidate[:_ALIGN_WINDOW_PDF], autojunk=False)
    head_blocks = [b for b in head_sm.get_matching_blocks() if b.size >= _MIN_ANCHOR_BLOCK]
    start = head_blocks[0].b if head_blocks else 0

    tail_sm = difflib.SequenceMatcher(
        a=reference[-_ALIGN_WINDOW_XML:], b=candidate[-_ALIGN_WINDOW_PDF:], autojunk=False
    )
    tail_blocks = [b for b in tail_sm.get_matching_blocks() if b.size >= _MIN_ANCHOR_BLOCK]
    if tail_blocks:
        last = tail_blocks[-1]
        offset = max(0, len(candidate) - _ALIGN_WINDOW_PDF)
        end = offset + last.b + last.size
    else:
        end = len(candidate)

    if end <= start:  # degenerate; keep everything rather than invent a span
        return candidate, {"aligned": False, "trimmed_head": 0, "trimmed_tail": 0}
    return candidate[start:end], {
        "aligned": bool(head_blocks or tail_blocks),
        "trimmed_head": start,
        "trimmed_tail": len(candidate) - end,
    }


def token_f1(reference: list[str], candidate: list[str]) -> dict:
    """Token-level precision/recall/F1 by MULTISET intersection.

    Tokens rather than characters: character similarity on a bill is dominated by
    whitespace and flatters every backend into the high nineties.

    Multiset rather than longest-common-subsequence, for two reasons. The practical one
    is cost: `difflib` is quadratic and the enrolled bills run to ~180k tokens, which is
    minutes per document per backend per mode, i.e. days for the full matrix. The
    principled one is that PDF-vs-XML *ordering* differences are expected by design --
    the two are different artifacts of one bill version, not two attempts at one artifact
    -- so penalising reordering would measure the format gap rather than the backend.

    A multiset still penalises every defect this bake-off is looking for: a dropped
    token, a duplicated token, a garbled token and a hallucinated token all move the
    score. Only pure reordering is invisible, and that is deliberate.

    AMENDMENT, recorded rather than quietly applied: PRE-REGISTRATION.md specified
    "token-level F1" without naming the algorithm, and the first implementation used
    LCS. The switch was made after seeing the runtime, not the ranking. See
    `--cross-check-lcs`, which recomputes both on documents small enough to afford it and
    reports the delta, so the substitution can be audited rather than trusted.
    """
    if not reference and not candidate:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "matched": 0}
    ref = Counter(reference)
    cand = Counter(candidate)
    matched = sum((ref & cand).values())
    precision = matched / len(candidate) if candidate else 0.0
    recall = matched / len(reference) if reference else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 5),
        "recall": round(recall, 5),
        "f1": round(f1, 5),
        "matched": matched,
    }


def token_f1_lcs(reference: list[str], candidate: list[str]) -> dict:
    """Order-sensitive F1, for the cross-check only. Quadratic; small documents only."""
    if not reference and not candidate:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "matched": 0}
    sm = difflib.SequenceMatcher(a=reference, b=candidate, autojunk=False)
    matched = sum(block.size for block in sm.get_matching_blocks())
    precision = matched / len(candidate) if candidate else 0.0
    recall = matched / len(reference) if reference else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 5),
        "recall": round(recall, 5),
        "f1": round(f1, 5),
        "matched": matched,
    }


def xml_body_tokens(xml_path: Path) -> list[str]:
    root = ET.parse(xml_path).getroot()
    bodies = find_bill_bodies(root)
    return normalize_for_text_compare("\n".join(extract_text_content(b) for b in bodies))


# ---------- M2: line-number recovery -----------------------------------------


def line_number_set(pages) -> set[tuple[int, int]]:
    return {(p.page_number, ln.line_number) for p in pages for ln in p.print_lines if ln.line_number is not None}


def line_number_scores(reference: set, candidate: set) -> dict:
    if not reference:
        return {"recall": None, "spurious_rate": None, "n_reference": 0}
    hit = len(reference & candidate)
    extra = len(candidate - reference)
    return {
        "recall": round(hit / len(reference), 5),
        "spurious_rate": round(extra / len(reference), 5),
        "n_reference": len(reference),
        "n_candidate": len(candidate),
    }


# ---------- M3 / M4: tree, conservation, breadcrumbs --------------------------

_AMOUNT = re.compile(r"\$[\d,]+(?:\.\d+)?")


def tree_scores(pages) -> dict:
    """Heading-tree shape plus the ADR 0014 money-conservation invariant.

    Conservation is measured the way the corpus gate measures it for PDF: the union of
    per-node `own_amounts` against the amounts present in the document's own full_text.
    PDF has no independent ground truth for this, which the corpus gate documents as a
    weaker carve-out; it is reported here on the same terms.
    """
    anchors = extract_anchors(pages)
    text, offsets = pdf_full_text(pages)
    nodes = _pdf_tree_payload(tuple(anchors), offsets, text)

    flat: list[dict] = []
    stack = list(nodes)
    while stack:
        node = stack.pop()
        flat.append(node)
        stack.extend(node.get("children") or [])

    own: Counter = Counter()
    for node in flat:
        for amount in node.get("own_amounts") or []:
            own[amount] += 1
    in_text = Counter(_AMOUNT.findall(text))
    over = sum(max(0, c - in_text.get(a, 0)) for a, c in own.items())
    dropped = sum(max(0, c - own.get(a, 0)) for a, c in in_text.items())

    crumbs = [breadcrumb_for(a, anchors) for a in anchors]
    return {
        "n_anchors": len(anchors),
        "n_nodes": len(flat),
        "levels": dict(Counter(n.get("level") for n in flat)),
        "conservation_overcount": over,
        "conservation_dropped": dropped,
        "conservation_holds": over == 0,
        "breadcrumbs": crumbs,
    }


def breadcrumb_agreement(reference: list, candidate: list) -> dict:
    if not reference:
        return {"agreement": None, "n_reference": 0}
    ref = Counter(tuple(c) for c in reference)
    cand = Counter(tuple(c) for c in candidate)
    shared = sum((ref & cand).values())
    return {
        "agreement": round(shared / sum(ref.values()), 5),
        "n_reference": sum(ref.values()),
        "n_candidate": sum(cand.values()),
    }


# ---------- M5: font-role separation -----------------------------------------


def font_role_scores(raw_pages) -> dict:
    """Can this backend separate the margin line-number from the body by FONT?

    Scored as role separation, never name-string equality: the source-signal inventory
    records bodies as `DeVinne` in bills but `NewCenturySchlbk` in enrolled,
    engrossed-amendment-senate and committee prints, so a name test would be measuring
    print class rather than backend capability.

    The margin glyph is identified positionally (leftmost run of digits on a line whose
    reconstruction starts with a margin number), which is independent of font, so the
    metric cannot be circular.
    """
    separated = 0
    total = 0
    empty_font = 0
    all_glyphs = 0
    for page in raw_pages:
        for row in cluster_lines(page):
            ordered = sorted(row, key=lambda g: g[X0])
            all_glyphs += len(ordered)
            empty_font += sum(1 for g in ordered if not g[FONT])
            digits: list = []
            for g in ordered:
                if 0x30 <= g[CP] <= 0x39:
                    digits.append(g)
                else:
                    break
            if not digits or len(digits) > 2 or len(ordered) <= len(digits):
                continue
            body = ordered[len(digits) :]
            body_fonts = [g[FONT] for g in body if g[CP] != 32 and g[FONT]]
            margin_fonts = [g[FONT] for g in digits if g[FONT]]
            if not body_fonts or not margin_fonts:
                continue
            total += 1
            if statistics.mode(margin_fonts) != statistics.mode(body_fonts):
                separated += 1
    return {
        "margin_vs_body_separation": round(separated / total, 5) if total else None,
        "n_numbered_lines_scored": total,
        "empty_font_name_rate": round(empty_font / all_glyphs, 5) if all_glyphs else None,
        "n_glyphs": all_glyphs,
    }


# ---------- driver ------------------------------------------------------------


def corpus_documents() -> list[tuple[str, int, Path, Path]]:
    """Every corpus version carrying BOTH formats, derived not enumerated (ADR 0015)."""
    out = []
    for d in sorted((REPO / "tests" / "corpus").iterdir()):
        if not d.is_dir():
            continue
        stems: dict[int, dict[str, Path]] = {}
        for f in d.iterdir():
            m = re.match(r"(\d+)_([a-z-]+)\.(pdf|xml)$", f.name)
            if m:
                stems.setdefault(int(m.group(1)), {})[m.group(3)] = f
        for n, formats in sorted(stems.items()):
            if {"pdf", "xml"} <= formats.keys():
                out.append((d.name, n, formats["pdf"], formats["xml"]))
    return out


def score_document(
    backend: str, pdf: Path, xml: Path, reference: dict | None, cross_check_lcs: bool = False
) -> dict:
    t0 = time.perf_counter()
    raw_pages, summary = run_backend(backend, pdf)
    extract_s = time.perf_counter() - t0

    result: dict = {
        "backend": backend,
        "extract_s": round(extract_s, 3),
        "backend_summary": summary,
        "font_role": font_role_scores(raw_pages),
    }

    xml_tokens = xml_body_tokens(xml)
    for mode in ("strict", "repaired"):
        pages, diag = reconstruct(raw_pages, repaired=(mode == "repaired"))
        tokens = normalize_for_text_compare("\n".join(p.text for p in pages))
        aligned, align_info = align_to_body(xml_tokens, tokens)
        tree = tree_scores(pages)
        entry = {
            "reconstruction": diag,
            "alignment": align_info,
            "text_vs_xml": token_f1(xml_tokens, aligned),
            "text_vs_xml_unaligned": token_f1(xml_tokens, tokens),
            "text_vs_xml_lcs": (
                token_f1_lcs(xml_tokens, aligned) if cross_check_lcs and len(aligned) <= _LCS_CROSS_CHECK_MAX else None
            ),
            "line_numbers": line_number_scores(
                reference[mode]["line_number_set"] if reference else line_number_set(pages),
                line_number_set(pages),
            ),
            "tree": {k: v for k, v in tree.items() if k != "breadcrumbs"},
            "breadcrumbs": breadcrumb_agreement(
                reference[mode]["breadcrumbs"] if reference else tree["breadcrumbs"],
                tree["breadcrumbs"],
            ),
            "n_pages": len(pages),
        }
        result[mode] = entry
        # The incumbent run also publishes the reference sets the challengers score
        # against for the no-regression gates (2 and 3).
        result.setdefault("_reference", {})[mode] = {
            "line_number_set": line_number_set(pages),
            "breadcrumbs": tree["breadcrumbs"],
        }
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit-docs", type=int, default=None)
    ap.add_argument("--backends", default=",".join(ALL_BACKENDS))
    ap.add_argument(
        "--cross-check-lcs",
        action="store_true",
        help="also compute the order-sensitive LCS F1 where affordable, to audit the "
        "multiset substitution recorded in token_f1's docstring",
    )
    args = ap.parse_args()

    backends = args.backends.split(",")
    if backends[0] != "pdfium-native":
        # The incumbent must run first: it is both the calibration gate and the reference
        # for the no-regression gates.
        backends = ["pdfium-native"] + [b for b in backends if b != "pdfium-native"]

    docs = corpus_documents()
    if args.limit_docs:
        docs = docs[: args.limit_docs]
    print(f"scoring {len(docs)} documents x {len(backends)} backends", file=sys.stderr)

    out: dict = {"documents": {}, "n_documents": len(docs), "backends": backends}
    args.out.parent.mkdir(parents=True, exist_ok=True)

    for i, (bill, version, pdf, xml) in enumerate(docs, 1):
        key = f"{bill}/{version}"
        out["documents"][key] = {}
        reference = None
        for backend in backends:
            try:
                res = score_document(backend, pdf, xml, reference, args.cross_check_lcs)
                if backend == "pdfium-native":
                    reference = res.pop("_reference")
                else:
                    res.pop("_reference", None)
                out["documents"][key][backend] = res
                mark = f"f1={res['strict']['text_vs_xml']['f1']:.3f}/{res['repaired']['text_vs_xml']['f1']:.3f}"
            except Exception as exc:  # a crash is a gate-1 failure, recorded not hidden
                out["documents"][key][backend] = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc()[-1500:],
                }
                mark = "ERROR"
            print(f"  [{i}/{len(docs)}] {key:<28} {backend:<14} {mark}", file=sys.stderr)
        args.out.write_text(json.dumps(out, indent=1, default=str))

    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
