# Issue analysis template

A fill-in skeleton for issues written from inside the codebase: a defect you found
while working, a gate that can't fail, a contract that's being violated, a piece of
work you've already analyzed.

This is **not** one of the templates in `.github/ISSUE_TEMPLATE/`. Those are for people
filing through the GitHub web UI, and the chooser deliberately stays short. This file is
for the team and for AI assistants filing from the command line, where
`gh issue create --body-file` bypasses the chooser entirely (see "Filing from the command
line" in [CONTRIBUTING.md](../CONTRIBUTING.md)).

Copy the skeleton, fill it, delete what doesn't apply, and file it with an explicit
`--type`. Sections marked optional are genuinely optional. A short issue that follows the
shape beats a long one that doesn't.

## Why this shape

An issue is read by people who weren't there when you found the problem: a teammate
triaging next month, a newcomer picking up their first issue, you in six weeks. Three
failure modes account for most unreadable issues, and the skeleton is built to prevent
each one.

- **Starting from the artifact.** Opening with a test node ID or a function name puts the
  evidence before the problem, so a reader has to reconstruct what's wrong from what you
  looked at. State the observable behavior first.
- **Bare cross-references.** `see #141` makes the number do the explaining, and a reader
  without that tab open loses the thread. Describe every reference inline.
- **Fusing the defect with its discovery.** "What's wrong" and "how I found it" are
  different claims. Merged, they read as lab notes: a story about your afternoon rather
  than a statement about the code.

---

## Skeleton

```markdown
**What's wrong**

<!-- First sentence assumes no knowledge of this codebase: state the observable
     wrong behavior before naming any file, test, or function. Someone without the
     repo open should finish it knowing what's broken and why they'd care.

     Then the supporting detail. Define project terms on first use ("anchors", the
     line-number markers the PDF parser uses to locate where a section starts).
     Describe cross-references inline: #141 (enrolled PDFs yield no anchors), not a
     bare #141. Same for decision records: ADR 0009 (validation ground truth). -->

**How it surfaced**

<!-- What you were doing, and the evidence. Paste real output, not a reconstruction
     of it. Keep it to the lines that matter. -->

**Why it matters**

<!-- Consequence: what breaks, for whom, and how urgently. Say if something is
     currently masking it, and whether pending work would make it worse. Don't
     assume it's obvious; the person triaging this has less context than you. -->

**What to do** <!-- optional -->

<!-- Directions with tradeoffs, or "unknown, needs investigation." Prefer options
     over one prescribed fix unless it's genuinely settled: an issue is where the
     decision gets made, not where it gets announced. Measurements comparing
     options are welcome and beat advocacy. -->

**Verification** <!-- optional -->

<!-- Fill this in when "the suite still passes" is not proof of a fix. For a
     fail-open defect it never is, because it passed before, which is the problem.
     Name the known-bad case the fix must be shown to catch. -->

**Unverified** <!-- optional -->

<!-- Anything you suspect but did not test, labeled plainly as such. Worth writing
     down; not worth presenting as established. -->

Refs #<n>, #<n>
```

## Evidence

An issue is a claim about the state of the code, and someone will act on it.

- **Only state results you actually ran.** Never quote a test result, count, coverage
  number, or benchmark from memory or from what a command "would" print. Run it or say
  it's unrun.
- **Scope results to what you ran them on.** A result belongs to one branch and commit.
  Say which if it could matter.
- **Say what you didn't check.** The boundary of the investigation is information.

## Other genres

The same shape trims down for work that isn't a defect. Keep the first-sentence rule and
self-describing references in all cases; those are what make an issue readable.

| Filing | Use |
|---|---|
| **Defect** | The full skeleton. |
| **Task / chore** | *What's wrong* becomes what needs doing; *why it matters* becomes what it unblocks. Drop the rest. |
| **Feature** | *What's wrong* becomes the problem and who has it; *what to do* becomes the proposed shape. Drop verification. |
| **Epic** | Problem and why, plus the decomposition. Sub-issues carry their own analysis. |

Don't add acceptance criteria, scope, priority, or sizing. Those get set during grooming
(see "Grooming an issue for pickup" in [CONTRIBUTING.md](../CONTRIBUTING.md)), and a filer
who guesses at them creates work to undo.
