"""Render a bill's PDF-derived and XML-derived diffs side by side and serve them.

A development aid for spotting parity bugs between the two diff pipelines: the
same two bill versions, diffed once from the published PDFs and once from the
structured XML, shown in two panes of one page. Differences in breadcrumbs,
section grouping, financial callouts, or change counts between the panes are
usually a pipeline inconsistency worth chasing.

Usage::

    uv run python scripts/serve_compare.py 118-hr-8752
    uv run python scripts/serve_compare.py 118-hr-8752 --v1 1_reported-in-house --v2 2_engrossed-in-house
    uv run python scripts/serve_compare.py path/to/bill-dir --port 8765 --no-browser

The bill directory holds ``<n>_<label>.{xml,pdf}`` version files — the layout
``fetch_bills.py download <congress> <type> <number> --format both`` produces
under ``bills/``. With no ``--v1``/``--v2`` the two lowest-numbered versions
that have *both* formats are used. Rendered HTML goes to a temp dir (never
committed); Ctrl-C stops the server.

The panes reflect whatever the current checkout produces, so run this on the
branch whose diff output you want to inspect.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import sys
import tempfile
import webbrowser
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bill_tree import bill_title, normalize_bill  # noqa: E402
from diff_bill import bill_diff_to_dict, diff_bills  # noqa: E402
from diff_pdf import render_pdf_diff_html  # noqa: E402
from formatters.canonical import view_from_canonical, xml_diff_to_canonical  # noqa: E402
from formatters.diff_html import format_diff_html  # noqa: E402
from formatters.text_serializer import build_xml_full_text  # noqa: E402
from shared.version_stems import label_from_stem, version_number_from_stem  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BILLS = PROJECT_ROOT / "bills"


def _resolve_bill_dir(arg: str) -> Path:
    """Accept either a path to a bill dir or a name under ``bills/``."""
    direct = Path(arg)
    if direct.is_dir():
        return direct
    under_bills = BILLS / arg
    if under_bills.is_dir():
        return under_bills
    raise SystemExit(f"Bill directory not found: tried ./{arg} and {under_bills}")


def _pick_versions(bill_dir: Path, v1: str | None, v2: str | None) -> tuple[str, str]:
    """Choose two version stems that have both an .xml and a .pdf.

    Defaults to the two lowest-numbered such versions; validates explicit picks.
    """
    both = {p.stem for p in bill_dir.glob("*.xml")} & {p.stem for p in bill_dir.glob("*.pdf")}
    stems = sorted(both, key=lambda s: (version_number_from_stem(s) or 0, s))
    if v1 and v2:
        missing = [s for s in (v1, v2) if s not in both]
        if missing:
            raise SystemExit(f"No .xml+.pdf pair for {missing} in {bill_dir}. Available: {stems}")
        return v1, v2
    if len(stems) < 2:
        raise SystemExit(f"Need two versions with both .xml and .pdf in {bill_dir}. Found: {stems or 'none'}")
    return stems[0], stems[1]


def _render_xml_diff_html(v1_path: Path, v2_path: Path) -> str:
    """Diff two bill XML versions and render the unified HTML report.

    Mirrors the XML branch of ``render_examples.render_xml_diff`` but takes paths
    and returns the HTML, so this tool stays independent of the examples script.
    """
    v1 = normalize_bill(v1_path)
    v2 = normalize_bill(v2_path)
    diff_dict = bill_diff_to_dict(diff_bills(v1, v2), financial=True)
    for key, stem in (("old_version_number", v1_path.stem), ("new_version_number", v2_path.stem)):
        num = version_number_from_stem(stem)
        if num is not None:
            diff_dict[key] = num
    full_text, full_text_spans, sections, tree = build_xml_full_text(v1, v2)
    canonical = xml_diff_to_canonical(diff_dict, full_text=full_text, full_text_spans=full_text_spans, tree=tree)
    return format_diff_html(
        view_from_canonical(canonical), canonical=canonical, title=bill_title(v2), sections=sections
    )


def _index_html(bill_label: str, v1_label: str, v2_label: str) -> str:
    """Two-pane shell that frames pdf.html and xml.html from the same server."""
    sub = escape(f"{v1_label} → {v2_label} · same versions, two pipelines")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(bill_label)} — PDF vs XML diff</title>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; height: 100%; color: #1c1c3a;
    font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; }}
  body {{ display: flex; flex-direction: column; }}
  header {{ padding: 0.6rem 1rem; background: #2c2c5c; color: #f9f7f5; flex: 0 0 auto; }}
  header h1 {{ font-size: 1rem; margin: 0; font-weight: 600; }}
  header p {{ margin: 0.15rem 0 0; font-size: 0.8rem; color: #c8c8e0; }}
  .panes {{ flex: 1 1 auto; display: flex; min-height: 0; }}
  .pane {{ flex: 1 1 50%; display: flex; flex-direction: column;
    min-width: 0; border-right: 1px solid #d8d4ce; }}
  .pane:last-child {{ border-right: none; }}
  .pane-head {{ flex: 0 0 auto; padding: 0.4rem 0.8rem; background: #eef0f8;
    border-bottom: 1px solid #d8d4ce; font-size: 0.82rem; font-weight: 600;
    display: flex; justify-content: space-between; align-items: center; }}
  .pane-head .src {{ font-weight: 400; color: #686881; font-size: 0.78rem; }}
  .pane-head a {{ color: #2c2c5c; font-size: 0.78rem; }}
  iframe {{ flex: 1 1 auto; width: 100%; border: 0; }}
</style>
</head>
<body>
<header>
  <h1>{escape(bill_label)}</h1>
  <p>{sub}</p>
</header>
<div class="panes">
  <div class="pane">
    <div class="pane-head"><span>PDF-derived diff</span>
      <span class="src">from the published PDFs · <a href="pdf.html" target="_blank">open ↗</a></span></div>
    <iframe src="pdf.html" title="PDF diff"></iframe>
  </div>
  <div class="pane">
    <div class="pane-head"><span>XML-derived diff</span>
      <span class="src">from the structured XML · <a href="xml.html" target="_blank">open ↗</a></span></div>
    <iframe src="xml.html" title="XML diff"></iframe>
  </div>
</div>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Serve a bill's PDF and XML diffs side by side.")
    p.add_argument("bill", help="Bill dir path, or a name under bills/ (e.g. 118-hr-8752)")
    p.add_argument("--v1", help="Older version stem (default: lowest-numbered version with both formats)")
    p.add_argument("--v2", help="Newer version stem (default: second-lowest)")
    p.add_argument("--port", type=int, default=8765, help="Port to serve on (default: 8765)")
    p.add_argument("--no-browser", action="store_true", help="Don't open a browser window")
    return p


def main() -> None:
    args = build_parser().parse_args()
    bill_dir = _resolve_bill_dir(args.bill)
    v1_stem, v2_stem = _pick_versions(bill_dir, args.v1, args.v2)
    v1_label, v2_label = label_from_stem(v1_stem), label_from_stem(v2_stem)

    print(f"Rendering {bill_dir.name}: {v1_label} → {v2_label}")
    pdf_html = render_pdf_diff_html(
        bill_dir / f"{v1_stem}.pdf", bill_dir / f"{v2_stem}.pdf", v1_label=v1_label, v2_label=v2_label
    )
    xml_html = _render_xml_diff_html(bill_dir / f"{v1_stem}.xml", bill_dir / f"{v2_stem}.xml")

    out_dir = Path(tempfile.mkdtemp(prefix="serve_compare_"))
    (out_dir / "pdf.html").write_text(pdf_html)
    (out_dir / "xml.html").write_text(xml_html)
    (out_dir / "index.html").write_text(_index_html(bill_dir.name, v1_label, v2_label))

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out_dir))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        url = f"http://127.0.0.1:{args.port}/"
        print(f"Serving side-by-side comparison at {url}  (Ctrl-C to stop)")
        if not args.no_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping.")


if __name__ == "__main__":
    main()
