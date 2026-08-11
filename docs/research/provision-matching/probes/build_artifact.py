"""Deterministic stdlib Markdown -> designed HTML artifact for the research paper.

Handles exactly the constructs this paper uses: #/##/### headings, GFM pipe tables,
- and 1. lists (one nesting level), > blockquotes, --- rules, paragraphs, and inline
**bold** / *italic* / `code` / [text](url). No network, no deps.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

# Resolve relative to this script so the paths survive relocation of the study bundle.
_HERE = Path(__file__).resolve().parent
SRC = _HERE.parent / "paper.md"
OUT = _HERE.parent / "paper.html"


# footnote reference counts, keyed by footnote name — reset per document in convert().
# Repeated references to one footnote get unique ids (fnref-N, fnref-N-2, …) so the emitted
# HTML has no duplicate ids; each footnote's back-link targets the first use (fnref-N).
_fnref_seen: dict[str, int] = {}


def _fn_marker(m: "re.Match[str]") -> str:
    key = m.group(1)
    n = _fnref_seen.get(key, 0) + 1
    _fnref_seen[key] = n
    refid = f"fnref-{key}" if n == 1 else f"fnref-{key}-{n}"
    return f'<sup class="fn"><a href="#fn-{key}" id="{refid}">{key}</a></sup>'


def inline(text: str) -> str:
    # escape first, then re-introduce markup
    t = html.escape(text)
    # footnote markers [^N] / [^slug] -> superscript link (before links; they don't overlap)
    t = re.sub(r"\[\^([\w-]+)\]", _fn_marker, t)
    # links [text](url)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', t)
    # inline code
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    # bold then italic (avoid clobbering ** with *)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    # arrows / en-dashes already literal; leave as-is
    return t


def cells(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in row.split("|")]


def convert(md: str) -> str:
    _fnref_seen.clear()  # deterministic per-document footnote ref numbering
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    def flush_para(buf: list[str]):
        if buf:
            out.append(f"<p>{inline(' '.join(buf).strip())}</p>")
            buf.clear()

    footnotes: list[tuple[str, str]] = []  # (num, text)
    para: list[str] = []
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # blank
        if not stripped:
            flush_para(para)
            i += 1
            continue

        # footnote definition [^N]: / [^slug]: text  (collect, render as a linked list at the end)
        fd = re.match(r"^\[\^([\w-]+)\]:\s*(.*)$", stripped)
        if fd:
            flush_para(para)
            num, txt = fd.group(1), fd.group(2)
            i += 1
            # absorb indented continuation lines
            while (
                i < n
                and lines[i].strip()
                and re.match(r"^\s+\S", lines[i])
                and not re.match(r"^\[\^[\w-]+\]:", lines[i].strip())
            ):
                txt += " " + lines[i].strip()
                i += 1
            footnotes.append((num, txt))
            continue

        # horizontal rule
        if stripped == "---":
            flush_para(para)
            out.append("<hr>")
            i += 1
            continue

        # headings
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            flush_para(para)
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue

        # table: a line with | and next line is a separator row
        if "|" in line and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1]) and "-" in lines[i + 1]:
            flush_para(para)
            header = cells(line)
            i += 2  # skip header + separator
            body_rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                body_rows.append(cells(lines[i]))
                i += 1
            thead = "".join(f"<th>{inline(c)}</th>" for c in header)
            trs = []
            for r in body_rows:
                tds = "".join(f"<td>{inline(c)}</td>" for c in r)
                trs.append(f"<tr>{tds}</tr>")
            out.append(
                '<div class="tablewrap"><table><thead><tr>'
                + thead
                + "</tr></thead><tbody>"
                + "".join(trs)
                + "</tbody></table></div>"
            )
            continue

        # blockquote (possibly multi-line)
        if stripped.startswith(">"):
            flush_para(para)
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(buf).strip())}</blockquote>")
            continue

        # lists (ordered / unordered) with one nesting level (2-space indent).
        # First collect items as (indent, text), absorbing wrapped continuation lines
        # (indented, no marker) into the preceding item's text.
        if re.match(r"^(\s*)([-*]|\d+\.)\s+", line):
            flush_para(para)
            items: list[tuple[int, bool, str]] = []  # (indent, ordered, text)
            while i < n:
                lm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if lm:
                    indent = len(lm.group(1))
                    ordered = bool(re.match(r"\d+\.", lm.group(2)))
                    items.append((indent, ordered, lm.group(3)))
                    i += 1
                elif lines[i].strip() and re.match(r"^\s+\S", lines[i]) and items:
                    # indented continuation of the previous item
                    items[-1] = (items[-1][0], items[-1][1], items[-1][2] + " " + lines[i].strip())
                    i += 1
                else:
                    break
            top_tag = "ol" if items and items[0][1] else "ul"
            out.append(f"<{top_tag}>")
            open_nested = None
            for indent, ordered, text in items:
                nested = indent >= 2
                if nested and open_nested is None:
                    open_nested = "ol" if ordered else "ul"
                    out.append(f"<{open_nested}>")
                if not nested and open_nested is not None:
                    out.append(f"</{open_nested}>")
                    open_nested = None
                out.append(f"<li>{inline(text)}</li>")
            if open_nested is not None:
                out.append(f"</{open_nested}>")
            out.append(f"</{top_tag}>")
            continue

        # default: paragraph accumulation
        para.append(stripped)
        i += 1

    flush_para(para)

    if footnotes:
        out.append('<ol class="footnotes">')
        for num, txt in sorted(footnotes, key=lambda f: (0, int(f[0]), "") if f[0].isdigit() else (1, 0, f[0])):
            # named footnotes get a visible [slug] label since the decimal bullet doesn't identify them
            label = "" if num.isdigit() else f'<span class="fn-key">[{num}]</span> '
            out.append(
                f'<li id="fn-{num}">{label}{inline(txt)} '
                f'<a class="fn-back" href="#fnref-{num}" aria-label="Back to reference {num}">&#8617;</a></li>'
            )
        out.append("</ol>")

    return "\n".join(out)


BODY = convert(SRC.read_text())

STYLE = """
<style>
:root{
  --ground:#f6f4ef; --panel:#fbfaf7; --ink:#1b1d24; --ink-soft:#4a4d57;
  --faint:#e7e2d8; --hair:#ddd7ca; --accent:#9a3b32; --accent-soft:#b9615a;
  --same:#3f6b52; --diff:#9a3b32; --link:#8a352d;
  --measure:66ch;
  --serif: "Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,"Times New Roman",serif;
  --sans: ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono: ui-monospace,"SF Mono","Menlo","Consolas",monospace;
}
@media (prefers-color-scheme: dark){
  :root{
    --ground:#15171c; --panel:#1c1f26; --ink:#e9e5da; --ink-soft:#a7a89f;
    --faint:#262a32; --hair:#2f333c; --accent:#d08a6f; --accent-soft:#b9615a;
    --same:#7bb08c; --diff:#d98a7f; --link:#e0a58f;
  }
}
:root[data-theme="light"]{
  --ground:#f6f4ef; --panel:#fbfaf7; --ink:#1b1d24; --ink-soft:#4a4d57;
  --faint:#e7e2d8; --hair:#ddd7ca; --accent:#9a3b32; --accent-soft:#b9615a;
  --same:#3f6b52; --diff:#9a3b32; --link:#8a352d;
}
:root[data-theme="dark"]{
  --ground:#15171c; --panel:#1c1f26; --ink:#e9e5da; --ink-soft:#a7a89f;
  --faint:#262a32; --hair:#2f333c; --accent:#d08a6f; --accent-soft:#b9615a;
  --same:#7bb08c; --diff:#d98a7f; --link:#e0a58f;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);
  font-family:var(--serif);font-size:18px;line-height:1.62;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;}
