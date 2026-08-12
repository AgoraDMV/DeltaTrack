# Naming architecture: authoritative vocabulary, discoverability, and rebrand resilience

A research spike on how this repository names things: whether product branding is
entangled with technical identity, and whether an unfamiliar human or agent can infer
capabilities and interfaces from the names alone.

**This is the spike, not the decision.** It records evidence and recommends what an ADR
should and should not freeze; it deliberately argues against several of its own proposals
(§7) rather than presenting a settled scheme. It binds nothing on its own.

The decision drawn from it is
[ADR 0021](../../decisions/0021-naming-authority-and-boundaries.md), proposed separately so
that the evidence and the decision can be reviewed apart. **The ADR is the binding record;
where the two differ, the ADR governs.** Recommendations below are inputs to that decision,
not the decision — several were narrowed or dropped before it was written.

**Status:** audit only. No code or configuration changes accompany this report.
**Revision 6.** A scoping correction. Rev. 5 read the normative sources (§1.0, §10),
overturned one of this report's own claims and falsified two of its criticisms — then
overextended the govinfo result by letting an *acquisition-register* fact govern the
product, CLI and contract layers. Rev. 6 narrows that to what the evidence supports and
promotes the corollary to a first-class finding: **authoritative vocabulary does not
propagate across architectural boundaries** (§1.1.1). Sections changed: §1.1, §1.2, §1.6,
§1.7, §1.8, §7.5, §9. Everything else stands.
**Repo state audited:** `spike/pdf-seam-external-validity` @ `df90e6e`.

---

## 0. The governing principle

> **Do not make an agent or human learn a DeltaTrack dialect before they can reason about DeltaTrack.**

Adopted as the primary naming principle, with one correction argued in §7.1: it must read
*unnecessary or undocumented* dialect, not *any* dialect. As an absolute it would indict
ADR 0020, which deliberately and correctly introduced project-specific stage vocabulary.

This reframes naming as an **auditability and interface-semantics concern**. The
repository is plausibly read by someone with deep legislative expertise and no software
context, or by an agent trained broadly on Congress and GPO material and not at all on this
project. Both bring vocabulary with them. Every place our identifiers mean something
*different* from what those readers already know is a silent mistranslation, and silent
mistranslation in a tool whose output is financial and traceability-critical is the failure
mode worth spending on.

---

## 1. Vocabulary authority

### 1.0 Evidence classes, and what each can support

| Class | What it is | Can establish | Cannot |
|---|---|---|---|
| **A — Normative authority** | The specification, DTD, data dictionary, glossary, or official documentation that *defines* a term | What a term officially means | — |
| **B — Observed official examples** | Values and structures in official documents in this repository's corpus | That a value or shape **exists**, and that the engine must handle it | Prevalence; the meaning of a term where class A exists |
| **C — Repository behaviour** | How this codebase names or processes a concept | What DeltaTrack currently does | Anything about what is correct |

Rev. 4 could cite no class-A source. Rev. 5 reads seven; §10 lists them with what each
settled and what remains unreachable.

#### What the committed corpus is, and is not

`tests/corpus/` holds 58 XML documents across 26 directories — genuine GPO artifacts,
byte-identical to what govinfo published (ADR 0015). It is also a **purposive,
appropriations-heavy sample** assembled for this project's own testing needs. Every
directory is `hr` or `s`; no resolution of any kind is present; one amendment shape
appears. It is not representative of congressional measures.

> `bill-type="appropriations"` on 24 of 58 documents establishes that the value **occurs**.
> It does not establish that ~41% of measures carry it — on an appropriations-selected
> corpus that proportion largely restates the selection criterion.

> 10 of 58 being `DOCTYPE amendment-doc` proves the corpus **contains** amendment documents
> and the code must handle them. It says nothing about their frequency in congressional
> publishing.

### 1.1 Authority is scoped to a concept *and a representation*

Not a ranking of institutions. The evidence forces this: **the same institution uses one
term for different concepts on different surfaces**, and in one case within a single
document.

| Concept and representation | Normative authority | Class |
|---|---|---|
| Package, path and metadata terminology for the data this project consumes | **govinfo API and bulk data** | A |
| Bill/amendment/resolution XML attribute and element semantics | **Congress `bill.dtd` / `res.dtd` / `amend.dtd`** | A |
| Substantive taxonomy of legislative business | **CRS / Congress** | A |
| Publishing and typography | GPO stylesheet and Style Manual | A (already used) |
| Appropriations and budget terms | GAO-05-734SP | A (already cited at `bill-structure.md:147`) |
| Drafting-form subdivision ladder | HOLC | already cited at `AGENTS.md:115` |
| Deliberately-defined project concepts | The narrower ADR that defined them | — |

The repository already practised the bottom four, unstated. What rev. 5 adds is the top
two, and the identification of the **govinfo acquisition register** as the authority for
the concepts this project *fetches* — which is what resolves §1.2 and §1.6, and only
those.

#### 1.1.1 Authority does not propagate across architectural boundaries

The corollary matters more than the table, and rev. 5 got it wrong by omission: having
established that govinfo governs acquisition vocabulary, it let that conclusion travel
into the product, CLI and contract layers on the strength of the system merely being
connected to govinfo.

