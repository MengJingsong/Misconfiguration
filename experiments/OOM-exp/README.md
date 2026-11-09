# OOM Experiment — Driving a Test Node Out of Memory

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

Resource-exhaustion research on **Apache Cassandra 5.0.9**, run on our own
CloudLab test nodes. Part of the **misconfiguration** project, and a direct
follow-on to [`if-check-exp`](../if-check-exp/README.md).

## Target of this experiment

**Under which reachable workloads and accepted configurations do Cassandra's
individual and aggregate capacity controls fail to keep live memory within its
budget?** Deliberate OOM on researcher-controlled CloudLab nodes supplies
counterexamples; passing runs establish protection only within the tested range.
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

This experiment takes those constraints and asks the inverse question: **how do
we turn them into an actual OOM on the node?**

## Two directions

### Direction 1 — convergence

Local controls work, but their reachable live allocations together exceed a
shared budget. Test replicated instances of one local limit, independent
consumers, overlapping bounded requests, and replacement/maintenance overlap.
A standing pool and two distinct constraints are not required. Trace existing
aggregate controls and other admission bounds; their presence does not guarantee
sufficient coverage, and absence of a byte cap does not imply unlimited concurrency.

**Sub-directions** (the eligible shapes above, named so a candidate declares
which it targets; each is a *shape of allocation*, not a new question):

| Sub-direction | Shape | Driver | Campaign candidate |
|---|---|---|---|
| Standing-pool / independent-consumer | independent bounded consumers (or replicated pools) sharing one budget | fixed pools filled to cap | runs 1–8 (done) |
| **Multiplicity** | multiple instances of **one** constraint (peers, links, connections, tables) | per-instance allowance × active instances | **C1** |
| **Concurrency / surge** | overlapping individually bounded requests, no standing pool required | N simultaneous bounded requests coexisting | **C2** |
| Replacement / maintenance-overlap | old and new allocations live at once during growth/replacement/maintenance | overlap window before cleanup | (C4) |

The list is open, not a closed enumeration; add a shape when a candidate needs
one. Never count configured-but-inactive instances as multiplicity.

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

Classify a bypass contributing to convergence as **mixed**. Separately identify
intentional exceptions, configuration-sizing/validation gaps, and suspected
implementation defects. A disabled limit is not automatically a bypass.

**A sub-direction labels the hypothesis chosen before the run; `mixed` labels
what the evidence shows.** The two are independent: a candidate filed under a
convergence sub-direction (e.g. C1) becomes `mixed` if a local contract turns
out to be violated, and a release-defect bypass (B1) is `mixed` if the retained
allocations accumulate into aggregate exhaustion.

Capacity defaults and budget defaults are independent labels. Record heap OOM,
direct/native OOM, kernel/container kill, and GC service loss separately; GC
unresponsiveness alone is not OOM. See the common protocol for matched controls,
repetitions, causal interventions, and negative/invalid results.

## Playbooks

Each direction is run from its own playbook — a repeatable procedure an agent
or a person follows to produce one case. Every closed case is tracked in that
system's index, e.g. [`cassandra/_INDEX.md`](cassandra/_INDEX.md).

| Direction | Playbook | What it produces |
|---|---|---|
| 1 — multiple usages reach capacity together | **`custom-convergence-playbook`** | a convergence case (constraint set, sizing, combined workload, memory outcome) |
| 1 (variant) — same, with every constraint at its default value | **`default-convergence-playbook`** | a default-value convergence case (same as above, plus a defaults audit) |
| 2 — get past one capacity check | **`bypass-playbook`** | a bypass case (check, defeating mechanism, measured usage past capacity) |

## Relationship to the project targets

This experiment is where the project's **Target 3** (bypass analysis / resource
exhaustion) is carried out for Cassandra. `if-check-exp` deliberately left
Target 3 out of scope and only noted bypasses in passing; they are chased here.

## Scope and safety

- All runs are on allocated nodes we own; one measured experiment per victim
  node at a time, with owned peers and clients as needed.
- Only researcher-controlled services participate; build/run data and full logs
  stay on local storage. Disk experiments remain skipped and disk-to-memory
  causal-chain experiments deferred until explicitly reopened.
- Findings that look like genuine upstream defects are checked against JIRA and
  may be reported to the Apache Cassandra project.
