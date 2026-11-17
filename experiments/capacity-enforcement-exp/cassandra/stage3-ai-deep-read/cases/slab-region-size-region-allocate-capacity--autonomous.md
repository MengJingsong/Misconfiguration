# slab-region-size-region-allocate-capacity — verification solution  <!-- file: cases/slab-region-size-region-allocate-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:201` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent session, 2026-10-26 (design only, nothing built or run) |
| Estimate | `negative`. Line 201 compares a bump offset with the capacity of one 1 MiB slab region. That is a per-region fit test, not a node-level cap. The memtable memory cap is enforced earlier, on requested bytes, by `memtable_heap_space` / `memtable_offheap_space`. |
| Ground | The constraint at line 201 is the compile-time constant `REGION_SIZE` (1 MiB), through `data.capacity()`. It bounds how many bytes one region holds, not how many regions exist. The number of regions is limited only indirectly, because the pool is charged the requested `size` (line 89) rather than the region bytes. Tail waste in each retired region (up to about 1/9 of a region for slab-eligible sizes) is never charged. Real heap/direct use can therefore exceed the accounted use, and `REGION_SIZE` does not bound that total. |

## A. Constraint trace

**A1. The constraint.** `REGION_SIZE`, with `MAX_CLONED_SIZE` as its companion.
- Kind: compile-time constant (`private final static int`). It is not a yaml key, JVM property or JMX attribute. Changing it needs a source edit and a rebuild.
- Declared at `SlabAllocator.java:51` (`REGION_SIZE = 1024 * 1024`, bytes). `MAX_CLONED_SIZE = 128 * 1024` is at `:52`. Allocations larger than that skip the slabs.
- It reaches line 201 as `data.capacity()`, where `data` is built in `getRegion()` at `:139` (`ByteBuffer.allocate(REGION_SIZE)` for on-heap, `allocateDirect(REGION_SIZE)` for off-heap).
- The class Javadoc (`:34-36`) says the same: 1 MiB regions, slices up to 128 KiB.
- The real memtable limits live in different places.
  - `memtable_heap_space` and `memtable_offheap_space` are declared at `config/Config.java:186-189`.
  - Defaults are 1/4 of max heap, from `config/DatabaseDescriptor.java:583-587`; the `cassandra.yaml` examples are commented out at `conf/cassandra.yaml:797,799`.
  - `memtable_allocation_type` is at `Config.java:524` (default `heap_buffers`, yaml `conf/cassandra.yaml:825`).
  - `memtable_cleanup_threshold` is at `Config.java:190`; its default is `1/(1+memtable_flush_writers)` (`DatabaseDescriptor.java:761-763`).
  - These are set in yaml and need a restart.

**A2. What it caps.** Heap, or direct (off-heap) memory when `allocateOnHeapOnly` is false.
- The quantity compared at `:201` is `newOffset + size` against `data.capacity()`, so it is the fill level of one region.
- It only decides "this region is full, retire it and take a new one".

**A3. Mechanism.**
1. `SlabAllocator.allocate(size, opGroup)` (`:83`) first charges the pool for the requested `size`: `(allocateOnHeapOnly ? onHeap() : offHeap()).allocate(size, opGroup)` (`:89`).
2. `SubAllocator.allocate` (`MemtableAllocator.java:169-197`) calls `parent.tryAllocate(size)`.
   - `MemtablePool.java:151-161` refuses when `allocated + size > limit`, where `limit` is the `memtable_*_space` value.
   - On refusal the caller blocks on `hasRoom()` (`MemtableAllocator.java:185-195`), unless `opGroup.isBlocking()` (`:180`). In that case it calls `allocated(size)` and overshoots the limit.
   - `MemtablePool.SubPool.maybeClean` (`MemtablePool.java:131-134`, threshold at `:143`) triggers `flushLargestMemtable` (`AbstractAllocatorMemtable.java:249`) well before the hard limit.
3. Back in `SlabAllocator`, sizes above `MAX_CLONED_SIZE` go straight to `ByteBuffer.allocate` or `allocateDirect` (`:92-100`), counted in `unslabbedSize`. The region logic is bypassed.
4. Otherwise `getRegion()` (`:126-153`) returns the current region or allocates a new `REGION_SIZE` one (`:139`). The loser of a CAS race parks its region in the static `RACE_ALLOCATED` queue (`:55,151`).
5. `Region.allocate(size)` (`:197-206`) does `nextFreeOffset.getAndAdd(size)` (`:199`). The check at `:201` returns null when `newOffset + size > capacity`.
   - The offset has already advanced, so the failing call permanently consumes the tail. The region is dead.
   - The caller then `compareAndSet(region, null)` on `currentRegion` (`:112`) and loops to `getRegion()`.
6. Outcome of line 201: false means the slice is carved out; true means a new 1 MiB region is allocated and the unused tail of the old one is wasted.

**Overshoot and bypass paths.**
- Tail waste is uncharged. The pool sees `size` per call, never `REGION_SIZE`, so real bytes minus accounted bytes equals the retired tails plus the unused part of the live region. For sizes of at most 128 KiB the tail is at most about 1/9 of a region. With 116509-byte values, 8 fit and 116504 bytes are left over, so real/accounted is about 1.125.
- The `isBlocking()` bypass at `MemtableAllocator.java:180` overshoots the limit.
- `setDiscarded` (`SlabAllocator.java:116-121`) frees off-heap regions only when the memtable is discarded after flush. On-heap regions wait for GC.
- `RACE_ALLOCATED` is static and shared across all allocators. Regions parked there are real memory not charged to any memtable.
- Allocations above 128 KiB are charged but live outside regions (`:92-100`).

**A4. Other consumers.**
- Heap: row and partition objects, BTree/Trie structures, key caches, the chunk cache and request buffers. For `heap_buffers` the slab covers only cloned byte buffers, not the memtable's object overhead.
- Direct memory: `BufferPool`, the chunk cache, compression buffers and netty buffers, all outside the memtable pool.
- `offheap_objects` uses `NativePool` (`AbstractAllocatorMemtable.java:107`), which does not use `SlabAllocator` at all.

**A5. Evidence beyond the source.** None used. Everything above comes from the pinned tree.

## B. Verification solution

