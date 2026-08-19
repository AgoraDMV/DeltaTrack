# Candidate 2 — NOT CONSTRUCTED. The permitted design space is exhausted.

Scope given: remove the result-changing document-local dependency that falsified
candidate 1, by investigating **only** whether `D1`/`D2` should be removed, demoted
behind stable typography, or made fail-closed; resolve `D7`; add no features and no
bill/layout/English exceptions.

That investigation is complete. **No configuration in the permitted space satisfies the
primary acceptance invariants**, and the reason is structural rather than a matter of
picking the right cell. No candidate 2 was frozen and no fresh holdout was spent.

## Evidence base

Original development corpus **plus** the now-spent 21-bill holdout, together treated as
development evidence: **3466 boundaries** over 3097 resolved multi-line runs, and **712
logical headings the XML independently establishes in two or more versions** of the same
bill, across 13 multi-version bills.

Shipped behaviour on that population: **64 false joins, 1296 missed joins.**

## The grid

`D1` (whole run matches an account-vocabulary entry -> JOIN) and `D2`/`D3` (lower side
matches an account entry, or upper matches a container entry -> SPLIT), each placed
ahead of the typography clauses, behind them, or removed. `D7` conservative throughout
(missing geometry -> decline to join).

| `D1` | `D2`/`D3` | false joins | **novel** FJ | missed joins | **novel** MJ | **unstable** |
|---|---|---|---|---|---|---|
| ahead | ahead *(= frozen candidate 1)* | 1 | 1 | 71 | 0 | **4** |
| ahead | behind | 19 | 19 | 55 | 0 | 2 |
| ahead | removed | 20 | 20 | 55 | 0 | 4 |
| behind | ahead | 1 | 1 | 72 | 0 | 3 |
| **behind** | **behind** | 19 | 19 | 56 | 0 | **1** |
| behind | removed | 20 | 20 | 56 | 0 | 3 |
| removed | ahead | 1 | 1 | 72 | 0 | 3 |
| **removed** | **behind** | 19 | 19 | 56 | 0 | **1** |
| removed | removed | 20 | 20 | 56 | 0 | 3 |

A fourth reading of "made fail-closed" was also tested: restrict the vocabulary clauses
to the **singleton** source (headings the document actually printed standalone) and drop
the slack-derived bootstrap entries. It is worse on both axes — **8 false joins, 5
instabilities** — and is rejected.

**Every false join in every row is novel.** Shipped's 64 are disjoint by construction:
shipped only ever cuts immediately before the leaf, so its false joins are inside runs
(container lines merged together), while the candidate's are at the leaf boundary.
Missed joins are never novel — the candidate's are always a subset of shipped's, in every
configuration.

**No row reaches zero instability.** The minimum is 1, and only at a nineteenfold
increase in novel false joins.

## Why the trade is structural

The 19 novel false joins introduced by demoting `D2` collapse to **2 distinct heading
pairs, and 18 of the 19 are the same one**, across seven unrelated bills
(`113-s-1371`, `115-s-3107`, `117-hr-4502`, `117-hr-8254`, `118-hr-2882`, `118-s-4928`,
`118-hr-4366`):

```
OFFICE OF INSPECTOR GENERAL     caps-per-word 0.0
SALARIES AND EXPENSES           caps-per-word 0.0     -> D6 joins them
```

`OFFICE OF INSPECTOR GENERAL` is a **container GPO sets in even small caps**, so it
carries no large capitals at all — caps-per-word 0.0, exactly like the account beneath
it. The typography signal is blind to this class by construction: it distinguishes
caps-and-small-caps containers from even-small-caps accounts, and says nothing about
even-small-caps *containers*.

What currently catches that case is `D2`, because `SALARIES AND EXPENSES` is a known
standalone account in those documents. So:

- `D2` is **load-bearing for precision** — it is the only thing holding novel false joins
  at 1 rather than 19;
- `D2` is **the source of the cross-version instability** — its vocabulary is
  document-local, so whether it fires depends on what else that document happened to
  print;
- therefore **precision and cross-version stability are coupled through the same
  clause**, and no reordering, removal or restriction of that clause can separate them.

Every instability observed is `D1`- or `D2`-caused, on both corpora:

| bill | heading | clause |
|---|---|---|
| `113-hr-2217` | `RESEARCH, DEVELOPMENT, ACQUISITION, AND OPERATIONS` | `D1` |
| `114-hr-2578` | `PUBLIC TELECOMMUNICATIONS FACILITIES, PLANNING AND CONSTRUCTION` | `D2` |
| `115-hr-5895` | `GRANTS FOR CONSTRUCTION OF STATE EXTENDED CARE FACILITIES` | `D2` |
| `118-hr-4366` | `LIMITATION ON INSPECTION AND WEIGHING SERVICES EXPENSES` | `D2` |

The last two are **on the original development corpus**. They were always there; nothing
had ever measured cross-version stability on it. The external-validity run did not
discover a holdout-specific weakness — it discovered a property of the rule that the
development study had not tested for.

## `D7`

Specified and tested in its conservative form throughout the grid (missing geometry ->
SPLIT, i.e. decline to join). It changes nothing measurable: `D7` has now failed to fire
on the development corpus, on the spent holdout, and on the combined set. It should still
be written conservatively in any future candidate, because "joins on absent evidence" is
not a property to keep by accident — but it is not the blocker, and no measurement here
depends on it.

## Ruling

**Candidate 2 is not constructible within the permitted scope.** Against the primary
acceptance invariants:

| invariant | best achievable in scope |
|---|---|
| no consequential novel false joins | 1 novel FJ — **met**, but only with `D2` ahead |
| materially better than shipped on missed joins | 56–72 against 1296 — **met** everywhere |
| no natural cross-version segmentation instability | **1 minimum, never 0** — **not met**, and only at 19 novel FJ |
| missing evidence fails closed | **met** (`D7` conservative), unexercised |
| negative controls can go red | not built — no candidate reached freezing |

Invariants 1 and 3 are satisfiable individually and not together. Nothing was frozen and
no new bills were exposed: spending a fresh independent holdout on a candidate already
known to fail an acceptance invariant on development evidence would consume a
non-renewable resource for no information.

## What would actually be needed

This is a newly discovered result-changing failure, which is the stated condition for
reopening. Escaping the trade needs evidence that separates a container from an account
**for containers set in even small caps**, and that is **not document-local**. By
definition that is a new feature, so it is a new methodology round, not a rearrangement
of this one.

Recorded so the next round does not re-derive it:

- the failing class is narrow and nameable — an even-small-caps container above an
  even-small-caps account — and it is what the whole trade turns on;
- any replacement for `D2` must be judged on cross-version stability from the start, not
  only on false joins and misses. That check now exists
  (`holdout/cross_version.py`) and it can go red;
- 712 comparable cross-version headings over 13 bills is enough development signal to
  falsify a candidate before a holdout is spent, and should be used that way.

Deferred work stays deferred: development error-set dominance, the actual-final-segmentation
pipeline A/B, and the PR #639 re-adjudication are all gated on a candidate that passes,
and none exists.
