# Matching provisions across bill versions: methodology research

An in-depth study of *how* to decide which provision in one bill version is "the same
provision" as one in the next — the matching problem underneath DeltaTrack's diff. Written
to (a) explain the methodology we should use and why, and (b) lay out the full universe of
options with tradeoffs, so the choice is defensible and a few finalists can be prototyped
head-to-head.

Bound to the **problem** (hard matching/diffing of versioned structured documents), not to
#170's specific solution. Companions: `spike.md` (the structural-signal spike),
`problem-framing.md` (the short naming note). This doc supersedes their
recommendation with a measured, literature-grounded one.

Every number here is measured on the real corpus (44 bills; 17 with ≥2 adjacent versions;
70 adjacent version pairs; 30,605 matched node pairs; 1,287 matched-and-changed pairs) or on
the 12-pair #8 hand-labeled answer key and the 119-hr-1 worked case. Reproduction scripts in
the session scratchpad (`probe_*.py`).

---

## 0. The bottom line

**The single highest-leverage change is a better *text* similarity measure, not more
structural machinery.** A rare-token measure (IDF-weighted **containment**, a weighted
Tversky index) cleanly separates "same provision, edited" from "different provision, reused
number" across the exact dead zone where today's word-overlap ratio has no skill — scoring
**12/12** on the #8 answer key (today's baseline: 6/12), including all six pairs the spike
could not resolve, while changing only ~25 of 1,287 corpus decisions.

**But no single signal is sufficient, and the literature and our data agree on why.** The
text measure has two characterizable failure modes that *structural* signals fix, and the
structural signals have blind spots (headerless sections, PDF degradation) that the text
measure covers. The right architecture is the one schema-matching and record-linkage have
used for 20 years: **combine several weak matchers into one calibrated score** (Fellegi-
Sunter / COMA), with `match_path` as a *blocking key* (never an identity), rather than
tuning a single threshold.

**Recommendation:** prototype a **hybrid multi-signal matcher** — rare-token containment as
the primary text term, word-overlap ratio as a guard for amount-only edits, and the tree
signals (account-path equality, header equality, parent-path) as complementary confirmers —
calibrated on an *expanded* answer key. This reframes #170 (structural signals) and #171
(rare-token text) as two terms in one scorer, not competing patches. Two or three finalists
worth a head-to-head bake-off are named in §7.

A notable finding from the literature sweep: **no published system does what we're
proposing.** Every deployed legislative tool either relies on persistent legislature-
assigned ids (which US bill versions don't carry), on human curation (national archives run
weeks-to-months of backlog), or on parsing the amendment instrument's own citation grammar
(not available for our version-to-version case). Combining header-name similarity with tree-
path similarity for independently-republished versions is a genuine gap in the public
record — so we should design deliberately and measure, not look for a library to copy.

---

## 1. The problem in plain terms

DeltaTrack lines up two versions of a bill and reports what changed per provision. The core
decision, made thousands of times per bill pair: **given a provision in the old version and
one in the new, are they the same provision (an edit) or different provisions (a
removal + an addition)?** Everything downstream — the change counts, the money diff, the
"moved" labels — depends on getting that pairing right.

Three real examples from our corpus make the difficulty concrete. Keep these in mind; the
whole report returns to them.

- **Alien SNAP (119-hr-1, reported → engrossed).** Section 10012 "Alien SNAP eligibility"
  starts as an 81-character stub (`Section 6(f) of the Food and Nutrition Act… is
  amended—`) and becomes a 2,242-character fully-written provision. It is obviously the
  *same* provision, expanded. Yet word-overlap similarity is **0.078** — near zero — because
  the new text is 28× longer. Today the tool wrongly tears it into a removal + an addition.

- **Tanker Security Program (118-hr-4366).** The same appropriations account, funding cut
  $120M → $60M with a long proviso appended. Same account, edited. Word-overlap **0.255** —
  the long added proviso dilutes it below the keep threshold, so again a false split.

