# EXCESS_WASTE_OFFSET — verification solution  <!-- file: cases/excess_waste_offset-updatewastedallocationtracker-delta--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`AtomicBTreePartition.java:283`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L283) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the constant is a contention trigger (switch from optimistic CAS retry to `synchronized`), not a cap on memory or disk; the garbage it counts is transient and is never charged to the memtable allocator. |
| Ground | The tracked quantity is the heap size of a failed CAS attempt (`heapSize`, passed at `AtomicBTreePartition.java:168`), which is discarded garbage. Exceeding the budget only sets a per-partition flag (`AtomicBTreePartition.java:293`); it does not reject, throttle, flush or evict anything. The retained memtable footprint is governed by other limits (`memtable_heap_space`, `memtable_offheap_space`, `memtable_cleanup_threshold`). |

## A. Constraint trace

**A1. The constraint.** `EXCESS_WASTE_OFFSET` (derived from `EXCESS_WASTE_BYTES`). Kind: hard-coded private static final constants (not configuration, not a JVM property). Declared at [`AtomicBTreePartition.java:63-64`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L63-L64): `EXCESS_WASTE_BYTES = 10 * 1024 * 1024L` and `EXCESS_WASTE_OFFSET = (int) (EXCESS_WASTE_BYTES / ALLOCATION_GRANULARITY_BYTES)`, with `ALLOCATION_GRANULARITY_BYTES = 1024` at line 61 and `CLOCK_SHIFT = 17` at line 66. Unit: `EXCESS_WASTE_BYTES` in bytes (10 MiB), `EXCESS_WASTE_OFFSET` in 1 KiB granules (10240). Default derived by arithmetic from the literals. Not settable: no yaml key, `-D` property or JMX (grep of the class shows none); changing it needs a source edit and rebuild. The allowed waste rate is about 7.63 KiB/ms per the comment at lines 72-79 (the comment's own figure; "7.45Mb/s" there is the comment's wording).

**A2. What it caps.** Nominally, the amount of memory "wasted" (allocated by a thread whose CAS on `ref` lost) per partition above an allowed real-time rate, before that partition switches to pessimistic locking. The quantity compared is the `delta` in granules: `wasteTracker - (int)(nanoTime() >>> 17)` (lines 281-282), compared with `-EXCESS_WASTE_OFFSET` at line 283, plus the single-attempt early check `wastedBytes < EXCESS_WASTE_BYTES` at line 272. The "waste" input is `heapSize` of the failed update attempt (`AtomicBTreePartition.java:168`; field at `BTreePartitionUpdater.java:46`, reset per attempt at `AtomicBTreePartition.java:183`). Resource: transient on-heap garbage (young generation), and CPU contention; it is not a bound on retained memtable memory or disk.

**A3. Mechanism.**
1. `SkipListMemtable.put` calls `previous.addAll(...)` (`SkipListMemtable.java:130`), which runs `Updater.addAll` (`AtomicBTreePartition.java:146`).
2. `shouldLock(writeOp)` at line 150 returns true only if `wasteTracker == TRACKER_PESSIMISTIC_LOCKING` (line 260) and this writeOp is the oldest live group (lines 247-256).
3. Optimistic path: `tryUpdateData` (lines 179-186) merges into a fresh tree and does `refUpdater.compareAndSet`. On failure, `heapSize` of that attempt is the waste; line 168 calls `shouldLock(heapSize, writeOp)`, which calls `updateWastedAllocationTracker(addWaste)` (line 241, defined line 269).
4. In the tracker, the `if` at [`AtomicBTreePartition.java:283`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L283) (`oldTrackerValue == TRACKER_NEVER_WASTED || delta >= 0 || delta < -EXCESS_WASTE_OFFSET`) resets the window to `-EXCESS_WASTE_OFFSET` (line 284) when the tracker is fresh, in the past (the allowed rate has caught up) or implausibly far ahead. Then `delta += wastedAllocation` (line 285); if still negative, the tracker advances via CAS (line 288) and the method returns false (keep retrying optimistically).
5. If `delta >= 0` (line 286-287) or the single wasted amount is at least 10 MiB (line 272 false), line 293 sets `TRACKER_PESSIMISTIC_LOCKING` and line 295 returns true.
6. Outcome at the limit: the caller (if oldest live group) re-runs the update inside `synchronized (this)` (lines 155-161), so no further CAS losses on that partition. Nothing is rejected, blocked from allocating, or flushed. The flag is never cleared in this class (only set at 293; assignments at lines 80 and 293), so it lasts until the partition object is dropped with its memtable (not verified beyond this class).
7. Bypasses / overshoot: waste below the offset window is unbounded in total over a long time, because the budget refills with real time (line 283 `delta >= 0` branch). Waste is also measured as `heapSize`, which excludes cloned data buffers charged directly via the cloner (`BTreePartitionUpdater.java:128-133`; whether those are all charged to the allocator is not verified), so it under-counts true allocation.

