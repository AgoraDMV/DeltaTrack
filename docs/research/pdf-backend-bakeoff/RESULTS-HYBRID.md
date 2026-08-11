# Which layer should own generic PDF text reconstruction?

- Run 2026-08-06, on the branch `spike/pdf-backend-bakeoff`. **No production code was
  changed and no spacing constant was tuned.** Every probe lives in
  [`probes/`](probes/) and imports `src/deltatrack` unchanged.
- Every table below is generated from raw JSON by
  [`probes/fill_hybrid.py`](probes/fill_hybrid.py). Nothing is transcribed.
- Predecessor: [`RESULTS-CONFIRMATORY.md`](RESULTS-CONFIRMATORY.md), whose
  "finding that reframes Concern A" reported that both PDFium builds, run through the
  bake-off's neutral **glyph** layer, produce 302 heading labels production does not.
  This document asks whether that was a defect of PDFium, of the constant, or **of the
  abstraction boundary**.
- **Successor, and read it before acting on this document:**
  [`validation/README.md`](validation/README.md). An independent falsification pass run on
  the assumption that this document's conclusion is wrong. Its verdict is *supported but
  not confirmed*: the conclusion holds, and **the reason given for it below is falsified**.
  PDFium's word-space rule is published geometry over pen origins and font advance widths,
  so "the engine is the only layer that has the font's own metrics" is not true as stated;
  a contract can carry them. Three further claims here are wrong as written. That opened a
  third seam this document never scored, which phases 2 and 3 then built and measured.
  **Nothing below is edited to agree with it**, for the same reason `RESULTS.md` keeps its
  withdrawn headline: a research record that quietly rewrites its own conclusions cannot be
  audited.

## The question, restated

The bake-off's design rule was that the seam between a PDF engine and DeltaTrack should be
**glyph facts** — positioned marks with no ordering and no spacing — so that no backend
could win by imitating the incumbent's text conventions. That rule is right about what it
was defending against. This document tests whether it also gave DeltaTrack a job it is not
the best-placed layer to do.

Two kinds of interpretation are involved, and the whole answer turns on keeping them apart:

| | what it needs to know | best-placed owner |
|---|---|---|
| **Generic PDF text layout** — which marks form a word, where a word break falls, what a syllable-break hyphen is | the encoding, the text-object structure, and the font's own metrics | the **PDF engine**, which is the only layer that has them |
| **GPO / legislative interpretation** — margin line numbers, running heads, watermarks, heading levels, account structure, amounts | how GPO sets a bill | **DeltaTrack**, which is the only layer that has that |

The glyph seam assigns *both* to DeltaTrack. The hybrid seam assigns the first to the
engine and keeps the second.

**Lower-level is not the same as more correct, and this corpus is a clean demonstration.**
Glyph positions are strictly more primitive than a character stream, and they are strictly
*less* informative about where a word ends: §4 shows the gap between two letters does not
determine whether a space belongs there, in any print class measured. Going lower-level
discarded a decision the engine had already made with information the positions do not
carry. The primitive layer is the right seam when the consumer knows something the producer
does not — which is true of GPO conventions and false of word breaks.

---

# 1. The APIs exist, natively and in the browser build

Every entry point the question named is present in `pypdfium2` 5.12.1 (PDFium
152.0.7947.0), and the browser-shippable `@embedpdf/pdfium` exports the same set.

Two of them answer the question directly, and neither was used by the bake-off:

- **`FPDFText_IsGenerated(page, i)`** — was character *i* synthesised by PDFium rather
  than read from the content stream? This is how the engine reports the word spaces it
  inferred rather than found.
- **`FPDFText_IsHyphen(page, i)`** — is character *i* a syllable-break hyphen?

<!-- H_WASM -->

`@embedpdf/pdfium` **2.15.0**, called for real on a GPO bill page (1183 characters). Presence is asked of the wrapper object an adapter would call, and each function is then invoked on every character so an exported stub cannot pass.

| entry point | exported | exercised |
|---|---|---|
| `FPDFText_LoadPage` | yes | called |
| `FPDFText_ClosePage` | yes | called |
| `FPDFText_CountChars` | yes | called |
| `FPDFText_GetUnicode` | yes | called |
| `FPDFText_GetText` | yes | called |
| `FPDFText_IsGenerated` | yes | 65 non-trivial returns |
| `FPDFText_IsHyphen` | yes | 4 non-trivial returns |
| `FPDFText_HasUnicodeMapError` | yes | 0 non-trivial returns |
| `FPDFText_GetCharBox` | yes | 1183 non-trivial returns |
| `FPDFText_GetLooseCharBox` | yes | called |
| `FPDFText_GetCharOrigin` | yes | 1183 non-trivial returns |
| `FPDFText_GetMatrix` | yes | 1183 non-trivial returns |
| `FPDFText_GetFontSize` | yes | called |
| `FPDFText_GetFontInfo` | yes | 1121 non-trivial returns |
| `FPDFText_GetFontWeight` | yes | called |
| `FPDFText_GetCharAngle` | yes | called |
| `FPDFText_GetTextIndexFromCharIndex` | yes | called |
| `FPDFText_GetCharIndexFromTextIndex` | yes | called |

**All 18 required entry points present: True.**

<!-- /H_WASM -->

## The index identity, measured rather than assumed

`FPDFText_CountChars` counts one char list per page, and **every** geometry and font call
addresses that same list by the same index. Measured on this corpus:

- `FPDFText_CountChars(page) == len(get_text_range(page))`. The adapter counts every page
  where it does not, so this is a falsifiable counter rather than a spot check.
- `FPDFText_GetTextIndexFromCharIndex` is the identity map.
- `get_text_range()[i]` and `FPDFText_GetUnicode(i)` agree everywhere **except** at GPO's
  soft hyphen, where the text API says U+FFFE and the glyph API says 0x02 — and those are
  exactly the indices `FPDFText_IsHyphen` flags.

