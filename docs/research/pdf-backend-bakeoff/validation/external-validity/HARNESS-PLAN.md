# Downstream harness — contract and dependency plan

**Status: `build_frames.py` is BUILT (A31, DEVELOPMENT slice). The other four components are
PLAN ONLY.** Nothing here is frozen protocol; it is a mapping of already-frozen rules onto
executable contracts. Where the frozen rules do not determine an outcome-affecting choice, the
ambiguity is surfaced in §7 rather than resolved.

Frozen inputs this plan assumes, all approved: A19 (neutral skeleton, 8-line regions,
withdrawn C-frame enrichment), A20 (M6 deferred, RQ2 narrowed), A21–A24 (`sci` vs `ngid`,
Model G, text vs segmentation discordance, M0 risk set), A25 (X2-b boundary counterfactual),
A5 + A10 (Rule 1 and the adjudication budget), **A27** (matching key, C-frame
reservation removed, region-based D-frame budget, Rule 0 outcomes, §8 owner, Rule 3 gate
vector, frozen determinism), and **A30** (the occurrence key's fourth component is the
absolute `start_ngid`; the oracle's occurrence position is geometric; P-head adequacy and
realized blind-ID uniqueness are executable).

**Every frozen methodology section has an owner** — §4.5 `decide_architecture` (**resolved by
A28.1/A28.2, executable since A30.4**); §5.3–5.4 `build_oracle`; §5.5.1 + §5.8 `build_frames` (frames) and
`decide_architecture` (budget); §5.6 `adjudicator_prompt` + `build_oracle`; §5.7
`build_oracle`; §6 `score_metrics`; §7 `decide_architecture`; §8 `score_metrics`.

---

## 1. Dependency order

```
        run_hybrid ──┐
                     ├──► build_frames ──► build_oracle ──► [HUMAN / AI adjudication]
        run_extended ┘         │                                      │
                               │                                      ▼
                               └──────────────────────────────► score_metrics
                                                                      │
                                                                      ▼
                                                            decide_architecture
```

`adjudicator_prompt.md` is an input to `build_oracle`, not a stage. It must be committed
before any oracle artifact is produced, because it is part of what determines a label.

**Build order: `build_frames` → `adjudicator_prompt` → `build_oracle` → `score_metrics` →
`decide_architecture`.** Each stage's output is a committed JSON artifact, so a later stage
never re-derives an earlier stage's decisions.

---

## 2. `build_frames.py` — **BUILT (A31)**

Implemented and tested on SYNTHETIC + DEVELOPMENT material only; evidence in
`results/x17_build_frames.json`, **56/56 controls passing**. No canonical `results/frames.json`
exists. The D-frame is emitted as a **complete census** — the A10/A27.3 budget is not applied
here. Anchor equality uses the **whole emitted production `Anchor` value**; no reduced
signature was invented. No runner instrumentation was added: each arm's anchors come from the
`Page` it already returns, exactly as `x14` does.

**Implements:** §5.8 (two frames, never pooled), A19 (neutral skeleton, 8-line regions,
enrichment withdrawn), A22/A23 (D-frame = union of text / segmentation / anchor discordance),
A23 (M0 comparative risk set).

| | |
|---|---|
| **inputs** | holdout PDF paths + `holdout_membership.json`; `run_hybrid.run`, `run_extended.run` |
| **outputs** | `results/frames.json`: per document → per page → neutral lines (`key`, `baseline`, bbox, `gids`), regions (8 consecutive neutral lines, page-bounded), per-neutral-line `line_state`, per-region C/D membership with the reason each entered |

**Permitted decisions:** JSON layout only. The C-frame draw is **not** a free choice: A27.7
fixes it as `rank by sha256("cframe-select|20260807|(doc_sha256,page,region_ordinal)")`,
first ≤ 8 per document.

**Must NOT decide:** which lines are neutral (that is `eligible` + `cluster`, frozen);
region size or alignment; any use of text to form a region; any enrichment predicate
(withdrawn by A19); **any amount-bearing reservation (REMOVED by A27.2)**; whether a
jointly-absent line enters the D-frame (it does not); the selection seed or ranking rule.