**A4. Other consumers.** Retained memtable memory is accounted separately: `reportAllocatedMemory` charges only the final attempt's `heapSize` to `allocator.onHeap()` (`BTreePartitionUpdater.java:180-183`, called from `AtomicBTreePartition.java:175`). That is limited by `memtable_heap_space` / `memtable_offheap_space` (`Config.java:187,189`; defaults of a quarter of max heap at `DatabaseDescriptor.java:584-587`; `conf/cassandra.yaml:797`), `memtable_cleanup_threshold` (`Config.java:190`) and `memtable_allocation_type` (`Config.java:524`). Failed attempts' trees are plain garbage reclaimed by the GC; the GC and young-gen size, not this constant, decide how that garbage affects the heap.

**A5. Evidence beyond the source.** Class comment at `AtomicBTreePartition.java:56-79`. Existing test `test/unit/org/apache/cassandra/db/partitions/AtomicBTreePartitionMemtableAccountingTest.java` and microbenchmark `test/microbench/org/apache/cassandra/test/microbench/btree/AtomicBTreePartitionUpdateBench.java` exercise the class (only file names checked; their content was not read). No issue numbers relied on.

## B. Verification solution

**B1. Claim under test.** Memory use does not follow `EXCESS_WASTE_OFFSET`: once a hot partition has crossed the waste budget and switched to locking, the retained memtable heap and process heap are still determined by `memtable_heap_space` and the data written, not by the 10 MiB budget; the constant only changes who is serialised (CAS vs lock). Falsified if the retained memtable size or peak heap tracks the waste budget (for example plateaus near it).

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $LOCAL/c509/`), `cd $LOCAL/c509 && ant jar`. Put a small driver class in `$LOCAL/driver/` (outside the tree) compiled against `build/classes/main` plus `build/lib/jars/*`; run with `java -cp ... -Dcassandra.config=file://$LOCAL/c509/conf/cassandra.yaml -Xmx512m`. `DatabaseDescriptor.daemonInitialization()` first (the class's `EMPTY_SIZE` at line 52 needs the partitioner).

**B2b. Knobs.** The constant is not settable, so the knob is the input `wastedBytes` passed to `updateWastedAllocationTracker`. Values: 1 byte, 1 KiB, 100 KiB, 1 MiB, 10 MiB - 1, 10 MiB, 64 MiB; and the inter-call time gap (0, 1 ms, 10 ms, 100 ms). Set by reflection on the private method (`setAccessible(true)`). To test a different offset, optionally compile a copy of the class with the literal at line 63 changed to 20 MiB, in the local copy only.

**B2c. Workload.** One `AtomicBTreePartition(null, key, null)` (constructor accepts nulls, as `EMPTY_SIZE` at line 52-54 shows). Call the method repeatedly with a fixed `wastedBytes`. Arithmetic: with no time passing, the window starts at -10240 granules (line 284); each call adds `ceil(wastedBytes/1024)` (line 275, 285); so the expected number of calls before returning true is about `10240 / ceil(wastedBytes/1024)`, e.g. 1 MiB calls (1024 granules) switch on about the 10th call; a single call of at least 10 MiB switches at once (line 272). With a gap, the budget refills at 1 granule per 2^17 ns, i.e. about 7.63 granules/ms.

**B2d. Observables and instruments.** Return value of the method; `useLock()` (line 258); reflection read of `wasteTracker` (line 80). Memory: `Runtime.totalMemory()-freeMemory()` and `jcmd GC.class_histogram` only to show the tracker holds no memory (it is one int). The tracker cannot show real heap use; it only reflects the operand.

**B2e. Procedure.**
1. Build as in B2a; write the driver; run each (wastedBytes, gap) pair on a fresh partition.
2. Record the number of calls and elapsed granules until the first `true`.
3. Positive control: run the same calls on a partition whose `ref` is large (insert rows with `Updater`/`addAll` against an `HeapPool` allocator with a small `memtable_heap_space`-sized pool) and show that the pool limit, not the tracker, blocks/flushes (the allocator `allocate` blocks or marks reclaiming, `MemtableAllocator.java:169-200`).
4. Stop the JVM; confirm no `java` process remains.

**B2f. Predictions.** Gap 0: calls-to-switch matches `10240 / ceil(wastedBytes/1024)` within one, and a single call at 10 MiB or more switches on the first call; calls below that, with a gap long enough to refill (>= 1.4 s for a full 10 MiB window), never switch. The tracker field stays a single int regardless of how much waste is reported (no memory growth). After the switch, `useLock()` stays true on further calls.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Switch count matches the formula; tracker is O(1) memory; nothing else changes after the switch | Mechanism as traced; it is a mode switch, claim (usage does not follow the constant) supported at unit level |
| Switch needs far more or fewer calls than the formula | Trace wrong (rate, window or rounding) |
| Pool-limited run (positive control) shows allocator `owns` bounded by pool size while the tracker has no effect on it | Claim confirmed |
| Allocator `owns` plateaus near 10 MiB when the pool is large | Claim refuted: usage follows the constant |
| Switch never reached, or control did not move | Not confirmed |

**B2h. Controls.** Fresh partition per run; fixed seed for sizes; gap measured with `nanoTime`, not wall clock; same JVM flags; run with the literal changed to 20 MiB to show the switch point moves with the constant (mechanism check) while allocator usage does not.

### B3. Cluster tier

**B3a. Environment and build.** One node (two for a replicated variant), JDK 11, local copy built with `ant jar`. Data, commit log, hints and saved caches under `$LOCAL/node/` on a local disk with at least 20 GiB free. JVM: `-Xms2g -Xmx2g`, G1, `-Xlog:gc*:file=$LOCAL/gc.log`, JFR optional (`-XX:StartFlightRecording=filename=$LOCAL/r.jfr,settings=profile`). Config: `memtable_allocation_type: heap_buffers`, `memtable_heap_space: 512MiB`, `memtable_offheap_space: 512MiB`, `commitlog_sync: periodic`, `concurrent_writes: 128`.

**B3b. Knobs.** The constant is not settable, so use two builds: stock, and a local build where line 63 is changed to a very large value (for example `1024 * 1024 * 1024L`, effectively never locking) and one with a very small value (for example `1024L`, locking almost at once). Second knob (positive control): `memtable_heap_space` 128MiB vs 512MiB vs 1024MiB.

**B3c. Workload.** Table `ks.hot(pk int, ck int, v blob, PRIMARY KEY (pk, ck))`. 64 client threads (`cassandra-stress` with a user profile, or a small driver) all upserting rows into a single partition `pk=1` with 4 KiB values and growing `ck`, for 10 minutes. Arithmetic: 64 concurrent writers on one partition make most CAS attempts fail while the partition tree is large, so failed-attempt heap far exceeds the 7.63 KiB/ms allowance, and the 10 MiB window is passed within about a second. A second run uses 64 distinct partitions (control: no contention, no switch).

**B3d. Observables and instruments.** `nodetool tablestats ks.hot` (Memtable data size, off-heap memory used); JMX `org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=hot,name=MemtableOnHeapSize` sampled every 1 s; GC log (allocation rate, heap after GC, young GC frequency); `jcmd <pid> GC.heap_info`; `nodetool tpstats` (MutationStage pending); write throughput and p99 from the client; JFR lock profile for contention. Disk: `du -sk` of the data directory every 10 s. Not directly observable: per-partition `wasteTracker`; infer the switch from the shift to lock contention in JFR and from throughput change between builds.

**B3e. Procedure.**
1. Copy the tree to `$LOCAL/c509`, `ant jar`; make the three variants as separate copies (`c509-big`, `c509-small`).
2. For each variant: wipe `$LOCAL/node`, start the node, wait for `nodetool status` UN, create schema, start sampling, run the hot-partition workload for 10 minutes, then the distinct-partition workload for 10 minutes; stop the node (`nodetool drain`, kill), keep logs.
3. Repeat the stock build with the three `memtable_heap_space` values (positive control).
4. Confirm no `CassandraDaemon` process is left (`pgrep -f CassandraDaemon`).

**B3f. Predictions.** Across the three constant values, `MemtableOnHeapSize` for equal data written, and peak heap after GC, are the same within normal noise, and neither plateaus near 10 MiB; what changes is throughput and contention (huge constant: more CAS retries and higher young-gen allocation rate; tiny constant: lock mode almost at once, lower allocation rate). Across `memtable_heap_space` values, `MemtableOnHeapSize` is capped near each value (flush at the cleanup threshold) and moves with it. The distinct-partition run shows no dependence on the constant.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Retained memtable size and heap-after-GC flat across the constant values; allocation rate and throughput differ | Claim confirmed: the constant is a contention switch, not a memory cap |
| `MemtableOnHeapSize` moves with `memtable_heap_space` (positive control) | Control valid: a cap does bind here |
| Retained size or peak heap changes in step with the constant, or plateaus near 10 MiB | Claim refuted |
| No difference at all in allocation rate or throughput between constant values | Contention not reached (not confirmed); raise threads or shrink values |
| The control does not move | Not confirmed |

**B3h. Controls.** Distinct-partition run (no contention); fixed JVM flags and heap; same data volume per run; identical seed; several repeats; compare after GC (heap after full GC), not instantaneous heap; keep `memtable_flush_writers` the same.

**B4. Risks and cleanup.** Disk: node data stays under `$LOCAL/node`, with a 20 GiB budget; the workload writes about 4 KiB per row, so cap each run by row count (for example 2 million rows is about 8 GiB logical) and check `df` before each run. No shared storage or shared source tree is touched; builds are in local copies. Leftover processes: `pkill -f CassandraDaemon` for the user's own PIDs, then `pgrep` to confirm; stop stress clients and JFR. Cleanup: delete `$LOCAL/node`, `$LOCAL/c509*`, the driver directory and the logs after the numbers are copied out.

## C. Sources read

- `/tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md`
- `.../agent-docs/playbook-autonomous.md`, `.../agent-docs/_TEMPLATE-autonomous.md`, `.../agent-in/139.md`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java` (lines 100-130)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java` (grep)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java`, `DatabaseDescriptor.java` (grep), `conf/cassandra.yaml` (grep)
- File listings of `test/unit/.../db/partitions/` and a grep for `AtomicBTreePartition` in test directories (contents not read)

## D. Stage-4 feedback

`none yet`
