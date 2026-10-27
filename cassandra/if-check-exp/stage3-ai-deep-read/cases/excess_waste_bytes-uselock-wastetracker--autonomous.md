# EXCESS_WASTE_BYTES — verification solution  <!-- file: cases/excess_waste_bytes-uselock-wastetracker--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:258` (`useLock()`, helper `org.apache.cassandra.db.partitions.AtomicBTreePartition.useLock()`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: `EXCESS_WASTE_BYTES` only decides when a hot memtable partition switches from CAS retries to `synchronized` updates; it does not bound how much memtable memory (heap or off-heap) or disk is used. |
| Ground | The "waste" it counts is the on-heap size of a failed, discarded merge attempt (`heapSize` of the Updater, `AtomicBTreePartition.java:168`), which is garbage that is never added to the memtable pool (`BTreePartitionUpdater.java:180-183` reports only the final successful attempt). The only effect of the sentinel is a mutual-exclusion choice (`AtomicBTreePartition.java:155-162`). What caps memtable memory is the pool limit (`memtable_heap_space` / `memtable_offheap_space`, `DatabaseDescriptor.java:583-594`), a different mechanism. |

## A. Constraint trace

**A1. The constraint.** `EXCESS_WASTE_BYTES`, a hard-coded `private static final long` constant, `10 * 1024 * 1024L` = 10 MiB (`AtomicBTreePartition.java:63`). It is a runtime-compiled constant with no yaml key, no `-D` property and no JMX setter; changing it needs a source edit and rebuild. Related constants: `ALLOCATION_GRANULARITY_BYTES = 1024` (`:61`), `EXCESS_WASTE_OFFSET = (int)(EXCESS_WASTE_BYTES / ALLOCATION_GRANULARITY_BYTES)` = 10240 units (`:64`), `CLOCK_SHIFT = 17` (`:66`; one clock tick is 2^17 ns, about 131 us, per the comment at `:67`), sentinels `TRACKER_NEVER_WASTED = 0` and `TRACKER_PESSIMISTIC_LOCKING = Integer.MAX_VALUE` (`:57-58`). The per-partition state is `private volatile int wasteTracker`, initially `TRACKER_NEVER_WASTED` (`:80`). The entry point `useLock()` (`:258-261`) is just `wasteTracker == TRACKER_PESSIMISTIC_LOCKING`; the earlier trace is correct on this. Correction to the earlier trace: it describes the waste as "memory allocated and thrown away" in general; precisely, the quantity is `Updater.heapSize` of the last failed CAS attempt (see A2). Also, the default is a literal, not derived from anything.

**A2. What it caps.** Nothing about memory or disk in the usual sense. The compared quantity is `wastedBytes`, the argument of `updateWastedAllocationTracker` (`:269`), which is the `heapSize` accumulated by the failed `tryUpdateData` attempt (`:168`; `heapSize` is reset to 0 at every attempt, `:182-183`, and accumulated in `BTreePartitionUpdater.java:86,91,132,155,164,177`). That is on-heap bytes of newly built cells/rows/tree nodes (`unsharedHeapSizeExcludingData`) that are dropped when the CAS (`:185`) loses. Off-heap cell data cloned by the allocator's `Cloner` (`BTreePartitionUpdater.java:128,153,162`) is not in this number. So it is a contention-handling threshold measured in short-lived heap churn (GC pressure), not a limit on live memtable size.

