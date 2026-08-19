# #524 external validity — RULING: B, MIXED

The development result at `9af49c0` is in-sample: the same corpus discovered the
typography signal, composed the rule and chose the operating point. This is the
out-of-sample test.

**Base**: `origin/develop` at `be76356`. Only `docs/architecture.md` changed since the
prior research base `19108be`; `pdf_text.py`, `pdf_anchors.py`, `pdf_blocks.py`,
`pdf_observations.py`, `diff_pdf.py`, `formatters/canonical.py`, the corpus manifest and
the fetch/corpus infrastructure are byte-identical, so the frozen numbers carry over.

**Frozen candidate**: `frozen/frozen_candidate.py`,
sha256 `2139aaf3eae0ec67f3319ee170b3b701ebbfd07631e8d3f18d87949323af6840`, T = 0.5.
`frozen/freeze_check.py` refuses to produce a number if that digest moves. Negative
control: mutating the operating point (`T` 0.5 -> 0.6) and mutating a load-bearing
predicate (`D5`'s `cl < t` -> `cl <= t`) each made the check exit 1 naming both digests;
restoring returned it to green. The frozen module reproduces the in-sample development
result exactly at T=0.5 — shipped 30 false / 654 missed, candidate 1 false / 27 missed
over 1698 boundaries — so what was validated is what was measured.

## Holdout

Selection rule and seed are pre-registered in `holdout/select_holdout.py`; the draw is
`holdout/draw_holdout.py`; provenance is `holdout/holdout_manifest.json` (bill id,
Congress, stage, govinfo package, PDF and XML sha256, byte sizes, every rejection with
its reason). Seed 20260819.

Frame 91,003 bills -> 815 with a version XML >= 300 KB -> 796 after excluding every bill
present in `tests/corpus/` **or** the repository's gitignored `/bills` download tree.
That second exclusion was a correction made before any draw: the first implementation
read the *worktree's* `bills/`, which is empty, and would have admitted `116-hr-133` —
a bill discovery could have swept. A holdout that leaks is not a holdout, so the
selection rule resolves the main checkout via `git rev-parse --git-common-dir`.

Drawn: **21 bills, 39 versions, 3 bills per Congress across 113-119**, nine stage types
(`ih`, `rh`, `rfs`, `rs`, `pcs`, `eh`, `eas`, `eah`, `rds`). Zero overlap with either
seen tree, verified by set intersection. Artifacts live in `bills/_holdout524/`, covered
by the existing `/bills` ignore rule; nothing was added to `tests/corpus/`, to
`tests/corpus_manifest.toml`, or to any fixture tier.

## Oracle

`holdout/holdout_oracle.py` reuses `probes/heading_runs.py` unchanged. Truth is the
unique XML-admissible segmentation; it never calls the joiner, never reads caps-per-word
or the bootstrapped vocabulary, and never uses PR #639's `_heading_run()`. The shipped
parser decides only WHICH runs exist, never what is true about them.

| | |
|---|---|
| versions downloaded | 39 |
| excluded, `derive_size_bands` returned None (#508/#261) | 6 |
| bands but zero runs | 2 |
| versions yielding runs | 31 |
| bills contributing scored boundaries | 17 of 21 |
| runs | 4240 |
| multi-line runs | 1662 |
| unresolved multi-line runs | 93 (5.6%), all `no_valid_segmentation` |
| boundaries scored | 1768 |
| boundaries unresolved | 163 |

Unresolved runs are 2-line (37), 3-line (42) and 4-line (14), and spread across every
stage in rough proportion (`pcs` 31, `rh` 29, `rs` 12, `eh` 9, `rfs` 6, `ih` 5, `eas` 1).
One document concentrates them — `116-s-4775/pcs`, 8 of its 10 multi-line runs — but it
contributes 3 scored boundaries in total, so it cannot move an aggregate. The four bills
contributing nothing were all excluded by `no_size_bands`, which is the documented
out-of-scope path, not a selective drop. Exclusions are symmetric: a boundary removed
from the candidate's score is removed from shipped's too.

## Result — scored once, under the frozen digest

Typography contract check clean: 8,467 pages, 0 divergences from
`pdf_text._page_glyph_sizes`.

| | correct joins | correct stacks | **false joins** | **missed joins** | join precision | join recall |
|---|---|---|---|---|---|---|
| shipped | 165 | 927 | **34** | **642** | 0.829 | 0.205 |
| frozen candidate | 763 | 961 | **0** | **44** | **1.000** | **0.946** |

807 true wraps, 961 true stacks.

### Error identities, not just counts

| question | answer |
|---|---|
| novel false joins (candidate errs where shipped was right) | **0** |
| novel missed joins (candidate errs where shipped was right) | **0** |
| candidate false joins ⊆ shipped false joins | **True** |
| candidate missed joins ⊆ shipped missed joins | **True** |

**There are no candidate false joins to report**: the frozen rule fabricated no
structure anywhere on 17 unseen bills. Its 44 misses are a strict subset of shipped's
642. Every error it makes, shipped already made.

Per bill, candidate false joins are 0 on all 17; per stage, 0 on all 7. The result is
not carried by one bill or one layout family. Deciding clauses: `D2` 782, `D6` 380,
`D9` 371, `D5` 223, `D4` 8, `D1` 4. `D7` (the one non-fail-closed clause, which joins on
absent geometry) did not fire on the holdout, as it did not in-sample — it remains
untested by any measurement so far.

## Cross-version bootstrap stability — the falsifier, and it fired

932 headings the XML independently establishes in two or more versions of the same bill,
across the 7 multi-version bills. **930 stable, 2 not.** Measured per OCCURRENCE, after
correcting a first pass that kept only one occurrence per version and so mislabelled the
second case.

**1 pure cross-version.** `113-hr-2217`, `RESEARCH, DEVELOPMENT, ACQUISITION, AND
OPERATIONS`, printed identically in all three versions:

```
rfs  p54L17   -> 'OPERATIONS'                                        D5 caps split
rh   p53L21   -> 'OPERATIONS'                                        D5 caps split
rs   p54L17   -> 'RESEARCH, DEVELOPMENT, ACQUISITION, AND OPERATIONS' D1 vocabulary join
```
Same caps evidence on every side (upper 0.75, lower 0.0) and same slack (-11.6). `rs`
gets it right only because `rs` *also* prints the heading unwrapped at p148L23, which
puts the whole string into that document's account vocabulary, so `D1` fires ahead of
`D5`. `rfs` and `rh` have no such instance.

**1 intra-document, which is also cross-version.** `114-hr-2578`, `PUBLIC
TELECOMMUNICATIONS FACILITIES, PLANNING AND CONSTRUCTION`: correct in `rfs`, `rh` and at
`rs` p9, but `CONSTRUCTION` at `rs` p116, where the line breaks one word later and `D2`
fires because `construction` is in that document's account vocabulary. One document
segments one heading two different ways.

**Mechanism, stated once**: the vocabulary clauses `D1`/`D2` override the typography
clauses, and vocabulary content depends on what else the document happens to print. In
`113-hr-2217` that override rescues the right answer; in `114-hr-2578` it destroys it.
Both failures are in the declining-to-join direction — neither fabricates a container —
but both produce two different labels for one printed heading, which is exactly the
spurious `Renumbered` artifact the label exists to remove.

**Negative control**: injecting one document's container vocabulary with the upper line
of a stably-joined heading moved the count 2 -> 3 and named the new instability;
removing the injection returned it to 2. The check can go red.

## Ruling

**B — MIXED.**

Against the stated criteria for A:

| criterion | verdict |
|---|---|
| materially improves on shipped on unseen bills | **met** — 34 -> 0 false joins, 642 -> 44 misses, join precision 0.829 -> 1.000 |
| no consequential novel false-join mode | **met** — zero false joins at all; zero novel errors of either kind |
| not hidden by one catastrophic bill or layout family | **met** — 0 false joins on every one of 17 bills and 7 stages |
| cross-version segmentation is stable | **NOT met** — 2 of 932, with an unbounded mechanism |
| oracle exclusions do not create selection bias | **met** — symmetric, and driven by the oracle and the shipped parser, never the candidate |

Four of five are met, decisively. The fifth is the one the design nominated as its own
headline falsifier, and it fired. The standard is not lowered after the fact: two
measured instabilities mean cross-version segmentation is not stable, and B is the
outcome defined for exactly that shape.

What this splits into, precisely:

- **The segmentation itself is strongly externally valid.** For #524's own purpose —
  reading a wrapped account heading as one heading without collapsing a real
  container/account boundary — the frozen rule generalises: zero fabricated structure on
  unseen bills, a strict error-subset of shipped behaviour.
- **Using the resulting label as a cross-version identity is not yet validated.** That is
  what `moved-semantics.md` wanted it for, and it is where the residue lands.

Per the task's own gate, the development-corpus safety checks (error-set dominance, the
actual-final-segmentation pipeline A/B, and the PR #639 re-adjudication) are **not run**:
they are conditioned on outcome A.

## Exact remaining blockers

1. **Vocabulary precedence over typography is document-dependent and unbounded.** `D1`
   and `D2` outrank `D5`/`D6`, and their content depends on whether a document happens to
   print an unwrapped instance elsewhere. Both instabilities come through that door.
2. **No cross-version invariant is enforced anywhere.** Nothing today would catch a
   recurrence.
3. **`D7` remains unexercised.** The single clause that joins on absent geometry has not
   fired in-sample or out-of-sample, so its behaviour is asserted rather than measured.

Any change to (1) is a change to the frozen rule. Per the task's own constraint, a
modified candidate needs a NEW independent holdout — this one is spent. The 796-member
pool minus the 21 drawn bills is the obvious source, and the seed and rule are recorded
so the next draw can exclude the spent set mechanically.

## Reproducing

```sh
uv run python docs/research/pdf-heading-identity/frozen/freeze_check.py
uv run python docs/research/pdf-heading-identity/holdout/select_holdout.py
uv run python docs/research/pdf-heading-identity/holdout/draw_holdout.py
uv run python docs/research/pdf-heading-identity/holdout/holdout_oracle.py
uv run python docs/research/pdf-heading-identity/holdout/score_holdout.py
uv run python docs/research/pdf-heading-identity/holdout/cross_version.py
uv run python docs/research/pdf-heading-identity/holdout/cross_version.py --perturb
```

Holdout PDFs and XMLs are downloaded to the gitignored `bills/_holdout524/` and are
never committed; `holdout_manifest.json` carries the hashes that make the run
reconstructible without them.
