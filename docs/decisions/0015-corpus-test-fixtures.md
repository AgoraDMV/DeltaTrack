# 15. Commit a curated corpus fixture set and collect the gates from a manifest

- Status: Accepted
- Date: 2026-07-17

## Context

A large share of the test suite is data-driven: the correctness gates that prove the
parser reads a bill right ([0009](0009-validation-ground-truth.md)) run against real
bill XML and PDF documents. Collecting those gates from the filesystem —
`sorted(BILLS_DIR.glob(...))` evaluated at collection time — makes the number of test
cases equal to how many bill files a given clone happens to have fetched.

Two problems follow, one cosmetic and one not.

The cosmetic one: pass/skip counts are not comparable across machines. Reviewing PRs
#211 and #216 surfaced a two-environment gap of over a hundred tests that was entirely
a difference in local corpus size, not in the diff. A contributor cannot report a count
anyone else can reproduce, which weakens the "run it before you send it" evidence the
project asks for.

The real one: a gate that parametrizes over an empty glob collects zero cases and
passes green with no assertions — the fail-open failure mode the project keeps hitting,
the same risk [0009](0009-validation-ground-truth.md) guards against when it insists
validation "does not silently skip." Underneath sits an unpinned obtain step: the fetch
tooling resolves a live, growing committee listing, so the set is not reproducible over
time.

Collection is only the first place this fails open, which is why the contract below has
four parts rather than one. Measured on the three modules that were still glob-collected:
they produced **7 trivial passes, 12 skips, and parsed no document at all** — a run that
is green, non-empty, and asserts nothing. "Cases were collected" does not prove
assertions ran.

This decision reverses a documented earlier stance, so the reversal is stated openly
rather than left to be rediscovered. PRs #62/#64/#66 deliberately made the corpus
fetch-scripted and gitignored, on the reasoning that a clean clone should not need a
large download. That solved a real problem but left the parser's most important gates
with no CI signal and made counts machine-dependent.

The reweighing rests on two facts. First, bill documents are **immutable** (a published
version is frozen on govinfo) and **small** (committed subcommittee-bill PDFs here are
240–360 KB; omnibus prints run into the low MB), so committing them is a one-time cost
with no binary churn — the usual case against committing PDFs does not apply. Second,
comparable parsers of government documents commit their fixtures directly in plain git,
no LFS: Juriscraper ships on the order of ~88 MB, PyMuPDF ~98 MB. A curated bill set is
well inside that norm and far under any platform limit. US bills are public-domain
government works (17 U.S.C. 105), so committing them carries no licensing encumbrance.

## Decision

The corpus the correctness gates assert against is a **committed, curated, versioned
fixture set**, enumerated by a **committed manifest** that the gates parametrize over —
not the filesystem.

- **A curated committed set, not bulk.** The manifest names the exact bills (id +
  version) the gates run against, curated by structural variety — one bill per code path
  and document class — never the full mining corpus. Those bills are committed to git,
  which gives CI an offline, zero-fetch, byte-identical corpus.

- **Committed fixtures and downloaded working data live in separate trees.** The
  committed bill-fixture tier is tracked by default. The disposable corpus the fetch
  tooling downloads is a tier of its own, ignored in full, and may be deleted or
  symlinked in from another checkout at any time. A third tier holds the other tracked
  test data (validation JSON, committee-report source documents, goldens), also tracked
  by default, with specific local-only artifacts ignored.

  **Committed fixtures do not depend on per-fixture `.gitignore` re-admissions.** Adding
  a fixture that way required an ignore-file edit nothing enforced, and `git add` on a
  still-ignored path is a silent no-op — so a fixture could be written, staged in good
  faith, and still never tracked.

  Today those tiers are `tests/corpus/`, `bills/` and `tests/data/`.

- **The completeness contract is fail-closed in four layers**, because each one alone
  leaves a way to be green while proving nothing:

  1. **Collection is manifest-derived.** Gates parametrize from the manifest itself, and
     the parametrization list is never filtered by whether the file is present —
     presence-filtering it is noncompliant, because that is exactly the shape that fails
     open. A manifested fixture that is missing therefore stays represented in
     collection: the case itself skips with a reason, and the completeness floor below
     makes the gate fail, rather than the case quietly disappearing from the run.
  2. **Committedness, not presence.** Every manifested fixture must be on disk *and*
     tracked by git. A file the author has locally but never staged passes a presence
     check and then silently collects fewer cases on a fresh checkout. (Outside a git
     work tree — an unpacked sdist — git cannot answer, and presence alone is the
     fallback; the untracked-fixture failure only exists inside a working checkout.)
  3. **A non-zero floor.** A gate may not quietly parametrize over zero cases, even if
     the manifest were empty or a filter removed everything.
  4. **A content-skip ceiling on the committed gate.** The three layers above prove
     fixtures are committed and cases collected; they do not prove any assertion ran. The
     corpus gates skip per-case on content conditions, so a corpus-wide regression that
     turned every case into a content-skip would keep CI green asserting nothing. In the
     committed-manifest run, therefore, every content-skip in the watched modules must be
     allowlisted **by both node id and reason**: an unlisted skip fails the session, and
     so does an allowlisted case that begins skipping for a different reason. Adding an
     entry records a coverage gap and is a deliberate act, not bookkeeping. The ceiling is
     calibrated against the committed set, so it governs that run and not the broad sweep
     below.

  This is stated as guarantees rather than as one helper's behaviour, but it is a floor,
  not a menu: an implementation that filtered absent files out before parametrization,
  or that collected every case and skipped every assertion, does not satisfy it.

