# GPO bill render conventions

How the official GPO stylesheet renders legacy-DTD bill XML — the authoritative
rules for spacing, enum/header layout, casing, and front matter. We mirror these
in our XML render path so the full-bill view and diff match the published bill.

This is a **reference spec**, distilled from the stylesheet so we don't have to
run it. It backs issues #48 (front matter), #50 (title enum), #51 (spacing/lists),
#53 (casing), #58 (line numbers), #59 (quoted-block casing). Evaluation context: #40.

## What the GPO stylesheet is

Every bill in our corpus names its renderer in the XML prolog:

```
<!DOCTYPE bill PUBLIC "-//US Congress//DTDs/bill.dtd//EN" "bill.dtd">
<?xml-stylesheet type="text/xsl" href="billres.xsl"?>
```

This is the legacy **bill DTD** chain (not USLM). `billres.xsl` is a thin wrapper
that pulls in `billres-details.xsl` (~24.8k lines), the element-by-element render
templates. `table.xsl` handles tables; `bills.css` carries styling.

- **It is XSLT 2.0.** Python `lxml`/libxslt is 1.0 only and cannot run it; running
  it needs Saxon (server-side only — never ship a JVM to the staffer path).
- **It is display-faithful, not diff-tuned.** Our extractor deliberately
  suppresses formatting noise for diff stability; GPO does not. Keep the two
  concerns separate (see #51): one normalized string for matching, one readable
  string for display.

### Where to get it / re-fetching for future updates

Vendored under `reference/gpo-bill-render/` (gitignored; public domain, 17 U.S.C.
§105). Source: <https://www.govinfo.gov/bulkdata/BILLS/resources/>. Fetch the full
render chain (`billres.xsl`, `billres-details.xsl`, `table.xsl`, `bills.css`, the
DTDs, and image assets) so it stays render-complete. When GPO updates the
stylesheet, re-fetch and re-verify this doc — **citations below quote literal
snippets precisely so you can re-locate each rule by `grep` even if line numbers
shift.** Citations are `name (line) — "quote"`.

## How casing works: two layers

Casing is applied **twice** and you must read both to get the right answer:

1. **XSLT** — `convertToNeededCase` (`billres-details.xsl:8279`) transforms the
   text via `translate()` / `capitalizeReplacement` before it hits the DOM.
2. **CSS** — `text-transform` / `font-variant` on the element's class.

The **inline `<style>` block in `billres-details.xsl` overrides `bills.css`**
where they disagree (it loads later). Reading `bills.css` alone gives wrong
answers for several classes (see Gotchas). For our HTML output we can reproduce
GPO faithfully by applying the same CSS classes (`font-variant: small-caps` etc.)
rather than string-uppercasing.

---

## Front matter (#48)

`<form>` and the enacting clause, everything before the bill body.

- **`<form>` children render in a fixed, stage-dependent sequence — NOT document
  order.** `form` (`billres-details.xsl:3435`) is a large `xsl:choose` branching on
  document stage (introduced / reported / engrossed / enrolled / …). Common
  non-enrolled order: calendar (right-aligned) → congress/session → legis-num →
  action → `<hr>` → legis-type → official-title.
- **Enacting clause is GPO-injected boilerplate, not from `<enacting-clause>`.**
  Variable `$enact` (`billres-details.xsl:713`) — literal
  `" Be it enacted by the Senate and House of Representatives of the United States of America in Congress assembled, "` —
  rendered as `<em>` at the **top of `legis-body`**, suppressed when
  `legis-body/@display-enacting-clause = 'no-display-enacting-clause'`. Wire it to
  the legis-body render, not the form block.
- **`<legis-type>` ("AN ACT" / "A BILL"), `<congress>`, `<session>` render
  verbatim** for non-enrolled stages — no synthesis. (Only enrolled bills swap in
  images / boilerplate like "AT THE SECOND SESSION".)
- **`<distribution-code>` renders nothing** — `match="distribution-code"`
  (`billres-details.xsl:20863`) is an empty template. Drop it from front-matter text.
- **`<official-title>` renders verbatim**, no casing transform.

| Element | Source of text | GPO injects? | Notes |
|---|---|---|---|
| `distribution-code` | — | — | empty template; nothing renders |
| `calendar` | XML verbatim | no | right-aligned, first |
| `congress` / `session` | XML verbatim | no | small-caps (non-enrolled) |
| `legis-num` | XML verbatim | no | font size by string length |
| `legis-type` | XML verbatim | no | must already contain "AN ACT"/"A BILL" |
| `official-title` | XML verbatim | no | hanging indent, no transform |
| enacting clause | **stylesheet `$enact`** | **yes** | top of `legis-body`, not `<form>` |

---

## Structural hierarchy: enum + header (#50)

Each level injects a literal **wrapper word** before the enum and an **em-dash
`—`** before the header, rendered on one line. The header text is recased per the
casing table below.

| Level | Wrapper word | Sep. | Enum class / casing | Header casing | XSL |
|---|---|---|---|---|---|
| `<title>` | `TITLE ` | `—` | small-caps (`lbexTitleLevelTrad`) | UPPERCASE (`translate`) | `displayEnumTitle` (5540) — `"TITLE "` (5548) |
| `<subtitle>` | `subtitle ` | `—` | capitalize | title-case | enum 5707 |
| `<division>` | `DIVISION ` | `—` | uppercase | UPPERCASE | enum 18856 |
| `<part>` | `Part ` | `—` | small-caps | small-caps | enum 5790 |
| `<chapter>` | `chapter ` | `—` | uppercase | uppercase | enum 6016 |
| `<section>` | `Sec. ` | space | small-caps (`lbexInitialCapTrad`) | UPPERCASE | `displayEnumSection` (5319) — `"Sec. "` |

Output shape for a title: `TITLE I—AGRICULTURAL PROGRAMS` (no spaces flanking the
em-dash; both on one centered line via `BigHeads`, `billres-details.xsl:9337`).

> **Note for our parser:** we currently emit only the `<header>` for titles and
> drop the enum entirely (#50). Reconstruct `TITLE {enum}—{HEADER}`.

---

## Casing rules (#53)

Per-level — **not a blanket uppercase.** Authoritative source: `convertToNeededCase`
(`billres-details.xsl:8279`) plus the inline CSS at `billres-details.xsl:1361`.

| Level | XSLT transform | CSS | Visual result |
|---|---|---|---|
| `appropriations-major` header | `translate($lower,$upper)` → UPPER | `text-transform:uppercase` | ALL CAPS |
| `appropriations-intermediate` header | `capitalizeReplacement` → title-case | `font-variant:small-caps` | title-case shown in **small-caps** |
| `appropriations-small` header | `translate($upper,$lower)` → lower | `small-caps` + `text-transform:lowercase` | lowercase in small-caps |
| `<section>` enum | literal `Sec. ` | `small-caps` (`lbexInitialCapTrad`, 5319) | `Sec. 401` shown as small-caps "SEC. 401" |
| `<title>` header | `translate($lower,$upper)` → UPPER | — | ALL CAPS |
| `<short-title>`, `<official-title>` | none | none | **verbatim — do not transform** |

`convertToNeededCase` (`billres-details.xsl:8279`):
```
<xsl:when test="ancestor::appropriations-major">
  ... header → translate($theActualTextToPrint, $lower, $upper) ...
<xsl:when test="ancestor::appropriations-intermediate">
  ... header → capitalizeReplacement ...
<xsl:when test="ancestor::appropriations-small">
  translate($theActualTextToPrint, $upper, $lower)
```

### Rationale & the trap that bit #53

The source XML stores intermediate/section headers in **sentence case** ("Office
of the secretary", `Sec. 401`). GPO does **not** uppercase them — it title-cases
(intermediate) or leaves them (section) and renders with `font-variant: small-caps`,
which *displays* lowercase letters as small capitals. To the eye that reads as
"ALL CAPS," but the underlying text is not uppercase.

Our **PDF path reads real capitals**, because PDF text extraction flattens
small-caps glyphs to actual uppercase. So:

- **Do not** "fix" the XML path by uppercasing the literal strings (the original
  #53 acceptance said `Sec. 401 → SEC. 401` — that was wrong). Apply GPO's CSS
  classes instead.
- **Parity caveat:** after this, PDF (real caps) and XML (title/sentence case in
  small-caps) hold *different underlying text* that matches only visually. Fine for
  diff-matching (already case-normalized); flag it so it isn't mistaken for a bug.

---

## Inline spacing & lists (#51)

- **One ASCII space after every `<enum>`** when the next sibling is `<text>` or
  `<header>`. `displayEnum` (`billres-details.xsl:5069`):
  ```
  <xsl:when test="local-name(following-sibling::*[1]) = 'text' or local-name(following-sibling::*[1]) = 'header'">
      <xsl:text> </xsl:text>
  ```
  This is authoritative — `(a)The` is a real defect; it should be `(a) The`.
- **Each structural level is its own block on its own line**, indented by a fixed
  ladder (`bills.css:513`+, all `text-indent:2em` hanging):

  | Level | `margin-left` |
  |---|---|
  | subsection | 0em |
  | paragraph | 2em |
  | subparagraph | 4em |
  | clause | 6em |
  | subclause | 8em |
  | item | 10em |
  | subitem | 12em |

  This is why list items appear on their own lines — block structure, not line-break
  tags.
- **`<linebreak>` / `<pagebreak>` are no-ops** in the renderer — they apply children
  (usually empty) and emit nothing. `billres-details.xsl:18461` / `:18464`:
  ```
  <xsl:template match="linebreak"><xsl:apply-templates/></xsl:template>
  <xsl:template match="pagebreak"><xsl:apply-templates/></xsl:template>
  ```
  Our "treat as whitespace" handling is consistent — no change needed.
- **Exception:** elements with `@display-inline='yes-display-inline'` render inline
  (no wrapping block) — for continuation runs.

---

## Quoted text casing (#59)

`<quote>` and `<quoted-block>` have **no dedicated casing class** — they inherit
from their container. Inside an `appropriations-major` block (`text-transform:
uppercase`) quoted text is uppercased by inheritance; inside an intermediate block
it's small-caps. If #53 adopts GPO's container-casing CSS verbatim, quoted text
nested in a cased header can be unintentionally re-cased. Decide deliberately:
scope the transform to the heading text, or mirror GPO's inheritance. Add a fixture
covering a quoted block inside a cased header.

---

## Not produced by the stylesheet

- **Line numbers (#58).** No `xsl:number`, `counter()`, `@line`, or line-number
  logic anywhere in `billres-details.xsl` / `bills.css`. The 1–25 line numbers in
  published bills are a downstream **print-composition artifact** (XSL-FO /
  proprietary typesetting), not part of the HTML render chain, and the bill XML
  carries no `@line` attributes. An XML/full-bill line-number column would have to
  be **synthesized** by us and would not match the PDF's print line breaks. PDF
  line numbers come only from the PDF itself.

---

## Gotchas (verified surprises)

1. **`bills.css` lies about three approp classes** — the inline XSLT style wins:
   `lbexHeaderAppropSmall` is `uppercase` in `bills.css` but **`lowercase`** inline;
   `lbexHeaderAppropIntermediate` has no transform in `bills.css` but **`capitalize`**
   inline. Always read the inline block (`billres-details.xsl:1361`+).
2. **"Sec." vs "SEC." is small-caps, not real caps** — see #53 rationale. The same
   applies to the title wrapper word.
3. **`appropriations-small` is lowercased then small-capped** — XSLT forces
   lowercase so CSS is the sole case authority.
4. **Enacting clause belongs to `legis-body`, not `form`** — and its text is the
   stylesheet's, not the XML's.
5. **`subtitle` wrapper is lowercase `subtitle `** + `capitalize` CSS — "SUBTITLE"
   in a published bill is the CSS transform, not a hardcoded string.
6. **`<part>` / `<section>` header classes have `capitalize` explicitly commented
   out** — they rely on `small-caps` over whatever case the XML provides.

---

## Re-verification

After re-fetching the stylesheet (or to audit this doc): for each rule, `grep` the
quoted snippet or template name in `reference/gpo-bill-render/billres-details.xsl`
(or `bills.css`) and confirm the line + behavior still hold. The literal quotes are
the stable anchors; line numbers are a convenience that may drift.