### Invariants

- **I1** C-frame regions are enumerated from the **neutral skeleton only**. Enumerating from
  emitted lines would make a jointly-dropped line unsamplable and a shared failure invisible.
- **I2** the skeleton is byte-identical under both arms (`x13` already asserts this).
- **I3** `BOTH_ABSENT` lines are in the region grid and in `frames.json`, are **excluded**
  from the M0 risk set, and **cannot alone** put a region in the D-frame.
- **I4** a D-frame region records the predicate(s) that caused **the region** to enter, and
  separately the specific neutral lines that were discordant. A non-discordant line inside a
  D-frame region must never be recorded as individually qualifying — the region is the
  membership unit, the line is the evidence.
- **I5** regions never cross pages.

### Controls

| control | what fact makes it fail |
|---|---|
| skeleton identity H vs X | any page where the two runners' `(key, gids)` lists differ |
| region partition is total | a neutral line belonging to zero or ≥2 regions |
| synthetic jointly-dropped body line | it fails to appear in any C-frame-eligible region |
| synthetic chrome-only page | any of its lines enters the D-frame |
| **negative:** injected merge/split on one arm | that region does **not** enter the D-frame |
| **negative:** injected text change on one arm | that region does **not** enter the D-frame |
| **negative:** anchor set differs, text identical | that region does **not** enter the D-frame |
| **negative:** a concordant line inside a D-frame region | it is recorded as individually qualifying (I4) |
| determinism | the same commit + inputs select a different C-frame set or order |

---

## 3. `adjudicator_prompt.md`

**Implements:** §5.4 (the adjudicator sees only the region), §5.5.1 (human for D-frame),
§5.6 (negative controls indistinguishable), A20 (RQ2 narrowed).

**Must contain:** the task, the region image, and nothing else identifying an architecture.
**Must NOT contain:** any H or X text, any architecture name, any hint that a region is a
control, or any question about amount→account attribution (M6 is deferred; asking would
collect data the study may not use and could bias heading answers).

**Asked for:** heading occurrences present, their exact printed text, their immediate parent,
a coarse leaf/container role, and — per **A30.3** — **enough source position to name the
occurrence key**: `start_physical_line`, and `start_x_px`, the integer horizontal coordinate
of the **left edge of the first printed character** of that occurrence in the rendered
stimulus. Nothing else.

`start_x_px` is an **identity annotation only** — text, role and parent stay independently
adjudicated. It replaces A27.1's "order on that line", which could not be derived: an ordinal
renumbers a later occurrence whenever an earlier one on the same line is missing, and
production emits a `section` and an inline `subsection` at the same `(page, line)`. The R1
repeat records its **own** `start_x_px` and is resolved independently.

| control | what fact makes it fail |
|---|---|
| prompt contains no architecture output | a grep for H/X text or arm names hits |
| N-A altered-PDF region | the adjudicator transcribes the unaltered text, i.e. cannot see the failure class → M2/M3 void |
| N-C heading-free region | a heading is reported → precision claims void |
| R1 repeat at a different scale | heading-text agreement < 0.90 → text metrics void |

---

## 4. `build_oracle.py`

**Implements:** §5.4, §5.7 (provenance), §5.6 (controls shuffled in), A19 (regions are
neutral), A24.2 (region bbox comes from the skeleton, which now excludes U+0020).

| | |
|---|---|
| **inputs** | `frames.json`; the PDFs; `adjudicator_prompt.md` |
| **outputs** | two artifacts with deliberately different contents, below |

**`results/oracle_key.json`** — committed **before** adjudication, then **not opened by the
adjudicator**:

```
opaque blind id ->
    canonical stimulus identity        (A28.3, pre-blinding)
    document_sha256
    page_number
    region_ordinal
    stratum
    frame                              C | D
    control / repeat bookkeeping       control_kind, control_variant, r1 base identity
    every H/X architecture output needed for the later join
    renderer name + version, DPI, bbox in PDF points, PNG sha256
```

**The adjudicator-facing blind artifact** carries **only** what the frozen blinding protocol
permits: the **opaque id**, the **rendered image**, and the **question / codebook**. It must
never carry architecture output, frame, stratum, document identity, or control status.

