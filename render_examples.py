"""Regenerate the committed example HTML diffs under `examples/`.

Run from anywhere:

    uv run python render_examples.py

Each example is a rendered diff between two versions of one bill in the
corpus, checked into the repo so reviewers can see real output without
running the pipeline themselves. Re-run after any change that affects
diff output (parser, diff classifier, renderer). The output HTML is also
marked `linguist-generated=true` in `.gitattributes` so it doesn't pollute
git blame or PR diff views by default.

Add a new bill by appending to `EXAMPLES_TO_RENDER`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bill_tree import bill_title, normalize_bill
from diff_bill import bill_diff_to_dict, diff_bills
from formatters.canonical import view_from_canonical, xml_diff_to_canonical
from formatters.diff_html import format_diff_html
from formatters.text_serializer import build_xml_full_text
from server.pdf_compare import compare_pdfs_html
from shared.version_stems import label_from_stem, version_number_from_stem

PROJECT_ROOT = Path(__file__).parent
BILLS = PROJECT_ROOT / "bills"
EXAMPLES = PROJECT_ROOT / "examples"


@dataclass(frozen=True)
class ExampleSpec:
    """One bill version-pair to render. Filenames follow `<n>_<label>.{xml,pdf}`."""

    bill_dir: str  # under bills/, e.g. "118-hr-8752"
    bill_type: str  # "hr", "s", etc.
    bill_number: int
    v1_filename_stem: str  # e.g. "1_reported-in-house"
    v2_filename_stem: str  # e.g. "2_engrossed-in-house"


EXAMPLES_TO_RENDER: list[ExampleSpec] = [
    ExampleSpec(
        bill_dir="118-hr-8752",
        bill_type="hr",
        bill_number=8752,
        v1_filename_stem="1_reported-in-house",
        v2_filename_stem="2_engrossed-in-house",
    ),
]


def render_xml_diff(spec: ExampleSpec) -> Path:
    bill_dir = BILLS / spec.bill_dir
    v1 = normalize_bill(bill_dir / f"{spec.v1_filename_stem}.xml")
    v2 = normalize_bill(bill_dir / f"{spec.v2_filename_stem}.xml")
    diff = diff_bills(v1, v2)
    diff_dict = bill_diff_to_dict(diff, financial=True)
    v1_num = version_number_from_stem(spec.v1_filename_stem)
    v2_num = version_number_from_stem(spec.v2_filename_stem)
    if v1_num is not None:
        diff_dict["old_version_number"] = v1_num
    if v2_num is not None:
        diff_dict["new_version_number"] = v2_num
    # Carry the serialized full text so the report offers the full-bill view.
    # XML full_text is gutterless paragraph flow (no PDF line-number column); the
    # v2 walk also yields the section TOC offsets.
    full_text, full_text_spans, sections = build_xml_full_text(v1, v2)
    canonical = xml_diff_to_canonical(diff_dict, full_text=full_text, full_text_spans=full_text_spans)
    html = format_diff_html(
        view_from_canonical(canonical),
        canonical=canonical,
        title=bill_title(v2),
        sections=sections,
    )
    out = EXAMPLES / f"{spec.bill_type}{spec.bill_number}_xml_diff.html"
    out.write_text(html)
    return out


def render_pdf_diff(spec: ExampleSpec) -> Path:
    # Delegate to the same pipeline the web app and CLI use, so the committed
    # example carries the full-bill text view, section TOC, and embedded export
    # rather than the thin per-change-only report.
    bill_dir = BILLS / spec.bill_dir
    html = compare_pdfs_html(
        (bill_dir / f"{spec.v1_filename_stem}.pdf").read_bytes(),
        (bill_dir / f"{spec.v2_filename_stem}.pdf").read_bytes(),
        start_label=label_from_stem(spec.v1_filename_stem),
        end_label=label_from_stem(spec.v2_filename_stem),
    )
    out = EXAMPLES / f"{spec.bill_type}{spec.bill_number}_pdf_diff.html"
    out.write_text(html)
    return out


def main() -> None:
    for spec in EXAMPLES_TO_RENDER:
        for renderer in (render_xml_diff, render_pdf_diff):
            out = renderer(spec)
            print(f"Wrote {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
