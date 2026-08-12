"""cross_engine_control -- A39.2: the CONFIRMATORY cross-engine qualification producer.

    frozen rule   PRE-REGISTRATION red-team #2 / A27.6 -- re-run the neutral skeleton through a
                  second engine on a 10 % page subsample; document >= 0.95 and every sampled
                  page >= 0.75, else label results PDFIUM-CONDITIONED FRAME. NEVER
                  decision-blocking.
    executable    `cross_engine_result(...)` and `write_cross_engine_control(...)`
    test          `x22_score_input_contract.py`

WHY THIS EXISTS SEPARATELY FROM x09. `x09` is the DEVELOPMENT proof that the mechanism works
and that its faults are detectable; its artifact is explicitly development-only and may not be
consumed as the confirmatory qualification. This module produces the distinct canonical
artifact for the confirmatory population, behind the same VALID execution boundary as every
other confirmatory writer.

THE RULE HAS EXACTLY ONE OWNER, AND IT IS `X09.gate`. This module selects A39.2's sampled rows
and then CALLS that function; it does not recompute the denominator or the thresholds. An
earlier version did recompute them and got both wrong -- it read a `pdfium_lines` key that does
not exist, and scored `matched / pdfium` instead of the frozen `matched / max(pdfium, pymupdf)`.
The larger-count denominator is load-bearing: it makes over-segmentation by EITHER engine lower
agreement, so scoring against PDFium alone made PyMuPDF over-segmentation invisible. Keeping
0.95 / 0.75 / `max(...)` in two independently executable places is what allowed that drift, so
they now live in one place only.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import methodology_contracts as MC  # noqa: E402
import x09_skeleton_cross_engine as X09  # noqa: E402

SOURCE_SHA256_MISMATCH = "SOURCE_SHA256_MISMATCH"


class CrossEngineError(Exception):
    """The measurement cannot be produced as frozen. Deterministic, never a value."""

    def __init__(self, reason: str, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason} {detail!r}")


def verified_sha256(pdf_path: Path, expected_sha256: str) -> str:
    """A39.2 -- the document SHA is RESULT-BEARING input, so it is verified, not trusted.

    The page sample is ranked over `(document_sha256, page_number)`. A caller-supplied string
    that does not match the bytes would therefore select a different sample for the same
    document -- silently, and reproducibly, so nothing downstream could notice. Verifying
    closes that freedom: the pure A39.2 contract will happily rank any SHA, but the
    result-bearing producer cannot reach that freedom.
    """
    actual = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise CrossEngineError(
            SOURCE_SHA256_MISMATCH,
            {"path": str(pdf_path), "expected": expected_sha256, "actual": actual},
        )
    return actual


def _page_count(pdf_path: Path) -> int:
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    try:
        return doc.page_count
    finally:
        doc.close()


def cross_engine_result(document: str, document_sha256: str, pdf_path: Path, limit: int | None = None) -> dict:
    """One document's cross-engine qualification, measured on the A39.2 sampled pages.

    `limit=None` means THE WHOLE DOCUMENT, which is what the canonical writer uses. It is
    resolved to the real page count rather than passed through: `X09.pymupdf_lines` computes
    `min(limit, page_count)` and would raise on None. It is never reinterpreted as zero or as
    some prefix -- a silently truncated confirmatory measurement would qualify a frame on a
    fraction of its pages and report it as the whole.
    """
    pdf_path = Path(pdf_path)
    sha = verified_sha256(pdf_path, document_sha256)
    effective_limit = _page_count(pdf_path) if limit is None else limit

    pdfium_pages = X09.pdfium_lines(pdf_path, effective_limit)
    pymupdf_pages = X09.pymupdf_lines(pdf_path, effective_limit)
    measured = X09.measure(pdfium_pages, pymupdf_pages)

    sampled_pages = MC.cross_engine_pages(sha, [row["page"] for row in measured])
    sampled_rows = [row for row in measured if row["page"] in set(sampled_pages)]

    # THE FROZEN RULE, called rather than reimplemented.
    verdict = X09.gate(sampled_rows)

    return {
        "document": document,
        "document_sha256": sha,
        "page_count": len(measured),
        "pages_measured": [row["page"] for row in measured],
        "sampled_pages": sampled_pages,
        "n_sampled": len(sampled_pages),
        "matched": sum(row["matched"] for row in sampled_rows),
        # the frozen denominator, reported so a reader can see WHICH one was used
        "denominator": sum(max(row["pdfium"], row["pymupdf"]) for row in sampled_rows),
        "denominator_rule": "sum(max(pdfium, pymupdf)) over sampled pages -- X09.gate's own",
        "gate": verdict,
        "passed": verdict["pass"],
        "qualification": None if verdict["pass"] else "PDFIUM-CONDITIONED FRAME",
        "decision_blocking": False,  # A27.6 -- qualifies reporting, blocks nothing
    }


def write_cross_engine_control(documents: list[dict], out_path: Path | None = None) -> dict:
    """A39.2 -- the CANONICAL execution-time artifact. Refuses before a VALID boundary.

    `documents` items: {"document", "document_sha256", "pdf_path"}. Guarded exactly as the
    oracle key and the S1 artifact are, so no confirmatory artifact can be written under a
    weaker condition than the material it describes.
    """
    import build_oracle as BO

    out_path = Path(out_path) if out_path else (HERE.parents[1] / "results" / "cross_engine_control.json")
    BO.assert_write_permitted(out_path)

    rows = []
    for doc in documents:
        BO.assert_source_permitted(doc["document"], doc.get("pdf_path"))
        rows.append(cross_engine_result(doc["document"], doc["document_sha256"], Path(doc["pdf_path"])))

    artifact = {
        "schema": "cross_engine_control/1",
        "population": BO.realized_population(
            [{"frame": {"document": d["document"]}, "pdf_path": d.get("pdf_path")} for d in documents]
        ),
        "execution_boundary_state": BO.execution_boundary_state(),
        "namespace": MC.CROSS_ENGINE_NAMESPACE,
        "fraction": MC.CROSS_ENGINE_FRACTION,
        "document_threshold": X09.DOC_MIN,
        "page_threshold": X09.PAGE_MIN,
        "rule_owner": "x09_skeleton_cross_engine.gate -- called, never reimplemented",
        "development_evidence_is_not_this": "results/x09_skeleton_cross_engine.json is DEVELOPMENT "
        "mechanism evidence only and is never a confirmatory scorer input",
        "per_document": rows,
        "n_documents": len(rows),
        "n_qualified": sum(1 for r in rows if not r["passed"]),
        "decision_blocking": False,
        "qualification_applies": any(not r["passed"] for r in rows),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1, default=str))
    return artifact