**Permitted decisions: NONE that affect an outcome.** Render scale is frozen by A28.4 —
**300 DPI** primary, **330 DPI** for the R1 repeat, same bbox and source region, raster scale
the only difference. Selection and ordering are frozen by A27.7 as amended by A28.3: the
`cframe-audit` and `r1-repeat` draws rank canonical **base** stimulus identities and
`blind-order` ranks canonical **final instance** identities. **No ranking may consume a blind
id.** The blind id is derived only after selection is settled and is an adjudicator-facing
alias only.

**Must NOT:** render from any architecture's text; let a region's H/X content influence
cropping; reveal control status; write the key after adjudication has begun.

### Invariants

- **I6** the renderer reads **PDF geometry only**. No arm's text reaches it.
- **I7** every stimulus carries its PNG sha256, so a later re-render is *detected*.
- **I8** `oracle_key.json` is committed strictly before `oracle_adjudicated.json` exists
  (F6 already checks this ordering by git).
- **I14** (A30.5) **blind ids are unique over the COMPLETE REALIZED stimulus set**, asserted
  before any oracle artifact is committed and before adjudication begins. A collision is a
  deterministic **build failure requiring review** — never an overwrite, a merge, a
  last-write-wins, or an automatic salt/re-roll. Salting after seeing the stimulus set would
  let the set choose the alias scheme, the influence A28.3 removed.
- **I15** (A30.3, **conversion clause superseded by A33**) the adjudicated `start_x_px` is
  converted to page PDF coordinates by the **measured MuPDF transform**:

  ```
  s = DPI / 72
  ε = 0.001 px            # measured MuPDF (fz_round_rect) device-rectangle constant, A34
  device_x0 = floor(bbox_x0 * s + ε)
  pdf_x     = (device_x0 + start_x_px) / s
  ```

  **A34 corrects A33's epsilon-free spelling.** Without `ε`, `device_x0` is a whole pixel low
  whenever `bbox_x0 * s` lands within 0.001 px below an integer — measured directly against
  MuPDF at both scales, with the boundary bracketed either side. Width validation uses the
  symmetric form `ceil(bbox_x1*s − ε) − floor(bbox_x0*s + ε)`. `ε` is a **renderer constant,
  not a tolerance**: the nearest-x resolver never consults it.

  **`image_width` is not the scale and is not required by the inversion** — A30.3's original
  "bbox + image width + DPI" wording described a linear map across the bbox, which `x20`
  measured is not what the renderer does. Everything else in I15 stands: the result is resolved
  to the **nearest neutral ink glyph** on the reported physical line, **no tolerance**, an exact
  tie or an absent candidate yields `UNMATCHED`, and the skeleton supplies **identity only**,
  never heading truth.
- **I16** (A33) the region bbox is the **minimal union of the committed neutral-line bboxes,
  zero padding**, read from the frame and never re-derived from the PDF. Geometry that is
  missing, non-finite, non-positive (per line **or** per region), or that extends past the page
  is **refused** — never clipped, intersected or padded.
- **I17** (A33) a source page with **non-zero rotation** is non-executable: it **aborts** oracle
  construction. It may never skip the page, skip the region, drop the stimulus, or reduce a
  denominator — each of those would turn an unrepresentable condition into a quietly smaller
  study, invisible precisely because the affected pages stop being counted.

| control | what fact makes it fail |
|---|---|
| re-render determinism | same region renders to a different PNG hash |
| scale | a primary is not 300 DPI, or an R1 repeat is not 330 DPI, or the repeat's bbox differs from its primary, or either is rescaled afterwards |
| **negative:** blind-id scheme swapped | any selected item or presentation rank changes (A28.3) |
| **negative:** blind artifact leakage | a grep of the adjudicator file finds frame, stratum, document id, control status or arm text |
| bbox ↔ skeleton agreement | a rendered crop omits a neutral line the region claims |
| **negative:** shuffle the key | adjudications still align to the right regions (would prove the key is not load-bearing, i.e. the join is fake) |
| **negative:** injected blind-ID collision | the build completes instead of aborting (I14) |
| **negative:** exact geometric tie for `start_x_px` | a glyph is chosen instead of `UNMATCHED` (I15) |
| R1 start identity | a repeat reuses the primary's coordinate or resolved identity rather than resolving its own |