- **Section 232 (114-hr-2029).** A general-provisions section whose number is *reused* for
  an unrelated provision: old requires 15-day notice before moving VA staff; new requires
  quarterly notice of marketing campaigns. *Different* provisions. Yet word-overlap is
  **0.429** — the shared "The Secretary of Veterans Affairs shall provide… to the Committees
  on Appropriations…" boilerplate props it above the 0.40 keep threshold, so the tool wrongly
  keeps them linked.

Notice the trap: **Alien SNAP (same) scores 0.078 while Section 232 (different) scores
0.429.** The correct answer is *inversely* related to the similarity score. That is not a
threshold that needs tuning; it is a measure that is asking the wrong question.

### What actually makes it hard — three failure modes

| failure mode | example | why word-overlap fails |
|---|---|---|
| **Boilerplate inflation** | Section 232 | Two unrelated provisions share appropriations boilerplate ("None of the funds…", "is amended by striking…"), which is a large fraction of short legal text, inflating overlap. |
| **Stub → expansion** | Alien SNAP, Tanker | The same provision grows many-fold; a symmetric length-normalized measure collapses because most of the new text is unmatched. |
| **Unstable identifier** | reused Sec. 232; renumbered Sec. 237→234 | The section number is not a reliable identity: it gets reused for new content and reassigned to the same content. |

### What it's called (so we can borrow solutions)

This sits at the intersection of three mature literatures, each with a name and a toolbox:

1. **Hierarchical change detection / tree differencing** — computing the edit script
   (including *moves*) between two trees. (XML-diff, source-code diff.)
2. **Entity resolution / record linkage** — deciding which record in A is the same entity as
   one in B, by combining several field-level similarity signals. (The Fellegi-Sunter
   framework.)
3. **Natural-key instability (temporal entity resolution)** — the specific reason it's hard:
   the obvious key (section number) is not stable, so it can only be a *blocking* device, not
   proof of identity.

In one sentence: **entity resolution over an ordered, hierarchical document whose natural key
is unstable.**

---

## 2. What signals our data actually gives us

Before surveying methods, an inventory of what the XML and PDF pipelines actually expose per
provision — because a method is only as good as the signals it can read, and the two engines
differ.

### XML (`bill_tree.BillNode`) — the rich pipeline

| signal | field | what it is | cross-version reliability |
|---|---|---|---|
| normalized path | `match_path` | lowercased, division-excluded, title-enum-stripped tuple, e.g. `(department of veterans affairs, administrative provisions, sec. 232)` | The join key today. Stable *except* the section-number leaf, which is the unstable part. |
| display path | `display_path` | division-qualified, cased, e.g. `Division J: … › TITLE II—… › sec. 232` | Churns on division re-lettering / title renumber — **not** a match key. |
| leaf level | `tag` | `appropriations-major/intermediate/small` (money accounts), `section`, `subsection`, `front-matter` | Reliable and typed. |
| header/catchline | `header_text` | the provision's title, e.g. `Alien SNAP eligibility`, `salaries and expenses` | **Coverage varies sharply by level (below).** |
| section number | `section_number` | e.g. `Sec. 232` | The unstable identifier itself. |
| body | `body_text` | the provision prose | Always present; the substrate for any text measure. |
| division | `division_label` | e.g. `Division A: …` | Display only; excluded from matching by design. |

**Header coverage by leaf level (corpus-wide) — a load-bearing number:**

| leaf level | has a header |
|---|---|
| agency (`appropriations-intermediate`) | 98.2% |
| department (`appropriations-major`) | 94.7% |
| account (`appropriations-small`) | 88.5% |
| subsection | 65.3% |
| **section** (general/administrative provisions) | **21.2%** |
| front-matter | 0% |

The header is a strong identity signal for *money accounts* but is **absent for ~4 of 5
bare sections** — exactly the provisions (like Section 232) where the reused-number problem
bites. So "use the section header" is not a general fix; it's an account-level fix.