.wrap{max-width:calc(var(--measure) + 6rem);margin:0 auto;padding:clamp(2rem,5vw,5rem) clamp(1.1rem,4vw,3rem) 6rem;}
/* title block */
.masthead{border-top:3px solid var(--accent);padding-top:1.4rem;margin-bottom:2.6rem;}
.eyebrow{font-family:var(--sans);font-size:.72rem;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);font-weight:600;margin:0 0 1rem;}
h1{font-size:clamp(2rem,4.4vw,3.1rem);line-height:1.08;margin:.2rem 0 .4rem;font-weight:600;
  letter-spacing:-.012em;text-wrap:balance;}
h1 + p, .masthead h3{color:var(--ink-soft);}
/* headings */
h2{font-size:1.62rem;margin:3.4rem 0 1rem;padding-top:1.4rem;border-top:1px solid var(--hair);
  letter-spacing:-.01em;text-wrap:balance;font-weight:600;line-height:1.16;}
h3{font-size:1.18rem;margin:2.1rem 0 .6rem;font-weight:600;color:var(--ink);text-wrap:balance;
  font-family:var(--sans);letter-spacing:-.005em;}
h4{font-family:var(--sans);font-size:.95rem;margin:1.6rem 0 .5rem;letter-spacing:.02em;
  color:var(--ink-soft);font-weight:600;}
p{margin:0 0 1.05rem;max-width:var(--measure);}
a{color:var(--link);text-decoration:none;border-bottom:1px solid color-mix(in srgb,var(--link) 35%,transparent);}
a:hover{border-bottom-color:var(--link);}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px;}
strong{font-weight:600;color:var(--ink);}
em{font-style:italic;}
code{font-family:var(--mono);font-size:.86em;background:var(--faint);padding:.08em .34em;border-radius:3px;
  color:var(--ink);border:1px solid color-mix(in srgb,var(--hair) 60%,transparent);}
