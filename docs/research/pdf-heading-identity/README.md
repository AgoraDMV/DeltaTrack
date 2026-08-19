# Stable PDF heading identity — DESIGN PROPOSED, NOT IMPLEMENTED

The question [#524](https://github.com/AgoraDMV/DeltaTrack/issues/524) asks, under the
[#551](https://github.com/AgoraDMV/DeltaTrack/issues/551) heading-detection epic, and the
follow-up [`pdf-matching-convergence/moved-semantics.md`](../pdf-matching-convergence/moved-semantics.md)
left open: **a GPO heading wraps across as many printed lines as it needs, and the parser
captures one of them.**

Measured on `develop` at `19108be`, under the pinned `pypdfium2==5.12.1`. Nothing in
`src/` is changed by this study.

## Three things this study keeps apart

| | what it is | status |
|---|---|---|
| **printed fragment** | what appeared on one printed line — `Anchor.text` today | keep, it is the source-traceability record |
| **stable heading label** | the complete heading, invariant to wrapping and hyphenation | **achievable**, see the rule below |
| **legislative location identity** | where a provision sits in the bill's structure | **not** delivered by a label; still open |

The second does not imply the third, and the evidence is direct: 9 of the 145 round-2
moves carry byte-identical anchors on both sides, including the clearest relocation in
the corpus. Label equality is silent about movement.

## What is true today

`#524` reproduces exactly: **14** wrapped headings on `118-hr-4820`, each confirmed by
the XML twin, which still supplies ground truth. Two further cases in the same bill are
three-line wraps the issue does not list, so 14 is a floor there as the issue says.

**The defect is much larger than one bill.** `heading_runs.py` resolves 3962 of 4173
heading runs against the XML, uniquely — no run admits two admissible segmentations. Of
the 1698 boundaries inside the 1528 resolved multi-line runs, **794 are wraps and 904 are
stacks**, and the shipped rule — which cuts only immediately before the leaf — scores:

```
shipped     false joins  30    missed joins 654
```

654 wrapped headings are read as a container plus a fragment. `#524`'s 14 are the subset
whose fragment is provably not a heading name in the XML.

## Evidence that does not work

Five plausible discriminators are dead, and saying so is load-bearing — one of them is an
open issue.

| signal | result |
|---|---|
| **per-line median glyph size** | identical on both sides of **every** boundary, both classes |
| **baseline leading** | GPO sets one uniform 26 pt pitch; the 25.77–26.23 pt spread is baseline-median noise. Best threshold errs on 344 of 728 |
| **font *name* and weight** (`#198`) | identical on both sides of every boundary; `DeVinne`/`DeVinne` and `DeVinne-Italic`/`DeVinne-Italic` both occur in both classes |
| **printed line-number gap** | exactly 1 at every boundary in both classes — no blank line ever separates two stacked headings |
| **centring** | the two lines share a centre axis whether wrapped or stacked, confirming the `#106` spike |
| **carry-over scope** (does the upper line container ≥2 leaves?) | 397/363 vs 365/387 — a coin flip; forcing it costs 400 missed joins |

**Line fullness is the only *geometric* signal that separates the classes, and not
cleanly.** `slack = column_width − (upper_width + space + first_word_lower)`:

```
true SPLIT   n=904  min=-75.8  p5=-48.8  med= 63.1  p95=209.1  max=257.7
true JOIN    n=794  min=-143.3 p5=-84.4  med=-27.6  p95= -2.6  max=116.8
```

The distributions overlap in both tails; no threshold on it separates them. That is
`#551`'s central claim, quantified — geometry alone cannot decide.

## What does work: typography the median throws away

`pdf_text._page_glyph_sizes` reduces every printed line to a **median** glyph size. That
collapse destroys the level marker GPO actually prints.

GPO sets a **container** heading in caps-and-small-caps, putting one large capital on
every word. An account heading set in even small caps carries at most a single
sentence-initial large capital, and often none:

```
DEFENSE NUCLEAR FACILITIES SAFETY BOARD   {14.0pt: 5, 11.2pt: 30}   5 large / 5 words
SALARIES AND EXPENSES                     {11.2pt: 19}              0 large / 3 words
SELF-HELP AND ASSISTED HOMEOWNERSHIP      {11.2pt: 32, 14.0pt: 1}   1 large / 4 words
```

The discriminating statistic is **large capitals per word**, not their presence — the
mere presence of a second size splits `SELF-HELP AND ASSISTED HOMEOWNERSHIP` from its own
continuation, which is one of `#524`'s fourteen.

Two independent signals plus geometry, applied in order — document-internal vocabulary,
then caps-per-word, then line fullness:

```
                                        false joins   missed joins
shipped (cut before leaf)                        30            654
line fullness alone                             175              3
vocabulary + fullness                            70             10
caps-per-word presence + vocabulary + fullness   12             92
caps-per-WORD + vocabulary + fullness             1             27
```

**The final rule is strictly better than the shipped one on both failure directions**:
1 false join against 30, and 27 missed joins against 654. It is not a trade.

The vocabulary pass is document-internal and carries no appropriations English, so
ADR 0018 holds: a run of one line is a complete heading by construction (body prose above
and below it), and a boundary with large positive slack was broken deliberately. Those
confident cases define per-document account and container vocabularies that decide the
ambiguous middle.

### A correction to an earlier version of this table

An earlier revision of this document headlined **1 false / 15 missed**. That is the
count at **T=0.6**, while the same document recommended shipping **T=0.5**, whose count
is **1 false / 27 missed**. Same 1528 runs, same 1698 boundaries, same scorer -- the
12-miss delta is entirely the operating point. The number a record headlines has to be
the one its design licenses, so the table above now carries the T=0.5 figure and 1/15
appears only as the far end of the plateau below.

### The margin, not just the outcome

`#501` option 1's lesson applied to this rule. The false-join count is **flat at 1 across
T ∈ [0.40, 0.60]**, then steps to 14 at 0.62 and 36 at 0.68:

```
T=0.50  false_joins=1   missed_joins=27      <- the frozen operating point
T=0.60  false_joins=1   missed_joins=15      <- top of the plateau; NOT the shipped point
T=0.62  false_joins=14  missed_joins=12      <- cliff
```

So **T=0.5 is the value to ship, not 0.6**: same false-join count, 0.12 of headroom
instead of 0.02, at a cost of 12 additional missed joins which fail closed. A standing
gate should measure the distance to the cliff, not merely that the corpus passes.

### Against `#524`'s own gate, at the frozen T=0.5

All **14/14** named headings recovered as single account headings. Account-vocabulary
recall and precision get **worse on zero documents**; **zero** breaches of the 0.70 floors
in `tests/test_pdf_anchor_golden.py`. At the container level — the one the account floors
structurally cannot see, and `#501`'s failure mode — **52 names gained, 5 lost**, with 4
documents seeing container recall fall.

(Re-derived at T=0.5 after the correction above. The gate outcome is insensitive to the
operating point across the plateau: T=0.6 gives the same 0 breaches, same 0 documents
worse on account, same 14/14, and 5 rather than 4 documents worse on container.)

## Negative controls

Seven named corpus cases, both directions, under five mutations of the rule (invert the
fullness inequality; drop the vocabularies; always split; always join; drop the
mid-word-hyphen guard). Every control is reddened by at least one mutation and none by
all, so the set discriminates rather than merely passing.

`EMPLOYMENT AND TRAINING ADMINISTRATION` + `TRAINING AND EMPLOYMENT SERVICES` fails under
vocabulary+fullness and **passes once caps-per-word is added** — it is the control that
earned the signal its place. The one residual false join corpus-wide is
`DEPARTMENT OF THE TREASURY` + `INTERNATIONAL AFFAIRS TECHNICAL ASSISTANCE`
(`118-s-4797`), which the control set should adopt.

## The label, and why it is not a key

With segmentation working, the **segment** — not the whole run — is the stable label, and
it is simultaneously wrap-invariant and correct as a displayed heading name. That
collapses what looked like two deliverables into one.

Re-adjudicating every moved row through the real `diff_pdfs`, using the whole-run join as
the identity:

```
canonical move.kind, today -> under a stable identity
  renumbered -> renumbered   139
  renumbered -> relocated     17
  relocated  -> relocated      9
```

All 17 are wrap artifacts including the cards `moved-semantics.md` names. **Nothing
genuine is erased**: the 3 real section renumberings, both in-place heading edits, the
edit-plus-relocation and the distinct-account mispair all stay `renumbered`. 131 of the
165 moved rows carry `section`/`section` anchors and are untouched by construction. One
class is not fixed — a hyphenated fragment inside a quoted amendment
(`GINIA.— → WEST VIRGINIA.—`) reaches no heading run at all.

**The label is not unique per block**: 1205 of 3282 labels are carried by more than one
block. Under today's fragmentation that is partly the defect itself; under correct
segmentation it is genuine recurrence (`MILITARY CONSTRUCTION, NAVY AND MARINE CORPS`
appears twice in `114-hr-2029`). Either way it is not an observation key. Measured by
substituting it into `_block_key` across the 17 accepted pairs:

```
opcodes 2   considered 2   candidates 2   post_revocation 2
round2_unmatched 2   n_moves_round2 2   summary 0   canonical 1
```

**That is a matching-policy change and belongs to a separate `#170`-style decision.** Not
implemented. The display use above moves none of those rows.

## Proposed data model

```
Anchor.text            raw printed fragment      KEEP — source traceability, unchanged
Anchor.heading_label   the joined SEGMENT        NEW — optional; None when undecidable
Anchor.kind            unchanged
(location identity)    NOT PROPOSED
```

- **Optional, and absent rather than guessed.** The 15 missed joins are the rule declining;
  a `None` label leaves today's behaviour, while a wrong join fabricates a heading that was
  never printed. Fail closed on the side that does not invent structure.
- **Observation production, not presentation.** It is a fact about the print, derived like
  `kind` and `division`. Computing it in `formatters/canonical.py` would put parsing inside
  presentation and hide it from the ADR 0019 contract.
- **It moves `pdf_parser_revision()`, and should.** Measured: `pdf_anchors`, `pdf_text`,
  `pdf_blocks` and `amounts` move it; `canonical`, `diff_pdf` and `similarity` do not.
- **Allowed consumers: presentation and classification-for-description only.** Forbidden:
  `_block_key`, CandidateSet membership, correspondence evidence, assignment.
- **Retaining the within-line profile is its own parser change.** `LineGeom` carries no size
  distribution today, so `pdf_text` must stop discarding it. That is the smallest production
  edit here and the one every number above depends on.

## External validity

The result below is IN-SAMPLE. It was tested out-of-sample against 21 unseen bills and
the ruling was **B, MIXED**: the segmentation generalises (zero fabricated structure on
17 scored bills, a strict error-subset of shipped behaviour), but cross-version
segmentation stability -- this design's own nominated falsifier -- fired at 2 of 932
headings. See [`EXTERNAL-VALIDITY.md`](EXTERNAL-VALIDITY.md). The recommendation below
is superseded by that document's ruling and its remaining blockers.

## Recommendation

**One change, not two, and it is a strict improvement — but land the gate first.**

1. **Add a container-level regression gate** to `tests/test_pdf_anchor_golden.py`, and make
   it measure the caps-per-word **margin** rather than only the outcome. The account floors
   cannot see a merged container, which is the failure that deletes a real heading.
2. **Retain the within-line glyph profile in `pdf_text`**, segment the heading run with
   vocabulary → caps-per-word (T=0.5) → fullness, and expose the segment as an optional
   `Anchor.heading_label`. This closes `#524` and the `moved-semantics.md` follow-up
   together.
3. **Stop there.** `_block_key`, CandidateSet, assignment and canonical `moved` semantics
   are untouched.

This supersedes an earlier draft of this document, which recommended shipping a
display-only label and holding the segmentation change. That was correct for the
vocabulary+fullness rule it was based on, which cost 60 container names; the caps-per-word
signal removes the trade, so holding is no longer the right call.

## Issue-by-issue

| issue | recommendation |
|---|---|
| **#524** | closable by the change above. Worth recording that the corpus-wide population is 654 missed joins, not 14 |
| **#551** | its central claim is now measured: geometry alone cannot decide, with the overlapping distributions to show it. `#524` and `#501` are one rule with one threshold |
| **#170** | owns the `_block_key` substitution and location identity. Neither is touched here |
| **#501** | **same rule, same threshold, opposite direction** — but measured at the heading band, **not** at the body-size major band `#501` is about. The evidence should transfer; it is not measured there, and should be before `#501` is called solved |
| **#500** | related but a different upstream predicate (`continues_section_catchline`). Not solved by this |
| **#508** | **precondition, not a shared solution.** No size bands means no runs at all |
| **#261** | same relationship as `#508`: no margin numbers, so no geometry sidecar and no run |
| **#198** | **partly vindicated, and redirected.** Font *name* is measured dead here. But `#198`'s underlying idea — key on typographic *role* rather than position — is exactly what carries this fix, in the form of the within-line size profile. Its own chrome-vs-body finding stands |

No new issue is proposed: every finding lands inside the existing structure.

## The falsifier

**Cross-version segmentation stability is the one this design has not measured.** The
label is derived per document, and the vocabulary pass is bootstrapped from *that
document's* confident boundaries. If two versions of one bill bootstrap different
vocabularies, the same printed heading can segment differently on the two sides — and the
false-`Renumbered` fix becomes a false-`relocated` bug. The 17-card result above was
measured with the whole-run join, which cannot segment differently; the segment label can.
**Measure it before implementing.**

Two narrower ones. A printed run spanning two logical headings whose caps-per-word profile
matches on both lines is undecidable by this rule and must fail closed, not join. And if a
future consumer needs a per-block key, the label cannot become one — a location identity
would have to be built rather than the label promoted.

## Reproducing

```sh
uv run python docs/research/pdf-heading-identity/probes/heading_runs.py
uv run python docs/research/pdf-heading-identity/probes/line_typography.py
uv run python docs/research/pdf-heading-identity/probes/segmentation_rules.py
uv run python docs/research/pdf-heading-identity/probes/identity_effects.py
```

The last three read the first's output. `results/` is gitignored.

Four probes are retained because each reproduces a consequential result no permanent test
owns: the XML-derived segmentation oracle (the account floors score a set of names and
cannot see where a run was cut), the typography signal and its threshold plateau, the
two-directional rule scoring with its mutations, and the display-versus-retrieval
separation. Both probes that duplicate the production glyph walk assert equality against
`pdf_text._page_glyph_sizes` on every page before reporting; `identity_effects.py`
perturbs each source file to show what the parser revision is sensitive to, and restores
and re-checks the tree before reporting.
