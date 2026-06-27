# Decision records

This directory holds Architecture Decision Records (ADRs): short, numbered notes
that capture a non-obvious choice, why it was made, and what follows from it. They
keep the reasoning from being lost and stop settled questions from being
relitigated.

## How to propose a decision

1. Copy [TEMPLATE.md](TEMPLATE.md) to `NNNN-short-title.md`, using the next free
   number (zero-padded, sequential, never reused).
2. Fill in Context / Decision / Consequences and set `Status: Proposed`.
3. Open a pull request. The decision is discussed and approved on the PR.
4. On approval a maintainer changes the status to `Accepted` and merges.

## Rules that keep the log trustworthy

- **One decision per file.**
- **Append-only.** Once a record is accepted, its substance is not edited. Numbers
  are never reused and records are not deleted.
- **Supersede, do not overwrite.** To change a past decision, write a new record
  that replaces it: set the old one to `Superseded by NNNN`, and note
  `Supersedes MMMM` in the new one. The old record stays as history.
- **Decision status, not implementation status.** A record's status describes the
  standing of the *decision*, not whether it has been built. Implementation
  progress lives in the issue tracker, so an accepted but unbuilt decision links to
  its tracking issue rather than inventing a status for it.

## Status values

| Status | Meaning |
|--------|---------|
| Proposed | Drafted and under review; not yet agreed. |
| Accepted | Agreed and in effect; the choice the project currently follows. |
| Superseded by NNNN | Replaced by a later decision; kept for history. |
| Deprecated | No longer applies, with no direct replacement. |
| Rejected | Considered and decided against; kept to record why not. |

## Records

| # | Decision |
|---|----------|
| [0001](0001-structured-money-diff.md) | Diff a structured model of the bill, not document text |
| [0002](0002-pdfium-single-engine.md) | Use pypdfium2 (PDFium) as the single PDF text engine |
| [0003](0003-pdfjs-client-side-viability.md) | Client-side PDF.js extraction is viable for published bills |
| [0004](0004-govinfo-bulk-data.md) | Fetch discovery and text from govinfo bulk data, not the Congress.gov API |
| [0005](0005-deltatrack-billtrax-boundary.md) | Keep DeltaTrack a contained two-version tool; put analysis in BillTrax |
| [0006](0006-canonical-diff-contract.md) | Make a versioned JSON document the contract between the diff engine and its consumers |