---

## 5. `score_metrics.py`

**Implements:** §6 (M0–M9 minus M6), A19 (denominators), A20 (RQ2 narrowed), A22/A23 (M0
components, risk set, D-frame), A3/A4 + `m3_boundaries` (M3), §5.8 cross-engine control,
A24.2 reporting.

| | |
|---|---|
| **inputs** | `frames.json`, `oracle_adjudicated.json`, `oracle_key.json`, `x09` cross-engine result |
| **also owns** | the **§8 statistical contract** (A27.5) |
| **outputs** | `results/metrics.json`: M0a/M0b/M0-any/M0c + raw components, M1–M5, M7, M9, per-document and pooled, each with its content-bearing denominator and any `PDFIUM-CONDITIONED FRAME` label |

### The M0 block, exactly

```
risk set      neutral lines with state != BOTH_ABSENT
M0a           |TEXT_DISCORDANCE|            / |risk set|
M0b           |SEGMENTATION_DISCORDANCE|    / |risk set|
M0-any        union, never a sum            / |risk set|
M0b_defined   lines where SEGMENTATION_DEFINED (C(N) non-empty)
M0b_rate_on_defined  |SEGMENTATION_DISCORDANCE| / |M0b_defined|
M0c           |regions with ANCHOR_DISCORDANCE| / |regions|   -- never pooled with the above
both_absent   raw count, reported, never in a denominator
```

**Reporting rule carried forward from the A23 review:** `M0b_segmentation_rate` is over the
full risk set; only `M0b_rate_on_defined` may be described as "the fraction of comparable
groupings that disagree". `score_metrics` must emit both and must not emit a single "M0b".

### The §8 block (A27.5)

```
event          per DOCUMENT: "has >= 1 heading-level H/X discordance"
estimand       pi = P(a document from the target population shows that event)
bound          exact one-sided 95% Clopper-Pearson upper bound on pi, unit = DOCUMENT
zero events    closed form 1 - 0.05**(1/N); NO bootstrap (degenerate, measured in 8.1)
non-zero       bootstrap permitted, reported alongside
paired         per-document paired differences; UNWEIGHTED mean over documents;
               per-document detail is mandatory, never collapsed to one number
forbidden      any per-heading probability, any heading-as-iid-trial denominator
```

**Must NOT decide:** to pool M0c with the line rates; to weight the components into a
composite; to drop `both_absent` from the report; to let M3 read a segmentation label
(M3 consumes **projected text + oracle** only).

### Invariants

- **I9** every M0a/M0b discordant line's region is in the D-frame (same predicates decide
  both — no divergent eligibility sets).
- **I10** M1 recall's denominator is the **adjudicated** enumeration, never the emitted one.
- **I11** a metric whose content-bearing denominator is zero is reported `VACUOUS`, never as
  agreement.
- **I12** M9 is computed per document per architecture and can reject an arm outright (§7.2
  rule 0) before any other metric is consulted.
- **I13** cross-engine: a document below **0.95** (or any sampled page below **0.75**) labels
  **every RQ1 and RQ2 result computed on it** `PDFIUM-CONDITIONED FRAME`; failure on **more
  than ⅓** of sampled documents applies the qualification to **both** headlines. Never blocks.

| control | what fact makes it fail |
|---|---|
| S1 liveness (advances × 1.25) | M0 does **not** rise → the comparator is not live and M0 is not reportable |
| M3 weld/space fixture | `FAMILYHOUSING` vs `FAMILY HOUSING` does not reach M3 as `X_CORRECTS` |
| M3 insulation | a split-only difference fabricates a weld/split against a clean oracle |
| **negative:** delete agency anchors | M4 does **not** fall further than M1 |
| **negative:** shift heading baselines one line-height | M4 does **not** fall |
| **negative:** inject an `R E P O R T` page | M7 does **not** detect it |
| M0 denominator | a `BOTH_ABSENT` line appears in any M0 denominator |
| vacuity | a zero-denominator metric is printed as a rate |
| **§8 independence** | the bound computed on `N` documents equals the bound computed on `H` headings when `H != N` — i.e. headings were treated as iid trials. §8.1's own 0.1926 vs 0.00498 (39×) is the fixture |
| **§8 zero-event** | a bootstrap is reported at zero events, or the closed form is not `1 - 0.05**(1/N)` |
| **§8 pairing** | the paired mean is weighted by heading count instead of unweighted over documents |

