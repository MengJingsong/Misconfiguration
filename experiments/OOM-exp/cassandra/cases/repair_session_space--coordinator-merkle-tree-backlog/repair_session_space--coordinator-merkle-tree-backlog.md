# C7 — repair_session_space / concurrent_merkle_tree_requests: the repair coordinator holds the off-heap Merkle trees of every (session × table) at once  <!-- file: cassandra/cases/repair_session_space--coordinator-merkle-tree-backlog/repair_session_space--coordinator-merkle-tree-backlog.md -->

| Field | Value |
|---|---|
| Case ID | `C7` (C = convergence, the ID assigned with the pick; README "ID prefixes"). Predicted class by the protocol's measurement table: **convergence** of per-validation tree sets, each within its `repair_session_space / RF` contract, under an **unprotected configuration** (the aggregate control `concurrent_merkle_tree_requests` ships at 0 = unlimited) — stage 2 labels it from the readings |
| From | `OC-6` of the phase 1 OOM candidate list |
| Phase-1 case file | [`repair_session_space-initHelper-max--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/repair_session_space-initHelper-max--autonomous.md) (also [`repair_session_space-split-maxsize--guided`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/repair_session_space-split-maxsize--guided.md)); stage-4 evidence [`results/repair_session_space-initHelper-max--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/repair_session_space-initHelper-max--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9). On the nodes: R7's aarch64 build `/mydata/s4/r7-w1/cassandra` (ms0640 copy: `git describe` tag `cassandra-5.0.9`, `git status` clean; jar `build/apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `2a9cbd5ce9f81687c6406aaa34dad4ed1404482051496fef6e3c177da2c26712` on **both** ms0625 and ms0640, checked read-only 2026-11-18 08:05), OpenJDK 11.0.33, aarch64 |
| Stage 1 (design) | OOM-agent stage-1 session (workflow), 2026-11-18 ~07:50–08:30 America/New_York; nothing run (read-only checks of ms0625 / ms0640 and read-only JIRA REST searches only) |
| Stage 2 (verify) | fresh OOM-agent stage-2 session (workflow), 2026-11-18 08:13–10:40 America/New_York on ms0625 + ms0640 (aarch64); freeze hash checked (matches); 9 counted runs (C ×3, T ×3, I ×3), all processes stopped 10:30 |
| Verdict | **true positive** — `verified-OOM · deployment` (convergence under an unprotected default: `concurrent_merkle_tree_requests` 0) |

## Summary

- **Conclusion:** **true positive** (`verified-OOM · deployment`). At shipped defaults with a 2 GiB heap and 2 GiB direct
  limit on the coordinator, `nodetool repair --full` of 106 small tables killed the coordinator with
  `OutOfMemoryError: Direct buffer memory` in `MerkleTree.allocate` in 3/3 runs (+139–154 s, 164 tree sets held, dumps: 96 %
  of live direct memory in off-heap Merkle trees); 4 tables completed 3/3 (direct peak ≤ 235 MiB), and
  `concurrent_merkle_tree_requests: 1` completed the 106-table repair 3/3 (direct peak ≤ 106 MiB, 17–18 min).
