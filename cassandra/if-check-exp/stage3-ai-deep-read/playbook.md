# Stage 3 playbook — how to run a deep-read pass

Practical technique. What stage 3 *is*, and where verdicts are filed, is in
[`README.md`](README.md). The three rules themselves are in
[`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case) and
are **not** restated here — one source of truth for the rules.

## Before starting

1. Read [`../../../HANDOFF.md`](../../../HANDOFF.md), then `_INDEX.md` to
   see which cases exist and `rejected.md` / `deferred.md` to see which lines
   are already judged. **Don't re-judge a recorded line** — cite it.
2. Confirm the source clone is at the pinned tag:
   `cd /proj/misconfiguration-PG0/git-repos/cassandra-src && git describe --tags`
   must print `cassandra-5.0.9`.
3. Pick a feed (README's "two feeds"). For **3a**, take
   `../stage2-ai-preprocessing/bands.md` in band order — A first, then B,
   then C; within A, read A1 → A2 → A3.

## Working a row

Order matters — each step can end the judgment early and save the next.

| # | Step | Ends early if |
|---|---|---|
| 1 | Open the line in the local clone and confirm it still reads as the row claims | the row is stale or the operand was misparsed |
| 2 | Identify the **enforcement pattern** (§3.2): is this `if` itself the decision point (a), does it set a verdict read elsewhere (b), or is it a guard before an unbranched allocation (c)? | it is (b) or (c) → `deferred.md`, under the §7.5 scope |
| 3 | Rule 1 — which operand is the limit, and what is it? | neither side is a limit |
| 4 | Rule 2 — does the gated allocation create a memory- or disk-significant object? | it gates a thread, permit, count or index |
| 5 | Rule 3 — do the branches actually **diverge on object creation**? | both branches allocate |
| 6 | Trace the limit back to its first declaration — this names the constraint (Target 1) and fixes the §6.1 file name | — |

Only after all six does a case file get written, from `_TEMPLATE.md`.

## Pitfalls, verified

- **Don't assume the disallow branch rejects anything.** Trace its real
  effect first: it may reject, throw, block and wait, defer, or be bypassed
  further down the call chain. Several filed cases park the caller rather
  than refuse it, and one overshoots the limit entirely via an escape hatch.
- **Non-domination.** A guard can exist and still not control the
  allocation — check whether the allocation is reachable on a path that
  skips the guard. One compaction case has a disk guard that the default
  code path never executes.
- **Check whether the limit is global or scoped** before believing a case is
  about total memory: a per-connection or per-file cap bounds one object's
  share, not the node's ceiling.
- **The row never decides.** Stage 2's rendering (`... + ...`) hides the real
  operands; two of the four known true positives look almost contentless as
  rows. Always read the source.
- **Config name ≠ operand name.** `limit`, `queueCapacity`,
  `MAX_ALLOCATED_BUFFERS` are check-site names; the constraint name comes
  from tracing back to the declaration (step 6). Joining operand names
  against `Config.java` does not work — tried and refuted, see
  `../stage2-ai-preprocessing/playbook.md`.

## Finishing

1. Write the case file from `_TEMPLATE.md`, answering all eight questions
   in `../README.md` §5. **Verify every `file:line` against the local clone
   before filing** — a case is not filed until its citations are checked.
2. Record the feed (`3a` or `3b`) in the case's Notes.
3. Add the `_INDEX.md` Master Index row and, if the module is new, a Notes
   entry.
4. Refused lines → [`rejected.md`](rejected.md); pattern-(b)/(c) lines →
   [`deferred.md`](deferred.md). Both cite the ground. A line that
   **qualifies but you are not writing up now** → [`pending.md`](pending.md),
   never left only in stage 2's files.
5. If the feed was 3a, note the batch in
   `../stage2-ai-preprocessing/README.md`'s coverage table so the row is not
   re-read.
