# Pre-registration: external validity of the PDF extraction seam

- **Status: PROTOCOL FROZEN. NOTHING SCORED.** This document must not be edited again
  before the confirmatory population is committed — `x04`'s F4 requires its
  **last-modifying** commit to strictly precede the membership commit, so any later edit
  closes the gate by construction. The authoritative state is whatever
  `probes/x04_freeze_check.py` prints; the population is whatever
  `results/holdout_membership.json` records. Neither is restated here, deliberately: a
  status line describing an outcome is a status line written after seeing it.
- **Everything committed up to `1350710` is DESIGN, not pre-registration, and is retained
  as such.** An external review found that the protocol was materially amended *after*
  selection ran — §4.4.1, M9, Rule 0 and the revised selection rules were all written
  because of facts the selection runs surfaced — and that the freeze check tested only the
  **first** commit of this file, which proves merely that *some* version predated the
  population. Both findings are correct. The consequence:
  - the five design selection runs are preserved in
    [`results/design_runs/`](results/design_runs/);
  - the **37 documents** they selected are enumerated in
    [`results/design_exposure.json`](results/design_exposure.json) and are **excluded** from
    the confirmatory population;
  - the confirmatory selection uses a **new seed (20260808)**;
  - `x04`'s F4 now tests the **last-modifying** commit of this file, so a protocol amended
    after selection fails the gate mechanically rather than being caught by a reviewer.
- **What this costs:** the 19-document population described in earlier commits is
  **withdrawn as confirmatory** and kept only as design history. No score was ever computed
  on it.
- This is a new study in the bake-off lineage, not a fourth phase of the old one. Phases
  1–3 repeatedly interrogated **development** evidence; this study tests **external
  validity** with a new oracle and a new population. The directory name says so on purpose.
- Read [`../README.md`](../README.md) first for how the argument reached this point.

## Three kinds of sentence, kept apart

This document has been a repeated source of error in this research when it was not.

| marker | meaning |
|---|---|
| **MEASURED** | a number produced by a committed probe in this repository, cited to its result file |
| **DESIGN JUDGMENT** | a choice this protocol is making, which a reviewer could reasonably make differently |
| **PROVISIONAL** | a belief carried from earlier phases that this study does not re-establish |

No sentence below asserts more than its marker licenses.

---

# 1. What this study is for

Two questions, both pre-registered, because the first is likely to return equivalence and
the second is the thing that has blocked an ADR since phase 1.

**RQ1 — comparative.** On genuinely new, structure-rich legislative PDFs, does **hybrid**
or **corrected extended glyph** produce more trustworthy input for DeltaTrack's downstream
legislative interpretation?

**RQ2 — absolute.** On the same population, how correct is the surviving seam family's
heading, hierarchy and amount-attribution output, measured against an oracle independent
of both PDFium and the XML reference?

The causal chain the project actually depends on is

```
PDF → text → headings → hierarchy → account attribution → financial interpretation / diff
```

