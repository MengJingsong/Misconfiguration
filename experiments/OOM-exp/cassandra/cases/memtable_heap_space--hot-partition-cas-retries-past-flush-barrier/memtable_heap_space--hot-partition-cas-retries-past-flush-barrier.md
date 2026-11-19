# B18 — memtable_heap_space: a hot partition's failed-CAS clones charged past the limit by the blocking flush cohort  <!-- file: cassandra/cases/memtable_heap_space--hot-partition-cas-retries-past-flush-barrier/memtable_heap_space--hot-partition-cas-retries-past-flush-barrier.md -->

| Field | Value |
|---|---|
| Case ID | `B18` (B = bypass, the ID assigned with the pick; README "ID prefixes"). Predicted class by the protocol's measurement table: **bypass, enforcement failure** (U > C and K > C in the memtable pool: the blocking-cohort exemption admits allocations past the limit), amplified by a lock that excludes no one; stage 2 labels it from the readings (§2.1) |
| From | Cluster of phase-1 candidates `OC-323` (primary), `OC-46`, `OC-367`, `OC-373`, `OC-257`, `OC-266`, `OC-41` |
| Phase-1 case files | [`excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous.md) (OC-323, OC-46), [`excess_waste_offset-updatewastedallocationtracker-delta--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/excess_waste_offset-updatewastedallocationtracker-delta--autonomous.md) (OC-367, OC-373), [`max-cloned-size-allocate-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max-cloned-size-allocate-size--autonomous.md) (OC-257), [`slab-region-size-region-allocate-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/slab-region-size-region-allocate-capacity--autonomous.md) (OC-266), [`memtable_heap_space-tryAllocate-limit--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/memtable_heap_space-tryAllocate-limit--autonomous.md) (OC-41); stage-4 results: the files of the same stems under [`stage4-runtime-verification/results/`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/), plus the sibling [`excess_waste_bytes-uselock-wastetracker--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/excess_waste_bytes-uselock-wastetracker--autonomous.md) (same shared harness, the 128 MiB-pool hot cells) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9; on pc75 `/mydata/s4/cassandra-base`, `build/apache-cassandra-5.0.9-SNAPSHOT.jar`), OpenJDK 11.0.33 |
| Stage 1 (design) | OOM-agent stage-1 session (workflow, wave 4), 2026-11-18 13:38–13:55 America/New_York; nothing run (read-only check of pc75 and read-only JIRA REST searches only) |
| Stage 2 (verify) | OOM-agent stage-2 session (workflow, wave 4, fresh), 2026-11-18 13:54–15:12 America/New_York, pc75, run directory `/mydata/s4/b18-w4`; 25 lifetimes (9 planned at 2 GiB, 3 Crm fallback, 6 budget search, 7 optional) |
| Verdict | **retry** — detail `candidate` (V1, V3, V5–V7 met; V2 only via the fallback control; V4 not met); bypass, enforcement failure, overshoot confirmed; T reaches heap OOM 3/3 at 2, 4 and 8 GiB, but the matched control C and the intervention I also reached OOM at the designed load |

## Summary

- **Conclusion:** a stock Cassandra 5.0.9 node, every capacity at its default, died with `java.lang.OutOfMemoryError: Java heap space`
  in **3/3** runs at a 2 GiB heap 7–10 s after 36 clients began writing 5 MiB single-partition batches into **one** partition (and 3/3 at
  4 GiB with 10 MiB, 3/3 at 8 GiB with 14 MiB; 2.5 and 1.25 MiB batches also died, 1/1 each). After each flush switch the old memtable's
  own counter rose from ≈ 36 % to **216–382 % of the whole `memtable_heap_space`** within 1–3 s while it held only 28–33 batches of rows;
  the OOM dumps held **3.2–3.6 × the pool in live 1 MiB slab regions** (81–94 % of the heap). The bypass (U > C, K > C) is confirmed, but
  the frozen design does not attribute the OOM to it: the uncontended control at the same in-flight load also died 3/3 (34–43 s), and the
  intervention `concurrent_writes: 4` kept the memtable below the limit yet died 2/3 from a MutationStage backlog of timed-out
  mutations. Only the rate-matched fallback control survived (3/3). Verdict **retry**.
- **Root cause (as measured):** the bytes are counted; the limit check admits them. A flush marks every older write as blocking and
  `SubAllocator.allocate` then charges with no limit; on one hot partition every successful CAS invalidates every concurrent attempt, so
  the 32 MutationStage writers re-clone the whole update ≈ 300–360 times per barrier (η 0.61–0.73), all past the limit. An exclusive
  per-partition lock (optional patch I2) does not stop it, because blocking writers skip the lock.
- **Claimed root cause (stage 1, tested above):** with the shipped `heap_buffers` allocator every attempt to merge an update into a
  memtable partition clones the update's values into 1 MiB slab regions and charges them to the memtable pool at clone time;
  a lost CAS keeps its clone (charged and physically retained until the memtable is discarded). The 10 MiB waste limit's
  "pessimistic lock" synchronizes on a per-call `Updater`, so it excludes no writer, and when a flush marks the older write
  cohort as blocking, that cohort's allocations are admitted **past** `memtable_heap_space` with no wait. On one hot partition
  with the 32 default MutationStage writers, each flush barrier therefore admits up to ≈ n(n−1)/2 = 496 failed clones of the
  update past the pool limit (stage 4 saw a memtable at 678 % of its pool).
- **Design in one line:** a fresh single node with a 2 GiB heap and shipped settings; 36 client threads from 4 loopback source
  addresses write single-partition unlogged batches of 5 MiB (640 rows × 8 KiB) into **one** partition; expect a Java heap OOM
  with the heap dump dominated by 1 MiB slab regions > 1.4 × the pool, 3/3; matched control = the same batches into 36
  partitions (one per thread, no contention); intervention = `concurrent_writes: 4` (bounds the contending cohort); then the
  budget search 4 → 8 GiB with the batch size the default in-flight limits admit at that heap.

## 1. Candidate

### 1.1 The cluster's rows, quoted

From `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md` (Status already `picked: B18`):

