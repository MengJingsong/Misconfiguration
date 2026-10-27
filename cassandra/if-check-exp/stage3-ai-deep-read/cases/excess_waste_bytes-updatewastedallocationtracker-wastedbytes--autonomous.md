# EXCESS_WASTE_BYTES — verification solution  <!-- file: cases/excess_waste_bytes-updatewastedallocationtracker-wastedbytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:269`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L269) (`updateWastedAllocationTracker()`; constant compared at [`:272`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L272)) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`. EXCESS_WASTE_BYTES bounds how much garbage a single partition's lock-free CAS retries may produce before the partition switches to `synchronized`; the garbage is never added to the memtable's accounted heap, and the constant is not a memory or disk cap. |
| Ground | The quantity compared (`wastedBytes`) is the `heapSize` of one failed merge attempt (`AtomicBTreePartition.java:168`, reset each attempt at `:183`). Only the successful attempt's `heapSize` is reported to the allocator (`BTreePartitionUpdater.java:180-183`, called from the `finally` at `AtomicBTreePartition.java:174`), so wasted allocation is short-lived young-generation garbage outside the memtable pool that `memtable_heap_space` bounds. The switch to locking limits CPU and GC churn, not retained memory or disk. |

## A. Constraint trace

**A1. The constraint.** `EXCESS_WASTE_BYTES`, kind: constant (`private static final long`), first declared at [`AtomicBTreePartition.java:63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L63) as `10 * 1024 * 1024L` (10 MiB, a hard-coded literal, not derived). Unit: bytes. Companion constants: `ALLOCATION_GRANULARITY_BYTES = 1024` (`:61`), `EXCESS_WASTE_OFFSET = (int)(EXCESS_WASTE_BYTES / 1024) = 10240` units (`:64`), `CLOCK_SHIFT = 17` (`:66`), reserved tracker values `TRACKER_NEVER_WASTED = 0` and `TRACKER_PESSIMISTIC_LOCKING = Integer.MAX_VALUE` (`:57-58`). The per-partition state is `private volatile int wasteTracker` (`:80`). It is used at `:272` (early check) and, through `EXCESS_WASTE_OFFSET`, at `:283-284`. The earlier trace is confirmed on all of these lines. Settable: no yaml key, no `-D` property, no JMX (grep of the tree shows the only uses are in this file); changing it means editing the source and rebuilding, which is a restart by definition. Correction to the earlier text: the "7.45 MB/s" allowance comes from the code comment at `:72-75`; the comment at `:67` says 132 us granularity (1 unit = 2^17 ns = 131.07 us), i.e. 1 KiB per 131 us = about 7.63 KiB/ms. Both are comment-level figures.

**A2. What it caps.** Not a memory or disk resource that persists. It caps the cumulative wasted on-heap allocation (garbage from merge attempts whose compare-and-set failed) that a single `AtomicBTreePartition` may incur, above a free allowance of about 1 KiB per 131 us, before further writers to that partition serialize on a lock. The quantity compared to `EXCESS_WASTE_BYTES` is `wastedBytes`, the `addWaste` argument passed from `shouldLock(heapSize, writeOp)` (`:168`, `:239-241`); `heapSize` is the unshared on-heap size computed by `BTreePartitionUpdater` for the failed attempt (`BTreePartitionUpdater.java:46`, accumulators at `:132,155,164,172,177`).

**A3. Mechanism.**
1. `Updater.addAll` (`AtomicBTreePartition.java:143-175`) calls `shouldLock(writeOp)` (`:150`), which is true only if `wasteTracker == TRACKER_PESSIMISTIC_LOCKING` (`:231-236, 258-261`) and the caller's `OpOrder.Group` is the oldest live group or becomes so after one `Thread.yield()` (`:247-256`).
2. If locked, it does `synchronized (this)` around `tryUpdateData` (`:155-160`). Otherwise it calls `tryUpdateData` (`:162-163`), which zeroes `dataSize`/`heapSize` (`:182-183`), builds a merged partition (`:184`) and does `refUpdater.compareAndSet` (`:185`).
3. If the CAS fails, `shouldLock(heapSize, writeOp)` (`:168`) calls `updateWastedAllocationTracker(heapSize)` (`:239-241`) and loops again.
4. `updateWastedAllocationTracker` (`:269-296`): if `wastedBytes >= EXCESS_WASTE_BYTES` (negation of [`:272`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L272)), skip accounting and go straight to `wasteTrackerUpdater.set(..., TRACKER_PESSIMISTIC_LOCKING)` (`:293`) and return true (`:295`). Otherwise round up to 1 KiB units (`:275`), read `time = (int)(nanoTime() >>> 17)` (`:281`), compute `delta = oldTracker - time` (`:282`), reset `delta` to `-10240` if the tracker is NEVER_WASTED, already in the past (`delta >= 0`), or older than the window (`:283-284`), add the units (`:285`). If `delta >= 0` the allowance is exhausted: break to the lock setter (`:286-287`). Else CAS `time + delta` into the tracker (`:288`, with `avoidReservedValues`, `:298-303`) and return false.
5. Once PESSIMISTIC, the state is permanent for that partition object (no code resets it; the loop condition `:278` and the setter `:293` only move toward it). The partition object lives as long as its memtable.
6. Boundary arithmetic: a first failed attempt of `w` bytes with the tracker at NEVER_WASTED gives `delta = -10240 + ceil(w/1024)`. It locks when `ceil(w/1024) >= 10240`, i.e. `w >= 10 MiB - 1023` bytes, even though the early check at `:272` only triggers at `w >= 10 MiB`. It does not lock when `w <= 10 MiB - 1024`.
7. Bypasses/overshoot: the cap is soft in two ways. A thread that is not the oldest live write group (`:247-256`) gets `false` back from `shouldLock` even though the tracker is now PESSIMISTIC, so it keeps retrying lock-free until `useLock()`-based `shouldLock(writeOp)` is consulted by a later call. `addAll` only evaluates `shouldLock(writeOp)` once at entry (`:150`), and after a failed CAS only reevaluates through `:168`. The first-attempt cost is also unbounded: a single merge can allocate arbitrarily much before the first CAS fails.

**A4. Other consumers.** The same heap is used by everything accounted through the memtable pool (`memtable_heap_space`, `AbstractAllocatorMemtable.java:81`; pool objects at `:96-102`), whose `adjust` is fed by `reportAllocatedMemory` (`BTreePartitionUpdater.java:180-183`), and by unaccounted consumers: request/response buffers, key and row caches, bloom-filter and index summaries, compaction and repair structures, and the young-generation garbage from the wasted attempts themselves, which no Cassandra setting tracks.

**A5. Evidence beyond the source.** Code comments at `AtomicBTreePartition.java:55-80`. Test `test/unit/org/apache/cassandra/db/partitions/AtomicBTreePartitionMemtableAccountingTest.java` (accounting of owned size after `addAll`; does not exercise contention) and JMH `test/microbench/org/apache/cassandra/test/microbench/btree/AtomicBTreePartitionUpdateBench.java` (multi-threaded updates to shared partitions, 4 threads, `:102`). The origin of the mechanism is CASSANDRA-7546 (public issue tracker, "AtomicSortedColumns.addAllWithSizeDelta has a spin loop that allocates memory"); cited from memory of the public tracker, not re-read here. Otherwise none.

## B. Verification solution

**B1. Claim under test.** Changing the waste threshold (`EXCESS_WASTE_BYTES`) does not change the memory the memtable accounts for or the disk it eventually flushes; it changes only whether contended writers to one partition retry lock-free (producing unaccounted garbage) or serialize on a monitor. Equivalently: retained heap and flushed bytes are flat across threshold values while the positive control (`memtable_heap_space`) moves them. The claim would be wrong if accounted memtable size, flush count, or flushed bytes follow the threshold.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c509/`; never build in the shared tree). `cd $WORK/c509 && ant jar` (and `ant build-test` for test classes). Add a new test class `test/unit/org/apache/cassandra/db/partitions/WasteTrackerProbeTest.java` in package `org.apache.cassandra.db.partitions`. Run with `ant testsome -Dtest.name=org.apache.cassandra.db.partitions.WasteTrackerProbeTest`. JVM options: the stock test options plus `-Xmx1g`. The private method and fields are reached by reflection with `setAccessible(true)` (`updateWastedAllocationTracker(long)` at `:269`, `wasteTracker` at `:80`); `useLock()` is public (`:258`). Model the setup on `AtomicBTreePartitionMemtableAccountingTest.java:119-135, 296-297` (daemonInitialization, TableMetadata, `createMemtableAllocatorPoolInternal`).

