# max-region-size-region-allocate-capacity — verification solution  <!-- file: cases/max-region-size-region-allocate-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/memory/NativeAllocator.java:273` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (Claude Code, autonomous stage-3 agent), 2026-10-26 |
| Estimate | `negative`. Line 273 compares against `Region.capacity`, a slab size bounded by the hard-coded constant `MAX_REGION_SIZE` (1 MiB). It bounds the size of one slab, not the number of slabs or the total off-heap bytes. |
| Ground | The constant limits one object (a region, at most 1 MiB, except oversize regions that are exactly the request size). Regions are chained without bound (`regions.add`, :181, :191). The real cap on total memtable off-heap memory is `memtable_offheap_space`, enforced by the pool accounting at :141 (`offHeap().allocate`) and by `SubPool.tryAllocate` (`MemtablePool.java:151-160`). Region slack and the static `RACE_ALLOCATED` stash are not charged to that pool. |

## A. Constraint trace

**A1. The constraint.** Two layers are involved.
- Directly at the target: `Region.capacity` (`NativeAllocator.java:244`, set at :261), compared at :273 as `newOffset + size > capacity`. A region's capacity is chosen in `trySwapRegion` (:158-184) and `allocateOversize` (:190).
- It comes from the constant `MAX_REGION_SIZE = 1 * 1024 * 1024` (:46). Related constants are `MIN_REGION_SIZE = 8 * 1024` (:48) and `MAX_CLONED_SIZE = 128 * 1024` (:47).
- Kind: compile-time constant. Unit: bytes. Default: 1,048,576, with no derivation. It is not settable by yaml, `-D` or JMX; changing it needs a source edit and rebuild.
- The pool-level constraint that actually caps the resource is `memtable_offheap_space` (`Config.java:189`). It is a yaml key in MiB, with a restart needed. Its default is `maxMemory()/4 MiB` (`DatabaseDescriptor.java:583-584`), and `conf/cassandra.yaml:799` shows it commented out.
- Also relevant: `memtable_allocation_type` (`Config.java:524`; `offheap_objects` selects `NativePool`, `AbstractAllocatorMemtable.java:106-108`) and `memtable_cleanup_threshold` (`Config.java:190`).

**A2. What it caps.** The resource is native (off-heap, `Unsafe.allocateMemory` via `MemoryUtil.allocate`, :176, :190) memory used by memtables when `memtable_allocation_type: offheap_objects`. The quantity compared at :273 is the next-free offset plus the request size against the capacity of one slab, so it caps the bytes carved from one region and nothing global.

**A3. Mechanism.**
1. `allocate(size, opGroup)` (:138) first charges `size` to the off-heap sub-pool with `offHeap().allocate(size, opGroup)` (:141). That is the real limit check. `MemtableAllocator.SubAllocator.allocate` (`MemtableAllocator.java:169-196`) calls `parent.tryAllocate`. If that fails and the op is not blocking, the writer waits on `hasRoom`. If `opGroup.isBlocking()`, it allocates anyway and overshoots (:179-183).
2. If `size > MAX_CLONED_SIZE`, `allocateOversize` (:186) mallocs a dedicated region of exactly `size`. Line 273 is trivially satisfied there, and the `-1` branch is an `AssertionError` (:194-195).
3. Otherwise it takes `currentRegion`, calls `region.allocate(size)` (:151), and :271-277 does `getAndAdd(size)` then the :273 check. On a miss (`-1`; note a returned `peer > 0` test at :151) it loops to `trySwapRegion` (:154).
4. `trySwapRegion` sizes the next region: 8 KiB if none, else double the current, rounded up to `highestOneBit(minSize)<<3` if too small, then `min(MAX_REGION_SIZE, size)` (:163-168). It first reuses a stashed race-loser region (:171-172), else mallocs (:176). It CAS-installs it and appends to `regions` (:180-181). A CAS loser is stashed (up to 8 per size class, `RaceAllocated`, :209-227) or freed (:183).
5. Regions are freed only in `setDiscarded` (:200-206), when the memtable is discarded after flush.
- Outcome at the limit of line 273: that region is abandoned as `currentRegion` and a new one is allocated. The memtable keeps growing.
- Overshoot and bypass paths:
  - Unused tail of every abandoned region (up to just under `MAX_CLONED_SIZE` per region) is allocated from the OS but never charged. Only the requested `size` is charged (:141).
  - A failed `getAndAdd` also advances `nextFreeOffset` past capacity, which is harmless but means the tail is dead.
  - The static `RACE_ALLOCATED` stash (:51-57; 8 permits per size class, 8 KiB..1 MiB) holds uncharged regions, at most about 8 x 2 MiB = 16 MiB in the worst case, shared across memtables.
  - Blocking writers overshoot the pool (`MemtableAllocator.java:176-180`).

