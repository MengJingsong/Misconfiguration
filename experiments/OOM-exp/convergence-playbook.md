# Convergence playbook (Direction 1)

> **Paths (multi-system layout).** This is a system-agnostic method doc. The per-system files it
> names (`_INDEX.md`, `cases/...`) live under `experiments/OOM-exp/<system>/` (for Cassandra,
> `cassandra/`). Paths into `if-check-exp` follow that experiment's layout: method docs at its
> root, data under `if-check-exp/<system>/`.

**This is the agent's whole instruction for a convergence run.** Give an
agent this file, read access to [`if-check-exp`](../if-check-exp/README.md)
(its case files and stage-4 results are the input; this experiment does not
re-derive them), and a copy of the Cassandra source at tag `cassandra-5.0.9`
built on a node you own. The agent does the whole job itself: **it picks
which constraints to combine, designs the test, runs it, and files the
result** — there is no separate design-then-execute split here (unlike
if-check-exp stage 3/4). Run it as a Claude Code session on the node, or on a
node it can reach, so it can build, start Cassandra, drive load and read
`dmesg`/heap output directly.

## Produces: multiple convergence cases, one agent run

**One playbook run produces a batch of convergence cases, not one.** Each
case is one specific combination of constraints, with its own design and its
own execution result. Work through combinations until either:

- a stopping budget is reached (number of combinations tried, or wall-clock
  time given), or
- the agent judges the remaining plausible combinations are exhausted for the
  shared budgets available (see "Picking combinations" below).

State at the top of the batch log how many combinations were attempted and
how many are filed as cases. A combination that was considered but rejected
before building (because it clearly can't reach the budget, or duplicates an
already-filed shared-budget group) does not need a full case file — note it
in the batch log instead; only combinations that were actually sized and run
get a case file.

## The goal, per case

Find **two or more** constraints from `if-check-exp` whose capacities draw on
the same memory budget (heap, off-heap/direct memory, or a shared pool, on
one node), such that:

- each one, pushed to its own capacity alone, leaves the node with a safe
  margin of free memory;
- pushed to their capacities **together**, in the same window, the sum
  exceeds what the node has and the node OOMs (the JVM throws
  `OutOfMemoryError`, is OOM-killed by the kernel, or Cassandra stops serving
  because GC cannot reclaim enough).

## Inputs from if-check-exp

For each candidate constraint, pull from its case file and stage-4 results
(`if-check-exp/cassandra/stage3-ai-deep-read/cases/`, `if-check-exp/cassandra/stage4-runtime-verification/results/`):

1. **The capacity check** — `file:line`, and what it compares.
2. **The constraint** — how its value is set (config/non-config), its default,
   and whether it can be raised or lowered without a build.
3. **What it caps** — heap, off-heap/direct memory, or disk, and roughly how
   many bytes at capacity.
4. **The outcome class** — prefer **true positive** (confirmed: it caps usage) or
   a confirmed **bypass**. Do not build a convergence case on a constraint the
   case file found does not cap (true negative) — if it never reached capacity
   on its own, driving it to "capacity" is not a load.
5. **Standing pool, not a per-request guardrail.** A true positive only
   qualifies if its usage is a **standing pool** — bytes that accumulate and
   can sit *at* capacity for a sustained window (a cache, a queue, a
   memtable, a disk directory total). A **per-request/per-item guardrail**
   (a size check on one mutation, one query response, one message, one
   batch) rejects or passes a single operation and releases the memory
   immediately — there is no window where it's "parked at capacity" for a
   second constraint to converge with, even though the bytes it touches are
   genuinely heap or off-heap. Exclude guardrails from convergence picking
   regardless of outcome class (examples: `max_mutation_size`,
   `max_value_size`, `tombstone_failure_threshold`, the
   `*_read_size_fail_threshold` family — see
   [`cassandra/cases/convergence/_constraint-groups.md`](cassandra/cases/convergence/_constraint-groups.md)'s
   "Not a shared budget" section for the full list and why each was excluded).

A standing survey of every true-positive constraint, grouped by budget and
already filtered for standing-pool vs. guardrail, lives at
[`cassandra/cases/convergence/_constraint-groups.md`](cassandra/cases/convergence/_constraint-groups.md).
Check it before re-deriving a group from scratch — it also flags
look-alike traps (e.g. several off-heap networking constraints that turn
out to share the exact same underlying pool, so combining two of them is
not a genuine 2-way combination). Keep it updated when a future survey
finds more true positives or corrects a classification.

## Picking combinations (the agent's job)

The agent chooses which constraints go into each case. There is no fixed
list to work down — survey if-check-exp's true-positive and confirmed-bypass
cases itself and group them.