---

## 6. `decide_architecture.py`

**Implements:** §7.2 rule 0 (M9), A5 rule 1 as amended by A20, A10 (budget), §7.2 rule 3.

**Rule 1 after A20 — choose X only if ALL hold, on a FULL census:**

```
1. X_CORRECTS   >= 5      heading occurrences
2. X_REGRESSES  == 0      heading occurrences
3. no heading whose immediate parent is correct under H and wrong under X   (M4)
   [the M6 condition is STRUCK by A20]
```

**Budget, per A10 as unit-fixed by A27.3:** the adjudication item is a **REGION**. Enumerate
the complete D-frame region census first. **≤ 60 regions** → adjudicate the full census and
Rule 1 may be evaluated. **> 60 regions** → Rule 1 cannot choose X; the outcome is
`INSUFFICIENT_COMPARATIVE_EVIDENCE`, and a 60-region sample is descriptive only. §5.8's
120-region clause is superseded; **Rule 1 never runs on a 60- or 120-region sample.**

**Rule 0 (M9) runs FIRST and has its own outcomes (A27.4):** `EXTENDED_BY_RULE_0_M9` when H
has an asymmetric M9 loss and X none; `HYBRID_BY_RULE_0_M9` for the mirror; and when **each**
arm has an asymmetric loss on different documents, **both are rejected** —
`INSUFFICIENT_COMPARATIVE_EVIDENCE`, with no invented comparison by count or severity.

**Rule 3 gate vector (A27.6), each an explicit inspectable status:** R1, N-A, N-B, N-C, S1,
confirmatory X2-a, confirmatory X2-b, M9 evaluability, §4.5 adequacy. Any failure →
`INSUFFICIENT_COMPARATIVE_EVIDENCE`. x09 is a **reporting qualification only**.

**Three outcomes, never collapsed:**

| outcome | meaning |
|---|---|
| `EXTENDED_BY_RULE_0_M9` | H lost a document's heading tree, X did not |
| `HYBRID_BY_RULE_0_M9` | X lost a document's heading tree, H did not |
| `EXTENDED_BY_RULE_1` | X met every condition on a full census |
| `HYBRID_BY_PRIOR` | the pre-stated architectural prior stands; comparative evidence did not overturn it |
| `INSUFFICIENT_COMPARATIVE_EVIDENCE` | Rule 1 could not be evaluated — census over budget, or a control failed |

**Must NOT:** write "H is more accurate" on an X failure. H survives **by prior**, only while
the study is valid and X fails its win conditions. The decider must emit the outcome enum and
a pre-committed sentence, and must refuse to emit any comparative-accuracy claim about H.

| control | what fact makes it fail |
|---|---|
| synthetic X win (6 corrects, 0 regressions, no M4 regression) | outcome is not `EXTENDED_BY_RULE_1` |
| synthetic 5 corrects **and 1 regression** | outcome is `EXTENDED_BY_RULE_1` (must be insufficient) |
| synthetic 5 corrects **and 1 M4 regression** | outcome is `EXTENDED_BY_RULE_1` |
| synthetic census of **61 regions** | outcome is anything other than `INSUFFICIENT_COMPARATIVE_EVIDENCE` |
| synthetic asymmetric M9 loss for H only | outcome is not `EXTENDED_BY_RULE_0_M9` |
| synthetic asymmetric M9 loss on BOTH arms, different documents | outcome is not `INSUFFICIENT_COMPARATIVE_EVIDENCE` (a severity comparison was invented) |
| any Rule 3 gate set to FAIL | outcome is not `INSUFFICIENT_COMPARATIVE_EVIDENCE` |
| x09 set to FAIL | the outcome changes at all (it must only add a label) |
| synthetic empty census | outcome is not `HYBRID_BY_PRIOR`, or the text claims H won empirically |
| **wording gate** | the rendered conclusion contains an empirical-superiority claim for H |
| M9 one-arm loss | the losing arm is not rejected outright before other metrics |