**B2b. Knobs.** The constant is `static final` and inlined, so it cannot be varied at run time. Two knobs: (1) the `wastedBytes` argument (the operand), swept relative to the constant; (2) a second build of the copied tree with the literal at `:63` edited to `1L << 20` (1 MiB) for a "threshold moved" arm (`EXCESS_WASTE_OFFSET` follows at `:64`). Argument values: `10 MiB - 2048`, `10 MiB - 1024`, `10 MiB - 1023`, `10 MiB - 1`, `10 MiB`, `10 MiB + 1`, and `1`, `1024`.

**B2c. Workload.** Direct calls: for each value, a fresh `AtomicBTreePartition` (tracker = 0), invoke `updateWastedAllocationTracker(v)` once and record the return and `useLock()`. Burst series: on a fresh partition call with `w = 1024` repeatedly in a tight loop; 10240 calls within a few ms are enough to exhaust the 10240-unit window if the clock advances by fewer than a few units (1 unit per 131 us). Slow series: the same calls with a sleep of 1 ms between (about 7.6 units of allowance per ms vs 1 consumed), expecting no lock. Contention series (accounting side): 8 threads each calling `partition.addAll(update, cloner, writeOp, NO_OP)` on one partition with 1,000 small single-row updates each, with an `OpOrder` per `AtomicBTreePartitionMemtableAccountingTest.java:292-326`, using the unmodified and the 1 MiB build.

