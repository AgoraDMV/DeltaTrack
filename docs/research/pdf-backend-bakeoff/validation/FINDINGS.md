# Adversarial validation of the hybrid text+geometry conclusion

- Run 2026-08-06 against `RESULTS-HYBRID.md` at commit `3a67b03`, tagged
  `pdf-bakeoff-prevalidation`. **No spike finding, table or probe was modified, and no
  production file was.** Every spike artefact is hashed in
  [`PRESERVED-MANIFEST.txt`](PRESERVED-MANIFEST.txt).
  Three spike documents were later given a pointer to this directory so a reader arriving
  at the spike's front door can find it; that is an addition of navigation, not an edit of
  a result, and [`README.md § Preservation`](README.md#preservation) states exactly what to
  check.
- Probes are `v01`–`v09` in this directory; raw output is in [`results/`](results/).
- The question asked was whether the conclusion *"hybrid text+geometry should replace raw
  glyph reconstruction as DeltaTrack's PDF adapter contract"* may be **wrong**.

**Answer, up front: the conclusion is not wrong, but its stated reason is.** The hybrid
seam is better than the shipped glyph seam on independently adjudicated text, and the
spike's own §4 experiment does not support the architectural sentence built on it. A third
option the spike never scored — extending the glyph contract with two facts it currently
discards — now has to be priced before an ADR can pick between them.

---

## 1. What §4 proves, restated precisely

**As written**, the framing section says geometry is *insufficient*:

> "Lower-level is not the same as more correct … §4 shows the gap between two letters does
> not determine whether a space belongs there, in any print class measured."
> "the engine is not applying a better-tuned version of the same rule; it is deciding with
> information the glyph stream does not carry."

**What the experiment supports:**

> A single global threshold on **ink-box gap ÷ font size** — the rule `_SPACE_FACTOR`
> implements over the fields `contract.Glyph` actually carries — cannot reproduce PDFium's
> word-boundary decisions in any print class measured. Its two class distributions overlap.

**What falsifies the broader claim.** PDFium's decision is public and is pure geometry
(`core/fpdftext/cpdf_textpage.cpp`: `GenerateSpace` + `NormalizeThreshold`). It reads two
things and nothing else: **pen origins** and **font advance widths**. No encoding, no
semantics. It is a per-pair adaptive threshold — structurally the same shape as
`_SPACE_FACTOR`, with the constant replaced by a step function of the adjacent characters'
advances.

`v03` reimplements that rule over glyph-level facts and scores it against PDFium's own
decisions (20 pages each):

| document | pairs | errors | recall, all boundaries | recall, **generated** subset |
|---|---|---|---|---|
| `116-hr-1865/6` | 48,320 | **0** | 1.0 | 1.0 (n=210) |
| `114-hr-2029/4` | 21,098 | 3 | 0.9997 | 1.0 (n=3,663) |
| `118-s-4795/1` | 22,066 | 3 | 1.0 | 1.0 (n=566) |
| `118-hr-4366/5` | 22,256 | 27 | 1.0 | 1.0 (n=538) |

The **generated** column is the one that carries the claim: an *explicit* space occupies an
advance of its own, so recovering it from pen origins is near-tautological. Recall is 1.0
on the synthesised subset in all four documents. Negative controls confirm the fit is not
degenerate — perturbing the advances ±25 % raises errors to 73–493 and 1,805–22,831.

**So the glyph seam's deficiency is a contract-design defect, not a proof that word
segmentation must move below the seam.** `contract.Glyph` carries the *ink box* and
`mat.f`; it discards the *pen origin* (`FPDFText_GetCharOrigin`, which the backend already
calls) and the *font advance width*. Both are facts a contract can carry.

**Additional evidence required to establish the broad claim**, if anyone wants it:
a rule using origins + advances would have to fail on a population where PDFium succeeds,
and no such population has been exhibited. `v03` is the falsification probe the review
asked for; it did not need a "more sophisticated geometric algorithm" invented, only
PDFium's own published one transplanted.

A text-object-boundary hypothesis was tested and **falsified**: word boundaries occur
overwhelmingly *inside* a single text object on three of four documents, so
`ProcessInsertObject` is not the gate. Recorded rather than dropped.

**Two further §4 qualifications** (`v02`, fitted-on-test upper bounds, so optimistic):

- A per-`(font, size)` threshold family still cannot separate the classes (129 errors
  pooled). §4's *direction* survives a real attempt to break it.
- The shipped `0.25` is not near the pair-level optimum. Pooled over 169,550 pairs: best
  threshold `0.177` costs 130 missed + 102 spurious; `0.25` costs **498 missed + 0
  spurious**. And `confirm_sensitivity.py` stepped `0.15 → 0.20`, straight past it. "Tuning
  cannot reach zero" is true; "the constant is not where the defect lives" understates a
  3.8× reduction in the *consequential* direction.

  **This is not a recommendation to retune.** The per-document optima scatter (0.169,
  0.178, 0.217, 0.235), so one global value cannot sit at all of them; and
  `confirm_sensitivity.py`'s end-to-end B2 got *worse* at both 0.20 and 0.15, so a
  pair-level gain is not known to survive to a heading metric. The point is narrower and it
  is about the evidence: the sweep never tested the region where the pair-level optimum
  lies, so "0.25 is a reasonable value on a rule that has no correct setting" is asserted
  over a gap in the sweep rather than measured across it.

---

## 2–3. PDFium as oracle, and separability under independent labels

`v04` froze 72 adjacent ink pairs — 8 per stratum, seed `20260806`, from a frame of 200,686
candidates over five print classes (house bill reported in senate, engrossed amendment,
enrolled/unnumbered, senate bill reported, committee report), 24 pages each. Crops are
rasterised with **MuPDF**, which shares no text-extraction code with any scored path. The
key was committed before adjudication; the adjudication was committed before the key was
opened. Strata include the directions §4 never samples: wide gaps PDFium declines to call
spaces, the narrowest it does, letter-spaced display caps, and the 179 pairs where PDFium
and pdfminer disagree outright.

**Accuracy against the printed page** (69 scored, 3 unreadable):

| path | as adjudicated | inconsistent class dropped¹ | errors |
|---|---|---|---|
| pdfium | 0.9275 | **0.9683** | 0 missed, 2 spurious |
| **hybrid** | 0.9275 | **0.9683** | identical to pdfium **by construction**² |
| glyph (`0.25`) | 0.8986 | 0.9365 | 4 missed, 0 spurious |
| pdfminer | 0.8065 | 0.8065 | 2 missed, 10 spurious |

¹ Post-hoc, and it moves every number the same way, so it is labelled. See §Reliability.
² `reconstruct_hybrid._line_text` joins the engine's characters and applies no spacing rule.
The hybrid's word-boundary accuracy *is* PDFium's. Reporting them as two columns is
misleading and the spike's tables invite it.

**The direction of §3 survives independent labels.** Item `B67` is `FAMILY|HOUSING` at
gap/size `0.2248`: adjudicated BOUNDARY, PDFium right, glyph rule wrong — with a label that
did not come from PDFium. And the two seams fail in **opposite directions**: the engine
*splits*, the glyph rule *welds*. That is the asymmetry §4 argues from, now measured against
truth rather than against PDFium.

**But "generated PDFium spaces are the correct word-boundary signal" does not hold.**
PDFium's two errors are both spurious spaces inside letter-spaced display caps, where it
extracts `REPORT` as `R E P O R T`. The glyph rule gets both right. The supported statement
is that the engine's spaces are the **better** signal on this sample, not the correct one —
and the hybrid inherits the error because it inherits the decision.

**Separability under independent labels** (item 3): the distributions still overlap —
boundary min `0.217`, intra-word max `0.228`. So the supported conclusion is exactly the one
the review proposed: *no single global gap/size threshold can perfectly classify these
independently adjudicated boundaries.* Best threshold `0.217` → 4 errors of 69; shipped
`0.25` → 7. **The sample is stratified toward hard cases, so these are not corpus rates.**

### Reliability of this review's own adjudication

Six items are the **identical stimulus** — `'1'|'1'`, gap 3.038, size 14.0, Times-Roman: the
two digits of a margin line number `11` — and were answered 3 BOUNDARY / 3 NO_BOUNDARY. On
that class the adjudicator is demonstrably unreliable. The frame is also at fault: the dedup
key was `(doc, page, x)`, so one recurring stimulus was drawn six times across three strata.
Both repairs are post-hoc and both favour pdfium/hybrid/glyph over pdfminer.

**Blinding limit, stated rather than claimed away:** the adjudicator is the same agent that
built the frame. The artefacts enforce that no backend's answer was visible at adjudication
time; they do not make this a second-party judgement.

---

## 4. Heading validation — PARTIAL

Not done as specified. What was done instead, and what it shows:

- The `small_caps` stratum (font or size change across the pair) scored **1.0 for every
  path**, so the 302-label glyph defect does not reproduce as a *spacing* error in that
  stratum on this sample.
- `B67` independently confirms the `FAMILY HOUSING` failure case.
- `v08` bounds the shared-interpretation risk directly. Scanning **the engine's own text**
  for the letter-spaced-split signature (3+ single-character tokens on a line), 40 pages
  each: 2 hits on the committee report, both display-sized (`R E P O R T`, `C O N T E N T S`),
  and **0 on all five bills**. So the one place PDFium's interpretation is demonstrably
  wrong about display type does not reach an appropriations account heading in the bills
  tested.

**Not established:** whether the hybrid's 2-spurious/2-missed corpus heading result is
parity with the correct printed label or parity with a shared PDFium reading. The
`COUPS D'ÉTAT` case is the report's own admission that on at least one label **both**
production and hybrid are wrong, differently. A blinded heading adjudication remains the
right test and was not run.

---

## 5. The XML accuracy oracle — NOT ADDRESSED

The review is right that §6 can only discriminate on documents affected by DeltaTrack#11,
and that using the defective parser as the decisive accuracy oracle is unsound. Neither
remedy was built. **Every sentence of the form "the hybrid matches production's accuracy"
should be read as unsupported until one of them is**, because the stratum that produces it
is the stratum whose reference is known to be missing content.

Partial mitigation from this review: §2–3 above supply *independently adjudicated* accuracy
at the word-boundary level, which is the level the heading defect originates at. That is not
a substitute for heading-level accuracy.

---

## 6. Fresh structure-rich holdout — NOT BUILT

Not attempted. It requires fetching appropriations bills outside P1 across chambers, stages
and Congresses, freezing membership and hashes before scoring, and then a full pipeline run
(the existing per-corpus scorers are ~90 min each). **Every generalization claim in
`RESULTS-HYBRID.md` therefore still rests on the same 52 documents the layer was developed
against**, and the previous confirmatory holdout was, as the review notes, dominated by
non-appropriations bills and could not exercise heading metrics.

---

## 7. The selective abstraction boundary — JUSTIFIED, on the side that matters

§7 justified not trusting the engine for lines with one instance. Measured across five
documents × 30 pages against the distinct ink baselines on each page (`v07`):

| document | printed lines | engine lines | error | engine rows spanning >1 printed line |
|---|---|---|---|---|
| `114-hr-2029/4` | 792 | 610 | −182 | 129 |
| `116-hr-1865/6` | 1,569 | 1,422 | −147 | 126 |
| `118-hr-4366/5` | 811 | 634 | −177 | 122 |
| `CRPT-118srpt198` | 1,479 | 1,092 | −387 | 268 |
| `118-s-4795/1` | 780 | 602 | −178 | 125 |

The engine emits 19–26 % fewer rows than the page has printed lines, and **23–29 % of its
numbered-body rows span more than one baseline** (50 % on the committee report). GPO's
margin-numbered body is the layout the product exists to read, so this is not an
exotic-layout result.

**Half of this comparison is circular and is reported as such:** clustering kept characters
by baseline and counting distinct ink baselines are nearly the same computation, so the
geometric side's "0 error, 0 straddles" is definitional. The engine-versus-ink comparison is
independent — break characters do not move ink — and it is the whole finding.

**So the answer to "why does word segmentation belong below the seam while printed-line
reconstruction belongs above it" is not the one §7 gives.** It is not that the engine knows
more about words and less about lines in some general sense. It is that:

- for **lines**, the engine's output is measurably *not* a model of printed lines at all —
  it is a reading-order stream, and 19–26 % short;
- for **words**, the engine's output *is* a model of word boundaries, and a good one, but
  the information it uses (origins + advances) is recoverable above the seam (§1).

Note this does not separate hybrid from glyph — both assign lines geometrically. It
separates both from any pipeline that takes line structure from the engine's stream.

---

## 8. Generated-character geometry — CONFIRMED, with three qualifications

§2's origin claim holds, and more strongly than stated. Over four documents × 40 pages
(`v06`): every generated character's `origin_y` sits at offset **exactly 0.0** from an ink
baseline on its page; **100 %** are assignable to exactly one printed line at the 0.6 pt
tolerance the layer uses; **0** ambiguous, **0** orphaned. The value is right, not merely
returned.

Qualifications the report does not carry:

- **Generated spaces that bridge two printed lines**: 1 of 7,569 (`114-hr-2029/4`), 0, 0,
  and **12 of 435** on the committee report. Small but non-zero, and this is the failure the
  design would not survive at scale, because the layer *keeps* generated spaces.
  (A first cut pooled CR/LF with spaces and read 87 % "bridging"; generated line breaks are
  supposed to bridge, so they are counted apart.)
- **Rotated text is untested, not passed.** `rotated_generated` is 0 on every document —
  PDFium generated no characters in rotated text at all.
- **The contract and the code disagree.** `contract_hybrid.py` and §2 both say a generated
  char's `x0` is `None`; `backends/pdfium_hybrid.py` stores the origin's X there, for every
  one of them. Nothing downstream reads it today (consumers gate on `cp == 32` first), but
  the "fail loudly" property §2 claims is not the property the code has.

---

## 9. WASM invariants at corpus scale — PARTIAL

`probe_hybrid_portability.py` never compares `IsGenerated` or `IsHyphen`, and those two
flags *are* the contract. Compared **by position** rather than by index (`v09`), since §7
already established the raw streams differ:

| document | ink codepoint sequence | generated-space positions differing | hyphen positions differing |
|---|---|---|---|
| `118-hr-4366/5` | identical 15/15 pages | 0 | 0 (96 = 96) |
| `116-hr-1865/6` | identical 15/15 | 0 | 0 (78 = 78) |
| `CRPT-118srpt198` | identical 15/15 | 1 native-only | 0 (161 = 161) |

`IsHyphen` agrees exactly in count and position on all three. Total character counts still
differ — the trailing-space divergence §7 documents. **Scale: 3 documents × 15 pages, not
the 52-document corpus.** This narrows the native/WASM asymmetry on the two Experimental
entry points; it does not close it. Heading labels, amount→heading association and line
assignment under WASM were not re-measured here beyond what the spike already did.

---

## 10. API stability — the risk is real and unpriced

- Both `FPDFText_IsGenerated` and `FPDFText_IsHyphen` are marked **`// Experimental API.`**
  in `public/fpdf_text.h`. So are `FPDFText_HasUnicodeMapError`, `FPDFText_GetMatrix`,
  `FPDFText_GetFontInfo`, `FPDFText_GetFontWeight`, `FPDFText_GetLooseCharBox`,
  `FPDFText_GetCharAngle`, `FPDFText_GetTextObject`, `FPDFText_GetFillColor` and
  `FPDFText_GetStrokeColor`. `backends/pdfium_hybrid.py` calls **five** of them —
  `IsGenerated`, `IsHyphen`, `HasUnicodeMapError`, `GetMatrix`, `GetFontInfo`. The
  dependency is wider than the two functions the review names. (`CountChars`, `GetUnicode`,
  `GetCharBox`, `GetCharOrigin` and `GetFontSize` are *not* marked Experimental, so the
  index identity §1 rests on is on stable ground; the flags and the font/matrix metadata
  are not.)
- PDFium publishes no ABI/deprecation policy page (`docs/api.md` is 404), and the header
  carries no blanket definition of what "Experimental" promises. **"Exported today" is not a
  stable public contract, and nothing found here upgrades it to one.**
- `@embedpdf/pdfium` 2.15.0 declares both entry points in `dist/vendor/functions.d.ts`, so
  they are in that build's *stated* surface rather than incidentally exported. That is a
  vendor-generated table with no versioning promise attached.
- **Behavioural consistency across the two revisions is measured, not assumed** (§9): the
  flags agree by position on 45 pages. Introduction versions and cross-version semantic
  changes were **not** established — the search did not surface a changelog, and the git
  history was not walked.

**Pinning/regression tests an adapter would need**, none of which exist today: a pinned
`pypdfium2` *and* `@embedpdf/pdfium` version with the PDFium revision recorded; a startup
assertion that both entry points return a value other than `-1` on a known fixture; a
corpus-level invariant on generated-character *rate* (a silent semantic change would move
it); and a fixture asserting `IsHyphen` fires on GPO's soft hyphen and not on ASCII `-`.

---

## 11. `FPDFText_IsHyphen` for syllable breaks — HALF SUPPORTED, and the wrong half is
load-bearing

Measured over four documents × 40 pages (`v06`):

- The flag **never** fires on an ASCII hyphen: 0 of 20, 47, 25 and 140. So keying a rejoin
  on it **cannot fuse `Child-Rescue`**. That half of §8 holds.
- A weak vocabulary oracle bounds the **false-rejoin rate at 0–0.2 %** (one instance,
  `Emir-ates`) and finds **no missed rejoins** among unflagged line-final ASCII hyphens.
- Continuation case, which is where §8's limitation lives: `lower` 176 / `upper` 6 on the
  enrolled bill; mostly `other` (a margin digit) on numbered layouts.

**But "available to no other layer" does not hold.** The flag fires on *exactly* the set
`cp == 0x02` — 246/246, 182/182, 235/235, 497/497, with **zero** flagged characters outside
it on any document. It is information-equivalent to the raw codepoint, and that codepoint is
already visible to the glyph layer, which carries it as the U+FFFD unnamed-ink marker its
own repair heuristic keys on. What the flag buys is a **documented predicate instead of a
private convention** — a good maintainability argument, and not an information advantage.
Follow-up 3 rests on the wrong half of that.

---

## 12. PyMuPDF — the report is wrong

§7 reports, for PyMuPDF, *"NONE - synthesised spaces get a real box and are
indistinguishable"*, and concludes the hybrid contract *"costs a safety property against
PyMuPDF"*.

In `probe_backend_spacing.py:probe_pymupdf` **that string is a hardcoded literal**. The
function measures `c["bbox"]` and nothing else; no key of the char dict is ever inspected
for a synthesised marker. The cell is an assertion about API shape, not a measurement — the
failure mode §7's own preamble says it exists to avoid.

PyMuPDF exposes `synthetic: bool` on RAWDICT char dicts (added v1.25.3; the spike ran
**1.28.0**). Measured (`v01`):

| document / page | spaces | synthetic | real | flag discriminates |
|---|---|---|---|---|
| `114-hr-2029/4` p99 — **the §7 probe boundary itself** | 155 | 5 | 150 | yes |
| `118-hr-2882/5` p711 | 211 | 6 | 205 | yes |
| `118-s-4795/1` p40 | 180 | 7 | 173 | yes |
| `118-hr-4366/5` p26 | 176 | 0 | 176 | n/a (no synthetic spaces) |

At the probe boundary the space reads `synthetic: True`. Half the original cell is right —
the box *is* real, unlike PDFium's zero-area point — and the half that carries the
conclusion is wrong.

**Consequence:** the portability table's PyMuPDF row should read *"yes — `synthetic` flag;
real box"*, and the sentence *"the hybrid contract costs a safety property against PyMuPDF"*
should be **withdrawn**. Two of four candidate backends satisfy the contract outright
becomes three of four.

---

## 13. pdfminer at corpus scale — PARTIAL, and the news is bad

The full conceptual hybrid through pdfminer was not implemented. What was measured is
pdfminer's **space decisions at pair level** on the frozen sample, via geometric matching
(same codepoint, left edge within 1.5 pt, vertical overlap; unmatched pairs scored as *not
available*, never as agreement). `LAParams()` defaults were used and are recorded in `v04`.

**pdfminer is materially worse than either PDFium path against the printed page: 0.8065,
with 10 spurious boundaries of 62 scored.** §5 and §6 could not see this, because those
tables score against production and against XML; this one scores against the page. In the
`backend_disagree` stratum pdfminer scored **0.0** — every pair where the two engines
disagree, pdfminer is the one that is wrong.

§7's *"pdfminer.six satisfies the contract outright"* is a claim about contract **shape**
(`LTAnno` is a distinct class carrying no bbox) and remains true as such. It should not be
read, as the surrounding prose invites, as a claim that pdfminer is an equally accurate
source of word boundaries. It is not.

---

## 14. Parity, correctness, generalization and portability, kept apart

| | status | evidence |
|---|---|---|
| **Production migration parity** | **not re-verified by this review** | §5's H1–H5 and the canonical-diff tables were not re-run. They remain the spike's own measurement. Expected to be high *because both paths consume PDFium's text interpretation* — which is why it cannot substitute for the row below. |
| **Independently adjudicated correctness** | **measured, first time** | hybrid/pdfium 0.968, glyph 0.937, pdfminer 0.807 on 69 blind-adjudicated pairs across 5 print classes (§2). Heading-level correctness **not** measured (§4, §5). |
| **Fresh-holdout generalization** | **untested** | no structure-rich holdout was built (§6). All generalization still rests on the 52 development documents. |
| **Backend portability** | **partially re-tested** | PyMuPDF row corrected (§12); native/WASM flag agreement measured at 3 docs × 15 pages (§9); PDF.js untouched. |

---

## 15. Classification

### Every major result

| result | classification |
|---|---|
| No single global `gap/size` threshold separates the classes | **independently reproduced** (§1) and **independently adjudicated** (§2–3) |
| "Geometry alone is insufficient" / "information the glyph stream does not carry" | **contradicted** (§1) |
| The engine's spaces beat the shipped glyph rule on real text | **independently adjudicated** (§2) |
| "The engine nonetheless gets it right" | **contradicted as stated**; better, not correct (§2, §4) |
| Generated characters carry a correct origin and nothing else | **independently reproduced**, with the `x0` contract/code mismatch and 12 bridging spaces as exceptions (§8) |
| Line structure must not come from the engine | **independently reproduced** (§7) |
| Hybrid reproduces production (H1–H5, canonical diff) | **production-parity only**, not re-verified here (§14) |
| "Hybrid matches production's accuracy" (§6) | **still untested** — the oracle is the defective parser (§5) |
| Corpus heading improvement 2/2 vs 302/280 | **production-parity only**; not adjudicated against printed labels (§4) |
| WASM portability of the contract | **partially reproduced**, 3 docs × 15 pages (§9) |
| `FPDFText_IsHyphen` distinguishes syllable from compound hyphens | **independently reproduced** (§11) |
| "…and is available to no other layer" | **contradicted** — identical to `cp == 0x02` (§11) |
| "Costs a safety property against PyMuPDF" | **contradicted** (§12) |
| "pdfminer satisfies the contract outright" | true of contract **shape**; **contradicted** if read as accuracy (§13) |
| Fresh-holdout generalization | **still untested** (§6) |
| API stability of the Experimental entry points | **still untested** beyond cross-build behavioural agreement (§10) |

### The architectural claim

> **B. SUPPORTED BUT NOT CONFIRMED.**

The hybrid clearly fixes the current glyph seam — independently adjudicated, on labels that
did not come from PDFium — and it is the leading design. It is not confirmed, for four
reasons: the *stated reason* for it is falsified (§1), which opens a third option that was
never scored; heading-level correctness has no valid oracle (§4–5); there is no fresh
holdout (§6); and the accuracy comparison that carries §6 rests on a parser the project
already tracks as defective.

It is emphatically **not C**. `_SPACE_FACTOR` is defective *and* this research does
establish that trusting the engine's spaces is better than the shipped rule. What it does
not establish is that the engine's spaces are the *best available* replacement.

### The strongest evidence FOR moving the seam

Independently adjudicated accuracy, on labels PDFium did not produce: **0.968 for the
engine's spaces against 0.937 for the shipped glyph rule**, and the two fail in opposite
directions — the glyph rule *welds* words together (4 missed boundaries, 0 spurious), the
engine *splits* them (0 missed, 2 spurious). Welding an account name misfiles every amount
beneath it and is invisible to any check that counts or sums; splitting one is visible.
`B67` = `FAMILY|HOUSING` is that failure caught in the act, with an independent label.

### The strongest evidence AGAINST moving the seam

PDFium's word-space decision is a **published, purely geometric rule over pen origins and
font advance widths**, and reimplementing it above the seam reproduces the engine's
decisions with 0–27 errors per ~22–48k pairs and **1.0 recall on the generated subset**.
That means the hybrid's entire measured advantage is available *without* moving the seam,
by adding two fields to `contract.Glyph`. Moving the seam also imports PDFium's own errors —
`R E P O R T` — which the glyph rule does not make, and deepens a dependency on entry points
upstream marks Experimental with no stated stability guarantee.

### The three assumptions most capable of invalidating the conclusion

1. **That PDFium's generated spaces are the right answer where they differ from the glyph
   rule.** Now known to be false in at least one class (letter-spaced display caps, §2, §8).
   Bounded to 2 lines of a committee report across 6 documents (§4) — bounded on a small
   sample, not on the corpus. If that class is more common in appropriations headings than
   measured, the hybrid's heading advantage shrinks or inverts, and headings are the
   financial data contract.
2. **That production-parity implies correctness.** §5 and §6 are the bulk of the evidence
   and both are anchored to production or to a parser known to drop `<quoted-block>`. If the
   hybrid's parity is agreement on a shared PDFium reading rather than on the printed label,
   §6's "matches production's accuracy exactly, to five decimal places" is measuring
   agreement between two consumers of the same interpretation.
3. **That the 52-document corpus generalizes.** The layer was written after reading the
   failure cases, on these documents, and no fresh structure-rich holdout has ever been
   scored on heading metrics. The spike answers the fitting objection well for *constants*;
   it cannot answer it for *design choices*.

### The claim I am least confident in

> §6: **"On the stratum that can discriminate, the hybrid matches production's accuracy
> exactly — to five decimal places on all three metrics."**

Five-decimal agreement between two paths that consume the same engine's text interpretation,
measured against a reference that is *known to be missing the very content the stratum is
selected for*, is the weakest link in the document. The report flags both limits honestly in
the surrounding prose — and then the conclusion's "so the parity in §5 is agreement on the
better answer, not agreement on a shared error" leans on it anyway. That sentence is not
supported by that table.

### Minimum additional evidence before writing an ADR that adopts the hybrid contract

1. **Price the third option.** Score an extended glyph contract — `contract.Glyph` plus pen
   origin and font advance width, running PDFium's own rule above the seam — on the same
   metrics as the hybrid. It preserves the bake-off's neutrality principle (every candidate
   backend exposes origins and advances) and, on §1's evidence, may cost nothing in
   accuracy. If it matches, the seam should not move and the ADR is about *fields*, not
   *layers*. **This is the single highest-value experiment remaining.**
