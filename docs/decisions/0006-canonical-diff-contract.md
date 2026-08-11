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

Every diff is a **versioned, semantic JSON document** that is the public contract
between the engine and all consumers. Both pipelines emit this shape
(`xml_diff_to_canonical`, `pdf_diff_to_canonical` in `formatters/canonical.py`).
The full field shape is specified in
[schema/canonical-diff.md](../../schema/canonical-diff.md) and enforced by
[schema/canonical-diff.schema.json](../../schema/canonical-diff.schema.json), which
this record does not restate.

JSON is chosen for two plain reasons: a person can read it and every browser can
read it directly, which is what lets the report embed its own data and work offline.

### Producer and consumer responsibilities

**The canonical artifact holds the semantic facts.** Consumer and view layers may
*derive* presentation data from those facts — headings, navigation labels, citations,
inline word-level diffs, HTML — but they do not add new semantic diff facts, and none
of that derived material belongs in the document. `view_from_canonical` is therefore
not a field-for-field projection: it composes presentation from the contract. The
contract itself stays presentational-free, which is what lets one renderer family
serve both pipelines and every output medium ([0007](0007-single-renderer.md)).

Producers are expected to emit schema-valid documents and are tested against the
schema. The schema defines validity; the DeltaTrack reader carries explicit
compatibility guards but is not a general schema validator, so "invalid" is a
statement about the schema, not a promise that every reader will reject it.

### The money contract

A `Change` carries exactly one exported money field, `amount_entries`.

- **Required, not merely sole.** These are two distinct guarantees. Being the only
  money field prevents ambiguity about which field to read; being *required* lets a
  consumer distinguish "this change has no money entries" (an empty array) from "this
  document does not satisfy the contract" (the field absent). An optional-and-sole
  field would collapse those two into one silence.
- **The obsolete changed-only money field is absent from the contract**, rather than
  retained beside `amount_entries` with prose declaring a winner. Two plausible
  machine-readable authorities for the same concept, one of them structurally
  incomplete, is a correctness bug rather than untidiness: the report ships prompts
  telling a staffer to hand `diff.json` to an AI assistant, and a machine holding only
  the exported artifact cannot read this repository's documentation to learn which
  field wins. Reading the incomplete one would answer questions about a bill's
  appropriations while seeing a fraction of them — confidently, with every newly
  funded or wholly defunded program invisible, and those are usually the changes a
  staffer most wants. The schema forbids the legacy field outright.
- **Entries are self-describing**, distinguishing `changed`, `added` and `removed`, and
  an absent side is represented explicitly as null. The schema is the exhaustive
  authority for the exact shape.
- **One-sided changes stay representable on the money axis.** A producer may not omit
  money from a change merely because one side is absent: a wholly added or wholly
  removed item is exactly the case a money-aware consumer most needs, so the pipelines
  extract against the empty side rather than emitting nothing.
- **Canonicalization does not perform value-symmetric cancellation.** An `added` and a
  `removed` entry are not collapsed merely because their values are equal. On a
  renumbered list the pairing emits a shuffled item's identical value as a net-zero
  added/removed pair, and distinguishing that from two genuinely distinct equal-value
  items needs within-list content alignment the producer does not have. So the producer
  reports the changed/added/removed entries the pairing semantics emit, and richer
  alignment — or presentation-side collapse — is downstream policy. (This is narrower
  than "every raw pair survives": a pair whose sides are equal is not a change and is
  dropped.)

This concerns the *extraction and representation* of money, not its interpretation.
Reading appropriations language for meaning is out of scope here and bounded by
[0018](0018-text-triggers-are-financial-only.md).

### Compatibility

The serialized contract carries a required `schema_version` under an
**additive-minor / breaking-major** policy. Compatible revisions stay within a major.
A consumer claiming support for this contract must **reject an unsupported major**
rather than silently interpreting it as the current shape — the failure that rule
exists to prevent is a document from an older major parsing cleanly and reading as
having no money anywhere.

A removed or required contract property is **tested in the rejection direction**.
Validating producer output only proves the producer is well behaved: if the schema
itself lost a constraint, every producer-output test would stay green while a removed
field became legal again. The rejection is asserted directly, alongside a positive
case so the probe cannot pass by rejecting everything.

## Alternatives

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
  layer built on top of these documents, not a replacement for them.

## Consequences

- One renderer family serves both input pipelines and every output medium, because
  they all meet at this shape. This is the enabler for the single-renderer decision.
- The self-contained offline HTML report and the "hand the diff to an internal LLM as
  an attachment" use case both fall out for free.
- The document repeats some information on purpose — the section number also appears
  in the breadcrumb path, and the full bill text is carried alongside the individual
  change fragments. That repetition keeps the file self-contained and is fine for a
  one-use artifact; it would be wasteful inside a database built to avoid duplication.
- The contract does not by itself answer questions that span many diffs, and that is
  deliberate. DeltaTrack stays the simple, local, offline engine that compares two
  versions; analyzing diffs over time, storing them, or running them through an LLM is
  BillTrax's job ([0005](0005-deltatrack-billtrax-boundary.md)). This JSON is the
  boundary between the two: the per-comparison record of truth lives here, anything
  spanning many comparisons lives one layer up.

Two format questions are open, and they are separate:

- **More than two bill versions in one document.** The schema notes N-way comparison
  as a possible future major break, but cross-version analysis may belong in BillTrax
  while DeltaTrack stays strictly two-at-a-time. Undecided; when it is decided, the
  question is the format's scope, not whether to keep JSON.
- **Grouping binary changes that come from one non-binary correspondence.** A `Change`
  is a binary row, so a 1:N or N:1 correspondence has no faithful representation;
  [0020](0020-matching-stages.md) deliberately degrades it into binary rows, which
  keeps every amount counted once. Whether this contract should grow a grouping field
  is undecided and needs a demonstrated consumer.