**B2d. Observables and instruments.** Return value of `updateWastedAllocationTracker`; `useLock()`; the `wasteTracker` field via reflection; for the contention series `allocator.onHeap().owns()` after all updates and after releasing the allocator; thread dump count of threads BLOCKED in `AtomicBTreePartition$Updater.addAll` is not needed at this tier. Not observable directly: total garbage produced by failed attempts (use `ThreadMXBean.getThreadAllocatedBytes` per worker thread, from `com.sun.management.ThreadMXBean`, as an approximation).

**B2e. Procedure.**
1. Build the unmodified copy; run the direct-call sweep and record the table.
2. Run the burst and slow series and record when `useLock()` flips.
3. Run the contention series 5 times; record `owns()` totals and per-thread allocated bytes.
4. Edit `:63` in the second copy to `1L << 20`, rebuild, rerun steps 1 to 3.
5. Positive control: in each build, rerun the contention series with the pool limit lowered (`HEAP_LIMIT` argument at `AtomicBTreePartitionMemtableAccountingTest.java:296-297` set to a small value) and record that `owns()`/flush-trigger behaviour changes with the limit.

**B2f. Predictions.** Unmodified build, first call on a fresh partition: `w <= 10 MiB - 1024` returns false and `useLock()` false; `w` in `[10 MiB - 1023, 10 MiB - 1]` returns true (rounding to 10240 units gives `delta = 0`, `:285-286`); `w >= 10 MiB` returns true via `:272`; `w = 1` and `1024` return false. Burst of 1 KiB calls: `useLock()` becomes true after roughly 10240 calls minus the allowance earned, never after fewer than about 10,000 calls unless a clock tick pattern intervenes; the slow series never locks. Once true, it stays true. The 1 MiB build shifts every boundary down by 9 MiB (first-call boundary `1 MiB - 1023`, burst count about 1024). Contention series: for the same updates, `allocator.onHeap().owns()` after completion is equal (within the nondeterministic contribution of CAS-interleaving, which is nil because only the successful attempt is reported) in both builds and equal to what a single-threaded run of the same updates yields; per-thread allocated bytes are larger in the lock-free regime than the locked regime.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Boundary behaves as in B2f; `owns()` identical across builds and equal to single-threaded `owns()` | Claim confirmed: the constant controls locking only, accounted memory is not governed by it |
| `owns()` differs between the 10 MiB and 1 MiB builds beyond sampling noise, tracking the threshold | Claim refuted: accounted usage follows the constant |
| Boundary differs from B2f by more than one unit | The trace in A3 is wrong; amend A3 |
| `owns()` flat across builds and the lowered pool limit also does not change `owns()`/flush trigger | Control did not move: not confirmed |
| `useLock()` never flips in the burst series | Limit never reached (clock faster than modelled, or call rate too slow): not confirmed; raise `w` to 8 KiB per call |