> **Do not allow terminology from one authoritative register to leak into another merely
> because the system connects them. At a boundary between registers, name each side
> according to the authority governing that side, and make the translation explicit.**

The repository already draws this boundary architecturally, which is what makes the
overreach visible. [ADR 0016](../../decisions/0016-product-tooling-surface-split.md)
separates the acquisition tooling from the product; `compare/` is the product surface and
has no acquisition responsibility; and the canonical diff contract
([ADR 0006](../../decisions/0006-canonical-diff-contract.md)) is **pipeline-neutral** — it
describes a comparison of two documents, which may be local XML or PDF files that govinfo
never touched. An engine that can run with no network and no govinfo package does not
automatically inherit govinfo's nouns.

Four live boundaries where a translation is currently implicit:

| Boundary | Left register | Right register |
|---|---|---|
| Acquisition ↔ engine domain | govinfo package metadata | product/domain model |
| Package metadata ↔ document content | govinfo `billType` | Congress XML `bill-type` (§1.2) |
| Document type ↔ measure category | `<bill>` / `<resolution>` / `<amendment-doc>` | bill / joint resolution / … |
| govinfo bill version ↔ local ordinal | `billVersion: "ih"` | `version_number: 1` (§1.3) |

Each is a place where one identifier currently spans two meanings, or where a value
crosses a register with no recorded translation.

### 1.2 "Bill type": three official meanings, and no demonstrated defect

*Class A throughout.*

**Congress DTD — a drafting-style designator.** Verbatim from `bill.dtd`:

```
bill-type (olc | traditional | appropriations) "olc"
```

Enumerated, defaulting to `olc` (Office of the Legislative Counsel). The DTD changelog ties
these values to the `style` and `section-style` attributes — "the values should be olc,
traditional, and usc"; "Added the value 'appropriations' to the style attribute values." It
is a *drafting form*, not a measure category. **No source was found contradicting this.**

**govinfo — the measure category.** The API package summary for `BILLS-118hjres1ih`, a House
joint resolution, returns live:

```
billType: "hjres"   billVersion: "ih"   docClass: "hjres"
collectionName: "Congressional Bills"   category: "Bills and Statutes"
```

**GPO BILLSUM — the same category, under a different name.** The Bill Summaries bulk-data
guide uses `@measure-type` ("The type of measure"), `@measure-number`, `@measure-id`, and
defines `<item>` as "Parent container for a single legislative measure." It adds:

> "@measure-number — The number associated with the measure. **This is commonly referred to
> as the bill number.**"

GPO itself marks "measure" as the formal term and "bill number" as the colloquial one.

**Resolution: the original criticism is falsified, without an endorsement replacing it.**
Rev. 4 made the canonical contract's `bill.type` the motivating problem case. **The spike
has not demonstrated that it is a defect.** Its values align with govinfo's `billType`,
`hjres` included, so it has authoritative precedent and cannot be condemned merely because
the Congress XML DTD uses `bill-type` for something else.

That is as far as the evidence reaches. Rev. 5 went further and said govinfo "is the
register the field describes" — **withdrawn**. The canonical contract is pipeline-neutral
(§1.1.1): it can describe a comparison of two local files with no govinfo package behind
them, so the field does not inherently name a govinfo artifact. Whether the contract
*should* ultimately use this term is a domain-vocabulary question owned by
[ADR 0006](../../decisions/0006-canonical-diff-contract.md), and **ADR 0021 should not
decide it**.

The collision with the DTD's `bill-type` is real, and it is between two *official*
vocabularies. DeltaTrack did not create it. What the episode establishes is the rule, not a
bug:

> Where official vocabularies differ by scope, an unqualified identifier does not merely
> risk ambiguity — it guarantees that some correct reader resolves it wrongly.

### 1.3 Version identity: four notions, and the repository is already consistent

*Class A for the first three.*

| Notion | Where | Example |
|---|---|---|
| govinfo **bill version** | API `billVersion`; filename suffix; help page: "Version of the bill. Corresponds to a step in the legislative process" | `ih` |
| Congress DTD **bill-stage** | `#REQUIRED` attribute, 50 enumerated values | `Introduced-in-House` |
| Congress.gov BILLSTATUS `textVersions.type` | A third spelling; the repo already patches "Reported to Senate" → `rs` at `fetch_govinfo.py:164-174` | `Reported in House` |
| DeltaTrack **per-bill ordinal** | ADR 0013; contract `version_number` | `1` |

**Measured overlap between the two closed official vocabularies:** 50 DTD `bill-stage`
values against 53 govinfo version names; **37 match after normalization**, 13 DTD-only, 16
govinfo-only. Most divergences are spelling (`Engrossed-in-House` vs `Engrossed (House)`;
`Enrolled-Bill` vs `Enrolled`; `Referred-w-Amendments` vs `Referred with Amendments`).
Genuinely DTD-only: `Pre-Introduction`. Genuinely govinfo-only: `Public Print`, `Printed as
Passed`, `Previous Action Vitiated`, `Engrossed and Deemed Passed by House`, `Returned to
House by Unanimous Consent`, `Ordered to be Printed with House Amendment`. **Neither is a
subset of the other, and no source claims primacy for either.**

*Method caveat.* The first comparison returned "0 shared" (BSD `sed` lacks `\+`) and the
second placed `sponsor change` in both exclusive lists (CRLF from the DTD). Only the third
run is trustworthy. Recorded because "0 shared" would have read as a dramatic finding.

