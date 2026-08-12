"""Concern B metrics for the confirmatory run, none of which may use PDFium as truth.

PRE-REGISTRATION-CONFIRMATORY.md, "Concern B -- independent document accuracy".

  B1   text recovery F1                vs the XML body            (existing, reused)
  B2   heading-LABEL recovery F1       vs the XML tree            (new at population scale)
  B3a  line-number self-consistency    vs the document itself     (new; no reference)
  B5   amount -> heading association   vs the XML tree            (new)
  B6   parent/child heading accuracy   vs the XML tree            (new)

Two things this module deliberately does NOT do:

  * It never reads the incumbent. The exploratory line-number metric scored against
    PDFium's own line-number set (score_phase1.score_document passes the incumbent's set
    as `reference`), which makes it a parity measurement, not an accuracy one. It now
    lives in Concern A. B3a replaces it with a property of the document: a page's margin
    numbers must form a gap-free run, which needs no external oracle at all.

  * It never compares heading LEVELS. The two pipelines assign different level names to
    the same objects -- the XML's `agency` holds "Military construction, air force",
    which the PDF calls an `account` -- and a level-by-level comparison produced a false
    reversal during the audit. Every heading metric here is level-agnostic by
    pre-commitment.

B2 is where "found the heading" stops. B5 and B6 exist because a backend can find every
heading and attach them all wrongly, and attachment is what puts an amount under the
right account in the financial tables.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.formatters.canonical import _pdf_tree_payload  # noqa: E402
from deltatrack.formatters.text_serializer import build_xml_full_text  # noqa: E402
from deltatrack.parsers.pdf_anchors import extract_anchors  # noqa: E402
from deltatrack.parsers.pdf_text import pdf_full_text  # noqa: E402

# Level-agnostic heading sets. The PDF and XML pipelines name levels differently, so the
# two sets are not the same strings -- they are the same OBJECTS on each side.
PDF_HEADING_KINDS = ("account", "agency", "grouping")
XML_HEADING_LEVELS = ("account", "agency", "heading")

_AMOUNT = re.compile(r"\$[\d,]+(?:\.\d+)?")


def norm_label(s: str | None) -> str:
    return " ".join((s or "").upper().replace(",", "").replace(".", "").split())


def f1(hit: int, n_cand: int, n_ref: int) -> dict:
    p = hit / n_cand if n_cand else 0.0
    r = hit / n_ref if n_ref else 0.0
    return {
        "f1": round(2 * p * r / (p + r), 5) if (p + r) else 0.0,
        "precision": round(p, 5),
        "recall": round(r, 5),
        "matched": hit,
        "n_candidate": n_cand,
        "n_reference": n_ref,
    }


# ---------- shared tree flattening -------------------------------------------


def _flatten(nodes: list[dict]) -> list[tuple[dict, list[dict]]]:
    """(node, ancestors-outermost-first) for every node, depth-first."""
    out: list[tuple[dict, list[dict]]] = []
    stack: list[tuple[dict, list[dict]]] = [(n, []) for n in reversed(nodes)]
    while stack:
        node, anc = stack.pop()
        out.append((node, anc))
        for child in reversed(node.get("children") or []):
            stack.append((child, anc + [node]))
    return out


def _heading_of(node: dict, ancestors: list[dict], levels: tuple[str, ...]) -> str | None:
    """Nearest heading-ish label at or above `node`, or None."""
    for cand in [node] + list(reversed(ancestors)):
        if cand.get("level") in levels and cand.get("label"):
            return norm_label(cand["label"])
    return None


def _parent_heading_of(ancestors: list[dict], levels: tuple[str, ...]) -> str:
    """Nearest heading-ish ancestor label, "" for a root-level heading."""
    for cand in reversed(ancestors):
        if cand.get("level") in levels and cand.get("label"):
            return norm_label(cand["label"])
    return ""


# ---------- XML side (the reference) -----------------------------------------


def xml_reference(xml_path: Path) -> dict:
    """Heading labels, amount->heading map and heading->parent map, from the XML tree.

    DeltaTrack#11 caveat travels with the caller: this reads the PARSER tree, which drops
    <quoted-block>. Documents carrying one are reported in their own stratum for B2/B5/B6
    and excluded from the primary figure. B1 is unaffected -- its reference is a raw
    itertext walk that includes quoted-block text.
    """
    v = normalize_bill(xml_path)
    _, _, tree = build_xml_full_text(v, v)
    flat = _flatten(list(tree["v1"]))

    labels: set[str] = set()
    parent: dict[str, str] = {}
    amounts: Counter = Counter()
    assoc: Counter = Counter()

    for node, anc in flat:
        lab = norm_label(node.get("label"))
        if node.get("level") in XML_HEADING_LEVELS and lab:
            labels.add(lab)
            parent.setdefault(lab, _parent_heading_of(anc, XML_HEADING_LEVELS))
        head = _heading_of(node, anc, XML_HEADING_LEVELS)
        for amt in node.get("own_amounts") or []:
            amounts[amt] += 1
            if head is not None:
                assoc[(amt, head)] += 1

    return {"labels": labels, "parent": parent, "amounts": amounts, "assoc": assoc}


def xml_has_quoted_block(xml_path: Path) -> bool:
    return "quoted-block" in xml_path.read_text(errors="ignore")


# ---------- PDF side (the candidate) -----------------------------------------


def pdf_structure(pages) -> dict:
    anchors = extract_anchors(pages)
    text, offsets = pdf_full_text(pages)
    nodes = _pdf_tree_payload(tuple(anchors), offsets, text)
    flat = _flatten(nodes)

    labels: set[str] = set()
    parent: dict[str, str] = {}
    amounts: Counter = Counter()
    assoc: Counter = Counter()

    for node, anc in flat:
        lab = norm_label(node.get("label"))
        if node.get("level") in PDF_HEADING_KINDS and lab:
            labels.add(lab)
            parent.setdefault(lab, _parent_heading_of(anc, PDF_HEADING_KINDS))
        head = _heading_of(node, anc, PDF_HEADING_KINDS)
        for amt in node.get("own_amounts") or []:
            amounts[amt] += 1
            if head is not None:
                assoc[(amt, head)] += 1

    # Anchor labels are the B2 candidate set: extract_anchors is the product's own
    # heading detector, and _pdf_tree_payload can synthesize interior nodes that are not
    # detected headings. Using anchors keeps B2 a measurement of detection.
    anchor_labels = {norm_label(a.text) for a in anchors if a.kind in PDF_HEADING_KINDS and a.text}

    return {
        "labels": anchor_labels,
        "tree_labels": labels,
        "parent": parent,
        "amounts": amounts,
        "assoc": assoc,
        "n_anchors": len(anchors),
    }


# ---------- the metrics -------------------------------------------------------


def b2_heading_labels(pdf: dict, ref: dict) -> dict:
    """B2 -- heading LABEL recovery. Says nothing about whether they are attached right."""
    hit = len(pdf["labels"] & ref["labels"])
    return f1(hit, len(pdf["labels"]), len(ref["labels"]))


def b3a_line_number_self_consistency(pages, scored_pages: set[int] | None = None) -> dict:
    """B3a -- a page's recovered margin numbers must form a gap-free run.

    No external reference: GPO numbers each page's body lines from 1 upward, so
    `|S| / max(S)` is 1.0 exactly when nothing is missing and nothing is invented, and it
    penalizes both directions. Pages with no numbers at all (covers, tables of contents)
    are scored only when another backend in the same run found numbers there --
    `scored_pages` carries that union, so a page nobody can number is not counted against
    anyone, and a page one backend CAN number counts against those that cannot.
    """
    per_page: dict[int, float] = {}
    starts_at_one = 0
    for page in pages:
        nums = {ln.line_number for ln in page.print_lines if ln.line_number is not None}
        if not nums:
            if scored_pages is not None and page.page_number in scored_pages:
                per_page[page.page_number] = 0.0
            continue
        if scored_pages is not None and page.page_number not in scored_pages:
            continue
        top = max(nums)
        per_page[page.page_number] = len(nums) / top if top else 0.0
        if min(nums) == 1:
            starts_at_one += 1
    if not per_page:
        return {"score": None, "n_pages": 0, "starts_at_one_rate": None}
    return {
        "score": round(sum(per_page.values()) / len(per_page), 5),
        "n_pages": len(per_page),
        "starts_at_one_rate": round(starts_at_one / len(per_page), 5),
        "worst_pages": sorted(per_page.items(), key=lambda kv: kv[1])[:5],
    }


def numbered_pages(pages) -> set[int]:
    return {p.page_number for p in pages if any(ln.line_number is not None for ln in p.print_lines)}


def b5_amount_association(pdf: dict, ref: dict) -> dict:
    """B5 -- of the amounts BOTH sides found, how many sit under the same heading?

    Restricted to the shared amount multiset on purpose: pooling in amounts only one side
    found would fold a DETECTION difference into an ASSOCIATION metric and make it
    uninterpretable. Detection is B1's and Concern A's business.
    """
    shared = pdf["amounts"] & ref["amounts"]
    if not shared:
        return {"f1": None, "n_reference": 0, "note": "no shared amounts"}
    keep = set(shared)
    p = Counter({k: c for k, c in pdf["assoc"].items() if k[0] in keep})
    r = Counter({k: c for k, c in ref["assoc"].items() if k[0] in keep})
    hit = sum((p & r).values())
    return f1(hit, sum(p.values()), sum(r.values()))


def b6_parent_child(pdf: dict, ref: dict) -> dict:
    """B6 -- for headings both sides found, is the immediate heading parent the same?"""
    shared = pdf["labels"] & ref["labels"]
    if not shared:
        return {"accuracy": None, "n": 0}
    agree = sum(1 for lab in shared if pdf["parent"].get(lab, "") == ref["parent"].get(lab, ""))
    return {
        "accuracy": round(agree / len(shared), 5),
        "n": len(shared),
        "agree": agree,
        "disagree_sample": sorted(
            (lab, pdf["parent"].get(lab, ""), ref["parent"].get(lab, ""))
            for lab in shared
            if pdf["parent"].get(lab, "") != ref["parent"].get(lab, "")
        )[:5],
    }
