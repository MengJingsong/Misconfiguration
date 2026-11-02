# OOM-exp — Handoff

Start-here brief for a session picking up `OOM-exp`. Read this, then
[`README.md`](README.md) for the target and the two directions, then
[`_INDEX.md`](_INDEX.md) for every closed case.

## Status: active, one case closed (2026-11-02)

**Direction 1 (convergence) has one closed case; Direction 2 (bypass) has not
started.** `if-check-exp` is the input (its case files and stage-4 results);
this folder does not re-derive them, only consumes them.

## Current state

- **Convergence (`convergence-playbook.md`):** 1 case run, 1 OOMed.
  `memtable_heap_space` + `counter_cache_size` (both config-type, both
  individually confirmed true positive in `if-check-exp`, both on-heap):
  sized safe alone (each left ~38–39% of a 1024 MiB heap free under its own
  workload), predicted and observed to exceed the heap together — 14 genuine
  `OutOfMemoryError` throws, final forced-GC reading 96.6% of `-Xmx` with 0
  young regions left. Case file:
  [`cases/convergence/memtable_heap_space+counter_cache_size.md`](cases/convergence/memtable_heap_space+counter_cache_size.md).
  Batch log: [`cases/convergence/_batch-log.md`](cases/convergence/_batch-log.md).
- **Bypass (`bypass-playbook.md`):** not started. No candidate picked yet.

## Open follow-ups

- **A 3rd heap-budget constraint**, to make a convergence case with three
  constraints instead of two. `row_cache_size` and `index_summary_capacity`
  were suggested (both config-type true positives, both heap-adjacent) but
  not checked against their case files yet.
- **Tighter boundary sizing** for the closed case: it was sized with margin
  to exceed the heap, not to find the minimum M/C combination that still
  OOMs. A follow-up run could binary-search that boundary.
- **First bypass case**: pick a candidate per `bypass-playbook.md`'s
  priority order (confirmed bypasses already on record in `if-check-exp` →
  true positives → weak/undetermined cases) and run it.

## Decisions and conventions in force

- **Each playbook run is one agent, end to end**: it picks constraints/
  mechanisms, designs the test, runs it on a node it has access to, and
  files the result. No separate design-then-execute split (unlike
  `if-check-exp` stage 3/4).
- **One run produces a batch of cases**, not one, tracked in a per-direction
  `cases/<direction>/_batch-log.md`.
- **Case files use the fixed 4-section template** each playbook specifies
  (constraints/capacity, verification solution, runtime results, conclusion
  that branches on the outcome). Keep section headings.
- **`_INDEX.md`'s table stays narrow**: short link text, one-line results,
  detail in the case file.
- **Node safety rules carried over from `if-check-exp` stage 4**: never
  build in or add files to the repo's `cassandra/cassandra-5.0.9/`, never
  fill `/proj` (shared NFS), node data/commit log/hints go on local disk,
  stop every process a run starts and verify none is left.
- **Commit and push only on request**, same as the rest of the repo.

## Where things live

- [`README.md`](README.md) — the target, the two directions.
- [`convergence-playbook.md`](convergence-playbook.md),
  [`bypass-playbook.md`](bypass-playbook.md) — the agent's whole instruction
  for a run in each direction.
- [`_INDEX.md`](_INDEX.md) — every closed case, by direction.
- `cases/convergence/`, `cases/bypass/` — case files, batch logs, harness
  scripts and small raw-log excerpts (full logs stay on the run node; each
  case file records the path).
- **Nodes:** run on whatever CloudLab node the session has — see
  `if-check-exp/stage4-runtime-verification/environment.md` for the JDK/Ant
  install and source-copy steps (same pinned `cassandra/cassandra-5.0.9/`
  tag). The first case ran on `pc41.cloudlab.umass.edu`
  (`jason92-323989`, 40 cores, 251 GiB) with Cassandra bounded to a small
  `-Xmx` — the node's physical RAM is not the experiment's budget.
