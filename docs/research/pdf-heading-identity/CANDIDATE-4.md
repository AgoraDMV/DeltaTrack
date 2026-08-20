# Candidate 4 (conservative) — VALIDATED. Research closed; implementation plan below.

The conservative option candidate 3's own measurements produced, and which the previous
round wrongly left out of the decision set: where the printed page cannot tell a genuine
near-full container from a deliberately condensed wrapped account, **decline to join**.

Frozen digest `4e3bd13caf948da0682381f174b7def407b33944cc433555942fe68abc74da15`
(the earlier `c604261…` digest is the same rule with one fail-open branch, closed at
implementation — see the closure correction below).

**Status: IMPLEMENTED.** `src/deltatrack/parsers/pdf_text.py` retains the evidence and
`src/deltatrack/parsers/pdf_anchors.py` interprets it. Research is closed.

## 1. The six declined wraps are bounded fail-closed under-joins

Consequence check on every genuine wrap the conservative discriminator declines.

| bill / version | heading (XML truth) | shipped | candidate 3 | candidate 4 | identical to shipped? |
|---|---|---|---|---|---|
| `118-hr-2882/5_eah` p701 | `UNITED STATES INTERNATIONAL DEVELOPMENT FINANCE CORPORATION INSPECTOR GENERAL` | agency `…FINANCE CORPORATION` + account `INSPECTOR GENERAL` | same | same | **yes** |
| `118-hr-4366/4_eas` p228 | `RAILROAD REHABILITATION AND IMPROVEMENT FINANCING PROGRAM` | agency `…FINANCING` + account `PROGRAM` | account = whole | agency `…FINANCING` + account `PROGRAM` | **yes** |
| `118-hr-4366/5_eah` p228 | `PUBLIC TELECOMMUNICATIONS FACILITIES, PLANNING AND CONSTRUCTION` | account `CONSTRUCTION`, no agency | account = whole | account `CONSTRUCTION`, no agency | **yes** |
| `118-hr-4366/5_eah` p412 | `DEFENSE URANIUM ENRICHMENT DECONTAMINATION AND DECOMMISSIONING` | account `DECOMMISSIONING`, no agency | account = whole | account `DECOMMISSIONING`, no agency | **yes** |
| `118-hr-4366/5_eah` p639 | `RAILROAD REHABILITATION AND IMPROVEMENT FINANCING PROGRAM` | agency `…FINANCING` + account `PROGRAM` | account = whole | agency `…FINANCING` + account `PROGRAM` | **yes** |
| `114-hr-2578/rs` p116 | `PUBLIC TELECOMMUNICATIONS FACILITIES, PLANNING AND CONSTRUCTION` | account `CONSTRUCTION`, no agency | account = whole | account `CONSTRUCTION`, no agency | **yes** |

**All six are byte-identical to shipped at those boundaries.** Three emit a fragment
container (`RAILROAD REHABILITATION AND IMPROVEMENT FINANCING`); the `_dangles` guard
suppresses it in the other three. Every one of those fragment containers is what shipped
emits today, so none is a new error.

Correspondence, move and financial effects: none attributable to the six. On
`115-hr-5895` 3→4 candidate 4 is identical to candidate 3 (52 moves, 4 false-fragment);
on `118-hr-4366` 4→5 it differs by 1–3 anchors with the same move counts. No account
loses its money; the truncation is in the label.

Breadcrumb parents, candidate 4 versus shipped, are **corrections**, not fabrications:

```
MAJOR RESEARCH EQUIPMENT AND FACILITIES   -> NATIONAL SCIENCE FOUNDATION
SALARIES AND EXPENSES, FOREIGN CLAIMS     -> LEGAL ACTIVITIES
CYBERSECURITY, ENERGY SECURITY, AND EMERGENCY -> ENERGY PROGRAMS
NORTH ATLANTIC TREATY ORGANIZATION        -> DEPARTMENT OF DEFENSE
ACQUISITION OF LANDS FOR NATIONAL FORESTS SPECIAL -> FOREST SERVICE
```

