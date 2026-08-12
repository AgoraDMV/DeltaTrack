# Region transcription task

You are shown one image. It is a crop of a printed page from a United States federal
appropriations document. Your job is to **transcribe and describe the headings printed in that
image**, and nothing else.

Answer only from what is visibly printed in the image. Do not infer, complete, correct or
normalise anything. If the image shows a typographic error, transcribe the error.

---

## What a heading is, for this task

A **heading** is a line, or part of a line, set apart from running body text by its printed
composition: it is centered, or set in capitals, or set in italic, or set in a distinctly
larger or heavier face, or otherwise typographically separated from the paragraphs around it.
Judge this **visually**, from composition alone.

Running body text, ordinary paragraphs, tables of figures, dollar amounts, and the small
numbers printed in the left margin are **not** headings.

---

## What to report

For the image, report **every heading occurrence you can see, in the order printed, top to
bottom**. For each one, six fields:

### 1. `text` — the exact printed text

Transcribe exactly as printed. **Preserve case** as set. Preserve internal spacing. Do not
expand abbreviations, do not fix spelling, do not add or remove punctuation, and do not
re-case a heading printed in capitals.

### 2. `role` — one label from this fixed list

| label | printed sense |
|---|---|
| `account` | a named spending account or appropriation heading |
| `agency` | a named agency, bureau, service, office or administration |
| `grouping` | a heading gathering several accounts or agencies under one label |
| `title` | a `TITLE` heading |
| `division` | a `DIVISION` heading |
| `section` | a numbered `SEC.` or section heading |
| `other` | a visible heading none of the above describes |

Choose the single best label. These labels describe **how the heading is composed and what it
names on the page**. The label is a judgement about printed composition only. Money printed in
the image is outside this task entirely and must not influence any answer.

### 3. `parent` — the immediate parent heading

The **exact printed text** of the nearest heading above this one that this heading sits under.

- If this heading has no parent, write `NONE`.
- If its parent is a heading that is **not visible in this image**, write `OFF_REGION`.

### 4. `start_physical_line` — which printed line it starts on

Count the printed lines of the image **from the top, starting at 1**. Report the number of the
line on which this heading's text **begins**. Count every line that carries printed matter;
do not count blank vertical space as a line.

### 5. `start_x_px` — where its first character begins

An **integer horizontal pixel coordinate**, measured from the **left edge of the image**, where
the left edge of the image is `0` and the coordinate increases to the right.

Mark the left edge of the **first character's own visible ink**.

- Ignore a strike-through, underline, border, rule, or other non-character mark crossing the
  character.
- Do **not** use a text-box or bounding-box edge. Mark the ink of the character itself.

`start_x_px` is used **only** to identify *which* occurrence on the page you are describing. It
is a position annotation. It is never read as evidence about the heading's text, its parent, or
its role, and those three are judged independently of it and of each other.

### 6. `unreadable` — anything you cannot resolve

If you cannot resolve a field, give the value `UNREADABLE` for that field and state the reason
in a `reason` note. Do not guess a value in order to fill the field.

---

## If the image contains no heading

Report an empty list. Reporting a heading that is not printed in the image is an error of the
same weight as missing one that is.

---

## Answer format

Return JSON only, with no commentary before or after:

```json
{
  "id": "<the id you were given, copied verbatim>",
  "headings": [
    {
      "text": "EXAMPLE-HEADING-TEXT-HERE",
      "role": "account",
      "parent": "EXAMPLE-PARENT-HEADING-HERE",
      "start_physical_line": 3,
      "start_x_px": 412
    }
  ],
  "notes": []
}
```

Put any `UNREADABLE` reason, or any observation you were unable to express in the fields, in
`notes`. `notes` never changes how a field is read.

---

## Rules

1. Answer **only** from the image in front of you.
2. Report every heading you see, and no heading you do not see.
3. Transcribe printed text exactly, including anything that looks like a mistake.
4. Judge `text`, `parent` and `role` independently. Do not let one adjust another.
5. Money printed in the image is outside this task. Leave every printed figure out of every
   field and out of `notes`.
6. How the image was produced, at what size, why it was selected, and what it may be used for
   are all outside this task. You have not been told, and a guess would be noise in the record.
7. Each image is judged on its own. Do not refer to any other image or to any earlier answer.