### PDF (`parsers.pdf_anchors.Anchor`) — the degraded pipeline

The PDF has no `match_path`. It emits a stream of typed *anchors* (`kind` ∈ title / major /
agency / account / grouping / section / subsection; `text` = the heading label; `division`),
and `breadcrumb_for()` reconstructs a path. Body text is reconstructed from the page lines
between anchors — so a text measure is computable on PDF too. The catch (ADR 0012): **tree
depth and label capture are detection-path dependent.** Measured on our two worked bills:

| bill | PDF anchor kinds | Tanker / Alien SNAP |
|---|---|---|
| 118-hr-4366 (appropriations) | title 33, major 32, agency 181, account 515, grouping 89, section 578, subsection 104 | `TANKER SECURITY PROGRAM` captured as an **account** with full breadcrumb `DOT › MARITIME ADMINISTRATION › TANKER SECURITY PROGRAM` ✅ |
| 119-hr-1 (reconciliation) | title 11, section 335, subsection 866, account **1** | `SEC. 10012` captured, but breadcrumb is only `TITLE I › SEC. 10012` — **the "Alien SNAP eligibility" catchline is NOT captured, and the "Committee on Agriculture › Nutrition" levels are absent** ❌ |

**This is the decisive per-engine fact.** On the appropriations bill the PDF structure is
rich; on the reconciliation bill it collapses and the disambiguating header is gone. A
matcher that leans on the header/agency structure shines on XML and PDF-appropriations but
goes blind on PDF-reconciliation. **A text measure over the reconstructed body is available
on *both* engines** — and it was the text measure (containment = 1.0) that fixed Alien SNAP.
Text degrades gracefully across engines; structure does not.

---

## 3. The universe of options

Organized by family. For each method: the intuition (with one of our examples), what it needs
from our data, and the tradeoff. Methods we measured are flagged **[measured]**; the rest are
characterized from the literature and our signal inventory.

### Family A — Better text similarity (the record-linkage family)

The insight tying this family together, proven by Cohen, Ravikumar & Fienberg (2003): **IDF
weighting is a special case of the Fellegi-Sunter match score.** Agreeing on a rare token is
strong evidence of a match; agreeing on a common one is weak. Everything here is a way to
operationalize "reward rare shared content, discount boilerplate."

