# Decision records

Short records of non-obvious architectural decisions: the context, the choice, and
the consequences, so the reasoning survives and the calls don't get relitigated.
Add a new file as `NNNN-short-title.md`, numbered in sequence, and list it below.

| # | Decision | Status |
|---|----------|--------|
| [0001](0001-structured-money-diff.md) | Diff a structured model of the bill, not document text | Accepted |
| [0002](0002-pdfium-single-engine.md) | Use pypdfium2 (PDFium) as the single PDF text engine | Accepted |
| [0003](0003-pdfjs-client-side-viability.md) | Client-side PDF.js extraction is viable for published bills | Accepted (spike finding) |
| [0004](0004-govinfo-bulk-data.md) | Fetch discovery and text from govinfo bulk data, not the Congress.gov API | Accepted as a decision; not yet implemented |
