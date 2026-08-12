# Pre-execution amendments

**Every amendment here was made while no confirmatory architecture output existed.** That
is the condition making it legitimate to amend a frozen protocol before execution rather
than a degree of freedom. **Its evidence is of two different strengths, and A11 separates
them:** F5 establishes as a *repository fact* that no canonical score artifact exists; that
no H/X extraction was ever *run* is an **attestation**, because git cannot prove a command
was never executed. The provable ordering fact is enforced instead by the execution-start
marker (A11).

## Why this file exists, and the invariant it protects

The fact worth preserving is not "the pre-registration file was never edited". It is:

> The **sampling procedure** and the **decision rule** were fixed before the population was
> drawn, and every later change was made without any confirmatory result in existence, so
> no change can have been selected for the answer it produces.

`PRE-REGISTRATION.md`'s F4 proxies that with "unmodified since before the membership
commit". That proxy is *too strong in one direction and too weak in another*: it forbids
correcting prose that contradicts an already-frozen rule, and it says nothing about the
**code** that draws the sample or computes the score. So the protocol document is left
**byte-frozen at `c399e9d`**, every later change is recorded here, and `x04` gains three
invariants:

| invariant | what it enforces |
|---|---|
| **F7** | the set of files under `holdout/` equals **exactly** the set named by `holdout_membership.json` — no unmanifested artifact may sit inside the frozen population |
| **F8** | every manifested file begins with `%PDF-` |
| **F9** | **every file in this study directory whose last commit is after the membership commit must be declared below**, and no amendment may declare `affects_membership: true` |

F9 is the general form of the defect this pass found: *a manifest, a protocol or a gate
claiming a closed world while the filesystem or the code admits something outside it.*

## Scope

| class | may it change a rule that scores the population? | conditions |
|---|---|---|
| `CLERICAL` | **no** — corrects prose that contradicts an already-frozen rule, or removes a withdrawn population's numbers | none |
| `SUBSTANTIVE` | **yes** | only while no confirmatory output exists; must argue explicitly why the population stays valid |
| `TOOLING` | **no** — harness code that cannot change membership or a score | must state the evidence that it cannot |

**No amendment may change membership.** A change requiring that is not an amendment; it is
a re-selection.

---

## A1 — CLERICAL. The protocol carried the withdrawn design population's numbers

```json
{"id": "A1", "class": "CLERICAL", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": [], "supersedes_text_in": "PRE-REGISTRATION.md"}
```

**Stale text.** §7.1 "what happened on 19 named documents"; §7.2's pre-committed reporting
template "On the 19 frozen documents"; §8.3 "at N ≈ 14 the tightest achievable zero-event
bound is ≈ 19 %"; §8.3 "the honest strength of a 14-document holdout".

**Why it became stale.** Those numbers described the **design** population (19 documents,
14 P-head) that was withdrawn as non-pre-registered. The confirmatory population is
different, and the numbers were never rules — they were illustrations baked into prose.

**Correct current interpretation.** The protocol is **population-agnostic**. Read every
such figure as a symbol whose realized value comes from
`results/holdout_membership.json` and the findings document, never from this prose:

| symbol | meaning | realized value |
|---|---|---|
| **N** | frozen documents | `holdout_membership.json` → `n_documents` |
| **N_head** | P-head documents | members with `population == "P-head"` |
| **H** | heading occurrences | computed at extraction time |
| **r** | achieved exact 95 % zero-event upper bound on the per-document rate, `1 − 0.05^(1/N_head)` | reported in findings |

The §8.1 table (600 headings → 0.00498 against 14 documents → 0.1926) is **retained as the
worked example that demonstrated the estimand defect**, on the design population, and is
correct as history. It is not a claim about the confirmatory population.

**Can this affect membership or scoring?** No. No rule changes.

---

## A2 — CLERICAL. Red-team rows still referenced the withdrawn δ

```json
{"id": "A2", "class": "CLERICAL", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": [], "supersedes_text_in": "PRE-REGISTRATION.md"}
```

**Stale text.** Red-team row 10 ("X must clear δ **and** be one-directional"); row 12
("δ is fixed before results, derived from a measured 652-heading document, and is 4×
tighter than the prior protocol's"); row 13 ("§7.2 rule 3 voids the run outright if the
denominator cannot support a bound under δ").

**Why it became stale.** §7.1 withdrew δ entirely and §7.2 rule 3 no longer mentions a
denominator floor. The rows were written when δ was live and were not updated with it.

**Correct current interpretation.** **There is no δ.** Row 10's risk is now answered by
§7.2 rule 1 being count-based and one-directional. Row 12's risk is **moot** — a margin
that does not exist cannot be chosen to make a tie unfalsifiable; the replacement risk,
that a *descriptive* result is over-read, is answered by §7.2's mandated reporting
sentence. Row 13's mechanism is now §7.2 rule 3's control failures, not a denominator
floor. Row 21 already records the δ withdrawal correctly and stands.

**Can this affect membership or scoring?** No.

---

## A3 — SUBSTANTIVE. The decision unit for M3 is the heading occurrence

```json
{"id": "A3", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/m3_boundaries.py", "probes/m3_selftest.py"],
 "supersedes_text_in": "PRE-REGISTRATION.md"}
```

**The defect.** §6.3 defined M3 at aligned **boundary positions** and said the decision
rule counts WELD/SPLIT outcomes there, while §7.2 rule 1 required X to repair
"≥ 5 printed account or agency **headings**". Those are different units, and one heading
can carry several boundary defects — so the same evidence could satisfy the rule on one
reading and not the other.

**Resolution, frozen.** The decision unit is the **unique heading occurrence**, because the
architecture question is about corrupted account and agency *labels*, which is the unit of
downstream harm. Boundary outcomes remain **diagnostic** and are always reported.

Mechanically, implemented and tested in `probes/m3_boundaries.py`:

> a heading is **CLEAN** for an architecture when it has zero WELD, zero SPLIT and zero
> TEXT_ERROR against the oracle.

| heading-level outcome | condition |
|---|---|
| `X_CORRECTS` | H not clean, X clean |
| `X_REGRESSES` | H clean, X not clean |
| `BOTH_CLEAN` | both clean |
| `BOTH_DIRTY` | neither clean, **whatever the defect counts** |
| `UNSCORABLE` | **superseded by A9**: only when the ORACLE has no text. `UNALIGNABLE` is withdrawn |

**The case the review raised is answered explicitly: if H has two WELDs and X repairs one,
that is `BOTH_DIRTY` and is NOT a correction.** A half-repaired account label is still a
wrong account label. `probes/m3_selftest.py` asserts exactly that case.

**Why the population stays valid.** The choice of unit is a statement about what counts as
product harm. It is independent of which documents were drawn, and it cannot be tuned
toward an answer, because **no H or X output exists on any confirmatory document**. The
pilot moreover found zero heading-level differences on development material, so there is no
observed direction to tune toward.

---

## A4 — SUBSTANTIVE. M3's alignment is operationalized; the edit budget is removed

```json
{"id": "A4", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/m3_boundaries.py", "probes/m3_selftest.py"],
 "supersedes_text_in": "PRE-REGISTRATION.md"}
```

**The defect.** §6.3 said "cannot be aligned within the frozen edit budget" but froze no
algorithm, no costs, no budget, no tie-breaking, no Unicode rule and no repeated-character
rule. Scoring behaviour was therefore left to whoever wrote the scorer.

**Resolution, frozen and executable.**

- Alignment is over the **non-space** character sequences, so a spacing difference can
  never cause a misalignment.
- Normalisation is **NFKC + end-strip only**; case preserved; interior spaces preserved for
  the boundary vector, then excluded from the alignment sequence.
- **Needleman–Wunsch** global alignment, unit costs (match 0, substitution 1, indel 1).
- **Deterministic tie-break**: DIAGONAL, then UP (oracle-only), then LEFT (extractor-only),
  so `AB AB` → `ABAB` resolves identically on every run.
- A run of spaces is **one** boundary.
- **The edit budget is removed.** It was an arbitrary threshold on the exact quantity being
  measured. `UNALIGNABLE` now means what it says: the two sequences share **no** common
  subsequence. A long string with many substitutions still aligns.
- A boundary is comparable only when **both** endpoints aligned to oracle characters.

**Why the population stays valid.** Purely mechanical, chosen from properties of the
algorithm rather than from data, verified on synthetic and development material, and fixed
before any confirmatory output exists.

---

## A5 — SUBSTANTIVE. Rule 1's omnibus veto is replaced by per-metric directionality

```json
{"id": "A5", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": [], "supersedes_text_in": "PRE-REGISTRATION.md"}
```

**The defect.** Rule 1 required that "no other metric moves against X by more than one
heading occurrence per affected document". M1 counts heading occurrences, M2 matched
headings, M4 **parent relations** and M6 **amount attributions** — so a veto denominated in
heading occurrences cannot literally apply to M6 at all.

**Resolution, frozen.** The omnibus veto is deleted. Each metric is vetoed in **its own
native unit**, and every veto is a **hard directionality check**, so no new threshold is
invented. This is deliberately *stricter* than what it replaces.

**Rule 1 — choose corrected extended glyph only if ALL four hold:**

| # | condition | unit |
|---|---|---|
| 1 | `X_CORRECTS ≥ 5` on the human-adjudicated D-frame census | heading occurrence |
| 2 | `X_REGRESSES == 0` | heading occurrence |
| 3 | no amount whose attributed account is correct under H and wrong under X | amount attribution (M6) |
| 4 | no heading whose immediate parent is correct under H and wrong under X | parent relation (M4) |

Condition 2 tightens the previous "regresses ≤ 1" to **zero**. With an expected denominator
near zero, "≤ 1" is not a tolerance — it is 20 % of the win threshold. M2 needs no separate
veto: a text difference already makes a heading not clean, so it is inside conditions 1–2.

**If condition 1 holds but any of 2–4 fails**, the outcome is **insufficient evidence /
review**, never an X win.

**Why the population stays valid.** Every change is a *tightening* in the incumbent's
favour, denominated in units fixed by the metrics themselves, made with no confirmatory
output in existence.

---

## A6 — TOOLING. Harness repairs after the population freeze

```json
{"id": "A6", "class": "TOOLING", "commits": [], "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["holdout/CRPT-118HRPT146/CRPT-118HRPT146.pdf"],
 "accounting_delegated_to": "A18",
 "note": "probes/x04_freeze_check.py moved to A11, which changes what the gate MEANS and is recorded SUBSTANTIVE."}
```

**What changed.**

1. `x03_select_holdout.py` — every download-rejection path now deletes the file, and a
   download must begin with `%PDF-` to be accepted (`accept_download`).
2. `x04_freeze_check.py` — F7, F8 and F9 added, with self-tests.
3. `m3_boundaries.py` / `m3_selftest.py` are declared under **A3/A4 only**. They
   carry scoring semantics, so listing them here as TOOLING as well would let a
   substantive change hide behind a tooling declaration — F9 now rejects exactly that,
   and it rejected this file until the duplicate was removed.

**Why it cannot change membership, with evidence rather than assertion.** The only
behavioural change in the selector is that a non-PDF download is now rejected by a header
check instead of by `page_count` raising. `CRPT-118HRPT146` was **already rejected** by the
old path — it was never a member; only its file was left behind. The header check could in
principle reject a PDF whose header is not at offset 0, so that was measured rather than
assumed: **all 17 manifested files begin with `%PDF-`**, asserted continuously by F8. So
the new rule would have accepted exactly the same 17 documents.

**Why the selector was not simply left alone.** Leaving it would preserve a bug that
writes unmanifested files into the frozen population directory on any future run.

---

## A7 — TOOLING. The contamination probe was reading its own output

```json
{"id": "A7", "class": "TOOLING", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": [], "superseded_by": "A8",
 "note": "A8 now owns probes/x01_contamination.py and results/contamination.json as a SUBSTANTIVE change; declaring them here as well would let a substantive change hide behind a tooling declaration, which F9 rejects."}
```

**Found while sweeping for the same class of defect as A6: a closed world that is not
closed.** `x01` scans the research tree for `.json` to find bill ids "named in research".
Its own output, `results/contamination.json`, is a `.json` in that tree, and it **records**
the 2,963 xml-only bills it deliberately does **not** exclude. So a second run re-ingested
every one of them as `named_in_research`.

**Measured:** re-running against the frozen artifact took the exclusion set from **93 bills
to 3,080**, and flagged **all 17 confirmatory holdout members** as contaminated. F3 reads
the committed file, so the frozen gate was never wrong — but any re-derivation would have
condemned the population the probe exists to protect, and the failure would have looked
like a contamination finding rather than a bug.

**Repairs.**

1. Generated artifacts are no longer scanned (`"results" in f.parts`). An output that is
   also an input is a ratchet, not a derivation.
2. **This study's own frozen population is subtracted**, in its own recorded class
   `own_study_population_not_excluded`. Once a holdout is committed it is exposed by
   construction, so without this the probe condemns it forever. The class name states the
   scope: a **future** study must treat these 17 as contaminated.
3. An **idempotence gate**: after writing, the derivation is re-run with the new file in
   place and must reproduce the same answer, else exit 3.

**A first version of that gate was wrong and is worth recording.** It compared against the
*committed* artifact and failed on any change — but the exclusion set legitimately **grows**
as material is committed, so it fired on honest growth (+17 bills, +5 reports, all of them
the withdrawn design PDFs that are now in git history). A gate that forbids legitimate
change is not a gate, it is a permanent red light. It now tests the property that actually
matters: re-deriving with its own output present must be a no-op.

**Verified:** two consecutive runs produce byte-identical output
(`5866c7da…`), and the honest exclusion set is now **110 bills / 38 report packages**.

**Can this affect membership or scoring?** No. Membership is unchanged, and the 17 members
are exempted rather than re-selected.

---

## A8 — SUBSTANTIVE. Freshness is decided against a pre-selection snapshot, not by subtraction

```json
{"id": "A8", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x01_contamination.py", "results/contamination.json"],
 "supersedes_text_in": "PRE-EXECUTION-AMENDMENTS.md A7"}
```

**The defect.** A7 subtracted the study's own membership from every exposure class. That
cannot distinguish

- **(A)** exposure this study *caused*, by committing its own frozen holdout — harmless;
- **(B)** exposure that existed *before* selection, on a document picked anyway —
  disqualifying,

and it silently forgives **(B)**. "Current exposure minus current membership" is a proxy
for freshness, not freshness.

**Repair.** Freshness is now decided against the **pre-selection snapshot**: the
contamination and design-exposure artifacts as they stood at the commit immediately before
the population commit, read from git at `<population_commit>~1`. That state is immutable,
cannot be edited by any later run, and **by construction cannot contain exposure this
study later caused**. No exemption is therefore needed, and the own-study subtraction is
**withdrawn**: `contamination.json` now records the 17 members as exposed in their natural
classes, which is true and which a future study needs.

**The audit result, which is the reason no reselection follows.** At `c399e9d` — the
pre-selection state — the inventory carried **93 excluded bills, 33 report packages** and
**no own-study class at all**, and **all 17 confirmatory members were absent from every
disqualifying exposure class**. Reproduce with
`git show c399e9d:…/results/contamination.json`.

**Controls.** Two self-tests now encode the distinction: case **B** (contaminated before
selection, later a member) must fail; case **A** (clean before selection, exposed only by
its own frozen commit) must pass. A snapshot that already carries an own-study exemption is
refused as not-pre-selection.

**Class note.** Recorded SUBSTANTIVE rather than TOOLING because it changes what F3 *means*,
even though it changes no score. It does not touch membership, and the audit shows the
answer is unchanged.

---

## A9 — SUBSTANTIVE. `UNALIGNABLE` is withdrawn; severe corruption stays in the denominator

```json
{"id": "A9", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/m3_boundaries.py", "probes/m3_selftest.py"],
 "supersedes_text_in": "PRE-EXECUTION-AMENDMENTS.md A4"}
```

**The defect, confirmed by the reviewer's own case.** A4 documented `UNALIGNABLE` as "the
two sequences share no common subsequence", but the code declared it when the *chosen
minimum-cost alignment* contained no exact match. **Measured:** `AB` against `BA` has
LCS = 1 — it plainly shares `A` and `B` — yet minimum cost is two substitutions, the
DIAGONAL tie-break selects them, and the implementation returned `UNALIGNABLE`. Prose and
code disagreed.

**The deeper problem, which decided the repair.** `UNALIGNABLE` made the heading
`UNSCORABLE`, which removed it from the comparison — so the mechanism **excluded precisely
the worst failures**. If X emitted garbage where H read the label correctly, X's
catastrophic failure vanished instead of counting as `X_REGRESSES`. That is an exclusion
that removes the distinguishing cases, the recurring defect of this study.

**Repair: the category is withdrawn rather than repaired.** Severe corruption is a severe
`TEXT_ERROR`; the heading is not clean and stays in the denominator. This needed neither of
the two offered options, because the semantic mismatch disappears with the category.

- `NO_REFERENCE` replaces it, and fires **only when the oracle has no text** for a heading
  (unreadable region). A missing *reference* is an oracle limit; a garbage *extraction* is
  an architecture result.
- `no_common_subsequence` survives as a **diagnostic flag** with no effect on scoring.
- An empty extraction now scores `TEXT_ERROR` on every printed character, not an exclusion.

**Direction of effect:** strictly *safer for the incumbent*. Catastrophic X output now
counts against X, where before it was discarded.

**Tests.** All six adversarial pairs (`AB/BA`, `ABA/BAA`, `ABC/BAC`, `AAB/ABA`,
`ABAB/BABA`, `AAAAAB/BAAAAA`) remain scorable and are not flagged as sharing nothing; a
garbage extraction is `X_REGRESSES` in both directions; only a missing oracle reference is
`UNSCORABLE`.

---

## A10 — SUBSTANTIVE. A count threshold may not be applied to a D-frame subsample

```json
{"id": "A10", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": [],
 "supersedes_text_in": "PRE-REGISTRATION.md 5.5.1 and PRE-EXECUTION-AMENDMENTS.md A5"}
```

**The defect.** §5.5.1 allows a seeded 60-item subsample when the D-frame census exceeds the
human adjudication budget, while A5's Rule 1 uses **raw counts** (`X_CORRECTS ≥ 5`,
`X_REGRESSES == 0`). A raw count is valid on a **census** and not on a **sample**: five
corrections among 60 sampled items says nothing definite about 150, and zero regressions
among 60 does not establish zero among 150.

**Repair, frozen.**

> If the D-frame contains more items than the pre-set human budget can adjudicate, **Rule 1
> cannot choose corrected extended glyph.** The outcome is `INSUFFICIENT_COMPARATIVE_EVIDENCE`.

A seeded 60-item sample may still be adjudicated **for descriptive diagnosis**, and is
reported as such, but the `≥5 / ==0` thresholds are **not** applied to it. No sampling
estimator is built for a contingency the pilot suggests is rare.

**Three outcomes, kept distinct, and never collapsed.**

| outcome | meaning |
|---|---|
| `HYBRID_BY_PRIOR` | the pre-stated architectural prior stands; comparative evidence did not overturn it |
| `EXTENDED_BY_RULE_1` | X met every condition of Rule 1 on a **full census** |
| `INSUFFICIENT_COMPARATIVE_EVIDENCE` | Rule 1 could not be evaluated — census too large for the human budget, or a control failed |

**"X failed to prove a win because we did not adjudicate enough items" must never be
written as "H empirically beat X."** Hybrid remains the default by prior, not by victory.

---

## A11 — SUBSTANTIVE. A one-way execution boundary, and F9 hardening

```json
{"id": "A11", "class": "SUBSTANTIVE", "commits": [], "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x04_freeze_check.py"],
 "note": "A12 also changes this file; both are SUBSTANTIVE, so neither hides behind a TOOLING declaration."}
```

**The defect.** This file claimed F5 "mechanically establishes" that no confirmatory output
existed. F5 checks `not scores.json.exists()`. That is a claim about **one artifact**; it
cannot establish that nobody ran H or X locally, wrote output elsewhere, or deleted it.
**Git cannot prove a computation was never performed.**

**Repair — narrow the claim, then make the useful fact provable.**

| claim | evidence |
|---|---|
| *no canonical score artifact exists* | **repository fact**, F5 |
| *no confirmatory H/X extraction has been run* | **attestation** recorded in the marker; weaker, and labelled so |

The provable and useful fact becomes **ordering**: *this scoring rule existed before the
commit that authorized execution.* That is enforced by an **execution-start marker**,
`results/EXECUTION-START.json`, emitted only by `x04 --authorize-execution`, which
**refuses** while any freeze or readiness gate is open. After the marker:

- no further `SUBSTANTIVE` pre-execution amendment is permitted — F9 rejects one whose
  commit is not an ancestor of the marker;
- a scoring-rule change becomes a **deviation**, not an amendment;
- confirmatory output may exist, and F5 stops requiring its absence.

**F9 hardening**, because a declaration must not be acceptable merely because a path is
listed. F9 now also rejects: duplicate amendment ids; a `files_touched` path that neither
exists nor was deleted; a file declared under **both** a SUBSTANTIVE and a TOOLING
amendment; and a TOOLING amendment that claims to change a scoring rule.

**F9 caught this file.** `m3_boundaries.py` and `m3_selftest.py` were declared under A3/A4
(SUBSTANTIVE) *and* A6 (TOOLING) — the exact hiding pattern the check exists to prevent.
The duplicate declaration was removed.

---

## A12 — SUBSTANTIVE. Two more proxy/property mismatches, found by targeted sweep

```json
{"id": "A12", "class": "SUBSTANTIVE", "commits": [], "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": []}
```

The recurring pattern in this study is *the gate checks a proxy for the property we care
about*. A deliberate sweep for further instances found two.

**F6 repeated F4's exact defect, in the check that proves BLINDING.** It compared
`first_commit(oracle_key)` against `first_commit(oracle_adjudicated)`. The membership file
has already demonstrated that an artifact can be withdrawn and re-created at the same path,
after which `first_commit` returns a commit for a version that no longer exists — so F6
would have "proved" the ordering of a key nobody would score against. Both sides now use
the last-modifying commit, matching F4.

**G2 believed a self-reported label.** The evidence file declares
`"population": "DEVELOPMENT"`, and G2 accepted that string as proof the X2 assertions were
not run on the holdout. A file can say DEVELOPMENT while having been produced on holdout
members — the same class as trusting a `.pdf` filename over PDF bytes. G2 now requires the
evidence to *list its documents* and checks them against membership directly; the label
alone is no longer sufficient, and a non-empty document list is required so the check
cannot pass vacuously.

**Controls:** `--self-test` gains "G2 rejects evidence LABELLED development that names a
holdout member" alongside the existing self-labelled-HOLDOUT case, giving 22/22.

**Can this affect membership or scoring?** No. Both are gate strictness; neither computes
a score. Recorded SUBSTANTIVE rather than TOOLING because each changes what a gate
*means*, and A11 established that as the dividing line.

---

## A13 — SUBSTANTIVE. The gate validated the working tree against itself

```json
{"id": "A13", "class": "SUBSTANTIVE", "commits": [], "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x04_freeze_check.py"],
 "note": "A11 and A12 also touch this file; all three are SUBSTANTIVE, so nothing hides behind a TOOLING declaration."}
```

**Found by a targeted sweep for the study's recurring pattern — the gate checks a proxy for
the property we care about. This is the most serious instance yet, because it defeats every
other freeze invariant at once.**

`committed()` was `git ls-files --error-unmatch`, which proves a path is **tracked**. The
property we need is that the artifact is **identical to what was committed**. Since every
invariant reads the working tree, they collectively validated the working tree *against
itself*.

**Demonstrated, not argued.** Deleting 7 members from `holdout_membership.json` and
removing their 7 PDFs — **no commit** — leaves an internally consistent tree, so:

| invariant | result on the tampered tree |
|---|---|
| F1 membership committed | **PASS** — "10 members, committed=True" |
| F2 hashes match | **PASS** — 10 files match |
| F3 freshness | **PASS** — 10 members clean |
| F7 set equality | **PASS** — 10 files == 10 manifested |
| F8 PDF headers | **PASS** |
| **FREEZE INTEGRITY** | **COMPLETE** — over a population that is not the committed one |

**Repairs.**

1. `committed()` now means **tracked AND unmodified against HEAD**.
2. **F10** asserts that the frozen artifacts — membership, contamination, design exposure,
   the pre-registration, this file, and the whole `holdout/` directory — carry **no
   uncommitted change of any kind**. Scoped to frozen artifacts: probe code is expected to
   change and is policed by F9 instead.

**A second, latent defect fixed in the same sweep.** `amendment_commits` selected an
amendment's latest commit with `max(commits, key=lambda c: git("rev-list","--count",c))`.
`rev-list --count` returns a **string**, so the comparison was lexicographic and `"9"`
beats `"1003"`. It is dormant today because no execution-start marker exists, but it would
have silently misjudged the one-way boundary the moment execution was authorized — the
check most likely to be trusted without re-derivation. Now compared as integers.

**Controls:** `--self-test` gains "F10 detects an uncommitted edit to the frozen manifest"
and "F1 no longer calls a MODIFIED manifest committed", giving **24/24**.

**Can this affect membership or scoring?** No. Membership is unchanged and re-verified at
17; this is gate strictness only. Recorded SUBSTANTIVE because it changes what *every*
freeze invariant means, on the dividing line A11 established.

---

## A14 — SUBSTANTIVE. Two post-freeze methodological commits were never declared

```json
{"id": "A14", "class": "SUBSTANTIVE", "commits": [],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x04_freeze_check.py"],
 "note": "Retroactive declaration. Found by binding F9 to commits instead of paths; the path-union rule had silently excused these."}
```

**Found by the F9 repair, in this study's own history.** The old F9 unioned every
`files_touched` and subtracted it from the changed-path set, so a path declared **once**
excused every later change to it. `probes/x04_freeze_check.py` has **nine** modifying
commits and was "declared", so all nine passed.

Binding declarations to commits instead exposed **two post-freeze commits that no amendment
ever described**:

| commit | change | why it is methodological |
|---|---|---|
| `70ec76c` | F4 compared against the withdrawn population — `first_commit(MEMBERSHIP)` returned the design-era commit after the file was re-created | changed what F4 *means* |
| `985def9` | F3 read the raw contamination classes rather than the exemption classes | changed what F3 *means* |

Both are gate-semantics changes made with no confirmatory output in existence, neither
touches membership, and neither computes a score — but neither was recorded, and under the
old rule neither ever would have been. They are declared here rather than excused.

**Why the population stays valid.** Both changes made gates *stricter* and neither can
select or deselect a document; membership is unchanged and re-verified at 17 by F11.

---

## A15 — SUBSTANTIVE. The freeze and the boundary were snapshots, not historical facts

```json
{"id": "A15", "class": "SUBSTANTIVE", "commits": [],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x04_freeze_check.py"],
 "note": "Declared after the fact by a LEDGER-ONLY commit, which is itself exempt from F9 -- so the loop closes rather than requiring an infinite regress of declarations."}
```

Five defects, each an instance of *the gate checks a proxy for the property*.

**1. A committed marker was never required for execution.** The final block of `main()`
consulted the marker **not at all**: with F/G green and no marker anywhere, x04 printed
`EXECUTION PERMITTED` and returned 0. Measured by stubbing both gate functions to pass —
authorization was optional. There is now a state machine: `ABSENT` → *READY TO AUTHORIZE*,
`UNCOMMITTED` → *AUTHORIZATION PENDING COMMIT*, `MUTATED` → *BOUNDARY VIOLATED*, all
`EXECUTION FORBIDDEN` with exit 1. Only a **valid committed write-once** marker permits
execution. Writing the file is not authorizing.

**2. The boundary was movable.** `marker_commit()` used `last_commit`, so editing the
marker at N would move the boundary to N and make a substantive change between M and N
appear to predate it. `first_commit` alone is not sufficient either — this study already
saw a path deleted and re-created. Immutability is now asserted directly: **exactly one
modifying commit, and the current blob equals the blob introduced by it.**

**3. The population freeze was movable.** F3, F4 and F9 derived it from
`last_commit(MEMBERSHIP)`, so a later committed edit to the manifest would have become the
new freeze, moved the pre-selection snapshot to that commit's parent, and shrunk the
post-freeze window. `POPULATION_FREEZE_COMMIT` is now **pinned to `4e2b520`**, and new
**F11** proves the current population is byte-identical to the frozen one (blob, id set,
paths, recorded SHA-256s). A later membership change now **fails** instead of re-anchoring.

**4. F9 bound declarations to paths, not changes** — see A14.

**5. The ledger was not sealed.** Nothing stopped `PRE-EXECUTION-AMENDMENTS.md` changing
after authorization. F9 now rejects any commit touching it after a valid boundary.

**Also:** the marker becomes a **manifest** of the exact frozen surface
(`population_freeze_commit`, `membership_blob`, `frozen_blobs` over every result-bearing
file), and normal x04 re-verifies those blobs afterwards, reporting **METHODOLOGY DRIFT**
as a deviation rather than silently moving to the new version.

---

## A16 — SUBSTANTIVE. Execution readiness did not cover the machinery that produces the answer

```json
{"id": "A16", "class": "SUBSTANTIVE", "commits": [],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x04_freeze_check.py"]}
```

**The conceptual gap.** G1–G4 covered the adapter, its evidence, the adjudicator prompt and
the exposure list. None of the **runners, frame builders, oracle builder, scorers or
decision evaluator** had to exist. Authorizing on that basis would have permitted inspecting
confirmatory H/X output and *then* finishing the scorer — innocently or not, the scoring
rule would postdate the data.

**G5** now requires the whole result-bearing surface to exist and be committed:

| file | what answer it can move |
|---|---|
| `pdfium_extended_corrected.py` | X's character facts → every X metric |
| `reconstruct_extended_corrected.py` | X's word segmentation → every X metric |
| `run_hybrid.py` / `run_extended.py` | each architecture's extraction → every metric |
| `build_frames.py` | which records enter the C-frame and D-frame |
| `build_oracle.py` | what the adjudicator sees; which label binds to which region |
| `m3_boundaries.py` | WELD/SPLIT/TEXT_ERROR and the heading-level decision unit |
| `score_metrics.py` | M0–M9 outcomes |
| `decide_architecture.py` | the architecture decision itself |
| `x2_verify.py` | whether X's contract assertions actually hold |
| `adjudicator_prompt.md` | what the adjudicator is asked and shown |

**Deliberately NOT frozen:** report generation, table formatting, summary prose and
diagnostics that cannot affect inclusion, oracle data, metric classification or the
decision. Freezing them would be ceremony.

**G2 strengthened in the same pass.** A hand-written file naming `fake-doc-123`, labelled
DEVELOPMENT, made G2 green — proving only that a file asserts its own success. Evidence must
now bind provenance: every fixture path must **exist in the repo**, not be a holdout
document, and hash to its recorded SHA-256; and the adapter, reconstructor and verifier blob
SHAs must match the committed files, so evidence cannot outlive the code that produced it.

**Consequence, stated plainly:** most of this surface does not exist yet, so the study is
**not** ready to authorize. That is the honest state rather than a gate that reads green on
four files.

---

## A17 — BLOCKING AMBIGUITY. The frozen protocol is not executable as written

```json
{"id": "A17", "class": "SUBSTANTIVE", "commits": [],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/x06_m6_feasibility.py", "results/x06_m6_feasibility.json"],
 "status": "OPEN -- resolution required before the harness can be completed"}
```

Deriving the executable pipeline from `PRE-REGISTRATION.md` + amendments, **before writing
the harness**, exposed four places where the frozen protocol does not determine what the
code should do. Per the standing instruction to stop at an ambiguity rather than code
through it, the harness is **not** completed past these. Each is recorded with what it
could bias.

### A17.1 — M6 has no oracle for most of its population *(blocking, measured)*

§6 defines M6 as "for each dollar amount in a C-region, emitted nearest heading-ish
ancestor **vs adjudicated**", while §5.3 fixes the adjudicated unit as a region of **6–10
printed lines** and §5.4 shows the adjudicator **only that region**. In GPO appropriations
an account heading governs a long run of prose, so the heading that owns an amount is
usually not in the region.

**MEASURED** ([`results/x06_m6_feasibility.json`](results/x06_m6_feasibility.json), three
development documents × 30 pages, 226 amounts):

| region size (printed lines) | 6 | 8 | **10** | 15 | 25 | 50 |
|---|---|---|---|---|---|---|
| share of amounts whose governing heading is inside | 0.434 | 0.491 | **0.571** | 0.677 | 0.774 | 0.823 |

Median distance to the governing heading is 5, 12 and 9 lines by document; the maximum is
**288**. At the protocol's own region size, **roughly two amounts in five have no oracle at
all** — and they are systematically the amounts deepest inside long appropriations blocks,
which is exactly where a misattribution does the most damage. A metric silently missing
40 % of its population, non-randomly, is not the metric §6 licenses.

**Could it favour H or X?** Not directly — the viewport is common to both arms. The risk is
to **RQ2**: absolute attribution correctness would be computed on the subset of amounts
that sit close to their heading, which is the easy subset, and reported as if it covered
the whole. That inflates the absolute claim.

**Resolution options, none adopted here.** (a) Give the adjudicator a *governing-heading
banner* derived from an architecture-neutral source, and adjudicate only whether the amount
belongs to it; (b) make M6's unit the **account block** rather than the region, with a
larger rendered span; (c) restrict M6's licensed claim to *in-region* attributions and say
so in every table. Each changes what the adjudicator sees, so each needs review before it is
frozen — which is why none is chosen unilaterally.

### A17.2 — The C-frame predicate cannot be implemented as described

§5.8 requires "an **ink-geometry predicate that reads no character identity and no word
spacing**: a page carrying ≥ 1 line whose median glyph height sits in the document's
**sub-body size cluster**". But the repository's only implementation of that clustering,
`pdf_anchors.derive_size_bands`, decides body size from lines carrying **lowercase letters**
and heading size from lines that are **uppercase headings** — both are character identity.
So the predicate as frozen has no implementation, and reusing production's would violate
its own stated neutrality.

"Sub-body size cluster" is also not operationally defined without that helper: no clustering
method, no threshold, no tie rule.

**Could it favour H or X?** No — it is common to both arms. It determines the **C-frame
population**, so it affects RQ2's denominator and nothing about the comparison.

### A17.3 — "Region" is defined in architecture-derived units

§5.3 fixes the region as "6–10 **printed lines**". Printed lines are produced by H and by X,
and §5.8's D-frame exists precisely because the two can **disagree about line segmentation**.
Defining the neutral adjudication unit in terms of an architecture-derived quantity is the
identity defect this study has repeatedly guarded against.

A neutral substitute exists — cluster **ink baselines**, which come from PDFium glyph boxes
common to both arms and are not the thing under test — but choosing it is a protocol
decision, not an implementation detail, and it changes which lines land in which region.

### A17.4 — No rule for comparing H and X text when line counts differ

The D-frame is "every region where the two architectures' reconstructed printed-line text
differs". The design pilot `x00` compared by `(page, ordinal)`, which is only valid when
both produce the same number of lines. §5.8 gives no rule for the case it exists to detect.
Once A17.3 fixes a neutral region grid this becomes tractable — assign each architecture's
lines to regions geometrically and compare per region — but it is unspecified today.

### Why the harness stops here

Every remaining component (`build_frames`, `build_oracle`, `score_metrics`,
`decide_architecture`) consumes the region identity and the M6 unit. Implementing them now
would mean **inventing** A17.1–A17.4 in code and calling the result "the frozen protocol",
which is the specific failure this whole review sequence exists to prevent. The components
that do **not** depend on the open questions are still tractable and are the natural next
step once A17 is resolved.

**Population impact: none.** No membership change, no scoring performed, no holdout document
opened.

---

## A19 — A17-N RESOLVED. The comparison unit is a neutral ink-line skeleton

```json
{"id": "A19", "class": "SUBSTANTIVE", "commits": [],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/neutral_geometry.py", "probes/x07_neutral_geometry.py",
                   "results/x07_neutral_geometry.json"],
 "supersedes_text_in": "PRE-REGISTRATION.md 5.3, 5.8",
 "resolves": ["A17.2", "A17.3", "A17.4"]}
```

**This is a post-selection protocol change.** No confirmatory output exists, so it is a
legitimate pre-execution amendment — but it changes what the adjudication unit *is*, and it
is recorded as substantive rather than clerical.

### Previous ambiguous rule

§5.3: the unit is "6–10 **printed lines**". §5.8: the D-frame is regions where "the two
architectures' **reconstructed printed-line** text differs", and the C-frame samples pages
carrying a line in "the document's **sub-body size cluster**". Printed lines are produced by
H and by X; the sub-body cluster had no implementation that does not read character identity.

### New rule

**Which source facts are below both seams, stated rather than assumed.** H and X differ in
exactly one place: who decides word spaces, and whether the engine's character ordering is
consumed. Both adapters read the *same* PDFium calls for geometry —
`FPDFText_GetCharBox`, `FPDFText_GetCharOrigin`, `FPDFText_GetFontSize`. So **ink glyph boxes
and baselines are common to both arms** and are legitimate neutral facts. Engine-generated
spaces are excluded (they carry no ink, and X-2 excludes them anyway), which is what makes
the skeleton *identical* under both architectures.

*Caveat, stated not waived:* these facts are still PDFium's. "Common to both arms" is not
"engine-independent" — a mis-boxed glyph would be inherited by both arms and the skeleton
together. §5.8's 10 % PyMuPDF cross-check remains the control, **re-pointed at the skeleton**
(per-page neutral line counts) rather than at the withdrawn page predicate.

1. **Neutral line clustering.** Tolerance `= 0.5 × median ink height on the page` — derived
   from page geometry, not a constant. Sort ink glyphs by descending baseline
   (top-to-bottom); start a new line when the baseline differs from the **current cluster's
   first-glyph anchor** by more than the tolerance. An anchor rather than a running mean, so
   gentle drift cannot walk one cluster down a page.
2. **Neutral line identity** = `(document_sha256, page_number, ordinal)`, the ordinal being
   the index in that top-to-bottom order. A pure function of geometry: **MEASURED** stable
   under glyph-order shuffling, and it never reads text, so repeated or duplicate headings
   cannot collide.