- **Word-overlap ratio (today's baseline).** `difflib` longest-common-subsequence ratio over
  word sequences. *Intuition:* what fraction of words line up in order. *Fails* all three
  modes in §1 (boilerplate counts full, length dilutes, order-sensitive). *Needs:* nothing.
  *Keep it for one thing:* it is high (0.83) for an amount-only edit of a short account line
  (`For Office of the Secretary, $25,783,000 → $26,315,000`), where the rare-token measures
  stumble (below).

- **TF-IDF cosine.** Build an IDF table over the corpus (a token's weight ∝ how rare it is
  across provisions); represent each provision as a weighted token vector; score by cosine.
  *Intuition:* boilerplate tokens get ~zero weight, so two provisions that share only
  boilerplate score low. **[measured]** — fixes the boilerplate cases (Section 232: 0.429 →
  **0.322**; ag-to-HHS: 0.629 → **0.225**). *But* cosine normalizes each vector by its own
  length, so it **fails stub→expansion**: Alien SNAP scores only 0.243 (the expansion's many
  new tokens inflate the denominator). *Needs:* a corpus for IDF. *Tradeoff:* fixes mode 1,
  not mode 2.

- **IDF-weighted containment (weighted Tversky index) — the standout. [measured]** Instead of
  cosine's symmetric normalization, normalize the weighted overlap by the *smaller* side's
  mass: "is the lighter provision's meaningful content contained in the heavier one?" This is
  the Tversky index with the asymmetric knob set to barely penalize content unique to the
  longer side (equivalently, BM25 with length-normalization turned off). *Intuition:* a stub
  fully contained in its expansion scores ~1.0; two different provisions sharing only
  boilerplate score low because boilerplate carries little weight. It fixes **both** modes at
  once:

  | pair | truth | word-ratio | cosine | **containment** |
  |---|---|---|---|---|
  | Section 232 (reused #) | different | 0.429 | 0.322 | **0.432** |
  | ag-to-HHS (boilerplate move) | different | 0.629 | 0.225 | **0.528** |
  | anchor-diff-780 | different | 0.154 | 0.139 | **0.238** |
  | — clean gap — | | | | |
  | Tanker (account edit) | same | 0.255 | 0.62 | **0.929** |
  | Alien SNAP (stub→expand) | same | 0.078 | 0.243 | **1.0** |
  | sec 8144 (headerless stub→expand) | same | 0.554 | 0.733 | **1.0** |

  On the split decision, containment separates every #8 pair: **different ≤ 0.43, same ≥
  0.69** — a 0.26-wide gap, versus no clean threshold for word-ratio. *Needs:* a corpus for
  IDF (we built one: 64,276 provision bodies, 20,587 tokens). *Two failure modes, both
  structure-addressable* (§5): (i) amount-only edits of short account lines dip (the changed
  dollar figure is a rare token that dominates a short vector); (ii) a short old provision
  whose few tokens coincidentally sit inside a large unrelated new one over-keeps.

- **Soft TF-IDF (Cohen et al. 2003).** TF-IDF but count near-matching tokens (via a
  secondary string similarity like Jaro-Winkler, θ≈0.9), not just exact matches. *Intuition:*
  handles "Dept." vs "Department", "sec. 101" vs "Section 101", and PDF/XML extraction noise.
  *Needs:* corpus + a secondary metric; ~10× slower. *Tradeoff:* helps token-level variants
  (useful for PDF↔XML parity), not the stub or boilerplate modes. A refinement, not the core.

- **BM25.** Retrieval-style asymmetric score (treat the shorter provision as the "query").
  Its two knobs — term-frequency saturation and length normalization — are exactly the levers
  for boilerplate repetition and stub→expansion. Essentially a tunable cousin of containment.

- **Embedding cosine (BERT / LEGAL-BERT).** Dense semantic vectors; catches same-meaning-
  different-wording. *This is what the one rigorous US-bill study (Kim et al., EMNLP 2021)
  uses* — and notably it *discards position entirely* and matches on content embeddings
  alone. *Tradeoff for us:* a black box w.r.t. "discount boilerplate", needs a model
  dependency (against our local-install constraint), and is heavier to justify to a
  non-technical audience than an explainable IDF score. Worth benchmarking as a ceiling, not
  a default.

### Family B — Structural / tree matching

- **Exact path equality (today).** Pair nodes with identical `match_path`; resolve collisions
  (same path, multiple nodes) by text similarity. *Intuition:* the section's structural
  address is its identity. *Fails* when the address is unstable: reused numbers collide,
  renumbers break the match (they fall through to the move-rescue). *This is X-Diff's
  "signature" idea* — and X-Diff's lesson is that **signature construction is the lever**: our
  `match_path` bakes in the section number, which is why renumbers break it. Dropping the
  number from the *children's* key would make them renumber-tolerant.

- **GumTree bottom-up propagation.** Match two container nodes when a large fraction of their
  *descendants* already matched (Dice coefficient ≥ 0.5), **ignoring the container's own
  label**. *Intuition:* an account is "the same account" if its sections matched, even if its
  name/number changed — renumber-tolerant by construction. *Tradeoff, documented in the wild
  (Frick et al., 307k Java revisions):* because it's **name-blind**, it also mis-matches two
  differently-named containers that happen to be structurally similar — up to 55% of its
  move/update actions were misclassified. It trades the text-boilerplate problem for a
  *structure*-boilerplate problem (two "Salaries and Expenses" accounts look alike). *Needs:*
  a materialized tree with descendant sets — which #108 gives us.

- **Cupid / COMA / Similarity Flooding (schema matching).** The family that formalized
  "combine name similarity + structural position." **Cupid**: weighted sum of linguistic
  (header) and structural (leaf-set overlap) similarity, with similarity propagated between a
  matched parent and its leaves. **COMA**: run several matchers and aggregate (their benchmark
  favors simple averaging; combining beat every single matcher). **Similarity Flooding**:
  iterate "if my neighbors match, I match more" to a fixpoint — disambiguate a node by its
  matched neighbors. *Tradeoff:* more moving parts and thresholds; the payoff is robustness
  from redundancy. These are the *architecture* we should borrow even if we don't implement
  them verbatim.

- **Tree edit distance (Zhang-Shasha; ordered vs unordered).** The principled "minimum edit
  script" foundation. *Ordered* TED is polynomial (cubic) but forces sibling order to be
  meaningful; *unordered* TED (what "same account regardless of position" really wants) is
  **NP-hard**. *Tradeoff:* too heavy and too rigid to run whole-document; its value is
  conceptual (it's what GumTree/X-Diff approximate) and local (bounded to a small collision
  block). Bills are *ordered*, so if position enters at all it is via LCS alignment of
  siblings, never absolute index.

### Family C — Combining and assigning

- **Fellegi-Sunter weighted score.** Combine per-signal agreements into one log-odds score;
  each signal's weight reflects how much its agreement distinguishes matches from non-matches.
  *This is the formal home for "header + path + containment + word-ratio → one decision."* Our
  spike's hand-tuned rule and the two-signal text rule are informal instances.

- **COMA meta-matching.** The practical, less-statistical version: run the matchers, average
  (or weight) their scores, threshold. Robust, explainable, easy to add a matcher to.

- **Greedy vs optimal (Hungarian) assignment.** Within a collision block, today's greedy
  "highest similarity first" can be replaced by minimum-cost bipartite assignment for a
  globally consistent pairing. *Tradeoff:* the literature (and our 119-hr-1 check) says greedy
  reaches ~93% of optimal with good inputs and is O(n) vs O(n³); the 119-hr-1 collision
  already pairs correctly under greedy. **Not the lever** — worth it only for large collision
  blocks, and only after the similarity *measure* is fixed.

### Family D — Domain-specific approaches (and why they don't transfer)

- **Akoma Ntoso / USLM persistent ids.** The legislative-XML standards carry a cross-version
  element id (`wId`). *But it is asserted at authoring time, never computed.* Whether GPO's `@id`
  survives a version boundary is **transition-dependent, not uniformly regenerated** (measured
  corpus-wide — see `paper.md` §3 and the source-signal audit
  `docs/source-signal-inventory.md`): stable across a cross-chamber hand-off (16/16 pairs), bimodal
  within a chamber, regenerated across amendment ping-pong and enrollment. But as a *matching* key
  it is still low-value — only ~59 conflict-free net-new matches corpus-wide (mostly same-senate),
  with 34 of 93 candidates contradicting the path matcher — so the standard *records* an identity
  where the drafter happened to preserve it and does not *find* one. A thin, guarded supplement,
  not a general cross-version id.

- **Amendment-grammar parsing (Xcential Comparative Print Suite — the one production system
  for Congress).** Parses the amending instrument's own citation language ("Section 3 is
  amended by striking…") to locate targets. *Doesn't transfer:* consecutive bill *versions*
  don't cite each other; we have no instruction text to parse.

- **Text-reuse / embedding matchers (GovTrack `xml_diff`, Kim et al., DocuToads, wTED).**
  GovTrack's redliner is explicitly structure-blind (word diff, moves shown as delete+insert).
  Kim et al. and wTED are the closest analogues — and both lean on content similarity
  (embeddings), Kim et al. *discarding position on purpose*. The honest read: **the hybrid
  header+path+rare-token direction is a gap in the record**, not a solved problem to copy.

---

## 4. What we measured — the head-to-head

All on the 12-pair #8 answer key (ground truth) and the full corpus. "Baseline" = today's
single word-ratio floor (0.40 split / 0.60 move).

| approach | #8 score | split precision/recall | move precision/recall | corpus decisions changed | notes |
|---|---|---|---|---|---|
| **Baseline** (word-ratio) | 6/12 | 0.40 / 0.50 | 0.667 / 1.0 | — | the dead zone, unresolved |
| **Structural rules** (spike) | 12/12* | 1.0 / 1.0 | 1.0 / 1.0 | — | *but two of its rules fail corpus stress (§spike): the floor-raise mis-splits genuine headerless edits; the move-gate demotes 400+ real moves. Genuinely safe wins: only 2 of 6. |
| **Rare-token containment alone** | split pairs cleanly separated (Δgap 0.26) | — | — | — | fixes both text modes; own failure modes in §5 |
| **Two-signal text rule** (keep if word-ratio ≥ 0.5 **or** containment ≥ 0.7; moves: containment ≥ 0.7) | **12/12** | 1.0 / 1.0 | 1.0 / 1.0 | **25** (11 new splits, 14 new keeps) | no structural signal used at all; leave-one-out 10/12 (see §6 caveat) |

The two-signal text rule reaching 12/12 **with no structural signal** is the headline: a
better text measure resolves the entire dead zone that both raw text *and* the spike's
structure struggled with. The 25 changed corpus decisions were hand-inspected:

- **New splits (11):** mostly correct (the reused-number provisions: Sec. 232, Sec. 110, Sec.
  204). One clear **false split** — `port infrastructure development program`, an *account*
  reworded (containment 0.674, just under 0.7). It is an account, so an account-path
  structural keep would rescue it.
- **New keeps (14):** mostly correct (Alien SNAP, Tanker, RDT&E accounts re-funded,
  definitions expanded, amount annotations). Two-to-three plausible **false keeps** (some VA
  admin provisions where a short old text sits inside a long unrelated new one, sharing agency
  vocabulary) — the short-in-large coincidence. Header/path scoping would guard these.

**The complementarity is the whole point.** Text containment fixes the dead zone; its two
residual errors are precisely where a *structural* signal (account-path equality; header/path
scoping) is strong. And vice versa — the spike's structural rules can't touch headerless
sections, which containment handles. Neither wins alone; combined, each covers the other's
blind spot. This is exactly COMA's empirical result (combining matchers beat every single
matcher) reproduced on our data.

---

## 5. Why the recommendation is the hybrid, and its failure modes

**Recommended methodology: a multi-signal matcher (Fellegi-Sunter / COMA architecture).**

1. **Blocking.** Keep `match_path` as the *candidate-generation* key (it's cheap and mostly
   right), explicitly treated as an unstable natural key — a way to form small candidate sets,
   never proof of identity. This is standard record-linkage blocking and it's what we already
   do; the reframe is conceptual but it licenses the rest.

2. **Primary text signal: rare-token containment.** Replace word-overlap as the *keep/split*
   and *move* similarity with IDF-weighted containment. This is the biggest single accuracy
   gain and it works on *both* engines (§2).

3. **Guard signal: word-overlap ratio.** Retain it only for its one strength — high on
   amount-only edits of short account lines — as an OR-guard so containment's short-line dip
   doesn't false-split "$25,783,000 → $26,315,000".

4. **Structural confirmers (where available): account-path equality; header equality
   (collision-scoped, generic-catchline-guarded); parent/agency-ancestor for move
   classification.** These rescue containment's two failure modes (account false-splits;
   short-in-large false-keeps) and add the renumber-vs-relocate distinction. On PDF-
   reconciliation, where structure degrades, the matcher leans on the text terms and still
   gets Alien SNAP right.