This study measures it as far as **account attribution**. It stops there deliberately;
[§ 6.4](#64-what-is-deliberately-not-measured) says why, rather than implying coverage it
does not have.

---

# 2. The design fact that shapes everything

**MEASURED** ([`results/x00_design_pilot.json`](results/x00_design_pilot.json), five
development documents × 24 pages):

| | |
|---|---|
| aligned reconstructed printed lines | **3,381** |
| printed lines whose text differs between hybrid and corrected extended glyph | **2** |
| heading occurrences emitted (account / agency / grouping) | **85** |
| heading occurrences differing | **0** |
| S1 control — extended advances × 1.25 | **458** differing lines, fires on **every** document |

The two differing lines are `H. R. 2029` vs `H.R. 2029` (a bill cover page) and
`C O N T E N T S` vs `C O N T E N TS` (a committee report contents page). Both are
letter-spaced display type on front matter, neither is an appropriations heading, and
**both architectures are wrong on the second** — GPO prints `CONTENTS`. This independently
reproduces phase 1's `v08` display-caps finding from the opposite direction.

**Three consequences, all of them binding on the protocol.**

1. **RQ1 is an equivalence-and-direction study, not a superiority study.** Drawing
   adjudication items at random would spend the entire budget on records where the two
   architectures agree by construction. The comparison is therefore a **census of the
   cases where they differ**, plus a **bound computed on 100 % of the holdout without any
   oracle at all**.
2. **The equivalence bound needs no adjudication and is where RQ1's statistical power
   lives.** Whether two extractors' heading strings differ is decidable without truth.
   Truth is needed only to say *which is right* on the cases where they do.
3. **A comparison reporting zero differences is indistinguishable from a comparison that
   cannot see one.** Every discordance count in this study is reported beside its S1
   sabotage row, and a count without its control is not evidence.

**A protocol clause that came out of getting this wrong.** The first pass of `x00`
compared hybrid in soft-hyphen-repaired mode against extended in strict mode, because
`reconstruct_hybrid._line_text` renders GPO's soft hyphen as ASCII `-` unconditionally
while `reconstruct_extended` only does so under `repaired=True`. It read **98 differing
lines of 424** on one document, every one a line truncated at a U+FFFD carrier — a
measurement of the mode, not of the seam. **Any comparison run in unequal soft-hyphen
modes is void.**

---

# 3. Architectures under test

Only the two surviving seams. The ink-box-only glyph seam is not carried forward: it is
**MEASURED** as the weakest of the three (0.8986 against 0.9275 adjudicated, 30 correct /
23 malformed against 53 / 0 on the named heading failure cases, `../phase2/`), and
preserving it for backend neutrality is not a reason this study accepts.

## 3.1 H — hybrid

PDFium supplies **ordered characters and word-space decisions**, plus the geometry above
the seam. DeltaTrack owns GPO normalisation, printed-line reconstruction, heading
recognition, hierarchy and financial interpretation.

Frozen implementation: `../../probes/backends/pdfium_hybrid.py` +
`../../probes/reconstruct_hybrid.py`, unmodified, at this protocol's freeze commit.

## 3.2 X — corrected extended glyph

PDFium supplies **character identity, pen origin, advance and geometry**. DeltaTrack owns
word segmentation. "Corrected" is not a slogan; it is two specific repairs phase 3 named
and did not apply, plus the contract text that makes them implementable by a second
backend.

### X-1. `font_size` has a defined axis

> **`font_size` is the HORIZONTAL type scale: the length, in points, of the image of the
> unit x-vector under the text-rendering matrix (text matrix × CTM).**

**Rationale.** The ported rule normalises an *advance* — a horizontal quantity — to
1/1000 em by dividing by `font_size`, then **buckets** the result at 400/700/800 to select
a divisor. Under anisotropic type the axis therefore chooses the threshold. **MEASURED**
(phase 3 §5 D1): GPO condenses display type at text matrix `12 0 0 13`; PDFium and PyMuPDF
report 12.0 (horizontal), pdfminer reports 13.0 (vertical); the advance is 722 em by one
and 666 em by the other, which crosses the 700 boundary, and that is the cause of the
single disagreement in 195,291 page-scale pairs.

Per-backend, each answering from its own API and none reproducing another's convention:

| backend | horizontal type scale |
|---|---|
| PDFium | `FPDFText_GetFontSize(i) × sqrt(a² + b²)` — already this quantity |
| PyMuPDF | `|transform_vector((1,0), trm × ctm)|` — already this quantity |
| pdfminer.six | `LTChar.size × |matrix[0]| / |matrix[3]|` — phase 3's N9, derived inside pdfminer's own API |
| PDF.js | **cannot emit the contract at all** — no API exposes a per-character pen origin (phase 3 §2) |

### X-2. U+0020 is excluded from the contract

A space carries no ink, and the contract is "facts about marks that are on the page". Every
word boundary is therefore decided above the seam.

**This is also the design's answer to `FPDFText_IsGenerated`**: not carrying U+0020 at all
excludes engine-invented spaces without the Experimental predicate the design exists to
avoid.

**It requires a test, because phase 3 D2 showed an adapter can satisfy the docstring's
letter while passing the engine's decision straight through** — `pdfium_extended.py` copied
PDFium's generated spaces and on `114-hr-2029/4` was taking eight of every nine word
boundaries from the engine. Two assertions run on **every** holdout document before any
score:

- **X2-a** no glyph with codepoint 32 exists in the contract, on any page;
- **X2-b** re-admitting the engine's spaces changes no reconstructed line — i.e. the
  geometric rule independently recovers every boundary they were supplying. A failure here
  means the rule is not doing the work and the run is void for X.

### X-3. What is unchanged, so a difference is attributable

`_ADVANCE_FALLBACK_EM = 0.5` stays, and stays declared as a cost: `FPDFFont_GetGlyphWidth`
cannot measure GPO's soft hyphen, so **MEASURED** (phase 2) 358 glyphs over 60 pages of
`118-hr-4366/5` — about 6 per page, all line-final soft hyphens — take a constant. The
design that exists to remove `_SPACE_FACTOR` carries a different unexplained constant, on a
narrow and well-understood population.

## 3.3 Held identical on both arms

Line clustering, chrome stripping, margin-number parsing, `_merge_print_lines`,
`rejoin_soft_hyphens`, `extract_anchors`, the structure tree and amount extraction are the
**same code** on both arms. A difference in any metric is therefore attributable to the
seam and to nothing else. Both arms run in the **soft-hyphen-repaired mode** (§2).

---

# 4. The holdout

## 4.1 Target population

**GPO-typeset legislative PDFs that carry appropriations heading structure** — the
documents whose heading tree is DeltaTrack's financial data contract.

**DESIGN JUDGMENT, and it is a deliberate reversal.** The prior holdout sampled
*legislation in general* and bought bill-type breadth at the cost of being unable to
exercise the downstream contract: **MEASURED** (RESULTS-CONFIRMATORY §B.5) 7 of its 44
documents carried any account or agency heading, 37 carried none, and the heading metric
was declared **VOID** on it. That protocol's own closing note says one 12-bill holdout
cannot both test generalisation beyond appropriations and exercise metrics that exist only
within it. This study takes the other side of that trade and states the cost: **it can say
nothing about non-appropriations legislation.**

## 4.2 Sampling frames

Two, kept apart, both enumerated **before** either architecture runs.

- **F1 — bills.** govinfo BILLSTATUS, Congresses 113–119, types `hr` / `s` / `hjres` /
  `sjres`, appropriations by committee referral (`hsap00` / `ssap00`) via the repository's
  own accessor `tools/fetch_govinfo.py`. Unit: one text version's PDF.
- **F2 — committee reports.** govinfo `CRPT` year sitemaps for the same Congresses,
  classified as appropriations from the package's own `mods.xml` title. Unit: one package's
  PDF. **This frame is only reachable because the oracle is not the XML** — reports carry
  no bill XML, which is exactly why the prior protocol had to move them out of its holdout.

## 4.3 Exclusions — the freshness rule

Every member is subtracted from [`results/contamination.json`](results/contamination.json),
generated by [`probes/x01_contamination.py`](probes/x01_contamination.py) with no network.
**MEASURED**: **93 bills and 33 report packages** are excluded, from five exposure classes:

| class | why it contaminates | n |
|---|---|---|
| `pdf_committed` | a PDF in the working tree today | 112 files → 51 bills, 1 report |
| `pdf_in_history` | a PDF **ever added on any ref**, including since-deleted ones — 35 paths are not in the worktree, and this is the class a working-tree scan misses | 112 files |
| `named_in_research` | a bill or package id appearing as **text** anywhere in the research tree or production source. A document can be read, argued over and tuned against without ever being committed; the five documents phases 1–3 drew their frozen sample from are named in prose far more than they are stored | 93 bills, 33 reports |
| `main_checkout` | bill directories in the developer's gitignored working tree | 20 bills |
| `xml_only` | 2,963 bills present only as XML (`bills_corpus`) | **not excluded** |

**The `xml_only` decision is recorded rather than assumed.** No PDF extractor has ever run
on those documents, and the architectures under test read PDFs. A reviewer who disagrees
can re-run the selection with them excluded; the list is in the artifact.

**Residual risk, stated because it is unfalsifiable:** exposure that left no trace in this
repository — a document read in a conversation and never named in a file — cannot be
detected by any of this.

## 4.4 Strata

Chosen to exercise the structures DeltaTrack depends on, and every predicate is decidable
**without running either architecture**. Version code, chamber, Congress, committee
referral and page count are container facts; page count comes from `pypdfium2`'s page
count, which reads no text.

| # | stratum | n | structural axis it buys |
|---|---|---|---|
| 1 | House appropriations bill, `ih` / `rh` | 3 | chamber + early stage |
| 2 | Senate appropriations bill, `rs` / `pcs` | 3 | chamber + watermarked print |
| 3 | Chamber-crossing appropriations amendment print, `eah` / `eas` | 2 | DeVinne-Italic typography |
| 4 | Enrolled appropriations bill, `enr` | 2 | NewCenturySchlbk, unnumbered layout |
| 5 | Appropriations joint resolution / continuing resolution | 2 | a class absent from the development corpus |
| 6 | Appropriations committee report (`CRPT`) | 3 | report typography, table-dense, continuation headings |
| 7 | Congress under-represented in development (113 / 116 / 117 / 119) | 3 | period typography drift |
| 8 | Omnibus / consolidated, ≥ 2 divisions | 2 | division banners, deep hierarchy |

**Target: 20 documents from ≥ 16 distinct bills or packages.**

### 4.4.1 Two populations, because two strata cannot carry a heading metric

**MEASURED**, by reading the production code and by `x00`: strata 4 and 6 produce **zero**
account / agency / grouping anchors, and would have contributed a zero denominator to
every heading metric.

| | why |
|---|---|
| **enrolled bills** (stratum 4) | production **declines** them — `compare/pdf.py::_is_unnumbered_layout` raises `UnsupportedLayoutError` — and `extract_anchors` emits no account anchors when `_coverage(pages) < 0.85`, which an unnumbered layout cannot reach. `x00` measures 0 heading occurrences on `116-hr-1865/6` |
| **committee reports** (stratum 6) | `parsers/committee_report.py` reads GPO's **HTML `<pre>` dump, not the PDF**, deliberately — "fixed-width column slicing instead of PDF coordinate reconstruction". A report PDF has no production heading consumer at all. `x00` measures 0 heading occurrences on `CRPT-118srpt198` |

The holdout is therefore split, **in advance**, and the split is reported in every table:

| population | members | metrics it carries |
|---|---|---|
| **P-head** | strata 1, 2, 3, 5, 7, 8 | **M0, M9 and M1–M7** — the heading, hierarchy and attribution chain |
| **P-robust** | strata 4, 6 | **M0 and M9 only**, plus safe-failure observation. **No heading metric is claimed on it** |

**They are never pooled**, and §4.5's heading-occurrence adequacy count is computed on
**P-head only**. This is the failure that voided the prior holdout's heading metric — 37 of
44 documents carrying no heading at all — caught here by reading the production code before
selecting rather than by discovering a VOID afterwards.

P-robust is retained rather than dropped because report and enrolled typography is dense,
table-heavy and differently set, which is where M0 is most likely to find a seam
divergence, and because the brief asks the holdout to cover reports.

**Within a stratum**: candidates sorted by id, permuted with seed **20260807**, and the
first satisfying the predicate is taken. Ties break by the permutation, never by
inspection. The number of candidates examined is recorded, so a thin stratum is
distinguishable from a lucky one.

**Cherry-picking is structurally prevented, not promised**: no candidate is opened by
either architecture before selection, and the selection script writes its output before any
extractor is imported.

## 4.5 Adequacy rule, pre-committed

| condition | consequence |
|---|---|
| ≥ 7 of 8 strata filled **and** ≥ 800 emitted heading occurrences | supports a generalisation claim over appropriations documents |
| 5–6 strata filled | reported as *"extends to the classes actually sampled"*, unfilled strata named in the headline |
| < 5 strata, **or** < 300 heading occurrences | **holdout declared inadequate**; RQ2 is not claimed and RQ1 reports a bound only |

## 4.6 The only admissible exclusions after freezing

A frozen document may be removed from a denominator **only** for one of the reasons below.
Each is a property of the **file**, decidable without running either architecture, and each
must be recorded with evidence in `results/DEVIATIONS.md`.

| # | admissible source-level exclusion |
|---|---|
| 1 | the file does not open as a PDF, or its SHA-256 no longer matches the frozen membership |
| 2 | the document carries **no extractable text layer at all** (an image-only scan) — a property of the file, not of a seam |
| 3 | the document is of the wrong class for its stratum (mis-selected: not an appropriations measure, wrong chamber, wrong version code) |
| 4 | govinfo has withdrawn or replaced the package, so the frozen bytes no longer correspond to a published document |

**Nothing else.** In particular, "the extractors performed badly on it", "it has no
headings", "the oracle found it hard", and "it dragged the average down" are **not**
admissible, and a document removed for any of them invalidates the run.

## 4.7 The rule that makes a holdout a holdout

**No holdout result may change a metric, threshold, normalisation, parameter, adapter,
repair rule, contract field or population.** An architecture crashing on a holdout document
is a *result*, not a bug to fix mid-run. If something must change, it is a deviation, it
gets a row in `results/DEVIATIONS.md` when it happens, and every affected score is
re-labelled non-confirmatory.

---

# 5. The heading oracle

## 5.1 Why the XML reference is not it — corrected

**Every phase so far gives the same reason: the reference comes from a parser known to drop
`<quoted-block>` (DeltaTrack#11). That reason is inherited, and this study checked it.**

**MEASURED** ([`results/x02_oracle_reference_defects.json`](results/x02_oracle_reference_defects.json),
all 58 development corpus XMLs):

| | |
|---|---|
| DeltaTrack#11 | **CLOSED** 2026-06-26, `COMPLETED`. A section's quoted-block **text** now reaches the section body |
| what the tree still drops **by design** | quoted-block *subsections* — `bill_tree._node_subsections`: "amendment payload … not this bill's structure" |
| `<header>` elements inside a `<quoted-block>` | **6,617** |
| **`appropriations-*` elements inside a `<quoted-block>`** | **0**, of 27,275 |
| documents carrying a quoted block | 30 of 58 |

**So the specific mechanism — "a printed appropriations account heading is missing from the
reference because it lives in a quoted block" — has zero instances on the development
corpus.** The XML is real for general legislation (119-hr-1 alone hides 1,347 headers) and
irrelevant for appropriations. **A protocol that disqualified the XML on that ground would
be citing a claim its own corpus contradicts.**

The XML is nonetheless not the oracle here, for three reasons this study *can* defend:

1. **It is not the printed page.** The question is what a PDF extractor recovers from
   *the print*. An XML reference cannot referee a printed-page fact — a heading GPO set in
   the heading band, a wrap GPO introduced, a letter-spaced display line.
2. **Its level vocabulary differs.** The XML's `appropriations-intermediate` → `agency`
   holds what the PDF calls an `account`; the prior protocol's mitigation was to go
   level-agnostic, which is precisely to give up measuring hierarchy — the thing RQ2 needs.
3. **It cannot see the one place the two architectures differ.** §2's differences are
   letter-spaced display type, a *typesetting* fact the XML does not carry at all.

**The XML is therefore retained as a corroborating sampling source and as a control
(§5.6 N-B), and never as truth.**

## 5.2 Mechanism

Blinded adjudication from page-region images rendered by **MuPDF** (`pymupdf`), which
shares no text-extraction code with PDFium and is the renderer phase 1 used for exactly
this reason. AGPL and reference-only per [`../../LICENSING.md`](../../LICENSING.md): it
renders pixels here and is not proposed as a backend.

## 5.3 The unit adjudicated — and why it is not a heading

**The unit is a printed-page REGION: a bounding box in PDF points spanning 6–10 printed
lines.**

**DESIGN JUDGMENT, and it is the load-bearing one in Part A.** An item whose unit is "this
heading" can only ever be sampled from something that already *found* the heading, which
hands the oracle's sampling frame to an extractor and makes a heading both architectures
miss structurally invisible. A region is defined by geometry alone and asks the adjudicator
to **enumerate**, so a missed heading is detectable and a fabricated one is refutable.

Per region the adjudicator records:

1. **every heading in the region, in order**, with its **exact printed text** — transcribed
   as printed, case preserved, internal spacing preserved;
2. each heading's **role** from a fixed codebook — `account` / `agency` / `grouping` /
   `title` / `division` / `section` / `other` — written from GPO's own composition
   conventions ([`../../../gpo-render-conventions.md`](../../../gpo-render-conventions.md)),
   **not** from DeltaTrack's anchor vocabulary;
3. each heading's **parent heading text as printed**, or `NONE`, or `OFF_REGION`;
4. `UNREADABLE`, with a reason, for anything it cannot resolve.

## 5.4 What the adjudicator sees, and what it does not

| sees | does not see |
|---|---|
| a 300 dpi PNG of the region | any architecture's output, or that there are two |
| the region's bounding box | any architecture's name |
| the page's printed margin line numbers, where the page has them | the XML |
| the question and the role codebook | the stratum label |
| | the document id (regions carry opaque ids) |
| | **which frame the region came from** (coverage or discordance) |
| | any neighbouring region's answer |

## 5.5 Blinding enforced by construction

Three committed artifacts in a fixed **commit order**, which is the evidence — "I
adjudicated first" is not:

1. `results/oracle_key.json` — region id → document, page, stratum, frame, and every
   architecture's output for that region. **Committed first, then not opened.**
2. `results/oracle_adjudicated.json` — the answers. **Committed second.**
3. the join — a **third** committed script, run only after (2) is in `git log`.

**Stronger than the prior runs managed, and the reason it is stronger:** phase 1 recorded
that its adjudicator was the same agent that built the frame, and said plainly that the
artifacts enforce no backend answer was *visible*, not that the judgement was
second-party. Here the adjudicator is a **separate process** — `claude -p`, with `HOME`
pointed at an empty directory so no `CLAUDE.md`, auto-memory or repository context reaches
it — reading only `oracle_blind.json` and the image directory. **Its prompt and its
transcript are committed.** A reviewer can verify what it was able to see rather than
trusting a claim about what it looked at.

**Honest naming, and it is stricter than the prior protocol's.** The coverage-frame oracle
is **AI image-adjudication**, not human ground truth, and every table says so in those
words. A seeded 25-item human audit **does not convert the key into human ground truth**:
it estimates the AI adjudicator's agreement with a human on 25 items and nothing more. The
licensed phrase is *"AI image-adjudicated, human-audited on a 25-item subsample at
agreement rate a"* — never *"human-adjudicated"* and never *"ground truth"*.

### 5.5.1 The D-frame requires human adjudication, item by item

**DESIGN JUDGMENT, and it is the one place this protocol spends a human.** The D-frame is
the census of items where the two architectures disagree. It is expected to be **small**
(the development pilot found 2 differing lines in 3,381 and 0 differing headings in 85),
and it is the **only** evidence that can satisfy §7.2 rule 1 and flip the ADR. Deciding an
architecture on an AI adjudicator's unaudited reading of a handful of images is not a
standard this decision should rest on.

Therefore:

| frame | adjudication | licenses |
|---|---|---|
| **C-frame** (coverage, RQ2) | AI image-adjudication, 25-item human audit, agreement rate reported | absolute correctness figures, labelled AI-adjudicated |
| **D-frame** (discordance, RQ1) | **every item human-adjudicated by Will**, blind, from the same region images and the same blind file | the architecture decision |

If the D-frame census is too large for that (> 60 items), the protocol does **not** silently
fall back to AI adjudication: it reports the census size, adjudicates a seeded random
**subsample** of 60 by human, and states that rule 1 was evaluated on a subsample with the
sampling fraction in the headline.

**Consequence, stated so it is not discovered later:** §7.2 rule 1 cannot be evaluated, and
no architecture may be chosen over the other, until that human adjudication exists. Until
then the study reports RQ2 and the descriptive RQ1 result only.

## 5.6 Negative controls — a green oracle that cannot go red is not evidence

Shuffled in with the real items and indistinguishable in the blind file.

| id | control | must happen | else |
|---|---|---|---|
| **N-A** | 8 regions rendered from a **modified** PDF: one word deleted from a known account heading; two words welded; one heading's size pulled into the body band | the adjudicator transcribes what is actually printed, i.e. reports the alteration | the oracle cannot see the failure class the study exists to detect → M2/M3 **void** |
| **N-B** | 8 regions whose printed heading is unambiguous and corroborated by the XML | agreement | the adjudicator is unreliable independent of any architecture → run void |
| **N-C** | 4 regions containing **no** heading | no heading reported | over-triggering → precision claims void |
| **R1** | 10 % of regions presented **twice**, at different shuffle positions, re-rendered at a different but visually equivalent scale so they cannot be recognised by hash | heading-text agreement ≥ **0.90**; role agreement ≥ **0.80** | below → text metrics void / role metric void |

**R1 exists because phase 1 found six identical stimuli answered 3 BOUNDARY / 3
NO_BOUNDARY and reported it as a defect in its own work.** Its frame's dedup key was
`(doc, page, x)`, so one recurring stimulus was drawn six times across three strata. Here
the region frame additionally dedups on the **rendered pixel hash**, so a recurring
identical stimulus cannot be drawn many times by accident.

## 5.7 Provenance — proving a ruling still refers to the same source region

Every region record carries: document SHA-256, page number, bbox in PDF points, renderer
name and version, DPI, and **the SHA-256 of the rendered PNG**. Rulings are anchored to the
image hash, so a later re-render that differs is *detected* rather than silently reused.

## 5.8 Preventing an extractor from defining the frame

Two frames. **Never pooled.**

**C-frame (coverage) — primary for RQ2.** Regions drawn by a seeded uniform sample over the
numbered-line bands of heading-bearing pages, where "heading-bearing" is decided by an
**ink-geometry predicate that reads no character identity and no word spacing**: a page
carrying ≥ 1 line whose median glyph height sits in the document's sub-body size cluster.

- The predicate is **common to both arms** and is not the thing under test.
- **Its own bias is stated:** it cannot select a page whose headings are set at body size.
  That limit is real and is recorded, not papered over.
- **It is still PDFium-derived**, so it is re-run through PyMuPDF `get_texttrace()` on a
  10 % subsample; the selected page sets must agree ≥ 0.95 or the C-frame is reported as
  **PDFium-conditioned** in every table that uses it.
- At most **8 regions per document**, so one large bill cannot dominate.
- **40 % of C-regions are drawn from pages carrying ≥ 1 dollar amount**, so M6 has a
  population on which it can fire.

**D-frame (discordance) — primary for RQ1.** A **census**: every region where the two
architectures' reconstructed printed-line text differs, and every region where their
emitted anchor sets differ.

- The selection predicate is `H ≠ X`, which is **symmetric under swapping the two**, so it
  cannot favour either.
- If the census exceeds 120 regions it is subsampled with seed 20260807 and the sampling
  fraction is reported in the headline.
- **What it cannot see, stated:** a failure both architectures share. That is exactly why
  the C-frame exists and why RQ2 is pre-registered beside RQ1.

---

# 6. Metrics

Every metric carries a definition, an oracle able to support it, a population where it can
fire, a control, and the conclusion it licenses. **Coverage and content-bearing
denominators are reported separately for every one**, in the shape RESULTS-CONFIRMATORY
used when it found that 3 of 30 holdout pairs carried any amount at all. **A metric whose
content-bearing denominator is zero is reported as VACUOUS, never as agreement.**

| id | metric | oracle | fires on | control | licenses |
|---|---|---|---|---|---|
| **M0** | **seam discordance rate** — fraction of aligned printed lines whose text differs between H and X; and the symmetric difference of emitted heading sets | **none needed** | **100 % of the holdout** | **S1** advances × 1.25 must raise it | the resolution at which RQ1's equivalence statement is made |
| **M1** | heading presence — recall and precision of emitted heading occurrences against the adjudicated enumeration, matched by printed-line position | adjudicator | C-regions with ≥ 1 adjudicated heading (recall) / ≥ 1 emitted heading (precision) | N-A, N-C | "the seam family finds X % of printed headings on fresh appropriations documents" |
| **M2** | heading text exactness — emitted == adjudicated under a **frozen** normalisation (NFKC; collapse internal whitespace **runs** to one space; strip ends). Case preserved | adjudicator | matched headings | N-A's welded-word region must fail M2 | "…and reads them correctly **up to whitespace-run normalisation**" — see §6.2 |
| **M3** | **heading word-boundary integrity**, defined at the boundary level in §6.3 — never a token multiset | adjudicator | matched headings that ALIGN (§6.3) | N-A | the failure class the seam actually controls, **and its direction** |
| **M4** | parent/child correctness — emitted immediate heading-ish parent's text vs adjudicated parent | adjudicator | matched headings whose parent is in-region or resolvable | delete agency-level anchors; M4 must fall further than M1 | "the hierarchy is right, not merely the labels" |
| **M5** | role agreement, on a coarsened leaf-vs-container map | adjudicator | matched headings, **gated on R1 role ≥ 0.80** | R1 | corroboration only — **may never decide** |
| **M6** | **amount → heading attribution** — for each dollar amount in a C-region, emitted nearest heading-ish ancestor vs adjudicated | adjudicator | C-regions containing ≥ 1 amount | shift heading baselines one line-height; M6 must fall further than M1 | "the money lands under the right account" |
| **M7** | display-split incidence — emitted headings matching the letter-spaced signature (≥ 3 single-character tokens), per architecture | none (a self-signature) | 100 % of the holdout | inject a known `R E P O R T` page and require detection | phase 2's flip condition 1, on fresh data |
| **M9** | **structural viability** — per document per architecture: does `derive_size_bands` return a band; is `_coverage` ≥ 0.85; how many margin-numbered lines are recovered | **none needed** | **100 % of the holdout, P-head and P-robust** | S1 | whether either architecture **loses the heading tree entirely** on a document the other keeps |

**M9 exists because reading the production code found an all-or-nothing failure mode
unique to X, and no other metric would see it.**

- `extract_anchors` emits **no** account-level anchor at all unless `derive_size_bands`
  returns a band **and** `_coverage(pages) ≥ 0.85`.
- `_coverage` counts lines whose `line_number is not None`, and a line number is parsed by
  `^(\d{1,2}) (.*)$` — **which requires a space after the margin number.**
- Under hybrid that space is PDFium's. **Under corrected extended glyph it is re-derived by
  the ported rule**, because X-2 removes every U+0020 from the contract.

So a systematic failure to re-insert the margin space would drop coverage below 0.85 and
**silently delete the entire heading tree for that document** — a catastrophic outcome that
M1–M6 would report as an empty denominator rather than as a failure. `derive_size_bands`
also reads line *text* (`_has_lowercase`, `_is_uppercase_heading`), so a word-boundary
change can move the bands themselves.

**MEASURED**: on the five development documents `x00` finds identical line counts and
identical heading counts for both architectures, so the rule re-derives the margin space
correctly there. That is five documents, and it is exactly the kind of property that
generalises badly, which is why it is a pre-registered metric rather than an assumption.

**M3 is the primary comparative metric.** It is the failure the seam choice actually
governs, and it is the one whose *direction* has a product consequence.

**M1 is the primary absolute metric** for RQ2, with M4 and M6 as the downstream chain.

**No heading metric may be written as a financial claim.** M6 is the only metric that
licenses an attribution sentence, and it has its own oracle, denominator and control. This
prohibition is part of the protocol because the failure it prevents — measuring headings
and concluding about money — is one this research has already made.

## 6.2 What M2 licenses, exactly

M2's normalisation collapses internal whitespace **runs** to a single space, so
`FAMILY  HOUSING` and `FAMILY HOUSING` compare **equal**. An earlier draft normalised that
way and then licensed the phrase *"character for character"*, which the measurement does
not support.

> **M2 licenses: "the emitted heading matches the printed heading exactly, up to
> normalisation of whitespace runs and Unicode NFKC form."** It does **not** license
> "character for character", and it cannot distinguish one space from three.

Single-versus-multiple spacing is not silently lost, though — it is **M3's** business, and
M3 is defined below at the level where it is visible.

## 6.3 M3, defined at the boundary level

A token **multiset** cannot represent word-boundary integrity: it discards order, so
`FAMILY HOUSING` and `HOUSING FAMILY` compare equal; and it cannot separate a spacing error
from a character error, so a misread letter is silently charged to the seam. M3 is
therefore defined on **boundaries between adjacent characters**, not on tokens.

Per matched heading, for each of H, X and the adjudicated printed text:

1. **Normalise** with the frozen non-spacing normalisation only (NFKC, strip ends). Casing
   and every character are preserved. **Spaces are not touched at this step.**
2. Form the **non-space character sequence** and its **boundary vector**: for each adjacent
   pair of non-space characters, `1` if one or more spaces separate them in the source
   string, else `0`.
3. **Align** the extractor's non-space sequence to the oracle's. Alignment is on characters
   only, so a spacing difference can never cause a misalignment.
4. **Classify each aligned boundary position**:

| outcome | condition |
|---|---|
| **WELD** | oracle boundary = 1, extractor boundary = 0 — the extractor ran two words together |
| **SPLIT** | oracle boundary = 0, extractor boundary = 1 — the extractor inserted a boundary that is not printed |
| **OK** | boundaries agree |
| **TEXT_ERROR** | the aligned characters differ — a **character** defect, reported in its own column and **never** counted as WELD or SPLIT |
| **UNALIGNABLE** | the two non-space sequences cannot be aligned within the frozen edit budget — reported as its own explicit outcome, **never** silently dropped and never scored as agreement |

`UNALIGNABLE` counts are reported per architecture and **split by discordance status**, for
the same reason `UNREADABLE` is (§9 row 5): an alignment failure concentrated on discordant
items would be an exclusion that removes exactly the distinguishing cases.

**The decision rule consumes this definition.** §7.2 rule 1's "corrects ≥ 5 headings that H
welds or splits, regresses ≤ 1" counts **WELD and SPLIT outcomes at aligned boundary
positions**, and `TEXT_ERROR` and `UNALIGNABLE` are excluded from that count and reported
separately.

## 6.4 What is deliberately not measured

**Downstream diff correctness.** It needs two versions adjudicated rather than one, it
inherits §2's line-level discordance and adds version-alignment noise on top, and this
study cannot adjudicate it independently at any budget available. It is **out of scope**,
stated here rather than approximated badly. RQ1's chain therefore stops at M6.

---

# 7. Decision rule

Fixed before any confirmatory result exists.

**The architectural prior, stated so it cannot be re-litigated afterwards:**

> If downstream correctness is effectively tied, **hybrid** is preferred, because it
> introduces no owned PDF-specific logic — no ported Chromium heuristic, no
> `_ADVANCE_FALLBACK_EM`, no three-call Experimental handle chain — and therefore fewer
> maintenance and API obligations.

## 7.1 There is no per-heading equivalence margin

An earlier draft set **δ = 0.005 of heading occurrences**. §8.1 shows that margin cannot be
carried by this design: it lives on a unit (the heading) that the protocol's own clustering
argument denies is independent, and at the achievable sample size it overstates precision
by **39×**. It is withdrawn.

**The comparative rules below are COUNT-based and need no population model.** A census of
the cases where the two architectures disagree, adjudicated for direction, is a description
of what happened on 19 named documents. It requires no estimate of a universal rate, which
is the only reason the decision survives §8's demotion intact.

## 7.2 The rules

Applied in order.

0. **M9 supersedes everything below, and RQ1 and RQ2 read it differently.**
   - **If exactly one architecture** loses `derive_size_bands`, falls below the 0.85
     coverage floor, or loses margin-numbered lines on a document the other keeps, **that
     architecture is rejected outright**, regardless of every other metric. Losing a
     document's whole heading tree is the largest available heading failure and is the one
     failure that would otherwise surface as an empty denominator rather than an error.
   - **If BOTH lose the same document**, it is **neutral for RQ1** — a shared failure
     distinguishes nothing — **and it is retained as a FAILURE in RQ2**, in M9 and in the
     RQ2 denominator. A fresh, in-scope P-head document on which both seams lose the
     heading tree is a **major negative result about the seam family**, and excluding it
     would condition absolute correctness on successful extraction and inflate it.
   - **No frozen document may be removed from the denominator by its own result.** The only
     admissible removals are the **source-level exclusions pre-specified in §4.6**, which
     are properties of the file, decidable without running either architecture.
1. **Choose corrected extended glyph** if, on the D-frame census, the discordant counts are
   one-directional in its favour — X corrects **≥ 5** printed account or agency headings
   that H welds or splits and regresses **≤ 1** — **and** no other metric moves against X
   by more than one heading occurrence per affected document.
2. **Choose hybrid** if either the reverse of (1) holds, **or** the census yields **no
   heading-level discordance in X's favour meeting (1)**. The tie is broken by the
   architectural prior above, explicitly and in advance, not by a claim that the two are
   provably identical.
3. **Declare the evidence insufficient** if **any** of: the R1 reliability gate fails; any
   of N-A / N-B / N-C fails; S1 does not fire; X2-a or X2-b fails; the M9 gate cannot be
   evaluated; or §4.5 returns *inadequate*.

**Pre-committed reporting for the most likely outcome.** If the census is empty and every
metric returns no difference, the result is written as

> **"On the 19 frozen documents, comprising H heading occurrences, no heading-level
> discordance was observed. Exact 95 % upper bound on the per-document discordance rate:
> r."**

— with the content-bearing denominator printed beside it, **never** as "the architectures
agree" and **never** as a per-heading rate.

## 7.3 What would falsify the preferred hybrid hypothesis

Asked explicitly by the brief, answered explicitly and in advance:

> A D-frame census in which **corrected extended glyph repairs ≥ 5 printed account or
> agency headings that hybrid welds or splits, and regresses at most 1**, on documents no
> architecture was developed against.

That is the result that makes owning the rule worth its cost. **Nothing weaker does, and
in particular a tie does not.**

## 7.4 Non-accuracy factors that may legitimately flip a tie

Ranked in advance, so none is discovered after the fact.

| factor | how it enters | weight |
|---|---|---|
| **failure direction** — WELD is worse than SPLIT. A welded account name misfiles every amount beneath it and is invisible to any check that counts or sums; a split one is visible | M3, reported split by direction, always | **can flip a tie** |
| **stratum robustness** — equivalent on average but materially worse on one structural stratum is not equivalent | M1–M4 per stratum, always reported | **can flip a tie** |
| **detectability of failure** | M7 plus the U+FFFD and no-advance rates | records a follow-up; does not flip |
| **backend portability** — zero for hybrid, demonstrated for extended (phase 3, **PROVISIONAL** here: not re-measured) | not re-measured | **does not flip.** ADR 0002 has declined a second engine. If ADR 0002 is reopened this study is superseded, and says so |
| **API / ownership cost** — hybrid 5 Experimental entry points reducible to 3, per-index predicates; extended 5, none removable, a handle chain, 1 magic constant, 1 ported heuristic | phase 2 G4, not re-measured | **is the tie-break in rule 2** |

**Supply chain and distribution are out of scope.** Bundle size, WASM provenance and egress
belong to RESULTS-CONFIRMATORY and RELEASE-READINESS and may not enter this decision. The
standing rule that concerns are never combined is what this study inherits most directly
from the withdrawn headline that started the audit.

---

# 8. Statistics

## 8.1 The estimand problem this section exists to fix

An earlier draft set δ on **heading occurrences**, required ≥ 600 of them, and proposed an
exact Clopper–Pearson bound plus a cluster bootstrap by document. **Those three statements
are mutually incompatible, and the incompatibility is measured, not argued.**

| | |
|---|---|
| 0 events / 600 **headings**, treated as iid Bernoulli trials | 95 % upper bound **0.00498** |
| 0 events / 14 **documents**, the unit this protocol itself calls independent | 95 % upper bound **0.1926** |
| ratio | **39×** |

Headings inside one bill share a face, a size, a producer and a typesetting run, and the
one discordance mechanism observed to date — letter-spaced display type — is a property of
**the document's typography**, not of an individual heading. Treating 600 such headings as
600 independent trials asserts an independence the design explicitly denies two rows above
it. To reach a 0.005 bound on the *document* unit would need **598 documents**.

**The zero-event cluster bootstrap is worse: it is degenerate.** Simulated on the outcome
this design expects (14 documents, all with zero discordances, 10,000 resamples,
seed 20260807), every resample of all-zero clusters is zero, so the percentile interval is
**[0.0, 0.0]** and the set of distinct bootstrap statistics is `{0.0}`. It carries **no**
information about a new document, precisely in the case the study is most likely to hit.

## 8.2 What is claimed instead

**The primary outcome is DESCRIPTIVE.** The study does not estimate a universal
per-heading probability, and no longer pretends to.

> On *N* fresh, structurally diverse appropriations documents comprising *H* heading
> occurrences, hybrid and corrected extended glyph produced identical heading output on
> *D* of *N* documents; the observed resolution is *r*.

Reported alongside, always: heading occurrences per document and per stratum; the D-frame
census as **raw occurrences and as documents-affected** (40 discordances on one bill is one
finding, not forty); and the content-bearing denominator for every metric.

## 8.3 The single inferential statement, if one is made

| element | frozen choice |
|---|---|
| **estimand** | π — the probability that a document drawn from the target population exhibits **≥ 1 heading-level discordance** between H and X |
| **independent unit** | **the document** (the same unit the margin and the sample-size logic use) |
| **margin on that unit** | none is pre-set, because no achievable *N* here supports a small one; the **achieved** bound is reported and the reader applies their own |
| **procedure** | exact one-sided Clopper–Pearson upper bound on π. With zero events this is the closed form 1 − 0.05^(1/N) |
| **sample-size logic** | stated as a limit, not a justification: at N ≈ 14 the tightest achievable zero-event bound is **≈ 19 %**. This holdout can **fail to falsify** equivalence and bound it loosely. It cannot establish a small per-document rate |
| **bootstrap** | used **only** where the event count is non-zero. At zero events it is degenerate (§8.1) and is not reported |
| **paired comparisons** | per-document paired differences, unweighted mean over documents, reported with per-document detail rather than as a single number |

**Overlapping independent confidence intervals are not evidence of anything** and are not
reported as such.

**What this costs, stated plainly.** The equivalence branch of the decision rule is now
carried by a descriptive result and a weak bound, not by a tight statistical guarantee. That
is a real weakening of the intended claim, and it is the honest strength of a 14-document
holdout. The architectural decision can rest on it because the decision rule's equivalence
branch defers to a **pre-stated architectural prior**, not to a precise measurement of
sameness.

---

# 9. Red team

The protocol attacking itself, before it is frozen. Each risk gets an engineered control or
an explicitly narrowed claim.

| # | risk | disposition |
|---|---|---|
| 1 | **Is either architecture used to select what gets adjudicated?** | **Yes, deliberately, and symmetrically.** The D-frame *is* the discordance set; its predicate `H ≠ X` is invariant under swapping them, so it cannot favour either. The C-frame is independent of both and is the only frame RQ2 uses. **Narrowed claim:** the D-frame cannot see a failure both share |
| 2 | **Can the oracle inherit the defect it measures?** | The oracle reads MuPDF-rendered pixels and never sees extractor output. But the C-frame's page predicate is computed from **PDFium** ink boxes. **Control:** re-run through PyMuPDF on a 10 % subsample, require ≥ 0.95 page-set agreement, else label the C-frame PDFium-conditioned everywhere |
| 3 | **Are any references derived from PDFium?** | Oracle: no. C-frame page selection: yes, controlled as above. XML: no, and it is not truth here. M7: a self-signature over each architecture's own output, explicitly not a correctness measure |
| 4 | **Are any metrics incapable of detecting the failure?** | **M5 (role) probably is** — role is the least reliable human judgement; it is gated on R1 ≥ 0.80 and may never decide. **M6 can be vacuous** if C-regions carry no amounts; 40 % of C-regions are therefore drawn from amount-bearing pages, and the content-bearing denominator is printed |
| 5 | **Can exclusions remove exactly the distinguishing cases?** | The dangerous one is `UNREADABLE` (phase 1 dropped 3 of 72). **Control:** the UNREADABLE rate is reported **split by discordance status**; if discordant regions are unreadable at a materially higher rate, the exclusion is eating the signal and the result is reported as biased. **No region may be excluded after its key is opened** |
| 6 | **Is the "fresh" holdout contaminated?** | x01 enumerates five exposure classes including git history for since-deleted paths and prose mentions across the whole research tree: 93 bills, 33 packages. **Residual, unfalsifiable:** exposure that left no trace here. **Recorded decision:** 2,963 XML-only bills are not excluded |
| 7 | **Pseudo-replication from repeated typography in one bill** | Real and severe; phase 1's six-identical-stimuli defect is this failure in miniature. Controls: document is the resampling unit; ≤ 8 C-regions per document; census reported as documents-affected as well as occurrences; region frame dedups on rendered pixel hash |
| 8 | **Clustering the analysis must respect** | Region ⊂ page ⊂ document ⊂ stratum. Cluster bootstrap by document; per-stratum and per-document tables mandatory |
| 9 | **Could the adjudicator infer architecture identity from presentation?** | It never sees either architecture's output, so there is no A/B to infer. **Residual channel:** D-frame regions are on average harder. **Control:** the blind file does not record which frame a region came from, and both frames are interleaved by one seeded shuffle |
| 10 | **Does the decision rule reward complexity?** | Built not to: X must clear δ **and** be one-directional; equivalence goes to H explicitly. The opposite bias — a rule unfalsifiable in H's favour — is answered by §7.3 naming the exact result that flips it |
| 11 | **Measuring headings, claiming financial correctness?** | Banned in text. M6 is the only metric licensing an attribution claim and has its own oracle, denominator and sabotage control |
| 12 | **Could δ be chosen to make "tie" unfalsifiable?** | δ is fixed before results, derived from a measured 652-heading document, and is 4× tighter than the prior protocol's. The achieved bound is published beside it |
| 13 | **The most likely outcome is a vacuous pass** | Pre-committed wording: *EQUIVALENT AT RESOLUTION r*, with denominators, never "the architectures agree". §7.2 rule 3 voids the run outright if the denominator cannot support a bound under δ |
| 14 | **The design pilot could be wrong in the same direction** | It **was**, first time: 98 differences that were a soft-hyphen mode artifact, now 2. A comparator that falls from 98 to 0 on a flag is exactly the kind that might be comparing nothing. **S1 is what establishes it is live** (458 differences), it runs on the holdout too, and **M0 without its S1 row is not reportable** |
| 15 | **The oracle's own frame could miss body-size headings** | The C-frame predicate cannot select a page whose headings are set at body size. **Narrowed claim** rather than a control: M1's recall is over *heading-band* headings, and the protocol says so wherever M1 appears |
| 16 | **A stratum that structurally cannot carry the metric** | Found at design time, not after: enrolled bills are declined by `_is_unnumbered_layout` and report PDFs have no production heading consumer, so both would have contributed a zero denominator. **Control:** §4.4.1 splits P-head from P-robust in advance and the adequacy count runs on P-head only |
| 17 | **"Appropriations" selected by committee referral is not "carries an account tree"** | Found by running the selection: the first pass chose three sub-6-page bills referred to Appropriations that carry no heading at all — the prior holdout's disease exactly. **Control:** GPO's title convention plus a 25-page floor, both BILLSTATUS/container facts. The superseded run is recorded in the membership artifact and nothing from it was scored |
| 18 | **A silent zero in the sampling frame reads as an empty collection** | Hit **twice**. The CRPT sitemap pattern required a trailing slash the URLs do not have and returned 0 packages; then the MODS classifier fetched from `/content/pkg` instead of `/metadata/pkg`, took 404 on all 60 candidates it examined, and reported "0 appropriations reports" — which is what a genuinely rare class also looks like. **Controls:** `stopped_on_budget` separates a budget-limited stratum from an exhausted one, and `mods_liveness` records whether the classifier could resolve *anything*, so a broken query can no longer present as scarcity |
| 19 | **The executable gate can contradict the protocol** | It did: `x04` checked 6 freeze invariants, printed `EXECUTION GATE OPEN`, and never tested the adapter or the adjudicator prompt that the prose gate required. **Control:** two separately reported gates, every prose condition is now an assertion, and `--self-test` drives each one that has a known-bad case |
| 20 | **"Frozen before selection" can be true of a superseded protocol** | It was: F4 tested the **first** commit of this file. The protocol was then materially amended in the *same* commit as the population (`1350710`), so the current protocol did **not** predate selection. **Control:** F4 now tests the **last-modifying** commit and requires a strict ancestor; the old population is withdrawn as confirmatory and its documents excluded via `design_exposure.json` |
| 21 | **A margin on the wrong statistical unit fakes precision** | δ = 0.005 on heading occurrences implied a 95 % bound of 0.005 where the document-unit bound at the same sample size is 0.193 — a **39×** overstatement — and the zero-event cluster bootstrap is degenerate at `[0, 0]`. **Control:** §8 withdraws the per-heading margin, makes the primary outcome descriptive, and confines inference to a document-unit exact bound whose weakness is stated |
| 22 | **A shared failure can be excluded and inflate absolute correctness** | Rule 0 previously dropped documents where **both** architectures lose the heading tree. That is neutral for RQ1 but is a **major negative result** for RQ2, and removing it conditions absolute correctness on successful extraction. **Control:** shared failures are neutral for RQ1 and **retained as failures** in RQ2 and M9; only §4.6's source-level exclusions may remove a frozen document |
| 23 | **A token multiset cannot represent word-boundary integrity** | It discards order and charges character errors to the seam. **Control:** §6.3 defines M3 on aligned character boundaries with explicit `TEXT_ERROR` and `UNALIGNABLE` outcomes, and `UNALIGNABLE` is reported split by discordance status |

---

# 10. Artifacts

Kept small on purpose.

```
validation/external-validity/
    PRE-REGISTRATION.md                       this file
    FINDINGS.md                               only once execution occurs
    probes/
        x00_design_pilot.py                   DESIGN: how far apart are the two seams?
        x01_contamination.py                  freshness proof; no network
        x02_oracle_reference_defects.py       DESIGN: is the XML actually disqualified?
        x03_select_holdout.py                 the frozen selection procedure
        x04_freeze_check.py                   audits the freeze invariants
    results/
        x00_design_pilot.json
        contamination.json
        x02_oracle_reference_defects.json
        holdout_membership.json               written by x03, committed before any score
```

Machine-readable membership, hashes and answer-key provenance live in `results/`. **No
number in any prose document is transcribed by hand.**

---

# 11. Deviations

Once execution starts, none of these may change silently: populations, metrics,
normalisations, thresholds, default parameters, repair rules, sampling rules, holdout
membership, the contract definition in §3.2.

Any change gets a row in `results/DEVIATIONS.md`, appended **when it happens**, carrying:
what changed old → new; when and at what stage; **whether results were already visible, and
which**; why; and which scores, rankings or gates it could move.

---

# 12. What this study cannot settle, by construction

| | why |
|---|---|
| Non-appropriations legislation | §4.1 deliberately trades breadth for the ability to exercise the downstream contract |
| Whether a second engine should be adopted | ADR 0002 has declined it; portability is carried as **PROVISIONAL** from phase 3 and is not re-measured |
| Downstream diff correctness | §6.4 — not independently adjudicable at any available budget |
| Genuine pre-publication material | Chair's marks and discussion drafts need a congressional contact; unchanged since the prior protocol |
| Windows | Everything is macOS / arm64 |
| Human-grade adjudication | Image-adjudicated until Will signs the 25-item check |

---

# Execution gate

**Two gates, machine-checked, both must hold.** An earlier version of this section listed
five prose conditions while `x04` checked only the first two and then printed
`EXECUTION GATE OPEN` — so the executable gate contradicted the protocol it was meant to
enforce. Every condition below is now an assertion in `probes/x04_freeze_check.py`, and
each one that has a constructible known-bad case is exercised by `--self-test`.

### Gate A — FREEZE INTEGRITY

| id | condition |
|---|---|
| **F1** | `results/holdout_membership.json` exists, is committed, and records a SHA-256 for every file |
| **F2** | every holdout file on disk still hashes to its recorded SHA-256 |
| **F3** | no member appears in any contamination class **or** in `results/design_exposure.json` |
| **F4** | the **last-modifying** commit of this document is a strict ancestor of the membership commit |
| **F5** | no confirmatory score file exists |
| **F6** | if adjudication has run, the answer key was committed **before** it, by git order |

### Gate B — EXECUTION READINESS

| id | condition |
|---|---|
| **G1** | the corrected extended-glyph adapter and reconstructor implementing §3.2 exist and are committed |
| **G2** | `results/x2_contract_assertions.json` exists, is committed, records `population = "DEVELOPMENT"`, checks ≥ 1 document, and reports **X2-a and X2-b both passing**. Recorded on development documents, **never** on the holdout |
| **G3** | the adjudicator prompt is committed |
| **G4** | `results/design_exposure.json` exists, is committed, and is non-empty |

**Both gates open ⇒ `EXECUTION PERMITTED` and exit 0. Anything else ⇒
`EXECUTION FORBIDDEN`, exit 1, and nothing may be scored.** The two are reported on
separate lines so "the freeze is honest" and "the machinery exists" can never again be
collapsed into one green word.

**Then, and only then**, in this order: extract → build both frames → render → write
`oracle_key.json` and **commit** → adjudicate (C-frame by AI, **D-frame by Will**, §5.5.1)
→ write `oracle_adjudicated.json` and **commit** → join → score.

**The commit boundary is part of the methodology.** The final protocol and the population
must be visibly frozen in `git log`, in that order, before any confirmatory result exists.
