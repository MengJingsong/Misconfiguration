# Convergence playbook (Direction 1)

Produces one **convergence case**: a set of constraints, each sized so that
reaching its own capacity is safe alone, combined so that reaching all of them
**at the same time** drives the test node out of memory.

Run this by hand or give it to an agent, in a Claude Code session with a copy
of the Cassandra source at tag `cassandra-5.0.9` and read access to
[`if-check-exp`](../if-check-exp/README.md) (its case files are the input;
this experiment does not re-derive them).

## The goal

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
(`if-check-exp/stage3-ai-deep-read/cases/`, `if-check-exp/stage4-runtime-verification/results/`):

1. **The capacity check** — `file:line`, and what it compares.
2. **The constraint** — how its value is set (config/non-config), its default,
   and whether it can be raised or lowered without a build.
3. **What it caps** — heap, off-heap/direct memory, or disk, and roughly how
   many bytes at capacity.
4. **The outcome class** — prefer **true positive** (confirmed: it caps usage) or
   a confirmed **bypass**. Do not build a convergence case on a constraint the
   case file found does not cap (true negative) — if it never reached capacity
   on its own, driving it to "capacity" is not a load.

## Choosing a combination

1. **Pick a shared budget.** Group candidate constraints by what they draw on:
   on-heap (JVM heap), off-heap/direct memory (`-XX:MaxDirectMemorySize`, or
   unbounded direct buffers), or a named pool (e.g. a memtable pool, a cache).
   Constraints on unrelated budgets (one heap-bound, one disk-bound) cannot
   converge into an OOM together — pick from the same budget, or from budgets
   that both ultimately compete for the same physical RAM (heap + off-heap
   both draw on the node's RAM even though the JVM tracks them separately).
2. **Size each one safe alone.** Set the node's total memory (`-Xmx`,
   container/cgroup limit, or physical RAM for a bare node) and size each
   constraint so that, driven to its capacity by itself with every other
   constraint at a conservative default, free memory stays comfortably
   positive (state the margin you used, e.g. ≥ 30% of `-Xmx` free).
3. **Size the combination to exceed it.** Confirm, by addition before running
   anything, that the sum of the per-constraint capacities (plus normal
   baseline usage: JVM baseline, other caches, metadata) exceeds the budget
   from step 2. Show the arithmetic in the case file before the run — this is
   a prediction, not a measurement.
4. **Prefer 2–3 constraints.** More constraints make the workload harder to
   drive simultaneously and harder to attribute; start with the smallest
   combination that is predicted to exceed the budget.

## Driving the workload

- A single client workload, or a small set of concurrent workloads, each
  targeting one constraint's capacity, run **concurrently** against one node
  (or small cluster) — not sequentially. Sequential saturation that recovers
  between steps is not a convergence case.
- State, per constraint, the exact knob values and the workload that pushes
  usage to that constraint's capacity (reuse the if-check-exp case's cluster-tier
  workload where it exists).
- Instrument total JVM heap and off-heap/direct usage (the same observables
  `if-check-exp` stage 4 used: `jcmd GC.class_histogram`, `RssAnon`, or the
  constraint's own metric) at a sampling rate fine enough to see the usages
  rise together, not just the final OOM.
- Run on a node you own, with every process you start accounted for and
  stopped afterward, and nothing outside that node touched.

## What counts as success

A convergence case is confirmed when:

1. Each constraint run alone (control arm, same node, same baseline) reaches
   its capacity without OOM.
2. All constraints run together (the convergence arm) reach their capacities
   in the same window and the node OOMs — recorded as an actual
   `OutOfMemoryError`, kernel OOM-kill (`dmesg`), or an observed failure to
   reclaim memory under GC pressure with the node becoming unresponsive.
3. The case file shows, numerically, that the predicted sum from step 3 above
   matches what was observed (within a stated tolerance).

If the combination does not OOM, that is still a result: record the measured
total and by how much it fell short, and whether a larger combination or
different sizing would close the gap.

## Output

Write one file per case to `cases/<constraint-1>+<constraint-2>[+...]--convergence.md`
in this folder, covering:

- **A.** The constraints involved, each with its if-check-exp case-file link,
  outcome class, and what it caps.
- **B.** The shared budget and the control-arm sizing (per-constraint capacity,
  predicted margin alone).
- **C.** The convergence-arm sizing and the predicted sum vs. the budget
  (arithmetic, before running).
- **D.** The workload and instruments for both arms.
- **E.** Results: control-arm readings (no OOM), convergence-arm readings
  (OOM or not), and whether the prediction held.
- **F.** Notes for Target 3 — is this combination realistic from a single
  operator misconfiguration, or does it need an attacker driving several
  workloads deliberately?

Commit case files and raw-log excerpts the same way if-check-exp stage 4 does
(small excerpts in the repo, full logs kept on the node, path recorded).
