# 21. Name things in the vocabulary an outside reader already speaks, scoped to the boundary being named

- Status: Accepted
- Date: 2026-08-08

## Context

This repository is read by people and agents who arrive with vocabulary already in hand:
congressional staff who know GPO and Congress terminology, engineers who know standard
software terms, and models trained broadly on both and not at all on this project. Its
output is financial and traceability-critical, so independent review is a design
requirement rather than a nicety. Every identifier that means something *different* here
from what those readers already expect is a silent mistranslation.

Naming is therefore an auditability concern, and the repository has already paid for
getting it wrong once: [ADR 0020](0020-matching-stages.md) found `reconcile_moves` to be
"a second retrieval pass, unnamed as such, running after classification." Recognizing and
naming that behaviour as a distinct stage made the responsibility possible to measure
independently, and the resulting probe found 496 recovered changes across 27 adjacent
version pairs of the committed corpus.

A research spike —
[docs/research/naming-architecture](../research/naming-architecture/README.md) — audited
the current state against normative sources over six revisions, four of which falsified or
narrowed the spike's own earlier conclusions. Three findings set up this record.

**Official vocabularies disagree with each other, by surface.** GPO's Bills XML Bulk Data
User Guide says there are "four types of legislation" and lists bills as one of them in
§1.1, then two pages later organizes the repository "by Congress, session, and **bill
type**" — where bill type includes `hjres`. The Congress `bill.dtd` declares
`bill-type (olc | traditional | appropriations) "olc"`, a drafting-style designator, while
the govinfo API returns `billType: "hjres"` for the same phrase. There is no institutional
ranking that resolves this, because one institution holds both meanings.

**Identifiers here already carry several meanings each.** `--format` means output
representation on `diff_bill.py compare` and input representation on
`fetch_bills.py download`; `source` means provider on the CLI and input representation in
the canonical contract's schema `enum`. `normalize_bill` calls `ET.parse`, then interprets,
extracts and transforms into `BillTree` — naming one step of a composite, and the step it
does not conventionally perform.

**A term proven authoritative for one interface does not settle another.** The spike
established `bill` as the umbrella in the govinfo acquisition register, then briefly
concluded it was therefore the umbrella for the product, CLI and canonical contract. That
was wrong, and the repository's own architecture is why:
[ADR 0016](0016-product-tooling-surface-split.md) separates the acquisition tooling from
the product, and [ADR 0006](0006-canonical-diff-contract.md) makes the canonical document
the contract for *all* consumers of a comparison — which may be two local files govinfo
never touched.

## Decision

We will treat naming as an architectural interface, governed by one principle:

> **Do not make an agent or human learn a DeltaTrack dialect before they can reason about
> DeltaTrack.** Where an authoritative vocabulary already exists for a concept, speak it.

### 1. Terminology authority by concept type

1. **Legislative and domain concepts** take the terminology of the authoritative
   institutional source that governs *that* concept and boundary — Congress, GPO/govinfo,
   the congressional XML specifications, the GPO Style Manual, GAO for budget terms.
2. **Technical concepts** take established software, data-processing and
   document-processing terminology where a conventional term exists.
3. **Project-specific concepts** may take new vocabulary, but only where the concept is
   genuinely specific to this architecture and neither of the above is adequate. A new term
   must be defined in one discoverable place.

We will not invent local synonyms for convenience. ADR 0020's stage vocabulary is the model
for a justified project-specific term: borrowed words, a genuinely new structure, defined
in the record that introduced it.

### 2. Authoritative vocabulary does not propagate across architectural boundaries

> A term proven authoritative for one register does not thereby become canonical for
> another. Authority must be established for the concept **at the boundary being named**.

Terminology established for the govinfo acquisition interface does not by itself decide
terminology for the Python API, the CLI, the pipeline-neutral canonical contract, future
package namespaces, MCP interfaces, or any other product-facing or composition boundary.
**This is a general rule, not a special exception for govinfo** — it binds equally to terms
taken from the DTDs, from CRS, or from any future source.

Where a value crosses registers, the translation is explicit rather than implied by a
shared word. A shared identifier spanning two meanings is not merely a naming blemish; it
is evidence of an undocumented boundary.

### 3. Naming conventions

- One canonical term per concept; one term does not carry several materially different
  meanings within a scope.