**A3. Mechanism.**
1. `SkipListMemtable.put` (`db/memtable/SkipListMemtable.java:108`) finds or creates the `AtomicBTreePartition` (`:111-127`) and calls `previous.addAll(update, cloner, opGroup, indexer)` (`:131`), which is `AtomicBTreePartition.addAll` (`:120-123`) creating an `Updater`.
2. `Updater.addAll` (`:146`) first calls `shouldLock(writeOp)` (`:150`): `useLock()` (`:233`), then `lockIfOldest` (`:247-256`), which requires this write op to be the oldest live `OpOrder` group (`OpOrder.java:251-254`; one `Thread.yield()` retry at `:251`).
3. If it should lock, it runs `tryUpdateData` inside `synchronized (this)` (`:157-161`). Otherwise it runs `tryUpdateData` optimistically (`:165`); on CAS failure it calls `shouldLock(heapSize, writeOp)` (`:168`), i.e. `updateWastedAllocationTracker(heapSize)` (`:241`) and then `lockIfOldest`.
4. `updateWastedAllocationTracker` (`:269-296`): if `wastedBytes >= EXCESS_WASTE_BYTES` (`:272`) it goes straight to `wasteTrackerUpdater.set(..., TRACKER_PESSIMISTIC_LOCKING)` (`:293`) and returns true. Otherwise it rounds the waste up to 1 KiB units (`:275`), reads a 32-bit clock `nanoTime() >>> 17` (`:281`), keeps the tracker within `EXCESS_WASTE_OFFSET` units of the clock (`:282-284`), adds the waste (`:285`), and if the sum reaches the clock (`delta >= 0`, `:286`) it breaks out to set the sentinel; else CAS the new tracker (`:288`) and return false. So the sentinel is set when a single failed attempt wastes at least 10 MiB, or when the tracked waste outruns the allowed rate (`ALLOCATION_GRANULARITY_BYTES` per clock tick, about 7.6 KiB/ms, per the comment `:72-78`) by more than the 10 MiB window.
5. The sentinel is never reset in this class (only `set` at `:293` writes `TRACKER_PESSIMISTIC_LOCKING`; the field is per partition object and is dropped with the memtable).
Outcomes: not at limit, the thread retries optimistically; at limit, later and current writers on that partition serialise on the partition monitor, which removes further failed attempts. Nothing is refused, evicted, flushed or blocked on memory grounds. Other reader: `SkipListMemtable.getFlushSet` calls `useLock()` only to count "heavily contended" partitions for a TRACE log line (`SkipListMemtable.java:261-267`, enabled by `logger.isTraceEnabled()` at `:255`). Bypass or overshoot: the sentinel is only taken when the writer is the oldest live group (`:247-256`); if not, the writer keeps retrying optimistically even after the tracker is saturated.

**A4. Other consumers.** The resources touched are the same ones capped elsewhere: memtable on-heap accounting via `allocator.onHeap().adjust(heapSize, writeOp)` (`BTreePartitionUpdater.java:182`), the partition overhead allocated in `SkipListMemtable.put` (`:124-125`, the code comments that this can overshoot the limit), and the pool limits `memtable_heap_space` and `memtable_offheap_space` (`config/Config.java:186-189`; defaults a quarter of max heap each, `DatabaseDescriptor.java:583-587`; flush threshold `memtable_cleanup_threshold` default `1/(1+memtable_flush_writers)`, `DatabaseDescriptor.java:761-763`; `MemtablePool.SubPool.needsCleaning`, `MemtablePool.java:125-129`). The failed attempts' garbage is bounded only by the JVM heap and GC, not by any of these.