**B1. Claim under test.** The 1 MiB region capacity checked at `SlabAllocator.java:201` does not bound the memory a node uses for memtable slabs. Real heap or direct bytes held by slab regions track the number of regions created, which is driven by the `memtable_*_space` accounting of requested bytes. They exceed the accounted bytes by the uncharged tail waste, by a factor that depends on value size and not on any limit. The estimate is negative, so the test looks for usage not following `REGION_SIZE`.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11, Ant. Copy the source tree to local disk and work only there (**amended 2026-10-26**: `copy-source.sh ~/s4-b7-sr7`, then `ant jar` in the copy; the copy stays stock).
- **Amended 2026-10-26.** One standalone probe class, `SlabWasteProbe` (package `org.apache.cassandra.utils.memory`, so it reaches the package-private members), compiled outside the tree against `build/classes/main` and run with `java`. It replaces the JUnit class: `ant testsome` forks a 1 GiB JVM and compiles every copied test. Run options: `-Xmx1g -XX:MaxDirectMemorySize=1g`, one scenario per JVM.
- **Amended 2026-10-26: how `REGION_SIZE` is varied.** The constant is a `private static final int` initialised by a compile-time expression, so the value is inlined into `SlabAllocator` only. For each variant the audit-time harness copies `SlabAllocator.java` outside the tree, edits line 51 to `512 * 1024` or `2 * 1024 * 1024`, compiles that one file into its own class directory and puts the directory ahead of `build/classes/main` on the class path. This is the same class a rebuild would produce, with no rebuild; the probe reads the loaded value of `REGION_SIZE` by reflection and prints it, and the harness checks the edit with `diff`.
- Build the pool with `AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal(type, heapLimit, offHeapLimit, 0.99f, cleaner)` (`:89`, public, `@VisibleForTesting`). The cleaner is a throttled stub returning a completed future (an unthrottled stub is called in a tight loop while `needsCleaning()` holds). For `offheap_buffers`, `heapLimit` = 2 GiB and `offHeapLimit` = L; for `heap_buffers`, `heapLimit` = L and `offHeapLimit` = 0 (`SlabPool.java:31-33` sets `allocateOnHeap = maxOffHeapMemory == 0`).
- Get an allocator with `pool.newAllocator("t")`. This gives a `SlabAllocator` for `heap_buffers` and `offheap_buffers`.

**B2b. Knobs.**
- Value size `S`: 116509 (about 1 MiB/9, the worst fit under 128 KiB), 131072 (exact fit, 8 per region, no waste), 100000 (10 fit, waste 48576 B, 4.6%), 4096 (256 per region, tests the partly filled last region), and 131073 (just over `MAX_CLONED_SIZE`, so unslabbed).
- Allocation type: `heap_buffers` and `offheap_buffers`.
- Pool limit `L`: 64 MiB and 128 MiB (the real cap, as positive control).
- `REGION_SIZE`: 512 KiB, 1 MiB (stock, the default) and 2 MiB, by the class-directory method of B2a. Used for S = 116509 and 100000.
- Each of these values is set in the test code or by the class directory.

**B2c. Workload.**
- One thread calls `allocator.allocate(S, group)` N times, where `group` comes from `new OpOrder().start()`.
- Waste measurement (**amended 2026-10-26: N = 400 for every S, pool limit 2 GiB, so the limit is not reached**): N = 400 at S = 116509 is accounted 46.6 MB, under any L of the limit test. Per region, floor(1048576/116509) = 9, but 9 x 116509 = 1048581 > 1048576, so 8 fit. Regions = 400/8 = 50, real = 50 x 1048576 = 52.4 MB, accounted 46.6 MB, ratio about 1.125.
- Limit test (**amended 2026-10-26**: the original N = 700 never reaches L = 128 MiB, which would make the positive control look dead). Worker thread, S = 116509, N = 1400 (163 MB, above both limits), 5 s join timeout, at L = 64 MiB and at L = 128 MiB; also S = 131072, N = 700 at L = 64 MiB (exact fit) and one `heap_buffers` run at L = 64 MiB, S = 116509. The worker should stall in `tryAllocate`/`SubAllocator.allocate`, not at `:201`; its stack is printed.
- Eight-thread run (B2h, amended 2026-10-26): 8 threads x 50 allocations of S = 116509 on one allocator, repeated for 20 fresh allocators in one JVM (pool limit 2 GiB); the static `RACE_ALLOCATED` queue size is read by reflection after each round.

**B2d. Observables and instruments.**
- Accounted bytes: `allocator.offHeap().owns()` or `onHeap().owns()` (`MemtableAllocator.java:280`), and `pool.offHeap.used()`.
- Real region count: reflection on the private `regionCount` (`SlabAllocator.java:58`). Real bytes = regionCount x REGION_SIZE, plus `unslabbedSize` (`:62`).
- Independent check for off-heap: `BufferPoolMXBean` named "direct" (`ManagementFactory.getPlatformMXBeans`), `getMemoryUsed()` before and after. For on-heap: `Runtime.totalMemory() - freeMemory()` after `System.gc()`, coarse and secondary.
- Not observable directly: the wasted tail per region. It is derived as real minus accounted, or from `Region.toString()` (`:208-213`), which prints the waste.

**B2e. Procedure.**
1. Build as in B2a.
2. For each (type, S, L): create the pool, create the allocator, read the baselines (direct pool usage, regionCount = 0).
3. Allocate N values of size S, then record owns(), pool.used(), regionCount, unslabbedSize, and the direct-pool delta.
4. Compute real = regionCount x 1048576 and ratio = real / owns().
5. Run the limit test of B2c and record whether the thread is blocked and where (thread dump).
6. Call `allocator.setDiscarding(); allocator.setDiscarded()` and confirm the direct delta returns to baseline for off-heap.
7. Repeat steps 2-4 with the 512 KiB and 2 MiB class directories (B2a) for S = 116509 and 100000.
8. **Amended 2026-10-26: first-trigger and instrument checks.** The first run is S = 116509 on the stock build; if its regionCount is not 50 the script stops. A known-answer run (L = 4 MiB, S = 116509, 1024 x 1 KiB) is checked by hand before run 1; none of these is a reading.

