# OOM-exp — Handoff

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

Start-here brief for a session picking up `OOM-exp`. Read this, then
[`README.md`](README.md) for the target and the two directions, then
[`_INDEX.md`](cassandra/_INDEX.md) for every closed case.

## Status: active, five cases closed (OOMed), one blocked-retryable, one closed (not reached), one void (2026-11-03)

**Direction 1 (convergence): on-heap and off-heap are both exhausted (five
OOMed cases across them), disk is paused by request with one blocked case;
Direction 2 (bypass) has not started.** `if-check-exp` is
the input (its case files and stage-4 results); this folder does not
re-derive them, only consumes them.

## Current state

- **Convergence (`custom-convergence-playbook.md`):** 8 cases run — 5 closed (OOMed: runs 1, 2, 6, 7, 8), 1 blocked (disk, skipped), 1 closed not reached (run 4, superseded), 1 void (run 5).
  - Run 1: `memtable_heap_space` + `counter_cache_size` (both config-type, both
    individually confirmed true positive in `if-check-exp`, both on-heap):
    sized safe alone (each left ~38–39% of a 1024 MiB heap free under its own
    workload), predicted and observed to exceed the heap together — 14 genuine
    `OutOfMemoryError` throws, final forced-GC reading 96.6% of `-Xmx` with 0
    young regions left, JVM survived (caught the exceptions). Case file:
    [`cassandra/cases/custom-convergence/memtable_heap_space+counter_cache_size.md`](cassandra/cases/custom-convergence/memtable_heap_space+counter_cache_size.md).
  - Run 2: same two plus `key_cache_size` as a 3rd on-heap constraint (config-type
    true positive; `row_cache_size`/`index_summary_capacity` were checked and
    turned out off-heap, not a fit — see below). Smaller individual values than
    run 1 (each still 46–87% free alone), combined drove the heap to 989/1024 MiB
    (96.6%) right after a forced full GC, a genuine `OutOfMemoryError`, a 1.35 GB
    heap dump, and this time `-XX:OnOutOfMemoryError=kill -9 %p` actually fired —
    the JVM was killed, not just stressed. Case file:
    [`cassandra/cases/custom-convergence/memtable_heap_space+counter_cache_size+key_cache_size.md`](cassandra/cases/custom-convergence/memtable_heap_space+counter_cache_size+key_cache_size.md).
  - Run 3: `commitlog_total_space` + `max_hints_size_per_host` (both disk-bound
    true positives), the first case in this folder to use a 2-node ring (a
    second node is structurally required to generate hints at all). **Blocked,
    not closed:** the control arm meant to confirm commit log is safe alone
    instead ran a dedicated 1536 MiB disk-budget mount to 100% full from
    flush/compaction overhead the sizing hadn't accounted for (real
    `FSWriteError`/`disk_failure_policy=stop`), and separately produced real
    (non-stale) hint growth in an arm meant to produce zero hints — diagnosed
    as contention-induced false suspicion from two co-located JVMs plus a
    loaded stress client on one host. The `hints_alone` and `converge` arms
    were never run. Filed as blocked/retryable, not exhausted. Case file:
    [`cassandra/cases/custom-convergence/commitlog_total_space+max_hints_size_per_host.md`](cassandra/cases/custom-convergence/commitlog_total_space+max_hints_size_per_host.md).
  - Run 4: `row_cache_size` + `index_summary_capacity`, the first off-heap/
    direct-memory case (unparks the group opened in run 2's survey). Found,
    before running anything, that `-XX:MaxDirectMemorySize` does **not**
    actually bind either constraint (both allocate via JNA `Native.malloc`,
    bypassing the JVM's own `DirectByteBuffer` accounting) — used a cgroup v2
    `memory.max` (via `systemd-run --user --scope`) as the real budget
    instead, independently confirmed to enforce a real kill-on-exceed
    ceiling. **Result: OOM not reached.** Both alone (row cache 550 MiB,
    index summary 100 MiB configured cap) stayed safe (24–29% free of a 2000
    MiB cgroup budget); the convergence arm's combined peak (90.1% of
    budget) came in notably below the naive additive prediction from the two
    alone arms (106.1%) and never crossed the budget — diagnosed as each
    constraint's own enforcement (Caffeine eviction, periodic index-summary
    resize) continuing to operate under combined load, so the two
    individually-measured "worst moments" didn't coincide when run together.
    Two earlier sizing attempts within this run's own calibration *did*
    genuinely OOM-kill the node (too many partitions for the chosen budget,
    before any resize could run) but in what was meant to be a safe control
    arm, so weren't filed as their own cases — they're the evidence behind
    the final sizing. Case file:
    [`cassandra/cases/custom-convergence/row_cache_size+index_summary_capacity.md`](cassandra/cases/custom-convergence/row_cache_size+index_summary_capacity.md).
  - Run 5 (2026-11-03): retry of run 4's pair with a 30 m resize interval and
    concurrent workloads. **Void:** the index-summary burst wrote 0
    partitions (the stress client's `CREATE TABLE` timed out under the
    concurrent read load; found in run 6). Case file, with a correction note:
    [`cassandra/cases/custom-convergence/row_cache_size+index_summary_capacity--run5.md`](cassandra/cases/custom-convergence/row_cache_size+index_summary_capacity--run5.md).
  - Run 6 (2026-11-03): both retries on the same pair, 120 m resize interval,
    `isc.t` pre-created with `cqlsh`. **Schedule B (row cache filled to 550
    MiB first, then a 1.5M-partition burst) OOMed:** kernel cgroup OOM-kill
    at 1973 MiB anon of a 2000 MiB budget, during the post-burst
    flush/compaction; alone arms 78% / 80%. **Schedule A (concurrent)**
    peaked at 93% with no kill, because the burst and its compaction finished
    long before the row cache filled. With a 1-minute resize (addendum arm
    C), no off-heap kill (93%), but the JVM died of an unattributed Java heap
    `OutOfMemoryError` (heap dump kept on the node, unanalyzed). Run 4 is
    superseded by run 6. Pair closed as OOMed. Case file:
    [`cassandra/cases/custom-convergence/row_cache_size+index_summary_capacity--run6.md`](cassandra/cases/custom-convergence/row_cache_size+index_summary_capacity--run6.md).
  - Run 7 (2026-11-03): `memtable_offheap_space` + `file_cache_size`, both
    new, both off-heap standing pools (off-heap `offheap_objects` memtable;
    chunk cache enabled). Same 3500 MiB cgroup budget in every arm, `-Xmx768M`.
    Each alone 78%; with the chunk cache full, a write burst got the JVM
    **kernel OOM-killed 16 s in** (anon-rss 3465 MiB). OOMed on the first try:
    both are hard standing caps, so no timing engineering was needed. Case file:
    [`cassandra/cases/custom-convergence/memtable_offheap_space+file_cache_size.md`](cassandra/cases/custom-convergence/memtable_offheap_space+file_cache_size.md).
  - Run 8 (2026-11-03): `DOB_MAX_RECYCLE_BYTES` + `MAX_HINT_BUFFERS`, both
    new, both JVM properties, both `ByteBuffer.allocateDirect` pools, so the
    budget is the JVM's own `-XX:MaxDirectMemorySize` (560 MiB), not a cgroup.
    2-node loopback ring (hints need a down replica; N2 killed before any
    reading). Alone 50% (hints pool at its 8-slab cap) and 70% (scratch
    buffers kept by ~44 threads at L = 8 MiB). Together: `OutOfMemoryError:
    Direct buffer memory` about 7 s into the DOB burst, then Cassandra's
    forced heap OOM and `kill -9`. The same arm with L at its default did not
    OOM (attribution control). Case file:
    [`cassandra/cases/custom-convergence/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS.md`](cassandra/cases/custom-convergence/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS.md).
  - Batch log: [`cassandra/cases/custom-convergence/_batch-log.md`](cassandra/cases/custom-convergence/_batch-log.md) —
    its "Shared-budget group status" table is the dedup record: on-heap is
    **exhausted** (2-way then 3-way, escalating outcome, no 4th
    attempted since it wouldn't add evidence), off-heap is **exhausted**
    (run 8: three disjoint pairs all OOMed, no independent standing pool
    left untried),
    disk is **skipped** (2026-11-02, by request — not exhausted or blocked,
    just deliberately paused; see run 3's case file for the retry that
    remains available once un-skipped). Read it before picking a combination
    for the next run — **do not pick from disk while it is marked skipped.**
- **Bypass (`bypass-playbook.md`):** not started. No candidate picked yet.

## Open follow-ups

- **Disk is paused by request (set 2026-11-02).** Do not retry the disk case
  or pick a new disk-group combination until this is explicitly lifted in
  `cases/custom-convergence/_batch-log.md`'s status table. When it is lifted, the
  retry needed is: (a) a bigger disk-budget mount or a smaller/throttled
  write workload so flush-and-compaction overhead doesn't itself exhaust the
  budget before commit log reaches its own target, and (b) either raising
  `phi_convict_threshold` or otherwise isolating/accounting for the
  contention-induced false-suspicion hint growth seen in the control arm —
  see the case file §3.0/§4 for exact numbers and diagnosis.
- **Off-heap group is exhausted (run 8).** Three disjoint pairs OOMed
  (runs 6, 7, 8). The rows left in `_constraint-groups.md` are not
  independent standing pools (same pool as one already used, or
  in-flight-only networking buffers). Reopen only for a different question:
  a cross-pair of already-used `allocateDirect` pools under
  `MaxDirectMemorySize` (e.g. `DOB_MAX_RECYCLE_BYTES` + `file_cache_size`),
  a 3-way case, or the minimum boundary.
- **Next convergence work needs a decision**: both memory groups are
  exhausted and disk is skipped by request, so the next convergence batch
  needs either disk un-skipped (run 3's retry is ready), the causal-chain
  scope opened, or one of the reopen questions above. Otherwise move to the
  first bypass case.
- **Harness lesson (run 8):** `cassandra-stress write` always sends
  `CREATE KEYSPACE`, which times out under a concurrent load; use
  `cassandra-stress user` profiles without schema definitions for any
  concurrent workload (run 8's `dob.yaml`/`hints.yaml`).
- **Tighter boundary sizing** for either closed heap case: both were sized with
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
  build in or add files to the repo's `systems/cassandra/source/`, never
  fill `/proj` (shared NFS), node data/commit log/hints go on local disk,
  stop every process a run starts and verify none is left.
- **How a case is run: a real Cassandra process on a node, not a unit
  test.** A run builds `cassandra-5.0.9` from source, starts the actual
  `bin/cassandra` daemon on the node with an edited `conf/cassandra.yaml`
  and a small `-Xmx`, drives it with real `cassandra-stress` workloads
  against its CQL port, and reads the outcome from the live process
  (`ps`/`jcmd`), its own `system.log`, and `dmesg` — not from Cassandra's
  JUnit/dtest suites. Both closed cases are single-node; a multi-node ring
  is only used if a case specifically needs cross-node behavior (run 3's
  `max_hints_size_per_host` did — hints require an unreachable replica,
  which a single node structurally cannot produce — so it used a 2-node
  loopback ring, 127.0.0.2/127.0.0.3 on one physical host; see
  `if-check-exp/cassandra/stage4-runtime-verification/environment.md` section 5 for
  the general ring-setup approach, and note the JMX-bind-address and
  resource-contention lessons in run 3's batch-log entry if reusing this
  pattern).
- **Commit and push only on request**, same as the rest of the repo.

## Where things live

- [`README.md`](README.md) — the target, the two directions.
- [`custom-convergence-playbook.md`](custom-convergence-playbook.md),
  [`bypass-playbook.md`](bypass-playbook.md) — the agent's whole instruction
  for a run in each direction.
- [`default-convergence-playbook.md`](default-convergence-playbook.md) —
  the convergence playbook plus one restriction: every constraint stays at
  its default value (only the budget and the workload are dials). Own batch
  log at `cases/default-convergence/_batch-log.md`. Run 1 (2026-11-04): `DOB_MAX_RECYCLE_BYTES` + `MAX_HINT_BUFFERS` at defaults **OOMed, strict default** (192 MiB `MaxDirectMemorySize`, narrow window); on-heap and off-heap JNA judged **cannot converge at defaults** by arithmetic.
- [`_INDEX.md`](cassandra/_INDEX.md) — every closed case, by direction.
- `cases/custom-convergence/`, `cases/bypass/` — case files, batch logs, harness
  scripts and small raw-log excerpts (full logs stay on the run node; each
  case file records the path).
- [`cassandra/cases/custom-convergence/_constraint-groups.md`](cassandra/cases/custom-convergence/_constraint-groups.md) —
  every if-check-exp true-positive constraint, surveyed and grouped by
  shared budget (on-heap/off-heap/disk) and classified **floor / surge /
  excluded** (floor = standing pool; surge = per-item allocation with no
  global aggregate cap, used on top of a floor; the exclusion axis is "is
  there a global aggregate cap?", not "per-request vs. standing" — see the
  playbook's "Picking combinations" step 5 and the floor+surge note at the
  top of that file). Read this before re-surveying if-check-exp from scratch
  for the next combination.
- **Available nodes (updated 2026-11-09):** `pc96` (local — the session runs
  here directly, no ssh; its full name is `pc96.cloudlab.umass.edu`, not
  `.emulab.net`), and `pc264`, `pc265`, `pc268`, `pc271`, `pc323` (remote,
  reach over ssh as `pc264.emulab.net` etc., user `jason92`, via the shared
  deploy key). SSH to all five remotes is confirmed working; `ssh pc96` itself
  needs `-i /proj/misconfiguration-PG0/.ssh/id_ed25519` (no `~/.ssh/config`
  entry for the local node). Set up JDK/Ant/source on any remote before use if
  not already done. (The earlier `pc41`/`pc39`/`pc29` allocation from
  2026-11-02 is retired.)
- **Nodes:** run on whatever CloudLab node the session has — see
  `if-check-exp/cassandra/stage4-runtime-verification/environment.md` for the JDK/Ant
  install and source-copy steps (same pinned `systems/cassandra/source/`
  tag). The first case ran on `pc41.cloudlab.umass.edu`
  (`jason92-323989`, 40 cores, 251 GiB) with Cassandra bounded to a small
  `-Xmx` — the node's physical RAM is not the experiment's budget.
