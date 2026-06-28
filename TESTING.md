# Testing and Accuracy

This document explains, in plain terms, how we test the tool and how far the
accuracy checks actually go. The how-to-run commands are at the end; you can 
skip them if you only want to understand how accuracy is checked.

## The diff does not guess

The comparison is done by plain, rule-based code. It does not use an AI model,
and it does not call out to any service. The same two documents always produce
exactly the same comparison. There is no randomness and nothing to "get lucky"
or "get unlucky" on.

The tool does need an internet connection and uses an API key for one thing only:
downloading bills from Congress.gov in the first place. That step is separate
from the comparison. If you already have the documents, the comparison needs 
no key and no internet connection.

## How accuracy is checked

Accuracy is checked in five ways. Each one answers a different question, and
each has limits worth being honest about. There is no single accuracy
percentage that would be truthful across all of appropriations, so we describe
what each layer does and does not establish.

### 1. Checking the numbers against an outside source

This is the strongest check. It now covers all twelve regular appropriations
subcommittees, through two kinds of independent source:

- **A separately maintained spreadsheet (Legislative Branch).** We took an
  appropriations spreadsheet kept by other people for Legislative Branch bills,
  covering both the House and Senate across several years, and confirmed that the
  dollar amounts our tool pulls out of the official bill text match the amounts in
  that spreadsheet, in the right place in the bill's structure.
- **Senate committee reports (the other eleven subcommittees).** For each of the
  remaining subcommittees we read the account-level amounts out of the Senate
  Appropriations committee report and confirmed that each amount the committee
  recommended appears in what our tool extracts from the reported bill. A committee
  report is written by different people for a different purpose than the bill, so
  it is a genuinely outside source.

