# Stable PDF heading identity — DESIGN PROPOSED, NOT IMPLEMENTED

The question [#524](https://github.com/AgoraDMV/DeltaTrack/issues/524) asks, under the
[#551](https://github.com/AgoraDMV/DeltaTrack/issues/551) heading-detection epic, and the
follow-up [`pdf-matching-convergence/moved-semantics.md`](../pdf-matching-convergence/moved-semantics.md)
left open: **a GPO heading wraps across as many printed lines as it needs, and the parser
captures one of them.**

Measured on `develop` at `19108be`. Nothing in `src/` is changed by this study.

## Three things this study keeps apart

| | what it is | status after this study |
|---|---|---|
| **printed fragment** | what appeared on one printed line — `Anchor.text` today | keep, it is the source-traceability record |
| **stable heading label** | the complete heading, invariant to wrapping and hyphenation | **available now**, and the recommendation below |
| **legislative location identity** | where a provision sits in the bill's structure | **not** delivered by a label; still open |

The second does not imply the third, and the evidence is direct: 9 of the 145 round-2
moves carry byte-identical anchors on both sides, including the clearest relocation in
the corpus. Label equality is silent about movement.

## What is true today

`#524` reproduces exactly: **14** wrapped headings on `118-hr-4820`, each confirmed by
the XML twin, which still supplies ground truth. Two further cases in the same bill are
three-line wraps the issue does not list (`GOVERNMENT NATIONAL MORTGAGE ASSOCIATION` /
`GUARANTEES OF MORTGAGE-BACKED SECURITIES LOAN` / `GUARANTEE PROGRAM ACCOUNT`, and
`NEIGHBORHOOD REINVESTMENT CORPORATION` / `PAYMENT TO THE NEIGHBORHOOD REINVESTMENT` /
`CORPORATION`), so 14 is a floor on that bill as the issue says.

**The defect is much larger than one bill.** Over the committed dual-format corpus,
`heading_runs.py` resolves 3962 of 4173 heading runs against the XML, uniquely — no run
admits two admissible segmentations. Of the 1698 boundaries inside the 1528 resolved
multi-line runs, **794 are wraps and 904 are stacks**, and the shipped rule — which cuts
only immediately before the leaf — gets:

```
shipped     false joins  30    missed joins 654
```

654 wrapped headings are read as a container plus a fragment. `#524`'s 14 are the subset
whose fragment is provably not a heading name in the XML.

## Evidence that does not work, measured

Five candidate discriminators are dead, and saying so is the substantive result — each
was plausible and one is an open issue.

| signal | result |
|---|---|
| **glyph size** within the heading band | identical on both sides of **every** boundary, both classes. Size cannot separate agency from account |
| **baseline leading** | GPO sets one uniform 26 pt pitch; the observed spread is 25.77–26.23 pt, which is baseline-median noise. The best threshold errs on 344 of 728 boundaries, worse than geometry |
| **font name / weight** (`#198`) | identical on both sides of every boundary, and both `DeVinne`/`DeVinne` and `DeVinne-Italic`/`DeVinne-Italic` occur in both classes. `#198`'s chrome-vs-body finding is real and unaffected; it carries no signal at this level |
| **printed line-number gap** | exactly 1 at every boundary in both classes. No blank line ever separates two stacked headings |
| **centring** | the two lines share a centre axis whether wrapped or stacked, confirming the `#106` spike |
| **carry-over scope** (does the upper line container ≥2 leaves?) | 397/363 vs 365/387 — a coin flip. Forcing it costs 400 missed joins |

Leading and font are not carried by `LineGeom` today; both were measured with a
duplicated glyph walk that also re-emitted the production `(size, LineGeom)` and asserted
equality against `pdf_text._page_glyph_sizes` on every line of 2974 pages before any
number was reported. Zero divergence.

**Line fullness is the only geometric signal that separates the classes, and it does not
separate them cleanly.** `slack = column_width − (upper_width + space + first_word_lower)`:

```
true SPLIT   n=904  min=-75.8  p5=-48.8  med= 63.1  p95=209.1  max=257.7
true JOIN    n=794  min=-143.3 p5=-84.4  med=-27.6  p95= -2.6  max=116.8
```

The distributions overlap in both tails. **No threshold on this statistic separates
them** — the best single cut still errs on 191 boundaries. That is `#551`'s central claim,
quantified: a stacked pair whose upper line happens to nearly fill the column is
geometrically identical to a wrap, which is `#501` and `#524` being the same judgement.

## The candidate rule, and its price

Geometry has to be arbitrated by something that is not the page. The one source available
without leaving the document — and without appropriations English, so ADR 0018 holds — is
**what the document repeats about itself**:

- a run of one line is a complete heading by construction (body prose above and below);
- a boundary with large positive slack was broken deliberately, so its lower side is an
  account name and its upper side a container name.

Pass 1 collects those confident cases into per-document account and container
vocabularies; pass 2 decides the ambiguous middle from them, falling back to geometry.

```
shipped                 false joins  30    missed joins 654    total 684
geometry alone          false joins 175    missed joins   3    total 178
candidate (two-pass)    false joins  70    missed joins  10    total  80
```

Insensitive to the pass-1 bound between 20 and 80 pt.

**Against `#524`'s own stated gate it passes outright**: all 14 named headings are
recovered as single account headings; account-vocabulary recall rises on every measured
bill (0.740–0.855 → 0.932–1.000, and 0.762 → 0.963 on `118-hr-4820`); precision rises or
holds on every bill; and there are **zero breaches** of the 0.70 floors in
`tests/test_pdf_anchor_golden.py`.

**And it is not free, in a way those floors cannot see.** At the container level the same
change loses **60** real container names and gains 40 — net −20. That is `#501`'s failure
mode, and `#501` is explicit that it is the worse one: a merged heading means a real
department disappears and its money is filed under a name that was never printed. The
account floors score a *set of leaf names*, so a lost container is invisible to them.

**A container-level gate does not exist and is owed before any segmentation change
lands.** That is the single most important finding for sequencing.

## Negative controls

Both symmetric failures are owned by named corpus cases, and each is re-run under five
mutations, because a control no mutation can redden is not a control:

```
control                           expect     none     M1     M2     M3     M4     M5
under-join #524 GREAT LAKES       JOIN       PASS   FAIL   PASS   FAIL   PASS   PASS
under-join #524 COMMUNITY DEV     JOIN       PASS   FAIL   PASS   FAIL   PASS   PASS
under-join #524 MARITIME TITLE XI JOIN       PASS   FAIL   PASS   FAIL   PASS   PASS
over-join DEFENSE NUCLEAR BOARD   SPLIT      PASS   PASS   FAIL   PASS   FAIL   PASS
over-join FEDERAL AVIATION        SPLIT      PASS   FAIL   PASS   PASS   FAIL   PASS
over-join EMPLOYMENT+TRAINING     SPLIT      FAIL   PASS   FAIL   PASS   FAIL   FAIL
over-join OFFICE OF SECRETARY     SPLIT      PASS   PASS   PASS   PASS   FAIL   PASS
```

`M1` inverts the fullness inequality, `M2` removes the bootstrapped vocabularies, `M3`
always splits (today's behaviour), `M4` always joins, `M5` drops the mid-word-hyphen
guard. Every control is reddened by at least one mutation and no mutation reddens all of
them, so the set discriminates rather than merely passing.

`EMPLOYMENT AND TRAINING ADMINISTRATION` / `TRAINING AND EMPLOYMENT SERVICES` **fails
under the candidate** and is recorded as a known over-join rather than removed from the
control set. `M5` moves nothing corpus-wide: the hyphen guard is inert on this corpus and
is retained on structural grounds, not measured ones.

## The label, and why it is not a key

A **heading run** — the contiguous in-band heading block delimited by body prose on both
sides — is invariant to where the typesetter broke the lines inside it. That is the
wrap-invariant unit, and **recovering it does not require solving wrap-versus-stack at
all**, which is what separates the two deliverables below.

Re-adjudicating every moved row through the real `diff_pdfs`:

```
canonical move.kind, today -> under a run identity
  renumbered -> renumbered   139
  renumbered -> relocated     17
  relocated  -> relocated      9
```

All 17 are visibly wrap artifacts, including the cards `moved-semantics.md` names
(`NAVY AND MARINE CORPS → AND MARINE CORPS`, `HOUSING IMPROVEMENT FUND → FUND`). **No
genuine distinction is erased**: the 3 real section renumberings, both in-place heading
edits (`RELATED AGENCY → RELATED AGENCIES`, the `ENERGY SECRUITY` typo), the heading edit
plus relocation, and the distinct-account mispair (`ELECTRICITY DELIVERY → NUCLEAR
ENERGY`) all stay `renumbered`. 131 of the 165 moved rows carry `section`/`section`
anchors and are untouched by construction.

One class is **not** fixed: a hyphenated fragment inside a quoted amendment
(`EXPENSES—MEMBERS' REPRESENTATIONAL ALLOW-` → `PENSES—…ALLOWANCES''`, and the
`GINIA.— → WEST VIRGINIA.—` card) reaches no heading run. That is a different mechanism.

**The label is not unique per block.** Over the corpus, 1205 of 3282 run labels are
carried by more than one block, and 2610 blocks sit inside a collision — partly genuine
recurrence, partly the very fragmentation this fixes (`NORTH ATLANTIC TREATY
ORGANIZATION` + `SECURITY INVESTMENT PROGRAM` are two blocks with one label). Used as a
retrieval key it merges observations.

Measured directly, by substituting it into `_block_key` in a probe over the 17 accepted
pairs:

```
opcodes 2   considered 2   candidates 2   post_revocation 2
round2_unmatched 2   n_moves_round2 2   summary 0   canonical 1
```

**That is a matching-policy change and belongs to a separate `#170`-style decision.** It
is not implemented here, and the display use above changes none of those rows.

## Proposed data model

```
Anchor.text            raw printed fragment      KEEP — source traceability, unchanged
Anchor.heading_label   the joined heading run    NEW — wrap/hyphenation invariant
Anchor.kind            unchanged
(location identity)    NOT PROPOSED — see below
```

- **Observation production, not presentation.** The label is a fact about the print,
  derived from the page the same way `kind` and `division` are. Computing it in
  `formatters/canonical.py` would put parsing inside presentation and hide it from the
  ADR 0019 contract.
- **It moves `pdf_parser_revision()`, and should.** Measured: editing `pdf_anchors.py`,
  `pdf_text.py`, `pdf_blocks.py` or `amounts.py` moves the revision; editing
  `canonical.py`, `diff_pdf.py` or `similarity.py` does not. A new anchor field changes
  what an observation *is*, so the revision moving is the mechanism working.
- **Allowed consumers: presentation and classification-for-description only** —
  `formatters/canonical._pdf_move`, breadcrumbs, the tree label. **Forbidden: `_block_key`,
  CandidateSet membership, correspondence evidence, assignment.** Not a style rule: the
  label is not unique per block, so as a key it merges observations, and the substitution
  measurably moves canonical output.
- **A legislative location identity is still missing.** A label answers "is this the same
  heading?"; it does not answer "is this the same place in the bill?". That needs the
  materialised tree path plus sibling position, which is `#170`'s territory, and the
  9 identical-anchor round-2 relocations are the evidence that a label cannot stand in.

## Recommendation

**Split the work; ship the label, hold the segmentation.**

1. **`Anchor.heading_label`, consumed by presentation only.** Fixes 17 of the 156 false
   `Renumbered:` cards with zero erasures and zero movement in any matching stage. Does
   not touch segmentation, so it carries no `#501` exposure at all. This closes the
   `moved-semantics.md` follow-up; it does **not** close `#524`.
2. **Segmentation (the actual `#524` fix) waits on a container-level regression gate.**
   The two-pass rule clears `#524`'s stated verification in full, and the account floors
   are structurally unable to see the 60 lost container names it costs. Add the gate
   first, then the rule is a defensible change with both failure directions visible.

## Issue-by-issue

| issue | recommendation |
|---|---|
| **#524** | stays open after deliverable 1. Closed by deliverable 2, whose blocker is a gate, not evidence. Worth recording on the issue that the corpus-wide population is 654 missed joins, not 14 |
| **#551** | the epic's core claim is now measured rather than asserted: geometry alone cannot decide, with the overlapping distributions to show it. `#524` and `#501` are one rule with one threshold |
| **#170** | owns the `_block_key` substitution and the location identity. Neither is touched here. The measured stage-output movement is the evidence that it is a separate decision |
| **#501** | **same rule, same threshold, opposite direction** — but measured at the heading band, not at the body-size major band `#501` is about. The evidence transfers in principle; it is **not measured there**, and should be before `#501` is called solved |
| **#500** | related but separate. `continues_section_catchline` runs upstream of run detection and is a different predicate. The bootstrapped vocabulary might help; not measured |
| **#508** | **precondition, not a shared solution.** No size bands means no runs at all, so the fix cannot reach reconciliation bills until `#508` lands |
| **#261** | same relationship as `#508`. Unnumbered layouts carry no margin numbers, so the geometry sidecar is empty and no run is formed |
| **#198** | **related evidence only, and now measured negative for this problem.** Font is identical on both sides of every boundary. Its chrome-vs-body value stands; it is not the epic's spine |

No new issue is proposed: every finding lands inside the existing structure.

## The falsifier

**What would make us reject this design:** a printed heading run that spans two logical
headings *and* is compared across a re-typeset version. The label is derived from the run,
so if runs are not stable units, two distinct headings would be handed one identity on
both sides and the false-`Renumbered` fix would become a false-`relocated` bug. The
corpus shows no such case, but the corpus is thin exactly here: 16 of the 20 disputed
round-1 rows come from a single strike-and-insert Senate amendment, and three pairs of
seventeen carry almost all of them.

Two narrower ones. If a bill sets a stacked pair with **no** body prose between the two
headings and their neighbours, run boundaries stop being derivable from prose and the
unit dissolves — that is `#500`'s shape arriving at the account level. And if a future
consumer needs a per-block key, the label cannot become one, so a genuine location
identity would have to be built rather than the label promoted.

## Reproducing

```sh
uv run python docs/research/pdf-heading-identity/probes/heading_runs.py
uv run python docs/research/pdf-heading-identity/probes/segmentation_rules.py
uv run python docs/research/pdf-heading-identity/probes/identity_effects.py
```

The second reads the first's output. `results/` is gitignored.

Three probes are retained because each reproduces a consequential result no permanent
test owns: the XML-derived segmentation oracle (the account-vocabulary floors score a set
of names and cannot see where a run was cut), the two-directional rule scoring with its
mutations, and the display-versus-retrieval separation. `identity_effects.py` perturbs
each source file to show what the parser revision is sensitive to, and restores and
re-checks the tree before reporting.
