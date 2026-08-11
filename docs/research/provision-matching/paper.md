# Matching Provisions Across Versions of U.S. Appropriations Bills

### A research study for DeltaTrack's version-comparison engine

> **This document has two parts.**
> **Part 1 is a plain-language summary** — no background assumed. Read it if you want the
> problem, what we found, and where it honestly stands. It stands on its own.
> **Part 2 is the full technical study** behind Part 1 — the methods, the measurements, the
> limitations, and the sources — for readers who want to check the work.
>
> **Status.** This is the **first of several planned studies**, not a finished design. Its job
> is to define the problem clearly and test one promising idea. Later studies (outlined at the
> end) build the evidence needed before any of this ships. **Date:** 2026-07-10. Every number in
> Part 2 can be reproduced from the scripts named in Appendix A.

---

# Part 1 — Plain-language summary

## What the tool is trying to do

A bill is republished many times as it moves through Congress — a new version each time it is
reported, passed by one chamber, amended, and enrolled. DeltaTrack takes two versions and shows
what changed.

Before it can show *what changed*, it has to do something more basic: **line up the pieces.** A
bill is made of provisions — sections, sub-sections, funding accounts. For every provision in
the old version, the tool must decide: is this the *same* provision as one in the new version
(so the difference between them is an **edit**), or is it a *different* provision (so one was
**removed** and another **added**)?

That lining-up step is the whole foundation. Get it wrong and everything after it is wrong — the
count of changes, the dollar-figure differences, the "this section moved" labels. This study is
about doing that step well.

## Why it is hard

Two things make it hard.

**1. The obvious label is unreliable.** You would think the section number would identify a
provision. It does not. Congress reuses a section number for brand-new content, and moves
existing content to a new number. So the number can *narrow down* candidates, but it can never
*prove* two provisions are the same.

**2. The current method measures the wrong thing.** Today the tool decides "same or different"
by counting how many words two provisions share. That is fooled in two opposite directions:

- **Two *different* provisions can look similar**, because legal text is full of shared
  boilerplate ("None of the funds made available by this Act may be used to…"). The shared
  boilerplate props up the score, and the tool wrongly links them.
- **The *same* provision can look different**, because a one-line placeholder in one version
  grows into a full page in the next. Word-counting sees two very differently-sized texts and
  wrongly splits them apart.

Three real examples from our data make it concrete (word-overlap runs 0 to 1, higher = more
similar):

| | what it is | truth | word-overlap score | what the tool does |
|---|---|---|---|---|
| **A** | A placeholder — "*Section 6(f) of the Food and Nutrition Act… is amended—*" — becomes a full 2,200-character provision | **same** | **0.08** (looks different) | wrongly splits |
| **B** | A funding account cut from \$120M to \$60M, with a long legal proviso added | **same** | **0.26** (looks different) | wrongly splits |
| **C** | A section *number* reused: old one moves VA staff, new one governs marketing notices | **different** | **0.43** (looks similar) | wrongly links |

Look at the trap: the **same** provision (A) scores **lower** than the **different** one (C). No
amount of adjusting the cutoff fixes that — the *measurement itself* is asking the wrong
question.

## The idea we tested

Instead of counting all shared words equally, **weight rare words heavily and common words
barely.** Agreeing on a specific statute citation ("Section 6(f) of the Food and Nutrition Act
of 2008") is strong evidence two provisions are the same. Agreeing on "funds" or "Act" is almost
no evidence. This is a standard idea in fields that match records (it is how duplicate-detection
systems work); we are applying it here.

Then ask a one-directional question we call **containment**: *is the shorter provision's
important content sitting inside the longer one?* When a placeholder grows into a full section,
the placeholder's content is entirely inside the expanded version, so containment is high (near
1.0) — exactly the case that defeats word-counting. When two provisions merely share boilerplate,
containment stays low, because boilerplate carries little weight.

## What we found

We tested against a small set of **12 provision pairs a person hand-labeled** as "same" or
"different," chosen to include the genuinely hard cases.

**The real, solid result:** containment correctly handles the two hardest cases — the
placeholder-grows-into-a-section pairs (examples A and B above) — that **no word-counting
cutoff can ever reach**, because for those pairs a same-provision score sits *below* every
different-provision score. That is the core win, and it is well-founded.

We want to be precise about how big the win is, because it is easy to overstate:

- On this 12-pair set, the current word-counting method at its production settings gets 6 right.
- Given the same freedom to re-tune, word-counting can get 10 of 12 right.
- Containment's *unique* advantage — the pairs it gets that no re-tuned word-counting can — is
  those **2 placeholder-grows cases**. That is the honest size of the improvement on this set.

**Being clear about scale:** 12 hand-labeled pairs, drawn from a handful of bills, is enough to
*show the idea works on known-hard cases*. It is not enough to *set the exact cutoffs* a
production tool would use. Those are two very different bars, and this study only clears the
first.

## What is solid, and what is still open

**Solid:**

- The better measurement (rare-word containment) beats word-counting on the hardest edit
  pattern, and the separation held up across the (few) bills we could test — including one bill
  of a different type.
- We checked one thing that could have inflated the result — building the "which words are rare"
  model from a set of bills that *includes* the ones we test on — and measured that it makes
  almost no difference (it moves the scores by less than 0.005). So the result is not an artifact
  of that.

**Still open (and load-bearing):**

- **The exact cutoffs do not yet generalize.** They are directional, calibrated on too few
  examples to trust in production.
- **Containment has its own blind spot.** For a *short* provision, sharing a single rare
  citation with an unrelated *large* provision can make it look "contained" when it is not — a
  false match. This is real, and — importantly — **our current 12-pair test set cannot even
  detect this failure**, because it happens to contain no example of it. Fixing that gap is the
  top priority for the next study.
- **The "combine several signals" idea is a hypothesis, not a result.** A natural next step is to
  blend containment with structural clues (does the funding-account path match? does the heading
  match?). That is promising, but we have *not* measured it, and our strongest evidence so far
  says the text measure alone already does most of the work.
- **We have tested a narrow slice of Congress.** Almost all our bills are appropriations
  (spending) bills, plus one reconciliation bill. Other kinds of bills are written differently
  and may behave differently.

**Two corrections to earlier internal write-ups**, stated plainly so the record is clean:

- An earlier draft framed the win as "solves 6 of the hard cases." A closer look shows the
  honest figure is **2 uniquely-solved cases** (the other 4 are also solvable by a re-tuned
  version of the old method).
- An earlier draft said containment "recovered 265 renumbered provisions" in the hardest bill. A
  closer look shows that of those 265 candidates, only about **74 are clean one-to-one matches**;
  the rest are the blind-spot above — many small provisions all pointing at one big section
  because they cite the same law — and need a further check before they can be trusted.

Neither correction changes the direction; both tighten numbers that were rounded generously.

## What happens next

Before we can pick and tune a production method, we need a **bigger, more varied set of
hand-labeled examples.** Specifically it must include the cases our current set is missing — the
"shares a citation but is genuinely different" trap, and the "one large section absorbs many
small ones" pattern — plus a held-aside portion we never tune on, so we can honestly measure how
well the method generalizes. We should also process the roughly dozen bills we have already
collected but not yet loaded, and start including bill types beyond appropriations.