3. **Neutral regions** = **non-overlapping windows of 8 consecutive neutral lines**, aligned
   to the page start, short trailing window kept. No sampling decision enters region
   identity. Regions do not cross pages. The same regions serve the C-frame, the D-frame,
   oracle rendering and both projections.
4. **Projection is by GLYPH MEMBERSHIP**, not baseline proximity: a reconstructed line
   belongs to the neutral line owning the plurality of its glyphs, ties to the lowest
   ordinal. **This replaced a rule that failed its own test** — a line merging two neutral
   lines can sit 6 pt from both when the tolerance is 5 pt, and baseline-proximity projection
   returned `None`, silently deleting the comparison unit for exactly the merge case the
   D-frame exists to detect. Membership needs no tolerance. **No text similarity is ever
   consulted**, so a spacing or character difference cannot move a line to another slot.
5. **H ≠ X is evaluated per neutral line**, then lifted to the region. Per neutral line the
   outcome is one of: `SAME`, `TEXT_DIFFERS`, `H_ABSENT`, `X_ABSENT`. A region enters the
   D-frame if any of its lines is not `SAME`, or if the two architectures' emitted anchor
   sets for the region differ. Symmetric under swapping H and X by construction: every
   outcome has a mirror.
6. **A17.4 disappears** because comparison is per neutral line, so differing line *counts*
   no longer break alignment: a merge shows as `X_ABSENT` on one slot, a split as two slots
   each carrying text.

### The C-frame enrichment predicate is WITHDRAWN, on evidence

**MEASURED** ([`results/x07_neutral_geometry.json`](results/x07_neutral_geometry.json), four
development documents × 20 pages): **both** candidate geometry-only predicates select
**100 % of pages** on the three appropriations bills.

| predicate | pages selected | share |
|---|---|---|
| sub-body line height (quantised mode) | 20 / 20 on each bill | **1.0** |
| narrow-and-centred line | 20 / 20 on each bill | **1.0** |

A predicate that selects everything enriches nothing. GPO appropriations pages are dense
enough that essentially every page carries some short centred line. Rather than tune a
fragile classifier toward a target it cannot hit, the enrichment is **removed**:

> **C-frame regions are drawn by a seeded uniform sample over the neutral regions of every
> page of every P-head document, at most 8 regions per document.**

**Why this costs little.** Page-level enrichment existed to avoid sampling structureless
pages — the disease that voided the prior holdout. That is now handled at the **document**
level by the selection frame (GPO title convention plus a 25-page floor, §4.4), so page-level
enrichment was redundant. The §5.8 clause reserving 40 % of C-regions for amount-bearing
pages is **retained**, because it is a *content* stratification, not a heading classifier.

### What changes, and what it cannot do

| | |
|---|---|
| metric/denominator | M0's denominator becomes **neutral lines**, not "aligned printed lines". M1/M2/M3/M4 denominators become headings matched within neutral regions |
| claim | unchanged for RQ1; RQ2's C-frame is now an unenriched page sample, so its precision per unit of adjudication falls and that is accepted explicitly |
| can it favour H or X? | **No.** Every rule reads only facts both arms share, and the D-frame predicate is symmetric. The skeleton cannot be tuned toward either because it never sees either's output |
| known limit, recorded | a **two-column page merges its columns** into one neutral line (asserted as a test, not discovered later). GPO bills are single-column; committee-report tables are not, and P-robust is where those live |
| known limit | baselines closer than half the median ink height are one neutral line |

**Development evidence:** 23/23 synthetic adversarial fixtures pass, covering adjacent
lines, sub-tolerance baselines, superscripts, subscripts, display headings, letter-spaced
caps, margin numbers, split text objects, two-column merge, table rows, identity stability,
all four projection cases, and region partitioning. Four development documents produce
26–47 neutral lines per page, consistent with GPO's ~25-line measure plus running heads.

**Population impact: none.** No membership change; no holdout document was opened.

---

## A21 — A19's projection semantics, corrected. The neutral identity contract

```json
{"id": "A21", "class": "SUBSTANTIVE", "commits": [],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/neutral_identity.py", "probes/x08_neutral_identity.py",
                   "probes/x09_skeleton_cross_engine.py",
                   "results/x08_neutral_identity.json", "results/x09_skeleton_cross_engine.json"],
 "supersedes_text_in": "PRE-EXECUTION-AMENDMENTS.md A19"}
```

**A19's concept is retained; three of its statements were false of its own code and are
withdrawn.**

| A19 said | actually |
|---|---|
| "projection is by GLYPH MEMBERSHIP" | `project_by_glyphs` received only **baselines** and took the nearest neutral line |
| "membership needs no tolerance" | it had **no maximum distance at all**: a glyph at `y = -5000` was still assigned to a neutral line |
| "a split [appears] as two slots each carrying text" | both fragments of a split contain glyphs of the **same** neutral line, so they projected to one slot |

### The neutral glyph identity

> **`gid = (document_sha256, page_number, source_char_index)`**, where `source_char_index`
> is the index `i` in `FPDFText_CountChars` order.

**MEASURED against the adapters:** neither contract stores it today — both `continue` past
rejected characters, so a list position is *not* the index. Recording `i` is pure
provenance: both loops already have it, and it changes no extraction decision on either arm.
No other exact common identity exists — geometry is a *measurement*, not an identity, and
two marks can share a box.

**Generated spaces have `gid = None`** and can never be a member of a neutral line. They are
engine inventions with no ink, which is exactly why the skeleton is identical under both
arms.

### Eligibility is geometric, and now literally so

A19 claimed the skeleton reads "no codepoint" while `x07` filtered `cp in (10, 13, 32)`. The
filter is **removed**. A source glyph is neutral-eligible iff it has a **valid, finite,
positive-area ink box** and is upright.

**MEASURED** ([`results/x08_neutral_identity.json`](results/x08_neutral_identity.json), two
development documents, 31,729 characters): the number excluded **only** by a codepoint rule
is **0**. Every non-eligible character is excluded by geometry alone. The invariant is now
true rather than aspirational.

### Projection is MODEL G — source-glyph partition

For each neutral line and each architecture, the contribution is the architecture's own text
restricted to the glyphs **that line owns**, by set membership on `gid`. No tolerance, no
nearest-anything, no text similarity.

**Spacing is preserved, which is the point.** An architecture's inserted character (a `gid`
of `None` — its own word-space decision) is kept when it sits *between* two retained glyphs
of that line. So the same gid set yields `FAMILYHOUSING` from an arm that welded and
`FAMILY HOUSING` from one that did not. **The skeleton supplies identity and never supplies
spacing.**

Fragments are concatenated in order of their first owned `gid`, so ordering is a function of
source identity: **reversing the fragment list cannot change the result** (tested).

### Why partition beats plurality

| case | plurality (Model P) | partition (Model G) | preferred |
|---|---|---|---|
| merge 3/1 | whole merged text → line 0, line 1 **blanked** — one glyph double-counted, one physical line vanishes | each line keeps its own glyphs | **G** |
| merge 50/50 | needs an **arbitrary tie-break** | no tie-break exists to need | **G** |
| split 1→2 | both fragments hit one slot; the second is lost or overwrites | rejoined in source order | **G** |

**MEASURED:** partition conserves every glyph exactly once; plurality does not.

### Per-neutral-line comparison state, frozen

State — `SAME` / `TEXT_DIFFERS` / `H_ABSENT` / `X_ABSENT` / `BOTH_ABSENT`.
Diagnostics travel **alongside** and do not enter the state, so nothing disappears silently:
`H/X_MULTIPART`, `H/X_SOURCE_GLYPH_LOSS`, `H/X_SOURCE_GLYPH_DUPLICATION`,
`H/X_CROSS_LINE_MERGE`.

**D-frame membership** = any line not `SAME`, or an anchor-set difference for the region.
**MEASURED symmetric:** `D(H,X) == D(X,H)` across every cardinality case, and the asymmetric
states are explicit mirrors (`H_ABSENT` ↔ `X_ABSENT`).

### The cross-engine control, strengthened

A19 re-pointed it at per-page line **counts**, which the review correctly calls
insufficient — two engines can report 30 lines each and disagree about every one. It is now
a **geometric correspondence**: a PDFium line matches a PyMuPDF line iff their baselines are
within `0.5 × median PDFium ink height` **and** their x-spans overlap by ≥ 0.5 of the
smaller; greedy by ascending baseline distance, one-to-one, ties on the lower ordinal. No
text.

**MEASURED** ([`results/x09_skeleton_cross_engine.json`](results/x09_skeleton_cross_engine.json),
10 pages each): `114-hr-2029/4` **256/256** matched, `118-s-4795/1` **258/259**; median
baseline delta **0.0**, median x-overlap **1.0**.

**No threshold is adopted.** The old 0.95 belonged to a different estimand (agreement on a
page *set*) and is not transplanted. A threshold must be set from this distribution, before
execution, and stated. *Caveat:* PyMuPDF's char box is an **advance** box, not an ink box,
so the x-overlap compares slightly different quantities; at line level the extents nearly
coincide, which the median of 1.0 reflects.

**Can any of this favour H or X?** No. Every input is a fact both arms share, the projection
reads no text, and D-frame membership is measured symmetric. **30/30 synthetic and
development tests pass.** Population impact: none.

---

## A20 — A17-M6 FROZEN: M6 is deferred to a separate validation study

```json
{"id": "A20", "class": "SUBSTANTIVE", "commits": [],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/x06_m6_feasibility.py", "results/x06_m6_feasibility.json"],
 "supersedes_text_in": "PRE-REGISTRATION.md 6 (M6), 7.2 rule 1",
 "resolves": ["A17.1"],
 "status": "FROZEN -- accepted by external review"}
```

### What the evidence actually says, corrected

x06's reference is the nearest preceding account/agency anchor **that production's
`extract_anchors` emits from the HYBRID reconstruction**. That is architecture-derived, not
independent truth. The supported statement is therefore:

> On three development documents, the nearest preceding **hybrid-produced** account/agency
> anchor lies within 6 reconstructed lines for **0.434** of observed amounts and within 10
> for **0.571**; a 50-line span reaches **0.823**.

It does **not** establish the distribution of distances to the *true* governing heading. It
does establish that a 6–10 line viewport cannot support a long-range attribution claim,
which is the design question. A17's earlier wording overstated this and is corrected here.

### Path A — build an independent long-range oracle: specified, then rejected as disproportionate

To adjudicate `amount occurrence → governing account` without using H or X as truth, an
oracle would need: the amount identified by neutral geometry (which neutral line, which
occurrence index within it, since identical dollar figures recur); the account identified by
its own printed occurrence, not by a label string, since account names repeat across
divisions; enough rendered context to contain **both**, which x06 shows means *hundreds* of
lines and frequently **spans pages**; a rule for continuation pages, where the governing
heading appeared on an earlier page under a running head; and controls that make it
falsifiable. The adjudicator would be reading a multi-page span to answer one question.

**Estimated burden on this study's own population:** P-head is 12 documents / 2,864 pages.
Even a modest sample of amounts would require adjudicating multi-page spans repeatedly, and
each item is far more work than a region item. This is a second research project — a
financial-semantics oracle — living inside a seam ADR.

### Path B — defer M6, and narrow RQ2 explicitly *(recommended)*

**Reasons, against the criteria the brief sets.**

| criterion | assessment |
|---|---|
| decision relevance | **low.** M3 is the primary comparative metric, M1 the primary absolute one, M4 tests immediate hierarchy. The seam governs word boundaries; attribution is downstream of the *tree*, not of the seam |
| whether failure could distinguish H from X | **weak.** The design pilot found H and X differ on 2 of 3,381 printed lines and 0 of 85 headings, so a difference is unlikely to appear at all. **Not** because attribution requires a heading difference first: equal heading output does not prove equal attribution, since hierarchy, continuation handling and positional association can all differ downstream |
| oracle independence | Path A's oracle is buildable but its context spans pages, so blinding and provenance get materially harder |
| implementation complexity / human burden | highest of any component, by a wide margin |
| hidden degrees of freedom | high: context size, occurrence matching and continuation rules would all be *invented* now |

**The resolution.**

1. **M6 is removed from this study**, and from §7.2 rule 1's vetoes. Rule 1 becomes:
   `X_CORRECTS ≥ 5`, `X_REGRESSES == 0`, **no M4 regression** — the M6 veto is struck.
2. **RQ2 is narrowed** to: seam → heading presence / text / boundary integrity → **immediate
   hierarchy**. It stops there.
3. **The claim "the money lands under the right account" is withdrawn from this study.** It
   may not appear in any table or summary.
4. **Stated explicitly, because the inference is tempting and wrong:** correct headings and
   correct immediate hierarchy do **not** establish correct financial attribution. Attribution
   depends on the full ancestor chain, on continuation handling across pages, and on amount
   parsing — none of which this study measures.
5. M6 is preserved as **future research** — a dedicated financial-attribution validation with
   its own oracle — not as an unvalidated implication of this one.

**This is a real weakening of the intended claim**, and it is the point of recording it. The
study answers the seam question and stops short of the money question rather than answering
the money question badly.

**Can this favour H or X?** No. It *removes* a veto that could only ever have blocked an X
win, so if anything it very slightly loosens the bar for X — which is why it is recorded as
substantive and why rule 1's other two conditions (including `X_REGRESSES == 0`) are
unchanged.

**Population impact: none.**

---

## A22 — A21's discordance semantics, corrected. Identity ≠ architecture output

```json
{"id": "A22", "class": "SUBSTANTIVE",
 "commits": ["89e9d91", "e277a3e", "7644687"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/neutral_identity.py", "probes/x08_neutral_identity.py",
                   "probes/x10_reconstruction_signature.py",
                   "probes/x11_provenance_chain.py",
                   "probes/x09_skeleton_cross_engine.py"],
 "supersedes_text_in": "PRE-EXECUTION-AMENDMENTS.md A21, A19; PRE-REGISTRATION.md 5.8, 6 (M0)",
 "status": "FROZEN pending external review"}
```

**A21's neutral identity is retained unchanged.** What it got wrong is what to *do* with it.

### The distinction this amendment freezes

> **Identity normalisation is not architecture-output normalisation.**

Model G answers *which physical line each source glyph belongs to*. That question has one
right answer and both arms are held to it. It must not be allowed to answer the different
question of *how many lines the architecture emitted, and which glyphs it grouped together*
— because that grouping **is** an architecture output, and it is one of the two things the
seam can change.

**MEASURED** ([`results/x10_reconstruction_signature.json`](results/x10_reconstruction_signature.json)):

| | neutral N0 | neutral N1 |
|---|---|---|
| H emitted lines | `ABCDEF` (one line, spanning both) | — |
| X emitted lines | `ABC` | `DEF` |
| Model G projected text | H `ABC` / X `ABC` | H `DEF` / X `DEF` |
| state under A21 | `SAME` | `SAME` |
| **A21 D-frame** | **excluded** | **excluded** |
| `H_CROSS_LINE_MERGE` | `True` — a diagnostic that entered nothing | `True` |
| **A22 D-frame** | **included** | **included** |

Partition hands each neutral line back exactly its own glyphs, so the text *cannot* differ.
`differs()` read only `state["state"]`, so the reconstruction disagreement A17.4 exists to
observe was erased. The repair is not to weaken the projection — that would give back the
identity defect A21 fixed — but to compare a **second, independent quantity**.

### The architecture's reconstructed printed line, stated exactly

> **One emitted line = one element of `Page.print_lines`.**

Both arms have the identical pipeline shape: cluster glyphs into rows on baseline → drop
chrome rows → strip the GPO margin number → `print_lines` → `_merge_print_lines` →
`Page.lines`. Production documents `print_lines` as "one entry per line the GPO actually
printed", which is precisely §5.8's "reconstructed printed line".

**`Page.lines` is NOT the unit.** It is the later `_merge_print_lines` soft-hyphen
recombination — *shared production code, called identically by both arms* — and one merged
line spans several physical lines by design. Scoring it would manufacture a cross-line merge
on every hyphenated line in **both** arms at once. It is also strictly less sensitive: it is
a deterministic function of `print_lines`, so any disagreement it shows, `print_lines` shows
first. This is exactly the review's caution about not making a test abstraction the metric
unit, resolved against the real emitted contract rather than against a `Fragment` object.

### The reconstruction signature

> **SUPERSEDED BY A23.** The signature below reads the exact emitted gid subset, so pure
> character **loss** moves it and is reported as a segmentation difference. A23 restricts
> both members to the jointly observed gid domain. The *shape* of the signature and
> everything it is designed to detect are unchanged; only the domain changes.

For a neutral line `N` under architecture `A`, one element per emitted line carrying at
least one of `N`'s glyphs, **ordered by its first owned gid**:

```
signature(A, N) = ( (gids of N that this emitted line carries,
                     other neutral lines this emitted line reaches),  ... )
```

Its length is the emitted-line cardinality, so a **split** shows; its first member
partitions `N`'s glyphs, so **where** a split falls shows; its second member names the
cross-line grouping, so a **merge** shows and merges with **different spans** are
distinguishable from each other.

Deliberately absent, each for a reason: **text and inserted characters**, so a word-space
decision can never register as a segmentation difference; **emitted-line ids**, since two
arms numbering their lines differently is not a disagreement about grouping; **glyphs off
the neutral skeleton**, which are a coverage fact counted separately.

### The three discordance predicates, and the D-frame

Every predicate is an **inequality between the two arms' own values**, so
`D(H,X) == D(X,H)` holds by construction rather than by test:

| predicate | definition |
|---|---|
| `TEXT_DISCORDANCE(N)` | `projected_text(H,N) != projected_text(X,N)` |
| `SEGMENTATION_DISCORDANCE(N)` | `signature(H,N) != signature(X,N)` |
| `ANCHOR_DISCORDANCE(R)` | `set(anchors(H,R)) != set(anchors(X,R))` |

> **A neutral region enters the D-frame iff any of its neutral lines has
> `TEXT_DISCORDANCE` or `SEGMENTATION_DISCORDANCE`, or the region has `ANCHOR_DISCORDANCE`.**

An anchor is placed in a region **by identity**: the neutral line owning the first gid of
the emitted line it was read from decides its region.

**One-arm flags are deliberately not used.** A rule reading `H_CROSS_LINE_MERGE or
X_CROSS_LINE_MERGE` would include a region where **both** arms merged `N0+N1` identically —
structurally odd, but no H/X discordance to adjudicate. It may still matter to RQ2, where
the C-frame is the population; it is not comparative evidence.

### Two further defects found while reproducing the first

**1. Agreement was scored as discordance.** `BOTH_ABSENT != "SAME"`, so every neutral line
*neither* arm emitted — running heads, page numbers, `VerDate` stamps, all correctly dropped
as chrome by both — entered a **census** D-frame. **MEASURED**
([`results/x11_provenance_chain.json`](results/x11_provenance_chain.json)): 22 of 310 and 22
of 313 neutral lines carry no hybrid emitted line, so on the condition that X drops the same
furniture, roughly **7 % of the D-frame was page furniture**. §5.8 is explicit that the
D-frame "cannot see a failure both architectures share. That is exactly why the C-frame
exists", so a shared drop belongs to RQ2. It is excluded from the comparative frame and
reported as the `both_absent` count.

**2. A split was projected as a weld.** A21 joined an arm's emitted-line contributions with
`""`, asserting an adjacency the arm never produced. A heading split at a word boundary
projected as `FAMILYHOUSING`, would have scored a **fabricated M3 weld** against an oracle
reading `FAMILY HOUSING`, and would have counted as **`X_REGRESSES` — a veto term in Rule
1**. The join is now `"\n"`, which is what production already puts between printed lines
(`Page.text`) and which `m3_boundaries.decompose` already reads as a word boundary via
`ch.isspace()`. No new machinery. A split **mid-word** still scores a real boundary defect,
which is correct: the arm did break the word across two printed lines.

### M0, with its components preserved

> **DENOMINATOR SUPERSEDED BY A23.** "Every neutral line in scope" includes lines *neither*
> arm emitted, which are not comparative observations. A23 replaces it with the comparative
> risk set. The component structure below — separate M0a/M0b, union not sum, anchors never
> pooled — is unchanged.

The A19 denominator (neutral lines) is kept. **No weighted composite is invented.** One
denominator for the three line-rate components, so they are comparable to each other:

| | numerator | denominator |
|---|---|---|
| **M0a** | neutral lines with `TEXT_DISCORDANCE` | every neutral line in scope |
| **M0b** | neutral lines with `SEGMENTATION_DISCORDANCE` | *same* |
| **M0-any** | neutral lines with either — the **union**, never a sum | *same* |
| **M0c** | regions with `ANCHOR_DISCORDANCE` | neutral regions in scope — **reported separately, never pooled with the line rates** |

`M0a_only`, `M0b_only` and `both_absent` are preserved raw beside them. **`M0b_only` is the
count this amendment exists to make reachable**: neutral lines where the arms agree on every
character but disagree on how they cut the page into lines. Under A21 it was structurally
zero. M0's control is unchanged: **S1 must raise it**.

### Why this does not disturb M3

Text correctness and line segmentation stay separate concepts, and that is tested rather
than argued:

- `FAMILYHOUSING` vs `FAMILY HOUSING` on the same glyphs → `TEXT_DISCORDANCE`, **no**
  segmentation discordance, reaches M3 as `X_CORRECTS` with H scoring exactly one weld;
- the same heading text under a different emitted-line grouping → `SEGMENTATION_DISCORDANCE`,
  enters the D-frame, and M3 returns `BOTH_CLEAN` — **no fabricated boundary error**;
- inserted characters carry no gid, so the signature is **provably insensitive** to a
  spacing decision.

### The cross-engine control: threshold and consequence, frozen

A21 left "no threshold adopted", a degree of freedom that must not survive into execution.

| | |
|---|---|
| metric | one-to-one matched neutral lines / **max**(PDFium, PyMuPDF) lines, per document, over §5.8's 10 % page subsample |
| threshold | `>= 0.95` per document **and** `>= 0.75` on every sampled page |
| consequence | **SUPERSEDED BY A23** — the "RQ1 is unaffected" clause is withdrawn. ~~a failing document labels every table using it PDFIUM-CONDITIONED FRAME; failing more than a third of sampled documents moves that label into RQ2's headline. RQ1 is unaffected either way — both arms inherit the same skeleton, so a frame error cannot favour H or X, only move the unit both are scored on.~~ **Execution is never blocked by this gate**, which stands. |

The denominator is the **larger** count so that over-segmentation by *either* engine lowers
the score. **Why 0.95 permits ~25× the observed disagreement** (development: 514/515
matched): development is two GPO **bills**, the holdout contains three **committee reports**,
and A19 already records that a two-column page merges its columns into one neutral line. On
that class the engines can disagree for a reason internal to the skeleton's own design, and a
threshold tuned on 20 pages of one document class would be pretending that sample establishes
a population error rate. The **per-page floor** exists because a document fraction hides the
failure that matters: one wholly divergent 26-line page still scores 0.91 across 300 lines.
**What it permits, plainly:** 5 % of a document's lines and 25 % of any single page's,
unlabelled.

**The gate is shown capable of failing** rather than assumed sound — five injected frames per
document: one page displaced 200 pt → FAIL (page floor); every line pairwise-merged → FAIL;
every line split in two → FAIL (the case the `max()` denominator exists for); a tenth of one
page dropped → PASS, permitted; baselines nudged 0.4 × tolerance → PASS, permitted, being
below the tolerance that *defines* a line.

### What the x-overlap evidence does and does not say

The two engines' x extents are **not the same quantity**, and phase 3 already measured this,
so it is cited rather than re-derived: `h01` found `bbox[0] == origin[0]` to 0.0 pt on every
sampled character — which **no ink box can satisfy** — and `h08` traced it to
`jm_trace_text_span`'s `x1 = x0 + adv`. PyMuPDF's line span therefore runs from the first pen
origin to the last advance, while PDFium's runs between ink edges, so the PyMuPDF span
*contains* the PDFium span and the overlap ratio pins to 1.0 — `x_overlap_min` is exactly
**1.0 on every matched line of both development documents**. Measured here: median `x0` delta
**0.602 pt** (the left side bearing), median `x1` delta **0.0**.

**So the x-overlap is a coarse guard**, whose real job is to stop two horizontally disjoint
lines that share a baseline (the two-column case) from matching. It is **not** evidence of
fine geometric agreement and is not reported as such. **Baseline is like-for-like** — both
are pen origins — and carries the control. The **vertical box is not comparable and is not
compared**: only PDFium's height is used, and only to set the tolerance.

### Source-glyph provenance: carried on development, not yet in a real adapter

**MEASURED** ([`results/x11_provenance_chain.json`](results/x11_provenance_chain.json)) —
the chain `PDFium char i → extracted record → reconstruction row → emitted printed line →
neutral projection` holds on two development documents, 12 pages each.

**The adapters are NOT modified**, and that is deliberate: `probes/backends/pdfium_hybrid.py`,
`probes/contract_hybrid.py` and `probes/reconstruct_hybrid.py` are byte-pinned in
[`validation/PRESERVED-MANIFEST.txt`](../PRESERVED-MANIFEST.txt) under tag
`pdf-bakeoff-prevalidation`, and **every `.py` in that manifest verifies clean today**. Those
are the exact bytes that produced the prior spike's confirmatory results; changing them would
retire that claim to buy a field a wrapper can carry.

Instrumenting a frozen implementation means duplicating it, and a duplicate drifts and then
measures a different population while reporting agreement. Both duplications are therefore
**gated by equality against the frozen original**: the instrumented extraction must reproduce
`pdfium_hybrid.extract` field-for-field on every character, and the provenance-carrying
reconstruction must reproduce `Page.print_lines` exactly and in order.

> **The membership contract is therefore NOT yet proven end-to-end in the harness.** It is
> proven on the development hybrid path, through a wrapper whose fidelity is asserted.

**G1 checklist — where the field must actually land:**

1. `contract_hybrid.CHAR_FIELDS` — append `source_char_index`; add `SCI = 9`. Append only,
   so every existing positional index is unchanged.
2. `pdfium_hybrid.extract` — append `i` to both `chars.append(...)` tuples (generated and
   non-generated). The loop already has `i`; no decision changes.
3. `contract_extended` / `pdfium_extended` — the same append on the X arm, from the same
   `FPDFText_*` index.
4. `reconstruct_hybrid.cluster_lines` — it already carries `i` internally and discards it in
   the final comprehension; return the pair instead.
5. `reconstruct_extended.cluster_lines` / `_line_text` — carry the gid through the
   `sorted(..., key=ORIGIN_X)` reordering, and emit `(gid, char)` cells with `gid=None` for
   every space **the rule inserts**.
6. Both `reconstruct_page`s — emit `EmittedLine(cells, lid=(page, index into print_lines))`
   beside each `Line`.
7. Re-hash the affected manifest entries **in the same commit**, with the old and new digests
   recorded, so the preservation claim is retired knowingly rather than silently.

**Population impact: none.** No membership change, no scoring performed, no holdout document
opened, no architecture run on holdout material. `x08` 31/31, `x10` 30/30 including negative
controls showing every predicate returning both answers, `x11` 8/8, `x09` gate PASS on both
development documents with all 10 injected-fault expectations met.

---

## A23 — A22's metric semantics, corrected. Grouping ≠ coverage; M0's risk set

```json
{"id": "A23", "class": "SUBSTANTIVE",
 "commits": ["2f548f0"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/neutral_identity.py", "probes/x10_reconstruction_signature.py",
                   "probes/x11_provenance_chain.py", "probes/x09_skeleton_cross_engine.py"],
 "supersedes_text_in": "PRE-EXECUTION-AMENDMENTS.md A22 (signature domain, M0 denominator, cross-engine consequence)",
 "status": "FROZEN pending external review"}
```

**A22's concept is retained in full.** Text and segmentation remain separate concepts, the
emitted-line unit remains `Page.print_lines`, the D-frame remains the union of comparative
discordances. Three metric-semantics defects are corrected.

### 1. Segmentation conflated glyph loss with line grouping

A22's signature read the exact emitted gid subset, so **pure character loss moved it**.

**MEASURED before repair** ([`results/x10_reconstruction_signature.json`](results/x10_reconstruction_signature.json)):

| | H | X |
|---|---|---|
| emitted | `{0,1,2}` → `ABC`, one line | `{0,2}` → `AC`, one line |
| signature | `((0,1,2),())` | `((0,2),())` |
| `TEXT_DISCORDANCE` | \- | **True** ✔ correct |
| `SEGMENTATION_DISCORDANCE` | \- | **True** ✘ **wrong** — both arms emitted *one* line |

**Duplication was already correct and is reported as such**, not as a repair:
`EmittedLine.gids` is a `set`, so a repeated gid can never reach the signature. Measured:
`H={0,1,2}` vs `X={0,1,1,2}` gave `TEXT=True, SEGMENTATION=False` *before* this amendment.

### 2. Segmentation is now defined on the jointly observed domain

> **`common`** = the page-wide set of gids **both** arms emitted.
> `signature(A,N)` = one element per emitted line of `A` carrying ≥1 gid of `N ∩ common`,
> ordered by its first such gid:
> **`( sorted(e.gids ∩ common ∩ N.gids),  sorted({owner[g] for g in e.gids ∩ common} − {N}) )`**

**Both members are restricted, and the second matters as much as the first.** Reading
`others` over all gids would let an emitted line be recorded as reaching a neutral line via
a glyph *only one arm emitted* — manufacturing a cross-line merge out of a coverage
difference.

**Topology survives a coverage defect**, which is the case that makes this non-trivial. If
H merges `N0+N1` **and** loses a glyph of `N1`, the surviving jointly observed glyphs of
`N1` are still carried by an emitted line that also carries `N0`'s, so `others` still names
`N0` for H and not for X. **Measured: segmentation discordance on both lines, with the loss
separately visible as `H_SOURCE_GLYPH_LOSS`.** Coverage cannot hide topology; topology
cannot be manufactured from coverage.

**Vacuous case, stated not hidden.** When no gid of a line is jointly observed — one arm
emitted nothing for it — both signatures are `()` and segmentation is concordant. That is
correct: with no shared evidence there is no grouping to disagree about. The case is carried
in full by text/coverage discordance, so it never leaves the D-frame; only its *attribution*
between the two components changes. `SEGMENTATION_DEFINED` records it per line, so a zero
M0b can never be misread as "the arms grouped identically" when it means "there was nothing
to compare".

### 3. The segmentation estimand, in one sentence

> **M0b is the fraction of neutral physical lines in the comparative risk set on which H and
> X group their jointly observed source glyphs into emitted printed lines differently.**

It does **not** measure — each of these belongs elsewhere and is reported elsewhere:

| not measured by segmentation | where it lives |
|---|---|
| character loss | `H/X/SHARED_SOURCE_GLYPH_LOSS`, and M0a via the projected text |
| character substitution | M0a; M2/M3 against the oracle |
| duplicate characters | `H/X_SOURCE_GLYPH_DUPLICATION`, and M0a |
| inserted spaces | M0a; M3's boundary vector |
| oracle correctness | M1–M4, C-frame only |

### 4. M0's denominator is the comparative risk set

| | |
|---|---|
| **old** | every neutral line in scope, **including lines neither arm emitted** |
| **new** | **neutral lines emitted by at least one architecture** (`state != BOTH_ABSENT`) |
| `BOTH_ABSENT` | **excluded from every M0 denominator**, **retained as a raw count**, and handled by the C-frame / RQ2 |