**A4. Other consumers.** Other memory outside this accounting: JVM heap, direct buffers (chunk cache, networking, `offheap_buffers` slabs), metaspace, mmapped sstables, bloom filters/index off-heap, compression buffers and glibc malloc arena fragmentation. The on-heap part of native objects is charged to the separate on-heap pool (`NativeAllocator` constructor :65, `memtable_heap_space`).

**A5. Evidence beyond the source.** In-tree test `test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java` (builds `new NativePool(1, 100, 0.75f, ...)`, :52-71; uses `owns()`, `getReclaiming()`, `pool.offHeap.used()`) shows the usage-side accounting API. Class javadoc (:34-43) describes slab sizes 8 KiB to 1 MiB serving allocations up to 128 KiB. Nothing external relied on.

## B. Verification solution

**B1. Claim under test.** Total native memory held by a `NativeAllocator` is not bounded by `MAX_REGION_SIZE`/`Region.capacity`: the number of regions, and the sum of region capacities, grow linearly with the data written. The sum of capacities exceeds the bytes charged to the off-heap pool (slack is uncharged). On a real node, peak off-heap use follows `memtable_offheap_space` and not `MAX_REGION_SIZE`. It is falsified if the sum of capacities stays at or below `MAX_REGION_SIZE`, or if node off-heap peak changes with `MAX_REGION_SIZE` while `memtable_offheap_space` is held fixed.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the source to local disk (`rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/`; never build in the shared tree). Build with `ant jar` (or `ant build-test`) in the copy. Write a small `main` (or JUnit test beside `NativeAllocatorTest`, same package `org.apache.cassandra.utils.memory` for package-private access) in the copy. Run with `-Xmx512m -Dcassandra.config=file:///local/scratch/c509/conf/cassandra.yaml`, plus `DatabaseDescriptor.daemonInitialization()` if `NativeCell` is used. A plain `allocator.allocate(int, OpOrder.Group)` needs no DatabaseDescriptor.

**B2b. Knobs.**
- Pool off-heap limit L passed to `new NativePool(heapLimit, L, 0.75f, cleaner)`: 1 GiB (never binding), 16 MiB (binding).
- Request size s: 100, 100000 (just below `MAX_CLONED_SIZE`), 131072 (exactly 128 KiB, still in-region), 131073 (oversize path).
- Optional source-edit variants of `MAX_REGION_SIZE` in the scratch copy: 256 KiB, 1 MiB (stock), 4 MiB. Each is a separate build.