That labeled-dataset work is the gate. The full plan, and the evidence behind every claim above,
follows in Part 2.

---
---

# Part 2 — Technical study

**Scope.** The *matching* problem underneath the diff: deciding which provision in one bill
version is "the same provision" as one in the next. This study characterizes the problem, lays
out the space of methods, and measures one strong candidate. It is the first of several planned
studies; the methodology is treated as unsettled.

**What is settled vs open after this study** (details in §8, plan in §10):

- *Settled enough to build on:* the problem's identity (entity resolution over an ordered tree
  with an unstable key); the signal inventory (§4); that word-overlap measures the wrong
  quantity; that rare-token containment separates the hardest edit pattern where word-overlap
  cannot (§6); and that the text measure alone carries most of the accuracy gain.
- *Open, needs later studies:* the exact measure + cutoffs + signal combination to ship; whether
  a structural-signal hybrid adds anything measurable on top of text; how it generalizes beyond
  appropriations bills; how to represent many-to-one consolidation (§6.4); PDF acceptance; and —
  the gating prerequisite — a labeled dataset large enough and varied enough to *calibrate* a
  threshold rather than *sanity-check* one, including the failure case the current set cannot
  test (§8, §9).

**How to read Part 2.** §1–2 restate the problem in its established terms. §3–4 survey the menu
of methods and the signals our data exposes. §5–6 are the experiments and results. §7 gives the
leading hypothesis and what we set aside. §8 is the limitations section — the part a reviewer
should push on hardest. §9 is the blocking prerequisite (a bigger labeled dataset). §10 is the
multi-study plan.

## Abstract

DeltaTrack compares two versions of an appropriations bill and reports what changed per
provision. The foundational step is *matching*: pairing each provision in the old version with
its counterpart in the new one. This is hard because the obvious identifier — the section number
— is unstable (reused for new content, reassigned to the same content), and because the current
similarity signal, word-overlap, is defeated by two dominant edit patterns: unrelated provisions
sharing boilerplate, and a short "stub" expanding into a full provision.

We frame the problem in its established terms (*entity resolution over an ordered tree with an
unstable key*), survey the methods four research literatures offer, inventory the signals our XML
and PDF pipelines expose, and measure candidate text measures on a 12-pair hand-labeled set and
the full corpus.

The central finding: **a better text measure — rare-token "containment" (a weighted Tversky
index) — resolves the one edit pattern that no word-overlap cutoff can reach**, the
stub→expansion case. On the hand-labeled set, containment's *unique* contribution over a
*re-tuned* word-overlap baseline is the 2 stub→expansion pairs (word-overlap at production
settings scores 6/12; re-tuned it reaches 10/12; the two-signal containment rule reaches 12/12).
Containment has its own failure mode — a short provision spuriously "contained" in a large
unrelated one via a shared rare token — which *structural* signals could in principle guard, and
which our current labeled set cannot test. A multi-signal hybrid is therefore a **hypothesis to
test in a later study**, not a result: the measured evidence here is that the text measure alone
carries the gain.

We are explicit about the limits. The measure generalizes across the bills we tested; the
decision *cutoffs* do not generalize from 12 labeled pairs, and the labeled set has no example of
containment's own failure mode. Expanding and re-stratifying that set is a hard prerequisite
before any cutoffs are fixed in production.

---

## 1. The problem, in plain terms

When a bill moves through Congress it is republished at each stage (reported → engrossed →
enrolled, and so on). DeltaTrack lines up two consecutive versions and shows what changed. To do
that it must first answer, for every provision: **is this provision in the new version the same
one as this provision in the old version (an edit), or a different provision (one removed, one
added)?**

Get that pairing wrong and everything downstream is wrong — the change counts, the dollar-figure
diffs, the "this section moved" labels. Matching is the load-bearing step.

Three real examples from our corpus show why it is hard. The study returns to them throughout.

> **Example A — "Alien SNAP" (bill 119-hr-1).** A section begins as an 81-character placeholder —
> `Section 6(f) of the Food and Nutrition Act of 2008 … is amended—` — and in the next version
> becomes a fully written 2,242-character provision. Obviously the **same** provision, filled in.
> Yet its word-overlap score is **0.078** (near zero), because the new text is 28 times longer.
> The tool wrongly reports it as a deletion plus an addition.

> **Example B — "Tanker Security Program" (bill 118-hr-4366).** The same appropriations account,
> funding cut from \$120M to \$60M with a long legal proviso appended. Same account, edited.
> Word-overlap **0.255** — the added proviso dilutes the score below the "keep" line, so again a
> false split.

> **Example C — "Section 232" (bill 114-hr-2029).** A general-provisions section whose *number is
> reused* for an unrelated provision: the old one governs moving VA staff; the new one governs
> marketing-campaign notices. **Different** provisions. Yet word-overlap is **0.429** — shared
> boilerplate ("The Secretary of Veterans Affairs shall provide … to the Committees on
> Appropriations …") props the score above the "keep" line, so the tool wrongly links them.

The trap across these: the **same** provision (A) scores 0.078, while a **different** provision
(C) scores 0.429. The correct answer runs *opposite* to the score. That is not a cutoff that
needs tuning — it is a measurement asking the wrong question.

### The three failure modes

| # | failure mode | example | why word-overlap fails |
|---|---|---|---|
| 1 | **Boilerplate inflation** | Section 232 | Unrelated provisions share appropriations boilerplate, a large fraction of short legal text. |
| 2 | **Stub → expansion** | Alien SNAP, Tanker | The same provision grows many-fold; a length-normalized overlap collapses. |
| 3 | **Unstable identifier** | reused Sec. 232; renumbered Sec. 237→234 | The section number is reused and reassigned, so it is not an identity. |

---

## 2. What kind of problem is this? (naming it, so we can borrow solutions)

Part of the difficulty is that the problem had no name in our own discussions. It sits at the
intersection of three mature research areas, each with decades of methods:

1. **Hierarchical change detection / tree differencing.** Computing the edit script (including
   *moves*) between two trees. Home of XML-diff and source-code diff tools.
2. **Entity resolution / record linkage.** Deciding which record in dataset A refers to the same
   real-world entity as a record in B, by combining several similarity signals. Home of the
   Fellegi-Sunter framework used across census and health-record matching.
3. **Natural-key instability (temporal entity resolution).** The specific reason ours is hard:
   the natural key (section number) is not stable, so it can only *narrow candidates*, never
   *prove identity*.

In one sentence: **entity resolution over an ordered, hierarchical document whose natural key is
unstable.** Naming it this way tells us which toolboxes to open (§3) and which mistakes are
already documented.

---

## 3. The universe of methods

Organized by family. For each: the intuition (with one of our examples), what it requires from
our data, and the tradeoff. This section is deliberately broad — part of the deliverable is
showing what was *considered*, including what we set aside (§7).

### Family A — Better text similarity (the record-linkage family)

The unifying insight, argued by Cohen, Ravikumar & Fienberg (2003)[^1]: **weighting words by
rarity (IDF) can be read as an approximation of the Fellegi-Sunter match score.** Agreeing on a
rare token (a specific statute citation) is strong evidence two provisions are the same; agreeing
on a common one ("funds", "Act") is weak. Every method here operationalizes "reward rare shared
content, discount boilerplate."

- **Word-overlap ratio — today's baseline.** Fraction of words that line up in order (a
  longest-common-subsequence ratio). Fails all three modes. *Worth keeping for one job:* it stays
  high (0.83) when a short account line changes only its dollar amount, where the rare-token
  measures stumble.