2. **A valid heading oracle.** Either a quoted-block-preserving XML reference built outside
   production parsing, or blinded rendered adjudication of the discriminating heading labels.
   Until one exists, no accuracy claim about headings should enter an ADR.
3. **A fresh, structure-rich holdout**, membership and hashes frozen before scoring, with
   multiple appropriations bills across both chambers, several stages and more than one
   Congress — scored on heading labels, parent/child structure and amount→heading
   association.
4. **A bound on the display-type split at corpus scale.** `v08`'s scan is cheap; run it over
   all 52 documents and the holdout. If `R E P O R T`-class splits reach account headings
   anywhere, that changes the recommendation.
5. **An API-stability plan, written down**: pinned PDFium revisions for both builds, a
   startup capability assertion, and a corpus-level generated-rate invariant. The adapter
   would depend on five Experimental entry points, not two.

Items 1 and 2 are blocking. Items 3–5 can be follow-ups if the ADR states them as open.

### Corrections `RESULTS-HYBRID.md` should carry regardless of the decision

- §7's PyMuPDF row and the "costs a safety property against PyMuPDF" sentence — **wrong**
  (§12).
- The framing table's "information the glyph stream does not carry" and §3's "it is deciding
  with information the glyph stream does not carry" — **wrong** as stated; the missing
  information is two specific, carryable fields (§1).
- Follow-up 3's "available to no other layer" — **wrong**; identical to `cp == 0x02` (§11).
- §2's "x0 … set to None" — the code does not do this (§8).
- `reconstruct_hybrid.py`'s module docstring still claims `normalize_raw` is dropped "in
  full", which the spike's own `probe_normalize_raw` falsified; `RESULTS-HYBRID.md` was
  corrected and the docstring was not.
