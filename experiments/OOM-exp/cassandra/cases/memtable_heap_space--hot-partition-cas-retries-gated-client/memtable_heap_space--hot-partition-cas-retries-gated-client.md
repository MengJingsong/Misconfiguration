# R16 (retry of B18) — memtable_heap_space: hot-partition CAS retries past the flush barrier, 1.25 MiB batches and a client that never re-sends while a write is pending  <!-- file: cassandra/cases/memtable_heap_space--hot-partition-cas-retries-gated-client/memtable_heap_space--hot-partition-cas-retries-gated-client.md -->

| Field | Value |
|---|---|
| Case ID | `R16` (R = a new attempt at an earlier case; README "ID prefixes"), retry of **B18**. Predicted class by the protocol's measurement table: **bypass, enforcement failure** (U > C and K > C in the memtable pool: the blocking-cohort exemption admits failed-CAS clones past the limit); stage 2 labels it from the readings (§2.1) |
| From | retry-list row **B18** of [`phase2-retry-list.md`](../../phase2-retry-list.md) (Status `picked again: R16 (2026-11-20)`); B18 came from the cluster `OC-323` (primary), `OC-46`, `OC-367`, `OC-373`, `OC-257`, `OC-266`, `OC-41` |
| Phase-1 case files | as B18 (its header and §1.3): [`excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous.md) (OC-323, OC-46), [`excess_waste_offset-updatewastedallocationtracker-delta--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/excess_waste_offset-updatewastedallocationtracker-delta--autonomous.md) (OC-367, OC-373), [`max-cloned-size-allocate-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max-cloned-size-allocate-size--autonomous.md) (OC-257), [`slab-region-size-region-allocate-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/slab-region-size-region-allocate-capacity--autonomous.md) (OC-266), [`memtable_heap_space-tryAllocate-limit--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/memtable_heap_space-tryAllocate-limit--autonomous.md) (OC-41); stage-4 results under [`stage4-runtime-verification/results/`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9; on pc75 `/mydata/s4/cassandra-base`, `build/apache-cassandra-5.0.9-SNAPSHOT.jar`), OpenJDK 11.0.33 |
| Stage 1 (design) | OOM-agent stage-1 session, 2026-11-20 10:30–11:50 America/New_York; nothing run (read-only check of pc75, read-only JIRA REST searches) |
| Stage 2 (verify) | fresh OOM-agent session, 2026-11-20 10:39–12:10 America/New_York, pc75 (lifetimes 10:45–11:52); offline dump diagnostics on pc96 |
| Verdict | **`retry`** (protocol status `candidate`: V1–V3, V5–V7 met for T at 2 GiB, V4 not met; §2.7 outcome row 3) |

## Summary

- **Conclusion:** **retry.** A hot-partition write load at shipped defaults runs Cassandra 5.0.9 out of heap: T 3/3 at 2 GiB in 7 s
  with no client timeout, 3/3 at the largest resolved heap (15,872 MiB), and the gated `perthread` control survives 3/3. But the intervention
  (`concurrent_writes: 4`), which removed the claimed overshoot entirely, also died 3/3, and the new pool reading shows the bytes that fill
  the heap are **not** counted by `memtable_heap_space` at the endpoint (pool 0.54–0.93 × C, live slab regions 3.5 × C). V4 and the
  attribution fail, so the design must be redone around the holder that was found.
- **Root cause (found in R16, diagnostic on the kept dumps):** every MutationStage worker (a `SEPWorker` thread) keeps a pooled
  `BTree.Updater` in a thread-local `TinyThreadLocalPool`; `reset()` clears its buffers but not its `updateF`, which is the
  `AtomicBTreePartition$Updater` of the thread's last write and reaches that whole partition. After the memtable is flushed and discarded
  (its charge released from the pool), its partition and the slab regions under it stay reachable, uncounted, on each worker thread that
  last wrote it. 2.7 × C of regions are reachable only through that one field in the T and I OOM dumps (0.84 × C at idle in the control).
  With one hot partition each pinned partition is a whole memtable, which the blocking-cohort overshoot makes larger; that only speeds the
  OOM up (7 s vs 64–100 s).
- **Root cause as claimed by the design (from B18's readings; not confirmed, see above):** with the shipped `heap_buffers` allocator every attempt to merge an update into a
  memtable partition clones the update's values into 1 MiB slab regions charged to the pool at clone time; a lost CAS keeps its
  clone. When a flush marks the older write cohort as blocking, `SubAllocator.allocate` charges that cohort's allocations with no
  limit and no wait. On one hot partition the 32 default MutationStage writers each lose ≈ n/2 rounds, so each barrier admits
  hundreds of failed clones past `memtable_heap_space` (B18: a single flushing memtable at 112–382 % of the whole pool).
- **What is new against B18:** B18 showed the overshoot and a T OOM 3/3, but its matched control and intervention also died from a
  timeout/re-send backlog. R16 keeps arm T, runs **T, C and I at 2 GiB with 1.25 MiB batches** (where B18's dial run T died at 7 s
  with zero client timeouts), uses a client that **never sends a new write while its earlier write may still be pending** (after a
  timeout it waits until that write's marker row is readable), and adds a **pool-total reading** (the cleaner's `Used total` log line
  and the pool's own fields read from the heap dump), which B18 lacked. Then a budget search to 15,872 MiB (what `cassandra-env.sh`
  resolves on pc75).

## 1. Candidate

### 1.1 The retry row, quoted

From [`phase2-retry-list.md`](../../phase2-retry-list.md):

> | [B18](cases/memtable_heap_space--hot-partition-cas-retries-past-flush-barrier/memtable_heap_space--hot-partition-cas-retries-past-flush-barrier.md) (from OC-323 cluster) | 2026-11-18 | Hot-partition 5 MiB batches from 36 clients: the flushing memtable counter reached 216–382 % of `memtable_heap_space` (failed CAS clones admitted through the blocking cohort), T OOM 3/3 at 2, 4 and 8 GiB, but the uncontended control and the intervention also ran out of heap (timeout/re-send backlog), so V2 was met only by the fallback control and V4 not at all | Keep arm T; run T, C and I at 2 GiB with 1.25 MiB batches (T still OOMs at 7 s with no client timeouts) and a client that does not re-send while an earlier attempt is pending, ≥ 3 runs each | picked again: R16 (2026-11-20) |

### 1.2 The earlier case and its verdict

[B18](../memtable_heap_space--hot-partition-cas-retries-past-flush-barrier/memtable_heap_space--hot-partition-cas-retries-past-flush-barrier.md)
(2026-11-18, pc75): **retry**, detail `candidate` (V1, V3, V5–V7 met; V2 only via the rate-matched fallback control; V4 not met).
What it measured, and what R16 takes from it:

| B18 reading | Value | Used in R16 |
|---|---|---|
| T, 2 GiB, S = 5 MiB, 36 clients, hot | heap OOM 3/3 at 7–10 s; flushing memtable 35–40 % at switch → **321 %, 382 %** after the barrier; dump regions 3.24–3.35 × C (83–87 %); 13–39 client timeouts | the mechanism; the K and U instruments |
| T at 4 GiB (10 MiB) / 8 GiB (14 MiB) | 3/3 / 3/3 heap OOM (10–34 s), regions 3.2–3.3 × C | budget search starts above 8 GiB |
| **Dial run H2-TR160-1**: T, 2 GiB, **S = 1.25 MiB** (R = 160) | heap OOM at **7 s**, **0 client timeouts**; three flushes with Writing **112 %, 115 %, 125 %** (50–62 MiB of rows each); `High update contention in 1/1`; regions **1,828 MiB = 3.57 × C, 94 %** of the dump | the fixed condition of R16 (1/1 so far) |
| Dial run H2-TR320-1: T, 2 GiB, S = 2.5 MiB | heap OOM at 6 s, 0 timeouts, Writing 174 %, 215 % | 4 GiB dial point |
| C (perthread), 2 GiB, 5 MiB | **heap OOM 3/3** at 34–43 s, regions 2.9–3.2 × C while every flushing memtable ≤ 59 %; **282–360 client timeouts**, client re-sent after 1 s → 2–3 writers per partition, `BlockedOnAllocation` +135…+196; pool total not measurable | the failure R16 must avoid (gated client) and attribute (pool-total reading) |
| I (`concurrent_writes: 4`), 2 GiB, 5 MiB | 2/3 heap OOM (70–79 s) from the **MutationStage backlog of timed-out mutations** (185–242 decoded 5 MiB mutations, 0.9–1.2 GiB of frames); memtable ≤ 67 % | the intervention is kept, at 1.25 MiB with the gated client so no backlog can build |
| Crm (perthread at T's acked rate 9.4 MiB/s) | survived 3/3, old gen 207 MiB, 0 timeouts | kept only as pre-declared fallback |
| I2 (exclusive lock that blocking writers skip) | 3/3 OOM at 8–9 s, Writing 338–355 % | not repeated: the per-`Updater` monitor is not what carries the overshoot |
| K instrument | `AllMemtablesOnHeapDataSize` sums only the **current** memtable in 5.0.9 (`TableMetrics.java:876-883`); JMX sampler stalled within 3–11 s in T | K from the per-memtable log lines plus two new pool-total readings (§2.6) |

B18 §4 "What a better design should change": (a) a client that does not re-send after a timeout while its earlier request may
still be applied; (b) an intervention that bounds the contending cohort without a backlog — `concurrent_writes: 4` at small S;
(c) a pool-total reading; (d) S = 1.25 MiB for T, C, I, ≥ 3 each; (e) the budget search above 8 GiB (15,872 MiB, S = 14 MiB).
**R16 implements (a), (b), (c), (d) and (e).** Not adopted: a diagnostic lock that blocking writers cannot skip (re-opens the
CASSANDRA-15367 deadlock; `concurrent_writes: 4` is a shipped setting and needs no patch).

### 1.3 Phase-1 constraints and stage-4 measurements

Unchanged from B18 §1.3 (the leads: `EXCESS_WASTE_BYTES` 10 MiB lock on a per-call `Updater` — 94 % of "locked" attempts still
failed in stage 4; the WE cells' `Writing` memtable at 478 % and 678 % of a 512 MiB pool; `MAX_CLONED_SIZE` unit probe: 16 MiB passed
the limit with no parking under a blocking group). Those stage-4 cells used `concurrent_writes: 128` and raised timeouts; R16 runs at
defaults.

### 1.4 JIRA prior art (re-checked 2026-11-20; read only, nothing posted)

Local survey `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv` (604 rows; grep `memtable`, `contention`,
`AtomicBTree`, `spin loop`, `OpOrder`, `blocking`, `7546`, `15367`, `21019`) and JIRA REST (reachable; JQL `text ~ "markBlocking"`,
`text ~ "AtomicBTreePartition" AND text ~ "contention"`, `text ~ "memtable" AND "exceed" AND "limit"` since 2024, `"hot partition" AND
memtable` since 2023, `"pessimistic" AND "Updater"`, `"isBlocking" AND "allocate"`):

| Issue | Status | Relevance |
|---|---|---|
| CASSANDRA-7546 "AtomicSortedColumns.addAllWithSizeDelta has a spin loop that allocates memory" | Fixed 2.1.1 | origin of the waste tracker and the pessimistic lock; in 5.0.9 the lock is `synchronized (this)` on the per-call `Updater` (`AtomicBTreePartition.java:120-123`), excluding no one (B18 §1.4) |
| CASSANDRA-15367 "Memtable memory allocations may deadlock" | Fixed 3.0.21/3.11.7/4.0 | the blocking-cohort exemption is **by design** ("limits may be lifted for operations in the first cohort") |
| CASSANDRA-21019 "Memtable allocator: separate memory usage tracking and limit checking" | Fixed 4.0.22/4.1.13/**5.0.10** | after the pin; checks the limit before a mutation starts and lets it complete (description: allocation-level limit checks hold "a partial copy of the mutation … and a likely expanded version … keeping hold of more total memory"). Whether it bounds a blocking writer's CAS retries is not checked; a 5.0.10 re-test is a follow-up, not part of R16 |
| CASSANDRA-18125 "Improve memtable allocator accounting when updating AtomicBTreePartition" | Fixed 4.0.9/4.1.1/5.0 | already in 5.0.9; accounting assertion in `released`, not this mechanism |
| CASSANDRA-12796 "Heap exhaustion when rebuilding secondary index over a table with wide partitions" | Fixed 2.2.9/3.0.11/3.10 | the nearest shape (one long `OpOrder` group past a barrier lets memtable memory exceed the limit), on the 2i rebuild path; fixed there, not the write path |
| CASSANDRA-20226 "Reduce contention in MemtableAllocator.allocate"; CASSANDRA-17163 | Fixed 6.0; Duplicate | allocator-counter CAS performance, not this mechanism |
| CASSANDRA-19564 "MemtablePostFlush deadlock" | Fixed 4.1.11/5.0.7 | in 5.0.9; flush deadlock, not memory |
| CASSANDRA-10937 (hot-partition write OOM) | Won't Fix | judged overload; no mechanism named |

No new issue since B18's search (2026-11-18). **Verdict: `new`** for the claimed OOM (failed-CAS clones of one hot partition
multiplied inside the blocking cohort's exemption); the exemption alone is `by design` (15367). Not `known-fixed` at 5.0.9.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

Unchanged from B18 §2.1 (source re-checked 2026-11-20 at the cited lines):

- **Write path.** CQL write, CL ONE, one node: applied on `MutationStage` (threads = `concurrent_writes`, default 32,
  `conf/cassandra.yaml:723`). A local write that expires before it starts is re-submitted as a hint runnable that applies it later
  (`StorageProxy.java:2634-2656`); so a timed-out write is still applied unless the node dies.
- **Clone per attempt.** `AtomicBTreePartition.addAll` makes a **new `Updater` per call** (`AtomicBTreePartition.java:120-122`); each
  attempt builds a merged partition whose values are cloned by the memtable cloner into `SlabAllocator` 1 MiB on-heap regions
  (`SlabAllocator.java:51-52`, `heap_buffers` is the shipped `memtable_allocation_type`, `conf/cassandra.yaml:825`), charged to the pool at
  clone time; a failed CAS keeps the clone (charged and retained until the memtable is discarded).
- **The lock that excludes no one.** After `EXCESS_WASTE_BYTES` (10 MiB) of waste, attempts run in `synchronized (this)` on the
  per-call `Updater` (B18 §2.1); B18's I2 showed that even an exclusive lock does not stop the overshoot when blocking writers skip it.
- **The exemption.** `SubAllocator.allocate` (`MemtableAllocator.java:169-197`): on a failed `tryAllocate`, if the writer's
  `OpOrder.Group.isBlocking()`, `allocated(size)` charges without limit or wait (`:180-184`). `Flush.run` calls
  `writeBarrier.markBlocking()` then `await()` (`ColumnFamilyStore.java:1236-1239`, "permitting them to exceed our memory limit").
- **Multiplication.** With n writers on one partition each successful CAS invalidates every concurrent attempt: overshoot per barrier
  ≈ η · n(n−1)/2 · S. B18 measured η = 0.61, 0.73 at S = 5 MiB; H2-TR160-1 at S = 1.25 MiB: (572 MiB − 50 MiB of rows)/1.25 MiB ≈ 418
  failed clones → η ≈ 0.84 at n = 32.
- **Direction label:** **bypass (enforcement failure)** — U > C and K > C in the memtable domain; the bytes are counted (B18: K/U
  0.66–1.15) and the check admits them. Interpretation: intentional exception (15367) multiplied by write contention on one partition,
  with a suspected defect in the per-`Updater` lock. **Mixed** if the OOM also needs D2/D3 beyond their contracts. Technique notes:
  [`bypass-playbook.md`](../../../bypass-playbook.md) (enforcement-failure bypass) with the multiplicity step of
  [`combo-playbook.md`](../../../combo-playbook.md).
- **Why the arms are now separable.** B18's C and I died from bytes that the **client's re-send after a 2 s timeout** created
  (D3 backlog; second and third writers on a `perthread` partition). R16's client keeps **at most one write per thread outstanding
  at any time, counting writes the server has timed out but may still apply** (§2.5 gate). Then D2 + D3 ≤ 36 × S = 45 MiB in every
  arm, a `perthread` partition never has two writers (no CAS failure at all in C), and `concurrent_writes: 4` cannot build a backlog
  beyond 36 queued mutations (I). The only difference between T and C is that 32 writers share one partition.
- **Overlap with C6** (verified, slab regions × written tables): same holder type and scanner; different failure (C6 uncounted
  regions across many tables; here one table, counted, admitted past the limit). Unchanged from B18 §2.1.

### 2.2 Protection map (2 GiB heap, S = 1.25 MiB)

| Domain | Allocation, owner, release | Local contract (C) | Scope / multiplicity | Aggregate coverage | Lifetime |
|---|---|---|---|---|---|
| **D1 memtable regions + charged overhead (claimed holder)** | `SlabAllocator` 1 MiB `byte[]` regions of the memtables of `ks.t` (and system tables) plus object overhead charged after merge; released when the flushed memtable is discarded | `memtable_heap_space` = heap/4 = **512 MiB**, hard wait at the limit (`hasRoom`), flush at `memtable_cleanup_threshold` 1/(1+2) = 0.33; documented soft overshoot: the blocking cohort's own single attempts (≤ 32 × 1.25 = 40 MiB), the 10 MiB waste allowance before locking, region-tail waste ≤ 12.5 % (64 MiB): **C_contract ≈ 512 + 40 + 10 + 64 ≈ 626 MiB** | all memtables share one pool; one table, one partition (T, I) or 36 partitions (C) | the pool is the aggregate control; the exemption is its only exit | until flush + discard (seconds) |
| D1' per-attempt garbage | rows/cells/B-tree arrays of failed merges | none (garbage) | × attempts | GC only | young gen |
| D2 decoded requests in flight | v4 frames decoded to `Mutation`s, held until the response | `native_transport_max_request_data_in_flight` heap/10 = 204.8 MiB, per IP heap/40 = 51.2 MiB (on-wire bytes); 36 × 1.25 = **45 MiB**, 9 × 1.25 = 11.25 MiB per IP | per IP | global reserve | until the response |
| D3 timed-out writes still queued/running | mutations answered with a timeout but still in MutationStage (or re-submitted as hint runnables) | none (uncounted after the response) — **bounded by the client gate**: a thread with a timed-out write sends nothing until that write is applied, so D2 + D3 ≤ 36 × S = 45 MiB | per client thread | — | until applied |
| D4 flush / compaction / commit log | flush writer and compaction buffers (heap), commit-log segments (mmap) | defaults | 2 flush writers, default compactors | — | transient |
| D5 baseline | schema, metrics, caches (key cache ≤ 100 MiB, unused by writes), JMX sampler | — | — | — | standing |
| Direct (not the budget) | Netty frames, `BufferPool` | `MaxDirectMemorySize` as `cassandra-env.sh` resolves on pc75 (B18 read back **15,872 MiB**) | — | — | recorded (RssAnon) |

### 2.3 Configuration and budget audit

- **Build:** `/mydata/s4/cassandra-base` on pc75 (Cassandra 5.0.9, B18 recorded jar sha256
  `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`), copied with `cp -a` to `/mydata/s4/r16/cassandra`; never run
  `ant` there; record the jar sha256 (a different hash is recorded, not a failure, but say so in §3). OS Ubuntu 22.04, kernel 5.15,
  cgroup v2, swap 8 GiB present (node scope `MemorySwapMax=0`), JDK 11.0.33, GC = shipped `jvm11-server.options` (G1,
  `G1HeapRegionSize=16m`, `G1NewSizePercent=50`, `MaxGCPauseMillis=300`, `HeapDumpOnOutOfMemoryError`; `cassandra-env.sh`
  `OnOutOfMemoryError=kill -9 %p`).
- **Capacity constraints (V6), all shipped defaults, read back from `system_views.settings` each lifetime:**
  `memtable_allocation_type: heap_buffers`; `memtable_heap_space` / `memtable_offheap_space` unset → heap/4; `memtable_cleanup_threshold`
  unset → 0.33; `memtable_flush_writers` → 2; `concurrent_writes: 32`; `concurrent_counter_writes: 32`;
  `native_transport_max_request_data_in_flight` / `_per_ip` unset → heap/10, heap/40; `native_transport_max_message_size` → 16 MiB;
  `max_mutation_size` → 16 MiB; `commitlog_segment_size: 32MiB`; `commitlog_total_space` → 8,192 MiB; `write_request_timeout: 2000ms`;
  `native_transport_timeout` 12 s; `native_transport_throw_on_overload` false; `batch_size_fail_threshold` 50 KiB (not applied to
  single-partition batches); `hinted_handoff_enabled: true`; `EXCESS_WASTE_BYTES` 10 MiB (hard-coded). Labels: all **default**.
- **Environment diff only** (classified *environment*): `cluster_name: r16`, `listen_address`/`rpc_address: 127.0.0.1`, seeds
  `127.0.0.1:7000`, data/commitlog/hints/saved_caches/cdc_raw directories under `/mydata/s4/r16/run/`. Ports 9042/7000/7199 (check
  free). Client source addresses 127.0.0.11–14.
- **Arm-only deviations:** I: `concurrent_writes: 4`; optional dose arms D8/D16: `concurrent_writes: 8` / `16` (all shipped
  settings, changed only in intervention arms, as V6 allows). Instrument only: `nodetool setlogginglevel
  org.apache.cassandra.db.memtable.SkipListMemtable TRACE` (one line per flush). No Byteman, no patch, no raised timeout, no fault →
  conditions label can be `deployment`.
- **Client behaviour (workload, not a setting):** the gate (§2.5) is a well-behaved client — it never has two writes of its own
  outstanding. It reduces load (conservative for C and I) and does not act in T unless T times out.
- **Budget (V7):** heap `MAX_HEAP_SIZE=2G` (the ideal; standing rule ≥ 512 MiB, no review needed) for the fixed condition; budget
  search at 4G and **15,872 MiB** (= what `cassandra-env.sh` resolves on pc75: min(½ RAM, 15,872 MiB); the largest heap it resolves on
  any node). Direct limit: as resolved (record; B18: 15,872 MiB). Container: a `systemd-run --user --scope -p MemoryMax=<heap + 6 GiB>
  -p MemorySwapMax=0` scope as isolation only; never the budget (`memory.events` `oom_kill` must stay 0).
- **Resolved values to record:** pool limit (512 / 1,024 / 3,968 MiB at 2 / 4 / 15.5 GiB), cleanup threshold, in-flight limits
  (204.8 / 51.2 MiB at 2 GiB; 1,587.2 / 396.8 MiB at 15,872 MiB), `MaxDirectMemorySize`, key-cache cap.

### 2.4 Ceiling arithmetic (2 GiB, S = 1.25 MiB)

| Item | Bound | Source |
|---|---|---|
| D5 baseline | L0 ≈ 65 MiB (B18, every arm) + sampler; take 100 MiB | B18 §3.1 |
| D2 + D3 (gated) | ≤ 36 × 1.25 MiB = 45 MiB on wire × ≈ 2 decoded ≈ 90 MiB | §2.2 |
| D1 contract | C_contract ≈ 626 MiB | §2.2 |
| D4 transient | ≈ 50 MiB | estimate |
| **Σ contract + baseline** | **≈ 0.85 GiB < 2 GiB** | |

Convergence of the contract capacities cannot exhaust 2 GiB (margin ≈ 1.15 GiB). An OOM requires U(D1) past its contract by
≳ 1.1 GiB, which is the claim. **Predicted D1 (T):** per barrier the flushing memtable goes from the switch level (≈ 0.35 × C = 180 MiB)
to ≈ 0.35 C + η · 496 · 1.25 MiB = 180 + 370–520 MiB ≈ **550–700 MiB (107–137 % of C)** (H2-TR160-1: 112–125 %); the pool total
stays above the limit across consecutive barriers (the next memtable's writers are themselves exempted at the next barrier), and the
heap fills in **≈ 3–5 barriers**: dump regions ≈ 1.3–1.9 GiB (2.5–3.7 × C; H2-TR160-1 1.83 GiB). **C (perthread, gated):** no failed
CAS; per barrier ≤ 32 × 1.25 = 40 MiB past the limit; pool total ≤ C + 45 MiB; live heap ≤ 0.85 GiB → survives. **I (4 writers):**
≤ (6 + 4) × 1.25 = 12.5 MiB past the switch per barrier → survives.

**Budget search arithmetic.** At 15,872 MiB (C = 3,968 MiB) with S = 14 MiB (the B18 8 GiB size; 36 × 14 = 504 MiB ≤ 1,587 MiB global,
9 × 14 = 126 MiB ≤ 397 MiB per IP; < 16 MiB message/mutation limits): per barrier 0.35 C + η · 496 · 14 MiB = 1.4 + 4.1–5.8 GiB =
**5.5–7.2 GiB (1.4–1.8 × C)**; B18 saw dumps at 3.2–3.3 × C at every heap from 2 to 8 GiB (the cascade over barriers), which at
15.5 GiB is 12.7–13.1 GiB: an OOM is **likely** but not certain (P6). At 4 GiB with S = 1.25 MiB: per barrier 0.35 × 1,024 + 370–520 =
730–880 MiB (71–86 % of C, under the limit): **survival predicted**; with S = 2.5 MiB: 360 + 740–1,040 = 1.1–1.4 GiB (107–137 %, as T at
2 GiB/1.25 MiB): OOM predicted.

### 2.5 Workload and environment (pc75 only)

**Node check (stage 1, read-only, 2026-11-20 10:32 EST):** pc75 = `node3.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`, 40
cores, 125 GiB RAM (124 GiB available), `/mydata` 714 GiB free (419 MiB used), no Java process running, JDK 11.0.33,
`/mydata/s4/cassandra-base/build/apache-cassandra-5.0.9-SNAPSHOT.jar` present. **B18's run folder `/mydata/s4/b18-w4` is gone**
(only `cassandra-base` under `/mydata/s4`): start from the repo copy of B18's harness.

**Directories (pc75, local `/mydata` only):** `/mydata/s4/r16/cassandra` (copy of the base), `/mydata/s4/r16/harness/` (synced from
this folder's `harness/`), `/mydata/s4/r16/cls/` (client classes), `/mydata/s4/r16/run/` (one lifetime; recreated per lifetime),
`/mydata/s4/r16/logs/<label>/` (kept). Do not touch `/mydata/s4/cassandra-base` or other cases' folders.

**Co-tenancy.** Before every lifetime: `ps -eo pid,cmd | grep '[C]assandraDaemon'` and `MemAvailable`. Proceed only with no other
Cassandra on pc75 (one measured experiment per victim node), ≥ 40 GiB available and free ports; else wait (bounded) and record.

**Harness** (`harness/` in this folder; base: B18's [`harness/`](../memtable_heap_space--hot-partition-cas-retries-past-flush-barrier/harness/)
— `run.py`, `plan.sh`, `after.sh`, `client.py`, `Jmx.java`, `hprof_scan.py`, `HoldRegions.java`, `instrument-check.sh`,
`analyze.py`, `excerpts.sh`, `logback-client.xml`; copy, rename `b18` → `r16` in unit/cluster names and paths, keep everything else):

- **`HotGen.java` — B18's client plus the gate.** Unchanged: driver 3.12.1 shaded from `build/lib/jars`, protocol V4, CL ONE,
  `INSERT INTO ks.t (pk, ck, v)` prepared; one request = an unlogged single-partition batch of R rows, value 8,192 random bytes (pool
  of 64), `ck` from a global counter; `hot` (pk = 1) or `perthread` (pk = thread number); one `Cluster` per source IP 127.0.0.(11+i)
  bound through `NettyOptions.afterBootstrapInitialized`; one connection per `Cluster`; read timeout 30 s; synchronous, one request in
  flight per thread; 4 IPs × 9 threads = 36. **Changed — the gate:** after a `WriteTimeoutException` or a client-side
  `OperationTimedOutException` (or any error other than `OverloadedException`, `NoHostAvailableException`, `TransportException`), the
  thread does **not** send another write; it polls the prepared `SELECT ck FROM ks.t WHERE pk = ? AND ck = ?` (CL ONE) for the **last
  row of its timed-out batch** every 500 ms until the row is returned (the batch is one `PartitionUpdate`, applied atomically, so the
  last row present ⇒ the whole write is applied and no longer pending). Poll errors are counted and polling continues. If the row has
  not appeared after **120 s**, the thread **retires** (sends nothing more; counted). `OverloadedException` (request refused, nothing
  pending): sleep 1 s. `NoHostAvailableException`/`TransportException` (node gone): sleep 1 s (the stall detector ends the run).
  Stats line every second: `ms,req_ok,rows_ok,err_wto,err_ovl,err_tra,err_nha,err_oth,connected,` **`gated_now,gate_waits,gate_wait_ms_total,gate_polls,gate_poll_err,retired`**.
  Optional rate (`rateMiBps`) as B18 (Crm fallback only). Args as B18. A `--gate-selftest` flag treats every 10th success as if it
  had timed out (the gate must then find the row on the first poll) — Step A only, never in a reading.
- **Sizes:** **R = 160 (S = 1.25 MiB)** for T, C, I at 2 GiB; budget search R = 160 and 320 at 4 GiB; R = 1,792 (14 MiB) at 15,872 MiB.
- **`Sampler`** — B18's `Jmx.java` `poll` at 500 ms (heap, G1 old-gen usage and collection usage, GC counts/times, `MemtableOnHeapDataSize`
  and `AllMemtablesOnHeapDataSize` for `ks.t` (both the **current** memtable only, A2 of B18), `MemtablePool` `BlockedOnAllocation`
  count and `PendingFlushTasks`, MutationStage active/pending/completed, `DroppedMessage` MUTATION_REQ count, `ClientRequest Write
  Timeouts`), fixed ObjectNames. A shell loop samples `RssAnon` and the scope's `memory.current` every 1 s. The sampler stalling in T
  (as in B18) is expected; K does not rest on it.
- **`hprof_scan.py` — B18's scanner extended with instance-field decoding** (the pool-total reading at the dump):
  parse `CLASS DUMP` (0x20) records (super-class id, instance field descriptors) and decode, for instances (0x21) of these classes,
  their declared and inherited fields: `org.apache.cassandra.utils.memory.SlabPool` (its `onHeap`/`offHeap` object ids, from
  `MemtablePool`), `org.apache.cassandra.utils.memory.MemtablePool$SubPool` (`limit`, `allocated`, `reclaiming`, `nextClean`),
  `org.apache.cassandra.utils.memory.SlabAllocator` (its `regionCount` → the `AtomicInteger` `value`; inherited `onHeap` from
  `MemtableAllocator`), `org.apache.cassandra.utils.memory.MemtableAllocator$SubAllocator` (`owns`, `reclaiming`, `state` → the
  `LifeCycle` enum constant name via its `name` field). Output `pool`: `{limit, allocated, reclaiming}` of the SlabPool's **on-heap**
  SubPool; `allocators`: per `SlabAllocator` `{regionCount, owns_onheap, reclaiming, state}`; plus B18's `byte[1048576]` count/bytes,
  top-20 classes, named classes, OOM thread stacks. Run with `python3 -I`. **Known-answer check (Step A, extended):** B18's
  `HoldRegions` (40 regions, 40 near-regions, 1,000 markers) plus a `FieldProbe` class with an inherited `long` and `int` field, an
  object reference and an `AtomicInteger`, set to known values (e.g. `0x0123456789ABCDEFL`, 4242, a referenced object, 77) — every count
  and value exact, else fix the scanner (not a reading).
- **`run.py life <label> <arm> <heap> [R] [rate]`** — B18's lifetime (fresh `run/`, conf, start in the scope, wait ≤ 300 s for CQL,
  read-backs with `EXPECTED:` lines, `s0`, schema, workload, endpoint handling, copy logs, stop by PID, `rm -rf run/`). Arms: `T`
  (hot), `C` (perthread), `I` (hot, `concurrent_writes: 4`), `Crm` (perthread, rate), optional `D8`/`D16` (hot, `concurrent_writes: 8`/`16`).
  Heaps `2G`, `4G`, `15872M`. Launch from `plan.sh` with `( setsid nohup bash harness/plan.sh harness/plan-<x>.txt < /dev/null >
  logs/plan-<x>.out 2>&1 & )`; poll with bounded waits; never edit a running script; `plan.sh` refuses a new lifetime after 16:50
  America/New_York.
- **`excerpts.sh`/`analyze.py`** — as B18, plus: grep `Flushing largest` (the cleaner's pool-total line, `system.log`/`debug.log`), the
  new client columns, and the scanner's `pool`/`allocators`.

**Step A — tree and checks (not readings).** Copy the tree; jar sha256; build `HotGen`, `Sampler`; scanner known-answer check;
**source-binding shakedown** (20 s, 2 GiB, `perthread` R = 64: `ss -tn state established '( dport = :9042 )'` shows 127.0.0.11–14;
B18's pre-declared LAN fallback stays available); **gate self-test** (same shakedown with `--gate-selftest`: ≥ 20 gate waits, each
ended by the first or second poll, 0 retired, `gated_now` back to 0).

**Lifetime (labels `<heap>-<arm>-<n>`, e.g. `H2-T-1`, `H16-T-1`):**
1. `rm -rf /mydata/s4/r16/run`; conf; start under `systemd-run --user --scope --unit=r16-<label>-<epoch> -p MemoryMax=<heap+6G>
   -p MemorySwapMax=0` with `MAX_HEAP_SIZE=<heap>`, `CASSANDRA_HEAPDUMP_DIR=run/dump`; wait for `Starting listening for CQL clients`.
2. Read back: `system_views.settings` (the §2.3 list), JVM command line (`-Xmx`, `-Xms`, `MaxDirectMemorySize`, G1 flags,
   `HeapDumpOnOutOfMemoryError`, `HeapDumpPath`, `OnOutOfMemoryError`), scope `memory.max`, `memory.swap.max`.
3. `CREATE KEYSPACE ks … SimpleStrategy rf 1`; `CREATE TABLE ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))` (shipped options);
   `nodetool setlogginglevel org.apache.cassandra.db.memtable.SkipListMemtable TRACE`.
4. `s0`: sampler + RSS loop; 15 s; two `jcmd <pid> GC.class_histogram` (**L0** = the second total); 10 s.
5. Workload (the only differences between arms are `mode` and the arm's `concurrent_writes`): T, I, D8, D16: `HotGen 4 9 R hot W`;
   C: `HotGen 4 9 R perthread W`. W = 240 s (T ends at its OOM).
6. **First-trigger check** at workload + 20 s (or at the OOM if earlier; a failure makes the lifetime invalid): ≥ 5 requests acknowledged;
   four client IPs connected; MutationStage `ActiveTasks` ≥ 24 in at least one sample for T and C (≥ 3 for I; if the sampler stalled
   before its first workload sample in T, the dump's MutationStage writer stacks ≥ 24 count instead).
7. **On OOM:** wait ≤ 300 s (≤ 600 s at 15,872 MiB) for `Heap dump file created` and the JVM exit; run `hprof_scan.py`; keep its JSON;
   delete the `.hprof`. **Surviving lifetime:** at W stop the client; 10 s; two `GC.class_histogram` (**U_end**); in **every** surviving
   C and I lifetime at 2 GiB also `jcmd <pid> GC.heap_dump -all=false` (live objects) and the scan (pool and allocator fields at the
   end); stop the node by PID; `nodetool flush` is not run.
8. Copy `system.log`, `debug.log`, `gc.log*`, `stdout.txt`, `sampler.csv`, `rss.csv`, `hotgen.csv`, histograms, scans, `memory.events`
   to `/mydata/s4/r16/logs/<label>/`; check no process left; `rm -rf /mydata/s4/r16/run`.

### 2.6 Instruments and readings (U measured independently of K)

| Reading | Source | When | Meaning |
|---|---|---|---|
| **K per memtable** | `Enqueuing flush of ks.t … Usage: X (P%)` (at switch) and `Writing Memtable-t@…(…, X (P%) on-heap)` (after the barrier) | per flush | the memtable's own counter (`owns`) |
| **K pool total (new)** | `Flushing largest … Used total: a/b, live: c/d, flushing: e/f, this: g/h` (INFO, `AbstractAllocatorMemtable.java:289-295`): `a` = pool on-heap `used/limit` | per cleaner-triggered flush | the pool counter across live + flushing memtables (B18 lacked it) |
| **K pool at the dump (new)** | scanner `pool.allocated`, `pool.reclaiming`, `pool.limit`; per allocator `owns`, `regionCount`, `state` | OOM dumps; end dumps of C, I | pool counter at the endpoint, per-memtable split, how many memtables are live/flushing/discarded-but-retained |
| contention | `High update contention in a/b partitions` TRACE | per flush | waste tracker flipped |
| **U(D1)** | dump scan: count × 1,048,592 B of `byte[1048576]` | OOM and end dumps | slab regions, independent of K |
| holder ranking | dump scan top classes | as above | regions vs `Mutation`/`PartitionUpdate`/`BufferCell`/other `[B` (D2/D3) |
| U trajectory | `gc.log`: heap after each GC; old-gen occupancy | continuous | live growth per barrier |
| U_end | `GC.class_histogram` total and `[B` | surviving lifetimes | live heap after the workload |
| control activity | sampler: `BlockedOnAllocation`, `PendingFlushTasks`, MutationStage active/pending/completed, dropped MUTATION_REQ, write timeouts | 500 ms | waits, cohort size, backlog |
| **client / gate** | `hotgen.csv`: ok requests and rows per second, errors by class, `gated_now`, gate waits/polls, retired | 1 s | load reached; **D3 bound held** (`gated_now` ≤ 36 and every timed-out write confirmed applied before that thread's next write) |
| first error | `stdout.txt` (`java.lang.OutOfMemoryError: Java heap space`, `Dumping heap`, `Heap dump file created`, `kill -9`), `system.log`, exit status, `memory.events`, dump thread stacks | T | V5 |
| process | `RssAnon`, scope `memory.current`, `memory.events` | 1 s / end | the scope never binds |

The overshoot window is 0.1–3 s (B18/H2-TR160-1: `Enqueuing` → `Writing` 0.15–0.3 s at 1.25 MiB); the per-flush log lines and the
dump fields resolve it; the 500 ms sampler covers C and I. Intrusive readings (histograms, dumps) only at `s0`, at the end of surviving
lifetimes and at the OOM.

### 2.7 Predicted response, outcome rows and stopping budget

**Predictions (frozen).** C = `memtable_heap_space` (512 MiB at 2 GiB). "T's pre-OOM acked bytes" = rows acknowledged × 8 KiB before the
OOM in that T lifetime (H2-TR160-1: 198 MiB).

- **P1 (T, 2 GiB, S = 1.25 MiB):** each `H2-T-n` ends in `java.lang.OutOfMemoryError: Java heap space` with a heap dump and the shipped
  `kill -9`, **3/3**, within 120 s of the workload start (expected 5–20 s).
- **P2 (T, K > C):** in each run at least one flushing memtable's own counter > 100 % of C (a `Writing` line, or a non-current allocator's
  `owns` > C in the dump); in ≥ 2 of 3 runs the pool total > 1.3 × C (a `Used total` ≥ 1.30 or dump `pool.allocated` ≥ 666 MiB); ≥ 1
  `High update contention in 1/1 partitions` line per run that reached a `Writing` line.
- **P3 (T, U and counting):** dump `byte[1048576]` ≥ **2.5 × C (1,280 MiB)** and ≥ 60 % of the dumped shallow bytes; regions ≥ 5 × the
  bytes of `Mutation` + `PartitionUpdate` + other `[B`; dump `pool.allocated` ≥ 0.6 × U(D1) (the bytes are counted).
- **P4 (T, no re-send needed):** client write timeouts ≤ 10 per run before the OOM and `gated_now` ≤ 10 at every second (H2-TR160-1: 0).
- **P5 (C, perthread, gated, 2 GiB):** **3/3 survive 240 s**; every `Writing` line ≤ 70 % of C; no `High update contention` line for
  `ks.t`; every `Used total` ≤ 1.10; end-dump `pool.allocated` ≤ C + 45 MiB; old-gen occupancy after each GC from workload + 30 s on
  ≤ 0.80 × heap (1,638 MiB); acked bytes in 240 s ≥ 5 × the median T pre-OOM acked bytes (the control is not starved); `retired` = 0.
- **P6 (I, `concurrent_writes: 4`, hot, gated, 2 GiB):** **3/3 survive 240 s**; every `Writing` line ≤ 70 % of C; every `Used total`
  ≤ 1.10; MutationStage pending ≤ 36 in every sample; old-gen after GC ≤ 0.80 × heap; acked requests ≥ 1/s on average **and** acked bytes ≥
  2 × the median T pre-OOM acked bytes (the intervention keeps doing useful work past the load at which T died); report its throughput
  against T's pre-OOM throughput.
- **P7 (budget search, T only):** 4 GiB, S = 1.25 MiB: survives 240 s (predicted; 1 lifetime); 4 GiB, S = 2.5 MiB: heap OOM (1 lifetime);
  **15,872 MiB, S = 14 MiB: heap OOM 3/3** (likely, §2.4), which would make the largest failing budget the largest heap `cassandra-env.sh`
  resolves on any node. If H16-T-1 survives, run one 8,192 MiB S = 14 MiB lifetime to re-confirm B18's largest failing budget with the
  gated client, and report the boundary as between 8,192 and 15,872 MiB.
- **P8 (optional dose, T at 2 GiB, S = 1.25 MiB):** D16 (n(n−1)/2 = 120): Writing ≥ 70 % and OOM or survival either way (stated, not a
  verdict condition); D8 (28): survives like I. Reported as a dose-response of multiplicity, not used for V4.
- **Validity (every lifetime):** read-backs equal the arm and §2.3; heap as planned; first-trigger check passes; scope `oom_kill` 0; no
  `ERROR` in `system.log` before the endpoint other than the OOM's and write-timeout lines; client `retired` = 0 (a retired thread means
  a write was never applied in 120 s: the lifetime is invalid for C/I, recorded for T).

**Outcome rows:**

| Readings | Verdict |
|---|---|
| P1 holds (3/3 T OOM), P5 holds (3/3 C survive), P6 holds (3/3 I survive), and every T dump shows U(D1) > C_contract with `pool.allocated` > C (the direction of P2/P3; their numeric thresholds are reported, a miss is stated but does not change the row) | **true positive**: `verified-OOM · deployment`, bypass (enforcement failure, D1); **mixed** if the dumps need D2/D3 (regions < heap − L0 − 300 MiB) |
| T 3/3 OOM; C or I reaches OOM **with the gate holding** and its dump shows `pool.allocated` > 1.3 × C with ≥ 1 non-current allocator `owns` > C | **retry**: the exemption overshoots without hot-partition contention too; the attribution to CAS retries fails; record η and the C-arm shape (OC-257 family) and name the next design |
| T 3/3 OOM; C or I reaches OOM with `pool.allocated` ≤ 1.1 × C while regions > 2 × C | **retry**: an **uncounted** region holder (accounting omission, C6-like) is active in one table; record it as a separate lead (new retry row) |
| T 3/3 OOM; C or I reaches OOM dominated by `Mutation`/frames (D2/D3) **although the gate held** | **retry**: some other backlog; record what held it |
| Pre-declared fallback used (C-1 OOM → Crm) and Crm 3/3 survive | V2 only through the fallback, as B18: **retry** unless C's dump attribution above shows C's OOM is the same exemption (then still **retry**, see row 2) |
| T survives (any run) with K > C_contract (Writing > 122 % or pool > 1.22 × C) but live heap < 0.8 × heap | **retry** (`verified-gap`, overshoot); name η and the S·n needed |
| T meets the service-loss criterion (≥ 90 % of wall time in stop-the-world GC over ≥ 60 s) with K > C_contract | **retry** (`verified-gap · service-loss`) |
| T survives with every barrier ≤ C_contract and the load reached (validity) | **retry** (B18's T reached OOM 3/3 at S = 5, 10, 14 MiB, so a survival at 1.25 MiB is an S boundary, not a false positive); name the S needed |
| Validity fails | invalid lifetime; one rerun; else retry |

**Pre-declared fallback (unchanged from B18 §2.8):** if `H2-C-1` reaches OOM, run `Crm` = `perthread` at T's acked rate (mean MiB/s of
`H2-T-1` over its pre-OOM window), 3 runs, after the nine planned 2 GiB lifetimes; report both. (`C` still runs 3 times.)

**Stopping budget (finite):** per lifetime CQL within 300 s (else invalid); workload W = 240 s; after a client stall (60 s with no
success) wait ≤ 120 s for an OOM, then classify from `gc.log`, one histogram if `jcmd` answers within 60 s, kill the JVM by PID. One
rerun per invalid lifetime. No escalation after an OOM: the 4 GiB and 15,872 MiB steps are the planned budget search. **No new lifetime
starts after 16:50 America/New_York on 2026-11-20; every process stopped by 17:05.**

### 2.8 Controls and intervention

- **Matched control (V2), C, 3 runs:** the same client (4 IPs × 9 threads, one request in flight per thread, the same gate), the same
  R = 160, value size, heap, build and settings; `mode = perthread`: each thread writes its own partition, and with the gate a partition
  never has two concurrent writers, so no CAS fails and a barrier admits at most one attempt per writer (≤ 40 MiB, the OC-257 shape).
  Only the sharing of one partition differs. Margin: old-gen after GC ≤ 0.80 × heap. C ingests more data per second than T (no wasted
  attempts), which only adds flush and compaction work to its side.
- **Causal intervention (V4), I, 3 runs:** `concurrent_writes: 4` (a shipped setting; bounds the contending cohort to n = 4: ≤ 6 failed
  clones per round instead of ≤ 496), same hot workload, same in-flight bytes; the gate keeps the queue at ≤ 36 requests. Throughput is
  recorded so an intervention that stops work is not taken for protection (P6's acked-bytes floor).
- **Optional dose arms D8, D16** (P8): T's workload with `concurrent_writes: 8` / `16`, 1 lifetime each, if time allows.
- **Not used (and why):** `unslabbed_heap_buffers` (changes holder and counter at once); a lock blocking writers cannot skip (re-opens
  CASSANDRA-15367's deadlock; B18's I2 showed an exclusive lock that they skip changes nothing); raised timeouts or Byteman (would make
  the result diagnostic); re-running T at 5 MiB (done 3/3 in B18).

### 2.9 Time plan (America/New_York, 2026-11-20; stage 2 starts ≈ 12:00; hard end 17:30)

Lifetime cost from B18 (pc75): start + read-backs + `s0` ≈ 1.5 min; 2 GiB OOM + dump + scan ≈ 1.5 min; W = 240 s + end histograms +
2 GiB live dump + scan ≈ 6 min. So T ≈ 3.5 min, C/I ≈ 7.5 min at 2 GiB; 15,872 MiB T ≈ 15 min (dump ≈ 16 GB written and scanned).

| Window | Work | Est. |
|---|---|---|
| 12:00–12:45 | Step A: copy tree; copy B18 harness, add the gate, extend the scanner; known-answer check; source-binding shakedown; gate self-test | 45 min |
| 12:45–13:50 | nine 2 GiB lifetimes in the order T-1, C-1, I-1, T-2, C-2, I-2, T-3, C-3, I-3 (3 × 3.5 + 6 × 7.5) | 56 min |
| 13:50–14:15 | Crm × 3 only if C-1 reached OOM (pre-declared); else reruns of invalid lifetimes | ≤ 25 min |
| 14:15–15:05 | budget search: `H16-T-1`, `H16-T-2`, `H16-T-3` (15,872 MiB, R = 1,792) — or `H16-T-1` + `H8-T-1` if H16-T-1 survives | 45 min |
| 15:05–15:30 | `H4-T-R160-1`, `H4-T-R320-1` (4 GiB dial points) | 20 min |
| 15:30–16:50 | optional, in order: D16, D8 (2 GiB); `H16-C-1` (perthread, R = 1,792, the control at the largest failing budget); spare | ≤ 80 min |
| 16:50–17:05 | last lifetime ends; stop everything; check no process left | 15 min |
| 17:05–17:30 | `analyze.py`, §3–§4, write-backs (retry-list row, `_INDEX.md`, clue pattern if new), excerpts to `logs/` | 25 min |

If stage 2 starts late, keep the window ends and drop from the bottom of this priority list: (1) the nine 2 GiB lifetimes; (2) Crm if
triggered; (3) `H16-T-1`; (4) `H16-T-2/3`; (5) the 4 GiB dial points; (6) the optional runs.

**Resource fit:** largest JVM 15,872 MiB heap (+ ≈ 2 GiB non-heap) in a 21.5 GiB scope plus a 3 GiB client against 125 GiB RAM; 40 cores
(36 client threads + 32 writers); disk per lifetime: commit log ≤ 8 GiB, sstables ≤ the acknowledged bytes (C unthrottled at 1.25 MiB:
≲ 15 GiB in 240 s), one dump ≤ 16 GB deleted after its scan, all removed with `run/`; kept logs < 2 GiB; 714 GiB free.

**Cleanup and leftovers.** Stop every JVM this case started (by PID); `rm -rf /mydata/s4/r16/run`; delete scanned `.hprof` files; keep
`/mydata/s4/r16/logs/`, `/mydata/s4/r16/cassandra`, `/mydata/s4/r16/harness` and say so in §3. Commit small excerpts (client stats
heads/tails, sampler around each barrier, `Enqueuing`/`Writing`/`Flushing largest`/TRACE lines, scan JSONs, histogram heads, first-error
lines, `analyze.py` output) to `logs/` in this folder.

`sha256 of §1–§2 at freeze: 4e7b16c555f0630a9a5047c46d6019df043371524586de3bcaf520ac4167399f` (computed as `awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-20) · amendments after the freeze: none.

## 3. Runs (stage 2)

### 3.1 Environment and checks (2026-11-20, before readings)

- **Freeze hash:** recomputed with the stated `awk … | sha256sum` at stage-2 start (10:39 America/New_York):
  `4e7b16c555f0630a9a5047c46d6019df043371524586de3bcaf520ac4167399f` = the frozen value.
- **Node:** pc75 (`node3.jason92-326665…cloudlab.umass.edu`), x86_64, 40 cores, 125 GiB RAM (124 GiB available), cgroup v2, swap 8 GiB
  present (each node scope `MemorySwapMax=0`), OpenJDK 11.0.33, `/mydata` 714 GiB free. `pgrep -af CassandraDaemon` empty at the start
  and before every lifetime (`cotenancy` line of each `session.log`: no daemon, ≥ 120 GiB available). Stage 2 started ≈ 80 min earlier
  than §2.9's plan (10:39 instead of ≈ 12:00); the window ends were kept.
- **Tree:** `cp -a /mydata/s4/cassandra-base /mydata/s4/r16/cassandra`; jar sha256
  `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e` = B18's; no `ant` run; the base untouched.
- **Harness:** [`harness/`](harness/) (B18's, renamed to `r16`, plus the gate in `HotGen.java`, field decoding in `hprof_scan.py`,
  arms D8/D16 and heap 15872M in `run.py`, the `Used total` and gate columns in `analyze.py`), synced to `/mydata/s4/r16/harness/`.
- **Scanner known-answer check** (`instrument-check.sh`): 40 regions, 40 near-regions, 1,000 `HoldRegions$Marker`, and the decoded
  `HoldRegions$FieldProbe` fields exact (inherited long `0x0123456789ABCDEF`, inherited int 4242, reference → `AtomicLong` 31337,
  `AtomicInteger` 77, enum ordinal 2, own int −5) — **ok**.
- **Source-binding shakedown** (`run.py shakedown`, 2 GiB, 20 s `perthread` R = 64; not a reading): client sockets from 127.0.0.11–14.
  It already met real write timeouts: 130, each gated and ended when the batch's last row was read (≤ 11 polls), 0 retired.
- **Gate self-test** (`run.py shakedown selftest`): 457 gate waits (354 self-test + 103 real timeouts), 356 ended at the first poll,
  max 11 polls, 0 poll errors, 0 retired, `gated_now` back to 0 at the end — **ok**.
- **Resolved values, read back every lifetime** (`system_views.settings`, JVM command line, scope files): `heap_buffers`;
  `memtable_heap_space` = `memtable_offheap_space` = 512 MiB at 2 GiB; cleanup threshold 0.33333334; flush writers 2; `concurrent_writes`
  32 (4 in I); counter writes 32; in-flight 214,748,364 B / per IP 53,687,091 B; message size 16 MiB; `max_mutation_size` 16384 KiB;
  segment 32 MiB; `commitlog_total_space` 8192 MiB; `write_request_timeout` 2000 ms; `native_transport_timeout` 12 s; `throw_on_overload`
  false; hints on; key cache 100 MiB; `batch_size_fail_threshold` 50 KiB. JVM: `-Xms` = `-Xmx` = heap, G1 `G1HeapRegionSize=16m`,
  `G1NewSizePercent=50`, `MaxGCPauseMillis=300`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError=kill -9 %p`,
  **`MaxDirectMemorySize=15872M`** (resolved by `cassandra-env.sh` on pc75; recorded, not the budget). Scope `memory.max` = heap + 6 GiB,
  `memory.swap.max` 0. Every `EXPECTED` read-back matched. **L0** = 65 MiB in every lifetime.

### 3.2 Amendments after the freeze (dated 2026-11-20; none changes an arm's workload, a setting or a budget)

- **A1 (10:45 America/New_York, before any reading) — harness details §2.5 leaves open.** (a) `run.py` treats `java.lang.OutOfMemoryError:
  Java heap space` / `Dumping heap to` in `stdout.txt` as the endpoint (so the first-trigger check runs at the OOM when that comes before
  workload + 20 s, as §2.5 step 6 says); (b) a live end dump (`jcmd GC.heap_dump`) is taken in every surviving lifetime at ≤ 4 GiB
  (§2.5 asks it of C and I at 2 GiB; an end dump of a surviving lifetime is an allowed intrusive reading, §2.6), not at 15,872 MiB;
  (c) the first-trigger floor for the optional D8/D16 arms is `concurrent_writes − 1` (7/15), like I's 3; (d) B18's `flush_lines` grep
  `Enqueuing flush of t` never matched the 5.0.9 line `Enqueuing flush of ks.t`: fixed, plus `Flushing largest` lines.
- **A2 (≈ 10:58, after the H2-T-1 reading, before H2-T-2) — an offline attribution diagnostic.** H2-T-1's dump showed the pool counter
  at 403 MiB (0.79 × C) with 1,821 live regions (3.56 × C) and three DISCARDED allocators (owns = 0). To attribute those regions,
  `run.py` keeps the dump of a lifetime that has a flag file `/mydata/s4/r16/keepdump.<label>` (set for H2-T-2, H2-C-2 (end dump),
  H2-I-2, H2-I-3) instead of deleting it after the scan; the kept dumps are copied to the controller node (`pc96:/mydata/r16-diag/`) and read
  there by two new read-only tools, [`harness/hprof_refs.py`](harness/hprof_refs.py) (backward references from the memtables / from the
  DISCARDED allocators) and [`harness/hprof_reach.py`](harness/hprof_reach.py) (regions reachable from GC roots, and reachable only through
  one cut edge). Nothing runs on pc75 for them; the lifetimes are unchanged. `run.py` was replaced between lifetimes by an atomic `mv`.
- **Not triggered:** the pre-declared `Crm` fallback (§2.7) — H2-C-1 survived.

### 3.3 The nine 2 GiB lifetimes (S = 1.25 MiB, R = 160; order T-1, C-1, I-1, T-2, C-2, I-2, T-3, C-3, I-3; 10:47–11:19)

Workload: 4 source IPs × 9 threads, one gated unlogged single-partition batch in flight per thread. "Writing (K)" = the flushing memtable's
own counter after the barrier (% of C = `memtable_heap_space` = 512 MiB); "Used total" = the cleaner's pool-total line (max); "regions (U)"
= `byte[1048576]` in the dump (× C, share of the dump's shallow bytes); "pool (K)" = the SlabPool's on-heap `SubPool.allocated` decoded from
the same dump; "DISC." = SlabAllocators in state DISCARDED (owns = 0). All lifetimes: first-trigger check passed (4 client IPs;
MutationStage active 32 in T and C, 4 in I), read-backs as §3.1, scope `oom_kill` 0, client `retired` 0.

| Lifetime | Endpoint (s after workload start) | acked req (MiB) | client timeouts / `gated_now` max | flushes: Enqueuing → Writing (K); Used total | regions U (× C, share) | pool K at the dump (× C); DISC. | other |
|---|---|---|---|---|---|---|---|
| H2-T-1 | **heap OOM** at 7 | 167 (209) | 0 / 0 | 4 × 35–40 % → **125, 98, 113 %**; `High update contention in 1/1` × 3; Used total ≤ 0.37 | **1,821 (3.56 ×, 93 %)** | **403 MiB (0.79 ×)**; 3 | post-full-GC heap 1,928 MiB; 27 writer stacks |
| H2-T-2 | **heap OOM** at 7 | 160 (200) | 0 / 0 | 4 × 35–38 % → **98, 109, 116 %**; contention × 3; ≤ 0.36 | **1,818 (3.55 ×, 94 %)** | **477 MiB (0.93 ×)**; 3 | 1,922 MiB; dump kept (A2) |
| H2-T-3 | **heap OOM** at 7 | 161 (201) | 0 / 0 | 4 × 34–45 % → **100, 129, 123 %**; contention × 3; ≤ 0.38 | **1,822 (3.56 ×, 93 %)** | **276 MiB (0.54 ×)**; 3 | 1,932 MiB |
| H2-C-1 | survived 240 s | 10,305 (12,881) | 1,355 / 36 | 81 flushes, Writing ≤ 43 %; no contention; ≤ 0.76 | end dump 462 (0.90 ×, 84 %) | end 39 KB (0.00 ×); 4 | post-GC old gen ≤ 908 MiB; U_end 543 MiB |
| H2-C-2 | survived 240 s | 10,861 (13,576) | 1,492 / 36 | 85 flushes, ≤ 54 %; none; ≤ 0.88 | end dump 444 (0.87 ×, 84 %) | end 39 KB; 4 | ≤ 1,091 MiB; U_end 525 MiB; end dump kept (A2) |
| H2-C-3 | survived 240 s | 10,391 (12,989) | 1,548 / 36 | 83 flushes, ≤ 46 %; none; ≤ 0.80 | end dump 550 (1.07 ×, 86 %) | end 45 KB; 8 | ≤ 941 MiB; U_end 631 MiB |
| H2-I-1 | **heap OOM** at 100 | 3,289 (4,111) | 685 / 36 | 41 flushes, Writing ≤ 36 %; **no contention**; ≤ 0.69 | **1,782 (3.48 ×, 91 %)** | **427 MiB (0.83 ×)**; 8 | MutationStage pending ≤ 33; 4 writer stacks |
| H2-I-2 | **heap OOM** at 64 | 2,437 (3,046) | 458 / 36 | 30 flushes, ≤ 36 %; none; ≤ 0.69 | **1,792 (3.50 ×, 91 %)** | **437 MiB (0.85 ×)**; 8 | pending ≤ 32; dump kept (A2) |
| H2-I-3 | **heap OOM** at 93 | 3,201 (4,001) | 577 / 36 | 40 flushes, ≤ 43 %; none; ≤ 0.77 | **1,796 (3.51 ×, 91 %)** | **391 MiB (0.76 ×)**; 8 | pending ≤ 33; dump kept (A2) |

**OOM evidence (V5), every OOM lifetime:** `stdout.txt` has `java.lang.OutOfMemoryError: Java heap space`, `Dumping heap to …`,
`Heap dump file created` and `Executing /bin/sh -c "kill -9 <pid>"` (the shipped `OnOutOfMemoryError`); `gc.log` ends in back-to-back
full GCs at the heap size (post-full-GC 1,898–1,932 MiB of 2,048). Request frames and decoded mutations are small in every dump
(`Mutation`/`PartitionUpdate`/`BufferCell` ≤ 9 MiB): the gate held D2 + D3 as designed (no re-send while a write was pending; in T no
timeout at all, in I MutationStage pending ≤ 33).

**The decisive reading (the pool-total instrument, new in R16).** In every OOM dump the pool's own counter is **0.54–0.93 × C**, below the
limit, while the live regions are **3.48–3.56 × C**. Live regions beyond everything the non-DISCARDED allocators ever allocated (their
`regionCount`): T 1,333–1,539, I 1,355–1,403, i.e. **2.6–3.0 × C of live regions belong to memtables that were flushed and DISCARDED and
whose charge the pool has already released** (`SubAllocator.setDiscarded` → `releaseAll`, `MemtableAllocator.java:140-154`). The same happens in the surviving control: each C
end dump (idle node, 10 s after the client stopped, live objects only) holds **444–550 regions (0.87–1.07 × C) with the pool counter at
≈ 0**. So the bytes that fill the heap are **not counted** at the endpoint; P3's "pool.allocated ≥ 0.6 × U(D1)" fails in all six OOM dumps
(0.15–0.26).

### 3.4 Attribution diagnostic (A2): what keeps the discarded memtables' regions alive

Read offline on pc96 from the kept dumps (H2-T-2 OOM, H2-C-2 end, H2-I-2 OOM, H2-I-3 OOM); outputs in [`logs/`](logs/)
(`reach-*.json`, `refs-*.json`).

- **Backward references from the DISCARDED allocators** (`hprof_refs.py … discarded`; [`logs/refs-disc-H2-T-2.json`](logs/refs-disc-H2-T-2.json),
  `refs-disc-H2-C-2-end.json`, `refs-disc-H2-I-2.json`): DISCARDED `SlabAllocator` ← `AtomicBTreePartition$Updater.allocator` (and its
  `cloner`, and `this$0` = the memtable's `AtomicBTreePartition`) ← **`BTree$Updater.updateF`** ← `TinyThreadLocalPool$TinyPool.val1` ←
  `InternalThreadLocalMap.indexedVariables` ← `FastThreadLocalThread` of a `SEPWorker` (the shared executor's worker threads that run
  MutationStage). H2-T-2: 24 pooled updaters on 24 worker threads; H2-C-2 end: 68; H2-I-2: 18 (8 DISCARDED memtables pinned).
- **Reachability with one edge cut** (`hprof_reach.py`; roots = every GC-root record, class objects and static fields):

  | Dump | regions reachable | reachable with `BTree$Updater.updateF` cut | **regions reachable only via `updateF`** | reachable shallow MiB, all / with the cut |
  |---|---|---|---|---|
  | H2-T-2 (OOM) | 1,814 | 412 | **1,402 (2.74 × C)** | 1,913 / 504 |
  | H2-I-2 (OOM) | 1,790 | 422 | **1,368 (2.67 × C)** | 1,953 / 546 |
  | H2-I-3 (OOM) | 1,795 | 382 | **1,413 (2.76 × C)** | 1,956 / 503 |
  | H2-C-2 (end, idle) | 444 | 13 | **431 (0.84 × C)** | 519 / 77 |

  (Cutting every reference out of `TinyThreadLocalPool$TinyPool` gives the same numbers.) Without that single field each OOM dump holds
  ≈ 0.5 GiB, of which ≈ 0.4 GiB are the counted regions of the live and flushing memtables: **the OOM needs the uncounted, pinned regions.**
- **Source (5.0.9).** Every merge into a memtable partition runs `BTree.update(current.tree, update.tree, comparator, this)`
  (`BTreePartitionUpdater.java:89`), which takes a pooled `BTree.Updater` from a per-thread `TinyThreadLocalPool` (`BTree.java:395`,
  `:3428-3434`) and sets `this.updateF = updateF` (`:3444`). `close()` → `reset()` (`:3593-3604`, `:3273-3290`) clears the leaf and branch
  buffers but **never nulls `updateF` (or `comparator`, `:3422-3423`)**, and returns the updater to the thread's pool. The stale `updateF`
  is the `AtomicBTreePartition$Updater` of that thread's last write: its `current` (`AtomicBTreePartition.java:139`) and `this$0` reach the
  whole partition of a memtable that has since been flushed and discarded, so every cell of it and every slab region those cells sit in
  (including failed-CAS clones interleaved in the same regions) stays reachable, uncounted, until that worker thread writes again. With
  one hot partition each pinned partition is a whole memtable (T: 500–660 MiB after the overshoot; I: ≈ 175 MiB); with 36 partitions (C) a
  thread pins only its last partition, but regions shared between partitions keep 0.84–1.07 × C alive at idle.
- **JIRA (read only, 2026-11-20):** `text ~ "TinyThreadLocalPool"`, `text ~ "updateF"`, BTree + thread local + memtable, memtable +
  retain / leak since 2021: nothing describes this retention (CASSANDRA-21418, open, only lists `TinyThreadLocalPool` among thread locals
  to move to `CassandraThread`; CASSANDRA-21055 is a different pooled-builder leak). **new**.

### 3.5 Budget search and optional runs (11:19–11:52; T unless stated)

Resolved values at 15,872 MiB (read back): `memtable_heap_space` 3968 MiB (C), in-flight 1,664,299,827 B / per IP 416,074,956 B, everything
else as §3.1; at 4 GiB: C = 1024 MiB, in-flight 429,496,729 / 107,374,182 B. `MaxDirectMemorySize=15872M`; scope 22,016 MiB / 10 GiB,
`oom_kill` 0. "uncounted ≥" = live regions minus every region the non-DISCARDED allocators ever allocated (`regionCount`), × C.

| Lifetime | Heap, S | Endpoint | acked req (MiB) | timeouts; retired | Writing (K) | regions U (× C, share) | pool K at dump (× C); DISC. | uncounted ≥ |
|---|---|---|---|---|---|---|---|---|
| H16-T-1 | 15,872 MiB, 14 MiB | **heap OOM** at 44 s | 49 (686) | 81; 31 | 34 % → **177 %, 170 %** (6.86 / 6.59 GiB, 521 / 591 MiB of rows); contention × 2 | **14,539 (3.66 ×, 96 %)** | 4,870 MiB (1.23 ×); 2 | 2.43 × C |
| H16-T-2 | 15,872 MiB, 14 MiB | **heap OOM** at 47 s | 47 (658) | 79; 36 | **179 %, 177 %** | **14,561 (3.67 ×, 96 %)** | 4,369 MiB (1.10 ×); 2 | 2.56 × C |
| H16-T-3 | 15,872 MiB, 14 MiB | **heap OOM** at 40 s | 48 (672) | 82; 36 | **175 %, 167 %** | **14,530 (3.66 ×, 96 %)** | 5,313 MiB (1.34 ×); 2 | 2.31 × C |
| H4-T-R160-1 | 4 GiB, 1.25 MiB | **heap OOM** at 18 s (P7 predicted survival) | 692 (865) | 66; 0 | 9 flushes, **71–87 % — every barrier below C**; contention × 9 | **3,734 (3.65 ×, 96 %)** | **293 MiB (0.29 ×)**; 5 | 3.35 × C |
| H4-T-R320-1 | 4 GiB, 2.5 MiB | **heap OOM** at 13 s | 159 (398) | 18; 0 | **120, 92, 135 %** | **3,732 (3.64 ×, 96 %)** | 961 MiB (0.94 ×); 3 | 2.70 × C |
| H2-D16-1 | 2 GiB, 1.25 MiB, `concurrent_writes: 16` (optional) | **heap OOM** at 19 s | 625 (781) | 72; 0 | 18 flushes, ≤ 68 %; **no contention line** | **1,831 (3.58 ×, 94 %)** | 342 MiB (0.67 ×); 6 | 2.89 × C |
| H2-D8-1 | 2 GiB, 1.25 MiB, `concurrent_writes: 8` (optional) | **heap OOM** at 68 s | 2,153 (2,691) | 316; 0 | 44 flushes, ≤ 49 %; none | **1,806 (3.53 ×, 93 %)** | 376 MiB (0.73 ×); 8 | 2.78 × C |
| H16-C-1 | 15,872 MiB, 14 MiB, `perthread` (optional) | survived 240 s | 315 (4,410) | 1,053; 0 | 13 flushes, ≤ 45 % | no dump (A1); U_end 3,944 MiB live (0.99 × C) | — | — |

So the largest budget tried, **15,872 MiB (what `cassandra-env.sh` resolves on any node), fails 3/3** at S = 14 MiB. In the 15,872 MiB
lifetimes the flushing memtable's own counter is above C at the dump (1.10–1.34 × C, the blocking-cohort overshoot), but the live regions
are 3.66 × C: the extra 2.3–2.6 × C are again in DISCARDED memtables. H4-T-R160-1 reaches OOM with **no barrier above the limit at all**
(K ≤ 0.87 × C throughout, pool 0.29 × C at the dump), and the dose arms D16/D8, like I, reach OOM with no contention flag: the endpoint does
not need the claimed enforcement failure. The gate held everywhere (no write re-sent while pending); at 15,872 MiB T threads retired
(31–36: their batch was not readable within 120 s while the node was in back-to-back full GCs), recorded for T as §2.7 says.

### 3.6 Deviations, leftovers and logs

- **Deviations from the design:** none in workloads, settings, budgets or order (A1, A2 above are instrument/harness details). §2.9's
  time plan ran ≈ 80 min early; every planned and optional lifetime ran (no rerun needed: no invalid lifetime).
- **Processes:** none left on pc75 (`pgrep -af "CassandraDaemon|HotGen|plan.sh|after.sh|Jmx"` empty at 11:53; each lifetime ends with
  `daemons_left: none`).
- **On pc75 `/mydata/s4/r16/`** (kept): `cassandra/` (tree copy, 419 MB), `harness/`, `cls/`, `logs/<label>/` (full logs of every
  lifetime: `system.log`, `debug.log`, `gc.log*`, `stdout.txt`, `sampler.csv`, `rss.csv`, `hotgen.csv`, histograms, scans; 485 MB),
  `logs/plan-*.out`, `excerpts/` (1.7 MB, = this folder's `logs/`). `run/` removed after every lifetime; every `.hprof` deleted after its
  scan/diagnostic (the four kept dumps were deleted on pc75 and on pc96 after `hprof_reach.py`/`hprof_refs.py`). `/mydata/s4/cassandra-base`
  untouched.
- **In this folder:** [`harness/`](harness/) (all scripts and plan files), [`logs/`](logs/): `analyze.jsonl` (every lifetime), per lifetime
  `summary.json`, `flush-lines.txt` (Enqueuing / Writing / contention / `Flushing largest` lines), `oom-lines.txt`, `scan-*.json` (incl.
  `pool`, top allocators, class histogram, dump stacks), client/sampler excerpts, histogram heads, `memory.events`, `yaml.diff`,
  `jvm-flags.txt`; `instrument-summary.txt`; `plan-*.out`; the diagnostic outputs `reach-*.json`, `refs-*.json`.

## 4. Conclusion (stage 2)

**Verdict: `retry`.** Protocol status (detail): **`candidate`** — for the fixed condition T, 2 GiB, S = 1.25 MiB, defaults: V1 (3/3 OOM),
V2 (C 3/3 survive), V3, V5, V6 and V7 are met, **V4 is not** (the intervention reached OOM 3/3), and the claimed attribution fails. Outcome
row of §2.7: **row 3** — "C or I reaches OOM with `pool.allocated` ≤ 1.1 × C while regions > 2 × C → retry: an uncounted region holder
(accounting omission, C6-like) is active in one table; record it as a separate lead". All three I lifetimes match it (pool 0.76–0.85 × C,
regions 3.48–3.51 × C).

**Reason.** The OOM itself is solid and needs no re-send: T at 2 GiB died 3/3 at 7 s with 0 client timeouts (P1, P4 hold), the gated
`perthread` control survived 3/3 for 240 s while ingesting 12.6–13.3 GiB (P5 holds: Writing ≤ 54 %, Used total ≤ 0.88, post-GC old gen
≤ 1,091 MiB, 0 retired), and the budget search failed at every heap up to **15,872 MiB (3/3)**. The flushing memtable's own counter does
pass the limit at the barrier in T (98–129 % at 2 GiB, 167–179 % at 15,872 MiB; P2's first part holds), but that is not what fills the heap.
The new pool-total reading shows the pool counter **below C in every 2 GiB OOM dump (0.54–0.93 × C) while live regions are 3.48–3.56 × C**
(P3's "counted" clause fails: pool/U = 0.15–0.26), and the intervention `concurrent_writes: 4` — which removed the claimed overshoot
completely (Writing ≤ 43 %, no contention flag, MutationStage pending ≤ 33, gate held) — still died 3/3 at 64–100 s with the same
3.5 × C of regions (P6 fails); so did D16, D8 and the 4 GiB S = 1.25 MiB T whose every barrier stayed below C. The diagnostic on the kept
dumps (§3.4) finds the holder: **each SEP worker thread's pooled `BTree.Updater` keeps its last `updateF`** (`BTree.Updater.reset()` does not
null it), which reaches the whole partition of a memtable that has already been flushed and DISCARDED and whose charge the pool has
released; **1,368–1,413 regions (2.67–2.76 × C) are reachable only through that one field** in the T and I OOM dumps (without it ≈ 0.5 GiB
is reachable), and 431 regions (0.84 × C) at idle in the control. In the protocol's terms the OOM is U > C with K ≤ C — an **accounting
omission / release defect** (memory released from the pool while still reachable), with the blocking-cohort overshoot only enlarging each
pinned memtable (T reaches OOM in 7 s instead of I's 64–100 s). R16's design attributed it to the enforcement failure (U > C, K > C) and
used an intervention that does not touch the real holder, so V4 and the attribution are not met; the case is not a false positive (the
endpoint is reached at defaults and at the largest resolved heap).

**Predictions, as frozen:** P1 holds (3/3, 7 s). P2: Writing > 100 % in each T run (125, 116, 129 %) and contention 1/1 × 3 per run hold;
the pool total > 1.3 × C in ≥ 2 of 3 runs fails (Used total ≤ 0.38; dump pool 0.54–0.93 × C). P3: regions ≥ 2.5 × C (3.55–3.56 ×) and
≥ 60 % of the dump (93–94 %) hold; regions ≥ 5 × (`Mutation` + `PartitionUpdate` + other `[B`) holds (other `[B` 42–49 MiB, the named classes ≤ 2 MiB: 37–43 ×); pool ≥ 0.6 × U fails.
P4 holds (0 timeouts, `gated_now` 0). P5 holds 3/3. P6 fails 0/3 (OOM at 100, 64, 93 s; acked 3.0–4.1 GiB ≥ 2 × T's 201 MiB median —
the intervention kept working until it died). P7: 15,872 MiB OOM 3/3 holds; 4 GiB S = 2.5 MiB OOM holds; 4 GiB S = 1.25 MiB survival
fails (OOM at 18 s). P8: D16 Writing ≤ 68 % (< 70 %) and OOM; D8 OOM (not "survives like I" — I did not survive either).

**What a better design should change (the new retry row):**
1. **Re-target the holder and class.** Claim "stale `updateF` in thread-local pooled `BTree.Updater` pins the last-written partition of a
   flushed memtable (released from `memtable_heap_space` at discard, still reachable)": bypass by accounting omission / release defect
   (U > C, K ≤ C), domain D1, holder `BTree.java:3422-3423` (`comparator`, `updateF`) not cleared in `reset()` (`:3593-3604`), reached via
   `BTreePartitionUpdater.java:89` → `AtomicBTreePartition$Updater` (`current`, `this$0`).
2. **Intervention = a diagnostic build** (separate tree, diff saved) whose `BTree.Updater.reset()` also sets `updateF = null; comparator =
   null`; run T (hot, 2 GiB, 1.25 MiB, gated client) and the I shape (`concurrent_writes: 4`) ≥ 3 each on it; prediction: both survive
   (≈ 0.5 GiB reachable without the field). The unmodified T/C readings of R16 can be reused only with documented equivalence; better
   re-run T and C beside it.
3. **U reading = `hprof_reach.py`'s "regions reachable only via `updateF`"** at every OOM and every end dump, plus the decoded pool fields
   (K); keep the gated client.
4. **Multiplicity dial:** the number of SEP worker threads holding a stale updater (workers that last wrote different memtables) × the
   pinned partition's size (one hot partition = a whole memtable); vary partitions per memtable (1, 4, 36) and record retained bytes at idle
   (the control already retains 0.84–1.07 × C with the pool at 0) — a long idle-retention arm may show the release defect without OOM.
5. **Version check:** read `BTree.Updater.reset()` on 5.0.10 / trunk (and CASSANDRA-21019) before the run; a fixed later version would
   make the case `known-fixed` there.

**Separate lead (row 3 of §2.7):** the same pinning, independent of hot-partition contention: any write workload keeps up to one partition
per SEP worker thread of already-discarded memtables reachable and uncounted (R16 control: 0.84–1.07 × C at idle; I/D8/D16: OOM at 2 GiB
without a contention flag).