- Commands, modules, APIs, types and schema fields describe the job or concept they
  actually represent.
- Names normally use nouns for concepts, results and capabilities, and verbs for
  operations, unless established domain or technical usage calls for something else. A
  convention, not a taxonomy: it does not override authoritative terminology.
- User-facing jobs are distinguished from internal mechanisms.
- Input representation (PDF/XML) does not create a different public job where the user's
  intent and the operation's contract are the same. Implementations may differ, and the
  representation may stay visible where it implies different guarantees, supported
  operations, failure modes or semantics.
- Input representation, output representation, operation, result, and provider/origin are
  distinct concepts and do not share an ambiguous identifier.
- The same conceptual vocabulary is used across Python, CLI, MCP, docs and UI where those
  surfaces represent the same concept. Semantic consistency, not identical strings —
  each surface keeps its own casing and separator conventions.
- Prefer explicit, conventional, independently understandable names over clever or
  project-local shorthand.

Conventional meanings are respected for `fetch`, `parse`, `extract`, `normalize`, `match`,
`serialize`, `render` and `validate`. Two distinctions the spike supports well enough to
record: **`compare` is the operation** of evaluating two representations to determine
change, and **`diff` is the resulting difference artifact** rather than a synonym for the
whole pipeline; and **`parse` and `extract` are not interchangeable** — XML arrives with
explicit markup governed by a DTD, while PDF arrives as presentation-oriented content from
which structure must be recovered by deterministic heuristics
([ADR 0008](0008-deterministic-engine.md), [ADR 0002](0002-pdfium-single-engine.md)).
Consistency does not override technical accuracy: two things share a name only when they
are the same concept.

### 4. Discovery and auditability are design objectives

Repository layout, CLI `--help`, public API names and any future MCP tool catalog are
**discovery interfaces**. A technically competent reviewer who has never seen this project
should be able to infer, from names, location, signatures, contracts and documentation:
responsibilities, inputs and outputs, transformations, where heuristics begin, which
contracts are stable, and where correctness can degrade — without first learning private
vocabulary.

Two review tests:

> If an experienced external practitioner or capable agent saw this name without DeltaTrack
> context, what would they reasonably expect it to mean or do?

> Is this the term they would naturally search for when looking for this concept?

A mismatch is evidence that the name or responsibility boundary may need investigation;
authoritative domain or technical usage remains controlling where it applies. An outsider's
expectation can itself be wrong, or be drawn from a different register.

Generic buckets (`core`, `helpers`, `utils`, `common`, `services`) may group internal
implementation but must not become public architectural boundaries merely for convenience.
A private, conventionally-named utility module is fine; the concern is whether an outsider
must reverse-engineer implementation buckets to find a capability.

**If a component's name suggests one responsibility but it performs several materially
distinct stages, treat that as a possible architecture defect rather than only a naming
problem.** That is what ADR 0020 found, and it is the reason this section exists.

### 5. Brand boundary

> Products get brands. Components get domain names.

Brand names may identify the product, the repository, the distribution and the user-facing
application. They may not define reusable architectural boundaries or APIs. The existing
`deltatrack` namespace is **grandfathered**; this record prevents *new* architectural
dependence on the product brand without forcing a cosmetic migration now.

Product identity may appear in metadata such as `generator.name`. Downstream consumers must
not use a brand string as a compatibility, protocol, dispatch or schema discriminator when
a stable contract identifier exists: for the canonical format that identifier is
`schema_version` ([ADR 0006](0006-canonical-diff-contract.md)), and `generator.name` is
product identity that may change under a future rebrand. Because "consumers must not" is
unenforceable against a consumer never told, the contract must say so where it is defined.

### Alternatives considered

- **Rank the institutions** (Congress → GPO → Style Manual). Rejected: `bill` is the
  umbrella in govinfo's register and one of four forms in CRS's, so a ranking makes the
  same word wrong or right by fiat rather than by scope.
- **Adopt one project glossary and normalize everything to it.** Rejected: it is the
  dialect the governing principle forbids, and it would erase distinctions the authorities
  make.
- **Freeze an exhaustive naming-role taxonomy.** Rejected: the spike falsified a four-role
  version on measures and thresholds, and a taxonomy is itself vocabulary contributors must
  learn.
- **Rename the offending identifiers now.** Rejected as out of scope; see non-decisions.

## Non-decisions

