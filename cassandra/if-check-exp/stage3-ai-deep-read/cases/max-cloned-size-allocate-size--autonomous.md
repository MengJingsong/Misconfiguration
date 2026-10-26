# max-cloned-size-allocate-size — verification solution  <!-- file: cases/max-cloned-size-allocate-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:92` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-26 (design only, nothing built or run) |
| Estimate | `negative`. The operand at line 92 (`size > MAX_CLONED_SIZE`, 128 KiB) is a routing threshold, not a cap. It decides slab region vs. dedicated buffer; both paths are charged to the same memtable pool limit before the branch (line 89). The real cap is `memtable_heap_space` / `memtable_offheap_space`. |
| Ground | `MAX_CLONED_SIZE` is a private static final int (line 52) with no config key; it never compares against any byte budget. Usage is bounded (softly) by the pool accounting at line 89, independent of which branch is taken. The only usage/accounting discrepancy that depends on the threshold is slab tail waste (unaccounted, up to ~12% of a region), which is not a cap either. |

## A. Constraint trace

**A1. The constraint.**
- Literal at the target: `MAX_CLONED_SIZE = 128 * 1024` (bytes), `SlabAllocator.java:52`; compared at line 92. Kind: hard-coded constant (private static final). Not settable by yaml, `-D`, or JMX; change requires editing source and rebuilding. Sibling constant `REGION_SIZE = 1024*1024` at line 51.
- The constraint that actually caps memory on this path: `memtable_heap_space` (`Config.java:186-187`) and `memtable_offheap_space` (`Config.java:188-189`), both `DataStorageSpec.IntMebibytesBound`, MiB. Defaults are derived in `DatabaseDescriptor.java:583-587` as `Runtime.maxMemory() / (4 * 1048576)` MiB (1/4 of max heap) each when unset. Commented out in `conf/cassandra.yaml:797,799`. Settable via yaml only, restart required. Interacting knobs: `memtable_allocation_type` (`Config.java:524`, default `heap_buffers`, `conf/cassandra.yaml:825`) and `memtable_cleanup_threshold` (`Config.java:190`; default `1/(1+memtable_flush_writers)`, `DatabaseDescriptor.java:761-763`; validated 0.01..0.99 at lines 770-773).
- Wiring: `AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal` builds `new SlabPool(heapLimit, 0, ...)` for `heap_buffers` and `new SlabPool(heapLimit, offHeapLimit, ...)` for `offheap_buffers` (`db/memtable/AbstractAllocatorMemtable.java:100-105`); `SlabPool` sets `allocateOnHeap = (maxOffHeapMemory == 0)` and builds `SlabAllocator` (`SlabPool.java:25-33`). `MemtablePool.SubPool.limit` holds the limit (`MemtablePool.java:105`).

**A2. What it caps.** Memtable data: on-heap `byte[]` slabs for `heap_buffers`; off-heap direct `ByteBuffer`s for `offheap_buffers`. The quantity compared against the limit is `SubPool.allocated` (`MemtablePool.java:111`), incremented by the requested `size` in `tryAllocate` (`MemtablePool.java:~157-166`: `allocated + size > limit` -> false). It is a sum of requested bytes, not of region capacities. The 128 KiB constant itself caps nothing: it is only the max size of a single allocation served from a slab.

