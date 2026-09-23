# Positives — rows stage 2 passes forward, with priority

Rows that stage 2 did **not** rule out, ranked by how promising the row looks.
This is a **work queue for stage 3**, not a list of qualified
cases: stage 2 works only from the row and never applies the three rules (see
[`README.md`](README.md)). A row here means "worth reading the source for,
in roughly this order" — nothing more.

Tiers (defined in [`playbook.md`](playbook.md)):

| Tier | Meaning |
|---|---|
| **P1** | Capacity-shaped name on one side **and** a compound usage side (`... + ...`) — the `current + requested vs limit` shape. Rare; read first. |
| **P2** | Capacity-shaped name on one side. |
| **P3** | Named operands on both sides, no capacity vocabulary — the long tail that the folder's rules deliberately refuse to exclude by keyword. |
| **P4** | Survived fast-reject but looks mechanical; parked at the bottom rather than refused. |

An entry moves to **Promoted** once a case file exists for it.

## Live candidates

## Current queue state

Tier membership is **computed from the stage-1 CSVs**, not enumerated here —
the filter is in [`playbook.md`](playbook.md) and reproduces exactly. This
section records only where the queue has got to.

| Tier | Rows (work-ahead scope) | State |
|---|---|---|
| **P1** | 34 | ✅ read by stage 3, 2026-09-22 |
| **P2** (excl. P1) | 337 | next, after the lexical re-rank |
| **P3** | 746 | pending — the insurance tier |
| **P4** | 1,337 | parked, not refused |

See [`README.md`](README.md)'s "Progress at a glance" for the full corpus and
remaining counts, and its coverage table for which batches are done.

## Where a row goes after stage 3 reads it

Stage 2 hands a row forward; what happens next is recorded by **stage 3**,
not here (verdicts file with the stage that judged them):

| Outcome | Recorded in |
|---|---|
| Qualified, written up | [`../stage3-ai-deep-read/cases/`](../stage3-ai-deep-read/cases/) + [`_INDEX.md`](../stage3-ai-deep-read/_INDEX.md) |
| Qualified, not yet written up | [`../stage3-ai-deep-read/pending.md`](../stage3-ai-deep-read/pending.md) |
| Refused against the three rules | [`../stage3-ai-deep-read/rejected.md`](../stage3-ai-deep-read/rejected.md) |
| Pattern (b)/(c), parked | [`../stage3-ai-deep-read/deferred.md`](../stage3-ai-deep-read/deferred.md) |

**Nothing in this file is a finding.** The P1 pass's outcomes — 4 qualified
candidates, 22 refusals, 3 deferrals — were recorded here until 2026-09-23
and now live in the stage-3 files above.