Fragment parents replaced by real containers — the exact opposite of the NOAA damage,
which replaced a real container with a *different real* container (NIST).

**Verdict: bounded fail-closed under-joins. Nothing comparable to the NOAA fabrication.**

## 2. Candidate 4, frozen

`frozen/frozen_candidate4.py`. Candidate 3 plus one clause:

```
C1  upper line ends in a wrap hyphen                         -> JOIN
C2  caps_per_word(upper) >= 0.5 and caps_per_word(lower) < 0.5 -> SPLIT
C3  fullness slack is None (geometry absent)                 -> SPLIT   fail closed
C4  fullness slack >= 0                                      -> SPLIT
C5  fill >= 0.97 and tracking_ratio <= 0.31                  -> SPLIT   fit manufactured
C6  otherwise                                                -> JOIN
```

`tracking_ratio` is the line's mean intra-word inter-glyph gap over the document's median.
`C5` says: a near-full line that was *also condensed relative to its own document* proves
only that a fit was manufactured, so fullness has nothing left to observe — decline.

**Missing-evidence behaviour, including where it is not conservative.** Missing caps skips
`C2`. Missing geometry hits `C3` and declines. **Missing tracking makes `C5` unavailable and
the boundary falls through to `C6` (JOIN) — the one residual fail-open**, frozen in that
direction because splitting every no-margin boundary in such a document would undo #524
there. It occurred on **0** documents in development and **0** in holdout 2. Seven
accepted-pair documents lacked tracking in the probe, and all seven produce zero in-scope
boundaries (no size bands, or no runs), so the clause is unreachable in them.

**Freeze control.** Mutating `FILL_MIN` (0.97→0.90), `TRACK_RATIO_MAX` (0.31→0.60), and the
`C3` fail-closed direction each made `freeze_check4` exit 1 naming both digests; restoring
returned it to green.

## 3. Second holdout — drawn after the freeze, scored once