> | OC-41 | 2026-11-16 | `memtable_heap_space-tryAllocate-limit--autonomous` | legacy | [lead list, blind, E1] A partition update's object overhead is charged only after it is merged (`AtomicBTreePartition.java:175`; "can overshoot", `SkipListMemtable.java:123`), so 32–96 writer threads can each hold one uncounted update when the pool is full: ≈ 0.6 GB for 1 MiB tiny-row updates, several GB for 16 MiB updates, beyond the heap/4 cap (per-row heap ≈ 20× serialized is an estimate). | CP-11, CP-1 | picked: B18 |
>
> | OC-46 | 2026-11-17 | `excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous` | legacy | [lead list, blind, E2; cf. B2 (memtable allocation past the limit, never run)] The "pessimistic lock" at the waste limit synchronizes on a per-call `Updater` (`AtomicBTreePartition.java:120-123`), so nothing is serialized; failed-CAS clones (90–94 % of attempts in stage 4) stay charged and held until flush, and in-flight writers pass the pool limit via `isBlocking`: memtable heap at flush start ≈ 2–3 × `memtable_heap_space` (figure unchecked). | CP-11, CP-6 | picked: B18 |
>
> | OC-257 | 2026-11-18 | `max-cloned-size-allocate-size--autonomous` | autonomous | A flush lets older writes allocate past the memtable limit. The flush marks every write older than its barrier as blocking (ColumnFamilyStore.java:1238). [details](runs/wave2.md#oc-257) | — | picked: B18 |
>
> | OC-266 | 2026-11-18 | `slab-region-size-region-allocate-capacity--autonomous` | autonomous | A flush lets older writes allocate past the memtable limit. The flush calls writeBarrier.markBlocking() (ColumnFamilyStore.java:1238). [details](runs/wave2.md#oc-266) | — | picked: B18 |
>
> | OC-323 | 2026-11-18 | `excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous` | guided | Under hot-partition write contention the memtable heap pool overshoots its limit. [details](runs/wave2.md#oc-323) | CP-6, CP-11, CP-1, CP-8 | picked: B18 |
>
> | OC-367 | 2026-11-18 | `excess_waste_offset-updatewastedallocationtracker-delta--autonomous` | autonomous | Holder: memtable slab regions (heap_buffers, default) filled by failed CAS retries on a hot partition. [details](runs/wave2.md#oc-367) | — | picked: B18 |
>
> | OC-373 | 2026-11-18 | `excess_waste_offset-updatewastedallocationtracker-delta--autonomous` | guided | Holder: memtable pool bytes cloned by failed CAS attempts on a hot partition, plus allocation past the pool limit while the write OpOrder group is blocking. [details](runs/wave2.md#oc-373) | CP-6, CP-11, CP-14 | picked: B18 |
>

Details of the stage-5 rows (`runs/wave2.md`; OC-41 and OC-46 are legacy rows with their text inline above):

**OC-323** (primary):

> **Case file:** `excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-11, CP-1, CP-8
> Under hot-partition write contention the memtable heap pool overshoots its limit. Holder: memtable slab regions (heap_buffers default) holding the cloned values of every failed CAS merge attempt. SlabAllocator charges these at clone time and never refunds them, and they stay until the memtable is discarded. Why nothing stops it: the pessimistic-lock fallback (EXCESS_WASTE_BYTES) does `synchronized (this)` on the per-call Updater, a new object for every addAll, so it excludes no writer. Stage 4 measured about 94% of CAS attempts still failing after the switch. A writer whose OpOrder group is blocking a flush barrier is charged past the pool limit without waiting (SubAllocator.allocate's isBlocking branch), and new-partition overhead is also allocated after the fact. Up to 32 writers (concurrent_writes) keep re-cloning while the flush starts. Size: stage 4 measured memtable on-heap at the `Writing` line of 328 MiB against a 128 MiB pool (2.6x), contended owns() 2-4x the single-writer value, and 2-9x fewer rows per flush. At the default memtable_heap_space of heap/4, a 2-3x overshoot puts 50-75% of the heap in memtables alone, on top of caches, reads and compaction. The two other EXCESS_WASTE_BYTES stems (excess_waste_bytes-updatewastedallocationtracker-wastedbytes--autonomous, excess_waste_bytes-uselock-wastetracker--autonomous) show the same mechanism; file it once, naming all three.
> **Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:180-183; src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:89; src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:122,137,157,168,293; src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java:122-125

**OC-367:**

> **Case file:** `excess_waste_offset-updatewastedallocationtracker-delta--autonomous` · **Agent:** autonomous · **Patterns:** —
> Holder: memtable slab regions (heap_buffers, default) filled by failed CAS retries on a hot partition. Each failed merge attempt clones the update's cell values through the memtable allocator, and they are charged and kept in 1 MiB slab regions (values up to 128 KiB). Nothing refunds them when the CAS loses. Why nothing stops it: (a) the 'pessimistic lock' is synchronized on the per-call Updater, so it excludes no one and retries go on after the flip; (b) while a flush barrier has marked the old write OpGroup as blocking, MemtableAllocator.allocate skips the pool limit and charges past memtable_heap_space. So every retry of every old-group writer during a barrier lands on the heap above the pool. Rough size at defaults: there are up to concurrent_writes=32 old-group writers on one partition, and each failure means another writer won, so up to about 32*31/2 ≈ 500 failed attempts × the update size. The update size is bounded only by max mutation size (commitlog_segment_size/2 = 16 MiB). That is ~500 MiB of real retained slab memory past the limit for 1 MiB batches and several GiB for maximum-size mutations, on top of memtable_heap_space = heap/4. Stage 4 measured memtable on-heap at flush start at 2-3x the pool limit in the hot-partition cells.
> **Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:180-183; src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:120-123,153-170,179-186; src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java:126-132,149-160; src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:89-92,139

**OC-373:**

> **Case file:** `excess_waste_offset-updatewastedallocationtracker-delta--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-11, CP-14
> Holder: memtable pool bytes cloned by failed CAS attempts on a hot partition, plus allocation past the pool limit while the write OpOrder group is blocking. Each optimistic attempt clones the update's values through the allocator (BTreePartitionUpdater.java:126-132). The clone is charged at clone time (SlabAllocator.java:89) and never refunded when the CAS fails, and small values stay inside the memtable's slab regions until the memtable is discarded. Why nothing stops it: (1) the 'pessimistic' lock is on a per-call Updater (AtomicBTreePartition.java:120-123, 157), so retries continue without bound (stage 4: 94% of locked attempts failed; contended runs charged 2-5x a single-threaded run; allocation 33.6-36.8 GB for 4.1 GiB payload); (2) once a flush barrier makes the op group blocking, MemtableAllocator.allocate charges with no limit check (MemtableAllocator.java:180-183). Retries in that window are therefore admitted past memtable_heap_space (default heap/4), bounded only by barrier duration x concurrent_writes (32) x retries x update size. Stage 4 saw on-heap at flush above the cleanup threshold but did not measure the overshoot during barriers. Rough size: up to tens to hundreds of MB past the pool per barrier with 16 MiB mutations on a hot partition; not measured.
> **Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:180-183 (blocking group bypasses limit); db/partitions/AtomicBTreePartition.java:153-170, :157 (per-call lock, retry loop); utils/memory/SlabAllocator.java:89 (charged at clone, not refunded)

**OC-257:**

> **Case file:** `max-cloned-size-allocate-size--autonomous` · **Agent:** autonomous · **Patterns:** —
> A flush lets older writes allocate past the memtable limit. The flush marks every write older than its barrier as blocking (ColumnFamilyStore.java:1238). After that, SubAllocator.allocate charges memory with allocated(size) even when tryAllocate fails (MemtableAllocator.java:180-184), so none of those writes wait for room. The overshoot is limited only by how many writes are in flight in the old group and how big they are: about concurrent_writes (32) plus counter writes, times max_mutation_size (default 16 MiB, half a commitlog segment). That is up to about 512 MiB above memtable_heap_space at defaults, held at the same moment the pool is full. Stage 4 saw 16 MiB pass the limit with no parking in the unit probe.
> **Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:169-197; src/java/org/apache/cassandra/db/ColumnFamilyStore.java:1236-1239

**OC-266:**

> **Case file:** `slab-region-size-region-allocate-capacity--autonomous` · **Agent:** autonomous · **Patterns:** —
> A flush lets older writes allocate past the memtable limit. The flush calls writeBarrier.markBlocking() (ColumnFamilyStore.java:1238). From then on, every write in the older op group that finds the pool full takes allocated(size) without waiting (MemtableAllocator.java:180-184). The excess is limited only by the writes in flight in that group: about 32 concurrent writes (plus counter writes) times max_mutation_size (16 MiB at defaults), so up to about 512 MiB above memtable_heap_space, at the moment the pool is already full.
> **Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:169-197; src/java/org/apache/cassandra/db/ColumnFamilyStore.java:1236-1239

**Triage row** (`runs/triage-2026-11-18.md`, rank 9):

> | 9 | OC-323 | yes | single ARM node | Under write contention on one hot partition, failed CAS merge clones stay charged in slab regions. The pessimistic-lock fallback synchronizes on a new Updater per call and so excludes nobody, and writers in a blocking flush barrier allocate past the limit. Stage 4 measured the memtable at 328 MiB against a 128 MiB pool (2.6x); at a 2 GiB heap (pool 512 MiB), a 2-3x overshoot (1-1.5 GB) plus the rest of the heap is a plausible single-node OOM. | Duplicates the legacy OC-46 (open), OC-367 and OC-373. Next to C6 (slab accounting) and B2 (never run). OC-257, OC-266 and the legacy OC-41 (flush-barrier isBlocking overshoot, up to 32 x 16 MiB) are the same family and could be one combined design. |

### 1.2 What this design covers, row by row

| Row | Its claim | Covered by B18? |
|---|---|---|
| **OC-323** (primary) | failed-CAS clones of a hot partition stay charged in slab regions; the pessimistic lock on the per-call `Updater` excludes nobody; the blocking cohort is charged past the limit; 2–3 × the pool at flush start | **Yes, fully**: arm T at a 2 GiB heap with the shipped heap/4 pool; U (dump regions) and K (pool gauge, `Writing` lines) against C; the lock and exemption as the mechanism, the cohort size as the intervention |
| **OC-46** | the same (legacy text: per-call `Updater` lock, 90–94 % failed CAS, in-flight writers pass the limit via `isBlocking`, memtable 2–3 × `memtable_heap_space`) | **Yes, fully** (same arms) |
| **OC-367** | failed retries of up to 32 old-group writers ≈ 32·31/2 ≈ 500 failed attempts × update size, past the limit during a barrier; several GiB for maximum-size mutations | **Yes** for the n(n−1)/2 × S multiplicity at n = 32 (default `concurrent_writes`). **Not** at S = 16 MiB: at a 2 GiB heap the default in-flight limits (heap/10 = 204.8 MiB, heap/40 = 51.2 MiB per IP) admit 36 concurrent requests only up to ≈ 5 MiB; the budget search raises S with the heap (10 MiB at 4 GiB, 14 MiB at 8 GiB), never to 16 MiB |
| **OC-373** | same holder; "stage 4 did not measure the overshoot during barriers" | **Yes**: the 0.5 s pool-gauge sampler and the `Writing` lines measure K through the barrier windows, the dump measures U |
| **OC-257** | the blocking cohort allocates past the limit with no retries: ≤ (32 writes + counter writes) × `max_mutation_size` ≈ 512 MiB above the pool | **Partly**: the no-retry exemption is exactly what the matched control C exercises (distinct partitions: no CAS failures, overshoot ≤ in-flight writers × S ≈ 160 MiB at 2 GiB), and C is **predicted to survive**; the 16 MiB size and counter writes (`concurrent_counter_writes`) are not tested |
| **OC-266** | same as OC-257 (different phase-1 stem) | **Partly**, as OC-257 |
| **OC-41** | a partition update's object overhead is charged only after the merge (`reportAllocatedMemory`, and new-partition overhead "after the fact", `SkipListMemtable.java:121-125`), so 32–96 writers each hold one uncounted update when the pool is full; ≈ 20 × serialized heap for tiny rows | **Partly**: the after-merge charge is part of K in every arm and the decoded requests in flight are measured as domain D2, but they are not isolated; the tiny-row variant (≈ 20 × expansion) is not tested (rows here carry 8 KiB values so the regions dominate) |

### 1.3 Phase-1 constraints, checks and stage-4 measurements

| Phase-1 stem | Constraint / check | Stage-4 (pc39, 2026-10-28; non-default settings: `concurrent_writes: 128`, pool 128/512/1024 MiB at an 8 GiB heap, timeouts raised, in-flight limits 2 GiB, hints off) |
|---|---|---|
| `excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2` | `EXCESS_WASTE_BYTES` (10 MiB, `AtomicBTreePartition.java:63`) in `updateWastedAllocationTracker` | true negative ("does not cap"): rows per flush flat across 1 MiB / 10 MiB / 1 GiB builds; failed CAS 90–92 % of attempts; **94 % of attempts in the "locked" regime still failed; no BLOCKED thread** (the monitor is the per-call `Updater`); WE cells (32 threads × 9.8 MB batches, hot) "not valid": **`Writing` memtable 2.391 GiB (478 %) and 3.391 GiB (678 %) of a 512 MiB pool** after `Enqueuing` at 195 / 183 MiB, 194–406 full GCs per 120 s, heap after GC 8.0 GB, client connections closed ≈ 42 s into the workload (the JVM's exit cause was not recorded) |
| `excess_waste_offset-updatewastedallocationtracker-delta` | `EXCESS_WASTE_OFFSET` | true negative; WF hot: failed CAS 60 %, 33.6–36.8 GB allocated for 4.1 GiB payload |
| `excess_waste_bytes-uselock-wastetracker` (sibling) | `useLock` | hot cells at a 128 MiB pool: `Writing` memtable **340 MiB (266 %)**, 322 MiB (252 %) after `Enqueuing` at 43 MiB (34 %); at 512 MiB: 374 MiB (73 %) |
| `max-cloned-size-allocate-size` | `MAX_CLONED_SIZE` (128 KiB) | unit probe: 16 MiB passed the limit with no parking under a blocking group |
| `slab-region-size-region-allocate-capacity` | `REGION_SIZE` (1 MiB) | per-table region (that is C6's mechanism, not this one) |
| `memtable_heap_space-tryAllocate-limit` | `memtable_heap_space` in `tryAllocate` | caps the counted pool outside barrier windows |

These are leads: every stage-4 cell above ran with `concurrent_writes: 128` and raised timeouts; B18 runs at defaults.

### 1.4 JIRA prior art (read only; nothing posted)

Local survey (`jira-oom-survey.csv`) and JIRA REST searches on 2026-11-18 (`AtomicBTreePartition AND synchronized`,
`"pessimistic locking" AND partition`, `markBlocking`, `wasteTracker`, `memtable AND contention AND OutOfMemoryError`,
`"hot partition" AND OOM` since 2019, `memtable_heap_space AND exceed`):

| Issue | Status | Relevance |
|---|---|---|
| CASSANDRA-7546 "AtomicSortedColumns.addAllWithSizeDelta has a spin loop that allocates memory" | Fixed 2.1.1 | Origin of the waste tracker and the pessimistic lock: past 10 MiB of waste the partition was to be **locked**. In 5.0.9 the lock is `synchronized (this)` inside the per-call `Updater` (`AtomicBTreePartition.java:120-123`, `:146-161`), so it excludes no one. Likely lost in the `Updater` refactor of CASSANDRA-15511 (4.1; inferred from the class structure, not checked against git history). Not reported. |
| CASSANDRA-15367 "Memtable memory allocations may deadlock" | Fixed 3.0.21/3.11.7/4.0 | Documents the design: "Memtable memory limits may be lifted for operations in the first cohort, since they block flush", and the 4.0 lock that waiters abandon once their group `isBlocking`. The exemption itself is **by design**. |
| CASSANDRA-21019 "Memtable allocator: separate memory usage tracking and limit checking" | Fixed 4.0.22/4.1.13/**5.0.10** (2026-09-13) | After the pin: checks the limit before a mutation starts and lets it complete; its effect on retries of the blocking cohort is not checked here. B18 stays at 5.0.9 (pinned); a re-test on 5.0.10 is a follow-up, not part of this design. |
| CASSANDRA-20226 "Reduce contention in MemtableAllocator.allocate" | Fixed 6.0 | Performance of the allocator CAS; not this mechanism. |
| CASSANDRA-17163 "High CAS failures in MemtablePool.SubPool.tryAllocate" | Duplicate of 15511 | Allocator-counter CAS contention; not this mechanism. |
| CASSANDRA-10937 (OOM under write load, hot partition) | Won't Fix | Judged overload/anti-pattern; no mechanism named. |
| CASSANDRA-20298 (slab regions per memtable, test-only fix) | Fixed (test) | C6's mechanism (uncounted region per memtable), not this one. |

**Verdict:** `new` for the claimed OOM (the non-exclusive pessimistic lock multiplying failed clones inside the blocking
cohort's exemption); the exemption alone is `by design` (15367). Not `known-fixed` at 5.0.9.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

- **Write path.** A CQL write at CL ONE on a single node is applied on `MutationStage` (`Stage.java:46`, threads =
  `concurrent_writes`, default 32, `conf/cassandra.yaml:723`); a write that expires before it starts is re-submitted to the same
  stage as a hint to self (`StorageProxy.java:2640-2656`, `:2827`), so at most 32 threads apply mutations at once.
  `SkipListMemtable.put` → `AtomicBTreePartition.addAll` (`AtomicBTreePartition.java:120-123`) creates a **new `Updater` per call**.
- **Clone per attempt.** `Updater.addAll` loops (`:146-176`): each `tryUpdateData` (`:179-186`) builds a merged partition with
  `BTreePartitionUpdater.makeMergedPartition` (`BTreePartitionUpdater.java:80-94`), which clones every inserted row's values
  through the memtable cloner (`insert`/`merge`, `:126-165`) into `SlabAllocator.allocate` (`SlabAllocator.java:83-110`):
  values ≤ `MAX_CLONED_SIZE` (128 KiB, `:52`) are bump-allocated in the current 1 MiB on-heap region (`REGION_SIZE`, `:51`;
  `heap_buffers` is the shipped `memtable_allocation_type`, `conf/cassandra.yaml:825`), and the bytes are charged to the pool
  **at clone time** (`:89` → `MemtableAllocator.SubAllocator.allocate`). Then the CAS on `ref` (`AtomicBTreePartition.java:185`): when it fails the
  clone is not refunded and its bytes stay in the region until the memtable is discarded after its flush. The object
  overhead of the winning attempt is charged afterwards (`reportAllocatedMemory`, `BTreePartitionUpdater.java:180-183`; OC-41).
- **The lock that excludes no one.** After `EXCESS_WASTE_BYTES` (10 MiB) of waste the partition switches to
  `shouldLock` (`AtomicBTreePartition.java:60-64`, `:231-296`), and `addAll` then runs each attempt inside
  `synchronized (this)` (`:155-161`) — `this` is the per-call `Updater`, so every writer holds its own monitor and the
  retries continue (stage 4: 94 % of "locked" attempts failed, no BLOCKED thread).
- **The exemption.** `SubAllocator.allocate` (`MemtableAllocator.java:169-197`): if `tryAllocate` fails and the writer's
  `OpOrder.Group` `isBlocking()`, it calls `allocated(size)` — charged, **no wait, no limit** (`:180-184`). A flush
  `switchMemtable`s and issues a barrier on the global `Keyspace.writeOrder` (`Keyspace.java:107`, `ColumnFamilyStore.java:1200-1224`);
  `Flush.run` calls `writeBarrier.markBlocking()` then `await()` (`ColumnFamilyStore.java:1236-1239`, comment "permitting them to
  exceed our memory limit"). Every write started before the barrier is in the blocking cohort until it completes.
- **Multiplication.** On one hot partition with n busy writers, each successful CAS invalidates every concurrent attempt, so
  n writers that started before the barrier finish only after ≈ n(n−1)/2 failed attempts (one winner per round). Each failed
  attempt clones the whole update (S bytes of values) into the old memtable's regions; once the pool is at its limit, all of it
  is admitted through the exemption. Overshoot per barrier ≈ η · n(n−1)/2 · S, η the fraction of rounds with a loser per
  writer (stage-4 WE cell, n ≤ 32, S = 9.8 MB: 2.2 and 3.2 GiB past the `Enqueuing` level → η ≈ 0.49–0.71). With n = 32
  and S = 5 MiB: 1.2–1.7 GiB past the switch level, against a 512 MiB pool at a 2 GiB heap.
- **Direction label:** **bypass (enforcement failure)** — U > C and K > C in the memtable domain, the counter tracks the bytes
  but the check admits them (blocking-cohort exemption) — with the non-exclusive pessimistic lock as the multiplicity that
  makes the exempted amount unbounded by anything but n² · S. If the OOM also needs D2/D3 beyond their contracts, stage 2
  tags it **mixed**. Interpretation: intentional exception (the exemption, 15367) combined with a suspected implementation
  defect (the per-`Updater` monitor). Technique note: [`bypass-playbook.md`](../../../bypass-playbook.md) (enforcement-failure
  bypass) with the multiplicity step of [`combo-playbook.md`](../../../combo-playbook.md).
- **Overlap with C6** (verified, `memtable_heap_space-slab-region--written-table-multiplicity`): same holder type (1 MiB
  `heap_buffers` slab regions, `byte[1048576]`), same pool, same dump scanner. Different control failure: C6 is an
  **accounting omission** across many tables (K stayed ≤ 82 MiB while U was 2.1 × C); B18 is **one table, one partition**,
  the bytes are counted (K ≈ U) and the counted pool itself goes past C through the exemption. C6's result does not predict
  B18 and B18 does not need many tables (its schema is one table; D5 is ≈ C6's B0). C6's intervention
  (`unslabbed_heap_buffers`) is not used here: under `HeapPool` failed clones become garbage but stay charged (K > U), which
  changes the holder and the counter at once.

### 2.2 Protection map

| Domain | Allocation, owner, release | Local contract (C) | Scope / multiplicity | Aggregate coverage | Lifetime |
|---|---|---|---|---|---|
| **D1 memtable regions + charged overhead (claimed holder)** | `SlabAllocator` 1 MiB `byte[]` regions of the memtable of `ks.t` (and system tables), object overhead charged after merge; released when the flushed memtable is discarded (`setDiscarded`) | `memtable_heap_space` = heap/4 (512 MiB at 2 GiB), hard wait at the limit (`hasRoom`), flush at `memtable_cleanup_threshold` = 1/(1+2) = 0.33; **documented soft overshoot**: the blocking cohort's own allocations (one attempt per in-flight writer: ≤ n·S = 32 × 5 = 160 MiB), the after-the-fact partition overhead (bytes), the 10 MiB waste allowance per partition before locking, region-tail waste ≤ 12.5 %. **C_contract ≈ 512 + 160 + 10 + 64 ≈ 746 MiB** at 2 GiB | all memtables share one pool; here one table, one partition | the pool is the aggregate control; the exemption is its only exit | standing until flush + discard (seconds) |
| D1' per-attempt garbage | rows/cells/B-tree arrays of failed merges (regular heap, unreachable after the CAS fails) | none (garbage) | × attempts | GC only | transient (young gen) |
| D2 decoded requests in flight | native-transport request frames decoded to `Mutation`s (heap), held until the response | `native_transport_max_request_data_in_flight` heap/10 = 204.8 MiB, per IP heap/40 = 51.2 MiB, on-wire bytes, v4: stop reading at the limit (`throw_on_overload` off); 36 × 5 MiB = 180 MiB on wire, 4 IPs × 45 MiB | per client connection/IP | global reserve | until response (success or timeout) |
| D3 MutationStage backlog after timeouts | mutations whose client request timed out (2 s) but whose task is still queued/running, and expired ones re-queued as hints to self | none (queue unbounded); charged nowhere after the timeout response | ≤ client re-send rate × residence | — | until applied/dropped |
| D4 flush / compaction / commit log | flush writer and compaction buffers (heap), commit-log segments (mmap/direct) | compaction throughput default; `commitlog_total_space` default | 2 flush writers, `concurrent_compactors` default | — | transient |
| D5 baseline | schema, metrics, caches (key cache cap min(5 % heap, 100 MiB), unused by a write-only workload), JMX sampler | — | — | — | standing |
| Direct (not the budget) | Netty frames, `BufferPool` networking | `MaxDirectMemorySize` as `cassandra-env.sh` resolves on pc75 (7,936 MiB) | — | — | recorded only (RssAnon) |

### 2.3 Configuration and budget audit

- **Build:** `/mydata/s4/cassandra-base` on pc75 (Cassandra 5.0.9 from `systems/cassandra/source/` at repository HEAD
  `411b6a8f`, smoke-tested 2026-11-18), copied with `cp -a` to `/mydata/b18/cassandra`; never run `ant` there. Record
  `sha256sum build/apache-cassandra-5.0.9-SNAPSHOT.jar`. OS Ubuntu 22.04, kernel 5.15, cgroup v2, swap 8 GiB present
  (set `MemorySwapMax=0` for the node's scope), JDK 11.0.33, GC = shipped `jvm11-server.options`: G1,
  `-XX:G1HeapRegionSize=16m` (so 1 MiB regions are not humongous), `-XX:G1NewSizePercent=50`, `MaxGCPauseMillis=300`,
  `-XX:+HeapDumpOnOutOfMemoryError`, `cassandra-env.sh` `-XX:OnOutOfMemoryError=kill -9 %p`.
- **Capacity constraints (V6), all shipped defaults, read back from `system_views.settings` each lifetime:**
  `memtable_allocation_type: heap_buffers`; `memtable_heap_space` unset → heap/4; `memtable_offheap_space` unset → heap/4;
  `memtable_cleanup_threshold` unset → 0.33; `memtable_flush_writers` unset → 2 (one data dir); `concurrent_writes: 32`;
  `concurrent_counter_writes: 32`; `native_transport_max_request_data_in_flight` / `_per_ip` unset → heap/10, heap/40;
  `native_transport_max_message_size` unset → 16 MiB; `max_mutation_size` unset → `commitlog_segment_size`/2 = 16 MiB;
  `commitlog_segment_size: 32MiB`; `commitlog_total_space` unset; `write_request_timeout: 2000ms`;
  `native_transport_timeout` 12 s; `batch_size_warn_threshold` 5 KiB / `batch_size_fail_threshold` 50 KiB (not applied to
  single-partition batches, `BatchStatement.java:333-335`); `hinted_handoff_enabled: true`; key/counter/row caches default;
  `EXCESS_WASTE_BYTES` 10 MiB (hard-coded). Labels: all **default**.
- **Environment diff only** (classified *environment*): `cluster_name: b18`, `listen_address`/`rpc_address: 127.0.0.1`,
  seeds `127.0.0.1:7000`, `data_file_directories`/`commitlog_directory`/`hints_directory`/`saved_caches_directory`/
  `cdc_raw_directory` under `/mydata/b18/run/`; everything else is the shipped `cassandra.yaml`. Ports 9042/7000/7199 (check
  free). Client source addresses 127.0.0.11–127.0.0.14 (four emulated client hosts, see §2.5).
- **Arm-only deviations:** intervention I: `concurrent_writes: 4`; optional I2: the diagnostic lock patch (§2.8). Instrument
  only: `nodetool setlogginglevel org.apache.cassandra.db.memtable.SkipListMemtable TRACE` (one line per flush, "High update
  contention"), the JMX sampler. No Byteman, no raised timeouts, no fault injection → the conditions label can be
  `deployment`.
- **Budget (V7):** heap `MAX_HEAP_SIZE=2G` (ideal; ≥ 512 MiB standing rule), then the budget search 4G → 8G. The claimed
  node class is a small-to-medium deployment node; for pc75 itself `cassandra-env.sh` would resolve heap 15,872 MiB and
  direct 7,936 MiB; the chosen heaps are below that and meet the standing rule without review. Direct limit: as resolved by
  `cassandra-env.sh` from RAM (7,936 MiB on pc75 even with a hand-set heap; record the value). Container: the node runs in a
  `systemd-run --user --scope -p MemoryMax=<heap + 6 GiB> -p MemorySwapMax=0` scope as isolation only; the scope is not the
  budget (it must not bind: `memory.events` `oom_kill` 0).
- **Resolved values to record:** pool limit (`memtable_heap_space` = 512 / 1024 / 2048 MiB), cleanup threshold 0.33,
  in-flight limits (204.8 / 51.2 MiB at 2 GiB; 409.6 / 102.4 at 4 GiB; 819.2 / 204.8 at 8 GiB), key-cache cap.

### 2.4 Ceiling arithmetic (2 GiB heap, the primary budget)

| Item | Bound | Source |
|---|---|---|
| D5 baseline (fresh node, one user table) | ≈ 150 MiB (estimate; stage 2 measures L0) | C6 B0 class |
| D2 requests in flight | ≤ 180 MiB on wire (client: 36 × 5 MiB; cap 204.8) × ≈ 1.1 on heap ≈ 200 MiB | §2.2 |
| D1 contract | C_contract ≈ 746 MiB | §2.2 |
| D4 transient | ≈ 50 MiB | estimate |
| D3 | 0 by contract (uncounted; measured) | — |
| **Σ contract + baseline** | **≈ 1.15 GiB < 2 GiB** | |

So convergence of contract capacities cannot exhaust a 2 GiB heap (margin ≈ 0.9 GiB, before G1's 50 % young minimum); an
OOM at 2 GiB requires U(D1) to exceed its contract by ≳ 0.9 GiB (or D3 to grow), which is the claim. Predicted D1 peak at a
barrier: switch level ≈ C/3 = 171 MiB plus η · 496 · 5 MiB = 1.2–1.7 GiB (η 0.49–0.71) → **1.4–1.9 GiB of memtable**, i.e.
2.7–3.7 × C, plus D2 + D5 ≈ 0.35 GiB → 1.75–2.25 GiB live: an OOM is expected at the upper part of the η range and GC
service loss at the lower. At 4 GiB (S = 10 MiB): 0.34 + 2.4–3.4 GiB + 0.55 ≈ 3.3–4.3 GiB (OOM likely); at 8 GiB
(S = 14 MiB): 0.68 + 3.3–4.8 + 0.95 ≈ 4.9–6.4 GiB (survival predicted; the boundary is expected between 4 and 8 GiB).

### 2.5 Workload and environment (pc75 only)

**Node check (stage 1, read-only, 2026-11-18 13:42 EST):** pc75 = `node3.jason92-326665`, 40 cores, 125 GiB RAM (124 GiB
available), `/mydata` 714 GiB free, swap 8 GiB unused, cgroup v2 (`memory` controller), JDK 11.0.33, no Java process running,
`/mydata/s4/cassandra-base` with `build/apache-cassandra-5.0.9-SNAPSHOT.jar` and the shaded driver
`build/lib/jars/cassandra-driver-core-3.12.1-shaded.jar` (contains `com/datastax/driver/core/NettyOptions.class` and the shaded
Netty `Bootstrap`). Note the node clock is shown in MST (America/Denver); all plan times below are America/New_York.

**Directories (pc75, local `/mydata` only):** `/mydata/b18/cassandra` (copy of the base), `/mydata/b18/harness/` (synced
from this folder's `harness/`), `/mydata/b18/var/lock2/` (optional I2 class dir), `/mydata/b18/run/` (one lifetime: `conf/`,
`data/`, `commitlog/`, `hints/`, `saved_caches/`, `cdc_raw/`, `logs/`, `dump/`; recreated per lifetime),
`/mydata/b18/logs/<label>/` (kept). Do not touch `/mydata/s4/`.

**Co-tenancy.** Before every lifetime: `ps -eo pid,cmd | grep '[C]assandraDaemon'` and `MemAvailable`. If another case's
node runs on pc75, record it; proceed only with ≥ 30 GiB available and free ports. The node and the client run on the same
host (loopback); the client is outside the node's scope.

**Harness to build in stage 2** (`harness/`; base: the stage-4 harness
`capacity-enforcement-exp/cassandra/stage4-runtime-verification/harness/excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous/`
(`LoadGen.java`, `mkvariant.sh`, `cluster-run.py`) and C6's
`OOM-exp/cassandra/cases/memtable_heap_space-slab-region--written-table-multiplicity/harness/` (`run.py`, `Jmx.java`,
`hprof_scan.py`, `HoldRegions.java`, `instrument-check.sh`, `plan.sh`)):

- `HotGen.java` — from `LoadGen.java`; driver 3.12.1 shaded from `build/lib/jars`, **protocol V4**, CL ONE, prepared
  `INSERT INTO ks.t (pk, ck, v) VALUES (?, ?, ?)`; one request = an **unlogged single-partition batch of R rows**, each value
  8,192 random bytes (pool of 64 distinct arrays), `ck` from a global counter (every row new). Args: `nIPs threadsPerIP R
  mode seconds statsfile stopfile [rateMiBps]`. `mode`: `hot` (pk = 1 for every request) or `perthread` (pk = global thread
  number). **One `Cluster` per source IP** 127.0.0.(11+i), bound with a `NettyOptions` subclass whose
  `afterBootstrapInitialized(Bootstrap b)` calls `b.localAddress(new InetSocketAddress("127.0.0.(11+i)", 0))`; one connection
  per host per `Cluster` (`setConnectionsPerHost(LOCAL, 1, 1)`, max requests per connection 2,048), read timeout 30 s;
  synchronous requests, one in flight per thread. On any error the thread counts it by class (`WriteTimeoutException`,
  `OverloadedException`, `TransportException`, `NoHostAvailableException`, other) and **sleeps 1 s before its next request**
  (client backoff; bounds D3). Stats line every second: epoch ms, requests ok, rows ok, errors by class. Stops at the end, at
  the stop file, or after 60 s with no successful request and no connection. Client JVM `-Xmx3g`, its own scope.
- Sizes: R = 640 rows (S = 5.0 MiB of values) at 2 GiB; R = 1,280 (10 MiB) at 4 GiB; R = 1,792 (14 MiB, < 16 MiB message and
  mutation limits) at 8 GiB — the largest multiple of 64 rows for which 36 × S ≤ heap/10 and 9 × S ≤ heap/40 (and S < 15 MiB).
  Threads: 4 IPs × 9 = 36 (≥ 32 so MutationStage stays saturated; 9 × 5 MiB = 45 MiB ≤ 51.2 MiB per IP; 180 MiB ≤ 204.8 global).
- `Sampler` — C6's `Jmx.java` `poll` mode at **500 ms** to `sampler.csv`: epoch ms; heap used; G1 Old Gen `Usage.used` and
  `CollectionUsage.used`; G1 Young/Old `CollectionCount`/`CollectionTime`; **K** = `org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize`
  (all tables, live + flushing memtables) and the same gauge for `keyspace=ks,scope=t`; `type=MemtablePool,name=BlockedOnAllocation`
  count; `type=MemtablePool,name=PendingFlushTasks`; `type=ThreadPools,path=request,scope=MutationStage,name=ActiveTasks`,
  `PendingTasks`, `CompletedTasks`; `type=DroppedMessage,scope=MUTATION_REQ,name=Dropped` count (if the scope name differs,
  list the `DroppedMessage` scopes once at `s0`); `type=ClientRequest,scope=Write,name=Timeouts` count. Fixed ObjectNames only
  (no pattern queries). A shell loop samples `RssAnon` (`/proc/<pid>/status`) and the scope's `memory.current` every 1 s.
- `hprof_scan.py` — C6's scanner, **extended**: in addition to the count/bytes of `byte[1048576]`, read `STRING` (0x01) and
  `LOAD CLASS` (0x02) records and print the top 20 classes by shallow bytes (instances by class; object arrays by element
  class; primitive arrays by type), with counts — at least `org.apache.cassandra.db.Mutation`,
  `org.apache.cassandra.db.partitions.PartitionUpdate`, `org.apache.cassandra.db.rows.BufferCell`,
  `org.apache.cassandra.utils.memory.SlabAllocator$Region`, `org.apache.cassandra.db.partitions.AtomicBTreePartition`,
  `org.apache.cassandra.db.memtable.SkipListMemtable` must be listed with their counts even if outside the top 20. Keep the
  OOM thread traces C6 added. Run with `python3 -I`. Known-answer check: C6's `HoldRegions` (40 × `byte[1048576]`) plus 1,000
  instances of a test class — counts exact, else fix the scanner (not a reading).
- `run.py life <label> <T|C|I|I2> <2G|4G|8G>` — one lifetime: fresh `run/`, conf from the base (§2.3 diff + arm setting),
  `CASSANDRA_HEAPDUMP_DIR=run/dump`, start in the scope, wait ≤ 300 s for CQL, read-backs, `s0`, schema, workload, endpoint
  handling, copy logs, stop by PID (`-p` pidfile; never `pkill -f`), `rm -rf run/`. `EXPECTED:` lines for every read-back.
  Launch from `plan.sh` with `( setsid nohup bash harness/plan.sh harness/plan-<x>.txt < /dev/null > logs/plan-<x>.out 2>&1 & )`,
  poll with bounded waits; never edit a running script.
- `analyze.py` — per lifetime the readings of §2.6 and the checks of §2.7.

**Step A — tree and checks (not readings).** Copy the tree; jar sha256; build `HotGen`, `Sampler`; scanner known-answer check;
source-binding check: during a 20 s shakedown with the node up (no user data needed beyond the schema),
`ss -tn state established '( dport = :9042 )'` must show four distinct client addresses 127.0.0.11–14. **Pre-declared
fallback** if the bind does not work: `rpc_address: 0.0.0.0` with `broadcast_rpc_address: 127.0.0.1`, two client groups
connecting to 127.0.0.1 and to pc75's LAN address 10.10.1.4 (two IPs × 18 threads, R = 320 rows = 2.5 MiB at 2 GiB so that
18 × 2.5 = 45 MiB ≤ 51.2 MiB per IP), recorded as an amendment; predictions then scale with S (§2.4 formula).

**Lifetime (each arm, labels `<heap>-<arm>-<n>`):**
1. `rm -rf /mydata/b18/run`; conf; start under `systemd-run --user --scope --unit=b18-<label> -p MemoryMax=<heap+6G> -p MemorySwapMax=0`
   with `MAX_HEAP_SIZE=<heap>`; wait for `Starting listening for CQL clients`.
2. Read back: `system_views.settings` (`memtable_allocation_type`, `memtable_heap_space`, `memtable_offheap_space`,
   `memtable_cleanup_threshold`, `memtable_flush_writers`, `concurrent_writes`, `native_transport_max_request_data_in_flight`,
   `native_transport_max_request_data_in_flight_per_ip`, `native_transport_max_message_size`, `write_request_timeout`,
   `max_mutation_size`, `commitlog_segment_size`); JVM command line (`-Xmx`, `MaxDirectMemorySize`, G1 flags,
   `HeapDumpOnOutOfMemoryError`, `HeapDumpPath`, `OnOutOfMemoryError`); scope `memory.max`, `memory.swap.max`; for I2 the
   class-path order and the marker class (§2.8).
3. `CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
   `CREATE TABLE ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))` (shipped table options);
   `nodetool setlogginglevel org.apache.cassandra.db.memtable.SkipListMemtable TRACE`.
4. `s0`: start the sampler and the RSS loop; 15 s; two `jcmd <pid> GC.class_histogram` (**L0** = total of the second); 10 s.
5. Workload (the only difference between arms): T and I and I2: `HotGen 4 9 R hot <W>`; C: `HotGen 4 9 R perthread <W>`.
   W = 300 s for T (it ends earlier at the OOM), 240 s for C, I, I2.
6. **First-trigger check** (at workload + 20 s; a failure stops the lifetime as invalid): ≥ 5 requests acknowledged;
   MutationStage `ActiveTasks` ≥ 24 in at least one sample (T, C; ≥ 3 for I); four client IPs connected.
7. **On OOM:** wait (≤ 240 s) for `Heap dump file created` in `stdout.txt` and the JVM to exit; run `hprof_scan.py` on the
   dump; keep its output; delete the `.hprof` after the scan. **Surviving lifetime:** at W, stop the client; 10 s;
   two `GC.class_histogram` (**U_end**); in the first surviving lifetime of each arm also `jcmd <pid> GC.heap_dump` and the scan;
   `nodetool flush` is **not** run; stop the node by PID.
8. Copy `system.log`, `debug.log`, `gc.log*`, `stdout.txt`, `sampler.csv`, `rss.csv`, client stats, histograms, scans,
   `memory.events` to `/mydata/b18/logs/<label>/`; check no process left; `rm -rf /mydata/b18/run`.

### 2.6 Instruments and readings (U measured independently of K)

| Reading | Source | When | Meaning |
|---|---|---|---|
| **K(t)** | sampler: `AllMemtablesOnHeapDataSize` (all tables and `ks.t`), 500 ms | continuous | the pool's counter (owns of live + flushing memtables) |
| K at flush | `Enqueuing flush of ks.t … Usage: X (P%) on-heap` and `Writing Memtable-t@…(…, X (P%) on-heap…)` lines | per flush | counter at switch and at flush start (stage-4 instrument) |
| contention | `High update contention in a/b partitions` TRACE lines | per flush | the waste tracker flipped (lock regime entered) |
| **U(D1) at OOM** | dump scan: count × 1,048,592 B of `byte[1048576]` | T | slab regions, independent of K |
| holder ranking | dump scan top classes (§2.5) | T at OOM; first C, I end dump | which class holds the heap (`[B` regions vs `Mutation`/`PartitionUpdate`/`BufferCell` of D2/D3) |
| U trajectory | `gc.log`: heap after each GC (young/mixed/full) and old-gen occupancy | continuous | live growth; post-GC peak per barrier |
| U_end | `GC.class_histogram` total and `[B` | surviving lifetimes | live heap after the workload |
| control activity | `BlockedOnAllocation`, `PendingFlushTasks`, MutationStage active/pending/completed, dropped mutations, write timeouts | 500 ms | the pool's waits, cohort size, backlog D3 |
| workload | client stats: requests/rows ok per second, errors by class | 1 s | load reached; throughput of each arm |
| first error | `system.log` first `OutOfMemoryError` (thread, stack, `JVMStabilityInspector`), `stdout.txt` (`java.lang.OutOfMemoryError: Java heap space`, `Dumping heap`, `Heap dump file created`), exit status, `memory.events` | T | V5 |
| process | `RssAnon`, scope `memory.current`, `memory.events` | 1 s / end | scope never binds |

The overshoot window lasts seconds (stage 4: `Enqueuing` → `Writing` in 0.7–3.8 s), so 500 ms sampling resolves it. Intrusive
readings (histograms, dumps) only at `s0`, at the end of surviving lifetimes and at the OOM; the mechanism is retention between
flushes, which they do not alter before the endpoint. Sampler overhead: its live heap appears in L0.

### 2.7 Predicted response, outcome rows and stopping budget

**Predictions (frozen):**
- **P1 (T, 2 GiB, S = 5 MiB):** each `H2-T-n` ends in `java.lang.OutOfMemoryError: Java heap space` with a heap dump and the
  JVM killed by the shipped `OnOutOfMemoryError`, **3/3**, within 300 s of the workload start (expected < 120 s).
- **P2 (T, K > C):** before the OOM, K(t) exceeds **1.3 × C (666 MiB)** in at least one sample or one `Writing` line, and
  exceeds C_contract (746 MiB) in at least 2 of 3 runs; at least one `High update contention in 1/1 partitions` line or (if no
  flush reached `Writing`) `BlockedOnAllocation` > 0.
- **P3 (T, U):** in the OOM dump, `byte[1048576]` count × 1 MiB ≥ **1.4 × C (717 MiB)** and ≥ 45 % of the dumped shallow
  bytes; the regions outnumber the bytes of `Mutation` + `PartitionUpdate` + `BufferCell` (D2/D3) by ≥ 2 ×;
  K at the last sample ≥ 0.6 × U(D1) (the bytes are counted: not C6's omission).
- **P4 (C, perthread, 2 GiB):** 3/3 survive 240 s; K max ≤ C + 36 × S + 64 MiB (≈ 756 MiB); no `High update contention`
  line for `ks.t`; old-gen post-GC peak ≤ 0.80 × heap; acknowledged bytes ≥ those of the T run with the same n in its first
  60 s (the control is not starved).
- **P5 (I, `concurrent_writes: 4`, 2 GiB):** 3/3 survive 240 s; K max ≤ C + 4·S + 6·S + 64 MiB (≈ 626 MiB); old-gen post-GC
  peak ≤ 0.80 × heap; acknowledged requests ≥ 1/s on average (the intervention does not stop work); report its throughput
  against T's pre-OOM throughput.
- **P6 (budget search):** 4 GiB (S = 10 MiB): T reaches OOM (1/1 first, then 3/3 if time); 8 GiB (S = 14 MiB): T survives
  (largest failing budget predicted = 4 GiB). If 4 GiB survives, the boundary is between 2 and 4 GiB.
- **Validity (every lifetime):** read-backs equal the arm and §2.3; heap as planned; the first-trigger check (§2.5 step 6)
  passes; scope `oom_kill` 0; no `ERROR` in `system.log` before the endpoint other than the OOM's and write-timeout lines.

**Outcome rows:**

| Readings | Verdict direction |
|---|---|
| P1–P5 hold (≥ 3/3 T, 3/3 C, 3/3 I) | **true positive**: `verified-OOM · deployment`, mechanism bypass (enforcement failure, D1); **mixed** if the dumps show D2/D3 bytes needed (regions alone < heap − L0 − 300 MiB) |
| T reaches OOM, but U(D1) ≤ C_contract in the dump (P3 fails) and D3 (`Mutation` objects) dominates | **retry**: the OOM is the MutationStage backlog (S2/OC-26 family), not this mechanism; better design: client without re-send on timeout |
| T reaches OOM and C or I also reach OOM | **retry**: not attributed (the contract capacities plus D2/D3 alone exhaust 2 GiB); report L0 and the dumps |
| T survives but meets the service-loss criterion (≥ 90 % of wall time in stop-the-world GC over ≥ 60 s) with K > C_contract | **retry** (`verified-gap · service-loss`); better design: larger S at a heap where the in-flight caps admit it, or n raised by writes from more client IPs |
| T survives, K > C_contract measured (bypass confirmed) but live heap stays < 0.8 × heap | **retry** (`verified-gap`, overshoot); name the measured η and the S·n needed |
| T survives with K ≤ C_contract in every barrier (no overshoot beyond the cohort's single attempts), load reached (P-validity) | **false positive** for this holder (the exemption does not multiply at defaults) |
| Validity fails | invalid lifetime; rerun once if time allows, else retry |

**Stopping budget (finite):** per lifetime: CQL within 300 s (else invalid); workload W (300 s T, 240 s others); after the client
stalls (60 s with no success) wait ≤ 120 s for an OOM, then classify from `gc.log`, take one histogram if `jcmd` answers within
60 s, kill the JVM by PID. One rerun per invalid lifetime at most. No arbitrary escalation after an OOM: the 4/8 GiB steps are
the planned budget search. **No new lifetime starts after 17:20 America/New_York on 2026-11-18; all nodes stopped by 17:35.**

**Time plan (America/New_York, 2026-11-18; stage 2 assumed to start by 14:45; hard end 18:07):**

| Window | Work | Est. |
|---|---|---|
| 14:45–15:15 | Step A: copy tree, `HotGen`/`Sampler`/scanner/`run.py`, known-answer check, source-binding shakedown | 30 min |
| 15:15–16:10 | nine 2 GiB lifetimes in the order T-1, C-1, I-1, T-2, C-2, I-2, T-3, C-3, I-3 (T ≈ 4 min: start 40 s, `s0` 40 s, OOM ≤ 2 min, 2 GiB dump + scan ≈ 1 min; C/I ≈ 6.5 min with W = 240 s) | 55 min |
| 16:10–16:50 | budget search: `H4-T-1` (≈ 6 min with a 4 GiB dump); if OOM → `H8-T-1` (≈ 9 min), then `H4-T-2`, `H4-T-3` (or the 8 GiB repeats if 8 GiB fails) | 40 min |
| 16:50–17:20 | optional, in this order: `H4-C-1`; I2 (lock patch, 1–3 lifetimes at 2 GiB); dial points at 2 GiB T with R = 160 and 320 (1.25 / 2.5 MiB) | 30 min |
| 17:20–17:35 | last lifetime ends; stop everything | 15 min |
| 17:35–18:05 | `analyze.py`, §3–§4, write-backs (candidate rows, `_INDEX.md`, retry list if retry, clue pattern if new), excerpts | 30 min |

If stage 2 starts later, keep the window ends and drop work from the bottom of this priority list: (1) the nine 2 GiB lifetimes;
(2) `H4-T-1`; (3) `H8-T-1` / the H4 repeats; (4) the optional runs. **Resource fit:** largest JVM 8 GiB heap (+ ≈ 1.5 GiB
non-heap) in a 14 GiB scope plus a 3 GiB client against 125 GiB RAM; 40 cores (36 client threads + 32 writers); disk per
lifetime: commit log ≤ 8 GiB, sstables ≤ the acknowledged bytes (C, unthrottled, at most ≈ 30–60 GiB in 240 s), one dump of
≤ 8 GiB deleted after its scan, all removed with `run/`; logs < 2 GiB in total; 714 GiB free.

### 2.8 Controls and intervention

- **Matched control (V2), C, ≥ 3 runs:** the same client (4 IPs × 9 threads, one request in flight per thread), the same batch
  size R, value size and count per request, the same heap, build and settings, `mode = perthread`: each thread writes its own
  partition, so no CAS fails and the blocking cohort holds at most one attempt per writer (the OC-257/OC-266 overshoot,
  ≤ 36 × S). Only the sharing of one partition differs. Margin: old-gen post-GC peak ≤ 0.80 × heap. The control ingests more
  real data per second than T (no wasted attempts), which only adds flush and compaction work to its side. **Pre-declared
  fallback** if C reaches OOM in its first lifetime: `C-rm` = `perthread` rate-limited (`rateMiBps`) to T's median
  acknowledged rate over its first 60 s (from `H2-T-1`), 3 runs; record both.
- **Causal intervention (V4), I, ≥ 3 runs:** `concurrent_writes: 4` (a shipped setting; bounds the multiplicity): the same hot
  workload and in-flight bytes (the other requests wait in the MutationStage queue, still charged to D2), but only 4 writers
  contend, so a barrier admits ≤ 4 · S + 6 · S of failed clones instead of ≈ 496 · S. Throughput is recorded so that an
  intervention that stops work is not taken for protection.
- **Optional diagnostic I2 (separate class dir, saved diff; not needed for the verdict):** the waste-tracker lock made
  exclusive with the 4.0 semantics of CASSANDRA-15367 — `AtomicBTreePartition` gets a field
  `final B18Lock b18Lock = new B18Lock()` (`static final class B18Lock extends java.util.concurrent.locks.ReentrantLock {}`),
  and in `Updater.addAll` the `synchronized (this)` block becomes: loop `b18Lock.tryLock(1, MILLISECONDS)`, giving up (attempt
  unlocked) only when `writeOp.isBlocking()`; unlock in `finally`. Built like the stage-4 `mkvariant.sh` (javac of the patched
  file against `build/classes/main` and `build/lib/jars/*` into `/mydata/b18/var/lock2/`, put first on `CLASSPATH` through
  `CASSANDRA_INCLUDE`); read-back: `AtomicBTreePartition$B18Lock` instances in the `s0` histogram. Prediction (stated, not a
  verdict condition): waste outside barriers drops, but the blocking cohort's waiters still retry unlocked, so the endpoint may
  persist; the result says whether the per-`Updater` monitor (a defect) or the exemption's unlocked retries (the 15367 design)
  carries the overshoot.
- **Not used (and why):** `unslabbed_heap_buffers` (changes holder and counter at once, §2.1); raising timeouts or Byteman
  delays (would make the result diagnostic); 16 MiB mutations at 2 GiB (the default in-flight limits do not admit 32 of them).

**Cleanup and leftovers.** Stop every JVM this case started (by PID); `rm -rf /mydata/b18/run`; delete scanned `.hprof` files;
keep `/mydata/b18/logs/`, `/mydata/b18/cassandra`, `/mydata/b18/var/` and say so in §3. Commit small excerpts (client stats
heads/tails, `sampler.csv` around each barrier and the OOM, `Enqueuing`/`Writing`/TRACE lines, scan outputs, histogram heads,
first-error lines, `analyze.py` output) to `logs/` in this folder.

`sha256 of §1–§2 at freeze: 50cb24f7c97e466232f2c74768adbafc0e40a2c670a606cd83e700a45b4520c6` (computed as `awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-18) · amendments after the freeze: none to §1–§2; stage-2 amendments A1–A4 are in §3.2.

## 3. Runs (stage 2)

### 3.1 Environment and checks (2026-11-18, before readings)

- **Freeze hash:** recomputed with the stated `awk … | sha256sum` at stage-2 start (13:54 America/New_York):
  `50cb24f7c97e466232f2c74768adbafc0e40a2c670a606cd83e700a45b4520c6` = the frozen value.
- **Node:** pc75 (`node3.jason92-326665…cloudlab.umass.edu`), x86_64, 40 cores, 125 GiB RAM, Ubuntu 22.04.2, kernel
  5.15.0-203-generic, cgroup v2, swap 8 GiB present (each node scope `MemorySwapMax=0`), OpenJDK 11.0.33. `pgrep -af CassandraDaemon`
  empty before the first lifetime and before every lifetime (`cotenancy` line in each `session.log`: no daemon, ≥ 124 GiB available).
- **Tree:** `cp -a /mydata/s4/cassandra-base /mydata/s4/b18-w4/cassandra`; jar `apache-cassandra-5.0.9-SNAPSHOT.jar` sha256
  `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`; no `ant` run. `/mydata/s4/cassandra-base` untouched.
- **Harness:** [`harness/`](harness/) (README there), synced to `/mydata/s4/b18-w4/harness/`. Scanner known-answer check
  (`instrument-check.sh`): 40 regions, 40 near-regions, 1,000 `HoldRegions$Marker` — **ok**.
- **Source-binding shakedown** (`run.py shakedown`, 2 GiB, 20 s of `perthread` R = 64; not a reading): `ss` showed the client
  sockets from **127.0.0.11, .12, .13, .14** (2 per IP: control + pool connection); the pre-declared LAN fallback was not needed.
- **Resolved values, read back every lifetime** (`system_views.settings`, JVM command line, scope files): `heap_buffers`;
  `memtable_heap_space` 512 / 1024 / 2048 MiB at 2 / 4 / 8 GiB; `memtable_offheap_space` = the same; cleanup threshold 0.33333334;
  flush writers 2; `concurrent_writes` 32 (4 in arm I); counter writes 32; in-flight 214,748,364 B / per IP 53,687,091 B at 2 GiB
  (858,993,459 / 214,748,364 B at 8 GiB); message size 16 MiB; `max_mutation_size` 16384 KiB; segment 32 MiB; `commitlog_total_space`
  8192 MiB; `write_request_timeout` 2000 ms; `native_transport_timeout` 12 s; `throw_on_overload` false; hints on; key cache 100 MiB;
  `batch_size_fail_threshold` 50 KiB. JVM: `-Xms=-Xmx` = heap, G1 with `G1HeapRegionSize=16m`, `G1NewSizePercent=50`,
  `MaxGCPauseMillis=300`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError=kill -9 %p`, **`MaxDirectMemorySize=15872M`**
  (resolved by `cassandra-env.sh` on pc75; §2.3 expected 7,936 MiB — recorded only, not the budget). Scope `memory.max` = heap + 6 GiB,
  `memory.swap.max` 0. Every lifetime's `EXPECTED` read-backs matched. **L0** (live heap after schema, `GC.class_histogram`) = **65 MiB** in every arm.

### 3.2 Amendments after the freeze (dated 2026-11-18; none changes an arm's workload, a setting or a budget)

- **A1 (13:56, before readings) — directory.** Everything under `/mydata/s4/b18-w4` instead of `/mydata/b18` (session instruction);
  paths only.
- **A2 (14:08, after H2-T-1/H2-C-1) — the K instrument.** In 5.0.9 `AllMemtablesOnHeapDataSize` sums the **current** memtable only
  (`TableMetrics.java:876-883`), not "live + flushing" as §2.5/§2.6 assumed; and in every T lifetime the JMX sampler stopped answering
  within 3–11 s of the workload start (full GCs). So the 500 ms K series does not cover the barrier windows. **K is read from the
  memtable's own counter in the `Enqueuing flush of ks.t … Usage` (at switch) and `Writing Memtable-t@…(… on-heap (P%))` (after the
  barrier) lines**, which §2.6 already lists. No pool-total gauge exists in 5.0.9; the pool total is ≥ the Writing line's memtable.
- **A3 (14:13, after H2-C-1 reached OOM, before any Crm reading) — pre-declared fallback C-rm invoked** (§2.8): `perthread`,
  rate-limited to T's acknowledged rate. H2-T-1 died 17 s into its workload, so "its first 60 s" is its whole pre-OOM window: 32 requests
  × 5 MiB in 17 s = **9.4 MiB/s** (mean, not median: the per-second median is 0). The first-trigger check's `ActiveTasks ≥ 24` cannot
  hold at that rate (≈ 1.9 requests/s); for Crm it requires ≥ 1 active writer (plus ≥ 5 acks and 4 client IPs).
- **A4 (14:33) — I2 build.** The optional lock patch built exactly as §2.8 describes (`harness/mklock2.sh`, `lock2_patch.py`; diff saved
  on pc75 `logs/lock2.diff` and in [`logs/lock2.diff`](logs/lock2.diff)); class dir first on the class path (read back), marker class
  `AtomicBTreePartition$B18Lock` in the `s0` histogram (44 instances).
- **Note (no change):** the scope's `memory.events` `max` counter is non-zero in C, I and 8 GiB lifetimes (page cache of the flush/commit
  log writes reaching `memory.max`); `oom_kill` = 0 and `oom` = 0 in every lifetime, RssAnon ≤ 3.3 GB (2 GiB heap) / 10.5 GB (8 GiB):
  the scope never killed anything. Dumps written at OOM were scanned and deleted.

### 3.3 Lifetimes and readings

Workload: 4 source IPs × 9 threads, one unlogged single-partition batch in flight per thread, R rows × 8,192 B (S = R × 8 KiB),
1 s client sleep after an error. "Writing (K)" = the flushing memtable's own counter after the barrier (`% of memtable_heap_space`);
"regions (U)" = live `byte[1048576]` in the OOM dump (MiB, × C); "other `[B`" = the rest of the byte arrays (request frames of
decoded mutations, D2/D3); "Mut." = `Mutation` objects in the dump. C = `memtable_heap_space`. All lifetimes: first-trigger check
passed (4 client IPs; MutationStage active 32 in T/C, 4 in I, 1 in Crm), read-backs as §3.1, scope `oom_kill` 0.

| Lifetime | Arm, heap, S | Endpoint: OOM at s (dump start, after workload start) | acked req (MiB) | Enqueuing → Writing (K) | regions U (× C, share of dump) | other `[B` MiB / Mut. | client timeouts |
|---|---|---|---|---|---|---|---|
| H2-T-1 | T, 2 GiB, 5 MiB | **heap OOM** at 7 | 32 (160) | 184 MiB (36 %) → **1.607 GiB (321 %)**, 17,920 ops, 140.8 MiB serialized; `High update contention in 1/1` | **1,693 (3.31 ×, 85 %)** | 193 / 35 | 13 |
| H2-T-2 | T, 2 GiB, 5 MiB | **heap OOM** at 9 | 33 (165) | 178 MiB (35 %) → **1.910 GiB (382 %)**, 19,840 ops, 155.9 MiB; contention 1/1 | **1,659 (3.24 ×, 83 %)** | 241 / 44 | 39 |
| H2-T-3 | T, 2 GiB, 5 MiB | **heap OOM** at 10 | 22 (110) | 205 MiB (40 %) → none (OOM before the barrier completed) | **1,717 (3.35 ×, 87 %)** | 176 / 33 | 30 |
| H2-C-1 | C, 2 GiB, 5 MiB | heap OOM at 34 | 241 (1,205) | 10 flushes, Writing ≤ 269 MiB (53 %) | 1,482 (2.89 ×, 75 %) | 392 / 76 | 282 |
| H2-C-2 | C, 2 GiB, 5 MiB | heap OOM at 36 | 256 (1,280) | 12 flushes, ≤ 269 MiB (52 %) | 1,634 (3.19 ×, 83 %) | 213 / 40 | 302 |
| H2-C-3 | C, 2 GiB, 5 MiB | heap OOM at 43 | 280 (1,400) | 14 flushes, ≤ 300 MiB (59 %) | 1,579 (3.08 ×, 80 %) | 282 / 53 | 360 |
| H2-I-1 | I (`concurrent_writes: 4`), 2 GiB, 5 MiB | heap OOM at 70 | 272 (1,360) | 32 flushes, ≤ 209 MiB (41 %), no contention line | 915 (1.79 ×, 45 %) | **966 / 185** (MutationStage pending ≤ 177) | 690 |
| H2-I-2 | I, 2 GiB, 5 MiB | survived 240 s | 508 (2,540) | ≤ 236 MiB (46 %), no contention line | U_end 570 MiB (histogram) | — (pending ≤ 213) | 2,616 |
| H2-I-3 | I, 2 GiB, 5 MiB | heap OOM at 79 | 298 (1,490) | ≤ 342 MiB (67 %), no contention line | 644 (1.26 ×, 32 %) | **1,242 / 242** (pending ≤ 221) | 779 |
| H2-Crm-1 | Crm (perthread, 9.4 MiB/s), 2 GiB, 5 MiB | survived 240 s | 488 (2,440) | ≤ 171 MiB (33 %), no contention | end dump 140 regions; U_end 207 MiB | — | 0 |
| H2-Crm-2 | Crm, 2 GiB | survived 240 s | 488 (2,440) | ≤ 171 MiB (33 %) | U_end 207 MiB | — | 0 |
| H2-Crm-3 | Crm, 2 GiB | survived 240 s | 488 (2,440) | ≤ 171 MiB (33 %) | U_end 207 MiB | — | 0 |
| H4-T-1 | T, 4 GiB, 10 MiB | **heap OOM** at 14 | 32 (320) | 361 MiB (35 %) → **3.400 GiB (340 %)**, 38,400 ops, 301.6 MiB | **3,274 (3.20 ×, 82 %)** | 613 / 56 | 37 |
| H4-T-2 | T, 4 GiB, 10 MiB | **heap OOM** at 10 | 32 (320) | 385 MiB (38 %) → **2.157 GiB (216 %)**, 241.3 MiB | **3,386 (3.31 ×, 85 %)** | 482 / 44 | 34 |
| H4-T-3 | T, 4 GiB, 10 MiB | **heap OOM** at 12 | 33 (330) | 388 MiB (38 %) → **3.645 GiB (364 %)**, 311.7 MiB | **3,269 (3.19 ×, 82 %)** | 633 / 62 | 44 |
| H8-T-1 | T, 8 GiB, 14 MiB | **heap OOM** at 22 | 38 (532) | 691 MiB (34 %) → **5.500 GiB (275 %)**, 57,344 ops, 450.5 MiB | **6,758 (3.30 ×, 84 %)** | 1,137 / 79 | 86 |
| H8-T-2 | T, 8 GiB, 14 MiB | **heap OOM** at 27 | 38 (532) | 710 MiB (35 %) → **5.199 GiB (260 %)**, 464.5 MiB | **6,701 (3.27 ×, 83 %)** | 1,220 / 84 | 92 |
| H8-T-3 | T, 8 GiB, 14 MiB | **heap OOM** at 34 | 38 (532) | 702 MiB (34 %) → **4.405 GiB (220 %)**, 422.3 MiB | **6,561 (3.20 ×, 81 %)** | 1,346 / 93 | 102 |
| H4-C-1 | C, 4 GiB, 10 MiB (optional) | heap OOM at 37 | 126 (1,260) | ≤ 662 MiB (65 %), no contention | 1,861 (1.82 ×, 46 %) | **2,017 / 199** (pending ≤ 166) | 354 |
| H2-I2-1 | I2 (lock patch), 2 GiB, 5 MiB (optional) | **heap OOM** at 8 | 25 (125) | 190 MiB (37 %) → none (OOM before the barrier completed) | **1,704 (3.33 ×, 87 %)** | 186 / 33 | 19 |
| H2-I2-2 | I2, 2 GiB, 5 MiB (optional) | **heap OOM** at 8 | 31 (155) | 193 MiB (38 %) → **1.773 GiB (355 %)**, 19,200 ops, 150.8 MiB; contention 1/1 | **1,664 (3.25 ×, 84 %)** | — / 43 | 33 |
| H2-I2-3 | I2, 2 GiB, 5 MiB (optional) | **heap OOM** at 9 | 31 (155) | 189 MiB (37 %) → **1.690 GiB (338 %)**, 18,560 ops, 145.8 MiB; contention 1/1 | **1,707 (3.33 ×, 86 %)** | — / 35 | 15 |
| H2-TR160-1 | T, 2 GiB, **1.25 MiB** (R = 160, optional dial) | **heap OOM** at 7 | 158 (198) | three flushes: Writing **112 %, 115 %, 125 %** (50–62 MiB of rows each); contention 1/1 | **1,828 (3.57 ×, 94 %)** | — / 27 | **0** |
| H2-TR320-1 | T, 2 GiB, **2.5 MiB** (R = 320, optional dial) | **heap OOM** at 6 | 76 (190) | two flushes: Writing **174 %, 215 %** (80–98 MiB of rows); contention 1/1 | **1,774 (3.46 ×, 91 %)** | — / 35 | **0** |

**OOM evidence (V5), every OOM lifetime:** `stdout.txt` has `java.lang.OutOfMemoryError: Java heap space`, `Dumping heap to …`,
`Heap dump file created [2.09–8.51 GB]` and `Executing /bin/sh -c "kill -9 <pid>"` (the shipped `OnOutOfMemoryError`); `system.log`
has no OOM line (the JVM is killed right after the dump). `gc.log` ends in back-to-back `Pause Full (G1 Evacuation Pause)` at the heap
size (e.g. H2-T-1: 27 full GCs, last `1974M->1954M(2048M)`). Thread stacks in the dumps: H2-T-1's thrower is a
`ScheduledThreadPoolExecutor` worker (`OutOfMemoryError.<init>` ← `addConditionWaiter`), and the other stacks are MutationStage writers
inside `BTreeRow.clone` → `ByteBufferCloner.clone` → `SlabAllocator.allocate` → `SubAllocator.allocate`/`acquired` and
`SlabAllocator$Region.allocate`; H2-T-2/T-3 show writers parked in `SubAllocator.allocate:195` (waiting for room) next to writers cloning;
H8-T-1 shows a writer in `SubAllocator.allocated:213` ← `allocate:182`, i.e. **the `isBlocking` branch that charges without a limit**.

**Derived numbers.** T: the flushing memtable's own counter went from 35–40 % of the pool at the switch to **216–382 %** after the barrier,
1–3 s later, while it held only 141–465 MiB of rows (17,920–59,136 ops = 28–33 batches): **88–92 % of the counted bytes are clones that
are not in the partition** (failed CAS attempts). Failed 5 MiB clones per barrier: H2-T-1 (1,646 − 141)/5 = 301, H2-T-2 360 → η = 301/496
= **0.61** and **0.73** (§2.1 predicted 0.49–0.71). U(D1) at the OOM is 3.19–3.35 × C in all nine T lifetimes, at 2, 4 and 8 GiB; it is
81–87 % of the dumped bytes; the request frames (other `[B`) are 176–241 MiB at 2 GiB. K (Writing) / U (dump) = 0.97 (T-1), 1.15 (T-2),
0.66 (H4-T-2) – 1.11 (H4-T-3), 0.67–0.83 (8 GiB): **the bytes are counted** (not C6's omission). Time to OOM (heap-dump start): T 7–10 s at 2 GiB with
≤ 165 MiB acknowledged (10–14 s at 4 GiB, 22–34 s at 8 GiB); C 34–43 s with 1.2–1.4 GiB acknowledged; I 70–79 s (2/3).

**What the C and I lifetimes show.** All three unthrottled C lifetimes also died, with regions at 2.9–3.2 × C while each flushing memtable's
counter stayed ≤ 59 % of the pool; with 282–360 client timeouts each, the client's re-send after a timeout put a second and third writer on
the same `perthread` partition (the first still blocked in `SubAllocator.allocate`; `BlockedOnAllocation` +135…+196), but no partition
reached the 10 MiB contention flag. The pool total was not measurable (A2), so whether C's regions were counted (pool > C through the
same exemption) or uncounted is **not attributed**. In I the 4 writers cannot keep up (MutationStage pending ≤ 221, 560–2,470 dropped
mutations): its two OOMs are dominated by the **MutationStage backlog of timed-out mutations (D3: 185–242 decoded 5 MiB mutations,
0.9–1.2 GiB of request frames)**, with regions at only 1.26–1.79 × C and every Writing line ≤ 67 %. So `concurrent_writes: 4` removed the
claimed holder's growth (K never above C) but not the endpoint. At the matched acknowledged rate (Crm, 9.4 MiB/s, no timeouts), the
uncontended control is far from OOM (post-GC old gen 207 MiB, 10 % of the heap, 3/3).

**Optional runs (§2.7 list, run after the planned ones).** I2 (exclusive lock that blocking writers may skip): 3/3 OOM at 8–9 s with the
same overshoot (Writing 338–355 %) — the per-`Updater` monitor is not what carries it; once the flush marks the cohort blocking, the
writers retry unlocked and unlimited. Dial points at 2 GiB: R = 160 (S = 1.25 MiB) and R = 320 (2.5 MiB) T both died within 6–7 s with
**no client timeout at all**, Writing 112–125 % and 174–215 %, regions 3.46–3.57 × C (91–94 % of the dump): the hot-partition overshoot
needs neither large batches nor the timeout/re-send backlog that drove C and I. (C and I were not run at these sizes: not in the frozen
design.)

### 3.4 Leftovers and logs

- **Processes:** none left (each lifetime ends with `daemons_left: none`; plan runners exited; `pgrep -af CassandraDaemon` empty at the end).
- **On pc75:** `/mydata/s4/b18-w4/` kept: `cassandra/` (tree copy, ~419 MB), `harness/`, `cls/`, `var/lock2/` (I2 classes), `logs/<label>/`
  (full logs of every lifetime: `system.log`, `debug.log`, `gc.log*`, `stdout.txt`, `sampler.csv`, `rss.csv`, `hotgen.csv`, histograms,
  scans; 356 MB in all), `logs/plan-*.out`. `run/` removed after every lifetime; all `.hprof` files deleted after their scan.
  `/mydata/s4/cassandra-base` untouched.
- **In this folder:** [`logs/`](logs/): per lifetime `summary.json`, `analyze.jsonl` (all lifetimes), `flush-lines.txt`, `oom-lines.txt`,
  `scan-*.json` (incl. class histograms and dump stacks), client/sampler excerpts, histogram heads, `memory.events`, `yaml.diff`,
  `jvm-flags.txt`; `lock2.diff`.

## 4. Conclusion (stage 2)

**Verdict: retry.** Protocol status (detail): **`candidate`** — V1, V3 and V5–V7 are met (see the table), V2 only through the
pre-declared fallback control, V4 not met; so neither `verified-OOM` nor `verified-gap`. The endpoint is a heap OOM in every T lifetime and
the bypass overshoot (U > C, K > C) is reproduced in every one where K was read, but the matched control at the designed load and the
intervention also reached OOM. Mechanism label from the readings:
**bypass, enforcement failure** (U > C and K > C in D1: a single memtable counted at 2.2–3.8 × `memtable_heap_space`, U ≈ K);
interpretation: an intentional exception (the blocking-cohort exemption, CASSANDRA-15367) multiplied by a suspected defect (the
pessimistic lock on the per-call `Updater` excludes no one). The optional I2 patch (an exclusive per-partition lock that blocking-cohort
writers may skip, the 4.0 semantics) changed nothing (3/3 OOM at 8–9 s, Writing 338–355 %): the overshoot is carried by the
blocking cohort's unlocked, unlimited retries (the CASSANDRA-15367 design), not only by the per-`Updater` monitor.

**Reason.** On a stock 5.0.9 node with every capacity at its default, 36 clients writing 5 MiB batches into one partition killed a 2 GiB
heap in 3/3 runs 7–10 s after the workload started (and 4 GiB in 3/3 with 10 MiB batches, 8 GiB in 3/3 with 14 MiB batches; the largest tested budget still
fails, so the boundary is above 8 GiB). Each time a flush switched the memtable at 35–40 % of the pool, the old memtable's own counter rose to
**216–382 % of the whole pool** within 1–3 s while it held only 28–33 batches of rows: ≈ 300–360 failed 5 MiB clones per barrier
(η 0.61/0.73), admitted through `SubAllocator.allocate`'s `isBlocking` branch; the OOM dumps hold **3.19–3.35 × C** in live 1 MiB slab
regions (81–87 % of the heap), with K/U 0.66–1.15. That confirms the bypass (U > C, K > C). It is not attributed as the cause of the OOM by
the frozen design: the matched uncontended control C (same 36 × 5 MiB in flight) also died 3/3 at 2 GiB (34–43 s, regions 2.9–3.2 × C with
every flushing memtable ≤ 59 %, origin not attributed) and at 4 GiB (1/1, D3-dominated); the intervention I (`concurrent_writes: 4`)
bounded the memtable counter (≤ 67 %) but died 2/3 from a different holder, the MutationStage backlog of timed-out mutations (0.9–1.2 GiB of
request frames). Only the pre-declared rate-limited control Crm (9.4 MiB/s, T's acknowledged rate) survived 3/3 (old gen 207 MiB). The
outcome table (§2.7) maps "T reaches OOM and C or I also reach OOM" to **retry**.

**V1–V7 at the fixed condition (2 GiB, S = 5 MiB, 36 writers, defaults):**

| | Met? | Evidence |
|---|---|---|
| V1 Repetition | yes | H2-T-1..3: 3/3 heap OOM (7–10 s); also H4-T 3/3, H8-T 3/3 |
| V2 Matched control | **only via the fallback** | C (same in-flight load): 3/3 OOM. Crm (pre-declared fallback, rate-matched): 3/3 survive, old gen 207 MiB, K ≤ 33 % |
| V3 Measurement | yes | U from the dump scan (`byte[1048576]`), K from the memtable's counter (Enqueuing/Writing lines); the 500 ms JMX K series is not usable (A2) |
| V4 Intervention | **no** | I: 2/3 OOM (holder shifted to D3), 1/3 survived with the old gen at the heap size; I2 (optional diagnostic lock patch): 3/3 OOM at 8–9 s, Writing 338–355 % — not an intervention that removes the endpoint either |
| V5 Initiating failure | yes | `stdout.txt` OOM + shipped dump per T run; writer stacks in `SlabAllocator`/`SubAllocator` (H8-T-1 in `allocated` via the `isBlocking` branch); dump holder 81–87 % regions |
| V6 Default constraints | yes | every memtable, native-transport, commit-log and concurrency setting at its shipped default, read back (§3.1) |
| V7 Acceptable budget | yes | 2 GiB heap (ideal), also 4 and 8 GiB; `MaxDirectMemorySize` 15,872 M resolved; scope a non-binding guard (`oom_kill` 0) |

**Predictions:** P1 held (3/3, OOM 7–10 s after the workload start). P2 held for T-1, T-2 (321 %, 382 % > 130 %; both > C_contract 746 MiB; contention 1/1 lines);
T-3 has no Writing line and no usable sampler reading. P3 held (regions 1,659–1,717 MiB ≥ 717, 83–87 %; other `[B` ≤ 241 MiB, so ≥ 7 ×;
K/U ≥ 0.6 where measured). **P4 failed** (C 3/3 OOM; fallback Crm met P4's criteria 3/3). **P5 failed** (I 2/3 OOM). **P6 failed in the
direction of the claim** (8 GiB also OOMs; predicted survival).

**Limits of attribution.** (1) The C OOMs: at the designed in-flight load the node also fails without a hot partition; the client's re-send
after a 2 s timeout creates overlapping writers per partition and a MutationStage backlog, and the pool total could not be measured, so it
is open whether C's 3 × C of regions is the same exemption at lower multiplicity or another gap. (2) The I arm changes the backlog as well as
the cohort size. (3) The K series by JMX is unusable in T (sampler stalled); K rests on the per-memtable log lines.

**Overlap with C6** (verified, slab regions × written tables). Same holder type (live `byte[1048576]` slab regions of `heap_buffers`
memtables), same pool, same scanner. Different failure of the control: in C6 the regions are **uncounted** (K ≤ 82 MiB while U = 2.1 × C,
many tables, the pool never blocks); in B18's T arm the bytes are **counted** (one table, one partition; the flushing memtable's own counter
at 2.2–3.8 × C, K/U 0.66–1.15) and the limit check admits them through the blocking-cohort exemption. B18 does not need many tables, and
C6's result does not predict it. The unexplained C-arm regions (≈ 3 × C with each flushing memtable ≤ 59 %) are one table too, so C6's
per-table region is not their source either.

**What a better design should change (retry row).** Keep T as is (it reproduces in seconds at 2/4/8 GiB). Make the arms separable at the
same load: (a) a client that does **not** re-send after a timeout while its earlier request may still be applied (e.g. one request per
thread for the whole run with a long client timeout, or a 30 s back-off), so that C and I cannot build the D3 backlog; (b) an intervention
that bounds the contending cohort without creating a backlog — `concurrent_writes: 4` at the small S of (d), where the 4 writers keep up,
or a diagnostic lock that also holds for blocking-cohort writers (I2 lets them retry unlocked and still dies; a lock they cannot skip
re-opens the CASSANDRA-15367 deadlock risk, so bound its wait); (c) a pool-total reading — 5.0.9 has none (`AllMemtablesOnHeapDataSize`
covers only the current memtable): a separate diagnostic build that logs `MemtablePool.onHeap` allocated/reclaiming once a second (diff
saved), so that C's region growth can be classified; (d) use the small batches of the dial runs: at **S = 1.25 MiB (R = 160)** T still died at 7 s at 2 GiB with **zero client
timeouts** (Writing 112–125 %, regions 3.57 × C, 94 % of the heap), so C and I at that S should not build a timeout/re-send backlog —
run T, C, I there, ≥ 3 each; (e) the budget search above 8 GiB (e.g. 15,872 MiB, what `cassandra-env.sh` resolves on pc75) with
S = 14 MiB, and S = 1.25 MiB at 4/8 GiB.