**B2f. Predictions (before any run).** *Rewritten 2026-10-26 in the step-0 audit, before any reading: the original numbers are replaced by the exact replay of the rule of `Region.allocate` (script `replay.py` in the harness folder, run before any probe). Changes: 2 MiB, S = 116509 gives 24 regions (the last holds 9 of 17), ratio 1.0800, not 1.059; the limit test needs N = 1400; S = 4096, the eight-thread run and heap rows added.* Single thread, N = 400, `offheap_buffers`; "real" = regionCount x REGION_SIZE (+ `unslabbedSize` for oversize), "owns" = N x S:

| REGION_SIZE | S | regionCount | real (B) | owns (B) | real/owns |
|---|---|---|---|---|---|
| 1 MiB | 116509 | 50 | 52,428,800 | 46,603,600 | 1.12499 |
| 1 MiB | 131072 | 50 | 52,428,800 | 52,428,800 | 1.00000 |
| 1 MiB | 100000 | 40 | 41,943,040 | 40,000,000 | 1.04858 |
| 1 MiB | 4096 | 2 | 2,097,152 | 1,638,400 | 1.28000 |
| 1 MiB | 131073 | 0 | unslabbed 52,429,200 | 52,429,200 | 1.0 (no region) |
| 512 KiB | 116509 | 100 | 52,428,800 | 46,603,600 | 1.12499 |
| 512 KiB | 100000 | 80 | 41,943,040 | 40,000,000 | 1.04858 |
| 2 MiB | 116509 | 24 | 50,331,648 | 46,603,600 | 1.07999 |
| 2 MiB | 100000 | 20 | 41,943,040 | 40,000,000 | 1.04858 |

- The pool's accounted bytes (`owns`, and `pool.offHeap.used()`) equal N x S exactly, independent of REGION_SIZE; `onHeap` stays 0 for `offheap_buffers`. The `BufferPoolMXBean` "direct" delta equals real exactly (1 MiB region = one direct buffer), so the count delta is regionCount (50, 50, 40, 2, 0 + 400 dedicated buffers for 131073).
- For fixed N and S, real does not follow REGION_SIZE: 512 KiB / 1 MiB / 2 MiB give 52.4 / 52.4 / 50.3 MB at S = 116509 (ratio 2 MiB to 512 KiB: 0.960) and 41.9 MB at all three at S = 100000 (ratio 1.000). The ratio real/owns depends on how S divides REGION_SIZE; the accounted bytes never change.
- Limit test, `offheap_buffers`, worker stalls in `SubAllocator.allocate` (`MemtableAllocator.java:195`): S = 116509, L = 64 MiB: 575 allocations succeed (owns 66,992,675), 72 regions, real 75,497,472 = 1.125 L exactly; L = 128 MiB: 1151 succeed (134,101,859), 144 regions, real 150,994,944 = 1.125 L. S = 131072, L = 64 MiB: 512 succeed (67,108,864 = L), 64 regions, real = L. Raising L from 64 to 128 MiB moves the stall from the 576th to the 1152nd allocation and leaves real/L at 1.125.
- `heap_buffers`, S = 116509, L = 64 MiB: the on-heap counter stalls at the same 575 allocations (66,992,675), `offHeap` stays 0, the direct delta stays 0, and the retained heap (`Runtime` used after two `System.gc()`, delta over the baseline) lies within 3 MiB of real (72 MiB).
- Eight threads (20 rounds, 400 allocations of 116509 per round): owns per round = 46,603,600 exactly; regionCount per round = 50 (each installed region takes exactly 8 allocations, because only a full region is retired); the direct delta of the whole JVM = (sum of regionCount + final `RACE_ALLOCATED` size) x 1 MiB, so any parked region is real memory that no allocator charged or counts.
- After `setDiscarding(); setDiscarded()` of the 400 x 116509 allocator the direct delta returns to the stash size x 1 MiB (the regions of an allocator are cleaned; stashed regions are not).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| owns() = N x S for every S and REGION_SIZE, regionCount and real match the B2f table, and real/owns varies with S and REGION_SIZE only through the division | claim confirmed on accounting: accounting ignores region size; REGION_SIZE shapes the waste, not a cap |
| Stall at about L accounted bytes (575 / 1151 allocations) while real bytes are above L (72 MiB / 144 MiB, ratio 1.125) | claim confirmed: the limit binds the requested bytes, and real use overshoots it |
| Accounted stall point moves with L (64 to 128 MiB) while REGION_SIZE changes do nothing to it (positive control moved, constant did not) | claim confirmed |
| Real bytes at stall are below or equal to L under every S | claim refuted: the region check would then be bounding real use |
| Real bytes grow with REGION_SIZE at fixed N and S in proportion (2 MiB / 512 KiB real ratio at or above 3.0) | claim refuted: usage follows the constant |
| owns() changes when REGION_SIZE changes | claim refuted: accounting depends on region size |
| Worker never stalls, or the limit control does not move the stall point | not confirmed (the limit was not reached, or the control did not work) |
| Ratio equals 1.000 for every S tested | not confirmed: no waste case was exercised, so the overshoot half is untested |
| regionCount or real differs from the B2f table, or the direct delta differs from real by more than 1 MiB | not confirmed (no matching row): the replay or the instrument is wrong; real use is not settled until explained |
| Eight-thread direct delta differs from (sum of regionCount + stash) x 1 MiB | not confirmed: parked-region accounting not understood |

**B2h. Controls.**
- Positive control: L = 64 vs 128 MiB moves the stall point, so a cap that binds is visible with the same workload.
- S = 131072 shows zero waste, which separates waste from the baseline.
- S = 131073 shows the unslabbed path, so the region count is not the only memory.
- A single-thread run avoids `RACE_ALLOCATED` noise. A second run with 8 threads checks that parked regions are real but uncharged.
- Run both allocation types, so the same code is checked on-heap and off-heap.

### B3. Cluster tier