5. **Combine, don't sequence.** Score each candidate pair on all available signals and
   combine (COMA-style average, or a small Fellegi-Sunter weighting), threshold the combined
   score. Calibrate on an *expanded* answer key (§6).

### Adversarial self-check — what would make this wrong

- *Containment's short-in-large false-keep.* A short old provision whose few weighted tokens
  coincidentally appear in a large unrelated new one. Measured: 2-3 cases in the corpus, all
  in VA admin provisions with shared agency vocabulary. Mitigations: require a minimum
  *absolute* weighted overlap (not just the ratio), or combine with cosine (which is low for
  these), or use header/path disagreement as a veto. Must be measured before shipping.
- *Containment's amount-only false-split.* Handled by the word-ratio OR-guard (measured to fix
  the `Office of the Secretary` case). Residual risk if a change is *both* an amount edit and
  a long proviso — but then it's a genuine large edit and either label is defensible.
- *Structure-boilerplate (GumTree lesson).* If we add descendant-based container propagation,
  we inherit the name-blind false-match risk (two "Salaries and Expenses" accounts). Keep
  propagation *scoped* (X-Diff signature blocking) and confirm with header/text, don't let it
  match across the whole document.
- *Overfitting the thresholds.* The clean 12/12 is on 12 points; leave-one-out is 10/12. The
  thresholds are directional, not fitted (§6). The corpus-wide census (25 changes, mostly
  correct) is the real evidence, not the 12/12.