**B2h. Controls.** Single-threaded run of the same updates (no CAS failures, so no waste, and tracker stays 0). Fresh partition per measurement (tracker is per object). Same machine, no other load. Positive control is the pool-limit change in step 5.

### B3. Cluster tier

**B3a. Environment and build.** One node suffices (CAS failures need concurrent writers to one partition, not multiple nodes); a second node is optional. Linux, JDK 11, Ant, local disk of known size (at least 20 GB free) for data, commit log and hints directories. Copy the tag to local disk as in B2a and build three variants by editing the literal at `AtomicBTreePartition.java:63`: V0 unmodified (10 MiB); V1 `1L` (so `wastedBytes < 1` is false for any real merge and every CAS failure locks immediately); V2 `1L << 40` (offset `(int)(2^40/1024) = 2^30`, fits an int, so locking essentially never triggers). `ant jar` each into a separate directory. JVM: `-Xms2g -Xmx2g` (G1 default), `-Xlog:gc*:file=gc.log`, and in `cassandra.yaml`: `memtable_allocation_type: heap_buffers` (the default, `conf/cassandra.yaml:825`), `memtable_heap_space: 512MiB`, `memtable_flush_writers: 2`, `concurrent_writes: 128`, `commitlog_sync: periodic`, directories on the local disk, `num_tokens: 1`. Default memtable (`SkipListMemtable`, `SkipListMemtable.java:130`) is used.

