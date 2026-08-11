# Methodology review — adversarial challenge to Study 1 and the Study 2 protocol

**Status:** Round 6 complete (+ follow-up closure); **human labeling stays gated.** This document is the deliverable that
`pass2-protocol.md` §10.1 gates on, extended to cover an independent adversarial review of Study 1.
**Date:** 2026-08-06, rounds 1–6. **Current machinery:** schema `pass2-anchor-v5`; oracles
`suggested-list` / `region-exhaustive` / `document-exhaustive`; observation identity
`(source_sha256, parser_commit, node_ordinal)`; global completeness requires coverage rule
`all-nodes` **and** a universe re-derived from the frozen parse; sampling frame
`probes/study2_frame.py`.
**Reviews:** `paper.md` (Study 1), `pass2-protocol.md` (Study 2), `probes/`, and — from round 2
onward — *this document and its own machinery*.
**Supersedes nothing.** It records what survived challenge, what did not, and what neither side saw.

Every claim below was tested against the code and the corpus rather than argued from the documents.
Where a criticism could be decided empirically, a probe decides it, and the probe is committed.
Failed falsification attempts are reported alongside successful ones.

**How to read this document.** It has six layers and the evolution is deliberately visible.

- **Round 1** (§"The eleven claims", §A–§E) is the original review. Its text is **unedited**.
  Where round 2 changed a conclusion, the round-1 section carries a **`↪ Round 2`** pointer and
  the reasoning lives in the round-2 section, not in a rewrite.
- **Round 2** (§R2) is a second adversarial review, which took this document as its target. Twelve
  criticisms; four hold as stated, six hold in part, and in two cases the attempt to falsify them
  succeeded. Two of the twelve overturn conclusions round 1 reported with more confidence than the
  evidence carried, and one of those — the cause of the label drift — inverts round 1's diagnosis.

- **Round 3** (§R3) is a third adversarial review, targeting rounds 1 and 2 together. Nine
  criticisms. It found that round 2's fixes were correct in direction and incomplete in three
  places that all share one shape: **a guard was built for one metric and the same defect was left
  running in the others.**

Round 2's own summary of what changed, in one paragraph: the three drifted observations did **not**
decay, and neither did the source; the parser's representation of byte-identical legislation
changed, which is a different defect with a different remedy (§R2-6). The headline comparison
between in-bill and cross-bill false-keep availability was constructed from three incompatible
quantities and had to be re-run; the direction survives in aggregate but not once the one bill
dominating it is removed (§R2-2). And the round-1 design's suggestion list still could not
establish whether a counterpart exists, which is now demonstrated on the corpus rather than argued
(§R2-1).

- **Round 4** (§R4) is a fourth adversarial review, targeting rounds 1–3 and specifically asking
  whether the new oracle and sampling machinery satisfies the rule it was built to enforce. Eleven
  criticisms. Its central question — *have we built independent ground truth and an independent
  sampling frame, or only renamed the last dependencies?* — was answered **renamed**, twice.

Round 3's summary: the anti-circularity guard protected candidate recall and left the other four
metrics consuming the same contaminated truth (§R3-2); `region-exhaustive` was treated as an
independent oracle when a bounded sweep cannot establish that no counterpart exists anywhere
(§R3-1); the evaluator identified nodes by their body text, and 33% of real documents contain two
provisions sharing one body (§R3-4); and the region-sampling design both broke its own sampling
frame and bought about a dozen independent observations rather than eighty (§R3-3).

Round 4's: **the sampling frame was still the matcher's output.** `probe_r10` built its anchors from
`diff_bills` and kept only `removed`/`moved` records, then measured that *those* anchors' regions
were matcher-independent — a true statement about the wrong population, and every design number
round 3 reported came from it (§R4-2). Separately, `document-search` granted "the counterpart set is
complete" on the strength of a reviewer having *searched*, which a reworded counterpart survives
(§R4-1); and the schema cited a measurement, "R9 §4", **that had never been committed** (§R4-3).
Correcting the frame changes the picture materially: the real frame is **29,530 anchors in 460
drawable regions across 12 bills**, not 2,137 in 36 across 4, so the constraint on Study 2 is
reviewer effort rather than the corpus.

---

## Read this first — the environment these results were produced in

**The corpus the probes read moved after Study 1 was written, and the probes did not move with it.**
Fixture-relocation #308 split the bill XML into two roots; `bills/` became the disposable working
tree. Measured today on `develop`:

| root | bills with XML | XML versions | bills with ≥2 versions |
|---|---:|---:|---:|
| `bills/` (what every Study 1 probe reads) | 20 | 71 | 13 |
| `tests/corpus/` | 31 | 58 | 12 |
| **union** | **34** | **106** | **18** |
| *`paper.md` §5 reports* | *31* | *102* | *17* |

So Study 1's probes, run today and unmodified, silently measure a corpus about a third smaller in
the multi-version bills every adjacent-pair number depends on. **Every number in this review was
produced on the union**, via a new `probes/corpus_roots.py`, which is a slight superset of Study 1's
corpus rather than a subset of it. Where a number here differs from `paper.md`, assume the corpus
difference is a contributing cause and re-check before treating the delta as a finding.

This caveat is load-bearing for the whole document, not a footnote: it invalidates any comparison
that pits a number in this review against a number in `paper.md` without re-running both.

---

## The finding neither the study nor the review raised

> **↪ Round 2 (§R2-6).** The word "decayed" throughout this section is wrong, and the round-2
> experiment says which link actually moved. The source XML is byte-identical to the file that
> entered git, and the parser *as of the answer-key commit* still reproduces all three stored texts
> from today's bytes (`probe_r7_provenance.py`). So the legislation did not change and the human
> judgments were never invalidated; the **parser's representation** changed, which re-segments the
> unit the judgment was about. Read this section as **representation drift**. The observable facts
> below all stand; the diagnosis and the remedy change.

Before the eleven claims, the result that changes the most: **Study 1's flagship case no longer
reproduces from the corpus, and re-deriving it inverts the paper's headline conclusion.**

The answer key stores `text_old`/`text_new` verbatim. That makes every probe that scores those
strings reproduce Study 1's numbers exactly and forever — including after the pipeline that produced
the strings has changed underneath them. It has changed.

`probe_r2_label_drift.py`, section 1: **3 of 12 labels no longer resolve to any node the current
parser emits** (`contested-2-corps-110`, `anchor-diff-sec252`, `extreme-alien-snap-10012`).

For Alien SNAP — the paper's Example A, its §6.2 unique win, and one of the two pairs the entire
"2-pair irreducible gain" rests on:

| | old side | new side | word-overlap | containment | §6.2 rule verdict |
|---|---:|---:|---:|---:|---|
| stored label (Study 1) | 81 chars | 2,242 | 0.078 | **1.000** | keep → correct |
| re-derived from today's parser | **1,443 chars** | 2,242 | 0.117 | **0.428** | split → **wrong** |

The 81-character stub exists in **no version** of 119-hr-1 under the current parser (verified across
all five — round 1 asserted this without a reproducer; `probe_r2` §4 now prints the per-version
provenance for all twelve labels, see §R2-7). Today's parser rolls the amendment's sub-paragraphs
into the section body, so the old side is already 1,443 characters and the stub→expansion signature
is gone. Containment 0.428 sits below the 0.70 keep bar, so the measure the study recommends
**would now false-split the case the study cites as its proof.**

And the production engine still gets it wrong today, for a different reason. `diff_bills` on
119-hr-1 v1→v2 emits at `sec. 10012`:

```
removed   old_len=1443   'Alien SNAP eligibility'
added     new_len=2242   'Alien SNAP eligibility'
moved     133 -> 133     'Emergency food assistance'  (correctly relocated to sec. 10013)
```

The two Alien SNAP nodes **carry identical headers**, and the v1 tree has a `match_path` collision
(two sections at `sec. 10012`). So on this pair, as it exists now: text containment fails, and header
equality would succeed. That is the exact opposite of the reading §7 builds on it. Note also that the
original labeler's own rationale said so — *"The identical section header ('Alien SNAP eligibility')
is the signal that would keep it linked"* — and the paper's §6.3/§7 framing did not carry that
forward.

**Scope discipline:** this is one pair, re-measured. It does not establish that structure beats text
in general. It does establish that the single exemplar the text-only reading leans on hardest no
longer supports it, and that Study 2 must re-derive its labels before calibrating anything.

**Independently confirmed by the repo's own regeneration path.** `scripts/build_similarity_labels.py`
re-derives every label's text from `tests/corpus/`, so it is the authority on whether the key still
rebuilds. It does not. Two defects, in order:

1. It is broken by the same #492 rename as the probes (`_MOVE_THRESHOLD`, `_SIMILARITY_THRESHOLD`,
   `_text_similarity`), so it exits on `ImportError` before doing anything. Unlike the probes it
   lives in `scripts/`, which *is* linted, and it still went unnoticed. **Fixed in this branch.**
2. Once it runs, it fails on the first drifted pair:

```
LookupError: modified ('corps of engineers—civil',
                       'general provisions—corps of engineers—civil', 'sec. 110') not found
```

That is `contested-2-corps-110`, one of the exact three pairs `probe_r2` independently flagged. The
cause is visible in `probe_r2` section 3: the engine no longer emits a `modified` record at that
path, it emits `added` + `removed`. So the drift is behavioural as well as textual.

**Three independent observations agree** — the stored text does not resolve to a node; the engine's
change type at that path has changed; and the fixture builder cannot rebuild the key. So the answer
key is currently **unregenerable**, and has been since at least the #492 refactor.

**Why nothing caught it.** `tests/test_similarity_labels.py` passes, and passing is consistent with
the key being decayed. Its own docstring says so: *"Self-contained: no `bills/` dependency."* It
scores `pair["text_old"]` — the frozen string — so it re-verifies that the stored text still gets the
stored score, which is true by construction and stays true forever. It is a threshold-regression
test, correctly, and it is not a drift guard. Nothing else was.

`pass2-protocol.md` §4 already has the right policy for this — a `text_sha256` mismatch quarantines a
pair for re-review rather than auto-refreezing. Two gaps: the policy was written for *future*
candidates and was never run against the *existing 12*, and the current fixture carries no
`text_sha256` field at all, so there is nothing for it to check.

---

## The eleven claims

### 1. The implemented "containment" may not be asymmetric

**Verdict: CONFIRMED as to the description. REJECTED as to the consequence.**

**Evidence.** Seven byte-identical copies of the measure exist across the probes
(`mine_common.py:45`, `probe_b1_tfidf.py:78`, `probe_b1_validate.py:67`, `probe_b2_multisignal.py:64`,
`probe_generalization.py:62`, `probe_consolidation.py:52`, `probe_review_gameability.py:78`). All
compute `sum(min(a[t],b[t])) / min(mass_a, mass_b)`. Both numerator and denominator are symmetric.
`probe_r1_containment_direction.py`:

```
max |contain(a,b) - contain(b,a)| over the 12 labeled pairs : 0.000e+00
max |contain(a,b) - contain(b,a)| over 20,000 random vectors : 0.000e+00
```

It is a **tf-idf-weighted overlap coefficient** (Szymkiewicz–Simpson), not a directional measure, and
**not a Tversky index for any fixed (α,β)**. Algebraically it is exactly `max(B, C)` — the maximum of
the two directional containments (`max |A − max(B,C)| = 0.000e+00`), because dividing by the smaller
mass yields the larger quotient.

Containment is **absent from production entirely** — `src/deltatrack/similarity.py` is word-overlap
only. This is a research-probe measure, so the mislabel has no runtime consequence today.

**The consequence does not follow.** `A ≡ B` on exactly the 7 of 12 pairs whose old side is lighter —
which is the definition of stub→expansion. Benchmarked on the same data (margin = min same − max
different; no threshold fitted):

| variant | margin | alone (resub) | §6.2 rule @ published cutoffs | 2-signal LOBO |
|---|---:|---:|---:|---:|
| **A current (min-side)** | **+0.440** | 12/12 | **12/12** | 11/12 |
| **B old-side (Tversky α=1, β=0)** | **+0.440** | 12/12 | **12/12** | 11/12 |
| C new-side (α=0, β=1) | −0.388 | 10/12 | — | 9/12 |
| D Tversky α=β=1 (Jaccard) | −0.206 | 10/12 | — | 9/12 |
| D Tversky α=β=0.5 (Dice) | −0.311 | 10/12 | — | 9/12 |
| D Tversky α=1, β=0.1 | −0.103 | 11/12 | — | 9/12 |

The genuinely directional measure reproduces the published 12/12 **identically**, and no swept
Tversky beats it. So the stub→expansion result **does not depend on directionality at all**, and the
property that produced the gain is not asymmetry — it is *normalising by the lighter side's rare-token
mass instead of by both sides*, which cosine does not do.

Where A and B differ, all three cases are `different`-labeled pairs and B scores **lower** (safer):
contested-3 0.365→0.202, contested-2 0.426→0.307, contested-1 0.439→0.346. Since `A = max(B,C) ≥ B`,
B is never more permissive. The 12 pairs cannot separate them; §6.4's 60 reverse-direction candidates
are where they would diverge operationally.

**Impact.** No measured result changes. The theory section is wrong in ~6 places.

**Action — wording correction, plus one implementation decision deferred.** Rewrite the theory around
the measured object. Do **not** switch to B on this evidence: the 12 pairs tie, and the case for B is
currently theoretical. Log it as a Study 4 comparison on the reverse-direction population.