**Before picking, read the "Shared-budget group status" table at the top of
[`cassandra/cases/convergence/_batch-log.md`](cassandra/cases/convergence/_batch-log.md).** It
records, per shared-budget group, whether prior runs consider it open,
exhausted, parked, or **skipped** (and why) — this is the dedup mechanism: it
exists so a new run doesn't re-survey or re-run a group a previous run
already closed out, or re-pick a group that was deliberately paused by
request. **Never pick a combination from a group marked `skipped` — move on
to another open group instead — until a later instruction explicitly
un-skips it in that table.** Unlike `exhausted` or `parked`, `skipped` does
not mean the group ran out of combinations or hit a blocker; it means
someone asked to stop working it for now, so treat it as a hard stop, not a
judgment call to override. Update that table (not just the per-run entry)
whenever a run's result changes a group's status — including marking a
group **exhausted** when the run judges the remaining plausible
combinations are no longer worth trying, or **parked** when it's blocked on
something outside the group (e.g. missing infrastructure).

1. **Group by shared budget first (this is the only lane in scope right
   now).** On-heap (JVM heap), off-heap/direct memory
   (`-XX:MaxDirectMemorySize`, or unbounded direct buffers), a named pool
   (e.g. a memtable pool, a cache), or disk. Two constraints are in the same
   group if they draw on the literal same budget, or on budgets that both
   ultimately compete for the same physical RAM (heap + off-heap both draw
   on the node's RAM even though the JVM tracks them separately).

   There is a second, distinct way two constraints could converge:
   **causal-chain convergence**, where exhausting one constraint's budget
   removes or slows the mechanism that normally keeps a *different* budget
   bounded (e.g. disk pressure stalling flush/compaction so an on-heap
   backlog queue can't drain — heap grows from the backlog, not because
   disk and heap share a pool). This is a real, plausible misconfiguration
   path and **is noted here on purpose so it isn't rediscovered as a gap
   later**, but it is **out of scope for picking combinations today** —
   only shared-pool grouping (above) is used to pick a combination for now.
   A constraint pair that looks like a causal-chain case should be recorded
   in the batch log's status table as **deferred (causal-chain, not
   picked)**, not built or run, until this scope is revisited.
2. **Within a shared-budget group, enumerate combinations of 2–3
   constraints** before trying 4+: start with the smallest combination
   predicted to exceed the budget, and prefer combinations that are
   plausible from a single operator's misconfiguration (see Target-3 note
   below) over ones that need many unrelated knobs changed at once.
3. **A shared-budget group with only one usable constraint, or with
   constraints whose summed capacities cannot plausibly exceed the budget
   even at extreme sizing, is noted and skipped** — record why in the batch
   log, do not force a case.
4. **Produce one case per combination actually built and run**, even if it
   does not OOM (a negative result is still a case — see "What a case
   records").

## Designing and sizing a case (the agent's job)

For each chosen combination:

1. **Size each one safe alone.** Set the node's total memory (`-Xmx`,
   container/cgroup limit, or physical RAM for a bare node) and size each
   constraint so that, driven to its capacity by itself with every other
   constraint at a conservative default, free memory stays comfortably
   positive (state the margin used, e.g. ≥ 30% of `-Xmx` free).
2. **Size the combination to exceed it.** Confirm, by addition before
   running anything, that the sum of the per-constraint capacities (plus
   normal baseline usage: JVM baseline, other caches, metadata) exceeds the
   budget from step 1. Show the arithmetic in the case file before the run —
   this is a prediction, not a measurement.
3. **Design the concurrent workload.** A single client workload, or a small
   set of concurrent workloads, each targeting one constraint's capacity, run
   **concurrently** against one node (or small cluster) — not sequentially.
   Sequential saturation that recovers between steps does not prove
   convergence. State, per constraint, the exact knob values and the
   workload that pushes usage to that constraint's capacity (reuse the
   if-check-exp case's cluster-tier workload where it exists).