**A3. Mechanism.**
1. `SlabAllocator.allocate(int size, OpOrder.Group)` returns the shared empty buffer for 0 (86-87).
2. Line 89: `(allocateOnHeapOnly ? onHeap() : offHeap()).allocate(size, opGroup)` charges the pool BEFORE the size branch. `MemtableAllocator.SubAllocator.allocate` (`MemtableAllocator.java:169-199`): `parent.tryAllocate(size)` success -> return; else if `opGroup.isBlocking()` (flush is waiting on this write) -> `allocated(size)` retroactively, exceeding the limit; else register on `hasRoom`, retry, and park until a flush/discard releases space. So the limit is soft: writers block at the limit except when the op group is blocking (overshoot permitted so flush can proceed). Note `allocate(int)` at line 80 passes a null opGroup, which would NPE at `opGroup.isBlocking()` if the pool is full; callers use the `OpOrder.Group` overload.
3. Line 92, `size > 128 KiB`: add to `unslabbedSize` (94, informational), then either `ByteBuffer.allocate(size)` (heap only mode, 95-96) or a dedicated `ByteBuffer.allocateDirect(size)` wrapped in a `Region`, recorded in `offHeapRegions` for freeing at `setDiscarded` (97-99, 116-121).
4. Else (<= 128 KiB): loop (102-113) taking the current 1 MiB `Region` (`getRegion`, 126-153; `allocateDirect(REGION_SIZE)` or `allocate(REGION_SIZE)`, line 139). `Region.allocate` (197-206) does `getAndAdd`; if `newOffset + size > capacity` it returns null, the region is dropped (`compareAndSet(region, null)`, 112) and a new 1 MiB region is made. The unused tail of the dropped region is never charged to the pool (only requested bytes were, line 89) but is real memory. Also, regions lost in the CAS race are stashed in static `RACE_ALLOCATED` (55, 151) and not charged.
5. Release: `setDiscarded` cleans direct buffers (118-120) and releases the pool accounting (`releaseAll`, `MemtableAllocator.java:151-155`). Heap slabs are freed by GC.
Overshoot/bypass paths: (a) blocking op group (above); (b) slab tail waste and race-stashed regions are real but uncharged: with sizes `s <= 128 KiB`, waste per 1 MiB region is `1024 KiB mod s` (worst case just above 1024/9 = 113.8 KiB: 8 per region, ~112 KiB lost, real/accounted ~ 1.123); (c) `RACE_ALLOCATED` is a static queue shared by all tables, not freed until used; (d) flush trigger is `used > reclaiming + limit*cleanThreshold` (`MemtablePool.java:125-129,137-146`), so flushing starts well before the limit; the limit is only reached if flushes cannot keep up.

**A4. Other consumers.** Heap: everything else in the JVM (row cache, key cache, index summaries, native frames, compaction, hints, the `AtomicBTreePartition`/`BTree` object overhead which is charged via `allocator.onHeap().allocate(overhead, ...)`, e.g. `db/memtable/SkipListMemtable.java:125`). Direct memory: `BufferPool` chunk cache (`file_cache_size`), Netty direct buffers, `ByteBuffer.allocateDirect` anywhere else, all under the JVM `MaxDirectMemorySize` (defaults to max heap; `conf/jvm-server.options:174` commented). The shared `jvm` cap is a separate constraint. Memtable-related off-heap beyond slabs: none in `offheap_buffers`, whereas `offheap_objects` uses `NativePool` instead (not `SlabAllocator`).

**A5. Evidence beyond the source.** `ClusteringPrefixTest.java:136` and `MemtableSizeOffheapBuffersTest.java:44` / `MemtableSizeHeapBuffersTest.java:43` in `test/unit` show how `SlabPool` is built in tests (pattern reused below). JDK `java.nio.ByteBuffer.allocateDirect` and `java.lang.management.BufferPoolMXBean` ("direct" pool) docs: https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html. Otherwise none.

## B. Verification solution