hr{border:0;height:1px;background:var(--hair);margin:2.4rem 0;max-width:var(--measure);}
/* lists */
ul,ol{margin:0 0 1.1rem;padding-left:1.4rem;max-width:var(--measure);}
li{margin:.32rem 0;padding-left:.2rem;}
li::marker{color:var(--accent-soft);}
ul ul,ul ol,ol ul,ol ol{margin:.3rem 0 .5rem;}
/* blockquote — worked example callouts */
blockquote{margin:1.4rem 0;padding:.9rem 1.3rem;background:var(--panel);
  border-left:3px solid var(--accent);border-radius:0 4px 4px 0;color:var(--ink);
  max-width:var(--measure);font-size:.97em;box-shadow:0 1px 0 rgba(0,0,0,.02);}
blockquote p:last-child{margin-bottom:0;}
/* tables */
.tablewrap{overflow-x:auto;margin:1.4rem 0 1.8rem;border:1px solid var(--hair);
  border-radius:6px;background:var(--panel);}
table{border-collapse:collapse;width:100%;font-family:var(--sans);font-size:.82rem;
  font-variant-numeric:tabular-nums;line-height:1.4;}
thead th{text-align:left;background:color-mix(in srgb,var(--accent) 8%,var(--panel));
  color:var(--ink);font-weight:600;padding:.6rem .85rem;border-bottom:2px solid var(--accent-soft);
  white-space:nowrap;letter-spacing:.01em;}
tbody td{padding:.52rem .85rem;border-bottom:1px solid var(--hair);vertical-align:top;color:var(--ink-soft);}
tbody tr:last-child td{border-bottom:0;}
tbody tr:nth-child(even){background:color-mix(in srgb,var(--hair) 22%,transparent);}
td strong{color:var(--ink);}
/* semantic tint for same/different verdicts in data tables */
td:nth-child(2){color:var(--ink);}
/* footer */
.colophon{margin-top:4rem;padding-top:1.4rem;border-top:1px solid var(--hair);
  font-family:var(--sans);font-size:.78rem;color:var(--ink-soft);}
/* footnote markers + reference list */
sup.fn{line-height:0;font-size:.68em;font-variant-numeric:normal;}
sup.fn a{color:var(--accent);font-family:var(--sans);font-weight:600;border-bottom:0;padding:0 .05em;}
sup.fn a:hover{border-bottom:0;text-decoration:underline;}
:target{scroll-margin-top:1.5rem;}
li:target,sup.fn a:target{background:color-mix(in srgb,var(--accent) 16%,transparent);border-radius:3px;}
ol.footnotes{counter-reset:none;list-style:decimal;font-family:var(--sans);font-size:.82rem;
  line-height:1.5;color:var(--ink-soft);max-width:var(--measure);padding-left:1.6rem;
  margin-top:1.2rem;}
ol.footnotes li{margin:.55rem 0;padding-left:.25rem;}
ol.footnotes li::marker{color:var(--accent-soft);font-weight:600;}
ol.footnotes a{word-break:break-word;}
.fn-back{border-bottom:0;color:var(--accent-soft);font-family:var(--sans);margin-left:.15rem;}
.fn-back:hover{border-bottom:0;color:var(--accent);}
@media (max-width:640px){ body{font-size:16.5px;} .wrap{padding-left:1.1rem;padding-right:1.1rem;} }
@media (prefers-reduced-motion: no-preference){ a{transition:border-color .15s ease;} }
</style>
"""

MAST = """
<div class="wrap">
<header class="masthead">
  <p class="eyebrow">DeltaTrack &middot; Methodology Research &middot; Pass 1 of a multi-pass program</p>
</header>
"""

# The first H1 in the converted body becomes the title; keep it. Wrap the rest.
TITLE = "<title>Matching Provisions Across Bill Versions — DeltaTrack Pass 1</title>\n"

html_doc = (
    TITLE
    + STYLE
    + MAST
    + BODY
    + """
<footer class="colophon">
DeltaTrack version-diff research &middot; Pass 1, 2026-07-10 &middot; Every quantitative claim is
reproducible from the scripts in <code>docs/research/provision-matching/probes/</code>. Prepared for review and
expert check; methodology not yet settled.
</footer>
</div>
"""
)

OUT.write_text(html_doc)
print(f"wrote {OUT} ({len(html_doc)} bytes)")
# quick sanity: counts
print(
    "tables:",
    html_doc.count("<table>"),
    " h2:",
    html_doc.count("<h2>"),
    " blockquotes:",
    html_doc.count("<blockquote>"),
)
