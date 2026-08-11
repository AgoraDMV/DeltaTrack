# Phase 2 — is an extended glyph contract a better seam than the hybrid?

- Run 2026-08-06. **Phase 1 (`../FINDINGS.md`) and every spike artefact are unchanged**;
  this is a new phase, not a rewrite. Pre-validation tree is tagged
  `pdf-bakeoff-prevalidation` and hashed in `../PRESERVED-MANIFEST.txt`.
- Probes are `g01`–`g07` here; raw output in [`results/`](results/).
- The question: **can DeltaTrack extend the neutral glyph contract with the minimum extra
  low-level facts needed to recover word boundaries at hybrid-level accuracy, without
  consuming an engine-generated text stream?**

**Answer: yes, it can, and the result is an exact tie on accuracy. Accuracy has therefore
stopped discriminating, and the decision is now purely architectural. On the architecture I
recommend the hybrid — but for a different reason than `RESULTS-HYBRID.md` gives, and with
a stated condition that would flip it.**

> **Phase 3 has since tested two claims this document made without measuring them, and
> found two defects in this phase's own work.** Read
> [`../phase3/FINDINGS-CROSS-BACKEND.md`](../phase3/FINDINGS-CROSS-BACKEND.md) after this
> one. Nothing below is rewritten; the rows phase 3 replaced are marked in place, and every
> phase-2 result file is untouched. In short: the portability claim is **supported**, one
> backend reason in §G3 was wrong, and `pdfium_extended.py` was consuming PDFium's
> generated spaces despite its docstring saying it does not. That last one contaminated
> `g05` and `g06`; the corrected contract scores identically.

---

## The feasibility gate

### G1 — does v03's result survive when PDFium supplies its own advance widths?

**Yes, and it improves.** Phase 1 took the advance widths from pdfminer, which is a
borrowed fact. The API path, all three calls Experimental:

```
FPDFText_GetTextObject(text_page, i)      -> FPDF_PAGEOBJECT
FPDFTextObj_GetFont(obj)                  -> FPDF_FONT
FPDFFont_GetGlyphWidth(font, cp, sz, &w)
```

Feeding those advances to the same `GenerateSpace` port, scored against PDFium's own
decisions over 20 pages each:

| document | pairs | phase 1 (pdfminer advances) | **phase 2 (PDFium's own)** |
|---|---|---|---|
| `118-hr-4366/5` | 22,256 | 27 errors | **0** |
| `116-hr-1865/6` | 48,320 | 0 errors | **0** |
| `114-hr-2029/4` | 21,098 | 3 errors | **1** |
| `CRPT-118srpt198` | ~52,000 | — | **1** |

Ink-character coverage is 1.0 on all four. Negative controls fire: perturbing the advances
+25 % gives 61–484 errors, −25 % gives 1,933–22,878.

**The predicted defect is real and is narrow.** `FPDFFont_GetGlyphWidth` takes a *Unicode
codepoint* and reverse-maps it with `CharCodeFromUnicode`, whereas PDFium's own rule uses
the content stream's charcode directly. The reverse map fails on exactly one codepoint in
this corpus — GPO's soft hyphen — returning TRUE with a width of 0. A returned TRUE is not
a returned advance, which is why zero width is counted separately from coverage.

### G2 — are the extended fields actually available in the browser build?

**Yes, with no wrapper work and no custom build.** All three calls are declared *and
executed* in `@embedpdf/pdfium` 2.15.0. Ink advance sequences are **identical** native vs
WASM, index for index:

| document / page | ink chars | advance sequences identical |
|---|---|---|
| `114-hr-2029/4` p99 | 987 | **yes** |
| `118-hr-4366/5` p26 | 1,130 | **yes** |
| `CRPT-118srpt198` p1 | 967 | **yes** |
| `116-hr-1865/6` p1 | 1,633 | **yes** |

Same `U+0002` zero-advance in both builds. The builds still disagree on *space* characters
(`RESULTS-HYBRID.md` §7) — the extended design consumes no engine spaces, so that surface
is not in its path at all.

### G3 — can the other backends supply the fields from their own APIs?

Tested **by value, never by field name**: the advance must predict the next character's
pen-origin delta on the same baseline to within 0.5 pt, on tight settings.

| backend | origin | advance | per character | rate |
|---|---|---|---|---|
| PDFium | `FPDFText_GetCharOrigin` | the three-call chain | yes | 805/805 **1.0** |
| pdfminer.six | `LTChar.x0` | `LTChar.width` | yes | 801/801 **1.0** |
| PyMuPDF | `get_texttrace()` origin | `get_texttrace()` advance box | yes | 805/805 **1.0** |
| PDF.js | item `transform[4]` | — | **no**, ~13 chars/item | **fails** |

Two corrections found by measuring rather than by reading attribute names, either of which
would have produced a false negative: **pdfminer's `LTChar.adv` is in em units, not
points** (`.width` is the points advance), and **PyMuPDF exposes the advance through
`get_texttrace()`**, not through `Font(fontname=…)`, which cannot instantiate GPO's
embedded DeVinne faces and covered only 36 of 987 characters.

That is the **same portability profile as the hybrid**: three backends in, PDF.js out, for
the same per-character-granularity reason ADR 0003 already records.

> **Phase 3 correction to this table's reasons, not to its verdicts** (`../phase3/`, §1–2).
> The table's three verdicts stand. Two of its reasons do not.
>
> - **pdfminer.** `LTChar.adv` is the advance in *text space* (`textwidth × fontsize ×
>   scaling`), not em units. It reads as em only because GPO writes `Tf 1` and carries the
>   size in the text matrix. `.width` is that value transformed into page space, which is
>   the space the rule works in, so the field choice above is right and the reason is not.
> - **PyMuPDF.** The `Font` route is open after all: `extract_font(xref)` yields the
>   embedded program and `Font(fontbuffer=…)` instantiates it, agreeing with
>   `get_texttrace()` at rate 1.0 over 987–1,633 characters per page. Two independent
>   routes, not one.
> - **PDF.js.** Granularity is the limitation of `getTextContent()` only. `getOperatorList()`
>   exposes a genuine per-character advance at coverage 1.0. The blocker is that **no PDF.js
>   API exposes a per-character pen origin**. Verdict unchanged, reason corrected.

### G4 — Experimental API burden

| design | Experimental APIs | which |
|---|---|---|
| glyph today | **2** | `GetFontInfo`, `GetMatrix` |
| hybrid | **5** | + `IsGenerated`, `IsHyphen`, `HasUnicodeMapError` |
| extended glyph | **5** | + `GetTextObject`, `FPDFTextObj_GetFont`, `GetGlyphWidth` |

A tie in count, asymmetric in kind. **Hybrid's set is reducible to 3**: `IsHyphen` is
information-equivalent to `cp == 0x02` (phase 1 §11) and `HasUnicodeMapError` is a
diagnostic. **Extended glyph's three advance calls are a chain and none is removable**, and
they pass object handles whose lifetime semantics are subtler than a per-index predicate.

**Gate verdict: PASS.**

---

## The implementation

`contract_extended.py` appends exactly two fields to `contract.Glyph` — `origin_x` (the pen
position, not the ink left edge) and `advance` (the font metric). `pdfium_extended.py` is a
byte-for-byte copy of the glyph backend's rules plus those two fields, and reads no
`get_text_range`, no `IsGenerated`, no engine-decided space.

> **Phase 3 falsifies the last clause of that sentence** (`../phase3/`, §5 D2). The adapter
> never *asks* whether a character was generated, which is what its docstring says, but it
> copies every character on PDFium's text page and PDFium's text page contains generated
> spaces. `reconstruct_extended._line_text` then emits `chr(32)` for each one before the
> geometric rule runs. On `114-hr-2029/4` that is 4,445 engine-invented spaces against 555
> from the content stream, so the reconstruction path was taking eight of every nine word
> boundaries from the engine. **`g04` below is unaffected** (it walks ink pairs and never
> reads a space glyph, confirmed independently by phase 3's N1 control); **`g05` and `g06`
> ran on the contaminated path.** Re-run with every U+0020 dropped from every backend, the
> heading failure cases score 53 ok / 0 bad exactly as below and the reconstructed text is
> identical, so the defect is in the design's stated property rather than in its numbers.
>
> A note on the fix, because it is the cheap one: dropping U+0020 from the contract is also
> how the design excludes engine-invented spaces *without* `FPDFText_IsGenerated`, the
> Experimental predicate it exists to avoid.

`reconstruct_extended.py` changes exactly one thing against `reconstruct.py`: the word-space
rule. **It is labelled in its own docstring as a port of PDFium's heuristic, not as a law of
PDF geometry**, with the costs stated there: upstream may change the heuristic and
DeltaTrack's copy will not, the 400/700/800 constants have no derivation this project can
appeal to, and a bug in it becomes DeltaTrack's bug.

---

## Scoring

### Independently adjudicated word boundaries (the correctness measure)

Phase 1's frozen 72-pair sample, adjudication unchanged and not reopened. All 72 pairs
re-located and asserted.

| path | as adjudicated | inconsistent class dropped (post-hoc) | errors |
|---|---|---|---|
| pdfium | 0.9275 | **0.9683** | 0 missed, 2 spurious |
| hybrid | 0.9275 | **0.9683** | identical to pdfium by construction |
| **extended** | 0.9275 | **0.9683** | 0 missed, 2 spurious |
| glyph | 0.8986 | 0.9365 | 4 missed, 0 spurious |
| pdfminer | 0.8065 | 0.8065 | 2 missed, 10 spurious |

**Extended glyph disagrees with PDFium on zero of the 69 scored pairs**, and matches on
every stratum. It also inherits PDFium's two errors — the spurious splits inside
letter-spaced display caps — because it is PDFium's algorithm.

### The four named heading failure cases (GPO's printing as reference)

| path | correct | malformed |
|---|---|---|
| production | 53 | 0 |
| glyph | 30 | **23** |
| hybrid | 53 | 0 |
| **extended** | **53** | **0** |
| pdfminer | 53 | 0 |

`116-hr-1865/6` is retained as the negative control. **The seam defect that motivated the
entire hybrid question is fixed by adding two fields to the glyph contract**, without
consuming an engine text stream.

### Corpus H1–H5 — MIGRATION PARITY, not correctness

Reference is production. 8 documents, named in `g06_corpus_parity.py` before the run, not
"the first N". `score_hybrid.py` is imported unmodified and one path added, so the four
existing columns cannot drift from §5's. **The `vs_xml` block that scorer also computes is
not used here**: phase 1 established that oracle drops `<quoted-block>` (DeltaTrack#11).

| metric | glyph | hybrid | **extended** | pdfminer |
|---|---|---|---|---|
| H1 text identical | 0/8 | 0/8 | 0/8 | 0/8 |
| H1 mean token F1 | 0.99827 | 0.99934 | **0.99927** | 0.99814 |
| H2 labels exact | 5/8 | 7/8 | **7/8** | 7/8 |
| H2 labels production does not produce | 206 | 1 | **1** | 1 |
| H2 production labels missed | 186 | 1 | **1** | 1 |
| H3 breadcrumb agreement | 0.95493 | 1.0 | **1.0** | 1.0 |
| H4 line-number sets identical | 6/8 | 7/8 | **6/8** | 6/8 |
| H5 amount→heading agreement | 0.97556 | 1.0 | **1.0** | 1.0 |

**Two small places where extended is behind hybrid, and they are the only ones:**

- **H4 on `116-hr-1865/6`**: extended yields 117 line numbers to hybrid's 115, Jaccard
  0.983, losing set identity. Two spurious margin numbers on one enrolled bill.
- **H1 token F1 is marginally lower on 6 of 8 documents** (e.g. 0.99878 vs 0.99892). Tiny,
  and consistent in direction, which is why it is reported rather than rounded away.

### Native vs WASM

Covered by G2 above for the extended fields, and by phase 1 §9 for the hybrid's flags.
Both designs' facts agree across builds on the pages tested. Neither has been checked at
full corpus scale.

### Cost and complexity

| | extraction, vs hybrid | new code DeltaTrack owns | magic constants |
|---|---|---|---|
| hybrid | 1.00× | none | none |
| **extended** | **1.01–1.13×** | the ported rule + the advance chain | **one** |

**Extraction cost is not a differentiator, and an earlier figure in this review's own
commit log was misleading.** The 2.8–4.3× measured in G1 was against a *minimal*
per-character loop, not against the hybrid. Measured directly against the hybrid backend it
is 1.01–1.13×.

**The magic constant is a real cost and it is the ironic one.** `FPDFFont_GetGlyphWidth`
cannot supply an advance for GPO's soft hyphen, so `reconstruct_extended` falls back to
`_ADVANCE_FALLBACK_EM = 0.5`. Measured on `118-hr-4366/5`, the glyphs in the kept
population with no advance are **exactly U+FFFD** — 358 over 60 pages, about 6 per page,
all line-final soft hyphens. So the design that exists to remove `_SPACE_FACTOR`
reintroduces a different unexplained constant, on a narrow and well-understood population.

---

## The architectural comparison, since accuracy no longer discriminates

| | **A. extended glyph** — richer portable contract, DeltaTrack owns word segmentation | **B. hybrid** — engine text decisions, DeltaTrack owns printed-line and GPO interpretation |
|---|---|---|
| adjudicated accuracy | 0.9683 | 0.9683 — **tied, 0 disagreements** |
| heading failure cases | 53/0 | 53/0 — tied |
| migration parity | slightly behind (H4 on one doc, H1 F1 on 6/8) | slightly ahead |
| backends that can emit it | 3 of 4 | 3 of 4 — tied |
| Experimental APIs | 5, none removable, handle-chain | 5, reducible to 3, per-index predicates |
| extraction cost | 1.01–1.13× | 1.00× |
| code DeltaTrack maintains | a ported Chromium heuristic | none |
| unexplained constants | one (`_ADVANCE_FALLBACK_EM`) | none |
| **word quality if the backend changes** | **fixed — the rule is ours** | **the backend's: pdfminer scores 0.807 against PDFium's 0.968 on truth** |
| **PDFium's `R E P O R T` split** | **fixable in-repo** | not fixable |

> **The last-but-one row was an assertion when this table was written. Phase 3 measured it,
> and it holds** (`../phase3/`, §3–4). The same `wants_space` fed each engine's own facts
> scores **0.9275 from PDFium, pdfminer and PyMuPDF alike on the primary adjudication**
> (0.9683 in phase 1's post-hoc sensitivity analysis), with 0 pairwise disagreements on the
> 72 adjudicated pairs and 1 in 195,291 at page scale. Under hybrid the swing is now
> measured on two alternative engines rather than one, and **paired**, on exactly the pairs
> where both the engine's own decision and the rule have an answer: **+16.12 points** over
> pdfminer's own decision and **+11.59** over PyMuPDF's, correcting 10 and 8 boundaries
> respectively and regressing none.
>
> The *mechanism* is narrower than "the rule is ours" implies, and it sits at two separately
> measured levels. **Raw** (`h06`): the engines' returned advances are not bit-identical,
> differing by at most **3.05e-5 pt** over 390,582 endpoints. **Contract** (`h04` N12): once
> packed into the four-decimal contract, the compared advances are **identical**, max delta
> **0.0 pt** on the same endpoints. The second is measured directly on the packed values,
> not inferred from the size of the first. The extended contract is not normalising a
> difference between engines; it is asking for a quantity on which they barely differ.
>
> Phase 3 also adds a row to the **cost** side that this table does not carry:
> `contract_extended.font_size` has **no defined axis**, and the ported rule buckets on it.
> PDFium and PyMuPDF report the horizontal type scale, pdfminer the vertical; GPO's
> condensed display type (text matrix `12 0 0 13`) separates them on 2.9 % of pairs, and
> that is the cause of the single page-scale disagreement.

---

## Recommendation

> **Corrected in strength, 2026-08-06.** This section originally opened "Adopt the hybrid
> contract." That is stronger than this document's own "Evidence still blocking an ADR"
> section supports, since a valid heading oracle and a fresh structure-rich holdout are both
> listed there as blocking and neither is closed. The recommendation now reads as a standing
> preference, not an adoption. Nothing else in the reasoning changed.

**Hybrid remains the preferred candidate on the evidence measured so far.** Accuracy is
tied on every measure taken, portability is tied, and cost is close enough not to decide
it. What separates them is that hybrid takes
on no new code and no new constant, while extended glyph asks DeltaTrack to own and
maintain a heuristic Chromium wrote for a different purpose, plus a fallback constant for a
character PDFium's own public API cannot measure.

The two genuine advantages of extended glyph — engine-independent word quality, and the
ability to fix PDFium's display-caps split — are **option value the project has decided not
to exercise**. ADR 0002 pins pypdfium2 as the single engine, and PDF.js can satisfy neither
contract, so the backend the hybrid binds to is the backend that is already bound.

**Prefer it for the corrected reason, though.** Not "geometry alone is insufficient", which
phase 1 falsified and phase 2 has now falsified a second way, by building the geometric
path and tying. The rationale an ADR could rest on, once the two blocking items below are
closed, is:

> The engine's word-boundary decision is at least as good as anything DeltaTrack would
> write — measured, by writing it and finding zero disagreements — and writing our own buys
> engine independence that ADR 0002 has already declined. Extended glyph is the better
> contract *if* that decision is reopened, and the work to build it is done and measured.

**What would flip this.** Any one of:

1. **The display-type split reaches account headings at corpus scale.** Phase 1's `v08`
   scan found `R E P O R T` and `C O N T E N T S` on the committee report and nothing on
   five bills. Run it over all 52 documents and the holdout. If PDFium splits a real
   account name anywhere, owning the rule stops being optional, because the heading tree is
   the financial data contract.
2. **ADR 0002 is reopened** and a second engine becomes real. Under hybrid, the measured
   quality swing is 16 points; under extended glyph it is zero.
   *(Phase 3 has now measured both halves of that sentence rather than asserting them, and
   paired: the swing is **+16.12** points to pdfminer and **+11.59** to PyMuPDF on the
   primary adjudication, and extended glyph's is zero on both, with 0 disagreements on the
   adjudicated sample and 1 in 195,291 at page scale.)*
3. **The Experimental handle-chain proves more stable than the flags**, reversing the API
   argument. Nothing here tests that; it is an upstream-history question neither phase
   answered.

---

## Evidence still blocking an ADR

Unchanged from phase 1, and phase 2 does not close any of them:

1. **A valid heading-level oracle.** Every "matches production's accuracy" sentence still
   rests on a parser known to drop `<quoted-block>`. Phase 2 deliberately did not use it.
2. **A fresh, structure-rich holdout**, membership and hashes frozen before scoring. All
   generalization still rests on the 52 development documents, and phase 2's parity table
   is 8 of them.
3. **Blinded heading adjudication** — whether the shared 1-extra/1-missed label on
   `118-hr-2882/5` is parity with truth or with a shared PDFium reading.

Phase 2 adds two of its own, both cheap:

4. **The corpus-scale display-split scan** (flip condition 1 above).
5. **An API-stability plan** covering whichever set is adopted: pinned PDFium revisions for
   both builds, a startup capability assertion, and a corpus-level invariant that would
   move if upstream changed the semantics.

Items 1 and 2 remain blocking. 3–5 can be follow-ups if the ADR states them as open.

Phase 3 adds two more, both design-level rather than evidence-level:

6. **`contract_extended.font_size` needs its axis specified.** PDFium and PyMuPDF report the
   horizontal type scale, pdfminer the vertical, and the ported rule buckets on it, so the
   omission is load-bearing under anisotropic type. One line of definition.
7. **The extended contract must exclude U+0020, and the exclusion needs a test.** D2 below
   shows an adapter can satisfy the docstring's letter while passing the engine's decision
   through.

---

## Corrections this phase makes to its own earlier claims

- **Extraction cost.** The 2.8–4.3× figure in `g01`'s commit is against a minimal loop, not
  against the hybrid. The like-for-like number is 1.01–1.13×.
- **A vacuous pass in this review's harness.** `g06`'s first run filtered documents by
  version *slug* while `corpus_documents()` keys by version *number*. It matched nothing,
  scored zero documents, and printed `wrote …`. The filter now asserts that the matched set
  equals the requested set.
- **Two backend APIs were wrong on first reading** (pdfminer's `adv` units, PyMuPDF's font
  path). Both would have produced a false "this backend cannot supply the field", which is
  the failure direction that would have wrongly killed the extended design.

### Corrections phase 3 makes to this phase

Detail and evidence in [`../phase3/FINDINGS-CROSS-BACKEND.md`](../phase3/FINDINGS-CROSS-BACKEND.md) §7.

- **`g03`'s pdfminer reason.** `.adv` is the text-space advance, not em units. The field
  chosen (`.width`) was right; the reason a reader would carry elsewhere was not.
- **`g03`'s PyMuPDF font path.** `Font(fontname=…)` is closed, as recorded, but
  `extract_font(xref)` + `Font(fontbuffer=…)` is open and corroborates `get_texttrace()`.
- **`g03`'s PDF.js reason.** Item granularity limits `getTextContent()` only;
  `getOperatorList()` gives a per-character advance at coverage 1.0. The blocker is the pen
  origin. Verdict unchanged.
- **`pdfium_extended.py`'s "never consumes a space the engine decided to insert".**
  Falsified. `g05` and `g06` ran on that path; `g04` did not. The corrected contract scores
  identically, so no number above moves.
- **`contract_extended.py`'s "no backend is asked to reproduce another's conventions".**
  True of `origin_x` and `advance`; not true of `font_size`.
- **The portability row in the architectural table**, and flip condition 2, were assertions
  when written. Phase 3 measured both and both hold.
- **The `0.9683` column below is the POST-HOC figure**, obtained by dropping the inconsistent
  class phase 1 found in its own adjudication. The primary adjudication is `0.9275`, and
  both are shown in the scoring table for exactly that reason. Phase 3's first draft used
  0.9683 as its headline throughout and has been corrected to lead with the primary result.