**B3a. Environment and build.**
- One node, Linux, JDK 11, Ant. **Amended 2026-10-26:** `copy-source.sh ~/s4-b7-sr7`, then `ant jar` there; run from that copy with `bin/cassandra`. Port slot 5: loopback 127.0.5.1, storage 7000, native 9042, JMX 7150.
- Data, commit log, hints and saved caches under the tmpfs `/dev/shm/s4-b7-sr7/{data,commitlog,hints,saved_caches}` (wiped per lifetime; 126 GiB tmpfs).
- JVM: `MAX_HEAP_SIZE=2G` (**amended 2026-10-26**: `HEAP_NEWSIZE` dropped, the server uses G1); `-XX:MaxDirectMemorySize=2g`; `-XX:NativeMemoryTracking=summary` (secondary only: NMT counts `Unsafe` direct buffers under "Other").
- cassandra.yaml: `memtable_allocation_type: offheap_buffers`, `memtable_offheap_space: 64MiB`, `memtable_heap_space: 256MiB`, `concurrent_compactors: 1`. **Amended 2026-10-26:** `memtable_flush_writers: 1` and `memtable_cleanup_threshold: 0.99` (the maximum `DatabaseDescriptor.java:772-773` accepts) replace the defaults (2 writers, threshold 1/3), because at 1/3 the cleaner flushes at about 21 MiB of the 64 MiB limit and the limit is never reached; `commitlog_total_space: 4096MiB` replaces 512MiB so that the commit log does not force the flushes; `file_cache_size: 64MiB`, `key_cache_size: 0MiB`, `row_cache_size: 0MiB`, `compaction_throughput: 16MiB/s`, `write_request_timeout: 30000ms`, `native_transport_timeout: 60000ms`.
- Keep reads off during the test so the chunk cache does not add to direct memory; the baseline is read before the workload and subtracted.

**B3b. Knobs.** (*Amended 2026-10-26: arm list.*)
- `memtable_offheap_space`: 64 MiB and 128 MiB (the known cap, also the positive control).
- Value size `S`: 116509 B (worst fit: 8 rows of 116513 B per region), 131068 B (exact fit: row = 4 B partition key + S = 131072 B, 8 per region) and 131072 B (one more than the exact fit: row 131076 B, 7 per region, ratio 1.143). The int partition key is cloned into the same region (`SkipListMemtable.java:115` through `ByteBufferCloner`), so a row costs S + 4 bytes of region space and of accounted bytes. The original text took S = 131072 as the exact fit; that holds for one allocation, not for a row.
- `memtable_allocation_type`: `offheap_buffers` for the main measurement. `heap_buffers` is a secondary run, using `memtable_heap_space` 64 MiB.
- Arms (one node lifetime each): `a64` (L 64, S 116509), `a128` (L 128, S 116509), `a64b` (repeat of a64, the noise estimate), `e64` (L 64, S 131068), `f64` (L 64, S 131072), `h64` (`heap_buffers`, heap space 64 MiB, S 116509). The original plan of two runs per setting is cut to one repeat (`a64b`) for session length.
- All are yaml keys set before the start; each change needs a restart. `REGION_SIZE` stays at 1 MiB (cluster tier does not rebuild it).

**B3c. Workload.**
- Table `CREATE TABLE ks.t (k int PRIMARY KEY, v blob)` with `compaction = {'class':'SizeTieredCompactionStrategy'}`, `compression = {'enabled': false}` and `caching = {'keys':'NONE','rows_per_partition':'NONE'}`; `nodetool disableautocompaction ks t` after creation (**amended 2026-10-26**, so that compaction reads add no direct buffers).
- Inserts via the bundled Python driver (protocol 4: large native-v5 requests leave unreturned direct frame buffers), one connection, 16 requests in flight, unique key `k = 1..rows`, value `v` of S bytes (one random buffer with a distinct 8-byte prefix per row), at `CL ONE`.
- Count (**amended 2026-10-26, twice**): the same two phases in every arm. Phase A: 3000 rows throttled to 50 rows/s (60 s, 5.8 MB/s at S = 116509: 350 MB, 5.2 x the 64 MiB limit and 2.6 x the 128 MiB limit). Phase B: 2000 rows unthrottled, 16 in flight (233 MB, 3.6 x 64 MiB and 1.8 x 128 MiB), keys continuing from phase A. Reason, found in a shakedown before any reading and checkable from the source: the gauge `AllMemtablesOffHeapDataSize` covers only the table's *current* memtable (`TableMetrics.getMemoryUsageWithIndexes` uses `getCurrentMemtable()`), so while a switched memtable is still being flushed its regions are in the direct reading and not in the gauge. An unthrottled writer fills 0.09 L in about 40 ms and overlaps flushes, which would inflate every direct/accounted ratio; at 50 rows/s the flush (a fraction of a second) is over long before the live memtable is back at 0.9 L, so phase A gives clean samples. Phase B is where writers block (the disallow evidence).
- The allocator is called with the cell value (S bytes) and the partition key (4 B) per row; clustering and cell path are empty (size 0, no allocation).
- Duration: a few minutes at the observed insert rate. Add 10 s idle at the end, then `nodetool flush ks t` and 15 s.

**B3d. Observables and instruments.** (*Amended 2026-10-26: sampling and reading rules, fixed before run 1.*)
- Real direct memory: JMX `java.nio:type=BufferPool,name=direct` `MemoryUsed` (exact for `allocateDirect`), polled every 200 ms together with the gauges; `RssAnon` from `/proc/<pid>/status` every 200 ms as the independent reading of real memory (the lesson of the memtable-offheap sibling: NMT misses non-JDK allocation; here NMT "Other" is only a secondary 5 s cross-check). The JVM heap is pre-touched (`-XX:+AlwaysPreTouch`), so `RssAnon` moves with direct and native memory only.
- Real heap, for the `h64` arm: `jcmd <pid> GC.class_histogram` taken once when the on-heap gauge first reaches 0.9 of the heap space, with the gauge read before and after it; `[B` total minus the same total at the baseline.
- Accounted memory: JMX `org.apache.cassandra.metrics:type=Table,name=AllMemtablesOffHeapDataSize` (and `...OnHeapDataSize`), `type=MemtablePool,name=BlockedOnAllocation` `Count`, every 200 ms (`metrics/TableMetrics.java:489-499`).
- Flush activity: `Enqueuing flush of ks.t, Reason: MEMTABLE_LIMIT` lines in `system.log`.
- Definitions. `acc(t)` = the AllMemtablesOffHeapDataSize sample (the live memtable only, see B3c); `dir(t)` = direct MemoryUsed minus its baseline (23 s after the node serves, after two `GC.run`); `peak_acc`, `peak_dir` and the RssAnon peak = the maxima over **phase A** (B3c); `rho` = the median of `dir(t)/acc(t)` over the phase-A samples with `acc(t)` at or above 0.9 L. Phase B maxima are reported but not used in a relation (flush overlap). Blocked count and flush lines are read over both phases. Not directly observable in the cluster tier: the region count (the unit tier reads it).

