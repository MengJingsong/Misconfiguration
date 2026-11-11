# OOM-exp — Hadoop (scaffold)

Empty placeholder for the **Hadoop** instance of `OOM-exp` (Target 3:
resource-exhaustion). No cases have been run yet.

The method is system-agnostic and documented once at the experiment root:

- [`../README.md`](../README.md) — experiment overview (convergence + bypass)
- [`../custom-convergence-playbook.md`](../custom-convergence-playbook.md), [`../default-convergence-playbook.md`](../default-convergence-playbook.md), [`../bypass-playbook.md`](../bypass-playbook.md)
- [`../HANDOFF.md`](../HANDOFF.md) — start-here brief

The Cassandra instance under [`../cassandra/`](../cassandra/) is the worked
example to mirror; put Hadoop cases under `hadoop/cases/`, using the same
status-first layout: `cases/convergence/` (verified OOM or gap by convergence),
`cases/bypass/` (verified OOM or gap by bypass), `cases/candidates/`
(not yet meeting the [promotion rule](../verification-protocol.md#verification-status-amended-2026-11-11))
and `cases/negatives/` (verified no-OOM), with
the capacity regime (custom | default) recorded as a label — not a folder. The
master status table lives at `cases/_INDEX.md` and the chronological run log at
`cases/_run-log.md`. Lead-source outputs (the
[JIRA OOM survey](../jira-mining-playbook.md) and
[data-flow holder tables](../dataflow-tracing-playbook.md)) go under
`hadoop/leads/`; the JIRA survey can start before if-check-exp Hadoop is done.

Prerequisites: this experiment consumes the constraints found by
[`../../if-check-exp/hadoop/`](../../if-check-exp/hadoop/), so it depends on
that instance being populated first, and on a runnable Hadoop test node
(see [`../../../systems/hadoop/`](../../../systems/hadoop/)).