<!-- H_ADAPTER -->

Counters from the hybrid adapter itself, aggregated over all 52 corpus documents.

| | total |
|---|---|
| pages | 14,856 |
| characters | 30,400,854 |
| engine-generated characters | 1,266,899 |
| `FPDFText_IsHyphen` characters | 83,775 |
| **pages where CountChars != len(text)** | 0 |
| **ink the engine could not name** | 0 |
| **unicode map errors** | 0 |
| **non-generated characters with an empty font name** | 0 |
| generated-character rate | 4.17% |

<!-- /H_ADAPTER -->

The four bolded rows are the ones that would invalidate the contract if they were non-zero,
and they are reported over the whole corpus rather than the page the mechanism was diagnosed
on. The empty-font-name row is worth noting separately: `docs/source-signal-inventory.md`
warns that a small fraction of glyphs return no font name and that font must therefore
supplement rather than replace the position gates. Through this adapter, on this corpus,
that fraction is zero.

So the answer to "is the character index used for PDFium's reconstructed text stream also
usable to retrieve geometry for that same logical character, including generated ones?" is
**yes, without a mapping step**. Production already depends on this: `_page_glyph_sizes`
reads codepoints from `get_text_range()` and geometry from `FPDFText_GetCharBox(raw, i)`
on the same `i`. What production does not do is read the *spaces*.

---

# 2. What generated characters carry — the honest cost

A generated character has **no** meaningful box, matrix, font size or font name. Its box is
a zero-area point, its matrix is the identity (so `matrix.f`, which the glyph contract uses
as the baseline, reads `0.0`), `GetFontSize × scale` reads exactly `1.0`, and the font name
is empty.

Exactly one geometric fact survives, and it happens to be the one that matters:
**`FPDFText_GetCharOrigin` returns the correct baseline.**

That is why the glyph adapter drops them silently rather than obviously: a generated space
fails the `size > 1.0` floor, and had it survived, its baseline of `0.0` would have put it
on a nonexistent line.

The hybrid contract therefore carries generated characters with `x0`, `x1`, `size` and the
vertical box set to `None` rather than filled, so that any downstream use of a generated
char's geometry fails loudly instead of consuming a placeholder.

<!-- H_SIGNALS -->

| document | generated chars | with a real box | with a size | with a font name | missing origin | glyph_size coverage | LineGeom coverage | margin/body font separation |
|---|---|---|---|---|---|---|---|---|
| `4_reported-in-senate.pdf` | 9111/54942 (16.6%) | **0** | **0** | **0** | **0** | 1.0 (963 lines) | 1.0 | 1.0 over 963 lines |
| `5_engrossed-amendment-house.pdf` | 2691/55942 (4.8%) | **0** | **0** | **0** | **0** | 1.0 (936 lines) | 1.0 | 1.0 over 936 lines |
| `CRPT-118srpt198.pdf` | 3337/129184 (2.6%) | **0** | **0** | **0** | **0** | 1.0 (2 lines) | 1.0 | 0.0 over 2 lines |

<!-- /H_SIGNALS -->

**Reading this table.** The three bolded columns are the claim "generated characters carry
their origin and nothing else", stated as a falsifiable count rather than a description: a
single generated char with a real box would mean the contract is discarding information.

## The sidecar values, not just their existence

Coverage of `1.0` above means a value *could be computed*, which is compatible with
computing the wrong one everywhere. The heading detector consumes these numbers directly —
`glyph_size` drives ADR 0012's size bands, `first_word_right` drives the major detector's
stacked-vs-wrapped split — so the stronger question is whether they agree with production's.

<!-- H_GEOM_AGREE -->

Agreement is over the numbered lines both paths recovered, to a 0.05 pt tolerance (these are floats derived through different call paths, so exact equality would report noise as disagreement).

| document | shared numbered lines | `glyph_size` | `content_left` | `content_right` | `first_word_right` |
|---|---|---|---|---|---|
| `4_reported-in-senate.pdf` | 718 | 1.0 | 0.99861 | 0.99304 | **0.97075** |
| `5_engrossed-amendment-house.pdf` | 705 | 1.0 | 0.99858 | 0.97305 | **0.92624** |
| `CRPT-118srpt198.pdf` | 2 | 1.0 | 1.0 | 1.0 | **1.0** |

<!-- /H_GEOM_AGREE -->

**`first_word_right` disagrees on about 7 % of lines, and production is the side that is
wrong.** Diagnosed at `118-hr-4366/5` page 26 line 2, `‘‘Military Construction, Navy and
Marine`:

```
char   box_bottom   box_top   origin_y
 ‘       686.895    690.591    681.001
 M       681.001    690.269    681.001
 r       681.001    687.021    681.001
 y       678.089    687.049    681.001      <- descender
 SP      681.001    681.015    681.001
```

Every character shares an origin of `681.001` **exactly**. The box bottoms span `678.089`
to `686.895` — a spread of **8.81 pt** against the `0.5 × 14.0 = 7.0` tolerance
`_cluster_baselines` uses. So production's geometry sidecar puts the `y` on a different line
from the word it belongs to, and `first_word_right` for `‘‘Military` comes back as the right
edge of `r` (253.70) instead of `y` (260.19).

