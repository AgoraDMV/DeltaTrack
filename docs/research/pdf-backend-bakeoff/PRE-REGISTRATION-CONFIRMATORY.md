# Pre-registration: narrow confirmatory run

- Status: **frozen protocol. Nothing has been run against it.** Revised 2026-08-05 after
  methodological review of the first proposal, then **amended 2026-08-05 before execution**
  on four points: per-metric sabotage controls (B0), an unfillable holdout stratum (P2 #8),
  gold-sample blinding, and an inside-the-sandbox known-bad control. All four were amended
  **with no results visible**, which is why they are amendments and not deviations —
  the [DEVIATIONS](#deviations) table opens when the first score is produced.
- Supersedes the 2026-08-05 *proposal* of the same name. It supersedes nothing else.
  [`PRE-REGISTRATION.md`](PRE-REGISTRATION.md) remains the record of what the exploratory
  spike committed to; [`RESULTS.md`](RESULTS.md) remains the authoritative record of the
  exploratory spike and its audit, and **is not to be rewritten by this run**.
- Once execution starts, every change to this document goes in
  [`results/DEVIATIONS.md`](results/) — see [§ Deviations](#deviations).

## What the exploratory record keeps saying, unchanged

This run does not edit, delete or "correct" the exploratory findings. `RESULTS.md` keeps,
verbatim: the original findings as published; the adversarial audit; the withdrawn
"PDFium-WASM is the best backend" claim; T4 reclassified as production migration parity;
pdfminer's stronger showing on incumbent-independent metrics; the repaired-mode bias toward
PDFium; all nine post-registration methodology changes; the narrowed security claim; the
corpus-diversity limitation; and the `@embedpdf/pdfium` provenance follow-ups.

**The exploratory spike is exploratory.** This run is a prospective replication under a
protocol frozen in advance, plus a first look at data none of these probes has ever seen.

## The three concerns, and why they are never combined

| Concern | Reference | Licenses the conclusion |
|---|---|---|
| **A. Production migration parity** | today's pypdfium2 output | "safe to swap without changing what staffers see" |
| **B. Independent document accuracy** | XML and adjudicated page images, never PDFium | "reads the document correctly" |
| **C. Security / egress** | network-layer observation | "cannot transmit under policy P / in environment E" |
| **D. Performance** | wall clock on an idle machine | "fast enough, and how much faster" |
| **E. Bundle / architecture** | built browser artifacts | "costs this much to deliver" |
| **F. Supply-chain release readiness** | upstream sources | "can be adopted and re-derived" |

**No composite score. No single "best backend" table. No verdict that spans two rows.**
Substituting an A result for a B conclusion is what produced the withdrawn headline, and it
is the single failure this document exists to prevent.

**Candidates: `pdfium-wasm` and `pdfminer.six`.** pypdf failed and PyMuPDF is
policy-excluded (AGPL); re-running them adds noise. **PDF.js is out of A and B** — its
exploratory score belongs to `getTextContent()`, not to the library, and the operator-list
adapter that would fix that is not being built (see
[§ Unresolved design choices](#unresolved-design-choices)). It stays in **E** only, where
its artifact is already installed and the measurement is nearly free.

---

# Populations

Three, kept apart in every table.

## P1 — replication corpus (52 documents, 30 bills)

The existing corpus, derived at runtime from `tests/corpus/*` by
`score_phase1.corpus_documents()`. **This is no longer unseen data**: it has been inspected,
methodology was tuned against problems found in it, and the backend results are known.

**It can only answer one question: do the exploratory findings survive the frozen
protocol?** Nothing measured on P1 generalizes on its own.

## P2 — holdout corpus (target 12 bills, never scored by any probe)

### Frozen selection procedure

Executed **before** either candidate runs, output committed to
`results/holdout_membership.json`, and never revised afterwards.

1. **Frame.** govinfo BILLSTATUS for Congresses 113–119, all bill types, via
   `tools/fetch_govinfo.py`. A bill is eligible if it has **≥ 2 text versions that each
   carry both PDF and XML** at `content/pkg`.
2. **Exclusions**, enumerated into the membership file at selection time rather than
   assumed: the 30 replication bills; every non-corpus probe fixture (`118-s-4795`,
   `CRPT-118srpt198`, the nine subcommittee prints); and **every bill present in the main
   checkout's `bills/` working tree**, because that material has been looked at.
3. **Strata**, filled in this fixed order, one bill per row unless stated:

   | # | Stratum | Bills | Diversity axis it buys |
   |---|---|---|---|
   | 1 | Non-appropriations House bill, 118th or 119th | 2 | bill type |
   | 2 | Non-appropriations Senate bill | 2 | bill type + chamber |
   | 3 | Joint resolution (`hjres` / `sjres`) | 1 | bill type |
   | 4 | Appropriations bill from 113 / 114 / 116 / 119 | 2 | Congress (under-represented in P1) |
   | 5 | Bill whose longest version is **< 20 printed pages** | 2 | document length |
   | 6 | Bill whose longest version is **> 400 printed pages** | 1 | document length |
   | 7 | Bill with a watermarked Senate print (`rs` / `pcs`) | 1 | watermark / layout |
   | 8 | Bill with a chamber-crossing amendment print (`eah` / `eas`) | 1 | typeface class — DeVinne-Italic, only 5 documents in P1 |

   **Stratum 8 changed, because the original was unfillable by P2's own rule.** It asked for
   a conference report or a committee print. Neither is a bill: they carry no bill XML and
   have no adjacent-version pairs, so neither can satisfy "≥ 2 versions each with PDF and
   XML", and a stratum that can never fill would have silently spent the adequacy budget.
   **Conference reports and committee prints move to P3a**, where they can be tested for
   robustness and safe failure without an XML reference.

   **Honest limit on the typeface axis:** the BILLS collection offers effectively three
   typesetting classes — DeVinne, DeVinne-Italic and NewCenturySchlbk-Roman (enrolled) —
   and **P1 already contains all three**. P2 can add new *bills* within those classes and
   can thin out P1's concentration; it cannot add a fourth class. Any GPO production class
   beyond those three is reachable only through P3, without XML.

4. **Within a stratum**: candidates sorted by bill id, permuted with seed **20260805**, and
   the first that satisfies the two-dual-format-versions rule is taken. Ties are broken by
   the permutation, never by inspection.
5. **Recorded before scoring**: bill id, package ids, version codes, page counts, SHA-256 of
   every file, and which stratum each bill filled.

### Adequacy rule, pre-committed

- **≥ 8 of the 8 strata filled** → holdout supports a generalization claim.
- **5–7 filled** → holdout is reported, and the claim is *"replicates, and extends to the
  classes actually sampled"*, with the unfilled strata named.
- **< 5 filled, or the fetch fails** → **the holdout is declared unobtainable**, no
  generalization claim is made, and the whole run is downgraded to
  **locked-protocol replication**. That downgrade is written into the results headline, not
  a footnote.

### The rule that makes a holdout a holdout

**No holdout result may change a metric, threshold, normalization, parameter, adapter,
repair rule or population.** A backend crashing on a holdout document is a *result*, not a
bug to fix mid-run. If something must change anyway, it is a deviation and every affected
score is re-labelled non-confirmatory.

## P3 — non-corpus robustness probes (renamed)

The exploratory "Tier B" section is renamed **non-corpus robustness probes**, because
eleven of its twelve fixtures are published GPO Tier A prints. It is not a pre-publication
test and never was.

| Sub-population | Fixtures | What it can support |
|---|---|---|
| P3a real, non-corpus GPO | the existing 12, **plus one real conference report (`CRPT-*`) and one real committee print (`CPRT-*`)**, both required | robustness and safe failure across GPO print classes. **No accuracy metric** — these have no XML reference and are not bills |
| P3b synthetic degradations | a rasterized (image-only) corpus PDF; a non-GPO producer PDF generated locally | **safe-failure only, never accuracy** |

**Source classes that remain unvalidated after this run**, listed in the results as a
standing section rather than a caveat: chair's marks; discussion drafts; genuinely
pre-publication committee documents; Word-generated legislative drafts; real (not
synthesized) image-only or scanned PDFs; conference-report and committee-print layouts as
*accuracy* claims, since P3a can only test robustness and safe failure on them; other
non-GPO PDFs. Obtaining real pre-publication material needs a congressional
contact and is outside what any protocol here can arrange.

### Safe failure is a first-class gate

For every P3 fixture, record which of three things the production entry point does:

| Outcome | Meaning |
|---|---|
| **DECLINES** | raises `UnsupportedLayoutError` — the safe outcome |
| **ANSWERS** | returns a diff with anchors |
| **ANSWERS ANCHORLESS** | returns a diff with **zero** anchors — a confident wrong answer |

**Gate S-1: no fixture may land in ANSWERS ANCHORLESS.** The exploratory run produced
exactly that state once (3,468 amount entries against the XML's 0, on an enrolled pair
reached by bypassing the guard), which is why this is a gate and not an observation.

---

# Concern A — production migration parity

**Question.** If we replace pypdfium2 with candidate X, does any output production currently
returns to users change?

**Reference: today's native pypdfium2 through the identical downstream pipeline.** That is
correct *here* and nowhere else — this section is about migration compatibility, not
correctness.

### Frozen population and strata

**All 15 consecutive corpus pairs, always all 15 visible**, in two strata:

| Stratum | N | Role |
|---|---|---|
| **Production-accepted** | 13 | **the migration gate** |
| **Production-declined** (`115-hr-5895/4→5`, `118-hr-4366/5→6`) | 2 | unsupported-layout **diagnostics**, scored with the guard bypassed |

Membership is derived at runtime from `compare/pdf.py::_is_unnumbered_layout`, never
hardcoded: if production's guard changes, the strata change with it and the run says so.
Holdout pairs (P2) are scored under the same rules and reported separately.

### Frozen metrics

| ID | Metric | Definition |
|---|---|---|
| A1 | Amount identity | `Counter[(old, new, kind)]` over all `amount_entries` equals the incumbent's, exactly |
| A2 | Change identity | `Counter[(change_type, norm(old), norm(new))]` equals the incumbent's, exactly |
| A3 | Amount F1 | precision / recall / F1 of the A1 multiset, for when A1 fails |
| A4 | Full-text identity | SHA-256 of `pdf_full_text` output equals the incumbent's |
| A5 | Line-number identity | exact `(page, line)` set equals the incumbent's |

`norm()` is frozen as the current `score_phase2.norm_text` (whitespace runs,
`normalize_glyphs`, soft-hyphen rejoin, margin line numbers, U+FFFD removal).
**Widening it later is a protocol violation**, because every widening inflates agreement.

A5 moved here from the exploratory Concern-B metric set: its reference is the incumbent, so
it is a parity measurement, not an accuracy one.

### Frozen gates

| Gate | Threshold | Name |
|---|---|---|
| **A-1** | A1 holds on **13/13** production-accepted pairs | production migration parity |
| **A-2** | A2 holds on **13/13** production-accepted pairs | production migration parity |
| **A-3** | A4 holds on all production-accepted documents | production migration parity |
| **A-4** | A1 **and** A2 hold on **15/15** including the 2 declined | *backend equivalence beyond supported production behavior* |

**Pass = A-1, A-2 and A-3.** A-4 is reported separately and is explicitly **not** production
migration parity — the two declined pairs are not staffer-visible output and must not decide
whether a migration is safe today. A candidate that passes A-1 but fails A-2 is reported as
*"money-safe, segmentation-divergent"*, which is a real intermediate state, not a pass.

### Repair mode for Concern A

**Primary: `repaired` — the mode we would actually ship.** A deterministic backend adapter
normalizing a known source-library quirk is part of the intended production implementation;
production already does the equivalent for the text API in `normalize_raw`.
**`strict` is reported as a diagnostic on every metric.** A1/A2 are mode-identical anyway,
so this costs nothing and it stops the migration gate from being graded against a mode
nobody would ship.

---

# Concern B — independent document accuracy

**Question.** Which candidate most accurately recovers the underlying legislative document,
when PDFium is not the reference?

**No metric in this section may take a PDFium-derived value as ground truth.** Excluded by
name: incumbent breadcrumb agreement; incumbent line-number sets; T4; and any expected value
computed by running PDFium. If a metric cannot be computed without PDFium, it does not
belong here.

**Reported separately for P1 (replication) and P2 (holdout). Never pooled.**

### Frozen population

- **Production-accepted documents** are the primary population. Enrolled documents are
  reported separately and never merged in.
- **Stratified by body font** (`DeVinne` / `NewCenturySchlbk-Roman` / `DeVinne-Italic`),
  because the audit found P1 is effectively one typesetting class and an aggregate hides it.
- **Per-bill results are mandatory.** One bill supplies 6 of 52 P1 documents.

### Frozen metrics

| ID | Metric | Reference | Definition |
|---|---|---|---|
| B1 | Text recovery F1 | XML body | Multiset token F1 after `align_to_body` edge-trim, both frozen as implemented today. Unaffected by DeltaTrack#11 — the reference is a raw `extract_text_content` walk that includes `<quoted-block>` text |
| B2 | **Heading-label recovery** F1 | XML tree | **Level-agnostic**: PDF anchors of kind {account, agency, grouping} against XML labels of level {account, agency, heading}; upper-cased, commas and periods stripped |
| B3a | Line-number self-consistency | the document itself | Per page: recovered margin numbers form a gap-free run `1..n`, and `n` equals the count of numbered body lines. **No external reference** |
| B3b | Line-number exactness | adjudicated page images | Exact `(page, line)` match on gold-sample pages only |
| B5 | **Amount → heading association** | XML tree | For amounts present on **both** sides, F1 over the multiset of `(amount, nearest heading-ish ancestor label)` pairs. Restricting to shared amounts isolates *association* from *detection* |
| B6 | **Parent/child heading correctness** | XML tree | For each PDF heading whose label matches an XML heading, accuracy of its immediate heading-ish parent's label against the XML node's |
| B7 | Independent-extractor corroboration | PyMuPDF `get_text()` | Sampled amounts appear in an unrelated extractor's text on the side claimed. **Corroboration, not ground truth** |
| B8 | Gold-sample agreement | adjudicated page images | Per-item agreement on the gold set (see below) |

**B2 measures heading-label recovery, not structural accuracy.** A backend can find every
heading and attach them all wrongly. B5 and B6 exist because that failure is the one with a
product consequence: heading attachment is what puts an amount under the right agency and
account in the financial tables.

**B2 is level-agnostic by pre-commitment, and this is load-bearing.** A level-by-level
comparison produced a *false reversal* during the audit (PDFium appearing to over-detect
accounts 46-to-27) because the two pipelines name the same objects differently — the XML's
`agency` holds `Military construction, air force`, which the PDF calls an `account`.

**DeltaTrack#11 scope, stated per metric rather than globally:** B2, B5 and B6 read the
parser tree, which drops `<quoted-block>`; **25 of the 52 P1 XMLs carry one**. Those documents
are reported in their own stratum for B2/B5/B6 and are excluded from the primary figure.
B1 and B3 are unaffected.

**B2 is new code at population scale.** The exploratory 0.5864 / 0.6253 heading figures are
means over the **six** documents in `redteam_ablation.py`, not over 52. Confirmatory B2 will
not be numerically comparable to them, and the results must say so rather than appear to
replicate a number it never measured.

### B0 — harness sensitivity controls (a gate on the metrics, not on the backends)

A metric that cannot distinguish good extraction from bad cannot rank anything, and an
all-green sweep looks identical either way.

**One uniform sabotage is not enough.** A 5 % random glyph dropout garbles text but barely
touches heading attachment, so a metric that survives it may be blind rather than robust —
and declaring it void on that evidence is itself a false negative. **Each metric therefore
gets its own sabotage, injecting the specific fault that metric claims to catch**, applied
to `pdfium-wasm` glyph output with seed 20260805. Glyph field indices are
`contract.GLYPH_FIELDS`.

| ID | Targets | Injected fault | Must happen |
|---|---|---|---|
| **S1** | B1 | delete 5 % of glyphs, uniformly at random | B1 falls |
| **S2** | B2 | on every line whose max `font_size` exceeds the page's dominant body size, set all its glyphs to the line median — collapsing the small-caps size band | B2 falls |
| **S3** | B3a | delete the leading margin-number glyph run on 5 % of numbered lines | B3a falls |
| **S4** | B5 | shift heading lines' `baseline`/`y0`/`y1` down one body line-height: headings keep their text, but attach to the wrong block | B5 falls **while B2 moves less than 0.020** |
| **S5** | B6 | delete agency-level heading lines only, keeping accounts, so their children reparent | B6 falls **by more than B2 does** |
| **S6** | B7 | relabel a sampled amount's side (old ↔ new) | the corroboration check flags it |
| **S7** | B8 | the ten corrupted gold items (wrong amount, wrong heading, wrong line number) | the scorer flags all ten |
| **SA1** | A1 | perturb one digit of one amount | A1 **fails** |
| **SA2** | A2 | delete one change block's glyphs | A2 **fails** |
| **SA3** | A4 | delete a single glyph | A4 **fails** |

**The discriminating requirements on S4 and S5 are the point, not decoration.** S4 leaves
every heading label intact and only moves where it sits; if B2 falls as far as B5 does, then
B2 and B5 are measuring the same thing and the association metric adds nothing. Same for S5
against B6.

Pre-committed verdicts:

- **B1, B2, B3a, B5, B6** — a metric whose own sabotage does not move it **beyond that
  metric's practical threshold** is **void for this run**, reported as void, and its Δ is
  not published as evidence.
- **B7 and B8** have no Δ and no threshold; their controls (S6, S7) are pass/fail. A missed
  flag voids that metric outright.
- **A1, A2, A4** — a gate its own sabotage does not fail is void, and a candidate's pass on
  a void gate is not evidence of parity.
- Where a discriminating requirement fails, the two metrics involved are reported as
  **not separable** — a different finding from either being blind, and it must not be
  written as one.

**Sabotage variants are scored as their own pseudo-backends. They are never pooled with the
candidates, never enter Δ, and never appear in a ranking table.**

### Statistics: paired cluster bootstrap by bill

Documents from one bill are correlated and some bills contribute far more documents than
others, so documents are not independent draws.

| Element | Frozen choice |
|---|---|
| Resampling unit | **the bill**, sampled with replacement; all of a sampled bill's documents travel together |
| Statistic | **Δ = score(pdfminer) − score(pdfium-wasm)**, paired per document, defined once and never inverted |
| Aggregation | per-bill mean of the paired per-document Δ, then the **unweighted mean over sampled bills** |
| Secondary | document-weighted aggregation, reported as a sensitivity check only |
| Resamples | 10,000 |
| Seed | 20260805 |
| Interval | percentile 95 % CI on Δ |

**Overlapping independent CIs are not evidence of anything and are not reported as such.**
That comparison is removed from the protocol.

### Practical-effect thresholds, chosen before seeing any confirmatory result

A backend **leads** on a metric only if **both** hold: the paired cluster-bootstrap 95 % CI
for Δ excludes zero, **and** |Δ̂| ≥ the threshold below. Statistical significance alone
never moves an architecture decision.

| Metric | Threshold | Why this number |
|---|---|---|
| B1 text F1 | **0.010** | Residual headroom to the XML is ~0.087 (the settled format gap), so 0.010 is ~11 % of everything achievable — and ~1,800 tokens on a 180k-token enrolled bill |
| B2 heading F1 | **0.020** | `118-hr-4366/1` carries 48 accounts and 18 agencies; at that scale 0.02 F1 ≈ 1.3 headings, i.e. one account's worth of the financial data contract |
| B3a self-consistency | **0.005** | Line numbers are the staffer's citation handle; 0.005 on a 1,000-numbered-line document is 5 unciteable lines |
| B5 amount→heading | **0.010** | One amount in 100 filed under the wrong account is a wrong number in a staffer's table |
| B6 parent/child | **0.020** | Same unit as B2 |

**If neither statistical nor practical superiority is established, the pre-committed
sentence is: "the backends are accuracy-indistinguishable on the available evidence."**
The exploratory 0.9131-vs-0.9126 ordering is below every threshold here and would be
reported as indistinguishable.

### Repair mode for Concern B

**Primary: `strict`. Secondary: `repaired`. The per-backend repair delta is reported for
both candidates on every metric.** A repair that lifts one backend by +0.0345 and every
other by 0.0000 is a fact about the metric, and burying it in a default is how the
exploratory ranking went wrong.

### The soft-hyphen repair must be tested for false repairs

Testing only whether a repair *helps* is testing one direction of a two-directional rule.

**False-repair probe.** For every line-final unnamed glyph PDFium reports, join positionally
(page, baseline ±0.6 pt, x0 ±0.5 pt) to the other backends' glyph streams and read what they
resolve it to. **A repair is false when ≥ 2 other backends agree the glyph is not
hyphen-like** (`-`, U+2010, U+2011, U+00AD).

- **Reported: false-repair count, rate, and the per-document distribution.**
- Run on P1 **and** P2 separately, because a positional rule that holds on one typesetting
  class need not hold on another. **Gate B-R: the false-repair rate on the holdout may not
  exceed the replication rate by more than 2×**; exceeding it means the rule is
  corpus-shaped and must be reported as such.

### Mandatory parameter-sensitivity tests

| Parameter | Settings | Default | Rule for claiming a lead |
|---|---|---|---|
| `_SPACE_FACTOR` | 0.15, 0.20, **0.25**, 0.30, 0.40 | 0.25 | lead at **≥ 4 / 5** |
| `_BASELINE_TOL` | 0.1, 0.3, **0.6**, 1.2, 2.0 | 0.6 | lead at **≥ 4 / 5** |
| `_CHROME_SIZE_RATIO` | 0.0 (off), 0.45, **0.55**, 0.65 | 0.55 | lead at **≥ 3 / 4** |
| `upright` filter | on / off | on | **ranking must not reverse** |
| repair mode | strict / repaired | strict (Concern B) | **ranking must not reverse** |

**Raw sensitivity magnitude is reported for every cell.** A backend whose metric moves by
**> 0.05** across a parameter's sweep is labelled **parameter-fragile on that metric**, next
to its score.

**Sensitivity at an arbitrary alternate setting is not itself evidence of inaccuracy.** The
question the sweep answers is narrower: *does a claimed lead depend on a PDFium-tuned
default?* A lead that exists only at the default is reported as
*"leads at the default parameterization only"*.

### Default-value audit — done before freezing, and it found two mismatches

§7 of the review asked that every bold default be verified against the implementation.

| Constant | Probe (`reconstruct.py`) | Production (`parsers/pdf_text.py`) | Verdict |
|---|---|---|---|
| `_SPACE_FACTOR` | 0.25 | **0.25** | **matches** — genuinely inherited from PDFium-tuned production |
| `_BASELINE_TOL` | 0.6 **points, absolute** | `_BASELINE_TOL_FACTOR = 0.5 × median glyph size`, **a fraction** | **different parameterization**, not a different value of the same knob |
| `_CHROME_SIZE_RATIO` | 0.55 | **no counterpart** — production strips chrome by regex on text | **spike-invented** |

Consequence, pre-committed so it cannot be reinterpreted later: only `_SPACE_FACTOR`
supports the audit's "a PDFium-tuned constant inside the neutral layer" framing. Sensitivity
in the other two is a property of **this harness**, and a candidate that looks fragile there
is fragile in a layer production does not have. Both readings are reported; neither is
allowed to borrow the other's interpretation.

---

# The gold sample

PyMuPDF is a second implementation, not an oracle. This is the only reference in the
protocol that depends on neither a PDF library's text layer nor the XML.

### Honest naming

The review asked for a **human-adjudicated** gold sample. **No human is at the keyboard for
this run.** What is built is an **image-adjudicated gold sample**: the execution agent reads
page images and records the fields. Rendering uses **macOS CoreGraphics** (`sips` /
`qlmanage`), an implementation independent of PDFium, pdfminer, PyMuPDF and PDF.js.

**This is weaker than human adjudication and is labelled that way in every table.** A
20-item seeded subsample is written to `results/gold_human_check.md` for Will to verify by
hand; **until he signs it off, every gold-derived number is published as provisional.**

### Frozen construction

1. **Frame.** The union of all six backends' outputs **and** the XML, over the
   production-accepted P1 documents. Union rather than any one backend, so no candidate's
   blind spot silently removes items from the frame — and items only one backend sees are
   the most informative ones in it.
2. **Sampling.** Seeded shuffle within each stratum, seed **20260805**, first N taken. The
   frame size and selection index of every item are recorded, so the sample is reproducible
   without re-running the shuffle.
3. **Strata.**

   | Financial (50) | N | | Structural (50) | N |
   |---|---|---|---|---|
   | Backends disagree on the line | 10 | | Backends disagree on presence or level | 10 |
   | Inside a long appropriations block (> 40 lines, no heading) | 8 | | Small-caps account headings | 12 |
   | Within 3 lines of a heading transition | 8 | | Agency headings | 8 |
   | Within 2 printed lines of a page boundary | 8 | | At a page boundary | 8 |
   | On a line carrying a soft hyphen | 6 | | On a watermarked page | 6 |
   | On a watermarked page | 6 | | Grouping / title headings | 6 |
   | Table-like layout (≥ 3 numeric columns) | 4 | | | |

   Additions and deletions are drawn across both halves rather than as a stratum, so a
   change item always carries its own before/after context.
4. **Recorded per item**: document; page; printed line number(s) where the page has them;
   exact source text of the line; the heading / account / agency context as printed; the
   amount as printed; and for change items the expected relationship.
5. **Blinding.** The frame is built from backend output, so the sampler knows every
   candidate's answer. **The adjudicator must not.** The sampler writes two files:

   | File | Contents | Read by the adjudicator? |
   |---|---|---|
   | `gold_key.json` | item id → document, page, **which backends contributed and what each said**, XML value, stratum | **no** — committed, then not opened until scoring |
   | `gold_blind.json` | item id → document, page, rendered image path, **a geometric locator (bounding box in PDF points)**, and the question | **yes — this is all it sees** |

   A blind record carries **no backend name, no candidate text, no XML value, and no stratum
   label**. Localisation is by bounding box, because a box says *where to look* without
   saying *what is there*. Items are presented in a seeded shuffle (20260805) across all
   strata, so neighbouring items do not reveal which cell — and therefore which expected
   difficulty — an item came from.

6. **Ordering, enforced by hash rather than by intent.** The adjudicated answers are written
   to `gold_adjudicated.json` and **committed, with their SHA-256 recorded, before
   `gold_key.json` is joined to them**. The join is a separate committed script. The commit
   order is the evidence that adjudication preceded exposure; "I adjudicated first" is not.
7. **Proof the gold set can fire.** Ten deliberately corrupted items (wrong amount, wrong
   heading, wrong line number) go into a separate control file. **The scorer must flag all
   ten.** A scorer that passes the control silently cannot distinguish a correct backend
   from a broken comparison, and the run is void for B8.
8. **Blinding residue that cannot be removed, stated rather than papered over.** The
   adjudicator is the same agent that has read `RESULTS.md` and therefore carries the
   exploratory prior that pdfminer led the independent metrics. No file-level blinding
   removes that. It is a standing limitation on B8, it is one of the reasons the 20-item
   human check exists, and **B8 alone may never decide a ranking** — it corroborates or
   contradicts B1–B6, which are computed without an adjudicator.

---

# Concern C — security / egress

### Threat model, stated before any policy is tested

| | Threat A | Threat B |
|---|---|---|
| **What** | DeltaTrack accidentally or deliberately includes ordinary application networking | Arbitrary or malicious code executing inside the browser tries to exfiltrate document data through any browser capability |
| **What this run can establish** | **Strong controls.** A policy plus network-layer observation genuinely covers this | **Bounds, not impossibility.** The exploratory run already disproved impossibility via WebRTC and `window.open` |

**Pre-committed: no result in this section may be written as "exfiltration is impossible",
"zero egress", or "permits no subresource or background network egress."** Every claim names
its policy or its environment.

### Frozen policy under test

```
default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src data:;
connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none';
frame-src 'none'; worker-src 'none'
```

`script-src 'self'` **without** `'unsafe-inline'`. The exploratory policy included it and was
defeated by Speculation Rules as a direct result. The cost is real and is reported: the
engine must load from external script files, which complicates a single-file artifact.

### Frozen vector set

The union of [`vectors.js`](probes/vectors.js) (16) and [`vectors2.js`](probes/vectors2.js)
(19) — **35 mechanisms**, enumerated in those files so the list cannot drift from the code.
Coverage for the exploratory bypasses is retained by name and may not be dropped:
**WebRTC / STUN, `window.open`, top-level navigation, Speculation Rules.**

**Adding a vector is encouraged and is not a deviation. Removing one is.**

### Per-vector observability replaces the global control threshold

The old rule ("control must leak on ≥ 12 of 35") let a vector that never worked in the
control be silently counted as "blocked by policy". In the exploratory round-2 run, five
vectors did exactly that (`link-dns-prefetch`, `link-preconnect`, `track`, `svguse`,
`webtransport`).

**Every vector receives a control status first:**

| Control status | Meaning | Eligible for "blocked by policy"? |
|---|---|---|
| **CONTROL TRANSMITTED** | the canary arrived at the server with no policy | **yes** |
| **CONTROL UNSUPPORTED** | the mechanism does not exist or threw in this browser | **no — not scored** |
| **CONTROL FAILED / VOID** | the mechanism ran but nothing arrived, cause unknown | **no — not scored** |

Then, for each supported mechanism: execute it, transmit a **unique canary derived from a
dummy document**, and observe at the receiving network layer whether that canary arrives.

**Canary format** (replacing the exploratory constant `secret=BILLTEXT`):
`DELTATRACK_SECRET_<vector>_<sha256(dummy-doc)[:12]>`. A per-vector unique value means a
received request proves *which* mechanism carried *document-derived* bytes, not merely that
some request happened. WebRTC is the one exception — a STUN binding request carries no
arbitrary payload — and is reported as **signal-only, not canary-bearing**.

**Reporting shape**, all four columns always present:

| vector | control | policy result | notes |
|---|---|---|---|
| … | transmitted marker | **blocked** | |
| … | transmitted marker | **bypasses CSP** | |
| … | transmitted marker | **outside CSP** | no directive governs it |
| … | unsupported | **not scored** | |

**CDP request events are recorded as diagnostics and never decide**, because a request
object exists before CSP rules on it. The server's received-request log decides.

### Frozen validity conditions

A run is **void**, not negative, unless all four hold:

1. **Per-vector control status assigned** for all 35, with at least one TRANSMITTED.
2. **Known-bad caught** — a build carrying the policy plus one deliberately permitted beacon
   is detected.
3. **Vectors ran** — the fixture reports `DONE` and a vector count equal to the frozen set.
   *(A `script-src` variant once reported "0 bypasses" with 0 vectors executed: the policy
   had blocked the harness's own bootstrap. That is void, not a pass.)*
4. **Observation at the network layer**, over both TCP and UDP.

### Environment-level isolation, as a separate and stronger claim

Browser policy and environment isolation support different sentences, and conflating them is
the same error as conflating A with B.

| Test | Claim it supports |
|---|---|
| Browser policy | "our app does not transmit through these mechanisms" |
| Environment isolation | "the process cannot reach the network at all" |

**Frozen procedure.** Run a full PDF comparison with outbound networking denied outside the
page, and require it to **succeed**:

- **Primary (available now): macOS `sandbox-exec` with `(deny network*)`.** Verified during
  protocol design: a sandboxed `curl` to a public host fails DNS resolution.
- **Stronger (attempted): a Linux container with `--network none`.** The Docker daemon is
  **not running** on this machine at freeze time; if it is unavailable at execution time this
  is recorded as **NOT RUN**, never inferred from the macOS result.
**Proof the isolation check can fire.** An unsandboxed run reaching the observation server
proves only that the *server* works; it says nothing about whether the sandboxed run's
silence came from the sandbox or from a dead listener, and it is evidence gathered in a
different environment from the one under test. **Both halves must run, and both inside the
same invocation window:**

| Control | Where it runs | Required outcome | What it establishes |
|---|---|---|---|
| **known-bad, inside the sandbox** | in the sandboxed process, alongside the comparison | **no request received** | the silence is attributable to the sandbox, not to the app happening not to call out |
| **observer liveness, outside the sandbox** | the harness process, same run, same listener, overlapping window | **request received** | the listener was alive and observing throughout — so "nothing received" means blocked, not unwatched |

Neither alone is sufficient: the first cannot distinguish a working sandbox from a dead
listener, and the second cannot attribute anything to the sandbox. **A run missing either
control is void, not a pass.**

Per the rule that a guard's probe must be inert if the guard fails open, both beacons target
`127.0.0.1:8973` — our own listener — carrying a canary. If isolation fails open, the worst
outcome is a loopback request we wanted to see anyway.

A third check separates loopback from the network generally: **a sandboxed request to an
external host must fail to resolve**, so a pass cannot come from loopback being blocked by
something other than the policy. Verified during protocol design; re-run and recorded each
time.

---

# Concern D — performance

The exploratory gate-9 verdict for pdfminer **did not reproduce** (37.9 s, then 69.2 s,
against a 60 s ceiling). Absolute timings in this spike are not reproducible to better than
~1.5×.

| Element | Frozen choice |
|---|---|
| Machine state | Load average **< 1.0** at start, verified and recorded. Above that, the run is **void** |
| Trials | **minimum of 5**, reported as min / median / spread. The **minimum** is the estimator |
| CPU time | recorded alongside wall time; material divergence means contention, and the run is void |
| Concurrency | one backend at a time, never alongside another probe |

| Gate | Threshold |
|---|---|
| D-1 | Largest corpus document (`119-hr-1/1`, 1118 pp) extracts in **< 60 s**, min-of-5, in-browser |
| D-2 | Within **3×** the incumbent's native full-document time, min-of-5 |

**A candidate whose min-of-5 straddles the ceiling is `UNRESOLVED`, never rounded.** That is
pdfminer's current state. Relative claims survive contention and may still be made; absolute
threshold claims may not.

---

# Concern E — bundle size and architecture

The axis the PDFium-WASM-vs-pdfminer decision most likely turns on, and the exploratory run
did not measure it. Build **real browser artifacts** for both finalists (plus PDF.js, whose
artifact is nearly free), then measure:

| Measurement | Unit |
|---|---|
| Total artifact size | uncompressed / gzip / brotli bytes |
| Incremental backend size | bytes over a common Pyodide + DeltaTrack baseline |
| First load (cold cache) | ms to interactive |
| Repeat load (warm cache) | ms to interactive |
| Pyodide + package initialization | ms |
| Full comparison latency | ms, min-of-5, under the Concern-D idle rules |
| Peak memory | MB |
| JS↔Python transfer | bytes and copy count per document |
| `file://` behavior | works / degraded / fails, per artifact |

**Pre-committed: do not optimize the 132 MB JS→Python glyph transfer in this run.** Measure
it first; optimize only if the measurement shows a real memory or latency problem. An
unmeasured optimization is how a spike acquires work nobody asked for.

---

# Concern F — `@embedpdf/pdfium` release readiness

Kept entirely separate from backend accuracy. Nothing here can rank a backend; it can only
gate adoption.

| Item | What must be established |
|---|---|
| Source revision | the exact upstream revision corresponding to the shipped WASM |
| Fork provenance | what `embedpdf/runtime` is, and how it relates to upstream PDFium |
| Fork patches | the diff against upstream, reviewed |
| Licence obligations | full licence + NOTICE set for everything bundled |
| Vendored third-party | enumerated (`zlib` is confirmed present by string inspection; the rest is open) |
| Reproducibility | whether the shipped artifact can be rebuilt from source independently |
| Vendoring | whether DeltaTrack can vendor a reviewed, checksummed WASM |
| Disappearance | the recovery path if the package or fork goes away |

**npm package metadata is a lead, not evidence.** The declared `repository.directory`
(`packages/pdfium`) does not exist in that repo's current `main`, and the npm licence (MIT)
disagrees with the upstream repo's own `LICENSING.md` (Apache-2.0 for `packages/`) — so the
metadata is already known to be unreliable here.

**Pre-committed release-readiness requirement:** DeltaTrack must **either** independently
reproduce the WASM build **or** vendor a reviewed, version-pinned, checksummed artifact tied
to documented source and third-party notices. Failing both is a **blocker for shipping**,
never a mark against measured accuracy.

---

# Cross-cutting rules

1. **No composite score.** Not across concerns, not within one.
2. **Seeds fixed at 20260805** for every sample, shuffle and bootstrap.
3. **Environment recorded with the results**, and re-stated next to any number quoted
   elsewhere. Still macOS 15 / arm64 until someone runs it on Windows.
4. **Raw outputs are immutable.** Every published table is generated from them by a
   committed script, never transcribed.
5. **The exploratory record is not edited.** Corrections to it go in this run's results,
   pointing at it.

## Deviations

Once execution starts, these may not change silently: populations; metrics; normalizations;
thresholds; default parameters; repair rules; sampling rules; holdout membership.

Any change gets a row in `results/DEVIATIONS.md`, appended **when it happens**, not
reconstructed afterwards:

| Column | Content |
|---|---|
| Change | exactly what changed, old → new |
| When | timestamp and stage |
| Results already visible? | **yes / no** — and which |
| Reason | why |
| Could move | which scores, rankings or gates |

Then continue only if the result is still interpretable. If it is not, the affected numbers
are published as exploratory, not confirmatory.

---

# Decision rules

Applied in order. **"Best backend" is not an available output unless rule 1 fires.**

1. If one candidate has a **clear, practically meaningful, independently validated** accuracy
   advantage on **both** replication and holdout data, surface that tradeoff explicitly.
2. If independent accuracy is indistinguishable, then **migration risk, performance, bundle
   size, maintainability and supply-chain risk become legitimate tie-breakers** — and the
   decision is written as a tie-break, not as an accuracy finding.
3. **PDFium-WASM's exact production parity is evidence for migration safety, not for
   independent correctness.**
4. **pdfminer's stronger exploratory independent metrics are evidence worth testing, not
   proof that it is more accurate.**
5. **Every security conclusion names the exact policy or environment under which it holds.**

---

# What this run cannot settle, by construction

- **Genuine pre-publication material.** Chair's marks, discussion drafts and real committee
  drafts do not exist in the repository and cannot be fetched; they need a congressional
  contact. This is the material ADR 0010 says the PDF pipeline exists for.
- **Windows.** Everything is macOS 15 / arm64.
- **PDF.js's true capability**, since the operator-list adapter is not being built.
- **Real scanned/image-only PDFs.** The synthetic rasterized proxy can test safe failure and
  nothing else.
- **Human-grade adjudication**, until Will signs off the 20-item check.

---

# Reviewer reproduction kit

The minimum another reviewer needs. Every command runs from the repo root with
`.venv/bin/python`; setup is in [`probes/README.md`](probes/README.md).

| Goal | Artifact / command |
|---|---|
| **1. Verify protocol compliance** | This file at its freeze commit; `results/DEVIATIONS.md`; `results/holdout_membership.json`, committed before any score file. **Check `git log` order, not file timestamps**: `gold_adjudicated.json` must be committed before `gold_key.json` is joined to it, and that ordering is the only evidence the adjudication was blind |
| **2. Regenerate tables from raw output** | `probes/fill_results.py` — every table in the results document is generated, none transcribed |
| **3. Reproduce migration parity** | `probes/score_phase2.py` (13 accepted) and `probes/redteam_unguarded.py` (the 2 declined, guard bypassed). **SA1 / SA2 / SA3 must fail A1 / A2 / A4 respectively**; a gate its own sabotage does not fail is void |
| **4. Reproduce independent-accuracy statistics** | `probes/score_phase1.py` → `probes/report_confirmatory.py`, which emits Δ, the paired cluster-bootstrap CI, the practical-threshold verdict and **every B0 row (S1–S5, with the S4/S5 separability checks)** together. **A Δ table without its own metric's B0 row is not reviewable** |
| **5. Reproduce the security table** | `probes/redteam_egress2.py` and `probes/redteam_csp_mitigation.py` for the per-vector control/policy matrix; `probes/phase4_egress.py` for the environment-isolation run, which must carry **both** the inside-sandbox known-bad and the same-run observer-liveness control |

**Independence.** The execution agent does not self-certify these conclusions. The
deliverables are: this frozen preregistration, immutable raw outputs, scripts that regenerate
every table, and a results document that keeps A / B / C / D / E / F apart — for review by a
separate model against the raw output, not against the summary.

---

# Unresolved design choices

Decisions the protocol had to make that a reviewer could reasonably make differently. Each is
frozen above; each is listed here so it is challenged rather than discovered.

| # | Choice | Made | Alternative, and why it was not taken |
|---|---|---|---|
| 1 | Gold-sample adjudicator | **Agent reading CoreGraphics-rendered page images**, blinded to backend output by a two-file split and a commit-order proof, with a 20-item human check pending | True human adjudication of 100 items. Nobody is at the keyboard; blocking the run on it delivers nothing. The claim is downgraded and labelled, and B8 may not decide a ranking on its own |
| 2 | B3 line-number oracle | **Split**: B3a self-consistency (no reference) + B3b exactness on gold pages | The old "vs the page's own margin numbers" has no implementation — the exploratory metric scored against the **incumbent**. There is no corpus-scale margin-number oracle that is not a backend |
| 3 | PDF.js in A / B | **Excluded**; measured in E only | Building the operator-list adapter. It is a large piece of work with no concrete trigger, and it would delay every other answer |
| 4 | B metric weighting | **Bill-weighted** (per-bill mean, then mean over bills) | Document-weighted, which lets one 6-document bill dominate. Reported as a secondary sensitivity |
| 5 | Concern A primary mode | **`repaired`** — the mode we would ship | `strict`, which grades a migration against a mode nobody would ship. Strict stays as a diagnostic |
| 6 | B5 restricted to shared amounts | **Yes** | Scoring all amounts, which folds detection failures into an association metric and makes it un-interpretable |
| 7 | Quoted-block documents | **Own stratum**, excluded from primary B2/B5/B6 | Pooling them, which lets a known reference defect (DeltaTrack#11) decide a backend ranking on 30 of 52 documents |
| 8 | Holdout size | **12 bills** | More would be better and slower. The adequacy rule is what protects the claim, not the number |
| 9 | Synthetic P3b fixtures | **Safe-failure only** | Scoring accuracy on them, which would measure the synthesis rather than the backend |
| 10 | Environment isolation | **macOS `sandbox-exec`** primary, Linux container attempted | Requiring Docker, which is not running and would need Will to start it |
