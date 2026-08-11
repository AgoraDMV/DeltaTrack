# Phase 3 — does the extended-glyph rule survive a change of engine?

- Run 2026-08-06. This is a new subphase. **Preservation, stated literally** (the first
  version of this line said phase 1 and phase 2 "are unchanged", which their findings
  documents no longer are):
  - **Phase 1 and phase 2 RESULT ARTIFACTS are unchanged.** No commit after each file's
    creating commit touches `../results/` or `../phase2/results/`; `git log -- <those
    paths>` lists only phase-1 and phase-2 spike commits.
  - **Their FINDINGS DOCUMENTS have been annotated**, by phase 3, with forward pointers and
    corrections: 109 lines added and 6 removed across both. Five of the six removed lines
    are the two sentences whose *strength* was corrected ("Adopt the hybrid contract" and
    "Adopt it for the corrected reason"), each replaced in place with an annotation saying
    what changed and why. The sixth is the superseded preservation claim itself. **No
    result, table or number was edited**, and the original claims stay visible.
- Probes are `h01`–`h08` here; raw output in [`results/`](results/).
- The question phase 2 left open. Phase 2 measured field *availability* on three backends
  and *accuracy* on one, then wrote into its comparison table:

  > word quality if the backend changes: **fixed, the rule is ours**

  and into its flip conditions:

  > under hybrid the measured quality swing is 16 points; under extended glyph it is zero.

  Neither sentence had been measured. Both are tested here.

**Answer: confirmed on the tested population, and the mechanism is not the one the phrasing
implies.** The same `wants_space` fed each engine's own facts gives the same answer on
195,290 of the 195,291 adjacent pairs all three engines could align, and produces
byte-identical reconstructed text from all three on four of five documents. On the frozen
adjudicated sample all three score **0.9275**, the primary result, with zero disagreements
between them.

The extended contract is not *normalising* a difference between engines. It is asking for a
quantity on which they barely differ, and the evidence for that sits at three separate
levels, each measured on its own rather than inferred from the one above it:

| level | measured by | result |
|---|---|---|
| **raw** | `h06` | the engines' returned advances are **not** bit-identical; max delta **3.05e-5 pt** over 390,582 endpoints |
| **contract** | `h04` N12 | after each backend is packed into the four-decimal contract, the compared advances are **identical**, max delta **0.0 pt** on the same 390,582 endpoints |
| **decision** | `h04` | the spacing rule then differs **once in 195,291** comparable pairs, and §5's D1 traces that one to `font_size`, not to an advance |

> **Corrected 2026-08-06, three times, and the third correction is the important one.**
> (i) The first version said the engines return "advances identical to 0.0 pt", which was
> the **contract-level** measurement reported as if it were the raw one. (ii) A second pass
> found `h06`'s bins were computed against 5e-5 while labelled 1e-4, overstating the
> *origin* divergence. (iii) That pass then replaced the withdrawn claim with a **false
> theorem**: that because every raw advance delta is below 5e-5, the rounded values must be
> equal. **They need not be.** Half a quantisation step bounds the error between one value
> and its own rounded form; it is not a pairwise criterion, and two values 2e-6 apart can
> straddle a boundary — `round(1.234949, 4) = 1.2349` against `round(1.234951, 4) = 1.2350`.
> Contract-level equality is not derived from raw distance at all. It is measured directly
> by `h04`'s N12 on the packed values. The architectural conclusion is unchanged through all
> three, because it never needed bit-identity.