**B1. Claim under test.** Because the 128 KiB threshold only routes between slab and dedicated buffers after the pool has been charged, memtable usage does NOT follow `MAX_CLONED_SIZE`: for the same total payload, the pool's `used()` is identical whether allocations are just below or just above the threshold, and the plateau where writers block is set by `memtable_offheap_space` (or `memtable_heap_space`) alone. Real memory differs from accounted memory only by slab tail waste (<= ~12.3%), never by a threshold-dependent cap. Falsified if accounted usage or the blocking plateau changes when the allocation size crosses 128 KiB (131072 bytes), or if real memory exceeds accounted by more than the slab-waste bound.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, Linux. Copy the tree to local disk: `rsync -a /users/jason92/cassandra-5.0.9/ /tmp/$USER/c509-unit/` (never build in the shared tree). `cd /tmp/$USER/c509-unit && ant jar` (or `ant build`). *[Amended 2026-10-26: the tree is made by `copy-source.sh` into `~/s4-b7-mc` and built with `ant jar`; the node and the probe run from it. The `SlabProbe` is `harness/max-cloned-size-allocate-size--autonomous/SlabCapProbe.java`, compiled outside the tree.]* Put a small program `SlabProbe.java` in package `org.apache.cassandra.utils.memory` in a separate dir `/tmp/$USER/probe/src`, compile with `javac -cp "build/classes/main:lib/*:build/lib/jars/*" -d /tmp/$USER/probe/out ...` and run with `java -Xmx2g -XX:MaxDirectMemorySize=1g -cp "/tmp/$USER/probe/out:build/classes/main:lib/*:build/lib/jars/*" org.apache.cassandra.utils.memory.SlabProbe <args>`. No `DatabaseDescriptor` initialisation is needed (as in `ClusteringPrefixTest.java:136`). Pool: `new SlabPool(2L<<30 /*heap*/, OFFHEAP_LIMIT, 0.99f, () -> ImmediateFuture.success(false))` (cleaner that frees nothing, so the limit really binds; *[Amended 2026-10-26: the stub sleeps 50 ms per call, because `MemtableCleanerThread` calls it in a tight loop while `needsCleaning()` stays true and the garbage it makes would enter the `RssAnon` reading (defect found in the sibling case `memtable-offheap-space-allocate-size`)]*); `allocateOnHeap` is false because the off-heap limit is nonzero, so the direct path is used.

**B2b. Knobs.**
- Allocation size `S` (bytes): 65536, 102400, 116736 (114 KiB, worst slab waste), 131072 (=MAX_CLONED_SIZE, still slabbed since the test is `>`), 131073 (first unslabbed), 163840, 262144. Chosen to straddle line 92 and to hit the waste extremes.
- `OFFHEAP_LIMIT` L: 64 MiB and 128 MiB (positive control: limit that is known to bind). *[Amended 2026-10-26: 32 MiB added, so the knob has three values 32 / 64 / 128 and the positive control is a proportional move over three points.]*
- Op-group state: normal, and blocking (issued barrier) to exercise the overshoot bypass. *[Amended 2026-10-26: the group becomes blocking when the barrier is issued and `markBlocking()` is called on it (`OpOrder.java:333`); `issue()` alone does not set `isBlocking`.]*
- *[Added 2026-10-26: mode control `heap_buffers`: `new SlabPool(heapLimit, 0, ...)`, same allocations, expect `offHeap.used() == 0` and `onHeap.used() == N*S`, no parking at L (the off-heap limit is not consulted). It shows that the pool limit and the allocation mode, not the constant, decide which counter is charged.]*