- **Root cause (confirmed by the runs):** `repair_session_space` (heap/16) bounds the Merkle trees built for **one** validation
  request (one table × one session's ranges) to `repair_session_space / RF`, but the coordinator of a repair command receives
  one such tree set from every replica for every (session × table) job, and the aggregate control,
  `concurrent_merkle_tree_requests`, ships at 0 (no limit), so every job requests its trees at once. A tree set stays in
  direct memory on the coordinator until **all** RF sets of its job have arrived. Because the coordinator is a replica in
  **every** session while each peer is in only some, the coordinator's own validations fall behind and the peers' trees
  pile up: with 4 nodes, RF 2 and vnodes the coordinator validates ≈ 3 × as many requests as each peer, so ≈ 2 × T remote
  tree sets wait at once for T tables (measured: 164 sets held when the 2 GiB limit was hit at T = 106, below the 2 T = 212
  the backlog would have reached). Each set stays inside its own contract (≈ 15.6 MiB vs 64 MiB); only their sum is unbounded.
- **Design in one line:** a 4-instance 5.0.9 cluster on ms0625 + ms0640 (two instances per machine, alias IPs), keyspace
  RF 2, 100–150 identical small tables (1 M partitions each, cloned by hard links), all defaults; `nodetool repair --full`
  of all T tables from the coordinator with a 2 GiB heap and a 2 GiB direct limit; expect `OutOfMemoryError` (direct buffer
  memory) on the coordinator 3/3; matched control = the same command for 4 tables (no OOM); intervention =
  `concurrent_merkle_tree_requests: 1` (no OOM, repair completes); then search the direct limit upward (3, 4 GiB).

## 1. Candidate

**Candidate row (quoted from `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`):**

> | OC-6 | 2026-11-12 | `repair_session_space-initHelper-max--autonomous` | legacy | [N5; L10; lead list ×6 (blind, E3/E4): `repair_session_space-initHelper-max`, budget ledger heap/direct, `repair_session_space-split-maxsize--guided`, `repair_session_space-applySimpleConfig-…`, `repair-session-space-histogram-add-values`, `repair_session_space-setrepairsessionspaceinmib-sizeinmib-2`] `repair_session_space` (heap/16) applies per validation and the default `concurrent_merkle_tree_requests: 0` submits every session and table at once (`RepairCoordinator.java:127`), so the coordinator holds ≈ heap/16 of trees in direct memory per in-flight (session, table) with no total cap: 8–16 in flight ≈ 0.5–1 × heap (timing-dependent; the yaml warns of OOM). | CP-7 | picked: C7 |

**Phase-1 constraint and check.** `repair_session_space` (`Config.java:207-208`, MiB; default `null` →
`max(1, maxHeap / 16 MiB)`, `DatabaseDescriptor.java:609-610`). Its check is the tree depth: `ValidationManager.createMerkleTrees`
(`ValidationManager.java:54-91`) sets `availableBytes = repair_session_space × 1048576 / RF` (`:61-63`, with the comment "the
repair coordinator must hold RF trees in memory at once"), gives each range `ratio × availableBytes` (`:67-71`), derives
`estimatedMaxDepth = MerkleTree.estimatedMaxDepthForBytes(...)` (`:74`, i.e. `floor(log2((bytes + inner) / (leaf + inner)))`,
`MerkleTree.java:1520-1541`), caps it at `repair_session_max_tree_depth` (20, `DatabaseDescriptor.java:606`) and at
`ceil(log2(partitions in range))` (`:79`), and builds a tree of `2^depth` leaves (`:80`); `MerkleTree.initHelper` stops the
recursion at that depth (`MerkleTree.java:151`, the phase-1 entry line).

**What stage 4 measured** (phase-1 `initHelper-max` results, advisor's Mac, arm64, JDK 11, 2026-10-27, outcome **true positive /
caps**): unit tier S = 1…16 MiB → 2^12…2^16 leaves, tree heap 0.590–0.594 × S; cluster tier (3 loopback nodes, RF 3,
3 M partitions, `repair -full -pr`), every replica built exactly `2^d` leaves, derived heap **0.586 × S/RF** for S ≤ 64 and the
default (128 MiB at a 2 GiB heap: 131,072 leaves, 26.2 MB per tree). So the per-validation cap holds; the bytes-per-leaf+inner
pair `c` that sets the depth lies in (170, 256] B on that JVM. Stage 4 explicitly did **not** measure the coordinator's off-heap
copies (its §4.2 part 6 "Gap"), nor more than one table. The companion `split-maxsize--guided` case (order-preserving `split()`
path) is also true positive / caps; it does not apply here (Murmur3 uses `init()`).

**Correction to the OC-6 magnitude.** The coordinator does not hold heap/16 per job: the trees it holds are the off-heap form,
`(2^d − 1) × 50 B + 2^d × 32 B ≈ 82 B × 2^d` for Murmur3 (`MerkleTree.java:799-802`, inner = 4 + 4 + 32 + 2 + 8 B at
`:1450-1456`, leaf = 32 B at `:1160-1163`), while `2^d` is sized from the **on-heap** cost `c ≈ 200 B`. One tree set is therefore
≤ 0.41 × S/RF (≈ 0.2–0.4 × S/RF), and one job (RF sets) ≤ 0.41 × S. The candidate's direction is unchanged; the multiplicity needed
is larger (§2.4).

**JIRA prior art** (read only; nothing posted). Sources: `stage5-oom-clue-find/jira-oom-survey.csv` (rows with `repair` /
`merkle`), and JIRA REST searches on 2026-11-18 (`text ~ "merkle" AND text ~ "OOM"` → 11 hits; `text ~
"concurrent_merkle_tree_requests"` → 29; `text ~ "repair_session_space"` → 39; `text ~ "merkle" AND text ~ "direct buffer
memory"` → 8). Relevant:

| Key | Status | What it says | Bearing |
|---|---|---|---|
| CASSANDRA-14096 | Fixed 3.0.19/3.11.5/4.0 | coordinator OOM holding trees for all ranges × replicas (256 vnodes, RF 3) | introduced `repair_session_space` (per validation) |
| CASSANDRA-15202 | Fixed 4.0 | deserialize Merkle trees off heap on the coordinator | moved the multiplicity to direct memory; no total cap |
| CASSANDRA-17787 | Duplicate (of 19336) | "`nodetool repair -pr --full` on a keyspace with a few hundred tables will cause a direct memory OOM … Adjusting repair_session_space_in_mb does not seem to help … holding many _remote_ trees" | the exact shape of this case (many tables, remote trees, direct OOM) |
| CASSANDRA-19336 | Fixed 4.0.13/4.1.5/5.0-rc1 | per-validation limit × simultaneous requests (11 nodes, RF 3, 256 tokens → 132 requests) exceeds `repair_session_space`; fix adds `concurrent_merkle_tree_requests` **defaulting to unbounded "so it keeps the previous behaviour"** | the fix is opt-in; 5.0.9 ships `0` (`Config.java:210`, `cassandra.yaml:861`) |
| CASSANDRA-18762 | Cannot Reproduce | direct-buffer OOM after many off-heap trees (4.0, 16 GB heap) | same family, no repro |
| CASSANDRA-16909 | Unresolved (epic) | lists the unbounded in-flight trees as a known repair problem | open |
| CASSANDRA-20565 | Not A Bug | kernel OOM kill during `repair --full` (9 nodes, Xmx8G, direct 12g) | possibly the same family; not attributed |

**Verdict: `documented` / `known-open` at defaults** — the mechanism is known and the shipped `cassandra.yaml:842-861` says
"There isn't a limit by default for backwards compatibility, but this can produce OOM for commands repairing multiple tables
or multiple virtual nodes". The fix (19336) is opt-in, so 5.0.9 at defaults is **not** known-fixed; the case is a valid
(non-control) pick. No JIRA reproduction at defaults with measured attribution exists (17787 / 18762 / 20565 have none). The
interpretation is an **intentional exception / configuration-sizing gap** (an aggregate control that ships disabled and is
documented as risky), not a suspected implementation defect.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

1. `nodetool repair --full <ks> <tables…>` (default parallelism `PARALLEL`, `tools/nodetool/Repair.java:171`; job threads 1) reaches
   `RepairCoordinator`, which builds `validationScheduler = Scheduler.build(concurrent_merkle_tree_requests)`
   (`RepairCoordinator.java:127`); `0` gives a `NoopScheduler` that runs every task at once (`Scheduler.java`, `build` and
   `NoopScheduler.schedule`).
2. The coordinator groups its ranges by replica set into `CommonRange`s (`RepairCoordinator.java:490-507`) and starts **one
   `RepairSession` per common range**, all at once (`AbstractRepairTask.java:66-79`). Each session starts one `RepairJob` per
   table (`RepairSession.java:339-343`) on the `Repair#<cmd>` executor with `jobThreads` (default 1) threads
   (`RepairCoordinator.java:482-487`); `RepairJob.run` is non-blocking (it only wires futures), so all S × T jobs start in
   milliseconds.
3. Each job schedules "validation + sync-task creation" through the scheduler (`RepairJob.java:195-197`); with no limit, every job
   sends `VALIDATION_REQ` to all its replicas (`RepairJob.java:238-262`, `sendValidationRequest` at `:493-509`), the coordinator included.
4. Each replica queues the requests on its validation executor (`concurrent_validations` 0 → `concurrent_compactors`,
   `DatabaseDescriptor.java:1073-1075`; `concurrent_compactors` = min(8, max(2, min(cores, data dirs))) = **2** with one data
   directory, `:777-778`) and builds one on-heap tree set of ≤ `repair_session_space / RF` per request (§1).
5. On the coordinator, its **own** tree set is moved off heap (`Validator.java:295-306` → `MerkleTree.tryMoveOffHeap/moveOffHeap`,
   `MerkleTree.java:769-785` → `allocate`, `ByteBuffer.allocateDirect`, `:747-755`); each **remote** set is deserialized straight
   into a direct buffer (`MerkleTree.java:757-761`, `:787-792`) on the single-threaded `ANTI_ENTROPY` stage (`Verb.java:165`,
   `Stage.java:51`) when `use_offheap_merkle_trees: true` (default, `Config.java:212`) and the partitioner is Murmur3.
6. The set waits in its `ValidationTask` until **all** replicas of that job have answered; only then `createStandardSyncTasks`
   diffs the sets and releases them (`RepairJob.java:306-357`, `trees.release()` at `:355`, `:357`; `ValidationTask.java:71-80`).
7. The coordinator is a replica in every session; each peer is in only the sessions it shares with the coordinator. With 4
   nodes, RF 2 and 16 vnodes, the coordinator's ranges fall into **3** common ranges (one per peer), so it validates 3 T requests
   on 2 threads while each peer validates T requests of the same size: the peers finish ≈ 3 × sooner and their trees wait for
   the coordinator's own. Peak held ≈ **2 T remote tree sets** (3 T received, ≈ T released when the peers are done).

**Direction:** convergence (many per-validation tree sets, each within its contract, exceed the direct budget together) under an
**unprotected configuration** (the aggregate control is disabled by default). Technique note:
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) (multiplicity at defaults) with the combo
playbook's "multiplicity" step (tables × sessions). No fault is injected; the skew comes from the topology.

### 2.2 Protection map

| Domain | Allocation and owner | Local contract (C) | Scope and multiplicity | Aggregate coverage | Lifetime | Budget |
|---|---|---|---|---|---|---|
| D1 coordinator off-heap tree sets (**claimed holder**) | `MerkleTree.allocate` → `ByteBuffer.allocateDirect` (`MerkleTree.java:747-755`); owners `OffHeapInner/OffHeapLeaf` under `MerkleTrees` in a `TreeResponse` of a `ValidationTask` | per set: depth from `repair_session_space × 2^20 / RF` (`ValidationManager.java:61-80`), so ≤ 82 B × `2^d` with `2^d × c ≤ S/RF` (≤ 0.41 × S/RF off heap); per job RF sets (the code's own comment) | one set per (session × table × replica); sessions = common ranges (3 here), tables = T | `concurrent_merkle_tree_requests` (`Config.java:210`): **0 = unlimited (default)** → none | from receipt until all RF sets of the job arrive and are diffed (`RepairJob.java:355-357`), or abort | `-XX:MaxDirectMemorySize` of the coordinator (JDK `Bits` counter) |
| D2 replica on-heap validation trees (coordinator's own validations) | `MerkleTree.init` / `OnHeapInner`, `OnHeapLeaf` (`MerkleTree.java:136-160`) | ≤ S/RF heap per validation (stage 4: 0.586 × S/RF) | ≤ `concurrent_validations` = 2 at once | validation executor size | until moved off heap | heap (2 GiB) |
| D3 inbound large-message buffers (serialized remote sets waiting for `ANTI_ENTROPY`) | internode inbound buffers, direct | `internode_application_receive_queue_capacity` 4 MiB per connection | 3 peer connections | endpoint reserve 128 MiB, global reserve 512 MiB (`Config.java:257-261`) | until deserialized | direct |
| D4 networking `BufferPool` | `BufferPool` chunks (`BufferPool.java:460`, `:1095-1101`, `allocateDirect`) | `networking_cache_size` = min(128, heap/16) = 128 MiB (`DatabaseDescriptor.java:573-574`) | process | pool cap (overflow allocations outside it, transient) | pooled | direct |
| D5 chunk cache | `file_cache_size` 512 MiB pool | **off**: `file_cache_enabled: false` default (`cassandra.yaml:742`, `Config.java:499`) | — | — | — | direct (0 here) |

The scope that matters (fixed before the run): each D1 set is compared with its **per-validation** contract S/RF (expected
U ≤ C: no bypass), and the D1 sum with the **direct budget**, which no capacity setting covers at defaults. Count controls
(D1's tree depth) are eligible because the per-leaf off-heap footprint is fixed (82 B) and the allocation sizes are logged.

### 2.3 Configuration and budget audit

- **Source/build:** stock 5.0.9, R7's aarch64 build (header), no patches, Byteman or agents. Stage 2 copies it to
  `/mydata/s4/cassandra-base` on each node (`cp -a /mydata/s4/r7-w1/cassandra /mydata/s4/cassandra-base`, then checks the jar
  sha256 above; never runs `ant` there; never touches `/mydata/s4/r7-w1`).
- **Nodes:** ms0625 (`10.10.1.1`) and ms0640 (`10.10.1.2`), Utah m400, **aarch64**, 8 cores, 62 GiB, Ubuntu 22.04, cgroup v2,
  swap 8 GiB (kept at 0 for every Cassandra JVM with `systemd-run --user --scope -p MemorySwapMax=0`), JDK 11.0.33, G1 (the
  `jvm11-server.options` default). `/mydata` free 17 GiB (ms0625) / 18 GiB (ms0640). Alias IPs `10.10.1.81` (ms0625) and
  `10.10.1.82` (ms0640) were free on 2026-11-18 08:07 (ping); re-check before `ip addr add`.
- **Capacity constraints (all shipped defaults, V6), resolved at heap 2 GiB:** `repair_session_space` = 2048/16 = **128 MiB**
  (G1 `maxMemory` = Xmx; stage 2 reads it back over JMX `org.apache.cassandra.db:type=RepairService` `RepairSessionSpaceInMiB`);
  `concurrent_merkle_tree_requests` **0**; `use_offheap_merkle_trees` **true**; `repair_session_max_tree_depth` 20 (deprecated,
  resolved); `concurrent_compactors` 2 → `concurrent_validations` 2; `networking_cache_size` 128 MiB; `file_cache_enabled` false;
  internode receive capacity 4 MiB / 128 MiB / 512 MiB; `num_tokens` 16, `allocate_tokens_for_local_replication_factor` 3;
  `tables_warn_threshold` / `tables_fail_threshold` −1 (the deprecated `table_count_warn_threshold` is not set).
- **Environment keys changed (not capacities):** `cluster_name: 'c7'`, `listen_address` / `rpc_address` (instance IP), `seeds:
  "10.10.1.1:7000"`, data / commitlog / hints / saved_caches / cdc_raw directories under the instance dir,
  `auto_bootstrap: false` (fresh empty cluster; tokens are still chosen by the default allocator path on first start), JMX
  port 7199 (`10.10.1.1`, `10.10.1.2` instances) / 7299 (alias instances) in the instance's `cassandra-env.sh`. Snitch stays
  `SimpleSnitch` (dc `datacenter1`). Everything else is the shipped yaml (`yaml.diff` per instance kept in the run dir).
- **Topology deviation (environment, disclosed):** 4 instances on 2 machines (two per machine at alias IPs), as R7 did on the same
  nodes. Keyspace `c7` = `NetworkTopologyStrategy {'datacenter1': 2}` (RF 2 is a keyspace choice, not a capacity constraint).
- **Budgets:** victim = the repair coordinator `n1` (ms0625, `10.10.1.1`): `MAX_HEAP_SIZE=2048M` (heap 2 GiB) and
  `MAX_DIRECT_MEMORY_SIZE` = **D** ∈ {2048 (primary), 3072, 4096} MiB (the documented `cassandra-env.sh` override). Peers `n2`,
  `n3`, `n4`: heap 2048M, direct 4096M explicitly (non-binding; otherwise `cassandra-env.sh` would resolve ¼ RAM), heap dumps off
  (`-XX:-HeapDumpOnOutOfMemoryError`). Victim cgroup `MemoryMax=24G` (safety only, non-binding), swap 0.
- **V7 argument.** What the system resolves by itself: on these 62 GiB nodes `cassandra-env.sh` gives heap 15,872 MiB and direct
  7,936 MiB; for a 4 GiB-RAM node heap 2,048 / direct 1,024 MiB; for an 8 GiB node 4,096 / 2,048 MiB. The claimed node is a
  4–8 GiB-RAM class node; heap 2 GiB with direct 2 GiB is at or above what `cassandra-env.sh` resolves for that class, and both
  are ≥ 512 MiB, so the standing budget rule (2026-11-11) applies without a per-case review; 2 GiB is the ideal value. The search
  then raises D (3, 4 GiB) at the fixed heap and T (§2.7). No container limit is part of the budget.

### 2.4 Ceiling arithmetic

Per remote tree set at the defaults above (RF 2, S = 128 MiB → per request 64 MiB on-heap budget):

- Data: P = 1,000,000 partitions per table; each of the coordinator's 3 sessions covers ≈ P/6 ≈ 167 k partitions per table,
  split over ≈ 10–11 vnode ranges (≈ 15.6 k each on average).
- Per range: budget leaves = `floor(log2(n_r × 402 B / c))` (64 MiB / 167 k ≈ 402 B per partition), partition cap
  `ceil(log2 n_r)`. With c ≈ 200 B the partition cap binds and leaves = `2^ceil(log2 n_r)` ∈ [n_r, 2 n_r); with c up to 256 B
  some ranges get half that. Expected leaves per set ≈ 0.72–1.44 × 167 k = 120 k–240 k.
- Off-heap per set: **m ≈ 82 B × leaves ≈ 10–20 MB** (central 15 MB); per-set contract on heap 64 MiB, so U/C (off-heap vs the
  S/RF figure) ≈ 0.15–0.3, i.e. every set is well inside its contract.

Aggregate on the coordinator: peak held ≈ 2 T × m (§2.1 step 7) + baseline (heap-independent direct: networking pool ≤ 128 MiB,
D3 transient ≤ 512 MiB worst case, reader buffers; measured idle direct expected 20–150 MiB). For T = 100 and m = 15 MB:
≈ 3.0 GB + baseline > 2 GiB; the 2 GiB limit is crossed after ≈ (2048 − baseline) / m ≈ 120 sets. No capacity setting bounds the
sum, so the ceiling at defaults is "unbounded in T × sessions": convergence is feasible at any acceptable budget for a large
enough T. Control (T = 4): ≤ 2 × 4 × 20 MB + baseline ≈ 0.3 GB < 0.7 × 2 GiB (30 % margin). Intervention
(`concurrent_merkle_tree_requests: 1`): ≤ one job = 2 sets ≤ 40 MB.

### 2.5 Workload and environment

All node work under `/mydata/s4/c7/` on each node (instance dirs `inst/<n>`, runs `runs/<run>`, helpers `h/`); the harness
source in this case folder's `harness/` (adapted from R7's `ctl.sh`, `node.sh`, `U1R2Sample.java`, `hprof_direct.py`,
`alias.sh` in [`../concurrent_writes+max_mutation_size--inflight-DOB-fill-R7/harness/`](../concurrent_writes+max_mutation_size--inflight-DOB-fill-R7/harness/),
copies, not edits). Data, commit logs, dumps and logs on `/mydata` (local disk), not NFS.

| Instance | Machine | IP | JMX | Role |
|---|---|---|---|---|
| `n1` | ms0625 | 10.10.1.1 | 7199 | seed, **repair coordinator, victim** (budget D) |
| `n3` | ms0625 | 10.10.1.81 (alias) | 7299 | peer |
| `n2` | ms0640 | 10.10.1.2 | 7199 | peer |
| `n4` | ms0640 | 10.10.1.82 (alias) | 7299 | peer |

**Step A — base and cluster (once, ≈ 15 min).**
1. On both nodes: check nothing runs (`ps -eo cmd | grep '[C]assandraDaemon'`), `df -h /mydata` ≥ 12 GiB free; copy the base
   (§2.3); `sudo -n ip addr add 10.10.1.81/24 dev enp1s0d1` on ms0625 and `10.10.1.82/24` on ms0640 after a failed ping.
2. Generate the 4 instance confs (§2.3 keys only). Start `n1`, wait for `Startup complete` / native port open, then `n2`, `n3`,
   `n4` one at a time (each waits for the previous to show `UN` in `nodetool status`), so the default token allocator
   runs on each. Save `nodetool ring` (64 tokens) to the run log.

**Step B — data (once, ≈ 15 min).**
1. `tools/bin/cassandra-stress write n=1000000 cl=ALL -col 'n=FIXED(1)' 'size=FIXED(8)' -schema keyspace=c7
   'replication(strategy=NetworkTopologyStrategy,datacenter1=2)' -rate threads=64 -mode native cql3 protocolVersion=4
   -node 10.10.1.1,10.10.1.2` (from ms0625; creates `c7.standard1`, keys 1..1,000,000 sequential, one 8-byte column).
2. `nodetool flush c7` and `nodetool compact c7 standard1` on all 4 (one SSTable per instance); `nodetool repair --full c7
   standard1` once from `n1` with stock settings (makes replicas identical; not a reading); record
   `nodetool tablestats c7.standard1` (partitions ≈ 500 k per instance).
3. Create 149 clones `c7.s001 … c7.s149` with the exact `DESCRIBE TABLE c7.standard1` DDL (name replaced), one `cqlsh -f` file;
   `nodetool describecluster` shows one schema version.
4. Drain and stop all 4; on each instance hard-link the standard1 SSTable components into every clone directory
   (`ln data/c7/standard1-*/nb-<gen>-big-* data/c7/sNNN-*/`); SSTables are immutable and full repair of identical data does not
   rewrite them (no streaming, no anticompaction), so links keep disk use at ≈ 1 × (≈ 30–40 MB per instance). Start all 4 (n1
   first). Check `nodetool tablestats c7` on n1: 150 tables, each with the standard1 partition estimate; record the link count
   (`stat -c %h` = 150) of one Data.db as the data-integrity check, re-read before every run (a change → copy instead of link,
   recorded as an amendment).

**Step C — one run (clean start, ≈ 7–10 min).** `run.sh <run-id> <arm> <D> <T>`:
1. Stop all 4 instances (PIDs, `ctl.sh stop`); delete `n1`'s old `logs/`, `dumps/`, commit log of the previous run (data stays).
2. Write the arm's yaml (intervention only: `concurrent_merkle_tree_requests: 1` on `n1`; peers never change). Start `n1` with
   heap 2048M / direct D, then `n2`, `n3`, `n4` in parallel; wait until all are `UN`, `nodetool compactionstats` shows 0 pending on
   all, and 60 s idle have passed.
3. Read back on `n1` (JMX): `RepairSessionSpaceInMiB` (expect 128), `ConcurrentMerkleTreeRequests` (0, or 1 for I),
   `UseOffheapMerkleTrees` (true), `nodetool getconcurrentcompactors` (2), `MaxDirectMemorySize` / `MaxHeapSize` from
   `jcmd <pid> VM.flags`. A mismatch stops the run (invalid).
4. Start the samplers (§2.6), then on ms0625: `timeout 1200 nodetool -h 127.0.0.1 -p 7199 repair --full c7 <tables>` in the
   background (test and intervention: `standard1 s001 … s(T−1)`; control: `standard1 s001 s002 s003`; the same command form in
   every arm), logged with start/end epoch and exit code.
5. End of run: `n1` dead (OOM), or the repair command finished, or 20 min passed. Collect (§2.6), stop all, extract the heap dump
   summary with `hprof_direct.py`, then delete the `.hprof` (disk).

### 2.6 Instruments and readings (U measured independently of K)

| What | How | Interval | Domain |
|---|---|---|---|
| **U_direct**: JDK direct counter `java.nio:type=BufferPool,name=direct` `MemoryUsed`, `Count` | JMX sampler on ms0625 (R7's `U1R2Sample` adapted: drop mutation columns, add the two below) | 1 s | D1 + D3 + D4 (all `allocateDirect`) |
| networking pool `org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=Size` and `OverflowSize`; heap used | same sampler | 1 s | D4, D3 overflow; D2 |
| **U_trees (log-derived)**: every `Allocating direct buffer of size N for an off-heap merkle tree` (debug.log, `MerkleTree.java:750`) on n1, with time; every `Received merkle tree for <table> from <endpoint>` (`RepairSession.java:241-242`, system.log); every `Created <k> sync tasks based on 2 merkle tree responses for <desc>` (`RepairJob.java:358`, the release point) | parser after the run: held sets(t) = received − 2 × released jobs; held bytes(t) = Σ allocations of sets not yet released (per job from the response order; fallback: held sets × mean m) | per log line | D1 |
| per-set depth (the K side) | `Created <n> merkle trees with merkle trees size <leaves>, <partitions> partitions, <bytes> bytes` (`ValidationManager.java:85`, debug.log) on all 4 instances | per validation | D1 contract |
| sessions and ranges | `new session: will sync <eps> on range <ranges> for c7.[…]` (`RepairSession.java:297`) | per run | multiplicity |
| peer vs coordinator progress | per-instance count of `Created … merkle trees` lines over time | after run | skew ratio |
| process | `/proc/<pid>/status` `RssAnon`, cgroup `memory.current`, `memory.events` of n1 | 1 s | cross-check |
| GC | `gc.log` of n1 (default `-Xlog:gc…`) | — | heap health |
| initiating failure | first `OutOfMemoryError` in n1 `system.log` (with thread and stack; expected `Cannot reserve … bytes of direct buffer memory` / `Direct buffer memory` from `MerkleTree.allocate` ← `deserializeOffHeap` or `moveOffHeap`), then Cassandra's `Force heap space OutOfMemoryError in the presence of` (`JVMStabilityInspector.java:193-197`), the heap dump (`-XX:+HeapDumpOnOutOfMemoryError` stays default on n1) and `kill -9` (`cassandra-env.sh:209`) | on failure | V5 |
| holder at failure | `hprof_direct.py <dump>`: live `DirectByteBuffer` owners attributed by referrer chain; add `org.apache.cassandra.utils.MerkleTree` (and `$OffHeap*`) to its classifying classes if missing | test runs | V5 |

K = the per-validation budget (`repair_session_space / RF`) and the resolved depth per set; U = the direct counter and the logged
off-heap allocations, which no repair code reads. Instrument check before the first reading: on the Step-B repair of
`standard1` (not a reading), the sum of logged allocation sizes of one job must equal `MemoryUsed` growth within 10 % at the
moment its two sets are held (or the parser's held bytes must match `MemoryUsed − networking Size` within 10 % on a sample),
and the sampler adds < 1 % CPU.

### 2.7 Predicted response, outcome rows and stopping budget

**Calibration and T (pre-registered rule).** The first reading run is control **C-1** (T = 4, D = 2048). From it:
m = Σ logged allocation bytes on n1 / number of `Received merkle tree` lines on n1 (24 expected: 4 tables × 3 sessions × 2).
Then **T = min(150, max(100, ceil(1.6 × 2048 MiB / (2 × m))))**, fixed for every test, intervention and search run. If T-1
at that T survives with peak held sets < the prediction and the peers finished first, T is raised once to 150 for the
remaining runs (all three counted test runs at D = 2048 must then be at T = 150). No other change of T.

**Predictions (made now, before any reading):**

| Arm | Condition | Predicted |
|---|---|---|
| C-1..C-3 control | T = 4, D = 2048 | 3 sessions; per-set leaves 120 k–240 k (m 10–20 MB); repair completes; direct peak ≤ baseline + 8 sets ≈ 0.15–0.35 GB; **no OOM 3/3** |
| T-1..T-3 test | T (rule; 100–150), D = 2048 | peers finish their T validations ≈ 3 × sooner than n1 its 3 T; held sets climb to ≈ (2048 MiB − baseline)/m ≈ 100–190; **`OutOfMemoryError` (direct buffer memory) on n1, 3/3**, from `MerkleTree.allocate` on `ANTI_ENTROPY` (remote set) or the local move; each set's U ≤ its contract S/RF (no bypass); heap stays < 50 % |
| I-1..I-3 intervention | T, D = 2048, `concurrent_merkle_tree_requests: 1` on n1 | held sets ≤ 2 (≤ 40 MB); repair completes (duration ≈ 3 T × per-job time, recorded with throughput); **no OOM 3/3** |
| S-3G, S-4G search | T, D = 3072 then 4096 | held peak ≈ 2 T × m ≈ 3–4.5 GB: 3 GiB likely OOM, 4 GiB at the boundary; report the largest D with OOM and its n/N |

**Outcome rows:**

| Readings | Verdict |
|---|---|
| T OOM ≥ 3/3 at D = 2048 with the claimed holder (D1 ≥ 70 % of `MemoryUsed` at failure, dump confirms), C 0/3, I 0/3 with completed repairs | **true positive** — `verified-OOM · deployment` (convergence under an unprotected default), V1–V7 |
| T OOM, but the dump/logs show another direct holder dominant (D3, D4) | retry (wrong attribution) or mixed if D1 is still needed (state which) |
| T survives at T = 150: peers did **not** finish first (skew ratio < 1.5) or held sets stayed < (D − baseline)/m | **retry**: the topology skew is the missing factor (better design: more peers per coordinator, i.e. more nodes / more sessions, or subrange sessions) |
| T survives with held bytes ≥ D − baseline without an OOM | invalid (instrument) — recheck the counter/parser |
| a set's off-heap bytes > S/RF | additionally a bypass of the per-validation contract (record; not expected) |
| sessions ≠ 3, repair fails before validations (prepare timeout, peer down), a peer OOMs, disk < 3 GiB | invalid run; fix and repeat (amendment) |

**Stopping budget.** Per run: 20 min after the repair starts (`timeout 1200`). Whole stage 2: start of Step C by **09:30**
America/New_York at the latest; **no new run after 10:40**; everything stopped and cleaned by **10:55** (deadline 11:00).
Run order (priority, so a late start drops the least important runs): C-1 (calibration), T-1, T-2, T-3, I-1, C-2, I-2, C-3,
I-3, then S-3G, S-4G (one each; repeats only if time remains). No escalation after an OOM beyond this list.

**Time plan (≈ 2 h 10 min):** Step A 15 min + Step B 15 min + 9 counted runs × ≈ 8 min (≈ 72 min) + 2 search runs × 8 min +
collection/cleanup 10 min. If stage 2 starts after 08:50, drop S-4G first, then S-3G; the V1–V4 set (T ×3, C ×3, I ×3) has
priority.

**Fit to the nodes.** RAM: ms0625 holds n1 (heap 2 + direct ≤ 4 + ≈ 0.5 GiB native) and n3 (heap 2 + small direct) ≈ 9 GiB
of 62; ms0640 two peers ≈ 6 GiB. Cores: 2 validation threads per instance, 4 per machine of 8. Disk: base copy ≈ 0.4 GB per
node; data ≈ 2 × 40 MB per machine with hard links (≤ 2 × 5 GB if copies are ever needed — still fits); commit logs: the load writes ≈ 30 MB per instance
(default `commitlog_total_space` = min(8 GiB, ¼ of the volume) is never approached); one 2 GiB heap dump at a
time, deleted after extraction; logs ≤ 200 MB per run. Keep ≥ 5 GiB free on ms0625 at all times; stop if below 3 GiB.

### 2.8 Controls and intervention

- **Matched control (V2):** the same cluster, data, build, budgets, command form and clean-start procedure, with **T = 4**
  tables (low multiplicity), ≥ 3 runs. It must complete without OOM; it also supplies the per-set footprint (calibration) and
  the "component safe alone" margin (≤ 0.35 GB of 2 GiB).
- **Causal intervention (V4):** bound the multiplicity with the shipped aggregate control, `concurrent_merkle_tree_requests: 1`
  on n1 only (the value `cassandra.yaml:844-846` says keeps a command within `repair_session_space`, and `:850-854` recommends, "at the expense of speed" with vnodes), at the test's T and D = 2048, ≥ 3 runs; it must remove the OOM
  while the repair still completes (record wall time and jobs completed, so the intervention is not "no useful work"). A
  constraint differs from its default only in this arm (V6 allows it).
- **Cleanup after stage 2:** stop every instance (by PID, then `systemctl --user stop` of its scope), remove the alias IPs, keep
  `/mydata/s4/cassandra-base` and the small run logs under `/mydata/s4/c7/runs`, delete instance data and every `.hprof`, and
  leave nothing running; say what is left on each node. Never touch `/mydata/s4/r7-w1`.

`sha256 of §1–§2 at freeze: 5fd7646d6a03145dd4ef46b58766de7482c6d119b68504edb87a84a283e6ffaa` (computed as `awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-18) · amendments after the freeze: none.

## 3. Runs (stage 2)

Stage 2 by a fresh OOM-agent session (workflow), 2026-11-18 08:13–10:40 America/New_York (all runs stopped 10:30, cleanup 10:31). Freeze hash re-computed at
08:14 with the command in §2's last line: `5fd7646d…e6ffaa`, **matches**. Nothing else ran on either node
(`pgrep -af CassandraDaemon` empty on both at 08:14).

### 3.1 Environment (as run)

| Item | Value |
|---|---|
| Nodes | ms0625 (`10.10.1.1`, n1 victim + n3 at alias `10.10.1.81`), ms0640 (`10.10.1.2`, n2 + n4 at alias `10.10.1.82`); Utah m400, **aarch64**, 8 cores, 62 GiB, Ubuntu 22.04.1, kernel 5.15.0-191-generic, cgroup v2, swap 8 GiB (0 for every Cassandra JVM via `systemd-run --user --scope -p MemorySwapMax=0`) |
| Build | `/mydata/s4/cassandra-base` = `cp -a /mydata/s4/r7-w1/cassandra` on each node (08:15); `git describe` `cassandra-5.0.9`, `git status` clean, jar sha256 `2a9cbd5c…2c26712` on both (= §2.3). No `ant`, no patches/agents. `/mydata/s4/r7-w1` untouched |
| JDK / GC | OpenJDK 11.0.33+9 (Ubuntu build), G1 (`jvm11-server.options` default) |
| Work dir | `/mydata/s4/c7-w3/` on each node (`h/`, `inst/n?`, `runs/<run>`, `cls/`) — amendment A1 |
| n1 budget | `MAX_HEAP_SIZE=2048M`, `MAX_DIRECT_MEMORY_SIZE=2048M`; **resolved** (`jcmd VM.flags`, every run): `-XX:MaxHeapSize=2147483648 -XX:MaxDirectMemorySize=2147483648 -XX:+UseG1GC`; scope `MemoryMax=24G` (safety, non-binding: `memory.events` `oom_kill 0` in every run), `MemorySwapMax=0`; `HeapDumpOnOutOfMemoryError` on (default) |
| Peers | heap 2048M, direct 4096M, `-XX:-HeapDumpOnOutOfMemoryError`; never changed between arms |
| Read-back on n1 (every run, `readback.txt`) | JMX `RepairSessionSpaceInMiB=128`, `ConcurrentMerkleTreeRequests=0` (I arms: `1`); `getconcurrentcompactors` 2; startup config line `use_offheap_merkle_trees=true`, `concurrent_validations=0`, `repair_session_space=null`; tables `c7.standard1` and `c7.s149` each 1 SSTable, 476,818 partitions (estimate); Data.db link count 150 before every run |
| yaml diff n1 | cluster name, addresses, seeds, five directories, `auto_bootstrap: false`; I arms add `concurrent_merkle_tree_requests: 1` (`logs/*/n1-yaml.diff`) |
| Topology | `nodetool status` before Step B: 4 × UN, 16 tokens each (allocator: `TokenAllocation.java:106 Selected tokens` on first start), effective ownership 48.5–52.0 % with RF 2; `logs/T-1/ring.txt` |

### 3.2 Steps A and B (setup, not readings)

- **A.** Base copied (above); alias IPs added after a failed ping from ms0625 (08:16). First cluster start at 08:16–08:24 was
  lost: every instance stopped ~5 s after its launching ssh session closed (`StorageServiceShutdownHook`), because the user's
  systemd manager (which owns the `--user --scope`) exits when the user has no session and lingering was off. Fix
  (amendment A2): `sudo loginctl enable-linger jason92` on both nodes, instance dirs wiped, cluster re-created 08:28–08:32
  (n1, then n2, n3, n4 one at a time, each `UN` after 20–25 s).
- **B.** `cassandra-stress write n=1000000 cl=ALL …` (§2.5 B.1): 1,000,000 partitions, 0 errors, 7,388 op/s
  (`logs/stepB/stress-summary.txt`); flush + `compact c7 standard1` on all 4 → one SSTable `nb-3` per instance (20.4–21.8 MB);
  stock `repair --full c7 standard1` from n1: 3 sessions (n1 with n3, n2, n4), completed in 9 s. 149 clones created with the
  standard1 DDL (`cqlsh -f`, 5 min 46 s; one schema version); drain + stop; `link.sh` hard-linked the 8 `nb-3` components into
  each of the 149 clone dirs on all 4 instances (link count 150 per Data.db, re-read before every run: 150).
- **Calibration of the instruments.** Per-set off-heap size: `ValidationManager.java:85` logs the number of range trees,
  not leaves (`Created 14 merkle trees with merkle trees size 14, 209664 partitions, …`), so per-set size comes from the
  `MerkleTree.allocate` debug lines (one direct buffer per range tree, sizes 671,776 / 1,343,520 / 2,687,008 B, i.e. 82 B ×
  2^13…2^15 leaves). The Step-B repair released its 6 sets within ~0.1 s, too fast for the 1-s sampler, so the 10 % check of
  §2.6 was done on **C-1** (amendment A3): at the C-1 direct peak, held sets × m = 156 MiB vs `MemoryUsed` − baseline −
  networking-pool growth = 173 − 16 = 157 MiB (within 1 %).

### 3.3 Calibration and T

C-1 (T = 4, D = 2048): 24 `Received merkle tree` lines on n1 (12 own, 4 from each peer), Σ logged allocations 374.1 MiB →
**m = 15.59 MiB** per set (≈ 199 k leaves; prediction 10–20 MB, central 15). Rule §2.7: T = min(150, max(100,
ceil(1.6 × 2048 / (2 × 15.59)))) = **106** tables (`standard1`, `s001`…`s105`), fixed for every T and I run. Every T run OOMed,
so the "raise T to 150" branch never applied.

### 3.4 Runs

All runs: clean start of all 4 instances (`harness/run.sh`), D = 2048 MiB, same data and command form; sessions = 3 in every
run (one per peer: n1–n3 209,664 partitions per request, n1–n4 194,304, n1–n2 81,920).
"Received" = `Received merkle tree` lines on n1 (from n2 / n3 / n4 / n1 itself); "held" = received − 2 × released jobs;
U_direct = JMX `java.nio:type=BufferPool,name=direct` `MemoryUsed` (1 s); times from the repair start.

| Run (start) | Arm, T | n1 outcome | Repair | Received (n2/n3/n4/n1) | Released jobs | Held sets peak | U_direct base → peak | Heap peak (pre-GC) | Dump: direct by holder |
|---|---|---|---|---|---|---|---|---|---|
| C-1 (08:44) | control, 4 | alive | completed, 34 s, exit 0 | 4/4/4/12 | 12 | 11 | 58.4 → **231.0 MiB** | 1,149 MiB | — |
| T-1 (08:50) | test, 106 | **`OutOfMemoryError: Direct buffer memory`** at +154 s (13:56:27.709Z), then `Force heap space OutOfMemoryError`, dump, exit | died, exit 2 | 106/60/54/56 | 56 | **164** | 50.4 → **2,046.5 MiB** (1,399 buffers) | 1,936 MiB | trees **1,964.2 MiB = 96.0 %** of 2,046.5; BufferPool 48.0; hints 32.2 |
| T-2 (08:58) | test, 106 | **direct OOM** at +145 s (14:04:14.103Z) | died, exit 2 | 106/53/56/51 | 51 | **164** | 50.4 → **2,047.8 MiB** | 1,942 MiB | trees **1,965.5 MiB = 96.0 %** |
| T-3 (09:06) | test, 106 | **direct OOM** at +139 s (14:12:05.414Z) | died, exit 2 | 106/51/55/54 | 51 | **164** | 50.4 → **2,047.2 MiB** | 2,048 MiB | trees **1,964.8 MiB = 96.0 %** |
| I-1 (09:13) | intervention, 106 | alive | **completed**, 17 min 35 s (1,060 s), exit 0, 318/318 jobs | 106/106/106/318 | 318 | **2** | 50.4 → **102.9 MiB** | 1,331 MiB | — |
| C-2 (09:36) | control, 4 | alive | completed, 33 s, exit 0 | 4/4/4/12 | 12 | 11 | 50.4 → **184.6 MiB** | 1,170 MiB | — |
| I-2 (09:41) | intervention, 106 | alive | **completed**, 17 min 11 s (1,036 s), exit 0, 318/318 jobs | 106/106/106/318 | 318 | **2** | 50.4 → **106.1 MiB** | 1,330 MiB | — |
| C-3 (10:03) | control, 4 | alive | completed, 30 s, exit 0 | 4/4/4/12 | 12 | 11 | 50.4 → **234.5 MiB** | 1,157 MiB | — |
| I-3 (10:08) | intervention, 106 | alive | **completed**, 17 min 37 s (1,063 s), exit 0, 318/318 jobs | 106/106/106/318 | 318 | **2** | 50.4 → **105.5 MiB** | 1,346 MiB | — |

**Initiating failure (V5).** T-1 and T-3: first error on `AntiEntropyStage:1`, `java.lang.OutOfMemoryError: Direct buffer memory`
at `Bits.reserveMemory` ← `ByteBuffer.allocateDirect` ← **`MerkleTree.allocate(MerkleTree.java:751)` ← `deserializeOffHeap(:789)`**
← `MerkleTrees$MerkleTreesSerializer.deserialize` ← `ValidationResponse$1.deserialize` ← `InboundMessageHandler$LargeMessage.deserialize`
(a remote tree set arriving); T-2: the same allocation from **`MerkleTree.moveOffHeap(:781)` ← `tryMoveOffHeap(:772)`** (n1's own set
being moved off heap). Each is preceded by the JDK's reserve-retry full GC (`G1 Old Generation GC in 537–694 ms`, old gen falling to
0.18–0.34 GB: the heap was not the problem) and followed by `JVMStabilityInspector … Force heap space OutOfMemoryError in the
presence of` and the heap dump (248–312 MB). `hprof_direct.py` on each dump: live `allocateDirect` owners 2,046.5 / 2,047.8 /
2,047.2 MiB, of which **`MerkleTree$OffHeapInner.buffer` 1,964–1,966 MiB (96.0 %)** in 1,048–1,054 × 1,343,520 B +
224–228 × 2,687,008 B + 60–62 × 671,776 B buffers; networking `BufferPool` 48 MiB, `HintsBuffer` 32 MiB. Excerpts:
`logs/T-*/first-oom.txt`, `logs/T-*/hprof-direct.txt`.

**Multiplicity and skew (the claimed mechanism).** In every T run n2 (the peer with the smallest requests) finished all 106
validations by +103–121 s, n3 and n4 had sent 51–60 sets each, and n1 had completed only 51–56 of its 318 own validations when
it died: received sets outran released jobs (≈ 1.4–1.5 remote sets/s in, ≈ 0.35–0.37 jobs/s released), held sets rose linearly
(T-1: 9 at +27 s, 53 at +57 s, 99 at +87 s, 141 at +117 s, 161 at +147 s) together with U_direct (178, 705, 1,217, 1,663,
1,987 MiB) until the 2 GiB limit, at **164 held sets** in all three runs (prediction: 100–190). Mean live tree bytes per held
set at failure 1,965 / 164 ≈ 12.0 MiB (the n2 sets, 81,920 partitions per request, are the smallest and dominate the backlog).

**Per-set contract (no bypass).** Per request the contract is `repair_session_space / RF` = 64 MiB. The largest request
(209,664 partitions over its ranges) gets < 2 leaves per partition from the partition cap, so ≤ 82 B × 2 × 209,664 ≈ 32.8 MiB
off heap; measured m = 15.6 MiB per set (C runs). U ≤ C for every set; the excess is the **sum** of 164 in-contract sets,
which no setting bounds at defaults (`concurrent_merkle_tree_requests` 0).

### 3.5 Deviations and amendments (dated 2026-11-18, stage 2)

- **A1 (environment, 08:15).** Node work dir `/mydata/s4/c7-w3/` instead of `/mydata/s4/c7/` (session instruction for a fresh
  directory). No effect on the runs.
- **A2 (environment, 08:26).** `loginctl enable-linger jason92` on ms0625 and ms0640: without it the user systemd manager, and
  with it every `--user --scope` instance, stopped when the launching ssh session closed (first start lost, no readings).
  Lingering was turned off again at cleanup.
- **A3 (instrument, 08:37).** The §2.6 10 % instrument check was done on C-1 instead of the Step-B repair (Step B's sets lived
  ~0.1 s, below the 1-s sampling) — result within 1 % (§3.2). Sampler overhead: 14 s CPU over 428 s of I-2 (3.3 % of one core, 0.4 % of the node's 8 cores).
- **A4 (procedure).** `run.sh` also clears the peers' `logs/` at each clean start (per-run validation counts), and keeps the
  `.hprof` in the run dir until `hprof_direct.py` has read it (run with `nice -n 19` on ms0625 while the next run executed: T-1's
  during T-2, T-2's during T-3, T-3's during I-1; one Python thread on an 8-core node), then deletes it at cleanup.
- **A5 (readings).** `held sets × mean m` over-states held bytes when the backlog is dominated by the small n2 sets
  (2,422–2,448 MiB vs U_direct − base 1,996–1,997 MiB at the T peaks); U_direct and the dumps are the U figures used.
- **Not run:** S-3G and S-4G (the upward search, last in §2.7's priority order). The cluster set-up loss (A2) and the
  intervention runs' 17–18 min repairs used the time; an S-3G run started after I-3 could have run past the 10:55 cleanup
  limit if it survived, so both were dropped as §2.7's time plan prescribes (S-4G first, then S-3G).

Full logs stay on ms0625 `/mydata/s4/c7-w3/runs/<run>/` (`n1-logs/` system/debug/gc, `samples.csv`, `cg.csv`, `repair.log`,
peer `n?-trees.txt`); small excerpts in [`logs/`](logs/); harness in [`harness/`](harness/) (`ctl.sh`, `run.sh`, `link.sh`,
`C7Sample.java`, `parse.py`, `hprof_direct.py`).

### 3.6 Cleanup and what is left on the nodes (10:31)

Every instance stopped by PID and its `systemctl --user` scope stopped after each run (`pgrep -af CassandraDaemon` and the
`c7-*` scope list empty on both nodes at 10:30); samplers ended with their runs; alias IPs `10.10.1.81` / `10.10.1.82` removed;
lingering disabled again (`Linger=no`); instance dirs (`/mydata/s4/c7-w3/inst/n?`, data and commit logs) and every `.hprof`
deleted. **Left:** `/mydata/s4/cassandra-base` on both nodes (the build copy, kept per §2.8); ms0625
`/mydata/s4/c7-w3/{h,cls,runs}` (72 MB: harness copy and full run logs); ms0640 `/mydata/s4/c7-w3/{h,inst,runs}` (empty
dirs and harness, 28 KB). `/mydata/s4/r7-w1` untouched.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`** — convergence of in-contract per-validation tree
sets under an **unprotected configuration** (the aggregate control `concurrent_merkle_tree_requests` ships at 0 = unlimited);
endpoint JVM direct-buffer `OutOfMemoryError` on the repair coordinator. Interpretation: intentional exception /
configuration-sizing gap (documented in `cassandra.yaml:842-861` and CASSANDRA-19336, whose fix is opt-in), not a suspected
implementation defect.

**Reason.** On a stock 5.0.9 four-instance cluster (RF 2, 16 vnodes, every capacity at its default, n1 heap 2 GiB and
direct limit 2 GiB), `nodetool repair --full` of 106 small identical tables from n1 started 3 sessions × 106 jobs at once;
the peers answered their 106 requests each ≈ 3 × faster than n1 could validate its own 318, so their off-heap tree sets
(m = 15.6 MiB each, every one ≤ its 64 MiB `repair_session_space / RF` contract) waited on n1 for n1's own trees. Held sets
rose linearly to 164 and `MemoryUsed` to 2,046–2,048 MiB of 2,048, and n1 died with `OutOfMemoryError: Direct buffer memory`
in `MerkleTree.allocate` at +139–154 s in **3/3** runs; the dumps attribute **1,964–1,966 MiB (96.0 %)** of live direct
memory to `MerkleTree$OffHeapInner` buffers. The matched control (4 tables) reached no OOM (**0/3**; all three repairs completed) with direct peaks of
231.0 / 184.6 / 234.5 MiB (≤ 11.5 % of the limit), and the shipped aggregate control `concurrent_merkle_tree_requests: 1` on n1 removed the OOM
(**0/3** OOM, 3/3 runs) at T = 106 (held sets ≤ 2, direct peak 102.9 / 106.1 / 105.5 MiB) while the repair still **completed** all 318 jobs
(17 min 35 s / 17 min 11 s / 17 min 37 s; ≈ 0.30 jobs/s vs 0.35–0.37 jobs/s released before the OOM in the test runs).

**V1–V7 (one fixed condition: build `2a9cbd5c…`, defaults, n1 heap 2 GiB / direct 2 GiB, T = 106):**

| | Evidence | Met |
|---|---|---|
| V1 Repetition | T-1, T-2, T-3: direct OOM 3/3 from clean starts | yes |
| V2 Matched control | C-1, C-2, C-3 (same cluster/build/budget/command form, T = 4): OOM 0/3, repairs completed, peaks 231.0 / 184.6 / 234.5 MiB (held sets ≤ 11) | yes |
| V3 Measurement | U_direct (JDK `Bits` counter over JMX, 1 s), per-tree allocation log, held-set count from repair logs, and heap-dump attribution — none read by repair code; K = per-request `repair_session_space / RF` (64 MiB) and resolved tree depth | yes |
| V4 Intervention | I-1, I-2, I-3: `concurrent_merkle_tree_requests: 1` on n1 only, T = 106: OOM 0/3, all three repairs completed 318/318 jobs in 17 min 11 s – 17 min 37 s, held sets ≤ 2, direct peak ≤ 106.1 MiB | yes |
| V5 Initiating failure | first error + stack in each T run (`MerkleTree.allocate` ← `deserializeOffHeap` ×2, ← `moveOffHeap` ×1), dumps at failure: trees 96 % | yes |
| V6 Default constraints | `repair_session_space` 128 MiB (heap/16 at 2 GiB, read back), `concurrent_merkle_tree_requests` 0, `use_offheap_merkle_trees` true, `concurrent_validations` → 2, networking cache and receive-queue capacities default; only I arms change one constraint | yes |
| V7 Acceptable budget | heap 2 GiB, direct 2 GiB (≥ 512 MiB standing rule; ≥ what `cassandra-env.sh` resolves for a 4–8 GiB node; no container limit); largest tested budget with OOM: **2 GiB direct, 3/3** (the upward search S-3G / S-4G was not run, §3.5) | yes |

**Limits of attribution.** (1) The multiplicity comes from tables × sessions on a 4-instance cluster packed on two machines (two
instances per machine, disclosed topology deviation); the skew that lets peer sets pile up is the coordinator being in every
session (3 × the validation work). (2) Tables are hard-linked clones of one small table (≈ 477 k partitions per instance), so
the per-set size (≈ 15 MB) is set by partition count, not data volume; larger tables would give larger sets up to the
64 MiB contract (fewer tables needed). (3) The 2-GiB direct limit is explicit; at the 62-GiB node's own resolved default
(7,936 MiB) about 4 × as many held sets would be needed, i.e. ≈ 400+ tables at this per-set size, or larger tables
— not tested (no upward search was run). (4) Throughput of the intervention is
lower (17–18 min; ≈ 14 min at the test runs' release rate had they survived), the documented "at the expense of speed".

**Back to phase 1.** OC-6 → `true positive (C7)`; shape covered by **CP-7** (per-owner limit × unbounded owners: Merkle trees
× ranges × tables, JIRA 14096 / 15202 / 19336) — no new pattern needed.