This record deliberately does not decide, and must not be read as deciding:

- **The umbrella term for the substantive comparison domain.** `bill` is established as
  authoritative *within the govinfo acquisition context* covering its eight measure types.
  It is not thereby established for the product domain, Python API, CLI, canonical
  contract, future namespace or MCP interface. `bill`, `measure` and terms not yet
  considered all remain open. That question belongs to the canonical-contract architecture
  governed by [ADR 0006](0006-canonical-diff-contract.md), and requires a future decision
  if the current contract vocabulary is changed.
- **Whether the canonical contract's `bill.type` is correct.** The spike established
  authoritative precedent for its current values in the govinfo register and therefore
  falsified the claim that it is defective. It did not establish which register should
  govern that field in a pipeline-neutral contract. That question likewise belongs to the
  canonical-contract architecture governed by ADR 0006, and requires a future decision if
  the current contract vocabulary is changed. This record neither endorses `bill.type` as
  the final term nor calls for its replacement.
- **Any rename**, of the `deltatrack` namespace or anything else.
- **A successor product name or package namespace.**
- **A migration strategy** (atomic rename versus compatibility shim). To be decided if and
  when a rename is undertaken, against the consumer graph as it stands then.
- **A package split or layout.**
- **A user-job taxonomy**, exact CLI syntax, or MCP tool names and protocol design.
- **A legislative glossary.** Terms are adopted from authorities as needed, not enumerated
  here in advance.

## Consequences

- New technical interfaces must name their concepts against the authority governing the
  boundary they sit on, and record which authority that is when it is not obvious. This is
  a small tax at design time and the whole benefit at review time.
- **Parts of the current surface do not comply, and this record does not schedule their
  repair.** Per `README.md` in this directory, a record's status describes the standing of
  the decision, not whether it has been built. The known non-compliance: `./diff_bill.py`
  and `./diff_pdf.py` present one user intent as two commands selected by input
  representation, with different grammars (one takes a `compare` subcommand, the other does
  not) — the clearest case against §3's rule, and the web API already does it the other way
  via one `/api/compare` with the representation as a parameter. Alongside it: `--format`
  and `source` overloading, `normalize_bill` naming one step of a composite,
  `version_number` colliding with govinfo's `billVersion`, and `bill` carrying both the
  acquisition umbrella and the `<bill>` document type. Each sits on a surface governed by
  another record — the canonical contract under ADR 0006, version identity under ADR 0013 —
  and changing any of them needs its own future decision. None is licensed by this record
  alone.
- Some name changes will look like churn to a reader who has learned the current
  vocabulary. That cost is accepted: the audience this record optimizes for is the reader
  who has not.
- The authorities themselves are not perfectly consistent, so this record cannot promise
  one term per concept globally — only within a scope, with explicit translation at the
  boundaries. `res.dtd`'s `resolution-type` mixes measure category with drafting form in a
  single official attribute; we mirror the authority rather than silently improving it.
- **Enforcement is partial and stays that way for now.** A vocabulary gate exists for
  ADR 0018 (`tests/test_structure_vocabulary_gate.py`) and demonstrates the pattern:
  coverage by subtraction, plus a test proving the detector can fire. A glossary-membership
  gate cannot be built until a glossary exists. What is buildable now is narrower — one
  meaning per public flag name across surfaces, and consistent CLI grammar — and is left as
  follow-up rather than required here.
- Reviewers gain a stated basis for a naming objection, which previously rested on taste.

## References

- Research spike: [docs/research/naming-architecture](../research/naming-architecture/README.md)
- [ADR 0006](0006-canonical-diff-contract.md) — the canonical contract and `schema_version`. It governs the architecture in which the domain-vocabulary question this record defers would be settled; settling it needs a future decision, not an edit to 0006
- [ADR 0016](0016-product-tooling-surface-split.md) — the product / tooling / delivery split that makes acquisition a distinct register
- [ADR 0019](0019-observation-identity.md) and [ADR 0020](0020-matching-stages.md) — vocabulary established by narrower records, authoritative within their own scope and not reopened here
- [ADR 0018](0018-text-triggers-are-financial-only.md) — the existing vocabulary gate and the enforcement pattern
- [ADR 0008](0008-deterministic-engine.md), [ADR 0002](0002-pdfium-single-engine.md) — the determinism and extraction facts behind the `parse` / `extract` distinction
