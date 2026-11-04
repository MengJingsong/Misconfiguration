# no_constraint — avoidReservedValues wasteTracker — verification solution  <!-- file: cases/no_constraint-avoidreservedvalues-wastetracker--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`AtomicBTreePartition.java:300`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L300) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the line is a sentinel-collision guard on a 32-bit time counter; it bounds no memory- or disk-significant object. |
| Ground | `avoidReservedValues` only maps two reserved integer values to value+1 (AtomicBTreePartition.java:298-303). The surrounding waste threshold (`EXCESS_WASTE_BYTES`) is a hard-coded constant that switches a partition from optimistic CAS to a lock; it limits retry contention, not how much heap the memtable holds. Memtable heap/off-heap volume is governed elsewhere (`memtable_heap_space`, `memtable_offheap_space`, via `MemtableAllocator.SubAllocator.adjust`). |

> **Link rule.** Followed: declaration and if statement are permalinks at tag `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** The target line has no memory or disk constraint. It is the `if` of `avoidReservedValues(int wasteTracker)` ([`AtomicBTreePartition.java:300`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L300), method declared at line 298). It compares its argument with the sentinels `TRACKER_NEVER_WASTED = 0` ([line 57](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L57)) and `TRACKER_PESSIMISTIC_LOCKING = Integer.MAX_VALUE` ([line 58](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L58)); on a match it returns value+1 (line 301), otherwise the value (line 302). The earlier trace's reading of this line holds. The nearest memory-significant limit-like value is `EXCESS_WASTE_BYTES = 10 * 1024 * 1024L` ([line 63](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L63)): kind constant (`private static final`), unit bytes, derived `EXCESS_WASTE_OFFSET = (int)(EXCESS_WASTE_BYTES / ALLOCATION_GRANULARITY_BYTES)` (line 64) with `ALLOCATION_GRANULARITY_BYTES = 1024` (line 61), `CLOCK_SHIFT = 17` (line 66). Not settable by yaml, `-D` or JMX (no reference to Config or System properties in the file: not verified beyond the grep of the symbols above in this file); changing it needs a rebuild. The per-partition field `wasteTracker` is `volatile int` initialised to `TRACKER_NEVER_WASTED` (line 80).

**A2. What it caps.** Line 300 caps nothing. It only keeps the packed value `time + delta` from equalling a reserved state. The quantity the surrounding logic compares with `EXCESS_WASTE_BYTES` is the bytes wasted by failed CAS attempts: `heapSize` of the failed attempt (passed at line 168, accumulated in `BTreePartitionUpdater.java:132,155,164,172,177`), tested at line 272. The effect of reaching it is a switch to `synchronized` locking (lines 155-160, 293-295), not a memory or disk bound.

**A3. Mechanism.**
1. `Updater.addAll` (line 146) calls `shouldLock(writeOp)` (line 150; method line 231), which is true only if `wasteTracker == TRACKER_PESSIMISTIC_LOCKING` (`useLock`, line 258-261) and this writer is the oldest live group (`lockIfOldest`, line 247-256).
2. If not locking, it loops: `tryUpdateData` (merge into a new BTree and CAS `ref`, `tryUpdateData`, lines 179-186) and, on CAS failure, `shouldLock(heapSize, writeOp)` (line 168).
3. `updateWastedAllocationTracker(wastedBytes)` (line 269): if `wastedBytes < EXCESS_WASTE_BYTES` (line 272), rounds wasted bytes up to 1 KiB units (line 275), reads a time counter `(int)(nanoTime() >>> CLOCK_SHIFT)` (line 281), computes a delta against the tracker (282-286) and, if still below zero, CASes the tracker to `avoidReservedValues(time + delta)` (line 288) and returns false (keep optimistic).
4. [`The if statement`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L300): outcome true, the packed value collides with 0 or `Integer.MAX_VALUE` and is shifted by 1; outcome false, it is returned unchanged (line 302). Neither outcome touches an allocator.
5. If `delta >= 0` (line 286-287) or the single waste is >= `EXCESS_WASTE_BYTES`, the tracker is set to `TRACKER_PESSIMISTIC_LOCKING` (line 293) and the caller locks.
6. After the loop, `reportAllocatedMemory()` (line 175) calls `allocator.onHeap().adjust(heapSize, writeOp)` (`BTreePartitionUpdater.java:180-183`), which is the path that charges the memtable pool.
Bypass or overshoot: the bound is a rate (the comment at lines 69-75 puts it at about 7.45 MB/s acceptable waste), not a total; wasted garbage from failed CAS attempts is never reported to the allocator, only the winning attempt's `heapSize` is (reset at each attempt, `this.heapSize = 0` at line 183).


The check itself is the if statement at [`AtomicBTreePartition.java:300`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L300).

**A4. Other consumers.** The same heap is used by memtable data for all tables, caches (key, row, counter, chunk), the Java heap garbage from retried merges, and off-heap structures, none controlled by this field. Memtable sizing is governed by `memtable_heap_space` (default quarter of max heap, `DatabaseDescriptor.java:586-587`), `memtable_offheap_space`, `memtable_allocation_type` (`Config.java:524`, default `heap_buffers`) and `memtable_cleanup_threshold` (`DatabaseDescriptor.java:761-763`).

**A5. Evidence beyond the source.** none (no issue numbers cited).

## B. Verification solution

**B1. Claim under test.** (Negative) The reserved-value guard and the waste tracker do not bound heap or disk: (a) `avoidReservedValues` never returns 0 or `Integer.MAX_VALUE` and changes nothing else; (b) the heap held by memtable data under contended writes tracks `memtable_heap_space`, not `EXCESS_WASTE_BYTES`, so a run that varies the tracker's behaviour (forced lock vs forced optimistic) leaves the memtable's accounted size unchanged for the same data.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`cp -r /users/jason92/cassandra-5.0.9 $WORK/c && cd $WORK/c && ant jar`), never build in the shared tree. Put a JUnit test in `$WORK/c/test/unit/org/apache/cassandra/db/partitions/` and run `ant testsome -Dtest.name=WasteTrackerProbe`. JVM options: `-Xmx512m`. The private method is reached by reflection (`setAccessible(true)`).

**B2b. Knobs.** (1) argument to `avoidReservedValues`: 0, Integer.MAX_VALUE, 1, -1, Integer.MIN_VALUE, Integer.MAX_VALUE-1, set directly. (2) Single-update waste size for `updateWastedAllocationTracker`: 1 KiB, 1 MiB, `EXCESS_WASTE_BYTES - 1`, `EXCESS_WASTE_BYTES` (boundary values at line 272). (3) Allocator memory type: `heap_buffers` vs `offheap_objects` (set `memtable_allocation_type` via `DatabaseDescriptor` before the pool is built) for the control.

**B2c. Workload.** Reflection calls for (1) and (2). For the usage-side control: build an `AtomicBTreePartition` with a `HeapPool` allocator, then apply N = 10,000 `PartitionUpdate`s of 100 rows each from 8 threads to the same key, forcing CAS contention; read `allocator.onHeap().owns()` (not verified: exact accessor name, check `MemtableAllocator.java:105-300`) after the run. Arithmetic: 8 threads x 10,000 updates guarantees many CAS failures on one partition; whether waste reaches 10 MiB (10,240 units of 1 KiB, line 64) is observed by reading `wasteTracker` by reflection.

**B2d. Observables and instruments.** Return values of `avoidReservedValues`; return value and resulting `wasteTracker` of `updateWastedAllocationTracker`; `useLock()` (line 258); allocator `owns` and `reclaiming` counters of the sub-allocator. Not directly observable: bytes of garbage from failed CAS attempts (use `-Xlog:gc` totals as a coarse indicator).

**B2e. Procedure.** 1. Build. 2. Run the reflection table for (1), assert results. 3. For (2), fresh partition per value; call `updateWastedAllocationTracker`; record return and `useLock()`. 4. Run contended workload twice, once with the tracker left alone, once with `wasteTracker` pre-set by reflection to `Integer.MAX_VALUE` (forced locking); record `owns` after identical data. 5. Repeat with `memtable_heap_space` set to 16 MiB vs 64 MiB for the positive control (cap known to bind: writes beyond it block in `SubAllocator.adjust`, `MemtableAllocator.java:160-185`).

**B2f. Predictions.** (1) 0 -> 1, Integer.MAX_VALUE -> Integer.MIN_VALUE (overflow of +1; this wraps, still not reserved), all others returned unchanged. Note: the wrap for MAX_VALUE is a consequence of int arithmetic at line 301; check that it is not reserved (MIN_VALUE is not 0 or MAX_VALUE). (2) values below `EXCESS_WASTE_BYTES` on a fresh tracker return false with a non-reserved tracker; values >= `EXCESS_WASTE_BYTES` return true and set the tracker to `Integer.MAX_VALUE`. (4) `owns` after identical data is equal (same accounting) in forced-lock and default runs, within allocator granularity. (5) Control: with a smaller `memtable_heap_space`, writes block or flush earlier; accounted `owns` stays at or below the limit plus in-flight allocations.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Guard output as predicted, `owns` equal across tracker states, `owns` bounded by `memtable_heap_space` in control | Claim confirmed: the tracker does not cap memory; the memtable pool does |
| `owns` differs materially between forced-lock and default runs | Claim refuted: the tracker mode affects accounted usage (contradicts A3 step 6) |
| Usage follows `EXCESS_WASTE_BYTES` boundary values | Claim refuted |
| `avoidReservedValues` returns 0 or MAX_VALUE for any input | Guard wrong (A1 refuted) |
| Contention never raised the tracker or control `memtable_heap_space` did not change blocking | Not confirmed |

**B2h. Controls.** Positive control: `memtable_heap_space` change (cap known to bind). Repeat each run 3 times; run with fixed seeds; GC logging on to separate garbage from accounted usage.

### B3. Cluster tier

**B3a. Environment and build.** One node (second optional), JDK 11, built from a local copy (`ant jar`). Local-disk data, commitlog and hints directories on a volume of known size (at least 20 GB free). JVM `-Xms2g -Xmx2g` in `conf/jvm11-server.options` of the copy.

**B3b. Knobs.** Cannot change the waste constants without recompiling. Vary instead: (1) tracker mode by building two jars: baseline and a variant with `EXCESS_WASTE_BYTES` changed to `1024L` (always locking quickly) and one with a very large value (never locking); (2) positive-control knob `memtable_heap_space` = 128MiB vs 512MiB in `cassandra.yaml`; `memtable_allocation_type: heap_buffers`.

**B3c. Workload.** `cassandra-stress` (shipped in `tools/`) hot-partition write: `cassandra-stress user profile=hot.yaml ops(insert=1) n=5000000 -rate threads=200` with a profile that has a single partition key (population=fixed(1)) and growing clustering rows, so CAS conflicts concentrate on one `AtomicBTreePartition`. Duration: until at least 3 flush cycles at the 128MiB setting. 200 threads on one key exceed the CAS-retry window many times over.

**B3d. Observables and instruments.** Heap used sampled every 5 s via `jcmd <pid> GC.heap_info` or JMX `java.lang:type=Memory`; `nodetool tablestats` (Memtable data size, Memtable off heap memory used); `nodetool tpstats` (MutationStage pending, blocked); GC log (`-Xlog:gc*`); `du -sh` of data dir. Not observable: per-partition `wasteTracker` value on a running node without a debugger.

**B3e. Procedure.** 1. Build three jars (baseline, small-constant, large-constant), each into its own directory. 2. For each jar: fresh data dirs, start node, run the stress profile, sample every 5 s, record peak heap, memtable data size, flush count. 3. Stop the node, confirm no leftover JVM (`pgrep -f CassandraDaemon`). 4. Repeat baseline with `memtable_heap_space` 128MiB then 512MiB (positive control).

**B3f. Predictions.** Peak memtable data size is about the same across the three jars (same data, same pool limit); flush timing follows `memtable_heap_space` (cleanup triggers at threshold, `DatabaseDescriptor.java:761-763`). Throughput and GC rate may differ (locking vs retries), but accounted memtable size should not. Control: 512MiB setting yields roughly 4x larger memtable data size at flush than 128MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Memtable size at flush equal across jars, scales with `memtable_heap_space` | Claim confirmed |
| Memtable size or peak heap scales with the waste constant | Claim refuted |
| Only total heap (GC garbage) differs between jars while accounted memtable size is equal | Confirmed for accounting; note unaccounted retry garbage (A3 bypass) |
| Memtable size does not change with `memtable_heap_space` (control flat) or no contention achieved | Not confirmed |

**B3h. Controls.** Same data volume, same seed, same host; unchanged JVM flags; positive control above; ensure MutationStage is not the bottleneck by checking CPU.

**B4. Risks and cleanup.** Disk: stress writes of about 5M rows; keep node dirs on the local volume and delete after each run (`rm -rf $WORK/data`). Do not build in the shared tree. Stop all Cassandra and cassandra-stress processes; verify with `pgrep -f "CassandraDaemon|cassandra-stress"`. Unit tier is in-JVM and leaves only the build directory.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/playbook-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/_TEMPLATE-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-in/140.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java (lines 125-186)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java (grep)

## D. Stage-4 feedback

`none yet`