**Second correction in the repository's favour.** Rev. 4 noted that `bill-stage` "is read
nowhere" as though that were an oversight. It is not. The repo derives `label` from the
filename stem, which carries govinfo's version vocabulary — so the pipeline stays inside
**one** official register end to end. Reading `bill-stage` instead would switch registers
mid-pipeline between two sets that overlap on only 37 of 50 values.

**What survives as a genuine defect: `version_number`.** In govinfo's vocabulary the "bill
version" of `BILLS-118hjres1ih` is `ih`. DeltaTrack's `version_number: 1` is a per-bill
chronological ordinal — a different concept wearing govinfo's word, in the published
contract. ADR 0013's ordinal is justified (stage codes do not sort); the *name* is the
problem. This is now the clearest vocabulary defect in the repository.

### 1.4 Three document types, three DTDs — and one untested branch

*Class A and B.*

govinfo's BILLS collection carries three distinct document types, each with its own
Congress DTD, root element, and attribute vocabulary:

| DTD | Root | Category attribute | Stage attribute |
|---|---|---|---|
| `bill.dtd` | `<bill>` | `bill-type` (drafting style) | `bill-stage` |
| `res.dtd` | `<resolution>` | `resolution-type` | `resolution-stage` |
| `amend.dtd` | `<amendment-doc>` | `amend-type`, `amend-degree` | — |

The corpus holds 48 `bill` and 10 `amendment-doc` roots — and **zero `resolution`
documents**, because every corpus directory is `hr` or `s`.

`bill_tree.find_bill_body` is documented as handling "a bill, resolution or amendment-doc
root" (`bill_tree.py:142`). **The `resolution` branch therefore has no corpus coverage at
all.** That is a testing gap, findable only once the three document types are named
separately, and it is a concrete instance of the report's thesis: the vocabulary collapse
and the coverage gap are the same blind spot.

Note also that `resolution-type` enumerates `house-joint | senate-concurrent | …` (measure
category) *mixed with* `standard | OLC-form | impeachment | order-of-business |
constitutional-amendment` (form and purpose). **One official attribute, two concepts.** Any
"one term, one meaning" rule must acknowledge that the authorities do not always obey it.

### 1.5 Legislative and technical vocabularies coexisting correctly

`changes[]` in the canonical contract are observed differences between two texts. An
*amendment* is the legislative instrument that effects a difference. Different concepts,
correctly given different words — `change` and `diff` being established *technical*
vocabulary rather than project inventions. Nothing currently states the distinction, which
is the only gap.

### 1.6 The umbrella: verified for the govinfo acquisition register, and only there

*Class A. This section replaces a rev. 4 claim that was false.*

**Rev. 4 asserted that `bill` is the umbrella in the document-XML surface. That is wrong**,
and the disproof is a single primary artifact: `BILLS-118hjres1ih.xml` opens

```
<!DOCTYPE resolution PUBLIC "-//US Congress//DTDs/res.dtd//EN" "res.dtd">
<resolution resolution-stage="Introduced-in-House" resolution-type="house-joint" …>
```

At the document level a joint resolution is **not** a bill; there are three sibling
document types and no umbrella element at all.

The substantive authorities agree. CRS R46603 (27 Aug 2025): "In each chamber of Congress,
**four forms of legislative measures** may be introduced … bills, joint resolutions,
concurrent resolutions, and resolutions of one house." GPO's own BILLS XML User Guide §1.1,
"Types of Legislation," lists bills as one of four.

**And yet "bill" is unambiguously the umbrella in the govinfo acquisition register**, at
every level of it:

- govinfo API: `billType: "hjres"`, `collectionName: "Congressional Bills"`
- bulk data: `/BILLS/118/1/hjres/BILLS-118hjres1ih.xml`
- govinfo BILLS help: "bill type", "Bill Version"
- GPO's BILLS User Guide §1.3 — **two pages after** its "four types of legislation" — "The
  Bulk Data repository is organized by Congress, session, and **bill type**."

One official document using both meanings, two pages apart, is the strongest available
evidence that the register, not the institution, is what has to be named.

**What is established, and what is not.**

> **`bill` is verified as the umbrella term in the govinfo acquisition / data-access
> register**, covering all eight measure types. That fact is freezable.