**B2c. Workload.** Single thread, one `OpOrder.Group` from `new OpOrder().start()`, no-op cleaner (`() -> ImmediateFuture.success(true)`). Allocate N requests of size s on one fresh `NativeAllocator`.
- Case A (L=1 GiB, s=100): N=2,000,000 gives 200 MB charged, about 200 regions of 1 MiB.
- Case B (L=1 GiB, s=100000): N=1000 gives 100 MB requested. The first region is 524,288 (since 100000 > 8192, size = 65536<<3) and holds 5; later regions are 1 MiB holding 10 each (10 x 100000 = 1,000,000; the 11th would end at 1,100,000 > 1,048,576).
- Case C (s=131072): 8 per 1 MiB region, zero slack. Case D (s=131073): each allocation is its own oversize region with `capacity == s`.
- Case E (L=16 MiB, s=100000, `OpOrder` group marked blocking via a barrier as in `NativeAllocatorTest.setUp` `markBlocking`): shows overshoot of the pool.
- **[Amended 2026-10-26, audit]** N for cases C and D is 1000 (the original gave none). Case E: fill with a non-blocking group until `used + s > L` (no wait, because the next request would not fit), then a second allocator with a non-blocking group must park, and a blocking group (barrier `issue()` + `markBlocking()`) makes 10 further allocations without parking. Cases A to D also run on each source-edit variant (B2b) with the same N and s; case E on the stock build only. The tree of each variant is a separate `copy-source.sh` copy with the one constant edited (256 KiB = `256 * 1024`, 4 MiB = `4096 * 1024`), built with `ant jar`.

