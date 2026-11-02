# OOM-exp — Handoff

Start-here brief for a session picking up `OOM-exp`. Read this, then
[`README.md`](README.md) for the target and the two directions, then
[`_INDEX.md`](_INDEX.md) for every closed case.

## Status: active, two cases closed (2026-11-02)

**Direction 1 (convergence) has two closed cases; Direction 2 (bypass) has not
started.** `if-check-exp` is the input (its case files and stage-4 results);
this folder does not re-derive them, only consumes them.

## Current state

- **Convergence (`convergence-playbook.md`):** 2 cases run, both OOMed.
  - Run 1: `memtable_heap_space` + `counter_cache_size` (both config-type, both
    individually confirmed true positive in `if-check-exp`, both on-heap):
    sized safe alone (each left ~38–39% of a 1024 MiB heap free under its own
    workload), predicted and observed to exceed the heap together — 14 genuine
    `OutOfMemoryError` throws, final forced-GC reading 96.6% of `-Xmx` with 0
    young regions left, JVM survived (caught the exceptions). Case file:
    [`cases/convergence/memtable_heap_space+counter_cache_size.md`](cases/convergence/memtable_heap_space+counter_cache_size.md).
  - Run 2: same two plus `key_cache_size` as a 3rd on-heap constraint (config-type
    true positive; `row_cache_size`/`index_summary_capacity` were checked and
    turned out off-heap, not a fit — see below). Smaller individual values than
    run 1 (each still 46–87% free alone), combined drove the heap to 989/1024 MiB
    (96.6%) right after a forced full GC, a genuine `OutOfMemoryError`, a 1.35 GB
    heap dump, and this time `-XX:OnOutOfMemoryError=kill -9 %p` actually fired —
    the JVM was killed, not just stressed. Case file:
    [`cases/convergence/memtable_heap_space+counter_cache_size+key_cache_size.md`](cases/convergence/memtable_heap_space+counter_cache_size+key_cache_size.md).
  - Batch log: [`cases/convergence/_batch-log.md`](cases/convergence/_batch-log.md).
- **Bypass (`bypass-playbook.md`):** not started. No candidate picked yet.

## Open follow-ups

- **An off-heap convergence group**: surveying candidates for the 3rd-constraint
  follow-up (now closed, see above) turned up `row_cache_size` and
  `index_summary_capacity` as off-heap (`Native.malloc`/off-heap index-summary
  bytes) true positives — a different shared budget from the two on-heap cases
  so far. The node's 251 GiB physical RAM isn't a usable ceiling for off-heap the
  way `-Xmx` is for on-heap; this would likely need a cgroup memory limit (or
  `-XX:MaxDirectMemorySize` as the actual constraint) set up first. Possibly
  closer to `bypass-playbook` territory than convergence.
- **Tighter boundary sizing** for either closed case: both were sized with
  margin to exceed the heap, not to find the minimum combination that still
  OOMs. A follow-up run could binary-search that boundary.
- **A 4th on-heap constraint**, on top of the closed 3-way case — not attempted
  this run since 3 already reached a harder outcome (crash, not just caught
  exceptions) than 2 did, so a 4th wouldn't yet add evidence either way.
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
- **How a case is run: a real Cassandra process on a node, not a unit
  test.** A run builds `cassandra-5.0.9` from source, starts the actual
  `bin/cassandra` daemon on the node with an edited `conf/cassandra.yaml`
  and a small `-Xmx`, drives it with real `cassandra-stress` workloads
  against its CQL port, and reads the outcome from the live process
  (`ps`/`jcmd`), its own `system.log`, and `dmesg` — not from Cassandra's
  JUnit/dtest suites. The closed case so far is single-node; a multi-node
  ring is only used if a case specifically needs cross-node behavior (see
  `if-check-exp/stage4-runtime-verification/environment.md` section 5 for
  ring setup).
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
- **Available nodes (updated 2026-11-02):** `pc41` (local — the session
  runs here directly, no ssh), `pc39` and `pc29` (remote, reach over ssh).
  Set up JDK/Ant/source on `pc39`/`pc29` before use if not already done.
- **Nodes:** run on whatever CloudLab node the session has — see
  `if-check-exp/stage4-runtime-verification/environment.md` for the JDK/Ant
  install and source-copy steps (same pinned `cassandra/cassandra-5.0.9/`
  tag). The first case ran on `pc41.cloudlab.umass.edu`
  (`jason92-323989`, 40 cores, 251 GiB) with Cassandra bounded to a small
  `-Xmx` — the node's physical RAM is not the experiment's budget.