**B3e. Procedure.**
1. Build and configure as in B3a. Start the node and wait until the client port answers.
2. Read the settings back from `system_views.settings`; wait 20 s, two `GC.run`, record the baselines of BufferPool `direct` MemoryUsed, RssAnon and NMT.
3. Create keyspace `ks` (`SimpleStrategy`, RF 1) and table `t`; disable autocompaction on it.
4. Start the 200 ms pollers (JMX reads and RssAnon to CSV on local disk).
5. Run the insert workload of B3c (phase A, then phase B). First-trigger check: the accounted gauge must reach 1 MiB within 90 s, else stop.
6. Wait 10 s, run `nodetool flush ks t`, wait 15 s, stop the pollers.
7. For each arm of B3b: stop the node, remove its data and commit log, change the yaml, restart and repeat steps 2-6. Order: `a64`, `a128`, `e64`, `f64`, `a64b`, `h64`.
8. Stop the node (SIGTERM to its PID), check that no `CassandraDaemon` of this harness is left, delete the tmpfs directory.

**B3f. Predictions (before any run).** *Rewritten 2026-10-26 in the step-0 audit, before any reading, from the replay in `replay.py` (4000 rows, key 4 B + value S in one region sequence).* Every figure is for `offheap_buffers` unless stated:
- Replay of the region rule for the workload: S = 116509 gives 8 rows per region (932,104 B), 500 regions for 4000 rows, real/charged = 1.12496; S = 131068 gives exactly 8 rows per region, 500 regions, 1.00000; S = 131072 gives 7 rows per region, 572 regions, 1.14397 (steady state 1.14282).
- Disallow evidence: in the arms `a64`, `a128`, `a64b`, `e64`, `f64` the `BlockedOnAllocation` count grows and `system.log` holds at least 2 `Enqueuing flush of ks.t, Reason: MEMTABLE_LIMIT` lines.
- `peak_acc` follows the knob: in [0.90 L, 1.05 L] for every offheap arm; `peak_acc(a128) / peak_acc(a64)` in [1.8, 2.2].
- Real follows the accounted bytes, not a region constant: `rho` in [1.10, 1.20] for `a64`, `a128`, `a64b`; in [0.97, 1.07] for `e64`; in [1.11, 1.20] for `f64`. The bands for `e64` and `a64` do not overlap. `peak_dir(a64)` is above L (64 MiB) because of the waste. `peak_dir(a128) / peak_dir(a64)` in [1.7, 2.3]; `RssAnon` peak delta ratio in [1.5, 2.5]; `RssAnon` peak delta in [0.9 x peak_dir - 4 MiB, peak_dir + 0.25 L + 32 MiB] for every arm.
- Repeat noise: `a64` and `a64b` agree on `peak_acc` within 0.05 L and on `rho` within 0.03.
- After the final flush, the accounted gauge is below 1 MiB and direct memory falls back toward the baseline (`dir` below 0.1 L after 15 s).
- `h64` (`heap_buffers`, heap space 64 MiB): the direct delta stays below 8 MiB, the off-heap gauge stays below 1 MiB, `AllMemtablesOnHeapDataSize` peaks in [0.90, 1.05] x 64 MiB with `BlockedOnAllocation` growth, and the `[B` growth in the histogram is in [0.9, 1.3] x the mean of the on-heap gauge before and after the histogram.
- A sustained rise of `peak_dir` past 1.20 x `peak_acc` + 8 MiB would contradict the claim that the waste is bounded by the fit of S (the sizes tested are slab-eligible).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `peak_acc` doubles with the limit (`a128` / `a64` in [1.8, 2.2]), each in [0.90 L, 1.05 L], blocked count grew and at least 2 MEMTABLE_LIMIT flushes in each arm; `rho` about 1.125 at S = 116509 and about 1.0 at S = 131068 (bands of B3f) | claim confirmed: the limit binds requested bytes, and real use overshoots by size-dependent waste, not by a constant (the region size) |
| `rho` or `peak_dir` above the limit at S = 116509 | confirms the overshoot path (part of the row above) |
| `rho` at S = 131068 is 1.10 or more | no matching row for the exact-fit prediction: the replay of the row layout is wrong (not confirmed) |
| `peak_dir` follows 1 MiB steps independent of limit or S (e.g. flat across `a64`, `a128`) | claim refuted: usage follows the region size |
| `peak_dir` stays at or below the limit for every arm (`rho` at most 1.05 everywhere) | claim refuted for this workload: waste is not visible, so check whether values were really slab-allocated |
| Doubling the limit leaves `peak_acc` unchanged (`a128` / `a64` outside [1.8, 2.2], or `peak_acc` outside [0.90 L, 1.05 L]) | positive control failed; not confirmed |
| `peak_acc` below 0.9 L in every arm, or no `BlockedOnAllocation` growth (cleanup flushes first and the limit is never approached) | limit never reached; not confirmed. Raise the row count or use fewer flush writers |
| `h64`: `[B` growth in [0.9, 1.3] x on-heap gauge, direct delta below 8 MiB | supports the claim for the on-heap path (secondary; its failure alone does not change a tier row) |
| Any other combination | not confirmed (no matching row) |

**B3h. Controls.**
- The positive control is `memtable_offheap_space` 64 vs 128 MiB with the same workload. This is a cap known to bind (`MemtablePool.java:156`).
- The S = 131068 run `e64` (exact fit, no waste) separates waste from the baseline (**amended 2026-10-26**: with the 4-byte key, S = 131072 is not an exact fit; `f64` shows that).
- Baseline direct memory is read before the workload and subtracted. No reads are issued.
- **Amended 2026-10-26:** the repeat is `a64b` (one repeat of `a64`) for the spread. A forced flush at the end checks that memory is released.
- Cross-check the cluster reading against the unit tier ratio for the same S (1.125 at S = 116509).