**Why, and the challenge answered.** §6 defines M0 as the fraction of aligned printed lines
whose text differs *between H and X*. A line neither arm emitted is not a comparative
observation on which they agreed; it is a unit **not at risk**. Including it would answer
the question "discordance per physical ink line on the page" — a real question, but an
**absolute coverage** one (did the arms emit the page's content at all), which is RQ2's and
is answered by the C-frame against an adjudicated oracle. M0 is RQ1's comparative resolution
statement and may not silently answer a different one.

The concrete harm is not dilution but **confounding**: the rate would depend on how much
page furniture a document carries, which is a property of GPO's *layout*, not of the seam.
Committee reports and bills carry different chrome densities, so a P-head/P-robust gap in M0
could be pure furniture.

**"At least one", never "both":** an arm emitting a line the other dropped is among the
strongest discordances there is, and a both-arms denominator would delete the numerator's
own members from the population it is a fraction of.

**MEASURED direction, so the choice cannot be read as chosen for the number.** Excluding
`BOTH_ABSENT` **shrinks** the denominator and therefore **raises** every reported rate. On
the synthetic denominator fixture, `M0_any` moves 0.2 → 0.5; on development material 22 of
310 and 22 of 313 neutral lines are emitted by no hybrid line at all, about a **+7 %
relative** shift conditional on X dropping the same furniture. **RQ1 seeks an equivalence
statement, so this makes the study's own claim harder to support, not easier.**

`M0b_defined` and `M0b_rate_on_defined` are reported beside the headline, and
`M0_any_rate_ALL_LINES_superseded` is emitted alongside so the two estimands stay comparable
in the record rather than the change becoming invisible after the fact.

### 5. Where a shared failure is caught, since M0 no longer sees it

`H absent + X absent + oracle says true content` is **not** an M0 or D-frame question — §5.8
already states the D-frame "cannot see a failure both architectures share. That is exactly
why the C-frame exists." **Verified against the frozen protocol**, the mechanism is already
specified and does not depend on M0:

1. **C-frame regions are drawn over the NEUTRAL SKELETON** (A19), not over either arm's
   emitted lines, so a jointly dropped line **can** be sampled.
2. **The oracle image is rendered from the region's PDF geometry** — §5.7 records "bbox in
   PDF points", DPI and the rendered PNG's SHA-256 — not from either arm's text, so a
   jointly dropped line **is still printed in what the adjudicator sees**.
3. **M1's recall denominator is the adjudicated enumeration**, not the emitted one, so a
   heading both arms missed is a recall miss for both.
4. **M9** independently reports `derive_size_bands` / `_coverage ≥ 0.85` / margin-numbered
   lines recovered, per document per architecture, catching a shared coverage collapse.

**REQUIRED INVARIANTS for `build_frames.py` / `score_metrics.py`** (none of which exist yet
— G5 lists them as missing), stated now so they cannot be violated silently later:

- **I1.** C-frame region enumeration reads the neutral skeleton **only**. Enumerating from
  emitted lines would make a shared drop structurally unsamplable, and the failure would be
  invisible rather than merely unmeasured.
- **I2.** Oracle rendering uses the region bbox in PDF points. No arm's text may reach the
  renderer.
- **I3.** M1 recall is computed against the adjudicated enumeration; the emitted set may
  only supply the precision numerator.
- **I4.** `both_absent` and `SHARED_SOURCE_GLYPH_LOSS` are carried into the per-document
  report so the C-frame result can be read against them.

Absolute correctness is **not** solved inside M0, and this amendment does not attempt it.

### 6. A failed cross-engine control qualifies RQ1 as well as RQ2

A22 said RQ1 was "unaffected" because both arms inherit the same frame. **Withdrawn.**

**MEASURED, and it did not support the obvious argument.** The per-line comparative
*verdict* proved **robust** to every partition tried — a merge/split disagreement is still
detected whether the frame separates two physical lines or merges them. Claiming a verdict
flips would have been an argument constructed rather than measured. The conditioning enters
through the **denominator and population**: identical architecture output scored against two
different neutral partitions of the same glyphs gives `M0_any` **0.667** and **0.5**,
because the frame decides how many neutral lines exist, which are in the risk set, and —
through the 8-line region grid — which regions enter the D-frame and which are drawn into
the C-frame.

> **A failed cross-engine control does not directly favour either architecture, because the
> frame is common to both. But every comparative and absolute result computed on that
> document remains conditional on the PDFium-defined frame.**

| | frozen consequence |
|---|---|
| one document fails | every **RQ1 and RQ2** result or table computed on it carries **PDFIUM-CONDITIONED FRAME** |
| more than ⅓ of sampled documents fail | the headline qualification applies to **both RQ1 and RQ2** |
| execution | **never blocked by this gate** — this is claim qualification, not post-hoc exclusion |

**Thresholds are unchanged at 0.95 document / 0.75 page.** They are already frozen,
deliberately loose, exercised by five injected faults per document, and explicit about what
they permit; nothing in this repair reveals a defect in the metric itself, so only the
consequence wording moves.

### 7. M0 and the D-frame have one eligibility set, not two

| | rule |
|---|---|
| **D-frame** | census of regions with **any** comparative discordance: text **or** segmentation **or** anchor |
| **M0** | descriptive rates over the comparative **risk set** (neutral lines emitted by ≥1 arm) |

- Every M0a/M0b discordant line **is** in the risk set, and its region **does** enter the
  D-frame — the same two predicates decide both, so no line can count toward M0 without
  putting its region in the frame.
- **Anchor** discordance can put a region in the D-frame **without** affecting M0a/M0b — it
  is region-level, and M0c carries it on the region denominator, never pooled with the line
  rates.
- `BOTH_ABSENT` affects **neither** the D-frame **nor** any M0 rate, and is reported raw.
- Shared failures stay eligible for RQ2 via the C-frame, under I1–I4.

### 8. M3 remains insulated

All four controls measured, the last two new:

| case | result |
|---|---|
| `FAMILYHOUSING` vs `FAMILY HOUSING` | `TEXT_DIFFERS`, **no** segmentation discordance, M3 `X_CORRECTS`, H weld 1 |
| same heading text, different line grouping | segmentation discordance, in the D-frame, M3 **`BOTH_CLEAN`** — no fabricated boundary error |
| X drops a character | text discordance, **no** segmentation discordance, M3 `X_REGRESSES` with `text_error 1 / weld 0 / split 0` |
| X duplicates a character | text discordance, **no** segmentation discordance, M3 `X_REGRESSES`, X dirty |

**M3 consumes text and oracle evidence and never an M0b label**, which is what keeps
segmentation out of the boundary metric.

### 9. Provenance scope is unchanged

The development wrapper still proves the chain without touching the byte-pinned prior-bakeoff
adapters, and `probes/backends/pdfium_hybrid.py`, `probes/contract_hybrid.py` and
`probes/reconstruct_hybrid.py` remain unmodified — re-verified against
[`PRESERVED-MANIFEST.txt`](../PRESERVED-MANIFEST.txt). A22's G1 checklist stands unchanged;
it is a known implementation gap, not a new blocker.

**Population impact: none.** No membership change, no scoring, no holdout document opened,
no architecture run on holdout material. `x08` 31/31, `x10` 43/43, `x11` 8/8, `x09` gate PASS
with all 10 injected-fault expectations met, `x04` unchanged at **FREEZE INTEGRITY COMPLETE /
EXECUTION FORBIDDEN**.

---

## A24 — Two frozen rules did not determine what the code should do. **RESOLVED**

```json
{"id": "A24", "class": "SUBSTANTIVE",
 "commits": ["db3c0d2", "277a0e5"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/run_hybrid.py", "probes/pdfium_extended_corrected.py",
                   "probes/reconstruct_extended_corrected.py", "probes/run_extended.py",
                   "probes/x2_verify.py", "probes/x11_provenance_chain.py",
                   "probes/x12_skeleton_eligibility.py", "probes/x13_x_arm.py",
                   "probes/neutral_identity.py", "probes/x08_neutral_identity.py",
                   "probes/x09_skeleton_cross_engine.py",
                   "probes/x10_reconstruction_signature.py", "probes/x04_freeze_check.py"],
 "supersedes_text_in": "PRE-REGISTRATION.md X-2 (X2-b scope); PRE-EXECUTION-AMENDMENTS.md A19, A21 (eligibility)",
 "status": "RESOLVED -- both rulings implemented and measured"}
```

**When the ruling was made, stated accurately.** An earlier draft of this section said the
ruling was "recorded before the evidence that motivated it". **That is withdrawn — it was
false.** The actual order was:

```
db3c0d2   DEVELOPMENT implementation exposes A24.1 / A24.2; ambiguity recorded OPEN
          external review rules: generated-only X2-b; provenance != neutral identity
277a0e5   the ruling is implemented
207e244   ledger declaration closed
```

> **The ruling was made AFTER development evidence exposed the ambiguity, but BEFORE any
> confirmatory H/X output existed and before execution was authorized.**

That is the methodologically load-bearing statement, and it is the true one. Development
evidence **did** inform the amendment — the measured numbers below are exactly what made the
two readings visible — and no confirmatory evidence existed to inform it, because no holdout
document has ever been opened by either architecture.

The frozen prose PERMITTED both readings in each case; neither alternative was unreasonable,
and implementation is what exposed the ambiguity. That is why both are recorded as amendments
rather than as defects.

### A24.1 — CLARIFICATION. "the engine's spaces" means PDFium-*generated* U+0020

> **X2-b: re-admitting PDFium-generated U+0020 characters (`FPDFText_IsGenerated == true`)
> must change no reconstructed printed line.**

X2-b is **not** required to reproduce every content-stream U+0020. Why:

- **X2-a already carries the contract invariant** that no U+0020 crosses the X seam. The two
  assertions have different jobs and X2-b need not re-state X2-a's.
- **X2-b's purpose is independence from PDFium's own inserted boundary decisions.** Its
  provenance is phase 3's D2 finding: the earlier extended adapter was taking most word
  boundaries from PDFium-generated spaces while claiming to derive them geometrically.
- **A content-stream U+0020 was supplied by the PDF, not invented by PDFium**, so
  reproducing it is not evidence about engine independence.
- **The strict reading would have made X2-b a partial H/X equivalence gate**, so a genuine
  architecture disagreement would make X unscorable *before* the independent oracle could
  determine which architecture is right. That inverts the study.

**Implemented** in `x2_verify.py` as `X2b_gate_generated_only` (the gate) and
`X2b_diagnostic_all_source_spaces` (DEVELOPMENT diagnostic only). The generic
`X2b_rule_recovers_engine_spaces` key is retained solely because `x04` reads it, and it now
carries the **gate**. A diagnostic failure is reported with its differing lines, does **not**
close G2, and does **not** void X.

**MEASURED**: `X2a` PASS on both development documents; `X2b` gate PASS on both; the
all-source-spaces diagnostic differs on `114-hr-2029/4` at one line in 191.

### A24.2 — SUBSTANTIVE. Positive-area geometry does not uniquely identify ink

`x12` falsified the assumption underneath A19/A21: PDFium reports a positive-area character
box for a content-stream U+0020 — about **3.6 pt wide and 0.014 pt tall** against ~**7.9 pt**
for a capital — so the geometric rule was admitting every word space into a skeleton defined
as ink-only.

**The absolute phrase "NO codepoint is consulted" is WITHDRAWN.** The replacement invariant:

> **Neutral physical-line identity is formed from upright source characters with valid,
> finite, positive-area geometry, EXCLUDING U+0020.**

**No ink-height threshold is introduced.** A minimum height would be a new tunable constant
and would immediately raise punctuation, tiny type, diacritics, footnote marks, superscripts
and unusual fonts. The lexical exception is narrower and is legitimate because: U+0020 is a
**below-seam source fact** available before either architecture runs; **X-2 already froze**
the judgment that a space carries no ink, so this adopts a decision the protocol had made
rather than inventing one; it reads **no H or X output**; it **cannot favour either arm**;
and `x12` measured that PDFium's char-box API simply does not encode the ink/non-ink
distinction by area. **Scope is U+0020 alone — this is not a whitespace blacklist.**

#### The representation repair, which is the substance

`source_char_index` was serving as **both** provenance and neutral ink identity. A24.2 proves
those are different concepts: a content-stream space has real provenance and **no** physical
ink identity — a state the single field could not express. Cells are now
`Cell(ngid, char, sci, generated)`:

| | `sci` | `ngid` | text | status |
|---|---|---|---|---|
| ordinary ink | 123 | **123** | `A` | source |
| content-stream U+0020 | 124 | **None** | `␠` | source |
| PDFium-generated U+0020 | 125 | **None** | `␠` | `generated=True` |
| X-inserted space | **None** | **None** | `␠` | architecture decision |

Only `ngid` may reach the neutral skeleton, `common`, the reconstruction signature or a loss
diagnostic. `sci` and the character stay visible to projected text, and therefore to M2/M3.

**Model G needed no change** to keep spaces in projected text — its rule was always about
ATTACHMENT, not identity:

> A non-neutral character contributes to neutral line N iff, in the architecture's own
> emitted order, it lies between two ink glyphs N owns, with no ink glyph of another neutral
> line intervening.

Tested across every provenance and position: content-stream, generated and X-inserted spaces
between owned ink are kept **identically**; leading, trailing, cross-neutral-line and
adjacent-to-foreign spaces are dropped; consecutive spaces travel together. A space never
becomes identity merely because it needed attachment semantics.

#### MEASURED, paired on one population and one page limit

| | `114-hr-2029/4` | `118-s-4795/1` |
|---|---|---|
| U+0020 admitted to skeleton, before → after | 229 → **0** | 1398 → **0** |
| neutral line count, before → after | 205 → **205** | 205 → **205** |
| pages where the **ink** partition changed | **0** | **0** |
| neutral lines whose x-extent changed | 132 | 138 |
| X source-glyph loss, **X-only** | **0** | **0** |
| X source-glyph loss, shared with H | 188 | 188 |
| cross-engine matched fraction, before → after | 1.0 → **1.0** | 0.9961 → **0.9961** |

Removing spaces is **not** geometrically inert for bounding boxes but **is** inert for which
ink glyphs share a physical line, which is the property that matters. The surviving loss is
**shared** — the GPO margin number, which §3.3 has both arms strip identically — so the
diagnostic is interpretable again instead of saturated by contractually excluded spaces.

**The cross-engine control now applies the same exclusion on both sides**, reading the
codepoint from PyMuPDF's own trace. Without that it would have compared two differently
*defined* frames and reported the definition gap as engine disagreement. Thresholds are
**unchanged** at 0.95 document / 0.75 page.

#### The `H. R. 2029` disagreement is preserved, not normalised

Frozen as a regression fixture: H projects `H. R. 2029`, X projects `H.R.2029`. That is
**TEXT discordance and NOT segmentation discordance**, and it enters the D-frame.

**What the fixture proves:** the spacing disagreement survives contract validation and
reaches M3, and *given a synthetic oracle of* `H. R. 2029`, the scoring path classifies it as
`X_REGRESSES`. **What it does not prove:** that H's form is correct on the real document. The
oracle in the fixture is chosen to exercise the pipeline, not to adjudicate. Whether
`H. R. 2029` or `H.R.2029` is right on `114-hr-2029/4` is for the independent oracle, which
does not exist yet. **The eligibility gate does not decide correctness — the oracle does.**

#### G2 now executes rather than trusts

`x04`'s G2 runs the authoritative verifier live and requires exit 0, on top of the existing
fixture-provenance and blob-binding checks. **Proven able to fail**: with `x2_verify`
temporarily faulted, G2 reported `live x2_verify exited 1` while the stored artifact still
read `X2a=True X2b=True` — precisely the failure mode the live check exists to catch.

**Population impact: none.** Post-selection, pre-execution. No membership change, no scoring,
no holdout document opened.

---

> # ⛔ SUPERSEDED HISTORICAL RECORD — NOT OPERATIVE
>
> **Everything from here to the "end of superseded record" marker below describes the state
> BEFORE the ruling above.** It is retained because it is the evidence that motivated the
> ruling, and deleting it would erase why the amendment exists. **It is not the protocol.**
>
> Where this block says A24.1 or A24.2 is *open*, *blocking*, *unresolved*, or that *a ruling
> is required*, read those as statements of the historical state at commit `db3c0d2`. Both
> are **RESOLVED**; the operative text is the A24.1 / A24.2 ruling sections above.
>
> Nothing in this block may be cited as current normative protocol.

### *(historical)* A24.1 — "the engine's spaces" in X2-b *(was blocking)*

X-2 freezes two assertions. X2-a is unambiguous and **passes**. X2-b says *"re-admitting the
engine's spaces changes no reconstructed line"*, and **"the engine's spaces" has two
defensible readings that disagree**:

| reading | textual support | result |
|---|---|---|
| **generated only** — spaces PDFium *invented* | X-2's own sentence that not carrying U+0020 "excludes **engine-invented** spaces without the Experimental predicate"; X2-b's "the boundaries **they** were supplying" | **PASSES** on both development documents |
| **all U+0020** the contract drops | X-2's rationale "a space carries **no ink**", equally true of a content-stream space; X2-a is stated over **all** codepoint-32 glyphs | **FAILS** on `114-hr-2029/4` |

**MEASURED** ([`results/x2_contract_assertions.json`](results/x2_contract_assertions.json)):
one differing line in 191 — the rule yields `H.R. 2029` where the engine had `H. R. 2029`.
**Both of those spaces are `generated=False`**: real content-stream spaces PDFium never
decided, which is precisely why the two readings separate here.

**The mechanism, measured rather than inferred.** On that line `'.'→'R'` and `'.'→'2'` have
an **identical 5.940 pt gap at size 36**, and the ported rule returns `False` for the first
and `True` for the second. `wants_space` scales its threshold by the **larger of the two
advances**: `R` (24.48) lifts the threshold to 6.12 pt, above the gap; `2` (20.16) leaves it
at 5.04 pt, below. So the rule misses a real word boundary whenever a wide glyph follows a
narrow one at display size. That is a property of the port, not a defect in this adapter.

**Why it is blocking.** §5 states that an X2-b failure means "the rule is not doing the work
and the run is **void for X**". So this single sentence decides whether the X arm can be
scored at all. `x2_verify` reports **both** readings and sets the headline field to the
**stricter** one, so G2 cannot open on an interpretation chosen by the implementation.

**Not adopted here**, and each needs review: (a) rule that X2-b means generated spaces only;
(b) keep the strict reading and treat the display-type miss as a real X defect, voiding X;
(c) keep the strict reading with a stated tolerance — but a tolerance is a scoring-rule
change and cannot be introduced by the implementation.

### *(historical)* A24.2 — geometric eligibility admits every content-stream space *(was blocking)*

A19/A21 froze eligibility as **geometric**, specifically to avoid a codepoint filter, and
A21 measured it in **one direction only**: "the number excluded *only* by a codepoint rule
is 0". That check cannot see what the rule **includes**.

**MEASURED** ([`results/x12_skeleton_eligibility.json`](results/x12_skeleton_eligibility.json)):
PDFium reports a positive-area box for a content-stream U+0020 — about **3.6 pt wide and
0.014 pt tall**, against **7.9 pt** for a capital, a **568×** height ratio. It clears
`(y1 − y0) > 0` by a hair, so `eligible()` admits it and every real word space becomes a
**neutral skeleton member**.

| | `114-hr-2029/4` | `118-s-4795/1` |
|---|---|---|
| U+0020 admitted to the skeleton | 229 | 1398 |
| neutral lines containing a space gid | **141 / 205 (69 %)** | **190 / 205 (93 %)** |
| lines showing X source-glyph loss | **150 / 151** | **157 / 158** |

**Why it is blocking.** X-2 drops every U+0020, so X can never emit these gids. They sit
permanently outside `common` and permanently inside `X_SOURCE_GLYPH_LOSS`, which is
therefore **structurally saturated and currently uninformative** — a reader would reasonably
read "X lost source glyphs on 157 of 158 lines" as X dropping content. They also widen each
neutral line's x-extent, which feeds region geometry and the **oracle's rendered bbox**.

**Not adopted here.** A minimum ink height would separate a space from a capital by ~568×
and would stay **purely geometric** — it needs no codepoint, so it does not reopen the
frozen "geometric eligibility" principle — but **choosing the threshold is a new
outcome-affecting decision** and belongs in an amendment. The frozen rule is implemented
faithfully and its consequence is measured.

### What was built, and what it is held to

Five result-bearing components are committed, each carrying
`frozen rule → executable behaviour → test → evidence` in its header:
`run_hybrid.py`, `pdfium_extended_corrected.py`, `reconstruct_extended_corrected.py`,
`run_extended.py`, `x2_verify.py`.

**The X contract is corrected against a measured defect.**
`validation/phase2/pdfium_extended.py` keys its undecodable rule on `cp < 0x20`, so U+0020
fell through: **1142 of 7382 glyphs (15.5 %)** on six pages, **947 of them PDFium's own
inventions**. That is phase 3's D2 finding, and X2-a failing on that adapter is now a
standing negative control.

**The A19 one-skeleton invariant is asserted, not assumed.** Both runners call the same
`run_hybrid.neutral_skeleton`, and `x13` checks per page that the results are identical.
Deriving the skeleton from X's own glyphs would have omitted every content-stream space and
silently given the two arms different adjudication units.

**DEVELOPMENT observations, which are explicitly not results** — no holdout document is
opened, no oracle exists, no decision rule has been evaluated: M0a 35/141 and 36/148;
**M0b 0 on both**, consistent with §3.3 holding line clustering identical across the arms.

**Population impact: none.** No membership change, no scoring, no holdout document opened.

> # ⛔ END OF SUPERSEDED HISTORICAL RECORD
>
> Operative text resumes here. The A24 rulings above are the protocol.

---

## A25 — SUBSTANTIVE. X2-b's operationalization, repaired. **RESOLVED**

```json
{"id": "A25", "class": "SUBSTANTIVE",
 "commits": ["070098e", "46b343a", "4db8cc8"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/x2_verify.py", "probes/x04_freeze_check.py",
                   "probes/reconstruct_extended_corrected.py",
                   "probes/neutral_identity.py", "probes/x08_neutral_identity.py",
                   "probes/x10_reconstruction_signature.py"],
 "supersedes_text_in": "PRE-EXECUTION-AMENDMENTS.md A24.1 (X2-b operationalization only)",
 "status": "RESOLVED -- non-vacuous counterfactual frozen and measured"}
```

**A24.1's estimand is unchanged.** X2-b is still exactly "independence from PDFium-generated
boundary decisions". What was wrong was the *executable representation*, not the scope.

### The defect

The first implementation re-admitted PDFium-generated U+0020 **as glyphs**. Those characters
report `font_size` exactly **1.0** — PDFium hands generated characters the identity matrix —
and X's `cluster_lines` keeps `size > _SIZE_FLOOR` with `_SIZE_FLOOR = 1.0`. Every one was
removed by X's pre-existing size filter *before reconstruction*, so both sides of the
assertion reconstructed an identical glyph set (**3914 glyphs either way**) and the gate
**compared a page against itself**. It could not fail, and a sabotage injected into
`wants_space` fired in both arms, confirming it from the rule side.

### The repair, at the layer the evidence lives at

A generated space is **not an ink glyph**. It carries exactly one fact:

> there is a word boundary between source character *i* and source character *j*

So the counterfactual re-admits that **decision**, not the glyph.

| | |
|---|---|
| **boundary identity** | `(page_number, sci_before, sci_after)`, read from a RAW PDFium text-page stream — never geometry, string matching, line ordinals, or X output |
| **raw stream** | `raw_source_stream` calls exactly three PDFium entry points — `FPDFText_CountChars`, `FPDFText_GetUnicode`, `FPDFText_IsGenerated` — and nothing else. `sci` is the text-page index itself, so no position can be lost or renumbered |
| **neighbour rule** | `select_neighbours` is **pure** and takes only `(sci, codepoint, generated)` triples: nearest preceding and following characters that are **not generated** and **not raw CR/LF**. It has no parameter through which geometry could reach it. A content-stream U+0020 on either side is counted and classified untestable, since X-2 drops every U+0020 |
| **X** | ordinary X — same contract, clustering, ordering, chrome, margin handling, reconstruction |
| **X′** | ordinary X **+ the generated-boundary map**; the only difference is the word-boundary decision |
| **X2-b PASS** | `X.print_lines == X'.print_lines`, byte-for-byte, page-for-page, line-for-line |

**X′ never receives a generated glyph.** Nothing is inserted into X's contract, nothing is
clustered, no generated geometry or font size is consulted, and no generated space receives
a neutral gid. X's scoring behaviour is untouched: the only production change is an optional
`decider` parameter defaulting to `wants_space`.

**Cross-line pairs are deliberately NOT testable.** X2-b asks whether X recovers a *word*
boundary; when X assigns the two characters to different reconstructed lines there is no
within-line boundary for X to have made. That disagreement is line-reconstruction behaviour,
which A22/A23 already route to M0b and the D-frame. Inventing a word space across an X line
break would make X2-b answer a segmentation question it was never scoped to.

### MEASURED on DEVELOPMENT (8 pages each)

| | `114-hr-2029/4` | `118-s-4795/1` |
|---|---|---|
| generated U+0020 | 1347 | 214 |
| candidate boundary pairs | 1347 | 214 |
| both neighbours survive X's contract | 1347 | 214 |
| same X reconstructed line | 1346 | 213 |
| different X lines (untestable) | 1 | 1 |
| **X2-b-testable** | **1346** | **213** |
| ordinary `wants_space` recovered | **1346** | **213** |
| missed | **0** | **0** |
| X vs X′ differing printed lines | **0** | **0** |

**X2-b PASS on 1559 testable boundaries.** X does independently recover every PDFium-generated
boundary decision on this material — now an evidenced result rather than an artefact of a
comparison that could not fail.

### The negative control, behavioural and isolated

Suppressing **one** ordinary geometric decision — source chars `211 → 213` on page 1 — while
X′ keeps the boundary because the **map** supplies it:

```
X   = 'MAY21, 2015'
X'  = 'MAY 21, 2015'      -> X2-b FAIL
```

Separate callables, no global monkeypatch. The fault is **page-qualified**: `sci` is
page-local, and 2 other pages carry the same index pair and are measured to be untouched.
Isolation is carried by eight recorded checks rather than by the claim — exactly one True
decision **site** flipped (sites, not invocations, since a call counter grows with the number
of reconstruction passes and says nothing about scope); the fault installed for the target
page only; the target is X2-b-testable; the map still holds that page-qualified boundary;
X differs from X′; **sabotaged X′ == unsabotaged ordinary X**; the sabotage did change
ordinary X; and the denominator and boundary map are unchanged.

### Gate hygiene

The superseded glyph-readmission path is **removed** — no generic `x2b()` silently means
different things by mode. A24.1's all-source comparison survives as
`all_source_space_diagnostic`, explicitly **non-authoritative**; it still differs on
`114-hr-2029/4` at the `H. R. 2029` line and neither closes G2 nor voids X.

**G2 requires the denominator as evidence, not inference:**
`X2b_testable_boundaries_total` must be a positive int and `X2b_gate_is_vacuous_SEE_A25`
must be `False`, checked independently of the gate boolean, alongside artifact provenance
and live execution. Non-vacuity is never inferred from a PASS.

### Implementation defects found in review, repaired without redesign (`4db8cc8`)

The first counterfactual built its map from `run_hybrid.extract_with_gids`, a **filtered**
wrapper: it omits a non-generated character when `GetCharBox`, `GetMatrix` or
`GetCharOrigin` fails, and rewrites every non-generated `cp < 0x20` to U+FFFD. Either can
move which character is "nearest" to a generated space, so the frozen "never geometry" rule
was violated in practice. Replaced by the raw stream and pure selector above.

**The census did not change**, and that is reported rather than dressed up as a fix that
mattered: 1347/1347/1346 and 214/214/213, **1559 testable, PASS**, identical before and
after. **MEASURED** exposure: on this material the wrapper omits **0** non-generated
characters but rewrites the codepoint of **53** and **45** of them, and a non-generated raw
CR/LF rewritten to U+FFFD would no longer be skipped as a neighbour. The defect was real in
principle; no boundary's neighbour selection actually changed here.

The sabotage was also not page-specific — `sci` is page-local — and is now page-qualified,
as recorded above.

**Population impact: none.** Post-selection, pre-execution. No membership change, no scoring,
no holdout document opened.

---

## A26 — TOOLING. The downstream-harness contract and dependency plan

```json
{"id": "A26", "class": "TOOLING",
 "commits": [],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": [],
 "status": "PLAN ONLY -- reasoning only; accounting handed to A27"}
```

`HARNESS-PLAN.md` maps the already-frozen methodology onto executable contracts for the five
unbuilt components (`build_frames`, `build_oracle`, `score_metrics`, `decide_architecture`,
`adjudicator_prompt`): inputs, output schema, the frozen rule each implements, what each may
and may not decide, invariants, positive and negative controls with "what fact would make
this fail" for every gate, and the dependency order.

**It changes no scoring rule and freezes nothing**, which is why it is TOOLING. Where the
frozen rules do not determine an outcome-affecting choice, the plan **surfaces** the
ambiguity rather than resolving it. Three are methodological and need a ruling before the
components they gate are written:

- **M1–M4's matching key under A19.** §6 matches "by printed-line position"; A19 moved the
  unit to neutral lines and restated only the *denominators*. The key itself is unspecified
  in neutral terms, and it determines which emitted heading pairs with which adjudicated
  heading — hence `X_CORRECTS` / `X_REGRESSES`, hence Rule 1.
- **The 40 % amount-bearing C-frame reservation after A20.** Its stated purpose was to give
  M6 a population; M6 is deferred, yet A19 retained the clause. It now constrains 40 % of a
  scarce adjudication budget for a metric the study may not report.
- **D-frame subsampling, 60 items (§5.5.1) vs 120 regions (§5.8).** A10 supersedes §5.5.1
  but does not name §5.8; applying §5.8's subsample first would let X win on a sample, which
  A10 forbids.

Two further items are implementation-only: confirming `Anchor` carries enough to place an
anchor on a neutral region by identity, and keeping `X_CORRECTS` counted in heading
occurrences rather than boundary-level tallies.

**A26 hands its protected-file accounting to A27**, and keeps only the reasoning above. When
A26 was written the plan froze nothing, so TOOLING was the honest class. A27 then put frozen
rulings *into* `HARNESS-PLAN.md`, which makes that file substantive — and F9 forbids one file
being declared under both a SUBSTANTIVE and a TOOLING amendment, correctly. Rather than
relabel A26's reasoning as substantive when it is not, the file and both its commits are
declared under A27, exactly as A6 hands its accounting to A18.

**Population impact: none.** No membership change, no scoring, no holdout document opened,
no component built.

---

## A27 — SUBSTANTIVE. The harness contract: matching key, frames, budget, outcomes, statistics, determinism

```json
{"id": "A27", "class": "SUBSTANTIVE",
 "commits": ["af10155", "2938312"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["HARNESS-PLAN.md", "probes/x14_anchor_bridge.py"],
 "supersedes_text_in": "PRE-REGISTRATION.md 5.5.1, 5.8, 6 (M1 matching), 7.2; PRE-EXECUTION-AMENDMENTS.md A10, A19 (40% clause)",
 "status": "FROZEN -- rulings recorded before any harness component exists"}
```

Mapping the frozen methodology onto executable contracts (A26) exposed places where two
readings would produce different numbers. These are the rulings. **No harness component is
built**, and no confirmatory output exists.

### A27.1 — M1–M4 heading matching is a source-position key, never text

> **Occurrence identity = `(document_sha256, page_number, start_neutral_line_key,
> occurrence_ordinal_on_that_line)`.**

A wrapped heading takes its **first physical neutral line**. Where several occurrences begin
on one neutral line they are separated by **source order on that line**. Architecture output
is mapped to this key through source/physical identity; **the oracle must record enough
source position to name the same key**.

**Text similarity and occurrence-order-within-region are both rejected.** §6's "matched by
printed-line position" names an architecture *output*, and A19 moved the unit to neutral
lines while restating only the denominators. Matching on text would be circular — text is
the thing under measurement — and order-within-region silently re-indexes every later
heading when an earlier one is missed.

If an emitted or adjudicated occurrence cannot be mapped **uniquely**, it is `UNMATCHED`.
**There is no text-similarity fallback**, and `UNMATCHED` is reported, never quietly dropped.

Required adversarial controls: a missing earlier heading does not shift later matches;
identical heading text on two neutral lines does not collide; a wrapped heading maps to its
first physical neutral line; an architecture merge or split does not move the positional
identity; two occurrences on one physical line stay separately matchable.

### A27.2 — the 40 % amount-bearing C-frame reservation is REMOVED

§5.8 reserved 40 % of C-regions for amount-bearing pages, for the stated purpose of giving
M6 a population. **A20 deferred M6 and forbade this study from claiming amount attribution**,
so the reservation now shapes the C-frame for no surviving estimand while spending 40 % of a
scarce adjudication budget.

> **Operative C-frame: a deterministic uniform selection over the neutral regions of every
> page of every P-head document, at most 8 regions per document, with NO amount-bearing
> enrichment and no other stratification.**

Recorded as substantive rather than folded into A19 silently: it changes which regions are
adjudicated, hence every M1–M5 denominator.

### A27.3 — the D-frame adjudication item is a REGION, and the budget is 60 regions

> The complete D-frame **region** census is always enumerated **before** any sampling.
>
> - **≤ 60 regions** → human-adjudicate the **complete census**; Rule 1 may be evaluated.
> - **> 60 regions** → **Rule 1 cannot choose X**; the outcome is
>   `INSUFFICIENT_COMPARATIVE_EVIDENCE`. A 60-region sample may be adjudicated for
>   **descriptive diagnosis only**.

§5.8's 120-region subsampling clause is **superseded** for operative D-frame behaviour.
**Rule 1 must never run on a 60- or a 120-region sample.** A10's principle is unchanged —
a raw count is valid on a census and not on a sample — but its unit is now stated: A10 spoke
of "items", §5.5.1 of 60 items, and §5.8 of 120 regions; the operative item is the
**region**.

### A27.4 — Rule 0 (M9) needs its own outcomes

The three-outcome enum could not express a decision made *before* Rule 1. Added:

| outcome | when |
|---|---|
| `EXTENDED_BY_RULE_0_M9` | H has an asymmetric M9 loss, X has none |
| `HYBRID_BY_RULE_0_M9` | X has an asymmetric M9 loss, H has none |

If **each** architecture has at least one asymmetric M9 loss, on different documents, then
**both have been rejected by the frozen Rule 0**. No comparison by number or severity of
losses is invented: the outcome is `INSUFFICIENT_COMPARATIVE_EVIDENCE`. A document **both**
lose stays neutral for RQ1 and a failure for RQ2, exactly as §7.2 rule 0 already freezes.

### A27.5 — the §8 statistical contract has an executable owner

`score_metrics.py` (or an explicitly named downstream output) must implement §8 in full:

- the per-document event **"this document has ≥ 1 heading-level H/X discordance"**;
- the **exact one-sided 95 % Clopper–Pearson upper bound** on that **document-level** rate;
- the **zero-event closed form** `1 − 0.05^(1/N)`;
- **no bootstrap at zero events** (§8.1 measured it degenerate: every resample is 0.0);
- **bootstrap only** when the event count is non-zero;
- per-document paired differences, **unweighted mean over documents**, with the
  **mandatory per-document detail**;
- the frozen descriptive wording, and the prohibition on converting any of it into a
  **per-heading probability**.

Required control: a test that **fails** if the implementation treats headings as independent
observations — e.g. asserting the bound computed on `N` documents does not equal the bound
computed on `H` headings whenever `H != N`. §8.1's own measurement (0.1926 vs 0.00498, a 39×
ratio) is the fixture.

### A27.6 — Rule 3's gate vector is explicit and inspectable

`decide_architecture` receives a named status for every decision-blocking condition still
operative: **R1, N-A, N-B, N-C, S1, confirmatory X2-a, confirmatory X2-b, M9 evaluability,
§4.5 adequacy.** Any failure → `INSUFFICIENT_COMPARATIVE_EVIDENCE`.

**Cross-engine (x09) failure is a reporting qualification, not a decision blocker** — it
labels results `PDFIUM-CONDITIONED FRAME` and never changes the outcome.

**G2 is not the confirmatory X2 run.** G2 proves on DEVELOPMENT that the verifier and its
denominator machinery exist and are falsifiable. The study still requires **X2-a and X2-b on
every confirmatory holdout document** before scoring. That execution-time path is planned and
**not run** in this pass.

### A27.7 — all randomization is frozen, deterministically and by domain

Every remaining "seeded" phrase named no seed and no procedure. Frozen:

> **Selection seed `20260807`, applied as a domain-separated deterministic ranking:** for
> purpose `P`, rank candidates ascending by `sha256(f"{P}|20260807|{stable_item_id}")` and
> take the first *k*. No RNG object, no input-order dependence, no post-hoc seed.

| purpose | namespace `P` | stable item id |
|---|---|---|
| C-frame region selection | `cframe-select` | `(document_sha256, page_number, region_ordinal)` |
| D-frame descriptive sample | `dframe-descriptive` | same |
| C-frame 25-item human audit | `cframe-audit` | stimulus blind id |
| R1 10 % repeat selection | `r1-repeat` | stimulus blind id |
| blind presentation order | `blind-order` | stimulus blind id |

Population selection keeps its own already-executed seeds — **20260807** for the stratum
permutation and **20260808** for the confirmatory draw — which are historical facts at
`4e2b520` and are not re-run. **Requirement: the same inputs at the same commit select
exactly the same items in exactly the same order.**

### A27.8 — §4.5 adequacy: the gap is recorded, the ruling is NOT taken here

> **Bookkeeping correction.** A27's `supersedes_text_in` originally listed
> `PRE-REGISTRATION.md 4.5`, which contradicted this very subsection: A27 recorded the §4.5
> gap and explicitly declined to rule it. §4.5 is removed from A27's supersession list and is
> superseded by **A28**, which is where the ruling was actually made. A27 is not rewritten to
> imply otherwise.

§4.5 says "≥ 800 **emitted** heading occurrences" without saying **whose** count when H and X
differ, and its rows are not exhaustive. **Both are outcome-affecting and neither is decided
in this amendment** — see the analysis returned with A26/A27, which sets out the competing
interpretations, what each changes, and a recommendation. `decide_architecture` may not be
built until §4.5 is ruled.

**Population impact: none.** Post-selection, pre-execution. No membership change, no scoring,
no holdout document opened, no harness component built.

---

## A28 — SUBSTANTIVE. §4.5 adequacy frozen; stimulus identity and renderer scale

```json
{"id": "A28", "class": "SUBSTANTIVE",
 "commits": ["0cf7daf"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["HARNESS-PLAN.md", "probes/methodology_contracts.py",
                   "probes/x15_methodology_contracts.py", "probes/x14_anchor_bridge.py",
                   "probes/run_hybrid.py"],
 "supersedes_text_in": "PRE-REGISTRATION.md 4.5, 5.4 (render scale), 5.6 (R1 scale); PRE-EXECUTION-AMENDMENTS.md A27.7 (blind-id ranking)",
 "status": "FROZEN"}
```

Closes the last outcome-affecting ambiguity (§4.5) and two determinism holes A27 left.
**No harness component is built.** Tested in `x15_methodology_contracts.py`, 19/19.

### A28.1 — the adequacy occurrence count

> **`adequacy_occurrences = |H_keys ∪ X_keys|`**, where each key is the unique **A27.1
> source-position occurrence key** `(document_sha256, page_number, start_neutral_line_key,
> occurrence_ordinal_on_that_line)`.

- only **P-head** documents contribute;
- only the kinds **`account`, `agency`, `grouping`** contribute;
- one physical occurrence emitted by **both** arms counts **once**;
- an occurrence emitted by **one** arm counts **once**;
- **no text similarity** enters identity; **no oracle result** enters the count.