Because every source was built independently of our tool, this catches mistakes
that checking the tool against itself never could. Across the committee-report
checks, the amounts we cannot recall are confirmed report-versus-bill differences
(indefinite accounts with no fixed-dollar line, totals the bill states only as
their parts, and a few report typos the report's own summary tables contradict),
not extraction errors. The per-subcommittee counts are tracked so they cannot
quietly rise.

**Limit:** the twelve subcommittees are checked to different depths. Legislative
Branch is checked structurally, meaning the right amount in the right place,
across several bills and both chambers. The other eleven are checked as
amount-recall, meaning the right amounts are present under the right agency, on a
single Senate-reported bill each, because the report and the bill name accounts
differently. Two consequences follow, and we track both on purpose: an amount that
landed on the wrong account inside the right agency would still pass the recall
check, and the House versions of those eleven subcommittees have no outside-source
check at all, because House committee reports print their account tables as images
we cannot read.

### 2. Sanity checks across every bill we have

These checks run automatically across every bill in the collection and confirm
that nothing falls through the cracks: every dollar figure in the source text
shows up somewhere in the parsed result, the same section is not accidentally
listed twice, and the tool does not silently drop large chunks of text.

**Limit:** these are broad but shallow. They confirm that the tool did not lose
or mangle content. They do not confirm that any particular comparison is
*correct*, only that nothing obvious was dropped.

### 3. Frozen expectations on specific bills

For a few real pairs of bill versions, we wrote down specific things that should
be true and turned them into automatic checks. For example: a certain set of
sections should show up as newly added rather than as edits, and a section that
was renumbered should be recognized as the same section moved, not as one
section deleted and a different one created. The tool also runs every
consecutive pair of versions through the comparison and confirms basic
soundness: it does not crash, it does not match up two sections that are
actually unrelated, and it does not report the same change twice.

The purpose of these checks is to stop the tool from getting *worse* over time.
If a future change breaks one of these expectations, a test fails.

**Limit:** these confirm the specific expectations we wrote down, plus the
section counts we recorded as a baseline. They are not a line-by-line human
review of every change in those bills. Treat them as guardrails, not as proof
that every comparison was read and signed off by a person.

### 4. Draft-bill comparisons (PDF)

Draft bills circulate as PDFs with no official machine-readable version behind
them, so they are handled and tested separately. For one draft bill, we built a
fixture by hand: a written list of the changes the comparison ought to surface,
including where each change appears (page and line) and what kind of change it
is. The tool's PDF comparison is then checked against that list.

**Limit:** this is the newest and thinnest area, and the hand-built list so far
covers a single draft bill.

### 5. Cross-checking the PDF reading against the official text

Most published bills exist in two forms: an official machine-readable version
and a PDF. For every bill we have in both forms, we confirm that every dollar
amount found in the official version also turns up when the tool reads the PDF.
Because the official version is the one checked against the outside spreadsheet
(check 1), this tells us the PDF reader is not quietly dropping or garbling
figures, even though a PDF is flat text with none of the structure the official
version carries. A second pass runs the PDF comparison across every consecutive
pair of versions and confirms it stays sound: it does not crash, it does not
report overlapping or out-of-bounds locations, and every change it reports has a
sensible type.

**Limit:** this confirms our PDF reader and our official-text reader *agree* on
the numbers, which catches reading mistakes. Agreement between our own two
readers is not the same as an outside source confirming the numbers are correct
— that is check 1, and only for Legislative Branch appropriations. (This
cross-check earlier surfaced a quirk in the official-text reader, where it
merged a dollar figure with an adjacent percentage in non-spending statutory
tables; that has since been fixed.) The soundness pass covers every bill,
including the largest omnibus in the collection.

## Known soft spots

We keep these in the open rather than papering over them:

- **"Is it the same section or a different one?"** When two sections are
  partly similar but not clearly the same and not clearly different, the tool
  has to make a judgment call, and that is where it is most likely to mislabel
  an edit. We track how often this borderline case comes up so it cannot quietly
  increase.
- **Large combined bills.** In omnibus bills that bundle many areas together,
  section numbers repeat across areas, which makes matching harder. The tool
  handles this, but it is the trickiest case.
- **Outside-source depth varies.** As noted in check 1, all twelve subcommittees
  now have an outside-source check, but only Legislative Branch is checked for the
  right place rather than just the right amount, and only it is checked on the
  House side. The other eleven rest on a single Senate-reported bill each.

## Running the tests

The rest of this is for people running the test suite.

Tests split into two groups by a `slow` marker. The fast group runs on small
built-in examples and needs no downloads. The slow group runs against real bill
files and skips automatically if those files are not present.

```bash
uv run pytest -m "not slow and not browser"   # Fast group: built-in examples, no downloads
uv run pytest                 # Everything, including checks against real bills
```

Run a single area:

```bash
uv run pytest tests/test_bill_tree.py            # Reading and structuring the bill text
uv run pytest tests/test_diff_bill.py            # Comparing two versions
uv run pytest tests/test_financial_diff.py       # Pulling out and comparing dollar amounts
uv run pytest tests/test_reconcile.py            # Recognizing moved sections
uv run pytest tests/test_format_html.py          # The HTML report
uv run pytest tests/test_corpus_properties.py    # Sanity checks across every bill (slow)
uv run pytest tests/test_validate_extraction.py  # Checking numbers against the spreadsheet (slow)
uv run pytest tests/test_pdf_diff_recall.py      # Draft-bill (PDF) comparison (slow)
uv run pytest tests/test_pdf_xml_amount_recall.py  # PDF reading vs official text, by the numbers (slow)
uv run pytest tests/test_pdf_corpus_smoke.py     # PDF comparison soundness across every bill (slow)
```

To run the slow group locally, download the bill files first (see the Testing
section of the [README](README.md#testing)). The PDF comparison tests
(`test_pdf_*`) need each bill's PDF as well as its XML; pass `--format both`
to `fetch_bills.py download` to fetch both at once, e.g.
`uv run python fetch_bills.py download 118 hr 4366 --format both`.

Some slow tests read files sourced directly from govinfo rather than the bill
API (for example, the reported-in-Senate watermarked PDF of S.4795 that
`test_pdf_watermark_recall.py` reads). They skip automatically if absent. Fetch
them with:

```bash
uv run python scripts/fetch_test_assets.py
```

### Speeding up the PDF tests for development

The slow PDF tests read every bill PDF, and reading a large omnibus takes a
couple of minutes. Three levers keep the loop fast:

```bash
# Restrict both PDF suites to one bill (substring match on the bill name):
TEST_BILL=4366 uv run pytest tests/test_pdf_xml_amount_recall.py tests/test_pdf_corpus_smoke.py

# Run across all CPU cores:
uv run pytest -n auto

# Combine them:
TEST_BILL=4366 uv run pytest -n auto tests/test_pdf_corpus_smoke.py
```

The first run extracts each PDF and caches the result to
`test_data/extract_cache/` (gitignored). Every later run loads from that cache
instead of re-reading the PDF, so re-running the same tests is near-instant. The
cache is keyed by file modification time, so editing or replacing a PDF
re-extracts it automatically.

## Comparing the two pipelines by eye

The automated checks above don't diff the two pipelines against *each other*. To
eyeball the PDF-derived and XML-derived reports for the same two versions side by
side — to catch parity gaps in breadcrumbs, section grouping, financial callouts,
or change counts — serve them together:

```bash
uv run python scripts/serve_compare.py 118-hr-8752
uv run python scripts/serve_compare.py 118-hr-8752 --v1 1_reported-in-house --v2 2_engrossed-in-house
uv run python scripts/serve_compare.py path/to/bill-dir --port 8765 --no-browser
```

With no `--v1`/`--v2` it picks the two lowest-numbered versions that have both a
`.pdf` and an `.xml`, so the bill must be fetched with `--format both` (the
vendored `bills/` corpus is XML-only). Rendered HTML goes to a temp dir, nothing
committed. The panes reflect the current checkout, so run it on the branch whose
diff output you're inspecting. This is a manual debugging aid, not a test.

## Measuring coverage

Coverage measures how much of the comparison code the tests actually exercise.
It is reported with `pytest-cov` (already included as a development dependency).

```bash
uv run pytest --cov --cov-report=term-missing                 # Full suite (needs bills/)
uv run pytest -m "not slow and not browser" --cov --cov-report=term-missing  # Fast group only
uv run pytest --cov --cov-report=html                          # Browsable report in htmlcov/
```

One caution: coverage tells you which lines of code ran during the tests, not
whether their output is correct. A high coverage number and a correct result
are different things. The five checks above are what speak to correctness.
