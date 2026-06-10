# Public web compare (`webapp/` + `server/`)

Brief map of the live home page, how it relates to the Python CLI, and where to change things.

**Live site:** [deltatrack.agoradmv.org](https://deltatrack.agoradmv.org) (served by the FastAPI app below).

HTTP→HTTPS: see **[docs/https-redirect.md](https-redirect.md)** — Apache `RewriteRule`
before `ProxyPass` + ISPConfig **Force HTTPS**. App middleware is a backstop only.
`webapp/.htaccess` is not used (Apache proxies all traffic to uvicorn).

---

## Two options on the home page

| Path | Status | What it does |
|---|---|---|
| **Browser-only** (`index.html`, left card) | Coming soon | Future WebAssembly build — PDFs never leave the device. Not wired up yet. |
| **Process on our server** (`compare.html`, right card) | **Available now** | User uploads start + end PDFs; server runs the Python PDF diff and returns a standalone HTML report in a new tab. Stateless — PDFs are not stored. |

Sample without uploading: `compare.html?example=1` loads a bundled report from `webapp/sample/example.html`.

The CLI path ([README](../README.md)) is separate: download Congress.gov **XML**, run `diff_bill.py compare … --format html` locally. Same HTML *renderer* family, different input pipeline (XML vs PDF).

---

## Background: CLI equivalent (pre-web development)

Past development was command-line first. The [README](../README.md) quickstart compares **XML** files:

```bash
uv run python fetch_bills.py download 118 hr 4366

uv run python diff_bill.py compare \
  bills/118-hr-4366/1_reported-in-house.xml \
  bills/118-hr-4366/2_engrossed-in-house.xml \
  --format html -o reports/hr4366_v1_vs_v2.html
```

The public upload page does the **same kind of output** (standalone HTML via `format_diff_html`) but on **PDF** inputs. There is no `diff_pdf.py compare` subcommand — the web service calls the same steps as `server/pdf_compare.py` / `render_examples.py` → `render_pdf_diff()`.

Local equivalent of uploading two PDFs to the site:

```bash
# Fetch PDFs alongside XML (README Testing section)
uv run python fetch_bills.py download 118 hr 4366 --format both

# Same pipeline as POST /api/compare?output=html
uv run python -c "
from pathlib import Path
from server.pdf_compare import compare_pdfs_html

start = Path('bills/118-hr-4366/1_reported-in-house.pdf')
end   = Path('bills/118-hr-4366/2_engrossed-in-house.pdf')
html = compare_pdfs_html(
    start.read_bytes(), end.read_bytes(),
    start_label='Reported in House',
    end_label='Engrossed in House',
)
Path('reports/hr4366_pdf_v1_vs_v2.html').write_text(html)
print('Wrote reports/hr4366_pdf_v1_vs_v2.html')
"
```

Or regenerate a committed corpus example (if the bill is listed in `EXAMPLES_TO_RENDER` inside `render_examples.py`):

```bash
uv run python fetch_bills.py download 118 hr 8752 --format both
uv run python render_examples.py   # writes examples/hr8752_pdf_diff.html
```

| | README quickstart (XML) | Web upload / `compare_pdfs_html` (PDF) |
|---|---|---|
| Input | Congress.gov XML on disk | User PDF bytes (upload) |
| Diff engine | `diff_bill.py` | `diff_pdf.py` |
| HTML renderer | `format_diff_html` via `xml_dict_to_view` | `format_diff_html` via `pdf_diff_to_view` |
| CLI entrypoint | `diff_bill.py compare … --format html` | `server/pdf_compare.py` (HTTP) or snippet above |

XML and PDF paths can disagree on section boundaries and change counts for the same bill pair; compare like with like when validating.

---

## Request flow (server path)

```
Browser (webapp/compare.html)
  │  POST /api/compare?output=html  (multipart: start_pdf, end_pdf)
  ▼
server/app.py                    ← FastAPI: upload guards, concurrency, timeout
  ▼
server/pdf_compare.py            ← thin wrapper (bytes in → HTML out)
  │  extract_clean_pages()       parsers/pdf_text.py
  │  diff_pdfs()                 diff_pdf.py
  │  pdf_diff_to_view()          formatters/adapters.py
  │  format_diff_html()          formatters/diff_html.py
  ▼
Standalone HTML report           ← opened in new tab by webapp/js/compare.js
```

This is the same PDF engine as `render_examples.py` → `render_pdf_diff()` and `prototype/generate_samples.py` — not a reimplementation. The web layer only handles HTTP upload, labels from filenames, and returning HTML.

JSON output (`?output=json`) still exists for tests and tooling; the compare UI uses HTML only.

---

## Repo layout

| Path | Role |
|---|---|
| `webapp/index.html` | Landing — two path cards |
| `webapp/compare.html` | PDF upload UI |
| `webapp/js/compare.js` | Upload, validation, fetch, open report tab |
| `webapp/css/styles.css` | Upload/landing styles (report CSS is inlined by Python) |
| `webapp/sample/example.html` | Bundled sample report for `?example=1` |
| `server/app.py` | FastAPI app: `/api/compare` + static mount of `webapp/` |
| `server/pdf_compare.py` | In-process call into `diff_pdf` + `format_diff_html` |

Run locally:

```bash
uv sync
uvicorn server.app:app --reload --port 8077
# → http://127.0.0.1:8077/
```

Production ops (hosting, limits, systemd) live in gitignored `docs-for-ai/deployment.md`.

---

## Update guidelines

**Diff accuracy or report content** — edit the Python engine, not the web UI:

- `diff_pdf.py`, `parsers/`, `formatters/diff_html.py`, `formatters/adapters.py`
- Re-run PDF tests: `uv run pytest tests/test_pdf_*`
- Regenerate committed examples if output shape changes: `uv run python render_examples.py`

**Upload / API behavior** — `server/app.py`, `server/pdf_compare.py`

- Keep **150 MB** cap aligned in three places: Apache `LimitRequestBody`, `MAX_UPLOAD_BYTES` in `app.py`, `MAX_BYTES` in `compare.js`
- Keep `MAX_CONCURRENT_DIFFS` and `DIFF_TIMEOUT_S` in mind on the 8 GB host

**Upload page copy or UX** — `webapp/compare.html`, `webapp/js/compare.js`, `webapp/css/styles.css`

**Landing page / two-path messaging** — `webapp/index.html`

**Sample report** — replace `webapp/sample/example.html` after renderer changes (copy from `examples/*_pdf_diff.html` or regenerate)

**Do not** duplicate diff logic in JavaScript; the web app should stay a thin client over `POST /api/compare`.

After deploy: `git pull && uv sync --no-dev && sudo systemctl restart deltatrack` (see private deployment runbook).