Sites to correct: `paper.md` §Abstract ("a weighted Tversky index"), §3 Family A ("ask an asymmetric
question", the α/β parenthetical), §5 ("asymmetric"), Part 1 ("a one-directional question we call
containment"), footnote [^3]; `probe_b1_tfidf.py:13` docstring ("asymmetric, stub-friendly").

---

### 2. Pass 2's estimation population may be conditioned on the current matcher

**Verdict: CONFIRMED, and the protocol's own framing is already half-right.**

**Evidence.** `pass2-protocol.md` §3 defines it exactly as challenged: *"all matched-changed decisions
the current matcher produces (each `modified` node + each `removed`/`added` pair it considered as a
split candidate)"*. `move_candidates()` (`similarity.py:91`) only returns pairs at or above the
threshold, so a pair that never reaches it was never "considered" and cannot be sampled.

The size of the blind spot is measurable. On 119-hr-1 v3→v4 (`probe_consolidation.py`, current
corpus): 516 removed provisions survive the word-overlap move rescue with **0** re-pairable at ≥0.6.
Every true counterpart among those 516 is invisible to a sampler defined over considered pairs.

**What the population can legitimately support.** It is an unbiased sample of **the decisions the
current matcher emits**. From it you can honestly estimate: the precision of `modified` decisions, the
precision of `moved` decisions, and the error rate of the split/keep call *among pairs the matcher
paired*. Those are real, useful, staffer-visible quantities.

**What it cannot support.** Any recall statement, because the denominator (true counterparts) is not
sampled. So §3's *"This is the only unbiased source of a real-world precision/recall"* is wrong on the
recall half, and §7's "population precision-in-regime" is correctly named but sits in a population
that is itself matcher-conditioned.

The protocol's **challenge/estimation split (§1) survives fully** — it is the right distinction, and
it already anticipates most of this criticism. What is missing is a third thing: an *anchor-sampled*
set.

**Impact.** No Study 1 conclusion changes. Study 2 cannot claim recall as drafted.

**Action — protocol redesign (blocking).** Change the ground-truth unit from *decision* to *anchor*,
as the review proposes. Design in §B below.

---

### 3. The Study 1 generalization claim may be too strong

**Verdict: PARTLY CONFIRMED. The cross-type half is not supportable; the across-bills half is,
weakly, and is now further weakened by drift.**

**Evidence.** The answer key spans 4 bills, distributed **114-hr-2029: 1, 115-hr-5895: 4,
118-hr-4366: 6, 119-hr-1: 1**. So:

- **What LOBO demonstrates.** That the *containment values* stay separated when the rarity weights
  and the cutoff are refit without one bill. The paper states this correctly.
- **What it does not.** With 4 folds and this distribution, the 119-hr-1 fold tests on **exactly one
  pair**. A one-pair fold cannot estimate a generalization gap; it is a single Bernoulli draw.
- **Selection before LOBO.** §5 records that 6 of 12 were chosen *because the baseline misclassifies
  them*, and §8.3 already discounts the 6/12 for it. The measure, the two cutoffs, and the rule form
  were all chosen with all 12 pairs visible, so LOBO re-fits only the cutoffs — the *measure* choice
  is never held out. LOBO therefore bounds cutoff transfer, not method-selection overfitting.
- **The reconciliation evidence is one challenge exemplar, not a cross-type test.** It is a single
  pair (`extreme-alien-snap-10012`), deliberately selected as an extreme, from the one non-approps
  bill. And per the drift finding above, **that pair no longer reproduces**: its containment is 0.428
  today, not 1.000. So the sentence *"the measure generalizes across bills and across the
  appropriations→reconciliation boundary"* now rests on a data point that has inverted.

**Impact.** §6.5's "Reading" and the Part 1 bullet "the separation held up across the (few) bills we
could test — including one bill of a different type" both overstate. The Abstract's *"The measure
generalizes across the bills we tested"* is defensible for the 3 appropriations bills only.

**Action — wording correction (blocking, because Study 3 inherits it).** Justified wording:

> On the three appropriations bills with more than one labeled pair, rare-token containment's
> separation survives refitting the cutoff without any one bill. The corpus contains one
> reconciliation pair, selected as an extreme case; it is a single challenge exemplar and is not a
> cross-type generalization test. Cross-type generalization is untested.

---

### 4. The "full corpus census" may not validate accuracy

**Verdict: CONFIRMED.**

**Evidence.** `probe_b2_multisignal.py` collects `to_split` (base keeps, new rule splits) and
`to_keep` (base splits, new rule keeps) — pairs where the two rules **disagree**. `probe_b1_validate.py`
does the same with `new_splits`/`new_keeps` at a 0.55 bar. Neither reads any label; the corpus has no
exhaustive SAME/DIFFERENT truth.

- **Can they detect errors both methods make identically? No — by construction.** A pair where
  word-overlap and containment both say "keep" and both are wrong falls in neither bucket and is never
  printed. The census is structurally blind to shared error, which is the error class most likely to
  survive into production, since both measures are word-based.
- **Can they support "text carries most of the accuracy gain"? No.** That is a comparison against a
  structural alternative, and no head-to-head was run. `paper.md` Appendix A itself records that
  `probe_classifier.py` (structural-only) scores **12/12 on the same 12 pairs** — so the labeled set
  cannot separate text from structure at all. §6.3's own honesty note says the structural rescues are
  "asserted"; the Abstract and the §Scope "settled enough to build on" bullet then promote it to
  settled.

**Reclassification.** Of the corpus-level claims:

| claim | actual evidential status |
|---|---|
| "25 of 1,287 decisions change" | **directly measured** (a disagreement count) |
| "~19–20 clearly correct, ~3 wrong, ~2–3 borderline" | **human-inspected**, unblinded, single rater, n=25 |
| "containment's failure modes are real" | **human-inspected**, and independently corroborated (C7) |
| "text carries most of the accuracy gain" | **inferred**, and contradicted by structural-only 12/12 |
| "the corpus census validates the rule" | **not established** — it censuses disagreement, not correctness |

**Impact.** §6.2's "Corpus census" paragraph, the §Scope settled-bullet, and the Abstract's "the text
measure alone carries the gain" all need restating. The 25-change count itself stands.

**Action — wording correction + rename.** Call these **disagreement analyses**, not censuses. Demote
"text carries most of the gain" from *settled* to *not yet measured*, alongside the structural half it
is contrasted with — the honest statement is that **the labeled set cannot distinguish them.**

---

### 5. The IDF definition itself may create artifacts

**Verdict: REJECTED for the ranking. CONFIRMED for the calibration — which the paper already says.**

> **↪ Round 2 (§R2-5).** Scope correction: every score here is computed on the fixture's **frozen
> strings**, so as written this was a claim about historical observations. `probe_r5` §2b now
> repeats the analysis over only the nine pairs whose stored text still resolves in the current
> parse. Every margin is unchanged to three decimals, so the result does **not** rest on the three
> quarantined records — but the claim is now scoped by a probe rather than by assumption, and the
> five variants are frozen for re-running after re-adjudication.

**Evidence.** `probe_r5_idf_ablation.py`, five preregistered DF definitions over one held-constant
corpus (34 bills), measure and 0.70 bar held constant:

| variant | documents | max different | min same | margin | 0.70 bar still works |
|---|---:|---:|---:|---:|:--:|
| V1 per-version (Study 1) | 65,502 | 0.526 | 0.929 | **+0.404** | yes |
| V2 dedup bodies per bill | 37,959 | 0.529 | 0.929 | **+0.400** | yes |
| V3 one document per bill | **34** | 0.632 | 0.956 | **+0.324** | yes |
| V4 numerics dropped | 65,502 | 0.672 | 0.985 | **+0.313** | yes |
| V5 citations dropped | 65,502 | 0.488 | 0.915 | **+0.427** | yes |

**Every variant preserves the ordering and the keep bar**, including V3, which collapses the corpus
from 65,502 documents to 34 — an extreme stress that should break a fragile rarity model and does not.
So on this evidence rarity is acting robustly as identity evidence, and the headline separation is
**not** an artifact of one tokenizer or one corpus definition.

Two hypothesised effects ran backwards:

- **Citations do not dominate.** Removing them *improves* the margin (+0.427, the best of the five).
  On the 12 pairs, containment is not citation-carried. (This says nothing about the false-keep mode,
  which the 12 pairs structurally cannot test — §8.2 — and where C7 shows citations do matter.)
- **Numbers carry discriminative signal.** Dropping them is the *worst* variant (+0.313) and pushes
  `contested-5-ag-to-hhs` (different) to 0.672, within 0.03 of the keep bar.

**What is confirmed:** absolute values move by up to 0.24 across variants (contested-3: 0.377→0.618).
A cutoff fixed under one definition is not portable to another. That is `paper.md` §8.4 restated, and
it reinforces it.

One real artifact, found by C6 rather than the ablation: bodies that are a single token (literally
`"$0."`) score containment 1.000 against anything sharing that token. V4 is the only variant that
neutralises it. This is narrow but it lands in the financial stratum, so it matters (see C6).

**Impact.** Strengthens Study 1's measure claim; changes nothing about the cutoffs.

**Action — no change to the measure.** Record the ablation as a robustness result. Add a minimum-token
floor to the *financial* miner rather than changing the global tokenizer.

---

### 6. The financial-line miner may exclude severe false-splits

**Verdict: CONFIRMED for the discovery floor (severe, quantified). REJECTED in practice for the text
source, though the latent coupling is real.**

> **↪ Round 2 (§R2-3).** The 240 is a **discovery population**, not a set of known correspondences:
> removed financial provisions in a version pair that also has at least one added financial
> provision. Some correspond to nothing. So 84.6% is the share of that population the miner cannot
> reach — a fact about the sampling frame. How many are genuine missed correspondences is unknown
> until labeled. The methodological conclusion is unaffected. The PR description's "hides 203 of
> 240 **eligible cases**" overstated it and is corrected.

**Evidence — the floor.** `mine_financial_lines.py:53` sets `SPLIT_SIM = 0.50` and line 139 gates
candidate discovery on `_text_similarity(ro, an) >= SPLIT_SIM`. `probe_r3_financial_miner.py` over the
union corpus (71 adjacent version pairs):

```
removed financial nodes with >=1 added financial partner available : 240
  best word-overlap >= 0.5 -> miner CAN see them    :  37 (15.4%)
  best word-overlap <  0.5 -> miner CANNOT see them : 203 (84.6%)
Of the invisible ones, with a strong containment partner (>= 0.70): 40
```

**The floor removes 84.6% of the population from discovery**, and 40 of the excluded have a strong
independent-signal partner — the severe-false-split shape the stratum exists to sample. Tanker appears
directly in the invisible set (`118-hr-4366 word=0.48 contain=0.936 [maritime administration/tanker
security program]`), confirming the review's specific example. The exclusion is not incidental: the
miner filters on the *same quantity whose failure it is studying*, so the worse the false split, the
less likely it is to be sampled.

**Evidence — the text source.** Production reads `amount_source_old/new` (`diff_bill.py:689,736`); the
miner reads `old_text/new_text`. I tried to falsify the claim that this matters and **succeeded**:
over **67,983 change records, 0 disagree**. `NodeDiff` documents this as a deliberate no-op pinned by
`TestAmountSourceCorpusRegression`. So there is no current measurement error. The coupling is still
wrong — the fields exist because the renderings *did* diverge (#365), and nothing pins the *miner* the
way the engine is pinned — but it is a latent-defect finding, not an active one.

**Impact.** The financial stratum as mined is not fit for its stated purpose. `pass2-protocol.md` §0's
"34 found, mostly 119-hr-1" is a count of what survived the floor, not of what exists.

**Action — implementation change (blocking, before any financial labeling).**
1. Make discovery signal-independent: retrieve candidates by **union** of word-overlap, containment,
   and same-account structural path; record which retriever(s) found each. Never gate discovery on the
   measure under evaluation.
2. Read `amount_source_old/new`, matching production.
3. Add a minimum-token floor so single-token bodies (`"$0."`) cannot reach containment 1.0.
4. Re-mine and re-report the population; the current 34/80 split numbers do not survive.

---

### 7. Cross-bill high-containment negatives may prove vulnerability but not prevalence

**Verdict: CONFIRMED on the logic — and the direction of the error is the opposite of the one
implied.**

> **↪ Round 2 (§R2-2). The "opposite direction" conclusion was not established by the evidence
> below.** The two numbers in the table differ in three ways at once — per-comparison vs
> per-anchor, unmatched candidate-set size, and (unnoticed by either round) **two different rarity
> models**. `probe_r6_rate_parity.py` re-runs it with all three held constant. The direction does
> survive in aggregate: 0.412% vs 0.054% per comparison, CIs disjoint. It does **not** survive
> removing 119-hr-1, which supplies 24 of the 27 hits: 0.592% [0.271, 1.285] vs 0.281%
> [0.217, 0.364], overlapping. And "0/976" was never evidence of a low cross-bill rate — at the
> measured control rate, 976 draws expect 0.53 hits, so zero is the likeliest single outcome.
> Cite §R2-2's numbers, not this table's.

**Evidence.** The construction is as described: `probe_review_gameability.py` and
`mine_high_containment_different.py` pair a short provision in bill A against a long one in bill B.
Production never does this — a move candidate is drawn only from the removed/added sets of one
adjacent version pair of one bill. So the cross-bill rate is not an operational false-positive rate.
That much is straightforwardly right.

But running the **identical construction inside the production neighbourhood**
(`probe_r4_production_neighborhood.py`) inverts the expected relationship:

| construction | population | rate at containment ≥ 0.70 |
|---|---|---:|
| cross-bill random (existing probe) | 4,000 random short×long pairs | 10/4,000 = **0.2%** |
| cross-bill random, **cited** shorts | 976 pairs | **0/976 = 0.0%** |
| **production neighbourhood** | 77 short(cited) removed provisions | **27/77 = 35.1%** have ≥1 such partner |

The random cross-bill probe finds **zero** hits among cited shorts; its 10 hits are degenerate
boilerplate (`"For other joint items, as follows:"`, `"In this division:"`). Inside one bill, where
drafting vocabulary, account names and statute targets are shared, **rare-token coincidence is far
more likely, not less.** The cross-bill mine is therefore an *easier* case than production, not a
worst case.

The `~1,330 pairs corpus-wide` figure (`pass2-protocol.md` §0) is a **count produced by targeted
blocked search over `bills_corpus`**, not a rate and not a sample. It supports "the failure mode
exists and is findable at scale". It supports nothing about frequency.

**Caveat, stated because it bounds the conclusion.** The 27/77 are **not labeled false keeps**. They
are pairs where a spurious keep is *available*. 119-hr-1 supplies 24 of the 27 and is the known
consolidation bill, where many will be genuine "absorbed into" relations. 118-hr-4366 supplies 3, and
those read as clear false keeps on inspection (`"None of the funds in this Act or any other Act shall
be used to enforce…"` matched to grant appropriations). Ruling these is exactly the labeling work.

**Impact.** The adversarial set stays, correctly characterised. The prevalence question was
unanswered and now has a first, unlabeled answer that raises rather than lowers concern.

**Action — keep the set, relabel the claim, adopt the new probe.** Describe the cross-bill mine as
*failure-existence / hard-negative mining*. Add `probe_r4` to the standing probe set and make the
production-neighbourhood pairs a labeled stratum — they are more operationally relevant than the
cross-bill ones.

---

### 8. Consolidation mining may be circular with respect to containment

**Verdict: CONFIRMED, quantified.**

**Evidence.** `mine_consolidation.py:73-82` computes, for each removed provision, its best added
target **by containment**, then keeps it only if `c >= 0.70 and wr < 0.60`. So a candidate must be
retrieved by containment to exist, and the label set can only ever answer *"among consolidation
candidates containment retrieved, which are genuine?"* — precision among retrieved. Two further
narrowings compound it: only the single **argmax** target is emitted (a genuine many-to-one whose true
target is not the argmax is lost), and `wr < 0.60` removes anything word-overlap already caught.

The blind spot has a size. On 119-hr-1 v3→v4 (`probe_consolidation.py`, current corpus): **516**
leftover removed provisions, of which containment recovers **271**. The other **245 (47.5%)** are
unobservable to any label set built this way. Consolidation **recall is not estimable** from the
current design — only precision-among-retrieved.

> **↪ Round 2 (§R2-4).** Stated exactly: those 245 are **excluded from the annotation
> population**, not 245 known consolidation relationships. Some correspond to nothing. The
> sentence above already says "unobservable to any label set built this way", which is the correct
> framing and survives; the PR description's "makes 47.5% **of relationships** unobservable" does
> not, and is corrected. The conclusion — no denominator, so no recall — is unchanged either way,
> because it follows from the exclusion alone.

**Impact.** `pass2-protocol.md` §9.1's acceptance criterion ("≥25 consolidation") can be met while
recall stays unmeasured. §7's consolidation numbers are precision-like only.

Note also that the §6.4 figures have drifted with the parser: paper reports 493 removed / 265
recovered / 74 one-to-one / 41 many-to-one / 88 reverse; current run gives **516 / 271 / 66 / 42 / 60**.

**Action — bounded exhaustive annotation (blocking for any consolidation recall claim).** Do not
enlarge the whole stratum. Take **one bounded subtree** of 119-hr-1 v3→v4 (one committee/title with
roughly 30–50 removed provisions) and annotate correspondence exhaustively: for each removed
provision, its counterpart(s) among all added provisions in that subtree, retrieved for the human by a
**union** of containment, word-overlap, and structural path so no single measure gates discovery.
That yields a genuine recall denominator at a cost of tens of items, not hundreds, and it is the only
way to state a consolidation recall number at all.

**Relationship vocabulary.** The evidence supports needing **one-to-one, one-to-many, many-to-one,
none, uncertain**. `many-to-many` is not yet evidenced in our corpus — do not add it speculatively.

---

### 9. Labelers may be score-blind but hypothesis-primed

**Verdict: PARTLY CONFIRMED — the priming is real, already disclosed, and its measurable harm is
bounded. The genuine defect is a different one: the label space has no escape hatch.**

**Evidence.** The blindness work is substantial and should be preserved: scores stripped
(`make_worklist.py`), stratum name never shown, one card at a time, forced rationale on medium/low
confidence, and an automated leak guard (`blindness.py`, `leaks_in`) tested by
`tests/test_pass2_labeler.py`. `make_form.py:37-50` confirms the stratum-conditional question:

- high-containment-different → *"Are these the same provision carried across versions, or two different provisions?"* → `same` / `different`
- financial-line → *"…same account/line (an amount edit of one line), or two different lines?"* → `same` / `different`
- consolidation → *"Is the OLD provision genuinely absorbed into the NEW section, or only coincidentally sharing a citation?"* → `genuinely-absorbed` / `coincidentally-contained`

`pass2-protocol.md` §5 already discloses this precisely, including that it is *correlated* framing
across the human and LLM labelers, and already floats a uniform question as a future simplification.
So this is a known, documented design choice, not a hidden bias.

**Why the harm is bounded.** §5's mapping folds `coincidentally-contained` into the false-keep
positive and `genuinely-absorbed` into "same", so the same/different metric is recoverable from the
consolidation labels regardless of the wording. All four decision standards are shown to every
reviewer, so the *concepts* are not stratum-private.

**The real defect.** The consolidation question is a **forced binary between two hypothesis-laden
options**. A candidate that is simply *unrelated* — neither absorbed nor sharing a citation — has no
correct answer, and the reviewer must file it under "coincidentally contained", which presupposes a
shared citation that may not exist. There is no `none`, no `unrelated`, and no `uncertain`
(`confidence: low` is a separate axis and does not mean "no answer fits"). Given C8, where the miner
retrieves by containment and 47.5% of relationships are unobservable anyway, a label space that cannot
express "no relationship" is the more consequential problem.

**Action — targeted UX change (blocking, small).** Do **not** restructure into a two-stage relationship
label on this evidence; the present same/different categories are adequate for the two same/different
strata and the change would cost the existing blindness guarantees. Instead:
1. Add `unrelated` and `uncertain` to the consolidation label space.
2. Adopt the uniform question §5 already proposes for the two same/different strata.
3. Keep everything else — the blindness machinery is the strongest part of this pipeline.

---

### 10. Check the literature inference about text-only success

**Verdict: PARTLY CONFIRMED. The citation is accurate; one inference drawn from it is not.**

**Evidence.** `paper.md` handles Kim et al. carefully in most places. §3 Family D explicitly offers
both readings and declines to resolve ("Two honest reads of that fact coexist… we flag it rather than
resolve it"), and footnote [^5] describes the work accurately (4,721 hand-labeled subsection pairs,
BERT/Legal-BERT, no positional features).

The overreach is in §3 Family A and §7, where Kim et al. is enlisted as one of "two data points [that]
cut against needing [structural confirmers] at all". That conflates two different propositions:

- **Supported:** semantic text models are viable for detecting relationships between legislative texts.
- **Not supported:** structural context has no marginal value for DeltaTrack's cross-version
  provision-identity problem.

They differ in task and in evidence type. Kim et al. classify *bill-pair similarity* on hand-labeled
subsection pairs; DeltaTrack must *resolve identity across consecutive versions of one bill*, where
the confusable negatives are boilerplate twins and reused section numbers inside the same document —
a population Kim et al.'s task does not contain. Absence of structural features in their model is
evidence that structure was **not necessary for their task**, not that it carries **no marginal
value** for ours. Establishing the latter requires an ablation on our data, which §7 itself concedes
has never been run.

The second "data point" — this study's own text-only 12/12 — is not independent evidence either, since
`probe_classifier.py`'s structural-only rule also scores 12/12 (see C4).

**Impact.** §7's "Two data points cut against needing them at all" does not hold. §3 Family D's
two-readings framing is fine and should be the model.

**Action — wording correction.** Replace the §7 sentence with: *Kim et al. establish that content
embeddings suffice for their bill-similarity task; they do not measure structure's marginal value for
cross-version identity, and neither do we. Our labeled set cannot separate the two, since a
structural-only rule also scores 12/12 on it.*

---

### 11. Reproducibility and research-state cleanup

**Verdict: CONFIRMED, worse than described. Repaired in this branch.**

**Evidence — the probes did not run at all.** Two independent breakages:

1. **Renamed imports (#492).** All 15 probe files hardcoded
   `Path("/Users/williamhea/Documents/Code/civictech/appropriations_bills")`, and 13 imported
   `_text_similarity` / `_MOVE_THRESHOLD` / `_SIMILARITY_THRESHOLD` from `deltatrack.diff_bill`. Those
   moved to `deltatrack.similarity` and lost their underscores. Verified as a **pure rename** (`git
   show 1d5836a`), so numbers reproduce once fixed.
2. **Corpus relocation (#308).** The probes read `bills/`; the curated fixtures moved to
   `tests/corpus/`. See the environment note at the top.

So `paper.md`'s *"Every number in Part 2 can be reproduced from the scripts named in Appendix A"* was
**false at review time** — none of them executed.

**Evidence — the breakage reaches outside the probes directory.**
`scripts/build_similarity_labels.py`, the answer key's regeneration path, is broken by the same
rename. That file is **not** ruff-excluded and is referenced by `tests/test_similarity_labels.py`'s
docstring as the way to re-freeze the fixture, and it still went unnoticed, because nothing runs it.
Fixed here; it now reaches its real failure (see the drift section above).

**Evidence — promised artifact missing.** `probes/eval_pass2.py`, promised by `pass2-protocol.md` §2.4
and load-bearing for §7, **does not exist**.

**Evidence — stale numbers.** Beyond the corpus table above: §6.4's consolidation figures (493/265/74/
41/88 vs current 516/271/66/42/60); `pass2-protocol.md` §0's "~1,330 pairs" (a targeted-search count
presented adjacent to rate language); §5's "64,276 provision bodies" (the union now yields 65,502, and
`mine_idf.py`'s own cache is built over a different, much larger pool — 232,924 bodies over 2,983
bills — so two rarity models coexist in one research program without the difference being stated).

**Repairs made in this branch** (mechanical only; no result rewritten):
- All 15 probes: absolute path → `Path(__file__).resolve().parents[4]`.
- 13 probes: renamed imports fixed.
- New `probes/corpus_roots.py` — union-corpus resolver + `merged_root()` symlink view, so probes read
  the whole corpus by changing one line.
- Verified no new lint: the 23 remaining ruff findings are pre-existing style in these
  deliberately-frozen scripts (12 E501, 5 E701, 3 E702, 2 F541, 1 I001); zero F401/F821.

**Action — remaining.** Write `eval_pass2.py` or delete the promise. Add a CI smoke test that
imports every probe, so the next rename fails loudly instead of silently. Mark superseded documents
explicitly rather than editing their conclusions.

---

## A. Revised statement of what Study 1 actually established

The strongest wording the evidence supports:

> On a 12-pair hand-labeled set drawn from four bills — six of them selected because the word-overlap
> baseline misclassifies them — a rare-token **weighted overlap coefficient** separates SAME from
> DIFFERENT with a margin of ~0.40, where word-overlap does not separate them at all and TF-IDF cosine
> misranks the stub→expansion cases. The separation is **robust to how rarity is defined**: five
> different document-frequency constructions, including one that collapses the corpus to 34 documents,
> all preserve the ordering and the 0.70 bar. It is **not robust as a calibration**: absolute values
> move by up to 0.24 across those same definitions, and leave-one-bill-out shows the cutoffs do not
> transfer.
>
> The measure is **symmetric** — a tf-idf-weighted overlap coefficient, exactly the maximum of the two
> directional containments — not the asymmetric Tversky index Study 1 describes. The property that
> produces the gain is normalising by the lighter side's rare-token mass; directionality is not
> required, and a genuinely directional variant reproduces every published result identically.
>
> Two claims Study 1 records as settled are **not established**. That "the text measure alone carries
> the accuracy gain" was never measured against a structural alternative, and cannot be: a
> structural-only rule also scores 12/12 on the same set. That the measure "generalizes across the
> appropriations→reconciliation boundary" rests on a single selected exemplar.
>
> **The labeled set has partly decayed.** Three of twelve pairs no longer correspond to any node the
> current parser emits. For the flagship stub→expansion case, re-deriving the pair from today's parser
> moves containment from 1.000 to 0.428 — below the keep bar — so the study's central exemplar now
> argues against the rule it was cited to support, while its identical section headers argue for the
> structural signal the study set aside.
>
> Containment's own false-keep mode is real, is untestable on this set, and is **more prevalent inside
> the production neighbourhood than in the cross-bill adversarial construction** used to demonstrate
> it: 35.1% of short cited removed provisions have a ≥0.70 partner available within their own bill
> version pair, against 0/976 for random cross-bill cited pairs.

> **↪ Round 2 (§R2-2)** replaces that last paragraph. The wording the evidence supports is:
>
> > Containment's own false-keep mode is real and is untestable on the 12-pair set. Holding the
> > anchor set, the rarity model and the candidate-set size constant, a spurious ≥0.70 partner is
> > available about **7.6× more often inside a bill than across bills** (0.412% vs 0.054% per
> > comparison, disjoint 95% CIs). That aggregate rests almost entirely on one bill: with 119-hr-1
> > removed the intervals overlap, and 119-hr-1 is the known consolidation bill, where a
> > high-containment pair is most likely to be a genuine "absorbed into" relation rather than an
> > error. So this is an **unlabeled opportunity rate**, and the direction is suggestive rather
> > than established. Cross-bill mining demonstrates that the failure mode exists; it does not
> > estimate operational prevalence, and neither does this until the pairs are ruled.

Unchanged and still sound: the problem framing (entity resolution over an ordered tree with an
unstable key), the signal inventory, the header-coverage table, that word-overlap measures the wrong
quantity, and the honesty apparatus in §8 — which anticipated more of this review than the review's
author expected.

---

## B. Revised Study 2 experimental design

> **↪ Round 2 (§R2-1, §R2-C).** The anchor unit survives and is right. The **candidate-union**
> mechanism below does not: a union of retrievers is still a retriever, so an anchor whose true
> counterpart every retriever misses is recorded as NONE and candidate recall computed from that
> dataset is 100% by construction. Measured on the corpus, the union@8 fails to show a
> header-identical candidate for **18.1%** of the anchors that have one
> (`probe_r8_oracle_gap.py`). §R2-C replaces this section's ground-truth mechanism with a
> region-exhaustive oracle and keeps everything else.

Keep the protocol's architecture. Its challenge/estimation separation (§1), by-bill splitting (§6),
blindness machinery (§5), and correlated-error caveat (§8) all survived challenge and are the strongest
parts. Three changes, then five clearly-separated evaluation targets.

### The unit changes from *decision* to *anchor*

Sample **provisions in version A**, not pairs the matcher produced. For each sampled anchor the human
records its counterpart(s) in version B — **including NONE and including MANY**. This is the only unit
from which recall is computable, and it makes every stage below measurable from one label set.

Candidates shown to the human are retrieved by a **union** of retrievers (structural path,
word-overlap, containment), with the retriever recorded per candidate and hidden from the labeler. No
single measure may gate discovery anywhere in Study 2 — that is the generalisation of the C6 and C8
defects.

### Five targets, never conflated

| # | target | question | population | metric |
|---|---|---|---|---|
| 1 | **candidate recall** | did the true counterpart enter the candidate set? | anchor sample | recall @ candidate-set |
| 2 | **ranking / scoring** | was the true counterpart preferred to false ones? | anchors with a true counterpart | top-1 accuracy, MRR |
| 3 | **assignment** | did the global matching pick the right correspondence? | anchors in collision groups | assignment accuracy |
| 4 | **final diff correctness** | did the staffer see the right modified/added/removed/moved? | anchor sample | per-anchor confusion matrix |
| 5 | **failure-mode existence** | does mode X occur, and how badly? | challenge strata | worst-case rate, **never a precision** |

Targets 1–4 are population estimates from the anchor sample. Target 5 is the challenge set and its
base rate is rigged by construction — the protocol §7 already says this and it must stay said.

### MVP cost

Deliberately small, because the point is to make the ruler honest, not large.

- **Anchor sample: 80 anchors.** Stratified by leaf level (account / section / subsection) and drawn
  proportionally across dev bills, with a separate held-out draw. Each anchor is one screen: the old
  provision, and ~8 union-retrieved candidates to accept, reject, or mark none/many.
- **Bounded consolidation subtree: ~40 anchors** in one committee subtree of 119-hr-1 v3→v4,
  annotated exhaustively (C8). This is the only recall denominator consolidation will have.
- **Financial stratum: re-mined** without the 0.50 floor (C6), then ~40 anchors.
- **Challenge strata: keep the existing pools**, re-characterised per C7, plus the
  production-neighbourhood pairs from `probe_r4` as a new and more operationally relevant stratum.

Roughly 160 labeled anchors, against the protocol's current ~150 pairs — comparable effort, and it
answers recall, which the current design cannot answer at any size.

### What stays exactly as drafted

By-bill splitting; scores stripped at label time with the automated leak guard; structural context
shown; per-stratum Cohen's kappa with support counts; the LLM as disagreement-flagger and reliability
screen but never a vote; Will's adjudication recorded before reading the LLM rationale; no silent caps.

---

## C. Blocking vs non-blocking

> **↪ Round 2 (§R2-E).** Superseded by the round-2 table. Three items move: the oracle design
> becomes a blocker in its own right, the evaluator moves from non-blocking to blocking (item 8
> below was wrong), and the drift item is restated as re-derivation plus quarantine rather than
> re-labeling. Items already done in round 2 are marked there.

**Blocking — must happen before any human labeling resumes**

1. **Re-derive the 12 existing labels against the current parser** and quarantine every drifted pair
   for re-review (protocol §4's own policy, never yet run on them). 3 of 12 are affected; one inverts.
2. **Re-mine the financial stratum** without the measure-dependent floor, reading
   `amount_source_old/new`, with a minimum-token floor (C6). The current pool is not fit for purpose.
3. **Switch the ground-truth unit to anchors** and freeze the five evaluation targets (C2, §B). This
   changes what the labelers are asked to do, so it cannot follow labeling.
4. **Add `unrelated` / `uncertain` to the consolidation label space** (C9) — small, and cheap only
   before labels exist.
5. **Correct the wording that would otherwise be laundered into Study 2's premises** (C1, C3, C4, C10)
   — specifically the asymmetry description, the cross-type generalization claim, "census", and "text
   carries the gain".

**Non-blocking — can wait**

6. Rewriting the theory section around the overlap coefficient (C1) — beyond the one-line correction.
7. Benchmarking directional-B against A on the reverse-direction population (C1) — Study 4.
8. `eval_pass2.py` (C11) — needed before *metrics*, not before labeling.
9. The probe-import CI smoke test (C11).
10. Superseded-document marking (C11).
11. Any decision about adopting structural confirmers (C4, C10) — Study 4, and now better motivated.

---

## D. New and changed reproducibility probes

All committed, all run from a normal checkout, all outputs quoted above.

| probe | decides | headline output |
|---|---|---|
| `corpus_roots.py` | *(infrastructure)* union-corpus resolver + merged view | 34 bills / 106 versions / 71 adjacent pairs |
| `probe_r1_containment_direction.py` | C1 | symmetry exact to 0.0; A ≡ max(B,C); A ≡ B on stub cases; 12/12 under both |
| `probe_r2_label_drift.py` | the drift finding | 3/12 labels unresolvable; Alien SNAP 1.000 → 0.428 |
| `probe_r3_financial_miner.py` | C6 | 203/240 (84.6%) invisible to the miner; 0/67,983 text-source disagreements |
| `probe_r4_production_neighborhood.py` | C7 | 27/77 (35.1%) in-bill vs 0/976 cross-bill cited |
| `probe_r5_idf_ablation.py` | C5 | all 5 rarity definitions preserve separation and the 0.70 bar |

Repaired (mechanical, no results rewritten): 15 probes de-hardcoded; 13 import-fixed.

---

## E. Documentation changes

Proposed, **not yet applied** — the review comes first, per the brief. History is preserved: nothing
is rewritten to look as though it was always right.

1. **`paper.md`** — add a dated **"Corrections after adversarial review (2026-08-06)"** block
   immediately after the Status header, linking here, carrying: the measure is a symmetric weighted
   overlap coefficient; the cross-type claim is one exemplar; "census" means disagreement analysis;
   "text carries the gain" is not established; and the Alien SNAP drift. Correct the six asymmetry
   sites in place with a footnote pointing at the block. Leave §6–§8's numbers standing with a note
   that they were computed on the pre-#308 corpus.
2. **`pass2-protocol.md`** — add a **§0b (2026-08-06)** update block in the same style as its existing
   §0: the anchor-unit change, the five evaluation targets, the financial re-mine, the consolidation
   subtree, and the label-space addition. Annotate §3's estimation-population definition inline rather
   than deleting it.
3. **`README.md`** — add `review-2026-08-methodology.md` to the contents table; add `corpus_roots.py`
   and the five `probe_r*` scripts to the reproduce section; fix the run instructions, which currently
   name a `PYTHONPATH=.` prefix and a `bills/`-only corpus that no longer hold.
4. **`methodology.md` / `spike.md`** — add a one-line header marking each as retained for research
   history and superseded by `paper.md` plus this review. Do not edit their conclusions.
5. **Memory** — `project_issue_56_similarity_thresholds` should record that the labels drifted and
   that labeling stays gated, so a future session does not resume from the stale premise.

---
---

# §R2 — Second adversarial review (round 2)

**Target: this document.** A second independent review put twelve criticisms to the round-1 review
itself, on the standard round 1 was held to: try to falsify each one against the code and the
corpus first, and only then act on it. Four hold as stated, six hold in part, and two attempts to
falsify succeeded well enough to leave the criticism materially narrower than it was put.

Two round-1 conclusions are overturned rather than refined, and both were overconfident in the same
way — a number was reported as evidence for a causal or comparative claim it could not carry.

**Failed falsification attempts are reported below alongside successful ones**, because the ones
that failed are what makes the surviving criticisms load-bearing.

| # | criticism | verdict | what changed |
|---|---|---|---|
| 1 | anchor truth still conditioned on retrieval | **CONFIRMED**, now measured | oracle redesigned; 18.1% gap demonstrated |
| 2 | 35.1% vs 0/976 has incompatible denominators | **CONFIRMED**, worse than stated | re-run; direction survives in aggregate only |
| 3 | financial 84.6% denominator | **PARTLY CONFIRMED** | restated literally; conclusion unchanged |
| 4 | consolidation 47.5% interpretation | **PARTLY CONFIRMED** (review text survives; PR text does not) | PR corrected |
| 5 | IDF robustness over-claimed | **PARTLY CONFIRMED**; bite falsified | scoped by probe; margins unchanged on the live 9 |
| 6 | "label decay" is the wrong model | **CONFIRMED**, and it inverts the diagnosis | parser drift, not decay; provenance schema |
| 7 | all-five-version claim had no reproducer | **CONFIRMED** | `probe_r2` §4, all twelve labels |
| 8 | evaluator must be blocking | **CONFIRMED** | schema + fixture + evaluator + tests built |
| 9 | `merged_root()` can go stale | **CONFIRMED** | content-addressed; tested both ways |
| 10 | corpus manifest missing | **CONFIRMED**, worse than stated | manifest + banner + committed snapshot |
| 11 | blocking list insufficient | **CONFIRMED** | §R2-E |
| 12 | do not adjudicate the drifted records | **ACCEPTED** | blind packet built, not adjudicated |

---

## §R2-1. Anchor ground truth is still conditioned on candidate generation

**Verdict: CONFIRMED. Attempted falsification failed, and the failure is quantified.**

**The criticism.** Round 1's §B shows the human ~8 candidates retrieved by a union of structural
path, word overlap and containment, and asks SAME / NONE / MANY. If all three retrievers miss the
true counterpart, the human answers NONE, the dataset records "no counterpart", and candidate
recall computed from that dataset is 100% by construction.

**Falsification attempted.** The criticism is unanswerable in principle — a union of retrievers is
a retriever — so the only way it could fail to matter is if the union were *effectively* exhaustive
in this corpus. `probe_r8_oracle_gap.py` tests that by holding out a fourth signal none of the
three uses: exact header-text equality between the anchor and a candidate. Over the union corpus:

```
removed provisions examined (anchors)                      : 1144
anchors with a header-identical `added` provision available:  243
of those, the union@8 does NOT show the header twin        :   44 (18.1%)
```

So for nearly one in five anchors that has an obviously relevant candidate, that candidate never
reaches the human. The examples are the expected shape — an anchor in a 747-provision neighbourhood
whose twin is ranked out by three retrievers that agree with each other. **This is a lower bound**:
a header twin need not be the true counterpart, and a true counterpart need not share a header, so
nothing here bounds the real hole from above.

**The distinction round 1 collapsed**, stated explicitly because the whole design turns on it:

| | candidate suggestions | the truth universe |
|---|---|---|
| purpose | make annotation fast | decide whether a counterpart exists |
| may be produced by | any retriever, including the measures under test | nothing under test |
| may be incomplete | yes, that is what candidate recall measures | no — incompleteness becomes false NONEs |
| recorded per | candidate (`retrievers`) | anchor (`truth.oracle`, and `region_id`) |

**The oracle, chosen for cost.** Full-document browsing is the obvious independent universe and is
too expensive to be the default. `probe_r8` §2 measures the cheaper one — reviewing every provision
in a bounded structural region of the new version — on the real corpus, so the choice is priced
rather than asserted:

| bound | n | median | mean | p90 | max |
|---|---:|---:|---:|---:|---:|
| anchor's parent path | 1124 | **0** | 13.9 | 44 | 855 |
| grandparent path | 952 | **0** | 24.6 | 95 | 285 |
| top-level division | 1138 | **37** | 56.1 | 104 | 855 |

The median of 0 at the two tighter bounds is itself a finding: renumbering means the anchor's old
parent path frequently does not exist in the new version at all, so a region defined by *the
anchor's old path* is empty for most anchors and would make "none" trivially true — the failure
mode in a new costume. **The region must be defined on the new version's own structure** (a
division/title/account that exists there), which is the row that resolves: median 37, p90 104.

**Design consequence — sample regions, not anchors.** Reviewing 37 provisions per anchor is
unaffordable at 80 anchors and unnecessary: a region read once serves every anchor inside it. So
draw a small number of regions, take all anchors within them, and read each region once. ~4 regions
at median size is a few hundred reads and yields exhaustive truth for every anchor they contain.
This is the same move round 1's C8 made for consolidation, generalised to the whole design.

**Enforcement, not intention.** `pass2_schema.py` requires `truth.oracle` per anchor and
`found_via` per counterpart; `region-exhaustive` additionally requires `region_id`, because "none"
is uninterpretable without the bound it is none within. `eval_pass2.py` then **refuses** to put an
anchor whose oracle is `suggested-list` into the candidate-recall denominator. A dataset labeled
entirely through the suggestion list therefore yields a denominator of zero and says so, instead of
yielding 100%. `tests/test_pass2_eval_contract.py` proves the refusal changes the answer by
removing it.

**Action — blocking, design changed.** Regions, not anchors, as the sampling unit; oracle and
`found_via` recorded; evaluator enforces the exclusion. A counterpart later found outside a stated
region is a recorded `region-escape`, not a labeling error.

---

## §R2-2. The 35.1% vs 0/976 comparison, re-run with everything held constant

**Verdict: CONFIRMED, and the incompatibility was larger than the criticism claimed. The
conclusion partly survives re-testing.**

**Falsification attempted, and it turned up a third defect.** The criticism named two differences
(per-anchor vs per-comparison; unmatched candidate-set size). There is a third, which neither round
had noticed: **the two numbers were computed under different rarity models.**
`probe_review_gameability.py` builds document frequencies inline over the 34-bill union (65,502
bodies); `probe_r4_production_neighborhood.py` imports `mine_common.vec`, which loads
`idf_cache.json`, built over `bills/` + `bills_corpus/` — **232,924 bodies over 2,983 bills**. The
containment values in the two rows of round 1's C7 table are not on the same scale.

**The apples-to-apples experiment.** `probe_r6_rate_parity.py` holds the anchor set, the measure,
the rarity model and the candidate-set size constant, and varies only where the long candidates
come from. Same 77 anchors; for each, k candidates where k is its own real neighbourhood size; 20
control draws per anchor from other bills' added provisions:

| arm | per-comparison | per-anchor |
|---|---|---|
| production (own bill) | **36 / 8,734 = 0.412%** [0.298, 0.570] | **27 / 77 = 35.1%** [25.3, 46.2] |
| control (other bills, k matched) | **94 / 174,680 = 0.054%** [0.044, 0.066] | **66 / 1,540 = 4.29%** [3.38, 5.42] |

The intervals are disjoint on both statistics, so **the direction round 1 claimed does survive** —
about 7.6× more available inside a bill than across bills, holding opportunity count constant.

**But it does not survive dropping one bill.** 119-hr-1 supplies 24 of the 27 production hits:

| arm, 119-hr-1 removed | per-comparison |
|---|---|
| production | 6 / 1,014 = 0.592% [0.271, 1.285] |
| control | 57 / 20,280 = 0.281% [0.217, 0.364] |

Overlapping intervals on n=11 anchors. And 119-hr-1 is the known consolidation bill, where a
high-containment same-bill pair is *most* likely to be a genuine "absorbed into" relation rather
than an error — so the bill carrying the aggregate effect is the bill whose hits are least likely
to be false keeps. **This remains an unlabeled opportunity rate.**

**And "0/976" was never evidence of anything.** At the control rate measured here, 976 draws expect
0.53 hits, so observing zero has probability ≈59% — the likeliest single outcome. Its Wilson upper
bound alone (0.392%) already overlapped the production per-comparison rate. Printing it as "0.0%"
beside "35.1%" read as a 350× gap that the data never contained.

**Action — claim narrowed** (wording in the §7 pointer above), `probe_r6` added to the standing
set, and `probe_r4`'s two headline numbers are no longer cited as a comparison.

---

## §R2-3. The financial miner's denominator

**Verdict: PARTLY CONFIRMED — right about the defect, slightly off about where it lives.**

**Falsification attempted.** The criticism says the review "describes 203/240 = 84.6% as
approximately the percentage of eligible cases hidden by the miner". Reading the artifacts:

- `probe_r3`'s own output line was already literal: *"removed financial nodes with >=1 added
  financial partner available : 240"*.
- Round 1's C6 says *"The floor removes 84.6% of the population from discovery"* — literal, but it
  never states which population, and never says the missed-correspondence count is unknown.
- **The PR description is not literal**: *"The financial miner hides 203 of 240 **eligible cases**
  (84.6%)"*. "Eligible cases" is exactly the promotion of a candidate count into a truth count.

So the criticism lands, on the PR body rather than on the probe.

**Restated literally, as required.** Of **240** removed financial provisions occurring in a version
pair that also contains at least one added financial provision, **203** have no added candidate
clearing the miner's 0.50 word-overlap floor. **40** of those 203 have a ≥0.70 containment
candidate. **The number that are genuine missed correspondences is unknown until they are labeled**
— and at least 3 of the 40 are the degenerate `"$0."` single-token artifact, so even 40 is not a
clean count of severe-false-split shapes.

Support, added in this round because a rate over an undeclared distribution invites the same error:

| bill | in population | below floor | + strong containment |
|---|---:|---:|---:|
| 119-hr-1 | 108 | 72 | 27 |
| 114-hr-2029 | 89 | 89 | 3 |
| 118-hr-4366 | 23 | 23 | 5 |
| 115-hr-5895 | 17 | 16 | 2 |
| 118-hr-8774 | 2 | 2 | 2 |
| 118-hr-8752 | 1 | 1 | 1 |

**The conclusion is not weakened.** The miner cannot be used to estimate severe false-split recall,
because its discovery mechanism suppresses low-word-overlap cases — and that follows from the
exclusion alone, with no assumption about how many of the excluded are real.

---

## §R2-4. The consolidation 47.5% interpretation

**Verdict: PARTLY CONFIRMED — the criticism is right about the claim, but the round-1 review text
already made it correctly.**

**Falsification attempted, and it succeeded for the review.** Round 1's C8 reads: *"The other 245
(47.5%) are unobservable to any label set built this way."* That is the exclusion framing the
criticism asks for, not a claim about relationships. There is no independent truth showing the 516
correspond anywhere, and round 1 never asserted one.

**The criticism lands on the PR description**, which says *"The consolidation miner makes 47.5% **of
relationships** unobservable"*. That is the error, and it is corrected in the PR body.

The wording now used in both places:

> 47.5% of leftover removed provisions are excluded from the containment-selected annotation
> population. A dataset produced by that miner therefore cannot supply a denominator for
> consolidation recall.

**No conclusion changes**, because the bounded-exhaustive-subtree proposal follows from the
exclusion, not from any belief about how many of the 245 have counterparts.

---

## §R2-5. Scope of the IDF robustness result

**Verdict: PARTLY CONFIRMED. The scope criticism is right; its practical bite was falsified.**

**Confirmed.** `probe_r5` scores `p["text_old"]` / `p["text_new"]` — the fixture's frozen strings.
Since three of twelve no longer correspond to anything the parser emits, a result over all twelve
is a result about historical observations, and round 1 stated it without that scope.

**Falsification succeeded, and it matters.** `probe_r5` §2b now repeats the entire analysis over
the nine pairs whose stored text still resolves on **both** sides in the current parse. For those
nine the frozen string is byte-identical to a body the parser emits today, so re-deriving them
returns the same string and therefore the same score — they are current observations, not merely
historical ones. Every margin is unchanged:

| variant | margin, all 12 (historical) | margin, resolving 9 (current) |
|---|---:|---:|
| V1 per-version | +0.404 | **+0.404** |
| V2 dedup bodies per bill | +0.400 | **+0.400** |
| V3 one doc per bill | +0.324 | **+0.324** |
| V4 numerics dropped | +0.313 | **+0.313** |
| V5 citations dropped | +0.427 | **+0.427** |

The 0.70 bar holds in all five, both ways. So the ablation **does not rest on the quarantined
records at all** — they are not load-bearing for the separation.

**Wording adopted.** *"Rarity is robust as identity evidence across five document-frequency
definitions, on the nine labeled pairs whose representation the current parser still emits, and on
all twelve as historically frozen. It is untested on the three quarantined observations."* The
narrower claim the criticism proposed would have understated what the probe can support.

**Frozen now, per the criticism.** The five variants, the 0.70 bar and the reported quantities are
fixed as of 2026-08-06 and recorded in the probe's docstring. Re-running the same five after
re-adjudication is a replication; changing them first is fitting to the answer.

---

## §R2-6. "Label decay" is the wrong model — and the right one inverts the diagnosis

**Verdict: CONFIRMED, and the experiment changed the finding rather than only the vocabulary.**

**The chain the round-1 word conflated:**

```
source legislation  ->  parser representation  ->  research observation  ->  human label
   (the XML bytes)        (the node bodies)         (text_old/text_new)      (SAME/DIFFERENT)
```

"3 of 12 labels no longer resolve" is a fact about the **third** arrow. It is silent on which of
the first two moved, and round 1 asserted the parser without testing it.

**The experiment.** `probe_r7_provenance.py`, two independent steps:

1. **The source is stable.** Every XML file the twelve labels reference is byte-identical (git blob
   identity, so a working-tree edit cannot fake it) to the copy that first entered git: 8 files
   unchanged, 0 changed.
2. **The parser is what moved.** The engine is materialized *as of the answer-key commit*
   (`402563e`, 2026-07-10) into a temp tree and run against **today's** XML. It reproduces **all
   three** stored texts that the current parser does not:

```
pair                       side     old parser   current parser
contested-2-corps-110      old             yes               NO
anchor-diff-sec252         old             yes               NO
extreme-alien-snap-10012   old             yes               NO

sides the OLD parser reproduces but the CURRENT one does not : 3
sides NEITHER parser reproduces from today's XML             : 0
```

**So nothing decayed.** The legislation is unchanged, and the human's judgment about it was never
invalidated. The engine now divides the same bytes into different provisions, so **the unit that
was ruled on is not a unit the pipeline produces**. The correct term is **representation drift**,
and the correct remedy is re-derivation plus a fresh ruling over the new unit — not treating the
old ruling as suspect.

That distinction is not cosmetic. "Decay" implies the labels are the damaged thing and invites
re-labeling; representation drift says the labels are intact and the *observation* has to be
rebuilt, which is a different, smaller, and better-defined job.

**Residual gap, stated because it is real.** Step 1 establishes stability only from each file's
first commit. The copy the builder actually read on 2026-07-10 lived in the then-gitignored
`bills/` and is unrecorded, so the window between labeling and first commit rests on no evidence.
That gap is precisely what a source hash in the fixture would have closed.

**The provenance invariant, so a future parser change fails loudly.** `pass2_schema.py` requires on
every node reference: `bill`, `version`, `source_sha256` (the XML bytes), `parser_commit`,
`schema_version`, `match_path` (which may legitimately drift) and `text_sha256` (which may not,
silently). A change to either hash re-quarantines the **observation** and leaves the **human label**
untouched — they are separate records, which is what `readjudication-sealed.json` already models
(`historical_observation` vs `current_observation`). `tests/test_pass2_eval_contract.py` fails any
record missing them.

**Not yet applied to the existing fixture.** `tests/data/similarity_labels.json` still carries no
`text_sha256` or `source_sha256`; adding them means rewriting the fixture, which is a change to a
committed answer key and is left for Will's call rather than done inside a review.

---

## §R2-7. The all-version assertion now has a reproducer

**Verdict: CONFIRMED. `probe_r2` did not demonstrate it; it does now.**

The round-1 claim — the 81-character stub exists in no version of 119-hr-1, "verified across all
five" — was true but rested on an ad-hoc check that was never committed. `probe_r2` §1 only ever
checked the single version each label names.

`probe_r2` §4 now prints, for **all twelve** labels, every version of the bill in which each stored
text appears, and separates two failure modes the single-version check conflated: a body that
**MOVED** to another version (stale locator) from one that is **ABSENT** everywhere (vanished
representation). All three drifted labels are ABSENT, not MOVED:

```
extreme-alien-snap-10012   (5 versions of 119-hr-1 in corpus)
    text_old  labelled 1_reported-in-house   -> ABSENT  found in: (none)
contested-2-corps-110      (5 versions of 115-hr-5895 in corpus)
    text_old  labelled 4_engrossed-amendment-senate -> ABSENT  found in: (none)
anchor-diff-sec252         (5 versions of 115-hr-5895 in corpus)
    text_old  labelled 4_engrossed-amendment-senate -> ABSENT  found in: (none)
```

Also visible, and worth recording: two other labels reference the *same* 115-hr-5895 version and
resolve fine, so this is provision-specific re-segmentation, not a whole-version parse failure.

---

## §R2-8. The evaluator belongs in the blocking set

**Verdict: CONFIRMED. Round 1's item 8 was wrong.**

Round 1 reasoned that metrics are needed after labeling. The risk is not lateness, it is that the
**schema cannot produce the metrics**, and the only way to find that out is to compute them —
after ~160 human rulings, that means collecting them again.

Built in this round, deliberately skeletal:

- **`probes/pass2_schema.py`** — the frozen schema (`pass2-anchor-v1`): relations
  (`one-to-one` / `one-to-many` / `many-to-one` / `none` / `uncertain`, no speculative
  `many-to-many`), oracles, per-candidate retrievers, per-counterpart `found_via`, and the
  provenance fields from §R2-6, with a validator that rejects a record which cannot support a
  metric it would be counted in.
- **`probes/fixtures/eval_contract_synthetic.json`** — ten hand-authored records, no legislation
  and no human judgments, covering every shape the design must handle: clean one-to-one, no
  counterpart, one-to-many with a retrieval gap, a candidate miss found only by browsing, a ranking
  miss, an assignment collision with one winner and one loser, a suggestion-list-only truth, an
  uncertain, and a challenge-stratum failure.
- **`probes/eval_pass2.py`** — computes all five targets and enforces each one's population.
- **`tests/test_pass2_eval_contract.py`** — pins each metric's value on the fixture and proves the
  guards fire.

Output on the synthetic fixture — every target non-degenerate, with both successes and failures so
no metric passes by being vacuously 1.0:

```
1 candidate recall     4/6 counterparts over 5 eligible anchors; misses: a3 (region-sweep), a4 (browse)
2 ranking              n=4, top-1 0.75, MRR 0.833
3 assignment           1 collision group, 2 anchors, accuracy 0.50
4 diff correctness     n=9, accuracy 0.556, full confusion matrix
5 failure modes        high-containment-different: 1/1, flagged NOT a precision
EXCLUDED from candidate recall: a8-suggested-only
```

**Answering the gate question directly.** *If we collect these labels exactly as designed, can we
later calculate candidate recall, ranking accuracy, assignment accuracy and final diff correctness
without discovering that our ground truth was conditioned on the matcher?* **Yes, demonstrably** —
and the demonstration is executable, not a claim: `test_the_anti_circularity_exclusion_can_fire`
shows candidate recall moving (6→7 counterparts, 4→5 found) when the exclusion is removed, so the
guard is doing work rather than decorating the code.

Two design decisions worth a reviewer's attention. Nodes are joined on `text_sha256`, not
`match_path` — the path is the unstable key this whole program exists because of, so joining on it
would break the evaluator exactly where matching is hardest. And collision groups are **derived**,
not annotated: a human ruling one anchor at a time cannot see that two anchors claim the same
target, so asking them to record it would be asking for something they are not positioned to know.

---

## §R2-9. `merged_root()` could go stale, and the precedence was backwards

**Verdict: CONFIRMED. Fixed, and the fix is tested in both directions.**

**Staleness.** The docstring said *"rebuilt on each call … so it cannot go stale"*. The
implementation reused one fixed temp directory and skipped any link that already existed, which
made that false in two ways: a link whose source had been deleted survived (`is_symlink()` is true
for a broken link), and a link pointing at the losing side of a precedence change survived, because
existing-at-all was the only test. Every later run then read a corpus no root described.

`merged_root()` is now **content-addressed**: the directory name is a hash of the exact
`{bill: {version: source path}}` mapping, built in a private staging directory and moved into place
with one `os.replace`. A changed corpus is a different name and therefore a fresh build; an
unchanged corpus reuses a tree correct by construction; a half-built tree is never visible.
Symlinks still mean a source whose *contents* change needs no rebuild — only the file **set** is
content-addressed, which is the part that could go stale.

**Proving the gate can fire.** `tests/test_research_probes.py` runs the replaced algorithm verbatim
against a synthetic corpus and asserts it *does* leave the stale link behind. A staleness test whose
counterpart has never gone red cannot distinguish "no staleness" from "no check".

**Precedence, flipped.** The docstring said `bills/` wins collisions, and it did. That was the wrong
way round: `bills/` is gitignored and disposable (#308, ADR 0015), `tests/corpus/` is committed and
byte-identical everywhere. `ROOTS` now puts `tests/corpus` first, so the largest possible share of
any result is reproducible from a clean checkout. `duplicate_versions()` makes the choice auditable
instead of assumed, and on the current corpus **all 23 collisions are byte-identical**, so the
precedence is immaterial to results and load-bearing only for provenance. A test asserts that, and
will fail if it stops being true.

**A gate where there was none.** These research scripts are excluded from lint and format
(`pyproject.toml`), and round 1 found what that cost: #492 renamed three names and broke thirteen
of them, #308 moved the corpus out from under all fifteen, and nothing noticed for months because
nothing ran them. `tests/test_research_probes.py` adds the two checks that would have caught both,
statically, with no corpus needed: every `from deltatrack… import` still resolves, and no probe
hardcodes an absolute home path. Excluding a directory from lint is a decision about *style*; it
should not also be a decision to stop checking that the code resolves.

---

## §R2-10. Corpus manifest

**Verdict: CONFIRMED, and the hole is larger than the criticism described.**

"34 bills / 106 versions" does mean "whatever XML happened to be on one disk". Measured:

```
versions by root : tests/corpus 58  |  bills 48
```

So **45% of the corpus every union number is computed over does not exist in a clean clone.** And
the bigger omission is not the XML at all: the containment values depend equally on the rarity
model, and `mine_idf.py` builds that over `bills/` + `bills_corpus/` — **232,924 provision bodies
across 2,983 bills**, both trees gitignored. Until this round, no probe's output said which of the
two rarity models it had used (see §R2-2, where that silence produced an invalid comparison).

**What was added.** `corpus_roots.manifest()` records `bill`, `version`, `root` and **SHA-256** for
every file, plus the repo commit, the per-root split, the collision report, and the IDF model's
corpus name, document count and cache hash. `manifest_digest()` reduces it to one short string that
two runs share iff they read the same bytes.

**Where it lives, and why that split.** Committing a full manifest and *maintaining* it would
conscript someone into upkeep for a tree that legitimately changes. So:

- **Printed by every probe**, as a one-line banner, so no output is anonymous about its inputs:
  `[corpus e3e05399eb6196d5] 34 bills / 106 versions / 71 adjacent pairs | idf=bills+bills_corpus n_docs=232924 sha=89d4508e5a4f | repo e3a98ae81bc1`
- **Committed once as a snapshot** of the run that produced the numbers reported here
  (`corpus-manifest.json`). A reader compares their banner digest against it and knows immediately
  whether they are looking at the same corpus, instead of inferring it from a bill count.

**Honest limit.** A manifest makes a result *auditable*; it does not make it *reproducible*. Half
this corpus and the entire rarity model cannot be reconstructed from the repository. The manifest's
value is that this is now visible in every output rather than in one caveat at the top of one
document.

---

## §R2-11 / 12. Adjudication of the drifted records

**Verdict: ACCEPTED without qualification. Packet prepared; nothing adjudicated.**

No ruling was inferred from word overlap, containment, header equality, or the current matcher, and
the historical label was not carried forward. `probes/make_readjudication_packet.py` writes two
deliberately separate files:

- **`readjudication/readjudication-packet.md`** — blind. Bill, versions, the current new-version
  provision, and the old-version candidates, with structural breadcrumbs and headers (shown on
  purpose: protocol §5 treats structural context as a signal the human legitimately uses). No
  scores, no matcher decision, no prior verdict, no indication of which approach an answer favours.
- **`readjudication/readjudication-sealed.json`** — the historical observation (stored text,
  hashes, original human label, historical scores, label commit) and the current observation
  (parser commit, source hashes, the current options) as **separate records**. The current one
  carries no label and must not inherit one.

**The subtle part is how the old side is chosen.** For two of the three the stored old text is gone,
so something must decide what the reviewer sees. Choosing by best text similarity — what `probe_r2`'s
diagnostic table does — would let a signal under evaluation pick the evidence its own re-validation
rests on. The packet therefore does not choose: it shows **every** node the current parser emits at
the label's structural path, in document order, and asks which (if any) is the counterpart. For
`extreme-alien-snap-10012` that surfaces both sides of the `sec. 10012` path collision, which is the
honest presentation of that case.

**Leak scan.** The packet is masked and scanned with the same `blindness.py` guard the live labeling
path uses, plus an explicit check that no stored score string appears. It fired once, on the word
"measures" in prose this round authored; the prose was reworded rather than the guard loosened.

**Two limits, stated rather than engineered away.** The seal is a convention — both files are
committed and readable. And Will ruled these pairs in July and may remember; no mechanism can
prevent that, so the packet asks the legislative question over the *current* unit, which is a
genuinely different question, rather than asking for the old verdict to be reconfirmed.

---

## §R2-C. Revised Study 2 labeling design

> **↪ Round 3 (§R3-1, §R3-3, §R3-C).** Two defects. The oracle: `region-exhaustive` cannot
> establish that no counterpart exists, only that none exists *in that region* — a counterpart that
> moved to another title reads as NONE, and 40.8% of anchors sit in an old top-level unit that does
> not even exist in the new version. Negatives now require a document-wide escalation. The sampling
> frame: defining regions on the **new** version made an anchor's inclusion probability depend on a
> correspondence judgment. Regions are now defined on the **old** version, where an anchor's region
> is read off the same parse that produced the anchor. And the four-region MVP buys ~12 effective
> observations, not 80, so the population-estimate claim is withdrawn.

Everything in round 1's §B stands except the ground-truth mechanism. The invariant:

> **Candidate generators may help humans find counterparts. They may not define whether a
> counterpart exists.**

Operationally, in four rules:

1. **Sample regions, then anchors inside them.** A region is a bounded structural unit of the
   **new** version (division / title / account) that exists there — not the anchor's old path,
   which renumbering empties for most anchors (§R2-1). Median region: 37 provisions.
2. **Read the region once, exhaustively.** Every provision in it is reviewable, retrieved or not.
   That, not the suggestion list, is the truth universe. Cost amortises across every anchor in the
   region.
3. **Retrieval still drives the UI, and is recorded as such.** Candidates are ordered by the
   retriever union so the common case is one click; the ordering is a convenience and the human may
   accept a counterpart from anywhere in the region. `found_via` records which happened —
   `suggested`, `region-sweep`, or `browse`.
4. **The oracle is recorded per anchor and enforced downstream.** `region-exhaustive` requires
   `region_id`; `suggested-list` anchors are excluded from candidate recall by `eval_pass2.py`.
   `document-search` is the escalation when a region sweep returns none and the reviewer suspects a
   cross-region move; a counterpart later found outside a stated region is a recorded
   `region-escape`.

Label space: `one-to-one`, `one-to-many`, `many-to-one`, `none`, `uncertain` — plus round 1's C9
addition of `unrelated` / `uncertain` to the consolidation stratum. `uncertain` is never folded
into `none`; a test pins that.

Unchanged from round 1 §B: the five evaluation targets, by-bill splitting, scores stripped at label
time with the automated leak guard, structural context shown, per-stratum kappa with support, the
LLM as disagreement-flagger and never a vote, no silent caps.

**MVP cost, restated on the new unit.** ~4 sampled regions (median 37 provisions each, p90 104)
gives exhaustive truth for every anchor they contain — on the order of 150–400 provision reads for
roughly 40–80 anchors, against round 1's 80 anchors × 8 candidates with no recall denominator at
all. The bounded consolidation subtree (C8) is the same mechanism and merges into it.

---

## §R2-E. Revised blocking / non-blocking

> **↪ Round 3 (§R3-G).** Superseded. Items 4 and 5 were marked done on schema v1, which round 3
> found could not produce valid metrics; they revert to open against schema v2. The table is also
> re-cut into four tiers, because "blocking" was doing two jobs at once.

**Blocking — before any human labeling resumes**

| # | item | state |
|---|---|---|
| 1 | **Re-derive the 12 observations** against the current parser and **quarantine** the drifted ones. The human labels are **not** rewritten (§R2-6). | probes done; fixture not yet carrying `text_sha256` / `source_sha256` — **Will's call** |
| 2 | **Re-mine the financial stratum** without signal-conditioned discovery: union retrieval, `amount_source_old/new`, minimum-token floor (C6, §R2-3). | not started |
| 3 | **Anchor-level ground truth with an oracle independent of retrieval** (§R2-1, §R2-C). | designed + enforced in schema/evaluator; sampling not run |
| 4 | **Freeze the correspondence/label schema**, including `none` / `uncertain` / multiple (C9, §R2-8). | **done** — `pass2_schema.py`, `pass2-anchor-v1` |
| 5 | **Skeletal evaluator proving the schema computes the promised metrics** (§R2-8). | **done** — `eval_pass2.py` + 14 tests |
| 6 | **Correct the Study 1 premises Study 2 would inherit** (C1, C3, C4, C10) — asymmetry, cross-type generalization, "census", "text carries the gain". | proposed in §E, **not applied** |

**Non-blocking — necessary to merge this review, not gates on annotation**

| # | item | state |
|---|---|---|
| 7 | Production-neighbourhood rate normalization (§R2-2) | **done** — `probe_r6` |
| 8 | Exact percentage wording, financial + consolidation (§R2-3, §R2-4) | **done** in this document; PR body corrected |
| 9 | `merged_root()` staleness + precedence (§R2-9) | **done**, tested both ways |
| 10 | Corpus manifest (§R2-10) | **done** — banner + committed snapshot |
| 11 | All-version provenance reproducer (§R2-7) | **done** — `probe_r2` §4 |
| 12 | Probe-import CI gate (round 1 item 9) | **done** — `tests/test_research_probes.py` |
| 13 | Theory rewrite around the overlap coefficient; directional-B benchmark; structural-confirmer decision | Study 4 |
| 14 | Re-run the frozen IDF ablation after re-adjudication (§R2-5) | blocked on item 1; **variants frozen, do not re-tune** |

**The distinction being drawn.** An item gates *annotation* if collecting labels without it would
produce a dataset that cannot answer its question — items 1–6 all fail that test. An item gates
*merging* if a reader would otherwise carry away a number the evidence does not support — items
7–11. Wording and infrastructure defects are real and are fixed, but a labeler's screen does not
change because a percentage was restated, so they do not hold up the labeling.

---

## §R2-D. Probes added and changed in round 2

| probe | decides | headline output |
|---|---|---|
| `probe_r6_rate_parity.py` | §R2-2 | production 0.412% vs matched control 0.054% per comparison; overlaps once 119-hr-1 is removed |
| `probe_r7_provenance.py` | §R2-6 | source byte-identical; the 2026-07-10 parser reproduces all 3 drifted texts from today's XML |
| `probe_r8_oracle_gap.py` | §R2-1 | union@8 misses a header-identical candidate for 18.1% of anchors that have one; region-size cost table |
| `pass2_schema.py` + `eval_pass2.py` + `fixtures/eval_contract_synthetic.json` | §R2-8 | all five targets computed; circularity exclusion proven to fire |
| `make_readjudication_packet.py` | §R2-12 | blind packet + sealed provenance, leak-scan clean |
| `corpus_roots.py` *(changed)* | §R2-9, §R2-10 | content-addressed merged view; committed-first precedence; manifest + banner |
| `probe_r2_label_drift.py` *(changed)* | §R2-7 | §4 all-version provenance for all 12 labels |
| `probe_r3_financial_miner.py` *(changed)* | §R2-3 | denominator stated literally; by-bill support |
| `probe_r5_idf_ablation.py` *(changed)* | §R2-5 | §2b margins over the 9 resolving pairs — identical |

New tests, which run in CI unlike the probes themselves: `tests/test_research_probes.py` (the
import gate, the corpus-view invariants, and the manifest) and `tests/test_pass2_eval_contract.py`
(the data contract). Both are parametrized over things that will grow, so their counts are not
quoted here — run them.

---

## §R2 — what still needs human judgment

1. **The three drifted observations.** Packet ready; not adjudicated, and deliberately not
   inferrable from any signal in this repository.
2. **Whether to add `text_sha256` / `source_sha256` to `tests/data/similarity_labels.json`.** It is
   the right invariant (§R2-6) and it means rewriting a committed answer key, which a review should
   not do to itself.
3. **Applying §E's documentation corrections to `paper.md` and `pass2-protocol.md`.** Still
   proposed, not applied, so the wording can be agreed first.
4. **Whether `tests/test_research_probes.py` should exist at all.** It couples the product suite to
   research artifacts, which is a real cost. The argument for it is that the alternative already
   failed: a lint exclusion silently became a "nothing checks this" exclusion for months.
5. **The region-sampling parameters** — how many regions, at which bound, across which bills. The
   cost table prices the options; the coverage/effort trade is a judgment call.

---
---

# §R3 — Third adversarial review (round 3)

**Target: rounds 1 and 2 together, including round 2's fixes.** Nine criticisms. Five hold as
stated, three hold in part, and one was falsified. The pattern across the three that hold hardest is
worth naming, because it is the same mistake three times: **round 2 built a guard for one metric and
left the identical defect running in the others.** The anti-circularity exclusion protected candidate
recall while four metrics kept consuming suggestion-list truth; `text_sha256` was rejected as an
identity for `match_path`'s instability and then adopted as one; `region-exhaustive` was introduced
to make negatives independent of retrieval and then treated as if it made them independent of
*location*.

| # | criticism | verdict | what changed |
|---|---|---|---|
| 1 | region-local NONE becomes global NONE | **CONFIRMED** | oracles are a list; negatives need document escalation |
| 2 | suggestion-list truth contaminates the other four metrics | **CONFIRMED** | per-metric truth requirements, enforced as data |
| 3 | region sampling breaks the estimand and the frame | **CONFIRMED**, both halves | frame moves to the old side; population claim withdrawn |
| 4 | `text_sha256` is not a node identity | **CONFIRMED**, at scale | observation identity = `(source, parser, element_id)` |
| 5 | the 18.1% causal wording overreaches | **CONFIRMED** | narrowed in probe, review and PR |
| 6 | rate-parity CIs ignore clustering | **CONFIRMED** | cluster bootstrap at three levels |
| 7 | "all five computable" ≠ "all five valid" | **CONFIRMED** | contract check re-specified; 5 adversarial records |
| 8 | preserve what survived | **ACCEPTED** | nothing reopened; one round-2 probe self-audited |
| 9 | existing blockers still apply | **ACCEPTED** | §R3-G |

---

## §R3-1. Region-exhaustive truth converts "none in this region" into global NONE

**Verdict: CONFIRMED. The falsification attempt failed on inspection, and the mechanism turned out
to be different from — and nastier than — the one the criticism described.**

**Falsification attempted.** The criticism asks whether the schema and evaluator already separate
`none-in-region` from `none-in-document`. Reading v1: the *information* was present
(`oracle=region-exhaustive` plus `region_id`), so a reader could in principle tell them apart. The
*metrics* could not. `INDEPENDENT_ORACLES = ("region-exhaustive", "document-search")` put both in
one bucket, and nothing downstream consulted `region_id`. So the distinction existed in the data and
nowhere else, which is the same as not existing.

**The mechanism, corrected.** The criticism says a false NONE would be consumed as truth by candidate
recall. Tracing it, that is not what happens, and the real path is worse:

- `candidate_recall` only ever iterated anchors whose relation was *positive*. A false NONE does not
  enter as a wrong observation — **it vanishes from the denominator entirely.** And the anchors that
  vanish are exactly the ones retrieval failed hardest on. **The bias is by selection, and selection
  bias is invisible in the metric it corrupts**: candidate recall goes up, nothing looks wrong, and
  no record is individually incorrect.
- `diff_correctness` is where the criticism's description lands exactly. A region-local NONE yields
  truth `change_type=removed`, and the matcher that also said `removed` is scored **correct** on the
  strength of a search that never looked at most of the document.

Measured on the contract fixture: admitting the two bounded-search negatives moves diff correctness
from **6/11 (54.5%) to 8/13 (61.5%)**, and `test_admitting_bounded_negatives_would_inflate_diff_correctness`
pins that both ways.

**Evidence that the escape is not hypothetical.** `probe_r10_sampling_design.py` §1: of 2,137
anchors, **872 (40.8%)** sit in an old top-level unit that does not exist in the new version at all.
Those are precisely the anchors whose counterpart, if any, must be somewhere else.

**Which metrics need global truth** — the criticism's central question, answered in §R3-B and
encoded in `pass2_schema.METRIC_TRUTH_REQUIREMENTS`. The short version: **ranking needs only an
affirmed positive; the other three need document-wide completeness.** Ranking asks where the true
counterpart sat in an ordering, and a second counterpart elsewhere does not change that. So
`region-exhaustive` is genuinely sufficient for one of the five, which is why the requirement is
per-metric rather than one global flag.

**Design adopted: Option A, systematic escalation** — with `truth.oracles` as a **list** of the steps
actually performed, so a region sweep followed by a document search is recordable as what it is. A
negative becomes global only when `document-search` is in the list. No reviewer judgment is
involved: the criticism's "do not rely on 'I suspect a move'" is met by making escalation
unconditional for negatives rather than discretionary.

Option B (relabel the metrics as region-local) was rejected on the arithmetic: a region-local recall
number answers no question anyone has, since a staffer's exposure to a missed counterpart does not
stop at a title boundary.

**Action — blocking.** `oracles` list, mandatory `region_id`, escalation for every negative, and an
evaluator that refuses. Cost: only negatives escalate, so the region economy survives for positives.

---

## §R3-2. Suggestion-list truth contaminated the other four metrics

**Verdict: CONFIRMED. No falsification available — the code says so plainly.**

**Falsification attempted, and abandoned at the source.** v1's `candidate_recall` filtered on
`INDEPENDENT_ORACLES`. `ranking`, `assignment`, `diff_correctness` and `failure_modes` each iterated
`records` with no oracle filter at all. The schema docstring even *asserted* that `suggested-list`
was "sufficient for ranking, assignment and diff correctness" — an assertion nobody had tested, and
which is two-thirds wrong.

The criticism's worked example is exact: system says `removed`, a suggestion-list reviewer sees no
counterpart, truth becomes `removed`, evaluator scores the matcher correct. Round 2 built a guard
against precisely this and then left the back door open.

**Required work — the mapping, derived rather than assumed.** For each metric, the proposition its
arithmetic silently relies on (full table in §R3-B, code in `METRIC_TRUTH_REQUIREMENTS`):

| metric | what its arithmetic assumes | requires |
|---|---|---|
| candidate recall | the counterpart set is enumerable | `complete-in-document` |
| ranking | *this node* is a counterpart | `affirmed-positive` |
| assignment | every competitor for a node has been found | `complete-in-document` |
| diff correctness | whether **any** counterpart exists | `complete-in-document` |
| challenge rates | per stratum: existence vs absence | declared in `challenge_requires` |

**A fourth requirement, found while encoding the third.** A contract test forced a distinction the
criticism did not raise: an `affirmed-positive` is only affirmed if the human was asked a
**per-candidate binary** question. A forced choice among eight candidates yields "the best of what I
was shown", which is manufactured by the candidate set. The protocol's card UI is already
per-candidate binary; `truth.judgment_mode` now records it, and `establishes()` returns False for
every proposition under `forced-choice` — a forced-choice dataset supports nothing. The first cut
gated only positives on it; `test_forced_choice_cannot_establish_a_positive` failed, correctly,
because a counterpart *set* is only as sound as each member's affirmation.

**Enforcement, and proof it fires.** Each metric now reports a `refused` block naming the anchors it
would not consume and the proposition they lack. On the fixture, three anchors are refused by three
metrics and zero by ranking — the asymmetry is the point, and
`test_ranking_still_admits_bounded_oracles` pins it so a future "just require the strictest oracle
everywhere" simplification cannot quietly discard valid evidence.

---

## §R3-3. Region sampling breaks both the frame and the estimand

**Verdict: CONFIRMED, both halves, and the second is worse than the criticism suggested.**

### The circularity — confirmed against round 2, and resolvable

**Falsification attempted, and it succeeded for a design round 2 did not write.** The criticism
asks: for every anchor, can inclusion probability be determined without knowing its true
counterpart? `probe_r10` §1 answers it for both framings:

| frame | anchors whose region is determined without correspondence |
|---|---|
| **old-side** (regions are units of the OLD version) | **2,137 / 2,137 = 100%** |
| **new-side** (round 2 §R2-C's actual wording) | 1,265 / 2,137 = **59.2%** |

An anchor *is* a node of the old version, so its old region is read off the same parse that produced
the anchor — no diff, no matcher, no counterpart. Inclusion probability is `P(region drawn) × 1`,
known before any labeling. Under round 2's new-side wording, **40.8% of anchors** sit in an old
top-level unit with no counterpart unit in the new version, so the sampler would have to make a
correspondence judgment before any human saw the anchor.

Round 2 conflated two different regions: the one that defines the **sampling frame** (must be
old-side, or the frame is circular) and the one that bounds the **oracle sweep** (must be new-side,
because that is where you look for the counterpart). They are now separate, and the sweep region is
demoted to a search heuristic whose failures are caught by the §R3-1 escalation — so it never
defines truth.

### The estimand — confirmed, and priced

`probe_r10` §2 measures intra-cluster correlation on two label-free proxy outcomes (the matcher's
`removed`-vs-`moved` call; whether any added provision reaches containment 0.70). Both are proxies
for the *correlation structure*, which does not require them to be correct:

| clustering | clusters | ICC (proxy A / B) | design effect | n_eff of 2,137 |
|---|---:|---:|---:|---:|
| old region | 147 | 0.271 / 0.291 | 4.7 / 4.9 | 458 / 432 |
| version pair | 32 | 0.153 / 0.268 | 11.1 / 18.6 | 193 / 115 |
| bill | 15 | 0.088 / 0.188 | 13.4 / 27.6 | 159 / 77 |

Applied to the proposed MVP (§3–4 of the probe), with the worse measured ICC:

| design | anchors | clusters | deff | n_eff | ±95% at p=0.5 |
|---|---:|---:|---:|---:|---:|
| **round 2 MVP: 4 regions × 20** | 80 | 4 | 6.5 | **12.2** | **±28%** |
| 8 regions × 10 | 80 | 8 | 3.6 | 22.1 | ±21% |
| 20 regions × 4 | 80 | 20 | 1.9 | 42.7 | ±15% |
| 80 random anchors | 80 | 80 | 1.0 | 80.0 | ±11% |

**The round-2 MVP buys about twelve independent observations and a ±28-point interval.** It cannot
distinguish 60% recall from 90%. And §3 of the probe shows the ceiling is structural, not a matter
of drawing more regions: only **36 regions hold ≥10 anchors, and they sit in 4 bills.**

### Decision: (B) development and challenge dataset

Study 2 is **not** a population-estimation study, and the claim that "targets 1–4 are population
estimates" is withdrawn. Reasons, in order of weight:

1. The arithmetic above. At ±28 points, an estimate is indistinguishable from no estimate, and
   quoting one implies a precision the design cannot deliver.
2. The population was never defined. The corpus is a convenience sample of 34 bills chosen for
   fixture coverage; there is no frame from which it is a probability sample of *anything*, so
   weighting would put a rigorous superstructure on an arbitrary base.
3. Each round has found the estimand harder, not easier — matcher-conditioned (R1), then
   retrieval-conditioned (R2), now cluster-limited (R3). Three consecutive corrections in the same
   direction are a signal about the ambition, not about the execution.

What is *kept* is everything that made the design worth building: the frame is frozen (§R3-C) and
recorded per record, so a later study can scale it into a genuine estimate without re-labeling;
selection is documented and reproducible; and the dataset answers "does this failure mode occur,
where, and does a change fix it", which is what the engineering work actually needs.

**Action — blocking.** Frame on the old side; freeze the algorithm (§R3-C); delete the
population-estimate language from §R2-B and the protocol.

---

## §R3-4. `text_sha256` is not a node identity

**Verdict: CONFIRMED, at a scale that makes it the most consequential defect in this round.**

**Falsification attempted — the criticism invited a corpus search, and the corpus answered.**
`probe_r9_node_identity.py`:

```
documents parsed                                  : 106
documents containing at least one duplicated body : 35 (33%)
distinct body texts that occur more than once     : 551
node occurrences involved in a duplicate group    : 1544
largest multiplicity (one text, one document)     : 12
```

It is not exotic and it is not marginal. Appropriations bills are assembled from repeated
boilerplate — "No part of any appropriation contained in this Act shall remain available for
obligation beyond the current fiscal year" appears six times in one version of 113-hr-3547, at six
distinct paths. And it reaches **every version of all four answer-key bills**, up to multiplicity 12
in 119-hr-1.

The criticism asked to report even a null result and not assume future legislation is safe. The
result is not null, so the stronger form applies: the schema now *requires* uniqueness and
`validate_dataset` fails loudly if a future parser stops providing it.

**The failure direction matters.** A content-hash join fails **optimistically**: a recall miss
against provision X scores as a hit whenever any boilerplate twin is in the candidate set; a rank-2
target scores as top-1; a wrong assignment scores as correct. Every collapse flatters the matcher.

**Design adopted** — the three concepts the criticism asked to separate:

| concept | field | may two distinct nodes share it? |
|---|---|---|
| observation identity | `(source_sha256, parser_commit, element_id)` | **no** — asserted, not assumed |
| content integrity | `text_sha256` | **yes**, routinely — that is the finding |
| cross-version identity | the human's SAME/DIFFERENT ruling | it is the study's OUTPUT, never an input key |

`element_id` is parser-emitted and measured **unique and non-empty on all 106 documents**. It is
preferred over a traversal ordinal because an ordinal shifts when anything earlier in the document
changes, while an element id does not.

**Adversarial test, both directions.** The fixture carries two distinct nodes sharing one body:
`a14` (true counterpart is `dupA`, only `dupB` retrieved, matcher assigned `dupB`) and `a15` (true
counterpart is `dupB`, sitting at rank 2 behind `dupA`).
`test_a_content_hash_join_would_corrupt_this_metric` restores v1's join and asserts candidate
recall, top-1 and assignment accuracy all score **strictly better** under it — the defect proven by
running it.

**Self-audit, because round 2 wrote the same bug twice.** `probe_r8_oracle_gap.py` keyed its
header lookup on normalized body text. Re-keyed on `element_id` and re-run: **18.1% unchanged**. The
defect was real and its effect on that number was nil, which is worth stating in both halves. The
re-adjudication packet was also checked: all three drifted records' new-side texts are unique in
their version, so the packet already shipped is unaffected. `element_id` is now recorded in the
sealed provenance so this cannot depend on luck next time.

---

## §R3-5. The 18.1% wording overreached

**Verdict: CONFIRMED.**

The probe's own caveat was adequate; the PR description's gloss was not. *"A labeler seeing only the
list would answer 'no counterpart'"* is a causal claim the evidence does not carry: header equality
is not ground truth, and five of the eight printed examples are generic headers (`definitions`,
`report`, `findings`, `rescission`). Nor is 18.1% a lower bound on true counterpart misses, since a
true counterpart need not share a header.

Adopted wording, in the probe, the review and the PR:

> Among anchors that have a candidate matching on an independent fourth relevance signal, the
> union@8 omits that candidate 18.1% of the time. This demonstrates the suggestion list is not
> exhaustive. It does not estimate true candidate recall, and it does not estimate how often a
> labeler would record a false NONE.

**The logical falsification of the oracle is untouched**, and it never needed the rate: one
retrievable-by-another-signal candidate that the union hides is sufficient to refute "the union can
serve as the oracle".

---

## §R3-6. The rate-parity intervals ignored clustering

**Verdict: CONFIRMED. The cluster-aware result is more informative than the nominal one, exactly as
the criticism predicted.**

The Wilson intervals treated every short×long comparison as independent. They are clustered within
anchors, version pairs and bills — and the 20 control replicates reuse the same 77 anchors, so they
cut Monte Carlo noise while entering the denominator as if they were fresh evidence. That is why the
control interval was so tight.

`probe_r6_rate_parity.py` §4 adds a cluster bootstrap (2,000 draws) on the **ratio** of the two
per-comparison rates:

| resampling unit | clusters | 95% percentile CI of the ratio | excludes 1? |
|---|---:|---|:--:|
| anchor | 77 | [4.62, 20.61] | yes |
| version pair | 7 | [2.26, 40.00] | yes |
| **bill** | **5** | **[0.00, 15.38]** | **NO** |

Point estimate 8.0×. **Stable under anchor and version-pair clustering; unstable under bill
clustering, because the support is five bills.** So the honest statement is the descriptive one, and
significance language is dropped:

> In this corpus, a spurious ≥0.70 partner was available about 8× more often inside a bill than
> across bills, holding the anchor set, the rarity model and the candidate-set size constant. The
> effect survives resampling anchors and version pairs. It does not survive resampling bills, of
> which there are five, so it is a property of this corpus rather than an estimate of a population
> rate.

**A reproducibility defect found while doing this.** The first cut recomputed the control draws for
the bootstrap and got a ratio of 9.7× against section 1's 7.6× — a 27% disagreement between two
numbers in one run, because the control arm's hits are concentrated in a few anchors and its
across-draw variance is far above Poisson. Both arms are now computed once, per anchor, and every
aggregate and bootstrap derives from those rows. The spread is itself part of why §4 exists.

---

## §R3-7. "All five computable" was not "all five valid"

**Verdict: CONFIRMED. The contract check was measuring the wrong thing.**

v1 printed YES for all five while three of them consumed truth that could not support their
arithmetic. The gate question is re-specified as the criticism proposes:

> If we collect labels using the actual frozen sampling and oracle workflow, can every promised
> metric be computed over a population whose ground truth is adequate for **that** metric?

Five adversarial records added, one per failure the criticism named:

| record | shape | what it would break without the fix |
|---|---|---|
| `a11-region-only-none` | region-local NONE | certifies the matcher's `removed` as correct |
| `a12-cross-region-escape` | counterpart outside the swept region | anchor silently leaves the recall denominator |
| `a13-suggestion-list-none` | suggestion-list NONE | same as a11, one step downstream of the guard |
| `a14-duplicate-text-wrong-node` | duplicate body, wrong node | recall miss and wrong assignment both score as correct |
| `a15-duplicate-text-right-node` | duplicate body, rank-2 target | rank-2 target scores as top-1 |

Plus `a3-one-to-many-outside-region`: a region-local **positive** whose second counterpart is
outside the region — the case the criticism flagged where finding one counterpart in-region does not
prove no others exist elsewhere.

Every fix is pinned by a test that **removes it and asserts the number moves**. Current output on
the fixture, all five populations non-degenerate:

```
candidate recall  5/9 counterparts over 8 eligible anchors; 3 refused (needs complete-in-document)
ranking           n=5, top-1 0.60, MRR 0.767; 0 refused (needs affirmed-positive only)
assignment        3 contended targets, 4 scorable anchors, accuracy 0.50; 3 refused
diff correctness  n=11, accuracy 6/11; 3 refused
failure modes     high-containment-different 1/1, flagged NOT a precision
```

---

## §R3-8. What round 3 did not reopen

Checked and left standing, with no contradicting evidence found: the measure is a symmetric weighted
overlap coefficient and symmetry did not cause the historical result (R1-C1); the IDF ablation
survives on the nine resolving observations (§R2-5); matcher-conditioned pair sampling cannot
estimate recall (R1-C2); the financial miner's signal-conditioned discovery makes it unfit for
recall estimation (R1-C6, §R2-3); the consolidation miner supplies no recall denominator (R1-C8,
§R2-4); observation drift is distinct from human-label validity (§R2-6); the manifest and the probe
import/staleness guards (§R2-9, §R2-10); the original 35.1%-vs-0/976 comparison was invalid
(§R2-2); and the same-bill opportunity effect is descriptive and driven by 119-hr-1 — now with the
clustering caveat from §R3-6 attached.

One round-2 artifact was audited rather than reopened: `probe_r8`'s text-keyed header join was the
same defect as §R3-4, was fixed, and the number did not move.

---

## §R3-A. Oracle semantics

> **↪ Round 4 (§R4-1, §R4-8, §R4-A).** Two changes. `document-search` is renamed
> **`document-exhaustive`** and now grants `complete-in-document` only on *measured review
> coverage* — the old name licensed "I searched and found nothing", which a transformed counterpart
> survives. And a fourth proposition, **`affirmed-negative`**, is added: a pairwise false-keep
> ruling is complete at one comparison and should not be charged for a ~161-adjudication document
> sweep it does not need.

| oracle | establishes | does NOT establish | metrics it may feed |
|---|---|---|---|
| `suggested-list` | `affirmed-positive` — this node is a counterpart | anything about counterparts not shown | ranking only |
| `region-exhaustive` | `affirmed-positive`, `complete-within-region` — no counterpart in region R | that no counterpart exists outside R | ranking only |
| `document-search` | all of the above plus `complete-in-document` | — | all five |

Three notes that make the table operational. `oracles` is a **list**: a region sweep followed by a
document escalation is `["region-exhaustive", "document-search"]`, and only the presence of the
second admits the record to a completeness metric. `region_id` is **mandatory** whenever
`region-exhaustive` appears, because "none" is uninterpretable without the bound it is none within.
And `judgment_mode` gates **every** proposition: under `forced-choice` the table collapses to
nothing, because "the best of these eight" is a claim about the candidate set, not the legislation.

A counterpart later found outside a stated region is a recorded **region-escape**, not a labeling
error — the record was true within its declared bound and says so.

---

## §R3-B. Metric truth requirements

Encoded in `pass2_schema.METRIC_TRUTH_REQUIREMENTS`, consumed by `eval_pass2._admits`, and pinned by
`tests/test_pass2_eval_contract.py`. Prose here is a reading of the data, not a second source.

| metric | proposition its arithmetic assumes | required | allowed oracles | exclusion rule |
|---|---|---|---|---|
| candidate recall | the complete counterpart set is known | `complete-in-document` | must include `document-search` | refuse; bias is by selection, so a refused anchor must be *named*, not dropped |
| ranking | this node is a counterpart | `affirmed-positive` | any, with `per-candidate-binary` | refuse only `forced-choice` |
| assignment | every competitor for a node is known | `complete-in-document` | must include `document-search` | refuse — and one refused member **disqualifies its whole collision group** |
| final diff correctness | whether any counterpart exists anywhere | `complete-in-document` | must include `document-search` | refuse |
| challenge failure rates | per stratum: existence needs a positive, absence needs completeness | `challenge_requires` | per stratum | refuse; a stratum that does not declare its claim is a schema error |

The group-level rule for assignment is the one that is easy to get wrong: scoring an anchor whose
own truth is complete, inside a group containing an anchor whose truth is not, still lets an unfound
competitor make a wrong assignment look right.

---

## §R3-C. Frozen sampling design

> **↪ Round 4 (§R4-2, §R4-B).** The frame below was frozen in prose while `probe_r10` measured a
> different, matcher-selected population, and the numbers that justified the design came from the
> probe. `study2_frame.py` is now the single executable definition and nothing else may define an
> anchor. The corrected frame is 13.8× larger and spans 12 bills, so the cluster-count ceiling this
> section reasoned from does not exist. Step 1's "≥10 anchors" floor and the region/anchor
> ambiguity (§R4-6) are resolved there.

**Estimand.** None. Study 2 is a **development and challenge dataset**, not a population-estimation
study (§R3-3). Every metric it produces is a statement about the sampled units, reported with its
selection rule, and never extrapolated to "the operational rate".

**Sampling unit.** The **region**, defined as a top-level structural unit of the **OLD** version of
one adjacent version pair — a division or title, as the old parse emits it.

**Inclusion mechanism**, stated as an algorithm because "sample roughly four regions" is not one:

1. Enumerate every `(bill, old_version, top_level_unit)` in the corpus with ≥ 10 anchors. Measured:
   **36 regions across 4 bills.** This is the frame, and it is computable from old-side parses alone.
2. Stratify by bill; draw regions **without replacement**, recording `P(selected)` per region.
3. Take **every** anchor in a drawn region. Inclusion probability of an anchor is
   `P(its region drawn) × 1` — computable with **no correspondence knowledge**, which is the
   property §R3-3 tests and round 2's frame did not have.
4. For each anchor: sweep the corresponding new-version region exhaustively; escalate **every**
   negative, and every `one-to-many` positive, to a document-wide search. Record `oracles`,
   `region_id` and per-counterpart `found_via`.
5. Freeze the drawn region list, with the corpus manifest digest, before labeling starts.

**Are these population estimates?** **No**, and the evaluator's output must not be reported as
though they were.

**Weighting and clustering.** No weighting, because there is no population to weight to. Any
descriptive rate reported from this dataset must carry the number of **regions and bills** it came
from, not only the anchor count — and where a comparison is made, a cluster bootstrap at the bill
level, as §R3-6 now does for the rate-parity result.

**Minimum clusters.** ≥ 8 regions across ≥ 3 bills for any cross-region statement. Below that, report
per-region numbers and no aggregate.

---

## §R3-D. Node identity

> **↪ Round 4 (§R4-3, §R4-4, §R4-C).** The direction was right and both halves of the execution
> were wrong. The claim that `element_id` is unique cited **R9 §4, a section that did not exist** —
> the measurement was run in a shell and never committed. It is committed now, and element_id does
> hold (0 empty, 0 duplicates over 73,296 nodes). It is still not the key: identity is
> `(source_sha256, parser_commit, **node_ordinal**)`, because uniqueness by construction beats an
> empirical regularity of GPO markup, and `parser_commit` already makes cross-parser stability
> irrelevant. The v2 validator also compared only `text_sha256`, so two distinct provisions sharing
> a body — the boilerplate case — collided undetected.

Three separate things, kept separate (full rationale in §R3-4):

```
observation identity   (source_sha256, parser_commit, element_id)   unique per parse, ASSERTED
content integrity      text_sha256                                  may legitimately collide
cross-version identity the human's SAME/DIFFERENT ruling            the study's output, never a key
```

`validate_dataset` rejects an empty `element_id` and rejects any observation id mapping to two
different body texts. `test_a_content_hash_join_would_corrupt_this_metric` restores the old join and
asserts three metrics improve, so the guard is proven to fire rather than assumed to work.

---

## §R3-E. Executable contract

`probes/fixtures/eval_contract_synthetic.json` — 15 hand-authored records, no legislation, no human
judgments. Rounds 1–2 shapes plus the five round-3 adversarial ones (§R3-7). The contract check now
asks whether each metric has an **adequate** population, and every guard is tested by removal.

---

## §R3-F. Rate-parity inference

Descriptive, with cluster bootstrap at three levels. Significance language removed. See §R3-6.

---

## §R3-G. Final blocking table

Round 2's single "blocking" list was doing two jobs — gating annotation and gating the merge — and
round 3's criticisms split cleanly along a third and fourth line. Four tiers:

**Tier 1 — required to merge this methodology review**

| item | state |
|---|---|
| Correct the 18.1% causal wording (§R3-5) | **done** — probe, review, PR |
| Cluster-aware rate-parity inference, significance language dropped (§R3-6) | **done** — `probe_r6` §4 |
| Restate the financial and consolidation percentages literally (§R2-3, §R2-4) | **done** |
| Corpus manifest, probe import gate, `merged_root` staleness (§R2-9, §R2-10) | **done** |

**Tier 2 — required before ANY human annotation**

| item | state |
|---|---|
| Oracle semantics: `oracles` list, mandatory escalation for negatives (§R3-1) | **done** — schema v2 |
| Per-metric truth requirements, enforced (§R3-2) | **done** — schema v2 + evaluator |
| Observation identity separated from content hash (§R3-4) | **done** — schema v2 |
| Executable contract over adversarial records (§R3-7) | **done** — 15-record fixture |
| Frozen sampling design, old-side frame (§R3-3, §R3-C) | **done** — algorithm frozen; **the draw has not been run** |
| Re-derive + quarantine the 12 observations; add `text_sha256`/`source_sha256` to the answer key | **OPEN — Will's call** (§R2-6) |
| Re-mine the financial stratum without signal-conditioned discovery (R1-C6) | **OPEN — not started** |
| Apply the Study 1 premise corrections to `paper.md` / `pass2-protocol.md` (§E) | **OPEN — proposed, not applied** |
| Adjudicate the three drifted observations | **OPEN — packet ready, deliberately not adjudicated** |

**Tier 3 — required before held-out evaluation**

| item | state |
|---|---|
| Held-out split drawn at the **region** level, not the anchor level (else regions straddle the split) | not started |
| Per-stratum `challenge_requires` declared for every existing challenge pool | not started |
| Reporting layer: CIs, per-stratum breakdowns, kappa, cluster-aware intervals | not started |

**Tier 4 — Study 4**

Theory rewrite around the overlap coefficient; directional-variant benchmark on the
reverse-direction population; whether to adopt structural confirmers; re-running the frozen IDF
ablation after re-adjudication (variants frozen, **do not re-tune**).

**Human labeling remains gated.** Tier 2 has four open items, and every one of them is a judgment
call rather than an implementation task.

---

## §R3 — probes added and changed

| probe | decides | headline output |
|---|---|---|
| `probe_r9_node_identity.py` | §R3-4 | 35/106 documents (33%) contain duplicate body text; 551 texts, 1,544 occurrences, max multiplicity 12; reaches all four answer-key bills |
| `probe_r10_sampling_design.py` | §R3-3 | old-side frame 100% computable vs new-side 59.2%; ICC 0.27–0.29 by region; round-2 MVP n_eff 12.2, ±28% |
| `probe_r6_rate_parity.py` *(changed)* | §R3-6 | cluster bootstrap: survives anchor and version-pair resampling, not bill (5 bills) |
| `probe_r8_oracle_gap.py` *(changed)* | §R3-4, §R3-5 | header join re-keyed on `element_id` (18.1% unchanged); causal wording narrowed |
| `pass2_schema.py` *(v2)* | §R3-1, §R3-2, §R3-4 | oracle capabilities, per-metric truth requirements, observation identity |
| `eval_pass2.py` *(changed)* | §R3-1, §R3-2, §R3-7 | per-metric admission, refusal reporting, re-specified contract check |
| `make_readjudication_packet.py` *(changed)* | §R3-4 | `element_id` recorded in the sealed provenance |

---

## §R3 — what still requires human judgment

1. **The three drifted observations.** Unchanged from round 2: packet ready, not adjudicated.
2. **Whether to add provenance hashes to `tests/data/similarity_labels.json`.** Round 3 adds a
   second field to the same decision: `element_id`.
3. **The region draw.** The algorithm is frozen; which regions, and how many, is a coverage/effort
   call. §R3-3's table prices it: 8 regions × 10 anchors is the cheapest design that keeps the
   interval under ±25 points, and the corpus caps the frame at 36 regions across 4 bills.
4. **Whether a ±28-point dataset is worth collecting at all**, or whether Study 2 should be
   re-scoped to the challenge strata only and the population question deferred to a corpus that can
   support it. The analysis says the dataset is worth building as a dev/challenge set; whether it is
   worth *this much labeling effort* is a product call.
5. **Applying §E's documentation corrections**, still proposed and not applied.

---
---

# §R4 — Fourth adversarial review (round 4)

**Target: rounds 1–3, and specifically whether the new machinery obeys its own rule.** Eleven
criticisms. Seven hold as stated, two in part, one is rejected, one is preserved-as-asked. The
review's framing question was:

> Have we actually built independent ground truth and an independent sampling frame, or have we only
> renamed the final remaining dependencies?

**Renamed, twice.** The sampling frame was still `diff_bills` output (§R4-2). The strongest oracle
still granted completeness for *searching* rather than for *covering* (§R4-1). Each had been
described in the review as independent, and each description was true of something other than what
the code did.

A third finding is about this document rather than the design: the schema cited **"R9 §4"** as
evidence for a load-bearing invariant, and that section had never been written (§R4-3). The
measurement had been run in a shell during round 3 and never committed. This programme has now
caught the same defect four times — `paper.md`'s unreproducible Appendix A, round 1's un-probed
"all five versions", round 3's uncommitted §4, and round 3's prose/code divergence on the frame.
The pattern is not carelessness about any one claim; it is that **prose and code were never forced
to agree**, so a citation could name a reproducer that did not exist and nothing turned red.

| # | criticism | verdict | what changed |
|---|---|---|---|
| 1 | `document-search` ≠ `complete-in-document` | **CONFIRMED** | renamed `document-exhaustive`; completeness granted on a measured count |
| 2 | `probe_r10`'s frame is matcher-selected | **CONFIRMED** | `study2_frame.py` is now the only definition; frame is 13.8× larger |
| 3 | `element_id` uniqueness cited but not measured | **CONFIRMED** | R9 §4 written; element_id holds, and is demoted anyway |
| 4 | the validator misses same-identity same-text collisions | **CONFIRMED** | compares every attribute; identity moves to `node_ordinal` |
| 5 | n_eff/±28 is sensitivity, not measured precision | **CONFIRMED**, and worse | proxies span ICC 0.058–0.700; reframed |
| 6 | "every anchor" vs "8 × 10" is ambiguous | **CONFIRMED** | `draw_study2_sample` makes both explicit |
| 7 | schema docstring contradicts schema v2 | **CONFIRMED** | rewritten as one authoritative v3 description |
| 8 | `affirmed-negative` is missing | **CONFIRMED** | added; pairwise challenges no longer buy completeness |
| 9 | re-decide the study shape on the corrected frame | **PARTLY CONFIRMED** | re-run; conclusion changes (§R4-G) |
| 10 | preserve what round 3 fixed | **ACCEPTED** | nothing reopened |
| 11 | annotation blockers stand | **ACCEPTED** | §R4-H |

---

## §R4-1. `document-search` did not establish `complete-in-document`

**Verdict: CONFIRMED.**

**Falsification attempted.** The criticism offers a way out: if the workflow already required
reviewing *every* provision in the target document, with search merely reordering the queue, then
the oracle was sound and only its name was wrong. Reading the artifacts, it did not. The schema
described it as *"the human searched the whole new version by their own means (text search, table of
contents)"* and *"reserved for anchors where region-exhaustive returned none and the reviewer
suspects a cross-region move"*. That is workflow **A** in the criticism's terms — arbitrary queries
until satisfied — and nothing in the schema, the evaluator or the protocol constrained it further.

**Why it matters.** A counterpart whose header changed, whose wording was rewritten, and which moved
to an unexpected title survives every query the reviewer did not think to type. The record then
claims the counterpart set is complete, candidate recall drops the anchor from its denominator, and
diff correctness certifies the matcher's `removed`. This is the same circularity one layer out: the
*reviewer's search vocabulary* takes over the role the retrievers had.

**Action — the completeness contract is now a count, not a promise.** The oracle is renamed
**`document-exhaustive`** and `truth.coverage` is mandatory:

```
truth.coverage = {"rule": "all-nodes-with-body", "eligible_total": 161, "reviewed": 161}
```

`complete-in-document` is granted **only when `reviewed >= eligible_total`**. Retrieval, search and
structural navigation may order the queue; they may not end it. `rule` must come from
`COVERAGE_RULES`, an allowlist of measure-independent rules — a rule that consulted containment
would let a system under evaluation set the denominator of its own completeness claim, which is the
defect one layer further out again.

A reviewer who stops early does not produce a defective record. They produce a record that claims
less, and the evaluator refuses it for the metrics that need more.

**Test.** `a16-incomplete-document-sweep` names `document-exhaustive` with coverage 40/161 and is
refused by all three completeness metrics; completing the sweep admits it and raises
`diff_correctness.n` from 11 to 12. Both directions are pinned.

**The cost this exposes, which drives §R4-G.** `probe_r10` §4: a target version holds a **median of
161** provisions. One document-complete record therefore costs ~161 adjudications. That is the real
constraint on Study 2, and it was invisible while the oracle could be satisfied by searching.

---

## §R4-2. The sampling frame was still the matcher's output

**Verdict: CONFIRMED. This is the most consequential finding of the round.**

**Falsification attempted, and it failed at line 97.** `probe_r10_sampling_design.py`:

```python
d = diff_bills(told, tnew)
...
if c.change_type not in ("removed", "moved") or not c.old_text:
    continue
```

Round 3 wrote: *"every anchor IS a node of the old version, so its region is read off the same parse
that produced the anchor"*. True — of the anchors the matcher had already selected. The probe
measured that the **region** was matcher-independent and reported it as evidence that the
**population** was.

**Consequence.** Every design number round 3 published came from a matcher-conditioned sample:
2,137 anchors, 147 regions, 36 drawable, 4 bills, ICC 0.27–0.29, n_eff 12.2, ±28 points — and the
decision to downgrade Study 2 rested on the last two.

**The corrected frame**, from `study2_frame.py`, which does not import `diff_bill` at all:

| | matcher-conditioned (round 3) | canonical frame (round 4) |
|---|---:|---:|
| eligible anchors | 2,137 | **29,530** |
| old-side regions | 147 | **1,029** |
| drawable regions (≥10 anchors) | 36 | **460** |
| bills with a drawable region | 4 | **12** |
| median drawable region size | — | 34 |

**Answering the criticism's question directly — what IS the anchor population?** Option **A**: every
eligible provision in the old version. Eligibility is two structural predicates and nothing else —
non-empty body text, non-empty structural path — and both are read from the parse. No diff, no
matcher, no similarity measure, no retrieval.

That population deliberately includes provisions the matcher handles perfectly. Those are not wasted
labels: a correspondence dataset containing only cases the matcher already flagged cannot measure
whether it is right about the ordinary ones, and *"the matcher says this is unchanged"* is a claim
that can be wrong.

**Action — one canonical implementation.** `probes/study2_frame.py` exposes
`enumerate_study2_anchors`, `enumerate_study2_regions` and `draw_study2_sample`; `probe_r10` now
consumes it; and `tests/test_research_probes.py` plus the contract suite assert **statically** that
it never imports `diff_bill`. The deeper fix is that the frame is now code that three consumers
share, rather than a concept each was free to re-invent.

---

## §R4-3. The `element_id` invariant was cited, not measured

**Verdict: CONFIRMED, and the citation was to a section that did not exist.**

`pass2_schema.py` asserted element_id was *"unique and non-empty on all 106 documents (R9 §4)"*.
`probe_r9_node_identity.py` had three sections and no mention of `element_id`. The check was run in
a shell during round 3 and never committed.

**Measured now** (R9 §4, committed):

```
documents checked                                 : 106
nodes checked                                     : 73296
nodes with an empty element_id                    : 0
documents with a duplicated element_id            : 0
maximum element_id multiplicity                   : 1
```

So the claim was **true**. That is exactly why the defect is worth recording: an unreproducible
citation that happens to be correct is indistinguishable, to every later reader, from one that is
not — and this document's own standard is that empirical claims carry reproducers.

---

## §R4-4. The validator could not see the collision that matters

**Verdict: CONFIRMED, and the proposed identity change is adopted.**

**Falsification attempted — the criticism's counterexample was constructed and run.** v2's validator
grouped refs by observation id and flagged an id mapping to more than one `text_sha256`. Give two
*distinct* provisions the same identity and the same body — the boilerplate case, present in 33% of
documents — and there is no conflicting hash to find. Measured on a deliberately corrupted fixture:

```
v2 text-only validator would flag: 0 collisions
v3 validator: REJECTED -> observation id collision: ...
```

**Identity changed to `node_ordinal`**, per the criticism's reasoning, which survives scrutiny: the
key already carries `parser_commit`, so cross-parser stability was never required, and a changed
parser must re-quarantine the observation anyway (round 2's drift finding) — which a shifted ordinal
forces. Uniqueness by construction beats an empirical regularity of GPO markup, especially for a
study whose purpose is legislation the corpus has not seen. `element_id` is retained as a recorded
attribute for traceability and is asserted, by test, **not** to affect any join.

The validator now compares every recorded attribute (`text_sha256`, `match_path`, `element_id`)
across a shared identity, so a generator that assigns one ordinal to two nodes is caught whenever
those nodes differ in any recorded way.

---

## §R4-5. n_eff and ±28 were a sensitivity calculation

**Verdict: CONFIRMED — and the corrected frame makes the point far more sharply than the criticism
did.**

**Falsification attempted.** Is there a reason either proxy bounds the true-label ICC? No. Both
round-3 proxies were matcher- or measure-derived, and neither has any argued relationship to the
clustering of human correspondence judgments. The tight range they produced (0.271–0.291) read as
precision and was really two views of one quantity on one selected population.

**Evidence, on the corrected frame.** `probe_r10` §2 now reports three proxies, two of them purely
structural:

| proxy | prevalence | region-level ICC |
|---|---:|---:|
| A structural: duplicated body | 2.9% | **0.118** |
| B structural: above-median length | 49.9% | **0.058** |
| C matcher: in the hard neighbourhood | 7.2% | **0.700** |

**A twelve-fold spread.** The proxies disagree so strongly that no single one of them can stand in
for the unknown outcome, which is the criticism's point made in data rather than in principle.

**Adopted framing**, in the probe and here:

> Proxy outcomes show clustering ranging from weak (ICC 0.058) to very strong (0.700) depending on
> which proxy is chosen. Under those bounds an 8-region × 10-anchor design behaves like anywhere
> between 11 and 53 independent observations, i.e. a worst-case half-width between ±14 and ±30
> points. This is a design **sensitivity** calculation, not the measured precision of an unlabeled
> outcome.

**The main conclusion survives and does not depend on the exact ICC**: this corpus and this labeling
budget cannot credibly estimate an operational error rate. Neither end of the range makes it
possible.

---

## §R4-6. "Every anchor" vs "8 × 10" was two designs

**Verdict: CONFIRMED.** §R3-C said *"take every anchor in a drawn region"*; the cost table priced
*"8 regions × 10 anchors"*. With a median drawable region of 34 anchors those are different designs
with different inclusion probabilities, and prose cannot arbitrate between them.

**Action.** `draw_study2_sample(n_regions, seed, anchors_per_region)` makes both explicit and
records which was used. `anchors_per_region=None` takes every anchor; an integer draws uniformly
without replacement within the region. Either way the per-anchor inclusion probability
`P(region) × P(within region)` is computed and persisted, along with the seed, the corpus manifest
digest, the selected region keys and the selected anchor identities. Regions are drawn without
replacement and stratified round-robin across bills, so one bill cannot supply the sample.

**The algorithm is frozen in this PR; the study's draw is not performed.** A demonstration draw runs
in `__main__` and in tests, to prove the algorithm reproduces under a fixed seed.

---

## §R4-7. The schema docstring still described v1

**Verdict: CONFIRMED, and this is the failure mode the programme itself named.**

The live `pass2_schema.py` still said `suggested-list` was *"sufficient for ranking, assignment, and
diff correctness"* — while its own executable rules refused it for two of those — and described
document search as discretionary while the rules made escalation systematic. It also referenced
`truth.oracle`, a field v2 had replaced with `truth.oracles`.

Round 2's §R2-6 finding was that stale explanatory prose preserves a superseded methodology after
the implementation changes. Round 3 shipped exactly that defect inside the new contract.

**Action.** The docstring is rewritten as a single authoritative description of v3 and nothing else,
with an explicit note that history belongs in this document rather than in the module.

---

## §R4-8. `affirmed-negative` was a real missing concept

**Verdict: CONFIRMED.**

**Falsification attempted.** Could the existing representation express it? A pairwise DIFFERENT
ruling could only be recorded by *omitting* the node from `counterparts`, which is indistinguishable
from never having seen it — the same conflation as "not retrieved" vs "does not exist", now on the
negative side. And `challenge_requires` accepted only `affirmed-positive` or `complete-in-document`,
so a stratum claiming *"this high-containment pair is actually DIFFERENT"* had to declare
`complete-in-document` and buy a ~161-adjudication document sweep for a judgment that is complete at
one comparison.

**Action.** Fourth proposition `affirmed-negative`, granted by every oracle under per-candidate
binary judgment; `truth.rejected` records the nodes a human looked at and ruled DIFFERENT;
`challenge_requires` accepts it; and the challenge metric branches on the stratum's declared claim
rather than applying the completeness test to everything.

Two useful side effects. Candidate-recall misses can now be split into *"the retriever never showed
it"* and *"the retriever showed it and the human ruled it out"*. And a stratum may not mix
requirements — a validator rule added after the v3 fixture exposed that a single reported rate would
otherwise pool two different propositions.

| challenge claim | needs |
|---|---|
| "this high-containment pair is actually DIFFERENT" | `affirmed-negative` |
| "the matcher failed to retrieve the true counterpart" | `affirmed-positive` (+ completeness for a rate) |
| "there is no counterpart anywhere" | `complete-in-document` |

---

## §R4-9. Re-deciding the study shape on the corrected frame

**Verdict: PARTLY CONFIRMED. The premise was right, the expected direction was not.**

The criticism says: do not choose between a general dev sample and challenge-only using numbers
generated from matcher-selected anchors. Correct, and round 3 did exactly that.

**Falsification attempted on the conclusion itself.** Round 3 downgraded Study 2 partly because
*"only 36 regions hold ≥10 anchors and they sit in 4 bills"*. On the real frame that is **460 regions
across 12 bills**. The corpus constraint round 3 reasoned from does not exist.

**But the decision does not flip**, because §R4-1 replaced it with a harder one: every metric except
ranking needs `complete-in-document`, and that now costs a median of **161 adjudications per
anchor**. Cluster count is free; reviewer effort is not.

| | measured |
|---|---|
| region sweep (median drawable region) | ~34 adjudications |
| document sweep (median target version) | ~161 adjudications |
| eligible anchors / drawable regions / bills | 29,530 / 460 / 12 |

**What the general sample adds that the challenge strata cannot** — the criticism's decisive
question. Challenge strata are selected for being hard, so they can only ever answer "does this
failure mode occur, and how badly". They structurally cannot answer *"does the matcher get ordinary
correspondences right, and does a change break any of them"*. That is regression coverage, it is the
thing every future change to the measure needs, and it is cheap: it needs only `affirmed-positive`,
so a region sweep suffices and no document escalation is required.

**Recommendation: Option 3, a three-tier design** (§R4-G), because the cost structure is no longer
uniform across the metrics and a single-tier design has to price everything at the most expensive
oracle.

---

## §R4-10 / 11. Preserved, and still open

Nothing from round 3 was reopened: metric-specific truth requirements, systematic escalation for
negatives, rejection of suggestion-list negatives for completeness metrics, rejection of
`text_sha256` as identity, the duplicate-body prevalence result, the cluster-aware downgrade of
rate-parity significance, the descriptive-only same-bill effect, drift-vs-label-validity, IDF
robustness on the nine resolving observations, the financial-miner and consolidation-miner
circularity results, the corpus manifest and probe guards, and the withdrawal of the
population-estimation claim. Round 4's changes extend these rather than revisiting them.

The existing annotation blockers stand unchanged and are re-listed in §R4-H.

---

## §R4-A. Oracle completeness contract

> **↪ Round 5 (§R5-1, §R5-A).** Right idea, weaker execution than it read. The contract below is
> satisfied by a **count** (`reviewed >= eligible_total`), and a count is still an assertion: review
> node 42 twice, never reach node 117, record 161/161. v4 records the reviewed **set** and grants
> completeness on set equality. Round 4's own contract test demonstrated the hole by *setting*
> `reviewed = eligible_total` to promote a record.

What a human must have done before a record may receive `complete-in-document`:

1. The queue was **every provision in the target version** admitted by a declared `coverage.rule`
   from `COVERAGE_RULES` — an allowlist whose members consult only the parse, never a similarity
   measure or a ranking.
2. The reviewer **adjudicated every item in that queue** — accept or reject — and the counts are
   recorded: `coverage.reviewed` and `coverage.eligible_total`.
3. `establishes(truth, "complete-in-document")` returns true only when `reviewed >= eligible_total`.

Retrieval, text search and structural navigation may set the **order** of the queue. They may not
set its **end**. That single sentence is the round-4 contract, and the count is what makes it
enforceable rather than aspirational.

| | region-exhaustive | document-exhaustive |
|---|---|---|
| coverage | one named region | whole target version, under a declared rule |
| grants | `complete-within-region` | `complete-in-document`, **iff reviewed ≥ eligible_total** |
| measured cost | ~34 adjudications | ~161 adjudications |

---

## §R4-B. Canonical Study 2 sampling implementation

> **↪ Round 5 (§R5-3, §R5-C).** The frame is matcher-independent and stands. The **draw** had two
> defects: the recorded `p_inclusion` was one corpus-wide figure that was wrong in both directions
> (6× understated for a small bill, 2.6× overstated for a large one), and deterministic bill
> ordering gave whole strata **zero** selection probability whenever `n_regions < len(bills)` —
> with 12 drawable bills and a 4-region request, eight bills were unsamplable.

`probes/study2_frame.py` is authoritative for all four questions, and nothing else may answer them:

| question | function | matcher-independent? |
|---|---|---|
| anchor eligibility | `enumerate_study2_anchors` | **yes** — non-empty body, non-empty path; asserted by static import test |
| region construction | `enumerate_study2_regions` | yes — top-level unit of the old parse |
| region draw | `draw_study2_sample` | yes — seeded, without replacement, stratified by bill |
| within-region selection | `draw_study2_sample(anchors_per_region=…)` | yes — uniform, or take all |

Anchor eligibility is **matcher-independent**, not "intentionally matcher-conditioned": the frame
contains provisions the matcher never flagged, by design.

---

## §R4-C. Observation identity experiment

Measured over the whole corpus (R9 §4): 106 documents, 73,296 nodes, **0** empty `element_id`, **0**
duplicate `element_id` within a document. The invariant holds — and identity is
`(source_sha256, parser_commit, node_ordinal)` regardless, because ordinal uniqueness is by
construction rather than by observation, and `parser_commit` already scopes the key to one parse so
cross-parser instability is not a defect. `element_id` is recorded, and a test asserts changing it
does not change any join.

---

## §R4-D. Capability model (v3, exhaustive)

> **↪ Round 5 (§R5-2, §R5-D).** A fifth proposition, `complete-source-side`, is added, and
> "assignment" splits into two estimands. A `document-exhaustive` sweep runs per OLD anchor over the
> NEW document: it enumerates that anchor's counterparts and is silent about which *other* old
> provisions claim the same node. Scoring a collision group with it is truth collected in one
> direction only.

| proposition | granted by | needs per-candidate binary |
|---|---|---|
| `affirmed-positive` | all three oracles | yes |
| `affirmed-negative` | all three oracles | yes |
| `complete-within-region` | `region-exhaustive`, `document-exhaustive` | yes |
| `complete-in-document` | `document-exhaustive` **and** complete measured coverage | yes |

Under `forced-choice` the table collapses to nothing: "the best of these eight" is a claim about the
candidate set, not the legislation.

---

## §R4-E. Contract fixture

17 records. Rounds 1–3 shapes plus round 4's two: `a16-incomplete-document-sweep` (searched, not
covered) and `a17-pairwise-false-keep` (a pairwise DIFFERENT ruling under a suggestion-list oracle,
`relation: uncertain` because the counterpart set genuinely is). The duplicate-identity case is
constructed in a test rather than committed, because it must fail validation.

Every guard is tested by removal: restoring the content-hash join improves three metrics; admitting
the three bounded-search negatives raises diff correctness from 6/11 to 9/14; completing a16's sweep
admits it; a forced-choice dataset produces zero admissible records for every metric.

---

## §R4-F. Revised sampling analysis

Run against the canonical frame, with the three categories kept apart:

- **Measured**: 29,530 anchors; 1,029 regions; 460 drawable; 12 bills; median drawable region 34;
  median target version 161 provisions; proxy ICCs 0.058 / 0.118 / 0.700.
- **Sensitivity (assumed)**: n_eff and interval widths, which depend on an outcome ICC nobody has
  measured and which the proxies bracket only loosely.
- **Product choice**: the tier structure in §R4-G.

---

## §R4-G. Revised Study 2 recommendation — Option 3, three tiers

> **↪ Round 5 (§R5-5, §R5-6, §R5-E).** The three tiers stand; the cost note below does not.
> "Amortised" conflated reading with deciding: judging that target node X is not anchor A's
> counterpart says nothing about anchor B, so K anchors against one document remain K×M pairwise
> decisions however many times the document is read. §R5-E separates the two, and drops the
> single "cost" figure in favour of counts plus an explicit refusal to guess seconds-per-decision.

The cost structure is no longer uniform across the metrics, so a single-tier design has to price
every anchor at the most expensive oracle. Three tiers instead:

| tier | oracle | supports | scale | cost |
|---|---|---|---|---|
| **A — regression** | region-exhaustive | ranking (top-1, MRR) | 20–30 regions × 10 anchors, 8–12 bills | ~34 adj./region, amortised across its anchors |
| **B — diagnostic** | document-exhaustive | candidate recall, assignment, diff correctness | **tens** of anchors, concentrated in few version pairs | ~161 adj. each, amortised when anchors share a target version |
| **C — challenge** | suggested-list + `affirmed-negative` | failure-mode rates | existing pools | one comparison each |

Tier A is the general development sample and is cheap because ranking needs only
`affirmed-positive`. Tier B is where the expensive truth lives and is deliberately small; its
numbers are **diagnostic**, never operational rates. Tier C becomes affordable for the first time
because §R4-8 stopped charging pairwise claims for document completeness.

Concentrating tier B within a few version pairs amortises the document sweep — a reviewer reads the
target document once and judges several anchors against it — which trades cluster diversity for
depth. That trade is a real one and is the main open judgment call.

**Study 2 still does not estimate operational prevalence**, on any tier.

---

## §R4-H. Blocker table

**1 — required to merge this methodology review**

| item | state |
|---|---|
| Commit the element_id measurement the schema cites (§R4-3) | **done** — R9 §4 |
| Rewrite the schema docstring to describe v3 only (§R4-7) | **done** |
| Reframe n_eff/±28 as sensitivity, with the proxy spread shown (§R4-5) | **done** — `probe_r10` §2–3 |
| Correct round 3's frame numbers wherever cited (§R4-2) | **done** |

**2 — required before ANY human annotation**

| item | state |
|---|---|
| Completeness granted on measured coverage (§R4-1) | **done** — schema v3 |
| Canonical matcher-free frame, one implementation (§R4-2, §R4-B) | **done** — `study2_frame.py` + static gate |
| Identity on `node_ordinal`; validator compares all attributes (§R4-3, §R4-4) | **done** — schema v3 |
| `affirmed-negative` and `truth.rejected` (§R4-8) | **done** — schema v3 |
| Sampling algorithm unambiguous and reproducible (§R4-6) | **done** — `draw_study2_sample`; **draw not performed** |
| Adjudicate the three drifted observations | **OPEN — packet ready, deliberately not adjudicated** |
| Add provenance to the answer key (`text_sha256`, `source_sha256`, `node_ordinal`) | **OPEN — Will's call** |
| Re-mine the financial stratum without signal-conditioned discovery | **OPEN — not started** |
| Apply the Study 1 premise corrections to `paper.md` / `pass2-protocol.md` | **OPEN — proposed, not applied** |
| Choose the tier-A/B/C scale and run the draw (§R4-G) | **OPEN — Will's call** |

**3 — required before held-out evaluation**

| item | state |
|---|---|
| Held-out split at the **region** level, drawn from the canonical frame | not started |
| `challenge_requires` declared for every existing challenge pool | not started |
| Reporting layer: cluster-aware intervals, per-stratum breakdowns, kappa | not started |

**4 — deferred future research**

Theory rewrite around the overlap coefficient; directional-variant benchmark; whether to adopt
structural confirmers; re-running the frozen IDF ablation after re-adjudication (variants frozen,
**do not re-tune**).

**Human labeling remains gated**: five open items in tier 2, all of them judgment calls.

---

## §R4 — probes added and changed

| probe | decides | headline output |
|---|---|---|
| `study2_frame.py` *(new)* | §R4-2, §R4-6 | 29,530 anchors / 1,029 regions / 460 drawable / 12 bills; seeded reproducible draw |
| `probe_r9_node_identity.py` *(§4 added)* | §R4-3 | 73,296 nodes, 0 empty and 0 duplicate element_id; ordinal chosen anyway |
| `probe_r10_sampling_design.py` *(rewritten)* | §R4-2, §R4-5, §R4-9 | proxy ICC 0.058–0.700; document sweep ~161 adjudications |
| `pass2_schema.py` *(v3)* | §R4-1, §R4-4, §R4-7, §R4-8 | coverage-gated completeness; ordinal identity; `affirmed-negative` |
| `eval_pass2.py` *(changed)* | §R4-1, §R4-8 | per-claim challenge test; uncertain records reach pairwise strata |
| `make_readjudication_packet.py` *(changed)* | §R4-4 | `node_ordinal` recorded in the sealed provenance |

---

## §R4 — what still requires human judgment

1. **The three drifted observations.** Unchanged since round 2: packet ready, not adjudicated.
2. **Provenance fields on `tests/data/similarity_labels.json`.** Now `text_sha256`,
   `source_sha256`, `node_ordinal`. Still a committed-fixture rewrite.
3. **Tier scale, and the tier-B concentration trade.** How many regions in tier A; how many
   document-complete anchors in tier B; and whether to concentrate them in few version pairs to
   amortise the sweep, at the cost of cluster diversity.
4. **Whether tier B is worth ~161 adjudications per anchor at all**, or whether candidate recall and
   diff correctness should wait for a cheaper oracle or a larger budget.
5. **Applying §E's documentation corrections**, still proposed and not applied.

---
---

# §R5 — Fifth adversarial review (round 5)

**Target: the human truth machinery — does it prove what it claims to prove?** Seven criticisms.
Five hold as stated, two in part, none is rejected. Round 5's sharper statement of the standard:

> Do not prove completeness with a count when what you need is a set, and do not prove a global
> assignment with truth collected in only one direction.

Both halves landed. And both were the *same shape as the defect the round before had just fixed*:
round 4 replaced "the reviewer searched" with a number, which is a weaker claim than it reads;
round 3 built collision groups from whatever records the dataset happened to contain, which round 4
tightened without noticing it was tightening the wrong axis.

| # | criticism | verdict | what changed |
|---|---|---|---|
| 1 | coverage proven by a count, not a reviewed set | **CONFIRMED** | v4 records sets; completeness is set equality |
| 2 | assignment truth collected in one direction | **CONFIRMED** | split into per-anchor and collision-resolution estimands |
| 3 | recorded inclusion probabilities are wrong | **CONFIRMED**, plus a zero-probability bug | explicit per-bill quota; probabilities re-derivable |
| 4 | `all-nodes-with-body` may not be a complete universe | **PARTLY CONFIRMED** | invariant measured, holds, now guarded by a test |
| 5 | tier A may pay for truth it does not use | **PARTLY CONFIRMED** | what region sweeps buy, stated precisely |
| 6 | "amortisation" conflates reading with deciding | **CONFIRMED** | costs separated; no seconds-per-decision guess |
| 7 | stale current-state prose | **CONFIRMED** | audited and corrected |

---

## §R5-1. Completeness was proven by a count

**Verdict: CONFIRMED.**

**Falsification attempted.** The criticism offers an exit: if some existing mechanism already
guaranteed `reviewed unique node identities == eligible node identities`, the integer was merely a
summary. Nothing did. `coverage_is_complete` read `reviewed >= eligible_total` and no other code
path examined membership. Worse, round 4's own contract test
(`test_completing_the_sweep_admits_the_record`) promoted a record by *assigning*
`reviewed = eligible_total` — the criticism's threat model, executed in the test suite as though it
were a legitimate operation.

**Evidence.** `a18-count-matches-set-does-not` reviews 21 nodes over a 21-node universe, repeating
one and omitting another:

```
v3 rule (reviewed >= eligible_total) : COMPLETE
v4 rule (set equality)               : NOT complete -> refused by all three completeness metrics
```

**Action — v4 records sets.** `coverage` carries `eligible_ordinals` (generated from the frozen
target parse by a coverage rule, never typed by a reviewer or client) and `reviewed_ordinals`.
Completeness is `set(reviewed) == set(eligible)`, so duplicates collapse and an omission has
nothing to hide behind. The block also pins `target_source_sha256` / `target_parser_commit`, so a
coverage set derived from one document cannot certify completeness over another.

All five adversarial tests the criticism asked for are present and each is proven to change an
outcome: duplicate-plus-omission at equal cardinality (refused), duplicates inflating the count
(refused), an ordinal outside the eligible universe (rejected at validation, named explicitly),
missing parse identity (rejected), and exact set coverage (granted).

---

## §R5-2. Assignment truth had only one direction

**Verdict: CONFIRMED. The distinction the criticism proposed survives an attempt to collapse it.**

**Falsification attempted.** Could target-side sweeps establish the group after all? No, and not for
want of thoroughness — it is the wrong axis. A `document-exhaustive` sweep answers *"for old anchor
A, which new nodes are its counterparts?"* Collision resolution asks *"for new node X, which old
provisions legitimately claim it?"* No amount of the first produces the second. Round 3's evaluator
derived groups from `claims` built over the records present in the dataset, which is a statement
about sampling, not about legislation.

**Evidence.** `a19-target-complete-source-unknown` is document-complete on the target side and its
counterpart is a contested node. The evaluator reports it as a group **without** source-side truth
and refuses to score it. Strip every `competition_coverage` from the fixture and the metric reports
`measurable: false` rather than scoring the two contested nodes it can still see.

**Action — two estimands, stated separately** (§R5-B):

- **`assignment_per_anchor`** — *for this anchor, did the system assign exactly its true counterpart
  set?* Needs target-side `complete-in-document` only. Measurable now: n=12, accuracy 0.50.
- **`collision_resolution`** — *for a contested target node, did the global assignment resolve the
  group correctly?* Needs `complete-source-side`: a reverse sweep recorded as
  `truth.competition_coverage`, with the same set-membership proof as §R5-1. On the fixture: 1 group
  scorable, 2 observed without source-side truth, accuracy 0.00.

**A defect neither reviewer predicted, found while building this.** The first cut compared the
system's assigned **target** ordinals against truth's **claiming** ordinals — two different
documents, a comparison that could never be right. The fix is `system.competition_claimants`
(matcher output: which old provisions it assigned to that target), so both sides are source-side
ordinals and neither depends on which anchors happen to be sampled. The schema now requires it
whenever `competition_coverage` is present.

---

## §R5-3. The recorded inclusion probabilities were wrong

**Verdict: CONFIRMED, and simulation found a second, worse defect the criticism only hinted at.**

**Falsification attempted by enumeration.** The round-4 draw recorded
`p_region = len(selected) / len(drawable)` for every region. Simulated over 20,000 seeds on a frame
with bill A holding 10 drawable regions and B holding 80, requesting 3:

| | true P(region selected) | recorded |
|---|---:|---:|
| region in bill A | **0.202** | 0.033 |
| region in bill B | **0.013** | 0.033 |

Wrong by 6× one way and 2.6× the other, so no scale factor repairs it.

**The second defect: zero-probability strata.** Round-robin iterated `sorted(by_bill)`, a
deterministic order. When `n_regions < len(bills)` only the alphabetically-first bills could ever be
drawn — with 12 drawable bills and a 4-region request, **eight bills had P = 0**. A stratification
scheme that silently excluded most strata.

**Action — explicit quota, verified against simulation.** Each bill gets a base quota
`n_regions // n_bills`; the remainder is handed out over a **seeded shuffle** of the bills, so no
stratum is structurally excluded; a bill whose quota exceeds its supply is capped and the surplus
redistributed. Then `P(region r in bill b) = quota[b] / drawable[b]`, exactly, recorded per region
alongside `quota_by_bill` and `drawable_by_bill` so a reader can re-derive it by hand.

Simulation agreement on hand-computable frames:

| frame | request | empirical P | predicted |
|---|---:|---:|---:|
| A=10, B=80 | 3 | A 0.1507 / B 0.0187 | 0.1499 / 0.0188 |
| A=2, B=50, C=50 | 9 | A 1.000 (capped) | 1.000 |
| A=B=C=D=5 | 2 | ~0.10 each, **including C and D** | 0.100 |

The last row is the zero-probability bug, fixed and pinned by a test.

---

## §R5-4. Is `all-nodes-with-body` a complete universe?

**Verdict: PARTLY CONFIRMED. The distinction is real and was untested; the invariant holds.**

The criticism correctly separates two properties the schema had run together. Measure-independence
stops a system under evaluation defining its own denominator. It says nothing about whether the rule
can omit a true counterpart — which is a *truth-universe* question.

**Measured** (R9 §5, all 71 adjacent pairs):

```
body-less target nodes that are CONTAINERS (text-bearing descendant exists) : 7054
body-less target nodes that are LEAVES                                      :    0
production records pairing OLD-with-text -> NEW-without-text                :    0
```

**So the invariant holds.** Every body-less node is a structural container whose text lives in a
descendant the rule *does* admit, so correspondence is established at the level that carries text.
A Study-2-eligible anchor must itself have body text, and a container carries none to correspond
with.

**Action.** `all-nodes-with-body` may establish global completeness, and the invariant is asserted
by `test_body_less_target_nodes_are_always_containers` rather than assumed in prose — if a body-less
leaf ever appears the test fails and the rule must stop granting completeness. `all-nodes` stays
available for a study preferring the guarantee to the assumption, at ~8.5% more review.

The same caution round 4 applied to `element_id` applies here — this is a regularity over 34 bills,
not a theorem — but unlike that case the alternative has real cost and no benefit, so the guarded
assumption is the better trade.

---

## §R5-5. What tier A's region sweeps buy

**Verdict: PARTLY CONFIRMED. The logic is right; the conclusion is narrower than "tier A is
overpaying".**

The criticism is correct that ranking needs only `affirmed-positive`, so a region sweep is not
logically required to answer *"given that X is the counterpart, where did the retriever rank it?"*
A pairwise binary judgment on a single retrieved candidate suffices.

**What the sweep actually buys**, stated precisely because the criticism asks for precision:

1. **Positives the retrievers missed.** A pairwise pass over retrieved candidates can only ever
   confirm what was retrieved. A region sweep finds counterparts no retriever proposed, which is
   what makes a ranking dataset contain the interesting cases rather than only the easy ones.
2. **Region-local candidate recall** — a genuine diagnostic, and explicitly *not* global recall.
   §R5-A keeps that distinction; `complete-within-region` never becomes `complete-in-document`.
3. **Regression coverage across structural neighbourhoods**, which is tier A's whole purpose.

**What it does not buy**: global candidate recall. Round 4 did not claim otherwise, and the
distinction is preserved.

**Action.** No change to the tier structure. The recommendation now says explicitly that a
cheaper ranking-only dataset is available if regression breadth is dropped, and that the sweep is
paid for the first two items rather than for ranking itself. This affects the budget, not the
validity, exactly as the criticism said.

---

## §R5-6. "Amortisation" conflated reading with deciding

**Verdict: CONFIRMED.**

Judging that target node X is not anchor A's counterpart says nothing about anchor B. Reading
amortises across anchors; deciding does not. Round 4's phrasing invited the reader to divide the
161-adjudication figure by the number of anchors sharing a document, which is wrong.

**The model, with the two costs separated** (`probe_r10` §5, using the measured medians — 34
provisions in a drawable region, 161 in a target version):

| tier | anchors | documents | reads (reusable) | pairwise decisions (not reusable) |
|---|---:|---:|---:|---:|
| A regression | 200 | 20 regions | 680 | 6,800 |
| B diagnostic | 20 | 4 | 644 | 3,220 |
| C challenge | 40 | 0 | 0 | 40 |

**Deliberately not modelled: seconds per decision.** Most tier-B decisions are obvious rejections;
some are the hard cases the study exists for. Nobody has measured the distribution, and multiplying
these counts by a guessed rate would manufacture a precision this analysis does not have.

**The bipartite alternative, analysed rather than adopted.** Presenting the whole target document
once and mapping all K anchors against it has the *same* decision count and the *same* reading cost.
Its real advantage is different and was not the one round 4 imagined: sweeping one target node
against every sampled anchor is the **source-side** direction, which is exactly how
`competition_coverage` gets collected (§R5-2). Anchor-by-anchor review cannot produce it at any
level of thoroughness. So the two criticisms interact: if collision resolution is wanted, the
bipartite workflow is the one that produces it as a by-product.

---

## §R5-7. Prose/code consistency audit

**Verdict: CONFIRMED.** Every named instance was stale current-state prose, not historical context:

| location | stale | corrected to |
|---|---|---|
| document status header | "Round 2 complete" | "Round 5 complete", plus a current-machinery line |
| `pass2_schema` docstring | `coverage = {rule, eligible_total, reviewed}` | the v4 set-based block |
| PR body | "fifteen-record synthetic fixture" | the fixture's actual contents |
| PR body | adding `element_id` to the answer key is "the right invariant" | `node_ordinal` (round 4 moved identity) |

Historical passages that *describe* superseded rules — "v3 asked `reviewed >= eligible_total`" — are
correct as history and were left alone; the audit's job was to separate the two, not to erase the
record.

The document header now carries a **current-machinery line** (schema version, oracle names,
identity, frame module) so the single most drift-prone paragraph states the current state
explicitly rather than leaving a reader to infer it from four rounds of narrative.

---

## §R5-A. Coverage-proof contract

| oracle | eligible universe derived from | reviewed membership recorded how | establishes | fails when |
|---|---|---|---|---|
| `suggested-list` | — (no universe) | — | `affirmed-positive`, `affirmed-negative` | always, for any completeness claim |
| `region-exhaustive` | the named `region_id` | not recorded per node | + `complete-within-region` | `region_id` absent |
| `document-exhaustive` | `COVERAGE_RULES[rule]` applied to the frozen target parse, pinned by `target_source_sha256` + `target_parser_commit` | `coverage.reviewed_ordinals` | + `complete-in-document` **iff set equality** | reviewed set ≠ eligible set; stray ordinal; missing parse identity; non-allowlisted rule |
| *(reverse sweep)* | `COVERAGE_RULES[rule]` applied to the frozen **source** parse | `competition_coverage.reviewed_ordinals` | `complete-source-side` | set inequality; parse mismatch with the anchor; missing `system.competition_claimants` |

Mechanically: `establishes(truth, "complete-in-document")` returns true only when
`"document-exhaustive" in truth.oracles` **and** `set(coverage.reviewed_ordinals) ==
set(coverage.eligible_ordinals)`. `eligible_ordinals` is generated from the parse; no reviewer or
client supplies it.

---

## §R5-B. Assignment estimand

**Two metrics, never blurred.**

| | `assignment_per_anchor` | `collision_resolution` |
|---|---|---|
| question | did the system assign exactly this anchor's true counterpart set? | did the global assignment resolve this contested node correctly? |
| OLD-side truth needed | the sampled anchor only | **every** provision claiming the target node |
| NEW-side truth needed | `complete-in-document` for this anchor | the target node's identity |
| oracle | `document-exhaustive` (target sweep) | reverse sweep → `complete-source-side` |
| measurable today | **yes** | **only for groups carrying `competition_coverage`** |
| on the fixture | n=12, accuracy 0.50 | 1 group scorable, 2 refused, accuracy 0.00 |

When no record carries a reverse sweep the metric reports **NOT MEASURABLE** with its reason,
rather than scoring the contested nodes visible in the dataset. That visibility is a fact about
sampling, not about legislation.

---

## §R5-C. Sampling probability derivation

**Algorithm.** (1) Enumerate drawable regions (≥ `MIN_REGION_ANCHORS` anchors) from the canonical
old-side frame. (2) Group by bill; `n_b` = that bill's drawable count. (3) Allocate quotas: base
`n_regions // n_bills` each, remainder distributed over a **seeded shuffle** of bills, each capped at
`n_b` with surplus redistributed. (4) Sample `k_b` regions uniformly without replacement within each
bill. (5) Within each selected region, take every anchor or draw `M` uniformly without replacement.

**Probabilities.** `P(region r ∈ bill b) = k_b / n_b`. `P(anchor a ∈ region r) = 1` if all anchors
are taken, else `M / |r|`. `P(a) = (k_b / n_b) × P(a | r)`. All three are recorded per anchor, and
`quota_by_bill` / `drawable_by_bill` are persisted so any of them can be re-derived by hand.

**`n_regions < n_bills`:** every bill retains positive probability, because the remainder is
allocated over a shuffled order rather than a sorted one. **Unequal regions-per-bill:** handled by
the per-bill denominator `n_b`; a small bill is capped at its supply and the surplus redistributed
so the requested sample size is still met. Both cases are tested against hand-computable frames.

---

## §R5-D. Capability model (v4, exhaustive)

| proposition | granted by | additional condition |
|---|---|---|
| `affirmed-positive` | any oracle | per-candidate-binary judgment |
| `affirmed-negative` | any oracle | per-candidate-binary judgment |
| `complete-within-region` | `region-exhaustive`, `document-exhaustive` | `region_id` present |
| `complete-in-document` | `document-exhaustive` | **target** coverage set equality |
| `complete-source-side` | *(reverse sweep; no oracle name)* | **source** coverage set equality |

---

## §R5-E. Tier cost model

See the table in §R5-6. Reads are reusable across anchors sharing a document; pairwise decisions are
not. Seconds per decision is deliberately unmodelled.

---

## §R5-F. Contract fixture

19 records. Rounds 1–4 shapes plus round 5's: `a18-count-matches-set-does-not` (equal cardinality,
wrong membership), `a19-target-complete-source-unknown` (an unsampled competitor), and
`a15`'s reverse sweep, which is the only thing that makes any collision group scorable. The
duplicate-identity and stray-ordinal cases are constructed in tests, because they must fail
validation.

Every guard is proven by removal: the count rule admits `a18` where set equality refuses it;
stripping `competition_coverage` makes collision resolution unmeasurable while leaving per-anchor
assignment untouched (proving they are genuinely separate estimands); restoring the content-hash
join improves two metrics; the old corpus-wide probability differs from the per-stratum one on the
real frame.

---

## §R5-G. Blocker table

**1 — required to merge this methodology review**

| item | state |
|---|---|
| Prose/code consistency audit (§R5-7) | **done** |
| Tier cost model separating reading from deciding (§R5-6) | **done** — `probe_r10` §5 |
| Coverage-universe invariant measured and guarded (§R5-4) | **done** — R9 §5 + test |

**2 — required before ANY human annotation**

| item | state |
|---|---|
| Completeness proven by set membership (§R5-1) | **done** — schema v4 |
| Assignment estimands separated; `complete-source-side` (§R5-2) | **done** — schema v4 + evaluator |
| Identity, oracle coverage, `affirmed-negative` (rounds 3–4) | **done** |
| Adjudicate the three drifted observations | **OPEN — packet ready, not adjudicated** |
| Provenance on the answer key (`text_sha256`, `source_sha256`, `node_ordinal`) | **OPEN — Will's call** |
| Re-mine the financial stratum without signal-conditioned discovery | **OPEN — not started** |
| Apply the Study 1 premise corrections to `paper.md` / `pass2-protocol.md` | **OPEN — proposed, not applied** |
| Decide whether collision resolution is in scope (it needs the reverse sweep) | **OPEN — Will's call** |

**3 — required before the real sample draw**

| item | state |
|---|---|
| Correct inclusion probabilities (§R5-3) | **done** — quota-based, simulation-verified |
| Choose tier A/B/C scale, `n_regions`, `anchors_per_region`, seed | **OPEN — Will's call** |
| Freeze the corpus manifest digest the draw is against | **OPEN** |

**4 — required before held-out evaluation**

Held-out split at the region level; `challenge_requires` declared for every existing challenge pool;
reporting layer with cluster-aware intervals.

**5 — deferred Study 4**

Theory rewrite; directional-variant benchmark; structural confirmers; re-running the frozen IDF
ablation after re-adjudication (variants frozen, **do not re-tune**).

---

## §R5 — Study 2 go / no-go

| # | question | answer |
|---|---|---|
| 1 | Can tier A validly measure ranking? | **Yes.** Needs `affirmed-positive`, which every oracle grants under per-candidate-binary judgment. |
| 2 | Can tier B validly measure candidate recall? | **Yes, for anchors with proven set coverage** — and only those; others are refused by name. |
| 3 | Can tier B validly measure per-anchor diff correctness? | **Yes**, on the same population. |
| 4 | Can the current dataset measure global assignment / collision resolution? | **No** — unless a reverse sweep is collected. The evaluator reports NOT MEASURABLE rather than a number. |
| 5 | Can tier C validly measure its named challenge claims? | **Yes**, for pairwise claims via `affirmed-negative`; absence claims still need document completeness. |
| 6 | Can any tier estimate operational prevalence? | **No.** Not a probability sample of any defined population, and the proxy ICC spread (0.058–0.700) means precision is a sensitivity range, not a measurement. |
| 7 | Does `complete-in-document` derive from actual set coverage? | **Yes** — `set(reviewed_ordinals) == set(eligible_ordinals)`, with the eligible set generated from the frozen parse. |
| 8 | Are the recorded inclusion probabilities mathematically correct? | **Yes**, now: `k_b / n_b` per stratum, verified against simulation on hand-computable frames. |
| 9 | What still requires human judgment? | §R5-G tier 2 and 3: the three drifted observations, answer-key provenance, the financial re-mine, the Study 1 wording corrections, whether collision resolution is in scope, and the tier scale + seed. |
| 10 | Should Study 2 labeling remain gated? | **Yes.** Eight open items, every one a judgment call rather than an implementation task. |

---

## §R5 — probes and modules changed

| file | decides | headline |
|---|---|---|
| `pass2_schema.py` *(v4)* | §R5-1, §R5-2 | coverage as sets; `complete-source-side`; `system.competition_claimants` |
| `eval_pass2.py` *(changed)* | §R5-2 | `assignment_per_anchor` + `collision_resolution`; NOT MEASURABLE reporting |
| `study2_frame.py` *(changed)* | §R5-3 | quota allocation; per-stratum probabilities; no zero-probability strata |
| `probe_r9_node_identity.py` *(§5 added)* | §R5-4 | 7,054 body-less containers, 0 leaves, 0 cross-boundary pairings |
| `probe_r10_sampling_design.py` *(§5 added)* | §R5-6 | reads vs pairwise decisions, per tier |


---
---

# §R6 — Sixth adversarial review (round 6)

**Target: does schema v4 enforce the independence it claims, or does it only store fields saying
so?** Six criticisms, all of them survived. The round's standard:

> Ground truth is not independent merely because its internal fields agree with one another. The
> universe those fields describe must itself come from an independently verifiable source.

That is the same defect this programme has now found six times, each time one field further out:
the matcher chose the pairs → the retrievers chose the candidate list → a bounded region chose the
search area → "the reviewer searched" stood in for coverage → a COUNT stood in for the reviewed set
→ **the record's own statement of the universe stood in for the universe.**

| # | criticism | verdict | what changed |
|---|---|---|---|
| 1 | `eligible_ordinals` is trusted input | **CONFIRMED** | universe re-derived from the parse; completeness needs the corpus |
| 2 | probabilities are conditional, not unconditional | **CONFIRMED** | both computed and named; unconditional derived exactly |
| 3 | `all-nodes-with-body` may not prove global completeness | **CONFIRMED** | only `all-nodes` may |
| 4 | `competition_coverage.target_ordinal` has no target identity | **CONFIRMED** | full target identity required |
| 5 | stale current-state prose remains | **CONFIRMED** | audited; see §R6-F |
| 6 | "all remaining items are judgment calls" was wrong | **CONFIRMED** | re-split in §R6-G |

---

## §R6-1. Completeness still rested on a claim the artifact made about itself

**Verdict: CONFIRMED.**

**Falsification attempted.** The criticism offers five exits: is `eligible_ordinals` generated by one
authoritative function; can the UI modify it; does validation reconstruct it; are the hash and
parser fields checked against a real parse; can a hand-edited but self-consistent block pass? The
answers were: no generator existed, nothing reconstructed it, the identity fields were required
strings that nothing compared against anything, and yes — executed:

```
eligible_ordinals = [5]      # the real document has 21 nodes
reviewed_ordinals = [5]
-> validation ACCEPTED, establishes complete-in-document = True
-> wrong target_source_sha256 ('a'*64): also ACCEPTED
```

Round 5 moved the trust from the count to the universe. It did not remove it.

**Action — the universe comes from the corpus, and completeness needs the corpus present.**

* `study2_frame.derive_eligible_ordinals(target_xml, rule)` is the one authoritative generator.
* `study2_frame.verify_coverage_against_corpus(records, resolve)` re-derives every coverage
  universe from the parse named by `target_version` + `target_source_sha256` + `target_parser_commit`
  and returns the records that do not match.
* `pass2_schema.mark_verified_universes` stamps `universe_verified` from that result, and
  `validate_dataset` **rejects** a record that carries the flag itself — an authored flag would
  restore exactly the self-certification it replaces.
* `eval_pass2.evaluate(records, verifier=...)`: **without a verifier, no record can establish
  `complete-in-document` or `complete-source-side`.** An evaluation run with no corpus reports the
  three completeness metrics as empty and names the reason.

That last point is the strongest form the contract can take: you cannot compute candidate recall,
per-anchor assignment or diff correctness without the corpus present to check what the reviewer was
supposed to have covered. Ranking and the pairwise challenge strata are unaffected, because neither
needs a universe.

Also fixed, found by a contract test: verification stamped the caller's records in place, so a
dataset that validated would fail validation after being evaluated once. `evaluate` now stamps a
copy.

---

## §R6-2. The recorded probabilities were conditional

**Verdict: CONFIRMED. The criticism's worked example reproduces exactly.**

**Falsification attempted by exhaustive enumeration**, on the frame the criticism proposes — three
bills of two regions each, requesting one region:

```
quota allocations observed : A=1 in 33.6% of seeds, B=1 in 33.1%, C=1 in 33.3%
empirical P(any region)    : 0.1648 - 0.1692        (true value 1/6 = 0.1667)
what v5 recorded           : 0.5 for whichever bill won the quota, 0 for the others
```

Quota allocation is itself random, so `k_b / n_b` is conditional on the realised allocation. v5's
field was named `p_region` and described as an inclusion probability, which it is not.

**Action — Option A, both quantities computed and honestly named.** The unconditional probability is
`E[k_b] / n_b`, and `expected_quota()` obtains `E[k_b]` exactly by one of two routes, refusing
rather than approximating when neither applies:

| route | when | how |
|---|---|---|
| closed-form | no bill can be capped (every supply ≥ base+1) | the remainder is an SRS of R bills from B, so `E[k_b] = base + R/B` |
| exact-enumeration | capping possible and ≤ 8 bills | average the realised quota over every permutation of the remainder shuffle |
| unavailable | otherwise | reported as `None` with a reason — a Monte-Carlo "probability" in a design document gets quoted later as exact |

Verified against the enumeration above (closed-form gives exactly 1/6) and against the capping case
`{A:2, B:50, C:50}` requesting 9, where enumeration gives `E[k_A] = 2.0` (capped at supply) and
`E[k_B] = 3.5`.

Fields are now named for what they are: `p_region_given_quota` / `p_inclusion_given_quota` versus
`p_region_unconditional` / `p_inclusion_unconditional`, with `expected_quota_by_bill` and
`expected_quota_method` persisted so both can be re-derived by hand. On the real frame the two
differ by 1.5× (0.00463 vs 0.00309), so the distinction is not academic.

**Semantic honesty, as the criticism asks:** the unconditional figure IS the inclusion probability
for the whole randomized design. Study 2 still promises no weighting and no population inference, so
neither figure is used as a sampling weight — but the number reported as an inclusion probability is
now the one that is.

---

## §R6-3. `all-nodes-with-body` may not prove global completeness

**Verdict: CONFIRMED. The criticism identifies an inadmissible step in round 5's own evidence.**

Round 5 justified the rule with two findings: every body-less node in this corpus is a container
with a text-bearing descendant, and **production never pairs old-with-text to new-without-text**. The
second is inadmissible, and the criticism is right to say so: **the matcher is the object under
evaluation**, so what it currently pairs cannot license an assumption about what a human would
legitimately judge.

**Falsification attempted.** Is there matcher-independent evidence that a body-less node can never be
correspondence-bearing? Not from the parser or the XML: a body-less node is a container by
construction, but "the section's text moved into its subsections" is exactly the segmentation drift
this programme identified in round 2, and a reviewer might reasonably record `Section X → Section X`
as a structural continuation, or `Section X → subsections (a)+(b)` as one-to-many. Nothing in the
schema defines the estimand narrowly enough to exclude that, and inventing such a definition now to
justify a 9% saving would be reasoning backwards.

**Action — Option 1.** `DOCUMENT_COMPLETENESS_RULES = ("all-nodes",)`. `all-nodes-with-body` stays in
`COVERAGE_RULES` for region-scoped work, where no global claim is made. Measured cost: ~8.5% more
nodes in a target sweep, on a tier that is already the expensive one — which is the right price for
removing an assumption from the ground-truth contract rather than carrying it forward.

---

## §R6-4. The reverse sweep's target was a bare ordinal

**Verdict: CONFIRMED, and it is round 5 breaking round 4's own invariant.**

`competition_coverage` carried `target_ordinal` with `source_source_sha256` / `source_parser_commit`
scoping the OLD document being swept — and nothing scoping the NEW target. Ordinal 602 exists in
every version of every bill, so a reverse sweep for one target could certify collision truth for
another. Round 4 established `(source_sha256, parser_commit, node_ordinal)` as the identity
invariant; round 5's new field violated it two rounds later.

**Action.** `competition_coverage` now requires `target_version`, `target_source_sha256`,
`target_parser_commit` and `target_ordinal` — a full observation identity — plus `source_version`
for the reverse side. The validator additionally rejects a block naming the same parse as both
source and target, since a reverse sweep compares OLD provisions against a NEW node.

**Classification:** this is a schema fix, not a tier A/B blocker, because collision resolution is
not yet in scope (§R6-G). It is fixed now rather than deferred because the cost was one field and
the alternative is carrying a known aliasing defect into a future study.

---

## §R6-5. Stale current-state prose, again

**Verdict: CONFIRMED.** Every item the criticism named was real:

| location | stale | corrected |
|---|---|---|
| `pass2_schema.py` docstring | "(v3)", "v3 removes it by making completeness a COUNT", a count-based coverage block | rewritten for v5 |
| `eval_pass2._key` | identity described as `element_id` | `node_ordinal`, with a note on why |
| review document | "It has four layers" while describing five rounds | six layers |
| review document header | schema `pass2-anchor-v4` | v5, plus the completeness rule |
| PR body | "fifteen-record fixture"; `element_id` called "the right invariant" | corrected in round 5 |

Two of these were introduced by the very rounds that named stale prose as a finding. The document
header now carries an explicit **current-machinery line**, which is the one paragraph a future
reader or agent will treat as authoritative.

---

## §R6-6. "All remaining items are judgment calls" was wrong

**Verdict: CONFIRMED.** Round 5's closing claim was made while criticisms #1–#4 were live
implementation defects. The corrected split is §R6-G, which separates work an agent can finish from
decisions that need Will from adjudication that needs legislative judgment.

---

## §R6-A. Coverage trust chain

| arrow | produced by | trusted or verified | what detects corruption |
|---|---|---|---|
| source XML → source hash | corpus reader (`hashlib`) | **verified** — recomputed at verification time | `verify_coverage_against_corpus` compares against `target_source_sha256` |
| source hash → parse | `normalize_bill` at `parser_commit` | **verified** — the parse is re-run | a changed parser produces a different universe |
| parse → eligible identities | `derive_eligible_ordinals(xml, rule)` | **generated, never authored** | `universe_verified` is stamped only from this |
| coverage rule | authored, from `DOCUMENT_COMPLETENESS_RULES` | **verified** — allowlist, and the universe is re-derived under the named rule | `test_only_all_nodes_may_establish_global_completeness`; rule mismatch changes the derived set |
| eligible → reviewed identities | the human/UI | **trusted, and correctly so** — this is the judgment being collected | out-of-universe ordinals rejected at validation |
| reviewed vs eligible → completeness | `_set_covers` + `universe_verified` | **verified** | set inequality, missing stamp, or a hand-set stamp all refuse |

The only trusted link is the one that *should* be trusted: which nodes the reviewer says they
adjudicated. The universe they were judged against comes from the corpus.

---

## §R6-B. Corruption tests

| corruption | result |
|---|---|
| truncated eligible set (self-consistent) | **refused** — `a21-fabricated-universe`, and by parametrized mutation |
| wrong-but-well-formed source hash | **refused** |
| unresolvable / wrong version | **refused** |
| wrong coverage-rule output | **refused** |
| target/source identity mix-up in a reverse sweep | **rejected at validation** |
| hand-set `universe_verified` | **rejected at validation** |
| no verifier supplied at all | **every completeness metric empty**, reason reported |
| correct derived universe | **granted** |

Each is proven to change an outcome, not merely to exist.

---

## §R6-C. Sampling probability proof

Enumerated frame: three bills × two regions, request 1. Sample space is the 3 quota allocations ×
2 within-bill choices = 6 equally likely outcomes, so every region has unconditional probability
**1/6**. Empirical over 6,000 seeds: 0.1648–0.1692. `expected_quota` closed-form: exactly 1/6.

| field | meaning |
|---|---|
| `p_region_given_quota`, `p_inclusion_given_quota` | **conditional** on the realised quota allocation |
| `p_region_unconditional`, `p_inclusion_unconditional` | **unconditional** design probability — the inclusion probability |
| `quota_by_bill`, `drawable_by_bill`, `expected_quota_by_bill`, `expected_quota_method` | inputs, so both are re-derivable by hand |

`n_regions < n_bills` is handled by the seeded remainder shuffle (every bill retains positive
probability); unequal supplies by the per-bill denominator; capping by redistribution, with the
expectation then obtained by exact enumeration rather than the closed form.

---

## §R6-D. Coverage rule decision — **Option 1**

`all-nodes` is required for `complete-in-document`. `all-nodes-with-body` remains valid for
region-scoped propositions. Rationale in §R6-3: the evidence for the narrower rule leaned on the
behaviour of the system under evaluation, and ~8.5% extra review is a low price for removing an
assumption from the ground-truth contract.

---

## §R6-E. Collision identity contract

| element | identity |
|---|---|
| contested target node | `target_version` + `target_source_sha256` + `target_parser_commit` + `target_ordinal` |
| source-side universe | `source_version` + `source_source_sha256` + `source_parser_commit` + `eligible_ordinals` |
| claimants (truth) | `claiming_ordinals`, required ⊆ the source eligible universe |
| claimants (system) | `system.competition_claimants`, source-side ordinals |

No bare ordinal appears on either side, and the two parses must differ.

---

## §R6-F. Current-state consistency audit

See the table in §R6-5. Historical passages describing superseded rules were left intact; only
current-state descriptions were changed.

---

## §R6-G. Blocker table

**1 — merge blockers**

| item | state |
|---|---|
| Current-state prose audit (§R6-5) | **done** |
| Probability fields named for what they are (§R6-2) | **done** |

**2 — implementation before labeling** *(agent can complete; none outstanding)*

| item | state |
|---|---|
| Universe re-derived from the parse; completeness needs the corpus (§R6-1) | **done** |
| `all-nodes` required for global completeness (§R6-3) | **done** |
| Full target identity in reverse sweeps (§R6-4) | **done** |
| Unconditional inclusion probability (§R6-2) | **done** |
| Re-mine the financial stratum without signal-conditioned discovery | **OPEN — agent can do this; not started** |
| Wire the real corpus verifier into the labeling pipeline (`resolve` callback) | **OPEN — agent can do this once the tier scale is chosen** |

**3 — human decisions before labeling** *(need Will)*

| item |
|---|
| Whether collision resolution is in Study 2 scope (it needs a reverse sweep per contested node) |
| Tier A/B/C scale: regions, anchors per region, how many document-complete anchors |
| Whether to accept the ~8.5% extra review that `all-nodes` costs, or shrink tier B instead |
| Whether to add provenance fields to `tests/data/similarity_labels.json` (rewrites a committed fixture) |
| Whether to apply §E's wording corrections to `paper.md` / `pass2-protocol.md` |

**4 — human legislative adjudication** *(nobody else can do these)*

| item |
|---|
| The three drifted Study 1 observations (blind packet ready) |
| The Study 2 labels themselves |

**5 — pre-draw**

Freeze the corpus manifest digest; choose the seed; run the draw.

**6 — pre-held-out**

Region-level held-out split; `challenge_requires` declared for every existing challenge pool;
cluster-aware reporting layer.

**7 — deferred Study 4**

Theory rewrite; directional-variant benchmark; structural confirmers; re-running the frozen IDF
ablation after re-adjudication (variants frozen, **do not re-tune**).

---

## §R6 — final answers

| # | question | answer |
|---|---|---|
| 1 | Does `complete-in-document` derive from the actual frozen parse? | **Yes.** The universe is re-derived by `derive_eligible_ordinals` and compared; without a verifier no record can claim it. |
| 2 | Can a fabricated eligible universe pass? | **No.** `a21` is internally perfect and is refused. |
| 3 | Are sampling probabilities unconditional or conditional? | **Both are recorded and named.** The unconditional one is exact (closed-form or enumeration) and is the inclusion probability. |
| 4 | Which coverage rule will tier B use? | **`all-nodes`.** Only it may establish global completeness. |
| 5 | Is global collision resolution in Study 2 scope? | **Not yet — Will's call.** It needs a reverse sweep per contested node. The machinery exists and reports NOT MEASURABLE until that truth is collected. |
| 6 | Is target identity in reverse sweeps fully scoped? | **Yes.** Full observation identity on both sides, and the two parses must differ. |
| 7 | What implementation work remains? | Re-mine the financial stratum; wire the real corpus verifier into the labeling pipeline. Both are agent work. |
| 8 | What decisions require Will? | §R6-G tier 3: collision-resolution scope, tier scale, the `all-nodes` cost, answer-key provenance, the wording corrections. |
| 9 | What requires human legislative judgment? | The three drifted observations, and the Study 2 labels. |
| 10 | Should labeling remain gated? | **Yes.** Tier 3 and tier 4 are both non-empty. |
| 11 | Should PR #554 be draft or ready? | **Ready is defensible now**, on the round-6 blocker table: no merge blockers remain, and the outstanding items are follow-on work rather than defects in what this PR contains. See the note below. |
| 12 | New commit SHA | `see the commit for this round` |

**On (11), stated plainly because the state changed under this review:** the PR was marked
ready-for-review by Will at 21:24Z on 2026-08-06, between rounds 4 and 5. Round 5 left it alone
rather than reverting a deliberate action. Round 6's table supports that: the merge blockers are
closed, and everything remaining is either follow-on implementation or a decision that does not
change the contents of this PR. **Labeling remains gated regardless of the PR's state** — those are
separate questions, and conflating them is what would let a merge read as permission to start.

---

## §R6 — probes and modules changed

| file | decides | headline |
|---|---|---|
| `study2_frame.py` | §R6-1, §R6-2 | `derive_eligible_ordinals`, `verify_coverage_against_corpus`, `expected_quota` |
| `pass2_schema.py` *(v5)* | §R6-1, §R6-3, §R6-4 | `universe_verified`, `DOCUMENT_COMPLETENESS_RULES`, full target identity |
| `eval_pass2.py` *(changed)* | §R6-1 | `evaluate(records, verifier)`; completeness refused without a corpus |


---

# §R6-FU — Round 6 follow-up and closure

Not a seventh round. Two substantive gaps found by re-reading the pushed code at `036f6f1`, plus
consistency work. Both gaps are the same shape as everything this programme has found: **a field
that records an intention rather than a fact.**

## 1. Parser commit — **CONFIRMED**

**Falsification attempted, executed against the pushed code:**

```
change ONLY target_parser_commit to 'b'*40 (well-formed, different)
-> universe_verified = True
-> record NOT refused by any completeness metric
-> the only verification failure reported was the unrelated a21
```

`verify_coverage_against_corpus` resolved the XML, checked its SHA, and re-derived the universe with
whatever `normalize_bill` happened to be checked out. It never looked at `parser_commit`. So the
field was decorative — in a programme whose round-2 finding was that a parser change silently
invalidated three observations.

**Fix — the frozen-revision contract, made executable.**

`study2_frame.parser_revision()` returns a SHA-256 over the source of `deltatrack.bill_tree` and
every `deltatrack.*` module it transitively imports, resolved by AST. Not a git commit: that moves
when documentation changes and does *not* move for an uncommitted edit to the parser. Not a
declared constant: it is derived from the code under evaluation.

`verify_coverage_against_corpus` now rejects any coverage block whose `*_parser_commit` is not that
revision. The contract is the weak, sufficient one Will proposed — Study 2 observations are produced
and verified only against one frozen parser revision — rather than historical-parser execution
machinery.

Deliberately over-broad: the transitive set may include a module that cannot affect node emission,
so an unrelated edit forces re-verification. That direction costs work; the other silently certifies
a universe derived by different code.

**Tests.** `test_a_wrong_parser_commit_cannot_establish_completeness` (same XML, same ordinals,
wrong commit → refused by all three completeness metrics) and
`test_the_parser_revision_is_derived_from_the_code_not_declared` (edits `bill_tree.py`, asserts the
revision moves, restores it, asserts it returns).

## 2. Reverse-sweep target identity — **CONFIRMED, and the machinery is now DEFERRED**

Two defects, both real:

* `collision_resolution` keyed proven groups on `(anchor.source_sha256, anchor.parser_commit,
  target_ordinal)` — the OLD side plus a bare ordinal. Reverse truth for target A:73 was reachable
  for B:73.
* the corpus verifier checked only the **source** universe of a `competition_coverage` block. The
  contested target's identity was never verified at all — in either the real verifier or the
  synthetic one.

**Fix.** The key is now `(target_source_sha256, target_parser_commit, target_ordinal)`. Both
verifiers check the reverse sweep's target identity as well as its source universe, and the real one
additionally checks that `target_ordinal` is in range for the named target parse.

**Scope — deferred, per Will's decision.** Tiers A/B/C collect no reverse sweeps.
`collision_resolution` now reports `study2_scope: "deferred"` and
`validation_status: "not fully validated…"`, and is **removed from `contract_check`** so it cannot
gate the start of the other tiers. The machinery is retained because it is the correct shape for the
question, not because it is ready.

Stated plainly rather than implied by silence: what is proven is the direction argument, the
target-identity key, and that a group without source-side truth is refused. What is **not** proven
is the reverse-sweep path on real corpus data, and `claiming_ordinals` have no independent check
beyond being a subset of the swept universe.

**Test.** `test_reverse_truth_for_one_target_cannot_certify_another` moves the sweep's target
document while holding the ordinal fixed, and asserts the record is rejected and the group
disappears.

## 3. Current-state prose

| location | stale | corrected |
|---|---|---|
| `eval_pass2` docstring | "3 assignment … for every anchor in the collision group" (the pre-v4 unsplit estimand) | 3a per-anchor + 3b collision, with 3b marked deferred |
| fixture `_about` | "schema v4", round-5 shape list | v5, round-6 shapes, and the published universes/revision |
| `probe_r9` §5 conclusion | "`all-nodes-with-body` MAY establish global completeness" | overruled; counts stand, inference does not |
| review header | schema v4, "four layers" | v5 → v6 machinery line, six layers |

Historical attributions ("Round 5 pointed out…") were left intact. Only text purporting to describe
the **current** machinery was changed.

## 4. Real-verifier integration — implemented, not deferred

`eval_pass2.evaluate_study2_dataset(path)` is the one canonical path for a real dataset. It wires
`corpus_roots` → `verify_coverage_against_corpus` → `evaluate`, and **raises `ProvenanceError`**
when the corpus is absent or the dataset's declared parser revision is not the checked-out one.

It raises rather than returning a degraded result because "the metrics came out empty" and "the
metrics could not be computed" look identical in a report and mean very different things. This
closes the gap Will named: real Tier B evaluation no longer depends on a caller remembering the
right callback. Independent of sample size, so it is implemented now.

**Test.** `test_the_canonical_real_dataset_path_fails_closed`.

## 5. Blocker table

**Merge blockers** — none. Both follow-up gaps are closed; prose is consistent.

**Agent implementation before labeling**

| item | state |
|---|---|
| Parser provenance verified (§1) | **done** |
| Reverse-sweep target identity + deferral (§2) | **done** |
| Canonical fail-closed evaluation path (§4) | **done** |
| Re-mine the financial stratum without signal-conditioned discovery | **OPEN — agent work, not started** |

**Decisions requiring Will**

| item |
|---|
| Tier A/B/C scale: regions, anchors per region, how many document-complete anchors |
| Whether to accept the ~8.5% extra review `all-nodes` costs, or shrink tier B instead |
| Whether to add provenance fields to `tests/data/similarity_labels.json` (rewrites a committed fixture) |
| Whether to apply §E's wording corrections to `paper.md` / `pass2-protocol.md` |
| Freeze the corpus manifest digest and seed, then run the draw |

**Human legislative judgment**

| item |
|---|
| The three drifted Study 1 observations (blind packet ready, unadjudicated) |
| The Study 2 labels themselves |

## 6. Closing note on the audit

The standing gates stay: universe verification fails closed without a corpus, the parser revision is
derived from the code, the sampling frame cannot import the matcher, and every guard is pinned by a
test that removes it and watches the number move. Those exist so the methodology remains falsifiable
by whoever comes next.

The audit itself stops here. Six rounds found six instances of one pattern — a dependency renamed
rather than removed — and the last two found it only in fields that had just been added to fix the
previous instance. That is the expected tail of a converging process, not evidence of a seventh
layer waiting. The remaining work is labeling-budget decisions and one mining task, none of which
turn on another review pass.