**A5. Evidence beyond the source.** In-tree test `test/unit/org/apache/cassandra/db/partitions/AtomicBTreePartitionMemtableAccountingTest.java` (shows how to build a pool, allocator and `AtomicBTreePartition` directly, lines 294-303) and `test/microbench/org/apache/cassandra/test/microbench/btree/AtomicBTreePartitionUpdateBench.java`. Public docs: Cassandra configuration docs for `memtable_heap_space` and `memtable_offheap_space` (https://cassandra.apache.org/doc/5.0/cassandra/managing/configuration/cass_yaml_file.html). No JIRA relied on.

## B. Verification solution

**B1. Claim under test.** The 10 MiB `EXCESS_WASTE_BYTES` threshold changes only which update path (optimistic CAS or `synchronized`) a hot partition uses; the memtable's accounted memory, and the node's actual heap/off-heap/disk use, do not follow it (a partition at the sentinel and one not at the sentinel own the same accounted bytes for the same data). It would be refuted if accounted or actual memtable memory differed systematically between a partition in locking mode and one in CAS mode, or if memtable memory stopped growing at a level tied to 10 MiB of waste.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tag to local disk (for example `rsync -a /users/jason92/cassandra-5.0.9/ $LOCAL/c509/`; never build in the shared tree). `cd $LOCAL/c509 && ant jar` (or `ant build-test`). Add a JUnit class `test/unit/org/apache/cassandra/db/partitions/WasteTrackerProbeTest.java` in the same package (so package-private `BTreePartitionUpdater.heapSize` is readable). Run `ant testsome -Dtest.name=org.apache.cassandra.db.partitions.WasteTrackerProbeTest`. Setup copies `AtomicBTreePartitionMemtableAccountingTest` (`setUp` at line 119, partition and allocator creation at lines 294-303, pool via `AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal`, line 296) with `heap_buffers`. Read the private `wasteTracker` field via reflection (`Field.setAccessible(true)`, allowed on JDK 11 for classpath code). The constant itself is not tunable; for the rate/threshold variants edit a local copy of `AtomicBTreePartition.java:63` (for example 1 MiB and 100 MiB) and rebuild.

**B2b. Knobs.** (1) Per-attempt waste size W of a forced failed CAS: 8 KiB, 1 MiB, and one update whose merge allocates at least 10 MiB on heap (size it so the probe's measured `heapSize` is at least `EXCESS_WASTE_BYTES`, and one clearly below). (2) Spacing between failures: back-to-back versus 2 ms apart. (3) The constant, local rebuild: 10 MiB (as shipped) and 1 MiB, to show the threshold location moves with it. (4) The allocation type of the pool: `heap_buffers` and `offheap_objects`.

**B2c. Workload.** To force a CAS failure deterministically on a single thread, pass an `UpdateTransaction` whose `onInserted` (called inside the merge, once per row inserted, `BTreePartitionUpdater.java:129`) runs, on the first call only, a nested `partition.addAll(otherUpdate, ...)` with `UpdateTransaction.NO_OP`. The nested write changes `ref`, so the outer `compareAndSet` (`AtomicBTreePartition.java:185`) fails and the outer loop calls `shouldLock(heapSize, ...)` (`:168`), then retries (the hook must not fire again, so the retry succeeds). The outer update is built with N rows of one small cell each; choose N so that the heap cost per attempt hits W (calibrate by running once without the hook and reading `updater.heapSize` returned by `addAll`; arithmetic: N = W / per-row heap cost). Failure sequences: (a) one failure with W above 10 MiB; (b) one failure with W below 10 MiB; (c) K = 12 failures of 1 MiB back-to-back on a fresh partition (units: 1024 each against a window of 10240, so the sum should cross after about 10 failures, less any clock credit); (d) 200 failures of 8 KiB, 2 ms apart (4 KiB/ms, below the 7.6 KiB/ms allowance, so never crosses). Accounting comparison: for each of two fresh partitions with identical data, force the sentinel on one by reflection (`wasteTrackerUpdater` field set to `Integer.MAX_VALUE`) and not on the other, then apply the same 1000 updates with no contention.

**B2d. Observables and instruments.** (i) `wasteTracker` after every forced failure (reflection), and `partition.useLock()`. (ii) `allocator.onHeap().owns()` and `allocator.offHeap().owns()` after the sequence (as in the accounting test, lines 328-329). (iii) `updater.dataSize` and `updater.heapSize` returned by `addAll`. Not observable: the garbage of failed attempts (not tracked by any pool); count it indirectly by summing the calibrated W per failure.

**B2e. Procedure.**
1. Copy tree, build, add the test class.
2. Calibrate: apply the N-row update to a fresh partition without hook; record `heapSize`; solve for N for each W.
3. Run sequences (a), (b), (c), (d) on fresh partitions, reading `wasteTracker` after each failure.
4. Run the accounting comparison (sentinel by reflection versus not), same data, `owns()` read at the end.
5. Repeat 3-4 with `AtomicBTreePartition.java:63` set to 1 MiB (rebuild).
6. Repeat with `offheap_objects`.
7. Positive control: on the same pool, write 1000 more distinct partitions and show `owns()` rises with data volume, and construct a `HeapPool` with a small limit (constructor `HeapPool(long, float, MemtableCleaner)`, `HeapPool.java:33`) with a counting `MemtableCleaner`; show the cleaner is triggered once `used() > nextClean` (`MemtablePool.java:125-136`), i.e. a cap that does bind memory.

**B2f. Predictions.** (a) `wasteTracker == Integer.MAX_VALUE` and `useLock()` true after the single failed attempt. (b) `wasteTracker` is a non-sentinel, non-zero value; `useLock()` false. (c) `useLock()` false for the first several failures and true at or before the 12th; with the constant at 1 MiB, it flips after about 1 failure of 1 MiB (since `wastedBytes < EXCESS_WASTE_BYTES` fails at exactly 1 MiB, `:272`) and with 100 MiB not within 12. (d) never true. Accounting: `owns()` on-heap (and off-heap) are equal, within the allocator's rounding, for the sentinel and non-sentinel partitions after the same uncontended updates; the failed attempts do not add to `owns()` (the final `owns()` equals the uncontended value for the same data). Control: `owns()` grows with partitions written; cleaner called after crossing `limit * cleanThreshold`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| (a) true, (b) false, (c) flips near 10 failures, (d) never | Mechanism works as traced (rate and single-shot paths). |
| (a) false although W >= 10 MiB | Trace wrong: the compared quantity is not `heapSize`, or `lockIfOldest` interfered (that alone does not change the tracker; check `wasteTracker`). |
| `owns()` differs between sentinel and non-sentinel partitions, or rises with failures | Claim refuted: waste/locking state changes memory accounting. |
| `owns()` equal in both modes and unchanged by forced failures, while the positive control rises and triggers the cleaner | Claim confirmed (usage does not follow the constant). |
| Failures never forced (outer CAS did not fail) or `owns()` control did not move | Not confirmed; fix the hook or workload. |
| Threshold flips at a different failure count when the constant is rebuilt to 1 MiB / 100 MiB | Confirms the constant is what controls the flip (but still only the locking mode). |

**B2h. Controls.** Fresh partition and allocator per sequence; same data order; the hook fires once per outer update (a counter); a run with the hook disabled shows `wasteTracker` stays 0; both allocation types; no other thread writes to the partition.

### B3. Cluster tier

**B3a. Environment and build.** One node on local disk with known free space (data, commitlog, hints on a local volume, 20 GB free or more). JDK 11, Ant; `ant jar` in a local copy of the tag. JVM: fixed `-Xms2G -Xmx2G` (G1 or CMS as shipped), so the default `memtable_heap_space` is 512 MiB (`DatabaseDescriptor.java:586-587`). `cassandra.yaml`: `memtable_allocation_type: heap_buffers` (also run once with `offheap_objects`), `memtable_flush_writers: 2` (so the cleanup threshold is 1/3, `DatabaseDescriptor.java:761-763`), `commitlog_sync: periodic`. Raise nothing else except leaving the default `commitlog_segment_size` so `max_mutation_size` is 16 MiB (`DatabaseDescriptor.java:898-899`); keep every batch below 8 MiB of data. Logging: `nodetool setlogginglevel org.apache.cassandra.db.memtable.SkipListMemtable TRACE` (flush-time contention message, `SkipListMemtable.java:255-267`). GC logging on (`-Xlog:gc*:file=$LOCAL/gc.log`).

**B3b. Knobs.** Workload contention shape (since the constant is not configurable): (A) hot: 64 client threads all writing to the same single partition key; (B) cold: the same total write volume spread over 1,000,000 distinct partition keys, so no CAS contention. Plus the real cap as positive control: `memtable_heap_space` 128 MiB versus 512 MiB (yaml, restart). Optional (rebuild): `AtomicBTreePartition.java:63` set to 1 MiB and to 100 MiB, to show the lock switch moves while memory does not.

**B3c. Workload.** Table `ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))` with `memtable` default, `compaction` default. Hot: 64 threads each issuing unlogged batches to `pk = 1`, each batch 2000 rows (distinct `ck`, `v` 100 bytes). Single-partition batches skip the batch size check (`BatchStatement.java:334`), and per-batch heap cost is well under 10 MiB but larger than 1 MiB-scale waste only matters in aggregate, so concurrent merges on one large partition drive failed CAS retries far above the allowed rate (7.6 KiB/ms is a small number against a 2000-row rebuild of a path in a growing tree). Total: 2,000,000 rows (about 200 MB of payload) for each of A and B, so the memtable fills the 128 MiB case more than once. Duration: until the load finishes, then 5 minutes quiet and `nodetool flush`.

**B3d. Observables and instruments.** (i) Memtable accounting: JMX `org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=MemtableOnHeapDataSize` and `MemtableOffHeapDataSize` (`TableMetrics.java:87,493`), sampled each second; `nodetool tablestats ks.t`. (ii) Actual process memory: `jcmd <pid> GC.heap_info` and `jstat -gc <pid> 1000`; RSS from `/proc/<pid>/status` (VmRSS); GC log allocation rate and number of young collections. (iii) Disk: `du -sk` of the data dir and `nodetool tablestats` Space used. (iv) Evidence of the lock mode: the TRACE line "High update contention in N/M partitions" on flush (`SkipListMemtable.java:266`). Not observable directly: per-partition `wasteTracker` and the amount of discarded work (use a throwaway `jdb`/jcmd-free alternative: none; rely on the TRACE line and GC allocation rate).

**B3e. Procedure.**
1. Copy the tag locally; build; apply yaml; start the node; create the schema; set the TRACE level; start samplers.
2. Run workload B (cold) with 64 threads; record samplers; flush; record disk; clear (drop table).
3. Run workload A (hot); same recording.
4. Repeat 2-3 with `memtable_heap_space: 128MiB` (restart) as the positive control.
5. Optional: rebuild with the constant at 1 MiB and 100 MiB and repeat A.
6. Stop the node and all samplers; confirm with `pgrep -f CassandraDaemon`; remove data dirs.

**B3f. Predictions.** In A the flush log shows heavily contended partitions >= 1 (the single hot partition is at the sentinel); in B it shows 0 or no message. In both A and B the peak `MemtableOnHeapDataSize` is bounded by about `memtable_heap_space` (plus the documented overshoot) and its level relative to the memtable pool limit is the same for A and B at the same total data; peak does not depend on the constant when rebuilt with 1 MiB or 100 MiB. A's GC allocation rate and young collection count are higher than B's while contended (garbage from failed attempts); that excess is not visible in `MemtableOnHeapDataSize`. With `memtable_heap_space` 128 MiB the peak memtable size and the flush count change accordingly (the positive control), while the constant at 1 MiB versus 100 MiB changes only the TRACE line and CPU/GC, not the peak.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak memtable size tracks `memtable_heap_space` (128 vs 512 MiB) and is the same in A and B and across constant values | Claim confirmed: a real cap binds, and the constant does not govern memory. |
| Peak memtable size or process RSS differs with the constant (1 MiB vs 100 MiB) beyond run-to-run noise at fixed contention | Claim refuted: usage follows the constant. |
| A shows higher GC allocation but equal memtable size to B | Consistent: waste is transient garbage outside the pool. |
| No TRACE contention line in A | The hot path never hit the sentinel; contention too low or not the oldest op group (`:247-256`); increase threads/batch size; not confirmed. |
| Positive control (memtable_heap_space) does not move peak size | Instruments or workload are wrong; not confirmed. |

**B3h. Controls.** Same data volume and row shape in A and B; fresh node data per run; same JVM flags; run order alternated; an idle baseline for RSS/heap; the TRACE line as the check that A really reached the locking state.

**B4. Risks and cleanup.** Disk: about 200 MB payload per run times compaction overhead; keep data, commitlog, hints on local disk with at least 20 GB free; never on shared storage. Memory: `-Xmx2G` fixed so a runaway cannot take the machine. Unit tier: local build copy only, nothing written to the shared tree. Cleanup: stop the node (`nodetool drain`, then kill), samplers and client threads; verify with `pgrep -f CassandraDaemon` and `pgrep -f jstat`; delete data, commitlog, hints, GC log and the local source copy; revert the local edit to `AtomicBTreePartition.java:63` by discarding the copy.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/OpOrder.java (lines 251-254)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/HeapPool.java (constructor)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (memtable fields)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java (memtable and max_mutation_size defaults)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java (verifyBatchSize)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/transactions/UpdateTransaction.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java (memtable gauges)
- /users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/db/partitions/AtomicBTreePartitionMemtableAccountingTest.java
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (memtable keys)
- https://cassandra.apache.org/doc/5.0/cassandra/managing/configuration/cass_yaml_file.html (cited, not re-read)

## D. Stage-4 feedback

none yet