**B4. Risks and cleanup.**
- Disk: the commit log is capped at 512 MiB and the data is under 1 GB per run; everything sits on local disk in `/local/$USER/`, never on shared storage and never in the shared source tree.
- Memory: the node runs with a 2 GB heap and a 2 GB direct cap; use a machine with at least 6 GB free.
- Both tiers build only in local copies (**amended 2026-10-26**: one stock copy `~/s4-b7-sr7`; the probe and the `REGION_SIZE` variants are compiled outside it, under `~/s4-b7-sr7-logs`).
- Cleanup (**amended 2026-10-26**): stop the node by its PID; check that no `java` of this harness is left (`ps`, matching `s4-b7-sr7`); remove `/dev/shm/s4-b7-sr7`.

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/utils/memory/SlabAllocator.java`
- `src/java/org/apache/cassandra/utils/memory/SlabPool.java`
- `src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java`
- `src/java/org/apache/cassandra/utils/memory/MemtablePool.java`
- `src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java` (lines 60-130, 249)
- `src/java/org/apache/cassandra/config/Config.java` (grep of memtable keys)
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (grep of memtable keys)
- `src/java/org/apache/cassandra/utils/concurrent/OpOrder.java` (`isBlocking`)
- `src/java/org/apache/cassandra/metrics/TableMetrics.java` (memtable size gauges)
- `conf/cassandra.yaml` (grep of memtable keys)

## D. Stage-4 feedback

**Result, 2026-10-26** ([results](../../stage4-runtime-verification/results/slab-region-size-region-allocate-capacity--autonomous.md), run 1 only, self-checked): unit **Confirmed** — does not cap; cluster **Confirmed** — does not cap; outcome class true negative. Accounted bytes were N x S in every build; real bytes followed how S divides the region (1.125 / 1.000 / 1.049 / 1.28) and moved at most 4 percent across a 4x change of `REGION_SIZE`; the pool limit set the stall (575 to 1151 allocations when L doubled) with real memory at 1.125 L; in the cluster the accounted peak was 0.99 L and doubled with `memtable_offheap_space` while direct memory sat 5 to 19 percent above it. Three secondary sub-predictions missed (reported in the results file): `heap_buffers` retained heap is 2.0 times real under G1 with 1 MiB regions (humongous allocation); `h64` `[B` relation; f64 rho 1.210 against a band to 1.20. Notes for stage 3: `AllMemtablesOffHeapDataSize` covers the current memtable only; a row's partition key is cloned into the same region as its value.

**Step-0 audit amendments, 2026-10-26** (stage-4 session `sr7`; made before any reading; marked in place). Reasons that depend on no reading:
1. B3a: `memtable_cleanup_threshold` 1/3 with 2 flush writers flushes at about 21 MiB of the 64 MiB limit, so the limit is never reached; set to 0.99, flush writers 1, commit log 4096MiB.
2. B3b/B3f: a row is the partition key (4 B, cloned into the same region by `SkipListMemtable.java:115`) plus the value, so S = 131072 is not an exact fit in the cluster tier (7 rows per region, ratio 1.143); the exact fit is S = 131068. Arms `e64` and `f64` added.
3. B2f: 2 MiB, S = 116509, N = 400 gives 24 regions (the last partly filled), ratio 1.0800, not 1.059; exact replay table replaces the approximate figures; S = 4096, heap and eight-thread rows added.
4. B2c: the limit test with N = 700 never reaches L = 128 MiB (stall at the 1152nd allocation); N = 1400.
5. B2a: the JUnit class and the rebuild per `REGION_SIZE` are replaced by a standalone probe and one-file class directories (same class, no rebuild).
6. B3d/B3g: reading rules (`rho`, `peak_acc`, `peak_dir`), RssAnon as the independent reading, bands and the disallow evidence (blocked count, MEMTABLE_LIMIT flushes) made exact; B3g gets a row for a missed prediction.
6b. B3c/B3d (second amendment, same day, after a shakedown that read no capacity value): the table gauge covers the live memtable only (source: `TableMetrics.java:876-883`), so the workload is split into a throttled phase A and an unthrottled phase B, and the relations use phase A (B3c, B3d). B3f and B3g are unchanged by this; the frozen hash of the prediction and conclusions text did not change.
7. Citation nits (no effect): `allocate` in `MemtableAllocator` is `:169-196`; `NativePool` is created at `AbstractAllocatorMemtable.java:108`.

**Recheck claim, 2026-11-17** ([results](../../stage4-runtime-verification/results/slab-region-size-region-allocate-capacity--autonomous--recheck-2026-11-17.md), one node pc91, run 1 + self-check): **Not confirmed (no matching row)**, Effect undetermined by rule; every relation of the claim held (1.0000 MiB `[B` per table given one 1 KiB write against 1.49 KiB counted, N = 200: 199.95 MiB vs 0.29 MiB; flat across `memtable_heap_space` 64/256/2048 MiB; 992 B per table under `unslabbed_heap_buffers`; positive control flushed only `t0`), but the frozen P4 bound on the global gauge (1.28 MiB) missed at 3.30 MiB, 2.13 MiB of it system tables before any write.


## Recheck — enforcement properties (guided, 2026-11-17, blind)

| Field | Content |
|-------|---------|
| **E1 Counted quantity** | The pool is charged the requested `size` per clone (`SlabAllocator.java:89`); the real unit is a 1 MiB region (`:51`, `:139`). Uncharged: each retired region's tail (`:199-203`, offset advanced before the fit test; up to 1/9 for slab sizes, stage 4: real 1.125 x accounted at S = 116509) and the unused part of every memtable's live region. Released: the charge at memtable discard; off-heap regions are cleaned at `setDiscarded` (`:116-121`), on-heap ones at the next GC. Under G1 with 1 MiB heap regions a `heap_buffers` slab is humongous (stage 4: 2.0 x), but the shipped options set `-XX:G1HeapRegionSize=16m` (`conf/jvm11-server.options:63,66`, `jvm17-server.options:33,36`), so that doubling is not a default. |
| **E2 At the limit** | `:201` only retires the region and takes a new one. The pool limit is graceful on accounted bytes: `tryAllocate` refuses at `allocated + size > limit` and the writer blocks (`MemtableAllocator.java:185-195`); a blocking `opGroup` bypasses and overshoots (`:180`); real memory at the stall is accounted x waste factor (1.125 L measured). |
| **E3 Owner and multiplier** | One `SlabAllocator` per memtable (`AbstractAllocatorMemtable.java:118`), so one live region per table (and per 2i, system tables included) written since its last flush; one node pool caps the accounted sum, nothing caps the regions. A table with a 1 KB write pins a 1 MiB region charged 1 KB. The cleaner flushes the largest memtable, so small ones keep their region until commit-log pressure. The table-count guardrail is off by default (`Config.java:865-866`). |
| **E4 Budget domain** | Default `heap_buffers` (`conf/cassandra.yaml:825`) → `SlabPool(heapLimit, 0)` (`AbstractAllocatorMemtable.java:100-102`): on-heap regions charged to `memtable_heap_space` = heap/4 by default (`DatabaseDescriptor.java:586-587`), sharing the heap with caches, request objects and the row/partition objects. `offheap_buffers` moves regions to direct memory, charged to `memtable_offheap_space` (also heap/4), alongside the other direct pools. |
| **OOM-lead flag** | E3: per-memtable live 1 MiB region is uncharged beyond the bytes written, multiplied by every table/index memtable written since its last flush with no cap — ~1 MiB x written tables (e.g. 300 tables ≈ 300 MiB on heap outside `memtable_heap_space`), on top of the measured ≤12.5 % tail waste (≈ heap/32 at the default heap/4 limit). |

**Real-memory estimate:** same as Estimate (negative: `REGION_SIZE` is not a cap); the real-vs-accounted gap is positive and decided by E3 (number of memtables holding a live region).
**Stage-4 claim to add:** With default `heap_buffers` and N tables each given one 1 KB write (no flush), retained `[B` heap rises by about N x 1 MiB while `MemtablePool` on-heap `used` rises by about N x 1 KB (plus row overhead); N = 200 gives ~200 MiB against ~0.3 MiB accounted.

## Stage-4 design for the recheck claim (2026-11-17)

Written by the stage-4 session of 2026-11-17 (one node, `pc91`) for the **Stage-4 claim to add** of the recheck above. Results: `../../stage4-runtime-verification/results/slab-region-size-region-allocate-capacity--autonomous--recheck-2026-11-17.md`. Nothing above this section is changed by it.

**How this verifies the claim.**
- *Hypothesis (the claim).* With the shipped `memtable_allocation_type: heap_buffers`, each table that receives one small write (no flush) pins one 1 MiB on-heap slab region (`SlabAllocator.java:139`, one allocator per memtable at `AbstractAllocatorMemtable.java:118`, region taken lazily at the first clone), while the memtable pool is charged only the cloned bytes plus row overhead (`SlabAllocator.java:89`, `SkipListMemtable.java:124-125`, `BTreePartitionUpdater.java:182`). So retained `[B` heap rises by about N x 1 MiB for N written tables while the accounted on-heap bytes rise by about N x 1 to 3 KiB; N = 200 gives about 200 MiB against about 0.3 MiB.
- *Test.* One node per lifetime; create 401 tables up front; write one 1 KiB row into 50, 100, 200, 400 of them cumulatively, and at each step read the live `[B` bytes from a class histogram (full GC) next to the accounted on-heap gauge. Vary `memtable_heap_space` (64 MiB, 256 MiB, shipped default heap/4 = 2048 MiB at the shipped 8 GiB heap); repeat the default with `unslabbed_heap_buffers` (no regions: `HeapPool`) as the matched control; a single table given 400 rows is the same-bytes control; in the 64 MiB lifetime a final fill of one table is the positive control (the pool limit binds on counted bytes and flushes).
- *Logic.* If real `[B` grows by about 1 MiB per written table under `heap_buffers`, not under `unslabbed_heap_buffers`, not when the same bytes go into one table, and the accounted gauge grows by only KiB per table, then the region bytes are real heap that the pool does not count; if the slope is the same for every `memtable_heap_space` and real passes the 64 MiB limit with no flush of the small tables, the pool limit does not cap them (it flushes only the table it counts as large: the positive control).
- *Refuted if* the `heap_buffers` `[B` slope is at most 0.10 MiB per table, or the accounted slope is at least 0.5 MiB per table (regions charged), or in the 64 MiB lifetime the small tables are flushed and real stays at or below the limit.

**Tier.** One node (cluster tier, single node). A unit tier is `n/a`: the claim is about tables on a node (one allocator per table memtable, no flush of small memtables, the shipped G1 options), which a probe of `SlabPool` would assume rather than test; the unit-level fact (a fresh allocator takes one 1 MiB region on its first clone) was already measured in the earlier stage-4 unit tier (`regionCount` 2 for 400 x 4096 B).

**Environment.** `pc91` (x86_64, 32 cores, 125 GiB), `cp -a /mydata/s4/cassandra-base /mydata/s4/slabrc` (Cassandra 5.0.9, JDK 11.0.33); conf copied to `/mydata/s4/slabrc-run/conf` with only: cluster name, `listen_address`/`rpc_address` 127.0.6.1, seeds 127.0.6.1, directories under `/mydata/s4/slabrc-run/`, the arm's `memtable_allocation_type` and `memtable_heap_space`, JMX port 7160 (local). Heap `MAX_HEAP_SIZE=8G` (*amended 2026-11-17, before any reading: the shipped 5.0.9 `cassandra-env.sh` sizes the heap at min(RAM/2, 31744 MiB with G1) = 31 GiB on this node, not 8 GiB; with the shipped `-XX:+AlwaysPreTouch` the first H2048 start was OOM-killed by the 12 GiB scope 7 s after launch, before the node served. 8 GiB keeps the default `memtable_heap_space` at the 2048MiB the predictions use; the predictions and conclusions are unchanged*). Everything else shipped: `jvm11-server.options` (G1, `-XX:G1HeapRegionSize=16m`, so a 1 MiB array is not humongous), `-XX:+AlwaysPreTouch`, `num_tokens` 16, flush writers 2, cleanup threshold 1/3. The node JVM runs in `systemd-run --user --scope -p MemoryMax=12G -p MemorySwapMax=0` (budget 12 GiB: pre-touched 8 GiB heap plus at most about 1 GiB of non-heap; the workload adds at most 0.42 GiB of heap inside the pre-touched heap).

**Lifetimes (arms).** `H2048` (`heap_buffers`, `memtable_heap_space` default, read back as 2048MiB), `H256` (`heap_buffers`, 256MiB), `H64` (`heap_buffers`, 64MiB), `U2048` (`unslabbed_heap_buffers`, default space). Order: H2048, U2048, H256, H64. The varied quantity is N (written tables: 0, 50, 100, 200, 400) inside each lifetime; `memtable_heap_space` (3 values including the default) across lifetimes.

**Workload** (bundled Python driver, protocol 4, CL ONE, 127.0.6.1:9042). Keyspace `ks` (SimpleStrategy RF 1); tables `ks.t0` .. `ks.t400`, each `(k int PRIMARY KEY, v blob)`, shipped table options, created one by one before any write. Value: 1024 random bytes. Steps, each followed by 10 s idle and the measurement M:
- `s0`: after the schema, 20 s idle, two `jcmd GC.run`; M (baseline).
- `c1` (same-bytes control): 400 rows into `t0` (k = 1..400); M.
- `s50`, `s100`, `s200`, `s400`: one row (k = 1) into each of `t1..t50`, `t51..t100`, `t101..t200`, `t201..t400` (cumulative N = 50, 100, 200, 400); M after each.
- `pc` (`H64` only, positive control): 40,000 more rows into `t0` (k = 401..40400, 32 in flight); wait until `PendingFlushTasks` is 0, 15 s idle; M.

**Measurement M** (the step's readings; the observables).
- Real (primary): two consecutive `jcmd <pid> GC.class_histogram` (each a full GC, live objects); the second gives `[B` bytes and instances and the histogram total. A 1 MiB region is one `byte[1048576]`, 1,048,592 B in the histogram.
- Real (secondary): JMX `java.lang:type=Memory` `HeapMemoryUsage.used` right after the histograms; cgroup `memory.current` of the scope (flat under pre-touch; recorded, not used in a relation).
- Counted: JMX global `org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize` (sum over every table of its memtable's `onHeap().owns()`; equal to the pool's on-heap `used` when no flush is in progress: the gap is named, the pool has no gauge of its own) and `...AllMemtablesOffHeapDataSize`; per table `type=Table,keyspace=ks,scope=t*,name=MemtableOnHeapDataSize` (count of `ks` tables with a value above 0, and their sum).
- Flushes: `Enqueuing flush of ks.` lines in `system.log` (with reason), counted per step.
- Definitions: `R(N)` = `[B` bytes at step `sN` minus at `c1`; `A(N)` = global on-heap gauge at `sN` minus at `c1`; `slope_R`, `slope_A` = least-squares slopes over N = 0 (`c1`), 50, 100, 200, 400; `Rc` = `[B` at `c1` minus at `s0`, `Ac` likewise.

**Predictions (frozen before any run).**
- P1 (`H2048`, `H256`, `H64`): `slope_R` in [0.95, 1.10] MiB per table; `R(200)` in [190, 225] MiB; `R(400)` in [380, 445] MiB.
- P2 (same lifetimes): `slope_A` in [1.0, 3.0] KiB per table; `A(200)` in [0.2, 0.6] MiB; `R(200) / A(200)` at least 300.
- P3: the three `heap_buffers` `slope_R` agree within 5 % (max/min at most 1.05): real does not follow `memtable_heap_space`.
- P4 (`H64`): `R(400)` above 64 MiB (predicted about 6.3 x the limit) while the global gauge at `s400` is below 0.02 x 64 MiB, and no `ks.` flush line before `pc`.
- P5 (`U2048`, matched control): `slope_R` at most 16 KiB per table; `slope_A` in [1.0, 3.0] KiB per table.
- P6 (same-bytes control): `heap_buffers` lifetimes `Rc` in [0.9, 2.5] MiB and `Ac` in [0.4, 1.2] MiB (400 rows, one region); `U2048` `Rc` in [0.2, 1.5] MiB.
- P7 (`H64`, positive control): at least 1 `Enqueuing flush of ks.t0, Reason: MEMTABLE_LIMIT`; 0 flush lines for `t1..t400`; all 400 small tables still hold a memtable gauge above 0 after `pc`; the global gauge after `pc` at most 0.40 x 64 MiB; `[B` at `pc` minus `[B` at `s400` in [-2, 30] MiB.
- Validity (every lifetime): settings read back as set (`memtable_allocation_type`, `memtable_heap_space`); JVM flags hold `-XX:G1HeapRegionSize=16m` and `-XX:+UseG1GC`; the scope's `memory.max` is 12 GiB; the count of `ks` tables with gauge above 0 equals N + 1 at every step `c1`..`s400`; no `ks.` flush line before `pc`; client errors 0; no `^ERROR` line in `system.log`; the node is not killed.

**Conclusions.**

| Readings | Row |
|---|---|
| Validity holds; P1, P2, P3, P5, P6 hold; P4 holds; P7's flush of `t0` and gauge bound hold | **Confirmed** — does not cap: each written table pins a 1 MiB region of real heap that `memtable_heap_space` does not count, at any `memtable_heap_space`, while the limit binds only on counted bytes |
| `heap_buffers` `slope_R` at most 0.10 MiB per table | **Refuted**: no region retained per table |
| `heap_buffers` `slope_A` at least 0.5 MiB per table | **Refuted**: the regions are charged |
| `H64`: small tables flushed (flush lines for `t1..t400` before `pc`) and `R(400)` at most 64 MiB | **Refuted**: the pool limit caps the region bytes |
| `U2048` `slope_R` at least half of the `H2048` slope | **Not confirmed**: the per-table heap is not the slab region (mechanism not isolated) |
| `heap_buffers` `slope_R` in (0.10, 0.95) or above 1.10 MiB per table, with P2 holding (for example 2 MiB per table from humongous allocation) | **Not confirmed**: real exceeds counted, but not by one region per table |
| P3 fails (slopes differ by more than 5 %) with P1 holding for at least one lifetime | **Not confirmed**: real follows the limit knob in part |
| P7 fails (no `MEMTABLE_LIMIT` flush of `t0`, or the gauge after `pc` above 0.40 x 64 MiB) with the rest holding | **Not confirmed**: positive control did not bind |
| Validity fails (settings, G1 flags, budget, a `ks.` flush before `pc`, table count, client errors, `ERROR` lines, node killed) | **Invalid** |
| Any other combination | **Not confirmed** (no matching row) |

**Stop conditions and cleanup.** A lifetime stops on a failed set-up check (port busy, read-back, node not serving in 300 s, histogram unreadable); the node is stopped by its PID; no `CassandraDaemon` is left (`ps -eo cmd | grep '[C]assandraDaemon'`). Run data stays under `/mydata/s4/slabrc-run/` and logs under `/mydata/s4/slabrc-logs/`.