**B2c. Workload.** Single-thread loop `ByteBuffer b = alloc.allocate(S, group)`, keeping no extra references (regions are pinned by `offHeapRegions`). Phase 1 (below limit): N1 = floor(L/2 / S) allocations (never blocks; at L = 64 MiB, S=102400 -> N1 = 327, accounted 33,484,800 B); phase 1, 2 and 3 run in one JVM per (S, L) in that order. Phase 2 (drive past limit): *[Amended 2026-10-26: the main thread keeps allocating on allocator `a` until `used() + S > L`; then an extra thread makes one more allocation on a second allocator `b` of the same pool (so that discarding `a` releases the pool); the main thread reads the extra thread's state after 2 s. (The text before had a worker allocate on the allocator being discarded.)]*  Reaching the limit: accounted reaches the last multiple of S not exceeding L, i.e. `floor(L/S)*S`, then `tryAllocate` fails (`MemtablePool.java` `allocated+size>limit`) and the thread parks in `signal.awaitThrowUncheckedOnInterrupt`. Phase 3: with a blocking group (`OpOrder order = new OpOrder(); OpOrder.Group g = order.start(); order.newBarrier().issue();` with the group still open so `g.isBlocking()` is true; *[Amended 2026-10-26: also `markBlocking()` on the barrier]*), allocate 16 MiB past L and expect no blocking.

**B2d. Observables and instruments.**
- Accounted: `pool.offHeap.used()` (`MemtablePool.java` `used()`), and `pool.onHeap.used()` (expect 0 for offheap mode data).
- Real direct memory: `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)` entry named "direct": `getMemoryUsed()` and `getCount()`; take deltas from a baseline read after JVM warm-up. Also `/proc/self/status` VmRSS as a sanity check. *[Amended 2026-10-26: the read of the real resource is `BufferPoolMXBean` "direct" (exact: it counts every `allocateDirect` capacity) and `RssAnon` (not `VmRSS`; `allocateDirect` zero-fills, so its pages are resident); NMT "Other" is also recorded as a reading, no rule rests on it. Unlike the sibling case's `NativeAllocator` (JNA malloc, invisible to NMT), `allocateDirect` goes through `Unsafe.allocateMemory`, which JDK 11 NMT sees. The `RssAnon` band is `[accounted - 1 MiB, direct delta + 4 MiB]` (the 4 MiB is the JVM's own noise floor, measured in the sibling case).]*
- Worker thread state via `Thread.getState()` (WAITING means blocked at the limit).
- Not directly observable: slab tail waste per region (inferred from direct delta minus accounted); the private `unslabbedSize`.

**B2e. Procedure.**
1. Build as in B2a; write `SlabProbe` taking `S`, `L`, mode.
2. For each S in the knob list, fresh JVM: read baseline direct bytes D0; Phase 1; print `S, N, offHeap.used(), D1-D0, count delta`.
3. Fresh JVM per (S, L) pair for Phase 2 *[Amended 2026-10-26: same JVM as phase 1; see B2c]*: start the extra thread, sleep 2 s, print `offHeap.used()`, direct delta, worker state; then call `allocator.setDiscarding(); allocator.setDiscarded();` and print `offHeap.used()` and direct delta again (expect return to ~0 / buffers cleaned).
4. Phase 3 on S=102400 and 262144 with L=64 MiB.
5. Repeat Phase 1 and 2 once to check determinism.

**B2f. Predictions (before any run).**
- Phase 1: `offHeap.used() == N*S` exactly for every S, including either side of 131072/131073. Direct delta: for S > 131072 it equals `N*S` (dedicated buffers, count delta = N); for S <= 131072 it equals `ceil(N / floor(1048576/S)) * 1048576` (count delta = number of regions). Example S=116736: 8 per region, so for N=280 (32 MiB / 116736 ~ 287; use 280) delta = 35 MiB regions = 36,700,160 vs accounted 32,686,080, ratio ~ 1.123. S=102400: 10 per region, ratio 1.024. S=131072 and 65536: ratio 1.000.
- Phase 2: for each S, plateau `offHeap.used() == floor(L/S)*S` (<= L, within S of L) and worker WAITING, for both below and above 128 KiB. Plateau is the same function of L only: halving L halves it. Direct delta at plateau: for S <= 131072 exactly `ceil(floor(L/S) / floor(1048576/S)) * 1048576` (the regions are full except the last; the ratio to `used()` is at most 1.1228 + one unfilled region), for S > 131072 exactly `used()`. *[Amended 2026-10-26: this replaces the earlier "<= 1.123 * L (+1 MiB)", which is wrong from the source alone: S = 116736, L = 64 MiB gives 574 allocations in 72 regions = 75,497,472 B = 1.125 L and 1.1267 x used(). The `RssAnon` and `BufferPool` readings in the knob table use this formula.]* After `setDiscarded`, `used()` -> 0 and direct delta -> ~0 once cleaned (`FileUtils.clean`, lines 118-120).
- Phase 3: blocking group: no WAITING; `used()` exceeds L by up to the 16 MiB driven past (soft limit bypass).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `used() == N*S` and plateau `== floor(L/S)*S` on both sides of 131072/131073 | Claim confirmed: the threshold does not change what is charged or where writers block |
| Plateau differs (beyond one S) between S=131072 and 131073, or between 100 KiB and 200 KiB at equal L | Claim refuted: usage depends on the threshold path |
| Plateau halves when L halves, at every S | Positive control: the pool limit binds and is the real cap |
| Direct delta > accounted for S in slab range, by <= 12.3% and matching the region formula | Expected slab waste; not a cap |
| Direct delta > 1.123x accounted, or > accounted for S > 131072 | Unmodelled uncharged memory; the claim's waste bound is wrong |
| Worker never reaches WAITING | Limit not reached (phase invalid; check L, cleaner and group state); not confirmed |
| Plateau does not move when L changes | Control failed; not confirmed |
| Blocking group allocates past L | Documented overshoot path (A3.2); not a refutation |

