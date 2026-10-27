# EXCESS_WASTE_BYTES — verification solution  <!-- file: cases/excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:272` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: EXCESS_WASTE_BYTES only decides when one memtable partition switches from optimistic CAS to `synchronized` updates; it is a threshold on garbage churn, and neither live heap, memtable accounted size, nor disk is bounded by it. |
| Ground | The compared quantity (`wastedBytes`) is the size of a failed-and-discarded merge attempt, i.e. short-lived garbage that the memtable allocator never charges (`BTreePartitionUpdater.java:180-183` reports only the last attempt's `heapSize`; `AtomicBTreePartition.java:197-198` resets it per attempt). The only effect of reaching the limit is a state flag (`:293`). Memtable size is capped elsewhere (`memtable_heap_space`, `DatabaseDescriptor.java:586-587`). |

## A. Constraint trace

**A1. The constraint.** `EXCESS_WASTE_BYTES`, a compile-time constant (`private static final long`), declared at `AtomicBTreePartition.java:63` as `10 * 1024 * 1024L` (10 MiB, a literal, not derived). Unit: bytes. Related constants: `ALLOCATION_GRANULARITY_BYTES = 1024` (`:60`), `EXCESS_WASTE_OFFSET = (int)(EXCESS_WASTE_BYTES / ALLOCATION_GRANULARITY_BYTES)` = 10240 granules (`:64`), `CLOCK_SHIFT = 17` (`:66`), reserved tracker values `TRACKER_NEVER_WASTED = 0` and `TRACKER_PESSIMISTIC_LOCKING = Integer.MAX_VALUE` (`:56-58`). Not settable by yaml, `-D` or JMX (a grep of `src` for `wasteTracker` finds only `AtomicBTreePartition.java`; `useLock()` is read-only, used at `SkipListMemtable.java:261`). Changing it needs a source edit, rebuild and node restart.
Corrections to the earlier trace: (i) the check at `:272` is on a single report of wasted bytes; the cumulative window is the `wasteTracker` int (`:80`) and `EXCESS_WASTE_OFFSET` (`:283-284`); the earlier line numbers for the granularity (61) were off by one (it is `:60`). (ii) "wasted bytes" is not a separate measured counter: it is the `heapSize` field of the updater, which is reset to 0 at every attempt (`:197-198`) and accumulates what that attempt allocated (`BTreePartitionUpdater.java:132,155,164`). It is passed as `addWaste` at `AtomicBTreePartition.java:168`, only after a failed `compareAndSet` (`:200`). (iii) The documented acceptable steady rate is 7.63 KiB/ms (about 7.45 MiB/s) (comment at `:72-74`); `EXCESS_WASTE_BYTES` is the burst allowance above that rate. (iv) Locking, once set, is never reset on this object (`:293` is the only writer to the reserved value; the object lives until its memtable is flushed).

**A2. What it caps.** Nothing in memory or disk terms. It is a trigger on allocation churn (heap garbage from lost CAS races) in one `AtomicBTreePartition`. The quantity compared at `:272` is `wastedBytes`, the heap bytes allocated by the thread's failed merge attempt (long `addWaste`, `:239`); inside the loop the rounded granules (`:274-275`) are added to a time-relative counter and compared to 0 (`:285-287`).

**A3. Mechanism.**
1. `SkipListMemtable.put` calls `previous.addAll(...)` (`SkipListMemtable.java:130`), which constructs an `Updater` (`AtomicBTreePartition.java:112`).
2. `Updater.addAll` computes `shouldLock(writeOp)` (`:150`; the one-arg form returns false unless `useLock()`, `:231-237`, `:259-262`).
3. Optimistic path: `tryUpdateData` snapshots `ref`, zeroes `dataSize/heapSize`, builds a merged `BTreePartitionData` and tries `refUpdater.compareAndSet` (`:194-201`). Success returns (`:164-165`).
4. On a lost CAS the merged structure is discarded as garbage, and `shouldLock(heapSize, writeOp)` is called (`:168`), which calls `updateWastedAllocationTracker(addWaste)` (`:241`).
5. `updateWastedAllocationTracker` (`:268-296`): if `wastedBytes >= EXCESS_WASTE_BYTES` (`:272`) it skips the rate logic and sets `wasteTracker = TRACKER_PESSIMISTIC_LOCKING` (`:293`), returns true. Otherwise it rounds the waste up to granules (`:275`), loops while not already pessimistic (`:278`), takes a coarse clock `nanoTime() >>> 17` (`:281`), resets the window to `-EXCESS_WASTE_OFFSET` if never wasted, already past, or older than the window (`:283-284`), adds the waste (`:285`), and if the sum reaches >= 0 breaks out to the pessimistic state (`:286-287`, `:293`); else it CASes the new tracker value and returns false (`:288-289`).
6. If true, `lockIfOldest` (`:243-257`): if this write is not the oldest live OpOrder group it yields once and returns whether it became oldest; only then does the loop take `synchronized (this)` (`:155-160`). So even in the pessimistic state, a non-oldest writer may keep retrying optimistically (`:165-169` loop continues).
7. In the locked path the CAS cannot fail from other lock-takers (`tryUpdateData` still uses CAS, `:200`, but only the lock holder or non-locking readers' writers race), so no further waste is expected.
8. Memtable accounting: `reportAllocatedMemory` in the `finally` (`:176`) calls `allocator.onHeap().adjust(heapSize, writeOp)` (`BTreePartitionUpdater.java:180-183`); `heapSize` is the last attempt's value, so wasted attempts are not charged to the memtable pool. At flush, `SkipListMemtable.java:261-266` counts partitions with `useLock()` and logs at trace level.
Outcomes at the limit: pessimistic flag on that partition only; no rejection, no flush, no back-pressure. Bypass/overshoot: waste is unbounded in the sense that it is garbage, only the rate of generating it drops after the switch; a single huge report short-circuits the rate window (`:272`).

**A4. Other consumers.** Heap use not governed by this constant: the memtable pool (`memtable_heap_space`, default 1/4 of max heap, `DatabaseDescriptor.java:586-587`; `memtable_allocation_type: heap_buffers`, `conf/cassandra.yaml:825`), flush writers (`memtable_flush_writers`, `conf/cassandra.yaml:912`), the key/row/chunk caches, read-path garbage, and the concurrent writes stage (`concurrent_writes`, `conf/cassandra.yaml:723`). Garbage from lost CAS races competes with all of them for young-generation space but is reclaimed by GC, not retained.

**A5. Evidence beyond the source.** In-tree test `test/unit/org/apache/cassandra/db/partitions/AtomicBTreePartitionMemtableAccountingTest.java` exercises concurrent updates and memtable accounting (checks accounted heap against actual); the in-tree JMH `test/microbench/org/apache/cassandra/test/microbench/btree/AtomicBTreePartitionUpdateBench.java` exists for update contention. Original rationale: CASSANDRA-6271 style "wasted work" lock switch (ticket number from memory, not re-verified; treat as unverified). Otherwise none.

## B. Verification solution

**B1. Claim under test.** Reaching or changing `EXCESS_WASTE_BYTES` does not change how much memory the memtable holds or how much disk the node uses: it only flips a per-partition lock flag and thereby the amount of short-lived garbage. Falsified if peak memtable-accounted size, live heap after full GC, or disk use scales with the constant (e.g. is capped near 10 MiB or moves with it).

### B2. Unit tier

**B2a. Environment and build.** Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c509/`), JDK 11, `ant jar` then `ant build-test` inside `$WORK/c509`. Add one JUnit class `AtomicBTreePartitionWasteTrackerTest` under `$WORK/c509/test/unit/org/apache/cassandra/db/partitions/` (modelled on the setup of `AtomicBTreePartitionMemtableAccountingTest.java`: `DatabaseDescriptor` daemon-init, a table in a `SchemaLoader` keyspace, a `HeapPool`/`MemtableAllocator` from `utils/memory`). Run with `ant testsome -Dtest.name=org.apache.cassandra.db.partitions.AtomicBTreePartitionWasteTrackerTest` (JVM options from build.xml defaults, `-Xmx1G` is sufficient).

**B2b. Knobs.** The constant itself is not settable at runtime; two variants of the source are built: V1 `EXCESS_WASTE_BYTES = 1024 * 1024L`, V2 default 10 MiB, V3 `1024 * 1024 * 1024L` (largest where `EXCESS_WASTE_OFFSET` still fits `int`). Edit only the copy at `:63`. The test reads the constant by reflection (`getDeclaredField` + `setAccessible`) so the same test body runs on all builds. Second knob: the per-report waste value `w` passed to the tracker.

**B2c. Workload.** (a) Direct: reflectively call private `updateWastedAllocationTracker(long)` (`:268`) on a fresh `AtomicBTreePartition` with chosen `w`; read `wasteTracker` (`:80`) and `useLock()` (`:259`). Cases: `w = C-1`, `w = C` (C = the constant read by reflection), `w = C+1`; and a burst of `k` reports of `w = C/8` issued in a tight loop (k = 6, 8, 10); and `w = 1 KiB` x 100000 reports spaced by `Thread.sleep(1)` (below the 7.63 KiB/ms steady rate). (b) Indirect: 16 threads call `addAll` of 64 KiB-row updates for one partition key, 20 s, into a `HeapPool` of 256 MiB; after the run record `useLock()`, `pool.onHeap.used()`/`owns()` and a sum of actually-retained row sizes. Arithmetic: the tight loop with `w = C/8` accumulates `k*C/8` in under 1 ms of the 132 us-granule clock, so with window = C it crosses at k >= 8 (earlier if the clock ticks).

**B2d. Observables and instruments.** `wasteTracker` value (0, a timestamp-relative int, or `Integer.MAX_VALUE`), `useLock()`, the allocator's `onHeap().owns()/used()` (`MemtablePool` accessors), and `Runtime.totalMemory()-freeMemory()` after `System.gc()` for retained size. Not observable directly: the per-attempt `heapSize` of real races (only via reflection on a custom `BTreePartitionUpdater` subclass, or the indirect run).

**B2e. Procedure.** 1) Build V2, run (a) cases, record `useLock()` per case. 2) Run (b), record accounted owns() and retained heap. 3) Rebuild V1 and V3, repeat 1-2 (copy the tree per variant; never touch the shared tree). 4) Positive control: repeat (b) with the pool limit set to 32 MiB and 256 MiB (the `HeapPool` size argument) and record `owns()` against the limit. 5) Delete `$WORK`.

**B2f. Predictions.** (a) V2: `w = C-1` single report: not locking (tracker is a timestamp); `w = C` and `w = C+1`: `useLock()` true, tracker == `Integer.MAX_VALUE`. Burst of `C/8`: not locking for k <= 7 and locking by k = 9 at most (unless a clock tick spreads them). The 1 KiB x sleep(1) stream (about 1 KiB/ms, under 7.63 KiB/ms): never locking. V1 and V3: thresholds scale to 1 MiB and 1 GiB respectively, same shapes. (b) in all three variants accounted `owns()` is within the same relation to retained data (equal to within allocator overheads) and independent of the variant; the only difference may be `useLock()` true/false. Control: `owns()` stays at or below the pool limit scale (32 MiB vs 256 MiB differ).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| (a) threshold at C exactly; (b) owns()/retained identical across V1/V2/V3 while `useLock()` differs | Mechanism as traced; usage does not follow the constant (claim confirmed) |
| (b) owns() or retained heap differs across V1/V2/V3 in proportion to C | Usage follows the constant (claim refuted) |
| (b) owns() tracks pool limit (control moves) and is flat across variants | Claim confirmed |
| (a) threshold elsewhere than C | The A3 trace is wrong; revise A3 |
| `useLock()` never true in (b) in any variant, or the control owns() did not move with pool size | Limit never reached or control inert: not confirmed |

**B2h. Controls.** Fresh partition per case (tracker starts 0). Fixed threads, key, row size across variants. Pool-limit control (B2e step 4). A run with 1 thread (no CAS failures) must give `useLock()` false and `owns()` equal to retained.

### B3. Cluster tier

**B3a. Environment and build.** One node (second optional), Linux, JDK 11, Ant. Three builds from three local copies (`$WORK/c509-v1|v2|v3`, constant at `:63` = 1 MiB, 10 MiB, 1 GiB), each `ant jar`. Each node in its own directory on local disk with at least 20 GB free for data, commit log, saved caches, hints. `cassandra.yaml`: `num_tokens: 1`, `memtable_allocation_type: heap_buffers`, `memtable_heap_space: 512MiB`, `memtable_flush_writers: 2`, `concurrent_writes: 128`, `commitlog_segment_size: 32MiB` (so max mutation = 16 MiB), `commitlog_sync: periodic`, `data_file_directories`/`commitlog_directory` on the local disk. `jvm11-server.options`: `-Xms4G -Xmx4G`, `-XX:+UseG1GC`, `-Xlog:gc*:file=$RUN/gc.log`. Logging: set `org.apache.cassandra.db.memtable.SkipListMemtable` to TRACE in `logback.xml`. Also JMX on.

**B3b. Knobs.** The build variant (1 MiB / 10 MiB / 1 GiB). Per-mutation size S (rows x row bytes) to put single reports above or below the constant: S_small = 64 rows x 1 KiB (about 64 KiB); S_big = 1200 rows x 8 KiB (about 9.6 MiB, under the 16 MiB mutation limit, above 1 MiB, just under 10 MiB; the heap cost of a failed attempt is the merged copy, larger than the payload, so it is near or above 10 MiB; V1 should be crossed in any case). Control knob: `memtable_heap_space` 128 MiB vs 512 MiB.

**B3c. Workload.** One table `ks.hot (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`, `compaction = SizeTiered`, all writes to the single partition `pk = 1`, 32 client threads (cassandra-stress user profile with `pk` fixed, or a driver script), unlogged batches of the size S, 120 s per cell, consistency ONE, new `ck` per row (so memtable keeps growing and CAS races on one `AtomicBTreePartition` are frequent). Reach: 32 writers racing on one partition give lost CASes on nearly every contended write; data ingress of at least 100 MB/s (arithmetic: 32 threads x 64 KiB per few ms) fills 512 MiB in seconds, so flush cycles are exercised. Run length 120 s per variant per S.

**B3d. Observables and instruments.** (1) Memtable accounted size and flush counts: `nodetool tablestats ks.hot` ("Memtable data size", "Memtable cell count", "Memtable switch count") and MBean `org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=hot,name=AllMemtablesHeapSize` sampled every 1 s via `nodetool` or jmxterm. (2) Heap: `jcmd <pid> GC.heap_info` and the GC log for used-after-GC, plus `jstat -gcutil <pid> 1000`. (3) Allocation/churn: GC log young-collection frequency and bytes freed per second. (4) Lock flag: TRACE line "High update contention in N/M partitions" at flush (`SkipListMemtable.java:265`) in `system.log`. (5) Disk: `du -sk` on data directory and commit log every 10 s. (6) Throughput: client ops/s. Not observable: per-attempt waste bytes.

**B3e. Procedure.** For each variant v in {V1, V2, V3} and each S in {small, big}: start node from build v with a fresh empty data dir (`$RUN/v/S`); create schema; run workload 120 s; sample as above; `nodetool flush`; stop node (`kill`, then `pgrep -f CassandraDaemon` to confirm none); archive the logs; delete the data. Then the positive-control cell: V2 with `memtable_heap_space` 128 MiB and 512 MiB, S_small, same workload. Commands: `bin/cassandra -R -p $RUN/pid` (from the matching build), `bin/cqlsh -f schema.cql`, `tools/bin/cassandra-stress user profile=hot.yaml 'ops(insert=1)' duration=120s -rate threads=32`.

**B3f. Predictions.** Peak "Memtable data size" / `AllMemtablesHeapSize` stays at or below about the `memtable_heap_space` scale (512 MiB, flush before it is exceeded, with overshoot bounded by in-flight writes) in all six cells, with no relation to the constant (not near 1 MiB, 10 MiB nor 1 GiB). Heap used-after-GC is similar across variants for the same S (differences within noise). Disk is the same function of ingress regardless of variant. What does differ: V1 with S_big shows the lock flag in the trace line and lower young-GC rate/higher or lower throughput than V3 with S_big (V3 almost never locks with a 1 GiB burst allowance until sustained waste exceeds the steady rate). Control: with `memtable_heap_space` 128 MiB the peak memtable size and flush frequency scale with 128 vs 512 MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak memtable size / used-after-GC / disk equal across V1-V3 (within sampling noise) and control cells move with `memtable_heap_space` | Usage does not follow the constant (claim confirmed) |
| Peak memtable size or used-after-GC clearly ordered V1 < V2 < V3 for the same S and workload | Usage follows the constant (claim refuted) |
| Only GC frequency/throughput and the lock-flag trace line differ across variants | Constant governs churn only (consistent with the trace; claim confirmed) |
| Lock-flag trace line never appears in any variant, or the control did not change memtable size | Limit never reached or control inert (not confirmed; raise S, threads, or check TRACE logging) |
| Memtable accounted size capped near the constant's size | A2/A3 wrong; the trace must be redone |

**B3h. Controls.** Same JVM flags, data dir size, table, key space, client threads, duration and warm-up (discard the first 20 s) across cells; only the constant changes. A single-thread cell (no CAS contention) must show no lock flag in any variant. Repeat each cell twice; accept variance only if repeat differences are smaller than between-variant differences. The `memtable_heap_space` control shows the harness can see a known cap bind.

**B4. Risks and cleanup.** Disk: data, commit log (32 MiB segments, `commitlog_total_space` left default but bounded by local disk of 20 GB or more) and hints all on local disk; never on shared storage. Peak disk per cell is about the ingress of 120 s, check `df` before each cell, abort if under 5 GB free. Processes: the node(s), cassandra-stress, jcmd/jstat samplers; stop all and confirm with `pgrep -f 'CassandraDaemon|cassandra-stress|jstat'`. Builds only in `$WORK` copies; `rm -rf $WORK $RUN` at the end. Unit tier needs no cluster and nothing beyond the copy.

## C. Sources read

- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/OpOrder.java` (`isOldestLiveGroup`, line 251)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (lines 586-590, 4055-4057)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java` (lines 186-190, 524)
- `/users/jason92/cassandra-5.0.9/conf/cassandra.yaml` (grep of memtable and concurrent_writes lines)
- `/users/jason92/cassandra-5.0.9/build.xml` (grep of testsome targets)
- Test file names only (grep): `AtomicBTreePartitionMemtableAccountingTest.java`, `AtomicBTreePartitionUpdateBench.java`

## D. Stage-4 feedback

`none yet`
