# MAX_REGION_SIZE — verification solution  <!-- file: cases/max_region_size-tryswapregion-minsize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/memory/NativeAllocator.java:166` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: `MAX_REGION_SIZE` is a hard-coded per-region size ceiling, not a cap on how much off-heap memory a node uses; the total is governed by `memtable_offheap_space` through a separate counter that charges requested bytes, not region capacity. |
| Ground | The constant bounds only the granularity of one `malloc` slab (`NativeAllocator.java:168`). It is applied per allocator (one per live memtable), is not consulted by the pool accounting (`MemtablePool.java:151-160`), and does not apply to allocations larger than `MAX_CLONED_SIZE`, which get an exact-size region of any size (`NativeAllocator.java:144-145,186-198`). Total native memory = accounted bytes + unaccounted region slack (grows with the number of live memtables) + stashed race regions. |

## A. Constraint trace

**A1. The constraint.** (Earlier AI trace verified and corrected.)

- Line 166 is `if (minSize > size)` inside `trySwapRegion(Region current, int minSize)` (`NativeAllocator.java:158-184`). It is a size-selection step, not a limit check: nothing is rejected or blocked at this line. `minSize` is the allocation size passed from `allocate` (`NativeAllocator.java:154`). `size` is `MIN_REGION_SIZE` when there is no current region (`:164`), else `current.capacity * 2` (`:165`). If the request does not fit, `size = Integer.highestOneBit(minSize) << 3` (`:167`), i.e. 4-8x the request. Then `size = Math.min(MAX_REGION_SIZE, size)` (`:168`).
- The constraint that bounds the result is `MAX_REGION_SIZE`: kind constant (`private final static int`), declared at `NativeAllocator.java:46`, value `1 * 1024 * 1024` = 1 MiB, unit bytes. Companions: `MAX_CLONED_SIZE` = 128 KiB (`:47`), `MIN_REGION_SIZE` = 8 KiB (`:48`). The class comment says regions scale from 8 KiB to 1 MiB and serve allocations up to 128 KiB (`:34-43`).
- Default: a literal, no derivation. Not settable via cassandra.yaml, a `-D` property or JMX; changing it needs a source edit and rebuild.
- Correction to the earlier trace: the check at :166 does not compare against a limit; and `MAX_REGION_SIZE` does not "cap memtable allocation" in any total sense. Also, the clamp at :168 is never below the request for requests up to 128 KiB (`highestOneBit(131072) << 3` = 1 MiB), so the clamp cannot make a region too small for a request that reaches this path. Requests above 128 KiB never reach `trySwapRegion` (`:144-145`).
- The class is only in use when `memtable_allocation_type: offheap_objects` (`AbstractAllocatorMemtable.java:106-108` builds `NativePool`; `NativePool.java:28-32` builds `NativeAllocator`). The yaml default is `heap_buffers` (`conf/cassandra.yaml:825`; `Config.java:524`), so by default this code does not run.
- Related real limit (a different constraint): `memtable_offheap_space` (`Config.java:188-189`), default heap/4 in MiB when unset (`DatabaseDescriptor.java:583-584`), yaml `conf/cassandra.yaml:797-799`, restart required. It becomes `SubPool.limit` (`MemtablePool.java:105,117-119`).

**A2. What it caps.** Resource: off-heap (native, `malloc`) memory. What `MAX_REGION_SIZE` bounds: the capacity of a single slab region obtained by `MemoryUtil.allocate(size)` (`NativeAllocator.java:176`; `MemoryUtil.java:81-84` calls `Native.malloc`). The quantity compared at :166 is request size vs candidate region size (a sizing computation). The quantity compared to the real off-heap limit is `SubPool.allocated + size > limit` (`MemtablePool.java:156`), where `size` is the requested bytes, charged at `NativeAllocator.java:141` before any region is picked.