**B2h. Controls.** Fresh JVM per run; direct memory baseline subtracted; cleaner returns false (no flush, no release) so only the limit gates; same JVM flags for all runs; `-XX:MaxDirectMemorySize=1g` set well above L so the JVM direct-memory cap does not interfere; check `jcmd <pid> GC.run` is NOT needed (buffers are pinned by `offHeapRegions`); repeat run.

### B3. Cluster tier

**B3a. Environment and build.** One node (two-node optional, not needed), Linux, JDK 11, Ant. `rsync -a` the tag to `/tmp/$USER/c509-node/` on local disk; `ant jar`. Use local data dirs on a disk of known free size (e.g. `/tmp/$USER/node/{data,commitlog,saved_caches,hints}`, >= 10 GiB free; set `commitlog_total_space: 1024MiB` *[Amended 2026-10-26: 4096MiB. At 1024MiB, commit-log pressure would flush the table before the pool reaches L = 512 MiB and cap the memtable below L, a confound; the sibling cases used 4096MiB]*). `cassandra.yaml`: `memtable_allocation_type: offheap_buffers`, `memtable_heap_space: 512MiB`, `memtable_offheap_space: L`, `memtable_cleanup_threshold: 0.99`, `memtable_flush_writers: 1`, `file_cache_size: 64MiB`, `max_mutation_size`: default; `native_transport_max_frame_size` default (blob values < 256 KiB fit). JVM: `-Xms2g -Xmx2g -XX:MaxDirectMemorySize=2g`. Start with `bin/cassandra -f` under `nohup`, record PID. *[Amended 2026-10-26: data on tmpfs `/dev/shm/s4-b7-mc` (wiped per lifetime), `key_cache_size`/`row_cache_size` 0, `concurrent_compactors` 1, `write_request_timeout` 30000ms and `native_transport_timeout` 60000ms (a write held at the limit waits longer than the 12 s default), `-XX:+AlwaysPreTouch` (shipped in `jvm-server.options:128`; heap pages are resident from the start, so `RssAnon` growth is not heap growth), `-XX:NativeMemoryTracking=summary`, client protocol 4 (large native-v5 requests leave unreturned direct frame buffers). The node starts as a daemon with a pid file.]*

**B3b. Knobs.**
- Value size `V`: 100 KiB (102400, slab path) vs 200 KiB (204800, dedicated direct buffer path). Both sit on opposite sides of the 128 KiB constant; note the allocation size charged is the cell value size plus key/name buffers, but the value dominates.
- `memtable_offheap_space` L: 128 MiB and 256 MiB (positive control: known binding cap). *[Amended 2026-10-26: 512 MiB added (the default at -Xmx2g, `DatabaseDescriptor.java:583-587`), so the knob has three values, the default among them.]*
- *[Added 2026-10-26: control arms, `heap_buffers` with `memtable_heap_space` 512MiB (the default at -Xmx2g) at V = 100 KiB and V = 200 KiB, same payload: they carry the non-memtable growth of the process (Netty, `BufferPool`, client load) that the arms with the same V share; a net memtable-attributable reading is arm minus control. This rule is fixed here, before any reading. The third positive control of B3h (`memtable_heap_space` 128MiB, V = 100 KiB) is arm `hp`.]*
Set via `cassandra.yaml` before each (restart required).

