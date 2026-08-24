#!/usr/bin/env python3
"""Emit a deliberately unstyled money-diff table for staffer validation.

DISABLED by #671, which removed `paired_amounts` from the `--financial` JSON this
reads. The script built exactly the paired old/new/change table that issue removed
from the report, for the same reason: an appropriations paragraph mixes top-line
appropriations, sub-allocations carved out of them, "not to exceed" ceilings and
loan guarantee commitment limitations, and this table rendered them identically.

It exits with an error rather than being deleted or quietly repointed. Deleting it
is a call for whoever owns the validation exercise; repointing it at the surviving
`old_amounts` / `new_amounts` would change what it measures without saying so; and
leaving it alone was the worst option, because `f.get("paired_amounts", [])` returns
`[]` now, so it would print "0 changed amounts" for a real appropriations bill --
a silent wrong answer, which is the failure class #671 exists to remove.

Restoring it needs the account-level model in #115 and the leveled tree in #175,
after which a table like this can say which KIND of figure each row is.

Usage (once restored):
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


DISABLED_MESSAGE = (
    "ugly_money_table.py is disabled: it renders paired old/new/change amounts, and "
    "#671 removed `paired_amounts` from the --financial JSON because the pipeline "
    "cannot yet say whether a figure is an appropriation, a sub-allocation of one, a "
    "ceiling or a commitment limitation. Running it now would report 0 changed "
    "amounts for every bill. See #115 and #175."
)


def main():
    raise SystemExit(DISABLED_MESSAGE)


def _build_table_disabled_pending_115():
    """The original body, kept intact so restoring it is a deletion rather than a rewrite."""
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