- **The broad sweep stays, as opt-in exploration.** Sweeping every locally-fetched bill
  has repeatedly caught bugs a few clean bills did not, and that value is real. It is
  exploration, not a gate, it does not run in CI, and CI must never depend on it.

- **The mining tier is not a test input.** The large research and mining corpus stays
  gitignored and outside this contract.

Alternatives considered:

- **Fetch on demand, pinned by a checksummed registry** (a pooch-style `filename
  sha256` list). This is the right tool when the pinned set is too large to commit, and
  **it is retained as the prescribed approach for the mining tier should it ever need
  reproducibility** — and for any other non-committed tier that needs reproducible
  pinned inputs; [0019](0019-observation-identity.md) cashes in that reservation for
  artifacts referencing a source outside git. Rejected for the *test* set, which is
  small and immutable, where committing removes the network from CI entirely and is
  simpler.
- **Git LFS / git-annex.** Rejected. Bills are re-fetchable from a durable host, so the
  need is to *pin* bytes, not *store* them off-repo; LFS pays storage, bandwidth and
  per-run CI-quota cost to version data already hosted free, and ties the repo to LFS
  hosting.
- **Status quo — glob-discovered collection.** Rejected: the direct cause of
  non-comparable counts and of correctness gates that fail open with no CI signal.

## Consequences

- **Test counts are reproducible** — the collected set is the manifest, identical
  everywhere — so reviews no longer chase environment-driven count gaps. CI green gains
  meaning it lacked: the corpus correctness gates actually run there, against a known
  set, and fail closed if the set is incomplete.

- **A size bar for fixture additions.** Committing fixtures trades repository weight for
  CI coverage, and git keeps blobs permanently — a fixture added is a fixture the clone
  carries forever, even if later removed. So a fixture addition should **prefer XML over
  PDF** wherever the gate under test accepts either (XML compresses roughly 4.5×, where
  these PDFs are near-incompressible and dominate the on-disk cost); **carry a stated
  reason in the PR above roughly 1 MB compressed per bill**, naming the specific gate
  that needs *that* document rather than a smaller or synthetic stand-in; and **prefer a
  single stage** over a whole version history unless adjacent-version diffing is the
  thing being gated. This is reviewer guidance, not a hard cap: the point is that each
  addition is a deliberate choice rather than growth by precedent.

- **A test's extra requirement is expressed as a marker, not an environment variable.**
  A marker is registered, discoverable in `-m` expressions, and names one requirement.
  A shared env var is none of those, and one here drifted into meaning two unrelated
  things — a network, and a set of uncommitted bills — under a name that described
  neither, so neither requirement was visible at the point it applied.

- **Fixture locations have one resolution authority.** Consumers do not respell
  repository paths independently, so a future move is one edit rather than thirty, and a
  path that stops resolving fails in one place. This is enforced, because the failure it
  prevents is silent: a committed fixture addressed through the disposable tree resolves
  on a machine that downloaded it and is simply absent in CI. The dangerous spelling is
  the composed one — a download root bound once and joined to a bill id hundreds of lines
  away — because the two never appear together to be grepped for. Currently
  `tests/corpus_paths.py`, with `tests/test_fixture_layout.py` as the guard.

- **CI runtime rises**: the corpus gates are slow and PDF extraction has no CI cache, so
  the curated set is sized against a CI time budget. The completeness floor always runs
  on every PR; a larger slice may run on a separate cadence, and the floor applies
  wherever the gates run.

- **The layered suite is unchanged.** Synthetic in-memory fixtures stay the hermetic
  floor; the committed corpus is the real-document layer, now fixed and CI-run rather
  than variable and local-only; the independent committee-report validation
  ([0009](0009-validation-ground-truth.md)) remains the top layer.

- **The repository grows by the committed set** (tens of MB, one-time, no churn since
  bill versions are immutable). Expected-output snapshots, not the bills, are the churn
  to watch, and are regenerated deliberately.

- **Reproducibility of the fetched corpus over time stops mattering for tests**, since
  tests no longer depend on the fetch path. It remains a caveat for building research
  corpora, documented where the fetch tooling lives.
