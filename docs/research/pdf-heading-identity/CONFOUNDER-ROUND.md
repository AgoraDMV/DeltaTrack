# Even-small-caps containers — the class IS separable, the candidate is not yet valid

Authorized round, one failure: a genuine **container** printed in even small caps is
indistinguishable from an account under caps-per-word, so clause `D6` joins them and
fabricates hierarchy — while the `D2` guard that catches them is document-local and
causes cross-version instability.

**Research question — answered YES.** Source-neutral print evidence does separate the
class, it needs **no new raw observation**, and it is already in the surface: **line
fullness**. The frozen rule never consults it there because `D6` short-circuits ahead of
it.

## The bounded population, stated before any feature was tested

The decisive population is the `D6` population — boundaries where **both** lines score
caps-per-word < T, so caps-per-word cannot separate them. Partitioned by the independent
XML oracle over the combined development evidence (original corpus + the spent 21-bill
holdout):

| | n |
|---|---|
| `D6` population (both lines even small caps) | **786** |
| **CONFOUNDER** — truth SPLIT, container over account | **18** |
| **AT-RISK WRAP** — truth JOIN, one wrapped account | **768** |

Confounders split evenly across the two corpora (9 dev / 9 holdout) and reduce to
**one distinct heading pair** in six documents of six different bills
(`113-s-1371`, `115-s-3107`, `117-hr-4502`, `117-hr-8254`, `118-hr-2882`, `118-s-4928`):

```
OFFICE OF INSPECTOR GENERAL     caps-per-word 0.000
SALARIES AND EXPENSES           caps-per-word 0.000
```

Two facts bound what any discriminator may be:

- `office of inspector general` occurs **33 times as a complete logical heading** and 18
  times as a container. The string is not the answer; it is the same string in both roles.
- `salaries and expenses` occurs **913 times** as a complete heading.

So the discriminator must be positional, and no vocabulary of names — learned or fixed —
can be correct.

## The signal

### Line fullness

`slack = column_width − (upper_width + one_word_space + first_word_width_of_lower)`

1. **What it measures.** Whether the first word of the lower line would physically have
   fitted at the end of the upper line, in the measured body column.
2. **Why it distinguishes.** A wrapped line broke *because the next word did not fit*; a
   container line stopped early because the heading ended. This is #130's argument,
   applied at the heading band.
3. **Confounders classified correctly: 18 / 18.** Their slack is +86.3 to +94.4.
4. **At-risk wraps damaged: 6 / 768** (and total missed joins *fall*, 71 → 62). The wrap
   distribution runs to p95 = −2.4; only the balanced-break tail reaches positive slack.
5. **Cross-version stable?** For this class, yes — the OIG confounders decide identically
   in every document. Not universally: see the residual below.
6. **Mutation that makes it fail.** Remove the fullness test (`M1`) or restore `D6` ahead
   of it (`M3`): confounders correctly split drops **18 → 0** in both. Inverting it
   (`M2`) does the same and adds 1516 missed joins.

### Signals tested and rejected for this class

| signal | result |
|---|---|
| upper line width, upper/column ratio | separates the 18 but splits **all 768** wraps — it is width, not fullness |
| absolute left edge (indent) | separates perfectly, but it is a proxy for width on centred text and would hard-code one column geometry |
| centre offset between the two lines | CONF median 0.17 pt vs WRAP median 0.21 pt — dead, as it was corpus-wide |
| lower line width | 225 wraps damaged |
| line balance ratio | **explicitly falsified**: the confounder sits at 0.78 and the balanced-break wrap at 0.89, with combined width exceeding the column in both. Any balance rule that joins one re-joins the other |

## Candidate 3

The smallest rule the finding supports. **No document-local learned state of any kind.**

```
C1  upper line ends in a wrap hyphen                        -> JOIN
C2  caps_per_word(upper) >= T and caps_per_word(lower) < T  -> SPLIT
C3  fullness slack is None (geometry absent)                -> SPLIT    (fail closed)
C4  fullness slack >= 0                                     -> SPLIT
C5  otherwise                                               -> JOIN
```

