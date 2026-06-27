# 8. Deterministic Diff Engine

- Status: Accepted
- Date: 2026-06-27

## Context

A staffer uses a DeltaTrack diff to make decisions that carry weight: briefing a
member, drafting report language, tracking a dollar amount through a bill. For that,
the diff has to be a record they can stand behind. Two properties make it one:

- **Reproducible** — the same two versions always produce the exact same diff. Run
  it today and next month, on this machine or a colleague's, and the result is
  identical.
- **Auditable** — every change the tool reports can be traced to a definite rule,
  not a judgment call that might come out differently next time.

The pressure to add a language model is real, because the hardest part of diffing a
bill is *matching*: deciding that a renumbered or reordered paragraph in the new
version corresponds to one in the old (see DeltaTrack #87 on reordered lists, #56 on
similarity thresholds). Models are good at that kind of fuzzy correspondence, so
"just have an LLM line them up" is a tempting shortcut.

We are not opposed to LLMs. The outputs support and *encourage* LLM use: the
report ships ready-made questions a staffer can paste into their own assistant
alongside the diff (`formatters/diff_html.py`), and BillTrax, the analysis product,
uses LLMs by design ([0005](0005-deltatrack-billtrax-boundary.md)). So "no LLM"
cannot be a blanket ban. It needs a precise line.

## Decision

We will keep the diff engine **deterministic**: the path from two bill versions to a
finished diff runs entirely on fixed rules (structured money matching,
[0001](0001-structured-money-diff.md); text alignment; PDF text extraction,
[0002](0002-pdfium-single-engine.md)). No language model, and no network or API key,
takes part in producing a diff. The same inputs always yield byte-identical output.

The line is about *direction*: a language model may **read** a finished diff, but
never **compute** one.

- Downstream of the diff, LLM use is welcome and even helped along: the staffer's own
  assistant can consume the diff (the canonical JSON, [0006](0006-canonical-diff-contract.md),
  plus the ready-made questions in the report), and BillTrax builds LLM analysis on
  top of DeltaTrack's output ([0005](0005-deltatrack-billtrax-boundary.md)).
- Inside the engine, the matching and money problems are solved with deterministic
  heuristics, even where a model might score better on fuzzy cases.

This constrains the *runtime* path to a result. Using a model offline as a
development aid — for example to help tune a threshold or explore test cases — does
not touch what ships, because nothing the model does ends up in the engine that runs
on a staffer's machine.

Alternatives:

- **Let an LLM do the matching inside the engine.** Rejected. It would likely
  improve the fuzzy cases, but at the cost of the two properties the use case cannot
  give up: a model's output is not guaranteed identical on a re-run and cannot be
  traced to a fixed rule, so the diff stops being reproducible and auditable. It
  would also pull in a network call or a bundled model, breaking the offline,
  no-install, no-key operation the staffer audience depends on
  ([0005](0005-deltatrack-billtrax-boundary.md)). The matching problem is real, but
  it is being solved with deterministic heuristics (#56), not by trading away
  reproducibility.

## Consequences

- The diff can serve as a record: reproducible and auditable, the same for every
  user every time.
- Reproducibility is what lets the test corpus act as ground truth — a fixed input
  has one correct output to assert against, which would be impossible with a
  nondeterministic engine. This underpins the validation approach.
- The accepted cost: the hard matching cases (reordered or renumbered text, near-
  duplicate sections) must be handled with deterministic heuristics, which is more
  work and will not always match what a model could do on a one-off basis. We take
  that trade deliberately; #56 and #87 are where it is paid.
- The offline, no-key safety contract is preserved, because the engine needs neither
  a network nor a model to run.
- The downstream-LLM use case is explicitly in scope, not a loophole: handing the
  diff to an assistant is a supported workflow precisely because the diff itself was
  produced without one. The determinism is what makes the artifact trustworthy enough
  to feed an LLM in the first place.
