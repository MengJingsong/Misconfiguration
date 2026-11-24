# Experiments — how they relate

*Written 2026-11-16; redesigned 2026-11-17 (owner).* What each experiment is for, which depends on
which, and the one hand-off between them. The method of each experiment is in its own README; the map
and flowchart are in [`FLOWCHART.md`](FLOWCHART.md).

## Vocabulary

| Term | Means | Where defined |
|---|---|---|
| **Target 1 / 2 / 3** | the goals of this repository: identify resource constraints; show how each restricts usage; investigate how usage gets past them to exhaustion | root [`README.md`](../README.md) |
| **Phase 1 / 2** | the experiments in dependency order: phase 2 depends on phase 1's results | this file |
| **Phase 1 stages 1–5** | CodeQL, AI preprocessing, AI deep read, runtime verification, OOM clue find | [`capacity-enforcement-exp/README.md`](capacity-enforcement-exp/README.md) |
| **Phase 2 stages 1–2** | pick and design, verify | [`OOM-exp/oom-agent-playbook.md`](OOM-exp/oom-agent-playbook.md) |

Write "phase 1" in full, never "P1".

## The phases

| Phase | Experiment | Targets | Question |
|---|---|---|---|
| **1** | [`capacity-enforcement-exp/`](capacity-enforcement-exp/README.md) (named `if-check-exp` until 2026-11-11) | 1 + 2 | Which factors affect how much memory or disk the system uses, and does usage follow each one? Stage 5: which of them hold clues that could lead to OOM? |
| 1 (supplement, paused) | [`entry-restriction-exp/`](entry-restriction-exp/README.md) | 1 + 2 | The same, worked forward from where a constraint is declared |
| **2** | [`OOM-exp/`](OOM-exp/README.md) | 3 | For each OOM candidate, at the constraints' **default values** and an acceptable memory budget, does a reachable workload run the node out of memory? |

**Phase 1** looks for every factor that affects resource usage. A factor is **config** (a yaml entry or a
JVM system property) or **non-config**: a local variable or constant, the **hidden factors**, because
nothing documents them. Its stage 5 reads the filed cases for OOM clues.

**Phase 2** tests the candidates. A case is a **true positive** only when the OOM is reproducible and
attributed at default constraints and an acceptable budget (OOM-exp
[verification protocol](OOM-exp/verification-protocol.md), V1–V7).

**Phases are per system.** Cassandra is in phase 2; Hadoop is in phase 1 (stages 3–5), and its phase 2
starts from Hadoop's candidate list.

## The hand-off

| From | File | To |
|---|---|---|
| Phase 1 stage 5 (autonomous and guided agents) | `capacity-enforcement-exp/<system>/stage5-oom-clue-find/phase1-oom-candidates.md` | Phase 2 stage 1 (OOM agent picks) |
| Phase 2 stage 2 (verdict) | Status column of the same list; `OOM-exp/<system>/phase2-retry-list.md` for `retry` | Phase 1's per-agent true-positive rate; phase 2 stage 1 (retries) |
| Phase 2 true positives, JIRA OOM reports | [`capacity-enforcement-exp/stage5-oom-clue-find/oom-clue-patterns.md`](capacity-enforcement-exp/stage5-oom-clue-find/oom-clue-patterns.md) (a pattern no row covers) | Phase 1 stage 5 guided agent |

The stage-5 **autonomous** agent never sees the patterns, the JIRA reports or phase 2; it is the control.
Neither stage-5 agent reads phase-2 results, so a candidate that phase 2 confirms counts as phase 1
predicting an OOM.

**Retired 2026-11-17:** the linking machinery of 2026-11-16/17 (guided OOM-lead patterns in stage 3,
autonomous OOM-lead section, rechecks of filed cases, the budget ledger, the OOM lead list, stage-4
rescan claims, the back-link playbook and phase-link tables, the queuing playbook) and phase 2's
JIRA and data-flow lead sources. Its data was migrated into the candidate list, the clue patterns and
the retry list; the files are in git before this change.

## Files at this level

| File | Holds |
|---|---|
| [`FLOWCHART.md`](FLOWCHART.md) | What both experiments do and a flowchart of the whole loop. **Rule (2026-11-17, widened 2026-11-23):** any change to design **or to a result number** under `experiments/` updates it in the same commit ([`CLAUDE.md`](CLAUDE.md)) |
| [`CLAUDE.md`](CLAUDE.md) | Rules for agents working under `experiments/` |