**B3c. Workload.** Table `ks.t (pk int PRIMARY KEY, v blob)` with `compaction` default and RF=1. Write with cassandra-stress user profile or a driver script: unique `pk`, `v` of `V` bytes, `write_consistency=ONE`, 16 threads. Volume: 2 GiB payload per run (e.g. V=100 KiB: ~21,000 rows; V=200 KiB: ~10,500 rows; *[Amended 2026-10-26: exactly 20,000 rows of 102,400 B and 10,000 rows of 204,800 B, both 1.91 GiB, at every L; table `ks.big (k int PRIMARY KEY, v blob)`, client in the harness, 16 requests in flight]*), far above L so memtable usage must hit the cap and flush repeatedly; arithmetic: cleanup begins when `used > 0.99*L` (L=128 MiB -> ~126.7 MiB), reached after ~1300 rows at 100 KiB. Duration: until the 2 GiB is written (minutes), plus 60 s settle.

**B3d. Observables and instruments.**
- Accounted memtable off-heap: JMX table metrics `org.apache.cassandra.metrics:type=Table,name=MemtableOffHeapDataSize` (sum over tables) and `MemtableLiveDataSize`; sampled every 1 s via `nodetool`/`jmxterm`/a small JMX poller. *[Amended 2026-10-26: the gauge read is the global `type=Table,name=AllMemtablesOffHeapDataSize` (`TableMetrics.java:515-521`), because the global `MemtableOffHeapDataSize` is registered under the name `MemtableOnHeapDataSize` (`TableMetrics.java:507`); the poller is a JMX client JVM (`Jmx.java`) at 200 ms, `RssAnon` at 200 ms, `BufferPool` "direct" `MemoryUsed` and `Count` at 200 ms, NMT summary every 5 s.]* `nodetool tablestats ks.t` for cross-check.
- Real direct memory: JMX `java.nio:type=BufferPool,name=direct` `MemoryUsed`, sampled 1 s; Linux `ps -o rss= -p PID` and `/proc/PID/smaps_rollup` 1 s *[Amended 2026-10-26: read `RssAnon` from `/proc/PID/status`, not `VmRSS`]*; `jcmd PID GC.heap_info` for heap.
- Pool blocking: `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation`.
- Not observable directly: slab waste (inferred); `unslabbedSize`.

**B3e. Procedure.**
1. Build and configure as in B3a with L=128 MiB. Start node; wait for "Starting listening for CQL clients"; create keyspace/table.
2. Baseline (60 s idle): record direct `MemoryUsed`, RSS, `MemtableOffHeapDataSize`.
3. Run write workload with V=100 KiB; sample all instruments every second until done; record peak and the sawtooth max of `MemtableOffHeapDataSize` and the peak of direct `MemoryUsed` minus baseline.
4. `nodetool drain`; stop node; delete `/tmp/$USER/node/data/ks`, commitlog; restart; repeat with V=204800 (same L).
5. Repeat steps 1-4 with L=256 MiB.
6. Stop the node (`kill PID`, confirm with `pgrep -u $USER -f CassandraDaemon`), and clean up.

