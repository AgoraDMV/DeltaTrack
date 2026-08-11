# #170 spike — structural signals as the matching primary, text similarity demoted

Research spike. Goal: decide *how* to make structural identity the primary matching
signal and demote text similarity to a confirmer/tiebreaker. Deliverable is this
design decision (it becomes #170's design comment). No production matcher code was
changed; every claim below is measured on the real corpus or the #8 / 119-hr-1
anchors. Reproduction scripts are in the session scratchpad (`probe1_signals.py`,
`probe_classifier.py`, `probe_corpus.py`, `probe_adversarial.py`, `probe_hr1.py`).

## TL;DR recommendation

Structure delivers **two clean, no-regression wins**, and the spike measured that the
other four target pairs are *threshold-calibration* problems structure cannot solve
for free. Concretely:

1. **Add a structural keep-override at the split guard** (`diff_bill.py:591`): keep a
   matched pair as `modified` (never tear into removed+added) when either
   (a) the leaf is an **appropriations account** (`appropriations-major/intermediate/small`)
   and the `match_path` is equal, or (b) both nodes carry a **specific, collision-scoped
   header** that matches. This flips `contested-4-tanker` and `extreme-alien-snap`
   (the 119-hr-1 case) to correct with **zero** measured corpus regression.
2. **Do NOT raise the 0.40 split floor or loosen the 0.60 move threshold.** The remaining
   four xfail pairs (`contested-1/2/3`, `contested-5`) are text dead-zone calibration,
   not structure. Raising the floor to catch them mis-splits genuine edits elsewhere
   in the corpus (measured: e.g. `118-hr-8774 Sec. 8144`, a headerless stub→expanded at
   0.554). Keep those four as documented xfails / a finding; the real fix path for them
   is boilerplate-discounted similarity, which is **#171's** scope, not #170's.
3. **Scope #170 to the XML engine** (`diff_bill.py`) where the signals are reliable.
   PDF (`diff_pdf.py`) is a sequenced follow-up with its own PDF-only fixture, because
   its tree depth is detection-path dependent (ADR 0012).

**This revises the epic's stated gate.** Epic #175 and the #8 note say "the six xfail
pairs become the acceptance gate — improved matching flips them to XPASS." The spike
measured that only **two** of the six are structurally fixable without regression. The
honest #170 success measure is: *flip `contested-4` and `extreme-alien-snap` to XPASS,
zero regression on the six anchors and the corpus dead-zone, and reclassify the other
four xfails as a calibration finding for #171.* Chasing all six via threshold moves
trades one dead-zone error for another (evidence below).

---

## Problem in plain terms

Two versions of an appropriations bill are diffed section by section. The engine must
decide, for each section: is this the *same* provision (edited) or a *different* one
(removed + added)? Two hard sub-decisions:

- **Split guard** — a pair already matched by path but whose text changed a lot: keep as
  `modified`, or tear into removed+added? Governed by `_SIMILARITY_THRESHOLD = 0.40`.
- **Move rescue** — a removed and an added that are really the same provision relocated:
  re-link as `moved`? Governed by `_MOVE_THRESHOLD = 0.60` (global greedy, no positional
  constraint).

Text similarity (difflib word-ratio) has no skill in the 0.40–0.70 band: appropriations
boilerplate ("None of the funds made available by this Act…", "Section X is amended by
striking…") inflates the ratio for unrelated provisions, while a stub expanded to full
text collapses it for the *same* provision. #170 asks whether the leveled tree
(division › title › major › agency › account › section) can carry the decision instead.

### How matching actually works today (premise correction, verified)

The "text similarity carries the whole decision" framing overstates it. XML matching
(`match_nodes`) keys on **exact `match_path` equality** first; text similarity only
enters as the collision tiebreaker (`_similarity_pair`), the 0.40 split guard, and the
0.60 move rescue. `match_path` is already a *normalized* key: lowercased
(`normalize_header`), division excluded, title enum stripped (`bill_tree._build_paths`).
So #170 is a **refinement of an already-structural matcher plus new signals**, not a
text→structure flip.

---

## Empirical findings

Corpus: 17 bills with ≥2 adjacent versions, **70 adjacent version pairs**, 30,605 matched
pairs, 1,013 currently `modified`, 1,280 `moved`. Collisions are common: **23 / 70**
version pairs contain at least one `match_path` shared by >1 node (1,256 colliding paths
total). All four #8 bills are present in XML and PDF.

### F1 — The tree's `display_path` is NOT a match key; `match_path` already is

`structure_tree.TreeNode` carries only `display_path` — division-qualified, original
case, enum-bearing (e.g. `Division C: …`, `TITLE I—…`, `sec. 237`). That vocabulary is
exactly what the matcher was built *not* to use: re-lettered divisions and renumbered
titles change every descendant `display_path`, so keying on it would fail bill-wide.
Measured churn: `contested-4-tanker` and `anchor-move-hud-237` both cross divisions
(C→F) with identical provisions; their `display_path` changes but their `match_path`
(division-excluded) is stable. **Conclusion: for XML, the normalized match key already
exists as `BillNode.match_path`; #170 does not need a new tree key — it needs to add
structural *signals* on top of the existing join.** (If a future tree-native matcher is
built, derive a `TreeNode.match_key` from the same normalization; see required-content §1.)

### F2 — The header signal is reliable for accounts, weak for sections

Fraction of nodes carrying a non-empty `header_text`, by leaf level (corpus-wide):

| leaf level | has header |
|---|---|
| appropriations-intermediate (agency) | 98.2% |
| appropriations-major (department) | 94.7% |
| appropriations-small (account) | 88.5% |
| subsection | 65.3% |
| **section (general/administrative provisions)** | **21.2%** |
| front-matter | 0% |

The three `contested-1/2/3` false-keeps are all bare general-provisions sections with
**empty headers on both sides** (verified in raw XML: `<enum>232.</enum><text>…` with no
`<header>`). The header signal is simply *absent* where those three need it.

### F3 — Header equality is discriminating only when scoped by `match_path`

Most-reused headers corpus-wide (distinct sections sharing them): `short title` (64×),
`in general` (61×), `definitions` (50×), `salaries and expenses` (45×, one per agency),
`report` (36×). Header equality alone would link any agency's "salaries and expenses" to
any other's. But `alien snap eligibility` appears 5× (once per version of 119-hr-1 —
bill-unique) and `tanker security program` 3×. **Header equality is safe as a
tiebreaker *within* a `match_path`-scoped collision group (which already localizes it to
one subtree), and as a keep-confirmer only when the header is specific/rare — not as a
global keep-override.**

### F4 — The #8 answer key, structural signals extracted

For each of the 12 labeled pairs, located in the real XML (matched on frozen body text):

| pair | label | dec | body_sim | leaf | match_path eq | header old → new | structural verdict |
|---|---|---|---|---|---|---|---|
| contested-1-va-232 | different | split | 0.429 | section | ✓ | `''` → `''` | **no signal** (headerless, same slot) |
| contested-2-corps-110 | different | split | 0.447 | section | ✓ | `''` → `''` | **no signal** |
| contested-3-interior-204 | different | split | 0.462 | section | ✓ | `''` → `''` | **no signal** |
| contested-4-tanker | same | split | 0.255 | **account** | ✓ | `TANKER SECURITY PROGRAM` → `(INCLUDING RESCISSION)` (sim 0.0!) | **account-path keep** ✓ |
| contested-5-ag-to-hhs | different | move | 0.629 | section | ✗ | `''` → `Medicare Improvement Fund` | cross-agency (see F6) |
| anchor-same-crs | same | split | 0.995 | account | ✓ | match | high text (keep) |
| anchor-same-sec716d | same | split | 0.994 | subsection | ✓ | `''` → `''` | high text (keep) |
| anchor-diff-sec780 | different | split | 0.154 | section | ✓ | `''` → `''` | low text (split) |
| anchor-diff-sec252 | different | split | 0.203 | section | ✓ | `''` → `''` | low text (split) |
| anchor-move-hud-237 | same | move | 1.0 | section | ✗ (237→234) | `''` → `''` | renumber, same agency ancestor |
| anchor-move-dod-135 | same | move | 1.0 | section | ✗ (135→138) | `''` → `''` | renumber, same agency ancestor |
| extreme-alien-snap | same | split | 0.078 | section | ✓ | `Alien SNAP eligibility` → same (sim 1.0) | **specific-header keep** ✓ |

Two traps this surfaces, both counter to the issue's framing:

- **The header signal *inverts* on `contested-4-tanker`.** `header_text` is
  `TANKER SECURITY PROGRAM` (old) vs `(INCLUDING RESCISSION)` (new) — a header-equality
  keep rule would **break** this pair. What actually links them is the stable *account*
  `match_path` leaf (`tanker security program`) plus the leaf level being a money account.
  The issue's "identical TANKER SECURITY PROGRAM heading is the context signal" is not
  what the data shows; the account-path is.
- **`contested-1/2/3` are structurally identical to the two `anchor-diff` true-splits**
  (`sec780`, `sec252`): same path, empty header, section leaf. The only thing separating
  "reused number, genuinely different" (should split) from "same provision, edited"
  (should keep) when the header is absent is the body text. Re-reading the fixture
  rationales confirms the author already tagged this: `contested-4/5` and `alien-snap`
  invoke "STRUCTURAL CONTEXT (for #170)"; `contested-1/2/3` talk only about the floor
  "sitting just above 0.40." Three pairs are structural; three are calibration.

### F5 — A structural classifier scores 12/12 on the answer key, but one lever is overfit

Prototype rule (structure primary, text one signal among several):

```
SPLIT: keep if  body_sim >= HIGH_KEEP
            or (leaf is a money account AND match_path leaf equal)      # durable account id
            or (both headers present AND header_sim >= 0.8)             # specific titled section
        else split
MOVE:  rescue if body_sim >= 0.60 AND (parent match_path eq OR header match) else leave split
```

| | split precision / recall | move precision / recall | total |
|---|---|---|---|
| baseline (0.40 / 0.60) | 0.40 / 0.50 | 0.667 / 1.0 | 6/12 |
| structural prototype | **1.0 / 1.0** | **1.0 / 1.0** | **12/12** |

The 12/12 is real **but two of its rules do not survive corpus stress** (F6, F7). The
account-path keep and the specific-header keep survive; the `HIGH_KEEP` floor-raise and
the parent-path move gate do not.

### F6 — Adversarial stress: the floor-raise and move-gate fail corpus-wide

**Raising the split floor (the `HIGH_KEEP` lever).** The prototype fixes `contested-1/2/3`
only because `HIGH_KEEP=0.60` splits their 0.43–0.46 while nothing "same" sits below 0.99
*in the 12-pair set*. Corpus-wide, **14** matched section-pairs would flip `modified`→`split`
at a 0.60 floor. Some are correct (the reused-number provisions), but at least two are
**genuine edits a 0.60 floor would wrongly split**:

- `118-hr-8774 Sec. 8144` (0.554): headerless section, `None of the funds… EFMP—` (214 ch)
  expanded to the full enumerated provision (590 ch). Same provision, stub→expanded — a
  *headerless* analog of Alien SNAP that structure **cannot** rescue (no header, not an
  account). A 0.60 floor mis-splits it.
- `118-hr-4366 Sec. 253` (0.590): identical opening, `Veterans Medical Care and Health
  Fund` → `Cost of War Toxic Exposures Fund` — same quarterly-report mechanism, repointed.

There is no clean floor value: `contested-3` (0.462, should split) and `Sec. 253` (0.590,
arguably keep) bracket every candidate. **Raising the floor trades one dead-zone error
for another.** Do not do it in #170.

**The parent-path move gate.** "Rescue a move only if parent `match_path` matches" would
demote **520 of 1,280** current moves. Reason: a subsection like `sec.508/(c)` has parent
`sec.508`, which *changes* when the section renumbers to `409` — so it demotes genuine
renumber-moves. Switching to the **agency-level ancestor** (strip trailing `sec.`/`(x)`
enums) still demotes 421 (127 with real text), and many of *those* are **genuine
cross-agency relocations** (e.g. `general provisions/sec.404` → `government-wide/…/sec.715`
at 0.948). This is the core insight: **genuine moves cross subtrees by definition, exactly
like false ones**, so a structural move-gate suppresses real relocations. `contested-5`
(0.629, false) vs the genuine relocations (0.95+) is separated by *text quality in a dead
zone*, not by structure. Move classification is a calibration problem parallel to the split
floor.

**Header-keep false-keep risk.** 13 corpus pairs have matching headers but body_sim < 0.40
(currently split). All but one are the generic `In general` / `Definitions` catchlines
(F3) on #188 run-in subsections — a naive header-keep would false-keep unrelated
provisions. Only `Alien SNAP eligibility` is specific. Confirms header-keep must be
collision-scoped and/or specificity-guarded.

### F7 — 119-hr-1 worked case, end-to-end

`reported-in-house` → `engrossed-in-house`, Committee on Agriculture › Nutrition:

| version | node @ path `…/sec. 10012` | header | body len |
|---|---|---|---|
| reported | Alien SNAP eligibility | `Alien SNAP eligibility` | 81 |
| reported | Emergency food assistance | `Emergency food assistance` | 133 |
| engrossed | Alien SNAP eligibility | `Alien SNAP eligibility` | 2242 |
| engrossed (`sec. 10013`) | Emergency food assistance | `Emergency food assistance` | 133 |

The collision at `sec. 10012` is old={Alien, Emergency}, new={Alien} (Emergency
renumbered out to 10013). Measured: **the collision already pairs correctly** — within the
group, Alien↔Alien (0.078) beats Emergency↔Alien (0.049), so `_match_collision_group`
returns Alien→Alien, Emergency→None. Emergency then correctly becomes `moved` 10012→10013
via `reconcile_moves` (text sim 1.0). The *only* bug is downstream: the split guard tears
Alien SNAP into removed+added because 0.078 < 0.40. Current output: Alien SNAP =
`removed`+`added` ❌, Emergency food = `moved` ✓.

**The fix lives entirely at the split guard.** Alien's headers are equal
(`Alien SNAP eligibility`) *and* bill-unique *and* it won the collision pairing — all three
say keep. Recommendation 1 fixes it with no move-logic change. (The issue's feared 0.50
wrong-pairing — Alien_old × Emergency_new@10013 — never fires: Emergency_new is claimed by
its 1.0 self-match first. It is a latent risk if Emergency were also edited; the header
tiebreaker neutralizes it.)

---

## Candidate approaches, with measured results

| approach | what it needs | answer-key | corpus verdict |
|---|---|---|---|
| **A. Account-path keep** at split guard (money-account leaf + equal `match_path` → keep) | leaf tag, `match_path` | fixes `contested-4` | **Safe.** 3 corpus rescues, all correct (tanker + 2 RDT&E accounts kept across re-funding). Recommend. |
| **B. Specific-header keep** at split guard (collision-scoped, specific header match → keep) | `header_text`, collision scope | fixes `alien-snap` | **Safe if scoped + specificity-guarded.** Unscoped: 13 false-keep candidates (generic `In general`). Recommend, scoped. |
| **C. Header as collision tiebreaker** in `_match_collision_group` | `header_text` | hardens 119-hr-1 pairing | **Safe** (match_path already localizes). Recommend as robustness. |
| **D. Raise split floor** (0.40 → ~0.6) | body_sim | fixes `contested-1/2/3` | **Refuted.** 14 corpus flips include genuine edits (`Sec.8144`, `Sec.253`). Reject. |
| **E. Parent/agency-path move gate** | `match_path` ancestry | fixes `contested-5` in isolation | **Refuted.** Demotes 421–520 genuine moves incl. real cross-agency relocations. Reject as a gate. |
| **F. Renumber confirmation** (same agency ancestor, changed section enum → high-confidence move) | `match_path` ancestry | consistent with hud/dod | **Promising** positive signal; lets renumbers be trusted at lower text sim. Recommend as follow-up, not a gate. |
| **G. Sibling-sequence (LCS) alignment for position** | ordered siblings under a shared ancestor | not needed for the 12 | **Not required.** The answer key resolves without position; absolute index is insertion-fragile. Defer; if added, LCS over sibling label-keys (never ordinal), scoped to collision tiebreaking. |
| **H. Boilerplate-discounted similarity** (down-weight common appropriations phrases) | corpus term stats | plausibly fixes `contested-1/2/3` (share only boilerplate) without splitting `Sec.8144` (shares specific content) | **The real fix for the calibration cases — but it is #171's template-aware scope, not #170.** |

---

## The five required contents (from the 2026-07-08 review)

**1. Normalized tree match-key vocabulary.** For XML, the normalized key already exists as
`BillNode.match_path` (lowercased, division-excluded, title-enum-stripped) and is what
`match_nodes` joins on today — do **not** key on `TreeNode.display_path` (F1: division/title
churn breaks it bill-wide). #170 adds *signals* to the existing join, it does not introduce
a new key. If/when a tree-native matcher is built, add `TreeNode.match_key` derived from the
same `normalize_header` machinery (normalized label; strip enum at division/title/section
levels; keep it division-independent) so the tree speaks the matcher's vocabulary rather
than the display vocabulary.

**2. Alignment-based sibling position.** Position is **not required** to pass the answer key
(F5) and is insertion-fragile as an absolute index (one inserted account shifts every
sibling's ordinal). Renumbering is already handled by the text-similarity move rescue
(`reconcile_moves`), not by position (F6). If position is added later it must be **LCS-style
alignment over sibling label-keys** within a shared agency ancestor — the exact pattern
`diff_pdf.py` already uses (`SequenceMatcher` over `_block_key` sequences) — and scoped to
collision tiebreaking, never a global ordinal key. Lower priority than A/B/C.

**3. Per-engine scope.** Implement A/B/C on the **XML engine (`diff_bill.py`) only** in
#170. The structural signals are reliable there (typed leaf tags; 88–98% header coverage on
accounts). **PDF (`diff_pdf.py`) is a sequenced follow-up** with its own PDF-only fixture:
it has no `match_path` (aligns `_block_key` sequences), its header analog is the anchor
catchline, and its tree depth is detection-path dependent (ADR 0012) so the agency ancestor
is not always present. The split/move constants are **duplicated** across engines
(`diff_pdf.py` has its own `_PAIR_BODY_THRESHOLD` / `_MOVE_SIMILARITY_THRESHOLD`); if both
engines change, give the constants a single shared home first, and the renderer is
pipeline-blind (ADR 0006/0007) so nothing downstream flags drift.

**4. Per-threshold sequencing.**
- Split guard (0.40): land the **structural keep-override (A + B) first**; it only ever
  *keeps* pairs the floor would split, so it is behavior-preserving except on the rescued
  cases. **Do not change 0.40** (F6: no clean value). `contested-1/2/3` stay xfail.
- Move threshold (0.60): **do not loosen** — `reconcile_moves` is a global greedy with no
  positional constraint, and loosening widens the boilerplate false-move surface #171
  documents. Any move change comes *after* renumber-confirmation (F) exists, and cross-agency
  relocation calibration (`contested-5`) is a separate, measured decision — not bundled here.
- Order: (A account-path keep) → (B/C header keep + collision tiebreak) → [later] (F renumber
  confirmation) → [later, with evidence] move-threshold calibration.

**5. Detection-path asymmetry rule.** Path-evidenced move classification (renumber vs
relocation) must require **both versions to expose the same level depth**; otherwise
degrade to today's text-only move rescue. Corpus hardening the spike surfaced:
**exclude empty-body nodes from move rescue** — they produce spurious 1.0 "moves" (F6, the
`department of defense/administrative provisions/sec. 122` empties). On PDF this matters more:
if v1 and v2 take different detection paths, breadcrumb depth differs and "parent changed →
relocated" would mint mass false relocations from extraction noise (ADR 0012).

---

## Recommended implementation sequence (respects the epic's verification gates)

The epic's suggested order puts **#167 for the diff-validation set** and the **#172 extent
gate** before #170. Assuming those are in place:

1. **Add the account-path keep (A)** at the split guard, XML only. Smallest diff; keeps a
   matched money-account pair as `modified` when `match_path` is equal regardless of body
   sim. Verify: `contested-4-tanker` flips to XPASS; the 3 corpus account rescues stay
   correct; `test_diff_validation.py` dead-zone tests unchanged (this doesn't move 0.40).
2. **Add the specific-header keep + collision tiebreaker (B + C)**, XML only, with a
   generic-catchline guard (frequency-derived stoplist or "specific within the collision
   group"). Verify: `extreme-alien-snap` flips to XPASS; 119-hr-1 renders Alien SNAP =
   `modified`, Emergency food = `moved` 10012→10013; no regression on the allowlisted
   cross-division collision bills; the 13 generic-header candidates are screened out.
3. **Update the pinned tests *with* evidence, in the same PR.** `test_similarity_labels.py`:
   move `contested-4` and `extreme-alien-snap` off `xfail` (they become the structural
   acceptance gate); **document `contested-1/2/3` and `contested-5` as remaining xfails with
   a comment pointing here and to #171** (they are calibration, not structure). Refresh the
   precision/recall guardrails in `test_diff_validation.py` with the new confusion matrices.
4. **File the calibration finding** (or fold into #171): boilerplate-discounted similarity is
   the path to `contested-1/2/3`; cross-agency move calibration is the path to `contested-5`.
   Neither is a threshold nudge; both need term statistics / template awareness.
5. **PDF follow-up** (separate PR, own PDF-only fixture): port A/B/C to `diff_pdf.py` using
   the anchor catchline, with the detection-path-depth guard (§5). Shared constant home first.

### Adversarial self-check (what would make the recommendation wrong)

- *If money accounts commonly get their number/name reused for a different account*, rule A
  false-keeps. Measured: the 3 corpus account rescues are all genuine same-account
  re-funding; appropriations accounts are durable identities (that is the point of the
  account level). Low risk; the split guard still fires on genuine account *replacements*
  because those change the `match_path` leaf.
- *If a specific header is reused for two genuinely different provisions in the same subtree*,
  rule B false-keeps. Mitigated by collision-scoping (the competing candidates share a path
  and the tiebreaker picks the best) plus the generic-catchline guard. Residual risk is small
  and strictly better than today's body-only tiebreak.
- *The recommendation deliberately does NOT fix four of the six xfails.* That is the finding,
  not a gap: the corpus shows those four are a text dead zone where every threshold move
  trades one error for another, and structure carries no signal (headerless sections /
  cross-subtree relocations). Pretending #170 fixes them would ship a floor-raise that
  mis-splits `Sec. 8144` and `Sec. 253`.
