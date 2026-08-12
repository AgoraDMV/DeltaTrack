# Pre-registration: metrics, materiality and pass thresholds

Written **2026-08-05, before any accuracy result was computed**, as Phase 0 step 5 of
[`README.md`](README.md) requires. A bake-off whose metrics are chosen after the fact is
not a bake-off.

## What had already been seen when this was written

Stating this plainly, because "pre-registered" is worth nothing if the boundary is vague.
The spec deliberately orders the cheap kill-gates (Phase 0 steps 1-4) **before**
pre-registration, so the following were known:

| Known | Value |
|---|---|
| PDFium-WASM FFI availability | All four required entry points exported and working |
| PDF.js whole-document cost | 1536 ms for 94 pages, incl. 408 ms `getOperatorList()` |
| pdfminer.six speed | 1.5x-3.3x the incumbent's native glyph walk |
| Incumbent extraction baseline | 5.8-10.9 s for a 1000+ page bill |
| All six adapters emit the contract | Yes, agreeing on line numbers over 6 pages |

**No accuracy score, diff-agreement number, or per-document result had been computed.**
Everything below concerns accuracy, and none of it was informed by an accuracy result.

One threshold, **gate 9 (performance)**, was necessarily set *after* seeing the speed
numbers, because the spec's own ordering puts that gate first. It is written as a
relative threshold for the reason given in its row, and that reasoning is stated so a
reader can judge whether the number was chosen to admit a favoured candidate.

---

## Definitions

### Material (gates 4 and 5)

Gates 4 and 5 are unfalsifiable without this. A disagreement between the PDF-derived and
XML-derived diff is **material** if any of:

- **(a) Money.** It is an `amount_entries` entry whose `old`, `new` or `kind` differs
  between the two pipelines, or which is present in one and absent from the other.
- **(b) Provision text.** It is a change whose `text.old` or `text.new` differs between
  pipelines by more than *typographic normalization* (see below).
- **(c) Whole change presence.** It is a change present in one pipeline and absent from
  the other, **and** its text contains a dollar amount, a section or heading identifier,
  or at least 20 non-whitespace characters of provision text.

**Typographic normalization**, explicitly non-material: runs of whitespace; the glyph
mappings `normalize_glyphs` already performs (em/en dashes, smart quotes, paired
apostrophes); soft-hyphen rejoining; GPO margin line numbers; and letter-spacing inside
small-caps headings.

Also **non-material by construction**, because the two pipelines are different artifacts
rather than two attempts at one artifact: `location` (the PDF carries page/line
coordinates, the XML carries none), `full_text_span` offsets, `anchor_resolution`, and
the ordering of changes. This follows the settled finding that PDF-vs-XML *output
parity* is impossible by design; the terminal metric is therefore scored on
structure-free content, not on coordinates.

The 20-character floor in (c) exists to keep a single stray chrome fragment from
counting as a material error. It is the one arbitrary constant here, and every
disagreement it excludes is reported separately so the choice is auditable.

### Agreement vs accuracy

Reported separately and never conflated, per Trap 2:

- **Agreement** = PDF-derived diff vs XML-derived diff. Cheap, computed for all pairs.
- **Accuracy** = adjudication of the *disputed subset* against ADR 0009's independently
  authored committee reports. Only this may be called accuracy.

---

## Metrics

Every metric is computed on output of the **one** neutral reconstruction layer, so it
measures glyph-fact quality rather than a library's own text-assembly.

### Phase 1, per document (N = 52)

| # | Metric | Definition |
|---|---|---|
| M1 | Text recovery | Token-level F1 against the XML body text, both sides normalized (case preserved, whitespace collapsed, `normalize_glyphs` applied, margin numbers removed). Tokens, not characters: character similarity is dominated by whitespace and flatters every backend. |
| M2 | Line-number recovery | Recall and spurious rate over the set of `(page, line_number)` pairs, referenced to the incumbent through the same layer. Exact set comparison, not text similarity. |
| M3 | Heading tree | Node count and `level` distribution vs incumbent, plus the ADR 0014 money-conservation invariant on `_pdf_tree_payload` (own_amounts never over-count; drops bounded). |
| M4 | Breadcrumbs | `breadcrumb_for` agreement rate over the anchors the incumbent resolves. |
| M5 | Font-role separation | Share of numbered lines where the margin-number glyph's font differs from the line's body font. Scored as **role separation**, never name-string equality, because bodies are `DeVinne` in bills and `NewCenturySchlbk` in enrolled/committee prints. Empty-font-name rate reported per backend. |