**B2d. Observables and instruments.**
- Charged bytes: `allocator.offHeap().owns()` and `pool.offHeap.used()`.
- Region structure: reflection (`setAccessible`) on `NativeAllocator.regions` (a `ConcurrentLinkedQueue<Region>`) and `Region.capacity`/`nextFreeOffset`. Compute region count, max capacity, sum of capacities, and slack = sum(capacity) - owns().
- Optional cross-check: process RSS delta from `/proc/self/status` (VmRSS) around the run. Note `Unsafe.allocateMemory` is not visible to JVM NMT.
- Cannot be observed directly: glibc malloc overhead and page-touch laziness (untouched malloc'ed pages may not be resident; allocate and write a byte per region, or rely on reflection numbers).

**B2e. Procedure.**
1. Copy the tree, build.
2. Write the harness: for each case, create the pool and allocator, run the loop, then print `owns`, `pool.offHeap.used()`, region count, max capacity, sum capacity and RSS.
3. Run the cases for the stock constant, then rebuild with `MAX_REGION_SIZE` = 256 KiB and 4 MiB and repeat A and B (note `MIN_REGION_SIZE` doubling loop at :55 still works; **[Amended 2026-10-26]** the earlier advice to skip cases C and D at 256 KiB is dropped: `MAX_CLONED_SIZE` (128 KiB) stays below 256 KiB, so s = 131072 still goes to a region, two per region, and C and D run on every variant).
4. Call `allocator.setDiscarding(); setDiscarded()` at the end of each case to free the native memory. Exit the JVM.

**B2f. Predictions (before any run).**
- A: `owns == pool.offHeap.used == 200,000,000`. Max capacity == 1,048,576. Region count about 190 to 200 (8K, 16K ... 512K ramp then 1 MiB regions), which is far more than 1. Sum of capacities >= 200,000,000 (slack under 1 percent, only ramp tails).
- B: `owns == 100,000,000`; region count = 1 + ceil(995/10) = 101; sum of capacities about 105 MB; slack about 4.9 percent (~48,576 per 1 MiB region), roughly 5 MB uncharged. **[Amended 2026-10-26, arithmetic, no reading involved]** Exact stock values (replay of the :163-168 rule): sum of capacities 524,288 + 100 x 1,048,576 = 105,381,888; slack 5,381,888 (5.38 percent of charged); the last region holds only 5 cells, which the first figure ignored. The earlier 4.9 percent is superseded.
- C: slack 0, sum capacity == charged. D: 1000 regions, each `capacity == 131073`; max capacity above 128 KiB but `MAX_REGION_SIZE` irrelevant.
- E, L=16 MiB and blocking group: `owns` and `pool.offHeap.used()` exceed L (overshoot, no block); with a non-blocking group the allocating thread waits once the pool reaches L (so the test needs a releaser thread, or a timeout to show the wait).
- Constant variants: max capacity tracks the constant (256 KiB, 1 MiB, 4 MiB); region count scales inversely; sum capacity and `owns` are unchanged within the slack (<=5 percent).
- **[Amended 2026-10-26, audit; replaces the "<=5 percent" clause above, which is wrong for 256 KiB with s = 100000]** `owns` and `pool.offHeap.used()` are exactly N x s on every variant (the constant is not in the charge at :141). Sum of capacities and region count, from a replay of the :163-168 rule (the harness repeats this replay as an instrument check and reads `MAX_REGION_SIZE` from the loaded class): A (s=100, N=2,000,000): 256 KiB 200,269,824 in 768 regions; 1 MiB 200,269,824 in 197; 4 MiB 201,318,400 in 56. B (s=100000, N=1000): 256 KiB 131,072,000 in 500 (two cells per region, slack 31.07 percent); 1 MiB 105,381,888 in 101 (5.38 percent); 4 MiB 104,333,312 in 27 (4.33 percent). C (s=131072, N=1000): 256 KiB 131,072,000 in 500; 1 MiB 131,072,000 in 125; 4 MiB 133,169,152 in 33 (1.60 percent). D (s=131073, N=1000): 131,073,000 in 1000 regions on every variant (capacity == s each). So the constant changes slack by up to 31 percent at one cell size, never the charged bytes, and at s = 100 the sum of capacities moves by under 0.7 percent across a 16x change of the constant.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Sum of capacities grows linearly with N, region count >> 1, max capacity == `MAX_REGION_SIZE` | Claim confirmed: the constant bounds one slab only, not total usage |
| Sum capacity > `owns()` in B (about 5 percent) | Uncharged slack exists: pool accounting does not equal real allocation |
| Total changes proportionally to `MAX_REGION_SIZE` variants at fixed N and s (beyond slack of a few percent) | Claim refuted: the constant influences total usage. **[Amended 2026-10-26, defines "total"]** "Total" is the charged bytes (`owns`, `pool.offHeap.used()`) and, at s = 100, the sum of capacities. Refuted if `owns` differs between variants at the same N and s, or if the s = 100 sum of capacities differs from the 1 MiB value by more than 2 percent. |
| **[Amended 2026-10-26]** Each variant's max capacity equals its constant, `owns` is identical across variants, and the sum of capacities equals the B2f replay (slack up to 31 percent at 256 KiB, s = 100000) | Claim confirmed on the knob axis: the constant sets slab geometry and uncharged slack only. A slack above 5 percent at 256 KiB is expected and is not a refutation |
| **[Amended 2026-10-26]** The replay (`model`) disagrees with the real region count or sum of capacities | Instrument or reading error: the tier is Not confirmed until the cause is found |
| Sum of capacities never exceeds `MAX_REGION_SIZE` | Claim refuted (it would be a total cap) |
| With a non-blocking group and L=16 MiB, `owns` stops at <= L and the writer waits | Positive control: the pool limit binds. Usage follows `memtable_offheap_space`, not the region constant |
| `owns` never reaches L, or the writer never waits in case E | Not confirmed (limit not reached); enlarge N |
| Blocking group exceeds L | Documented overshoot path, not a refutation |

**B2h. Controls.** Fixed s and N across constant variants; fresh JVM per variant (the static `RACE_ALLOCATED` stash is shared); single thread so no CAS races produce stash regions (then repeat with 8 threads to see stash regions appear in `RACE_ALLOCATED`, whose size is read by reflection, and confirm total stash <= 8 per size class); the L-binding run is the positive control.

### B3. Cluster tier

**B3a. Environment and build.** One node suffices. JDK 11, Ant. Copy the tree to local disk, `ant jar` there. Node config (all paths on a local disk of known size, at least 20 GB free):
- `memtable_allocation_type: offheap_objects`
- `memtable_offheap_space: 64MiB`, `memtable_heap_space: 256MiB`
- `memtable_flush_writers: 2` (so `memtable_cleanup_threshold` defaults to 1/3) **[Amended 2026-10-26, audit: `memtable_flush_writers: 1` and `memtable_cleanup_threshold: 0.99`.** With the default 1/3 the cleaner flushes at about 21 MiB of a 64 MiB pool and the pool limit is never reached, so "usage driven to the limit and past it" fails and the 64/128/256 sweep would show only the 1/3 threshold; 0.99 is the highest value `DatabaseDescriptor.java:772-773` accepts, so writers must meet the pool limit and block (`MemtableAllocator.java:182-196`)]
- `commitlog_total_space: 512MiB` **[Amended 2026-10-26: 4096MiB, so the commit log does not force the flushes before the pool is full]**
- `data_file_directories`, `commitlog_directory`, `hints_directory` and `saved_caches_directory` on local disk **[Amended 2026-10-26: on the node's tmpfs `/dev/shm/s4-b7-mr`, wiped per lifetime (an environment lesson in HANDOFF); tmpfs pages count as RssShmem, not RssAnon, which is the reading used below]**
- `-Xms1G -Xmx1G (the shipped `-XX:+AlwaysPreTouch` makes the heap resident before the baseline)` (set `MAX_HEAP_SIZE=1G`, `HEAP_NEWSIZE=256M`)
- `-XX:MaxDirectMemorySize=256M` (`jvm-server.options:174`) so direct buffers cannot masquerade as memtable memory.
- Chunk cache can stay at its default. Disable swap interference by checking `free`. Use `MALLOC_ARENA_MAX=2` to limit glibc arena noise.
- Builds: stock, plus scratch builds with `MAX_REGION_SIZE` = 256 KiB and 4 MiB.
- **[Amended 2026-10-26]** Also `table`: `ks.t` created with `compression = {'enabled': 'false'}`; the node's settings are read back from `system_views.settings` before the workload; `-XX:NativeMemoryTracking=summary` is on (it cannot see `Unsafe.allocateMemory`, so it shows that the regions are outside JVM tracking).

**B3b. Knobs.**
- Primary: `MAX_REGION_SIZE` (source-edited build): 256 KiB, 1 MiB, 4 MiB, with `memtable_offheap_space` fixed at 64 MiB.
- Positive control: `memtable_offheap_space` 64 MiB, 128 MiB, 256 MiB with the stock build.
- Via `cassandra.yaml` and a restart for each value.

**B3c. Workload.** Table `ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))` with `memtable` default (skiplist; trie memtable is a different allocator path, so do not use it). Write rows with a 100,000-byte blob through the CQL client (`cassandra-stress` user profile, or a Python/`cqlsh` loop with 8 concurrent writers, so data path is `NativeCell` -> `NativeAllocator.allocate`; cell size 100,000 < `MAX_CLONED_SIZE`, so it exercises line 273). Note `max mutation size` is half the commitlog segment (32 MiB default), so 100 KB values are fine. Total 2 GB written (20,000 rows x 100 KB), roughly 30 times the 64 MiB limit. **[Amended 2026-10-26: rows are written with `pk = i // 20, ck = i % 20`, 16 requests in flight, protocol 4, CL ONE; the blob is one random 100,000-byte buffer with a distinct 8-byte prefix per row.]** Duration: until finished (minutes). Disk use: 2 GB commit log traffic recycled plus sstables of at most 2 GB (use `compression: none`), well under the local disk.

**B3d. Observables and instruments.**
- Charged usage: JMX `org.apache.cassandra.metrics:type=Table,name=AllMemtablesOffHeapDataSize` (or `nodetool tablestats ks.t` "Off heap memory used", Memtable lines), sampled every 1 s with `nodetool` or a JMX poller; `MemtableOffHeapSize`.
- Actual process memory: `ps -o rss= -p $PID` and `/proc/$PID/smaps_rollup` every 1 s; `jcmd $PID GC.heap_info` for heap; `jcmd $PID VM.native_memory summary` (start with `-XX:NativeMemoryTracking=summary`) to subtract JVM-tracked areas. RSS minus (heap committed + metaspace + code + thread + NMT-visible internal) estimates untracked native, i.e. Unsafe-malloc'ed regions.
- Flush activity: `nodetool tpstats` MemtableFlushWriter, and the `system.log` "Enqueuing flush" lines; writer stalls via metric `WaitingOnFreeMemtableSpace` (`type=Table,name=WaitingOnFreeMemtableSpace`).
- Cannot observe directly: per-region slack and the `RACE_ALLOCATED` stash in a live node (a debugger or heap dump only); glibc retention after free (RSS may not drop after flush; use peak, not final).

**B3e. Procedure.**
1. Copy the tree, build the stock jar, plus the 256 KiB and 4 MiB variants, in separate scratch copies.
2. Configure as in B3a, with a unique data dir under local disk; start with `bin/cassandra -f` in a background shell recording the PID.
3. Create the keyspace (RF 1) and table. Warm up with 200 MB of writes, flush with `nodetool flush`, and record baseline RSS. **[Amended 2026-10-26: no warm-up writes (they would leave the first memtable and glibc arenas in a state the other arms do not share); the baseline is `RssAnon` after the node serves, 20 s idle and two `GC.run`.]**
4. Start the samplers (JMX gauges and `RssAnon` every 200 ms instead of 1 s, NMT summary every 5 s).
5. Run the 2 GB workload. Record peak `AllMemtablesOffHeapDataSize`, peak RSS-above-baseline, number of flushes.
6. Stop the node (`nodetool drain`, then kill the PID), delete the data dirs, check `pgrep -u $USER -f CassandraDaemon` is empty.
7. Repeat steps 2-6 for each variant: 3 `MAX_REGION_SIZE` builds at 64 MiB, then 128 MiB and 256 MiB with the stock build. Repeat each run 3 times. **[Amended 2026-10-26, audit: run 1 is five arms, `m256`, `m1024` (stock, 64 MiB), `m4096`, `o128`, `o256` (stock), plus one repeat of `m1024` for a noise estimate, six lifetimes instead of 15. The readings are single-run relations on direct counters (JMX gauges, blocked counter, flush lines), and 15 lifetimes of about 2 GB each do not fit one session. A reading inside the noise band of the two `m1024` runs is not read as a difference; run 2 may add repeats.]**

**B3f. Predictions.**
- Stock build, 64 MiB: peak `AllMemtablesOffHeapDataSize` is at or below about 64 MiB plus a few MiB overshoot (blocking writers), and flushes occur at about the cleanup threshold: first flush when charged use passes about 64 x 1/3 = 21 MiB (plus reclaiming). Peak RSS-above-baseline is the charged peak plus slack (<= about 5 percent for 100 KB cells) plus the stash (<= 16 MiB), plus malloc fragmentation. **[Amended 2026-10-26, audit; replaces the flush and RSS sentences just above, per the B3a threshold change:** peak `AllMemtablesOffHeapDataSize` is in [0.9 L, 1.05 L] for the 1 MiB build (writers block at L; `BlockedOnAllocation` count grows; at least 2 `Enqueuing flush of` lines for `ks.t`, the first near 0.99 L, not 21 MiB). Peak `RssAnon` above the baseline (taken after the node serves, 20 s idle, two `GC.run`) is at most 1.3 L. `RssAnon` counts touched pages and the unused tail of an abandoned region is never written, so slack (31 percent at 256 KiB, 5.4 percent at 1 MiB for 100,000-byte cells) mostly stays out of `RssAnon`; the capacity-level slack is read in the unit tier only.**]
- Across `MAX_REGION_SIZE` 256 KiB, 1 MiB, 4 MiB at 64 MiB: peak charged and peak RSS-above-baseline differ by only a few MiB (slack and stash scale with region size: slack up to one `MAX_CLONED_SIZE` per region, stash up to 8 x sum of size classes), and are nowhere near proportional to the constant (not a 16x spread). **[Amended 2026-10-26, audit, quantifies "a few MiB": the three peak charged values are within 0.05 L of each other (3.2 MiB at 64 MiB); the three peak `RssAnon` deltas have a spread (max minus min) of at most 0.25 L (16 MiB) and a max/min ratio of at most 1.3, far from the 16x spread of the constant.]**
- `memtable_offheap_space` 64 -> 128 -> 256 MiB (stock): peak charged and peak RSS-above-baseline roughly double each step, within about 15 percent of the limit plus constant overheads. This is the positive control. **[Amended 2026-10-26: peak charged is in [0.9 L, 1.05 L] for each L; the `RssAnon` peak-delta ratios 128/64 are in [1.5, 2.5] and 256/64 in [3.0, 5.0]; `BlockedOnAllocation` grows in each arm.]**
- Number of regions in a live memtable is not visible, but total charged bytes are many times 1 MiB (tens of MiB), showing that the constant is not the cap.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak RSS growth and charged peak track `memtable_offheap_space` across 64/128/256 MiB, but stay flat (spread under about 10 MiB) across `MAX_REGION_SIZE` builds | Claim confirmed: usage follows the pool limit, not the constant. **[Amended 2026-10-26, audit: "flat" is the B3f quantification (charged within 0.05 L; `RssAnon` delta spread <= 0.25 L and max/min <= 1.3, replacing "under about 10 MiB"), and the row also needs direct disallow evidence: the `BlockedOnAllocation` count grew and the table flushed at least twice in every arm of the sweep.]** |
| Peak RSS growth proportional to `MAX_REGION_SIZE` at fixed `memtable_offheap_space` | Claim refuted |
| Charged peak stays flat across `memtable_offheap_space` values (control did not move) | Not confirmed (limit not binding or wrong allocation type): check `offheap_objects`, workload size and the metric |
| Peak charged use never reaches the limit (no flush, no waiting) | Not confirmed: increase write volume or lower the limit |
| RSS-above-baseline exceeds charged peak by far more than slack plus 16 MiB stash | Other unaccounted native users or fragmentation; report it as the gap, not as the constant's effect |
| Charged peak exceeds `memtable_offheap_space` by tens of MiB | Overshoot from blocking writers; a cap violation of the pool itself, not related to the region constant |

**B3h. Controls.** Identical workload, row count, heap and direct-memory settings across runs. Restart and wipe the data dirs between runs. Positive control is the `memtable_offheap_space` sweep with the stock build. Baseline RSS taken after warmup, with `MALLOC_ARENA_MAX` fixed. Check `memtable_allocation_type` in `system.log` startup output ("Memtables allocating with off-heap objects", `AbstractAllocatorMemtable.java:107`). Repeat each run 3 times to separate noise.

**B4. Risks and cleanup.** Disk: up to about 4 GB per run on local disk (sstables plus commit log); delete the data, commitlog, hints and saved_caches directories after each run, and never put them on shared storage. Never build in the shared source tree. Memory: the 1 GiB heap plus about 400 MiB native stays well within a normal node; the unit tier at L=1 GiB uses at most about 300 MB of native memory, so run it with at least 2 GB free. Processes: stop the Cassandra JVM and every poller; verify with `pgrep -fl "CassandraDaemon|java"` and `jps` that nothing is left. Remove scratch builds when done.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/utils/memory/NativeAllocator.java
- src/java/org/apache/cassandra/utils/memory/NativePool.java
- src/java/org/apache/cassandra/utils/memory/MemtablePool.java
- src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java
- src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
- src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java (excerpt)
- src/java/org/apache/cassandra/config/Config.java (grep)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (grep)
- src/java/org/apache/cassandra/db/rows/NativeCell.java, db/NativeClustering.java, db/NativeDecoratedKey.java (grep)
- conf/cassandra.yaml (excerpt), conf/jvm-server.options (grep)
- test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java (excerpt)

## D. Stage-4 feedback

**Step-0 audit amendments, 2026-10-26 (stage 4, before run 1; each is also marked in place above).** (1) B2c: N for cases C and D (1000) and the exact shape of case E, and that variants run cases A to D. (2) B2e: the advice to skip C and D at 256 KiB is dropped. (3) B2f case B: slack is 5.38 percent (5,381,888), not 4.9 percent. (4) B2f constant variants: the "<=5 percent" clause is replaced by exact replay values (31.07 percent slack at 256 KiB for s = 100000). (5) B2g: "total" defined, two rows added. (6) B3a: `memtable_cleanup_threshold: 0.99`, `memtable_flush_writers: 1`, `commitlog_total_space: 4096MiB`, tmpfs directories, table without compression. (7) B3e: six lifetimes instead of 15, no warm-up, 200 ms sampling. (8) B3c: key layout. (9) B3f/B3g: flush and RSS sentences replaced to match the 0.99 threshold; "few MiB" and "under about 10 MiB" quantified; the confirming row needs the blocked counter. None of these depends on a reading.

**Stage-4 feedback, 2026-10-26** ([results](../../stage4-runtime-verification/results/max-region-size-region-allocate-capacity--autonomous.md); case file frozen at sha256 `9d344c9c...a48c`, prediction tables `885629d6...e2ed`).

- **Unit tier: Confirmed, does not cap.** All twelve fill runs (cases A to D on the 256 KiB, 1 MiB and 4 MiB builds) match the B2f replay and literals exactly: stock A 200,269,824 in 197 regions, B 105,381,888 in 101 (slack 5.38 percent), C 131,072,000 in 125, D 131,073,000 in 1000; the 256 KiB build gives 31.07 percent slack for s = 100000 (500 regions); the 4 MiB build 4.33 percent (27 regions). Charged bytes are identical across the three builds; max capacity equals the constant. The `limit` run is the positive control (writer parks at L; a blocking group overshoots to 17,700,000 > 16,777,216). The 8-thread run leaves 10.4 MB in the static `RACE_ALLOCATED` stash (never more than 7 per class), uncharged.
- **Cluster tier: Not confirmed (no matching row).** Charged peaks (`AllMemtablesOffHeapDataSize`) were 60.4 to 63.6 MiB over nine lifetimes at L = 64 MiB on the three builds (flat to 0.05 L) and 119.0 and 251.0 MiB at L = 128 and 256 MiB; `BlockedOnAllocation` and MEMTABLE_LIMIT flushes in every arm. The frozen real-resource relations did not hold on single lifetimes: `RssAnon` peak above the baseline was 99 to 150 MiB at L = 64 (B3f: <= 1.3 L = 83 MiB) and the knob-axis spread was 50.7 MiB (B3f: <= 16 MiB, ratio <= 1.3; seen 1.51). Two identical `m1024` lifetimes differ by 30 MiB, and the JVM's own native tracking grows 56 to 84 MiB in every arm independent of L and build, so the RSS bound and flatness thresholds, which were derived (audit amendment) without a noise estimate, are too tight. Three repeats per build (supplement) give means 121.3 (256 KiB), 109.4 (1 MiB), 126.5 (4 MiB) MiB, within noise and not proportional to the 16x constant.
- **What this changes in the design (for a restart of the cluster tier, if wanted):** make the charged gauge the primary relation and `RssAnon` a secondary one with a tolerance of at least 40 MiB plus the JVM-side growth; do not state slack in cluster predictions (untouched tail pages are not resident, unit tier reads it directly); keep `memtable_cleanup_threshold: 0.99` (without it the pool limit is not reached).
- **Estimate:** `negative` stands; the unit tier and the charged gauge say it does not cap. Outcome class recorded as undetermined by the protocol's wording because of the cluster row; the evidence is a true negative.