**B3f. Predictions (before any run).**
- Peak `MemtableOffHeapDataSize` is <= L (plus transient overshoot of at most the in-flight writes, <= 16 threads x V ~ 3.2 MiB) for both V, with a sawtooth topping out near 0.99*L plus whatever accrues until flush completes; i.e. the same peak (within ~10%) for V=100 KiB and V=200 KiB at equal L. *[Amended 2026-10-26, before any run: the peak is the maximum of 200 ms samples, so the sawtooth top can be missed; it is expected between 0.85 L and L + 16 x V, "limit reached" means a peak >= 0.9 L or a growing `BlockedOnAllocation` count with at least two flushes; the equal-peak relation is read within 15 %; peaks at L = 128 / 256 / 512 order and scale about 1 : 2 : 4.]*
- Peak direct `MemoryUsed - baseline`: for V=200 KiB approx accounted peak (+ small); for V=100 KiB approx accounted peak x 1.024 (10 per region). At L=256 MiB all peaks about double those at L=128 MiB. No behaviour step appears between 100 and 200 KiB other than the waste factor. *[Amended 2026-10-26, before any run: "direct memory minus baseline" is the net of the matching control arm (same V, `heap_buffers`): net `BufferPool` direct delta = accounted peak x 1.024 (V = 100 KiB) or x 1.00 (V = 200 KiB) plus up to one 1 MiB region per live memtable, so within [0.9 L, 1.13 L + 4 MiB]; net `RssAnon` delta within [0.9 L, 1.3 L]; the net deltas at 256 and 512 over 128 are in [1.7, 2.3] and [3.2, 4.8].]*
- `BlockedOnAllocation` count may be nonzero at both V; no V-dependent threshold.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak memtable off-heap tracks L (doubles from 128 to 256 MiB), roughly equal for V=100 and 200 KiB | Claim confirmed; limit is the pool limit, not the 128 KiB constant. L doubling is the positive control |
| Peak direct memory minus baseline tracks accounted peak within 1.0 to 1.13x | Real usage follows the pool limit plus slab waste |
| Peaks differ markedly between V=100 KiB and 200 KiB at the same L (> 25%) | Claim refuted: threshold path affects usage |
| Net direct memory (arm minus the control of the same V) grows beyond ~1.15x L, or without bound while accounted stays flat | Uncharged allocation (bypass), refutes the cap for this path; investigate A4 consumers |
| Peaks do not change with L | Control failed (limit not reached or wrong allocation type); not confirmed |
| Memtable never approaches L | Workload too small / limit not reached; not confirmed |
| Heap grows with L in offheap_buffers mode | Wrong `memtable_allocation_type` in effect; check startup log |

**B3h. Controls.** Same yaml except L; same JVM flags; restart with clean data between runs; subtract idle baseline for direct memory (BufferPool, Netty); `file_cache_size` pinned small; confirm in `system.log` that "Memtables allocating with off-heap buffers" is logged (`AbstractAllocatorMemtable.java:103`, debug level; set `<logger name="org.apache.cassandra.db.memtable" level="DEBUG"/>` in `logback.xml` of the copy) to rule out the allocation-type confound; a third positive control: `heap_buffers` at `memtable_heap_space` 128 MiB with V=100 KiB should show heap (not direct) following the heap limit.

**B4. Risks and cleanup.** Disk: node data and commit log on local `/tmp/$USER/node` only, sized under `commitlog_total_space` + ~2 GiB payload + compaction headroom (reserve 10 GiB); never use shared storage or the shared source tree. Memory: JVM 2 GiB heap + up to 2 GiB direct; run on an otherwise idle node. Processes: Cassandra, JMX pollers, stress client, probe JVMs; kill all and verify with `pgrep -u $USER -f 'CassandraDaemon|SlabProbe|cassandra-stress'`. Cleanup: `rm -rf /tmp/$USER/node /tmp/$USER/probe /tmp/$USER/c509-*`. The unit tier needs no cluster; do not run on the shared cluster.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/SlabAllocator.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/SlabPool.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableCleaner.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java (grep)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml, conf/jvm-server.options (grep)
- test/unit references via grep (ClusteringPrefixTest, MemtableSize*Test)
- https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html (cited, from knowledge)

## D. Stage-4 feedback