It does **not** follow that `bill` is the canonical umbrella for the product domain, the
public Python API, the CLI, the pipeline-neutral canonical contract, a future package
namespace, or an MCP interface. Rev. 5 made that leap; §1.1.1 is why it does not hold.
Those surfaces expose concepts the acquisition register does not govern, and each must be
evaluated against the authority governing the concept *it* exposes. The candidates include
`bill`, `measure`, and terms not yet considered; the dissenting sources on the substantive
side are real (CRS's "four forms of legislative measures"; GPO's own §1.1; the BILLSUM
model's `@measure-type`, `@measure-number`, `@measure-id`), and they are not answered by
the acquisition evidence.

**This is not a reason to rename anything now.** It is a reason for ADR 0021 to prohibit
*accidental* propagation: the term may well end up being `bill` on several of those
surfaces, but that should be a decision made against each surface's own authority rather
than an inheritance nobody examined.

**The containment requirement, meanwhile, is live today.** Inside the repository `bill`
already carries two meanings, and both have authoritative backing: the umbrella in the
acquisition tooling and the fetch paths; the specific `<bill>` root at the parsing layer,
distinct from `<resolution>` and `<amendment-doc>`. The collision point is `normalize_bill`
/ `BillTree` / `BillNode` / `find_bill_body` — code that handles all three root types while
using the specific word for the general job. The containing rule: **where the code
distinguishes document types, the DTD root element names govern; where it addresses govinfo
packages, govinfo's vocabulary governs; and the translation between them should be
explicit rather than implied by a shared word.**

### 1.7 An unrelated data-quality finding, recorded because it is actionable

Both official "is this appropriations?" signals are **wrong** on the largest appropriations
act in the corpus. For `115-hr-1625` (enrolled):

| Signal | Value | Class |
|---|---|---|
| govinfo API `isAppropriation` | `"false"` | A, live |
| Congress DTD `bill-type` | `"olc"` — not `"appropriations"` | B, corpus |
| The document itself | "Consolidated Appropriations Act, 2018", **823** `appropriations-*` elements | B, corpus |

**Neither signal is sufficient on its own to determine whether the legislative text
DeltaTrack is processing contains appropriations content.** One counterexample is enough to
establish that, because it shows the signals can disagree with the document in the
direction that matters here — a false negative on an omnibus appropriations act. It does
**not** establish that the signals are useless for every filtering or metadata purpose, nor
how often they are wrong.

A plausible mechanism, consistent with both values but not established by a single case: on
this document each signal reflects the original measure rather than what the legislative
vehicle became, and shell vehicles are a known route for omnibus appropriations. Testing
that would need a sample designed for it — which the committed corpus, being
appropriations-selected, is not.

This independently supports
[ADR 0018](../../decisions/0018-text-triggers-are-financial-only.md): content
classification must not be inferred from such signals. Out of scope for a naming ADR;
recorded so the finding is not lost.

### 1.8 Claims corrected across revisions

| Claim | Disposition |
|---|---|
| "The corpus is the authoritative source" | **Withdrawn** (rev. 4) — class-B observation from a purposive sample |
| Corpus proportions as population facts | **Withdrawn** (rev. 4) |
| "`bill` is the umbrella in the document-XML surface" | **False** (rev. 5) — `res.dtd` / `<resolution>` disproves it (§1.6) |
| "`bill.type` collides with GPO's" (as a DeltaTrack defect) | **Falsified** (rev. 5) — authoritative precedent in govinfo; not shown to be a defect (§1.2) |
| "govinfo is the register the `bill.type` field describes" | **Withdrawn** (rev. 6) — the contract is pipeline-neutral; this over-endorsed after correctly falsifying the criticism (§1.2) |
| "`bill` is the canonical umbrella for the product/CLI/contract" | **Narrowed** (rev. 6) — verified for the govinfo acquisition register only; other surfaces undecided (§1.6) |
| "Neither signal is usable as an appropriations filter" | **Narrowed** (rev. 6) — one counterexample shows insufficiency, not uselessness (§1.7) |
| "`bill-stage` is read nowhere" (as an oversight) | **Reversed** (rev. 5) — staying in one register is the better choice (§1.3) |
| "GPO's `bill-type` *is* the drafting style" | **Upgraded** (rev. 5) from inference to class-A proof (§1.2) |
| "`bill-stage` is the authoritative version identifier" | **Withdrawn** (rev. 4); rev. 5 **proves** the withdrawal correct — no source claims primacy |
| "`normalize_bill` is a misnamed parser" | **Replaced** (rev. 4) with a more accurate reading (§3.4) |
| XML parsing is "lossless" | **Withdrawn** (rev. 4) |
| PDF recovery is "probabilistic" | **Withdrawn** (rev. 4) — contradicts ADR 0008 |
| "The stage had no name, so it went unmeasured" | **Downgraded** (rev. 4) from causal to associative (§3.6) |

---

## 2. Rebrand-resilience findings (unchanged)

*Class C throughout.*

**Branding is not materially coupled to this architecture.** 1,002 occurrences (603
`deltatrack`, 355 `DeltaTrack`, 44 `DELTATRACK`) collapse to four groups; one is structural.

By directory: `docs/research` 308 · `tests` 299 · `docs/decisions` 99 · `src` 81 · root Markdown 51 · `scripts` 46 · `web` 18 · `examples` 16 · `pyproject.toml` 10 · root wrappers 10 · `schema` 4 · `.github` 1 · `tools` 0.

| Category | Evidence | Impact | Risk |
|---|---|---|---|
| **Python namespace** | 360 imports: `tests/` 210, frozen probes 88, `src/` self 37, `scripts/` 21, `web/` 2, wrappers 2 | One grep; every failure is an ImportError or build error | Low (loud); **High (process)** for the 88 frozen |
| **Distribution identity** | `[project] name`, hatch `packages = ["src/deltatrack"]`, `uv.lock:242` | 3 edits; mismatch is a build error by design (`pyproject.toml:9-13`) | Low — never published |
| **Serialized value** | `canonical.py:32` `GENERATOR_NAME`, emitted lines 205/473 | Regenerates examples byte-compared by `test_committed_examples.py:80` | Medium — §6 |
| **Published artifacts** | `examples/*.html` embed `{"generator":{"name":"deltatrack"}}` on GitHub Pages | `render_examples.py` + `update-examples.yml` | Low technically, public in effect |
| **Layout gates** | `test_surface_boundary.py:155-169`, `test_fixture_layout.py` (33) | ~50 path strings, all fail closed | Low |
| **Deployment** | `systemctl restart deltatrack`; `deltatrack.agoradmv.org`. App is host-agnostic (`web/app.py:152-156`) | External DNS/TLS/unit | **High**, externally owned |
| **Research canaries** | `DELTATRACK_SECRET_*`, all 44 uppercase hits | Evidence of observed egress | **Immutable** |
| **UI / prose** | `web/webapp/*`, `title="DeltaTrack API"`, ADR titles | Intended blast radius / editorial | Low / none |

**Already brand-independent:** zero in `.github/workflows/` (all four files); zero branded
env vars (`BILLTRAX_ARTIFACTS` is the *sibling* brand, in a dev-only script); zero
`[project.scripts]`; zero persistent branded paths in the engine; zero in `tools/`.

**CI detects a rename, it does not suffer one.** `uv sync` fails on a hatch package/dir
mismatch; `conftest.py:41-90` aborts before collection if `deltatrack` resolves outside this
checkout's `src/`; `test_engine_installs.py` builds a real wheel. No partial rename produces
a green run.

**No observed external consumer requires a compatibility namespace.** BillTrax's
`submodules/DeltaTrack/` is not a submodule (no `.gitmodules`); it is a tracked vendored
fork of the pre-#398 flat layout (last modified 2026-06-09, `ac29d7e`) doing
`sys.path.insert(...)` then `from bill_tree import normalize_bill` — bare names. It emits
its own shape and never reads canonical JSON. *Limit:* one checkout, one commit.

**Renaming during the frozen research work is unjustified.** 41 probes import `deltatrack`
(88 lines) under a git-blob-hash freeze (`x04_freeze_check.py` F2) and an amendment ledger
(F9); `external-validity/PRE-REGISTRATION.md:128` declares `reconstruct_hybrid.py` frozen
unmodified.

---

## 3. Discoverability findings (unchanged)

### 3.1 Three public surfaces disagree about whether input representation is a job

| Surface | Treatment |
|---|---|
| Canonical contract | Property of the input — `versions.v1.source` is an `enum ["xml","pdf"]` |
| Web API | Parameter on one operation — `POST /api/compare?format=…&output=…`, `_COMPARE` dispatch (`web/app.py:47,249-256`) |
| CLI | Selects the command — `./diff_bill.py compare A B` vs `./diff_pdf.py A B` |
| Python API | Six names — `compare_xml`, `compare_xml_html`, `compare_xml_trees_html`, `compare_xml_files_html`, `compare_pdfs`, `compare_pdfs_html` |

### 3.2 The two CLIs use different grammars for one user intent

Descriptions read "Compare two bill XML versions" (`diff_bill.py:944`) and "Diff two PDF
bill versions" (`diff_pdf.py:601`). An agent generalizing from the first invokes
`diff_pdf.py compare A B` and gets an argparse error.

### 3.3 `--format` carries two meanings, and `source` carries two more

| Identifier | Surface | Meaning |
|---|---|---|
| `--format json\|html` | `diff_bill.py compare` | **Output** representation |
| `--format xml\|pdf\|both` | `fetch_bills.py download` | **Input** representation |
| `?format=pdf\|xml` | `POST /api/compare` | **Input** representation |
| `--source govinfo\|api` | `fetch_bills.py` | **Provider / origin service** |
| `source: "xml"\|"pdf"` | canonical contract | **Input representation** |

`source` is the worse of the two: the contract version is a schema `enum` — published,
versioned, load-bearing. Three distinct concepts — output representation, input
representation, and provider/origin — across two overloaded words.

### 3.4 `normalize_bill` names one step of a composite

Reading `bill_tree.py:1470-1499`:

```
serialized XML → ET.parse            the actual XML parse (stdlib)
  → find_bill_bodies                 source interpretation: which element(s) are the body
  → _extract_metadata                extraction
  → extract_front_matter_nodes       selection
  → _walk_one_body per body          structural transformation to BillNode
  → BillTree                         the project's representation
```

It *contains* a parse but is not one, and it is not a normalization either — conventionally
that means canonicalizing while preserving information, and this selects and discards.
`BillNode` (`bill_tree.py:31-60`) retains no XML, and `<quoted-block>` content is dropped
(DeltaTrack#11). **The name states one step of a five-step composite, and names the step the
function does not conventionally perform** — the same failure mode ADR 0020 documented for
`reconcile_moves`.

Separately, `parsers/` holds `pdf_text.py`, `pdf_anchors.py`, `committee_report.py`; the XML
entry point sits at package root, and both `compare/xml.py:7` and `docs/architecture.md`
label that stage **Parse**.

### 3.5 `view` is claimed twice before any `view` job exists

`formatters/view_model.py` (`DiffView`, `ChangeView`, `view_from_canonical()`) is the
presentation model *of a diff*; "full-bill view" (`README.md:195`) is a *panel inside a
comparison report*. No standalone single-document capability ships.

### 3.6 Naming an implicit stage made a responsibility measurable

ADR 0020 identifies `reconcile_moves` as "a second retrieval pass, unnamed as such, running
after classification." Recognizing and naming it as a distinct stage made the responsibility
possible to measure independently; the resulting probe found **496 recovered changes across
27 adjacent version pairs**, with no inspectable candidate set behind them. The association
is strong; the causal form ("no name, therefore unmeasured") is not claimed.

### 3.7 Overloaded terms

| Term | Distinct meanings |
|---|---|
| `normalize` | **4** — `normalize_bill` (§3.4) · `normalize_header`/`_normalize_text` · `normalize_glyphs` · `normalize_raw` |
| `extract` | **6** — `extract_clean_pages` · `extract_text_content`/`extract_display_text` · `extract_amounts` · `extract_front_matter_nodes` · `extract_anchors` · `extract_pre_text` |
| `diff` | **4 roles** — verb, result type, subsystem, qualifier |
| `view` | **3** (§3.5) |
| `format` / `source` | **4 concepts across two words** (§3.3) |
| `version` | **2** — govinfo's stage-in-the-process vs DeltaTrack's local ordinal (§1.3) |
| `bill type` | **3 across official surfaces**, before this repository names anything (§1.2) |
| `tree` | **2, asymmetrically named** — `BillTree`/`BillNode` vs `TreeNode` |

### 3.8 Consistently used, and worth protecting

`canonical` (ADR 0006), `anchor`, `level` (glossary-governed), `slug` (ADR 0013), and the
ADR 0019/0020 stage vocabulary.

### 3.9 The `compare` / `diff` distinction the architecture already supports

`compare/` is the composition layer — every entry point goes through it, its functions
return finished artifacts. `*Diff` types are results; `diff_bills()` is the core algorithm.
**Compare-as-operation and diff-as-result is already the architecture**; only the
identifiers disagree.

### 3.10 Public boundary vs internal grouping — not a blanket verdict

| Name | Verdict | Reason |
|---|---|---|
| `formatters/` | **Acceptable** | Coherent output-side grouping |
| `parsers/` | **Poor as a public boundary** | Excludes the XML entry point; includes `committee_report.py`, which has **no engine consumer** |
| `formatters/_text.py` | **Correct** | Genuine utility bucket, and **private** |
| `version_stems.py` | **Acceptable** | Filename-convention plumbing |

The operative distinction is **public discovery boundary vs private implementation
grouping**, not domain-word vs generic-word.

---

## 4. Naming grammar — a convention, not a taxonomy

An exhaustive role taxonomy is withdrawn: `similarity` falsified the four-role version, and
a fifth role only postpones the failure. A taxonomy is itself a dialect contributors must
learn, which contradicts §0.

> **Names should make their technical role apparent and follow conventional grammatical
> expectations where those expectations exist.**

Operations read as verbs; entities, results, measures and capabilities read as nouns;
predicates read as predicates; exceptions follow established technical convention.

**Where it is awkward:** measures and cutoffs (`SIMILARITY_THRESHOLD`) fit no role cleanly,
and ADR 0020 owns their reclassification. Verb-first module names are sometimes right.
Private buckets stay legitimate. Representation qualifiers are correct one layer down —
`compare_xml` / `compare_pdfs` are wrong as *the public surface* and right as
implementations behind a dispatcher, which is how `_COMPARE` uses them.

**`bill_diff` remains a live ambiguity**, not a hypothetical: within one package the token
names a subsystem (`diff_bill.py`), an action (`diff_bills()`), a result (`BillDiff`), and a
serializer (`bill_diff_to_dict()`), with word order reversed between module and function.

---

## 5. Technical vocabulary against conventional expectation

| Term | Repo usage | Verdict |
|---|---|---|
| `parse` | `parse_lines`, `ET.parse` ✓; but the composite around it is labelled "Parse" in the docs | **Docs compress a composite** |
| `normalize` | Three uses conform; `normalize_bill` neither preserves nor is a single step | **Violated once, prominently** |
| `extract` | Six meanings | **Diluted** |
| `serialize` / `render` / `validate` | `serialize_tree`; `format_diff_html`; validation against committee reports (ADR 0009) | **Conform** |
| `match` / `compare` | Governed by ADR 0020 | **Deferred** |
| `fetch` | Tool named `fetch_bills.py`, primary verb `download`, plus a `fetch-index` subcommand | **Synonym drift** |

### 5.1 XML and PDF differ, and not in the way rev. 3 said

**PDF recovery is not probabilistic.** ADR 0008 requires "the same inputs always yield
byte-identical output" and states the hard problems are "solved with deterministic
heuristics (#56), not by trading away reproducibility."

> XML arrives with explicit structural markup governed by a DTD and is transformed
> deterministically into the internal representation. PDF arrives as presentation-oriented
> content from which textual and structural information must be **recovered** using
> deterministic heuristics.

PDF is more inferential, more lossy, engine-sensitive and structurally ambiguous — without
being nondeterministic. **And XML → BillTree is not lossless either** (§3.4).

**Consistency never overrides technical accuracy.** `parse` and `extract` stay distinct;
collapsing them would erase the distinction ADR 0002, ADR 0012 and the external-validity
study exist to characterize.

---

## 6. Rebrand rule (final form)

> **Product branding must not be a load-bearing technical identifier.** Branded identity may
> appear in explicitly product-facing metadata and copy, but protocol, capability, dispatch,
> compatibility, and other technical behavior must not depend on the brand.
>
> **Producer-side obligation.** A field carrying replaceable product identity must say so
> where the contract is defined. "Consumers must not depend on it" is unenforceable against
> a consumer never told.

| Case | Ruling |
|---|---|
| `schema_version` | **Load-bearing technical identity** — consumers should dispatch on it |
| `generator.name` | **Replaceable product identity** — must be documented as non-dispatchable |
| `from deltatrack.x import y` | **Violation** — every consumer must spell the brand |
| Docstrings; user-facing copy in `compare/` | **Fine** |
| `DELTATRACK_SECRET_*` canaries | **Exempt and immutable** — evidence of observed egress |
| `title="DeltaTrack API"` | **Fine** — product-facing metadata |

**Recommended action:** document `generator.name`'s semantics in `schema/canonical-diff.md`
and add a `description` to the schema's `generator` object. **Do not change the emitted
value.** It costs a paragraph, changes no output bytes, and is the only finding that gets
harder the longer it waits.

---

## 7. What I recommend rejecting or amending in the proposed policy

Adversarial by design: the spike was asked to falsify the policy it was evaluating. "The
brief" and the numbered items refer to a review proposal setting out a candidate policy; the
numbering is preserved so each objection stays traceable.

### 7.1 Reject "No DeltaTrack dialect" as an absolute

ADR 0020 deliberately creates project-specific vocabulary — the four-stage boundary and the
`Candidate` / `Proposal` / `Retriever invocation` distinction are this project's. The words
are borrowed from IR and record linkage; the structure is not. Stated absolutely the
principle is unfalsifiable-by-design and would be cited against good decisions later, which
matters because ADRs are append-only.

**Amend to:** *no unnecessary or undocumented dialect.*

### 7.2 Reject ranked institutional authority; scope to concept *and representation*

A ranking fails, and so does merely assigning concepts to institutions — because the same
institution uses one term for two concepts on two surfaces, two pages apart in one document
(§1.6). §1.1 carries the replacement, with the conflict rule: where scopes overlap and
sources differ, document the conflict and record which was chosen and why. §1.2, §1.3 and
§1.6 are the first three entries.

### 7.3 Amend the representation freeze — provider/origin is another distinct concept

Adopt "input representation, output representation, operation, and result are different
concepts," and add **provider/origin as another distinct concept** (§3.3). Also soften the
absolute form:

> Input representation should not create a separate user-facing operation when user intent
> and the operation's contract are otherwise the same. It may remain visible where it
> implies different guarantees, supported operations, failure modes, or semantics.

### 7.4 A glossary-membership CI gate cannot ship yet

It cannot be built until the glossary exists. What can ship now: one meaning per public flag
name across all surfaces, and a CLI-grammar assertion. Precedent —
`tests/test_structure_vocabulary_gate.py` is an ADR-0018 vocabulary gate that scans by
subtraction so a new module is guarded by default, and carries `TestDetectorCanFail` proving
the detector still fires.

### 7.5 "Do not freeze `bill`" — partly resolvable, and only partly

Rev. 4 could not settle this at all. Rev. 5 settled it too broadly. The supportable
position:

- **Freezable:** `bill` is the umbrella in the **govinfo acquisition / data-access
  register** (§1.6), which governs the fetch tooling and anything naming a govinfo package.
- **Not freezable:** the umbrella for the product domain, public Python API, CLI,
  pipeline-neutral canonical contract, future package namespace, or MCP interface. Those
  expose concepts the acquisition register does not govern (§1.1.1), and the substantive
  authorities point at `measure` for at least some of them.

Both remain **separate from** any package-name decision, which stays open.

### 7.6 Accepted without amendment

Loosening the grammar; narrower ADRs authoritative in scope; the rebrand rule plus producer
obligation; grandfathering without freezing a mechanism; not freezing `view`; not freezing a
job taxonomy; preserving parse/extract; public boundary vs private grouping; discoverability
and auditability as criteria.

---

## 8. Migration recommendation

**Do not rename now.** No architectural justification; the frozen research surface forbids
it; no deadline.

- **Current finding, dated 2026-08-07.** On the consumer graph as observed today, no compatibility namespace is justified.
- **Deferred decision.** The migration mechanism is chosen at rename time against the graph as it stands then. **Not frozen.**

**Triggers to reassess:** the product is rebranded; the distribution is about to be
published to an index; a consumer begins importing `deltatrack.*`; the external-validity
freeze lifts; #62 is resolved and a package split is on the table architecturally.

**Do not change yet:** package name, distribution name, `GENERATOR_NAME`'s value, frozen
probes, deployment names, prose, and the 37 `src/` self-imports.

---

## 9. ADR 0021 — scope

`0019-observation-identity.md` and `0020-matching-stages.md` are both merged on
`origin/develop` (PR #562 merged 2026-08-07). Nothing above 0020 exists on any remote
branch and no open pull request touches `docs/decisions/`, so **0021 is the next free
number** — re-verified at this revision. Re-check again at draft time.
`tests/test_adr_index.py` regenerates both the `AGENTS.md` index and the README Records
table and fails if either disagrees, so a new ADR requires updating both.

### What the ADR should freeze, after rev. 6's scoping correction

- **Freezable:** the authority model — scoped to a concept **and the representation or
  interface in which it is expressed**, not ranked by institution (§1.1).
- **Freezable, and the most consequential result of the research:** *authoritative
  vocabulary does not propagate across architectural boundaries.* Where data crosses
  registers, name each side by its own authority and make the translation explicit rather
  than hiding two meanings behind one identifier (§1.1.1).
- **Freezable, narrowly:** `bill` is the umbrella in the **govinfo acquisition register**
  (§1.6). Not the product domain, Python API, CLI, canonical contract, package namespace,
  or MCP interface — those stay open (§7.5).
- **Falsified as a defect, without becoming an endorsement:** `bill.type` (§1.2). Whether
  the contract should keep the term is ADR 0006's question.
- **Promoted to the clearest current tension:** `version_number` (§1.3).

### Tensions to acknowledge, not schedule

| Tension | Owner |
|---|---|
| `version_number` vs govinfo `billVersion` (§1.3) | ADR 0013 / 0006 |
| `bill` umbrella vs `<bill>` document type inside the code (§1.6) | 0021 states the boundary rule; renames belong elsewhere |
| Whether the canonical contract's domain vocabulary should be `bill` or `measure` (§1.2, §1.6) | **ADR 0006** — 0021 must not decide it |
| `source` collision (§3.3) | ADR 0006 and the tooling |
| `normalize_bill` names one step of a composite (§3.4) | Example only |
| `resolution` branch has no corpus coverage (§1.4) | Testing, not naming |
| ADR 0020's `similarity` reclassification | **0020 governs; 0021 must not touch it** |
| ADR 0018's vocabulary gate | 0021's gate proposals must compose with it |

### Open questions

1. **What is the umbrella term for the product domain, Python API, CLI, canonical contract
   and any future namespace?** Reopened, deliberately, by rev. 6. `bill` is verified only
   for the acquisition register; `measure` has substantive backing; each surface needs
   evaluating against the authority governing what it exposes (§1.1.1, §1.6).
2. Will the product be rebranded, and when?
3. What is the canonical term for single-document presentation? Not `view` (§3.5).
4. Mixed-representation comparison (`compare v1.pdf v2.xml`) — unsupported; ADR 0010 silent.
5. Does anything downstream read `generator.name`?
6. Will the BillTrax fork re-converge?
7. Who owns `deltatrack.agoradmv.org`, the certificate and the systemd unit?
8. Should `parsers/committee_report.py` be in the shipped engine at all?
9. Should the `resolution` document type get corpus coverage (§1.4)?
10. How often do `isAppropriation` and `bill-type` misclassify, and on what population?
    Unanswerable from an appropriations-selected corpus (§1.7).

*Closed in rev. 5:* whether `bill` is the umbrella **in the govinfo register**; whether
`label` should be backed by an official vocabulary and which; and the class-A gap that was
rev. 4's largest. *Question 1 above is what rev. 5 wrongly believed it had also closed.*

---

## 10. Sources

**Class A, read first-hand:**

| Source | Settled |
|---|---|
| [`bill.dtd`](https://www.govinfo.gov/bulkdata/BILLS/resources/bill.dtd) | `bill-type (olc \| traditional \| appropriations) "olc"`; `bill-stage` `#REQUIRED`, 50 values |
| [`res.dtd`](https://www.govinfo.gov/bulkdata/BILLS/resources/res.dtd) | Root `<resolution>`; `resolution-type` mixes category and form |
| [govinfo API, `BILLS-118hjres1ih`](https://api.govinfo.gov/packages/BILLS-118hjres1ih/summary?api_key=DEMO_KEY) | `billType: "hjres"` — bill is the umbrella in the API register |
| [govinfo API, `BILLS-115hr1625enr`](https://api.govinfo.gov/packages/BILLS-115hr1625enr/summary?api_key=DEMO_KEY) | `isAppropriation: "false"` on the Consolidated Appropriations Act, 2018 |
| [GPO BILLS XML User Guide v2](https://www.govinfo.gov/bulkdata/BILLS/resources/BILLS-XML_User-Guide-v2.pdf) | §1.1 "four types of legislation" vs §1.3 "bill type" — both registers, one document |
| [GPO BILLSUM XML User Guide v2](https://www.govinfo.gov/bulkdata/BILLSUM/resources/BILLSUM-XML_User-Guide-v2.pdf) | `@measure-type`; "commonly referred to as the bill number" |
| [CRS R46603](https://www.congress.gov/crs_external_products/R/PDF/R46603/R46603.4.pdf) (27 Aug 2025) | "four forms of legislative measures" |

**Class A, read via fetch summary:** [govinfo Congressional Bills help](https://www.govinfo.gov/help/bills) (version table, "Bill Version" definition); [Congress.gov API bill endpoint docs](https://raw.githubusercontent.com/LibraryOfCongress/api.congress.gov/main/Documentation/BillEndpoint.md); [`BILLS-118hjres1ih.xml`](https://www.govinfo.gov/bulkdata/BILLS/118/1/hjres/BILLS-118hjres1ih.xml).

**Not reachable, and what stays unverified:** `api.govinfo.gov/docs` (JS-rendered);
`xml.house.gov` and `congress.gov/help/*` (HTTP 403). The Congress.gov *glossary* definition
of "measure" is therefore second-hand — CRS R46603 corroborates it first-hand, so nothing in
this report rests on the glossary alone.
