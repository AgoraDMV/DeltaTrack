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

Accuracy is checked in four ways. Each one answers a different question, and
each has limits worth being honest about. There is no single accuracy
percentage that would be truthful across all of appropriations, so we describe
what each layer does and does not establish.

### 1. Checking the numbers against an outside source

This is the strongest check. We took a separately maintained appropriations
spreadsheet for Legislative Branch bills, covering both the House and Senate
across several years, and confirmed that the dollar amounts our tool pulls out
of the official bill text match the amounts in that spreadsheet. Because the
spreadsheet was built independently, this catches mistakes that checking the
tool against itself never could.

**Limit:** this only covers the Legislative Branch, which is one of the twelve
areas (subcommittee jurisdictions) that appropriations bills are divided into.
The other eleven have not been checked against an outside source. This is the
biggest known gap, and we track it on purpose.

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
— that is check 1, and only for the Legislative Branch. (This cross-check also
surfaced one quirk in the official-text reader, where it can merge a dollar
figure with an adjacent percentage in non-spending statutory tables; that is
logged and set aside until fixed.) The soundness pass skips one record-setting
~5,600-page omnibus where the PDF comparison does not yet finish in reasonable
time.

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
- **Coverage outside the Legislative Branch.** As noted in check 1, the
  outside-source comparison covers only one of the twelve areas.

## Running the tests

The rest of this is for people running the test suite.

Tests split into two groups by a `slow` marker. The fast group runs on small
built-in examples and needs no downloads. The slow group runs against real bill
files and skips automatically if those files are not present.

```bash
uv run pytest -m "not slow"   # Fast group: built-in examples, no downloads
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
section of the [README](README.md#testing)).

## Measuring coverage

Coverage measures how much of the comparison code the tests actually exercise.
It is reported with `pytest-cov` (already included as a development dependency).

```bash
uv run pytest --cov --cov-report=term-missing                 # Full suite (needs bills/)
uv run pytest -m "not slow" --cov --cov-report=term-missing    # Fast group only
uv run pytest --cov --cov-report=html                          # Browsable report in htmlcov/
```

One caution: coverage tells you which lines of code ran during the tests, not
whether their output is correct. A high coverage number and a correct result
are different things. The four checks above are what speak to correctness.