- **TF-IDF cosine.**[^2] Represent each provision as a vector of rarity-weighted word counts;
  score by the angle between vectors. Fixes boilerplate inflation (Section 232: 0.429 → 0.322)
  but, because it normalizes each vector by its own length, **fails stub→expansion** (Alien SNAP
  only 0.243). Needs a corpus to compute word rarities.

- **Rare-token containment (weighted Tversky index[^3]) — the standout.** Instead of the
  symmetric cosine, ask an asymmetric question: *is the shorter provision's rarity-weighted
  content contained in the longer one?* A filled-in stub scores ~1.0; two different provisions
  sharing only boilerplate score low (boilerplate carries little weight). It addresses modes 1
  **and** 2. (Formally, the Tversky index with the knob set to barely penalize content unique to
  the longer side; closely related to BM25 retrieval scoring[^4] with length-normalization turned
  down.) Its own failure mode — a short provision spuriously contained in a large one — is
  measured in §6.3–6.4.

- **Soft TF-IDF.** TF-IDF that also counts *near*-matching tokens ("Dept." vs "Department",
  "sec. 101" vs "Section 101"). Useful for reconciling PDF-extracted and XML-extracted text; does
  not by itself solve the stub or boilerplate modes. A refinement, not the core.

- **Embedding cosine (BERT / LEGAL-BERT).** Dense "meaning" vectors that catch
  same-meaning-different-wording. This is what the one rigorous US-bill study (Kim et al., EMNLP
  2021)[^5] uses — and it *matches on content alone, using no structural-position features at
  all*. For us it is a black box with respect to "discount boilerplate," adds install weight and
  reduces auditability (both matter for a locally-installed tool with a non-technical audience),
  and is harder to explain. Worth benchmarking as a quality *ceiling*, not shipping as the
  default. (Note: this study's own text-only result and Kim et al.'s content-only success both
  suggest structural features may not be necessary — see §7.)

### Family B — Structural / tree matching

- **Exact path equality (today).** Pair provisions with the same structural address
  (`match_path`), resolve ties by text. Fails when the address is unstable. In tree-diff terms
  this is X-Diff's "signature" idea[^6], and X-Diff's lesson is that **signature construction is
  the lever**: our address bakes in the section number, which is exactly why renumbers break it.

- **GumTree bottom-up propagation.**[^7] Match two container nodes (of the *same type*) when most
  of their *descendants* already matched — *ignoring the container's own value*, e.g. its section
  number. Renumber-tolerant by construction. The documented cost (Frick et al., 307,000 real code
  revisions)[^8]: being name-blind, it also mis-matches two differently-named containers that
  merely look alike — it trades the text-boilerplate problem for a *structure*-boilerplate
  problem.

- **Schema matching — Cupid[^9], COMA[^10], Similarity Flooding[^11].** The family that formalized
  "combine name similarity + structural position." COMA's benchmark result: **combining several
  individually-weak matchers beat every single matcher.** The precondition worth remembering is
  *individually weak* — see §7 for whether that precondition holds here.

- **Tree edit distance (Zhang-Shasha[^12]).** The principled "minimum edit script" foundation.
  *Ordered* edit distance is polynomial but forces sibling order to be meaningful; *unordered* is
  NP-hard[^13]. Too heavy and too rigid to run whole-document; its value is conceptual and local.

### Family C — Combining and assigning signals

- **Fellegi-Sunter weighted score.**[^14] Combine per-signal agreements into one score, each
  signal weighted by how well its agreement distinguishes matches from non-matches. The formal
  home for "header + path + containment + word-ratio → one decision."
- **COMA meta-matching.** The practical, less-statistical version: run the matchers, average
  their scores, threshold. Robust, explainable, easy to extend.
- **Greedy vs optimal (Hungarian) assignment.** How to turn pairwise scores into a consistent set
  of pairings within a collision group. The literature reports greedy reaching most of optimal at
  far lower cost; **not our lever** — worth revisiting only after the similarity *measure* is
  fixed. (We have not measured the greedy/optimal gap on our data; this is a literature
  characterization, not a probe result.)

### Family D — Domain-specific approaches (and why they don't transfer)

- **Akoma Ntoso / USLM persistent ids.**[^15] Legislative-XML standards carry a cross-version
  element id — but it is *asserted by the drafter*, never computed. Whether it survives a version
  boundary is **transition-dependent, not uniformly regenerated** (measured corpus-wide[^src-audit]):
  stable across a cross-chamber *hand-off* (16/16 version pairs), bimodal within a chamber (a few
  bills preserve it, most regenerate), and fully regenerated across amendment ping-pong and
  enrollment. But as a *matching* key it is still low-value: id-equality flags only ~59
  conflict-free matches the path matcher misses (concentrated in same-senate pairs), while 34 of 93
  candidates *contradict* an existing pairing, and `normalize_bill` already drops every id on one
  file. So the standard *records* an identity where the drafter happened to preserve it and discards
  it elsewhere; it does not *find* one — a thin, guarded supplement, not a general cross-version id.
- **Amendment-grammar parsing (Xcential's Comparative Print Suite — the production system for
  Congress).**[^16] Parses the amending instrument's own citation language ("Section 3 is amended
  by…") to locate targets. Doesn't transfer: consecutive bill *versions* don't cite each other.
- **Text-reuse matchers (GovTrack[^17], Kim et al.[^5], DocuToads, wTED[^18]).** GovTrack's
  redliner is explicitly structure-blind. The closest analogues lean on content similarity — Kim
  et al. classify on text embeddings using no positional features at all. Two honest reads of that
  fact coexist: either a text+structure hybrid is an unexplored gap in the published record, or —
  since the rigorous prior work matches on content alone and succeeds — structure is simply *not
  needed* for this problem. This study's own evidence (§6.2) is closer to the second read; we flag
  it rather than resolve it.

---

## 4. What our data actually provides

A method is only as good as the signals it can read, and our two pipelines differ sharply.

### XML pipeline — the rich source

Per provision we have: a normalized structural path (`match_path`, the join key today), a typed
leaf level (money account vs section vs subsection), a header/catchline, the section number, and
the body text. The critical caveat is **header coverage by level**:

| leaf level | has a header |
|---|---|
| agency | 98.2% |
| department | 94.7% |
| account | 88.5% |
| subsection | 65.3% |
| **section (general/administrative provisions)** | **21.2%** |

The header is a strong identity signal for *money accounts* but is **absent for four of five bare
sections** — exactly the provisions where the reused-number problem (Example C) bites, and
exactly the provisions where §6.3's containment false-keeps occur. So "use the section header" is
an account-level fix, not a general one — a point that bears directly on the header-based guard
proposed in §7.

**Two further XML signals the source carries** — surfaced by a corpus-wide source-signal
audit[^src-audit], unused by the current matcher, and neither a matching signal in itself:

- **The bill's own change markup** (`@changed` / `@reported-display-style`). GPO's *version-internal*
  record of what this version changed against its own predecessor base — present and dense on
  amendment versions (engrossed-amendment 21/21), clean-absent on introduced (0/10). Because it is
  version-internal it *corroborates* a computed diff rather than replacing the diff engine, and it is
  a natural **validation oracle** for the Study-4 head-to-head (§10), not a matching input.
- **Explicit level labels** (`toc-entry@level`, `header-in-text@level`). GPO's own hierarchy depth on
  roughly a third of files (29–38/102) — an independent oracle to validate or repair inferred
  structure. It bears on §7: `toc-entry@level` could in principle reach some of the bare sections
  where the header is absent (21.2% coverage), but `header-in-text@level` by definition requires a
  header, and the audit measured only *file-level* presence — provision-level `@level` coverage on
  headerless sections is unmeasured. And it encodes *depth, not identity*, so at most it aids blocking
  and hierarchy validation, not the reused-number disambiguation the header guard was meant to do.

### PDF pipeline — the degraded source

The PDF emits typed anchors (title / agency / account / section …) and reconstructs body text
between them, but its structural depth is *detection-path dependent*. Observed by hand on our two
worked bills (this is a manual observation of the two PDFs, not a probe output):

| bill | Tanker / Alien SNAP in the PDF |
|---|---|
| 118-hr-4366 (appropriations) | `TANKER SECURITY PROGRAM` captured as an **account**, full agency breadcrumb ✅ |
| 119-hr-1 (reconciliation) | `SEC. 10012` captured, but breadcrumb only `TITLE I › SEC. 10012` — **the "Alien SNAP" catchline and the agency levels are absent** ❌ |

**This is the decisive per-engine fact.** On the reconciliation bill the PDF loses exactly the
structural signal a structure-first matcher would rely on. But the *text* measure is computable
on both engines from the reconstructed body — and it was the text measure (containment = 1.0)
that resolved Alien SNAP. **Text degrades gracefully across engines; structure does not.** This
argues for text-primary, structure-confirmatory — and, as §7 notes, it also argues *against*
leaning on structural confirmers as load-bearing, since they vanish precisely on the hard case.

---

## 5. Experimental setup

- **Corpus.** **31 bills** (the extracted bill directories the probes read; a further ~13
  collected bills remain as unextracted archives and are *not* in any number below — processing
  them is a cheap way to grow and diversify the corpus, and a named next step in §9). Of the 31,
  17 have ≥2 consecutive versions, giving 70 adjacent version pairs, 30,605 matched node pairs, of
  which 1,287 are matched-and-changed (the interesting ones). Heavily weighted toward
  appropriations bills. This is both our test bed and a limitation (§8).
- **Hand-labeled set.** 12 real provision pairs, each ruled SAME or DIFFERENT by a human,
  spanning the ambiguous-similarity band and clear-cut anchors. Small, and drawn from only four
  bills — and, as built, 6 of the 12 were selected *because the current word-overlap baseline
  misclassifies them* (§6.2), which is why the "6/12 baseline" is partly a property of the set's
  construction rather than a neutral measurement. Limitations measured in §8.
- **Measures compared.** Word-overlap (baseline); TF-IDF cosine; rare-token containment; and a
  two-signal rule combining containment with word-overlap. Rarity weights (IDF) built from all
  64,276 provision bodies in the corpus, smoothed to avoid single-occurrence tokens dominating.
- **How we guard against fooling ourselves.** Every rule is checked three ways: on the 12-pair
  hand-labeled set (ground truth), across all 1,287 corpus decisions (hand-inspecting what
  changes), and with leave-one-*bill*-out (train on three bills, test on a held-out fourth — §8).
  A perfect score on the 12 pairs alone is treated as a warning sign, not a result — and §8
  records the specific reason it is not sufficient: the set contains no example of containment's
  own failure mode.

Two similarity measures, defined plainly:

- **Cosine** = the angle between two rarity-weighted word vectors; symmetric; penalizes length
  differences.
- **Containment** = (rarity-weighted words the two share) ÷ (rarity-weight of the *shorter*
  provision, by weighted mass); asymmetric; ~1.0 when the shorter provision sits inside the
  longer.

---

## 6. Results

### 6.1 Containment separates the stub cases; cosine and word-overlap do not

The 12 hand-labeled pairs plus two additional corpus cases, sorted by containment (the two extra
rows — `sec 253` and `sec 8144` — are **author-assumed** "same," not part of the hand-labeled
set; they are shown for context and flagged as such):

