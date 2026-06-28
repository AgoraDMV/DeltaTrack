# DeltaTrack

Downloads U.S. bill text from Congress.gov and compares versions structurally. Shows what changed between versions: added, removed, modified, and moved sections, with optional financial change filtering.

Works on any bill type (HR, S, HJRES, etc.), not just appropriations.

**See it in action:** [Committee vs. Floor](https://agoradmv.github.io/DeltaTrack/hr4366_committee_vs_floor.html) | [House vs. Senate](https://agoradmv.github.io/DeltaTrack/hr4366_house_vs_senate.html) (example reports for HR 4366, 118th Congress)

## Why not a generic differ?

A generic XML or PDF differ reports which document nodes or lines of text changed.
That output is mostly formatting noise (renumbered lines, page headers, reflow)
and has no sense of a bill's structure. DeltaTrack parses each version into the
bill's own sections and diffs those, so on any bill type you see what actually
changed (added, removed, modified, and moved sections) without the noise, even
when no dollar amounts move. For appropriations bills it adds a structured money
model on top, producing an account-level table of paired old → new amounts. See
[docs/decisions/0001-structured-money-diff.md](docs/decisions/0001-structured-money-diff.md)
for the rationale and a reproducible comparison.

## Prerequisites

- **Python 3.12+** - Download from https://www.python.org/downloads/ if you don't have it. To check, open a terminal (Terminal on Mac, Command Prompt on Windows) and type `python3 --version`.
- **uv** (Python package manager) - Open a terminal and run:
  - Mac/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

## Quickstart

Generate an HTML report comparing two versions of a bill:

```bash
# 1. Install dependencies and activate environment (run this once, from the project folder)
# This runs the init script. The script needs to be run indirectly using source so that the change in 
# Python environment sticks
source init

# 2. Download all versions of a bill
#    Example: HR 4366 from the 118th Congress (2023-2024)
./fetch_bills download 118 hr 4366

# 3. Generate an HTML report comparing two versions
./diff_bill compare \
  bills/118-hr-4366/1_reported-in-house.xml \
  bills/118-hr-4366/2_engrossed-in-house.xml \
  --format html -o reports/hr4366_v1_vs_v2.html
```

Open the HTML file in any browser to view the comparison. No additional software needed. Reports are saved to the `reports/` folder.

The tool works without an API key using a free demo key (limited to 30 requests per hour). For heavier use, get a free key at https://api.congress.gov/sign-up/ and save it in a file called `.env` in the project folder:

```
CONGRESS_API_KEY=your_key_here
```

## Command reference

The product commands are wrapper scripts in the project root; run them after `source init`. `download` and `download-all` default to **XML** — pass `--format pdf` or `--format both` for PDFs.

| Command | What it does |
|---------|--------------|
| `./fetch_bills versions <congress> <type> <number>` | List a bill's available text versions |
| `./fetch_bills download <congress> <type> <number>` | Download a bill's versions (XML by default; `--format pdf\|both`, `--version N`) |
| `./fetch_bills download-all --start_year <Y> --end_year <Y>` | Download all appropriations bills in a year range (or `--file <csv>` for a specific set) |
| `./diff_bill compare <old.xml> <new.xml>` | Diff two XML versions (HTML by default; `--format json`, `--financial`, `--filter`, `-o`) |
| `./diff_pdf <old.pdf> <new.pdf> -o <out.html>` | Diff two PDF versions into the same HTML report |
| `./fetch_bill_archives` | Bulk-build a bill-metadata index from govinfo archives — **see the warning below** |

Environment setup is `source init` (installs dependencies and activates the virtualenv). Use `source` so the environment change sticks; it is not a runnable command.

> **`fetch_bill_archives` is an advanced bulk tool.** Run with no arguments it immediately downloads every GovInfo BILLSTATUS archive for congresses 112–119 (hundreds of MB) with no prompt, extracts them, and writes a `bills/bills.csv` metadata index. The congress range is hardcoded and there are no CLI flags yet (tracked in [#10](https://github.com/AgoraDMV/DeltaTrack/issues/10)). Reach for it only when you specifically need a bulk bill index.

To run the web comparison app locally: `uvicorn server.app:app --reload --port 8077` (see [docs/web-compare.md](docs/web-compare.md)).

## Downloading Bills

```bash
# List available text versions
./fetch_bills versions 118 hr 4366

# Download all versions of a bill (XML by default; add --format pdf or --format both for PDFs)
./fetch_bills download 118 hr 4366

# Download a specific version (1-indexed)
./fetch_bills download 118 hr 4366 --version 2

# Download all appropriations bills for a year range
./fetch_bills download-all --start_year 2024 --end_year 2026

# Or batch-download a specific set of bills from a CSV that has an 'id' column
./fetch_bills download-all --file my_bills.csv
```

Files are saved to `bills/<congress>-<type>-<number>/`.

## Comparing Bills

```bash
# Compare two versions (prints an HTML report to stdout by default)
./diff_bill compare bills/118-hr-4366/1_reported-in-house.xml bills/118-hr-4366/6_enrolled-bill.xml

# Only sections with dollar amount changes
./diff_bill compare old.xml new.xml --financial

# Filter to a specific section
./diff_bill compare old.xml new.xml --filter "military construction"

# Include unchanged sections
./diff_bill compare old.xml new.xml --include-unchanged

# Save machine-readable JSON to a file (output defaults to HTML, so request json explicitly)
./diff_bill compare old.xml new.xml --format json -o diff.json

# Generate a standalone HTML report
./diff_bill compare old.xml new.xml --format html -o reports/report.html
```

### HTML report

`--format html` produces a self-contained HTML file that can be opened in any browser with no install or server required. See [examples/](examples/) for sample reports you can open immediately. The report includes:

- **Header** with bill number, congress, and version numbers (e.g., "v1: reported-in-house → v2: engrossed-in-house")
- **Sidebar** listing all changed sections with color-coded change type badges. Type in the filter box to narrow the list. Click any item to jump to that section.
- **Financial summary table** showing dollar amounts before and after, with change amounts and percentages. Click column headers to sort. Click a row to jump to that section's detail. Sections with floor amendment annotations show a warning badge.
- **Change cards** for each modified, added, removed, or moved section. Modified sections show word-level inline diffs: additions highlighted in green, deletions in red strikethrough. Moved sections show both the old and new location, plus body text.
- **Prev/next buttons** in the bottom right corner to step through changes one at a time.

When no changes are detected between versions, the report displays "No changes found" rather than a blank page.

Financial data is automatically included in the HTML report without needing the `--financial` flag.

### Change types

| Type | Meaning |
|------|---------|
| `modified` | Section exists in both versions, text changed |
| `added` | Section only in new version |
| `removed` | Section only in old version |
| `moved` | Section relocated (renumbered or moved under a different title) |
| `unchanged` | Identical text in both versions (hidden by default) |

### Financial filtering

`--financial` filters to sections where dollar amounts changed and adds amount details to the JSON output. Sections where text changed but amounts stayed the same are excluded.

### Text normalization

The tool focuses on substantive changes and ignores formatting differences between bill versions. The following will not be flagged as changes:

- Spacing and line break differences between versions
- Differences in spacing around numbered list markers like (1), (A), or (iv), which vary between House and Senate formatting conventions

Floor amendment annotations like "(increased by $2,000,000)" appear in engrossed versions after floor votes. These annotations reference the budget request baseline, not the previous bill version, so the base amount in the text is the authoritative appropriation. The tool strips the annotations before comparing amounts across versions, then flags their presence with an informational badge in the HTML report so readers can see where the floor acted.

## Comparing PDF versions

Some bill versions are only available as PDF — pre-publication committee prints, chair's marks, and markup amendments are posted as PDF before the authoritative XML exists (see [ADR 0010](docs/decisions/0010-pdf-pipeline-pre-publication.md)). For those, use `diff_pdf`, the PDF-native counterpart to `diff_bill`:

```bash
# download defaults to XML, so request the PDFs explicitly
./fetch_bills download 118 hr 4366 --format pdf

# Generate the same standalone HTML report from two PDFs
./diff_pdf bills/118-hr-4366/1_reported-in-house.pdf bills/118-hr-4366/2_engrossed-in-house.pdf -o reports/hr4366.html
```

`diff_pdf` runs the same pipeline as the web app (full-bill view, in-page search, section navigation, embedded export) and writes the same HTML report described above. Output goes to stdout unless `-o` is given. Prefer `diff_bill` on XML whenever the published XML exists; it extracts structure and amounts exactly rather than reconstructing them from a rendered page.

## Output Structure

```
bills/
  118-hr-4366/
    1_reported-in-house.xml
    2_engrossed-in-house.xml
    6_enrolled-bill.xml
```

Files are numbered in chronological order. Each number represents a version of the bill as it moved through Congress.

## Bill versions

A bill goes through several versions as it moves through the legislative process. Common versions for appropriations bills:

| Version | What it means |
|---------|--------------|
| introduced-in-house | The bill as originally filed |
| reported-in-house | The bill as approved by committee, before a full House vote |
| engrossed-in-house | The bill as passed by the House, including any floor amendments |
| placed-on-calendar-senate | The House-passed bill placed on the Senate calendar for consideration |
| referred-in-senate | The House-passed bill referred to a Senate committee |
| engrossed-amendment-senate | The Senate's version, often substantially different |
| engrossed-amendment-house | The House's response to the Senate version |
| enrolled-bill | The final text signed into law |

**Which versions to compare:** Adjacent versions (v1 vs v2, v2 vs v3) show what changed in each step of the process. These are the most useful comparisons. Comparing distant versions (v1 vs v6) shows cumulative changes but can be overwhelming, especially when a bill is folded into an omnibus package with hundreds of new sections from other bills.

## Architecture

The shared data model the whole project rests on — the bill hierarchy, the glossary, and how the XML and PDF paths reconstruct it — is documented in [docs/bill-structure.md](docs/bill-structure.md). Start there.

Four modules:

- **`fetch_bills.py`** - Downloads bill XML and PDF from Congress.gov API v3 (`--format xml|pdf|both`, default `xml`). CLI commands: `versions`, `download`, `download-all`.
- **`bill_tree.py`** - Normalizes bill XML into a `BillTree` of `BillNode` objects. Handles divisions, titles, and flat sections, plus structural containers within titles (subtitle, part, chapter, subchapter). Captures preamble sections that sit alongside divisions or titles.
- **`diff_bill.py`** - Compares two `BillTree`s. Uses division-aware matching for omnibus bills (resolves cross-division path collisions by normalized division title). Detects false matches via text similarity, reconciles moved sections, and extracts dollar amounts (stripping floor amendment annotations before comparison, flagging their presence separately).
- **`formatters/diff_html.py`** - Generates standalone HTML reports from diff output (via adapters that feed both XML and PDF diffs through one renderer) with sidebar navigation, financial summary table, and word-level inline diffs.

## Design decisions

The reasoning behind non-obvious architectural choices (why a structured money diff, why a single PDF engine, why govinfo bulk data) lives in [docs/decisions/](docs/decisions/).

## Testing

```bash
uv run pytest -m "not slow and not browser"     # Fast unit tests (~1s, no XML files needed)
uv run pytest                                    # All tests (needs bills/ XML files)
uv run pytest tests/test_bill_tree.py            # Normalization tests
uv run pytest tests/test_diff_bill.py            # Diff/matching tests
uv run pytest tests/test_financial_diff.py       # Financial filtering tests
uv run pytest tests/test_reconcile.py            # Section move detection tests
uv run pytest tests/test_format_html.py          # HTML report formatter tests
uv run pytest tests/test_corpus_properties.py    # Corpus-wide property tests
uv run pytest tests/test_validate_extraction.py  # External validation tests
```

Tests that require real bill XML files are marked `@pytest.mark.slow`. The fast suite (`-m "not slow and not browser"`) runs entirely on inline XML and mocked data, needs no downloads, and finishes quickly. Every pull request also runs the full CI gate set (lint, formatting, the fast and browser tests, and an external-validation subset) -- see [What CI checks](CONTRIBUTING.md#what-ci-checks). The slow suite adds corpus-wide property checks, cross-version diff validation, and external ground-truth validation against real bills.

The diff engine is fully deterministic: no LLM and no API key. The only API key (`CONGRESS_API_KEY`) is used by `fetch_bills.py` to download bills, not by the diff itself.

See [TESTING.md](TESTING.md) for how the test suite is organized, how diff accuracy is validated, what each validation layer proves, and where the known gaps are.

Integration tests use real XML files from `bills/` and skip if not present. To run the full suite including validation tests, download the required bills:

```bash
# fetch_bills reads CONGRESS_API_KEY from .env automatically; no need to source it.
# --format both fetches XML and PDF together, covering both the XML tests and the
# PDF comparison tests (test_pdf_*) in one pass.
./fetch_bills download 118 hr 4366 --format both
./fetch_bills download 118 hr 2882 --format both
./fetch_bills download 118 hr 8282 --format both
./fetch_bills download 118 hr 8752 --format both
./fetch_bills download 118 hr 8774 --format both
./fetch_bills download 118 hr 4820 --format both
./fetch_bills download 117 hr 2471 --format both
./fetch_bills download 117 hr 4432 --format both
./fetch_bills download 117 hr 4502 --format both
./fetch_bills download 116 hr 1865 --format both
./fetch_bills download 116 hr 133 --format both
./fetch_bills download 115 hr 5895 --format both
./fetch_bills download 115 hr 1625 --format both
./fetch_bills download 115 hr 244 --format both
./fetch_bills download 114 hr 2029 --format both
./fetch_bills download 113 hr 83 --format both
./fetch_bills download 113 hr 3547 --format both
```

These fetch both XML and PDF: the XML covers the XML-based tests, and the PDF rendering is what the PDF comparison tests (`test_pdf_*`) need. Drop `--format both` if you only want the XML (the default).

The validation tests compare extracted line items across Legislative Branch bills (both chambers, multiple fiscal years) against amounts from a curated appropriations spreadsheet. The corpus property tests (`test_corpus_properties.py`) check dollar coverage, path uniqueness, and character coverage across all downloaded bills. See [TESTING.md](TESTING.md) for what each validation layer proves and where the gaps are.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up a dev environment, find and claim work on the project board, run the CI gates locally, and open a pull request. New contributors and reviewers both have a path there.
