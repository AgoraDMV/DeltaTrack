# CLI / UI diff parity audit

**Question.** Two surfaces generate and manage diffs — the `diff_bill.py` / `diff_pdf.py`
commands and the `POST /api/compare` web endpoint. Do they produce the same result for the
same input, and what is duplicated between them?

**Measured on** `8fb0fa16`, fixture pair `tests/corpus/118-hr-8752`
(`1_reported-in-house` → `2_engrossed-in-house`, XML and PDF).

## Answer

The engine is already shared, and the sharing holds. For the same two files the
CLI-rendered and UI-rendered HTML reports differ by **two lines out of ~900** — the header
and the embedded `diff.json` version block. Every change card, every word-level diff and
every full-bill line is byte-identical. The convergence work behind [#42], [#367],
[ADR 0006](../../decisions/0006-canonical-diff-contract.md) and
[ADR 0007](../../decisions/0007-single-renderer.md) did the hard part.

What still diverges sits in a thin layer *above* the engine — turning a filename into a
version label and ordinal — plus one genuine contract split in what "JSON" means.

## Findings

### 1. Three surfaces, three headers, one PDF pair

| Surface | Report header |
|---|---|
| `scripts/render_examples.py` (the published example) | `v1: reported-in-house → v2: engrossed-in-house` |
| `./diff_pdf.py` | `reported-in-house → engrossed-in-house` |
| Web upload | `1_reported-in-house → 2_engrossed-in-house` |

`compare_pdfs_html` accepts `start_version_number` / `end_version_number`.
`render_examples.py` passes them; `diff_pdf.render_pdf_diff_html` does not, though its own
docstring names that caller: *"Pass the version numbers when the caller knows the bill's
legislative ordinals (rendering a numbered corpus file, not an upload) so the report heads
itself identically to the XML report for the same pair."*

Two docstrings and one README section state an invariant the code does not hold:

- `compare_xml_files_html`: deriving ordinals from stems *"is what makes a rendered example
  identical to the report a reader would get by uploading the same two files."* Measured: the
  upload keeps the `1_` / `2_` prefix and carries `version_number: null`.
- README §HTML report documents the header as `v1: … → v2: …` and says `diff_pdf.py`
  *"writes the same HTML report described above."*

### 2. Two filename→label algorithms, six derivation sites

`deltatrack.version_stems.label_from_stem` strips a numeric `<n>_` prefix.
`web/app.py::_label_from_filename` strips path components and the extension only, and is the
one label derivation with no test.

Sites that re-derive version identity from a filename:

| # | Site | Label | Ordinal |
|---|---|---|---|
| 1 | `compare/xml.py::compare_xml_files_html` | ✅ | ✅ |
| 2 | `diff_pdf.py::render_pdf_diff_html` | ✅ | ✗ |
| 3 | `diff_bill.py::cmd_compare` (html branch) | ✅ inline | ✅ inline |
| 4 | `diff_bill.py::cmd_compare` (json branch) | ✗ | ✅ separate inline loop |
| 5 | `web/app.py::_label_from_filename` | different algorithm | ✗ |
| 6 | `scripts/render_examples.py::render_pdf_diff` | ✅ inline | ✅ inline |

(`tests/test_canonical_baseline.py` and `tests/test_pdf_canonical_baseline.py` re-derive too.)

### 3. `--format json` and `?output=json` are different schemas

| | CLI `--format json` | API `?output=json` |
|---|---|---|
| Top-level keys | `bill_number`, `bill_type`, `changes`, `congress`, `new_version`, `new_version_number`, `old_version`, `old_version_number`, `summary` | `bill`, `changes`, `full_text`, `generator`, `schema_version`, `summary`, `tree`, `versions` |
| `changes[0]` keys | `change_type`, `display_path_new`, `display_path_old`, `element_id_new`, `element_id_old`, `match_path`, `new_text`, `old_text`, `section_number`, `text_diff` | `amount_entries`, `anchor_resolution`, `change_type`, `full_text_span`, `id`, `location`, `move`, `path`, `section_number`, `text` |
| Shared | `changes` and `summary` at top level; `change_type` and `section_number` within a change |

Both report 39 changes and an identical summary — the *diff* agrees, only the serialization
differs. The split is deliberate and documented (`docs/architecture.md`, README). Its
consequence is not: **there is no CLI route to canonical JSON.** The README directs consumers
to obtain it by rendering HTML, opening it in a browser and clicking *Download `diff.json`*.
In the other direction, `?output=json` is unreachable from the UI — `web/webapp/js/compare.js`
only ever requests `output=html`.

### 4. `--financial` means two things depending on `--format`

`bill_diff_to_dict(financial=True)` attaches a `financial` block to 18 of the 39 changes and a
top-level `financial_summary`.

- `--format json` → `financial_only=args.financial` (filters) **and** `financial=args.financial` (enriches)
- `--format html` → `financial_only=args.financial` (filters); enrichment hardcoded on in `compare/xml.py`

One flag, two meanings, selected by a sibling flag. ([#671] may overtake this.)

### 5. Error handling lives only in the web layer

| Input | CLI | UI |
|---|---|---|
| Enrolled / unnumbered PDF | uncaught `UnsupportedLayoutError` → traceback | HTTP 422, message shown verbatim |
| Malformed XML | uncaught `ParseError: syntax error: line 1, column 0` | HTTP 415, `start_file: not XML (no leading '<')` |

`UnsupportedLayoutError` carries a message written for an end user (*"…Use the XML version of
the bill instead."*). The CLI never presents it as a message.

### 6. Ragged capability matrix

| | `diff_bill.py compare` | `diff_pdf.py` | `POST /api/compare` |
|---|---|---|---|
| HTML out | ✅ default | ✅ only | ✅ default |
| JSON out | ✅ legacy shape | ✗ | ✅ canonical |
| `--include-unchanged` | ✅ | ✗ | ✗ |
| `--filter` | ✅ | ✗ | ✗ |
| `--financial` | ✅ | ✗ | ✗ |
| Explicit labels | ✗ derived | ✅ `--v1-label` / `--v2-label` | ✗ derived |
| Version ordinals | ✅ auto | ✗ | ✗ |

No knob is available on all three surfaces.

### 7. Module API asymmetry

`compare/xml.py` exposes four entry points (`compare_xml`, `compare_xml_html`,
`compare_xml_trees_html`, `compare_xml_files_html`); `compare/pdf.py` exposes two. The absent
`compare_pdf_files_html` is why `render_examples.py` and `diff_pdf.py` each hand-roll the
file→label→ordinal step, and why they disagree (finding 1). Separately, `compare_pdfs_html`
accepts version numbers and `compare_xml_html` does not, yet `web/app.py`'s `_COMPARE` table
calls both through one uniform call site.

### 8. Stale descriptions

- `web/__init__.py` says the app *"returns canonical diff JSON … for the browser front-end in
  `web/webapp/` to render."* The front-end requests `output=html` and writes the returned HTML
  straight into a tab; it never touches JSON.
- `docs/web-compare.md`'s "CLI entrypoint" row omits `./diff_pdf.py`, and its local-equivalent
  snippet imports `from compare.pdf import …` (pre-[#398] path) — already [#606].

### 9. Nothing tests CLI/UI parity

`tests/test_pipeline_parity.py` compares the XML and PDF *pipelines*.
`tests/test_surface_boundary.py` enforces import direction. Nothing renders one input through
both the CLI and the API and compares the results. That absence is why findings 1–5 are
invisible to CI.

## Reproducing

```
uv run python docs/research/cli-ui-parity/probes/probe_paths.py       # findings 1, 3, 6
uv run python docs/research/cli-ui-parity/probes/probe_htmldiff.py    # findings 1, 2 (run after probe_paths)
uv run python docs/research/cli-ui-parity/probes/probe_flags.py       # findings 3, 5, 6
uv run python docs/research/cli-ui-parity/probes/probe_financial.py   # finding 4
```

Each drives the real entry points — `argparse` `main()` for the commands, the FastAPI route
through `TestClient` for the endpoint — rather than reasoning about them. Output lands in the
gitignored `probes/out/`.

## Closure

Working material, per AGENTS.md §"Research artifacts are working material". Once the findings
are filed as issues and the parity gate (finding 9) exists to hold the invariant, delete this
directory — the gate, not this document, is the durable home for the conclusion.

[#42]: https://github.com/AgoraDMV/DeltaTrack/issues/42
[#367]: https://github.com/AgoraDMV/DeltaTrack/issues/367
[#398]: https://github.com/AgoraDMV/DeltaTrack/issues/398
[#606]: https://github.com/AgoraDMV/DeltaTrack/issues/606
[#671]: https://github.com/AgoraDMV/DeltaTrack/issues/671
