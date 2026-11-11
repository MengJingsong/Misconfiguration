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
> `cassandra/`). Paths into `capacity-enforcement-exp` follow that experiment's layout: method docs at its
> root, data under `capacity-enforcement-exp/<system>/`.

Start-here brief for a session picking up `OOM-exp`. Read this, then
[`README.md`](README.md) for the target and the two directions, then
[`_INDEX.md`](cassandra/cases/_INDEX.md) for case status.

## Status as of 2026-11-10

**Convergence is active.** The case index lists six convergence OOMs
across the custom- and default-capacity regimes, all filed before the protocol and
moved to `candidates/` as `candidate (pre-protocol)` on 2026-11-11 (one failing run
each; V1, V2, V4 unmet; their rechecks are queued as R1–R4 (P1) and R5–R6 (P2) in the
[campaign plan](cassandra/campaign-plan.md#prioritized-queue)). The original on-heap and
off-heap standing-pool surveys are complete within their historical scope.
C1, the internode receive-queue multiplicity case, is still in progress.
Disk work remains paused by request. **Bypass has its first runs:** B6
(internode queue accounting mismatch) run 1 (2026-11-10) confirmed the bypass and
reproduced heap OOM with supporting deviations; run 2 (2026-11-11) reproduced the
memory effect at default timeouts and an 8 GiB replica, mostly as GC service loss
with 2 heap OOMs in 8 arms; run 3 (2026-11-11) repeated the reserve intervention and
same-day positives. **B6 is the first verified bypass** (filed 2026-11-11 in `bypass/`):
`verified-gap · service-loss · deployment` (8 GiB replica, storage stall) and
`verified-OOM · diagnostic` (2 GiB coordinator); the 2 GiB replica condition stays candidate.
Use the [campaign plan](cassandra/campaign-plan.md) and
[current run log](cassandra/cases/_run-log.md#current-campaign-status--2026-11-06)
for current priorities and results.

**New lead sources (2026-11-10).** Besides the capacity-enforcement-exp inventory, leads now
also come from **JIRA OOM history** ([`jira-mining-playbook.md`](jira-mining-playbook.md))
and **data-flow tracing** ([`dataflow-tracing-playbook.md`](dataflow-tracing-playbook.md)).
They are lead sources, not new directions: results are still convergence,
bypass, mixed or **unprotected** (memory no check guards is in scope; protocol
amendment of 2026-11-10). Outputs go under `<system>/leads/`. Pilots J1, J2 and
F1 are queued in the [campaign plan](cassandra/campaign-plan.md#lead-source-pilots);
none has run yet.

## Current state

- **Historical custom-convergence batch:** 8 runs. Five OOMed (runs 1, 2, 6,
  7, 8), one was blocked (disk, skipped), one did not reach OOM (run 4,
  superseded), and one was void (run 5).
  - Run 1: `memtable_heap_space` + `counter_cache_size` (both config-type, both
    individually confirmed true positive in `capacity-enforcement-exp`, both on-heap):
    sized safe alone (each left ~38–39% of a 1024 MiB heap free under its own
    workload), predicted and observed to exceed the heap together — 14 genuine
    `OutOfMemoryError` throws, final forced-GC reading 96.6% of `-Xmx` with 0
    young regions left, JVM survived (caught the exceptions). Case file:
    [`cassandra/cases/candidates/memtable_heap_space+counter_cache_size.md`](cassandra/cases/candidates/memtable_heap_space+counter_cache_size.md).
  - Run 2: same two plus `key_cache_size` as a 3rd on-heap constraint (config-type
    true positive; `row_cache_size`/`index_summary_capacity` were checked and
    turned out off-heap, not a fit — see below). Smaller individual values than
    run 1 (each still 46–87% free alone), combined drove the heap to 989/1024 MiB
    (96.6%) right after a forced full GC, a genuine `OutOfMemoryError`, a 1.35 GB
    heap dump, and this time `-XX:OnOutOfMemoryError=kill -9 %p` actually fired —
    the JVM was killed, not just stressed. Case file:
    [`cassandra/cases/candidates/memtable_heap_space+counter_cache_size+key_cache_size.md`](cassandra/cases/candidates/memtable_heap_space+counter_cache_size+key_cache_size.md).
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
    [`cassandra/cases/candidates/commitlog_total_space+max_hints_size_per_host.md`](cassandra/cases/candidates/commitlog_total_space+max_hints_size_per_host.md).
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
    [`cassandra/cases/candidates/row_cache_size+index_summary_capacity.md`](cassandra/cases/candidates/row_cache_size+index_summary_capacity.md).
  - Run 5 (2026-11-03): retry of run 4's pair with a 30 m resize interval and
    concurrent workloads. **Void:** the index-summary burst wrote 0
    partitions (the stress client's `CREATE TABLE` timed out under the
    concurrent read load; found in run 6). Case file, with a correction note:
    [`cassandra/cases/candidates/row_cache_size+index_summary_capacity--run5.md`](cassandra/cases/candidates/row_cache_size+index_summary_capacity--run5.md).
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
    [`cassandra/cases/candidates/row_cache_size+index_summary_capacity--run6.md`](cassandra/cases/candidates/row_cache_size+index_summary_capacity--run6.md).
  - Run 7 (2026-11-03): `memtable_offheap_space` + `file_cache_size`, both
    new, both off-heap standing pools (off-heap `offheap_objects` memtable;
    chunk cache enabled). Same 3500 MiB cgroup budget in every arm, `-Xmx768M`.
    Each alone 78%; with the chunk cache full, a write burst got the JVM
    **kernel OOM-killed 16 s in** (anon-rss 3465 MiB). OOMed on the first try:
    both are hard standing caps, so no timing engineering was needed. Case file:
    [`cassandra/cases/candidates/memtable_offheap_space+file_cache_size.md`](cassandra/cases/candidates/memtable_offheap_space+file_cache_size.md).
  - Run 8 (2026-11-03): `DOB_MAX_RECYCLE_BYTES` + `MAX_HINT_BUFFERS`, both
    new, both JVM properties, both `ByteBuffer.allocateDirect` pools, so the
    budget is the JVM's own `-XX:MaxDirectMemorySize` (560 MiB), not a cgroup.
    2-node loopback ring (hints need a down replica; N2 killed before any
    reading). Alone 50% (hints pool at its 8-slab cap) and 70% (scratch
    buffers kept by ~44 threads at L = 8 MiB). Together: `OutOfMemoryError:
    Direct buffer memory` about 7 s into the DOB burst, then Cassandra's
    forced heap OOM and `kill -9`. The same arm with L at its default did not
    OOM (attribution control). Case file:
    [`cassandra/cases/candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md`](cassandra/cases/candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md).
  - Batch log: [`cassandra/cases/_run-log.md`](cassandra/cases/_run-log.md) —
    its "Historical shared-budget group status" table records prior
    standing-pool coverage. On-heap is **exhausted** (2-way then 3-way, escalating outcome, no 4th
    attempted since it wouldn't add evidence), off-heap is **exhausted**
    (run 8: three disjoint pairs all OOMed, no independent standing pool
    left untried),
    disk is **skipped** (2026-11-02, by request — not exhausted or blocked,
    just deliberately paused; see run 3's case file for the retry that
    remains available once un-skipped). Read it before picking a combination
    for the next run — **do not pick from disk while it is marked skipped.**
- **C1 — internode receive-queue multiplicity (campaign plan, 2026-11-09/10): in progress.**
  Three runs, all cases, harnesses and design files in
  [`cassandra/cases/candidates/internode_application_receive_queue_capacity-multiplicity/`](cassandra/cases/candidates/internode_application_receive_queue_capacity-multiplicity/).
  Run 1 (default Q): admission ceiling matched to 0.2 MiB at N=4, but N·Q ≪ noise and coordinators OOMed
  under replica fan-out. Run 2 (custom Q, victim sole replica): senders survive, but the client waits on
  the victim, so occupancy settles at ~266 MiB below the ceiling and is Q-invariant. Run 3 (fast
  co-replica, CL=ONE, fixed-rate load): reached 543 of 544 MiB of accounted
  admission capacity at N=8 and Q=4 with live senders. A sampler bug stopped
  the run after calibration. The Q/N sweeps and OOM stage remain outstanding.
  Next, verify the **coordinators'** `write_request_timeout` against the
  measured drain rate and run the matched sweeps. Proceed to the fixed-budget
  OOM stage after a reproducible live-memory increase.
- **Bypass (`bypass-playbook.md`):**
  - **B6 — internode queue accounting mismatch (2026-11-10/11): verified, runs 1–3 done.**
    Final case: [`internode_application_queue_capacity--accounting-mismatch.md`](cassandra/cases/bypass/internode_application_queue_capacity-accounting-mismatch/internode_application_queue_capacity--accounting-mismatch.md)
    (A: `verified-gap · service-loss · deployment`; B: `verified-OOM · diagnostic`; C: candidate).
    Found by tracing C1's write path (`source: flow:coordinator-write`). The internode
    send/receive queues charge on-wire bytes; a 1000-cell map mutation is 10.8 KiB on
    the wire but ≈ 213 KiB on the coordinator heap and ≈ 181 KiB on the replica heap
    (R ≈ 19.7× / 16.7×; matched blob ≈ 2.2×). The coordinator also keeps each
    `Mutation` after flush (`hintOnFailure`) until the replica answers, charged to no
    sender counter. At a 2 GiB heap: coordinator and slow replica each OOM 3/3 with
    counters ≤ 132 MiB, blob 0/3; 8 MiB endpoint reserves remove the OOM (n=1).
    Run 1 needed an injected slow replica and 60 s deadlines. **Run 2** dropped both:
    default timeouts and threads, Java client, 4 coordinators, 30 s storage stall
    (dm-delay) on the replica. Tiny-cell writes drove an 8/6 GiB replica to ≈ 99% live
    heap with ≈ 97% of an 80–123 s window in Full GC in 5/5 stall arms; heap OOM in
    2/8 stall/hang arms; blob 0 Full GCs; an 8 MiB receive endpoint reserve removed
    it (n=1). Outcome per protocol: mostly GC-driven service loss, not a
    deterministic OOM. Cases: [run 1](cassandra/cases/bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-1),
    [run 2](cassandra/cases/bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-2).
    **Run 3** (2026-11-11, [case](cassandra/cases/bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-3)):
    8 MiB endpoint reserves removed the effect 3/3 per condition, same-day positives reproduced
    except run 1's 2 GiB replica (survived at 98% live). Run 2 and run 1's 2 GiB coordinator now meet
    the promotion rule V1–V5; run 1's replica side stays candidate. The reserve protects by shedding
    (≈ 83% of writes to the slow replica dropped at the run-1 condition) and the capped 2 GiB
    coordinator still runs at 69–75% live.
    Filed 2026-11-11 (run 2's condition labelled `deployment`: hints off is an accepted setting).
    Next: JIRA check (CASSANDRA-15066 introduced these limits) before any upstream report; stall-length
    sweep (5/15/60 s); ≥ 2 slow replicas at 8 GiB.
  - **B1** (native-v5 large-request retention) remains the first planned
    if-check-inventory bypass; not started.

## Open follow-ups

- **Disk is paused by request (set 2026-11-02).** Do not retry the disk case
  or pick a new disk-group combination until this is explicitly lifted in
  `cases/_run-log.md`'s status table. When it is lifted, the
  retry needed is: (a) a bigger disk-budget mount or a smaller/throttled
  write workload so flush-and-compaction overhead doesn't itself exhaust the
  budget before commit log reaches its own target, and (b) either raising
  `phi_convict_threshold` or otherwise isolating/accounting for the
  contention-induced false-suspicion hint growth seen in the control arm —
  see the case file §3.0/§4 for exact numbers and diagnosis.
- **Current convergence work** follows the [campaign plan](cassandra/campaign-plan.md).
  The multiplicity queue continues with C1, then C3 (per-worker serialization
  buffers) and C5 (per-destination compressed hints buffers). C2 covers
  overlapping bounded reads. The historical standing-pool exclusions apply
  to the surveyed combinations and assumptions.
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
- **Next bypass work**: finish B6's open arms (above), then B1, per the
  [campaign plan](cassandra/campaign-plan.md) priority order.

## Decisions and conventions in force

- **Each playbook run is one agent, end to end**: it picks constraints/
  mechanisms, designs the test, runs it on a node it has access to, and
  files the result. No separate design-then-execute split (unlike
  `capacity-enforcement-exp` stage 3/4).
- **One run produces a batch of cases**, not one, tracked chronologically in
  the single `cases/_run-log.md` (regime labeled per run).
- **Verified means V1–V5 (protocol amendment 2026-11-11).** A case moves out of
  `candidates/` only when it meets the promotion rule in
  [`verification-protocol.md`](verification-protocol.md#verification-status-amended-2026-11-11):
  ≥ 3 failing runs of one condition, ≥ 3 matched controls, U measured apart from
  K, intervention ×3 (or documented infeasible), initiating failure kept. Statuses
  are `verified-OOM`, `verified-gap` (confirmed gap ending in service loss,
  overshoot or leak), `candidate`, `negative`, each verified one labelled
  `deployment` or `diagnostic`. The six convergence OOMs filed before 2026-11-06
  are `candidate (pre-protocol)` in `candidates/` (moved there 2026-11-11) and need
  a V1–V5 recheck before they return to `convergence/` or are used upstream. B6 is the first case filed this way (2026-11-11). **A verified case keeps one
  final case file**; its per-run case files are moved verbatim into `history.md` in
  the same folder (protocol, *Case evidence and batch status*).
- **Case files use the fixed 4-section template** each playbook specifies
  (constraints/capacity, verification solution, runtime results, conclusion
  that branches on the outcome). Keep section headings.
- **`_INDEX.md`'s table stays narrow**: short link text, one-line results,
  detail in the case file.
- **Node safety rules carried over from `capacity-enforcement-exp` stage 4**: never
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
  `capacity-enforcement-exp/cassandra/stage4-runtime-verification/environment.md` section 5 for
  the general ring-setup approach, and note the JMX-bind-address and
  resource-contention lessons in run 3's batch-log entry if reusing this
  pattern).
- **Commit and push only on request**, same as the rest of the repo.

## Where things live

- [`README.md`](README.md) — the target, the lead sources, the two directions.
- [`jira-mining-playbook.md`](jira-mining-playbook.md),
  [`dataflow-tracing-playbook.md`](dataflow-tracing-playbook.md) — how to
  produce leads from JIRA OOM reports and from tracing core data flows; their
  outputs live in `<system>/leads/`.
- [`custom-convergence-playbook.md`](custom-convergence-playbook.md),
  [`bypass-playbook.md`](bypass-playbook.md) — the agent's whole instruction
  for a run in each direction.
- [`default-convergence-playbook.md`](default-convergence-playbook.md) —
  the convergence playbook plus one restriction: every constraint stays at
  its default value (only the budget and the workload are dials). Own batch
  log at `cases/_run-log.md`. Run 1 (2026-11-04): `DOB_MAX_RECYCLE_BYTES` +
  `MAX_HINT_BUFFERS` at defaults OOMed at an explicit 192 MiB
  `MaxDirectMemorySize`. The arithmetic exclusions for on-heap and off-heap
  JNA apply to the standing-pool combinations surveyed in that batch.
- [`_INDEX.md`](cassandra/cases/_INDEX.md) — every closed case, by status.
- `cases/convergence/`, `cases/candidates/`, `cases/bypass/`, `cases/negatives/` —
  case files (status-first folders) and small raw-log excerpts; the merged
  `cases/_run-log.md` holds the chronological run log (full logs stay on the
  run node; each case file records the path).
- [`cassandra/cases/_constraint-groups.md`](cassandra/cases/_constraint-groups.md) —
  every capacity-enforcement-exp true-positive constraint, surveyed and grouped by
  shared budget (on-heap/off-heap/disk) and classified **floor / surge /
  excluded** (floor = standing pool; surge = per-item allocation with no
  global aggregate cap, used on top of a floor; the exclusion axis is "is
  there a global aggregate cap?", not "per-request vs. standing" — see the
  playbook's "Picking combinations" step 5 and the floor+surge note at the
  top of that file). Read this before re-surveying capacity-enforcement-exp from scratch
  for the next combination.
- **Available nodes (updated 2026-11-09):** `pc96` (local — the session runs
  here directly, no ssh; its full name is `pc96.cloudlab.umass.edu`, not
  `.emulab.net`; 32 cores, ~125 GiB), plus **five remote r320 nodes** (APT,
  8 cores / 16 GiB each): `apt138`, `apt140`, `apt149`, `apt179`, `apt190`
  (reach over ssh as `apt138.apt.emulab.net` etc., user **`jason92`**, via the
  shared deploy key). Plain `ssh apt138` works — `~/.ssh/config` has a
  `# setup-node: peer` block for each (user `jason92`, the deploy key); note the
  login user is `jason92`, **not** `jason`. `ssh pc96` itself needs
  `-i /proj/misconfiguration-PG0/.ssh/id_ed25519` (no config entry for the
  local node). Build JDK/Ant/source on any remote before use if not already
  done — see `environment.md`. (The earlier `pc41`/`pc39`/`pc29` allocation from
  2026-11-02, and the interim `pc264/265/268/271/323` nodes at 2 c/1 GiB that
  were too small to build or host peers, are retired.)
- **Nodes:** run on whatever CloudLab node the session has — see
  `capacity-enforcement-exp/cassandra/stage4-runtime-verification/environment.md` for the JDK/Ant
  install and source-copy steps (same pinned `systems/cassandra/source/`
  tag). The first case ran on `pc41.cloudlab.umass.edu`
  (`jason92-323989`, 40 cores, 251 GiB) with Cassandra bounded to a small
  `-Xmx` — the node's physical RAM is not the experiment's budget.
