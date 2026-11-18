# OOM-exp — Hadoop (scaffold)

Empty placeholder for the **Hadoop** instance of `OOM-exp` (Target 3: resource exhaustion). No cases have
been run yet.

The method is system-agnostic and documented once at the experiment root (redesigned 2026-11-17):

- [`../README.md`](../README.md) — experiment overview and the two-stage pipeline
- [`../oom-agent-playbook.md`](../oom-agent-playbook.md) — the OOM agent: stage 1 (pick and design), stage 2 (verify)
- [`../_TEMPLATE-case.md`](../_TEMPLATE-case.md), [`../verification-protocol.md`](../verification-protocol.md)
- [`../HANDOFF.md`](../HANDOFF.md) — start-here brief

**Inputs:** the Hadoop phase 1 OOM candidate list,
[`../../capacity-enforcement-exp/hadoop/stage5-oom-clue-find/phase1-oom-candidates.md`](../../capacity-enforcement-exp/hadoop/stage5-oom-clue-find/phase1-oom-candidates.md),
and [`phase2-retry-list.md`](phase2-retry-list.md). Put case folders under `hadoop/cases/<stem>/` with a
`cases/_INDEX.md` carrying each case's verdict (true positive / false positive / retry), as Cassandra does.

Prerequisites: candidates from `capacity-enforcement-exp` Hadoop stage 5, and a runnable Hadoop test node
(see [`../../../systems/hadoop/`](../../../systems/hadoop/)).