Phase 3 also found **two defects in phase 2's own work**, one of which falsifies a sentence
in `pdfium_extended.py`'s docstring ([§5](#5-h5--the-two-divergences-diagnosed)), and **eleven
in its own successive passes**, listed in
[§7](#7-corrections-this-phase-makes-to-earlier-claims).

---

## 1. H1 — what each backend's "advance" actually is

Tested against the **installed source**, then by value. Phase 2's `g03` reached the right
field for pdfminer by a wrong reason, and the reason is what a reader carries elsewhere.

| backend | the value | what the source says it is |
|---|---|---|
| PDFium 5.12.1 | `FPDFFont_GetGlyphWidth(font, cp, size)` | the font's glyph width at that size, charcode reverse-mapped from Unicode |
| pdfminer.six 20260107 | `LTChar.width` | `layout.py` builds the box as `(0, descent+rise, self.adv, ...)` then applies `matrix`. It is an **advance box**; pdfminer computes no ink bounds at all. After the transform, `x0` is the pen and `width` is the advance **in page space** |
| pdfminer.six | `LTChar.adv` | `textwidth * fontsize * scaling`, the advance in **text space**. `pdfdevice.render_string_horizontal` walks the pen with exactly this value |
| PyMuPDF 1.28.0 | `get_texttrace()` `chars[i][3]` | `jm_trace_text_span`: `adv = fz_advance_glyph(font, gid, wmode) * fsize`, then `x1 = origin.x + adv`. The rectangle is **constructed from the advance**, at the origin |

### The correction to `g03`

`g03` recorded "**pdfminer's `LTChar.adv` is in em units, not points**". Read as a statement
about the library that is wrong. `.adv` is in text-space points. It looks like em units on
this corpus only because GPO writes `Tf 1` and carries the type size in the text matrix, so
`fontsize` is 1 and `matrix[0]` is 8 to 14.

Measured on the five documents the frozen sample draws from:

| document | text-matrix `a`, median | `width / adv`, median | `.adv` predicts origin delta | `.width` | `.adv × matrix[0]` |
|---|---|---|---|---|---|
| `114-hr-2029/4` p99 | 14.0 | 14.0 | **0 testable pairs** | 805/805 | 805/805 |
| `118-hr-4366/5` p26 | 14.0 | 14.0 | 0 | 922/922 | 922/922 |
| `116-hr-1865/6` p1 | 8.0 | 8.0 | 0 | 1353/1366 | 1353/1366 |
| `118-s-4795/1` p5 | 14.0 | 14.0 | 0 | 970/970 | 970/970 |
| `CRPT-118srpt198` p1 | 10.0 | 10.0 | 0 | 822/822 | 822/822 |

`width / adv` equals the text-matrix horizontal scale on every document, and
`.adv × matrix[0]` reproduces `.width` pair for pair. So `.adv` is not the wrong quantity,
it is the **untransformed** one, and `.width` is the field the rule needs because the rule
works in page space. `g03`'s field choice stands; its stated reason does not.

**C3 (separability).** If `width == adv` on this corpus the probe could not tell the two
apart and would have to say so. The ratio is 8 to 14 on every document, never 1.

### The correction the review expected for PyMuPDF, which did not materialise

The review flagged `chars[i][3]` as possibly a character **ink** box, which would make
`bbox[2] - origin[0]` an ink width and PyMuPDF **UNSUPPORTED**. Two controls say otherwise:

- **C1.** For every upright character of all five documents, `bbox[0] - origin[0]` is
  **0.0 pt exactly**. An ink box cannot satisfy that: nearly every glyph has a non-zero
  left side bearing.
- **C5.** The trace advance was checked against `Font.glyph_advance` on the **embedded font
  program**, extracted from the PDF by PyMuPDF itself. Agreement **1.0** over 987, 1130,
  1633, 1215 and 967 characters. Two independent PyMuPDF routes to the same metric; no
  other engine consulted.

  This is the avenue the review named. Phase 2's `g03` had reported `pymupdf.Font(fontname=…)`
  as unable to instantiate GPO's DeVinne faces, which is true, and concluded the font path
  was closed. It is not: `extract_font(xref)` gives the embedded program and
  `Font(fontbuffer=…)` instantiates it. **PyMuPDF is SUPPORTED, on two routes.**

**A control on the control.** PDFium's *ink* width was run through the identical identity
test and predicts the origin delta at only 0.31 to 0.58. The test does discriminate an
advance from ink, so the 1.0 rates above are not an artefact of a loose tolerance.

---

## 2. H2 — PDF.js, and a correction to why it fails

Phase 2 recorded PDF.js as failing "for the same per-character-granularity reason ADR 0003
already records". That is the right verdict from the wrong evidence, and the wrong evidence
is the optimistic-API kind that nearly produced false negatives for pdfminer and PyMuPDF.

`getTextContent()` is item-level (12.8 to 13.9 characters per item), which is what `g03`
measured. `getOperatorList()` is not:

| document | `showText` glyph objects | carry a per-character `width` | carry any position field |
|---|---|---|---|
| `114-hr-2029/4` p99 | 1,137 | **1,137 (coverage 1.0)** | 0 |
| `118-hr-4366/5` p26 | 1,306 | **1,306 (1.0)** | 0 |
| `CRPT-118srpt198` p1 | 1,094 | **1,094 (1.0)** | 0 |

Glyph objects expose `unicode`, `originalCharCode`, `fontChar`, `isSpace`, `isInFont`,
`vmetric` and `width`. The width is a real per-character font advance in 1/1000 em, and it
agrees with the other engines (`'9'` is 519, `'H'` 870, `'R'` 815).

**So PDF.js has one of the two facts and not the other.** No API exposes a per-character
pen origin. It exists only inside PDF.js's text-state machine, and a consumer wanting it
would have to interpret the text-showing operators itself: on these three pages that is
7 to 21 `setTextMatrix`, 14 to 50 `setLeadingMoveText`, 24 to 52 `setWordSpacing`, 1 to 5
`setCharSpacing`, 13 to 53 `setFont`, plus `nextLine` and `beginText`/`endText`. That is a
PDF text interpreter, not an adapter.

**Verdict unchanged (PDF.js cannot emit the extended contract), reason corrected: the
missing fact is the ORIGIN, not the granularity of the advance.**

---

## 3. H3 — the frozen 72-pair sample, every backend

Phase 1's sample, adjudication unchanged and not reopened. All 72 pairs relocated in
PDFium; **0 unmapped in any backend**. The join is by pen origin (codepoint, `|Δx| ≤ 0.05` pt,
`|Δbaseline| ≤ 0.6` pt, unique match required), which is safe because H1 measured the
engines' origins as agreeing to under 2e-4 pt.

**On the primary adjudication, unchanged and not reopened**, all three extended paths score
**0.9275**, with zero pairwise disagreements between them.

| backend | backend's own text decision | extended-rule decision | coverage |
|---|---|---|---|
| PDFium | **0.9275** | **0.9275** | 69/69 |
| pdfminer.six | **0.8065** (on the 62 it can decide) | **0.9275** | 69/69 ext, 62/69 own |
| PyMuPDF | **0.8116** | **0.9275** | 69/69 |
| PDF.js | n/a | unsupported (no pen origin) | 0 |

Three of the 72 are UNREADABLE and excluded, as in phase 1. pdfminer's *own* column keeps
phase 1's frozen coverage of 62/69; the 7 it could not locate were not scored then and are
not scored now.

> **The post-hoc sensitivity analysis, kept visibly secondary.** Phase 1 found six identical
> stimuli answered 3–3 by its adjudicator and reported that as a defect in its own work.
> Removing that inconsistent class raises **all three extended paths to 0.9683**, PDFium's
> own decision to 0.9683, pdfminer's own to 0.8065 and PyMuPDF's own to 0.8413. It is a
> sensitivity check on a known adjudication weakness, it moves the numbers in the direction
> that favours the paths under test, and phase 1 labelled it post-hoc for exactly that
> reason. **The primary adjudication above is the result; 0.9683 is the sensitivity.**

### The cost of a backend change, computed PAIRED

Phase 3's first pass subtracted 0.9683 from 0.8065 and called the gap 16.2 points. Those
accuracies were computed on different denominators (69 pairs against 62), so the subtraction
was not licensed. Scored on **exactly the pairs where both the engine's own decision and the
extended rule have an answer** (`h07`):

| backend | paired n | own | extended | paired delta | extended fixed | extended broke |
|---|---|---|---|---|---|---|
| pdfminer.six | 62 | 0.8065 (12 errors) | **0.9677** (2 errors) | **+16.12 pts** | **10** | **0** |
| PyMuPDF | 69 | 0.8116 (13 errors) | **0.9275** (5 errors) | **+11.59 pts** | **8** | **0** |

Post-hoc, inconsistent class dropped: pdfminer **+16.12** (n unchanged at 62, because all six
inconsistent items are already outside pdfminer's paired set), PyMuPDF **+12.70** (n = 63).

The discordant counts are the part a bare delta hides, and they are one-directional: the
extended rule corrects **10** of pdfminer's boundaries and **8** of PyMuPDF's, and regresses
**none**. PyMuPDF's coverage was already equal, so its paired number moving only from
"12.7 post-hoc" to "11.59 primary" is the control that the pairing machinery is not itself
introducing the effect.

### Pairwise disagreement

| comparison | disagreements |
|---|---|
| PDFium-extended vs pdfminer-extended | **0 / 72** |
| PDFium-extended vs PyMuPDF-extended | **0 / 72** |
| pdfminer-extended vs PyMuPDF-extended | **0 / 72** |
| PDFium-extended vs PDFium's own text | 0 / 72 |
| pdfminer-extended vs pdfminer's own text | **12 / 65** |
| PyMuPDF-extended vs PyMuPDF's own text | **8 / 72** |

The three extended paths are unanimous. The rule agrees with PDFium's own text assembly on
all 72, which is expected, since it is a port of PDFium's heuristic. It disagrees with
pdfminer's on 12 of 65 and with PyMuPDF's on 8 of 72, and on the paired subsets above the
extended answer is the more accurate one in every discordant case.

### By stratum, on the primary adjudication

| stratum | n | PDFium-ext | pdfminer-ext | PyMuPDF-ext | pdfminer own |
|---|---|---|---|---|---|
| backend_disagree | 6 | 1.0 | 1.0 | 1.0 | 0.0 |
| body_prose | 7 | 1.0 | 1.0 | 1.0 | 1.0 |
| explicit | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| generated | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| **narrowest_generated** | 8 | **0.75** | **0.75** | **0.75** | 0.75 |
| **near_threshold** | 8 | **0.875** | **0.875** | **0.875** | 1.0 |
| no_space_wide | 8 | 1.0 | 1.0 | 1.0 | 0.6 |
| small_caps | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| **widest_intra** | 8 | **0.75** | **0.75** | **0.75** | 0.667 |

The hard strata do not disappear into the aggregate: the three extended paths are equally
wrong in the same places, which is what a shared rule on shared facts should look like.

### Controls

| control | result | reads as |
|---|---|---|
| **N1** adapter vs phase 2's `g04`, full 72-decision vector | **0 mismatches** | see the correction below: N1 as first written did less than it claimed, and now does what it claimed |
| **N2** advances ×1.25 | 0.9275 → **0.8986** (all three backends) | the rule is reading the advance |
| **N2** advances ×0.75 | 0.9275 → **0.7971** (all three) | as above, larger effect |
| **N3** pdfminer fed `.adv` instead of `.width` | 0.9275 → **0.6087**, 27 spurious splits | the harness can see the field choice; a wrong field collapses |
| **N4** coverage | 72/72 relocated, 0 unmapped per backend | no silent partial match |
| **N5** the facts themselves | max &#124;Δorigin_x&#124; **1.9e-4 pt**, max &#124;Δadvance&#124; **0.0 pt** over 144 endpoints | at the contract's 1e-4 rounding. See §4 and `h06`: the raw values are **not** identical |

### N1, corrected: what it did and what it now does

As first written, N1 was described as reproducing phase 2's extended result "item by item".
It did not. `g04_boundary_scores.json` persists only the extended-vs-PDFium
**disagreements**, and there were none, so there is no phase-2 extended vector on disk to
compare against. What phase 3 actually did was reconstruct the expected value as "equal to
`pdfium_own`" and compare with that, which tests agreement with PDFium's engine-space
decision and not agreement with phase 2's computation.

`h07` replaces it with the comparison originally claimed. Phase 2's `g04` code path is
re-run, its complete **72-decision** extended vector is materialised, and each decision is
compared with phase 3's adapter-derived vector. The two extractions are genuinely different
implementations: `g04._page_pairs` reads the text page inline, `pdfium_extended.extract` is
the adapter.

| | |
|---|---|
| vector length | **72** (41 space, 31 no-space) |
| extended decisions differing between the two implementations | **0** |
| engine decisions differing | **0** |
| `g04.main()` re-run to a scratch path, published blocks vs the frozen artifact | **all four identical** |
| `g04_boundary_scores.json` modified | **no** |

The last two rows matter: without them, a drift between the imported functions and the
committed entry point would make "a different implementation" untrue and the replication
worthless.

---

## 4. H4 — the same question at a scale that could detect a rare divergence

Zero disagreements on 72 pairs is consistent with a divergence rate up to about 4 % at
95 % confidence, so the 72-pair result cannot carry a portability claim on its own. H4
trades truth for power: every adjacent same-baseline pair on 24 pages of each of the five
documents, no oracle, agreement only.

**Of 195,291 adjacent pairs that all three engines could align and compare, one
word-boundary decision differed.** The population this claim covers, and the population it
does not, in full:

| | |
|---|---|
| pairs PDFium saw | 200,684 |
| pairs all three engines report at the same pen origin | 196,105 (**join coverage 0.977**) |
| shared key but a different following glyph, excluded | 814 |
| **pairs compared** | **195,291** |
| **word-boundary disagreements** | **1** |
| **never joined, and therefore never tested** | **4,579 (2.28 %)**, characterised in §4.1 |

This is a statement about 120 pages of five GPO documents through three engines. It is not a
statement about the PDF population at large, and the sentence "the engines have nothing to
disagree about" that appeared in the first draft of this document overreached in exactly
that way. What is measured is that on this corpus, through these three engines, at these
pages, the same rule on each engine's own facts returns the same answer.

Reconstructed text, all three engines through the same reconstructor:

| document | PDFium vs pdfminer | PDFium vs PyMuPDF |
|---|---|---|
| `114-hr-2029/4` | **byte-identical** | **byte-identical** |
| `118-hr-4366/5` | **byte-identical** | **byte-identical** |
| `116-hr-1865/6` | token F1 0.999861 | **byte-identical** |
| `118-s-4795/1` | **byte-identical** | **byte-identical** |
| `CRPT-118srpt198` | **byte-identical** | **byte-identical** |

### What bounds this result, stated because the control says so

**N7, the sabotage curve.** One engine's advances scaled, then compared against PDFium's:

| scale | disagreements / 198,400 | rate |
|---|---|---|
| ×1.05 | 13 | 0.00007 |
| ×1.10 | 61 | 0.00031 |
| ×1.25 | 910 | 0.0046 |
| ×0.75 | 61,033 | **0.31** |

**The decision test is nearly blind to a small advance error.** A systematic 5 % difference
between two engines would move 7 pairs in 100,000, which this comparison would report as
"essentially identical". So "1 disagreement in 195,291" would, on its own, be weak evidence.

**N12 removes that limit by measuring the inputs instead of the outputs** — but N12 as first
written compared the values *after* the adapters rounded them to four decimal places, so it
established equality at the contract's precision and was reported as equality full stop.
`h06` re-reads the same glyphs raw, straight from each API before packing, on the identical
joined population. Over **390,582 glyph endpoints**, advance available on both sides of
every one:

**Two reference scales, and neither is an equivalence criterion.** The contract's
four-decimal quantisation **step** is 1e-4; half a step is **5e-5**, the largest error
between one value and *its own* rounded form. Both are reported below because they make the
bins readable, and each bin is named for its literal threshold. **Neither licenses a
statement about whether two independent values round alike** — that is measured separately,
at the contract level, by `h04`'s N12.

| raw **advance** vs PDFium | max | median | exactly equal | 0 < d < 5e-5 | **≥ 5e-5** | **≥ 1e-4** |
|---|---|---|---|---|---|---|
| pdfminer.six | **4.40e-7 pt** | 9.8e-15 | 43,077 | 347,505 | **0** | **0** |
| PyMuPDF | **3.05e-5 pt** | 4.9e-6 | 41,681 | 348,901 | **0** | **0** |

| raw **origin_x** vs PDFium | max | median | exactly equal | 0 < d < 5e-5 | **≥ 5e-5** | **≥ 1e-4** |
|---|---|---|---|---|---|---|
| pdfminer.six | 2.12e-4 pt | 1.1e-5 | 5,205 | 362,632 | **22,745** | **901** |
| PyMuPDF | 1.22e-3 pt | 3.1e-5 | 138,100 | 145,341 | **107,141** | **34,157** |

**So: the raw values are not identical.** The largest advance difference is 4.40e-7 pt
(pdfminer) and 3.05e-5 pt (PyMuPDF), with no endpoint reaching 5e-5 and none reaching 1e-4.
The honest reading of those bins is simply that **the raw advance differences are extremely
small relative to the spacing rule's decision scale** — the rule's own thresholds are
1.7–2.2 pt, and §4's perturbation bracket puts the smallest relative change it can feel at
10⁻²–10⁻¹.

Raw origins are further apart: 22,745 and 107,141 endpoints differ by ≥ 5e-5, and **901 and
34,157** by ≥ 1e-4.

**What none of this establishes is contract-level equality**, and an earlier version of this
section inferred exactly that from the advance bins. It does not follow: values closer than
half a step can still round apart. The contract-level fact is measured directly and is
reported in §4 above — `h04`'s N12 compares the **adapter-packed** advances, the values that
actually enter `contract_extended`, and finds **max |delta| = 0.0 pt across all 390,582
endpoints, with the advance available on both sides of every one**.

> **Corrected 2026-08-06.** An earlier version of this table reported 22,745 and 107,141 as
> the counts differing by more than **1e-4**. They are the counts at or above **5e-5**: the
> probe binned against the round-to-nearest error bound and labelled the bin
> `at_or_above_contract_precision`, which reads as the quantisation step. The true ≥1e-4
> counts are **901 and 34,157**, so the previous sentence overstated the origin divergence
> by 25× for pdfminer and 3× for PyMuPDF. **This was a reporting and binning defect, not a
> change in the portability result**: no advance count moved, and the origin residue was
> already three orders of magnitude below the thresholds the rule compares against.

**Two controls say why that does not matter here, and both were run because the answer was
not assumed.**

- **Where PyMuPDF's floor comes from** (`h06` for the pattern, `h08` for the mechanism).
  Every one of PyMuPDF's advances is **exactly representable in float32** (share 1.000 on
  all five documents), while only 2.6–16.3 % of PDFium's and pdfminer's are. That is a
  pattern; on its own it does not establish a cause, and the first version of this section
  wrote that single-precision storage "is the entire residue", which claims one.
  `h08` closes the two links needed. The code path: `jm_trace_text_span` returns
  `char_orig` (an `fz_point`) and `char_bbox` (an `fz_rect`), so the advance `h06` reads is
  `fz_rect.x1 − fz_point.x`. The storage width: a double pushed through `fz_make_point`,
  `fz_make_rect` and `fz_make_matrix` **returns quantised to float32** (0.1 comes back as
  0.10000000149011612), with a negative control on 0.5 confirming the test can tell a
  quantising struct from a non-quantising one. So the origin and the advance box reach
  Python already rounded to binary32, which accounts for a residue at the observed scale.
  **It does not prove that no other rounding contributes anywhere else in the pipeline**,
  and the mechanism is explanatory rather than architectural either way.
- **How much room there is.** On the same pages, the largest relative advance perturbation
  that changed **no** decision is 1e-2 (1e-1 on `118-hr-4366/5`); the smallest that changed
  **any** is 1e-1. Against a maximum observed cross-engine relative difference of 3.97e-8
  (pdfminer) and 1.08e-5 (PyMuPDF), that is **5.4 to 11.7** and **3.0 to 4.4** orders of
  magnitude of headroom, quoted from the conservative end of the bracket. The origin
  residue is likewise ~3 orders below the 1.7–2.2 pt thresholds the rule actually compares
  against.

The honest formulation is therefore: **the engines agree on these facts far more closely
than the rule can distinguish**, which is what the architecture needs. They do not return
bit-identical values, and this document no longer says they do.

### 4.1 The 4,579 pairs that never joined

2.28 % of PDFium's pairs never entered the comparison. If that population were concentrated
on the display type that carries account names, the portability claim would miss the place
DeltaTrack most depends on, because the heading tree is the financial data contract.

**N16, strengthened.** The rematch originally required the two codepoints to match plus the
**first** glyph's origin and baseline to fall within tolerance. That does not establish what
the prose claimed, because nothing tied the candidate's **second** glyph to the second glyph
of the PDFium pair: a candidate whose first glyph coincided but whose successor was a
different instance of the same character would have been accepted. The rule now constrains
both endpoints — both codepoints, both `origin_x` within 0.05 pt, both baselines within
0.6 pt, exactly one candidate — with the tolerances unchanged.

| | |
|---|---|
| unjoined | **4,579** of 200,684 (2.28 %) |
| concentrated in | `CRPT-118srpt198` (2,999) and `116-hr-1865/6` (1,484); the other three total 96 |
| **uniquely rematched under the two-endpoint rule** | **4,558 (99.5 %)** |
| ambiguous candidate | **0** |
| unmatched | **21** |
| of the 4,558, decisions that then **disagree** | **0** |

**The stronger rule preserves the result exactly**: same 4,558, no ambiguity, still zero
disagreements. So the claim it was supposed to support now actually holds.

**The gap is overwhelmingly an artefact of the join key, not of the engines.** The key
buckets the pen origin at 0.05 pt and the baseline at 0.6 pt; a glyph whose coordinate sits
near a bucket edge can land on either side, and the engines' sub-1e-3 pt coordinate
differences are enough to separate them. The rematch is reported as a diagnostic and is
**not** folded into H4's 195,291, which stays as measured.

**The 21 that are genuinely absent are all the same known case:** every one is a pair whose
second glyph is **U+FFFD**, PDFium's carrier for GPO's soft hyphen, which the other two
engines do not emit. That is the glyph-inventory difference N8 and §5's D2 already document,
not a new one.

**Typography, and only typography.** Type size, joined against unjoined:

| | modal size | share **above** the modal size |
|---|---|---|
| joined (195,291) | 10.0 pt | **39.0 %** |
| unjoined (4,579) | 10.0 pt | **2.1 %** |

The unjoined population is strongly under-represented in above-modal-size text, which
reduces the concern that the join gap is concentrated in display typography.

> **This analysis does not semantically classify the pairs as headings versus body prose.**
> Font size is a proxy for semantic role and nothing here validates it as one. An earlier
> version of this section said the unjoined population "is body prose, and headings are if
> anything better covered", which is an inference from type size alone. The project does
> not yet have a trustworthy heading-level oracle — that is item 1 on the list blocking an
> ADR — so a claim of that shape cannot be checked and is withdrawn.

**N8** guards against crediting an engine that simply emitted less: glyph inventories are
diffed per document. The only codepoint not reported by all three is U+FFFD (120 to 294 per
document), which PDFium alone carries. That difference is neutralised by `repaired=True`,
the same mode `g05` uses, which turns the carrier into `-` before `rejoin_soft_hyphens`.

---

## 5. H5 — the two divergences diagnosed

### D1 — CONTRACT INSUFFICIENCY: `font_size` has no defined axis

The single disagreement in 195,291 pairs is `.` followed by `R` on page 1 of
`116-hr-1865/6`. All three engines report the **same** origins (129.196, 134.512) and the
**same** advances (3.336, 8.664). The divergent input is `font_size`:

```
text matrix (12.0, 0.0, 0.0, 13.0)      GPO condenses display type: 12 wide, 13 tall

PDFium    FPDFText_GetFontSize x sqrt(a^2+b^2)  -> 12.0   the HORIZONTAL scale
PyMuPDF   |transform_vector((1,0), trm x ctm)|  -> 12.0   the HORIZONTAL scale
pdfminer  LTChar.size = transformed box HEIGHT  -> 13.0   the VERTICAL scale
```

`wants_space` normalises each advance to 1/1000 em by dividing by `font_size`, and
`_normalize_threshold` then **buckets** that value at 400/700/800. The advance is 722 em by
PDFium's size and 666 em by pdfminer's, which crosses the 700 boundary, so the threshold is
`w/5` (1.733 pt) for two engines and `w/4` (2.166 pt) for the third. The observed gap is
1.980 pt and falls between them.

**Category: contract insufficiency, not an adapter bug.** Every adapter reports its own
engine's own documented size. The extended contract inherited `font_size` from
`contract.Glyph`, where it fed `_SPACE_FACTOR × size` and scaled smoothly, so the axis
never mattered. The ported PDFium rule makes it select a divisor, and there it does.

Blast radius, measured rather than assumed: **5,722 of 197,573 pairs (2.9 %)** have an
engine-to-engine `font_size` difference, and exactly **one** of them changes the answer.

**N9, the fix, derived inside pdfminer.** `LTChar.size` is `fontsize × |matrix[3]|`; the
advance axis is `fontsize × |matrix[0]|`; both matrix entries are on the object. Rebuilding
every pdfminer glyph with `size × |matrix[0]| / |matrix[3]|`:

| document | text identical to PDFium, as built | after axis correction |
|---|---|---|
| `114-hr-2029/4` | yes | yes |
| `118-hr-4366/5` | yes | yes |
| `116-hr-1865/6` | **no** | **yes** |
| `118-s-4795/1` | yes | yes |
| `CRPT-118srpt198` | yes | yes |

Closed at the output, not only at the pair. Nothing was tuned: no constant moved, and the
correction is a coordinate-axis choice available in pdfminer's own API. **It is recorded,
not applied to phase 2.**

### D2 — ADAPTER BUG: `pdfium_extended.py` emits PDFium's generated spaces

`pdfium_extended.py`'s docstring states:

> it never reads `get_text_range()`, never asks whether a character was generated, and
> **never consumes a space the engine decided to insert**. It asks only for facts about
> marks that are on the page.

The first clause holds. The second does not, and not asking is not the same as not
consuming. The adapter copies every character on PDFium's text page, PDFium's text page
contains **generated** space characters, and `reconstruct_extended._line_text` emits
`chr(32)` for each of them before the geometric rule is ever consulted.

| document, 24 pages | space glyphs in the contract | | | PDFium's spaces by provenance | |
|---|---|---|---|---|---|
| | PDFium | pdfminer | PyMuPDF | generated | explicit |
| `114-hr-2029/4` | **5,000** | 592 | 592 | **4,445** | 555 |
| `118-hr-4366/5` | 5,090 | 4,482 | 4,482 | 642 | 4,448 |
| `116-hr-1865/6` | 10,706 | 10,530 | 10,530 | 235 | 10,471 |
| `118-s-4795/1` | 5,138 | 4,499 | 4,499 | 684 | 4,454 |
| `CRPT-118srpt198` | 9,112 | 8,896 | 8,896 | 251 | 8,861 |

On `114-hr-2029/4` the content stream supplies 555 spaces and PDFium synthesises 4,445, so
on that document the phase-2 extended reconstruction was taking **eight of every nine word
boundaries straight from the engine**.

**What it did and did not contaminate.**

- `g04` is **unaffected**. It walks ink pairs and never reads a space glyph, so phase 2's
  adjudicated tie is real. H3's N1 control confirms this independently.
- `g05` and `g06` ran through `reconstruct_extended` and **were** on the contaminated path.

**The corrected contract, and the result.** A space carries no ink, so no space belongs in a
contract of "marks on the page". Dropping every U+0020 from every backend and letting the
rule decide all boundaries:

| | extended, as phase 2 built it | extended, no space glyphs |
|---|---|---|
| four named heading failure cases | 53 ok / 0 bad | **53 ok / 0 bad** |
| reconstructed text, all 5 documents | — | **identical to the loose run** |
| cross-engine token F1 | 1.0 (4 docs), 0.999861 | 1.0 (4 docs), 0.999861 |
| **N10** tokens gained/lost by dropping stream spaces | — | 0 on four documents, −1 on one |

**The design defect is real and its effect on phase 2's numbers is nil.** The geometric rule
independently recovers every boundary the generated spaces were supplying, which is the
property the design claimed and had not demonstrated. Removing them is also the answer to
the awkward part of the design: the clean way to exclude engine-invented spaces without
`FPDFText_IsGenerated`, the Experimental predicate the extended design exists to avoid, is
simply not to carry U+0020 at all, and that costs nothing.

---

## 6. What this changes in phase 2's comparison

| | phase 2 wrote | phase 3 measured |
|---|---|---|
| backends that can emit the contract | 3 of 4 | **3 of 4, confirmed by construction rather than by field probe**; PyMuPDF on two independent routes |
| PDF.js failure reason | item granularity | **no per-character pen origin**; the advance *is* available at 1.0 coverage |
| pdfminer's advance field | `.adv` is em units | `.adv` is text-space points; `.width` is its page-space transform. Field choice unchanged |
| "word quality if the backend changes: fixed" | asserted | **supported**: **0.9275** from all three engines on the primary adjudication (0.9683 post-hoc), 0 pairwise disagreements on the 72 adjudicated pairs, 1 in 195,291 at page scale |
| "under hybrid the swing is 16 points" | asserted from pdfminer alone | **measured on two engines, paired**: **+16.12 pts** against pdfminer's own decision and **+11.59** against PyMuPDF's, correcting 10 and 8 boundaries respectively and regressing none |
| the reason it ports | the contract normalises engines | **the engines already agree at the level the contract carries**: raw advances differ by at most 3.05e-5 pt (`h06`), the packed contract advances are identical at max delta 0.0 pt (`h04` N12), and the raw residue is three or more orders of magnitude under the smallest perturbation that changes any decision |
| `pdfium_extended` consumes no engine space | stated in its docstring | **false as built**; corrected contract scores identically |

**This is the review's Outcome A.** Extended segmentation stays at PDFium accuracy across
engines. So the architectural argument in phase 2's §"the architectural comparison" now has
a measured row where it had an asserted one, and the row favours extended glyph.

It does not settle the decision, for the reason phase 2 already gave: engine independence is
option value that ADR 0002 has declined. What phase 3 changes is that the option value is
now **priced**, not assumed. On the primary adjudication, paired, the hybrid's cost of a
future engine change is **11.6 to 16.1 points** of word-boundary accuracy, and it is
one-directional: the extended rule corrected 10 of pdfminer's boundaries and 8 of PyMuPDF's
and broke none. The extended contract's cost is zero of those points, plus one ported
heuristic, one fallback constant, and one contract field (`font_size`) that needs its axis
specified.

---

## 7. Corrections this phase makes to earlier claims

To phase 2:

1. **`g03`'s pdfminer reason.** `.adv` is not in em units; it is the text-space advance. The
   field chosen (`.width`) was right.
2. **`g03`'s PyMuPDF font path.** `pymupdf.Font(fontname=…)` cannot instantiate GPO's faces,
   which `g03` recorded correctly, but `extract_font(xref)` + `Font(fontbuffer=…)` can, so
   the font route is open and corroborates `get_texttrace()` at rate 1.0.
3. **`g03`'s PDF.js reason.** Granularity is the limitation of `getTextContent()` only.
   `getOperatorList()` gives a per-character advance at coverage 1.0. The blocker is the
   pen origin.
4. **`pdfium_extended.py`'s docstring.** "Never consumes a space the engine decided to
   insert" is falsified by the adapter's own output; the generated spaces are copied through.
   `g05` and `g06` ran on that path. `g04` did not.
5. **`contract_extended.py`'s neutrality claim.** "No backend is asked to reproduce another's
   conventions" is true of `origin_x` and `advance` and **not** of `font_size`, which the
   ported rule made load-bearing and which the contract does not define on an axis.

To phase 3's own first pass:

6. **H4's first text comparison ran without `repaired=True`** and reported token F1 0.95,
   which was PDFium's U+FFFD soft-hyphen carriers being scored as a spacing difference. The
   `g05` mode gives 1.0. The N8 inventory diff exists so that error cannot recur silently.
7. **H4's first sabotage control was a single ×1.10 point** and fired 0 to 48 times per
   document. That is not evidence the comparison can see a divergence. It is now a curve,
   and the curve says the decision test is insensitive below about ×1.25, which is why N12
   (comparing the facts) carries the portability claim instead.
8. **"Advances identical to 0.0 pt" was measured on ROUNDED values.** Every adapter rounds
   `advance` to 4 dp, so N12 as first written established equality at the contract's
   precision and reported it as equality. Raw, the advances differ by up to 4.40e-7 pt
   (pdfminer) and 3.05e-5 pt (PyMuPDF). The raw and contract levels are now reported as
   the separate measurements they are: `h06` for the raw distance, `h04`'s N12 for equality
   of the packed values.
9. **The 16.2-point engine-change cost was an UNPAIRED subtraction** across 69 and 62 pairs.
   Paired, it is +16.12 (pdfminer) and +11.59 (PyMuPDF) on the primary adjudication. The
   number barely moved; the licence to state it did not exist before.
10. **N1 claimed an item-by-item replication of phase 2 that it was not performing.**
    `g04_boundary_scores.json` stores only disagreements, so phase 3 had reconstructed the
    expected value from `pdfium_own`. `h07` now re-runs g04's code path and compares the
    full 72-decision vector.
11. **0.9683 was the headline number throughout the first draft.** It is the *post-hoc*
    figure, obtained by dropping the inconsistent class phase 1 identified in its own
    adjudication. The primary adjudication gives **0.9275**, and that is now the headline
    everywhere, with 0.9683 kept and labelled as the sensitivity analysis it is.
12. **`h06`'s bins were computed against 5e-5 and labelled as 1e-4.** The reported "origins
    differ by more than 1e-4 on 22,745 and 107,141 endpoints" was wrong: those are the
    ≥5e-5 counts. The true ≥1e-4 counts are **901 and 34,157**. A reporting and binning
    defect, not a change in the portability result.
12b. **The fix for 12 introduced a false theorem, which is the more serious error.** It
    argued that because no raw advance delta reaches 5e-5, the rounded values must agree.
    **That does not follow.** Half a step bounds one value against its own rounded form, not
    two values against each other: `round(1.234949, 4) = 1.2349` and
    `round(1.234951, 4) = 1.2350` differ although the inputs are 2e-6 apart. No measurement
    changed — the repair is to stop inferring and to cite the direct measurement instead.
    `h04`'s N12 compares the packed contract values and finds max |delta| = 0.0 pt.
13. **N16's rematch validated only one endpoint.** It required both codepoints and the
    **first** glyph's origin and baseline, then the prose claimed the recovered pairs were
    the same pairs separated by a bucket edge. Both endpoints are now constrained; the
    result is unchanged (4,558 rematched, 0 ambiguous, 0 disagreements), so the claim is
    now established rather than assumed.
14. **"It is body prose" was an inference from font size alone.** The measurement supports
    only that the unjoined population is strongly under-represented in above-modal-size
    text. Semantic heading-versus-body classification needs the heading oracle this project
    does not have.
15. **"Single-precision storage is the entire residue" claimed a cause from a pattern.**
    `h08` now establishes the code path and demonstrates at runtime that MuPDF's geometry
    structs quantise to float32, with a negative control. The wording is scoped to what
    that shows, and still does not claim no other rounding contributes.
16. **A 20-minute O(n²) in this phase's own harness.** `h06`'s type-size profile evaluated
    `Counter(joined_sizes).most_common(1)` inside a generator condition, rebuilding a
    195,291-element counter once per element. Found by sampling the process rather than by
    guessing; the modal size is now computed once.

---

## 8. Evidence still blocking an ADR

Unchanged from phases 1 and 2. Phase 3 closes none of them:

1. **A valid heading-level oracle.** Still a parser known to drop `<quoted-block>`.
2. **A fresh, structure-rich holdout**, membership and hashes frozen before scoring. Phase 3
   scores the same five development documents phase 1 drew its sample from, deliberately,
   so the frozen sample stays the frozen sample. Nothing here generalises past them.
3. **Blinded heading adjudication.**
4. **The corpus-scale display-split scan** (phase 2's flip condition 1).
5. **An API-stability plan** for whichever set is adopted.

Phase 3 adds two of its own:

6. **`font_size`'s axis must be specified in the contract** before either design ships. It
   is one line of definition and it is currently undefined; D1 shows it is load-bearing.
7. **The extended contract must exclude U+0020** if the design is adopted, and the exclusion
   needs a test, because D2 shows an adapter can satisfy the docstring's *letter* while
   passing the engine's decision through.

Items 1 and 2 remain blocking.

---

## 9. Recommendation

> **Hybrid remains the preferred candidate on the evidence measured so far, but phase 3
> materially strengthens the extended-glyph alternative by demonstrating cross-engine
> portability rather than merely asserting it.**

Accuracy is tied within PDFium (phase 2) and now tied across engines (phase 3), so accuracy
still does not decide it. What phase 3 changes:

- extended glyph's engine independence is **demonstrated**, not asserted, and priced at the
  11.6 to 16.1 paired points hybrid would give up if ADR 0002 were reopened, one-directional
  (18 boundaries corrected across the two engines, none regressed);
- extended glyph carries **one more unspecified contract field** than phase 2 recorded
  (`font_size`'s axis), which is a real cost on its side of the ledger;
- the "one ironic magic constant" cost is unchanged, and D2 removes a different one: the
  design does not need the engine's spaces, so nothing about it depends on `IsGenerated`.

The heading oracle and the fresh holdout remain blocking for an ADR, so no recommendation
here should be read as "adopt". The defensible statement is the phase-2 one with phase 3's
row substituted for its assertion:

> The engine's word-boundary decision is at least as good as anything DeltaTrack would
> write, measured by writing it and finding zero disagreements. Writing our own buys engine
> independence that ADR 0002 has already declined, and phase 3 has now measured what that
> independence is worth rather than assuming it.

### Do this phase's corrections overturn the cross-engine result?

**No, and the reason is that every correction moved a claim's precision or its licence, not
its direction.**

| correction | effect on the cross-engine result |
|---|---|
| advances equivalent-at-precision, not identical | **none.** The architecture needs the engines to agree more closely than the rule can distinguish. They agree 3 to 11 orders of magnitude more closely than that |
| origins differ above contract precision | **none.** The residue is ~1e-3 pt against thresholds of 1.7–2.2 pt |
| paired instead of unpaired deltas | **strengthens.** 16.2 → 16.12 and 12.7 → 11.59, now licensed, and the discordant counts show the gain is one-directional |
| 0.9275 headline instead of 0.9683 | **none for portability.** All three engines move together; the *tie* is unaffected by which adjudication is quoted |
| N1 narrowed then genuinely widened | **strengthens.** The replication now compares 72 decisions against phase 2's own code path, not 0 |
| threshold bins mislabelled (5e-5 reported as 1e-4) | **none, and it sharpens the advance claim.** No advance count moved; the corrected origin counts are *lower* than stated |
| N16 rematch validated one endpoint | **strengthens.** The two-endpoint rule returns the same 4,558 with 0 ambiguous and 0 disagreements, so the claim is now established |
| heading/body wording narrowed | **none.** The measurement is unchanged; only the inference drawn from it is withdrawn |
| float32 mechanism | **none.** Explanatory, not architectural. Now demonstrated (`h08`) rather than asserted |
| 2.28 % unjoined characterised | **strengthens.** 99.5 % is a bucket artefact that agrees on rematch under a two-endpoint rule; the 21 real absences are the known U+FFFD case; the gap is strongly under-represented in above-modal-size type |

### Is the word-spacing question closed?

**Yes.** Three phases have now asked whether the seam between a PDF engine and DeltaTrack
should carry word spaces, and the word-spacing-specific evidence has converged: the rule is
recoverable above the seam (phase 1), it ties the engine on adjudicated truth (phase 2), and
it ports across every engine that can supply the facts (phase 3). No remaining
word-spacing-specific measurement would change the architectural choice, because accuracy
stopped discriminating two phases ago and portability has now been measured rather than
assumed.

**Continuing to probe the same 72-pair development sample would be optimisation against a
fixed sample, not evidence.** The two items that have blocked an ADR since phase 1 are not
about word spacing at all, and they are where the next work belongs:

1. a valid heading-level correctness oracle, with blinded heading adjudication;
2. a genuinely fresh, structure-rich holdout, membership and hashes frozen **before** either
   contract is scored.

Both should score **hybrid and corrected extended glyph side by side**, because phase 3 has
made extended a credible architectural alternative rather than a discarded option. "Corrected"
means with `font_size`'s axis specified and U+0020 excluded from the contract.

---

## Reproduction

Run from the repo root with the worktree venv. `h02` needs the phase-1 node tree:

```
.venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase3/h01_advance_semantics.py
cd docs/research/pdf-backend-bakeoff/validation/phase3
NODE_PATH=../../probes/js/node_modules node h02_pdfjs_percharacter.mjs <pdf> <page>
.venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase3/h03_score_cross_backend.py
.venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase3/h04_page_scale_agreement.py
.venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase3/h05_diagnose_divergence.py
.venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase3/h06_raw_precision.py
.venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase3/h07_paired_and_replication.py
.venv/bin/python docs/research/pdf-backend-bakeoff/validation/phase3/h08_mupdf_precision_path.py
```

`h06` takes a few minutes: the perturbation bracket walks a decade-spaced ladder over every
compared pair. `h07` re-runs phase 2's `g04` as a subprocess to a scratch path and does not
touch `g04_boundary_scores.json`.

Versions: pypdfium2 5.12.1 (PDFium 152.0.7947.0), pdfminer.six 20260107, PyMuPDF 1.28.0
(MuPDF 1.29.0), pdfjs-dist 6.2.108, Python 3.12.12, macOS / arm64. Every number in this
document comes from `results/`; none is transcribed by hand.
