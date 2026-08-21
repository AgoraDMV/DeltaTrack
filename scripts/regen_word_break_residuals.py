"""Regenerate the word-break residual fixture read by tests/test_pdf_word_break_recall.py.

A residual is a printed word break the merger could not decide correctly: neither
candidate form (`left-right` nor `leftright`) appears anywhere in the document's own
text, so `pdf_text._shape_keeps_hyphen` decides it from letter case alone, and case
cannot tell a lowercase-continuation compound (`government-` / `driven`) from a
syllable break (`equip-` / `ment`).

Run after an INTENTIONAL change to the break rule, then review the JSON diff:

    uv run python scripts/regen_word_break_residuals.py

The test asserts SET EQUALITY against this file, so both directions show up in review:
a new entry is a site that stopped resolving, a removed entry is one that started.
Never add an entry just to clear a red run -- establish which form the bill actually
uses first, because a wrong entry silently blesses an invented word.

Note this measures the SINGLE-DOCUMENT path (`extract_clean_pages`). The shipped
comparison pools both versions' evidence (`compare/pdf.py`) and resolves strictly
more, so this fixture is an upper bound on what a reader actually sees.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests"))

from pdf_corpus import cached_pages, dual_format_versions  # noqa: E402

from tests import test_pdf_word_break_recall as gate  # noqa: E402


def main() -> int:
    rows: list[dict[str, str]] = []
    for bill, xml_path, pdf_path in dual_format_versions():
        version = f"{bill}/{pdf_path.stem}"
        pages = cached_pages(pdf_path)
        forms = gate._xml_word_forms(xml_path)
        seen: set[tuple[str, str]] = set()
        for left, right, produced in gate._joined_words(gate._merge_groups(pages)):
            if gate._canon(produced) in forms or (left, right) in seen:
                continue
            seen.add((left, right))
            rows.append(
                {
                    "version": version,
                    "left": left,
                    "right": right,
                    "produced": produced,
                    "reason": "no in-document evidence for either form; decided by case shape",
                }
            )
        print(f"{version:52s} residuals={len(seen)}", flush=True)

    rows.sort(key=lambda r: (r["version"], r["left"], r["right"]))
    out = gate._RESIDUALS_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"residuals": rows}, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote {len(rows)} residuals to {out.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
