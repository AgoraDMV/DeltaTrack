"""Regenerate the committed example HTML diffs under `examples/`.

Run from the project root:

    uv run python render_examples.py

Each example is a rendered diff between two versions of HR 8752, checked
into the repo so reviewers can see real output without running the pipeline
themselves. Re-run after any change that affects diff output (parser,
diff classifier, renderer). The output HTML is also marked
`linguist-generated=true` in `.gitattributes` so it doesn't pollute git
blame or PR diff views by default.
"""

from __future__ import annotations

from pathlib import Path

from bill_tree import normalize_bill
from diff_bill import bill_diff_to_dict, diff_bills
from diff_pdf import diff_pdfs
from formatters.html import format_html
from formatters.pdf_html import format_pdf_html
from parsers.pdf_text import extract_clean_pages

BILLS = Path(__file__).parent / "bills" / "118-hr-8752"
EXAMPLES = Path(__file__).parent / "examples"


def render_xml_diff() -> None:
    v1_path = BILLS / "1_reported-in-house.xml"
    v2_path = BILLS / "2_engrossed-in-house.xml"
    v1 = normalize_bill(v1_path)
    v2 = normalize_bill(v2_path)
    diff = diff_bills(v1, v2)
    diff_dict = bill_diff_to_dict(diff, financial=True)
    diff_dict["old_version_number"] = 1
    diff_dict["new_version_number"] = 2
    html = format_html(diff_dict)
    out = EXAMPLES / "hr8752_xml_diff.html"
    out.write_text(html)
    print(f"Wrote {out.relative_to(Path.cwd())} ({len(html):,} bytes)")


def render_pdf_diff() -> None:
    v1 = extract_clean_pages(BILLS / "1_reported-in-house.pdf")
    v2 = extract_clean_pages(BILLS / "2_engrossed-in-house.pdf")
    diff = diff_pdfs(v1, v2)
    html = format_pdf_html(
        diff,
        bill_type="hr",
        bill_number=8752,
        congress=118,
        v1_label="reported-in-house",
        v2_label="engrossed-in-house",
    )
    out = EXAMPLES / "hr8752_pdf_diff.html"
    out.write_text(html)
    print(f"Wrote {out.relative_to(Path.cwd())} ({len(html):,} bytes)")


def main() -> None:
    render_xml_diff()
    render_pdf_diff()


if __name__ == "__main__":
    main()