4. **Design the instruments.** Total JVM heap and off-heap/direct usage (the
   same observables if-check-exp stage 4 used: `jcmd GC.class_histogram`,
   `RssAnon`, or the constraint's own metric), at a sampling rate fine enough
   to see the usages rise together, not just the final OOM; `dmesg` for a
   kernel OOM-kill.

## Running it (the agent's job)

1. **Control arms first**: run each constraint alone (same node, same
   baseline, same workload sizing as in the combination) and confirm it
   reaches its capacity without OOM. Skip a control arm only if the same
   constraint already has one in this batch's run log.
2. **Convergence arm**: run all constraints in the combination together and
   observe. Log everything (`script`/`tee`); stop every process the run
   starts and check none is left before moving to the next combination.
3. Run on a node you own, with nothing outside that node touched. Never fill
   shared storage; put node data, commit log and hints on local disk of
   known size.
4. **If a combination OOMs the node**, that is the point of the run — record
   it, recover the node (restart, clear state as needed) and move to the next
   combination. Do not push further "to see how bad it gets" once OOM is
   confirmed.

## What a case records (success or not)

A combination's case file records the outcome whichever way it goes:

- **OOM reached**: control arms stayed safe, the convergence arm's usages
  rose together and the node OOMed (actual `OutOfMemoryError`, kernel
  OOM-kill, or GC-pressure unresponsiveness), and the predicted sum from
  sizing step 2 matches what was observed (within a stated tolerance).
- **OOM not reached**: record the measured total and by how much it fell
  short of the budget, and the agent's judgement on whether a different
  sizing, a third constraint, or a different workload mix would close the
  gap. This is filed as a case too, not discarded.

## Output

Write one file per attempted combination to
`<system>/cases/convergence/<constraint-1>+<constraint-2>[+...].md` in this folder (for Cassandra, `cassandra/cases/convergence/`).
Use this template — four sections, in this order:

### 1. Constraints and capacities

For each constraint in the combination: its if-check-exp case-file link and
outcome class, the capacity check (`file:line`), what it caps (heap,
off-heap/direct memory, a named pool, or disk), the constraint's default and
how it is set, and the capacity value chosen for this case. Name the shared
budget the combination draws on and the node's total for it (`-Xmx`,
`-XX:MaxDirectMemorySize`, cgroup limit, or physical RAM). This section is
the output of "Picking combinations" above.

### 2. Verification solution

How to reach all the capacities **at the same time**. This is the design,
written before running anything:

- **Sizing.** Each constraint's capacity sized safe alone (state the margin
  left free when it alone is at capacity), and the arithmetic showing the
  combination's summed capacities plus baseline usage exceeds the shared
  budget.
- **Workload.** The concurrent client workload(s) — one per constraint,
  run together, not sequentially — with exact knob values, data volumes,
  concurrency, and how long each must run to reach its capacity.
- **Instruments.** What is sampled (JVM heap, off-heap/direct usage, the
  constraint's own metric, `dmesg`) and at what rate, fine enough to see the
  usages rise together.
- **Procedure.** The control arms (each constraint alone, confirming it is
  safe alone) and the convergence arm (all together), as an exact,
  executable sequence — commands, not prose a later reader has to re-derive.

### 3. Runtime results

What happened after the solution was executed:

- Control-arm readings: did each constraint alone stay safe (no OOM), and
  at what measured usage/margin.
- Convergence-arm readings: the usage trajectory while all constraints were
  driven together, and the final state — **did the node OOM**: an actual
  `OutOfMemoryError`, a kernel OOM-kill (`dmesg`), GC-pressure
  unresponsiveness, or none of these. Cite the raw log/excerpt for every
  number and every claimed event.
- Whether the sizing prediction from section 2 matched what was observed
  (within a stated tolerance).

### 4. Conclusion

- **If the node OOMed:** state the conclusion as a capability gap — *Cassandra
  has no mechanism that caps the combined usage of these constraints, so
  reaching their individual capacities together is enough to OOM the node
  even though each capacity is individually enforced.* Say which combination
  reproduces it and the minimum sizing found.
- **If the node did not OOM:** state why, specifically — the agent's
  diagnosis, not just "it didn't happen." Common reasons to check and name
  whichever applies: the combination's predicted sum didn't actually exceed
  the budget (sizing error), the workloads didn't reach their individual
  capacities together (timing/synchronization), GC or another mechanism
  reclaimed memory from one constraint while the other grew (the budget
  isn't as shared as assumed), or a different guardrail intervened first
  (e.g. a request was rejected before memory was taken). State whether a
  resized or re-timed version of the same combination is worth a retry, or
  whether this shared-budget group should be marked exhausted.
- **Target-3 note:** is this combination realistic from a single operator
  misconfiguration, or does it need several workloads driven deliberately?

Keep a **batch log** at `cases/convergence/_batch-log.md` (append one entry
per playbook run): the date, the shared-budget groups surveyed, every
combination attempted with a link to its case file, every combination
considered and skipped with why, and the stopping reason (budget exhausted
vs. time/count limit).

Commit case files, the batch log, and raw-log excerpts the same way
if-check-exp stage 4 does (small excerpts in the repo, full logs kept on the
node, path recorded). The agent does not commit or push unless asked.