This is not a new finding so much as a measured one: `probes/reconstruct.py`'s docstring
already predicted it ("on a 14pt body line the descender drop is ~8.4pt against a 7pt
tolerance"). What is new is that it is **live in production**, in the signal that decides
whether two heading lines are stacked or wrapped.

**Credit where it is due: this is not a hybrid advantage over the glyph contract.** Both
carry the text-matrix origin as their baseline, so both avoid it; production is alone in
clustering on the box bottom. It is an argument for moving the seam, not for choosing
between the two candidate seams.
`glyph_size` and `LineGeom` coverage are `1.0` on every numbered line, so nothing the
engine consumes — ADR 0012's heading sizes, the major detector's line-fullness split — is
lost. Font-role separation is `1.0` on the bills. The committee report's `0.0` is a
population artifact and not a defect: it is not a line-numbered bill, so only two lines
qualify at all.

---

# 3. The failure cases

The four headings `RESULTS-CONFIRMATORY.md` names, counted on the printed lines they are
set on rather than on the anchor labels, so the heading detector cannot mask or manufacture
a difference.

<!-- H_HEADINGS -->

| document | heading | production | glyph | **hybrid** | pdfminer |
|---|---|---|---|---|---|
| `114-hr-2029/4_reported-in-senate` | FAMILY HOUSING | 14 ok | **7 ok / 7 malformed** | 14 ok | 14 ok |
| `114-hr-2029/4_reported-in-senate` | NAVY AND | 6 ok | **4 ok / 2 malformed** | 6 ok | 6 ok |
| `114-hr-2029/4_reported-in-senate` | ARMY NATIONAL | 2 ok | **1 ok / 1 malformed** | 2 ok | 2 ok |
| `114-hr-2029/4_reported-in-senate` | AMERICAN BATTLE | 2 ok | **1 ok / 1 malformed** | 2 ok | 2 ok |
| `118-hr-4366/5_engrossed-amendment-house` | FAMILY HOUSING | 8 ok | **0 ok / 8 malformed** | 8 ok | 8 ok |
| `118-hr-4366/5_engrossed-amendment-house` | NAVY AND | 2 ok | **0 ok / 2 malformed** | 2 ok | 2 ok |
| `118-hr-4366/5_engrossed-amendment-house` | ARMY NATIONAL | 1 ok | **0 ok / 1 malformed** | 1 ok | 1 ok |
| `118-hr-4366/5_engrossed-amendment-house` | AMERICAN BATTLE | 1 ok | **0 ok / 1 malformed** | 1 ok | 1 ok |
| `116-hr-1865/6_enrolled-bill` | FAMILY HOUSING | 9 ok | 9 ok | 9 ok | 9 ok |
| `116-hr-1865/6_enrolled-bill` | NAVY AND | 5 ok | 5 ok | 5 ok | 5 ok |
| `116-hr-1865/6_enrolled-bill` | ARMY NATIONAL | 2 ok | 2 ok | 2 ok | 2 ok |
| `116-hr-1865/6_enrolled-bill` | AMERICAN BATTLE | 1 ok | 1 ok | 1 ok | 1 ok |
| **all** | **all four** | 53 ok / 0 malformed | 30 ok / 23 malformed | 53 ok / 0 malformed | 53 ok / 0 malformed |

<!-- /H_HEADINGS -->

`116-hr-1865/6` is in the table deliberately as a **negative control**: it is a document
where the glyph path does not fail, so the table shows the defect is print-class dependent
rather than universal, and that the hybrid is not simply scoring on an easier population.

## Mechanism, at the character level

The clearest instance is not one of the four but a fifth label from the same document,
chosen because its gap is the narrowest and so the arithmetic is unambiguous. At
`114-hr-2029/4` page 99, `NATIONAL CEMETERY ADMINISTRATION`:

```
 idx ch  cp  gen        x0        x1   origin_y   mat.f    size  font
 607  Y   89 False   322.61    329.79     421.00  421.00   11.20  DeVinne-Italic
 608  SP  32 True    322.86    322.86     421.00    0.00    1.00
 609  A   65 False   332.19    341.98     421.00  421.00   14.00  DeVinne-Italic
```

The gap from `Y` to `A` is **2.40 pt** against a threshold of `0.25 × 14.00 = 3.50`, so the
neutral layer inserts nothing and the label becomes `CEMETERYADMINISTRATION`. The word
space is **not missing from the document** — it is character 608, flagged generated.

Note what the three rows show together: the engine placed a space at a gap *narrower* than
the threshold, and §4 shows no threshold would have worked. So the engine is not applying a
better-tuned version of the same rule; it is deciding with information the glyph stream does
not carry. That is the argument for moving the decision, and it does not depend on any
claim about PDFium's internals — only on the measurement that geometry alone is insufficient
and that the engine nonetheless gets it right.

---

# 4. No `_SPACE_FACTOR` can work — the rule is not the constant

Before tuning, the prior question is whether a single global gap/size threshold can
separate word boundaries from intra-word kerning **at all**.

PDFium's own stream supplies the label for each adjacent ink pair (did the engine put a
space there?) and the geometry supplies the feature (gap ÷ size). This is not circular: the
question is not whether PDFium is right, it is whether the geometry the neutral layer sees
is *sufficient* to recover the same decision with one constant.

The labels are also corroborated rather than taken on trust. Where the two disagree, the
engine's answer is the one that matches **two independent references** — GPO's own printing
(§3, `FAMILY HOUSING` is set with a space) and the XML tree (§6, on the stratum that can
discriminate).

<!-- H_SEPARABILITY -->

| document | word boundaries | intra-word | boundary gap/size min | intra-word max | separable | best threshold, errors | shipped 0.25, errors |
|---|---|---|---|---|---|---|---|
| `6_enrolled-bill.pdf` | 11610 | 61759 | 0.056 | 0.215 | **NO** | 0.181, 9 | 94 missed + 0 spurious |
| `1_introduced-in-house.pdf` | 140 | 661 | 0.0627 | 0.284 | **NO** | 0.235, 4 | 5 missed + 1 spurious |
| `BILLS-118s4795rs.pdf` | 5751 | 26886 | 0.0627 | 0.225 | **NO** | 0.217, 23 | 49 missed + 0 spurious |
| `CRPT-118srpt198.pdf` | 10663 | 68608 | 0.177 | 0.245 | **NO** | 0.177, 2 | 38 missed + 0 spurious |
| `5_engrossed-amendment-house.pdf` | 5763 | 27345 | 0.038 | 0.22 | **NO** | 0.169, 148 | 306 missed + 0 spurious |
| **POOLED** | 33927 | 185259 | 0.038 | 0.284 | **NO** | 0.177, 214 | 492 missed + 1 spurious |