T = 0.5. Against frozen candidate 1: `D1`/`D2`/`D3` (vocabulary) removed entirely, and
`D6` removed so those boundaries reach the fullness test instead of short-circuiting past
it. `C3` is the explicit conservative missing-evidence rule the previous round lacked.

### Results, combined development evidence (3466 boundaries, 712 cross-version headings)

| | false joins | novel FJ | missed joins | novel MJ | unstable |
|---|---|---|---|---|---|
| shipped | 64 | — | 1296 | — | — |
| frozen candidate 1 | 1 | 1 | 71 | 0 | 4 |
| **candidate 3** | **2** | 2 | **62** | **0** | **3** |

Clause usage: `C2` 1882, `C5` 1524, `C4` 43, `C1` 17. Confounder class **18/18** split,
**762/768** at-risk wraps preserved.

### Negative controls

| mutation | false joins | missed joins | unstable | confounders split |
|---|---|---|---|---|
| none (candidate 3) | 2 | 62 | 3 | **18/18** |
| `M1` remove fullness | 39 | 56 | 2 | **0/18** |
| `M2` invert fullness | 37 | 1578 | 14 | **0/18** |
| `M3` restore `D6` ahead of fullness | 20 | 56 | 3 | **0/18** |
| `M4` remove the caps clause | 373 | 6 | 19 | 18/18 |
| `M5` make `C3` fail **open** | 2 | 62 | 3 | 18/18 |

`M1`/`M2`/`M3` each turn the confounder result red; `M4` turns the segmentation result
red. `M5` is **inert and reported as such**: the missing-geometry clause has still never
fired on any corpus, so its direction is specified but unexercised.

## Why candidate 3 is NOT returned as development-valid

Of the four stated viability conditions it meets three: it prevents the known
container/account false joins (18/18), preserves genuine wrapped accounts (misses fall
71 → 62), and carries no document-local vocabulary. It fails the fourth — **3
cross-version instabilities of 712** — and it adds one novel false join relative to
candidate 1.

The residuals are diagnosed, and **neither belongs to the class this round was authorized
to fix**:

**(a) A container whose line nearly fills the column.** Both false joins are one pair, in
two documents:

```
NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION   width 326.0 of a 335.0 column
OPERATIONS, RESEARCH, AND FACILITIES              slack -67.8  ->  C5 joins
```

There is no early break to see, so fullness is blind by construction. This is exactly
`#501`'s recorded limitation, arriving at the account band. It also produces 2 of the 3
instabilities, because the same bill prints the agency wrapped across two lines elsewhere
and gets it right there.

**(b) A balanced centred break.** The remaining instability is one heading typeset two
ways in two versions of one bill:

```
2_engrossed-in-house   'GRANTS FOR CONSTRUCTION OF STATE EXTENDED CARE' / 'FACILITIES'
                        328.5 / 63.6   slack -63.0  -> join, correct
4_engrossed-amdt-senate 'GRANTS FOR CONSTRUCTION OF' / 'STATE EXTENDED CARE FACILITIES'
                        177.8 / 200.2  slack +116.8 -> split, wrong
```

The second is broken for **visual balance**, not because the column filled. Fullness asks
"did the next word fit?", and for a deliberately balanced centred heading the honest
answer is no — the break was a typesetting choice. So this instability is a property of
the fullness signal itself, not of any vocabulary, and it survives the removal of every
document-local input.

## What additional observation the residuals would require

Not a gap in extraction. For (a) the two lines are physically indistinguishable from a
wrap on the page; the only evidence separating them is that NOAA recurs as a container,
which is document-local vocabulary and therefore banned, or the XML twin, which draft
PDFs do not have. For (b) the print genuinely encodes a balanced break that looks like a
deliberate stop.

Both are the wrap-versus-stack ambiguity `#551` names, at the residual. Nothing in the
glyph layer resolves them: the additional observation required is **not in the PDF**.

## Status

Candidate 3 is **not frozen** and **no holdout was drawn**, per the instruction that both
wait on passing the development invariants. It is returned for review as the smallest
rule the authorized finding supports, with its two residual classes named and bounded.

Reproduce:

```sh
uv run python docs/research/pdf-heading-identity/confounder/population.py
uv run python docs/research/pdf-heading-identity/confounder/candidate3.py
```