- *IDF instability on a 40-bill corpus.* Singleton tokens get maximal, noisy IDF. Mitigated by
  the smoothed `log((N+1)/(df+1))+1` form (used in the probes) and by building IDF at the
  provision level (64k documents), not the bill level.

---

## 6. Calibration — an honest note on the 12 labels

The literature is blunt here and it matches our `feedback_finding_not_gate` convention: with
**12 labeled pairs you can responsibly fit at most one or two parameters**, not a
multi-feature model (the "one-in-ten" rule of thumb; Firth's penalized regression is the
small-sample fix; leave-one-out AUC is high-variance at this N). Our two-signal rule has
exactly two thresholds and its leave-one-out accuracy is 10/12 — meaning the thresholds are
somewhat sensitive on this tiny set. **Treat every threshold here as directional, validated
by the corpus-wide census, not as a fitted gate.**

Concrete implication: the #8 answer key is too small to *calibrate* a multi-signal matcher —
it can only *sanity-check* one. **Expanding the hand-labeled set (toward the scale Kim et al.
used — thousands of pairs — or at least a few hundred stratified across the failure modes) is
the prerequisite for turning this from "promising rule" into "calibrated matcher."** That is
itself a concrete, fundable next step (and a natural extension of #8's workstream).

---

## 7. What to prototype next (the finalists for a bake-off)

The research narrows the field to a small number of finalists worth building and comparing
head-to-head on an expanded label set + the corpus census:

1. **Containment-primary two-signal text matcher** (§4's rule), XML and PDF. *Cheapest, and
   already 12/12 + 25 sensible corpus changes.* The baseline to beat.
2. **Hybrid: containment + account-path + collision-scoped header**, combined COMA-style. The
   recommended design — adds the structural confirmers that fix containment's two failure
   modes. Prototype measures whether the confirmers remove the 2-3 false keeps / 1 false split
   without new regressions.
3. **(Ceiling check) embedding-cosine text term** (LEGAL-BERT) in place of / alongside
   containment. Not for shipping (local-install constraint, explainability), but as a measured
   ceiling so we know how much accuracy an explainable IDF measure leaves on the table.

Optional structural experiment, lower priority: **GumTree-style descendant propagation** for
collision resolution and renumber detection — but only after (1)/(2), and scoped to blocks,
given the documented name-blind false-match risk.

Each finalist is gated the same way: flip the #8 pairs it should, change only sensible corpus
decisions (hand-checked census), and — for anything touching thresholds — update the pinned
`test_diff_validation.py` dead-zone tests *with* precision/recall evidence, per the epic's
verification gates. PDF acceptance needs a PDF-only fixture (the 119-hr-1 reconciliation case
is the hard one, since its structure degrades).

---

## 8. How this maps back to #170 and the epic

- **#170 ("tree as the structural matching signal")** becomes *the structural-confirmer terms*
  of the combined matcher (account-path, header, parent-path). The spike's finding stands:
  structure alone safely fixes only 2 of the 6 xfails.
- **#171 ("template-aware matching")** becomes *the rare-token text term* (containment / IDF).
  The research de-risks it: containment is the measured fix for the boilerplate dead zone, and
  it is a standard record-linkage method, not a bespoke hack.
- **The epic's "six xfails flip to XPASS" gate** is achievable — but by the *text* term
  (containment: 12/12), not by structure. The spike showed structure caps at 2/6; this shows
  text reaches 6/6. That reframes the acceptance gate and the sequencing.
- **New, larger recommendation:** treat matching as one calibrated multi-signal scorer over an
  ordered tree with an unstable key, and **invest in expanding the labeled set** so the scorer
  can be calibrated rather than hand-tuned. #170 and #171 are two terms in that scorer, not
  two separate patches.

---

## Sources

Text similarity / record linkage: Cohen, Ravikumar & Fienberg, *A Comparison of String
Distance Metrics for Name-Matching Tasks* (2003, IDF-as-Fellegi-Sunter, Soft-TFIDF) —
https://www.cs.cmu.edu/~wcohen/postscript/ijcai-ws-2003.pdf ; Manning et al., *Intro to
Information Retrieval* ch. 6 (tf-idf, cosine) — https://nlp.stanford.edu/IR-book/pdf/06vect.pdf ;
Tversky index — https://en.wikipedia.org/wiki/Tversky_index ; Okapi BM25 —
https://en.wikipedia.org/wiki/Okapi_BM25 ; Splink / Fellegi-Sunter —
https://moj-analytical-services.github.io/splink/topic_guides/theory/fellegi_sunter.html ;
Binette & Steorts, *(Almost) All of Entity Resolution* — https://arxiv.org/pdf/2008.04443 .

Tree / structural diff: Falleri et al., *GumTree* (ASE 2014) —
https://www.labri.fr/perso/falleri/img/slides/ase14.pdf ; Frick et al., *Generating Accurate
and Compact Edit Scripts* (GumTree's name-blind misclassifications) —
https://pinzger.github.io/papers/Frick2018-ijm.pdf ; Wang, DeWitt, Cai, *X-Diff* —
https://pages.cs.wisc.edu/~yuanwang/papers/xdiff.pdf ; Cobéna et al., XyDiff survey —
http://abiteboul.com/gemoReports/GemoReport-221.pdf ; Paaßen, *Tree edit distance tutorial* —
https://arxiv.org/abs/1805.06869 .

Schema matching: Madhavan, Bernstein, Rahm, *Cupid* — https://www.vldb.org/conf/2001/P049.pdf ;
Do & Rahm, *COMA* — https://dbs.uni-leipzig.de/files/research/publications/2002-1/pdf/COMA.pdf ;
Melnik, Garcia-Molina, Rahm, *Similarity Flooding* —
https://web.archive.org/web/2020/http://ilpubs.stanford.edu:8090/730/1/2002-1.pdf .

Legislative prior art: Akoma Ntoso Naming Convention v1.0 —
https://docs.oasis-open.org/legaldocml/akn-nc/v1.0/akn-nc-v1.0.html ; USLM User Guide —
https://xml.house.gov/schemas/uslm/1.0/USLM-User-Guide.pdf ; Kim et al., *Learning Bill
Similarity…* (EMNLP 2021) — https://arxiv.org/abs/2109.06527 ; Hershowitz & Mador-Haim,
*Comparative Prints Suite…* (JURIX 2023) — https://ebooks.iospress.nl/doi/10.3233/FAIA230993 ;
GovTrack `xml_diff` — https://github.com/JoshData/xml_diff ; Zhu, Klabjan, Bless, *wTED* —
https://arxiv.org/abs/1709.01256 ; Burgess et al., *Legislative Influence Detector* (KDD 2016) —
https://www.kdd.org/kdd2016/papers/files/adf0831-burgessA.pdf .
