# R17 (retry of U11) — RangeTombstoneList of a hot memtable partition: per-write full copies × 32 writers stall MutationStage, and the unbounded local-write backlog behind them exhausts the heap  <!-- file: cassandra/cases/range-tombstone-list--copy-thrash-stalls-local-write-backlog/range-tombstone-list--copy-thrash-stalls-local-write-backlog.md -->

| Field | Value |
|---|---|
| Case ID | `R17` (a new attempt at `U11`; README "ID prefixes") |
| From | retry of `U11` (retry-list row U11; cluster `OC-206` primary, `OC-200`, `OC-201`, `OC-202`, `OC-368`) |
| Phase-1 case files | [`range_tombstone_list_growth_factor-addInternal-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/range_tombstone_list_growth_factor-addInternal-capacity--autonomous.md), [`range_tombstone_list_growth_factor-grow-newLength--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/range_tombstone_list_growth_factor-grow-newLength--autonomous.md), [`range_tombstone_list_growth_factor-growToFree-newLength--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/range_tombstone_list_growth_factor-growToFree-newLength--autonomous.md), [`none-addall-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/none-addall-size--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`), build `/mydata/s4/cassandra-base` on `pc96` (the local node), OpenJDK 11.0.33, G1 as shipped |
| Stage 1 (design) | OOM-agent stage-1 session, 2026-11-20 ≈ 10:30–11:50 America/New_York, repository HEAD `581de552` |
| Stage 2 (verify) | fresh OOM-agent session on `pc96`, 2026-11-20 10:54–13:13 (all 22 runs) and 21:27–≈ 22:30 America/New_York (write-up after an API usage-limit interruption, §3.0) |
| Verdict | **`retry`** (detail `candidate`; no OOM in 13 main-design runs; GC service loss 3/3 at 512 MiB with short controls) |

## Summary (stage 1)

- **Design intent:** U11 showed that the hot partition's in-flight RangeTombstoneList copies alone stay at ≤ 0.37 × heap
  (no OOM 0/6). This retry keeps that holder as the *trigger* and adds the holder it starves: while 32 writers thrash on
  the hot partition, MutationStage serves ≈ 10–30 hot writes/s, and every other local write (here a steady 48 MiB/s of
  4 MiB blob inserts to a second table) waits in MutationStage's unbounded queue after its client was answered with a
  2 s timeout. Predicted endpoint: **Java heap OOM at 8 GiB and 15,872 MiB**, none at 2 GiB (n, and so the stall,
  scale with the heap). GC service loss is a pre-registered secondary reading.
- **Conclusion (stage 2): `retry`, no OOM.** At 2, 4 and 8 GiB the 48/s open-loop hot stream never started the 32-writer thrash
  (one writer serves ≈ 80/s at n₀ = 640 k), so nothing queued and every run ended at ≈ 150 s with the default commit-log-cap
  flush of the hot table. At 15,872 MiB the stall formed and ≈ 9–10 GiB of local writes queued (12,898 `Mutation`s in the
  histogram, Old 11.9 of 15.5 GiB, STW 0.875), but growth flattened inside the 450 s cap because GC-held request threads
  throttled arrivals. U11's workload at 512 MiB met the default GC service-loss criterion 3/3 (0.908–0.910), its controls
  only 5–27 s long.
- **Root cause (as measured):** MutationStage's queue is unbounded and expired local writes are re-submitted and kept, with
  nothing counting them; the only brake seen is implicit (128 request threads × the ≥ 2 s each is held). A retry must enter
  the thrash state on purpose and give most request threads to large-value writes (§4).

## 1. Candidate

### 1.1 The retry row (quoted from `phase2-retry-list.md`, Status as of 2026-11-20)

| Case | Verdict date | Why retry (what was shown, what was missing) | What a better design should change | Status |
|---|---|---|---|---|
| [U11](../range-tombstone-list--per-write-full-copy-x-writers/range-tombstone-list--per-write-full-copy-x-writers.md) (from OC-206 cluster) | 2026-11-18 | The per-write full copy of a partition's RangeTombstoneList is real and uncounted (266 MiB of in-flight copies at 2 GiB, 949 MiB at 8 GiB; GC thrash, ≈ 25 % write timeouts; MutationStage concurrency 1 removes it), but no OOM 0/6 (live heap ≈ 0.2–0.4 of budget); GC service loss only 1/1 at 512 MiB | Target GC service loss, not OOM: 512 MiB (searching up to 1 GiB), T, C and I ×3 each, keep the write phase below the memtable flush, pre-define the STW window | picked again: R17 (2026-11-20) |

### 1.2 The earlier case and its verdict

[`U11`](../range-tombstone-list--per-write-full-copy-x-writers/range-tombstone-list--per-write-full-copy-x-writers.md),
verdict **`retry`** (detail `candidate`), stage 2 on `pc96` 2026-11-18. Facts this design relies on (U11 §3.3):

- Every write attempt carrying a range tombstone into a memtable partition holding n of them copies the partition's
  whole `RangeTombstoneList` and grows the copy 1.5× (≈ 50 B × n, `BTreePartitionUpdater.java:120-121`,
  `RangeTombstoneList.java:106-114, 680-739`); only the size delta is charged, failed CAS attempts nothing. Multiplicity
  is bounded only by the 32 `MutationStage` permits (`concurrent_writes`).
- Measured: in-flight copies 219–302 MiB at 2 GiB (arm D) and 949 MiB at 8 GiB (B8 L1) while the counter moved < 1 MB;
  467–476 full GCs per 300 s at 2 GiB; live heap at full GCs 0.24 × H (2 GiB), 0.19 × H (8 GiB), 0.37 × H (512 MiB).
  **No OOM 0/6.** Matched control (1,000 partitions) and intervention (`setconcurrency MutationStage 1`) removed the
  thrash (I: 0 full GCs, 8.2 × T's rate, 0 timeouts).
- **Hot-write service rate** (applied writes/s with 32 writers, 64 client requests in flight): ≈ 41/s at n ≈ 300 k
  (2 GiB; 31 acked + ≈ 10 applied after their timeout), ≈ 7.8/s at n ≈ 1.19 M (8 GiB), ≈ 96/s at n ≈ 75 k (512 MiB).
  A log-log fit of the 2 and 8 GiB points gives rate ∝ n^-1.2.
- **Timed-out writes were applied late, not dropped**, and at 8 GiB `MutationStage` pending reached **6,434** (one
  tiny mutation each). U11 §4: "Only a stacked design (S) with a second heap holder that grows during the thrash
  could reach it, and the 6,434 queued mutations at 8 GiB are too small for that."
- B05 (512 MiB): STW60 = 0.920, the default service-loss criterion met once (≈ 100 s ≥ 0.90), not repeated, no C/I there.

### 1.3 Phase-1 cases and stage-4 evidence

The four phase-1 case files (header) were filed by stage 4 as **true negative** ("does not cap") for their capacity
checks; their measured facts are quoted in U11 §1.3: memtable counter ≈ 504–510 B per tombstone at f = 1.5 on the
`add()` branch, live ≈ 272–363 B; growth allocates 20 B × capacity; single-writer cost ≈ 18–20 ns per slot. No stage-4
run had more than one request in flight per partition.

### 1.4 JIRA prior art (read only; nothing posted)

Survey file `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv` (grep for RangeTombstoneList,
range tombstone, MutationStage, hints to self):

| Issue | Status | Relevance |
|---|---|---|
| CASSANDRA-21492 | Unresolved (*Triage Needed*, created 2026-07-08) | The per-write `RangeTombstoneList.copy()` as an O(N²) allocation cost; no OOM, no concurrency (the trigger half; U11 §1.4) |
| CASSANDRA-11460 "memory leak" | Won't Fix | Heap OOM with the MutationStage SEP queue holding 60+ GB under a write rate above node capacity (the backlog half, as a generic overload) |
| CASSANDRA-13213 | Unresolved | Node OOMs from pending mutations after compaction metrics hang (another stall source for the same backlog) |
| CASSANDRA-12689 | Fixed 3.0.10 | All MutationStage threads blocked on MV locks; pending mutations pile up to OOM (another stall source, fixed for MV) |
| CASSANDRA-3440, 4753, 6510 | Fixed (1.0.4, 1.2.1, 2.0.4) | Local writes that time out: 3440/4753 stopped writing hints *for the local node*; 6510 "Don't drop local mutations without a hint" — the 5.0.9 behavior that re-submits an expired local write to MutationStage (§2.1) |

JIRA REST (anonymous GET `issues.apache.org/jira/rest/api/2/search`, 2026-11-20 ≈ 10:40):

| Query (JQL) | Hits | Relevant |
|---|---|---|
| `key=CASSANDRA-21492` | 1 | still *Triage Needed*, no fix version |
| `project=CASSANDRA AND text ~ "RangeTombstoneList" AND created >= 2026-11-01` | 0 | nothing new since U11 |
| `project=CASSANDRA AND text ~ "MutationStage" AND text ~ "range tombstone"` | 8 | none on this path (6181, 7401, 6949 …: replay, live-ratio loop, read regression) |
| `project=CASSANDRA AND text ~ "LocalMutationRunnable"` | 48 | **CASSANDRA-19958** "Local Hints are stepping on local mutations" (*Needs Committer*, 2024-09-26): the re-submitted expired local write competes with fresh ones on MutationStage; 6510, 4753, 6427 (counter writes not resubmitted), 16499 (SEP wait), 13235 (open: all threads blocked, writes pending). No report of a range-tombstone hot partition as the stall |
| `key in (CASSANDRA-11460, CASSANDRA-13213, CASSANDRA-3440)` | 3 | as in the table above |

**Verdict: the stack is `new`.** Each half is known separately — the copy cost `known-open` (21492), an overloaded
MutationStage queue reaching OOM `known` and closed Won't Fix (11460) / open (13213), the local re-submission by design
(6510) with an open follow-up (19958) — but no issue reports that a range-tombstone hot partition at shipped defaults
stalls every local write on the node until the heap is gone. Not a known-fixed bug, so not a positive control. The
backlog holder is the one S2 verified (coordinator's own CL=ONE local-write backlog, true positive); this case differs in
the stall source (a slow *local* apply caused by the RTL copies, one node, no faster replica needed).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism (direction: **combo — unprotected accumulation (trigger) × unprotected accumulation (holder)**)

**Stall (U11's holder, unchanged).** A write carrying a range tombstone runs `AtomicBTreePartition.Updater.addAll`
(`AtomicBTreePartition.java:146-186`): per optimistic attempt `BTreePartitionUpdater.merge` →
`existing.mutableCopy().add(update.clone(HeapCloner.instance))` (`BTreePartitionUpdater.java:120`) copies the
partition's four RTL arrays at size n (20 B × n) and `growToFree` reallocates them at 1.5 n (30 B × n)
(`RangeTombstoneList.java:106-114, 664-739`). With 32 writers on one partition, most attempts lose the CAS and repeat the
O(n) copy; the waste tracker sees only the charged delta and its lock excludes nobody (U11 §2.1). Measured result: the
32 `MutationStage` threads are busy, and the stage completes only μ_h ≈ 41 hot writes/s at n ≈ 300 k and ≈ 8/s at
n ≈ 1.19 M.

**Backlog (the holder this design adds).** Every local write — for *any* table — goes through the same stage. On a
one-node, RF = 1 keyspace at CL ONE, `StorageProxy.mutate` (`:878-906`) → `sendToHintedReplicas` first serializes the
mutation into its cached buffer (`Mutation.serializer.prepareSerializedBuffer`, `StorageProxy.java:1501`, unconditional),
then `performLocally` (`:1674-1690`) wraps the apply in a `LocalMutationRunnable` and calls
`Stage.MUTATION.maybeExecuteImmediately`: with no free permit it is appended to the SEP queue, which has **no bound**.
The `Native-Transport-Requests` thread then blocks in `responseHandler.get()` (`:906`) and at `write_request_timeout`
(2 s) answers the client with a `WriteTimeout`, which **releases** the request's native in-flight bytes
(`native_transport_max_request_data_in_flight`, heap/10; per IP heap/40) and the request thread (128,
`Config.java:283`). The runnable stays queued. When a worker finally dequeues it after its deadline,
`LocalMutationRunnable.run` (`StorageProxy.java:2634-2656`) records a self-drop and, because
`requestTime.shouldSendHints()` is true (`Dispatcher.java:258-266`; `enforce_native_deadline_for_hints: false`,
`Config.java:1400`), **re-submits the same apply as a `HintRunnable` at the tail of `MutationStage`**
(`submitHint`, `:2822-2828`), which applies it on its second pass. The only hint brake, `checkHintOverload`
(`:1585-1599`, `maxHintsInProgress` = 128 × processors, `:202`), never fires for the local replica because
`shouldHint(self)` returns false (`:2442-2447`). So a queued local write holds its decoded `Mutation` — the bound blob
value copied to the heap by `CBUtil.readValue` (`CBUtil.java:443-450`) — until the stalled stage applies it, and nothing
counts it. (The cached serialization made at `:1501` is kept only for mutations below `CACHEABLE_MUTATION_SIZE_LIMIT` =
1,000,000 B, `Mutation.java:439-463`, `CassandraRelevantProperties.java:80`; the 4 MiB blob writes of this design are above
it, so each queued blob write holds ≈ 1 × its value, not 2 ×.)

**Rates (FIFO model, the arithmetic of §2.4).** Hot writes arrive at λ_h, blob writes at r_b. While the hot writes keep
all 32 permits, the stage completes μ_h hot applies/s and, because blob applies are fast (≈ ms) and interleaved in queue
order, ≈ μ_h × r_b / λ_h blob applies/s. If λ_h > μ_h the queue grows, and the **blob backlog grows at
r_b × (1 − μ_h/λ_h) mutations/s**, each holding ≈ the blob size (4 MiB). Arrivals are capped by the 128 request threads,
each blocked up to 2 s: λ_h + r_b ≤ 64/s. Because the flush trigger bounds n ∝ heap and μ_h falls with n, **the stall
needs a large heap** (μ_h < λ_h at 8 GiB and above, not at 2 GiB), which is the direction the budget search goes.

Why the RTL copy is the cause and not just load: the same blob stream at the same rate, with the same range-tombstone
count spread over 1,000 partitions, is applied as it arrives (arm C); bounding the copies' multiplicity to 1 lets the stage
keep up (arm I, U11 I: 8 × T's hot rate). Technique note: [`combo-playbook.md`](../../../combo-playbook.md) (a bounded
per-instance holder whose multiplicity starves a shared executor, stacked with the executor's unbounded queue).

### 2.2 Protection map

| Domain | Allocation and owner | Counter / limit | Scope and multiplicity | Lifetime | At the limit |
|---|---|---|---|---|---|
| D1 in-flight RTL copy (stall source) | `RangeTombstoneList.copy()` + `grow` on a MutationStage thread (`BTreePartitionUpdater.java:120`) | **none** (failed attempts charge 0) | ≤ 32 permits on the hot partition | `mutableCopy()` → CAS | nothing |
| D2 retained hot-partition RTL | memtable `DeletionInfo` of table `r17.rt` | memtable pool `memtable_heap_space` = heap/4, counted ≈ 510 B, live ≈ 290 B per tombstone | one memtable | until flush | cleaner flushes the **largest** memtable when used > reclaiming + ⅓ × pool (`MemtablePool.java:125-145`, `AbstractAllocatorMemtable.java:249-300`) |
| D3 local-write backlog (claimed OOM holder) | `LocalMutationRunnable` / `HintRunnable` → `Mutation` (blob `byte[]` via `CBUtil.readValue`; no cached serialization above 1,000,000 B) in the `MutationStage` SEP queue | **none**: queue unbounded; native in-flight bytes and the request thread released at the 2 s timeout; `checkHintOverload` exempts self | every write not yet applied; grows at r_b (1 − μ_h/λ_h) | until applied (second pass after expiry) | nothing |
| D4 blob memtable | memtable of table `r17.blob` (4 MiB values > `MAX_CLONED_SIZE` 128 KiB, unslabbed, `SlabAllocator.java:52,92`) | the same pool | one live + flushing | until flush | flushed as the largest memtable (design keeps D2 below half of the trigger, §2.4) |
| D5 requests in flight | native-transport `Message` + decoded statement values (≤ 32 blob + ≤ 96 hot requests) | `native_transport_max_request_data_in_flight` heap/10, per IP heap/40 (wire bytes); 128 request threads | node | until the response (success or timeout) | backpressure (Netty stops reading); not reached by design at ≥ 8 GiB (≤ 24 × 4 MiB = 96 MiB in flight vs 195 MiB per IP) |
| D6 commit log | mmap segments (off-heap, page cache) | `commitlog_total_space` = min(8 GiB, ¼ of the volume) | node | until all memtables dirty in a segment are flushed | forces a flush of the tables dirty in the oldest segment (would flush `r17.rt` and end the stall; §2.4 keeps T below it) |
| D7 baseline | caches, schema, metrics, Netty | own caps | node | standing | — |

Budget: the Java heap (`-Xmx`). D1–D5 and D7 are heap; D6 is not (recorded only because its cap can flush D2).
`memtable_allocation_type: heap_buffers`; no direct-memory domain is claimed (protocol 4 is used so large requests do not
use v5 direct frame buffers, HANDOFF "Lessons").

### 2.3 Configuration and budget audit

- **Source / build:** Cassandra 5.0.9 at repository commit `581de552`; built tree `/mydata/s4/cassandra-base`
  (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`). Stage 2 copies `bin conf lib build pylib tools` once to
  `/mydata/s4/r17/cassandra` and never runs `ant` there.