**Step-0 audit amendments, 2026-10-26 (stage 4, before any reading; independent of any run).** Results: `stage4-runtime-verification/results/max-cloned-size-allocate-size--autonomous.md` §1. Marked `[Amended 2026-10-26 ...]` in B2a-B2f, B3a-B3f:
1. B2a: tree by `copy-source.sh`, `ant jar`; the cleaner stub sleeps 50 ms per call (an unthrottled stub makes the cleaner thread spin and its garbage enters `RssAnon`).
2. B2b: L = 32 / 64 / 128 MiB (three values); op-group blocking needs `markBlocking()` (`OpOrder.java:333`), not only `issue()`; added the `heap_buffers` mode control.
3. B2c/B2e: phases 1-3 in one JVM per (S, L); the parked extra allocate runs on a second allocator so that discarding the first releases the pool.
4. B2d: the real-resource read is `BufferPoolMXBean` "direct" plus `RssAnon` (the regions are `allocateDirect`, visible to NMT, unlike the sibling case's JNA regions); band `[accounted - 1 MiB, direct delta + 4 MiB]`.
5. B2f: the plateau direct delta is the exact region formula, not "<= 1.123 L" (S = 116736 at L = 64 MiB gives 72 MiB = 1.125 L).
6. B3a: `commitlog_total_space` 4096MiB (1024MiB would flush before L = 512 MiB), tmpfs data, caches off, timeouts 30 s / 60 s, `AlwaysPreTouch`, NMT, protocol 4.
7. B3b/B3c: L = 128 / 256 / 512 MiB (three values, 512 is the default at -Xmx2g); control arms `heap_buffers` at both V (net-of-control rule fixed before any reading); exactly 20,000 x 102,400 B and 10,000 x 204,800 B.
8. B3d: gauge `AllMemtablesOffHeapDataSize` (the global `MemtableOffHeapDataSize` is registered under the name `MemtableOnHeapDataSize`, `TableMetrics.java:507`: stage-3 note and upstream candidate); `RssAnon`, not `ps rss`.
9. B3f: sampling-aware limit-reached rule; net direct / `RssAnon` bands and L ratios stated.
Citation spot-check: `SlabAllocator.java:52,89,92-100,102-113,116-121,126-153`, `SlabPool.java:25-33`, `MemtablePool.java:151-158` (the case says `~157-166`), `MemtableAllocator.java:169-197` (case: 169-199), `AbstractAllocatorMemtable.java:99-105`, `DatabaseDescriptor.java:583-587,761-773`, `Config.java:186-190,524`: hold, minor line drift only. The claim is sound.

**Stage-4 result (run 1, 2026-10-26, `results/max-cloned-size-allocate-size--autonomous.md`):** unit **Confirmed** - does not cap; cluster **Confirmed** - does not cap; outcome class true negative. `used()` and the blocking plateau are identical either side of 131072 / 131073 (21 fill runs, 0.996-1.000 L) and scale 1 : 2 : 4 with L; the direct memory exceeds the accounted bytes by exactly the slab-region formula (0 above the threshold, 2.4-3.3 % at 100 KiB, 12.6 % at 116736); cluster peaks 0.95-0.99 L, equal within 1.2 % for 100 and 200 KiB values, 1 : 2 : 4 across L = 128 / 256 / 512 MiB, net direct memory 1.01-1.08 L, `heap_buffers` controls and the heap-limit positive control as predicted.
**Findings for stage 3 (not applied to the frozen text):** (1) B1 and the B2g waste rows give the slab-waste bound as 12.3 % (1.123 x); it ignores the partly filled last region and is exceeded (12.57-12.67 %) at S = 116736 although the direct delta equals the exact formula; the bound is `ceil(n / floor(1 MiB / S)) x 1 MiB` over `n x S`, and per full region `(1 MiB mod S) / (1 MiB - (1 MiB mod S))` (12.28 % at S = 116736). (2) The net `RssAnon` relations of B3f (net of the `heap_buffers` control, band 0.9-1.3 L and L ratios 1.7-2.3 / 3.2-4.8) were missed twice (d128 0.83 L, ratio 2.30-2.34); `RssAnon` carries 10-20 MiB of noise at these sizes, the `BufferPool` direct reading is exact. (3) The default `memtable_cleanup_threshold` (0.5) was not run. (4) The global `MemtableOffHeapDataSize` gauge is registered as `MemtableOnHeapDataSize` (`TableMetrics.java:507`), an upstream candidate.
