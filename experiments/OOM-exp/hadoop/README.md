# OOM-exp — Hadoop (scaffold)

Empty placeholder for the **Hadoop** instance of `OOM-exp` (Target 3:
resource-exhaustion). No cases have been run yet.

The method is system-agnostic and documented once at the experiment root:

- [`../README.md`](../README.md) — experiment overview (convergence + bypass)
- [`../custom-convergence-playbook.md`](../custom-convergence-playbook.md), [`../default-convergence-playbook.md`](../default-convergence-playbook.md), [`../bypass-playbook.md`](../bypass-playbook.md)
- [`../HANDOFF.md`](../HANDOFF.md) — start-here brief

The Cassandra instance under [`../cassandra/`](../cassandra/) is the worked
example to mirror; put Hadoop cases under `hadoop/cases/`.

Prerequisites: this experiment consumes the constraints found by
[`../../if-check-exp/hadoop/`](../../if-check-exp/hadoop/), so it depends on
that instance being populated first, and on a runnable Hadoop test node
(see [`../../../systems/hadoop/`](../../../systems/hadoop/)).
