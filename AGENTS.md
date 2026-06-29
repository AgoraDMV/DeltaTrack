# AGENTS.md

Guidelines for AI coding agents working on this repository.

## Quick reference

```bash
uv sync                          # Install dependencies
uv run pytest -m "not slow and not browser"  # Fast tests only (~1s)
uv run pytest                    # All tests (needs bills/ XML files)
uv run pytest tests/test_diff_bill.py::TestMatchNodesIntegration  # Single test
uv run python scripts/serve_compare.py 118-hr-8752  # PDF vs XML diff side by side (see TESTING.md)
```

## Workflow

This repo follows the workflow in [CONTRIBUTING.md](CONTRIBUTING.md). The load-bearing parts for an agent:

- **Pick work from the `Ready` column** of the project board — `Ready` means groomed and safe to start. Pick a discrete issue, not an epic.
- **Own it and keep status current.** Before starting, **assign yourself** and move the card to **In progress**. Don't work an issue you aren't assigned to without claiming it first. Opening the PR moves it to **In review** automatically; keep the Status honest as you go so the board reflects reality.
- **Branch from `develop`** (never `main`), commit in small focused steps, and open the PR against `develop`. A maintainer merges; do not merge yourself.
- **Link the issue in the PR** body with `Closes #<n>` so the issue and its board card resolve on merge.
- **Before pushing, run the CI gates locally** (lint, `ruff format --check`, fast, browser, external-validation) -- see CONTRIBUTING's "What CI checks." `ruff check` is not covered by the pre-commit format hook, so run it explicitly.

### Filing and grooming issues

- **File with a template** (bug / feature / task). Keep *reporting* lean — for a bug, a way to reproduce is the highest-value thing. Don't pre-scope or pre-size; that's the grooming step.
- **Kind is the issue type** (Bug / Feature / Task), not a label — the template sets it. Type is single-select (a thing is one kind); labels are for cross-cutting attributes that stack (`security`, `blocked`, `epic`, `testing`, `good first issue`). Don't reintroduce `bug`/`enhancement` labels.
- **Grooming makes an issue pickup-ready** (the `Backlog → Ready` move): add acceptance criteria, scope, where-to-start, and set **Priority**. See CONTRIBUTING's "Grooming an issue for pickup."
- **Priority and Effort are org-level issue fields**, not labels: Priority = Urgent / High / Medium / Low (single source of truth — don't reintroduce priority labels); Effort = High / Medium / Low, optional and not a current focus.
- **Watch for security-sensitive work.** Anything touching the public/deployed surface (e.g. `server/`, `/api/compare`) gets the `security` label and a hard look — that's the one outward-facing, abusable part of the project.
- **Epics** carry the `epic` label and stay **untyped** (no issue type) until the org-level `Epic` type exists (#127); they are decomposed into native **sub-issues**; the parent's progress bar is its status. Pick up the sub-issues, not the epic. An epic stays open until all its sub-issues close, then a maintainer closes it by hand (the parent does not auto-close). Epics live on the Roadmap view and are filtered off the working board.

## Key architecture concepts

- The shared bill data model (the two-tree hierarchy, the glossary, why the XML encodes nesting positionally, and the PDF↔XML parity goal) lives in [docs/bill-structure.md](docs/bill-structure.md). Read it before working on heading/anchor/account detection or DeltaTrack#54.
- Bill XML has structural containers nested inside titles: `subtitle`, `part`, `chapter`, `subchapter`. These are handled by `_walk_structural_children()` in `bill_tree.py`, which recurses through them to reach sections and appropriations elements.
- `_process_section_element()` is the shared helper for section handling, called from both the main title walk and structural containers.
- `BillNode.division_label` stores the division context (e.g., "Division A: Military Construction"). `normalize_division_title()` strips the letter prefix for matching.
- `match_nodes()` in `diff_bill.py` uses division-aware matching: unique paths pair directly, collision groups (same `match_path` in multiple divisions) are resolved by normalized division title, then text similarity.
- Floor amendment annotations like "(increased by $2,000,000)" reference the **budget request baseline**, not the previous bill version. The base amount in the text IS the correct appropriation. `amounts_changed` compares base amounts (annotations stripped). The `has_amendment_annotations` field on `FinancialChange` flags their presence for informational display.
- Preamble sections (Short Title, References, etc.) sit alongside divisions/titles at the body level and are captured by `walk_body_sections()`.

## Test conventions

- All test files live in `tests/`; source modules stay at the repo root and are importable because `pythonpath = ["."]` is set in `pyproject.toml`. Run pytest from the repo root so CWD-relative fixtures (`bills/`, `test_data/`) resolve.
- Tests requiring real bill XML files are marked `@pytest.mark.slow`; front-end tests `@pytest.mark.browser`. The fast suite is `-m "not slow and not browser"`. CI runs more than the fast suite (see CONTRIBUTING's "What CI checks")
- Shared test helpers live in `tests/conftest.py`: `make_bill_node()`, `make_bill_tree()`, `make_node_diff()`, `make_change_dict()`
- Session-scoped fixtures in `tests/conftest.py` cache parsed bill trees and diffs to avoid redundant XML parsing
- `fetch_bills.py` tests use `respx.mock` decorator and monkeypatch `time.sleep`
- `bill_tree.py` tests use inline XML snippets; integration tests use session fixtures
- `tests/test_diff_validation.py` holds the hand-curated cross-version correctness assertions plus `TestCorpusDiffSmoke`, which runs invariant checks across every adjacent version pair in the corpus
- `tests/test_corpus_properties.py` parametrizes over all XML files in `bills/`; uses `_KNOWN_DUPLICATE_COUNTS` and `_KNOWN_MISSING_APPRO` dicts for per-file baselines
- Bill DTD XML uses flat-sibling `appropriations-major/intermediate/small` tags (not nested)
- Dollar amounts are embedded in prose `<text>` elements, extracted via regex
- HTML formatter functions (`word_diff`, `build_financial_table`, etc.) are individually testable