`holdout2/draw2.py`, seed **20260820** (distinct from draw 1's 20260819). Pool 796, minus
all **117** bills draw 1 touched (21 selected + 96 rejected), leaving 679. Drawn **21
bills / 35 versions, 3 per Congress across 113–119**, nine stage types. Zero overlap with
`tests/corpus/`, with holdout 1, or with `/bills`. Artifacts in the gitignored
`bills/_holdout524b/`; provenance and SHA-256s in `holdout2/holdout2_manifest.json`.

Oracle built by the same modules: 2975 runs, 1142 multi-line, **1031 resolved**, 111
unresolved, 8 documents excluded for `no_size_bands`. Contract check on both glyph walks:
**12,206 pages, 0 divergences**.

### Result

| | false joins | novel FJ | missed joins | novel MJ |
|---|---|---|---|---|
| shipped | 42 | — | 389 | — |
| **candidate 4** | **0** | **0** | **21** | **0** |

**PRIMARY GATE — no oracle-established SPLIT joined: PASS.** Missed joins fall 389 → 21, a
94.6% reduction, reported as the secondary metric and not driven to zero.

Zero false joins on **every one of 17 bills** and **every one of 9 stages**. `C5` fired 3
times on unseen bills. 487 true wraps, 684 true stacks.

## 4. Deferred checks, now run

### 10A — development error-set dominance

Over the original corpus plus spent holdout 1 (3466 boundaries): shipped 64 FJ / 1296 MJ;
candidate 4 **0 FJ / 68 MJ**. Novel false joins **0**; candidate FJ ⊆ shipped FJ. One novel
missed join — `118-hr-2882/5_eah` p701, inside the run `UNITED STATES INTERNATIONAL
DEVELOPMENT FINANCE` / `CORPORATION` / `INSPECTOR GENERAL` — and it is **inert**: the
emission collapses everything before the account into one agency anchor, so the emitted
anchors are byte-identical to shipped. Candidate 4 introduces no development-corpus error
with any anchor-level consequence.

### 10B — actual final segmentation through the real pipeline

All 17 production-accepted adjacent pairs, `src/` untouched, `extract_anchors`
monkeypatched and restored. Every stage moves on most pairs — expected, since corrected
observation production propagates — and the deltas trace to oracle-confirmed corrections:
shipped-only hunks are fragments (`ACTS`, `CORPORATION`, `FUND`, `CIVIL WORKS`,
`DECOMMISSIONING`), candidate-4-only hunks the complete headings. `118-hr-8752` 1→2 shows
**no stage change at all**, which is the control that the pipeline is not moving for
unrelated reasons.

### 10C — PR #639 re-adjudication with the actual segmentation

With **no change to `_pdf_move`**:

| | shipped | candidate 4 |
|---|---|---|
| canonical moves | 165 | **157** |
| **false-fragment `Renumbered`** | **21** | **8** |
| distinct-label moves | 135 | 137 |

The false-fragment cards fall by 62% upstream. `NAVY AND MARINE CORPS → AND MARINE CORPS`,
`HOUSING IMPROVEMENT FUND → FUND`, `POWER ADMINISTRATION → ADMINISTRATION` and the rest
disappear because the observations feeding the matcher are now correct. Genuine section
renumberings, the `ENERGY SECRUITY` heading edit and the `ELECTRICITY DELIVERY → NUCLEAR
ENERGY` mispair are all preserved. The residual 8 are the wrap artifacts candidate 4
declines, and they remain move/matching work rather than segmentation work.

## 5. Implementation plan

Bounded. No production code is written by this task.

**`src/deltatrack/parsers/pdf_text.py`** — retain the minimum print evidence the frozen
measurement needs, and nothing semantic:

- extend `LineGeom` (or add a sibling record) with the **glyph-size histogram** and the
  **mean intra-word inter-glyph gap** for the line's content glyphs. Both come from the
  existing `_page_glyph_sizes` char walk at no extra PDFium cost — the same walk already
  computes sizes and boxes; only the aggregation is new.
- no `is_account`, no `is_container`, no heading vocabulary. `pdf_text` exposes print
  evidence; `pdf_anchors` interprets it.

**`src/deltatrack/parsers/pdf_anchors.py`** — apply the frozen boundary predicate inside
`_account_anchors_by_size` only:

- compute the document's median tracking once per parse;
- replace "the account is the run's last line" with "the account is the run's last
  **segment** under C1–C6"; the agency remains everything before it, with the existing
  `_dangles` guard unchanged;
- leave the grouping-header path, `continues_section_catchline`, `_major_anchors_by_size`,
  the TITLE/SEC/subsection passes and the division pass untouched.

**Out of scope, explicitly:** `_block_key`, `CandidateSet`, correspondence evidence,
assignment, move thresholds, canonical move-kind semantics, `#501`'s major band, `#170`.

**Parser revision.** Both edits are inside the ADR 0019 observation closure, so
`pdf_parser_revision()` moves. That is correct — what an observation *is* changes.

**Behaviour gates that will move, and must be re-derived deliberately rather than
regenerated silently:** `tests/test_pdf_anchor_golden.py` account vocabulary floors (they
improve), and `tests/test_pdf_canonical_baseline.py` (canonical output changes on 15 of 17
accepted pairs). The baseline exists to make exactly this visible; re-derive it as its own
reviewed step with the move-card table above as the justification.

**Tests to add** — three, each with the mutation that reddens it:

1. *A wrapped account heading is one heading.* `GREAT LAKES ST. LAWRENCE SEAWAY
   DEVELOPMENT` / `CORPORATION` on the committed `118-hr-4820` must emit one account
   anchor. Reddens if `C6` is removed or the fullness comparison inverted.
2. *A container is never merged into its account.* `OFFICE OF INSPECTOR GENERAL` /
   `SALARIES AND EXPENSES` on a committed fixture must stay two anchors. Reddens if `C2`
   is removed, or if caps-per-word is replaced by mere mixed-size presence.
3. *A manufactured fit is declined.* A near-full condensed upper line must not be joined.
   Reddens if `C5` is removed — which is the control that brings the NOAA fabrication back.

Prefer committed fixtures; do not promote holdout bills into `tests/corpus/`. Retire the
`#524` xfail in `tests/test_pdf_size_detection.py` only if the new tests own the same
invariant.

**Known limitation to record on the issues.** Candidate 4 does not recover all fourteen
historical `#524` examples: `RAILROAD REHABILITATION AND IMPROVEMENT FINANCING PROGRAM` is
declined where its first line is condensed and near-full. The research established that
requiring all fourteen is incompatible with the no-fabricated-hierarchy invariant on
observed print, so `#524`'s verification section should be amended rather than the rule
bent to meet it.

## Reproducing

```sh
uv run python docs/research/pdf-heading-identity/frozen/freeze_check4.py
uv run python docs/research/pdf-heading-identity/holdout2/draw2.py
uv run python docs/research/pdf-heading-identity/holdout2/build2.py
uv run python docs/research/pdf-heading-identity/holdout2/score2.py
uv run python docs/research/pdf-heading-identity/holdout2/pipeline_ab.py
```


## 6. Closure correction and implementation

### The fail-open branch is closed

The frozen specification had one branch that was not conservative: when tracking was
unavailable, `C5` could not be evaluated and the boundary fell through to `C6` (JOIN).
It is now `C5b -> SPLIT`.

This changes no validated result. The branch fired **zero** times on the development
corpus and **zero** times on either holdout, and re-scoring holdout 2 under the corrected
specification reproduces its numbers exactly (0 false joins, 21 missed joins, `C5b` never
taken). The change is monotonic toward the primary invariant: declining can only remove
joins, and a false join is what the invariant forbids. `TestFailClosedOnMissingEvidence`
is the control, and it includes the case where the document median cannot be computed at
all.

### The median guard is a sign test, not a truthiness test

Implementation review found a second fail-open shape in the same clause. `C5b` was written
as `not track_median`, which catches `None` and `0.0` but passes a NEGATIVE median through
to `C5`. The ratio `tracking_upper / track_median` is monotone in "how condensed" only for
a positive median; with both terms negative the ordering reverses, so a *more* condensed
line scores a *larger* ratio, clears `TRACK_RATIO_MAX`, and falls through to `C6 -> JOIN`.
That is a false join on exactly the near-full condensed shape `C5` exists to decline.

It is now `track_median is None or track_median <= 0 -> SPLIT`.

**Measured before changing anything, because "no new holdout" depends on the branch being
unexercised.** Every document median in every validation population is strictly positive:

| population | documents with a median | minimum |
|---|---|---|
| development corpus (`tracking.jsonl`) | 63 | 0.02949 |
| holdout 2 (`holdout2-tracking.jsonl`) | 35 | 0.03071 |
| committed corpus, via the PRODUCTION function | 52 | 0.02924 |

Holdout 1 stored no tracking at all, so its 31 documents took the `None` path already and
the change cannot reach them. The production-side row is measured with
`pdf_anchors._document_tracking_median` rather than the research probe's stored output, so
the two are independent measurements of the same quantity; one committed document
(`118-hr-9468/4_enrolled-bill`) yields `None` and fail-closes both before and after.

The clause census settles it directly: over **2869 boundaries** in the development corpus
and holdout 2, `C5b_no_tracking` fires **0 times** (`C2` 1591, `C6` 1222, `C4` 36, `C1` 11,
`C5` 9). The branch is unreachable on all validated data, the change is monotonic toward
the primary invariant, and no validated number moves.

`test_a_negative_document_median_declines` is the negative control: a near-full even-small-caps
boundary at upper tracking `-0.04` against a median of `-0.03`, which the previous form
JOINs and the corrected form SPLITs. It was written first and confirmed red against the
unfixed parser before the fix landed.

**Production still reproduces the frozen rule.** Both the specification and the parser were
corrected together and the digest re-frozen
(`74813bc5f66e1787b4a3c0e5b1578f5f74dcefdf29264f52a2792904892083e1`). Driving
`frozen_candidate4.decide()` and `pdf_anchors._account_boundary_splits()` from the same
stored run/typography/tracking data gives **2869 boundaries, 0 disagreements**. That
harness is itself controlled: flipping production's `C4` fullness comparison produces
exactly 36 mismatches, matching `C4`'s census count, and restoring returns it to 0 — so a
clean result is evidence rather than a harness that cannot fail.

### Production reproduces the frozen rule

The check that matters, and the one an implementation can silently fail: for **89
documents** across the corpus and both holdouts, every account name the frozen
specification predicts from the stored run/typography/tracking data is emitted by the
production parser. **8814 predicted names, 0 divergences.** What ships is what was
validated.

### One property that preserved the existing suites

On geometry-less input every boundary takes the fail-closed branch, so the rule degenerates
exactly to the pre-#524 behaviour: account = the run's last line, container = the rest.
That is why the synthetic size-detection suites needed no rewriting, and
`test_geometryless_input_reproduces_the_pre_524_behaviour` pins it rather than leaving it
as a happy accident.

### Baselines re-derived, each delta explained

**Anchor goldens.** `118-hr-8282` and `118-hr-8752` are **unchanged** — the controls.
`118-s-4795` moves 212 → 208. Twelve anchors removed, eight added; eleven of the twelve
removed are fragments absent from the XML (`SETTLEMENT COMMISSION`, `RESTORATION`,
`CORPORATION`, …) and seven of the eight added are confirmed XML headings
(`SALARIES AND EXPENSES, FOREIGN CLAIMS SETTLEMENT COMMISSION`, …).

Two deltas needed individual explanation rather than a set-level pass:

- The removed `account CONSTRUCTION` looked like a real heading disappearing. It is a
  name-recurrence artifact: three anchors carried that name, two are genuine standalone
  accounts and survive; the removed one was the fragment of
  `MAJOR RESEARCH EQUIPMENT AND FACILITIES CONSTRUCTION`, now emitted whole.
- The added `agency STATE AND LOCAL LAW ENFORCEMENT ACTIVITIES OFFICE ON VIOLENCE AGAINST
  WOMEN` is a container anchor where shipped emitted none, because shipped's join ended on
  "AND" and the dangle guard suppressed it. Only the second half is an oracle-established
  container, so the merge is not adjudicable as a fabrication. Measured corpus-wide over
  all 89 documents, agency anchors merging two *oracle-established* containers are
  **1 under shipped and 1 under candidate 4** — the same instance. The change does not
  make the one-agency-per-leaf shape reachable more often.

**Canonical baseline.** Twelve of twenty-seven cases move; fifteen are unchanged. The
aggregate justification is §4's 10B/10C: every hunk delta is fragment → complete heading,
and across the seventeen accepted pairs canonical moves go 165 → 157 with false-fragment
`Renumbered` cards 21 → 8, with no change to `_pdf_move`.

### Scope actually touched

`pdf_text.py` gains a `LineTypography` record (size histogram, tracking, gap count) filled
from the existing char walk, and a `typography` field on `Line`. No structural semantics.
`pdf_anchors.py` gains `_caps_per_word`, `_document_tracking_median`,
`_account_boundary_splits`, `_account_segment_start`, and the account leaf now emits the
run's last **segment**. `_is_line_fullness_break` is deliberately **not** reused: it
carries the major band's 4 pt slack guard and a keep-joined default on missing geometry,
both wrong here, and sharing it would couple two bands' tuning.

Untouched: `_block_key`, `CandidateSet`, correspondence evidence, assignment, move
thresholds, `_pdf_move`, grouping-header detection, `_major_anchors_by_size`, `#170`.
`pdf_parser_revision()` moves, which is correct — what an observation *is* changed.