**A3. Mechanism.**
1. `allocate(size, opGroup)` first charges `size` to the off-heap sub-allocator (`NativeAllocator.java:141`). `SubAllocator.allocate` (`MemtableAllocator.java:169-197`) calls `parent.tryAllocate` (`MemtablePool.java:151-160`); if over limit it blocks on `hasRoom` (`MemtableAllocator.java:187-195`) unless the `opGroup` is blocking, in which case it overshoots (`:180-184`).
2. If `size > MAX_CLONED_SIZE` (128 KiB) it goes to `allocateOversize`, a dedicated `Region` of exactly `size` bytes (`:186-198`), so a single allocation can exceed `MAX_REGION_SIZE`.
3. Otherwise loop: bump-allocate in `currentRegion` (`:147-152`, `Region.allocate` at `:269-277` via `getAndAdd`); if full, `trySwapRegion` (`:154`).
4. `trySwapRegion` picks the new size (:164-168). It then reuses a stashed race-allocated region of that size from the static `RACE_ALLOCATED` map (`:51-57,171-172`) or mallocs a new one (`:175-176`). `compareAndSet` installs it and adds it to `regions` (`:180-181`); a CAS loser is stashed (up to 8 permits per size, `:212`) or freed (`:182-183`).
5. Regions are freed only when the allocator is discarded (`setDiscarded`, `:200-206`), so a memtable holds all its regions until flush.
6. Bypass/overshoot paths: (a) region slack: the unfilled tail of the current region and the abandoned tail of each replaced region are real malloc'd capacity but were never charged (only requested bytes are); (b) one active region per live memtable, so slack scales with the number of tables with non-empty memtables; (c) up to 8 stashed regions per size class (8 KiB..1 MiB, 8 sizes) held globally and uncharged (`:208-227`); (d) oversize regions exceed 1 MiB; (e) the blocking `opGroup` overshoot above.

**A4. Other consumers of off-heap memory outside this constraint.** Direct buffers (`BufferPool`/chunk cache `file_cache_size`, `DatabaseDescriptor.java:575-576`), mmap'd commit log and sstable segments, bloom filters / index summaries / compression metadata off-heap, netty direct buffers, JVM metaspace, thread stacks and code cache. All are unaffected by this constant.

**A5. Evidence beyond the source.** Existing test `test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java` (builds a `NativePool` with tiny limits and checks `owns()`/`used()` bookkeeping against requested sizes, not region capacity; reusable as a harness model). Cassandra docs on memtable settings: https://cassandra.apache.org/doc/5.0/cassandra/managing/configuration/cass_yaml_file.html (`memtable_offheap_space`, `memtable_allocation_type`). Otherwise none.

## B. Verification solution

