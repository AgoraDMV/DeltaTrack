# 2. Use pypdfium2 (PDFium) as the single PDF text engine

- Status: Accepted
- Date: 2026-06-27

## Context

Many bills reach us only as PDF: pre-introduction drafts have no XML upstream, and
Senate prints and committee reports are PDF-first. Text extraction quality
therefore sets a ceiling on the whole diff for those documents.

The original extractor used pdfplumber (pdfminer.six). Two problems made it the
wrong foundation:

1. It dislocated the section-heading line numbers. Changes then landed in
   unanchored, page-spanning blobs instead of the small, citeable hunks a reader
   can locate in the published bill. This works directly against the
   navigate / find / verify goal of the diff.
2. It leaked page chrome (watermark and footer text) into section bodies, so the
   diff would flag boilerplate as substantive change.

Committee-report tables were also read out of order under pdfplumber.

## Decision

Extract PDF text with **pypdfium2** (the Python binding for PDFium, the PDF engine
in Chrome) as the *single* engine. Remove pdfplumber and pdfminer.six.

A normalization layer (`normalize_raw` + `strip_page_chrome`) handles PDFium's own
raw-text quirks: CRLF endings, soft-hyphen plus glued margin numbers, the
top-floated bullet-HR header, and page-boundary hyphens that glue VerDate /
watermark chrome onto body text. The downstream pipeline (`parse_lines` onward) is
unchanged.

Before removing pdfplumber, we verified pypdfium2 against it on the full corpus:
99.93% numbered-line parity, with the diffs that *did* differ being improvements,
not regressions. pypdfium2 recovers the heading line numbers pdfplumber
dislocates, and it stops leaking watermark/footer text into bodies. The migration
shipped in PRs #38 and #40.

## Consequences

- The diff lands in anchored, citeable hunks for PDF-sourced bills, which is the
  point of extraction quality for this tool.
- One engine instead of two means one set of text quirks to understand and one
  cleaning path to maintain, at the cost of that path being PDFium-specific.
- The engine-vs-engine parity check could not survive pdfplumber's removal, so the
  regression guard is now a golden snapshot: five curated pages, each exercising
  one cleaner path (soft-hyphen reconstruction, VerDate-glue, watermark-glue,
  title-page join, watermarked committee-report table read forward). Regenerate
  intentionally with `UPDATE_GOLDEN=1`.
- PDFium ships as self-contained, permissively licensed (BSD-3 / Apache-2.0)
  wheels with no system libraries to install. That matters for an audience under
  strict IT constraints, where "pip install pulls a system dependency" can block
  adoption.
- This decision covers server-side extraction in Python. A separate spike found
  that a different engine (Mozilla's PDF.js) reproduces the extraction in the
  browser at high parity, which keeps a no-Python delivery channel open. That
  finding is recorded in [ADR 3](0003-pdfjs-client-side-viability.md).