| pair | truth | word-overlap | cosine | **containment** |
|---|---|---|---|---|
| anchor-diff-780 | different (labeled) | 0.154 | 0.139 | 0.238 |
| Section 232 (reused #) | different (labeled) | 0.429 | 0.322 | 0.432 |
| ag-to-HHS (boilerplate) | different (labeled) | 0.629 | 0.225 | 0.528 |
| sec 253 (fund repointed) | same (*assumed*) | 0.590 | 0.606 | 0.689 |
| Tanker (account edit) | same (labeled) | 0.255 | 0.62 | 0.929 |
| CRS salaries (near-identical) | same (labeled) | 0.995 | 0.973 | 0.974 |
| sec 8144 (headerless stub→expand) | same (*assumed*) | 0.554 | 0.733 | 1.0 |
| Alien SNAP (stub→expand) | same (labeled) | 0.078 | 0.243 | 1.0 |

Containment separates every pair in this table without interleaving (all "different" below all
"same"). But state the boundary honestly: **among the hand-labeled pairs, the highest "different"
is ag-to-HHS at 0.528 and the lowest "same" is Tanker at 0.929** — a wide, clean band of ~0.40.
Including the two author-assumed rows narrows the visible gap to 0.528 → 0.689. (An earlier draft
stated "different ≤ 0.43, same ≥ 0.69, a 0.26-wide gap"; that boundary silently excluded the
ag-to-HHS row at 0.528 shown in the same table, and drew its lower bound from an assumed-label
row — both corrected here.) Word-overlap has no separating value at all (different pairs at
0.43–0.63 interleave with same pairs at 0.08–0.26); cosine fixes boilerplate but misranks the
stubs.

### 6.2 A two-signal text rule reaches 12/12 — but the honest gain over a *re-tuned* baseline is 2 pairs

Rule: *keep as an edit if word-overlap ≥ 0.5 OR containment ≥ 0.7; treat a removed+added pair as
a move only if containment ≥ 0.7.* (Word-overlap guards the amount-only-edit case; containment
carries everything else.)

The comparison must be like-for-like. The current baseline is word-overlap at its **production**
cutoffs (0.40 split / 0.60 move). Giving word-overlap the same freedom to re-tune that the new
rule enjoys:

| approach | hand-labeled set |
|---|---|
| Word-overlap @ production cutoffs (0.40 / 0.60) | 6/12 |
| Word-overlap, best re-tuned cutoffs (0.47 / 0.63) | 10/12 |
| **Two-signal containment rule** | **12/12** |

So containment's **unique** contribution on this set — the pairs it gets that *no* word-overlap
cutoff can — is exactly **2 pairs: Tanker (0.255) and Alien SNAP (0.078)**, the two
stub→expansion cases whose same-provision word-overlap sits below every different-provision
word-overlap. That 2-pair gain is genuine and unreachable by tuning; it is the real result. The
"6 pairs flip" framing of an earlier draft conflated this irreducible gain with the four
boilerplate-inflation pairs that a re-tuned word-overlap floor separates on its own.

Two further honesty notes on the 12/12:

- It is a *resubstitution* score — the two cutoffs (0.5 / 0.7) were chosen on the same 12 pairs
  they are scored on. The honest generalization estimate is the leave-one-bill-out 10/12 (§6.5).
- The rule is *over-parameterized* for 12 points: a **single** containment threshold anywhere in
  (0.528, 0.929) already scores 12/12 on this set. The word-overlap clause and the split/move gate
  earn their place on corpus cases (§6.3), not on the 12/12.

**Corpus census.** Against the current 0.40 word-overlap floor, the two-signal rule changes 25 of
1,287 matched-changed decisions (11 now split, 14 now kept). Hand-inspection of all 25: roughly
19–20 are clearly correct (reused numbers now split; stubs and re-funded accounts now kept), ~3
are clearly wrong, and ~2–3 are borderline. The ~3 wrong are the containment failure modes §6.3
describes.

### 6.3 The signals are complementary — but the evidence is asymmetric

Inspecting the 25 changes surfaced the text measure's own two failure modes, and they are where a
*structural* signal is, in principle, strong:

- **False split:** `port infrastructure development program`, an *account* reworded (containment
  0.674, just under the line). It is an account, so an **account-path** structural keep would
  rescue it.
- **False keep:** a few VA administrative provisions where a short old text sits inside a long
  unrelated new one sharing agency vocabulary (e.g. sec 229, 474→1,820 chars, containment 0.86).
  **Header/path scoping** would in principle guard these — but note §4: these are exactly the
  bare-section provisions with 21.2% header coverage, so the header half of that guard is
  unavailable for four of five of them.

State the asymmetry honestly, because it matters for §7. The text measure's failure modes are
**measured** (the 25-change census). The structural rescues are **asserted** ("an account-path
keep would rescue it") and have *not* been run end-to-end, nor has the structural signal's own
false-positive cost (two different accounts sharing a path — the structural analogue of
boilerplate inflation) been measured. And the purely structural approach explored earlier (an
exploratory study that this one supersedes) safely fixes only 2 of the 6 hard cases and cannot
touch headerless sections at all — which containment handles.

So the accurate statement is **not** "neither text nor structure wins alone." It is: **text is
strong alone (12/12 on the labeled set, and it carries the hardest real case); structure *might*
patch two residual text failures, but that has not been measured.** This is *consistent with* the
COMA finding that combining matchers can beat a single one — but we have not run a combined
matcher, so we are not reproducing that result, only pointing at it as a hypothesis (§7).

### 6.4 Hard case: deliberate consolidation (119-hr-1, Senate rewrite)

The adversarial worst case is when Congress rewrites and *consolidates* a bill — renumbering
sections and recycling text. Bill 119-hr-1 (the 2025 reconciliation act) has exactly this at its
Senate stage (`placed-on-calendar-senate` → `engrossed-amendment-senate`). Because the structural
path bakes in the section number, renumbering shatters the join:

| current-matcher outcome on this transition | count |
|---|---|
| unchanged (path still aligned) | **17** |
| shown as removed | 525 |
| shown as added | 400 |
| rescued as "moved" (word-overlap ≥ 0.6) | 605 |

Only 17 of ~1,150 provisions line up — the diff is almost entirely noise, as observed. The
current rescue already caught the easy recycled text (605 moves); the question is the 493 leftover
"removed" provisions. Rare-token containment finds a match at ≥ 0.7 for **265 of those 493** —
every one of which word-overlap misses (0 reach the 0.6 move bar).

**But "265 recovered" over-states what containment actually found, and the same probe output shows
why.** Reading the 265 by their target section:

- Only **74 are clean one-to-one** (one old provision → one new section) — the plausibly-genuine
  recycled-text recoveries.
- **41 new sections each absorb multiple old provisions** — 191 old provisions in total (72% of
  the 265), one new section absorbing 30.
- **88 of the 265 point at a *shorter* new section than the old provision** — the short-new-in-
  long-old direction, which is the §6.3 false-keep mode running in reverse.
- The very first pair the probe prints is the bill's **official title** ("To provide for
  reconciliation pursuant to title II of H. Con. Res. 14.") matched to a subsection at containment
  1.000 — a clear false positive, and evidence that non-provision nodes leak into the set.

The mechanism is visible: five different old subsections each score containment 1.000 against the
same new `sec. 81001`, because each cites "Section 455(a) of the Higher Education Act" and the new
section's short amending text repeats that citation. Containment = 1.0 fires identically for a
genuine 1:1 recycle (Alien SNAP) and for an unrelated short provision whose one rare citation sits
inside a large section. **They are indistinguishable by the containment value alone.**

Three honest conclusions from this case:

1. **The current differ fails on deliberate consolidation** — confirmed, not just asserted (17 of
   ~1,150 aligned).
2. **Containment is a useful *detector* of candidate recycled-across-renumbering text** — it
   surfaces 265 candidates the word-overlap rescue cannot see, of which ~74 are clean matches.
   That is real value on the hardest input, but "265 recoveries" should be read as "265
   candidates, ~74 clean, the rest needing verification," not 265 confirmed moves.
3. **Detecting is not representing, and the metric cannot self-verify.** Consolidation is
   many-to-one, and distinguishing "genuinely absorbed" (the old provision's statute target
   really appears in the new section) from "coincidentally contained" (§6.3's failure mode) needs
   a *structural* signal alongside containment — plus a richer output vocabulary
   ("absorbed into" / "consolidated") and ground-truth labels we do not yet have (§8, §9). We flag
   this as a roadmap item beyond this study's scope, not a solved problem.

### 6.5 Generalization — the measure travels, the cutoffs wobble, and leakage is negligible

Leave-one-*bill*-out (fit the two cutoffs on three bills, test on the held-out fourth) scored
**10/12**. Both misses (`contested-3`, `contested-5`) are *cutoff-boundary* cases: a fold fits a
slightly different cutoff on its three training bills, and the held-out pair sits just across the
line. The **containment values themselves stay well-separated** in every fold, and Alien SNAP —
the structurally-degraded reconciliation outlier — still scores 1.0 with rarity weights that never
saw its bill.

Two method caveats, stated for accuracy:

- The *test* signal in each fold correctly uses rarity weights rebuilt to **exclude** the held-out
  bill (so "Alien SNAP scores 1.0 with weights that never saw its bill" is honored). The *cutoff
  fit* on the training bills, however, still uses full-corpus rarity weights. One bill of 31 does
  not move the coarse cutoff grid, so 10/12 stands, but the exclusion is not applied throughout the
  fold.
- We separately measured the concern that building rarity weights from a corpus that *includes*
  the test bills inflates the headline. It does not: rebuilding the weights to exclude a test bill
  shifts that bill's containment values by **< 0.005** (e.g. Tanker 0.929 → 0.930). Document
  frequencies over 64,276 bodies barely move when one bill is removed. This is a measured
  non-issue, not an assumption.

**Reading:** the *measure* (rare-token containment) generalizes across bills and across the
appropriations→reconciliation boundary; the decision *cutoffs* do not robustly generalize from 12
pairs. This is the empirical core of the limitations in §8.

---

## 7. Leading hypothesis, and what we set aside

This is the direction this study points to, offered as a **hypothesis to test in later studies**,
not a decision to implement now. Later studies (§10) should try to break it.

### Leading hypothesis: a multi-signal matcher, with the structural half explicitly unproven

Adopt the record-linkage / schema-matching architecture — combine several signals into one
calibrated decision rather than tuning a single cutoff:

1. **Blocking.** Keep the structural path (`match_path`) as a *candidate-narrowing* key, treated
   as an unstable natural key — never as proof of identity.
2. **Primary text signal: rare-token containment.** The single biggest measured accuracy gain, and
   it works on both the XML and PDF pipelines.
3. **Guard signal: word-overlap.** Retained only for its one strength — amount-only edits of short
   account lines.
4. **Structural confirmers where available** (account-path equality; header equality scoped to a
   collision group with a generic-catchline guard; parent/agency ancestor for move-vs-renumber).
   These *could* rescue the text measure's two failure modes (§6.3) and *could* disambiguate the
   §6.4 consolidation case — **but this is the unproven half of the hypothesis.** The measured
   evidence in this study is that text alone scores 12/12 on the labeled set; the structural
   confirmers rest on two anecdotes, have not faced the corpus census the text measure did, and
   (per §4) are unavailable for the very bare-section provisions where they are most needed and on
   the degraded PDF where the hard case lives. Two data points cut against needing them at all:
   this study's text-only 12/12, and Kim et al.'s content-only success. A later study must
   **measure** whether structure adds anything on top of text before the confirmer half is
   adopted.
5. **Combine, don't sequence.** Score each candidate pair on all available signals; combine (a
   simple average, or a small learned weighting) and threshold once.

The honest framing: the **text** thesis is measured and strong; the **hybrid** is a reasonable
architecture from the literature whose marginal value here is *not yet demonstrated*. Do not ship
the structural half on the strength of COMA; ship it only if a later study measures a gain.

### Deliberately set aside (and why)

| option | why not (now) |
|---|---|
| **Raise the word-overlap threshold** (the earlier structural study's lever) | Measured to trade one ambiguous-band error for another — mis-splits genuine headerless stubs (e.g. bill 118-hr-8774 Sec. 8144). No clean threshold exists. |
| **Purely structural matcher** | Safely fixes only 2 of 6 hard cases; blind to headerless sections; degrades on the PDF-reconciliation case exactly where needed. |
| **Structural move-gate** ("only a move if paths align") | Measured to demote 400+ genuine relocations — real moves cross subtrees by definition, like false ones. |
| **Optimal (Hungarian) assignment** | The literature reports greedy captures most of the benefit; the 119-hr-1 collision already resolves acceptably. Not the lever until the *measure* is fixed. (Greedy/optimal gap unmeasured on our data.) |
| **Embedding / BERT matching** | Black-box w.r.t. boilerplate, adds install weight and reduces auditability, harder to explain to a non-technical audience. Benchmark as a ceiling, don't ship as default. |
| **Adopt Akoma Ntoso ids / amendment-grammar parsing** | Amendment-grammar doesn't apply (consecutive versions carry no amendment instruction to parse). The XML `@id` *is* stable on some transitions (cross-chamber hand-off 16/16; bimodal within a chamber) but is a thin, conflict-prone matching key — ~59 conflict-free net-new matches corpus-wide, 34/93 candidates contradicting the path matcher — so a guarded low-priority supplement, not an identity.[^src-audit] |
| **GumTree-style descendant propagation** | Promising for renumber detection, but inherits a documented name-blind false-match risk; defer until after the text core, and scope it to blocks. |

---

## 8. Limitations and threats to validity

Stated plainly, because this is the section a reviewer should push on hardest.

1. **Small, narrow hand-labeled set.** 12 pairs from 4 bills. Enough to *sanity-check* a rule, not
   to *calibrate* one. Small-sample cross-validation estimates are high-variance, and 12 labels
   support at most one or two fitted parameters. Our two cutoffs are therefore **directional, not
   fitted** — justified by the corpus-wide census (§6.2), not by the 12/12.

2. **The labeled set cannot test containment's own failure mode** (the most important limitation).
   Every "different"-labeled pair in the set has containment ≤ 0.528; the keep bar is 0.70. So
   there is **no "different" test point anywhere in containment's high-confidence regime** — the
   set structurally cannot exercise the false-keep mode that §6.3 and §6.4 show is real and, on the
   hardest bill, dominant. A perfect score on a set that omits the failure regime is exactly why
   12/12 is a warning sign rather than a result. The next study's stratification must fix this
   directly (§9).

3. **The baseline comparison must be like-for-like.** The headline gain is 2 pairs over a *re-
   tuned* word-overlap (10/12), not 6 pairs over the *production* baseline (6/12); and the 6/12 is
   partly a property of how the set was built (§5, §6.2). Any future reporting should quote the
   re-tuned baseline.

4. **Cutoffs do not yet generalize (measured).** Leave-one-bill-out is 10/12, and the misses are
   cutoff-boundary cases (§6.5). We can trust the *measure*; we cannot yet fix a *cutoff* for
   production.

5. **Corpus composition bias, and it is smaller than first counted.** The analyzed corpus is 31
   bills, appropriations-heavy, with one reconciliation bill (119-hr-1) and no authorization/tax
   bills. (An earlier draft said "44 bills"; that counted 13 unextracted archives that contribute
   to no number — they should be processed, §9.) Drafting conventions and boilerplate vary by bill
   type; a measure calibrated on appropriations text may not transfer. Our one cross-type data
   point (Alien SNAP) is encouraging but is a single point.

6. **The rarity model is corpus-derived** (but robust). Word rarities come from our 31 bills. A
   future bill with novel vocabulary would move the weights — though we measured that removing any
   one current bill barely moves them (§6.5). The measure should be monitored, not frozen.

7. **Containment's failure modes are real, not hypothetical** (§6.3–6.4). The recommendation
   depends on structural confirmers to catch them; that combination is designed but **not yet
   measured** end-to-end — a later-study target (§10), not a proven result.

8. **PDF acceptance is unproven.** The text measure is computable on PDF, but we have not run the
   full matcher on a PDF-only fixture. The reconciliation-bill degradation (§4) is the hard case
   and must be a named acceptance test.

9. **"Same provision" is sometimes genuinely ambiguous.** A handful of corpus pairs (a section
   number reused for a related-but-different provision; a fund repointed to a new statute) are
   judgment calls a reasonable human could rule either way — including two of the "context" rows in
   §6.1, which is why they are marked *assumed* rather than labeled. No measure will be "correct" on
   these; the goal is to match a documented human standard, which is another reason the labeled set
   must grow and be adjudicated carefully.

---

## 9. The blocking prerequisite: expand and re-stratify the labeled dataset

**We should not fix production cutoffs, nor pick a final matcher, until the labeled dataset is
materially larger and — critically — stratified to include the cases the current set cannot
test.** §8 makes this concrete: the measure is trustworthy, the calibration is not, and the one
failure mode that matters most is invisible to the current set. Proposed methodology:

- **Target size.** Move from 12 pairs toward the low hundreds at least (the one rigorous US-bill
  study used ~4,700). Even a few hundred well-chosen pairs would turn "directional cutoff" into
  "calibrated cutoff with a held-out estimate of error."
- **Stratify deliberately** — and note the two strata the current set is *missing entirely*, which
  are now the highest priority:
  - **(NEW, top priority) High-containment "different" pairs** — a short provision that shares a
    rare token (a statute citation) with an unrelated large provision, scoring containment ≥ 0.7
    but truly *different*. Without these, no test set can detect containment's false-keep mode
    (§8.2). Mine these directly from the §6.4 consolidation clusters.
  - **(NEW) Many-to-one consolidation pairs** — the §6.4 "absorbed into" case, each old provision
    labeled *genuinely absorbed* (statute target appears in the new section) vs *coincidentally
    contained*. This is the ground truth needed to represent consolidation at all.
  - by **bill type** (appropriations, reconciliation, authorization, tax — sample beyond
    appropriations on purpose);
  - by **failure mode** (boilerplate-shared, stub→expansion, reused number, genuine renumber,
    cross-agency relocation, amount-only edit);
  - by **transition distance** (adjacent versions *and* the deliberate-rewrite jumps like
    119-hr-1's Senate consolidation);
  - by **engine** (XML and PDF, including a PDF-only reconciliation sample where structure
    degrades);
  - by **difficulty** (clear-cut anchors *and* ambiguous-band judgment calls).
- **Process the ~13 unextracted bills** (§5, §8.5) as part of the mining pool — a cheap way to
  widen bill-type coverage.
- **Hold out a true test set.** Reserve a portion of the labels *never* used to set cutoffs, and
  report performance on it separately. This is the single most important guard against overfitting:
  it measures the generalization gap instead of assuming it away.
- **Define the baseline fairly.** Fix the comparison as *re-tuned* word-overlap, so future
  measurements are like-for-like (§8.3).
- **Adjudicate the judgment calls.** For genuinely ambiguous pairs (§8.9), record the rationale
  and, ideally, a second labeler, so "ground truth" is a documented standard rather than one
  person's call.
- **Automate candidate mining, keep labeling human.** Cheaply surface candidate pairs in each
  stratum (pairs whose measures disagree; high-containment cross-citation pairs; consolidation
  clusters) for a human to rule — the sampling is assisted, the labeling stays human.

This is a self-contained workstream and the honest gate before further engineering.

---

## 10. A multi-study program

Settling on a methodology takes **several studies across multiple sessions**, not one. This study
characterized the problem and measured a first candidate. A proposed sequence — each a
self-contained deliverable that can revise the ones before it:

- **Study 1 (this document): characterize + first candidate.** Problem framing, signal inventory,
  method survey, and the measured finding that rare-token containment resolves the stub→expansion
  pattern word-overlap cannot. Output: this study.
- **Study 2: expand and re-stratify the labeled dataset, with a held-out test set (§9).** The
  blocking prerequisite — nothing downstream can be calibrated without it, and it must add the two
  missing strata (§9). Output: a materially larger labeled set + a labeling protocol.
- **Study 3: measure generalization across bill types.** Deliberately test reconciliation,
  authorization, and tax bills, not just appropriations. Does containment's separation hold? Where
  do the cutoffs move? Output: a generalization report that confirms or breaks the Study 1
  hypothesis.
- **Study 4: head-to-head of finalists** on the expanded, stratified set + a hand-checked corpus
  census: (a) two-signal text rule (the baseline to beat); (b) **the hybrid, run end-to-end so the
  structural half is finally *measured* rather than asserted** (§7); (c) an embedding text term as
  a measured ceiling. Output: a chosen matcher design with held-out error estimates.
- **Study 5: the hard structural relationships.** Many-to-one consolidation / "absorbed into"
  (§6.4), cross-version tracing, and PDF-only acceptance (with the reconciliation degradation as
  the hard case). Output: a diff-vocabulary and matcher extension for the adversarial cases.
- **Study 6: implementation + regression gates.** Only after the above — frame the engineering as
  one multi-signal scorer, and update the pinned hard-case tests *with* precision/recall evidence.

Each study should stress-test the prior studies' conclusions rather than assume them. Nothing here
is a decision yet; it is a route to one.

---

## Appendix A — Reproducibility

All measurements come from scripts in `probes/` (run with the repo venv,
`PYTHONPATH=. .venv/bin/python <script>`):

| script | what it measures | key numbers |
|---|---|---|
| `probe1_signals.py` | structural signals per hand-labeled pair | header coverage, the Tanker header inversion |
| `probe_classifier.py` | the structural-only rule on the 12 pairs | 12/12 but see corpus stress |
| `probe_corpus.py` | corpus-wide header coverage, collisions, floor-raise risk | the coverage table; 14 floor-raise flips |
| `probe_b1_tfidf.py` | word-overlap vs cosine vs containment on the 12 pairs + risks | §6.1 table |
| `probe_b1_validate.py` | full-corpus containment behavior + failure modes | new-split/new-keep census |
| `probe_b2_multisignal.py` | the two-signal rule, leave-one-pair-out, corpus census | 12/12; 25 changes |
| `probe_generalization.py` | leave-one-*bill*-out; held-out-IDF signals | 10/12; §6.5 |
| `probe_consolidation.py` | 119-hr-1 Senate consolidation stress test | 17 unchanged; 265 candidates; 74 one-to-one; 41 many-to-one absorbing 191; fan-in 30; 88 reverse-direction (§6.4) |
| `probe_review_gameability.py` | controlled short-provision false-positive rate for containment | negative-control probe added during review (§6.4 failure mode) |

Two claims in the text are *not* probe-derived and are labeled as such where they appear: the §4
PDF Tanker/Alien-SNAP structural facts (a manual observation of the two PDFs) and the §3/§7
greedy-vs-optimal "most of the benefit" characterization (from the assignment literature, not
measured on our data). The corpus size is **31 extracted bill directories**; the header-coverage
percentages map the raw leaf tags (`appropriations-intermediate/-major/-small`) to the
agency/department/account labels used in prose.

Companion documents: `methodology.md` (the fuller working draft this study
formalizes), `problem-framing.md` (the short naming note), `spike.md` (the
earlier structural exploration this study supersedes), and the source-signal audit
`docs/source-signal-inventory.md` (a corpus-wide inventory of PDF/XML signals; reproducer
`scripts/audit_source_signals.py`), which measured the `@id`-stability, change-markup, and
`@level` facts cited in §3, §4, and §7.

## Appendix B — References

Numbered by first appearance. (The internal source-signal audit is cited separately as a named note,
`[src-audit]`, and is not one of these numbered references.) Page ranges are given for the canonical
works; for claims that rest on a specific result, the in-paper equation / table / figure / section is
cited. Where a precise page was not verified, the venue and a locating section are given rather than a
guessed page.

*All 18 references were independently checked against primary sources in a separate verification
pass (2026-07-10); the citations themselves held up, with corrections applied to five items —
[1] locator, [5] venue, [6] section locator, [7] algorithm number + label wording, [18] title.
Three older works ([12], [13], [14]) are paywalled and were confirmed via authoritative
bibliographic records and peer-reviewed secondary sources rather than a primary read. Note that
the review corrected how two of these works are **interpreted** in the body — the Cohen [1]
IDF↔Fellegi-Sunter relation is a motivating approximation, not a proof, and the BM25 [4] link is
a close analogy, not an equivalence — see §3.*

[^1]: Cohen, W. W., Ravikumar, P., & Fienberg, S. E. (2003). *A Comparison of String Distance Metrics for Name-Matching Tasks.* Proc. IJCAI-2003 Workshop on Information Integration on the Web. The IDF-as-Fellegi-Sunter connection ("SFS") and Soft-TFIDF are defined in the (unnumbered) Methods section — subsections "Token-based distance functions" and "Hybrid distance functions" respectively. https://www.cs.cmu.edu/~wcohen/postscript/ijcai-ws-2003.pdf

[^2]: Manning, C. D., Raghavan, P., & Schütze, H. (2008). *Introduction to Information Retrieval*, Cambridge Univ. Press, ch. 6 — idf (eq. 6.7), tf-idf (eq. 6.8), cosine (eq. 6.10), sublinear tf (eqs. 6.13–6.14). https://nlp.stanford.edu/IR-book/pdf/06vect.pdf

[^3]: Tversky, A. (1977). *Features of Similarity.* Psychological Review, 84(4), 327–352 — the asymmetric index; set the α/β weights to barely penalize content unique to the longer side (containment).

[^4]: Robertson, S., & Zaragoza, H. (2009). *The Probabilistic Relevance Framework: BM25 and Beyond.* Foundations and Trends in Information Retrieval, 3(4), 333–389 — the length-normalization parameter *b* (turn toward 0 for the stub→expansion case).

[^5]: Kim, J., Griggs, E., Kim, I. S., & Oh, A. (2021). *Learning Bill Similarity with Annotated and Augmented Corpora of Bills.* Proc. of the 2021 Conference on Empirical Methods in Natural Language Processing (EMNLP 2021, main conference), pp. 10048–10064 — 4,721 hand-labeled subsection pairs; classifies on BERT / Legal-BERT content embeddings, using no positional or structural features. https://arxiv.org/abs/2109.06527

[^6]: Wang, Y., DeWitt, D. J., & Cai, J.-Y. (2003). *X-Diff: An Effective Change Detection Algorithm for XML Documents.* Proc. ICDE 2003, pp. 519–530 — the node signature = ancestor-name path (Def. 3.6, §3.5), and only same-signature nodes are compared. https://pages.cs.wisc.edu/~yuanwang/papers/xdiff.pdf

[^7]: Falleri, J.-R., Morandat, F., Blanc, X., Martinez, M., & Monperrus, M. (2014). *Fine-grained and Accurate Source Code Differencing.* Proc. ASE 2014, pp. 313–324 — two-phase matcher; bottom-up container matching by the Dice coefficient of already-matched descendants (Algorithm 2). The bottom-up step requires the two nodes' **type** to match and ignores their **value** — the "name-blind" behavior Frick et al. later document. https://hal.science/hal-01054552/document

[^8]: Frick, V., Grassauer, T., Beck, F., & Pinzger, M. (2018). *Generating Accurate and Compact Edit Scripts using Tree Differencing.* Proc. ICSME 2018 — instruments GumTree over 307,081 Java revisions; >55% of its move/update actions inaccurate (Table VI: MOVE 58.2% / UPDATE 40%); the name-blind/type-only cause is §II. https://pinzger.github.io/papers/Frick2018-ijm.pdf

[^9]: Madhavan, J., Bernstein, P. A., & Rahm, E. (2001). *Generic Schema Matching with Cupid.* Proc. VLDB 2001, pp. 49–58 — weighted sum of linguistic + structural (leaf-set) similarity, with leaf↔ancestor propagation. https://www.vldb.org/conf/2001/P049.pdf

[^10]: Do, H.-H., & Rahm, E. (2002). *COMA — A System for Flexible Combination of Schema Matching Approaches.* Proc. VLDB 2002 — meta-matching; across many strategy combinations, combining the individually-weak hybrid matchers (avg. Overall ≈ 0.73) beat every single matcher. https://dbs.uni-leipzig.de/files/research/publications/2002-1/pdf/COMA.pdf

[^11]: Melnik, S., Garcia-Molina, H., & Rahm, E. (2002). *Similarity Flooding: A Versatile Graph Matching Algorithm.* Proc. ICDE 2002, pp. 117–128 — fixpoint propagation over a pairwise-connectivity graph. https://web.archive.org/web/20201124040436/http://ilpubs.stanford.edu:8090/730/1/2002-1.pdf

[^12]: Zhang, K., & Shasha, D. (1989). *Simple Fast Algorithms for the Editing Distance Between Trees and Related Problems.* SIAM J. Computing, 18(6), 1245–1262 — ordered tree edit distance via keyroot/forest decomposition.

[^13]: Zhang, K., Statman, R., & Shasha, D. (1992). *On the Editing Distance Between Unordered Labeled Trees.* Information Processing Letters, 42(3), 133–139 — unordered TED is NP-complete (reduction from exact-cover-by-3-sets).

[^14]: Fellegi, I. P., & Sunter, A. B. (1969). *A Theory for Record Linkage.* J. American Statistical Association, 64(328), 1183–1210 — per-field agreement weight = log(m/u); weights sum across fields.

[^15]: OASIS *Akoma Ntoso* Core v1.0, Part 1 (Vocabulary) — eId churns per version, wId asserted against a master Expression, never computed (https://docs.oasis-open.org/legaldocml/akn-core/v1.0/akn-core-v1.0-part1-vocabulary.html). U.S. House *USLM* User Guide — @id re-minted on copy, so by the *standard's* stated semantics it does not persist across independently-generated bill versions (measured GPO bill-XML behavior is transition-dependent — a cross-chamber hand-off preserves it; see [^src-audit]) (https://xml.house.gov/schemas/uslm/1.0/USLM-User-Guide.pdf).

[^16]: Hershowitz, A., & Mador-Haim, S. (2023). *Comparative Prints Suite of the United States House of Representatives: NLP for Tracking Changes in Bills and Laws.* JURIX 2023, Frontiers in Artificial Intelligence and Applications, vol. 379, pp. 379–382 — a grammar of amendatory phrases parses the amending instrument's own citation language. https://ebooks.iospress.nl/doi/10.3233/FAIA230993

[^17]: GovTrack `xml_diff` (J. Tauberer) — the redliner is explicitly structure-blind (word-level diff via diff-match-patch; moves render as delete+insert). https://github.com/JoshData/xml_diff

[^18]: Zhu, X., Klabjan, D., & Bless, P. N. (2017). *Semantic Document Distance Measures and Unsupervised Document Revision Detection (wTED).* Proc. IJCNLP 2017, pp. 947–956 — tree edit distance with word2vec-based leaf-content similarity; the closest methodological analogue outside the legal domain. https://arxiv.org/abs/1709.01256

[^src-audit]: DeltaTrack source-signal audit, `docs/source-signal-inventory.md` (snapshot 2026-07-10; PR #197). Corpus-wide inventory of the signals the source PDFs and XMLs carry, measured across 102 XML versions (31 bills, 17 multi-version) and 87 PDFs by the committed reproducer `scripts/audit_source_signals.py` — not a maintained invariant. Source of the `@id`-by-transition table, the ~59 conflict-free / 34-conflicting id-match decomposition, the change-markup presence-by-version-type counts, and the `toc-entry@level` / `header-in-text@level` coverage.
