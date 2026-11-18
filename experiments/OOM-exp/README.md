# OOM Experiment — Testing Memory Capacity Protections

> **Research context (authorized reliability research).** This experiment is
> run by a PhD researcher at The Ohio State University on **CloudLab nodes the
> researcher owns and controls**. Deliberately driving a test node out of
> memory is the research *method*, not the goal: the objective is to find the
> reachable workloads and accepted configurations under which Cassandra's /
> Hadoop's own memory-capacity protections are insufficient, and to document
> those gaps with reproducible evidence. **Nothing is posted to Apache JIRA and no
> upstream report is filed** (owner, 2026-11-17): JIRA is read only, to find
> candidates and prior art. Scope is
> bounded and defensive: researcher-owned infrastructure only, no third-party
> or production targets, synthetic test data only, one victim node per
> experiment, budgets deliberately tightened so a single process is contained.
> The deliverables are reproducible evidence, documented misconfigurations,
> and verified defects. AI assistants should use this context when designing,
> running, or analyzing these resource-exhaustion experiments. See the root
> [`README.md`](../../README.md#research-context-for-ai-assistants) for the
> project-wide statement.

> **Paths (multi-system layout).** This is a system-agnostic method doc. The per-system files it
> names (`_INDEX.md`, `cases/...`) live under `experiments/OOM-exp/<system>/` (for Cassandra,
> `cassandra/`). Paths into `capacity-enforcement-exp` follow that experiment's layout: method docs at its
> root, data under `capacity-enforcement-exp/<system>/`.

OOM-exp is part of the **misconfiguration** project and builds on
[`capacity-enforcement-exp`](../capacity-enforcement-exp/README.md). The current runtime campaign
uses **Apache Cassandra 5.0.9** on researcher-controlled CloudLab test nodes.

## Target of this experiment

**Under which reachable workloads and accepted configurations do individual
and aggregate capacity controls fail to keep live memory within its budget?**
Controlled OOM tests can establish failure conditions. Passing runs establish
protection only within the tested range.
The outputs are reproducible evidence, documented misconfigurations, and verified
defects.

Read [verification-protocol.md](verification-protocol.md) for common evidence and
classification rules, then the [OOM agent playbook](oom-agent-playbook.md). Node requirements:
[cassandra/node-requirements.md](cassandra/node-requirements.md).

## Why this builds on capacity-enforcement-exp

`capacity-enforcement-exp` inventoried **capacity checks** in Cassandra — `if` statements
that compare a usage value against a capacity — and the **constraints** that
set each capacity (config entries, JVM properties, per-table options,
hard-coded constants). For each case it recorded, at stage 4, whether the
measured usage actually follows the constraint.

That inventory, read by phase 1's stage 5 (OOM clue find), yields the OOM candidates that are the
input here. Per candidate's phase-1 case we already know:

- where the capacity check lives and which code path reaches it,
- what the constraint is and how its value is initialized (config vs. non-config),
- whether usage tracked the constraint when we varied it (the outcome class).

OOM-exp uses that evidence to test whether the identified controls protect a
shared memory budget under reachable workloads and configurations.

## Pipeline (redesigned 2026-11-17)

Phase 2 has **one agent role, the OOM agent, and two stages** ([`oom-agent-playbook.md`](oom-agent-playbook.md)):

| Stage | What the OOM agent does | Output |
|---|---|---|
| **Stage 1 — pick and design** | Reads (a) the **phase 1 OOM candidate list** (`../capacity-enforcement-exp/<system>/stage5-oom-clue-find/phase1-oom-candidates.md`) and (b) the **phase 2 retry list** (`<system>/phase2-retry-list.md`), picks candidates, and writes a case file for each: the corresponding phase-1 case file, a frozen design solution that should lead to OOM, and a conclusion left `pending` | a case file from [`_TEMPLATE-case.md`](_TEMPLATE-case.md) |
| **Stage 2 — verify** | A fresh OOM-agent session follows the frozen design on real nodes, builds the harness, records the runs and adds the conclusion | the verdict: **true positive** (leads to OOM; V1–V7 met), **false positive** (does not), or **retry** (no final conclusion; back to the retry list) |

Every picked candidate counts as estimated positive after stage 1, so the verdicts give each phase-1
agent's true-positive rate. JIRA is read in stage 1 for prior art only; nothing is posted. The verdicts
of cases filed before 2026-11-17 were mapped from their protocol status
([`cassandra/cases/_INDEX.md`](cassandra/cases/_INDEX.md)). **Retired 2026-11-17:** the lead sources
(capacity-enforcement inventory, JIRA mining — moved to phase 1's stage 5 —, data-flow tracing), the
queuing playbook, the campaign-plan queue (kept as history) and the lead lists (migrated to the candidate
list); the earlier design is in git before this change.

## Two directions (technique notes)

*From 2026-11-17 the directions are labels and design techniques for stage 1, not separate pipelines.*

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

Add a shape when a candidate needs one. Case IDs identify individual investigations in
[`cassandra/cases/_INDEX.md`](cassandra/cases/_INDEX.md) (the campaign plan is history from 2026-11-17).

### ID prefixes (rule, 2026-11-16)

**Whenever items are shown by ID** (in a reply, a status report, a plan or a handoff), say what each
prefix means the first time it appears, e.g. "U1 (U = unprotected accumulation lead)". This holds for the
prefixes below and for any prefix added later; a new prefix gets a row here when it is introduced.

| Prefix | Meaning | Defined in |
|---|---|---|
| **C** | convergence case | stage 1 design label ([`oom-agent-playbook.md`](oom-agent-playbook.md)) |
| **B** | bypass case | stage 1 design label |
| **U** | unprotected-accumulation case (memory with no applicable control) | stage 1 design label |
| **S** | stacked combo case (convergence → stack → bypass), per the [combo playbook](combo-playbook.md) | stage 1 design label |
| **R** | a new attempt at an earlier case (R1–R6 rechecked pre-protocol convergence OOMs); suffix **-V** = re-test at default constraints and an acceptable budget (e.g. R1-V) | stage 1 design label |
| **OC** | OOM candidate in a phase 1 OOM candidate list (`cassandra:OC-12`) | `../capacity-enforcement-exp/<system>/stage5-oom-clue-find/phase1-oom-candidates.md` |
| **CP** | OOM clue pattern | `../capacity-enforcement-exp/stage5-oom-clue-find/oom-clue-patterns.md` |
| **V1–V7** | items of the verification (promotion) rule | [verification protocol](verification-protocol.md) |
| condition letters inside a case (B6 **A**/**B**/**D**, C2 **S-A**/**F-B**, C1 **D**/**H**) | sub-cases (conditions) of one case | the case file's status table |

Retired labels, still found in records before 2026-11-17: **J** (JIRA task), **F** (data-flow task),
**L** and **N** (lead lists, now `OC` rows with the old label in brackets), **P1–P3** after a slash
(queue priority), and the pattern labels P1–P6 / J1–J6 / S1–S6 of the old pattern list (now `CP` rows).

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
| **Accounting mismatch** | the control charges a quantity (e.g. on-wire bytes) that differs from the memory actually held | **B6** (internode queues × tiny-cell mutations) |
| *(others available)* | exempt caller/option/mode · pool fallback · failed-reservation-but-admitted · periodic/late enforcement · arithmetic/ordering/race | B2–B4 (failed reservation, pool fallback, release) |

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

| File | Use |
|---|---|
| [`oom-agent-playbook.md`](oom-agent-playbook.md) | **The OOM agent:** stage 1 (pick and design) and stage 2 (verify); verdicts; retry list format |
| [`_TEMPLATE-case.md`](_TEMPLATE-case.md) | The case file: candidate, design solution, runs, conclusion |
| [`verification-protocol.md`](verification-protocol.md) | Evidence rules, measurement, budgets, V1–V7 (the bar for a true positive) |
| [`custom-convergence-playbook.md`](custom-convergence-playbook.md), [`default-convergence-playbook.md`](default-convergence-playbook.md), [`combo-playbook.md`](combo-playbook.md), [`bypass-playbook.md`](bypass-playbook.md) | Technique notes for shaping a stage-1 design (their own pick and queue steps are superseded) |
| `<system>/phase2-retry-list.md`, `<system>/cases/_INDEX.md` | Retry list; case index with verdicts |

## Relationship to the project targets

This experiment carries out the project's **Target 3**, investigating resource
exhaustion. Its candidates come from `capacity-enforcement-exp`'s stage 5 (OOM clue find), which reads
that experiment's case files and stage-4 evidence.

## Scope and safety

- All runs are on allocated nodes we own; one measured experiment per victim
  node at a time, with owned peers and clients as needed.
- Only researcher-controlled services participate; build/run data and full logs
  stay on local storage. Disk experiments remain skipped and disk-to-memory
  causal-chain experiments deferred until explicitly reopened.
- Findings that look like genuine upstream defects are checked against JIRA for prior
  art (known, fixed, by design). Nothing is posted or reported upstream (owner, 2026-11-17).