---

## 7. Ambiguity register

### RULED by A27 — no longer open

| was | ruling |
|---|---|
| 7.1 M1–M4 matching key | **A27.1** — source-position key; no text similarity, no order-within-region; unmappable → `UNMATCHED`. **Its fourth component is SUPERSEDED by A30.1** — see below |
| 7.2 40 % amount reservation | **A27.2** — REMOVED; plain uniform C-frame, ≤ 8 regions/document |
| 7.3 60 items vs 120 regions | **A27.3** — the item is a **region**; full census enumerated first; ≤ 60 → adjudicate all, Rule 1 evaluable; > 60 → `INSUFFICIENT_COMPARATIVE_EVIDENCE`, sample descriptive only |

### RESOLVED by measurement — 7.4 anchor→neutral bridge

**Proven, not argued** (`x14_anchor_bridge.py`, `results/x14_anchor_bridge.json`):

```
Anchor(page_number, line_number)   <- line_number is the GPO PRINTED margin number
  -> the unique index i in Page.print_lines carrying that margin number
  -> run_hybrid.emitted_lines(...)[i]    same index, equality re-asserted locally
  -> EmittedLine.cells -> ngid           neutral ink identity (A24.2)
  -> owning NeutralLine -> region ordinal
```

The bridge is **BILATERAL** (A28.5): the *same* refusing rule runs on both arms over the same
material, and both are asserted to bridge onto the *same* neutral skeleton.

| document | H placed / anchors | X placed / anchors | unplaceable |
|---|---:|---:|---|
| `114-hr-2029/4` | **11 / 11** | **11 / 11** | none |
| `118-s-4795/1` | **16 / 16** | **16 / 16** | none |

No heading text is consulted at any step. Four negative controls prove the bridge **refuses
rather than guesses**: a margin number appearing twice on a page → `AMBIGUOUS_MARGIN_NUMBER_ON_PAGE`;
a margin number on no print line → `NO_PRINT_LINE_WITH_THAT_MARGIN_NUMBER`; an emitted line
carrying no neutral ink → `EMITTED_LINE_CARRIES_NO_NEUTRAL_INK`; and a clean anchor places.

**No further instrumentation is required for `build_frames`.** `run_hybrid.run()` already
exposes `page` additively (A28.5), and `run_extended.run()` returns the same key, so each arm
hands back its own production `Page` objects carrying `print_lines` and `merge_ranges`.
`build_frames` derives each arm's production anchors by calling `extract_anchors` on those
returned `Page` objects — **exactly as `x14` does** — so no `anchors` key is added to the
runner dict and no arm has a private path. The earlier proposal to add one is **withdrawn as
unnecessary**, not deferred.

**Anti-drift gate, still binding:** the index-for-index `print_lines` ↔ `emitted` assertion
must run over **every page the harness consumes**, not one example. `x14` and `x17` both
enforce it.

### RULED by A28 — §4.5 and the last two determinism holes

| was | ruling |
|---|---|
| §4.5 Gap A, whose occurrence count | **A28.1** — `|H_keys ∪ X_keys|` over A27.1 source-position keys; P-head only; `account`/`agency`/`grouping` only; both-arms counts once; no text, no oracle |
| §4.5 Gap B, non-exhaustive/overlapping rows | **A28.2** — ordered exhaustive state machine, thresholds unchanged; `LIMITED` does **not** fail Rule 3 |
| blind ids could steer sampling | **A28.3** — canonical pre-blinding identities are ranked; the blind id is a post-selection alias only |
| render DPI was an implementation choice | **A28.4** — 300 DPI primary, 330 DPI R1 repeat, same bbox |

### RULED by A30 — the occurrence identity, proven derivable

