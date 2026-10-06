# Stage 3 long-path playbook — how to run a deep-read pass

**This is the long path.** The short path ([`../short-path/README.md`](../short-path/README.md))
does not use this playbook, the three rules or the case template, and its isolated
writer cannot see them. The long path goes first and has no isolation rule.

Practical technique. What stage 3 *is*, and where verdicts are filed, is in
[`README.md`](README.md). The three rules themselves are in
[`../../README.md` §3.4–§3.6](../../README.md#3-core-concept-the-if-check-case) and
are **not** restated here — one source of truth for the rules.

## 1. Before starting

1. Read [`../../../../HANDOFF.md`](../../../../HANDOFF.md), then `_INDEX.md` to
   see which cases exist and `rejected.md` / `deferred.md` to see which lines
   are already judged. **Don't re-judge a recorded line** — cite it.
2. Confirm the source clone is at the pinned tag: `git -C <clone> describe --tags`
   must print `cassandra-5.0.9`. The clone is `$CASSANDRA_SRC`, else `cassandra-src`
   next to this repository (for example `~/repos/cassandra-src`), else
   `/proj/misconfiguration-PG0/git-repos/cassandra-src` on CloudLab.
3. Pick a feed (README's "two feeds"). For **3a**, take
   `../../stage2-ai-preprocessing/bands.md` in band order — A first, then B,
   then C; within A, read A1 → A2 → A3.

## 2. Working a row

Order matters — each step can end the judgment early and save the next.

| # | Step | Ends early if |
|---|---|---|
| 1 | Open the line in the local clone and confirm it still reads as the row claims | the row is stale or the operand was misparsed |
| 2 | Identify the **enforcement pattern** (§3.2): is this `if` itself the decision point (a), does it set a verdict read elsewhere (b), or is it a guard before an unbranched allocation (c)? | — all three are in scope (§7.5, revised 2026-09-25); the pattern sets how much tracing steps 3–5 need, not whether to continue |
| 3 | Rule 1 — which operand is the limit, and what is it? | neither side is a limit |
| 4 | Rule 2 — does the gated allocation create a memory- or disk-significant object? | it gates a thread, permit, count or index |
| 5 | Rule 3 — do the branches actually **diverge on object creation**? | both branches allocate |
| 6 | Trace the limit back to its first declaration — this names the constraint (Target 1) and fixes the §6.1 file name | — |
| 7 | **Design the test** stage 4 will run — §9 of the case file, per [`../../README.md` §8](../../README.md#8-designing-a-test-for-a-case): a **unit tier and a cluster tier**, or `n/a: <reason>` for a tier that cannot be done (section 2.2 below) | — |

Only after all seven does a case file get written, from `_TEMPLATE.md`.

### 2.1 Under (b) and (c)

Steps 3–5 cost more. Rule 3 under (b) needs the
verdict's path traced to whoever reads it; under (c) it needs domination
checked across every caller that reaches the allocation. Non-domination is a
**finding to record**, not grounds for rejection — the compaction case's guard
does not dominate, and that is its most useful result.

### 2.2 Step 7 in detail: the two tiers (new cases)

A new case's §9 designs **both** tiers (the 11 cases filed earlier have all been
converted to it; see [`README.md`](README.md) §2.3):

- **Unit tier:** construct or drive the check's classes directly in a JVM test
  built from the tree; measure the check's own usage-side operand. Look in
  `test/unit/...` for existing coverage of the class first and extend it rather
  than writing a harness from scratch. It proves the mechanism.
- **Cluster tier:** a real node with the knob at the boundary and a workload
  through the normal client path; measure the actual resource (heap, off-heap or
  disk), not process RSS. It proves the dose-response claim.

Each tier gets its own setup (9b), workload (9c), observables (9d), prediction and
conclusions rows (9a), and scenario steps (9e). If a tier cannot be done (the knob
is a hard-coded constant, nothing can be driven without a node, the operand is
unreachable), keep its place in §9 as `n/a: <reason>` and say what answers the
same question instead; do not delete the tier silently. Record the case's
Testability in 9a either way.

## 3. Pitfalls, verified

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
- **Instrument the operand, not the process.** When designing §9, the thing to
  measure is the usage-side operand the check compares — not process RSS,
  which `-Xms` pre-commits and GC timing masks. The operand is often not
  exposed: there is no `MemtablePool` gauge in the metrics package, so the
  memtable cases can only be watched through per-table proxies. Name the gap
  in §9 rather than passing a proxy off as the measurement.
- **A per-object limit needs a multiplier before it says anything about the
  node.** A 4MiB per-connection cap moves node-wide usage by `limit × N`. A
  §9 design that varies the limit but not N, or lets N drift, measures
  nothing.
- **A constraint that fails to govern usage is a result.** Two filed cases
  predict exactly that (the `markBlocking()` overshoot, the skipped disk
  guard). Predict both curves in §9a (§9d in the old layout), or stage 4 cannot tell a real bypass
  from experimental noise.
- **Config name ≠ operand name.** `limit`, `queueCapacity`,
  `MAX_ALLOCATED_BUFFERS` are check-site names; the constraint name comes
  from tracing back to the declaration (step 6). Joining operand names
  against `Config.java` does not work — tried and refuted, see
  `../../stage2-ai-preprocessing/playbook.md`.

## 4. Finishing

1. Write the case file from `_TEMPLATE.md`, answering all nine questions
   in `../../README.md` §5 — including §9's test design with both tiers (section 2.2). **Verify every `file:line` against the local clone
   before filing** — a case is not filed until its citations are checked.
2. Record the feed (`3a` or `3b`) in the case's Notes.
3. Add the `_INDEX.md` Master Index row and, if the module is new, a Notes
   entry.
4. Refused lines → [`rejected.md`](rejected.md). [`deferred.md`](deferred.md)
   is no longer where (b)/(c) go — all three patterns are judged now (§7.5);
   it holds its remaining entries as a worklist. Both cite the ground. A line that
   **qualifies but you are not writing up now** → [`pending.md`](pending.md),
   never left only in stage 2's files.
5. If the feed was 3a, note the batch in
   `../../stage2-ai-preprocessing/README.md`'s coverage table so the row is not
   re-read.
