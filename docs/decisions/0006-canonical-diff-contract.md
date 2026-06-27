# 6. Make a versioned JSON document the contract between the diff engine and its consumers

- Status: Accepted
- Date: 2026-06-27

## Context

A comparison of two bill versions has to travel from the diff engine to several
different consumers: BillTrax (the analysis product that uses DeltaTrack as its
diff engine), the HTML report, a future browser extension, a CSV/Markdown export,
a staffer's internal LLM tool (i.e., CoPilot), and possible third-party tooling. 
There are two input pipelines (XML and PDF) that must converge so consumers do 
not care which one produced a diff (see [0002](0002-pdfium-single-engine.md),
[0003](0003-pdfjs-client-side-viability.md)).

The shape of a single diff is specific. It is **binary** (exactly two versions,
`v1` and `v2`), **read-only**, **single-use** (produced, consumed once to render,
not mutated), and **scoped to one comparison**. It is a document, not a long-lived
queryable dataset.

The delivery constraint is hard: the primary report is a self-contained HTML file
that opens in any browser with no server and no install. We believe this is
the correct decision to limit IT and procurement limitations for staffers. The 
canonical payload is embedded inside that file and read back by the browser
to drive find, navigation, and the full-bill view.

What makes the choice non-obvious is that "how should a diff be represented" is
often discussed with "how should we store and query many diffs." Those are 
different layers, and the question that will recur — "why not a database ?" — 
lives at the second one.

## Decision

We will represent every diff as a **versioned, semantic JSON document** that is
the public contract between the engine and all consumers. Both pipelines emit this
shape (`xml_diff_to_canonical`, `pdf_diff_to_canonical` in `formatters/canonical.py`);
the renderers only read this shape and turn it into a view (`view_from_canonical`
→ the HTML renderer); they add no data of their own. The contract is semantic, not
presentational: it carries no pre-rendered HTML, and word-level inline diffs are
computed at render time. It is versioned with a `schema_version` field under an
additive-minor / breaking-major policy. The full shape is specified in
[schema/canonical-diff.md](../../schema/canonical-diff.md) and validated by
[schema/canonical-diff.schema.json](../../schema/canonical-diff.schema.json).

JSON is chosen for two plain reasons: a person can read it and every browser can 
read it directly, which is what lets the report embed its own data and work offline.

Alternatives:

- **Wire the engine straight to the report, with no standalone file.** The engine
  could pass its results directly to the HTML report, or produce finished HTML
  itself. Either way there is no separate artifact to hand to an LLM, feed a future
  browser extension, or give a third party, and the engine and the report stay
  locked together. The JSON file is what keeps them independent.
- **A database as the primary representation.** This is the "why not a database?"
  question. A database is built to store and query many records that change over
  time; a single diff is one fixed, read-only result, not a dataset. Requiring a
  database would also break the self-contained report, which has to run with no
  server. Storing and querying many diffs may matter later, but that would be a
  layer built on top of these documents, not a replacement for them (see
  Consequences).

## Consequences

- One renderer family serves both input pipelines and every output medium,
  because they all meet at this shape. This is the enabler for the single-renderer
  decision.
- The self-contained offline HTML report and the "hand the diff to an internal
  LLM as an attachment" use case both fall out for free: a semantic JSON document
  enables both.
- The document repeats some information on purpose — for example, the section
  number also appears in the breadcrumb path, and the full bill text is carried
  alongside the individual change fragments. That repetition keeps the file
  self-contained and is fine for a one-use artifact; it would be wasteful inside a
  database built to avoid duplication.
- The contract does not by itself answer questions that span many diffs, and that
  is deliberate. DeltaTrack stays the simple, local, offline engine that compares
  two versions; analyzing diffs over time, storing them, or running them through an
  LLM is BillTrax's job (see [0005](0005-deltatrack-billtrax-boundary.md)). This
  JSON is the boundary between the two: DeltaTrack produces it,
  BillTrax and any other consumer build on it. The per-comparison record of truth
  lives here; anything spanning many comparisons lives one layer up.
- Whether the format should ever grow beyond two versions is left open. The schema
  notes N-way comparison (more than two versions in one document) as a possible
  future v2.0 change, but cross-version analysis may belong in BillTrax while
  DeltaTrack stays strictly two-at-a-time. That call is not made here, and when it
  is, the question is the format's scope, not whether to keep JSON.