| was | ruling |
|---|---|
| A27.1's `occurrence_ordinal_on_that_line` was never derived | **A30.1** — the fourth component is the absolute **`start_ngid`**, the A24.2 ink identity of the occurrence's first neutral-ink character. Used for **equality only**; nothing orders occurrences by it |
| could production supply it? | **A30.2** — yes. `Anchor` → merged-line start offset → `Page.merge_ranges` → print line + offset → `emitted[...].cells` → first cell carrying an `ngid`. Instrumented **study-locally**; production recognition unchanged; nine explicit refusal classes, all → `UNMATCHED` |
| how does the oracle name the same occurrence? | **A30.3** — geometrically: `start_physical_line` + `start_x_px`, resolved to the nearest neutral ink glyph with **no tolerance**; tie or no candidate → `UNMATCHED`. **A33 supersedes the conversion clause only**, as corrected by **A34**: `pdf_x = (floor(bbox_x0·DPI/72 + 0.001) + start_x_px) / (DPI/72)`, not a linear map across the bbox |
| §4.5 P-head was a caller obligation | **A30.4** — `filter_keys` now takes `(key, kind, population)` and applies both restrictions itself |
| blind-ID uniqueness was only synthetic | **A30.5** — asserted over the **realized** set; a collision aborts the build |

**Proven, not argued** (`x16_occurrence_identity.py`, `results/x16_occurrence_identity.json`):

```
instrumented mirror == production extract_anchors    every DEVELOPMENT page consumed
same-line collisions                                 7 lines, ALL section+subsection, H == X
cross-arm occurrence identity                        1249 shared, 1249 agree, 0 disagree
   of which the arms' TEXT disagreed                 30, identity agreed on all 30
refusals on development material                     none
key_H(B) == key_X(B) with A missing                  holds, and holds in the mirror
the REJECTED arm-local ordinal                       renumbers B 1 -> 0, so the control can fail
```

The `start_ngid` residue is stated rather than rounded off: ngid order agrees with printed
order on **33,592 of 33,602** emitted lines, the exceptions being single adjacent
transpositions in PDFium's text-page order. This is why A30.1 forbids *ordering* by `ngid`
and uses it for equality only; on the collisions themselves, ngid order matched printed
order **14/14**.

### Sweep for remaining delegated choices

§§4.5, 5.3–5.8, 6, 7 and 8 re-read for any surviving "permitted" or "seeded" phrase that
hands an outcome-affecting choice to future implementation. **Three hits, none open:**
`build_frames` permits "JSON layout only"; `build_oracle` permits "NONE that affect an
outcome"; §8's "bootstrap permitted" is the frozen rule itself (allowed only at non-zero
events). No further edge cases are manufactured.

> **Unresolved outcome-affecting ambiguities: ZERO.**

### 7.2 `X_CORRECTS` unit — *implementation-only, closed*

A3 fixes the M3 decision unit as the heading occurrence and Rule 1 counts heading
occurrences; they agree. `decide_architecture` counts `heading_outcome` results and never
boundary-level WELD/SPLIT tallies, which would inflate both counters. Recorded as a build
check, not an ambiguity.

---

## 8. Recommended implementation slice

**DONE (A31).** `build_frames.py` was the first slice — DEVELOPMENT material only, invariants
I1–I5, the nine planned controls plus three the review added (short trailing region kept,
region grid resets at every page boundary, a 61-region D census is not truncated) and five
more. It consumes only frozen, tested inputs (`run_hybrid` / `run_extended` — both already
exposing `page` — `neutral_identity`, `methodology_contracts`, and `extract_anchors` on each
arm's own returned `Page`).

**The next slice is NOT the oracle layer.** Before `adjudicator_prompt.md` or
`build_oracle.py`, A30.3's geometric annotation needs a DEVELOPMENT discriminability study:
real neutral-glyph `x0` separation at 300 DPI, pixel quantization, how ±1/±2/… px of
annotation error maps under the nearest-glyph / no-tolerance resolver, the frequency of
ambiguous or wrong resolution, and the same at 330 DPI for R1. That study must establish the
annotation is practically discriminable **before** human or AI adjudication begins.

Nothing downstream may start until `build_frames` and its controls are reviewed.