**B3b. Knobs.** (1) The variant V0/V1/V2 (the constant's value). (2) Positive control: `memtable_heap_space` at 128MiB vs 512MiB vs 1024MiB in V0 (this is a known cap: pool built at `AbstractAllocatorMemtable.java:81,96-99`). Variants are chosen to put the lock regime at its two extremes plus the default.

**B3c. Workload.** `cassandra-stress` (from the tree's `tools/bin`) with a user profile on one table with a single partition key value and wide clustering: schema `CREATE TABLE ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`, populate with `pk` fixed to 1, `ck` random over 10 million values, `v` 200 bytes, 256 client threads, `cl=ONE`. A single hot partition makes all mutation-stage writers contend on one `AtomicBTreePartition`, and the growing BTree makes each failed merge allocate more, so `heapSize` of failed attempts grows toward the threshold. Arithmetic: a tree of N rows copies on the order of log N branch nodes per insert, so waste per failure is KiB-scale early and the 10 MiB single-failure shortcut at `:272` is not expected; the rate path (`:281-288`) is what triggers, requiring about 7.45 MB/s of waste per partition. Duration: 10 minutes per run, which at several MB/s of ingest includes several flushes at 128 MiB. Same 10 minutes for each variant and each pool size.

**B3d. Observables and instruments.** (a) Accounted memtable size: JMX `org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=AllMemtablesHeapSize` and `MemtableOnHeapSize`, sampled every 5 s with `nodetool sjk mx` or a small JMX poller. (b) Actual resource, heap: GC log (`gc.log`) for allocation volume per second (heap before/after each young collection) and old-gen occupancy after mixed/full collections; `jcmd <pid> GC.heap_info`. (c) Actual resource, disk: sum of `du -sb` of the `ks/t-*` data directory and flush count (`nodetool tablestats ks.t`: `Memtable switch count`, `Space used (live)`). (d) Lock regime evidence: `jstack` or `jcmd Thread.print` 20 times at 30 s intervals counting threads BLOCKED on `AtomicBTreePartition$Updater` monitor (`:157`); in V0/V1 expect some, in V2 none. Not observable directly: the `wasteTracker` value or wasted bytes (private, no metric).

**B3e. Procedure.**
1. Start V0 with a clean data directory and the yaml of B3a; create the schema; record baseline (`nodetool tpstats`, tablestats).
2. Start sampling (JMX poller, `jstat -gc <pid> 5000`, `du` every 10 s) and run cassandra-stress for 10 minutes; take the 20 thread dumps during the run.
3. Stop stress, `nodetool flush`, record final tablestats and data size, stop the node, delete data, commit log, hints and saved caches directories.
4. Repeat steps 1 to 3 for V1 and V2, 3 runs each, order randomized.
5. Positive control: V0 with `memtable_heap_space` 128MiB, 512MiB, 1024MiB, same workload.
6. After the last run verify no `CassandraDaemon` or `cassandra-stress` process remains (`pgrep -fa 'CassandraDaemon|stress'`).

**B3f. Predictions.** Across V0, V1, V2 at the same `memtable_heap_space`: peak `MemtableOnHeapSize` stays at or below the pool limit with the flush trigger firing at about the same accounted size (cleanup threshold times the limit), so the memtable switch count and per-flush data size agree between variants to within run-to-run variation; data-directory growth at the same number of inserted rows is the same. Differences are expected only in write throughput and GC: V2 shows the largest young-GC allocation rate (retries produce garbage), V1 the smallest allocation rate and BLOCKED threads in every dump, V0 between. Positive control: peak `MemtableOnHeapSize`, flush count and per-flush size scale with `memtable_heap_space` (roughly 8x range between 128MiB and 1024MiB for per-flush size).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak accounted size, switch count and flushed bytes flat across V0/V1/V2 while they scale with `memtable_heap_space` | Claim confirmed: usage does not follow the constant |
| Peak accounted size or flushed bytes changes monotonically with the variant, beyond run-to-run spread, and the effect exceeds the spread across repeat runs | Claim refuted |
| Only GC allocation rate and BLOCKED-thread counts differ across variants | Claim confirmed and the real effect identified (churn/CPU, not retained memory) |
| No BLOCKED threads in V1, or no difference in allocation rate between V1 and V2 | Limit not reached or contention absent (too few CAS failures): not confirmed; raise client threads, shrink the value size, or use a smaller table so merges collide more |
| `memtable_heap_space` change does not move accounted size or flush count | Control did not move: not confirmed; check the yaml was loaded |
| Old-gen occupancy after full GC differs by variant | Possible retained-memory effect; investigate (e.g. pause-induced differences) before concluding |

**B3h. Controls.** The positive control is the pool-limit sweep in the same workload. Identical yaml, JVM options, and stress seed across variants; fresh data directory per run; randomized variant order; 3 repeats to judge spread; check the node has no other compaction load (`nodetool compactionstats`) when sampling.

**B4. Risks and cleanup.** Disk: data directory sized for at most about 20 GB (10 minutes of stress; cap with `-n`/duration and watch `df`); commit log set to 1024 MiB total (`commitlog_total_space`), hints disabled (`hinted_handoff_enabled: false`). All directories on local disk, none on shared storage; the source tree is only read. Processes: node, stress, JMX poller, `jstat` must be stopped after each run and checked with `pgrep`. Cleanup: delete the data, commit log, hints, saved caches and log directories and the copied source trees under `$WORK`. Unit tier: no files besides the compiled test output under `$WORK`.

## C. Sources read

- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java` (grep)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/ShardedSkipListMemtable.java` (grep)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java` (grep)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java` (grep)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/OpOrder.java` (grep)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java` (grep)
- `/users/jason92/cassandra-5.0.9/conf/cassandra.yaml` (grep)
- `/users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/db/partitions/AtomicBTreePartitionMemtableAccountingTest.java`
- `/users/jason92/cassandra-5.0.9/test/microbench/org/apache/cassandra/test/microbench/btree/AtomicBTreePartitionUpdateBench.java` (grep)
- Public: CASSANDRA-7546 on issues.apache.org (named, not re-read)

## D. Stage-4 feedback

`none yet`
