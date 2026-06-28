# Contributing to DeltaTrack

Thanks for your interest in contributing! This project compares versions of U.S. appropriations bills to make the legislative process more transparent. Contributions of all kinds are welcome: bug fixes, new features, documentation improvements, and bug reports.

New to the codebase or to congressional bills? Two things are worth reading first:

- **[docs/bill-structure.md](docs/bill-structure.md)** -- the data model the whole project rests on: what a division, account, or section is, and how the XML and PDF paths reconstruct the bill's hierarchy. Read this before touching parsing or diff code.
- **[docs/decisions/](docs/decisions/)** -- short records of the non-obvious choices and why they were made.

## Community

DeltaTrack is built by the Congressional Tech team at [Civic Tech DC](https://luma.com/civic-tech-dc). The work focuses on diffing draft versions of bills for congressional staffers, across two repos: **BillTrax** (online) and **DeltaTrack** (local). The fastest way to get oriented and find people to pair with:

- **Join the Slack** -- the [`#congressional-tech` channel](https://civictechdc.slack.com/archives/C0AT13U25V2) in the Civic Tech DC workspace. Day-to-day questions and coordination happen here.
- **Come to the biweekly meetup** -- in person, via [Civic Tech DC on Luma](https://luma.com/civic-tech-dc). The single best way to get started: come, say hello, and pick up a first issue with someone alongside you.

You don't need either to send a pull request, but both make the on-ramp much shorter.

## Getting started

### Prerequisites

- **Python 3.12+** -- check with `python3 --version`
- **uv** (Python package manager) -- install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Git** -- for version control

### Setup

```bash
# Fork the repo on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/DeltaTrack.git
cd DeltaTrack

# Install dependencies (including dev tools)
uv sync

# Install pre-commit hooks (runs linting/formatting automatically on commit)
uv run pre-commit install

# Run the fast test suite to verify everything works
uv run pytest -m "not slow and not browser"
```

### Optional: download bill files for full test suite

The fast tests use inline XML and mocked data. Integration tests need real bill files: XML for the diff tests and PDF for the PDF comparison tests (`test_pdf_*`):

```bash
# An API key is optional: the tool falls back to a rate-limited demo key
# (~30 requests/hour). For heavier use, get a free key at
# https://api.congress.gov/sign-up/ and put it in .env. fetch_bills.py loads
# .env automatically, so no `source` is needed.
cp .env.example .env   # then edit .env and paste your key

# Download the primary test bill (--format both gets XML + PDF; default is XML only)
uv run python fetch_bills.py download 118 hr 4366 --format both

# Run the suite; tests whose bill isn't downloaded yet skip automatically
uv run pytest
```

See the README for the full list of bills used by the test suite.

## Finding work to do

Work is tracked in [GitHub Issues](https://github.com/AgoraDMV/DeltaTrack/issues) and on the [project board](https://github.com/orgs/AgoraDMV/projects/1). An issue moves across the board left to right:

| Column | Meaning |
|--------|---------|
| **Backlog** | Captured, but not yet groomed or ready to start. |
| **Ready** | Groomed and safe to pick up -- **start here**. |
| **In progress** | Someone is actively working it. |
| **In review** | A pull request is open and awaiting review. |
| **Done** | Merged and complete. (Pull requests land on `develop`; `main` is the protected release branch.) |

To pick up work:

1. Choose an issue from **Ready**, or one labeled [`good first issue`](https://github.com/AgoraDMV/DeltaTrack/labels/good%20first%20issue) if you're new.
2. **Claim it** so two people don't start the same thing: comment on the issue to call it. If you have write access, also assign yourself and move the card to **In progress**; otherwise a maintainer will. We're a small team and work mostly async between syncs, so visible ownership matters.

The board handles the later transitions for you: opening a pull request with `Closes #<n>` moves the issue to **In review**, and merging it moves the issue to **Done** and closes it. The only card you move by hand is **In progress**, when you start work.

Not sure whether an issue is a good fit? Ask in a comment or at the regular sync (see [Community](#community)).

## Making changes

### Branch workflow

`develop` is the integration branch; `main` is the protected release branch. Day-to-day
work targets `develop`, not `main`.

1. Create a branch from `develop` for your work
2. Make your changes in small, focused commits
3. Push your branch and open a pull request against `develop`

### Code style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting. If you installed the pre-commit hooks, this runs automatically on each commit. You can also run it manually:

```bash
uv run ruff check .          # Lint
uv run ruff check --fix .    # Lint and auto-fix
uv run ruff format .         # Format
```

### Testing

Tests are split into groups by speed and dependencies:

- **Fast tests** (`uv run pytest -m "not slow and not browser"`) -- unit tests on inline XML and mocked data; no bill files needed.
- **Browser tests** (`uv run pytest -m browser`) -- Playwright/Chromium front-end tests. One-time setup: `uv run playwright install chromium`.
- **Slow tests** (`uv run pytest -m slow`) -- integration and external-validation tests against real bill files in `bills/`.

When adding code, write tests for it. Test files live in `tests/`; mark tests that need real XML files with `@pytest.mark.slow` and front-end tests with `@pytest.mark.browser`. Shared helpers are in `tests/conftest.py`. [TESTING.md](TESTING.md) is the home for the full command catalog and what each validation layer proves.

### What CI checks

Every pull request runs these gates (defined in `.github/workflows/ci.yml`). Run them locally before pushing to avoid a surprise red CI:

```bash
uv run ruff check .                          # 1. Lint
uv run ruff format --check .                 # 2. Formatting (run `ruff format .` to fix)
uv run pytest -m "not slow and not browser"  # 3. Fast tests
uv run pytest -m browser                     # 4. Browser tests (needs `playwright install chromium`)
uv run pytest -m slow \
  tests/test_committee_report.py \
  tests/test_validate_extraction.py::test_report_amounts_recalled \
  tests/test_validate_extraction.py::test_fixture_is_senate_reported_bill  # 5. External validation
```

The pre-commit hooks cover gates 1 and 2 on each commit, but `ruff format --check` still fails CI if you committed without them. Gate 5 runs against vendored committee-report sources, so it needs no downloads or API key.

## Submitting a pull request

1. Run the CI gates locally (above) and make sure they pass.
2. Open a pull request against `develop`.
3. In the description, link the issue it addresses ("Closes #123") and say what changed and why.
4. For a behavior change, note how you verified it -- not just "tests pass," but what you ran or eyeballed (see [Reviewing a pull request](#reviewing-a-pull-request)).

A maintainer reviews and merges. CI must be green.

## Reviewing a pull request

Review is how a small team shares context and catches the bugs tests miss. New teammates are encouraged to review early -- it's one of the fastest ways to learn the codebase.

What to look at, roughly in priority order:

- **Correctness of the diff itself.** This is the product. Passing tests are necessary, not sufficient: a diff can be green and still wrong. For any change that affects diff output, **run the tool on a real bill and eyeball the report** rather than trusting the suite alone. `scripts/serve_compare.py` gives a side-by-side view (see [TESTING.md](TESTING.md)).
- **The risk hotspots**, where a bug does the most damage:
  - **Parser accuracy** (`bill_tree.py`, `parsers/`) -- does the bill's structure come through intact? A missing or mis-nested section corrupts everything downstream. See [docs/parser-validation.md](docs/parser-validation.md).
  - **Financial diff** (`diff_bill.py` and its financial filtering) -- dollar amounts and their changes must be exact.
  - **The canonical schema contract** (`formatters/canonical.py`) -- both pipelines and the renderer depend on it, so a breaking change there ripples everywhere.
- **Tests for the change.** New behavior should come with a test that would fail without the fix.
- **Docs and decisions.** A non-obvious choice belongs in a code comment or a [decision record](docs/decisions/); a user-facing change belongs in the README.

Leave specific comments, then approve or request changes. A maintainer does the actual merge.

## Filing an issue

Keep it light. Pick the matching template (bug, feature, or task) and fill in
what you know — you don't need to scope, size, or solve it. The most useful thing
you can provide for a bug is a way to reproduce it.

For bug reports, include:
- What you expected to happen
- What actually happened
- Steps to reproduce (bill number, versions compared, command you ran)
- Any error output

That's enough. The team fleshes out the rest when grooming the issue for pickup.

## Grooming an issue for pickup

Reporting and picking-up are two different jobs. Filing should be low-friction;
making an issue *ready to pick up* is the team's job, done during triage (the
**Backlog → Ready** move on the board, usually at the biweekly sync). An issue is
**Ready** when it answers:

- **Problem / why** — what's wrong or missing, and why it matters.
- **Acceptance criteria** — a short checklist of what "done" looks like.
- **Scope** — one line on what's in and out, so the work doesn't sprawl.
- **Where to start** — entry file(s) or the relevant doc.
- **Priority** — set the org-level Priority field: Urgent / High / Medium / Low (see below).
- **Effort** *(optional)* — set the org-level Effort field if useful; not a focus right now.

This keeps the bar to *report* low while still giving a newcomer everything they
need to *start*.

### Priority

Priority lives in the **org-level Priority issue field** (defined once for the
AgoraDMV org, so it's consistent across DeltaTrack and BillTrax), set during
grooming. Its values are **Urgent / High / Medium / Low**:

- **Urgent** — broken or trust-critical: wrong/lost diff output, silent data
  corruption. Drop other work for these.
- **High** — important correctness or coverage to do soon; cheap unblockers.
- **Medium** — coverage, fidelity, structure, contributor on-ramp. Most work.
- **Low** — cleanups, cosmetics, deferred decisions, nice-to-haves.

Priority is "the next-couple-weeks tier," not a permanent ranking — the **Ready**
column holds the current Urgent/High items, and we re-look at each sync. We track
priority in one place (the field), not also as labels, to avoid two competing
sources of truth.

Sizing is available via the org-level **Effort** field (High / Medium / Low) if a
piece of work needs it, but it isn't a focus right now — don't block grooming on
it.

## Epics

A larger effort that spans several pull requests is tracked as an **epic**: an
issue with the **`epic` label** that is broken into **sub-issues** (the smaller,
discrete pieces of work). Pick up the *sub-issues*, not the epic itself.

- The epic's progress is the **sub-issues progress bar** on the parent — it isn't
  dragged through the board columns like a normal issue.
- Each **sub-issue** flows the board normally and closes via its own
  `Closes #<n>` pull request. When all sub-issues are done, a maintainer closes
  the epic.
- Epics live on the **Roadmap** view; the working board filters them out, so the
  day-to-day columns show only discrete, pickup-ready work.

Reach for an epic only when work genuinely needs decomposing — most features are a
single issue.

## Questions?

Open an issue, ask in [Slack](https://civictechdc.slack.com/archives/C0AT13U25V2), or bring it to the [meetup](https://luma.com/civic-tech-dc). There are no dumb questions. See [Community](#community) for how to join.