<!-- /H_SEPARABILITY -->

**The distributions overlap in every print class measured.** The `separable` column is `NO`
throughout, so the shipped `0.25` is not a badly chosen value on a workable rule — it is a
reasonable value on a rule that has no correct setting. Tuning moves errors between the two
directions; it cannot reach zero.

That matters more than the error count, because the two directions are not equally
survivable. A spurious space splits a word; a missed space welds two words together, and
when those words are an account name, the amounts beneath it are misfiled — the heading
tree is the financial data contract ([`0012`](../../decisions/0012-pdf-heading-levels.md),
[`0014`](../../decisions/0014-leveled-heading-tree-scope.md)).

**This is the answer to "should we tune `_SPACE_FACTOR` first".** No: the constant is not
where the defect lives.

---

# 5. Corpus parity with production

Reference is production's own output, because the question is migration risk. Reproducing
production exactly is evidence about **risk**, never about correctness — section 6 supplies
the accuracy half so that agreement cannot stand in for it.

<!-- H_CORPUS -->

Reference is **production** (`extract_clean_pages`) on the 42 corpus documents production accepts. Heading metrics (H2/H3/H5) are over the 33 of those that carry any heading; the rest cannot discriminate.

| metric | glyph | **hybrid** | pdfminer |
|---|---|---|---|
| H1 full text digest identical | 0/42 | 0/42 | 0/42 |
| H1 mean token F1 vs production | 0.99501 | 0.99609 | 0.9952 |
| H2 heading-label set exact | 26/33 | 31/33 | 29/33 |
| H2 labels production does NOT produce | 302 | 2 | 5 |
| H2 production labels missed | 280 | 2 | 2 |
| H3 breadcrumb (parent) agreement | 0.98324 | 1.0 | 1.0 |
| H4 line-number set identical | 41/42 | 42/42 | 41/42 |
| H4 mean line-number Jaccard | 0.99997 | 1.0 | 0.99997 |
| H5 amount→heading agreement | 0.99081 | 1.0 | 1.0 |

<!-- /H_CORPUS -->

## The canonical diff

This is the product's actual output, and it separates two things the earlier tables do not.

<!-- H_PAIRS -->

Reference is **production**'s canonical diff over 15 consecutive version pairs. `amounts` is the `Counter[(old, new, kind)]` of `amount_entries` — the money, and the highest-consequence field. `changes` is the `Counter[(change_type, norm(old), norm(new))]` signature set, which embeds the line text and therefore cannot be byte-identical for any path that assembles lines geometrically; its **overlap** is the informative figure and the identity column is reported only so the distinction is visible.

| path | amount signatures identical | amount recall | change signatures identical | change recall |
|---|---|---|---|---|
| glyph | 15/15 | 1.0 (10229/10229) | 0/15 | 0.87642 (6929/7906) |
| **hybrid** | 15/15 | 1.0 (10229/10229) | 0/15 | 0.99671 (7880/7906) |
| pdfminer | 15/15 | 1.0 (10229/10229) | 0/15 | 0.91437 (7229/7906) |

<!-- /H_PAIRS -->

**All three paths reproduce production's `amount_entries` exactly** — the same 10,229
amount signatures, on 15 of 15 pairs. No path loses or invents money, so the glyph seam's
heading defect is **not** an amount-extraction defect.

**It is an attachment defect, and the two tables have to be read together.**
`amount_entries` carries `(old, new, kind)`; it does not carry which account the amount sits
under. That is H5, where the glyph path scores 0.99081 against the hybrid's 1.0. The failure
mode is therefore precise: the right money, filed under a corrupted account name. That is
worse than a missing amount rather than better, because it is invisible to every check that
counts or sums — including, as `RESULTS-CONFIRMATORY.md` recorded, the ADR 0014 conservation
check, which compared totals and passed.

On change signatures the separation is large: the hybrid recovers 99.7 % of production's
changes against the glyph path's 87.6 %. The identity column is 0/15 for every path,
including pdfminer, because these signatures embed the line text and no geometrically
assembled line matches `normalize_raw`'s output byte for byte. Recall is the figure that
carries information here, which is why both are shown.

## The hybrid's entire heading-label error, named

Across the 33 heading-bearing documents the hybrid produces **two** labels production does
not and misses **two**, and they are the same label twice: `COUPS D'ÉTAT`, on `118-hr-2882/5`
and `118-s-4797/1`. `pdfminer` produces exactly the same substitution.

GPO sets the É as two characters — an `E` and a separate `´` (U+00B4) overprinted on it.
Measured at `118-hr-2882/5` page 711 character 578, the accent's origin sits at
**448.284** while the rest of the line sits at **447.000**, a 1.284 pt offset against the
`_BASELINE_TOL = 0.6` used to decide which line a character belongs to. So geometric line
clustering assigns the accent to a line of its own, and the label loses it.

Two things follow, and neither is hidden:

- **This is a limitation of geometric line assignment, not of the hybrid contract.** It is
  the one place where PDFium's reading order is better than baseline clustering, and the
  neutral glyph layer inherits the same tolerance and the same behaviour.
- **Production is not right here either.** It yields `COUPS D'E´TAT` — the accent retained
  as a stray character after the E rather than composed onto it. Neither path produces
  `COUPS D'ÉTAT`, so this is a pre-existing diacritic gap in which the two paths are wrong
  differently. It is reported as a difference, not as a regression, and it is not fixed
  here because tuning is out of scope for this spike.

## What H1 does not say

No path reproduces production's `pdf_full_text` digest byte for byte, and that is expected
rather than a hybrid defect: the reconstruction layers assemble lines geometrically while
`normalize_raw` assembles them from a page-wide text blob. Characterised on
`114-hr-2029/4` (2738 production lines):

