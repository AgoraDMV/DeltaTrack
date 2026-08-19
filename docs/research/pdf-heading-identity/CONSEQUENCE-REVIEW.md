# Candidate 3 consequence review — RULING: A, BLOCKED

Not because of raw segmentation instability. **Raw instability turns out not to be the
right invariant**, and this review's main result is which invariant should replace it.

Candidate 3 was run **unchanged** through the real pipeline — anchors → blocks and
ordinals → `_block_key` → `SequenceMatcher` opcodes → round-1 considered population →
`CandidateSet` → settled correspondences → round-2 unmatched → round-2 moves → classified
hunks → canonical — on every adjacent version pair touching a document where its
segmentation differs. `src/` is untouched; `extract_anchors` is monkeypatched inside the
probe and restored.

*Emission shape, stated because it matters:* the probe emits at most one agency plus one
account per leaf, exactly as `_account_anchors_by_size` does, and moves only the boundary
between them. Where Candidate 3 joins a whole run there is no container left to emit, so
no agency anchor is produced — that is a consequence of the join, not of the probe.

## 1. The 2 novel false joins

Both are the same pair, both decided by `C5_fullness_join` (slack −67.5 / −67.8: the
container line runs 326 pt of a 335 pt column, so there is no early break to see).

| | |
|---|---|
| bill/version | `118-hr-4366/5_engrossed-amendment-house` p234 L4, and `114-hr-2578/rs` p121 L5 |
| printed boundary | `NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION` \| `OPERATIONS, RESEARCH, AND FACILITIES` |
| XML truth | `[[0], [1]]` — **two** logical headings |
| shipped segmentation | `NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION` + `OPERATIONS, RESEARCH, AND FACILITIES` — **correct** |
| Candidate 3 segmentation | one segment: `NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION OPERATIONS, RESEARCH, AND FACILITIES` — **wrong** |
| overlaps an instability? | `114-hr-2578` yes (causes 2 of the 3). `118-hr-4366` **no** — NOAA is scored in only one version of that bill, so the same error is invisible to the stability check |

### The exact structural consequence

```
shipped     L5  agency   'NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION'
            L6  account  'OPERATIONS, RESEARCH, AND FACILITIES'
                breadcrumb: TITLE I > DEPARTMENT OF COMMERCE >
                            NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION >
                            OPERATIONS, RESEARCH, AND FACILITIES

candidate3  L5  account  'NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION OPERATIONS, RESEARCH, AND FACILITIES'
                breadcrumb: TITLE I > DEPARTMENT OF COMMERCE >
                            NATIONAL INSTITUTE OF STANDARDS AND TECHNOLOGY >
                            NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION OPERATIONS, RESEARCH, AND FACILITIES
```

Three distinct damages, in one place:

1. a heading label is **fabricated** — that string is never printed as one heading;
2. a real container node **disappears** from the tree;
3. the account is **reparented under a different, real, wrong agency** — `NATIONAL
   INSTITUTE OF STANDARDS AND TECHNOLOGY` — because the breadcrumb walk, finding no NOAA
   anchor, reaches back to the previous agency.

(3) is the serious one. It is not a degraded or missing answer; it is a confident wrong
one, and it files NOAA's Operations, Research and Facilities appropriation under NIST.
Identical in both bills.

## 2. The 3 instabilities, and their overlap

| # | bill | XML heading | cause | overlaps a novel false join |
|---|---|---|---|---|
| 1 | `114-hr-2578` | `national oceanic and atmospheric administration` | the NOAA false join at rs p121 | **yes** |
| 2 | `114-hr-2578` | `operations research and facilities` | the **same** false join — one printed occurrence, two oracle headings | **yes** |
| 3 | `115-hr-5895` | `grants for construction of state extended care facilities` | a **missed** join at 4_eas p159 (`C4_fullness_split`) — the balanced-break case | no |

So 2 of 3 instabilities are one false join counted twice, and the third is a missed join.
There is no instability whose cause is cross-version asymmetry *per se*.

## 3. Pipeline results, adjudicated against XML truth

| pair | anchors | round-2 unmatched | moves | added |
|---|---|---|---|---|
| `114-hr-2578` rfs→rh | 229/198 → 224/193 | — | 0 → 0 | — |
| `114-hr-2578` rh→rs | 198/430 → 193/421 | (0,232) → (0,228) | 0 → 0 | 232 → 228 |
| `115-hr-5895` 2→3 | 454/454 → 432/432 | — | 0 → 0 | no hunk change |
| `115-hr-5895` 3→4 | 454/481 → 432/464 | (137,164) → (135,167) | **60 → 52** | 120 → 121 |
| `118-hr-4366` 4→5 | 737/1532 → 704/1481 | (135,931) → (136,914) | 64 → 65 | 869 → 851 |

**Every stage moves**, which is expected: corrected observation production propagates.
The question is whether the deltas are corrections. Adjudicated:

**The hunk deltas are overwhelmingly corrections.** Hunks present only under shipped are
fragments — `ACTS`, `CORPORATION`, `FUND`, `CIVIL WORKS`, `DECOMMISSIONING`,
`ADMINISTRATION`, `COMMISSION`, `RESTORATION`, `MISCELLANEOUS PAYMENTS TO INDIANS`.
Hunks present only under Candidate 3 are the corresponding complete headings. That is
#524 being fixed, visible in canonical output.

**On the pair that carries almost every PR #639 disputed row (`115-hr-5895` 3→4), false
`Renumbered` cards fall from 15 to 4**, adjudicated by whether the two labels are
fragments of one printed heading:

```
shipped     60 moves   15 false-fragment   40 distinct-label   5 relocated
candidate3  52 moves    4 false-fragment   42 distinct-label   6 relocated
```

Removed naturally, with no change to `_pdf_move`: `NAVY AND MARINE CORPS → AND MARINE
CORPS`, `HOUSING IMPROVEMENT FUND → FUND`, `POWER ADMINISTRATION → ADMINISTRATION`,
`TRATION → MAINTENANCE, WESTERN AREA POWER ADMINISTRATION`, `FOR CIVIL WORKS → CIVIL
WORKS`, `ARMY → FAMILY HOUSING OPERATION AND MAINTENANCE, ARMY`, and five more.

Preserved: **all** genuine section renumberings (`SEC. 103 → SEC. 102` and 30 more), the
genuine heading edit (`CYBERSECURITY, ENERGY SECURITY… → …ENERGY SECRUITY…`, now with
complete labels on both sides), and the distinct-account mispair (`ELECTRICITY DELIVERY →
NUCLEAR ENERGY`).

### Per-instability verdict

| | false added/removed/modified/moved? | false Renumbered/relocation? | wrong correspondence? | fabricated tree/breadcrumb? |
|---|---|---|---|---|
| 1–2 NOAA | **yes** — two correct `added` hunks become one wrong one | no (pair emits 0 moves) | no | **yes** — container deleted, account reparented under NIST |
| 3 GRANTS | no | **yes**, but **not novel** — shipped emits `FACILITIES → STATE EXTENDED CARE FACILITIES` for the same provision; Candidate 3 emits `GRANTS FOR CONSTRUCTION OF STATE EXTENDED CARE FACILITIES → STATE EXTENDED CARE FACILITIES`. One false card either way, and the pair's total falls 15 → 4 | no | no |

## 4. A, B and C do not need the same invariant

- **A — within-document segmentation (#524's actual scope).** Candidate 3 solves it, and
  the pipeline shows the fix reaching canonical output. Its failures here are **#501's
  class** (over-join of a container whose line fills the column), not #524's.
- **B — cross-version label identity.** Not safe. Four false-fragment cards survive on the
  worst pair, one of them from instability 3.
- **C — actual diff/correspondence correctness.** **Improved**, materially and measurably:
  false `Renumbered` 15 → 4, every genuine renumbering and heading edit preserved, no
  correspondence adjudicated as newly wrong.

Raw cross-version equality is therefore **not** the right gate. Instability 3 is a real
instability that costs nothing new, and the 118-hr-4366 false join is a real fabrication
that the stability check **cannot see at all** because that bill scores NOAA in only one
version. A gate on raw instability would have passed the damaging case and failed the
harmless one.

## 5. Ruling — A, BLOCKED

The blocking failure is named exactly: **the `NATIONAL OCEANIC AND ATMOSPHERIC
ADMINISTRATION` over-join**, at `114-hr-2578/rs` p121 and
`118-hr-4366/5_engrossed-amendment-house` p234. It is novel against shipped, it fabricates
a heading, it deletes a container, and it reparents an account under the wrong agency in
canonical output. Two occurrences in two bills is not an aggregate-noise argument away —
it is a confident wrong answer about where money sits.

This is **not** the cross-version instability question, and it earns a narrowly targeted
round: over-join of a container whose printed line leaves no early break. That is `#501`,
arriving at the account band, and it is the one thing standing between Candidate 3 and
implementation.

The GRANTS instability does **not** earn a round. It is non-novel and the pair's false
`Renumbered` count falls sharply with it present.

### Replacement invariant to govern any future candidate

Retire "zero raw cross-version segmentation instability". Gate instead on:

> **No candidate may produce a novel false join** — a boundary the independent XML oracle
> calls SPLIT, joined by the candidate where shipped split it. Measured per boundary over
> the combined evidence, reported with the identity of every instance, never as a rate.

with two supporting checks that are diagnostic rather than blocking: false-fragment
`Renumbered` cards must not increase on any adjacent pair, and no anchor's breadcrumb
parent may change to a different real container.

That invariant catches both NOAA sites, including the one no stability check can see, and
does not spend a round on an instability that costs nothing.

## Reproducing

```sh
uv run python docs/research/pdf-heading-identity/confounder/pipeline_consequence.py
```
