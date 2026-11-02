# OOM Experiment — Driving a Test Node Out of Memory

Resource-exhaustion research on **Apache Cassandra 5.0.9**, run on our own
CloudLab test nodes. Part of the **misconfiguration** project, and a direct
follow-on to [`if-check-exp`](../if-check-exp/README.md).

## Target of this experiment

**Make the testing node run out of memory while running Cassandra**, by
driving the resource usage that Cassandra's own capacity checks are meant to
bound. The point is to show, at runtime, the conditions under which those
checks fail to prevent exhaustion — so the misconfigurations and bypasses that
lead to OOM can be documented and, where they are real defects, reported
upstream.

This is a defensive, research-only exercise: every run is on a node we own and
control, one Cassandra process we started, and no external or third-party
system is targeted.

## Why this builds on if-check-exp

`if-check-exp` inventoried **capacity checks** in Cassandra — `if` statements
that compare a usage value against a capacity — and the **constraints** that
set each capacity (config entries, JVM properties, per-table options,
hard-coded constants). For each case it recorded, at stage 4, whether the
measured usage actually follows the constraint.

That inventory is the input here. We already know, per constraint:

- where the capacity check lives and which code path reaches it,
- what the constraint is and how its value is initialized (config vs. non-config),
- whether usage tracked the constraint when we varied it (the outcome class).

This experiment takes those constraints and asks the inverse question: **how do
we turn them into an actual OOM on the node?**

## Two directions

### Direction 1 — convergence (multiple usages reach capacity at once)

A single resource pool reaching its capacity usually does **not** OOM the node:
the check either bounds it, or the pool is small relative to the heap. The idea
here is to **manipulate several constraints at the same time** so that:

- each individual usage, at its capacity, stays within a safe margin, but
- several usages sit at their capacities **simultaneously**, and their sum
  exceeds the available memory.

We pick a set of constraints whose capacities draw on the same budget (heap,
off-heap/direct memory, or a shared pool), size each one so it is harmless in
isolation, and construct a workload that pushes all of them to capacity in the
same window. The deliverable is a set of **convergence cases**: which
constraints combine, how each is sized, the workload that saturates them
together, and the measured memory outcome.

### Direction 2 — bypass (get past a single capacity check)

For each constraint/capacity, look for a way that usage **exceeds the capacity
the check was meant to enforce**. The check is present, but something lets
usage grow past it. Causes vary:

- an **escape hatch** — a config flag, a code path, or an option that skips or
  loosens the check,
- an **accounting gap** — the check counts one thing while a correlated
  resource grows uncounted,
- a **unit/overflow/ordering flaw** — the check computes its bound wrongly
  (e.g. integer overflow, wrong unit, check-after-allocate).

Several such gaps were already noted in passing during if-check-exp (see its
"upstream bug candidates" list). The deliverable is a set of **bypass cases**:
the check, the mechanism that defeats it, and the measured usage past the
capacity — ideally driven far enough to threaten OOM.

## Playbooks

Each direction is run from its own playbook — a repeatable procedure an agent
or a person follows to produce one case. Every closed case is tracked in
[`_INDEX.md`](_INDEX.md).

| Direction | Playbook | What it produces |
|---|---|---|
| 1 — multiple usages reach capacity together | **`convergence-playbook`** | a convergence case (constraint set, sizing, combined workload, memory outcome) |
| 2 — get past one capacity check | **`bypass-playbook`** | a bypass case (check, defeating mechanism, measured usage past capacity) |

## Relationship to the project targets

This experiment is where the project's **Target 3** (bypass analysis / resource
exhaustion) is carried out for Cassandra. `if-check-exp` deliberately left
Target 3 out of scope and only noted bypasses in passing; they are chased here.

## Scope and safety

- All runs are on test nodes we own; one Cassandra instance we start and stop.
- No remote, shared, or third-party target; no network service outside the node.
- Findings that look like genuine upstream defects are checked against JIRA and
  may be reported to the Apache Cassandra project.
