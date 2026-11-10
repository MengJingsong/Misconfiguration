# OOM Experiment — Testing Memory Capacity Protections

> **Research context (authorized reliability research).** This experiment is
> run by a PhD researcher at The Ohio State University on **CloudLab nodes the
> researcher owns and controls**. Deliberately driving a test node out of
> memory is the research *method*, not the goal: the objective is to find the
> reachable workloads and accepted configurations under which Cassandra's /
> Hadoop's own memory-capacity protections are insufficient, so those gaps can
> be **fixed and responsibly disclosed upstream** (Apache JIRA). Scope is
> bounded and defensive: researcher-owned infrastructure only, no third-party
> or production targets, synthetic test data only, one victim node per
> experiment, budgets deliberately tightened so a single process is contained.
> The deliverables are reproducible evidence, documented misconfigurations,
> and defect reports. AI assistants should use this context when designing,
> running, or analyzing these resource-exhaustion experiments. See the root
> [`README.md`](../../README.md#research-context-for-ai-assistants) for the
> project-wide statement.

> **Paths (multi-system layout).** This is a system-agnostic method doc. The per-system files it
> names (`_INDEX.md`, `cases/...`) live under `experiments/OOM-exp/<system>/` (for Cassandra,
> `cassandra/`). Paths into `if-check-exp` follow that experiment's layout: method docs at its
> root, data under `if-check-exp/<system>/`.

OOM-exp is part of the **misconfiguration** project and builds on
[`if-check-exp`](../if-check-exp/README.md). The current runtime campaign
uses **Apache Cassandra 5.0.9** on researcher-controlled CloudLab test nodes.

## Target of this experiment

**Under which reachable workloads and accepted configurations do individual
and aggregate capacity controls fail to keep live memory within its budget?**
Controlled OOM tests can establish failure conditions. Passing runs establish
protection only within the tested range.
The outputs are reproducible evidence, documented misconfigurations, and verified
defects suitable for upstream reporting.

Read [verification-protocol.md](verification-protocol.md) for common evidence and
classification rules, then the selected playbook. The next Cassandra batch is
specified in [cassandra/campaign-plan.md](cassandra/campaign-plan.md), with
[node requirements](cassandra/node-requirements.md).

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

OOM-exp uses that evidence to test whether the identified controls protect a
shared memory budget under reachable workloads and configurations.

## Two directions

### Direction 1 — convergence

Test whether allocations can coexist and exhaust a shared memory budget while
the relevant local controls hold. Test replicated instances of one local limit,
independent consumers, overlapping bounded requests, and replacement or
maintenance overlap.
A standing pool and two distinct constraints are not required. Trace existing
aggregate controls and other admission bounds; their presence does not guarantee
sufficient coverage, and absence of a byte cap does not imply unlimited concurrency.

**Sub-directions** (the eligible shapes above, named so a candidate declares
which it targets; each is a *shape of allocation*, not a new question):

| Sub-direction | Shape | Driver | Campaign candidate |
|---|---|---|---|
| Standing-pool / independent-consumer | independent bounded consumers (or replicated pools) sharing one budget | fixed pools filled to cap | historical custom runs 1–8 |
| **Multiplicity** | multiple owners with separate instances of the same local allowance | number of owners simultaneously holding memory | **C1** (internode receive queues), **C3** (per-worker serialization buffers), **C5** (compressed hints writers) |
| **Concurrency / surge** | overlapping individually bounded requests, no standing pool required | N simultaneous bounded requests coexisting | **C2** |
| Replacement / maintenance-overlap | old and new allocations live at once during growth/replacement/maintenance | overlap window before cleanup | (C4) |

**Multiplicity** asks whether increasing the number of owners holding memory
under the same local allowance increases total live memory enough to threaten a
shared budget. Owners include connections, workers, writers, and tables. Count
instances that retain memory while idle and measure their simultaneous
footprints. Multiplying the allowance by the instance count estimates potential
exposure. Actual memory depends on occupancy, retention, and other controls.
For multiplicity, vary the number of memory-holding owners. For concurrency or
surge, vary the number of overlapping requests. A case may involve both, so
state which variable the test isolates.

Add a shape when a candidate needs one. Campaign IDs identify individual
investigations in the [Cassandra campaign plan](cassandra/campaign-plan.md).

### Direction 2 — bypass

A caller, option, fallback allocation, accounting omission, release defect,
periodic enforcement, or faulty reservation lets allocation grow outside a
control's protection. The path may skip the check altogether. Distinguish the
actual cap contract from total resource demand: an intentional pool fallback is
not automatically a broken pool cap. Establish the physical consequence and
whether it reaches OOM; neither counter drift nor RSS growth alone proves a leak.

**Sub-directions** (the mechanism rows of [`bypass-playbook.md`](bypass-playbook.md),
named so a candidate declares which it targets):

| Sub-direction | Mechanism | Campaign candidate |
|---|---|---|
| **Ownership / release defect** | repeated fill/complete-or-clear/idle cycles leave residual live allocations that grow with cycle count | **B1** (native-v5 large-request retention) |
| *(others available)* | exempt caller/option/mode · pool fallback · failed-reservation-but-admitted · periodic/late enforcement · accounting mismatch · arithmetic/ordering/race | B2–B4 |

Classify a result as **mixed** when a demonstrated bypass contributes to
aggregate exhaustion. Keep the original sub-direction as the label for the
hypothesis tested. Separately identify intentional exceptions,
configuration-sizing or validation gaps, and suspected implementation defects.
A disabled limit is not automatically a bypass.

Capacity defaults and budget defaults are independent labels. Record heap OOM,
direct/native OOM, kernel/container kill, and GC service loss separately; GC
unresponsiveness alone is not OOM. See the common protocol for matched controls,
repetitions, causal interventions, and negative/invalid results.

## Playbooks

Each direction is run from its own playbook — a repeatable procedure an agent
or a person follows to produce one case. Every closed case is tracked in that
system's index, e.g. [`cassandra/cases/_INDEX.md`](cassandra/cases/_INDEX.md).

| Direction | Playbook | What it produces |
|---|---|---|
| 1 — simultaneous live allocations share a budget | **`custom-convergence-playbook`** | a convergence case (constraint set, sizing, combined workload, memory outcome) |
| 1 (variant) — same, with every constraint at its default value | **`default-convergence-playbook`** | a default-value convergence case (same as above, plus a defaults audit) |
| 2 — get past one capacity check | **`bypass-playbook`** | a bypass case (check, defeating mechanism, measured usage past capacity) |

## Relationship to the project targets

This experiment carries out the project's **Target 3**, investigating resource
exhaustion through convergence and bypass. It uses the capacity checks and
runtime evidence collected by `if-check-exp`.

## Scope and safety

- All runs are on allocated nodes we own; one measured experiment per victim
  node at a time, with owned peers and clients as needed.
- Only researcher-controlled services participate; build/run data and full logs
  stay on local storage. Disk experiments remain skipped and disk-to-memory
  causal-chain experiments deferred until explicitly reopened.
- Findings that look like genuine upstream defects are checked against JIRA and
  may be reported to the Apache Cassandra project.