**B1. Claim under test.** Native memory held by `NativeAllocator` is not bounded by `MAX_REGION_SIZE`: (i) the sum of region capacities exceeds the bytes charged to the off-heap limit, by slack that grows with the number of live allocators, so the real off-heap footprint can exceed `memtable_offheap_space` accounting; and (ii) a single allocation above 128 KiB gets a region larger than 1 MiB. The positive control is that `memtable_offheap_space` does bind the charged bytes under the same workload.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c509/`), never build in the shared tree. `cd $WORK/c509 && ant jar` (or `ant build-test`). Add a new test class `test/unit/org/apache/cassandra/utils/memory/NativeAllocatorRegionTest.java` in package `org.apache.cassandra.utils.memory` (so the protected `NativeAllocator(NativePool)` constructor and package-private `SubPool.tryAllocate` are visible). Run: `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NativeAllocatorRegionTest`. JVM options: defaults of `ant testsome`, plus `-Xmx512m`. Private state is read by reflection (`setAccessible(true)`, allowed on JDK 11): `NativeAllocator.regions` (`:60`), `Region.capacity` (`:244`), `RACE_ALLOCATED` (`:51`).

**B2b. Knobs.** (1) Allocation size `s` per call: 64 B, 100 KiB (102400), 131072 (= `MAX_CLONED_SIZE`, last size that uses regions), 131073 (first oversize), 4 MiB. (2) Pool off-heap limit `L` passed to `new NativePool(1<<30, L, 0.75f, cleaner)`: 10000 B, 2 MiB, 1 GiB. (3) Number of allocators `A` (a new `NativeAllocator(pool)` each): 1, 10, 100. Set in code. The constant itself cannot be changed without editing source; as an optional extra, a second build with `MAX_REGION_SIZE` changed to 256 KiB (and the same test) shows regions follow the constant while charged bytes do not.

**B2c. Workload.** Use one `OpOrder` group (`new OpOrder().start()`, as in `NativeAllocatorTest.setUp`). Cases:
- C1: one allocator, 64 B x 20000 calls (1,280,000 B charged, > 8+16+...+512 KiB = 1016 KiB so the 1 MiB class is reached).
- C2: `L` = 10000, 100 calls of 100 B (exactly 10000 B charged, at the limit). Then `pool.offHeap.tryAllocate(1)` is expected false.
- C3: one allocation per size in `s` list for 100 KiB, 131072, 131073, 4 MiB on fresh allocators.
- C4: `A` allocators, each given 64 B x 100 calls (6400 B charged each).
- Positive control P1: with `L` = 2 MiB, run 64 B calls from a second thread until `pool.offHeap.used()` reaches `L`, and confirm the next call blocks (thread state WAITING on the `hasRoom` queue after 1 s) until `allocator.setDiscarding()/setDiscarded()` or a `released(...)`.

**B2d. Observables and instruments.** Charged bytes: `allocator.offHeap().owns()` and `pool.offHeap.used()` (the operand at `MemtablePool.java:156`). Capacity: sum over `regions` of `Region.capacity` and the max of those capacities, via reflection. Region count and sizes list (to check 8K,16K,...,1M doubling). Not directly observable: actual page residency (malloc'd but untouched pages); this tier measures reserved capacity only. Sampled once after each case.

**B2e. Procedure.** 1) Copy tree, build. 2) Write the test class with cases C1-C4 and P1, each printing/asserting charged bytes, total capacity, max capacity, region count. 3) Run `ant testsome`. 4) For each case compare per predictions. 5) Call `allocator.setDiscarding(); allocator.setDiscarded()` at the end of each case so native memory is freed (`:200-206`).

**B2f. Predictions (before any run).**
- C1: charged = 1,280,000 exactly. Region capacities are 8192, 16384, ..., 524288, then 1048576 (and further 1 MiB regions as needed); max capacity = 1,048,576 and never greater. Total capacity > charged (slack > 0, below 1 MiB + the fill-in fragments).
- C2: charged = 10000 = `L`; capacities are 8192 then 16384 (total 24576 > L); `tryAllocate(1)` returns false. So reserved capacity exceeds the limit while charged is at the limit.
- C3: 100 KiB: one region of 524288 (`highestOneBit(102400)=65536`, x8); 131072: one region of 1048576; 131073 and 4 MiB: a single region of capacity exactly 131073 / 4194304 (oversize), i.e. max capacity > 1 MiB for the 4 MiB case. Charged equals the request in every case.
- C4: total capacity ≈ A x 8192 (first region each), charged = A x 6400, so slack = A x ~1792, linear in A.
- P1: the blocked call confirms the charged counter, not region size, is what stops writers.
- Optional rebuild with 256 KiB constant: max capacity = 262144 for C1 while charged unchanged.
What would show the claim wrong: any case where total region capacity is <= charged bytes for partially filled regions, or an oversize allocation producing a region of <= 1 MiB, or `used()` changing with region capacity.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Charged flat across region-size variants (optional rebuild) while capacity follows the constant; C2 capacity > L with `tryAllocate` false; C3 oversize region > 1 MiB; P1 blocks at charged = L | Claim confirmed: usage does not follow `MAX_REGION_SIZE`; the accounting limit is what binds |
| Charged bytes (`owns`/`used`) change when `MAX_REGION_SIZE` changes, or equal region capacity | Claim refuted: charging is by region |
| Max capacity always <= 1 MiB including 4 MiB allocation | Claim (ii) refuted: oversize path does not exist as traced |
| C1 never reaches 1 MiB regions, or P1 does not block (control did not move) | Not confirmed: workload too small or limit not reached; rerun with larger counts |

**B2h. Controls.** P1 is the positive control (a cap that binds: pool limit). A zero-slack control: allocate exactly 8192 B once; capacity 8192 = charged, showing the measurement itself does not invent slack. Repeat each case 3 times on fresh allocators to rule out race-stash reuse (`:171-172`); clear `RACE_ALLOCATED` stashes by reflection between runs or use a fresh JVM per case.

### B3. Cluster tier

**B3a. Environment and build.** One node, local disk of known size (>= 20 GiB free) for data, commit log, hints and saved caches. Copy the tree to local disk, `ant jar`, run from `bin/cassandra -f` in that copy. JDK 11. JVM: `-Xms2G -Xmx2G -XX:+AlwaysPreTouch` (heap fixed and resident so deltas are non-heap), G1. Configuration (conf/cassandra.yaml in the copy): `memtable_allocation_type: offheap_objects`, `memtable_heap_space: 512MiB`, `memtable_offheap_space: 512MiB` (run R-big) or `32MiB` (run R-small, the positive control), `memtable_cleanup_threshold: 0.99` (R-big only, so no size-triggered flush; value allowed by `DatabaseDescriptor.java:770-773`; deprecated warning expected), `commitlog_total_space: 8GiB`, single token, no other tables. Keyspace `ks` RF=1.

**B3b. Knobs.** `memtable_offheap_space` in {512MiB, 32MiB} (yaml, restart). Number of tables `T` in {1, 50, 150} (each has its own memtable and so its own `NativeAllocator`; `NativePool.java:28-32`). Per-table data volume `D` = 1.2 MiB of cell payload (> 1016 KiB so each memtable has reached its 1 MiB region class). `MAX_REGION_SIZE` is not settable at runtime.

**B3c. Workload.** `T` tables `ks.t0..t(T-1)` `(pk int, ck int, v blob, PRIMARY KEY (pk, ck))`. Per table write 1200 rows with 1000-byte `v` (about 1.2 MB payload, 1 partition, via cqlsh `COPY`, a python-driver script, or `cassandra-stress user` profile with the per-table insert) so the memtable of every table has requested bytes just above 1 MiB. Arithmetic: R-big, T=150: charged about 150 x 1.3 MiB = 195 MiB < 512 MiB x 0.99, so no flush; per-table region capacity is 1016 KiB + 1 MiB class, slack up to about 1 MiB per table, so up to about 150 MiB of reserved but uncharged capacity. R-small: the same workload with 32 MiB limit exceeds the limit at about 25 tables and forces flushes. Additional 4 MiB-blob insert (one row, `v` = 4 MiB, within `max_mutation_size`) to a fresh table for the oversize path. Duration: minutes; no flush wait needed for R-big.

**B3d. Observables and instruments.** (1) Charged bytes: JMX `org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=*,name=MemtableOffHeapSize`, summed (or `nodetool tablestats ks` "Off heap memory used (total)" for memtable); `MemtablePool` metrics `type=MemtablePool`. (2) Flush counts: `nodetool tablestats` memtable switch count, and `nodetool flush` not run in R-big. (3) Process memory: `/proc/$PID/status` fields `RssAnon` and `VmData`; `/proc/$PID/smaps_rollup`; optionally `pmap -x $PID`. (4) Optional exact malloc sizes: `bpftrace -e 'uprobe:/lib/x86_64-linux-gnu/libc.so.6:malloc /pid==$PID && arg0>=8192/ { @sz = hist(arg0); }'` (requires privileges; skip if unavailable). Limit of the instruments: `malloc` slabs of 1 MiB are mmap-backed, so untouched tail pages are not resident; `RssAnon` therefore approximates charged bytes, while `VmData` (virtual) reflects reserved capacity. The tier reports both and does not claim the slack is resident. Sample baseline and end state after a 30 s settle; take 3 samples each.

**B3e. Procedure.**
1. Copy tree to `$WORK/c509`, `ant jar`; set the yaml per B3a; start node; wait for "Starting listening for CQL clients"; record PID.
2. Record baseline: `RssAnon`, `VmData`, MemtableOffHeapSize sum (0), flush counts.
3. For T in {1, 50, 150}: create T tables, write D to each, wait 30 s, record RssAnon, VmData, summed MemtableOffHeapSize, switch counts. Between T values restart the node with a wiped data dir, to keep baselines equal (or use separate keyspaces and compare deltas).
4. Write the 4 MiB blob row to a new table; record deltas.
5. Stop node, change `memtable_offheap_space: 32MiB` (remove cleanup threshold override), wipe data, restart, repeat step 3 with T=150, recording MemtableOffHeapSize samples every 5 s during writes and flush counts.
6. Stop node (`nodetool drain` then kill), verify no `java` process of this run remains (`pgrep -f CassandraDaemon`).

**B3f. Predictions (before any run).**
- R-big: no flush occurs (switch counts unchanged). Sum of MemtableOffHeapSize about T x (payload+per-cell overhead) and scales linearly with T. ΔVmData - ΔMemtableOffHeapSize is positive and grows roughly linearly with T, between about 0 and 1 MiB x T (R-big T=150: tens of MiB); ΔRssAnon is close to ΔMemtableOffHeapSize (within allocator overhead), i.e. reserved capacity exceeds charged bytes without all being resident. Nothing in these numbers changes at region-size boundaries because the constant is fixed; the independent variable is T, not `MAX_REGION_SIZE`.
- 4 MiB blob: ΔVmData about 4 MiB for one row (a single 4 MiB malloc, larger than `MAX_REGION_SIZE`), charged +4 MiB.
- R-small (positive control): summed MemtableOffHeapSize stays <= about 32 MiB plus overshoot from blocking `opGroup`s, flushes occur (switch counts > 0), and writes stall at times; RssAnon growth stays bounded near that figure rather than the R-big value.
What would show the claim wrong: VmData growth minus charged bytes not growing with T (or negative), or charged bytes in R-big not tracking payload, or R-small charged bytes not bounded.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| R-big: Δ(VmData) - Δ(charged) grows with T; no flush; R-small: charged bounded near 32 MiB with flushes | Claim confirmed: reserved native capacity is not bounded by the region constant or the accounted limit; `memtable_offheap_space` governs charged bytes only |
| Δ(VmData) - Δ(charged) about 0 for all T | Claim refuted: usage follows charged bytes; no unaccounted slack (or VmData noise masks it; check with bpftrace) |
| R-small charged bytes grow past the limit without flushes or stalls | Positive control failed: the pool limit did not bind, so conclusions about accounting are void; check `memtable_allocation_type` actually `offheap_objects` in the log ("Memtables allocating with off-heap objects", `AbstractAllocatorMemtable.java:108`) |
| R-big flushes occurred, or RSS dominated by other growth (heap not pretouched, compaction) | Not confirmed; rerun with controls fixed |
| 4 MiB row shows no virtual growth of about 4 MiB | Oversize path not confirmed in vivo; rely on unit tier C3 |

**B3h. Controls.** Heap fixed with `AlwaysPreTouch`; idle-node drift sample (same wait, no writes) to subtract background VmData/RssAnon change; `memtable_allocation_type: heap_buffers` run with identical workload as a negative control (expected no NativeAllocator regions: MemtableOffHeapSize about 0); positive control R-small as above; T=1 as the near-zero-slack case.

**B4. Risks and cleanup.** Disk: data, commit log and hints on local disk of known size; R-big writes under 1 GiB in total (150 x 1.3 MiB plus commit log); do not use shared storage or the shared source tree. Memory: R-big can add up to about 200 MiB virtual; the node needs under 4 GiB RSS (2 GiB heap). Processes: node, optional bpftrace, JMX clients; stop all, run `pgrep -fl 'CassandraDaemon|bpftrace'` to confirm none are left. Unit tier: test JVM exits on its own; delete `$WORK/c509` and the data directories when finished.

## C. Sources read

- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativePool.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemoryUtil.java` (excerpt)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java` (excerpt)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java` (excerpt)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java` (excerpts)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (excerpts)
- `/users/jason92/cassandra-5.0.9/conf/cassandra.yaml` (excerpt)
- `/users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java`
- https://cassandra.apache.org/doc/5.0/cassandra/managing/configuration/cass_yaml_file.html (cited, not fetched)

## D. Stage-4 feedback

`none yet`