### Phase 2, terminal metric (N = 15 pairs)

| # | Metric | Definition |
|---|---|---|
| T1 | Change-set agreement | Precision/recall/F1 of PDF-derived changes against XML-derived changes, matched on normalized `(change_type, text.old, text.new)`. |
| T2 | `amount_entries` agreement | Precision/recall/F1 over `(old, new, kind)` triples, aggregated per pair. Money is scored separately because it is the highest-consequence field. |
| T3 | Material disagreements | Count of disagreements meeting the materiality definition, listed individually for adjudication. |

Reported **per bill**, never only as an aggregate: 15 pairs concentrate in `118-hr-4366`
(5), `113-hr-3547` (3) and `115-hr-5895` (2), so one bill would otherwise drive the
headline.

### Strict vs repaired

Every Phase 1 and Phase 2 number is computed **twice**: once in `strict` mode, where a
glyph the backend could not name stays U+FFFD, and once in `repaired` mode, where a
line-final unnamed glyph is read as a hyphen from position alone. The repair rule is
available to all backends equally and is a no-op for those that name the glyph. The
**gap between the two** is the measurement of a backend's glyph-naming deficit, and
collapsing it to one number would hide the single largest difference found so far.

---

## Pass thresholds

Hard gates. A backend passes or fails; ranking applies only among survivors. No weighted
composite: DeltaTrack is accuracy-sensitive, and a composite lets a missed appropriation
be offset by 200 ms of speed.

| # | Gate | Threshold | Reference |
|---|---|---|---|
| 1 | Opens the corpus | 52/52 documents, no exception, no zero-glyph page beyond those the incumbent also reports empty | absolute |
| 2 | Line-number integrity | recall >= incumbent - 0.005 **and** spurious <= incumbent + 0.005 | **incumbent** (no-regression) |
| 3 | Structural conservation | ADR 0014 conservation holds on every document where it holds for the incumbent; heading-node count within 2% | **incumbent** (no-regression) |
| 4 | Material diff correctness | **Zero** adjudicated material errors across 15 pairs | **XML + ADR 0009** (correctness) |
| 5 | `amount_entries` | **Zero** adjudicated amount errors across 15 pairs | **XML + ADR 0009** (correctness) |
| 6 | Browser execution | Runs under Pyodide or natively in-browser and matches its own native result | absolute |
| 7 | Fully offline | Zero network requests, proven by a harness with a known-bad control | absolute |
| 8 | Licensing | Satisfies the project distribution policy | absolute |
| 9 | Performance | Largest corpus document within **3x** the incumbent's native extraction time, **and** projected Pyodide time <= 60 s | **incumbent**, relative |

Gates 2 and 3 are **no-regression** gates measured against PDFium; gates 4 and 5 are
**correctness** gates measured against XML. They are different questions and are kept
labelled distinctly in the results.

**Gate 9's threshold, and why it is relative.** The incumbent itself takes 5.8-10.9 s
natively on a 1000+ page bill, which is 9-21 s under the delivery spike's measured
1.6x-1.9x Pyodide penalty. An absolute "tens of seconds" rule would therefore disqualify
PDFium, which is not a coherent outcome for a no-regression exercise. 3x keeps a backend
in contention if it is the same order of magnitude as what ships today, and the 60 s
projected ceiling is the point past which a staffer would reasonably abandon a
comparison. Both numbers are stated so a reader can disagree with them explicitly.

---

## Statistical power, stated up front

Zero material failures across **15 pairs** is consistent, by the rule of three, with a
true material-failure rate as high as **~20% at 95% confidence**. This is reported
alongside any zero result. It is not an argument against the gate; it is the reason
Tier B is necessary rather than optional, and the reason the phrase "PDF is solved"
may not appear in the results regardless of how Tier A scores.

## What would falsify the whole exercise

The calibration gate. If the incumbent does not score near ceiling **through the neutral
layer**, the layer is wrong and no other number in this document means anything. That
check runs before any challenger is scored, and its result is reported first.

One caveat the spec did not anticipate, recorded here before the gate runs: the premise
"PDFium is known-good" is true of PDFium *through its text API plus `normalize_raw`*, not
necessarily of its **glyph API**, which is what this bake-off actually measures. A
measured shortfall in PDFium's glyph facts is therefore a real finding rather than
automatic proof that the layer is broken, and the two are distinguished by whether the
other five backends show the same shortfall on the same input.