- **Node `pc96`** (checked read-only 2026-11-20 10:39): x86_64, **32 CPUs**, **125 GiB RAM (122 GiB available)**, 8 GiB
  swap; `/mydata` on a **spinning** RAID volume (`sda`, PERC H710P, `ROTA 1`), 572 GiB free; `/dev/shm` tmpfs 63 GiB, empty;
  no `CassandraDaemon` running; load ≈ 1. Kernel 5.15.0-198-generic, cgroup v2.
- **Capacity constraints, all at shipped defaults (V6):** `concurrent_writes: 32`; `range_tombstone_list_growth_factor`
  1.5 and `initial_range_tombstone_list_allocation_size` 1 (not in the yaml); `memtable_heap_space` unset → heap/4;
  `memtable_cleanup_threshold` unset → ⅓; `memtable_flush_writers` unset → 2; `memtable_allocation_type: heap_buffers`;
  memtable implementation default; `max_mutation_size` unset → 16 MiB (`commitlog_segment_size: 32MiB`);
  `commitlog_total_space` unset → min(8192 MiB, ¼ of the commit-log volume) = **8192 MiB** on a 63 GiB `/dev/shm`;
  `native_transport_max_threads` 128; `native_transport_max_request_data_in_flight` heap/10 and per IP heap/40;
  `native_transport_max_frame_size` 16 MiB; `write_request_timeout: 2000ms`; `native_transport_timeout` 12 s;
  `cql_start_time: REQUEST`; `hinted_handoff_enabled: true`; `enforce_native_deadline_for_hints: false`;
  `max_hints_in_progress` 128 × processors (not applicable to self); guardrails default (column value size disabled;
  single-partition batches not size-checked); key/counter/row caches default. **Read back per run** from
  `system_views.settings` (and JMX for `MaxHintsInProgress`): every value above with its resolved number.
