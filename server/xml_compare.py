"""Turn two bill-XML byte blobs into canonical diff JSON or standalone HTML.

The XML counterpart to ``server/pdf_compare.py``. Same contract, same stateless
guarantee: uploaded XML lives only for the duration of the request (temp files
deleted before return), nothing is persisted.

    normalize_bill()       (bill_tree)            — parse XML → BillTree
    diff_bills()           (diff_bill)            — structural diff
    bill_diff_to_dict()    (diff_bill)            — diff → dict (+ financial)
    serialize_tree()       (formatters.text_serializer) — full bill text per side
    xml_diff_to_canonical()(formatters.canonical) — dict → canonical JSON
    view_from_canonical()  (formatters.canonical) — canonical → DiffView (HTML path)
    format_diff_html()     (formatters.diff_html) — HTML path (view + canonical)

The XML pipeline resolves changes structurally (no page/line coordinates), and
its full_text is gutterless paragraph flow — the renderer keys off
``versions.v2.source == "xml"`` to drop the PDF line-number gutter.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from bill_tree import normalize_bill
from diff_bill import bill_diff_to_dict, diff_bills, filter_diff
from formatters.canonical import view_from_canonical, xml_diff_to_canonical
from formatters.diff_html import format_diff_html
from formatters.text_serializer import serialize_tree


def _build_canonical(
    start_bytes: bytes,
    end_bytes: bytes,
    start_label: str,
    end_label: str,
) -> dict:
    """Parse, diff, and serialize both XML versions into canonical JSON.

    Temp files exist only long enough for ``normalize_bill`` to read them. The
    filename-derived labels override the XML's embedded version names so the
    report reflects what the user uploaded (matching the PDF path).
    """
    with tempfile.TemporaryDirectory(prefix="deltatrack-") as tmp:
        start_path = Path(tmp) / "start.xml"
        end_path = Path(tmp) / "end.xml"
        start_path.write_bytes(start_bytes)
        end_path.write_bytes(end_bytes)

        old_tree = normalize_bill(start_path)
        new_tree = normalize_bill(end_path)

    result = filter_diff(diff_bills(old_tree, new_tree), include_unchanged=False)
    diff_dict = bill_diff_to_dict(result, financial=True)
    diff_dict["old_version"] = start_label
    diff_dict["new_version"] = end_label

    full_text = {"v1": serialize_tree(old_tree), "v2": serialize_tree(new_tree)}
    return xml_diff_to_canonical(diff_dict, full_text=full_text)


def compare_xml(
    start_bytes: bytes,
    end_bytes: bytes,
    *,
    start_label: str = "Start version",
    end_label: str = "End version",
) -> dict:
    """Diff two bill XML documents and return canonical diff JSON (schema v1.2)."""
    return _build_canonical(start_bytes, end_bytes, start_label, end_label)


def compare_xml_html(
    start_bytes: bytes,
    end_bytes: bytes,
    *,
    start_label: str = "Start version",
    end_label: str = "End version",
) -> str:
    """Diff two bill XML documents and return a standalone HTML report.

    The DiffView is rebuilt from the canonical (``view_from_canonical``) so the
    rendered report and the embedded ``diff.json`` come from one source of truth.
    The XML full-bill view renders gutterless (no PDF line-number column).
    """
    canonical = _build_canonical(start_bytes, end_bytes, start_label, end_label)
    view = view_from_canonical(canonical)
    return format_diff_html(view, canonical=canonical)
