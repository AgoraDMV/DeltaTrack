"""The oracle: every PDF heading run, with the segmentation the XML says is correct.

A **run** is the contiguous in-band uppercase heading block that ends at a leaf
account -- exactly the lines ``_account_anchors_by_size`` reads (the run
``agency_before_leaf`` joins, plus the leaf itself). It is the unit both #524 and #501
argue about.

**Ground truth is derived, never hand-labelled.** For each run, every contiguous
segmentation of its lines is tried; a segmentation is admissible when each segment's
joined text is an XML heading, with the last segment an account-level name and the
earlier ones container-level. A run is RESOLVED when exactly one segmentation is
admissible. Over the committed dual-format corpus that is 3962 of 4173 runs, and no run
admits more than one -- the oracle is unique where it exists, and silent where it does
not, rather than guessing.

This probe is retained because nothing in ``tests/`` owns it: the account-vocabulary
floors in ``tests/test_pdf_anchor_golden.py`` score a *set of names*, which cannot see
where a run was cut. Writes ``results/heading-runs.jsonl`` (gitignored), consumed by
``segmentation_rules.py``.

    uv run python docs/research/pdf-heading-identity/probes/heading_runs.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from itertools import product
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from deltatrack.bill_tree import normalize_bill, normalize_header  # noqa: E402
from deltatrack.parsers.pdf_anchors import (  # noqa: E402
    _ENUM_PREFIX,
    _SECTION_PATTERN,
    _SIZE_EPS,
    _body_column_width,
    _flatten,
    _is_parenthetical,
    _is_uppercase_heading,
    derive_size_bands,
)
from deltatrack.parsers.pdf_text import extract_clean_pages  # noqa: E402
from scripts.heading_precision import _xml_headings  # noqa: E402

FIXTURES = PROJECT_ROOT / "tests" / "corpus"
OUT = Path(__file__).resolve().parent.parent / "results"
WRAP_HYPHENS = ("-", "‐", "‑")

#: Runs longer than this are recorded but not segmentation-searched. The search is
#: 2^(n-1) and the corpus maximum is 4, so this is a guard, not a limit that bites.
MAX_SEG_LINES = 8


def xml_vocabs(xml_path: Path) -> tuple[set[str], set[str]]:
    """``(account_vocab, container_vocab)``, normalized.

    The account vocabulary is the harness's own effective-heading set (#499). The
    container vocabulary is every intermediate ``display_path`` segment plus any
    standalone intermediate/major header -- the same derivation
    ``tests/test_pdf_anchor_golden._xml_agency_vocab`` uses, minus its casing split,
    because a run's upper line may be either a department or an agency.
    """
    _counts, unique = _xml_headings(xml_path)
    account = unique["appropriations-small"] | unique["appropriations-intermediate"]
    tree = normalize_bill(xml_path)
    container: set[str] = set()
    for node in tree.nodes:
        if node.tag == "appropriations-small":
            for seg in node.display_path[1:-1]:
                container.add(normalize_header(seg))
        elif node.tag in ("appropriations-intermediate", "appropriations-major") and node.header_text:
            container.add(normalize_header(node.header_text))
    return account, container


def join_texts(texts: list[str], indices) -> str:
    """Join lines with the parser's own de-hyphenation rule (``_join_major_run``)."""
    out = texts[indices[0]]
    for i in indices[1:]:
        seg = texts[i]
        out = out[:-1] + seg if out.endswith(WRAP_HYPHENS) else f"{out} {seg}"
    return out


def _segmentations(n: int):
    for cuts in product((0, 1), repeat=n - 1):
        groups = [[0]]
        for i, cut in enumerate(cuts, start=1):
            (groups.append([i]) if cut else groups[-1].append(i))
        yield groups


def correct_segmentation(texts, account_vocab, container_vocab):
    """The unique XML-admissible segmentation, or ``(None, reason)``."""
    if len(texts) > MAX_SEG_LINES:
        return None, "too_long"
    admissible = []
    for groups in _segmentations(len(texts)):
        ok = True
        for gi, group in enumerate(groups):
            joined = normalize_header(join_texts(texts, group))
            last = gi == len(groups) - 1
            if last and joined not in account_vocab:
                ok = False
                break
            if not last and joined not in container_vocab and joined not in account_vocab:
                ok = False
                break
        if ok:
            admissible.append(groups)
    if len(admissible) == 1:
        return admissible[0], "resolved"
    if not admissible:
        return None, "no_valid_segmentation"
    return None, f"ambiguous_{len(admissible)}"


