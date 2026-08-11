# Pass 2 Protocol — Expand and Re-Stratify the Provision-Matching Labeled Dataset

**Status:** Miners built + verified (Pass-2a, 2026-07-11); **human labeling still gated** on
Will's review of this protocol and of the mined candidate samples. The automated candidate
mining is done; no pair is labeled or frozen into the fixture until Will approves.
**Context:** Study 2 of the provision-matching program (DeltaTrack #203, blocking #170; epic
#175). Prerequisites and the numbers it builds on are in `paper.md` §8–§10 and memory note
`project_issue_56_similarity_thresholds` (AUTHORITATIVE UPDATE block). This document is the
labeling protocol §9 called for.
**Date:** 2026-07-10 (draft); 2026-07-11 (Pass-2a update block below).

---

## 0. Pass-2a update — corpus census supersedes the "17-bill hard limit" (2026-07-11)

The draft below was written against the curated 31-directory `bills/` set, before the wider
`bills_corpus/` mining pool was assembled. A census of that pool (reproducer:
`probes/mine_idf.py` + the census in the #203 work log) changes two load-bearing premises. This
is a gap the draft could not have closed — the pool did not exist when it was written — not an
error in it. What changed:

- **The mining pool is corpus-wide, not 17 bills.** `bills_corpus/` holds **2,784 parseable
  multi-version bills** (1,822 `hr` + 962 `s`; the 177 unparseable are joint/concurrent
  resolutions whose XML body `normalize_bill` does not recognize). **1,884** produce ≥1
  matched-changed decision on their first version pair alone (≥5,191 modified decisions, a lower
  bound). The pool is **disjoint** from the 17 curated appropriations bills and is broad
  *general legislation*, not appropriations.
- **Cross-bill-type coverage is now available**, not deferred. §3's "cross-type generalization
  cannot be measured in Pass 2" was true of `bills/`; it is false of `bills_corpus/` (both
  chambers, many subjects). And ≥11 corpus bills show consolidation-scale churn (NDAAs etc.) —
  candidate *second* consolidation-bearing bills that could give consolidation a held-out
  counterpart §6 says it lacks (needs validation before use).

**What this pass built (Pass-2a, automated half — the two priority strata):**
`probes/mine_idf.py` (shared rarity model → `idf_cache.json`), `probes/mine_common.py`
(candidate schema §4 + the three measures, stored analysis-only), and the two priority miners:
- `mine_high_containment_different.py` → **80 candidates** (quota 30). Cross-bill short(cited)→
  long negative control, the §8.2 false-keep mode the 12-pair set cannot test. Split: **30 dev /
  17 held-out** (33 cross-line pairs excluded, §6). ~1,330 such pairs exist at containment ≥ 0.70
  corpus-wide — the false-keep mode is abundant, confirming §6.4 at scale.
- `mine_consolidation.py` → **51 candidates** (quota 25), all in many-to-one groups (119-hr-1
  v3→v4). Reproduces §6.4 (493 removed, ~261 repaired, 41 many-to-one targets, max fan-in 29).
  Dev-only (§6). `assign_split.py` freezes the by-bill split.
- `mine_financial_lines.py` → **80 candidates** (priority stream, added per Will 2026-07-11 —
  appropriations financial tables are the primary value). Two regimes over the 17 approps bills,
  all adjacent pairs: `amount-edit-kept` (modified financial nodes, amounts changed — 384 exist,
  the "same, amount edit" anchor) and `amount-edit-split` (removed↔added financial re-pairing —
  the false-split an amount swap causes; 34 found, mostly 119-hr-1). Split: **65 dev / 15
  held-out**. This is the §7 word-overlap regime, distinct from the containment strata.

**Decisions Will ruled (2026-07-11):**
- **Estimation-set scope = (A)+cross-type slice.** Appropriations is the *headline* deployment
  precision/recall (primary focus, financial tables specifically); general-legislation (the hr/s
  bills that parse in `bills_corpus/`) is a *secondary* cross-type generalization number,
  reported separately. Approps stays primary but the differ is meant to work across bill types,
  so cross-type is a real (secondary) acceptance concern, not merely deferred to Study 3.
- **Financial tables = a first-class priority stream** (the `mine_financial_lines.py` above), not
  the buried "amount-only edit" fill of the draft §3.
- **Continuing-resolution / other-document-type coverage is tracked separately in DeltaTrack
  #201** (Parser: handle joint/concurrent resolutions), NOT re-filed here — CRs are enacted as
  H.J.Res. and #201 already measures the 0/57 hjres parse gap with the root cause. #203's
  cross-type/CR *estimation* is therefore **blocked-by #201** for the resolution family; the
  cross-type estimation proceeds on the hr/s bills that parse today, with CR coverage documented
  as pending #201.

**Labeling toolchain (built 2026-07-11 — supersedes §8's solo-labeler assumption).** Labeling is
a mixed technical/non-technical CivicTech team (3-4 reviewers, possibly one), no server, labels
returned as files. The pipeline decouples the immutable candidate pool from labels so multiple
reviewers and future candidate additions never clobber each other (candidate `id`s are content
hashes, so re-mining is idempotent and only new pairs appear):
- `make_worklist.py` → blind entries (scores stripped, §5); `make_assignments.py <names...>` →
  disjoint shards + a stratified ~24-item **overlap set labeled by everyone** (real
  inter-annotator agreement, not solo-plus-LLM); only new ids are assigned on re-run.
- `make_form.py <reviewer>` + `form_template.html` → a **self-contained HTML form** per reviewer
  (no install; one card at a time; neutral question, never the stratum name; rationale forced on
  medium/low confidence; localStorage autosave; exports `labels_<name>.json`).
- `merge_labels.py` → joins the returned files, reports **per-stratum Cohen's kappa** (pooling
  across the different label spaces would trigger the kappa paradox) + raw agreement on the
  overlap, and flags disagreements as `needs_adjudication` for Will's final ruling (§8). The LLM
  second opinion writes the same file shape and is reported separately — a disagreement-flagger,
  never a vote in the human agreement number (§8 correlated-error caveat).

This does **not** block the challenge strata already built (their split is independent). §3 and
§6 below are annotated inline where the census supersedes them.

---

## 1. Purpose and the one design decision that matters

Pass 1 established that rare-token containment resolves the stub→expansion pattern no word-overlap
cutoff can reach (honest unique win: 2 pairs over a re-tuned baseline), and that the 12-pair set
**structurally cannot test containment's own false-keep failure mode** — every "different"-labeled
pair sits at containment ≤ 0.528 while the keep bar is 0.70. Pass 2 fixes the dataset so a cutoff
can be *calibrated* and *validated*, not just sanity-checked.

The core decision is **not "more labels."** It is **separating two subsets with different sampling
disciplines**, because the current fixture is a *challenge set* being read as an *evaluation set*
(the paper already caught that "6/12 is partly by construction"):

| subset | sampling | answers | must NOT be used for |
|---|---|---|---|
| **Challenge set** | targeted / disagreement mining, incl. the two missing strata | "Does the matcher handle failure mode X *at all*?" | estimating real-world accuracy (its base rate is rigged) |
| **Estimation set** | **random** draw from the real matched-changed decision population | "What precision/recall would a staffer actually see?" | stress-testing rare modes (it contains few by design) |

Every metric Pass 2 reports is tagged with which subset it came from. This is the honest version of
what the 12/12 tried to be.

---

## 2. Artifacts (four, cleanly separated)

Today's `scripts/build_similarity_labels.py` fuses mining + human labels + freezing into one
hand-written file. That does not scale to ~150 pairs. Split into:

1. **Miners** (`probes/mine_*.py`, reproducible) → emit *unlabeled candidate
   pools* per stratum as JSON. Each candidate carries stable identity (`bill`, `version_old`,
   `version_new`, `match_path`, `change_type`, a `text_sha256` of old+new), provenance
   (`miner`, `stratum`, `sampling`), and the measure scores **stored for later analysis only, never
   shown to the labeler**.
2. **Labeling worklist generator** → renders each candidate blind to the scores (see §5), collects
   `label` / `confidence` / `rationale` into a worklist JSON.
3. **Frozen fixture** (committed, schema-extended from today's `tests/data/similarity_labels.json`)
   → text re-derived byte-identical from the corpus as today, plus the Pass 2 fields (§4). The
   existing 12 pairs migrate in unchanged (tagged `challenge` / their bills' split per §6).
4. **Baseline + eval harness** (`probes/eval_pass2.py`) → fits the re-tuned
   word-overlap baseline on dev bills only, evaluates candidate rules on held-out, reports the two
   subsets separately + the generalization gap (§7).

**Reuse, don't rebuild:** `probe_consolidation.py` (many-to-one clusters) and
`probe_review_gameability.py` (cross-bill short-cite-vs-large pairs) already emit exactly the two
missing strata; they become miners with a JSON-emit mode. New code: the random-population sampler,
the failure-mode tagger, the worklist generator, the extended fixture builder, the eval harness.

---

## 3. Strata and MVP quotas (~150 labeled pairs)

Structure is fixed; these absolute numbers are the ~150 MVP tier. The two missing strata are
priority zero (currently at literal zero). Existing 12 pairs fold into the challenge counts.

| stratum | subset | target | miner | why |
|---|---|---:|---|---|
| **High-containment-DIFFERENT** | challenge | **30** | consolidation clusters + gameability | the false-keep mode the paper hinges on; the set's top gap |
| **Many-to-one consolidation** | challenge | **25** | consolidation clusters | ground truth for "absorbed vs coincidentally contained"; needed to represent consolidation at all |
| **Random estimation sample** | estimation | **70** | population sampler | first honest population precision/recall |
| **Failure-mode fill** (boilerplate, stub→expansion, reused-number, genuine renumber, cross-agency relocation, amount-only) | challenge | **~25** (incl. existing 12) | disagreement + failure-mode tagger | keep per-mode coverage non-degenerate; ≥3 per mode |

**Estimation-set population, defined precisely:** all matched-changed decisions the current matcher
produces (each `modified` node + each `removed`/`added` pair it considered as a split candidate)
across adjacent version pairs in **all** usable bills. Sample **within each split separately** (dev
and held-out each get their own estimation subset — §6/§7 need both). Stratify by leaf-level
(account/section/subsection); add an engine (XML/PDF) stratum **only if** PDF decisions actually
exist at population scale (verify first — the corpus is XML-dominant and PDF may contribute ~0
matched-changed decisions; do not assert a stratum that cannot be filled). No measure-based
filtering. This is the only unbiased source of a real-world precision/recall.

**Underpowered by design at MVP, stated up front.** 70 estimation pairs, split across dev/held-out
and stratified, gives a *wide* confidence interval and may contain ~zero instances of the rare
error modes (that is what the challenge set is for). The estimation number is **directional** at
this scale; tightening it is Study 3's job. Report the CI, do not over-read a point estimate.

**Bill-type coverage.** *[Superseded by §0, 2026-07-11: the "hard limit" held for `bills/` only;
`bills_corpus/` supplies 2,784 usable bills across both chambers. The paragraph below still
governs the appropriations-only estimation option (A); cross-type is now option (C), not a
deferral.]* As drafted: the usable matching pool (bills with ≥2 versions) is **17 bills, all
House: 16 appropriations + 119-hr-1 (reconciliation), the only non-appropriations and only
consolidation-bearing bill** (verified 2026-07-10). So:
- The estimation sample is appropriations-dominated and stays proportional (it must, to be
  representative).
- **Cross-bill-type generalization cannot be measured in Pass 2** and is deferred to Study 3. Any
  non-appropriations *held-out* presence is *conditional* on processing the ~13 zips yielding a
  multi-version non-appropriations bill — verify before promising it; most zip contents (resolutions,
  single-version Senate bills) are unusable for matching.

---

## 4. Fixture schema (extends today's record)

Every field on the current record is retained. Added:

```jsonc
{
  // ...existing fields (id, bill, version_old/new, match_path, display_path_*,
  //    change_type, decision, label, text_old, text_new, rationale, _observed_similarity)...
  "stratum": "high-containment-different",   // one of the §3 strata
  "sampling": "challenge",                     // challenge | estimation
  "split": "dev",                              // dev | held-out  (assigned by BILL, §6)
  "confidence": "high",                        // high | medium | low  (labeler's)
  "labeler": "r1",                             // opaque reviewer id (never a personal name)
  "adjudication": null,                        // null | {llm_label, agreed: bool, resolved_by, note}
  "miner": "mine_consolidation",               // provenance
  "text_sha256": "…",                          // drift guard for the re-derived text
  "measures": { "word_overlap": 0.43, "containment": 0.86, "cosine": 0.31 }  // analysis-only, NEVER shown at label time
}
```

`_observed_similarity` stays for continuity; `measures` is the fuller analysis-time record. The
build asserts `text_sha256` matches the freshly re-derived corpus text, so drift fails loudly.

**Drift policy — a mismatch invalidates the label, it does not auto-refreeze.** This repo actively
changes `normalize_bill`/`diff_bills`; a legitimate parser change alters the re-derived text. On a
`text_sha256` mismatch the pair is **quarantined for re-review** (the human confirms the label still
holds for the new text) — it is never silently re-frozen, because the label was assigned to the old
text and may no longer apply.

---

## 5. Labeling protocol (blind to scores, sighted on context)

The anti-circularity guard: validating a measure against labels the measure influenced is
worthless. So at label time the human sees **text + structural breadcrumb (division › agency ›
account › section) + bill/version metadata**, and does **not** see word-overlap / containment /
cosine scores or the current matcher's decision.

The nuance that is deliberate, not a leak: structural *context* IS shown, because it is the
ground-truth-establishing signal a human legitimately uses and is exactly #170's thesis (context
disambiguates where body similarity fails). Only the scores-under-test are hidden.

Per candidate the labeler records:
- `label` ∈ {same, different}. For consolidation candidates: {genuinely-absorbed,
  coincidentally-contained}.
- `confidence` ∈ {high, medium, low}.
- `rationale`: one or two sentences. **Mandatory** for any medium/low confidence pair.

**Decision standard (written down so "ground truth" is a documented standard, not one gut call):**
- *Same* = the two texts are the same provision continued/edited across versions (same subject,
  same statutory target, same account/authority), regardless of how much text was added or removed.
- *Different* = distinct provisions that happen to share boilerplate, a citation, or a reused
  section number.
- *Genuinely-absorbed* (consolidation) = the old provision's statutory target actually appears,
  substantively, inside the new section — not merely a shared citation string.
- *Coincidentally-contained* = the containment score is driven by a shared boilerplate citation
  with no substantive continuation.

**Label-space mapping for the false-keep metric (§7):** *coincidentally-contained* is the
false-keep positive (a "different" that scores high containment); *genuinely-absorbed* is a true
many-to-one "same." The consolidation labels feed the false-keep test under this mapping and are
also reported in their own bucket.

**Delivery + question framing (disclosed, not hidden).** Reviewers only ever receive their
generated `form_<name>.html`, never `worklist.json` (which carries `stratum`/`split`). The neutral
question is **stratum-conditional** — consolidation asks "genuinely absorbed vs coincidentally
contained," the rest ask "same vs different provision" — so the wording encodes the mining
hypothesis for that stratum. This framing is shared by the human form and the LLM labeler
identically, so it is *correlated framing across labelers*, not an LLM-only leak; it does not reveal
the stratum name or the scores. (A uniform question across the two same/different strata is a
possible future simplification.)

**Mining-by-the-measure is not circular** as long as the *label* is independent (human rules on
substance) and *tuning never sees the held-out labels* (§6). Targeting high-containment pairs is
standard hard-negative mining; the challenge set's rigged base rate is disclosed (§1), not hidden.

---

## 6. Held-out split — by BILL, not by pair

Pairs from one bill share vocabulary and drafting style; pair-level holdout leaks. Split by whole
bill (continues the leave-one-bill-out discipline the paper already validated).

- Designate ~1/3 of the usable bills as locked held-out test bills. **All** their pairs —
  challenge and estimation — are held out and touched **once, at the end**. *[Implemented in
  `assign_split.py`: deterministic by-bill hash (~1/3 held-out) over the whole `bills_corpus/`
  pool, not "5–6 of 17". A cross-bill high-containment-different pair is held-out only if BOTH
  endpoint bills are; cross-line pairs are excluded from both metrics, never leaked. Live Pass-2a
  partition: high-containment-different 30 dev / 17 held-out / 33 cross-excluded.]*
- Cutoffs and any learned weighting are fit **only** on dev bills. The re-tuned word-overlap
  baseline is fit the same way, on the same dev bills, so the comparison is like-for-like.
- Report **generalization gap = dev accuracy − held-out accuracy**, per subset.
- The existing 12 pairs come from 4 bills already "seen" in Pass 1 → their bills go to **dev** (do
  not launder a seen bill into the held-out estimate).

**Which strata can actually be held out (a corpus constraint, not a design choice):**
- **High-containment-different CAN be held out** — the gameability miner pairs a short provision in
  one bill against a large one in another, so these pairs can be built from held-out bills.
- **Consolidation CANNOT be held out at MVP** — it exists only in 119-hr-1, which is a seen bill
  forced to dev. So the consolidation false-keep metric has a dev number but **no held-out
  counterpart**; its generalization is untested until a second consolidation-bearing bill enters the
  corpus (Study 3+). State this limitation in the §9.7 report; do not paper over it.

---

## 7. Baseline and evaluation harness

- **Baseline = re-tuned word-overlap.** Grid-search the split/move cutoffs on dev bills only;
  freeze the best pair; that is the number every future study quotes (kills the misleading "6/12 at
  production cutoffs"). Report it beside every candidate rule.
- **Metrics, per subset, per split:** precision/recall/accuracy for same-vs-different; a separate
  bucket for the consolidation labels. Report accuracy **both with and without** the low-confidence
  pairs — excluding them is a researcher degree of freedom, so it must be shown, not assumed.
- **The false-keep test that the current set cannot run — read it correctly.** Two distinct numbers,
  and conflating them repeats Pass 1's "12/12 by construction" error:
  - *Challenge-set number:* containment's error rate on the adversarially-mined
    high-containment-different pairs. This is a **worst-case failure-existence probe** — "does the
    false-keep mode exist and how severe" — **not** a precision. It is enriched for the failure by
    construction; never quote it as containment's precision.
  - *Population precision-in-regime:* containment's precision among score ≥ 0.70 pairs **in the
    random estimation set**. This is the honest go/no-go — but it is power-limited at MVP (§3), so
    it is directional and may rest on few high-regime points. Report its support count alongside it.
- **No silent caps:** if any miner truncates a candidate pool (top-N per cluster, sampling), the
  harness logs what was dropped.

---

## 8. Adjudication (multi-reviewer + LLM second-opinion)

> **Annotation (2026-07-11, supersedes the solo-labeler bullets below).** The labeling toolchain
> (§0) is now a **multi-reviewer** round-robin with a stratified overlap set, so the primary
> inter-annotator signal is a real **per-stratum Cohen's kappa** among humans (with support counts,
> §7), not a solo-plus-LLM agreement rate. The LLM second opinion now plays **two never-conflated
> roles**, both reported separately and neither ever voting in the human number
> (`probes/merge_labels.py`):
> 1. **Per-pair disagreement-flagger** — `llm_label` / `llm_disagrees` on every id, including the
>    many SOLO round-robin ids, collected in `llm_disagreements`. Kept **distinct from
>    `needs_adjudication`** (which stays human-driven: a human-human disagreement or an
>    all-low-confidence id). An LLM disagreement is a flag for Will's *attention*, weaker evidence
>    than a human-human split — silence would be the only wrong choice, but it must not inflate the
>    human adjudication queue.
> 2. **Per-reviewer reliability screen** — a **two-tailed** LLM-agreement rate over each reviewer's
>    full shard (denser than the ~24-item human overlap). LOW agreement (below a leave-one-out
>    cohort mean) flags a confused/speedrunning reviewer; HIGH agreement flags possible LLM
>    delegation (which would *correlate* the reviewer with the LLM on the shared-cite false-keeps —
>    the worst case for independence); near-constant per-stratum labeling is flagged via entropy
>    (raw agreement misses it under the strata's rigged base rates). **Reliability ≠ validity:** the
>    screen says who to inspect, never whether a label is correct. Flags are triage, never verdicts.
>
> **Procedural guard (adjudication independence).** Will records his ruling on a flagged pair
> **before** reading the LLM rationale, and the `adjudication` record notes if he changed his mind
> after — otherwise a persuasive LLM rationale can launder a correlated false-keep into held-out
> ground truth.
>
> **Threshold home.** The reliability thresholds live in `probes/merge_labels.py`
> (`_MIN_SUPPORT=20` overall / `_MIN_STRATUM_SUPPORT=12` per stratum before a flag fires;
> `_LOW_FLOOR=0.55` + `_LOW_MARGIN=0.15` below the LOO cohort mean → low engagement;
> `_HIGH_DELEGATION=0.90` → possible delegation; `_LOW_ENTROPY=0.2` bits → near-constant responder).
> They are heuristic triage screens, not tuned operating points; each is commented at its
> definition. In SOLO mode (one reviewer) the low-vs-cohort tail cannot fire and there is no human
> kappa — the screen is half-dead and `merge_labels.py` says so.

- Will is the primary adjudicator for all pairs.
- Every reviewer (and the LLM) labels **blind to the scores** and blind to every other labeler; the
  LLM is additionally blind to project context (verified empirically — see
  `plans/pass2-llm-review-fixes.md`).
- Disagreements are surfaced to Will with all rationales; Will's ruling is final and recorded in
  `adjudication` (`{final_label, llm_label, agreed, resolved_by: "<reviewer id>", read_llm_after, note}`).
- Pairs that stay contested after adjudication are flagged `confidence: low` and reported **both in
  and out** of the headline accuracy (§7), so a hard core is visible rather than silently averaged in.
- **Correlated-error caveat — the load-bearing one.** The LLM can fail the *same way* the measure
  under test does: an LLM reasoning about shared statute citations may rule "same" precisely where
  containment false-keeps on a shared cite. So **high LLM agreement is weak evidence** (it may be
  two correlated errors), while **low agreement is the informative signal** (it flags a genuinely
  hard pair for Will). Use the LLM as a disagreement-flagger, not a validator; never treat agreement
  as confirmation that a label is correct.
- The LLM is a *second opinion*, never the ground truth — it proposes, Will disposes.

---

## 9. Acceptance criteria for the Pass 2 dataset

The dataset is done when:
1. Both missing strata are populated at quota (≥30 high-containment-different, ≥25 consolidation),
   so the false-keep mode is testable.
2. The estimation set is a genuine random draw from the defined all-bills population, sampled
   within each split (documented sampler, seed, no measure filtering).
3. Every bill is assigned dev or held-out; no bill spans both. (Cross-bill-**type** held-out is
   **not** a Pass-2 criterion — the corpus cannot support it, §3/§6; deferred to Study 3.)
4. High-containment-different is present in **both** dev and held-out; consolidation is present in
   dev only, and its missing held-out counterpart is documented (§6), not silently omitted.
5. Every pair has label + confidence; every medium/low-confidence pair has a rationale; every pair
   has an LLM second opinion recorded (`llm_label` + `llm_disagrees`). Human inter-annotator
   agreement is recorded as **per-stratum Cohen's kappa with support counts** over the overlap set;
   the LLM's contribution is recorded as the **per-reviewer two-tailed reliability screen**, never as
   a per-pair "agreement" that votes in the human number (§8 annotation).
6. The fixture rebuilds from the corpus with `text_sha256` assertions passing; any drift-quarantined
   pair is re-reviewed, not auto-refrozen (§4).
7. The re-tuned baseline is frozen and reported. Both false-keep numbers run and are labeled
   correctly — the challenge-set failure-existence probe and the estimation-set population precision
   (with its support count), never conflated (§7).
8. A short `docs/`-or-`plans/` writeup records the sampler, quotas hit vs targeted, the per-stratum
   inter-annotator kappa (with support) + LLM reliability screen, the estimation-set CI, and every
   stratum or metric that fell short (consolidation held-out,
   engine stratum, cross-type) — stated as limitations, not omitted.

---

## 10. Sequencing (what happens after this review)

1. **Will reviews this protocol; fresh-eyes pass applied.** ← gate.
2. Process the ~13 unextracted `bills/*.zip` (cheap) **and check how many yield ≥2 matchable
   versions** — this determines whether any non-appropriations bill can enter the pool at all. Do
   not assume it will; most zip contents are single-version or resolutions. Cross-type coverage is
   a bonus here, not a Pass-2 requirement.
3. Build/convert the miners → emit candidate pools. Will reviews a sample of candidates before
   labeling.
4. Labeling worklist → Will labels + LLM second opinion → adjudicate disagreements.
5. Build the frozen fixture; run the eval harness; write the §9.7 report.
6. Study 3 (cross-type generalization) consumes this dataset; nothing downstream is calibrated until
   §9 acceptance is met.

**Not in scope for Pass 2:** choosing the final matcher, measuring the structural-hybrid half
(Study 4), representing consolidation in the diff output (Study 5). Pass 2 produces the *ruler*,
not the verdict.