| path | line-diff operations vs production | word spaces lost |
|---|---|---|
| hybrid | 2 | **0** |
| glyph | 104 | **113** |

Both hybrid differences are on the **cover page**, where geometric clustering separates
`1ST SESSION` from `H. R. 2029` because they are printed on different lines and PDFium's
reading order glues them together. That is a difference in favour of the hybrid.

The glyph path's 113 lost spaces are **not confined to headings**. They appear in ordinary
body prose — `the Department ofVeterans Affairs`, `Committees on Appropriations ofboth
Houses`, `section 2906(a) ofthe Defense Base Closure Act` — which the aggregate token-F1
metrics in `RESULTS-CONFIRMATORY.md` were too tolerant to surface.

---

# 6. Accuracy, so that parity is not mistaken for correctness

Section 5 shows the hybrid reproduces production. On its own that is compatible with the
hybrid faithfully reproducing production's *mistakes*, so the same paths are scored against
XML here.

**The primary stratum cannot answer this question, and the table says so rather than
letting a flat row read as equivalence.** `RESULTS-CONFIRMATORY.md` recorded that every
corpus document where the paths' heading recovery differs carries a `<quoted-block>`, which
the DeltaTrack#11 parser defect drops from the XML reference. Measured again here and it
still holds exactly: all 7 documents where the glyph path differs from production carry
one, and the 26 documents without one produce **zero** differences on any path. Excluding
quoted blocks removes precisely the documents that can discriminate.

<!-- H_ACCURACY -->

Reference is **XML**. `production` is a fourth column rather than the reference, because against XML it is a candidate like any other.

**primary — no `<quoted-block>`** — 26 documents. _Can this stratum discriminate?_ **NO** — no path differs from production anywhere in these 26

| metric | production | glyph | **hybrid** | pdfminer |
|---|---|---|---|---|
| B2 heading-label F1 | 0.52823 | 0.52823 | 0.52823 | 0.52823 |
| B5 amount→heading F1 | 0.75132 | 0.75132 | 0.75132 | 0.75132 |
| B6 parent/child accuracy | 0.46676 | 0.46676 | 0.46676 | 0.46676 |

**quoted-block stratum** — 16 documents. _Can this stratum discriminate?_ **YES** — 10 of 16 documents separate the paths

| metric | production | glyph | **hybrid** | pdfminer |
|---|---|---|---|---|
| B2 heading-label F1 | 0.67106 | 0.63198 | 0.67106 | 0.67086 |
| B5 amount→heading F1 | 0.75327 | 0.7387 | 0.75327 | 0.75327 |
| B6 parent/child accuracy | 0.59615 | 0.56897 | 0.59615 | 0.59615 |

<!-- /H_ACCURACY -->

**On the stratum that can discriminate, the hybrid matches production's accuracy exactly**
— to five decimal places on all three metrics — while the glyph path is measurably lower on
all three. So the parity in §5 is agreement on the better answer, not agreement on a shared
error.

Two limits on how far this table can be pushed. The **absolute** values in the
quoted-block stratum are depressed for every path by the same reference gap (the XML side
is missing the quoted-block content entirely), so they are not a measure of how accurate
any path is; only the **comparison within a column-set** is meaningful, and that comparison
is valid because all four paths face an identical reference. And B6's parent/child accuracy
is the weakest of the three: it is computed only over labels both sides found, so it moves
for reasons the heading-label metric already counted.

---

# 7. Portability, and one real build difference

<!-- H_PORTABILITY -->

| document | raw stream identical | trailing-space divergences | line-break-vs-space | **unclassified** | **page text digest identical** | line numbers identical | heading labels identical |
|---|---|---|---|---|---|---|---|
| `4_reported-in-senate.pdf` | False | 705 | 0 | **0** | **True** | True (963) | True (49) |
| `5_engrossed-amendment-house.pdf` | False | 779 | 0 | **0** | **True** | True (936) | True (45) |
| `BILLS-118s4795rs.pdf` | False | 682 | 0 | **0** | **True** | True (952) | True (52) |
| `CRPT-118srpt198.pdf` | False | 1436 | 1 | **0** | **True** | True (2) | True (0) |

<!-- /H_PORTABILITY -->

**Native PDFium and PDFium-WASM do not emit the same character stream.** That is worth
recording rather than smoothing over, and "harmless" has to be a claim about *what*
differs, so every divergence is sorted into a named kind and anything that does not fit is
counted as `unclassified` and sampled. A non-zero `unclassified` column is the signal that
this section's conclusion no longer covers its evidence.

Two kinds appear:

- **line-trailing space** — the WASM build omits the space native keeps at the end of most
  printed lines, the same trailing spaces `normalize_raw` exists to strip. This is the bulk
  of the divergence.
- **line-break vs space** — on the committee report only, the WASM build joins two printed
  lines that native separates. This one is more interesting than its count suggests: it is
  a genuine *reading-order* disagreement between two builds of the same engine, and it
  cannot reach the output because the hybrid layer assigns lines by **baseline** and
  discards the engine's break characters outright. Had the design taken line structure from
  the engine's `\r\n` as well as spacing from its generated characters, this would have been
  a real portability defect.

After the hybrid layer the two builds produce identical page text, identical line-number
sets and identical heading-label sets. Stream identity would not have proved this, and
stream difference does not disprove it, which is why both are measured.

## Answering the portability questions as asked

| question | answer |
|---|---|
| Can `@embedpdf/pdfium` expose everything needed today? | **Yes.** All required entry points are already exported and were called for real, not read from a symbol table or a typing. |
| Is anything missing an FFI/export issue or a fundamental limit? | **Neither — nothing is missing.** |
| How much custom WASM wrapper work? | **None.** `js/dump_pdfium_hybrid_wasm.mjs` is a peer of the existing glyph dumper and uses no new build. |
| Does this deepen the PDFium dependency? | **Less than expected.** See the measurement below, which contradicted the assumption. |

