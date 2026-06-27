# 5. Keep DeltaTrack a contained two-version tool; put analysis in BillTrax

- Status: Accepted
- Date: 2026-06-27

## Context

Two products share the same problem space. DeltaTrack compares two versions of a
bill. BillTrax analyzes bills and their diffs. They are easy to confuse, and that
confusion produces a recurring question: where does a given feature belong? The
pressure usually arrives as "let's also support more than two versions," "let's
track a bill across its whole lifecycle," or "let's add local files and storage so
the user doesn't redo work each time."

DeltaTrack's audience is congressional staffers working under strict IT rules,
often offline. For that audience, one property of the tool is doing a lot of quiet
work: it runs locally, modifies nothing on the user's machine, stores nothing, and
leaves nothing behind. "This tool touches nothing and is safe to run" is not a
nicety; it is part of why a staffer can use it at all.

Without an explicit boundary, every new request gets relitigated from scratch, and
each "just add storage" suggestion quietly erodes the property above. This record
draws the line and says why.

## Decision

We will keep **DeltaTrack** the ephemeral, local tool that compares **two**
versions of a bill. Its principles are simplicity, accuracy, speed, offline
operation, and a safety contract: it does not write to the user's files, does not
persist data, and stays self-contained. The user provides the two versions; the
tool produces a self-contained report and keeps no state. DeltaTrack also serves as
**BillTrax's** diff engine, but that is a by-product of being a clean, trustworthy
engine, not its main purpose. DeltaTrack stands on its own as a staffer tool first.

We will keep **BillTrax** the analysis product. It has storage, automation, and
access to LLMs, and it owns everything that spans more than a single two-version 
comparison: multi-version and full-lifecycle tracking, comparison over time, and 
trends across many bills. BillTrax consumes DeltaTrack's diffs (the canonical 
JSON contract, see [0006](0006-canonical-diff-contract.md)) and builds on them.

The test for where a feature belongs is not processing power. It is whether the
feature needs **persistent state or automated input gathering**. If it does, it is
BillTrax's. Three reasons hold the line, in order of weight:

1. **The safety contract.** No persistence and no file writes is a security
   property the staffer audience relies on. Adding storage or local-file support
   breaks it, and a DeltaTrack that breaks it is no longer DeltaTrack.
2. **Input burden.** Because the tool is ephemeral, the user hand-provides the
   inputs. Two versions is reasonable to ask for; five versions, or a bill's full
   lifecycle, forces the user to gather, upload, and manage every version and every
   pairwise comparison by hand. Removing that burden requires the storage and
   automation DeltaTrack deliberately lacks.
3. **Focus.** Speed and accuracy on the two-version case are easier to guarantee in
   a tool that does only that.

Alternatives:

- **Add storage and local-file support to DeltaTrack** so users do not redo work
  each session. Rejected: it breaks the safety contract above, which is the core
  reason the staffer audience can run the tool. The need it addresses is real, but
  it is BillTrax's need.
- **Fold both into one product.** Rejected as a scope decision: a contained,
  zero-persistence tool and a stored analysis platform have incompatible core
  contracts, so one set of responsibilities cannot be both. (Whether the two are
  ever *packaged* together — for example as layers in one codebase — is a separate,
  still-open question. Even layered, the DeltaTrack layer keeps this contract.)

## Consequences

- Every "where does this go?" question now has a default answer: if it needs
  persistent state or automated input gathering, it is BillTrax's. Settled questions
  stop being reopened per feature.
- DeltaTrack's offline, self-contained design (and the self-contained HTML report
  and canonical-JSON handoff in [0006](0006-canonical-diff-contract.md)) is justified
  rather than incidental — it is the safety contract expressed in the architecture.
- The accepted cost: in DeltaTrack the user redoes setup each session, because **the
  tool remembers nothing.** That repetition is the price of the safety contract, not a
  defect to fix by adding storage.
- N-way comparison, which the schema notes as a possible v2.0 change, is unlikely to
  be DeltaTrack's job; cross-version work points to BillTrax. This record does not
  decide the format question, only where the responsibility sits.
- The scope is not frozen forever. DeltaTrack may expand, but only on demonstrated
  user demand, and never into territory that requires persistent state or otherwise
  breaks the safety contract. That demand, not internal convenience, is the trigger
  to revisit.
