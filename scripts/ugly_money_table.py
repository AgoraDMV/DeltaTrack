#!/usr/bin/env python3
"""Emit a deliberately unstyled money-diff table for staffer validation.

The point is to strip ALL fidelity and styling so the only thing under test is:
is the structured money data itself worth looking at? If a staffer leans into
this ugly table, the moat is the data, not the rendering.

Usage:
    python scripts/ugly_money_table.py OLD.xml NEW.xml -o table.html
"""

import argparse
import html
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PY = sys.executable  # the interpreter running this script already has the deps


def fmt(n):
    return "—" if n is None else f"${n:,.0f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old_xml")
    ap.add_argument("new_xml")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()

    out = subprocess.run(
        [PY, "diff_bill.py", "compare", args.old_xml, args.new_xml, "--financial", "--format", "json"],
        cwd=HERE,
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        raise SystemExit(f"diff_bill.py failed ({out.returncode}):\n{out.stderr}")
    d = json.loads(out.stdout)

    rows = []
    for c in d["changes"]:
        f = c["financial"]
        path = " &rsaquo; ".join(html.escape(p) for p in c.get("match_path", []))
        for old, new in f.get("paired_amounts", []):
            if old == new:
                continue
            delta = "" if None in (old, new) else fmt(new - old)
            rows.append(f"<tr><td>{path}</td><td>{fmt(old)}</td><td>{fmt(new)}</td><td>{delta}</td></tr>")

    title = f"H.R. {d['bill_number']} — {d['old_version']} &rarr; {d['new_version']} — money changes"
    doc = (
        "<!doctype html><meta charset=utf-8>"
        f"<title>{title}</title>"
        "<body style='font-family:monospace'>"
        f"<h3>{title}</h3>"
        f"<p>{len(rows)} changed amounts. No styling on purpose.</p>"
        "<table border=1 cellpadding=4 cellspacing=0>"
        "<tr><th>account</th><th>old</th><th>new</th><th>change</th></tr>" + "".join(rows) + "</table></body>"
    )
    Path(args.output).write_text(doc)
    print(f"wrote {args.output} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