## The dependency question — measured, after the first answer proved wrong

The first draft of this section reasoned from the shape of each library's API and
concluded the hybrid contract would narrow the candidate set, because only PDFium exposes
an explicit generated-character flag. **That was wrong on the first backend checked**, so
the question was measured instead.

<!-- H_BACKEND_SPACING -->

Probe boundary: `CEMETERY ADMINISTRATION` on `tests/corpus/114-hr-2029/4_reported-in-senate.pdf` page 99. The neutral glyph layer produces `CEMETERYADMINISTRATION` here.

| backend | its own text keeps the space | produces the joined form | how a synthesised character is marked |
|---|---|---|---|
| pdfium | **True** | **False** | FPDFText_IsGenerated flag; zero-area box, origin only |
| pdfminer.six | **True** | **False** | LTAnno object (distinct class, carries no bbox at all) |
| pymupdf | **True** | **False** | NONE - synthesised spaces get a real box and are indistinguishable |
| pdf.js | **True** | **False** | NONE - text-item granularity, no per-character box at all |
| **the glyph seam** | **False** | **True** | n/a — the information is discarded before this point |

<!-- /H_BACKEND_SPACING -->

**Every candidate's own text output keeps the space. None of them produces the joined
form. Only the seam does.** The word break is not a hard problem that PDFium happens to
solve; it is a problem every one of these libraries already solved, and that the glyph
contract discards on the way in.

That reframes the portability tradeoff rather than removing it. The contract has two
halves, and backends satisfy them differently:

| | ordered text with engine-decided spaces | per-character geometry | synthesised chars distinguishable |
|---|---|---|---|
| **PDFium** (native + WASM) | yes | yes | yes — `FPDFText_IsGenerated` |
| **pdfminer.six** | yes | yes | yes — `LTAnno` is a distinct class carrying no bbox |
| **PyMuPDF** / mupdf.js | yes | yes | **no** — synthesised spaces get a real box |
| **PDF.js** | yes | **no** — ~13 chars per item | **no** |

- **PDFium and pdfminer.six satisfy the contract outright.** pdfminer needs no flag
  reconstruction: `LTAnno` *is* the generated-character marker, and it carries no bbox at
  all, which is a stricter version of the same guarantee the hybrid contract enforces with
  `None` fields.
- **PyMuPDF** would need the adapter to treat all spaces alike. That is safe here (its
  synthesised boxes are real, not placeholders) but it forfeits the "fail loudly" property.
- **PDF.js** is the one genuine narrowing, and it was already the weakest fit for the glyph
  contract for the same reason: no per-character box. Its *spacing* is fine — 0 of 23
  font-boundary adjacencies on the probe page lost a space, and 0 over 1657 such
  adjacencies across 60 pages of `114-hr-2029/4`. Its limitation is geometry granularity,
  not text assembly.
  [`README.md`](README.md) records a `Providedfurther,That` artifact from naive item
  joining; that did not reproduce here under pdfjs-dist 6.2.108. The note does not name the
  document it was measured on, so this is one document failing to reproduce it rather than
  a refutation, and the check was first shown able to fire (1657 adjacencies examined)
  before its zero was believed.

So the honest statement is narrower and firmer than the draft's: the hybrid contract costs
nothing against pdfminer, costs a safety property against PyMuPDF, and does not change
PDF.js's standing either way.

---

# 8. What becomes unnecessary if the hybrid model is adopted

Asked of both existing layers, since they carry different repair code.

**Retired from `probes/reconstruct.py` (the neutral glyph layer):**

| logic | why it goes |
|---|---|
| `_SPACE_FACTOR` and the x-gap word-space rule in `_line_text` | the engine supplies the spaces |
| the x-gap fallback inside `_first_word_right` | it exists only to cover boundaries the engine already marks |
| `_repair_line_end` / the `repaired` vs `strict` mode split | the "unnamed ink, line-final" position heuristic is replaced by `FPDFText_IsHyphen` |
| the `repaired`-mode machinery the U+FFFD unnamed-ink carrier fed | the carrier itself stays as a safety net, but it never fires: `unnamed_ink` is **0** over all 14,856 corpus pages (§1) |

