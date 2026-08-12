# Release: promoting `develop` to `main`

`develop` is the integration branch and `main` is the protected release branch (see
[CONTRIBUTING.md](../CONTRIBUTING.md#branch-workflow)). Promotion is the only way work reaches
either public surface, and it is a deliberate, human-initiated step.

**Promotion is the maintainer's call to initiate.** A runbook step saying "open the
pull request" is a description of the sequence, not standing authorization to run it.
Raise it as a question and let the maintainer decide.

## Two surfaces, both keyed off `main`

Promotion updates both at once. Neither tracks `develop`.

| Surface | What it is | How it updates |
|---|---|---|
| The hosted comparison app | The FastAPI upload app | The server pulls from `main`, then a redeploy (below) |
| The example reports | Static reports linked from the README's "See it in action" | `.github/workflows/update-examples.yml`, on push to `main`. Copies the already-committed `examples/` directory into a Pages artifact and deploys it |

**The workflow does not render anything.** It used to, and that is worth stating plainly
because the older behaviour is still what is running on `main` today and is the version
most people will have seen. Since #42, rendering happens in exactly one place,
`scripts/render_examples.py`, run by a human and committed to `develop`.
`tests/test_committed_examples.py` (#284) re-renders from the committed corpus in the
normal CI job and fails if `examples/` no longer matches what the renderer produces, so
the files being published are already proven current before promotion.

One consequence is easy to miss: a promotion replaces `update-examples.yml` itself before
the push run executes, so the workflow that publishes is always `develop`'s, never the one
that was sitting on `main`.

Because Pages publishes what is on `main`, the reports lag whatever is on `develop`. A
long gap between promotions means the project's front page shows visitors an older build
of the renderer than the one the code produces.

## Sequence

Do these in order. The steps are separable and the ordering is what makes a failure
attributable.

1. **Confirm continuous integration is green on the exact commit being promoted.**
   CI runs on pull requests, on pushes to **both** `main` and `develop`, and on
   `merge_group` events, and the `develop` push run is the same full matrix a pull
   request gets. So the integrated state *is* checked automatically. Two separate
   mechanisms cover it: the merge queue tests each merge commit before it lands
   (prevention), and the push run re-tests it afterwards, attributed to the merge that
   caused any breakage (detection). See the header comment in `.github/workflows/ci.yml`
   for why both are kept. The trigger itself is pinned by
   `tests/test_ci_workflow.py::test_ci_runs_on_pushes_to_develop`, so this statement
   fails loudly rather than silently going stale if the trigger is ever removed.

   Check the run attributed to the head commit being promoted, not merely the branch's
   most recent green run: another pull request can land in between, and a green mark on
   an earlier commit says nothing about the one going to `main`. A local full run is a
   fallback if no run exists for that commit, not the gate.

2. **Confirm the committed examples are current, and check whether the Pages action
   versions have moved.** The first half needs no separate work: step 1's green run
   includes `tests/test_committed_examples.py`, which re-renders and compares, so a green
   `develop` already means `examples/` matches the renderer. If it had drifted, CI would
   be red.

   The second half does need a look. Diff `.github/workflows/update-examples.yml` between
   `main` and `develop` and note whether the `actions/*` versions changed. They are
   pinned by major version and the promotion is the first time the new pins execute in
   the Pages environment, so a bump turns step 4 from a formality into a real gate. This
   is a one-command check and it decides how closely to watch the deploy.

3. **Open the promotion pull request** from `develop` to `main`. `main` is protected; the
   maintainer merges.

4. **Watch the post-merge runs on `main` finish.** Three land: CI, security, and
   `update-examples.yml`. Confirm all three against the actual merge commit before
   treating the promotion as done.

   CI and security are the ones easiest to skip, because both already reported green on
   the pull request. That green describes a *preview* merge, not the commit that landed.
   `develop` is protected from this by a merge queue that tests the real merge commit
   before it lands; **`main` has no queue**, so its push run is the only test the actual
   promotion merge ever gets. `.github/workflows/ci.yml` says so directly, and
   `pip-audit (production deps)` is a required check on `main`. Skipping them here means
   the largest merge the project performs is the one merge nothing verifies as landed.

   Two of these claims — that `main` has no queue, and that `pip-audit (production
   deps)` is a required status check on `main` — are GitHub **branch-protection
   settings**, not repository files. They are not derivable from the workflows and are
   not covered by the repository consistency gate, so nothing here goes red if they
   change. Rely on them knowing they could drift with no test signalling it.

   The Pages run is the release gate for the published demo, and step 2 decides how
   closely to watch it: the publishing steps run only on `main` and only in the Pages
   environment, so when the action versions have moved, this run is the first evidence
   anyone has about them. A failure there leaves the previous Pages deploy serving, which
   is stale rather than broken. That is recoverable and does not by itself justify rolling
   back. A red CI or security run on `main` is a different matter and belongs in the
   rollback conversation at step 7.

5. **Redeploy the hosted app.** The server pulls from `main` and restarts. The command is
   in [docs/web-compare.md](web-compare.md); hosting specifics live outside this
   repository.

6. **Smoke both surfaces.** Run a real comparison on the hosted app, and open the
   README's "See it in action" links to confirm they serve the promoted reports. Checking
   only one surface leaves the other unverified, and they fail independently.

7. **Leave a rollback window.** Do not start unrelated work on `main` inside it.

   Rollback is reverting the promotion pull request and redeploying, and it has a
   consequence worth knowing before you need it. Promotions land on `main` as merge
   commits, so reverting one restores the files while leaving the promoted commits in
   `main`'s ancestry. Git then treats them as already merged, and **the next promotion
   will not bring them back.** Recovering forward is a deliberate act: revert the revert,
   or otherwise reapply the release, as part of the following promotion. Nobody should be
   left assuming the next merge will quietly restore what the rollback removed.

## What the workflow does not exercise

Steps 1 and 2 read evidence that already exists. The Pages publishing steps in
`update-examples.yml` (`checkout`, `configure-pages`, `upload-pages-artifact`,
`deploy-pages`) produce none: they need the Pages environment and run only on `main`, so
no local run and no pull-request run says anything about them.

Do not assume they carry over from the last successful publish. These actions are pinned
by major version, and dependency updates move those pins on `develop` between promotions,
where nothing executes them. When the pins have changed, the promotion is the **first**
execution of the new versions, not a repeat of a proven one. At the time this was written
every one of the four had moved since the previous release, which is why step 2 asks for
the diff rather than treating the publish as routine. If Pages publishing fails, look here
first.

## Files that look disposable and are not

The committed example reports are the README's front-page demo and a live Pages surface.
Being generated files checked into the repository, they read as build output that can be
deleted or moved freely. Nothing regenerates them on promotion; the publish step only
copies what is already committed, so whatever is in `examples/` at merge time is exactly
what the public gets.

`tests/test_committed_examples.py` covers more than freshness. It fails when a rendered
file is missing from `examples/`, and `test_no_committed_example_is_orphaned` fails in the
other direction, on a committed file the renderer no longer produces. So deleting one, or
adding a stray, goes red.

The gap it cannot close is narrower and easy to walk into. Nothing knows which filenames
the README links to. Its "See it in action" line points at absolute Pages URLs naming
specific files, and a coordinated change, renaming an output in `render_examples.py` and
committing the regenerated results, satisfies every example test while leaving the front
page pointing at a URL that no longer exists. Repoint the README in the same commit as any
rename, because no gate will remind you.