- **Budgets (V7, all heap, all ≥ 512 MiB, so V7 is met without per-case review):** primary **8 GiB**; budget search
  **15,872 MiB** (what `cassandra-env.sh` resolves on `pc96` by itself: min(½ RAM, 15,872 MiB)), **4 GiB**, **2 GiB**;
  secondary set at **512 MiB**. `MaxDirectMemorySize` as `cassandra-env.sh` resolves it (U11 read 15,872M on this host):
  record it. No container memory limit; `systemd-run --user --scope -p MemorySwapMax=0` only keeps swap away.
  Why 8 GiB is the primary and not 2 GiB: the stall needs μ_h < λ_h, and μ_h falls with n ∝ heap (§2.4); 2 GiB is run
  as the predicted surviving boundary.
- **JVM as shipped:** G1, `G1HeapRegionSize=16m`, `G1NewSizePercent=50`, `MaxTenuringThreshold=2`,
  `MaxGCPauseMillis=300`, IHOP 70, `AlwaysPreTouch`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError="kill -9 %p"`;
  `ParallelGCThreads`/`ConcGCThreads` as `cassandra-env.sh` resolves them (U11: 32): record.
- **Deviations (environment / instrumentation only; none changes a capacity setting):**
  - E1 one node on loopback, keyspaces RF 1; ports storage **7710**, ssl 7711, native **9742**, JMX **7799** (if busy, the
    next free block, recorded); cluster name `r17-<label>`.
  - E2 **data, commit log, hints, saved caches and cdc on `/dev/shm/r17/<label>/`** (tmpfs; deleted after each run). Reason:
    the node's disk spins (HANDOFF "Lessons": a node applying every write stalls on a spinning disk), and a disk stall would
    build the same backlog in C and I and confound the attribution. tmpfs size 63 GiB keeps `commitlog_total_space` at its
    8 GiB preferred value. Logs, GC logs, histograms and heap dumps stay on `/mydata/s4/r17/<label>/`.
  - E3 CPU: the node under `taskset -c` on **8 CPUs** chosen at the start as the least loaded (U11 used 24–31), the hot
    client, blob client and poller on 3 other CPUs; the same sets in every arm. Record the JVM's processor count.
  - E4 instrumentation: GC log line in the run's `jvm-server.options`
    (`-Xlog:gc*=info,gc+heap=debug,safepoint=info:file=<run>/logs/gc.log:time,uptime,level,tags:filecount=50,filesize=20M`);
    `CASSANDRA_HEAPDUMP_DIR=<run>`; `-Dcassandra.printHeapHistogramOnOutOfMemoryError=true`. No Byteman, no patch.
  - E5 the only runtime change: `nodetool -p <jmx> setconcurrency MutationStage 1` (two-argument form) in arm I.

### 2.4 Ceiling arithmetic (before any reading)

Per heap H: pool = H/4; trigger T_tr = ⅓ × H/4 (counted). The hot partition is filled to **K₀ = 0.45 × T_tr** so that
the blob memtable, not the hot one, is the largest whenever the trigger fires (blob ≥ 0.55 T_tr at the trigger); n₀ =
K₀ / 510 B. μ_h from U11's fit (∝ n^-1.2, anchored at 41/s at 300 k); the 15,872 MiB point is anchored at B8's 7.8/s
(humongous copies at n > ≈ 1.1 M). Offered load (all arms): **hot λ_h = 48 writes/s** (open loop, ≤ 96 outstanding),
**blob r_b = 12 writes/s × 4 MiB = 48 MiB/s** (open loop, ≤ 32 outstanding); 96 + 32 ≤ 128 request threads.

| H | T_tr | n₀ (K₀) | μ_h predicted | D1 32 × 50 B × n₀ (peak; measured share 0.5–0.65) | blob backlog growth r_b(1 − μ_h/λ_h) × 4 MiB | non-backlog live (D1 + D2 + D4 + D5 + D7) | backlog needed for OOM | predicted endpoint |
|---|---|---|---|---|---|---|---|---|
| 2 GiB | 171 MiB | 158 k (81 MB) | 80–100/s > λ_h | 0.25 GB | 0 (no stall) | 0.5–0.8 GB | — | **none** (boundary) |
| 4 GiB | 341 MiB | 316 k (161 MB) | 35–60/s ≈ λ_h | 0.5 GB | 0–13 MiB/s | 0.8–1.2 GB | ≈ 2.8 GiB | none or late (≥ 220 s); boundary |
| **8 GiB** | 683 MiB | **632 k (322 MB)** | **12–30/s (central 18)** | 1.0 GB (0.5–0.65 GB typical) | **18–36 MiB/s (central 30)** | 1.1–1.9 GB | **≈ 6.0–7.0 GiB** | **heap OOM at ≈ 170–400 s of W (central ≈ 220 s)** |
| 15,872 MiB | 1,323 MiB | 1.22 M (624 MB) | 5–10/s | 2.0 GB (humongous) | 38–43 MiB/s | 2–3.5 GB | ≈ 12.5–13.5 GiB | heap OOM at ≈ 300–360 s (may reach the 450 s cap) |

Other terms: D2 ≈ 290 B × n₀ (183 MB at 8 GiB); D4 ≤ 0.55 T_tr live + one flushing (≤ 0.8 GB at 8 GiB); D5 ≤ 24 × 4 MiB × 2 (frame +
decoded value) ≈ 0.2 GB; D7 ≈ 0.1–0.15 GB; hot backlog (λ_h − μ_h) ≈ 30/s × < 1 KB, negligible. Checks against protective events:

- **Memtable trigger:** in T at 8 GiB the blob memtable fills at μ_h r_b/λ_h ≈ 4.5 blobs/s ≈ 18 MiB/s and reaches 0.55 T_tr
  (394 MB) after ≈ 21 s; it is then the largest and is flushed; the hot memtable keeps n₀ (+ ≈ 18 tombstones/s, < 2 % over
  W). In C the blob memtable fills at 48 MiB/s (flushes every ≈ 8 s).
- **Commit-log cap (a real protective event for T):** the log keeps every segment since F because `r17.rt` stays dirty, so
  the cap is reached after 8 GiB of *applied* blobs and then flushes `r17.rt` (n resets, the stall ends). T applies blobs at
  μ_h r_b/λ_h × 4 MiB and queues them at r_b(1 − μ_h/λ_h) × 4 MiB, so at the OOM (backlog ≈ 6.5 GiB) the log holds
  6.5 GiB × μ_h/(λ_h − μ_h): 2.6 GiB at μ_h = 12, 3.9 GiB at 18, 8 GiB at ≈ 26/s. **The design reaches OOM before the cap
  only while μ_h ≲ 26/s**; above that the cap flushes first (stop rule, §2.5). C writes 48 MiB/s → the cap at ≈ 170 s,
  then periodic forced flushes (harmless for C, recorded).
- **Native limits:** blob bytes in flight ≤ 12/s × 2 s × 4 MiB = 96 MiB < per-IP heap/40 (195 MiB at 8 GiB; 97.7 MiB at 4 GiB and 48.8 MiB at 2 GiB,
  where no request waits 2 s); hot requests < 200 B each.
- **I arm:** one writer at n₀ ≈ 632 k copies ≈ 32 MB per write (≈ 8–12 ms, U11 I: 3.9 ms at 300 k) → ≈ 80–125 hot writes/s
  > 48; blob applies ≈ 12 × 4 ms/s (4 MiB memtable clone + log write on tmpfs); utilization ≈ 0.5–0.65, so no timeouts and a queue ≤ ≈ 100.

So the OOM is reachable at defaults only through D3, and only while D1's multiplicity keeps μ_h below λ_h. Without the
stall (C, I, 2 GiB) the sum of contract capacities plus baseline is ≤ ≈ 0.3 × H.

### 2.5 Workload and environment

- **Node:** `pc96` (local; no ssh). Run directory `/mydata/s4/r17/<label>/` (`conf/` copy with E1–E4, `logs/`, `hist/`,
  heap dump) and `/dev/shm/r17/<label>/` (`data/`, `commitlog/`, `hints/`, `saved_caches/`, `cdc_raw/`), both fresh per
  run. Launch as U11 (`harness/run.sh` of U11 is the model): `( setsid nohup systemd-run --user --scope -p MemorySwapMax=0
  taskset -c <8 CPUs> env CASSANDRA_CONF=… CASSANDRA_LOG_DIR=… MAX_HEAP_SIZE=<H> CASSANDRA_HEAPDUMP_DIR=… JVM_EXTRA_OPTS=…
  <cassandra>/bin/cassandra -f < /dev/null > <run>/logs/stdout.txt 2>&1 & )`; bounded wait for the native port (≤ 180 s);
  find the PID from the process list (U11: `-p` writes no pid file). **Before each run:** `ps -eo pid,cmd | grep
  '[C]assandraDaemon'` (other sessions may run nodes: leave them alone, use free ports), `free -g` (need ≥ H + 35 GiB
  available: heap + ≤ 35 GiB tmpfs + native), `df -h /dev/shm` (≥ 40 GiB free), ports free. **After each run:** kill the node
  and clients by PID, copy readings, `rm -rf /dev/shm/r17/<label>`; keep at most one `.hprof` per heap size (delete the
  others after the printed histogram is saved).
- **Client:** Python 3 with the bundled driver (`lib/cassandra-driver-internal-only-*.zip`, loaded as in U11's
  `client.py`), **protocol 4**, one node whitelist, `FallthroughRetryPolicy` (no retries), CL ONE,
  `token_metadata_enabled=False`, client request timeout 30 s. Two processes: the **hot client** and the **blob client**,
  started together at the start of W, each with its own connection.
- **Schema:** `CREATE KEYSPACE r17 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE r17.rt (pk int, ck int, v int, PRIMARY KEY (pk, ck))`; `CREATE TABLE r17.blob (k bigint PRIMARY KEY, v blob)`
  (all table options default). Hot statement S = `DELETE FROM r17.rt WHERE pk = ? AND ck > ? AND ck < ?` bound to
  `(pk, 4i, 4i+2)`; blob statement B = `INSERT INTO r17.blob (k, v) VALUES (?, ?)` with a fresh k per write and one
  4 MiB (4,194,304 B) random value generated once (serialized mutation > 1,000,000 B, so not cached).
- **Phase F (fill, one request in flight):** T/I/D: unlogged single-partition `BatchStatement`s of **1,000** S to `pk = 0`,
  i ascending (n > 10,000 after 10 batches, so every later tombstone takes the `add()` branch, counted ≈ 510 B as in U11);
  C: batches of 100 S to one partition at a time, round-robin over `pk = 0..999`. Read `MemtableOnHeapDataSize` of
  `r17.rt` every 10 batches; stop at **K₀ = 0.45 × memtable_cleanup_threshold × memtable_heap_space** (resolved values
  read at start). Check `MemtableSwitchCount` = 0. Predicted F time ≤ 90 s at 8 GiB, ≤ 4 min at 15,872 MiB.
- **Quiesce Q:** 10 s idle, one `jcmd <pid> GC.class_histogram` (L0), 20 s idle. Arm I: `setconcurrency MutationStage 1`
  here (check `getconcurrency`).
- **Phase W:** hot client issues S with fresh ascending i above the fill range (C: `pk = i mod 1000`) at **48/s open loop**,
  never more than **96 outstanding** (an issue slot that finds 96 outstanding is skipped and counted as `capped`); blob
  client issues B at **12/s open loop**, never more than **32 outstanding** (same rule). Timeouts and errors are counted,
  never retried. **W stops** at the first of: node death (OOM), **450 s**, or `MemtableSwitchCount` of `r17.rt` rising
  (n reset). Read the flush reason from `system.log`: a **commit-log cap** flush (`COMMITLOG_DIRTY`) is a default protective
  event and the run is a valid `no OOM · protective flush` reading; a **memtable-limit** flush of `r17.rt` (the largest-memtable
  rule, `MEMTABLE_LIMIT`) means the design's K₀ was wrong and the run is `invalid-T` (reason recorded). After W: 5 s, histogram L1 if the node
  lives, then kill.
- **Arms** (labels in §3):
  - **T8 (test):** hot partition `pk = 0`, H = 8 GiB, **×3**.
  - **C8 (matched control):** the same F target K₀, the same W streams, rates, caps and stop rule, but the hot statements
    spread over 1,000 partitions (n ≈ 1,000 per partition, D1 ≈ 50 KB per attempt). H = 8 GiB, **×3**.
  - **I8 (intervention: bound D1's multiplicity):** as T8, plus `setconcurrency MutationStage 1` in Q. **×3**.
  - **B (budget search, T only, ×1 each):** **15,872 MiB** (then ×2 more if it reaches OOM and time allows), **4 GiB**,
    **2 GiB**. If T8 fails to reach OOM in ≥ 2 of its first 3 runs and 15,872 MiB does, run C and I there ×3 instead of
    the 4/2 GiB points (the verdict then uses 15,872 MiB as its fixed condition).
  - **D8 (diagnostic, intrusive, optional):** as T8 with `jcmd GC.class_histogram` every 30 s of W (each forces a full GC;
    never counted toward V1/V2).
  - **S512 (secondary, service loss; U11's retry row):** U11's workload and harness unchanged except: H = 512 MiB, F to
    **0.75** × trigger (batches of 100), W = hot client only, 64 closed-loop in flight, stop at **150 s** or a
    `MemtableSwitchCount` rise. Arms T, C (1,000 partitions), I (`setconcurrency MutationStage 1`), **×3 each**.
- **Stopping budget:** ≤ 450 s of W per run; ≤ 25 runs; no heap above 15,872 MiB; no change of any constraint after a
  failure; a node that does not answer JMX for 120 s is `jcmd Thread.print`-ed once and killed by PID; never start a run
  after **16:50**; every process stopped by **17:20** (America/New_York, 2026-11-20).

### 2.6 Instruments (U independent of K)

- **Poller (JMX, every 1 s; U11's `Poll.java` extended):** G1 Eden/Survivor/Old usage and Old Gen *collection usage*; GC
  MXBean counts/times; for **both** tables `MemtableOnHeapDataSize`, `MemtableSwitchCount`, `WriteLatency` Count (=
  applied local writes per table); `AllMemtablesOnHeapDataSize`; `ThreadPools` `MutationStage` and
  `Native-Transport-Requests` `ActiveTasks`/`PendingTasks`/`CompletedTasks`; `Storage` `TotalHintsInProgress`;
  `DroppedMessage` `MUTATION_REQ` dropped count (self-drops of expired local writes); `ClientRequest` `Write` `Timeouts`;
  `CommitLog` `TotalCommitLogSize`. Any MBean name that differs in 5.0.9 is listed once at start and the real name used.
- **Clients:** per second and per stream: issued, capped, acked, timed out, errors, p50/p99 latency.
- **U per domain:**
  - D3 (claimed holder): **backlog_blob(t) = blob requests issued − capped − `r17.blob` WriteLatency Count**; U_D3 ≈
    backlog_blob × 4 MiB; checked physically by the OOM-time histogram (`[B` bytes above L0, counts of
    `org.apache.cassandra.db.Mutation`, `StorageProxy$…LocalMutationRunnable` subclasses and `StorageProxy$HintRunnable`
    subclasses, `PartitionUpdate`) and, in D8, every 30 s. K for D3: none exists (the native in-flight counter, read from
    the client side as outstanding requests × size, is the nearest and is expected ≤ 96 MiB).
  - D1: `ClusteringBound[]` + `long[]` + `int[]` above L0 in the OOM histogram / D8 histograms (as U11 arm D).
  - Live heap: GC log (heap after each `Pause Full`, humongous regions, pause type), Old Gen collection usage.
- **On OOM (V5):** first `OutOfMemoryError` line and thread from `system.log`/`stdout.txt`, the printed histogram, the
  `.hprof` (one per heap kept), the last 60 s of the GC log, the poller's last 30 rows.
- **Derived per run:** μ_h (hot applies/s over W), blob applies/s, backlog growth slope (MiB/s, least squares over W),
  time to OOM, STW fraction per 60 s window and its maximum, the share of writes timed out per 60 s window.

### 2.7 Predicted response, endpoints and verdict mapping

Predictions (before readings):

1. F reaches K₀ with `MemtableSwitchCount` 0; n₀ = 632 k ± 5 % at 8 GiB (1.22 M at 15,872 MiB); K/n ≈ 510 B.
2. **T8 (×3):** MutationStage active 32, pending rising; μ_h 12–30/s; ≥ 50 % of hot writes time out; blob applies ≈
   2–7/s; `TotalHintsInProgress` rising; no client errors (no `Overloaded`); backlog growth 18–36 MiB/s; **Java heap OOM
   in 3/3 at ≈ 170–400 s of W**; the OOM histogram shows `[B` ≥ 5 GiB above L0 with ≥ 1,300 queued blob `Mutation`s, plus
   D1 arrays ≈ 0.3–1.0 GB. `r17.rt` does not switch. Secondary: the default service-loss criterion (≥ 90 % STW over ≥ 60 s)
   is met in the last 60–120 s before the OOM in ≥ 2/3 runs.
3. **C8 (×3):** pending < 100, no hot timeouts, blob applies ≈ 12/s with p99 < 1 s, backlog ≈ 0, peak live ≤ 2.5 GiB,
   **no OOM**, runs the full 450 s (commit-log forced flushes from ≈ 170 s).
4. **I8 (×3):** active 1; hot applies ≈ 48/s and blob ≈ 12/s (no reduction in useful work); timeouts ≈ 0; pending ≤ 150;
   peak live ≤ 2 GiB; **no OOM**.
5. **B:** 15,872 MiB OOM (≈ 300–360 s; may hit 450 s); 4 GiB survival or late OOM; 2 GiB no stall, no OOM. Largest failing
   budget predicted: 15,872 MiB.
6. **S512 (secondary):** T STW60 ≥ 0.90 in ≥ 2/3 (B05: 0.920); C and I ≤ 0.2.

Endpoints: Java heap OOM (first error + thread, histogram); GC service loss (default criterion, plus the availability
reading: ≥ 50 % of writes timed out over ≥ 60 s, reported, not a verdict criterion); kernel kill (not expected); none.

Verdict mapping ([`oom-agent-playbook.md`](../../../oom-agent-playbook.md)):

- **true positive** — at one fixed heap (8 GiB, or 15,872 MiB per the arm rule above): T reaches a Java heap OOM in ≥ 3
  runs, C ×3 and I ×3 at that heap do not, the OOM-time histogram shows the D3 backlog (blob `Mutation`s / `[B`) as the
  largest holder with D1 arrays present, and every constraint is at its default (V1–V7). Status `verified-OOM ·
  deployment` (environment deviations E1–E5 only; tmpfs data is an environment choice favouring the controls).
- **retry** — OOM in T but also in C or I (the backlog is not caused by the copies; B18's failure mode); T OOM in < 3 runs
  at every heap; GC service loss without OOM (T8 or S512, `verified-gap` if V1–V5 hold); a T run whose `r17.rt` switched or
  whose stall did not form for a reason outside the design (disk, another node on the host); T runs at both 8 GiB and
  15,872 MiB ended by the commit-log cap flush before an OOM (μ_h above ≈ 26/s; the better design is then named from the
  measured μ_h and backlog slope).
- **false positive** — every valid T run at 8 GiB and 15,872 MiB ran 450 s without OOM with the stall measured (μ_h, the
  backlog slope) and the backlog's growth stopping below the headroom (or μ_h ≥ λ_h at defaults, so the stall cannot form
  at the 128-thread arrival cap), **and** S512 gives no service loss (≤ 1/3 T runs ≥ 0.90): then neither endpoint is
  reachable at defaults with this holder.

### 2.8 Controls, intervention, time plan

- **Matched control C8:** same counter trajectory (K₀), same offered load (48/s hot, 12 × 4 MiB/s blob), same caps,
  same writer count; only n per partition differs (≈ 1,000 vs ≈ 632 k). Isolates D1's multiplicity as the cause of the
  stall from the blob load itself and from D2.
- **Causal intervention I8:** bound D1's multiplicity to 1 (`setconcurrency MutationStage 1`), a runtime change in the
  intervention arm only; throughput of both streams is recorded so a stage that stops useful work is not mistaken for
  protection. If the node refuses 1, use 2 and record it.
- **Time plan (America/New_York, 2026-11-20; stage 2 starts ≈ 12:00, hard end 17:30):**

  | Window | Work | Est. |
  |---|---|---|
  | 12:00–12:50 | freeze check; node check; copy build; harness from U11's (`run.sh` dirs/ports/tmpfs, `client.py` open-loop hot + blob process, `Poll.java` extra MBeans, `analyze.py`); shakedown at 4 GiB with 60 s W (not a reading) | 50 min |
  | 12:50–13:30 | T8 ×3 (start ≈ 1 min, F ≈ 1.5 min, Q 0.5 min, W ≤ 7.5 min, dump/cleanup ≈ 2 min ≈ 12 min each) | 36 min |
  | 13:30–14:00 | C8 ×3 (≈ 10 min each) | 30 min |
  | 14:00–14:30 | I8 ×3 (≈ 10 min each) | 30 min |
  | 14:30–15:05 | B: 15,872 MiB (≈ 16 min, F ≈ 4 min, dump ≈ 3 min), 4 GiB (≈ 10 min), 2 GiB (≈ 9 min) | 35 min |
  | 15:05–15:40 | 15,872 MiB ×2 more if it failed, else D8 (≈ 12 min) | ≤ 35 min |
  | 15:40–16:30 | S512: T, C, I ×3 (≈ 5 min each) | 45 min |
  | 16:30–17:20 | write-up (§3, §4, V1–V7 table), write-back, clean-up | 50 min |

  If stage 2 starts late or runs overrun, drop in this order: S512's C and I (keep T ×3), then D8, then the 15,872 MiB
  repeats, then 2 GiB, then 4 GiB; never drop T8, C8, I8 ×3. Never start a run after 16:50; stop everything by 17:20.
- **Resources:** peak RAM ≈ 16 GiB heap + ≈ 2 GiB native + ≤ 35 GiB tmpfs (C at 8 GiB: commit log ≤ 8 GiB + flushed blob
  SSTables ≤ 22 GB + compaction scratch) ≈ 53 GiB of 122 GiB; `/mydata` ≤ 16 GiB per kept heap dump (≤ 30 GiB total); CPU 8 for the node + 3.
- **Left on the node at the end:** `/mydata/s4/r17/` with logs (no data), `/dev/shm/r17` removed, nothing running.

`sha256 of §1–§2 at freeze: 6847196ef4bea0f524bf6a19bd218152443065809c971df3cedbcd78b3e92ac4` (lines 23–365 of this file, from "## 1. Candidate" through the line before this one, `sed -n '23,365p' | sha256sum`; 2026-11-20 10:47 America/New_York) · amendments after the freeze: A1 (interruption note) and A2 (time plan +10 h, clock only), §3.0, 2026-11-20 21:30. Stage 2 added 8 lines to the Summary, so §1–§2 are now lines 31–373: `sed -n '31,373p' | sha256sum` gives the same hash (checked 2026-11-20 21:30).

## 3. Runs (stage 2)

Stage 2 by a fresh OOM-agent session on `pc96` (the local node), 2026-11-20 10:54–13:13 and 21:27–≈ 22:30 America/New_York.
Freeze check at 10:54: `sed -n '23,365p' | sha256sum` = `6847196ef4bea0f524bf6a19bd218152443065809c971df3cedbcd78b3e92ac4`
(matches §2's last line).

### 3.0 Dated notes and amendments

- **A1 (2026-11-20 21:30 America/New_York) — interruption by the API usage limit, resume.** The stage-2 session was cut
  off by an API usage limit (not by the design) at ≈ 13:15; the coordinator resumed it at ≈ 21:30. State at the resume:
  no `CassandraDaemon`, no harness process, `/dev/shm/r17` empty, `/mydata/s4/r17` 373 MB. The run sequence
  (`seq.sh`, node-side, detached) had **finished every run of the frozen design cleanly before the cut-off** (last line of
  `/mydata/s4/r17/seq.log`: `13:12:49 seq done`; every run directory has its `DONE` marker; the last run, `S512-I3`, ended
  13:12:44 with its normal stop rule). **No run was cut mid-run, so none is redone**; all 22 readings below are reused
  as taken (among them the S512-T readings STW max over 60 s = 0.908, 0.908, 0.910). Only the analysis, log excerpts and
  this write-up were done after the resume.
- **A2 (2026-11-20 21:30) — time plan shifted (clock only).** New hard deadline 03:30 2026-11-21 (was 17:30): every time in
  §2.8's plan and §2.5's stopping budget moves by +10 h (no run starts after 02:50, every process stopped by 03:20);
  the drop order is unchanged. The design is otherwise unchanged. In fact no run was needed after the resume (A1).
- **Order of arms (not a design change):** T8 ×3 was run first and then B 15,872 MiB, because §2.5's arm rule ("if T8
  fails to reach OOM in ≥ 2 of its first 3 runs and 15,872 MiB does, run C and I there") depends on those two readings;
  15,872 MiB did not reach OOM, so C8, I8, B 4 GiB, B 2 GiB, D8 and S512 followed as planned. The "15,872 MiB ×2 more
  if it failed" slot was therefore filled by D8, as §2.8 says.
- **Harness fixes before any reading was used:** `analyze.py`/`run.sh` first counted the `-XX:OnOutOfMemoryError` JVM
  argument line as an OOM line; the match was narrowed to `java.lang.OutOfMemoryError` (11:18, during B15872-1's fill;
  `run.sh` changed only at a line the running copy had not reached; no reading changed).
- **Shakedown** `shake-4G` (4 GiB, T, 60 s W; 10:59–11:02) checked the harness; not a reading.

### 3.1 Environment

- Node `pc96`, 32 CPUs, 125 GiB (121 GiB available at every start), kernel 5.15.0-198-generic, cgroup v2, OpenJDK
  11.0.33, G1. No other `CassandraDaemon` on the host at any start (checked by `run.sh` each time; logged in each
  `driver.log`); per-CPU load ≤ 0.13 before the first run.
- Build copied once from `/mydata/s4/cassandra-base` (`bin conf lib build pylib tools`) to `/mydata/s4/r17/cassandra`;
  `apache-cassandra-5.0.9-SNAPSHOT.jar`; no `ant`. Poller compiled to `/mydata/s4/r17/classes`.
- E1 ports 7710/7711/9742/7799 (free at every start), cluster `r17-<label>`, RF 1. E2 data/commit log/hints/caches/cdc on
  `/dev/shm/r17/<label>/` (deleted after each run; ≤ 3 GiB used). E3 node `taskset -c 24-31` (JVM affinity list 24-31),
  hot client CPU 20, blob client CPU 21, poller CPU 22. E4 GC log line, `CASSANDRA_HEAPDUMP_DIR=<run>`,
  `-Dcassandra.printHeapHistogramOnOutOfMemoryError=true`. E5 `nodetool -p 7799 setconcurrency MutationStage 1` in I arms
  (`getconcurrency` read back `MutationStage 0 1`). Node launched under `systemd-run --user --scope -p MemorySwapMax=0`.
- **Resolved values (V6/V7, every run):** `-Xmx` as the arm says (8G ×10, 15872M ×1, 4G ×1, 2G ×1, 512M ×9);
  **`MaxDirectMemorySize` = 15872M** (all 22 runs, as `cassandra-env.sh` resolves it from RAM); `ParallelGCThreads` = 32,
  `ConcGCThreads` = 32. From `system_views.settings` (8 GiB run): `concurrent_writes` 32, `memtable_heap_space` 2048MiB
  (= heap/4), `memtable_cleanup_threshold` 0.33333334, `memtable_flush_writers` 2, `memtable_allocation_type` heap_buffers,
  `range_tombstone_list_growth_factor` 1.5, `initial_range_tombstone_list_allocation_size` 1, `max_mutation_size`
  16384KiB, `commitlog_segment_size` 32MiB, **`commitlog_total_space` 8192MiB**, `native_transport_max_threads` 128,
  `native_transport_max_request_data_in_flight` 858993459B (heap/10), `…_per_ip` 214748364B (heap/40; 416074956B at
  15,872 MiB, 13421772B at 512 MiB), `native_transport_max_frame_size` 16MiB, `write_request_timeout` 2000ms,
  `native_transport_timeout` 12s, `cql_start_time` REQUEST, `hinted_handoff_enabled` true,
  `enforce_native_deadline_for_hints` false, `native_transport_rate_limiting_enabled` false, key cache 100MiB, counter
  cache 50MiB, row cache 0MiB, column value size guardrails unset. JMX `StorageProxy.MaxHintsInProgress` = 1024
  (128 × 8 processors). Every capacity setting at its shipped default (V6).
- Harness (`harness/`): `run.sh` (one run), `seq.sh` (runs in sequence; refuses to start after 16:50 or with a STOP file),
  `client.py` (schema, settings, fill, open-loop `stream`, U11's closed-loop mode for S512), `Poll.java` (JMX 1 s, the
  MBeans of §2.6; all names resolved in 5.0.9, listed in each `poll.err`), `analyze.py`, `excerpt.sh`, `hprofhist.py`
  (unused: no OOM, no `.hprof`).
- Full logs: `pc96:/mydata/s4/r17/<label>/` (`logs/driver.log, poll.log, hot.csv, blob.csv, gc.log*, system.log,
  debug.log, rss.log, settings.json, fill.json, hot.json, blob.json | write.json, flushes.txt`, `hist/L0.txt, L1.txt[, D*.txt]`).
  Excerpts: [`logs/<label>/`](logs/) (`analysis.json`, poll every 10 s + last 30 rows, client CSV every 10 s, GC pause
  excerpt, histogram heads, flush lines).

### 3.2 Runs

F = fill (n₀ = tombstones in `r17.rt`, K = `MemtableOnHeapDataSize` after F); μ_h = `r17.rt` applied writes/s over W;
"blob/s" = `r17.blob` applied writes/s; A = MutationStage active (max / mean); backlog = blob requests sent − applied
(× 4 MiB = U_D3); STW60 = max share of wall time in STW pauses over any 60 s window of W; Old = Old Gen usage after the
last collection (max). Offered load in every R run: hot 48/s (≤ 96 out), blob 12 × 4 MiB/s (≤ 32 out).

| Run (time) | Arm · heap | F: n₀ (K, K/n) | W end (reason) | μ_h · blob/s | A max / mean; pending max | Backlog peak | Old max; full GCs; STW60 | Hot p50 / p99, timeouts | Endpoint |
|---|---|---|---|---|---|---|---|---|---|
| T8-1 (11:03) | T · 8 GiB | 640 k (324.0 MB, 506 B) | 149 s (r17.rt `COMMITLOG_DIRTY` flush) | 47.6 · 11.9 | 8 / 0.9; 0 | 0 | 3.1 GiB; 0; 0.032 | 12 / 88 ms, 0 | none · protective flush |
| T8-2 (11:07) | T · 8 GiB | 640 k (324.0 MB) | 150 s (`COMMITLOG_DIRTY`) | 47.7 · 11.9 | 9 / 1.0; 1 | 0 | 7.0 GiB; 1 (after 671 MiB); 0.045 | 11 / 102 ms, 0 | none · protective flush |
| T8-3 (11:12) | T · 8 GiB | 640 k (324.0 MB) | 150 s (`COMMITLOG_DIRTY`) | 47.7 · 11.9 | 6 / 0.6; 0 | 0 | 3.6 GiB; 0; 0.032 | 13 / 79 ms, 0 | none · protective flush |
| B15872-1 (11:17) | T · 15,872 MiB | 1.23 M (624.9 MB, 508 B) | **450 s (cap)** | **4.95 · 1.40** | **32 / 31.8; 12,776** | **2,310 (9.0 GiB), slope 23.6 MiB/s, flattening** | **15.2 GiB; 269; 0.875** | 54 / 12,968 ms; 12,693 of 12,840 hot and 2,892 of 2,940 blob timed out | **none** (GC thrash, live ≈ 11.7 GiB) |
| C8-1 (11:29) | C · 8 GiB | 1.108 M over 1,000 partitions (322.2 MB, 291 B) | 149 s (`COMMITLOG_DIRTY`) | 47.8 · 11.9 | 1 / 0.2; 0 | 0 | 0.3 GiB; 0; 0.006 | 1.3 / 2.3 ms, 0 | none · protective flush |
| C8-2 (11:44) | C · 8 GiB | as C8-1 | 150 s (`COMMITLOG_DIRTY`) | 47.6 · 11.9 | 1 / 0.0; 0 | 0 | 0.3 GiB; 0; 0.005 | 1.3 / 2.2 ms, 0 | none · protective flush |
| C8-3 (11:59) | C · 8 GiB | as C8-1 | 150 s (`COMMITLOG_DIRTY`) | 47.8 · 12.0 | 1 / 0.0; 0 | 0 | 0.3 GiB; 0; 0.004 | 1.4 / 2.3 ms, 0 | none · protective flush |
| I8-1 (12:14) | I · 8 GiB | 640 k (324.0 MB) | 151 s (`COMMITLOG_DIRTY`) | 47.8 · 12.0 | 1 / 0.6; 7 | 0 | 7.5 GiB; 1 (after 468 MiB); 0.038 | 14 / 94 ms, 0 | none · protective flush |
| I8-2 (12:19) | I · 8 GiB | 640 k | 151 s (`COMMITLOG_DIRTY`) | 47.8 · 12.0 | 1 / 0.8; 14 | 0 | 7.7 GiB; 1; 0.038 | 14 / 86 ms, 0 | none · protective flush |
| I8-3 (12:24) | I · 8 GiB | 640 k | 151 s (`COMMITLOG_DIRTY`) | 47.8 · 11.9 | 1 / 0.8; 16 | 0 | 7.1 GiB; 1; 0.038 | 13 / 88 ms, 0 | none · protective flush |
| B4-1 (12:29) | T · 4 GiB | 330 k (165.9 MB) | 149 s (`COMMITLOG_DIRTY`) | 47.7 · 11.9 | 5 / 0.3; 0 | 0 | 0.1 GiB; 0; 0.020 | 8 / 44 ms, 0 | none · protective flush |
| B2-1 (12:34) | T · 2 GiB | 170 k (84.3 MB) | 150 s (`COMMITLOG_DIRTY`) | 47.6 · 11.9 | 2 / 0.2; 0 | 0 | 0.1 GiB; 0; 0.015 | 4.5 / 25 ms, 0 | none · protective flush |
| D8-1 (12:38) | D · 8 GiB (histogram every 30 s) | 640 k | 151 s (`COMMITLOG_DIRTY`) | 47.9 · 12.0 | 19 / 1.2; 1 | 0 | 0.5 GiB; 4 (forced); 0.039 | 14 / 192 ms, 0 | none; live 458–542 MiB in the 4 W histograms, D1 arrays ≤ 24 MiB, `Mutation` ≤ 1 |

S512 (secondary, U11's workload: F to 0.75 × trigger with batches of 100, W = 64 closed-loop hot writes, 150 s or a switch):

| Run (time) | Arm | F (K) | W end (reason) | Hot applied/s | A mean; pending max | Full GCs (after, MiB) | STW60 (STW over W) | Timeouts | Endpoint |
|---|---|---|---|---|---|---|---|---|---|
| S512-T1 (12:43) | T, pk 0 | 67 k (33.9 MB) | 152 s (cap) | 94.1 | 31.4; 44 | 469 (123–164) | **0.908** (0.891) | 786 of 14,328 | GC service loss (default criterion met) |
| S512-T2 (12:48) | T | 67 k | 152 s (cap) | 93.8 | 31.6; 46 | 472 (136–157) | **0.908** (0.891) | 844 of 14,174 | GC service loss |
| S512-T3 (12:53) | T | 67 k | 152 s (cap) | 93.5 | 31.5; 44 | 477 (126–166) | **0.910** (0.890) | 801 of 14,222 | GC service loss |
| S512-C1 (12:58) | C, 670 partitions | 67 k (33.6 MB) | **4.9 s** (r17.rt `MEMTABLE_LIMIT` flush) | 6,456 | 0.4; 0 | 0 | 0.000 (0.001) | 0 of 32,284 | none |
| S512-C2 (13:00) | C | 67 k | 5.0 s (`MEMTABLE_LIMIT`) | 6,305 | 0.2; 1 | 0 | 0.000 (0.001) | 0 of 31,525 | none |
| S512-C3 (13:02) | C | 67 k | 4.9 s (`MEMTABLE_LIMIT`) | 6,193 | 0.4; 1 | 0 | 0.000 (0.001) | 0 of 30,965 | none |
| S512-I1 (13:04) | I | 67 k | 27 s (`MEMTABLE_LIMIT`) | 1,051 | 0.9; 63 | 0 | 0.118 (0.263) | 0 of 31,025 | none |
| S512-I2 (13:07) | I | 67 k | 26 s (`MEMTABLE_LIMIT`) | 982 | 0.9; 63 | 0 | 0.113 (0.262) | 0 of 25,545 | none |
| S512-I3 (13:10) | I | 67 k | 26 s (`MEMTABLE_LIMIT`) | 977 | 1.0; 62 | 0 | 0.114 (0.263) | 0 of 26,888 | none |

(S512-C filled 100 per batch round-robin, so only 670 of the 1,000 partitions were reached before K₀; every C and I run
applied 1.8–2.3 × the writes a T run applied in its whole 150 s before the memtable switch ended it.)

### 3.3 Readings against the predictions (§2.7)

1. **F (prediction 1): met.** n₀ = 640 k at 8 GiB (predicted 632 k ± 5 %), 1.23 M at 15,872 MiB (1.22 M); K/n = 506–508 B
   (`add()` branch); `MemtableSwitchCount` 0 at the end of every F. C's spread fill is counted at 291 B per tombstone, so
   C reached the same K₀ with 1.108 M tombstones (≈ 1,108 per partition).
2. **T8 (prediction 2): not met — the stall did not form.** With the open-loop 48/s hot stream, MutationStage served every
   hot write as it arrived (μ_h 47.6–47.7/s = λ_h, A mean 0.6–1.0, pending ≤ 1, no timeout, no hint, `TotalHintsInProgress`
   0). One writer at n₀ = 640 k needs ≈ 12.5 ms per write (I8: A mean 0.6–0.8 at 48/s), so the stage capacity with no
   contention is ≈ 80/s > 48/s; the 32-writer CAS thrash that U11's 64-closed-loop workload produced (μ_h ≈ 18/s
   predicted from U11's fit) is never entered from an uncongested start. Blob writes were applied at the offered 12/s
   (p99 ≤ 139 ms), so they filled the commit log at 48 MiB/s and the **commit-log cap (8 GiB) flushed `r17.rt`
   (`COMMITLOG_DIRTY`) at 149–150 s** in all three runs — the default protective event of §2.4/§2.5; valid
   `no OOM · protective flush` readings (no `MEMTABLE_LIMIT` flush of `r17.rt`, so K₀ was right).
3. **C8 (prediction 3): met** (no stall, no timeout, live ≤ 0.35 GiB), except that C, like T, ended at the commit-log cap
   flush at 149–150 s (the shared stop rule; §2.7 had expected 450 s).
4. **I8 (prediction 4): met** (A 1, μ_h 47.8/s, blob 12/s, pending ≤ 16, no timeout, no OOM); ended at the cap flush, 151 s.
5. **B (prediction 5): partly met.** 4 GiB and 2 GiB: no stall, no OOM (as predicted for 2 GiB; 4 GiB "survival" as
   one of the two predicted outcomes). **15,872 MiB: the stall formed at once and the backlog built, but no OOM in the
   450 s W cap** (predicted OOM at ≈ 300–360 s, "may hit 450 s"). Per minute of W (from `poll.log`, `blob.csv`, `gc.log`):

   | min | STW share | full GCs | heap after full GC (max, MiB) | blob sent | blob applied | blob backlog | hot applied | MutationStage pending | hints in progress |
   |---|---|---|---|---|---|---|---|---|---|
   | 1 | 0.42 | 11 | 3,689 | 601 | 176 | 425 | 561 | 1,989 | 380 |
   | 2 | 0.56 | 19 | 5,305 | 1,130 | 298 | 832 | 991 | 3,867 | 1,514 |
   | 3 | 0.64 | 25 | 7,177 | 1,648 | 396 | 1,252 | 1,363 | 5,890 | 1,922 |
   | 4 | 0.70 | 32 | 8,635 | 2,166 | 472 | 1,694 | 1,658 | 8,062 | 1,551 |
   | 5 | 0.79 | 39 | 10,136 | 2,558 | 538 | 2,020 | 1,893 | 9,922 | 1,663 |
   | 6 | 0.85 | 49 | 11,358 | 2,791 | 584 | 2,207 | 2,065 | 11,348 | 1,662 |
   | 7 | 0.87 | 58 | 11,693 | 2,907 | 611 | 2,296 | 2,175 | 12,388 | 2,562 |
   | 7.5 | 0.86 | 64 | 11,887 | 2,940 | 630 | 2,310 | 2,241 | 12,877 | 2,476 |

   (cumulative except STW share and full GCs, which are per minute). The backlog grew ≈ 420 blobs/min (28 MiB/s) for
   4 min, then flattened (≈ 190 and 90 blobs/min, then 14 in the last 30 s) because **arrivals fell, not because applies rose**: the blob client
   could send only while it had < 32 requests outstanding, and under GC thrash each request was held well past the 2 s
   timeout (blob p99 2.56 s; 2,460 of 5,400 blob slots `capped`; hot 8,759 capped), with `Native-Transport-Requests`
   active up to 126 of its 128 threads. The JVM ended W at Old after full GC ≈ 11.6–11.9 GiB of 15.5 GiB, STW60 0.875,
   RssAnon max 16.8 GiB; `DroppedMessage MUTATION_REQ` +5,098 (expired local writes re-submitted as hints, `TotalHints`
   unchanged: none written to disk).
   **Holder at the end of W (L1, `jcmd GC.class_histogram`, 5 s after W, node alive):** total live 11,761 MiB (L0 381 MiB);
   `[B` 10,383 MiB (+10,309 MiB over L0), **12,898 `org.apache.cassandra.db.Mutation` and 12,898 `PartitionUpdate`**
   (one per queued write), **12,898 `StorageProxy$4`** (the `LocalMutationRunnable` built by `performLocally`) and
   **2,466 `StorageProxy$LocalMutationRunnable$1`** (expired writes re-submitted by `LocalMutationRunnable.run` →
   `submitHint`), RTL arrays (`ClusteringBound[]`, `long[]`, `int[]`) 1,038 MiB above L0 (D1). So U_D3 ≈ 9.0–10.3 GiB
   against K (native in-flight bytes, released at each timeout) ≤ 128 MiB: the queued local writes are the dominant live
   holder, as §2.1 claims — but the node stayed up.
6. **S512 (prediction 6): T met** — STW60 0.908, 0.908, 0.910 (3/3 ≥ 0.90; marginal), STW over the whole W 0.89, 469–477
   full GCs per 150 s at a live heap of 123–166 MiB after full GC, A 31.4–31.6, 5.5–5.9 % of writes timed out. **C and I
   could not run their 150 s:** both applied writes 10–70 × faster than T and reached the memtable flush (`MEMTABLE_LIMIT`)
   after 5 s (C) and 26–27 s (I), the U11 stop rule; over those windows C's STW share was 0.001 and I's 0.26 (no 60 s
   window exists; STW60 computed over a 60 s window holding all of W: 0.000 and 0.11–0.12).
7. **D8:** no stall at 8 GiB (as T8), so its four W histograms show only the memtables and in-flight work (458–542 MiB live).

### 3.4 What was left on the node

`pc96:/mydata/s4/r17/` 373 MB: the build copy `cassandra/` (≈ 286 MB), `classes/`, `seq.log`, and one directory per run
(`shake-4G`, `T8-1..3`, `B15872-1`, `C8-1..3`, `I8-1..3`, `B4-1`, `B2-1`, `D8-1`, `S512-{T,C,I}{1..3}`) with logs and
histograms only (no data, no `.hprof`). `/dev/shm/r17` removed. No process left running (no `CassandraDaemon`, poller,
client or sequence script).

## 4. Conclusion (stage 2)

- **Verdict: `retry`** ([`oom-agent-playbook.md`](../../../oom-agent-playbook.md)).
- **Protocol status (detail): `candidate`** — no OOM in any of 13 main-design runs; the claimed holder (D3, the
  MutationStage local-write backlog) was measured once as the dominant live holder (15,872 MiB, 9.0–10.3 GiB) without an
  endpoint; the secondary GC service loss (S512) is `candidate` too (V1 met, V2/V3/V4 incomplete, see the table).
- **Reason:** The frozen workload never put the hot partition into the 32-writer CAS thrash at 2, 4 or 8 GiB: with the
  hot stream open-loop at 48/s, one MutationStage writer serves a hot write at n₀ = 640 k in ≈ 12.5 ms (I8 active 0.6–0.8),
  so the stage keeps up (μ_h 47.6–47.9/s = λ_h, active mean ≤ 1.2, 0 timeouts in T8 ×3, B4, B2, D8), blob writes are
  applied at the offered 48 MiB/s, and the 8 GiB commit-log cap flushed `r17.rt` (`COMMITLOG_DIRTY`, a default
  protective event) at 149–151 s in every 8/4/2 GiB run, C8 and I8 included. The U11 thrash state (μ_h ≈ 8–41/s) needs
  ≥ 32 hot writes in flight at once, which a 48/s open-loop start at 8 GiB never creates. At **15,872 MiB** (n₀ = 1.23 M,
  ≈ 25 ms per write) the stall formed at once: MutationStage active 31.8 of 32, μ_h 4.95/s, blob applies 1.40/s, pending
  12,776, 98.9 % of hot and 98.4 % of blob requests timed out, and the backlog reached **2,310 blobs ≈ 9.0 GiB**; 5 s after
  W the histogram held **12,898 queued `Mutation`s, 10.3 GiB of `byte[]` above baseline, 2,466 re-submitted expired local
  writes and 1.04 GiB of RTL copies**, with Old after full GC 11.6–11.9 GiB of 15.5 GiB and STW60 0.875 — but **no OOM in the
  450 s cap**: the backlog's growth fell from ≈ 420 to ≈ 30 blobs/min because GC thrash held each request thread past its
  2 s timeout (`Native-Transport-Requests` active up to 126 of 128; 2,460 of 5,400 blob slots capped by the client's
  32-outstanding limit), so arrivals, not applies, stopped the growth at ≈ 76 % of the heap (n = 1). U11's closed-loop
  workload at 512 MiB gave the default GC service-loss criterion 3/3 (STW60 0.908, 0.908, 0.910; marginal), while its
  C and I arms ran only 5 s and 26–27 s before their memtable flush (STW 0.001 and 0.26 over those windows). This is not
  a false positive: T8 never formed the stall the design depends on (the thrash state is a named factor left untried at
  8 GiB), the 15,872 MiB growth was throttled by the offered-load split rather than bounded by a control, and S512 shows
  service loss in 3/3. It is not a true positive: no OOM (V1 0/3 at 8 GiB, 0/1 at 15,872 MiB).
- **Mechanism, as far as measured (root cause, for the next design):** MutationStage's SEP queue has no bound; a local
  write that misses its 2 s deadline releases its request thread and native in-flight bytes but stays queued, and on
  dequeue is re-submitted (`LocalMutationRunnable` → `submitHint`, self exempt from `checkHintOverload`), holding its
  decoded `Mutation` until applied; nothing counts these bytes. Once 32 writers thrash on a hot range-tombstone partition,
  every local write queues behind them (15,872 MiB: 9.0–10.3 GiB queued, U_D3 ≫ K). The only brake observed is implicit:
  128 request threads × the time each is held (≥ 2 s, longer under GC), which caps how fast the queue can grow.
- **V1–V7** (main endpoint: Java heap OOM; secondary: GC service loss, S512):

  | | Main (OOM, 8 GiB; 15,872 MiB) | Secondary (service loss, 512 MiB) |
  |---|---|---|
  | V1 repetition | **not met**: 0/3 (8 GiB), 0/1 (15,872 MiB) | met: 3/3 STW60 ≥ 0.90 (0.908–0.910, marginal) |
  | V2 matched control | C8 ×3: no stall, no endpoint (but T8 had none either) | C ×3: none, but W 5 s only (memtable flush), no 60 s window |
  | V3 U vs K | D3 measured at 15,872 MiB (L1 histogram; backlog from counters), D1 1.04 GiB; K ≤ 128 MiB | D1 not measured in R17 (U11 arm D only) — **not met here** |
  | V4 intervention | I8 ×3: no endpoint (but T8 had none either) | I ×3: none, W 26–27 s only (memtable flush) |
  | V5 initiating failure | no OOM | GC logs over W kept (469–477 full GCs per 150 s, live 123–166 MiB) |
  | V6 defaults | met (all capacity settings default, read back) | met |
  | V7 budget | met (8 GiB, 15,872 MiB = `cassandra-env.sh`'s own value on this node) | met (512 MiB, standing minimum) |

- **For retry — what a better design should change:**
  1. **Enter the thrash state on purpose** at 8 GiB and 15,872 MiB: start W with U11's closed loop (64 hot writes in flight
     for ≈ 15 s), then keep the hot stream closed-loop at 32 in flight (or open-loop just above the thrash μ_h, ≈ 10/s at
     15,872 MiB, ≈ 20–25/s at 8 GiB); an uncongested open-loop start stays uncongested (R17 T8: one writer serves ≈ 80/s).
  2. **Give the request threads to the memory, not to the trigger:** at most ≈ 32 of the 128 `Native-Transport-Requests`
     threads for hot writes, ≈ 96 for blob writes, from 2–3 loopback client addresses so the per-IP in-flight limit
     (heap/40: 205 MiB at 8 GiB, 397 MiB at 15,872 MiB) is not the cap, and larger values (≈ 12 MiB, below the 16 MiB
     `max_mutation_size` and frame size) so each thread held for ≥ 2 s queues 3 × the bytes. R17's arrival rate fell to
     ≈ 2 MiB/s under GC thrash with only 32 blob requests outstanding.
  3. **W ≥ 900 s** at 15,872 MiB (growth was still positive at 450 s), with the same commit-log check (once stalled, blob
     applies are ≈ 1.4/s, so the 8 GiB cap is ≈ 25 min away).
  4. For the service-loss reading at 512 MiB: let C and I run ≥ 60 s (stop on a switch only in T, or fill C/I lower) and
     add a D-arm histogram series for D1, so V2–V4 can be met (`verified-gap`).