**Why the union.** §4.5 asks an **adequacy** question — does the holdout *contain* enough
heading structure to generalise from — not an accuracy question. Structure either arm
demonstrates is structure the documents possess. The union is symmetric, so **an arm's own
failure can never shrink the denominator and void the study**, which is the hazard §7.2 rule
0 already forbids ("no frozen document may be removed from the denominator by its own
result"). It is capped only by a **shared** miss, which is honest.

**Why only three kinds.** The frozen design pilot's "heading occurrences emitted" quantity
used exactly `account` / `agency` / `grouping`. The later oracle codebook is broader, and
widening the adequacy denominator to title/division/section would make the holdout look more
adequate than the frozen quantity it is compared against.

### A28.2 — the §4.5 state machine

Ordered and exhaustive. **No threshold is changed.**

```python
if strata_filled < 5 or adequacy_occurrences < 300:
    adequacy = "INADEQUATE"
elif strata_filled >= 7 and adequacy_occurrences >= 800:
    adequacy = "GENERALISABLE"
else:
    adequacy = "LIMITED"
```

| state | consequence |
|---|---|
| `INADEQUATE` | **Rule 3 fails**; RQ2 is not claimed; RQ1 reports a bound only |
| `LIMITED` | Rule 3 does **not** fail; the architecture decision may proceed, but the licensed generalisation is only *"extends to the classes actually sampled"*, with unfilled strata named in the headline |
| `GENERALISABLE` | Rule 3 does not fail and the broader appropriations-document generalisation is licensed |

The frozen table was neither exhaustive nor disjoint: `≥ 7` strata with **300–799**
occurrences matched **no** row, and `5–6` strata with `< 300` matched **two** with no
precedence. Evaluating the failure condition first makes the space total and resolves the
overlap conservatively. **MEASURED**: 10 branch cases plus a 54-point sweep, no pair
unclassified, all three states reachable.

### A28.3 — canonical PRE-BLINDING stimulus identity

A27.7 ranked three purposes by *stimulus blind id* while the blind-id scheme was still an
implementation choice — so changing that scheme could have changed the audit sample, the R1
sample or the presentation order. **Sampling may not depend on blind ids.**

```
base region      ("region", document_sha256, page_number, region_ordinal)
control          ("control", control_kind, source_fixture_sha256, page_number,
                  region_ordinal, control_variant)
R1 repeat        ("r1-repeat", base_stimulus_identity)
```

Serialization is canonical (`json.dumps`, `sort_keys`, no whitespace, tuples and lists
normalised to one form) and tested. Then:

- **`cframe-audit`** ranks canonical **base** identities;
- **`r1-repeat`** ranks canonical **base** identities;
- **`blind-order`** ranks canonical **final instance** identities;
- **no ranking consumes an opaque blind id.**

The blind id is derived **only after all selection is settled**, as a domain-separated hash
of the canonical final identity. **It is an adjudicator-facing alias and never determines
membership, repeat selection, audit selection or order.** *Negative control:* replacing the
blind-id scheme wholesale, with canonical identities held fixed, changes **no** selected item
and **no** presentation rank — and the alias itself is asserted to have changed, so the
control is not vacuous.

### A28.4 — renderer scale, frozen

| stimulus | scale |
|---|---|
| primary C-frame / D-frame / control | **exactly 300 DPI** |
| R1 reliability repeat | **exactly 330 DPI** |

Render DPI is **not** an implementation choice. §5.6 requires the R1 duplicate at "a
different but visually equivalent scale"; **330 = 300 × 1.10**, a mechanical pre-execution
choice made **higher** rather than lower so the reliability repeat is never *less* legible
than the original. The repeat uses the **same PDF bbox and same source region** — only the
raster scale differs.

Controls must fail if a primary stimulus is not 300 DPI, an R1 repeat is not 330 DPI, the
repeat's bbox or source identity differs from its primary, or a renderer rescales either
artifact afterwards.

### A28.5 — the anchor bridge is proven BILATERALLY

`x14` now runs the **same** rule on both arms over the same material — H **11/11** and
**16/16**, X **11/11** and **16/16** anchors placed uniquely, zero unplaceable, and both arms
asserted to bridge onto the **same** neutral skeleton. `print_lines` ↔ `emitted`
index-for-index equality is checked on **every** consumed page, not one example. Five
negative controls prove the bridge **refuses rather than guesses**. **No arm has a private
matching rule and there is no fallback.**

`run_hybrid.run()` gained an **additive** `page` key (the production `Page` from the frozen
reconstructor) so H can reach `print_lines` and anchors. Every pre-existing key is unchanged.

**Population impact: none.** Post-selection, pre-execution. No membership change, no scoring,
no holdout document opened, no harness component built.

---

## A29 — WITHDRAWN. Bootstrap reproducibility, recorded and reverted unexecuted

```json
{"id": "A29", "class": "SUBSTANTIVE",
 "commits": ["134a115", "18ef71d"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["HARNESS-PLAN.md", "probes/methodology_contracts.py",
                   "probes/x15_methodology_contracts.py"],
 "supersedes_text_in": "none -- withdrawn before it superseded anything",
 "status": "WITHDRAWN -- content reverted; the number is spent and is not reused"}
```

A29 froze the non-zero-event bootstrap procedurally (10,000 resamples, document unit,
hash-derived draws) and restated it as non-gating. It was **reverted before review** for
process reasons, not because a ruling in it was found wrong: the work belongs to the session
that owns this branch's harness contracts, and two sessions writing the same amendment number
is the failure this ledger exists to prevent.

**This record is deliberately not deleted.** `134a115` touched protected files and remains in
history, so F9 requires it to stay declared; and the ledger's job is to record what happened,
including what was undone. Deleting the entry — or rewriting history to remove the commit —
would leave the branch looking as though the episode never occurred, which is the opposite of
the provenance this study relies on. **Freeze integrity is unaffected:** after `18ef71d` the
content is byte-identical to the state before `134a115`.

**One finding from the withdrawn work is recorded here and nowhere else, because it is real
and it would otherwise be lost with the revert:** the non-zero-event bootstrap resampled
differently depending on the order its caller listed documents in, and canonical sorting fixed
it. That is a genuine reproducibility defect in a §8 quantity. It **does not gate
`build_frames.py`** — nothing upstream of `score_metrics` consumes a bootstrap — but it **must
be resolved under a future amendment before `score_metrics.py` is implemented.** A30 does not
carry it, and does not expand into §8.

> **That obligation is DISCHARGED by
> [A37](#a37--substantive-freeze-the-supplementary-non-zero-document-bootstrap).** A29's status
> is unchanged — it remains **WITHDRAWN**, and A37 adopts the valid finding forward under a
> fresh number rather than resurrecting this one. **A29 was not wrong.**

---

## A30 — SUBSTANTIVE. The occurrence identity is an absolute source position

```json
{"id": "A30", "class": "SUBSTANTIVE",
 "commits": ["23af18e", "e64913d"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["HARNESS-PLAN.md", "probes/anchor_provenance.py",
                   "probes/x16_occurrence_identity.py",
                   "probes/methodology_contracts.py",
                   "probes/x15_methodology_contracts.py"],
 "supersedes_text_in": "A27.1 (the matching key's fourth component)",
 "status": "FROZEN -- approved by external review; isolated branch pending integration into PR #560"}
```

A27.1 froze the M1–M4 matching key as a source position and named its fourth component
`occurrence_ordinal_on_that_line`. That component was **never derived**. `Anchor` carries
`page_number, line_number, kind, text, division` and no within-line position, and the `x14`
bridge terminates at `(region_ordinal, neutral_line_key)`. `x15`'s "two occurrences on one
neutral line stay distinct" control supplied the ordinals to itself, so it proved the
representation could *hold* two values, not that production could *derive* the right ones.

### A30.1 — the fourth component becomes `start_ngid`

```
(document_sha256, page_number, start_neutral_line_key, start_ngid)
```

`start_ngid` is the A24.2 neutral ink identity of the **first neutral-ink source character of
the recognized occurrence**.

**Why an ordinal could not survive.** `pdf_anchors._anchors_from_page` emits a `section` and an
inline `subsection` at the **same `(page, line_number)`** — the production comment calls this a
deliberate physical collision and says the ordering is load-bearing. An ordinal among the
anchors *an arm emitted* renumbers the later occurrence whenever the earlier one is missing:

```
H: A, B   ->  B is ordinal 1
X:    B   ->  B is ordinal 0        the same physical occurrence, two keys
```

`start_ngid` cannot do that: it names a physical mark, and A24.2 makes that the one identity
both arms give the same number. A U+0020 carries no `ngid`, so the arms may disagree about
spacing freely without moving it.

**Frozen:** `key_H(B) == key_X(B)` must hold in **both** the A+B / B-only and the B-only /
A+B adversarial cases.

**`ngid` is an identity, not a reading-order key.** It is used only for equality; nothing
orders occurrences by it. Measured on DEVELOPMENT material, ngid order agrees with printed
order on **33,592 of 33,602** emitted lines, the residue being single adjacent transpositions
in PDFium's text-page order. Ordering by `ngid` would inherit that residue for no benefit.

### A30.2 — the provenance derivation, and the fidelity contract

```
recognized Anchor occurrence
  -> merged-line occurrence start offset
  -> Page.merge_ranges
  -> originating print line + offset
  -> emitted[print_line].cells
  -> first neutral-ink Cell at/after the occurrence start
  -> Cell.ngid
  -> owning NeutralLine
```

The offsets are coordinates in **the arm's own emitted text** and legitimately differ between
H and X. They are inputs to the derivation, never the identity: only the resolved `start_ngid`
is compared across arms.

**Instrumented study-locally, not by changing production.** Production `Anchor` gains no
study-only field and **no recognition behaviour changes**. `anchor_provenance` transcribes
only the small per-page pass, which is the one that needs an exact within-line match position;
the size path is **called, not copied**, and its occurrences are located positionally (an
account/grouping/agency/major anchor is emitted from `line.text.strip()`, so its first ink
character is its line's first non-space).

**The fidelity assertion is the whole warrant for the copy:**
`strip_to_production(instrumented) == extract_anchors(pages)` — order, page, line, kind, text
and division, **element for element, on every DEVELOPMENT page consumed**. When confirmatory
execution is authorized, that assertion **must also cover every consumed confirmatory page**.
Drift fails the probe; it is never reported as a rate.

**Every failure returns `UNMATCHED` with an explicit reason. Nothing guesses:**
`PAGE_HAS_NO_PRINT_LINE_PROVENANCE`, `PRINT_LINE_INDEX_UNRESOLVED`,
`MERGE_RECONSTRUCTION_MISMATCH`, `OFFSET_PAST_END_OF_LINE`,
`CELLS_NOT_ALIGNED_WITH_PRINT_TEXT`, `NO_NEUTRAL_INK_AT_OR_AFTER_START`,
`START_NGID_NOT_OWNED_BY_NEUTRAL_LINE`, `NO_NEUTRAL_INK_ON_LINE`,
`AMBIGUOUS_SOURCE_POSITION`.

**No text similarity, anchor-kind matching, or emitted-occurrence ordinal appears anywhere in
the cross-arm identity join.**

### A30.3 — the oracle's occurrence position is geometric

For every adjudicated heading occurrence the oracle records **`start_physical_line`** and
**`start_x_px`** — the integer horizontal coordinate of the **left edge of the first printed
character** of that occurrence in the rendered stimulus. This is an **identity annotation
only**: heading text, role and immediate parent remain independently adjudicated exactly as
before.

`build_oracle` converts it deterministically to page PDF coordinates from the **committed
region bbox**, the **rendered image width** and the **frozen DPI**. No architecture output
participates. For the reported physical neutral line:

1. project every neutral ink glyph's physical `x0` into the same coordinate system;
2. choose the glyph whose `x0` is at **minimum absolute distance** from the adjudicated start;
3. **no candidate → refuse**;
4. **exact tie → refuse**;
5. the selected glyph's `ngid` is the oracle occurrence's `start_ngid`.

**No distance tolerance is introduced.** A tolerance would silently accept a wrong glyph and
there is no principled width to choose. A tie is not broken by `ngid`, kind, occurrence order,
or text — each is a rejected shortcut, and a tie means the stimulus genuinely does not
determine the answer.

**The neutral skeleton supplies IDENTITY only.** It never supplies heading truth.

**Qualification inheritance.** This occurrence-position join reads the neutral skeleton, so it
inherits the already-frozen **`PDFIUM-CONDITIONED FRAME`** qualification when the cross-engine
neutral-frame control fails. It does **not** change the oracle's heading text/role/parent truth
source.

**R1.** The 330-DPI repeat records its **own** `start_x_px` and is resolved to `start_ngid`
**independently**; the repeat may not reuse the primary's coordinate or its resolved identity.
`R1_start_identity_agreement` is reported for repeated items. **A30 adds no
architecture-selection threshold from this field** — it is a reliability observation and
control, and the existing oracle reliability rules are otherwise unchanged.

### A30.4 — the P-head adequacy restriction becomes executable

`methodology_contracts.filter_keys()` filtered on **kind alone** and made the P-head
restriction an obligation on callers. A caller obligation is not a gate: it cannot fail, and a
P-robust document silently inflating the adequacy count would simply have produced a larger
number — and larger reads as *more* adequate.

Its input is now `(key, kind, population)`, retained only when
`population == "P-head" and kind in {account, agency, grouping}`.

**Negative control:** adding arbitrarily many P-robust account/agency/grouping keys must leave
`adequacy_occurrences` **unchanged**. All existing A28 adequacy controls are retained. **The
§4.5 ruling itself is unchanged** — this makes the frozen clause falsifiable.

### A30.5 — blind IDs must be unique over the REALIZED stimulus set

> Before any oracle artifact is committed or adjudication begins, blind IDs must be unique
> across the **complete realized** stimulus set.

Artifact construction **aborts** on a collision. **No overwrite, merge, last-write-wins, or
automatic salt/re-roll is permitted** — salting after seeing the stimulus set would let the set
choose the alias scheme, which is exactly the influence A28.3 removed when it stopped blind ids
from steering sampling. A collision is a **deterministic build failure requiring review**.

x15's prior uniqueness check was a property of a handful of constructed identities, not a proof
about the set the study will build. A **synthetic collision injection** now proves the check can
fail.

**Population impact: none.** Post-selection, pre-execution. No membership change, no scoring, no
holdout document opened, and no downstream harness component built — `build_frames`,
`build_oracle`, `score_metrics`, `decide_architecture` and `adjudicator_prompt.md` are all
untouched.

---

## A31 — SUBSTANTIVE. `build_frames` implements the already-frozen frame rules

```json
{"id": "A31", "class": "SUBSTANTIVE",
 "commits": ["d316dfb", "97a1deb", "2c64132", "b27ecb3", "d7fb105"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["HARNESS-PLAN.md", "probes/build_frames.py", "probes/x17_build_frames.py"],
 "supersedes_text_in": "none -- it implements A19/A22/A23/A27 exactly as already frozen",
 "status": "FROZEN -- approved by external review; isolated branch pending integration into PR #560"}
```

**Why SUBSTANTIVE, and why `affects_scoring_rule` is nevertheless `false`.** These are two
different questions and the ledger keeps them apart deliberately.

`build_frames` decides **frame membership**, and frame membership decides which regions are
ever adjudicated and which lines ever enter a denominator. A wrong implementation therefore
**can move a realized score** — which is exactly why it may not be filed as TOOLING, whose
contract is that the code cannot. (F9 enforces this mechanically: a TOOLING amendment
carrying `affects_scoring_rule: true` is rejected, and a file may not be declared under both
a TOOLING and a SUBSTANTIVE amendment.)

But **A31 introduces no new methodological rule.** Region size, alignment, page-bounding, the
trailing-window rule, the C-frame draw and its seed, the three D-frame predicates and the
comparative risk set were all frozen by A19/A22/A23/A27 before this component existed. A31
writes them down executably; it does not decide anything they left open. Hence
`affects_scoring_rule: false` — there is no scoring *rule* here that a reviewer must
re-approve, only an implementation of rules already approved.

Fidelity therefore comes from two places, neither of which is this component's own opinion:
the frozen contracts it calls (`neutral_identity`, `methodology_contracts`, the A28.5 bridge),
and the executable positive **and negative** controls in `x17_build_frames.py`.

### What was implemented

Invariants **I1–I5** exactly, plus A19's trailing rule stated explicitly: a final page
fragment of 1–7 neutral lines is **retained as one short trailing region**. Dropping it would
make the last lines of every page unsamplable — a coverage hole aligned with page structure,
not a rounding detail.

**The D-frame is a COMPLETE census.** The A10/A27.3 60-region budget is **not** applied here
and no sampling or truncation occurs; a synthetic 61-region census is emitted in full. The
budget belongs to `decide_architecture`, and applying it early would destroy the very count
that decides whether Rule 1 may be evaluated at all.

**Anchor equality uses the whole emitted production `Anchor` value** — page, line, kind, text
and division. `Anchor` is a frozen dataclass, so set comparison already decides on the entire
value and **no reduced signature was invented for frames**. This was the one place the plan
warned an implementer might silently choose a projection; no choice was required.

**No new instrumentation was added to either runner.** Each arm's production anchors are
derived by calling `extract_anchors` on the `Page` that arm already returns, exactly as `x14`
does, and `x17` asserts `build_frames`' placement reproduces `x14`'s anchor for anchor on
every development page.

### Controls

Twelve required controls plus the later repair and API-split controls, **56/56 passing**. The
four D-frame predicates are
established by **injected faults** (a one-arm text change, a one-arm merge, an anchor-set
difference, and a jointly-dropped body line), each paired with an un-injected baseline that
must be clean — a control that only reads back a boolean the code just computed cannot tell a
working rule from one that never fires.

### Repair, after review of the first implementation

Three defects were found in review and corrected in place under A31. None changes a
methodological rule; all three were the implementation failing to honour rules already frozen.

**1. Anchor extraction is DOCUMENT-SCOPED, exactly as production and `x14` do it.** The first
implementation called `extract_anchors([page])` once per page. `extract_anchors` is
document-scoped by construction — `derive_size_bands` and `_coverage` are computed over the
supplied collection, the account/agency/major passes run over the **flattened** pages, and
`_assign_divisions` needs document order. Per-page calls therefore re-derive the size bands
from a single page's glyphs, cut every cross-page agency/major run at the page seam, and lose
division context. The census is now extracted **once per arm over the whole consumed page
set**, in page order, and only then grouped by page for placement.

This is not a theoretical difference. A constructed two-page collection where page 2 carries
an account heading but no body-size prose yields **one `account` anchor** under document scope
and **none** under per-page extraction, because page 2 alone has no derivable size band. The
control asserts the two procedures disagree, so it cannot pass by coincidence.

**2. An anchor-placement refusal ABORTS frame construction.** It is not an absent anchor, not
`ANCHOR_DISCORDANCE`, not a regional indeterminate, and not
`INSUFFICIENT_COMPARATIVE_EVIDENCE`. Dropping a refused anchor and comparing the surviving
sets silently converts *"the frozen bridge cannot name this document's anchor census"* into
*"the arms emitted different anchors"* — a harness artifact wearing the costume of an
observation. `x14`'s contract already said any non-zero placement residue makes anchor
discordance non-executable as frozen; `build_frames` now enforces it, raising
`FrameConstructionError` carrying arm, page, the `Anchor` value and the refusal reason.

**3. Every structural precondition fails closed inside `build_frames`.** Previously the page
sets were intersected and skeleton skew was *returned* for a caller to notice. **A caller
obligation is not a gate: it cannot fail.** Now `PAGE_SET_MISMATCH`,
`NEUTRAL_SKELETON_MISMATCH` and `PRINT_LINES_EMITTED_DRIFT` each abort, the last checked for
**both arms on every consumed page before any anchor index is used** — because the bridge
reads `emitted[i]` for the i-th print line, and drifted lists would place every anchor on the
page onto the wrong neutral line. HARNESS-PLAN's claim that the anti-drift gate runs over
every harness-consumed page is now literally true.

`PageInput` deliberately has **no refusal field**, so a refusal is not representable in a
frame and no later code can ignore one. **No caller obligation can silently produce a reduced
frame.**

A further silent-reduction path was closed by auditing for the same defect class: an
**unrecognised population string** read as "not P-head" and drew **zero** C-frame regions while
still producing a valid-looking frame. The population set is now closed and validated
(`UNKNOWN_POPULATION`).

### The public entrypoint is fail-closed; the pure constructor is a private testing seam

An earlier cut recorded that `build_document_frame` accepted hand-constructed `PageInput`
objects and therefore bypassed the structural gates, and treated that as an acceptable seam
because "every real path goes through `page_inputs_from_arms`". **That is a caller obligation,
and a caller obligation is not a gate.** It also had a concrete exploit: both halves took a
`region_size`, so a caller could place anchors on a **7**-line grid and then build an **8**-line
grid. The frame looked entirely valid, the region-size guard compared its own default against
itself and passed, and the anchor evidence was silently assigned against a different partition
than the one reported.

The API is now split:

```
PUBLIC / REAL     build_document_frame(sha, id, population, h_pages, x_pages)
                    -> duplicate page numbers -> page-set equality -> A28.5 anti-drift
                    -> one-skeleton equality -> document-scope extraction -> exact placement
                    -> pure constructor -> frame

PRIVATE / SYNTHETIC  _build_document_frame_from_inputs(sha, id, population, [PageInput, ...])
```

The public entrypoint takes **runner outputs, not `PageInput`s**, so there is no argument
through which validation can be skipped. **No result-bearing signature accepts a region size**
— not the entrypoint, not `_page_inputs_from_arms`, not the constructor — so the 7-vs-8 defect
is not rejected, it is **unspellable**. A19's 8 is a module constant on every path that can
return a study frame. `enumerate_regions` keeps its argument for isolated testing only, and no
result-bearing route passes anything but the frozen value.

**Page numbers must also be unique within each arm** (`DUPLICATE_PAGE_NUMBER`), checked before
set equality — which cannot see a duplicate, since `H=[1,1,2]` and `X=[1,2]` have equal sets
and the later page map would silently collapse it. A physical PDF page has one identity, so
duplicate runner records make the document frame ill-defined. This completes the page-set
invariant rather than adding a new rule.

Each repair carries injected negative controls: page-set mismatch in both directions, a
one-glyph skeleton difference, an emitted-line deletion, a same-length text drift, and an
unplaceable anchor in **each** arm via a different refusal class — each also asserting the
refusal is **not** reported as `ANCHOR_DISCORDANCE` — plus a clean case that must **not**
abort, so the aborts prove something.

**Population impact: none.** Post-selection, pre-execution. No membership change, no scoring,
no holdout document opened, no canonical `results/frames.json` created, and no oracle, prompt,
metrics or decision code written.

---

## A32 — SUBSTANTIVE. Is A30.3's geometric occurrence position practically discriminable?

```json
{"id": "A32", "class": "SUBSTANTIVE",
 "commits": ["b78a9df", "77a7b95"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/x18_start_x_discriminability.py",
                   "probes/x19_raster_edge_diagnostic.py"],
 "supersedes_text_in": "none -- A32 does NOT supersede A30.3",
 "status": "FROZEN -- reviewed; A30.3 stands unchanged"}
```

**This block is committed BEFORE the measurement runs.** Every quantity below is defined here
so that none of them can be chosen after seeing a DEVELOPMENT number. A32 is a *measurement*,
not a ruling: it states no pass criterion and changes no rule. Its result may show that A30.3
needs a future reviewed amendment; that decision is the reviewer's, not this amendment's.

It is filed SUBSTANTIVE rather than TOOLING because it is a pre-execution feasibility
measurement of an **outcome-affecting oracle-identity interface** — F9 rejects TOOLING that
touches a scoring rule, and hiding a study of the oracle join under TOOLING would misstate what
it is. It changes no rule itself, hence `affects_scoring_rule: false`.

### The question

A30.3 freezes: the adjudicator reports `start_physical_line` and an integer `start_x_px`; the
resolver takes the **nearest** neutral-ink glyph `x0` on that physical line, with **no
tolerance**, an exact tie → `UNMATCHED`, and no candidate → `UNMATCHED`.

> Are real neutral-glyph starts separated enough, in pixel coordinates, for that nearest-x
> operation to be practically discriminable at the frozen **300 DPI** primary and **330 DPI**
> R1 scales?

The load-bearing quantity is **distance to the nearest competing `x0`** — not average character
spacing, which would answer a different and easier question.

### Why the result is independent of the unfrozen crop rule

The headline quantities are **invariant to horizontal crop translation**. A translation adds the
same constant to every candidate and to the target, so it moves no nearest-neighbour spacing and
no nearest-x decision boundary. Scaling by DPI is likewise uniform. The study therefore does not
need — and **must not invent** — a padding or crop-origin value. Any quantity found to require
one is separated as a diagnostic or dropped, never silently parameterised.

### Populations, measured and reported separately

| | |
|---|---|
| **G** stress census | every eligible neutral-ink glyph on every consumed DEVELOPMENT page, each treated *as if* it could be an occurrence start. Not a claim that every glyph is a heading start; it asks whether the mechanism can separate arbitrary physical marks, including narrow punctuation |
| **H** task-relevant | every DEVELOPMENT heading occurrence whose A30 provenance path yields a valid `start_ngid`. Starts come from the A30 mechanism, never rediscovered from heading text. Heading kind is retained only as a descriptive stratum **after** identity is known, and never participates in the resolver |
| **C** collisions | every occurrence in a same-physical-line multi-anchor collision, including the known `section` + inline `subsection` cases — the adversarial population that forced A30 |

Frequency may not be used to retire the invariant.

### Geometry, per target

For a target `ngid` on its neutral line: collect every **distinct** neutral-ink glyph on that
same line, use each candidate's physical PDF `x0`, and find the nearest candidate strictly left
and strictly right by x.

```
left_gap_pt  = x - nearest_left_x          (+INF if no left neighbour)
right_gap_pt = nearest_right_x - x         (+INF if no right neighbour)
left_margin_pt  = left_gap_pt  / 2         the nearest-x decision boundary
right_margin_pt = right_gap_pt / 2
margin_px = margin_pt * DPI / 72           DPI in {300, 330}; NO rounding
m = min(left_margin_px, right_margin_px)
```

Nothing here is derived from architecture output.

### Exact-x collisions

Distinct `ngid`s on one neutral line with **exactly equal** `x0` are recorded separately and
excluded from the margin distribution, where `m` would be meaningless. For each, report
document, page, neutral line, the `ngid`s, glyph geometry, whether any member is an A30 heading
start, and whether any belongs to a same-line anchor collision. Codepoints appear only as a
diagnostic **after** the geometry case is identified.

**An exact-x collision involving a task-relevant heading start is a HARD finding**: A30.3 cannot
uniquely identify that occurrence from `start_physical_line` + x alone. No tie is broken by
`ngid`, text, kind, emitted order or y position.

### Integer-annotation robustness, with no invented threshold

No "human error tolerance" is chosen, and no post-hoc pass threshold is set. For each scale:

```
guaranteed_integer_error_px = the largest integer k >= 0 with  k + 0.5 < m
```

Read as: *whatever the subpixel phase between the PDF `x0` and the integer pixel grid, an
integer annotation displaced by at most ±k px from the nearest integer representation of the
true start stays strictly inside the target's nearest-x cell.* When `m <= 0.5` no `k >= 0`
qualifies; that is reported as **`none`**, never rounded up to 0.

Reported per population, per scale: N targets, N exact-x ambiguous, N with no competitor on
their line (infinite margin, reported separately so they cannot inflate the good tail),
min / p01 / p05 / median / p95 of `m`, min / p01 / p05 / median of `k`, and counts for
`k = none, 0, 1, 2, 3, 4, 5, 6, 7, 8+`.

**Per-document minima are reported separately and unweighted**, so one easy bill cannot hide one
difficult document.

### Resolver simulation

The frozen nearest-x resolver is exercised as a pure function. Ten controls, each injecting
**both sides** of the relevant boundary: clean isolated target; an x crossing the midpoint
resolving to the neighbour; exact midpoint → `UNMATCHED`; duplicate candidate x → `UNMATCHED`
when nearest; absent physical line → `UNMATCHED`; line with no neutral ink → `UNMATCHED`;
changing heading text changes nothing; changing anchor kind changes nothing; an H/X spacing
disagreement before the occurrence changes nothing; and same-line `section` + `subsection`
starts remain separately resolvable where geometry permits. A translation-invariance control
asserts the crop origin cannot change any resolution.

### MuPDF raster diagnostic, and its stated limit

PRE-REGISTRATION §5 renders adjudication stimuli with **MuPDF (`pymupdf`)**; that is the
oracle's renderer and is unrelated to the pypdfium2 extraction engine frozen by ADR 0002.
`pymupdf` is **not installed in the project venv**, and it is not added there: the venv is
shared across worktrees and PyMuPDF is a deliberately rejected extractor, so the diagnostic runs
in an **isolated throwaway environment** and touches no project dependency.

Its purpose is narrow: *does the rendered raster reveal a systematic reason that "left edge of
the first printed character" would be materially displaced from the neutral glyph's geometric
`x0`?* No OCR step is invented. No pixel-intensity threshold is invented and then treated as
truth. **If a faithful glyph-specific visible-edge measurement cannot be made without inventing
a threshold or a segmentation heuristic, that sub-measurement STOPS** and returns worst-case
rendered crops for human inspection instead. Inability to automate the visual-edge measurement
may not be allowed to corrupt the exact geometry census, which stands on its own.

### Hard stop conditions

Measurement STOPS and returns immediately if population **H** or **C** shows: distinct
task-relevant candidates at exactly equal `x0`; a true target absent from its neutral line's
candidate set; the frozen resolver unable to return the known A30 `start_ngid` even at the exact
geometric start; same-line collision identities collapsing under the resolver; or a case
requiring text/kind/order to disambiguate. A30.3 is **not** patched in the same pass. A finding
confined to the all-glyph stress census **G** is flagged separately and not generalised to
heading starts.

### Reviewed: A30.3 stands unchanged, and one denominator correction

External review **approved A32 and left A30.3 unchanged** — `start_ngid`, nearest-x, the
no-tolerance rule and the tie/refusal semantics are not reopened.

One bookkeeping defect was found and corrected under this amendment (no new number). `x19`
asserted `measured=True` on a row **before** the per-scale `measure()` calls ran, so the
struck-through target — which `measure()` correctly returned as
`NON_GLYPH_VECTOR_INK_IN_BAND` — still counted in the denominator: the summary read
`n_measured = 16` where only **15** targets had a valid raster-edge measurement. It now reports
`n_attempted = 16`, `n_cleanly_measured = 15`, `n_excluded_non_glyph_vector_ink = 1`, with the
flag derived from the results rather than asserted ahead of them.

**The correction changed no geometry result and no review ruling.** The offset arrays were never
contaminated, because the excluded row carries no `visible_edge_offset_px` at either scale —
which a new negative control now *proves* rather than assumes, alongside controls that a
vector-ink exclusion cannot enter the measured denominator and that
`cleanly_measured + excluded == attempted`. `x18` was not touched.

### `ORACLE_CROP_OPERATIONALIZATION_REMAINS_OPEN`

Asked explicitly, and answered from the frozen text rather than manufactured. **The eventual
region bbox / crop operationalization is NOT uniquely determined.** What is frozen:

| where | text |
|---|---|
| §5.3 | "The unit is a printed-page REGION: a bounding box in PDF points spanning 6–10 printed lines" (A19 makes it 8 neutral lines) |
| §5.7 | the record carries "bbox in PDF points, renderer name and version, DPI, and the SHA-256 of the rendered PNG" |
| A22 I2 | "Oracle rendering uses the region bbox in PDF points. No arm's text may reach the renderer" |
| A24.2 | a neutral line's x-extent "feeds region geometry and the oracle's rendered bbox" |
| A28.4 | 300 / 330 DPI, "the same PDF bbox and same source region" |

Each of these says the bbox **is used**, **is recorded**, and **depends on** the skeleton. None
states **how it is computed** from the region's 8 neutral lines: whether the horizontal extent
is the union of line ink extents, the full page width, or the justified column; whether any
padding is added, horizontally or vertically, to admit ascenders and descenders the neutral
line box excludes; and what pixel-origin convention maps `bbox_x0` to column 0. The
HARNESS-PLAN control "a rendered crop omits a neutral line the region claims" constrains the
bbox to *cover* its lines but does not determine its extents.

**This does not weaken the A32 result**, whose quantities are translation-invariant by
construction, and the A30.3 inversion is exact for *any* crop provided the committed bbox is
the one rendered. **It does mean `build_oracle.py` remains unauthorized** until the crop rule
is reviewed. It is not resolved here.

**Population impact: none.** Pre-execution, DEVELOPMENT + synthetic only. No membership change,
no scoring, no holdout document opened, no oracle/frame artifact created, and A30.3 unchanged.

---

## A33 — SUBSTANTIVE. Region crop and pixel-coordinate operationalization

```json
{"id": "A33", "class": "SUBSTANTIVE",
 "commits": ["3a07740", "c794b89"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["HARNESS-PLAN.md", "probes/oracle_geometry.py",
                   "probes/x20_oracle_crop_coordinates.py"],
 "supersedes_text_in": "A30.3 PIXEL->PDF CONVERSION CLAUSE ONLY; closes ORACLE_CROP_OPERATIONALIZATION_REMAINS_OPEN (A32)",
 "status": "FROZEN -- reviewed; crop and pixel-coordinate contract approved"}
```

**This block is committed BEFORE `x20` exists.** `affects_scoring_rule` is **true**, unlike A32:
the exact pixels shown to the adjudicator and the pixel→PDF inversion can move an oracle label
and therefore a realized score. It is not TOOLING and is not filed as one.

### A33.1 — the region bbox is the minimal union of committed line bboxes, zero padding

For region `R` whose committed frame carries neutral lines `L`:

```
bbox_x0 = min(L.bbox.x0)      bbox_y0 = min(L.bbox.y0)
bbox_x1 = max(L.bbox.x1)      bbox_y1 = max(L.bbox.y1)
```

**Zero padding.** A `NeutralLine` bbox is already the min/max over every eligible source-glyph
box assigned to that physical line, so padding would add a new free parameter, could expose
neighbouring content outside the frozen region, and would displace the unique least-expansive
rectangle that implements the existing "region bbox from neutral geometry" rule. Short trailing
regions use the identical rule over their 1–7 lines.

**Forbidden:** re-deriving neutral geometry from the PDF; expanding to page width or a text
column; horizontal or vertical padding; and any use of H text, X text, anchor content or
adjudicated content.

**ABORT** if a committed line bbox is missing, non-finite, or non-positive, or if the committed
region cannot be rendered without the renderer clipping part of it. The geometry is **not**
repaired by adding padding.

### A33.2 — the committed frame is authoritative

```
oracle region geometry == deterministic function of frames.json geometry
```

No fresh neutral clustering and no new source-glyph census may determine the realized crop.
**The PDF supplies pixels; the frame supplies which rectangle to render.**

### A33.3 — the pixel↔PDF transform is a measured renderer fact, not a guess

Image column 0 is **not assumed** to correspond exactly to `bbox_x0`. `x20` establishes
empirically, from MuPDF's own returned pixmap metadata, what PDF coordinate column boundary 0
represents, how the right edge is rounded, what width MuPDF returns, and whether the mapping is
exactly derivable from `bbox + DPI`. Synthetic PDFs with known marks are exercised across many
fractional device-pixel phases of `bbox_x0`, at widths that do and do not land on integral pixel
widths, with marks at `bbox_x0`, at known interior coordinates, and near `bbox_x1`, **at 300 and
330 DPI independently**. The R1 repeat uses its own raster transform and its own `start_x_px`.

**The mapping is chosen because the renderer does it, never because it flatters `x18`.**

**Required roundtrip:** `PDF x → render → expected integer start_x_px → frozen inverse → PDF x
estimate → nearest-x resolver` must recover the intended source position across the whole
tested fractional-origin grid, with a **deliberately wrong origin convention** demonstrated to
break it.

**If exact inversion needs renderer state not deterministically derivable from `bbox + image
dimensions + DPI`, `x20` STOPS and reports
`A30_3_RENDER_TRANSFORM_METADATA_INSUFFICIENT`**, naming the missing value. A pixmap origin or
renderer matrix is **not** silently added to the oracle key. If the device rectangle *is*
mechanically derivable, the derivation is encoded and tested rather than a free field added.

### A33.4 — page rotation

The coordinate contract is inspected on **synthetic** pages at **0°, 90°, 180°, 270°**, and a
rotation census is reported for the DEVELOPMENT pages consumed. The rule:

> a rotated page either has a proven deterministic PDF→rendered-image coordinate transform, or
> frame/oracle construction **refuses** it.

No approximate transform is improvised. If exact support is proven synthetically it is recorded;
otherwise a fail-closed `NONZERO_PAGE_ROTATION` rule is **proposed for review**, not adopted
unilaterally. No confirmatory page is inspected to choose this rule.

### A33.5 — what `start_x_px` points at

A30.3's resolver is unchanged. The eventual adjudicator instruction is clarified to:

> `start_x_px` marks the left edge of the **first character's own visible ink**. Ignore a
> strike-through, underline, border, rule or other non-character mark crossing the character.
> Do not use a text-box or bounding-box edge.

This says what the adjudicator points at; it introduces no geometric rule. The `x19`
struck-through case is **retained as the DEVELOPMENT negative-control example** of why the
distinction matters. Struck-through headings are **not** excluded from future adjudication —
that exclusion applied only to `x19`'s automated occupancy measurement.

### Controls (all frozen here, before measurement)

1 bbox is exactly the min/max union of committed line bboxes · 2 input line order cannot change
it · 3 H/X text cannot change it · 4 anchor content cannot change it · 5 no padding is added ·
6 every region line bbox is contained by its region bbox · 7 a neighbouring line outside the
region does not expand the crop · 8 a short trailing region follows the same rule · 9
invalid/non-finite committed geometry aborts · 10 300 and 330 render the SAME PDF bbox · 11
re-render of the same bbox/renderer/DPI reproduces the PNG hash · 12 pixel→PDF→nearest-ngid
roundtrip succeeds across fractional origins · 13 a deliberately wrong pixel-origin convention
makes control 12 FAIL · 14 rotated-page handling is exact or explicitly refusing.

Each states what fact would make it fail, and **no control may compare a helper with itself**.

### DEVELOPMENT diagnostics (not pass thresholds)

Region count, short-trailing count, bbox width/height distribution, invalid-bbox count,
out-of-page bbox count, empty-render count, render-determinism failures, page-rotation census,
pixel-inversion failures. **If the zero-padding union clips committed neutral content, `x20`
STOPS and returns the cases — padding is not tuned after observing them.**

### What A33 supersedes, and what survives untouched

A33 supersedes **exactly one clause of A30.3: the pixel→PDF conversion.** A30.3 said the
coordinate was converted from the "committed region bbox, the rendered image width and the
frozen DPI"; `x20` measured that this describes a linear map across the bbox, which is not what
MuPDF does. **A30.3's occurrence-identity design is NOT superseded.**

The surviving A30.3 rule, in full:

```
adjudicator records start_physical_line + integer start_x_px
  -> convert start_x_px with the A33 transform
  -> choose the NEAREST neutral-ink glyph x0 on that physical line
  -> no candidate  => UNMATCHED
  -> exact tie     => UNMATCHED
  -> no tolerance
  -> the selected ngid IS the occurrence identity
```

The frozen A33 transform:

```
s         = DPI / 72
device_x0 = floor(bbox_x0 * s)
pdf_x     = (device_x0 + start_x_px) / s
```

**`image_width` is not the scale and is not required by the inversion.** It is retained only as
a validation quantity. The historical record is not rewritten: A30.3 did originally carry the
image-width wording, and this amendment corrects it forward rather than pretending otherwise.
`HARNESS-PLAN` I15 and the §7 register row are updated to match, and I16/I17 record the bbox
and rotation rules.

### MEASURED — the renderer's mapping is not the one A30.3 sketched

`x20`, 25/25 controls, **0 stop conditions**. Over 80 synthetic cases spanning ten fractional
origin phases, four widths and both scales:

```
pix.x     == floor(bbox_x0 * DPI/72)                   80/80, every phase, both scales
pix.width == ceil(bbox_x1*s) - floor(bbox_x0*s)
```

**Image column 0 is NOT `bbox_x0`**, and one pixel is exactly `72/DPI` points — never
`(bbox_x1 - bbox_x0) / image_width`, because the integer pixmap is the rounded-**out** bounding
box of the transformed clip. The frozen inversion is therefore

```
pdf_x = (floor(bbox_x0 * DPI/72) + start_x_px) / (DPI/72)
```

needing **only `bbox_x0` and the frozen DPI**. This is **not**
`A30_3_RENDER_TRANSFORM_METADATA_INSUFFICIENT`: no pixmap origin and no renderer matrix is added
to the oracle key, which is the outcome the contract preferred.

The sketched convention is not merely inelegant. On a 40 pt test region it misses by up to
**0.352 pt = 1.468 px at 300 DPI** and failed **11 of 60** arithmetic cases; against `x18`'s
measured H minimum margin of **5.571 px** that is roughly a quarter of the worst-case budget.
Real DEVELOPMENT regions are far wider — median **358 pt**, max **461 pt**.

**Rotation.** A clip in unrotated PDF space renders **no ink at all** on a rotated page, and
`page.rotation_matrix` carries it exactly at all four rotations — yet that is still not
sufficient, and the reason is the point: at 90° and 270° the image's x axis is the PDF **y**
axis, and at 180° it is **mirrored**, so `start_x_px` stops corresponding to a neutral glyph
`x0`. **`NONZERO_PAGE_ROTATION` is PROPOSED fail-closed, for review, not adopted.** Every
DEVELOPMENT page consumed has rotation 0 (36/36), so the refusal costs nothing today.

**DEVELOPMENT diagnostics** (3 documents × 12 pages): 162 regions, 34 short trailing, **0**
invalid bboxes, **0** out-of-page, **0** empty renders, **0** render-determinism failures, **0**
pixel-inversion failures. **Zero committed neutral lines are clipped by the zero-padding union**,
so no padding question arose and none was tuned.

Two fixture defects were found and fixed rather than reported as findings, because either would
have produced a false result: `draw_rect(color=...)` **strokes** with a default ~1 pt pen,
placing ink ~2 px left of the mark and mimicking a broken transform (marks are now fill-only,
and the renderer then matches the forward map with delta **0**); and `expected_image_width`
applied `math.ceil` to a float where `x1*s` is mathematically an integer. The latter carries a
documented float guard and is a **validation helper only** — `pixel_to_pdf_x` does not consume
width, so nothing in the inversion depends on it.

### Completion repairs, reviewed and folded in

**End-to-end recovery**, through the **actual** A30 resolver rather than an arithmetic proxy —
`known x0 → pdf_x_to_pixel → pixel_to_pdf_x → resolve_oracle_start_ngid`:

| | 300 DPI | 330 DPI |
|---|---|---|
| **H** (A30 starts) | **541 / 541** | **541 / 541** |
| **C** (collision starts) | **4 / 4** | **4 / 4** |

A non-vacuity control guards those denominators and earned its place: at the original 12-page
window **C was empty (0/0)** and its recovery claim was vacuous. The window is 95 pages so the
known same-line collisions are actually exercised.

The wrong-transform control now moves the **identity**, not merely the arithmetic: a
deterministic search finds **48** configurations where the linear-across-bbox convention
resolves to a **different ngid**. An earlier grid found none because it placed the competitor at
the far edge, where the drift shrinks.

**Fail-closed additions.** `NON_POSITIVE_LINE_BBOX` — each committed line must be positive-area
in its own right, since a union check alone passes whenever the siblings rescue it. A
consequence is recorded rather than hidden: `NON_POSITIVE_REGION_BBOX` is now **unreachable
through `region_bbox`** and is retained only as a documented backstop, with its control
asserting the reason the code actually returns. `REGION_BBOX_OUTSIDE_PAGE` —
`validate_region_bbox_for_page()` refuses on any side, with **no** clip, intersection, padding
or repair.

**`NONZERO_PAGE_ROTATION` ratified.** `rotation == 0` permitted; anything else **aborts oracle
construction**. It may **never** skip the page, skip the region, drop the stimulus or reduce a
denominator — each would convert an unrepresentable condition into a quietly smaller study,
invisible precisely because the affected pages stop being counted.

**Render denominators are explicit:** all **1164 / 1164** DEVELOPMENT regions rendered, so
"0 empty renders" is 0/1164 and cannot be misread as a sample. 282 short trailing, 0 invalid,
0 out-of-page, 0 determinism failures, 0 width failures, rotation census `{0: 285}`, and no
committed line clipped by the zero-padding union.

**One further renderer fact**, measured while chasing a single width mismatch
(`118-hr-8752` p52 r2: `x1*s = 2025.0004`, predicted 2026, actual 2025): MuPDF rounds a device
rectangle out only once it exceeds an integer by **more than 0.001 px** — `fz_round_rect`'s
epsilon, found by sweeping the overhang rather than assumed, and applied symmetrically. This
mattered beyond the width helper: the same epsilon belongs in `device_origin_px`, where its
absence is a **latent off-by-one** whenever `bbox_x0*s` sits just below an integer — a case no
synthetic phase grid and no development region happened to hit. It is a **renderer constant,
not a tolerance**; the nearest-x resolver never consults it.

`x20`: **37/37, 0 stop conditions.**

**Population impact: none.** Pre-execution, DEVELOPMENT + synthetic only. No membership change,
no scoring, no holdout document opened, no oracle artifact created, and A30.3's resolver, ties
and no-tolerance rule unchanged.

---

## A34 — SUBSTANTIVE. The MuPDF device-rectangle epsilon

```json
{"id": "A34", "class": "SUBSTANTIVE",
 "commits": ["f3fd700", "4767930"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["HARNESS-PLAN.md", "probes/oracle_geometry.py",
                   "probes/x20_oracle_crop_coordinates.py"],
 "supersedes_text_in": "A33 renderer/device-rectangle formula ONLY, wherever the epsilon-free expression is normative",
 "status": "FROZEN -- reviewed; MuPDF device-rectangle epsilon correction approved"}
```

`affects_scoring_rule` is **true**: the constant can move `device_x0` by a whole pixel and so
change the PDF coordinate handed to the nearest-ngid resolver.

### Why this is a correction, not a new decision

The exact renderer mapping was **deliberately an empirical output of A33**, not something A33
asserted a priori. The epsilon was discovered while resolving A33's own DEVELOPMENT width
discrepancy (`118-hr-8752` p52 r2). **No confirmatory output exists**, membership is unchanged,
and A25/A30/A31/A32 conclusions are untouched. A34 makes the **written contract agree with the
renderer behaviour A33 already implemented in code** — the implementation and the prose had
drifted apart, and that contradiction is what is being closed. It is **not a tolerance** in the
nearest-ngid resolver, which never consults it.

**A33's historical text is not rewritten.** A33 did state the epsilon-free formula; A34 corrects
it forward.

### The canonical transform after A34

```
s         = DPI / 72
eps       = 0.001 px          # measured MuPDF (fz_round_rect) device-rectangle constant
device_x0 = floor(bbox_x0 * s + eps)
pdf_x     = (device_x0 + start_x_px) / s
```

Width **validation** uses the symmetric right-edge form actually implemented by
`expected_image_width`:

```
width = ceil(bbox_x1 * s - eps) - floor(bbox_x0 * s + eps)
```

### The falsification A33 lacked

Coordinates are derived **mathematically** from a target device coordinate (`x0 = (n − δ)/s`,
`x1 = (m + δ)/s`), not found by searching until something passed, and the boundary is
**bracketed** either side. Measured against the pinned **PyMuPDF 1.28.2 / MuPDF 1.28.2**:

| δ (px) | `x0·s` | MuPDF `pix.x` | zero-ε prediction | ε-aware prediction |
|---:|---|---:|---:|---:|
| 0.0005 | 499.9995 | **500** | 499 ✗ | **500** ✓ |
| 0.0010 | 499.9990 | **500** | 499 ✗ | **500** ✓ |
| 0.0011 | 499.9989 | **499** | 499 ✓ | 499 ✓ |
| 0.0020 | 499.9980 | **499** | 499 ✓ | 499 ✓ |

Identical at **300 and 330 DPI**, and the same threshold holds on the **right edge** used by
`expected_image_width`. Inside the band the two predictions genuinely differ — asserted, so the
case is discriminating rather than merely favourable.

**The load-bearing negative control:** with `MUPDF_ROUND_EPS = 0`, both the origin control and
the width derivation **stop matching the renderer on every in-band case**, and a further check
confirms the injection does not leak. Had that not fired, the constant would have been
unfounded and `device_origin_px` reverted.

### Preserved unchanged

Nearest neutral glyph `x0`; **no tolerance**; exact tie → `UNMATCHED`; no candidate →
`UNMATCHED`; the selected `ngid` is the occurrence identity; the minimal-union crop with **zero
padding**; every fail-closed bbox refusal; and `NONZERO_PAGE_ROTATION` **abort-never-skip**.

**Population impact: none.** Pre-execution, DEVELOPMENT + synthetic only. No membership change,
no scoring, no holdout document opened, no oracle artifact created.

### Reviewed: approved, with one clerical repair (`4767930`)

External review **approved A34 substantively**. One stale evidence label survived the
consistency sweep: the `x20` width check was still described as `ceil(x1*s) - floor(x0*s)`,
epsilon-free, contradicting the rule the check evaluates via `expected_image_width`. The label
now states `ceil(x1*s - eps) - floor(x0*s + eps)` and the artifact was regenerated so the
committed test description agrees with the committed source. **No implementation and no
measurement changed** — the regenerated artifact differs by exactly that one line, every
measured value byte-identical on re-measurement against the same pinned renderer, so the
reproduction is evidence rather than an assumption. Re-measured: `x20` 45/45, 0 stop
conditions; H 541/541 and C 4/4 at both scales; 1164/1164 DEVELOPMENT regions rendered.

---

## A35 — SUBSTANTIVE. `adjudicator_prompt` + `build_oracle` implement already-frozen oracle rules

```json
{"id": "A35", "class": "SUBSTANTIVE",
 "commits": ["acc7c6a", "4ba99da"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/adjudicator_prompt.md", "probes/build_oracle.py",
                   "probes/x21_build_oracle.py"],
 "supersedes_text_in": "none",
 "status": "FROZEN -- reviewed; adjudicator prompt and oracle builder approved under A36 overlap semantics"}
```

**Why SUBSTANTIVE despite `affects_scoring_rule: false`.** `adjudicator_prompt.md` and
`build_oracle.py` are **result-bearing methodology surface**: a wrong implementation could alter
a label, a stimulus or a join, and therefore a realized score. They cannot be filed as TOOLING.
`affects_scoring_rule` is nonetheless **false** because A35 introduces **no new rule** — it
implements what PRE-REGISTRATION §5.3–5.8, HARNESS-PLAN §3–§4 and A19–A34 already froze.

**A35 may introduce no methodology.** Where the frozen sources do not determine an
outcome-affecting choice, the obligation is to **STOP and report**, never to settle it in code.

### A35.1 — implementation obligations, `adjudicator_prompt.md`

The prompt asks for exactly six things and nothing else: heading occurrences present, exact
printed text, immediate parent, role from the **§5.3 codebook**, `start_physical_line`, and
integer `start_x_px`. `start_x_px` carries the **A33.5** instruction verbatim — the left edge of
the first character's **own visible ink**, ignoring strike-through, underline, border or rule,
and never a text-box or bounding-box edge — and is declared an **identity annotation only**,
with text, parent and role independently adjudicated.

It must not reveal or mention `H`, `X`, hybrid, extended glyph, architecture, frame `C`/`D`,
stratum, control status, repeat status, document identity, architecture-produced text, or
amount/account attribution, and must not indicate which answer would favour either
architecture. **M6 remains deferred and is not asked.**

**The role codebook stays the fine §5.3 one** — `account`/`agency`/`grouping`/`title`/
`division`/`section`/`other`. HARNESS-PLAN §3's "coarse leaf/container role" describes **M5's
scoring map**, not what the adjudicator records; §5.3 is the specific normative statement about
what is recorded, and asking only leaf-vs-container would discard information §5.3 requires and
could not be recovered later. *Forward finding, not resolved here:* the **leaf-vs-container
coarsening map itself is defined nowhere** in the frozen sources. It is `score_metrics`'
obligation and must be ruled before M5 is computed. A35 does not choose it and does not need it.

**Leakage is gated executably, not by inspection.** A grep-based control runs over the realized
adjudicator-facing artifact, and a **negative control injects forbidden text and requires the
gate to fail**.

### A35.2 — `start_physical_line` is region-relative, and this is an encoding, not a rule

The adjudicator sees a cropped region, so it cannot report a page-level neutral-line ordinal.
`start_physical_line` is therefore the **1-based index of the printed line within the rendered
stimulus, counted top to bottom**, which `build_oracle` maps to the region's committed neutral
line at that position.

**This is determined up to isomorphism and so is not a new methodology choice.** A region is 8
**consecutive** neutral lines by ordinal; the crop is the minimal union of exactly those lines'
bboxes; ordinals run top to bottom; and every ink line on a page **is** a neutral line, since
the skeleton clusters all ink glyphs. So no foreign line can fall vertically between the
region's own lines, and visible printed lines stand in **bijection** with committed region
lines. A30.3's rule names the physical line as a *referent*; any encoding naming the same line
yields the identical nearest-glyph outcome. The bijection is recorded in the private key so a
reviewer can check it, and an out-of-range index **refuses** rather than resolving to a guess.

Explicitly **not** chosen: the page's printed margin line number. §5.4 lists it as something
visible, not as an answer format, and qualifies it "where the page has them" — so it cannot be
the required format without leaving pages unanswerable.

### A35.3 — implementation obligations, `build_oracle.py`

Consumes frames, the PDFs and `adjudicator_prompt.md`; emits two artifacts of deliberately
different content. The **private key** carries blind id → canonical pre-blinding identity,
`document_sha256`, page, region ordinal, stratum, frame, control/repeat bookkeeping, the H/X
output needed for the later join, renderer name and version, DPI, committed bbox in PDF points,
and PNG sha256. The **adjudicator-facing artifact** carries **only** the blind id, the rendered
image and the question/codebook.

Frozen behaviour implemented, not redesigned: 300 DPI primary and 330 DPI R1 (A28.4), identical
committed bbox and source region with **raster scale the only difference**; R1 records its own
`start_x_px` and resolves independently; selection settled from canonical pre-blinding
identities (A28.3) with blind ids derived only afterwards and **never** consumed by sampling or
presentation ranking; realized blind-id uniqueness asserted over the **complete** set including
controls and repeats, a collision being a deterministic **build abort** with no salt, re-roll,
overwrite, merge or last-write-wins (A30.5).

Geometry comes from `oracle_geometry.py` — never a competing copy — using the A34 transform
`s = DPI/72`, `eps = 0.001`, `device_x0 = floor(bbox_x0*s + eps)`,
`pdf_x = (device_x0 + start_x_px)/s`, width `ceil(bbox_x1*s - eps) - floor(bbox_x0*s + eps)`.
The crop is the committed frame's minimal union with zero padding: **no** fresh PDF clustering,
arm-text-derived crop, column or full-page expansion, padding, or clip/intersection repair.
`MISSING_LINE_BBOX`, `NON_FINITE_LINE_BBOX`, `NON_POSITIVE_LINE_BBOX`,
`REGION_BBOX_OUTSIDE_PAGE` and `NONZERO_PAGE_ROTATION` **abort construction** — a refusal may
never drop a stimulus or reduce a denominator.

### A35.4 — controls fixed before the components exist

Twenty, each stating the fact that would make it fail, and **no control may compare a helper
with itself where independent mutation is possible**: 1 re-render determinism · 2 300/330 share
one bbox · 3 R1 differs only by raster scale · 4 the renderer consumes PDF geometry, not H/X
text · 5 mutating H/X text cannot change the PNG · 6 blind-id scheme changes select nothing
different · 7 …and change no presentation rank · 8 an injected blind-id collision aborts · 9 the
adjudicator artifact leaks no architecture/frame/stratum/document/control field · 10 **injected**
forbidden leakage makes the gate fail · 11 the private key carries the downstream join · 12 a
shuffled key breaks the join, proving it load-bearing · 13 the crop equals committed frame
geometry exactly · 14 an outside-page bbox aborts · 15 a non-positive line bbox aborts · 16
nonzero rotation aborts and cannot become a skip · 17 the PNG hash moves when the stimulus
really changes · 18 no M6/amount-attribution question is asked · 19 the A33.5 visible-character
instruction is present · 20 realized blind-id uniqueness is checked after every instance,
controls and R1 repeats included.

### A35.5 — STOP, open for review: `REGION_IN_BOTH_FRAMES`

**A region can be in the C-frame and the D-frame, and the frozen sources do not say what
happens then.** `build_oracle` **refuses**; it does not choose.

Measured on the same DEVELOPMENT frames `x17` committed — region counts **238 / 239 / 267**
match `x17` exactly — **17 of 24 C-frame regions (71 %) are also D-frame regions**; on `x21`'s
20-page demonstration window it is **18 of 24**. The mechanism is structural, not incidental:
the C draw ranks **every** region of a P-head document while ~70 % of regions carry text
discordance, and **A27.2 forbids replacing a drawn region after inspecting its content**, so it
cannot be designed away in the draw either.

| undetermined | why it is outcome-affecting |
|---|---|
| one stimulus or two? | A28.3's base identity is `("region", doc_sha, page, ordinal)` with **no frame component**, so two instances of one region are **unrepresentable** — A30.5 sees a duplicate identity and aborts. Adding a frame component would be new methodology |
| which adjudication route? | §5.5.1 sends C-frame to **AI** adjudication and D-frame to **human** adjudication item by item. An overlapping region has two routes and no rule to pick one |
| which denominators? | §5.8's "never pooled" governs **metrics**, not set membership, so it does not settle whether the region counts in RQ1, RQ2 or both |

Choosing here would silently decide **who adjudicates 71 % of the C-frame** and which
denominators move. `x21` records the stop with its instances; the ruling belongs to review.

> **RESOLVED FORWARD BY [A36](#a36--substantive-cd-overlap-semantics-and-m5-role-coarsening).**
> The stop was reviewed and held **valid**. A36 rules that C and D may overlap, that one
> physical region is one stimulus carrying both memberships, and that the single blind stimulus
> takes both adjudication routes. This paragraph is the historical record of the open question
> and is **not** rewritten to read as though it had always been answered.

Note this contradicts HARNESS-PLAN §7's "**Unresolved outcome-affecting ambiguities: ZERO**".
That sweep looked for surviving *"permitted"* and *"seeded"* phrases — a choice a source hands
to implementation explicitly. This ambiguity is of a different kind: it arises from the
**interaction** of two independently frozen rules, neither of which delegates anything, so a
phrase-level sweep could not have found it. §7's claim is not rewritten here; it is corrected
forward, as A34 corrected A33.

### Population and boundary

DEVELOPMENT + SYNTHETIC only. **No holdout document is opened**, an explicit guard enforces it,
nothing is adjudicated or scored, and none of `results/frames.json`, `results/oracle_key.json`,
`results/oracle_adjudicated.json`, `results/metrics.json`, `results/scores.json` or
`EXECUTION-START.json` is created. `score_metrics.py` and `decide_architecture.py` are **not**
started.

**Realized at A35 (superseded by A36's rerun):** `x21` 55/55 controls pass, **1 stop
condition**. DEVELOPMENT: 3 documents, 193 stimuli, 193 images rendered, 17 R1 repeats. After
A36 the same probe reports **93/93 and 0 stop conditions**; the A35 figures are kept as the
state at which the stop was raised.

**Forward finding closed:** A35.1 flagged that M5's leaf-vs-container coarsening map was
defined nowhere. **A36.7 freezes it**, so `score_metrics` no longer opens onto a known
ambiguity.

---

## A36 — SUBSTANTIVE. C/D overlap semantics and M5 role coarsening

```json
{"id": "A36", "class": "SUBSTANTIVE",
 "commits": ["34e5384", "368ae63"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/build_oracle.py", "probes/methodology_contracts.py",
                   "probes/x21_build_oracle.py"],
 "supersedes_text_in": "the UNSPECIFIED INTERACTION of PRE-REGISTRATION 5.5.1 and 5.8 for a region in both frames, and HARNESS-PLAN section 7's claim of zero unresolved outcome-affecting ambiguities; no frozen clause is reversed",
 "status": "IMPLEMENTED -- reviewed and ruled; x21 93/93, 0 stop conditions"}
```

`affects_scoring_rule` is **true**: the overlap rule fixes which denominators a region enters
and which adjudication source a metric reads, and the M5 map fixes a role comparison.

**A35.5's STOP is resolved forward, not retroactively.** A35.5's historical record stands as
written — it correctly reported that the frozen sources did not determine this. A36 supplies
the ruling that was missing. HARNESS-PLAN §7's "**Unresolved outcome-affecting ambiguities:
ZERO**" is likewise **corrected forward**, not rewritten: it was true of the sweep it
described (surviving *"permitted"*/*"seeded"* phrases) and false of ambiguities arising from
two frozen rules **interacting**, which that sweep could not see.

**On materiality versus justification.** The DEVELOPMENT overlap measurement (17 of 24 C-frame
regions) establishes only that the case is **material** and must be ruled before execution. It
is **not** the reason for the rule chosen. The rule below is chosen because it is the only one
that leaves the **independently frozen C and D estimands intact**: C remains a uniform draw over
a P-head document's regions, D remains the complete discordance census, and neither is redefined
as a function of the other. A rule selected to make an overlap count smaller would be a rule
selected by the data.

### A36.1 — C and D memberships MAY overlap

C and D are **independent membership predicates**. A region selected into C stays in C even if
it is also D; a region satisfying D stays in D even if it was already drawn into C.

**Forbidden:** dropping the overlap from C; dropping it from D; replacing a C draw after
observing D membership; re-sampling C; forcing the frames disjoint. A27.2's uniform C draw and
A27.3's D census are **unchanged** — and note that A27.2 already forbids replacing a drawn
region after inspecting its content, so an overlap-avoiding draw was never available.

### A36.2 — one physical region is ONE stimulus identity

For a C∩D region: **one** canonical base identity, **one** 300-DPI primary rendering, **one**
primary PNG, **one** blind id.

**Forbidden:** adding a frame component to A28.3's base identity; creating a separate C stimulus
and D stimulus; salting or re-rolling a second blind id; rendering the same primary twice as two
frame instances. A28.3 remains exactly:

```
("region", document_sha256, page_number, region_ordinal)
```

**Frame membership is metadata about a stimulus, not part of its identity.** The private key
therefore carries an explicit membership list with deterministic ordering — `["C"]`, `["D"]`,
`["C","D"]` — replacing the singular `frame` projection, which could not represent the overlap
without being ambiguous. The adjudicator-facing artifact is **unchanged**: `{id, image,
question}`. No frame membership, and no route, may leak.

### A36.3 — "never pooled" means separate estimands, not disjoint sets

> **C and D may overlap in physical regions. "Never pooled" means their estimands and
> denominators remain separate; it does not require disjoint membership.**

A C∩D region therefore counts **once** in the applicable C-frame denominator **and once** in the
applicable D-frame census/denominator. `|C ∪ D|` is **never** substituted for either frame's
denominator. The **raw overlap count is reported alongside both frame sizes**, so a reader can
see the double-counting across estimands rather than infer it.

### A36.4 — a stimulus and an adjudication are different objects

The same blind stimulus receives **both** independently required answer routes:

| membership | routes |
|---|---|
| C only | AI |
| D only | human |
| C ∩ D | AI **and** human |

Neither answer may be visible to the other adjudicator before it answers. The eventual
adjudication artifact must represent **two separately namespaced answers keyed to the same blind
id** (`ai[id]`, `human[id]`). That **schema requirement is frozen here**; the artifact itself is
not built in this pass.

**CRITICAL PROHIBITION.** The human D answer is **not** substituted into C metrics merely
because it exists. C's licensed claim is *AI image-adjudication with a seeded human audit*. D
membership is **conditional on architecture disagreement**, so using human truth only on C∩D
regions would make C a **mixed oracle whose source is selected by H/X discordance** — the
architectures would be choosing their own oracle on precisely the regions where they disagree.

```
C metrics          -> AI answer
D decision evidence -> human answer
```

### A36.5 — the 25-item C audit is invariant to D membership

The audit sample is selected **solely** by the frozen `cframe-audit` ranking over **C base
identities**. D membership may not change audit membership or its denominator.

If a C-audit-selected region is also D, the **already-required human D answer MAY serve as that
item's audit answer** — it is the same blind image and the human need not answer it twice. But a
C∩D human answer **does NOT enter the C audit** unless that base identity was independently
selected by `cframe-audit`.

### A36.6 — route inheritance for controls and R1

Every result-bearing adjudication route must remain falsifiable, so **N-A / N-B / N-C must be
exercised on every route whose labels are later consumed**.

R1 selection is still made **once** from canonical base identities under the frozen ranking and
seed, both unchanged. The repeat remains **one** canonical `r1-repeat` identity and **inherits
its primary's required route(s)**: C only → AI, D only → human, C∩D → both. **No route-specific
R1 identities.** Where one physical R1 stimulus goes to two adjudicators, the answers stay
separately namespaced.

### A36.7 — M5 role coarsening, frozen

The adjudicator continues to record the **fine §5.3 role**. **M5 alone** coarsens it.

| oracle role | M5 | | emitted kind | M5 |
|---|---|---|---|---|
| `account` | LEAF | | `account` | LEAF |
| `section` | LEAF | | `section` | LEAF |
| `agency` | CONTAINER | | `major` | CONTAINER |
| `grouping` | CONTAINER | | `agency` | CONTAINER |
| `title` | CONTAINER | | `grouping` | CONTAINER |
| `division` | CONTAINER | | `title` | CONTAINER |
| `other` | UNSCORABLE | | `subsection` | UNSCORABLE |
| | | | `preamble` | UNSCORABLE |

**The emitted map is complete against production**, and this is asserted executably rather than
believed: `AnchorKind` is `Literal["title","section","account","grouping","agency","major",
"subsection","preamble"]` — exactly the eight mapped kinds. A control compares the map's domain
with that Literal, so a kind added to production later **fails** instead of silently arriving as
an unmapped role. (`division` is an oracle role and an `Anchor` *field*, never an emitted
*kind*, which is why it appears in one column only.)

**`section -> LEAF` is defined only at M5's adjudicated-heading granularity.** It is not a claim
that a legal section cannot contain subsections.

**M5 denominator:** matched heading occurrences where **both** sides map to LEAF or CONTAINER.
If either side is `UNSCORABLE`, the occurrence is **excluded** and the **raw unscorable count is
reported**. A zero denominator is **VACUOUS**. An unknown role on either side **refuses**.

**M5 remains CORROBORATION ONLY and MAY NEVER AFFECT THE ARCHITECTURE DECISION.** Rule 1 is
unchanged by this ruling.

### Population and boundary

Pre-execution. No membership change, no holdout document opened, nothing adjudicated or scored,
and no confirmatory or scoring artifact created. `score_metrics.py` and
`decide_architecture.py` remain **unstarted**.

### Realized under A36

`x21` **93/93 controls pass, 0 failures, 0 stop conditions** (was 55/55 with one stop). The
`REGION_IN_BOTH_FRAMES` refusal is removed because A36 resolves it — **duplication is no longer
attempted**, and A30.5's identity uniqueness was *not* weakened to permit it.

DEVELOPMENT, 20-page demonstration window (not a census): **C 24, D 170, overlap 18**, union
**176 = 24 + 170 − 18**, and 193 stimuli = 176 primaries + 17 R1 repeats. The union is labelled
information-only and is never substituted for either denominator. `c_audit_selected` is **24
rather than 25** because this window contains only 24 C regions in total; the draw takes
`min(k, available)` and does not invent items.

Regression: `x15` remains **26/26** and its committed artifact is **byte-identical**, so the M5
block changed no existing contract.

---

## A37 — SUBSTANTIVE. Freeze the supplementary non-zero document bootstrap

```json
{"id": "A37", "class": "SUBSTANTIVE",
 "commits": ["26fda38", "f2d16d0"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/methodology_contracts.py", "probes/x15_methodology_contracts.py",
                   "probes/x21_build_oracle.py"],
 "supersedes_text_in": "none -- A27.5 and PRE-REGISTRATION 8.3 are unchanged; this freezes the reproducibility of a quantity they already permit",
 "status": "FROZEN -- reviewed; supplementary section 8 document bootstrap reproducibility approved"}
```

**`affects_scoring_rule` is false, and that is a substantive claim rather than a convenience.**
The primary inferential procedure remains A27.5 / §8.3 exactly: the **exact one-sided 95 %
Clopper–Pearson upper bound**, **independent unit = document**, zero-event closed form
`1 − 0.05^(1/N)`. The bootstrap is **supplementary reporting only** and may never affect Rule 0,
Rule 1, Rule 3, adequacy or `decide_architecture`. A37 freezes *how a permitted companion
number is produced*; it does **not** promote that number into evidence.

### A37.1 — provenance: A29 stays WITHDRAWN, its finding is adopted forward

The order-dependence defect was measured by **withdrawn A29** (`134a115`). A29 was withdrawn
for **process/ownership** reasons — two sessions writing one amendment number — **not** because
its finding was rejected. A29 therefore remains **WITHDRAWN** and is not resurrected, silently
or by cherry-pick; A37 adopts the valid finding under a fresh number and closes the details
A29 left embodied in code rather than stated normatively. **A29 was not wrong.**

| retained from A29 | made explicit or tighter by A37 |
|---|---|
| 10,000 document resamples | **one unique record per document**, duplicates refused |
| with replacement | **event count DERIVED from the records**, never a caller-passed integer |
| seed family `20260807` | scoped to **the §8 document-discordance event only**, no generic API |
| hash-derived draws, no RNG object | **exact percentile order-statistic indices**, stated normatively |
| canonical ordering before any draw | **no interpolation**, no library quantile convention |
| supplementary / non-gating | canonical statistic identity **carries the population** |
| zero-event refusal | |

### A37.2 — the input is one record per independent document

```
records : [(document_identity, event_boolean), ...]
```

`N = len(records) >= 1`. The **event count is derived** as `sum(event_boolean)`. There is no
`events=` parameter, because a caller-supplied count can contradict the vector it claims to
summarise and nothing would detect the disagreement.

**Refusals**, each deterministic: an **empty** set → `EMPTY_DOCUMENT_SET`; a **repeated**
document identity → `DUPLICATE_DOCUMENT_IDENTITY`; a **non-boolean** event →
`NON_BOOLEAN_EVENT`. A duplicate is refused rather than silently weighting that document twice,
because **the document is the independent unit** (§8.3, red-team #7). This refusal is also what
makes a headings-as-rows table unpassable: several headings from one document collide on that
document's identity and the construction refuses.

Records are **sorted by canonical document identity before any draw**. The draw is an *index*,
so without canonical sorting the caller's listing order silently selects different documents —
the exact defect A29 measured.

### A37.3 — the canonical statistic identity carries the population

```
("section8", "document-heading-discordance", "P-head")
```

Frozen as a single constant; callers may not invent labels for the same statistic. **The
population component is not decoration.** §4.4.1 splits **P-head** (strata 1,2,3,5,7,8) from
**P-robust** (strata 4,6) and states that **no heading metric is claimed on P-robust**. The §8
event is heading-level, so this statistic is **P-head only**, and encoding that in the identity
means a P-robust variant cannot silently reuse the same draw sequence.

### A37.4 — the frozen draw

```
B         = 10_000 resamples          unit = document, sampling = WITH REPLACEMENT
seed      = 20260807                  namespace = bootstrap-document

digest = sha256("bootstrap-document|20260807|<canonical statistic identity>|<r>|<d>")
index  = int.from_bytes(digest[:8], "big") % N
```

Drawn from the **canonically sorted** vector. **No RNG object**, no dependence on Python /
NumPy / `random` generator behaviour, and no dependence on caller input order — so any
implementation in any language reproduces the same resample.

### A37.5 — the statistic, scoped

Per replicate, `bootstrap_rate = mean(resampled event booleans)`: a distribution over the
**document-level discordance rate**. Explicitly **not** a bootstrap over headings as
independent observations, over M1–M5 occurrence rows, or over the D-frame region census.

### A37.6 — the percentile endpoint rule, stated normatively

A29 froze the resamples but left the endpoint rule embodied in code. A37 states it:

```
sort the B replicate rates ascending
lower_index = floor(0.025 * (B - 1))      # B = 10_000  ->  249
upper_index = floor(0.975 * (B - 1))      # B = 10_000  ->  9749
interval    = [sorted_rates[249], sorted_rates[9749]]
```

**No interpolation. No NumPy percentile default. No library-dependent quantile convention.**
Both endpoints are therefore always *observed replicate values*, which is asserted rather than
assumed.

### A37.7 — zero events

If `sum(event_boolean) == 0` there is **no bootstrap**:
`reason = ZERO_EVENTS_BOOTSTRAP_REFUSED`. §8.1 measured it degenerate — every resample is 0.0 —
and **`[0, 0]` is never emitted as an interval**. The only inferential result is the exact
Clopper–Pearson upper bound, whose frozen zero-event closed form `1 − 0.05^(1/N)` is returned
alongside the refusal so the branch yields the licensed number rather than only an absence.
**The general (non-zero-event) Clopper–Pearson bound remains `score_metrics`' obligation under
A27.5 and is not implemented here.**

### A37.8 — non-gating, structurally

A27.6's decision-blocking conditions are written down executably as `GATE_VECTOR` — R1, N-A,
N-B, N-C, S1, confirmatory X2-a, confirmatory X2-b, M9 evaluability, §4.5 adequacy — so *"the
bootstrap is not one of them"* is a **checkable statement rather than a promise in prose**. A
control asserts no bootstrap field appears in the gate vector, and the result carries
`gating: False`. Cross-engine (`x09`) is absent from the vector on purpose: it qualifies
reporting and never blocks a decision.

### Population and boundary

SYNTHETIC only. No holdout document opened, nothing adjudicated or scored, no confirmatory or
scoring artifact, no execution marker. `score_metrics.py` and `decide_architecture.py` remain
**unstarted** — this is a pure contract in `probes/methodology_contracts.py` with its controls
in `probes/x15_methodology_contracts.py`, the existing owner.

### Realized

`x15` **51/51, 0 failures** (was 26/26). Fixture: 9 documents, 3 events → interval
`[0.0, 0.667]` at indices `[249, 9749]`. **200 of 200** sampled replicates repeat at least one
document, so replacement is proven rather than assumed. Zero-event branch at N=14 returns
**0.19263617565013536**, which independently corroborates the closed form against §8.3's stated
"≈ 19 % at N ≈ 14" and §8.1's measured 0.1926.

**Incidental artifact-reproducibility fix, found by the regression run.** `x21`'s committed
artifact was **not byte-reproducible**: two controls serialized raw Python **sets** into
`expected`/`observed`, and set repr order varies with per-process string-hash randomisation, so
identical inputs produced a diff on every run. Contents and pass state were always identical,
but the churn would pollute the ledger and it contradicts the reproducibility A37 exists to
establish. Both now compare sorted lists. **Proven** by running each probe twice and diffing:
`x15` and `x21` artifacts are byte-identical across runs. No control's meaning changed and
`x21` remains **93/93**; `probes/x21_build_oracle.py` is declared above because this commit
touched it.

---

## A38 — SUBSTANTIVE. Make the frozen scoring joins executable from committed artifacts

```json
{"id": "A38", "class": "SUBSTANTIVE",
 "commits": ["e44dc39", "5f558c1", "92cddbe"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "files_touched": ["probes/adjudicator_prompt.md", "probes/build_frames.py",
                   "probes/build_oracle.py", "probes/neutral_identity.py",
                   "probes/s1_control.py", "probes/x21_build_oracle.py",
                   "probes/x22_score_input_contract.py"],
 "supersedes_text_in": "none -- no metric, denominator, matching rule, threshold, normalisation, hierarchy rule, statistical rule or decision rule is introduced or changed",
 "status": "FROZEN -- approved by external review after the A40 freeze verification; the control-fixture scorer/adjudication input path it was held for is settled by A40.15/A40.16"}
```

**`affects_scoring_rule` is false and A38 must keep it so.** It introduces **no** new metric,
denominator, matching rule, threshold, normalisation, hierarchy rule, statistical rule or
decision rule. It makes already-frozen A30 / §6 / §8 facts **reachable from committed
artifacts**, so the future `score_metrics.py` is a pure consumer that never reopens a PDF,
re-runs neutral clustering, re-runs anchor recognition, or invents an input schema.

### A38.0 — the defect being closed

A35's `verify_join` proves a blind id stays bound to its **image and region**. It does **not**
prove the **occurrence-level** join A30/M1–M5 require. Concretely: the committed frame stores
`gids` but not each gid's `x0`, so A30.3's nearest-glyph resolver has no candidates;
`architecture_output` is an **optional caller-supplied opaque blob** with no schema and no
deterministic producer; and M9 and S1 have no committed producer at all. A38 closes these
together rather than discovering them one at a time inside the scorer.

### A38.1 — the score-input ownership table

Every future `score_metrics` obligation, its committed producer, and whether any PDF or runner
re-read would be needed. **"PDF re-read" is `no` for every owned row — that is the point.**

| required fact | committed artifact · field | producer | PDF re-read |
|---|---|---|---|
| **M0a** text-discordant neutral lines | frames · `neutral_lines[].line_state.text_discordance` | `build_frames` | no |
| **M0b** segmentation-discordant lines | frames · `neutral_lines[].line_state.segmentation_discordance` | `build_frames` | no |
| **M0b_defined / rate_on_defined** | frames · `line_state.common_gids`, `line_state.diagnostics` | `build_frames` | no |
| **M0-any** | derived from M0a ∪ M0b | `score_metrics` | no |
| **M0c** anchor-discordant regions | frames · `regions[].anchor_evidence.differ`, `d_reasons` | `build_frames` | no |
| **both_absent** | frames · `neutral_lines[].in_m0_risk_set == false` | `build_frames` | no |
| **M1–M3** emitted occurrences | frames · `architecture_occurrences.{H,X}[]` **(A38.3, new)** | `build_frames` | no |
| **M1–M5** adjudicated headings | `oracle_adjudicated` **(A38.7 encoding, new)** | adjudication | no |
| **occurrence join** geometry | frames · `neutral_lines[].identity_candidates` **(A38.2, new)**; oracle key · `bbox_pdf_points`, `dpi`, `region_line_bijection` | `build_frames` + `build_oracle` | no |
| **M4** emitted immediate parent | frames · `architecture_occurrences[].immediate_parent` **(A38.4, new)** | `build_frames` via production `breadcrumb_for` | no |
| **M5** roles | adjudicated `role` + `architecture_occurrences[].anchor.kind`; map frozen by **A36.7** | adjudication + `build_frames` | no |
| **M7** display-split signature | frames · `architecture_occurrences[].anchor.text` | `build_frames` | no |
| **M9** structural viability | frames · `m9.{H,X}` **(A38.8, new)** | `build_frames` via production functions | no |
| **C-frame AI answers** | `oracle_adjudicated.ai` | adjudication | no |
| **D-frame human answers** | `oracle_adjudicated.human` | adjudication | no |
| **C-audit answers** | oracle key · `is_c_audit_selected` + `human` namespace | `build_oracle` + adjudication | no |
| **R1 answers** | oracle key · `is_r1_repeat`, `r1_base_identity` + both namespaces | `build_oracle` + adjudication | no |
| **S1** liveness | `results/s1_control.json` **(A38.9, new)** | dedicated pre-score control | no |
| **§8 document event** | derived: document has ≥ 1 heading-level H/X discordance | `score_metrics` | no |
| **§8 Clopper–Pearson** | `score_metrics` (A27.5) | `score_metrics` | no |
| **A37 bootstrap** | `methodology_contracts.section8_document_bootstrap(records)` | A37 | no |
| **cross-engine qualification** | `results/cross_engine_control.json` **(A39.2)** | `cross_engine_control.py` | no |
| **N-A / N-B / N-C** | `results/control_fixtures.json` **(A39.3/A40)** + oracle key · `control_kind`, `control_variant` | `control_fixtures.py`, gated by **G6** | no |

**`results/x09_skeleton_cross_engine.json` is DEVELOPMENT mechanism evidence only and is NEVER
a confirmatory scorer input.** The row above named it as the producer, which was stale: `x09`
proves the mechanism works and that its faults are detectable, on development material. The
confirmatory qualification comes from `cross_engine_control.py`, which **calls `X09.gate`**
rather than reimplementing the `max(pdfium, pymupdf)` denominator or either threshold.

**The control-fixture row has a producer but is NOT yet a complete input path.**
`results/control_fixtures.json` exists with 8 / 8 / 4, every hash verified against the bytes,
and holdout exclusion now enforced by **source identity** (A40.7 / F7). But the A40.7
falsification established that the controls are **not executable through `build_oracle`**
(F5) and that the manifest does **not** commit the adjudication region for N-A/N-B (F6), so
this row was **owned but incomplete**, and A38 was held unfrozen for exactly that reason.

> **RESOLVED, and A38 is now FROZEN.** F5 landed in A40.11 and is committed executable evidence
> in A40.15 (`x26`: 20 controls through the real `build_oracle`, both routes, none in C/D/C-audit/
> R1, leakage and join clean); F6 committed the exact adjudication region per control in A40.11.
> The row is a complete input path, so the condition this paragraph records is discharged rather
> than deleted — it is kept as the historical reason the freeze waited.

### A38.2 — persist the A30 identity candidates

Additive on the committed frame: `neutral_lines[].identity_candidates = [{"ngid", "x0"}, …]`,
where `ngid` is the A24.2 neutral ink identity and `x0` that source glyph's **physical PDF
x0**. Requirements: candidates derive from the **same A24.2 neutral-eligible source glyphs**
that formed the line; **every `gids` member has exactly one candidate and no candidate lies
outside `gids`**; **U+0020 never appears** (A24.2 excludes it by codepoint); `x0` is **source
geometry, never H/X reconstructed text geometry**; **`x0` is not rounded** — nearest-x identity
consumes it; ordering is by `ngid` **for serialization only**, and **ngid order may never
become reading order** (A30.1: equality only; ngid order disagreed with printed order on 10 of
33,602 emitted lines).

**Bilateral gate, with its limit stated.** The existing skeleton gate compares each arm's
returned `(key, gids)`; A38 extends it to compare **candidates including `x0`**, so mutating
one arm's candidate `x0` fails construction. **This is not two independent implementations**:
A19 requires *one* skeleton and both runners deliberately call the same
`run_hybrid.neutral_skeleton`. The gate therefore catches divergence in what each arm
**returns and carries**, which is the reachable failure; `x13` separately asserts skeleton
identity. Claiming more would overstate it.

### A38.3 — persist deterministic architecture occurrence records

The scorer receives **records, not an opaque blob**. Built from the frozen A30 machinery —
`anchor_provenance.instrumented_extract_anchors`, `strip_to_production`, `key_for` — and **no
third anchor-recognition implementation**. Per architecture, document-scope: run the
instrumented extraction; assert `strip_to_production(instrumented) == production
extract_anchors(...)` **element for element**; resolve every occurrence through A30 `key_for`.

**Identity never comes from text, anchor kind, or emitted occurrence ordinal.** Every
production occurrence is persisted **including one whose A30 resolution refuses** — an
`UNMATCHED` occurrence is never dropped, because dropping it would shrink a denominator
invisibly. Records carry the anchor, `region_ordinal`, `occurrence_key | null`, `match_status`,
`unmatched_reason`, and `immediate_parent`, in **document order, never ngid order**.

### A38.4 — immediate parent reuses production hierarchy

M4's emitted parent is the **penultimate element of production
`pdf_anchors.breadcrumb_for(anchor, all_anchors)`**; a one-element breadcrumb has **no** emitted
parent. `division` behaviour is production's, unchanged. **No new hierarchy walk is invented**,
and controls compare against `breadcrumb_for` itself rather than against a second copy of the
same logic.

### A38.5 — the frame owns the architecture occurrences

The frame stage already owns the complete H/X extraction and the A30 source-position bridge, so
`architecture_occurrences: {H: [...], X: [...]}` lives on the committed document frame.
Existing `anchor_evidence` remains **D-frame membership evidence only** and is not overloaded
into occurrence scoring. **No frame membership or metric changes; C/D counts keep their exact
meaning.**

### A38.6 — one source of truth in `build_oracle`

The result-bearing path takes architecture occurrences **from the committed frame**, never from
a caller-invented `architecture_output`. Accepting both a frame-derived and a conflicting
caller-provided representation is forbidden. The private key carries or deterministically
references, per stimulus: the region's architecture occurrences, its `identity_candidates`, the
`region_line_bijection`, `bbox_pdf_points` and `dpi`. **The blind artifact remains exactly
`{id, image, question}`** and no new private field may leak.

### A38.7 — the occurrence-level join, and the adjudicated encoding

A pure helper over **committed facts only**:

```
start_physical_line -> region_line_bijection      -> committed neutral line
start_x_px          -> oracle_geometry.pixel_to_pdf_x(start_x_px, bbox_x0, dpi)   [A34-aware]
identity_candidates -> anchor_provenance.resolve_oracle_start_ngid(candidates, target_pdf_x)
resolved ngid       -> anchor_provenance.occurrence_key(doc_sha, page, line_key, ngid)
```

The **superseded linear** `anchor_provenance.image_x_to_pdf_x` is **not** used. No tolerance, no
text/kind/order fallback; no candidate → `UNMATCHED`; exact tie → `UNMATCHED`; a refusal is
reported and **never converted to an incorrect match**.

The adjudicated artifact encoding is frozen (`oracle_adjudicated/1`) with `ai` and `human`
namespaces keyed by blind id, fields corresponding **exactly** to `adjudicator_prompt.md`,
`UNREADABLE` representable per field, `notes` never altering a field, the answer `id` equal to
its namespace key, an unknown blind id refused, a missing required route refused, C metrics
reading **AI** and D decisions reading **human**, a C-audit overlap reusing its one human answer,
and **no route fallback**. **What the prompt asks is unchanged**, and no real confirmatory
adjudicated artifact is created.

### A38.8 — M9 raw facts, recorded not decided

Per document per architecture, from production: whether `derive_size_bands` returns a band;
`_coverage`; the frozen floor `_COVERAGE_MIN = 0.85`; total lines; margin-numbered lines
(`line_number is not None`); margin-numbered lines **carrying a glyph size** (which is
`_coverage`'s actual numerator); and the **margin-numbered line keys** themselves. **This stage
records facts. It does not compute Rule 0.**

> **STATUS: RESOLVED by [A39.1](#a39--substantive-rule-0s-margin-line-clause-cross-engine-sampling-control-sources).**
> `margin_lines_recovered` is the **count of `Page.lines` where `line_number is not None`**, and
> **any strictly positive per-document deficit fires, with no tolerance**. The glyph-size count
> and the per-line keys remain **diagnostics** and do not determine the clause. `x22` carries an
> **executable** assertion that `margin_line_loss` implements exactly this, so the resolution
> cannot drift from the code. The original open question is preserved below as the record that
> the gap was found and reported **before** execution rather than discovered inside the scorer.
>
> **FORWARD AMBIGUITY as originally recorded — HISTORICAL.** Rule 0's *"loses
> margin-numbered lines on a document the other keeps"* does **not** uniquely determine the
> comparable quantity. At least three readings survive the frozen text: (a) the **count** of
> lines with `line_number is not None`; (b) `_coverage`'s **numerator**, numbered lines that
> also carry a glyph size — note §6's prose describes `_coverage` as counting lines whose
> `line_number is not None`, which is its **denominator**, so the prose and the code do not
> pin the same quantity; (c) a **set** difference, i.e. specific numbered lines present under
> one architecture and absent under the other, which a count comparison cannot see. No
> threshold is stated for "loses" either. **A38 chooses none of them**: it records the raw
> basis for all three, including per-line keys so a set comparison remains possible. The
> ruling belongs to `decide_architecture` and must be made before Rule 0 is implemented.

### A38.9 — S1 gets a committed producer

The frozen liveness control — **extended advances × 1.25 must raise M0** — gets a dedicated
pre-score artifact so the scorer never re-runs an architecture. Requirements: the sabotage scale
is exactly **1.25** and is **not a tunable parameter on the result-bearing path**; **only X's
advances change**; ordinary H and ordinary X are untouched; S1 uses **the same M0 definition**
as the primary comparison; primary M0 and sabotaged M0 are reported **separately** alongside
`fires`; and S1 **never** changes C/D membership or any primary artifact. A DEVELOPMENT control
proves the sabotage actually changes the input, and a **synthetic dead comparator, where
sabotage does not raise M0, must report S1 FAIL**.

### A38.10 — the A37 helper boundary

The result-bearing scorer calls only `methodology_contracts.section8_document_bootstrap(records)`
and may **not** supply a custom statistic id. `bootstrap_draw_index` and `bootstrap_resample`
encode and test the frozen mechanism and domain separation; they are **not** a generic scoring
surface.

### Population and boundary

SYNTHETIC + DEVELOPMENT only. No holdout document opened, no H/X run on any holdout member,
nothing adjudicated or scored, no architecture decision, and none of `frames.json`,
`oracle_key.json`, `oracle_blind.json`, `oracle_adjudicated.json`, `metrics.json`,
`scores.json` or `EXECUTION-START.json` created. `score_metrics.py` and
`decide_architecture.py` remain **unstarted**, and **G5 is not modified to hide an unowned
component**.

### Realized

`x22` **26/26** (new), `x21` **112/112** (was 93/93), `x17` 56/56, `x16` 27/27, `x15` 51/51.
Private key schema `oracle_key/2 → /3`. On the DEVELOPMENT window: 24 occurrences per arm, all
MATCHABLE; every `immediate_parent` equals `breadcrumb_for`'s penultimate element; **S1 fires**,
with the risk set provably unchanged by sabotage.

**Two incidental fixes, found by the controls rather than by inspection.** Occurrence keys were
compared **tuple-vs-list** across the two sides of the join — unequal while being the same key,
which would have made every matched-heading denominator silently **zero**. Both sides now
normalise to JSON lists. Separately the leakage value-scan fired 118 times on DEVELOPMENT; the
token was `grouping`, an anchor **kind** colliding with the prompt's published role codebook. A
term from that closed vocabulary cannot identify *which* stimulus an item is, so it is excluded
by **membership of the A36.7 maps** — a kind added later is covered automatically rather than
reappearing as a false positive — and the injection controls still fire, so the gate is not
vacuous. The prompt's JSON example also used two **real** appropriations headings; they are now
obviously synthetic placeholders, which removes both the collision and an anchoring risk.
**What the prompt asks is unchanged.**

---

## A39 — SUBSTANTIVE. Rule 0's margin-line clause, cross-engine page sampling, control sources

```json
{"id": "A39", "class": "SUBSTANTIVE",
 "commits": ["e25edcd", "ba8e899", "b4bce1a", "67ae92a"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/build_frames.py", "probes/cross_engine_control.py",
                   "probes/methodology_contracts.py", "probes/s1_control.py",
                   "probes/x04_freeze_check.py", "probes/x15_methodology_contracts.py",
                   "probes/x22_score_input_contract.py"],
 "supersedes_text_in": "none -- A38.8's forward ambiguity is RULED, not reversed; no frozen threshold is changed",
 "status": "FROZEN -- A39.1 APPROVED; A39.2 APPROVED; A39.3 and A39.4 APPROVED + FROZEN on the A40 fixture integration they were held for (A40.15/A40.16); A39.5 APPROVED"}
```

`affects_scoring_rule` is **true**: A39 makes the previously unspecified Rule 0 margin-line
comparison **executable**, and freezes the cross-engine page sample whose failure attaches a
reporting qualification.

### A39.1 — Rule 0's margin-line clause, ruled

A38.8 recorded three surviving readings and chose none. **The §6 M9 row settles it**: it lists
three *separate* quantities — does `derive_size_bands` return a band; is `_coverage ≥ 0.85`;
**how many margin-numbered lines are recovered**. The third is therefore **not** `_coverage`'s
numerator, or the row would be naming the same quantity twice.

```
margin_lines_recovered(A, d) = count of Page.lines where line_number is not None
                               for architecture A on document d
```

Per document: `H < X` → **H** has a Rule-0 margin-line loss; `X < H` → **X** has one; equal →
the margin-line clause **does not fire**. **Any strictly positive deficit counts as "loses".
There is NO tolerance** — no minimum lost lines, no percentage, no severity threshold. The
frozen text says *loses*, not *loses more than N*.

`n_margin_numbered_with_glyph_size` and `margin_numbered_line_keys` remain **diagnostics** and
do **not** determine this clause; a per-line set difference may be *reported* but may never
become a second Rule 0 gate. **`_coverage < 0.85` remains its own independent M9 failure
condition** and is not double-counted as the margin-line criterion.

### A39.2 — the cross-engine 10 % page sample, frozen

`x09` stays the **DEVELOPMENT proof of the mechanism** and may **not** be consumed as the
confirmatory qualification. A distinct canonical artifact
(`results/cross_engine_control.json`) is produced at execution time, reusing **x09's already
frozen matching rule and thresholds** — document ≥ **0.95**, every sampled page ≥ **0.75** —
with **no second geometry comparator invented**.

```
scope     = per document (independent sampling)
identity  = (document_sha256, page_number)
seed      = 20260807
namespace = "cross-engine-page"

k = max(1, ceil(0.10 * page_count))
rank ascending by sha256("cross-engine-page|20260807|<canonical page identity>"), take first k
```

No RNG and no caller-order dependence. **`max(1, …)` is load-bearing**: the frozen consequence
is per-document, so a document with no sampled page could never acquire the qualification the
rule attaches to it.

**Never decision-blocking.** A failure labels results `PDFIUM-CONDITIONED FRAME` and changes no
architecture outcome and no gate (A27.6).

### A39.3 — the control sources must be realized

N-A (8 modified-PDF regions), N-B (8 XML-corroborated unambiguous-heading regions) and N-C (4
heading-free regions) are **already frozen by PRE-REGISTRATION §5.6** and are **all Rule 3
blockers**. Their *existence* was never an open question; their **committed source fixtures**
are what is missing. **No confirmatory holdout material may supply a control** — DEVELOPMENT
and purpose-built synthetic material only.

A committed manifest (`results/control_fixtures.json`) must carry, per control stimulus:
control kind, variant, source type, source document/fixture identity, source sha256, page,
committed bbox/region, expected control truth, and the construction recipe where the material
is modified or generated.

**N-A** — 8 regions, sources selected **deterministically before mutation**, with a balanced
frozen assignment over the 8 ranked items: `index mod 3` → `0 DELETE_ONE_WORD`,
`1 WELD_TWO_WORDS`, `2 PULL_HEADING_TO_BODY_SIZE`, realizing **3 delete / 3 weld / 2 size**.
**Exactly one mutation per region**, its target deterministic and recorded, exact before/after
printed strings recorded for delete and weld, and the size control using the **source
document's already-derived body size** rather than an invented constant. **N-A truth comes from
the committed mutation recipe, never from H or X's output on the modified PDF.**

**N-B** — 8 real DEVELOPMENT regions whose printed heading is independently corroborated by
paired GPO XML, expected text recorded **before** adjudication, selected deterministically from
the complete eligible set (namespace `nb-source`, seed `20260807`) rather than by picking the
best-looking eight. The gate consumes **only** the truth the frozen N-B statement supports.

**N-C** — 4 heading-free regions; purpose-built body-only synthetic regions are preferred
because they make "no heading" **constructionally certain**. They pass through the **same
renderer and blinding path** as real items, and control status may not leak.

### A39.4 — G6, execution readiness must know the controls exist

A readiness condition **G6** requires the committed control-fixture manifest to exist and
validate before an execution marker may be authorized: **8 N-A, 8 N-B, 4 N-C**, all source
hashes present, all source files/recipes committed, **no confirmatory holdout member used**,
all control identities unique, expected truth present. A malformed or missing control set keeps
**EXECUTION FORBIDDEN**. This is **not** folded into G5's file-existence check.

### A39.5 — G5 must be truthful, not stable

G5's denominator tracks the **actual result-bearing surface**. `s1_control.py` and the
confirmatory cross-engine producer are result-qualifying producers and belong in it. **The
point of G5 is truthful completeness, not a stable numerator**, so a denominator larger than 11
is correct if the surface is larger.

### Population and boundary

DEVELOPMENT + SYNTHETIC only. No holdout opened, nothing adjudicated or scored, no architecture
decision, no confirmatory or scoring artifact, and no execution marker.

### A39.3 STOP — `PULL_HEADING_TO_BODY_SIZE` is observationally invisible to the frozen task

**The liveness check A39.3 required was run before freezing the two size controls, and it
fails. Reported, not worked around.**

Measured over the **complete eligible DEVELOPMENT population** — every `account` anchor on the
documents whose size bands are derivable:

| document | account anchors | uppercase | size bands |
|---|---:|---:|---|
| `114-hr-2029/4` | 31 | **31 / 31** | body 14.0, heading 11.2 |
| `118-hr-8752/1` | 20 | **20 / 20** | body 14.0, heading 11.2 |
| `119-hr-1/1` | 0 | — | `derive_size_bands` → `None`, so no account anchors |
| **total** | **51** | **51 / 51, zero exceptions** | |

GPO sets account headings in the **sub-body** band: 11.2 pt against a 14.0 pt body, so the
mutation `11.2 → 14.0` makes the heading the **same size as body text**, not smaller-to-larger.

**Why that changes nothing the adjudicator records.** `adjudicator_prompt.md` defines a heading
disjunctively — *centered, **or** set in capitals, **or** set in italic, **or** set in a
distinctly larger or heavier face, **or** otherwise typographically separated*. Every one of
the 51 candidates is **in capitals**, and the mutation does not change that. The line therefore
remains a heading under the frozen definition. The prompt collects `text`, `role`, `parent`,
`start_physical_line`, `start_x_px` — **it never asks for font size**. So the expected oracle
answer is **identical before and after**: same heading present, same text, same role, same
parent.

A control whose expected answer cannot move cannot distinguish an oracle that sees the failure
class from one that does not — which is the *only* thing N-A exists to establish.

**Per A39.3 this STOPS.** The two `PULL_HEADING_TO_BODY_SIZE` slots are **not** counted as
realized N-A controls. No substitute mutation was invented and the prompt was **not** changed;
both would require a reviewer ruling. **Consequence:** N-A cannot reach 8, so the manifest
cannot be completed and **G6 cannot pass**, which is why A39.3/A39.4 remain outstanding below
rather than being delivered partially.

### Realized so far, and what is NOT built

**Done** — A39.1 (Rule 0 margin clause), A39.2 (page sampling + the confirmatory cross-engine
producer), A39.5 (G5 corrected 11 → 13). `x15` **67/67**.

**A39.3 and A39.4 are now COMPLETE**, under A40's revised control contract:

| | |
|---|---|
| **A39.3** control sources | realized — 8 N-A (3 delete / 3 weld / 2 **split**), 8 N-B, 4 N-C, in `results/control_fixtures.json`. The original size clause remains **STOPPED** and is superseded by A40, not quietly replaced |
| **A39.4** G6 | implemented in `x04`, **separate from G5**, validating counts, allocation, recomputed hashes, expected truth, identity uniqueness and the absence of confirmatory provenance |

`x23` **21/21**, **G6 PASS**. The A39.3 STOP above is preserved as the record of why
`PULL_HEADING_TO_BODY_SIZE` was retired.

---

## A40 — SUBSTANTIVE. Replace N-A's dead size mutation with a live boundary control

```json
{"id": "A40", "class": "SUBSTANTIVE",
 "commits": ["31b19c7", "c6ccd4e", "c8df8cf", "d2f7eea", "a071216", "3c072a5", "fcc88d0",
             "9606a6e", "767abe9", "3f49fed", "2c06749", "84e3672", "0f89e9e"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/build_oracle.py", "probes/control_fixtures.py",
                   "probes/x04_freeze_check.py", "probes/x23_control_fixtures.py",
                   "probes/x24_xml_source_bridge.py", "probes/x25_bridge_validation.py",
                   "probes/x26_control_oracle.py", "probes/xml_sources.py"],
 "supersedes_text_in": "PRE-REGISTRATION 5.6 N-A's 'one heading's size pulled into the body band' ONLY; A39.3's PULL_HEADING_TO_BODY_SIZE and its two scheduled slots; and the M1 control mapping insofar as it names N-A",
 "status": "IMPLEMENTATION COMPLETE + FROZEN -- approved by external review. F1-F8 all implemented and falsified: bridge independently validated (A40.9), parenthetical ruled structurally then WITHDRAWN on source authority (A40.10/A40.12), F1/F2/F5/F6 (A40.11), placement repaired (A40.13), PDF bytes deterministic (A40.14), F3/F4 replay + committed 20-control oracle probe (A40.15), G6's own two gaps closed under freeze verification (A40.16). G6 PASS carries its full section-13 meaning"}
```

`affects_scoring_rule` is **true**: N-A is part of the frozen negative-control / Rule-3
machinery, so changing which perturbation satisfies that blocker changes what the gate tests.

**A40 is permitted because the pre-execution liveness control falsified the previous mutation
before any confirmatory material was opened.** The A39.3 STOP is **preserved as historical
evidence** and is not rewritten as though the size control never existed. `PRE-REGISTRATION.md`
itself is **not edited**; the amendment lives here.

### A40.1 — three LIVE mutation classes

```
N-A total = 8        index mod 3:  0 -> DELETE_ONE_WORD
                                   1 -> WELD_TWO_WORDS
                                   2 -> SPLIT_ONE_WORD

realized: 3 DELETE_ONE_WORD · 3 WELD_TWO_WORDS · 2 SPLIT_ONE_WORD
```

**Exactly one mutation per N-A region.** `PULL_HEADING_TO_BODY_SIZE` is **RETIRED**: the
complete eligible DEVELOPMENT census (51/51 account headings uppercase) showed a size-only
alteration cannot change any field the frozen task records, and a control whose expected answer
is identical before and after cannot establish liveness. **No font-size field is added to the
prompt and the heading definition is unchanged.**

### A40.2 — `SPLIT_ONE_WORD`

One ordinary visible word boundary is inserted **inside one existing alphabetic word**:
`"SALARIES AND EXPENSES"` → `"SALA RIES AND EXPENSES"`. It removes no character, adds no
non-space character, changes no other boundary, preserves case, changes no punctuation, and
touches no other heading. **The non-space character sequence is identical before and after**,
and the boundary vector changes at **exactly one position, `0 → 1`**. The exact inserted space
and resulting printed string are committed as truth **before** adjudication, and **no
architecture output** determines the target or the truth.

### A40.3 — eligibility is frozen BEFORE ranking

A candidate must: be a known real `account` heading under independently established source
truth; be **non-holdout**; have enough words for DELETE and WELD; contain at least one
alphabetic token of length **≥ 6** for SPLIT; and have a renderable source region. Eligibility
is applied **before** ranking and **before** any mutation is assigned, so no variant-specific
convenient source can be chosen afterwards. **Fewer than 8 eligible → STOP**; the criteria are
not relaxed.

Ranking: namespace **`na-source`**, seed **`20260807`**, first 8, then the frozen
index-mod-3 schedule. **No H or X output participates** in eligibility, ranking or targeting.

### A40.4 — deterministic mutation targets

An *alphabetic token* is a maximal contiguous run of alphabetic characters in the independently
recorded expected source string.

| variant | target | assertion |
|---|---|---|
| `DELETE_ONE_WORD` | longest alphabetic token, tie → earliest | non-space sequence genuinely **changes** |
| `WELD_TWO_WORDS` | first adjacent token pair separated only by whitespace | non-space **unchanged**, exactly one boundary `1 → 0` |
| `SPLIT_ONE_WORD` | longest token with len ≥ 6, tie → earliest; insert one U+0020 after `floor(len/2)`, both pieces ≥ 3 chars | non-space **unchanged**, exactly one boundary `0 → 1` |

No more visually convenient target may be chosen after rendering.

### A40.5 — liveness is proven before the manifest exists

Every realized N-A item must satisfy `expected_before != expected_after` at the
exact-transcription level, **and** its structural class must be proven independently of any
adjudicator, using **`m3_boundaries.decompose`** rather than a second boundary definition. A
deliberately dead mutation (`before == after`) must make validation **fail**.

### A40.6 — the metric-control mapping, corrected

| metric | control | why |
|---|---|---|
| **M1** heading presence | **N-B, N-C** (was N-A, N-C) | N-B supplies 8 corroborated TRUE headings, N-C 4 constructionally certain NO-heading regions — together a direct positive/negative enumeration test. **The revised N-A is not a heading-presence control.** |
| **M2** text exactness | **N-A** | the adjudicator must report the exact altered print; WELD and SPLIT must be capable of failing exactness under the frozen normalisation |
| **M3** boundary integrity | **N-A** | N-A now spans `TEXT_ERROR` (delete), `WELD`, and `SPLIT`, aligning the control with M3's already-frozen distinctions. **M3 itself is unchanged.** |

### A40.7 — the eight-finding falsification pass, and what it found

Every reviewer finding was attacked against the committed HEAD `2782140` **before** any code
changed. **All eight SURVIVED**; none was withdrawn.

| # | claim | verdict | evidence |
|---|---|---|---|
| **F1** | N-A/N-B source truth depends on H | **SURVIVES** | `control_fixtures.py:235` `run_hybrid.run`, `:240` `extract_anchors`, `:241` `anchor.kind != "account"` — all **before** the XML test at `:244`. The H anchor supplies membership, kind, text, page and line |
| **F2** | XML proves only string occurrence | **SURVIVES** | operative test is `text.upper() not in xml_text`; the manifest records a fixed prose string and no element identity |
| **F3** | G6 does not replay selection | **SURVIVES** | `x04.g6_control_fixtures()` loads the JSON and calls `validate_manifest`, which never rebuilds the eligible population, re-ranks, or re-selects |
| **F4** | G6 does not replay the mutation target | **SURVIVES** | validator checks `recipe.variant == variant` and `mutation_evidence(...).live` only; it never calls `MUTATORS[variant](expected_before)`, so a **different but still live** target passes |
| **F5** | controls are not executable through the oracle path | **SURVIVES** | 20 `StimulusSpec`s built from the manifest, then `build_oracle.build([], controls=...)` → **`KeyError: '118-hr-8752/1'`** from `frames_by_doc[spec.document_id]`. No manifest→spec adapter exists |
| **F6** | the manifest lacks the adjudication region | **SURVIVES** | N-A carries only `source_bbox`, a **single 9.5 pt heading line**; N-B carries **no bbox at all**; N-C carried none. The 8-line oracle region would still be re-derived later |
| **F7** | holdout exclusion is name-based | **SURVIVES → REPAIRED** | validator scanned provenance strings only. Now checks the **17 authoritative SHA-256** values from `holdout_membership.json`; a DEVELOPMENT-named record carrying a holdout SHA is rejected, and the control asserts the name scan does **not** fire on it |
| **F8** | the four N-C controls may be visually duplicate | **SURVIVES → REPAIRED** | rendered through the real `render_region` at 300 DPI: **all four produced the identical PNG `3f709d21…`** while their container SHAs differed. `generate_nc_pdf` ignored its `index`. Now four distinct rendered hashes |

**Feasibility established for the F1/F2 repair, so it is not blocked.** The committed GPO XML
**does** independently determine `account` truth: `<appropriations-small id="…"><header>TEXT</header>`
is GPO's own account-level element, carrying a stable element identity and the exact heading
text — 41 and 105 such elements in the two DEVELOPMENT documents. **No STOP is owed.**

Physical targeting was measured under two fail-closed rules: requiring the header text to be
unique in **both** XML and PDF yields only **5** located sources (too few); pairing the *k*
XML occurrences with the *k* PDF occurrences in document order, and **refusing the whole header
group on any count mismatch**, yields **17** — enough for both the 8-item `na-source` and
8-item `nb-source` draws.

**Outstanding: F1, F2, F3, F4, F5, F6 (N-A/N-B regions).**

### A40.8 — item 0 settled, and the F1/F2 foundation (`x24` 16/16)

**The account population is established from the committed files and GPO's own renderer, not
from naming and not from correlation with H.** Both DEVELOPMENT sources declare
`<!DOCTYPE bill PUBLIC "-//US Congress//DTDs/bill.dtd//EN">` with `bill-type="appropriations"`
— the **legacy** US Congress bill DTD, not USLM. Measured on those exact files:

| | 114-hr-2029/4 | 118-hr-8752/1 |
|---|---:|---:|
| `<account>` elements | **0** | **0** |
| `appropriations-small` | 107 | 44 |
| `header` as **attribute** | **0** | **0** (always a `<header>` child) |
| header-less (split-account money half) | 2 | 3 |

So the newer schema's `<account><header>` does **not** exist here; the account level is
`appropriations-small`, on the authority of GPO's own `bills.css` / `billres-details.xsl` as
recorded in `docs/gpo-render-conventions.md` (agency = `appropriations-intermediate`, **account
= `appropriations-small`**) with `docs/bill-structure.md` documenting the flat sibling model.
**The direction is what makes it admissible:** the XML *carries* the hierarchy explicitly and
PDF segmentation is what must *recover* it. **No STOP is owed.**

**The XML header is not the printed string.** `billres-details.xsl` applies
`translate($upper,$lower)` at this level, so 114-hr-2029 stores `Compensation and pensions`
while the page prints `COMPENSATION AND PENSIONS`. The XML establishes *which* heading and that
it is an account; the **exact printed characters are read back from the PDF** and are what every
expectation uses. Left unnoticed this would have made every N-A control unsatisfiable.

**The locator is whole-line, and that was measured.** A substring search paired only 13/105 and
4/41 because the same words occur in body prose. Requiring the heading to be the entire printed
line once its margin number is stripped gives **45/105 and 41/41, zero refusals** on
118-hr-8752. It constrains *line occupancy*, not typography — no size, case or centering test,
because classifying by those would re-implement the recognition under test.

**The order bridge is validated before it is relied on:** XML document order agrees with
physical print order with **zero inversions**, on the all-paired set *and* separately on the
independently identifiable unique-occurrence subset. Both negatives fire — a contradicted
ordering is detected, and an added occurrence refuses the **whole** group.

**The decisive control:** with `run_hybrid.run`, `run_extended.run` and
`pdf_anchors.extract_anchors` made to **raise**, the source population, N-A eligibility and the
`na-source` selected 8 are **byte-identical**, and a further check proves the sabotage bites.

**Populations after the bridge: 86 paired sources, 73 N-A eligible** — far above the 8 each
frozen draw needs, so STOP condition 17 is not triggered.

### A40.9 — the bridge, falsified on evidence independent of the pairing (`x25` 18/18)

**A40.8's ordering claim is CORRECTED, and the correction is the point.** A40.8 reported "zero
inversions … on the all-paired set *and* separately on the independently identifiable
unique-occurrence subset". The all-paired half of that is **circular**: those rows were paired
index-to-index, so the check cannot falsify the rule that produced them and a green result is
guaranteed by construction. The independent half is **n=1** in 114-hr-2029/4 (n=8 in
118-hr-8752/1), and n=1 establishes nothing about order preservation. A40.8's sentence is left
standing as the historical record; `x24` now labels that check `CONSISTENCY ONLY` in its own
output, and the licensing evidence moved to `x25`.

**What replaces it.** An anchor is admitted only if its XML identity is structural, its physical
occurrence is uniquely locatable without pairing, and neither side consults H or X:

| class | XML identity | physical identity |
|---|---|---|
| **A** | a `<header>` at ANY legacy-DTD level, text unique among all structural headings | occupies exactly one whole printed line |
| **C** | a monetary literal, unique **substring** of the reading-order text | unique substring of the printed text, on exactly one line |

Class A is the reviewer-permitted widening beyond account headings; it is what lifts
118-hr-8752/1 from 8 to 22. Class C is what makes 114-hr-2029/4 tractable at all — that document
has **3 XML-unique header texts out of 183**, because an omnibus reuses heading strings
pervasively, so structural headings alone yield **2 anchors over 138 pages** and every bracketing
test would pass vacuously. `x25` enforces a floor of 50 anchors per document precisely so that a
green bracketing result cannot be produced by an empty grid.

| | 114-hr-2029/4 | 118-hr-8752/1 |
|---|---:|---:|
| independent anchors (A + C) | **85** (2 + 83) | **111** (22 + 89) |
| anchor inversions | **0** / 84 pairs | **0** / 110 pairs |
| repeated account groups | 27 | 4 |
| bracket-DISAGREEING groups | **0** | **0** |
| refused `UNDISCRIMINATED_GROUP` | 2 | 0 |
| refused `NO_PHYSICAL_OCCURRENCE` | 3 | 0 |
| paired | 55 | 41 |

**The bracketing rule is set agreement, not nearest-neighbour.** For occurrence *k* the anchors
preceding it in XML reading order must be the **same set** as the anchors preceding it on the
page. That is strictly stronger than an interval test and it is what detects a structurally
incompatible heading interleaving in only one representation. **Discrimination is required
separately**: if two consecutive occurrences share an anchor prefix, nothing independent
separates them, so the group is REFUSED rather than paired — `(INCLUDING TRANSFER OF FUNDS)`
(n=38) and `SALARIES AND EXPENSES` (n=6).

**Three defects were found while building this, each of which had made an earlier number look
better than it was.** They are recorded because two of them presented *as* order violations:

1. **Element index is not a text position.** A child's `.tail` belongs to the parent, which sorts
   earlier, so a tree-walk coordinate manufactures inversions that are artifacts of the walk.
   Every class now shares one coordinate: character offset in the reading-order text.
2. **`\$[\d,]{7,}` absorbs a trailing separator.** `$150,000,000,` (XML) and `$150,000,000.`
   (PDF) tokenise differently, so a `find()` on the shorter form lands on a **different
   instance** — presenting as three document-order inversions that do not exist. Literals are now
   digit-delimited and uniqueness is a **substring** count in both representations.
3. **`bridge()` grouped case-SENSITIVELY while the comparator is case-insensitive.** Five texts
   in 114-hr-2029/4 carry case variants, so 33 phantom groups formed over 28 real ones and each
   split group self-refused on count mismatch. It **fails closed** — nothing wrong was ever
   paired — but it shrank the document from 55 paired to 45 and mis-labelled the loss as
   `GROUP_COUNT_MISMATCH`.

**A fourth anchor class was built, measured and REJECTED rather than patched.** "Any printed line
unique in the PDF and a unique substring of the XML" yields ~1000 anchors per document, but the
printed bill's **endorsement page reprints the long title with different line breaking**, so
front-matter fragments resolve to back-matter lines and invert against everything (2 and 3
residual inversions, all front/back matter). A class that needs a special case to stay monotone
is not independent evidence of monotony.

**All five required negatives attack the bracketing rule, not a derived summary field**: swapping
two repeated occurrences, moving one across its neighbouring anchor, adding one, removing one,
and swapping two anchors — the last both registers as an inversion *and* makes real groups refuse
with `CROSSES_INDEPENDENT_ANCHOR`, proving the corruption reaches the pairing decision.

### A40.9.1 — the three objects, and which authority decides each dimension

| dimension | provenance | authority |
|---|---|---|
| text content | **SOURCE-DETERMINED** | every rule recorded at this level is a pure case transform; none edits a character |
| punctuation | **SOURCE-DETERMINED** | as above |
| whitespace | **SOURCE-DETERMINED** | as above, up to run collapse |
| **case** | **PHYSICALLY OBSERVED** | see below |
| margin number | **PHYSICALLY OBSERVED** | GPO page furniture, stripped before comparison |

**Case is not source-determined, and asserting it from the stylesheet would have been wrong.**
`convertToNeededCase` (`billres-details.xsl:8279`) applies `translate($upper,$lower)` at
`appropriations-small` and `bills.css` small-caps it — but **those artifacts govern GPO's HTML
renderer**, and `docs/gpo-render-conventions.md` (#89) records the measurement that forces the
distinction: the CSS `em` values predict agency > body > account while the PDF measures agency ≈
account < body, because "the published PDF is typeset by GPO's separate photocomposition system,
whose point sizes do not track the HTML renderer's `em` values". The PDF prints real capitals.
So the stylesheet is authoritative for **content** and silent about the PDF's realised **case**.

`cross_check_rendering()` requires the observed whole line to equal the source-determined
expectation **under case folding alone**; a one-letter content change, a punctuation change or a
whitespace change all REFUSE, and each is exercised as a negative. This is what keeps the
independent PDF backend an *observation instrument* rather than the source of account semantics.

### A40.9.2 — TWO FINDINGS RETURNED FOR RULING; the `control_fixtures.py` swap is HELD

**Neither is a bridge contradiction, so section 1 is not a STOP.** Both change what the source
population *means*, and both are result-bearing, so the swap is not performed.

**Finding 1 — `appropriations-small/header` is not always an account name.** GPO's markup in the
MilCon division puts the account name on the **preceding `appropriations-intermediate`** and
leaves the `appropriations-small` carrying only a parenthetical qualifier:

```xml
<appropriations-intermediate><header>Military construction, defense-<enum-in-header>W</enum-in-header>ide</header></appropriations-intermediate>
<appropriations-small><header>(including transfer of funds)</header><text>For acquisition, … $1,931,456,000 …</text></appropriations-small>
```

Measured: **56 of 105** `appropriations-small` headers in 114-hr-2029/4 and 4 of 41 in
118-hr-8752/1 are purely parenthetical; **22 of the 96 paired** survive the bridge. All seven
distinct texts are GPO transfer/rescission qualifiers — `(INCLUDING TRANSFER OF FUNDS)`,
`(RESCISSION(S) OF FUNDS)`, `(TRANSFER OF FUNDS)`, `(INCLUDING TRANSFERS AND RESCISSIONS OF
FUNDS)`, `(INCLUDING TRANSFERS OF FUNDS)`, `(INCLUDING RESCISSIONS OF FUNDS)`. **This is
result-bearing now**: under the validated bridge the `na-source` draw selects
`(RESCISSIONS OF FUNDS)` **twice** and the `nb-source` draw **three times** — 5 of the 16
selected sources. **A40.3 requires a candidate to "be a known real `account` heading"**, and
A40.6 assigns N-B the job of supplying "8 corroborated TRUE headings" for M1. Excluding wholly
parenthetical headers is fail-closed and leaves 74 N-B / 61 N-A eligible, far above 8 — but it
narrows an approved predicate on a source-side text rule, so it is the reviewer's call, not an
implementation detail. **Not acted on.**

**Finding 2 — the case-grouping defect** (A40.9 item 3) is fixed in this slice because it fails
closed and its correction only *restores* records the comparator always intended to group. It is
recorded here because it changes A40.8's reported refusal counts, not because it is contested.

**Why the swap is held rather than performed under a stated assumption.** Swapping now would
commit a manifest in which 5 of 16 control sources are not account headings, and the manifest is
the artifact every later slice (F5, F6, G6) is verified against. The reviewer's own instruction
to stop before the swap was given for exactly this class of question. **RESOLVED by A40.10.**

### A40.10 — the parenthetical question, ruled STRUCTURALLY

**No lexical rule was created.** Nothing reads the heading text — not its first character, not
its words. The admission predicate is source POSITION: the legacy DTD models the appropriations
hierarchy as flat siblings under `<title>` (`docs/bill-structure.md`), and exactly two parents
occur in this corpus.

| ancestor path | paired records | admitted-position accounts |
|---|---:|---:|
| `bill/legis-body/title/appropriations-small` | 79 | **79** |
| `bill/legis-body/title/section/appropriations-small` | 17 | **0** |

`title/section/appropriations-small` carries **17 paired records and not one** that shares a
position with any admitted account, so it is a different source-defined structural role.
`ACCOUNT_PARENT_ELEMENT = "title"`; the refusal is `NOT_ACCOUNT_POSITION`.

**The corpus proves this is not a disguised parenthetical filter**: five parenthetical-headed
records sit at the admitted position and REMAIN ELIGIBLE — `(INCLUDING TRANSFER OF FUNDS)` at
118-hr-8752/1 p11 is in the realized **N-B 8**. 114-hr-2029/4's `(RESCISSIONS OF FUNDS)` records
are excluded because they hang off `<section>`, not because of how they read.

**Applied AFTER the bridge, never before.** Two 114-hr-2029/4 groups mix `section`- and
`title`-parented records; filtering the enumeration would drop XML occurrences whose lines are
still printed, break the equal-count test and refuse the whole group.

### A40.11 — F1/F2, F6 and F5 landed; F3/F4 OUTSTANDING

**`control_fixtures.py` no longer uses H for any result-bearing source truth.** The chain is
committed XML → structurally identified `appropriations-small` under `<title>` → approved bridge
→ independently observed printed line. No `run_hybrid`, no `run_extended`, no `extract_anchors`
on the path. The three objects stay separately named on every record (`xml_source_text`,
`expected_rendered_heading`, `expected_before`/`expected_text`).

| | 114-hr-2029/4 | 118-hr-8752/1 |
|---|---:|---:|
| XML account records | 105 | 41 |
| independent anchors / inversions | 85 / **0** | 111 / **0** |
| bridge paired | 55 | 41 |
| refused `UNDISCRIMINATED_GROUP` / `NO_PHYSICAL_OCCURRENCE` | 2 / 3 | 0 / 0 |
| refused `NOT_ACCOUNT_POSITION` | 17 | 0 |
| **admitted sources** | **38** | **41** |

**79 admitted / 66 N-A eligible**, far above the 8 each frozen draw needs.

**F6** commits the exact adjudication region under the already-frozen rule —
`build_frames.REGION_SIZE`, non-overlapping, `ordinal = start // size`, A33's zero-padding union
— applied to the independently observed lines, so the crop size stays frozen while H/X stay out
of the geometry. Each record carries the canonical XML source identity, source PDF SHA, page,
heading line index and bbox, region ordinal, `region_bbox_pdf_points`, the ordered line mapping
and the expected rendered heading. Nothing downstream re-derives a boundary or searches for a crop.

**F5** is done and measured: all **20 controls execute through the real `build_oracle`** — the
same `load_prompt`, `render_region`, canonical identities, `blind_id`, `presentation_order`,
`leakage_report` and `verify_join`. 20 stimuli, 20 blind ids, both routes on every control, **0 in
C, 0 in D, 0 C-audit, 0 R1**, blind records exactly `{id,image,question}`, leakage clean, join
clean, four N-C PNG hashes still distinct. `x21` **117/117**, so ordinary C/D/C∩D/C-audit/R1
semantics are unchanged: every addition is additive (`frames=()` for a control, and
`select_c_audit` / `plan_r1_repeats` already excluded `control_kind`).

Byte reproducibility holds: 13 artifacts, **0 changed** on a second complete build.

**OUTSTANDING, AND G6 DOES NOT YET CARRY ITS SECTION-12 MEANING.** `validate_manifest` still
checks a self-consistent manifest; it does **not** yet replay source enumeration, the bridge,
eligibility, ranking or the 8/8 selection (**F3**), and does **not** yet recompute
`MUTATORS[variant](expected_before)` to prove the exact deterministic target (**F4**). The x25
PDF-side anchor negatives and the committed end-to-end 20-control probe are also not yet in the
tree. A green G6 at this commit means "coherent and internally verified", NOT "independently
replayed", and must not be read as A40 complete. **A40.12 WITHDRAWS this caveat as insufficient
and makes the gate itself red.**

### A40.12 — `ACCOUNT_PARENT_ELEMENT` FALSIFIED AND WITHDRAWN; G6 made RED; a new STOP

**A40.10's parent rule was wrong, and its justification was the defect.** It rested on corpus
correlation — "17 records sit at `title/section/appropriations-small` and no admitted account
does" — which is observational clustering, not a source-semantic rule. Tested against the
authorities, all key on the TAG and none conditions on the parent:

| authority | what it says | bearing |
|---|---|---|
| `docs/bill-structure.md`, *Caveat: the level tags are convention* | the bill DTD gives `appropriations-major/intermediate/small` **identical content models and no defining comments**, verified against `usgpo/bill-dtd` | a content model that does not vary cannot license a parent distinction, and none is declared |
| `docs/bill-structure.md` level table | `account` = "**leaf**, tag `appropriations-small` (and the default)" | the level is keyed on the tag; the same section states "the tag is authoritative" |
| `docs/gpo-render-conventions.md` casing table; `billres-details.xsl:8279` `convertToNeededCase` | the branch is `<xsl:when test="ancestor::appropriations-small">` | an ELEMENT-TYPE ancestor test with **no parent predicate**, so GPO's own renderer applies the identical template under `<title>` or `<section>` |
| `bills.css` | one class per appropriations level | styled per level, not per parent |

**Decision: REMOVED.** No authoritative source distinguishes a section-parented
`appropriations-small`, so all 96 bridged records are account sources. Restoring an exclusion
needs new AUTHORITY, not a new correlation. Populations: **96 admitted / 83 N-A / 96 N-B**, and
the 3/3/2 N-A allocation is unchanged.

**G6 is now RED by machine, not by prose.** `validate_manifest` emits
`SOURCE_REPLAY_NOT_IMPLEMENTED` (F3) and `MUTATION_TARGET_REPLAY_NOT_IMPLEMENTED` (F4) until the
replays land. `x23` asserts the defect set is EXACTLY those two, so a real defect cannot hide
behind them, and separately asserts G6 is not green.

### A40.12.1 — STOP: one selected N-A has no usable committed region

Restoring the full population exposed a real defect the narrowed population had hidden. Measured
on the rebuilt fixtures, over the GENERATED PDF:

| # | page | variant | `expected_before` on page / in region | `expected_after` on page / in region |
|---:|---:|---|---:|---:|
| 1 | 126 | WELD | 1 / **0** | 1 / 1 |
| 2 | 21 | SPLIT | 2 / **0** | 1 / 1 |
| **6** | **23** | **DELETE** | 0 / 0 | 1 / **0** |

Items 1 and 2 are **not** defects: the surviving original occurrences lie OUTSIDE the committed
adjudication region, and the contract is region-scoped. `x23`'s page-scope check is stricter than
the frozen contract, which is what surfaced them.

**Item 6 IS the STOP.** `COMPENSATION AND PENSIONS` on page 23 renders its mutated heading
OUTSIDE its own committed region, so the stimulus would not contain the mutation the control
exists to test. Suspected cause, **not yet confirmed**: the region bbox is computed from the
ORIGINAL page lines while `generate_na_pdf` redacts and redraws at `(rect.x0, rect.y1)` with
`fontsize = rect.height`, so where the heading is the last line of its 8-line window the redrawn
descender can fall below the region's lower bound. **It must not be repaired by loosening the
region or re-selecting a more convenient source** — either would be choosing the population that
gives nicer fixtures, which A40.12 has just finished removing. **CLEARED by A40.13.**

### A40.13 — the fixture-placement repair (STOP A40.12.1 CLEARED)

**The frozen population, ranking, region and `REGION_SIZE` were not touched.** The defect was in
`generate_na_pdf`, which took BOTH placement facts off the line's bounding box:

| | box-derived (old) | independently observed | error |
|---|---|---|---|
| baseline | `rect.y1` = 166.339 | span origin y = **163.000** | **+3.339 pt low** |
| font size | `rect.height` = 14.0 | span size = **10.8671** | **~29 % oversized** |

The 14.0 comes from a **trailing whitespace span at a different size** which inflates the line box
without inking anything (6 spans on that line; five inked at 10.8671, one space at 14.0). N-A #6 is
line **0** of its window, so the region's top edge *is* the line's top edge and the oversized glyphs
escaped **upward** by 0.742 pt — not the descender originally suspected.

**Preserving the baseline alone was measured insufficient** (+0.782 pt): Times-Roman's ascender is
**1.0530**, so 1.0530 × 10.8671 = 11.44 pt against 10.661 pt of room. The rule is therefore
arithmetic over measured facts, identical for every control:

```
size = min(source span size, above / font.ascender, below / -font.descender)
```

drawn at the observed span origin and fitted inside the **source line box** — a subset of the
region, so it holds at any position in the window. No per-heading constant, no search, no
reselection. All eight N-A satisfy `after_in_region == 1`, `before_in_region == 0`, each on its
intended physical line.

### A40.14 — PDF byte determinism: root cause found, and the /ID-only claim falsified first

**ROOT CAUSE: save-time `/ID` handling, and nothing else.** Masking `/ID` alone made two differing
outputs **byte-identical across their whole 537 KB**, so the explanation was falsified before being
acted on. Two save behaviours combined, and only both together explain what was seen:

| behaviour | consequence |
|---|---|
| pymupdf writes a **random** `/ID` whose serialized length is **not constant** — measured spans of **69 and 73** bytes on one fixture | `canonicalise_pdf_id` padded to whatever span it found, so file length followed the random id (537524 vs 537528). This is the intermittent, arbitrary-fixture difference. |
| setting the trailer id **without `no_new_id=True`** is silently half-undone — the save replaces the SECOND element | the earlier `xref_set_key`-only attempt looked correct and was not |

Measured, 40 builds per variant: old path **2** distinct SHAs · `no_new_id` alone **1** · fixed id
alone **40** · **fixed id + `no_new_id=True` → 1**.

**The repair is native and structural**: derive a deterministic `/ID` from the output basename, save
with `no_new_id=True`, and **delete `canonicalise_pdf_id`** rather than keep post-save byte surgery
beside it. Nothing rewrites a saved PDF.

Falsified across **12 conditions × 12 fixtures** — same-process repeats, read-only opens of every
fixture interleaved, randomized build order, fresh subprocesses — **one SHA per fixture**. The
earlier "opening a PDF perturbs the next build" note was a **misattribution**; the variable was
always the random `/ID`.

### A40.14.1 — the x23 occurrence-scope correction

The page-wide `expected_before` assertion was **stricter than the frozen region-scoped contract**
and failed fixtures that are correct, because GPO legitimately repeats a heading elsewhere on the
same page and such a duplicate is a different occurrence the adjudicator never sees. It is now
gated on the target region, with three live controls: **NEGATIVE A** (an original inside the region
is detected), **NEGATIVE B** (a mutation absent from the region is detected), **POSITIVE** (a
fixture whose original repeats elsewhere still passes), plus a diagnostic proving the
duplicate-elsewhere case is actually exercised rather than hypothetical.

**Still outstanding, and G6 stays RED for exactly this**: F3 and F4. `x23` **35/35**, `x24`
**16/16**, `x25` **18/18**; a double run over **39 artifacts changed 0 bytes**. **CLOSED by A40.15.**

### A40.15 — F3 and F4 exist; G6 is GREEN on the whole section-13 contract

**The two defects are gone because the replays were built, not because the flags were flipped.**
`SOURCE_SELECTION_REPLAY_IMPLEMENTED` and `MUTATION_TARGET_REPLAY_IMPLEMENTED` remain as named
switches precisely so a future slice that has to disable a replay makes G6 go RED for that reason.

**F3.** `validate_manifest` rebuilds the entire selected population from committed primary inputs
— XML structural enumeration, the approved bridge, every refusal, N-A/N-B eligibility, canonical
identities, both deterministic rankings, the selected 8/8 and the 3/3/2 assignment. **The manifest
is the object under test, never an input**: nothing on this path reads `control_fixtures.json`, a
generated PDF, the oracle key, or H/X output. Counts are recomputed rather than hardcoded, so a
corpus change surfaces as a disagreement instead of a stale constant.

**F4.** Expectations come from the **replayed** source. `expected_before` is the independently
replayed rendered heading and `variant` is the frozen `index mod 3` schedule — neither is read
from the record being checked. That is what stops a manifest rewriting `expected_before`,
`expected_after` and `mutation_recipe` *together* and remaining self-consistent; that exact case
is exercised and rejected with `MUTATION_INPUT_MISMATCH`.

| falsification | reason reached |
|---|---|
| alternate eligible N-A / N-B; 8-8 kept, one substituted | `SOURCE_SELECTION_MISMATCH` |
| same text, wrong XML structural identity | `SOURCE_IDENTITY_MISMATCH` |
| same text, wrong physical occurrence | `PHYSICAL_SOURCE_MISMATCH` |
| right members, deterministic order broken | `SOURCE_SELECTION_ORDER_MISMATCH` |
| live-but-different DELETE / WELD / SPLIT target | `MUTATION_TARGET_MISMATCH` |
| recipe metadata altered, `expected_after` correct | `MUTATION_RECIPE_MISMATCH` |
| self-consistent rewrite of before/after/recipe | `MUTATION_INPUT_MISMATCH` |

None of these is a stale hash, a missing file or bad JSON. **Each alternative mutation is asserted
LIVE before its rejection is asserted** — otherwise the negative would only re-prove that dead
mutations fail. One trap worth recording: the first DELETE alternative picked "the last token",
which in `RESEARCH AND DEVELOPMENT` *is* the token the frozen rule picks, so the negative silently
tested nothing. It now selects relative to the frozen target.

**F5 is now committed evidence (`x26`), not a manual run**: 20 controls through the real
`build_oracle` — 20 identities, 20 renders, 20 blind ids, blind keys exactly `{id,image,question}`,
both routes on all 20, **0 in C / D / C-audit / R1**, leakage clean, join clean, four distinct N-C
images, and the shuffled-binding negative (valid truth on the wrong valid control is rejected
**while both records stay well-formed**, so it cannot pass for the wrong reason).
**G6 now requires that evidence**, so its green covers the oracle half of section 13 rather than
the manifest half alone.

**A40.14 §1**: the deterministic trailer `/ID` is proven **non-semantic** by counterfactual — a
renamed copy carries a different id, and neither source selection nor any control identity moves.

`x15` 64/64 · `x16` 27/27 · `x17` 56/56 · `x21` 117/117 · `x22` 52/52 · `x23` 46/46 · `x24` 16/16 ·
`x25` 19/19 · `x26` 12/12. Double run over **40 artifacts: 0 changed**.

### A40.16 — freeze verification found TWO real gaps in G6 itself, both closed

The freeze pass was narrowly about whether **G6 deserves to be trusted**. It did not, in two ways.

**Gap 1 — the x26 evidence certified only itself.** `_oracle_integration_defects` read the
artifact's own `failures`, `n_controls` and `counts`. Measured: an x26 result whose every certified
value was replaced with garbage (`nc_png_sha256` = `deadbeef`×4, `frame_counts` nonsense, a fourth
blind key) **still left G6 green**, because `failures: []` was all G6 read. A stale PASS produced
for a *different* valid control state would have been accepted identically — the precise
false-green shape A40.12 was opened to remove.

**Closed by a shared authoritative digest.** `build_oracle.control_oracle_input_digest(manifest)`
covers every record's truth-bearing digest (identity, kind, variant, source/generated SHA, expected
truth, mutation recipe, committed region), the adjudicator prompt SHA, the frozen route vocabulary
and the control join fields. `x26` records it; **G6 recomputes it from the manifest and prompt on
disk** and refuses on disagreement (`ORACLE_EVIDENCE_STALE`). The renders are a deterministic
function of those inputs, so binding the inputs binds the images without G6 re-rendering.

**Gap 2 — N-B private truth was never replayed.** Swapping the expected headings between two valid
N-B controls left **both x26 and G6 green** once x26 was regenerated: each record stayed
well-formed, and `verify_join` compares the key against the manifest, so with both derived from the
same mutated manifest it could not see the swap. Only the independently replayed source can, and
F4 covered N-A only. N-B's expected heading **is** the rendered heading of its own source
occurrence, and that is now asserted (`MUTATION_INPUT_MISMATCH`).

**The falsifications, after the repairs:**

| condition | result |
|---|---|
| G6 run with `run_hybrid.run` / `run_extended.run` / `extract_anchors` raising, replay cache cleared | **0 defects**, same 96 / 83 / 96, 8/8, 3/3/2 |
| each sabotaged entrypoint invoked directly | raises `AssertionError` |
| well-formed N-B truth swap, x26 evidence left stale | `ORACLE_EVIDENCE_STALE` |
| …and after regenerating x26 against that state | still fails, `MUTATION_INPUT_MISMATCH` |
| x26 reporting its own binding negative as failed | `ORACLE_INTEGRATION_NOT_VERIFIED` |
| inputs restored | G6 **0 defects**, x26 rc 0 |

Clearing `_REPLAY_CACHE` before the sabotage run is load-bearing: a cached population computed
before the monkeypatch would have been returned without re-executing the source path, and the
control would have passed while proving nothing. **Now committed as a regression — see below.**

### A40 post-freeze bookkeeping — `84e3672` and `0f89e9e`

**Post-freeze REGRESSION COVERAGE ONLY. No methodology, population, bridge, selection, fixture,
mutation rule, oracle contract, scoring rule or decision rule changed, and no result-bearing
contract changed.** Declared here mechanically because both commits touch protected `probes/*.py`
already named in `files_touched`; **no A41 is opened**, because neither commit amends anything.

- **`84e3672`** — `x04`'s F9 deletion probe gains `--full-history`. A latent gate defect that only
  surfaced once the study merged: path-limited `git log` applies history simplification, so at the
  merge commit the orphan PDF is absent from both the result and the first parent, the merge is
  TREESAME to parent 1, and traversal never enters the side branch that recorded the deletion.
  F9 then called a correctly-declared deletion "neither exists nor was deleted". Measured on the
  merged tree: simplified → empty, `--full-history` → `3d3e3fc`, the commit A6/A18 already
  declare. The ledger was right; the probe's traversal was wrong. This restores an already-frozen
  invariant rather than changing one.
- **`0f89e9e`** — `x23` gains the three A40 freeze-verification falsifications that had only ever
  been run ad hoc: H/X sabotage through the **actual** G6 path (with a control proving a warm
  `_REPLAY_CACHE` would otherwise mask it), stale `x26` evidence rejected via
  `ORACLE_EVIDENCE_STALE`, and current-but-wrong `x26` evidence still rejected via
  `MUTATION_INPUT_MISMATCH`. Each previously caught a real false green, so leaving them
  uncommitted meant a reintroduced defect would have gone unnoticed. `x23` 55/55.

### Population and boundary

DEVELOPMENT + SYNTHETIC only. No holdout opened, nothing adjudicated or scored, no architecture
decision, no confirmatory or scoring artifact, and no execution marker.

---

## A41 — SUBSTANTIVE. `score_metrics` implements the already-frozen §6 and §8 contracts

```json
{"id": "A41", "class": "SUBSTANTIVE",
 "commits": ["b82bb2b", "f5d6171", "bd543dc", "7d34796", "64ba7a4", "33f98bd", "70ab8e0"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/score_metrics.py", "probes/x27_score_metrics.py"],
 "supersedes_text_in": "none -- NO PREVIOUSLY FROZEN rule is changed. A41 makes previously UNSPECIFIED scorer ranges and operationalizations executable, before any confirmatory execution exists",
 "status": "IMPLEMENTATION COMPLETE; R1-R9 ALL RULED AND IMPLEMENTED -- no reading remains open and no result-bearing factual gate is unowned. `decide_architecture.py` remains UNSTARTED and G5 is intentionally incomplete for it alone"}
```

**Why `affects_scoring_rule` is `true` while `supersedes_text_in` is `none`.** These are different
questions and this amendment keeps them apart, as A31 did — but the distinction is **not** "no
scoring or statistical rule is introduced". It is:

> **No PREVIOUSLY FROZEN rule is changed.** Every metric, denominator, threshold and normalisation
> the scorer applies was fixed by §6, §8, A19–A24, A27, A28 and A36–A39 before this component
> existed, and none of them is amended, reinterpreted or relaxed here.
>
> **A41 DOES make previously UNSPECIFIED scorer ranges and operationalizations executable** — and
> pins result-bearing behaviour the frozen text left open. R6 fixes how R1's agreement is computed;
> R8 fixes how a control verdict is decided; R9 fixes which quantities §8's pairing covers. Those
> are new *operationalizations*, not new *rules*, and the distinction only holds because every one
> was settled **before any confirmatory output existed**, which is the condition that makes
> pre-execution amendment legitimate at all.

**A41.2 records all nine places the frozen text had to be read or ruled — R1 through R9.** Four
move a reported number: R1's §8 event evidence, R2's M7 threshold, and **R6 and R9, which were
raised as STOPs and ruled by review rather than chosen here**. R8 was reported as an unowned factual
gate and is likewise now ruled and implemented. Filing `affects_scoring_rule: false` would
understate what a reviewer approved. **Nothing was smuggled: every reading is recorded, and the ones
that could decide a gate were escalated first.**

### A41.1 — what was implemented, and what it calls rather than restates

`score_metrics.py` is a pure consumer of committed artifacts: frames, `oracle_key`,
`oracle_adjudicated`, `results/cross_engine_control.json`, `results/s1_control.json`, and the
committed membership's stratum labels. It opens no PDF, runs no arm, re-runs no clustering or
anchor recognition, performs no adjudication, discovers no file on disk, and takes **no**
architecture decision. `x27` asserts the import graph from the AST rather than from a substring
scan, and separately scores a payload built from **JSON alone** to show no live object is needed.

Where a frozen rule already had an executable owner, the scorer **calls** it:

| quantity | owner called |
|---|---|
| M0a / M0b / M0-any / M0b_defined / both_absent | `neutral_identity.m0` (A22/A23) |
| M3 boundaries and the heading-level outcome | `m3_boundaries.heading_outcome` (A3/A4/§6.3) |
| M2's normalisation | `xml_sources.normalize` (§6.2) |
| M5's role coarsening and UNSCORABLE rule | `methodology_contracts.m5_*` (A36.7) |
| §4.5 adequacy | `methodology_contracts.filter_keys` / `adequacy_occurrences` / `adequacy` |
| §8 zero-event closed form | `methodology_contracts.zero_event_upper_bound` |
| §8 supplementary bootstrap | `methodology_contracts.section8_document_bootstrap` (A38.10) |
| Rule 0's margin-line clause | `methodology_contracts.margin_line_loss` (A39.1) |
| the occurrence-level join | `build_oracle.resolve_adjudicated_occurrence` (A38.7) |
| the adjudicated encoding | `build_oracle.validate_adjudicated` (A38.7) |
| which answer each estimand reads | `build_oracle.PURPOSE_ROUTE` (A36.4) |
| the cross-engine verdict and its thresholds | `cross_engine_control.json`, from `X09.gate` (A39.2) |

**The one quantity implemented here is the general one-sided Clopper–Pearson upper bound**, which
A27.5 assigns to `score_metrics` and which `methodology_contracts` deliberately does not carry. It
is a fixed-iteration bisection on the binomial CDF, so the bound is reproducible bit for bit; the
**zero-event case delegates to the frozen closed form**, and a control requires the general path to
agree with `1 − 0.05^(1/N)` at k = 0 for N ∈ {1, 14, 600}. §8.1's own fixture reproduces exactly:
**0.1926 on 14 documents against 0.00498 on 600 headings, a factor of 39**.

**Malformed or incomplete input REFUSES.** Fifteen explicit refusal classes, each because the
alternative — skipping the record — moves a denominator with nothing to show for it. The scorer
also **recomputes** the committed line-level predicates from `neutral_identity`'s own rules and
refuses on drift, and refuses a frame whose committed coverage floor is not production's 0.85.

### A41.2 — R1–R9, every one ruled

**All nine are settled. Nothing here is open.** R1, R2 and R7 are approved as implemented; R3 and
R4 are reporting shape; R5 is closed as a channel; **R6, R8 and R9 were STOPs or reported gaps and
are now RULED and implemented**. None invents a threshold: every number is §5.6's, §6's or §8's.

| ruling | subject | state |
|---|---|---|
| R1 | §8's event evidence | APPROVED — `ANCHOR_DISCORDANCE` |
| R2 | M7's threshold | APPROVED — §6's ≥ 3, not an open choice |
| R3 | recall's denominator on an A30 refusal | reading — stays in, sensitivity secondary |
| R4 | C / D reported separately | reading — never pooled (A36.3) |
| R5 | the R1 scalar channel | CLOSED — parameter removed |
| **R6** | **R1's computation** | **RULED — union denominator, exact text, fine role, per-route micro-average** |
| R7 | the M4 parent sentinels | APPROVED as repaired |
| **R8** | **the N-A/N-B/N-C verdicts** | **RULED and IMPLEMENTED in the scorer** |
| **R9** | **§8's paired-quantity scope** | **RULED — the two numeric M9 bases, per population, never pooled** |

| # | where the frozen text stops | reading taken | rejected, and why |
|---|---|---|---|
| **R1** | §5's §8 block names the event *"per DOCUMENT: has ≥ 1 heading-level H/X discordance"* without naming the evidence | **any region whose emitted `Anchor` sets differ** (`ANCHOR_DISCORDANCE`). `Anchor` equality is whole-value — page, line, kind, text, division — so a heading either arm missed, placed, classed or read differently makes the sets differ. That is §8.2's *"produced identical heading output"*, it needs no oracle, and the predicate `H ≠ X` is symmetric | the **adjudicated** heading outcome, which would make §8's numerator a function of the D-frame draw and the adjudication budget, i.e. condition the estimand on the sample; and the **line-level** M0 predicates, which are not heading-level and would answer a different question under §8's name |
| **R2** | §6's M7 row says *"≥ 3 single-character tokens"* | **§6's threshold, on the emitted anchor text** (A38.1's input). The longest run is recorded beside the count as a diagnostic | — |

> **REVIEWER RULINGS, recorded.**
>
> **R1 — APPROVED** as implemented: `ANCHOR_DISCORDANCE`, i.e. emitted whole-`Anchor`-set
> disagreement. Not to be reopened absent a concrete producer-valid falsification.
>
> **R2 — APPROVED, and it is NOT an open methodological choice.** §6 explicitly says ≥ 3
> single-character tokens and A38.1 fixes the input as emitted `anchor.text`; phase 2's
> exploratory ≥ 4-uppercase-run regex **is not authority** and was never a competing frozen
> reading. The row above is kept only to record what the implementation follows. The `x27`
> control that pins the threshold at 3 stands.
>
> **The live §5 control table has ELEVEN rows.** The earlier handoff's "12" was stale wording;
> no twelfth row is to be invented to match it. `x27` enumerates the eleven and fails if any has
> no executable test.
| **R3** | I10 fixes recall's denominator as the adjudicated enumeration, but not what to do with an adjudicated heading whose A30 geometric identity **refuses** | it **stays in the denominator** and counts as a miss — it was printed — and `n_adjudicated_unresolvable` is reported beside it. A recall figure excluding them is emitted as an explicitly **SECONDARY** sensitivity value | dropping them, which shrinks a denominator invisibly; and headlining the sensitivity figure, which would report the number the design does not license |
| **R4** | §6 fires M1 on C-regions; A36.3 makes C and D separate estimands; neither says how to lay the rows out | every heading metric is reported **per frame, per document, and pooled**, and never summed across frames. Each row carries its own denominator | pooling C and D into one denominator, which A36.3 forbids |
| **R5** | §6 gates M5 on *"R1 role ≥ 0.80"*, and A38.1 assigned the R1 agreement computation to nobody | **the channel is CLOSED**: `r1_role_agreement` is removed and §5.6's reliability is computed from the committed key and adjudications by `score_metrics.r1_reliability` | a caller-supplied float, which can assert PASS with nothing behind it |

> **R5 is CLOSED.** A caller scalar is not evidence for a result-bearing gate. `x27` asserts that
> no such field or parameter exists, so the channel cannot return unnoticed. **Ownership now sits
> with the scorer, and R6 fixes what it computes.**

### R6 — RULED. R1's computation, and why it was a STOP first

**Audited:** §5.6, §6 (M5's gate), §7.2 rule 3, A28.3, A28.4, A30.3, A36.4, A36.6, A36.7, A37,
A38.1, A38.7, `build_oracle`, `methodology_contracts`. **Frozen:** both thresholds (text ≥ 0.90,
role ≥ 0.80) and their consequences; the repeat's canonical identity, its 330 DPI, its identical
committed bbox, its inherited routes, its separately namespaced answers, and that it resolves its
**own** `start_x_px` independently (A30.3). **Not frozen anywhere:** the computation. Two of its
choices changed gate results, which is why this was raised as a STOP rather than implemented:

- **the denominator when the two answers enumerate different numbers of headings.** On the fixture
  below, `intersection` gave **1.000 (PASS)** and `union` / `primary` / `max` gave **0.667 (FAIL)**.
  R1 is a Rule 3 gate, so that is the difference between a valid comparative study and
  **`INSUFFICIENT_COMPARATIVE_EVIDENCE`**. The same fixture does the same to M5's void at 0.80.
- **per route or pooled.** A C∩D repeat is answered on **both** routes (A36.6), so one physical
  repeat yields two pairs, and pooling an AI pair with a human pair measures **inter-source**
  disagreement rather than repeat reliability — masking a failing route behind a passing one.

**The reviewer ruled both.** The ruling is recorded and implemented below; the STOP is discharged
rather than deleted, because the reason the choice needed a ruling is part of the record.

### THE RULING, as implemented

**R6.1 — denominator and matching.** The **symmetric union of the COMPLETE primary and repeat
enumerations**, under **one-to-one matching on uniquely resolved A30 occurrence keys**. It is
`|P| + |R| − matched`, never `|set(resolved keys)|`. Chosen because it is the only candidate that
counts a heading the repeat *failed to enumerate* against agreement, and enumeration instability
is exactly what §5.6 exists to detect; `intersection` is the one reading that makes an adjudicator
who silently drops headings look perfectly reliable.

| case | treatment |
|---|---|
| a uniquely resolved key appearing once on each side | one matched pair |
| a heading on one side only | denominator, no numerator |
| an UNRESOLVED adjudicated heading | denominator, no numerator |
| the same resolved key more than once on either answer | **not pairable** — those rows stay denominator-bearing disagreement evidence, and are never collapsed through a dict or matched by choosing a duplicate |

**R6.2 — text agreement is EXACT equality of the values as returned.** No `m2_normalize`, no NFKC,
no whitespace collapse, no case folding: §5.3 and the prompt require exact transcription with case
and internal spacing preserved, and M2's normalisation belongs to M2's accuracy claim. Using it
here would hide precisely the spacing instability the repeat records. `UNREADABLE` on either side is
denominator-bearing and earns no numerator.

**R6.3 — role agreement is the exact fine §5.3 role** (A36.7: *"M5 **alone** coarsens it"*).
`UNREADABLE` never agrees, **including `UNREADABLE` against `UNREADABLE`**: repeated unreadability
is an absence of evidence, and it is the one answer an adjudicator can always produce.

**R6.4 — aggregation.** A **heading-occurrence micro-average** within each route: numerator and
denominator summed across that route's R1 pairs, never a mean of per-region rates. Each required
route is evaluated **separately and never pooled**. The gate is the **worst** required route — any
`FAIL` → FAIL; else any non-evaluable route → `NOT_EVALUABLE`; else PASS. Thresholds unchanged:
text **≥ 0.90**, role **≥ 0.80**.

**The abstention machinery is DELETED**, not deprecated: the four candidate rules and
`AMBIGUOUS_PENDING_A41_RULING` are gone, so no consumer can read a status the protocol no longer
defines. Pair-level and route-level raw counts stay in the output, so the gate is inspectable.

**Realized on the ruling's own fixture** (`x27.part_r1`, real `build_oracle`, real A38.7 join):

```
one-sided     P 3 · R 2 · matched 2 · agree 2 · denominator 3 · 0.667 -> FAIL
unresolved    P 3 · R 3 (1 unresolved) · matched 2 · agree 2 · denominator 4 · 0.500 -> FAIL
duplicated    P 3 · R 3 (2 non-unique) · matched 1 · denominator 5 · FAIL
whitespace    identical but for one doubled space · 0.000 -> FAIL (M2 would call them EQUAL)
UNREADABLE    role UNREADABLE on both sides · 0.000 -> FAIL, text unaffected
```

### R7 — the M4 parent encoding, repaired

**Found by review, and it was a false green.** §5.3 and `adjudicator_prompt.md` §3 give the
adjudicator four answers for `parent`: the printed text, literal **`NONE`**, literal
**`OFF_REGION`**, or **`UNREADABLE`**. The scorer read a Python `None` as "no parent" and compared
everything else as text, and every M4 fixture supplied `None` — so M4 was green **without ever
seeing the representation the real oracle will produce**. Under the real encoding, `"NONE"` would
have scored a correct root heading WRONG, and `"OFF_REGION"` would have counted against an
architecture on every occurrence, because it can never equal an emitted parent.

Repaired on the scoring path: `NONE` scores against `immediate_parent is None`; `UNREADABLE` stays
excluded as frozen; a **null refuses** (`PARENT_MISSING`), since it is not one of the four answers.

**`OFF_REGION` leaves M4's content-bearing population, and that is a reading.** §6 fires M4 on
*"matched headings whose parent is in-region **or resolvable**"*, and **no frozen source defines a
resolver**: `OFF_REGION` occurs exactly twice in the study (§5.3 and the prompt), and neither
`build_oracle` nor `methodology_contracts` carries one. A resolver would have to recover the
parent from an architecture's own document-scope hierarchy — the very quantity M4 measures — so it
is excluded and **counted** (`excluded_off_region`), never scored and never charged to an arm. No
resolver was invented, and the prompt was **not** edited to suit the implementation.

### R8 — RULED and IMPLEMENTED: the N-A / N-B / N-C factual verdicts

**The gap, as reported.** The control *fixtures* were owned (`control_fixtures.py`, G6-gated, 8/8/4
with every hash verified) and their *binding* was owned (`build_oracle.verify_join` checks the key's
carried truth against the manifest; `x26` drives all 20 through the real oracle path) — but
**nothing computed the verdict.** No component compared an adjudicated control answer against the
committed `control_expected_truth`, so nothing decided "did the adjudicator report the alteration
(N-A)?", "did it agree on the corroborated heading (N-B)?", "did it report no heading (N-C)?".
Three Rule 3 blockers had no factual owner, and Phase 2 would have had to derive control truth on
its own authority.

**The ruling, implemented in `score_metrics.control_verdicts`.** The committed chain is reused, not
rebuilt: `control_fixtures.json` → `build_oracle.control_expected_truth` → committed key, joined to
the committed adjudications. Nothing reruns `control_fixtures`, source enumeration, XML/PDF truth
construction, H, X, `x01`, or any oracle generation.

| kind | rule, on EVERY required route |
|---|---|
| **N-A** | the single committed mutated expected heading text occurs **exactly once** in `headings[].text`, by **exact raw string equality**. Absent, duplicated or `UNREADABLE` → FAIL |
| **N-B** | the single committed corroborated expected heading text occurs **exactly once**, same comparison, same failure conditions |
| **N-C** | `headings` is **exactly empty**. Any reported heading → FAIL |

**No normalisation, deliberately.** A `WELD_TWO_WORDS` or `SPLIT_ONE_WORD` control differs from its
source **only in whitespace**, so normalising the comparison would make the control incapable of
detecting the mutation it exists to test — it would pass whether or not the adjudicator saw the
alteration. **Other headings in the crop do not by themselves fail N-A or N-B:** the committed truth
establishes the *target* occurrence, not a complete oracle for every heading the region may contain,
and failing on an extra heading would charge the control for correct enumeration.

**Aggregation:** per control, per route, with observed texts recorded; per-kind status; counts by
route and kind. A kind PASSES only if **every** fixture passes on **every** required route — no
tolerance, no percentage. The three statuses are Rule 3 **inputs**; no consequence is applied here.

**Realized** on the committed manifest, against its own committed truth: **N-A 16/16 · N-B 16/16 ·
N-C 8/8** across 20 controls × both routes.

### A41.2.1 — two completeness enforcements, added on review. **Not new rulings**

Both close the same shape of hole: a **self-consistent but incomplete** artifact certifying a Rule 3
blocker. Neither introduces a rule — each enforces one already frozen.

**A36.6, enforced for R1's routes.** `r1_reliability` iterated the routes the **repeat** declared,
so a shortened repeat record plus a correspondingly shortened answer set could delete a **failing**
required route and leave the gate passing on the survivor, with nothing in the artifact looking
wrong. A36.6 already freezes the invariant: the repeat *"inherits its primary's required route(s):
C only → AI, D only → human, C and D → both"*. The required routes are now derived from **frame
membership** (via `build_oracle`'s own `C_FRAME_ROUTE` / `D_FRAME_ROUTE`, not restated), the
repeat's frames must equal the primary's, and its declared routes must equal the frame-derived set.
`R1_FRAME_SET_MISMATCH` / `R1_ROUTE_SET_MISMATCH`.

> **One deliberate divergence from the literal instruction, because the literal form would refuse
> valid frozen input.** The review asked that the repeat's `adjudication_routes` equal the
> **primary's**. It cannot: a C-audit-selected primary carries `human` **in addition** to its frame
> routes, and `plan_r1_repeats` explicitly does **not** inherit `is_c_audit_selected`
> (`replace(s, is_r1_repeat=True, is_c_audit_selected=False)`). For a C-only audited primary the two
> sets legitimately differ — primary `(ai, human)`, repeat `(ai,)` — and the real run will contain
> exactly that case, since most C regions are not discordant and the audit draws 25 of them. The
> primary is therefore required to **contain** its frame routes; the repeat must **equal** them.
> This is the same invariant A36.6 states, spelled so it cannot refuse a legal configuration.

**The frozen 8 / 8 / 4 census, enforced for R8.** `control_verdicts` passed a kind when all rows
**present** passed, so a coherent key missing one N-A would report **7/7 PASS** and satisfy a
blocker on a smaller census than A40.1 froze. The scorer now requires the frozen population (8 N-A,
8 N-B, 4 N-C), **both** result-bearing routes per control, and **unique** control identities — a
duplicated identity keeps the count looking right while one real fixture goes unexercised and
another is scored twice. `CONTROL_POPULATION_INCOMPLETE` / `CONTROL_ROUTE_SET_MISMATCH` /
`CONTROL_IDENTITY_DUPLICATED`, all raised **before** any verdict is computed, because an incomplete
artifact is not an observed control failure. Nothing is rebuilt: no `control_fixtures` run, no
source selection, no XML/PDF truth, no G6, no `x26`.

> **A key carrying NO controls is not refused, and that is deliberate.** The self-certification risk
> is a *partial* population reporting PASS. A key with none certifies nothing — every kind reports
> `NOT_EVALUABLE`, which no Rule 3 blocker accepts — and refusing it would make the scorer
> unrunnable on the DEVELOPMENT and mechanism material it must be tested against, including its own
> real-producer end-to-end check. `population_present` is reported so the two cases are
> distinguishable, and the confirmatory key carries all 20 by construction.

### R9 — RULED. §8's paired-quantity scope

**The gap.** §8.3 requires per-document paired differences, an unweighted mean over documents and
mandatory per-document detail, but **never enumerates which quantities are paired**. The first
implementation chose M1 recall/precision, M2, M3-clean, M4 and M5 — not frozen anywhere — and
silently dropped `VACUOUS` documents from each mean, which is an **unruled missingness policy** on
top of an unruled quantity list.

**The ruling: pair exactly the two non-constant numeric M9 basis quantities.**

```
n_margin_numbered_lines        A39.1's own quantity
coverage                       production _coverage, against the frozen 0.85 floor
```

Both are defined on **every** document for **both** arms, so no missingness or vacuity policy has
to be invented — which is precisely why the alternatives are excluded:

| excluded | why |
|---|---|
| M1–M5, M7 | can be `VACUOUS`; pairing them needs a new rule for which documents enter each mean |
| `derive_size_bands_returns_a_band`, `coverage_meets_floor` | booleans Rule 0 consumes, not numeric differences |
| `coverage_floor` | a frozen constant — its difference is always zero |
| `n_margin_numbered_with_glyph_size` | a diagnostic; A39.1's quantity is the margin-line count |
| internal support counts | not themselves frozen result quantities |

**POPULATION RULE.** M9 is valid on **both** P-head and P-robust (§4.4.1 claims M0 and M9 on
both), and the two are **never pooled**: each quantity is reported per population with its own
per-document detail and its own unweighted mean, and **no combined 17-document mean exists**. A
control asserts the pooled figure appears nowhere in the payload.

**§8's heading-discordance statistic stays P-head ONLY** — unchanged, and deliberately not
broadened: a heading-level statistic may not take a population §4.4.1 claims no heading metric on.

### A41.2.2 — three schema/reporting repairs, from a parallel implementation's review

Found by comparing against an independent implementation. **No methodology changes; all three make
the artifact say what the frozen rules already require.**

**M6 is ABSENT from the schema, not present-and-annotated.** The payload carried
`"m6": "DEFERRED by A20 …"`. §5 owns "M0–M9 minus M6", so a key named for it — even one whose value
says DEFERRED — puts a deferred metric in a result-bearing artifact and invites a consumer to
reserve, look up or later fill it. The key is gone, the explanation lives in module prose and here,
and `owns` now **enumerates** the metrics owned rather than describing them by subtraction (which
named M6 in passing). The control **recursively walks the finished payload** for any key or string
naming M6 at any depth, and is proven non-vacuous by planting one.

**I13 labels every applicable result surface, not a parent block.** The qualification now travels
with M0, M7, M9, each per-document C/D heading estimand, the §8 event vector and **every** §8
paired-difference detail row. A passing document carries an explicit `None`, so "not conditioned" is
distinguishable from "nobody labelled this", and both headline qualifications are emitted explicitly
from the >⅓ rule. It reaches **no** decision input: cross-engine qualifies reporting only (A27.6).
The control **discovers** per-document result surfaces from the finished payload by content marker,
not from the production list of paths, so a labelling path nobody enumerated is still covered.

**The exact `d_frame == bool(d_reasons)` invariant.** `build_frames` emits the flag from the same
expression that builds the reason list, so the two can only disagree if something rewrote one. The
existing line-level and anchor checks each inspect **one** predicate and cannot see a broken
relationship between the flag and the list as a whole — a concordant region carrying a reason with
`d_frame` false satisfies every one of them. `D_FRAME_FLAG_DRIFT`, with a fixture chosen so no other
check can fire first. #618's independent recomputation of anchor-set discordance from the serialized
H/X evidence is **unchanged** and predates this.

### A41.2.3 — the scorer no longer needs a PDF renderer to be imported. **Not a rule change**

The fourth item from the same parallel-implementation review, and the only one not already
subsumed. **No metric, denominator, ruling, schema, population or boundary moves; the x27 evidence
diff is exactly this control and no reported figure changes.**

`score_metrics` imported `build_oracle` at module scope, and `build_oracle` imports `pymupdf` at
module scope because rendering the adjudication stimuli is part of what **it** owns. A38 exists so
the scorer consumes committed JSON and nothing else — and that held for the **data** path while
being false at the **import line**: importing the scorer re-acquired the very renderer dependency
A38 had removed, and the module could not be imported at all in a renderer-free environment.

`build_oracle` is now resolved on first use (`_bo()`). **The delegation is unchanged and that is the
point**: the A38.7 join, the A38.7 adjudication encoding and the A36.4 routing are still *called*,
never restated locally, so a derivation that genuinely needs them still requires the renderer and
still fails loudly without it. Removing the dependency by copying a frozen rule would have been the
defect, not the fix — two copies of a rule are two rules. `FROZEN_CONTROL_ROUTES` became
`frozen_control_routes()` for the same reason: evaluating it at module scope is exactly what would
pull the renderer back into the import graph, and it is still derived from `build_oracle`'s own
constants so the two cannot drift.

**The control is executable, not a source grep.** A grep reads the import line an author wrote
rather than the graph the interpreter walks, and would keep passing if some other frozen dependency
acquired a renderer later. A child interpreter makes `pymupdf`/`fitz` genuinely unimportable and is
asked what happens. Three of the four checks exist to stop it passing for the wrong reason: the
blocker is asserted **live** (without which an interpreter that merely lacks a renderer is
indistinguishable from a scorer that needs none); JSON-only scoring must still **compute** there
(A27.5's Clopper–Pearson bound reproducing §8.1's own 0.1926), so the property is not a cosmetic
import that reaches no working function; and a `build_oracle`-owned derivation must still fail under
the blocker, which is what proves the rule was not copied. The fourth records that the control is
**decisive only while `build_oracle` imports the renderer eagerly**, so it is re-pointed rather than
silently trusted if that ever changes.

Falsified by restoring the eager import: **187/190, the three renderer checks RED on named checks
with no crash**, `blocker_live` still true — so the red is attributable to the scorer rather than to
a broken blocker — and the decisiveness check still green. Restored, **190/190**, evidence
byte-identical to the committed artifact.

### A41.3 — the controls, and that each can go RED

`x27_score_metrics.py`, **190/190**, on SYNTHETIC + DEVELOPMENT material only. It covers all
**eleven** current §5 control rows (the row list is enumerated in the evidence file and a final
check fails if any row has no executable test), the twelve explicit negatives, the false-green
attacks, and the refusals.

**Every frozen quantity was then falsified by injection.** Seventeen faults were applied to
`score_metrics.py` one at a time — the all-lines M0 denominator, a vacuous rate printed as 0.0,
recall against the emitted enumeration, dropping an UNMATCHED occurrence, M4 against full ancestry,
M5's UNSCORABLE inside the denominator, M7's threshold moved to 2, a tolerance in the margin-line
clause, an accepted coverage-floor drift, a bootstrap at zero events, a heading-unit §8
denominator, a heading-count-weighted paired mean, an arm's own output substituted for oracle truth
in M3, an accepted duplicate document, a control entering an estimand, an R1 repeat counted, and a
line-level §8 event — and **16 of the 17 were caught by the specific control written for each**.
Evidence: `results/x27_score_metrics.json` plus the injection table in the session report.

**Round 2, after the reviewer's repairs: 26 faults, and the sweep again earned its cost.** Nine
new faults cover the repaired surfaces — `NONE` compared as text, `OFF_REGION` scored as text, a
null parent read as no-parent, containment-only cross-engine population, extras admitted, §8's
unfiltered vector, R1 resolving its own open denominator, R1 coarsening the role, R1 pooling
routes. **Twenty-four were caught first time; two were not, and both were non-discriminating
controls of exactly the kind this sweep exists to find:**

- **the fine-role control reused a fixture whose roles differ under the coarsening too**
  (`account` → LEAF vs `grouping` → CONTAINER), so a coarsening implementation failed it
  identically. Repaired with `account` vs `section`, which are different fine roles that **both**
  coarsen to LEAF — the only shape that separates the two readings.
- **the per-route control asserted a self-declared `pooled_across_routes: False` label** rather
  than behaviour, so pooling the rows left it green. Repaired with a route-asymmetric fixture
  (only the human repeat disagrees), which forces the two implementations to different numbers.

Fixing the second exposed a third defect, in the fixture builder itself: `synthesize_adjudication`
assigned **one** headings list to both answer routes, and `copy.deepcopy` memoizes, so a
"human-only" perturbation silently changed the AI answer as well. Two adjudication sources produce
two answers (A36.6), and the fixture now does too. **26/26 after the repairs.**

> **The seventeenth of round 1 is the reason the sweep was run at all.** Deleting the scorer's own
> `DUPLICATE_DOCUMENT_IDENTITY` guard left the whole suite **green**: `methodology_contracts`
> refuses the same input one layer below and defines the **same reason string**, so a control
> asserting the reason alone could not tell which layer had refused. Two layers refusing a
> duplicated document is good defence; the defect was a control that could not go red. It now pins
> the exception **class** (`f5d6171`), and re-injecting the fault fails it. **17/17 after the
> repair.** The sweep also measured that deleting the `control_kind` skip does not move the
> "adding 20 real controls changes nothing" invariance — a control carries `frames == ()`, so the
> frame-membership filter refuses it again — and that the exclusion **count** is what makes that
> deletion visible. Both facts are now recorded beside the controls they concern rather than
> assumed.

**Not merely a synthetic suite.** The frames come from `build_frames`' own private synthetic
constructor (the seam `x17` uses), the oracle keys from the **real** `build_oracle` over rendered
synthetic PDFs, the twenty controls from the **committed** `control_fixtures.json` manifest through
`BO.control_specs`, and one part runs the whole chain — `run_hybrid`, `run_extended`,
`build_document_frame`, `build_oracle`, the scorer — on a real **non-holdout** DEVELOPMENT document.

**The synthetic adjudications are a MECHANISM fixture and are labelled as such in the artifact.**
Their oracle text is derived from an arm's own emitted output, so every agreement figure `x27`
prints is evidence about the **join**, never about accuracy. No human or AI adjudication exists.

### A41.4 — a DEVELOPMENT observation the reviewer should see, with its caveat

On the first **8 pages** of `118-hr-8752/1`, the A39.1 quantity — `Page.lines` where
`line_number is not None` — is **H 134 against X 171**, so Rule 0's margin-line clause **fires**,
naming H. This is a machinery observation on a truncated window of a development document, it is
**not** a confirmatory result, and it is not evidence about either arm on the holdout. It is
recorded because A39.1's clause has no tolerance by design, so a reviewer should know the clause
does fire on real material, and because the page-limit truncation is an obvious candidate
explanation that only a whole-document run can eliminate. `x00`'s five-document measurement is of
different quantities (line counts and heading counts), so it neither confirms nor contradicts this.

### Population and boundary

SYNTHETIC + DEVELOPMENT only. No holdout document opened, no H/X run on any holdout member,
nothing adjudicated by a human or an AI, no architecture decision, and none of `frames.json`,
`oracle_key.json`, `oracle_blind.json`, `oracle_adjudicated.json`, `s1_control.json`,
`cross_engine_control.json`, `metrics.json`, `scores.json` or `EXECUTION-START.json` created —
`x27` asserts their absence as its last act. The canonical `metrics.json` writer is guarded by
`build_oracle.assert_write_permitted`, the same VALID-only authority the oracle, S1 and
cross-engine writers use, and a control proves it refuses today and would write to a scratch path.

### Realized

`x27` **190/190**; **55** injected faults caught in total, each failing a NAMED control rather than
crashing — 54 through round 5, plus round 6's renderer fault (A41.2.3). **Scope, stated because a
falsification belongs to the tree it ran on:** the round 6 fault is the only one re-injected against
this HEAD; the other 54 were run against their own rounds' HEADs and are not re-asserted here.
`contamination.json` byte-identical.

**Round 3 added a fourth class of control defect worth recording: a control that detects a fault
only by CRASHING.** Four R6/R8 negatives indexed `failures[0]` or relied on a bare `KeyError`, so
under their fault the probe raised instead of reporting a red check. The fault was caught either
way, but a traceback cannot distinguish "the rule broke" from "the probe has a bug". All four now
fail a named check, and the injection driver asserts `crashed == False`.
`decide_architecture.py` is **not** created and **G5 is not modified to hide it**: G5 still reports
the surface as incomplete, naming that one file.

---

## A42 — SUBSTANTIVE. `decide_architecture` implements the already-frozen section 7.2 machinery

```json
{"id": "A42", "class": "SUBSTANTIVE",
 "commits": ["7aa3751", "7df515c"],
 "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": true,
 "files_touched": ["probes/decide_architecture.py", "probes/x28_decide_architecture.py",
                   "probes/score_metrics.py", "probes/x27_score_metrics.py"],
 "supersedes_text_in": "none -- NO PREVIOUSLY FROZEN rule is changed. A42 makes the already-frozen Rule 0 / Rule 1 / Rule 3 machinery executable, before any confirmatory execution exists. A41's REALIZED x27 figure moves 190 -> 194; none of A41's rulings is reversed",
 "status": "IMPLEMENTATION COMPLETE. A42.3 RULED -- Rule 1's M4 condition is the per-heading existential, and `score_metrics` now emits the paired fact"}
```

**Why `affects_scoring_rule` is `true` while `supersedes_text_in` is `none`.** The same distinction
A31 and A41 kept, and for the same reason:

> **No PREVIOUSLY FROZEN rule is changed.** Every threshold, unit, outcome and gate this module
> applies was fixed by section 7.2, A5, A10, A20, A27.3, A27.4, A27.6, A28.2 and A39.1 before the
> component existed, and none is amended, reinterpreted or relaxed.
>
> **A42 DOES make previously UNSPECIFIED orderings and operationalizations executable.** Which rule
> runs first, what an unevaluable gate does, where the census count comes from, and how the R1 gate
> composes its two dimensions are all result-bearing and none was spelled out. They are recorded in
> A42.2 rather than absorbed, and every one was settled **before any confirmatory output existed**.

### A42.1 — the decision state, and which frozen source owns each predicate

`decide_architecture.py` is a pure consumer of `score_metrics`' payload and the committed frames.
It opens no PDF, runs no arm, recomputes no metric, reconstructs no oracle truth, alters no
population and repairs no surprising input. `score_metrics` emits `rule0_outcome: None` and
`decision_taken_here: False`; **this module is where the decision is taken, and the only one.**

| predicate | frozen source |
|---|---|
| Rule 0's three clauses | section 7.2 rule 0 -- band, the 0.85 floor, margin-numbered lines |
| the margin-line quantity, with NO tolerance | **A39.1**, via `methodology_contracts.margin_line_loss` |
| a document BOTH arms lose is neutral, never an asymmetric loss | section 7.2 rule 0's both-lose branch |
| an asymmetric loss on EACH arm rejects BOTH, with no ranking | **A27.4** |
| `EXTENDED_BY_RULE_0_M9` / `HYBRID_BY_RULE_0_M9` | **A27.4** |
| `X_CORRECTS >= 5`, `X_REGRESSES == 0` | **A5** rows 1 and 2 |
| no M4 parent regression, as a PAIRED per-heading existential | **A5** row 4, as A20 restated it, **ruled by A42.3** |
| the M6 veto is STRUCK | **A20** |
| condition 1 holding while a veto fails is "insufficient evidence, NEVER an X win" | **A5** |
| the item is a REGION; `<= 60` evaluable, `> 60` insufficient | **A10** as unit-fixed by **A27.3** |
| Rule 1 never runs on a sample | **A27.3** |
| the nine-gate vector | **A27.6** |
| `INADEQUATE` blocks, `LIMITED` does not | **A28.2** |
| cross-engine qualifies REPORTING only | **A27.6** |
| `HYBRID_BY_PRIOR`, and the ban on writing it as an H victory | section 7.2 rule 2, **A10** |
| the five-outcome enum, closed | **A10** + **A27.4** |

The decision unit is the **heading occurrence**: Rule 1 reads `m3_outcomes` and never the WELD/SPLIT
boundary tallies beside it, which would inflate both counters (HARNESS-PLAN 7.2, recorded there as
a build check rather than an ambiguity).

### A42.2 — the readings taken, each with its authority

Recorded so a reviewer can overturn any of them, rather than discovering them in the code.

**1. Rule 0 runs before the remaining Rule 3 gates.** Section 7.2 rule 0 says M9 "supersedes
everything below" and rejects an arm "regardless of every other metric"; HARNESS-PLAN section 6
restates it as "Rule 0 (M9) runs **FIRST**"; I12 has M9 rejecting an arm "before any other metric
is consulted"; and the section 6 control row is "the losing arm is not rejected outright **before
other metrics**". No text supports the opposite order. **The consequence, stated because it is the
uncomfortable one:** a Rule 0 outcome can be emitted while, say, X2-b has failed. That is what the
frozen text says, and M9 needs no oracle, no adjudication and no control -- section 6's M9 row
gives its oracle requirement as "none needed" -- so no Rule 3 gate except M9's own evaluability is
an input to it. **The full gate vector is emitted whatever decided**, so a failing gate is visible
in the artifact rather than erased by the rule that won.

**2. M9 evaluability is checked BEFORE Rule 0.** It is section 7.2 rule 3's own listed item ("the
M9 gate cannot be evaluated") and it is Rule 0's precondition. Rule 0 is **not run** without it:
the facts it would read are the ones whose absence made the gate unevaluable, and refusing there
would turn rule 3's frozen ANSWER into an exception. `x28` found this by stripping one clause.

**3. `NOT_EVALUABLE` is not a pass.** A41.2.1 already states it, of an oracle key carrying no
controls: every kind reports `NOT_EVALUABLE`, "**which no Rule 3 blocker accepts**". Every gate
therefore satisfies Rule 3 only on `PASS`.

**4. The R1 Rule 3 gate is the worse of section 5.6's two dimensions**, composed with **R6.4's own
precedence** -- any `FAIL` wins, else any `NOT_EVALUABLE`, else `PASS`. Nothing new is invented:
R6.4 already defines that precedence for the routes within each dimension, and both thresholds
(text 0.90, role 0.80) are unchanged.

**5. The D-frame census is read from `build_frames`' own committed `counts["d_frame_census"]`**,
cross-checked against the committed census LIST it was derived from, with a truncated census
refusing. A27.3 requires the complete census be enumerated **before** any sampling and
`build_frames` commits exactly that ("the COMPLETE census, never sampled and never truncated to the
A10 budget"). **Rejected: a caller-supplied integer**, which is R5's closed channel -- "a caller
scalar is not evidence for a result-bearing gate". Reading a producer's committed count is not
recomputing a metric; deriving the census from regions here would be, and is not done.

**6. Rule 1's D-evidence adequacy condition is that the adjudicated D-frame region count EQUALS the
committed census.** A27.3: "`<= 60` regions -> human-adjudicate the **complete census**", and "Rule
1 must never run on a 60- or a 120-region **sample**". A census of 40 with 39 adjudicated is a
sample, and yields `INSUFFICIENT_COMPARATIVE_EVIDENCE`. This is the frozen budget clause enforced,
not a second threshold.

**7. X2-a and X2-b are SUPPLIED named statuses.** A27.6 says the decider "**receives** a named
status for every decision-blocking condition still operative" and separately records that the
confirmatory X2 run "is planned and **not run**", so no committed artifact carries the verdict and
none has a frozen shape. Every other gate is DERIVED from a fact `score_metrics` computed, per R5.
A missing or unrecognised status **refuses**.

**8. The wording gate is blunt on purpose.** HARNESS-PLAN section 6 requires a pre-committed
sentence and forbids any comparative-accuracy claim for H. The gate is a literal pattern scan over
the **rendered** conclusion, and the first thing `x28` caught was the study's own natural
disclaimer -- "this is not a finding that hybrid is more accurate" -- tripping it. **The disclaimer
was reworded rather than the gate taught to parse negation**: a negation-aware gate is precisely
the check that passes for the wrong reason.

### A42.3 — RULED. Rule 1's M4 condition is the per-heading existential, and it now has a producer

> **THE RULING, taken by the study owner on the record below, not by the implementation.**
>
> 1. Rule 1's fourth condition is the **literal per-heading existential**.
> 2. **`score_metrics` must emit the paired fact.** The aggregate `m4_correct` counts are
>    insufficient and may not be substituted for it.
> 3. The decider's **supplied `m4_no_regression` channel is removed**; condition 4 is read from the
>    scorer like every other decision input.
>
> The gap as it was originally reported is preserved below, because the reason the question had to
> be escalated is part of the record — the same way A38.8's forward ambiguity was kept when A39.1
> ruled it.

**What changed, and what deliberately did not.** `score_metrics` gains `m4_h_correct_x_wrong`, its
mirror `m4_x_correct_h_wrong` (a **diagnostic**; Rule 1 is one-directional and reads only the
first), and `m4_h_correct_x_wrong_keys` — the occurrence keys of the vetoing headings, because a
veto that decides an architecture should name the headings it fired on and a bare count cannot be
checked against the adjudication. The pair is counted inside `_score_stimulus`, where both arms'
per-heading M4 results are in hand; nothing downstream can recover it from the aggregates. **No
existing metric, denominator, threshold, rate or exclusion moves** — this is an addition, and every
one of A41's 190 checks still passes unchanged.

**One sub-reading the ruling did not need to state, recorded because the implementation had to take
it.** The paired population is **headings scored under M4 for BOTH arms**. §6 fires M4 on *matched*
headings, so a heading X never emitted is not in M4's population for X, and charging it here would
count one failure twice — once in M1's recall and again as a hierarchy regression. **Nothing escapes
by it:** an unemitted heading scores a maximal `TEXT_ERROR` in M3 (A9 — a severe failure may never
become an exclusion), so if H is clean it is already `X_REGRESSES`, and Rule 1's condition 2 vetoes
at **zero**. The veto is therefore about hierarchy specifically, which is the quantity A5 row 4
names.

**The gap, as originally reported.** Rule 1's fourth condition is a **per-heading existential**:

> A5 row 4: "**no heading** whose immediate parent is correct under H and wrong under X"
> A20: Rule 1 becomes `X_CORRECTS >= 5`, `X_REGRESSES == 0`, "**no M4 regression**"

`score_metrics` emits M4 as **per-arm counts** -- `m4_correct: {H, X}`, `m4_scored: {H, X}`, plus
the exclusions -- and **no paired quantity**. The existential is therefore not computable from
`metrics.json`, and the scorer is closed.

**Two readings, and they disagree on real payloads.**

| reading | what it evaluates |
|---|---|
| **(a) existential** | does ANY scored heading have H's immediate parent correct and X's wrong? A5 row 4's literal words |
| **(b) count directionality** | does M4 move against X, i.e. `m4_correct[H] > m4_correct[X]`? A5's own framing -- "each metric is vetoed in **its own native unit**, and every veto is a **hard directionality check**" -- and the only form the scorer emits |

**The concrete payload on which they differ.** A D-frame census of 10 regions, fully adjudicated,
every Rule 3 gate `PASS`; `m3_outcomes` = `X_CORRECTS 5`, `X_REGRESSES 0`; M4's scored population
is two matched headings with readable printed parents:

```
heading P    H's immediate parent CORRECT, X's WRONG
heading Q    X's immediate parent CORRECT, H's WRONG
--> m4_correct = {"H": 1, "X": 1}   m4_scored = {"H": 2, "X": 2}   M4 rate 0.5 on both arms
```

Reading **(a)**: heading P exists, condition 4 fails, condition 1 holds, and A5 gives
`INSUFFICIENT_COMPARATIVE_EVIDENCE`. Reading **(b)**: the counts are equal, M4 does not move
against X, all three conditions hold, and the outcome is `EXTENDED_BY_RULE_1`. **Different
architectures.**

**Reading (a) was ruled.** Reading (b) is now a **defect**, and it is one nothing else in the suite
could see: on every other fixture the aggregates and the pairing agree, so only a payload built to
make them disagree can tell the two implementations apart. That payload is therefore an executable
control in **both** probes — `x27` proves the scorer computes the pair over a real oracle key and a
real adjudication, and `x28` injects reading (b) into the decider as a **named fault** and requires
the architecture to flip.

**A one-directional inference was considered and NOT built.** `m4_correct[H] > m4_correct[X]` does
imply, by pigeonhole, that at least one such heading exists -- but the converse does not hold, so
it could prove the veto FIRES and never that it does not. Building it would substitute an argument
for a measurement on the majority of payloads, and the ruling makes the measurement available.

**The refusal stays, repointed.** `M4_VETO_FACT_MISSING` no longer means "no component owns this";
it means the D-frame block reached the decider **without** the paired quantity. The decider does not
fall back to the aggregates, because that fallback IS reading (b), and it does not default to "no
regression", because that is the one default that can only ever help X. An **absent** D block is a
different thing entirely -- an empty census, a frozen and legitimate state in which condition 1
fails and the prior stands -- and is not a refusal.

Recorded in the same shape as A38.8's forward ambiguity: the gap was found and reported **before**
execution rather than discovered inside the decider, and the escalation is what produced the ruling
rather than an implementation choice nobody reviewed.

### A42.4 — the controls, and that each can go RED

`x28_decide_architecture.py`, **92/92**, SYNTHETIC only, and `x27_score_metrics.py` **194/194**
(was 190; the four new checks are A42.3's). x28 covers all **eleven** HARNESS-PLAN section 6 control
rows (a final check fails if any row has no executable test), every Rule 0 predicate with a positive
and a near-miss fixture, both precedence directions, the 4-vs-5 and 0-vs-1 boundaries, 5-and-1, the
M4 veto, D = 60 vs 61, all five outcomes, and eleven refusals.

**Two controls the ruling added, each aimed at a reading that would otherwise pass silently.**

**A5 row 4's paired quantity, where the aggregates are blind (`x27`).** A real oracle key over a
real frame, with H wrong on `ACCOUNT 0` and X wrong on `ACCOUNT 1`, so `m4_correct` is **3/4 on both
arms and the M4 rates are equal** while `ACCOUNT 1` is correct under H and wrong under X. The paired
fact reports 1 and names the occurrence; the near-miss — both arms wrong on the **same** account,
aggregates equal again — reports 0, so the quantity is not a restatement of the aggregates. Neither
arm is clean in this fixture, so the oracle cannot be synthesized from one arm's output the way the
other M4 controls do it: the structure still comes from the real key and only the `parent` field is
stated, which is the one field the control is about.

**One document, DIFFERENT clauses (`x28`).** H loses the band and X loses margin lines on the **same**
document. §7.2 rule 0 fires only when exactly one architecture loses a document the other keeps, so
this is neutral for RQ1 and stays a failure in RQ2. An implementation that asked each clause "did an
arm lose me?" independently would see a band loss naming H and a margin loss naming X, fire twice,
and reject **both** arms on a single document — inventing A27.4's two-sided branch, which requires
**different** documents. A second check asserts both clauses really did fire, so the trap is live.

**The fixtures are real producer output.** Every payload is `score_metrics.score(...)` over
synthetic frames, and the pooled D block is shaped by the scorer's **own**
`_heading_metrics_from_counts`. `part_contract` walks every field path the decider reads against a
real payload and is proven non-vacuous by planting an absent path -- the check that would catch a
scorer/decider field-name mismatch, which a hand-written fixture cannot see because it encodes the
decider's belief about the producer. The **61-region census is produced by `build_frames`** from
real discordant lines and read back, so the budget boundary is tested against the producer's count
and not against a number the probe wrote down.

> **Rule 3 gate STATUSES are overwritten on those real payloads to reach later rules, and they are
> FIXTURES, never evidence.** Building genuinely passing R1, control and adequacy artifacts is
> `x27`'s work against the real oracle path. What `x28` must prove is what the DECIDER does with a
> status, and `part_contract` is what stops the overwrite drifting onto a field the scorer lacks.

**Eleven faults were injected into `decide_architecture.py` one at a time** -- the threshold lowered
to 4, the regression tolerance restored, the budget relaxed to 120, the M4 veto disabled, **reading
(b) substituted for the paired fact**, A27.4's two-sided rejection removed, `NOT_EVALUABLE` accepted
as a pass, 5-and-1 collapsed into the prior, Rule 0 no longer superseding, the wording gate
disabled, and the closed-enum guard removed -- and **all eleven were caught by a NAMED check with
`crashed == False`**. The anchor for each fault is asserted **unique** in the source, so a fault
cannot silently patch zero or two sites.

> **The fifth is the ruling's own guard.** It replaces the paired read with
> `max(0, m4_correct[H] - m4_correct[X])` -- reading (b), exactly as A42.3 states it -- and requires
> the architecture to flip from `INSUFFICIENT_COMPARATIVE_EVIDENCE` to `EXTENDED_BY_RULE_1` on the
> equal-aggregate payload. Without that fault the ruling would be a sentence in a document; with it,
> re-deriving condition 4 from the aggregates fails a named check.

**Three real defects were found by the controls rather than by inspection.** `decide` evaluated
Rule 0 eagerly even when M9 was not evaluable, so a stripped M9 clause raised `MISSING_REQUIRED_FACT`
instead of returning rule 3's frozen answer; Rule 0 is now not run without its precondition and
reports a same-shaped `evaluated: False` block. The closed-enum fault was at first detected **only
by a `KeyError`** -- A41.3's fourth class of control defect; `render_conclusion` now refuses an
outcome with no pre-committed sentence by the distinct name `SENTENCE_MISSING_FOR_OUTCOME`, so the
two layers are distinguishable and the fault fails a named check. And the empty-census control was
itself wrong: it removed the D block while leaving a **five-region** census, which is a census that
went unadjudicated and correctly refuses -- the fixture, not the decider, was at fault, and it now
uses a zero census, which is the state it meant to describe.

**No sixth outcome can be emitted.** The enum is asserted closed on the way out of `decide`; an AST
walk (not a grep) finds no outcome-shaped literal in the module outside the five; a 240-payload
sweep over the fixture dimensions emits only the five; and all five are reached.

### Population and boundary

SYNTHETIC only. No holdout document opened, no H/X run on any holdout member, nothing adjudicated,
**no architecture decision taken on real evidence**, and none of `frames.json`, `oracle_key.json`,
`oracle_blind.json`, `oracle_adjudicated.json`, `s1_control.json`, `cross_engine_control.json`,
`metrics.json`, `scores.json` or `EXECUTION-START.json` created -- `x28` asserts their absence as
its last act. `contamination.json` is byte-identical. **The decider has no writer at all**: it
returns a payload and never persists one, and a control asserts the module contains no write path,
so an architecture decision cannot be recorded before the frozen start procedure is performed.

**`score_metrics.py` is reopened by A42.3's ruling, and only as an ADDITION.** Three new emitted
quantities, computed inside the existing join from results the scorer already had in hand. No
metric, denominator, threshold, rate, exclusion, refusal class, population or boundary moves, and
`x27`'s 190 pre-existing checks all still pass unchanged -- which is the evidence that the change is
additive rather than the claim that it is.

**G5 now goes GREEN**, because `probes/decide_architecture.py` was the one file it named as
missing. G5 is **not** modified: the surface it measures is unchanged and the file simply exists.
**Execution remains FORBIDDEN and the boundary remains ABSENT** -- G5 is a readiness gate, not an
authorization, and A11's one-way marker is not created here.

---

## A18 — the commit ↔ file accounting of record

```json
{"id": "A18", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
 "affects_membership": false, "affects_scoring_rule": false,
 "commits": ["70ec76c", "3d3e3fc", "481731b", "985def9", "c111433", "0e877b4", "641013c",
             "2b07a60", "c394e7b", "c3cb3c0", "6b6eb7e"],
 "files_touched": ["probes/x01_contamination.py", "probes/x03_select_holdout.py",
                   "probes/x04_freeze_check.py", "probes/m3_boundaries.py",
                   "probes/m3_selftest.py", "probes/x06_m6_feasibility.py",
                   "probes/neutral_geometry.py", "probes/x07_neutral_geometry.py",
                   "probes/neutral_identity.py", "probes/x08_neutral_identity.py",
                   "probes/x09_skeleton_cross_engine.py"]}
```

**Why one accounting block rather than per-theme attribution.** F9 is now **bidirectional**:
declaring a commit is not enough, every protected file that commit touched must be named by
a declaration *for that commit*. Applying that to the existing thematic amendments exposed
real gaps — `c111433` touched four protected files while A11 named one, and `0e877b4` was
declared with `files_touched: []`. Spreading the files back across A3/A4/A6/A11–A17 by theme
would be **invented attribution**: several commits carried more than one theme, and a
reviewer cannot check a guess. So the accounting lives here, in one reviewable block, and the
thematic amendments keep the *reasoning* while this keeps the *bookkeeping*.

**The complete post-freeze protected history**, from
`git log 4e2b520..HEAD`:

| commit | protected files touched | theme |
|---|---|---|
| `70ec76c` | `x04_freeze_check.py` | F4 vs the withdrawn population (A14) |
| `3d3e3fc` | `m3_boundaries.py`, `m3_selftest.py`, `x03_select_holdout.py`, `x04_freeze_check.py` | orphan file, M3 executable (A3/A4/A6) |
| `481731b` | `x01_contamination.py` | contamination self-ingestion (A7) |
| `985def9` | `x04_freeze_check.py` | F3 read raw classes (A14) |
| `c111433` | `m3_boundaries.py`, `m3_selftest.py`, `x01_contamination.py`, `x04_freeze_check.py` | freshness snapshot, UNALIGNABLE, >60, boundary (A8–A11) |
| `0e877b4` | `x04_freeze_check.py` | F6/G2 proxy sweep (A12) |
| `641013c` | `x04_freeze_check.py` | working-tree-vs-committed (A13) |
| `2b07a60` | `x04_freeze_check.py` | freeze/boundary as historical facts (A15/A16) |
| `c394e7b` | `x06_m6_feasibility.py` | M6 feasibility probe (A17) |
| `c3cb3c0` | `neutral_geometry.py`, `x07_neutral_geometry.py` | neutral ink-line skeleton (A19) |
| `6b6eb7e` | `neutral_identity.py`, `x08_neutral_identity.py`, `x09_skeleton_cross_engine.py` | literal glyph membership (A21) |
| `89e9d91` | `neutral_identity.py`, `x08_neutral_identity.py`, `x10_reconstruction_signature.py` | segmentation discordance (A22) |
| `e277a3e` | `x11_provenance_chain.py` | source-glyph provenance (A22) |
| `7644687` | `x09_skeleton_cross_engine.py` | cross-engine gate frozen (A22) |
| `2f548f0` | `neutral_identity.py`, `x09_skeleton_cross_engine.py`, `x10_reconstruction_signature.py`, `x11_provenance_chain.py` | grouping ≠ coverage; M0 risk set (A23) |
| `db3c0d2` | `run_hybrid.py`, `pdfium_extended_corrected.py`, `reconstruct_extended_corrected.py`, `run_extended.py`, `x2_verify.py`, `x11_provenance_chain.py`, `x12_skeleton_eligibility.py`, `x13_x_arm.py` | H/X arms; two frozen-text ambiguities (A24) |
| `277a0e5` | `neutral_identity.py`, `run_hybrid.py`, `reconstruct_extended_corrected.py`, `pdfium_extended_corrected.py`, `x2_verify.py`, `x04_freeze_check.py`, `x08_neutral_identity.py`, `x09_skeleton_cross_engine.py`, `x10_reconstruction_signature.py`, `x12_skeleton_eligibility.py`, `x13_x_arm.py` | A24 resolved: X2-b gate scope; ink identity vs provenance (A24.1/A24.2) |
| `070098e` | `x2_verify.py`, `x04_freeze_check.py`, `neutral_identity.py`, `x08_neutral_identity.py`, `x10_reconstruction_signature.py` | A24 record cleanup + finite-geometry enforcement (A24); X2-b vacuity found (A25) |
| `46b343a` | `x2_verify.py`, `x04_freeze_check.py`, `reconstruct_extended_corrected.py` | A25 resolved: X2-b boundary-decision counterfactual |
| `4db8cc8` | `x2_verify.py` | A25 defects: raw boundary stream; page-qualified sabotage |
| `af10155` | `HARNESS-PLAN.md` | harness plan created; reasoning A26, **accounting A27** |
| `2938312` | `HARNESS-PLAN.md`, `probes/x14_anchor_bridge.py` | harness contract rulings + anchor bridge proof (A27) |
| `0cf7daf` | `HARNESS-PLAN.md`, `probes/methodology_contracts.py`, `probes/x15_methodology_contracts.py`, `probes/x14_anchor_bridge.py`, `probes/run_hybrid.py` | 4.5 frozen; stimulus identity; render scale; bilateral bridge (A28) |

The last three are declared **by A22's own JSON block**, not by this one, so the record that
carries the reasoning also carries the bookkeeping for the commits it produced. They are
listed here because this table claims to be the complete post-freeze history, and a table
that silently stopped short of HEAD would be the same defect A18 was written to remove.

**No file is declared under both a SUBSTANTIVE and a TOOLING amendment**: A6 hands its
protected-file accounting here and keeps only the deleted orphan PDF, which is not a
protected suffix.

---

## What was deliberately NOT amended

- **Membership.** Unchanged, 17 documents. The orphan `CRPT-118HRPT146.pdf` was never a
  member; deleting it corrects the *directory*, not the population.
- **The stale-prose findings did not trigger a re-selection.** Consuming a fresh population
  to fix prose contradictions found before scoring would waste a scarce resource for no
  methodological gain.
- **`PRE-REGISTRATION.md` itself.** Byte-frozen at `c399e9d`, so F4 keeps its plain
  meaning. Read it **as amended by this file**.