def runs_for(pdf_path: Path):
    """Every ``(run lines + leaf)`` sequence the account detector reads, with geometry.

    Transcribed from ``_account_anchors_by_size`` rather than calling it, because that
    function returns anchors -- the lines it discarded on the way are the whole subject
    here.
    """
    pages = extract_clean_pages(pdf_path)
    bands = derive_size_bands(pages)
    if bands is None:
        return None, None
    flat = _flatten(pages)
    n = len(flat)

    def is_candidate(line) -> bool:
        return (
            line.line_number is not None
            and line.glyph_size is not None
            and bands.heading_lo - _SIZE_EPS <= line.glyph_size <= bands.heading_hi + _SIZE_EPS
            and _is_uppercase_heading(line.text)
            and not _ENUM_PREFIX.match(line.text)
            and not _is_parenthetical(line.text)
        )

    def continues_catchline(idx: int) -> bool:
        for j in range(idx - 1, -1, -1):
            prev = flat[j][1]
            if not prev.text.strip() or _is_parenthetical(prev.text):
                continue
            if _SECTION_PATTERN.match(prev.text):
                return True
            if is_candidate(prev):
                continue
            return False
        return False

    def is_body(line) -> bool:
        if not line.text.strip():
            return False
        if line.glyph_size is None:
            return True
        return abs(line.glyph_size - bands.body) <= _SIZE_EPS

    out = []
    for idx in range(n):
        page_number, line = flat[idx]
        if not is_candidate(line) or continues_catchline(idx):
            continue
        nxt = None
        for j in range(idx + 1, n):
            cand = flat[j][1]
            if not cand.text.strip() or _is_parenthetical(cand.text):
                continue
            nxt = cand
            break
        if nxt is not None and _SECTION_PATTERN.match(nxt.text.strip()):
            continue  # a grouping header, not a leaf
        if not (nxt is None or is_body(nxt)):
            continue  # mid-run, not a leaf
        run = []
        j = idx - 1
        while j >= 0:
            page_no, prev = flat[j]
            if not prev.text.strip() or _is_parenthetical(prev.text):
                j -= 1
                continue
            if is_candidate(prev) and not continues_catchline(j):
                run.append((page_no, prev))
                j -= 1
                continue
            break
        run.reverse()
        out.append([*run, (page_number, line)])
    return out, _body_column_width(pages)


def _geom(line):
    if line.geom is None:
        return None
    return {
        "left": round(line.geom.content_left, 3),
        "right": round(line.geom.content_right, 3),
        "fwr": round(line.geom.first_word_right, 3),
    }


def main() -> None:
    only = os.environ.get("ONLY_BILL")
    OUT.mkdir(exist_ok=True)
    rows = []
    for bill_dir in sorted(FIXTURES.iterdir()):
        if not bill_dir.is_dir() or bill_dir.name.startswith("CRPT-"):
            continue
        if only and only not in bill_dir.name:
            continue
        for pdf in sorted(bill_dir.glob("*.pdf")):
            xml = pdf.with_suffix(".xml")
            if not xml.exists():
                continue
            sequences, column_width = runs_for(pdf)
            if sequences is None:
                continue  # no size bands: #508 / #261 territory, not this study's
            account_vocab, container_vocab = xml_vocabs(xml)
            resolved = 0
            for seq in sequences:
                texts = [line.text.strip() for _p, line in seq]
                segmentation, status = correct_segmentation(texts, account_vocab, container_vocab)
                resolved += status == "resolved"
                rows.append(
                    {
                        "bill": bill_dir.name,
                        "version": pdf.stem,
                        "column_width": round(column_width, 3) if column_width else None,
                        "pages": [p for p, _l in seq],
                        "lines": [line.line_number for _p, line in seq],
                        "texts": texts,
                        "sizes": [line.glyph_size for _p, line in seq],
                        "geoms": [_geom(line) for _p, line in seq],
                        "truth": segmentation,
                        "status": status,
                    }
                )
            print(f"{bill_dir.name}/{pdf.stem}: runs={len(sequences)} resolved={resolved}")

    path = OUT / "heading-runs.jsonl"
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    multi = [r for r in rows if len(r["texts"]) > 1]
    print(f"\nwrote {len(rows)} runs -> {path}")
    print("status:", Counter(r["status"] for r in rows))
    print(f"multi-line runs: {len(multi)}", Counter(r["status"] for r in multi))


if __name__ == "__main__":
    main()
