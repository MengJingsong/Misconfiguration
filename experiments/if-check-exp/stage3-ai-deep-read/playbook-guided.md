# Stage 3 guided-agent playbook — how to run a deep-read pass

**This is the guided agent.** It gets the target plus the human suggestions in this
file: the three rules, the enforcement patterns and the test-design method. The
[autonomous agent](playbook-autonomous.md) gets the target only. Both write a case
file into `cases/` (this one as `<stem>--guided.md`, from `_TEMPLATE-guided.md`),
and stage 4 runs either file the same way. There is no isolation rule: this agent
may read an autonomous file when the user says so (section 1, step 1).

Practical technique. What stage 3 *is*, and where verdicts are filed, is in
[`README.md`](README.md). The three rules themselves are in
[`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case) and
are **not** restated here — one source of truth for the rules.

## 1. Before starting

1. **Ask the user** whether to read the autonomous agent's file for this case (or,
   for a batch, for each case in it). If yes, the user names the file in `cases/`;
   record it in §10 ("Autonomous reference"). If no, work from the target and this
   playbook alone. The answer is per case or per batch, never assumed.
2. Read [`../../../HANDOFF.md`](../../../HANDOFF.md), then `_INDEX.md` to
   see which cases exist and `predicted-negative.md` / `undetermined.md` to see which lines
   are already judged. **Don't re-judge a recorded line** — cite it.
3. Confirm the source is the pinned tag: the source is
   [`../../cassandra-5.0.9/`](../../cassandra-5.0.9/) in this repository;
   its `build.xml` `base.version` must read `5.0.9`, and
   `git status cassandra/cassandra-5.0.9` must show nothing changed.
4. Pick a feed (README's "two feeds"). For **3a**, take
   `../stage2-ai-preprocessing/bands.md` in band order — A first, then B,
   then C; within A, read A1 → A2 → A3.

## 2. Working a row

Order matters — each step can end the estimate early and save the next.

| # | Step | Ends early if |
|---|---|---|
| 1 | Open the line in the local source and confirm it still reads as the row claims | the row is stale or the operand was misparsed |
| 2 | Identify the **enforcement pattern** (§3.2): is this `if` itself the decision point (a), does it set a verdict read elsewhere (b), or is it a guard before an unbranched allocation (c)? | — all three are in scope (§7.5, revised 2026-09-25); the pattern sets how much tracing steps 3–5 need, not whether to continue |
| 3 | Rule 1 — which operand is the limit, and what is it? | neither side is a limit |
| 4 | Rule 2 — does the gated allocation create a memory- or disk-significant object? | it gates a thread, permit, count or index |
| 5 | Rule 3 — do the branches actually **diverge on object creation**? | both branches allocate |
| 6 | Trace the limit back to its first declaration — this names the constraint (Target 1) and fixes the §6.1 file name | — |
| 7 | **Design the test** stage 4 will run — §9 of the case file, per [`../README.md` §8](../README.md#8-designing-a-test-for-a-case): a **unit tier and a cluster tier**, or `n/a: <reason>` for a tier that cannot be done (section 2.2 below) | — |

Only after all seven does a case file get written, from `_TEMPLATE-guided.md`.

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
  `../stage2-ai-preprocessing/playbook.md`.

### 3.1 Lines that look like capacity checks but are not

Learned from the stage-3 passes over bands A1 to C (2026-09-22 to 2026-10-13;
moved here 2026-10-21 from `predicted-negative.md`, which now groups its
rejections by these patterns).

- **Ask where the limit's number comes from.** A comparison can be shaped like
  a capacity check, with an operand named `limit`, and still have no constraint
  on that side. If the number is the length of the data being read, it fails
  Rule 1 and the other rules need not be reached.
- **Per-item sanity bounds are the commonest false positive.** A byte count on
  each side and a config name on the limit, but the check refuses one item.
  Rule 2's test settles it: does changing the value move a maximum? Ask which
  value binds the total before judging.
- **Rollover is the second.** "The current buffer, file or segment is full,
  start another" is README §3.5's edge case; the caller's read settles it.
- **Path selection:** ask whether the disallow branch allocates the same bytes
  somewhere else. **Grow when full:** ask whether the item is stored on both
  branches. If so, the check sizes a structure; it does not limit one. A
  configurable growth factor sets slack, not a ceiling.
- **Invariant guards** throw when a pre-sized structure would overflow. The
  memory was spent at the sizing; if there is a limit, it is there.
- **Check the release path.** The same comparison as a filed case can sit in
  `releaseCapacity()` rather than the acquiring method.
- **Check that the class runs in production.** One grep for the constructor
  settles it before any rule is applied.
- **Stage 2's one-line reason can be wrong about the limit's kind.** Trust the
  row for where to look, never for what the limit is.
- **Disk admission checks are worth searching for:** callers of
  `DiskUsageMonitor`, `getAvailableSpace` and
  `hasDiskSpaceForCompactionsAndStreams`.
- **A ring buffer bounds by eviction, not by withholding**, and a count cap on
  entries of no fixed size fails Rule 2. A count cap on **held** rows of
  table-bounded size passes it (ruled 2026-10-21, README §3.5:
  `cached_rows_fail_threshold`).
- **A pool target with no admission check is a soft target.** If new objects
  are built at full size and a periodic job shrinks them toward the pool
  (`index_summary_capacity`), no comparison withholds creation: the
  constraint is real, but no single if-check qualifies.
- **A retention cap passes Rule 3.** Keeping or freeing a buffer is an effect on
  what stays resident (`DOB_MAX_RECYCLE_BYTES`).
- **A soft limit is a finding even when the line is rejected.** A flush or
  reclaim trigger is not a ceiling (`commitlog_total_space`), and a rejection
  can correct a filed case that called it one.
- **Stage 4 refuted 4 of the 6 negative estimates it ran (2026-10-20/21).**
  A count of concurrent tasks (`concurrent_compactors`), of connections
  (`native_transport_max_concurrent_connections`), a per-request bound
  (`native_transport_max_message_size`) and a time-based check
  (`native_transport_queue_max_item_age_threshold`) all capped memory after
  all: each limits how many items are admitted or held, and memory follows
  that count. Before rejecting a count, time or per-item check, ask how many
  bytes each admitted item holds.

## 4. Finishing

1. Write the case file from `_TEMPLATE-guided.md`, answering all nine questions
   in `../README.md` §5 — including §9's test design with both tiers (section 2.2).
   **Verify every `file:line` against the local source before filing** — a case is
   not filed until its citations are checked. Save it as `cases/<stem>--guided.md`.
2. Record the estimate and its ground, the autonomous reference (or `none`) and the feed (`3a` or
   `3b`) in §10.
3. **A line that fails a rule is still written up.** Record the estimate `negative`
   and the rule it failed as its ground, mark the sections that do not apply `n/a: <reason>`,
   and design §9 to test the opposite claim, that usage does **not** follow the
   constraint, so stage 4 can confirm or refute the estimate. Include the positive control and the extra conclusions rows described in `_TEMPLATE-guided.md` §9a. An undetermined line
   (not read against the rules) gets no case file and stays in
   [`undetermined.md`](undetermined.md).
4. Add the `_INDEX.md` Master Index row (Agent `guided`, Estimate, Ground) and, if the
   module is new, a Notes entry. For a negative estimate written up from an existing
   [`predicted-negative.md`](predicted-negative.md) entry, link the case file from that entry's
   reason; the entry is removed once the case is verified at stage 4. A line that **qualifies but you are not writing up now** →
   [`predicted-positive.md`](predicted-positive.md), never left only in stage 2's files.
5. If the feed was 3a, note the batch in
   `../stage2-ai-preprocessing/README.md`'s coverage table so the row is not
   re-read.