**Additionally retired from `parsers/pdf_text.py` (production's text path):** the
`_HYPHEN_BREAK` rewrite of `U+FFFE` plus a glued margin number, the `_GLUED_CHROME`
rewrite, and the trailing-space strip. Production's own `_cluster_baselines` and its
`_line_text` gap rule also go, replaced by the exact text-matrix/origin baseline — and
§5's `first_word_right` result shows that is a fix, not a wash.

**An earlier draft said "the whole of `normalize_raw`", and the probe below falsified it.**
That claim was read off the code, and the stratum that could disprove it is the one §5
excludes: production declines unnumbered layouts, and the enrolled bills it declines are
precisely where the mid-line soft-hyphen branch fires.

<!-- H_NORMALIZE_RAW -->

Measured on the **production-declined** stratum — the unnumbered layouts, mostly enrolled bills, which section 5's parity table excludes and which are exactly where `normalize_raw`'s mid-line soft-hyphen branch exists to act (its docstring names them). A branch counts as having fired by matching its own pattern against PDFium's raw page text, so the zeros to its right are only meaningful because the number to its left is large.

| document | mid-line branch fired | trailing-hyphen tokens (prod / hybrid) | soft-hyphen chars in text (prod / hybrid) | hyphenated tokens only in hybrid |
|---|---|---|---|---|
| `113-hr-3547/6` | 3,466 | 28 / 59 | 0 / 0 | **36** |
| `113-hr-83/7` | 3,731 | 37 / 80 | 0 / 0 | **37** |
| `114-hr-2029/7` | 4,716 | 39 / 226 | 0 / 0 | **138** |
| `115-hr-1625/6` | 4,754 | 31 / 144 | 0 / 0 | **90** |
| `115-hr-244/6` | 3,897 | 33 / 91 | 0 / 0 | **54** |
| `115-hr-5895/5` | 431 | 3 / 11 | 0 / 0 | **9** |
| `116-hr-1865/6` | 3,871 | 45 / 169 | 0 / 0 | **88** |
| `117-hr-2471/6` | 5,960 | 40 / 201 | 0 / 0 | **122** |
| `118-hr-4366/6` | 2,338 | 30 / 69 | 0 / 0 | **36** |
| `118-hr-9468/4` | 13 | 0 / 0 | 0 / 0 | **0** |
| **total** | **33,177** | 286 / 1050 | 0 / 0 | **610** |

Hyphenated tokens the hybrid produces and production does not:

- `APPRO-`
- `APPROPRIA-`
- `AUTHOR-`
- `Bankhead-`
- `Bay-`
- `Counter-`
- `Defense-`
- `ENVI-`
- `ACTIVI-`
- `APPRO-`
- `APPROPRIA-`
- `Al-`
- `Bankhead-`
- `Bay-`
- `CRIT-`
- `Counter-`
- `AGREE-`
- `AGRI-`
- `ALTER-`
- `AMER-`

<!-- /H_NORMALIZE_RAW -->

**What it found, and it is a real limitation.** No soft-hyphen character survives into
either rendering, so that half of the claim holds. But the hybrid leaves **1050** tokens
ending in a dangling hyphen against production's **286**, and the samples name the pattern
exactly:

```
only in hybrid:      'APPRO-'            'AUTHOR-'          'ACTIVI-'
only in production:  'APPRO-PRIATIONS'   'AUTHOR-IZED.—'    'ACTIVI-TIES'
```

These are **uppercase** syllable breaks. PDFium's text API does not emit a line break at
them, so production receives `APPRO￾PRIATIONS` inline and `normalize_raw`'s
`text.replace("￾", "-")` yields one token. The hybrid assigns lines geometrically — correctly,
since GPO did print them on two lines — and then `_merge_print_lines` declines to rejoin,
because its guard requires a **lowercase** continuation. That guard exists to protect real
compounds like `Child-Rescue`, and it is production's rule, reused unchanged.

So `normalize_raw` is **not** retired in full: one of its branches is doing work that the
hybrid's geometric line assignment plus production's lowercase-guarded rejoin does not
reproduce.

**It is fixable with information only this contract has, and that fix is not written.**
`FPDFText_IsHyphen` distinguishes a syllable break from a compound hyphen directly, so a
rejoin keyed on the flag rather than on the continuation's case would be both more correct
than the lowercase guard and available to no other layer. Per this document's own standard,
a fix that is described and not written is not evidence, so this stands as a limitation.

**Scope, which matters here, and is measured rather than asserted.**

<!-- H_NORMALIZE_RAW_SCOPE -->

The same probe over a **mixed** stratum, to locate the limitation rather than just measure it. `declined` is production's own unnumbered-layout guard.

| document | production declines it | mid-line branch fired | trailing-hyphen tokens (prod / hybrid) | hyphenated tokens only in hybrid |
|---|---|---|---|---|
| `113-hr-3547/1` | no | 0 | 0 / 0 — **identical** | 0 |
| `113-hr-3547/2` | no | 0 | 0 / 0 — **identical** | 0 |
| `113-hr-3547/3` | no | 0 | 0 / 0 — **identical** | 0 |
| `113-hr-3547/4` | no | 2 | 0 / 0 — **identical** | 0 |
| `113-hr-3547/6` | **yes** | 3,466 | 28 / 59 | 36 |
| `113-hr-83/7` | **yes** | 3,731 | 37 / 80 | 37 |
| `114-hr-2029/1` | no | 7 | 7 / 7 — **identical** | 0 |
| `114-hr-2029/3` | no | 13 | 13 / 13 — **identical** | 0 |
| `114-hr-2029/4` | no | 1 | 36 / 36 — **identical** | 0 |
| `114-hr-2029/7` | **yes** | 4,716 | 39 / 226 | 138 |
| `115-hr-1625/6` | **yes** | 4,754 | 31 / 144 | 90 |
| `115-hr-244/6` | **yes** | 3,897 | 33 / 91 | 54 |
| `115-hr-5895/1` | no | 1 | 19 / 18 | 0 |
| `115-hr-5895/2` | no | 1 | 54 / 53 | 0 |

<!-- /H_NORMALIZE_RAW_SCOPE -->

The dichotomy is sharp. On numbered layouts the mid-line branch fires a handful of times
and the hybrid produces **no** hyphenated token production does not — its trailing-hyphen
count is equal to production's or, on two documents, one lower. On unnumbered layouts the
branch fires in the thousands and the counts diverge by 3–6×.

The limitation therefore lives entirely inside the stratum production already refuses. That
is why §5's parity table does not see it — and equally why that table could not have ruled
it out, which is the reason this probe exists.

**A correction worth recording, because it is the kind that publishes cleanly.** The first
version of this probe paired tokens against the other rendering's whole-document bag,
asking "does some split of this token into two tokens present somewhere in the document
exist?". At ~100k tokens that is trivially satisfiable, and it duly reported that the hybrid
had fused `pro` + `vided`. Production's `pro` was from `a pro rata share`, on a different
page, and had nothing to do with the word `provided`. A test satisfiable by coincidence
cannot distinguish a defect from its absence, so it was replaced with a set difference over
the tokens that actually carry a hyphen — the population the branches act on, where a
coincidental match is not available.

**Explicitly NOT retired, and this is the point of the split:** `strip_page_chrome`'s
patterns, the chrome size ratio, the margin-number regex, `_merge_print_lines`,
`rejoin_soft_hyphens`, `extract_anchors`, the size bands and the leveled tree. That is GPO
and legislative interpretation, and it stays DeltaTrack's.

---

# 9. Conclusion

> **Hybrid text+geometry is viable and should replace raw glyph reconstruction as the PDF
> adapter contract.**

The evidence, in the order it should be checked:

1. The APIs exist and execute in both the native and the browser-shippable build, with no
   wrapper work and no index mapping (§1).
2. The failure cases are fixed, on the documents where they occur, with a negative control
   showing the population was not chosen favourably (§3).
3. The rule they were blamed on cannot be fixed by tuning: no single gap threshold
   separates word boundaries from kerning in any print class measured (§4). This is why
   the recommendation is not "raise `_SPACE_FACTOR`".
4. The cost is characterised rather than hidden: generated characters carry an origin and
   nothing else, measured exactly, and every signal DeltaTrack consumes still has full
   coverage (§2).
5. It survives the WASM build, including a real stream-level difference between the two
   PDFium builds that the layer absorbs (§7).
6. Moving the seam at all **fixes a live production defect** neither contract was built to
   fix (§2): production's geometry sidecar clusters on the character box bottom, so a
   descender falls outside the tolerance and `first_word_right` comes back one glyph short
   on ~7 % of lines — in the signal that decides whether two heading lines are stacked or
   wrapped. This one is not a hybrid advantage over the glyph contract; **both** carry the
   text-matrix origin, and it is production that is alone in clustering on the box bottom.

**The two limitations, both found by probes built to find them:**

- **A diacritic set above its line** is assigned to a line of its own, costing one heading
  label on two documents (§5). Shared with the glyph layer, and a property of the 0.6 pt
  clustering tolerance rather than of the contract.
- **Uppercase syllable breaks are left dangling** on unnumbered layouts (§8): 1050 tokens
  against production's 286. Confined to the stratum production already declines, and
  fixable with `FPDFText_IsHyphen`, which no other layer has — but that fix is not written,
  so it stands.

Neither is an argument for keeping raw glyph reconstruction, because the glyph layer has
the first defect too and is worse on everything else. They are arguments for what the
follow-up has to cover.

## Was the hybrid layer fitted to the failure cases?

It was written after reading them, so the question is fair and is worth answering directly
rather than leaving to the reader.

- **No constant was tuned.** `reconstruct_hybrid.py` carries `_BASELINE_TOL`, `_SIZE_FLOOR`,
  `_CHROME_SIZE_RATIO`, the chrome patterns and the margin-number regex at exactly the
  values `reconstruct.py` uses. The only change is where word spaces come from, and it
  removes a parameter rather than adding one.
- **The discriminating documents were not chosen.** §3 includes a document where the glyph
  path does not fail, and §5 scores all 52 corpus documents. The hybrid's entire
  corpus-wide heading error is two labels, and **neither is on a document inspected while
  building the layer** — both are the `COUPS D'ÉTAT` diacritic, on `118-hr-2882/5` and
  `118-s-4797/1`, which the corpus run surfaced rather than the development loop.
- **One bug was found by a diagnostic rather than by the score, and it is recorded** in
  `probes/README.md`: the first version sorted each line by baseline and rendered `MILITARY`
  as `M6 ILITARY`, because a heading's full-size initial reports an origin 0.003 pt above
  its small caps. It was caught by an out-of-order counter, not by a metric, which is a
  reason to keep such counters rather than a reason to trust the metrics more.
- **What was NOT re-examined:** `_BASELINE_TOL = 0.6` is inherited unchanged and is exactly
  what the `COUPS D'ÉTAT` case above trips over. This spike deliberately did not tune it. It
  is the obvious first candidate for the follow-up, and it should be decided on its own
  evidence, not folded into the contract decision.

## What this does not establish

- **It does not make the glyph seam wrong about what it was defending against.** Grading
  challengers on how well they imitate PDFium's text conventions is still the trap the
  bake-off correctly avoided. The hybrid contract avoids it differently: it asks each
  backend for *its own* text decisions, which is a neutral question, rather than for
  PDFium's.
- **It narrows backend portability, but by less than the shape of the APIs suggests** (§7).
  The measured cost is one safety property against PyMuPDF and nothing against pdfminer.
  The draft of this document claimed a larger cost from API shape alone and was wrong.
- **It is measured on published GPO material only.** The two-tier rule in
  [`README.md`](README.md) still binds: nothing here licenses a "PDF is solved" sentence,
  and image-only draft PDFs remain out of scope and untested.
- **It is a spike result, not a shipped refactor.** Nobody has written the production
  change, and `RESULTS-CONFIRMATORY.md`'s standing caveat applies to this document too: a
  fix that is described but not written is not evidence available to a decision.

## Recommended follow-up, as separate decisions

1. **Adopt the hybrid contract as the PDF adapter seam**, replacing `contract.PdfPage`.
   This is the decision this document supports and the only one it supports.
2. **Re-run Concern A's migration gate against the hybrid path** before any production
   change. Concern A's reference was the harness incumbent through the glyph layer, so it
   says nothing about this path.
3. **Rejoin syllable breaks on `FPDFText_IsHyphen` rather than on the continuation's case**
   (§8). This is the fix for the one limitation the contract introduces, and it is
   strictly better than the lowercase guard it replaces, because the flag distinguishes a
   syllable break from `Child-Rescue` directly instead of inferring it.
4. **Re-examine `_BASELINE_TOL` on its own evidence**, not as part of this decision. It is
   inherited unchanged here and it is what the `COUPS D'ÉTAT` case trips over.
5. **Fix production's descender clustering, or let the seam change fix it** (§2). Either
   way the ~7 % `first_word_right` error is a live defect in heading detection today and
   should be tracked whether or not the contract changes.
6. **Record the backend-portability narrowing** in an ADR amendment to
   [`0002`](../../decisions/0002-pdfium-single-engine.md), with the measured version from
   §7 rather than the API-shape version this document first drafted.
