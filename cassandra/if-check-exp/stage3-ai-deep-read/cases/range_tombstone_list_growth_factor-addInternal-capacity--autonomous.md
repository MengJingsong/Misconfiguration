# range_tombstone_list_growth_factor — verification solution  <!-- file: cases/range_tombstone_list_growth_factor-addInternal-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/RangeTombstoneList.java:668` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-sonnet-5-5 (Claude Code), 2026-10-23 |
| Estimate | `negative`: the factor sets how much spare array capacity a `RangeTombstoneList` allocates when full; it does not cap how much memory the list or the node can use. Heap grows with the number of tombstones whatever the factor is. |
| Ground | `RangeTombstoneList.java:668` only asks "is the array full?" and grows it, with no refusal path. The factor (valid range 1.2–5.0 over JMX) only scales spare slots, which are bounded by (factor−1)×n slots at 20–28 bytes each. The real bounds are elsewhere (memtable heap space, `tombstone_failure_threshold`, partition size). |

## A. Constraint trace

**A1. The constraint.**
- **Name and kind:** `range_tombstone_list_growth_factor`, a configuration entry. The target line also reads `initial_range_tombstone_list_allocation_size`, a sibling entry that gives the starting capacity.
- **Declared:** `src/java/org/apache/cassandra/config/Config.java:802` (`public volatile double range_tombstone_list_growth_factor = 1.5;`). The sibling is at `Config.java:798` (default 1).
- **Unit:** a dimensionless multiplier on the array capacity (slots).
- **Default:** the literal 1.5. It is not derived, and it is not in `conf/cassandra.yaml`; the grep over `conf/*` found nothing.
- **How to set it:**
  - yaml key `range_tombstone_list_growth_factor`, a restart is needed. Nothing validates the yaml value at startup: `DatabaseDescriptor` has only a plain getter and setter (`DatabaseDescriptor.java:4649-4657`).
  - JMX `StorageServiceMBean.setRangeTombstoneListResizeGrowthFactor(double)` (`StorageServiceMBean.java:1172`), implemented at `StorageService.java:6903-6915`. It rejects values outside [1.2, 5.0], and no restart is needed.
  - The read-back is `getRangeTombstoneResizeListGrowthFactor()` (`StorageService.java:6898`).
  - I found no nodetool command for it.

**A2. What it caps.**
- **Resource:** on-heap memory, and only indirectly.
- **Compared quantity:** the check at `RangeTombstoneList.java:668` compares `size` (tombstones stored) with `capacity()` (`starts.length`, line 658). It is not a limit comparison. It only decides whether to grow.
- **Effect of the factor:** it sets how many spare slots are added across the four parallel arrays `starts`, `ends`, `markedAts`, `delTimesUnsignedIntegers` (lines 60-63). Per slot that is 2 references (4 B each with compressed oops, 8 B without) + 8 B + 4 B, so 20 or 28 B.
- **Accounting:** `unsharedHeapSize()` (lines 770-778) counts `ObjectSizes.sizeOfArray` of the whole arrays, so the spare capacity is counted. It also counts `boundaryHeapSize`, the bound objects themselves.

**A3. Mechanism.**
1. `MutableDeletionInfo.add(RangeTombstone, comparator)` creates the list on first use with capacity `initial_range_tombstone_list_allocation_size` (`MutableDeletionInfo.java:117-118`), then calls `ranges.add(tombstone)` (line 120).
2. `RangeTombstoneList.add(...)` (lines 157-179) calls `addInternal` directly when the list is empty or the new tombstone sorts last (lines 159-170). Otherwise it goes through `insertFrom`, which also ends in `addInternal` (lines 608, 629, 635, 653).
3. `addInternal` (lines 664-675):
   - If `size == capacity()` it calls `growToFree(i)` (line 669).
   - Otherwise, if `i < size`, it shifts elements with `moveElements(i)` (line 671).
   - Then it stores the element and increments `size`.
4. `growToFree` (lines 680-689) computes `newLength = ceil(capacity * factor)`. If `newLength <= capacity` it falls back to `capacity*3/2 + 1`. `capacity` 0 with a factor of 1.5 gives 0, so the fallback gives 1. It then calls `grow(i, newLength)`, which copies all four arrays (lines 700-739).
5. **Outcomes at the limit:** the only outcome is that the arrays are reallocated larger. There is no rejection, eviction or error path.
6. **Overshoot and bypass:**
   - The old and new arrays coexist during the copy, so there is a transient peak of about (1+factor)×capacity slots.
   - `copyArrays` / `grow(int)` (line 694) is a second growth path; I did not read `copyArrays`.
   - **Memtable path:** `BTreePartitionUpdater.merge` calls `existing.mutableCopy().add(update...)` and then `onAllocatedOnHeap(newInfo.unsharedHeapSize() - existing.unsharedHeapSize())` (`BTreePartitionUpdater.java:120-121`).
     - `mutableCopy()` calls `ranges.copy()` (`MutableDeletionInfo.java:83`), which trims the arrays to exactly `size` (`RangeTombstoneList.java:109-112`).
     - The next `addAll` then fills the list and triggers one growth by the factor. After each merge the memtable list therefore carries about (factor−1)×n spare slots, and that spare capacity is charged to the memtable's heap accounting.
   - **Accounting quirk:** `add()` line 178 does `boundaryHeapSize += start/end.unsharedHeapSize()`, and `setInternal` (line 766) has already added the same amount, so on the `add()` path the bound sizes appear to be counted twice. This is a side observation for the unit tier (see B2g).

**A4. Other consumers.**
- Memtable heap/off-heap limits (`memtable_heap_space`, `memtable_cleanup_threshold`) are what really bound range tombstone memory.
- The bound objects (`ClusteringBound` and their `ByteBuffer` values) are cloned onto the heap (`BTreePartitionUpdater.java:117-120`). They are usually larger than the array slots.
- Read-path `MutableDeletionInfo` instances are limited by the tombstone scan thresholds (`Config.java:534-535`, `ReadCommand.java:594`).
- The row cache, the key cache and SSTable index structures use the same heap and are unaffected by this knob.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/db/RangeTombstoneListTest.java:579-605` covers only the JMX range check, not memory.
- The `Config.java` javadoc and the "Introduce getRangeTombstoneResizeFactor" comments (lines 682, 117) show the knob was added to tune growth, not to cap usage.
- No external link used (not looked up).

## B. Verification solution

**B1. Claim under test.** Heap used by a `RangeTombstoneList` (and by a memtable holding range tombstones) is not capped by `range_tombstone_list_growth_factor`. It grows with the tombstone count N at every legal factor, and the factor only changes the spare-capacity slack, which is at most (factor−1)×N slots. Falsified if usage plateaus at a level set by the factor, or if the factor changes total usage by more than the slack bound.

### B2. Unit tier

> Amended 2026-10-23 (stage-4 step 0): see B5 R1, R2, R3, R6, R7.

**B2a. Environment and build.**
- Linux, JDK 11, Ant.
- Copy the tree to local disk: `cp -r ~/cassandra-5.0.9 /local/work/c509`. Never build in the shared tree.
- `cd /local/work/c509 && ant jar` (use `ant build-test` if the test target needs it).
- Add a new JUnit class `test/unit/org/apache/cassandra/db/RangeTombstoneListGrowthProbeTest.java` in the copy. Its `@BeforeClass` runs `DatabaseDescriptor.daemonInitialization()`.
- Run: `ant testsome -Dtest.name=org.apache.cassandra.db.RangeTombstoneListGrowthProbeTest`. The ant test target should pass the Jamm agent that `ObjectSizes` needs; check `build.xml` in the copy. If the agent is missing, add `-javaagent:lib/jamm-*.jar` to `test.jvm.args`.
- JVM options: `-Xmx2g`, `-XX:+UseCompressedOops` (default), kept the same for all runs.

**B2b. Knobs.**
- `DatabaseDescriptor.setRangeTombstoneListGrowthFactor(f)` for f ∈ {1.2, 1.5, 2.0, 5.0}: the JMX bounds and the default. The unit test may also call it with 1.0 and 0.5 to exercise the fallback `capacity*3/2+1` (line 686), since the setter has no range check.
- `DatabaseDescriptor.setInitialRangeTombstoneListAllocationSize(s)` for s ∈ {0, 1, 1024}.
- N ∈ {1_000, 10_000, 100_000} tombstones.

**B2c. Workload.**
- `new ClusteringComparator(Int32Type.instance)`.
- N non-overlapping tombstones `[2i, 2i+1]` built as `new RangeTombstone(Slice.make(...), DeletionTime.build(ts, nowInSec))`, added in sorted order with `list.add(...)`. This is the fast path of lines 167-170 and always reaches the `size == capacity()` branch at line 668.
- Arithmetic: starting from capacity 1, the number of growth events is about log_f(N). For f=1.5 and N=100_000 that is about 28 growths.
- Second pass: random-order insertion of the same tombstones to exercise `insertFrom`.

**B2d. Observables and instruments.**
- `list.unsharedHeapSize()` (the check's own usage-side value).
- `starts.length` read by reflection on the private field, for capacity.
- `list.size()`.
- Independently, `org.github.jamm.MemoryMeter.measureDeep(list)`, to cross-check the accounting (it is not available if the agent is not loaded).
- Not observable in this tier: GC behaviour and real RSS.

**B2e. Procedure.**
1. For each (s, f, N): set the knobs, build the list, add N tombstones, and record capacity, size, `unsharedHeapSize()`, `measureDeep`.
2. Also record the capacity after each growth step for N=1000, to get the sequence.
3. Repeat the same list through `list.copy()` and record the same values (capacity == size, trimmed).
4. Repeat the sequence for the random-order workload.
5. Record the `boundaryHeapSize`-related difference: `unsharedHeapSize()` minus the sum of array sizes minus EMPTY_SIZE, compared with N × (start+end bound sizes).

**B2f. Predictions (stated before any run).**
- Capacity after each growth is `ceil(cap*f)` as Java double arithmetic; with s=1 and f=2.0 it is 1,2,4,8,..., and with f=1.5 it is 1,2,3,5,8,12,18,... (computed by the same expression in the test, not hard-coded). f=1.0 and f=0.5 use the `cap*3/2+1` fallback.
- Final capacity ≥ N and < ceil(f·N)+1, so slack ≤ about (f−1)·N slots.
- `unsharedHeapSize()` grows linearly in N for every f. Going from f=1.2 to f=5.0 changes it by at most 20-28 B × (5.0−1.2) × N, and that is dominated by the N × (bound objects) term.
- After `copy()`, capacity == size, and heap is lower by exactly the slack.
- Prediction that would show the claim wrong: heap at fixed N is flat or capped as N grows, or the f=5.0 vs f=1.2 difference exceeds the slack bound.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Heap grows ~linearly in N at every f; f only moves it by ≤ slack bound | Claim confirmed: factor does not cap usage |
| Heap at fixed large N is flat in N or saturates at a value depending on f | Claim refuted: something caps it |
| Heap difference between f values is far above (f₂−f₁)·N·slot bytes | Claim refuted or unmodelled consumer; investigate |
| Positive control (`copy()` trimmed, capacity==size) shows heap = no-slack baseline, and varying N moves it linearly | Control worked; slack is attributable to the factor |
| N small enough that no growth occurs beyond the initial allocation | Limit not reached; not confirmed |
| `measureDeep` and `unsharedHeapSize()` disagree by about N × bound size | The line-178 double count is real; note for stage 4 |

**B2h. Controls.**
- The `copy()` baseline gives zero-slack heap.
- Varying N alone, at a fixed f, shows count-driven growth.
- Fixed JVM flags and a fresh JVM per (f) run, with a `System.gc()` and no other allocations between measurements.
- Repeat each run 3 times and require identical numbers (sizes are deterministic).

### B3. Cluster tier

> Amended 2026-10-23 (stage-4 step 0): see B5 R1, R3, R4, R5, R7, R8.

**B3a. Environment and build.**
- One node on Linux with JDK 11, built from a local copy of the tag (`ant jar`, `bin/cassandra -f`).
- Heap pinned: `-Xms2G -Xmx2G`, set in `conf/jvm11-server.options` in the copy.
- Local-disk data, commitlog and hints directories of known size, for example under `/local/work/node1/` (≥ 20 GB free), in `conf/cassandra.yaml`.
- `memtable_allocation_type: heap_buffers`.
- Pin `memtable_heap_space: 512MiB`; `memtable_cleanup_threshold` stays at its default.
- `tombstone_failure_threshold` raised so reads do not abort in the read check.

**B3b. Knobs.**
- `range_tombstone_list_growth_factor` ∈ {1.2, 1.5, 5.0}, set through yaml before start. Also check via JMX: `setRangeTombstoneListResizeGrowthFactor` for a runtime change.
- Positive control: `memtable_heap_space` ∈ {128MiB, 512MiB} with the same workload.

**B3c. Workload.**
- One table `t(pk int, ck int, v int, PRIMARY KEY (pk, ck))`.
- Range deletes through CQL, many per partition so that one partition's memtable `RangeTombstoneList` grows: `DELETE FROM t WHERE pk = 1 AND ck > 2i AND ck < 2i+1`, i = 0..N−1, in batches by `cassandra-stress` or a small Python/Java driver script.
- N = 50_000, then 500_000 per partition, across 1, 10 and 100 partitions.
- Arithmetic: each tombstone costs a few hundred bytes with its bounds, so 500_000 × ~250 B ≈ 125 MB, which is below `memtable_heap_space` at 512MiB. Use the 128MiB setting for the control so the cap binds and flushes occur.
- Duration: each run lasts until all deletes are acknowledged plus 60 s.

**B3d. Observables and instruments.**
- Memtable on-heap size: `nodetool tablestats ks.t`, field "Memtable data size" / "Memtable off heap memory used"; also JMX `MemtableOnHeapSize` on the table metrics.
- JVM heap used after full GC: `jcmd <pid> GC.heap_info` and `jstat -gc <pid> 1000`.
- Flush count: `nodetool tablestats` "Memtable switch count".
- Process RSS: `ps -o rss= -p <pid>`.
- Sampling: every 5 s during the load and once after a forced `nodetool flush` and `jcmd GC.run`.
- Not observable directly: the spare capacity inside one list. A heap histogram can show array counts: `jcmd <pid> GC.class_histogram` for `[Lorg.apache.cassandra.db.ClusteringBound;`, `[J` and `[I`.

**B3e. Procedure.**
1. Copy the tree, build, and set the options above for the first (factor) value.
2. Start the node; wait for `nodetool status` to report UN.
3. Create the keyspace (RF 1) and the table.
4. Run the workload; sample as in B3d.
5. Record memtable on-heap size and post-GC heap at the end of load, before any flush.
6. `nodetool flush`; record disk usage with `du -sm` on the data directory.
7. Stop the node (`kill`, then confirm with `pgrep -f CassandraDaemon`); wipe the data directories.
8. Repeat for each factor value and for the control settings.

**B3f. Predictions (stated before any run).**
- At fixed N, memtable on-heap size grows with N at each factor. The 1.2 → 5.0 difference is at most (5.0−1.2) × N × 20-28 B for single-partition runs (about 4 MB for N=50_000); it is small compared with the bound objects.
- Multi-partition runs: slack is per partition, so the absolute difference is smaller per tombstone.
- The memtable-space control: with 128MiB the memtable flushes (switch count > 0) and on-heap size stays under about 128MiB plus transient; with 512MiB it does not flush at 125 MB. Heap follows `memtable_heap_space`, but never the growth factor.
- Claim wrong if: on-heap size at the largest N is the same across N (a cap) at a level set by the factor, or the factor changes the heap by more than the slack bound.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Heap rises with N at all factors; factor changes it only within the slack bound | Claim confirmed |
| Heap rises with N and the factor-related gap is larger than the slack bound | Unmodelled consumer; the claim is not refuted but the bound needs revising |
| Heap plateaus as N grows, with the plateau depending on the factor | Claim refuted |
| Positive control: lowering `memtable_heap_space` causes flushes and a lower heap while the factor stays unchanged | Control worked; usage follows the real cap, and the factor is flat |
| The control showed no flushes or no change in heap | Cap not reached or control did not move; not confirmed |
| Load never reached memtable pressure at any N | Limit not reached; not confirmed |

**B3h. Controls.**
- The same table and load for every run, a fresh data directory each time, and the same JVM flags and heap.
- Run the load twice per setting to check stability.
- `memtable_heap_space` is the positive control: the same workload shown to move usage where a cap binds.
- Pause compaction (`nodetool disableautocompaction`) so that compaction does not change disk figures.

**B4. Risks and cleanup.**
- Disk: keep data, commitlog and hints on local disk of known size (≥ 20 GB); never on shared storage. 500_000 tombstones per run is small.
- Processes: stop the node and any load generator; check `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` return nothing.
- Unit tier: remove the test class and `/local/work/c509/build`.
- Cleanup: `rm -rf /local/work/node1 /local/work/c509`.

### B5. Step-0 audit amendments (2026-10-23, stage 4, before the freeze and before any reading)

Each item says which filed text it changes. The case's claim (B1), the estimate and the *meaning* of every B2g/B3g row are unchanged; R3 only defines words, and the control designations make explicit what the filed controls already were.

**R1 (environment; B2a, B3a, B4).** Every working tree is made by `stage4-runtime-verification/copy-source.sh` from this repository's `cassandra/cassandra-5.0.9/` (README safety rules), here `~/cassandra-rtl-a` (built with `ant build-test`; this file's tiers both use it). The `cp -r ~/cassandra-5.0.9 …`, `rsync … /tmp/ct` and `/local/...` paths of B2a, B3a and B4 are replaced by that tree and by node data under `~/stage4-rtl-a/` (local `/dev/sda3`, not `/proj`). Cleanup (B4) is therefore `rm -rf ~/stage4-rtl-a` and removing the test file from the tree; the tree stays on the node and is listed in the results file.

**R2 (unit instruments; B2a, B2d).** `ant testsome` already passes the Jamm agent (`build.xml:1159`, `-javaagent:…/jamm-0.4.0.jar`) and forks a 1024 MiB JVM (`build.xml:1153`), so the "check build.xml / add -javaagent" step and the `-Xmx2g` / `-Xmx512m` options do not apply: the unit tier runs with the harness JVM (`-Xmx1024m`, compressed oops on). `ObjectSizes.measureDeep(Object)` exists (`ObjectSizes.java:230`). The independent size is `measureDeep(list) − measureDeep(empty list with the same comparator)`, so the shared comparator cancels. Capacity is the reflected `starts.length` and the other three array lengths are recorded as well.

**R3 (definitions of the words in the predictions; B2f/B2g/B3f/B3g).** Written before any reading and used by the analyzer as `EXPECTED:` lines.
- *Exact:* capacities, growth-event counts, array lengths, sizes and the repeat-identity checks are compared exactly against the iterated expression `c -> ceil(c*f)` (fallback `c*3/2+1` when that is `<= c`, integer arithmetic) computed by the analyzer from the source expression, never hard-coded.
- *About / roughly / ≈ ln(N)/ln(f):* the growth-event count of a sorted run from capacity 1 is within `max(3, 15 %)` of `ln(N)/ln(f)`; the exact count is the iterated one above.
- *Grows linearly in N:* `unsharedHeapSize()(100k) / unsharedHeapSize()(1k)` lies in [50, 150] (the ideal is 100) at every f.
- *Moves it by at most the slack bound:* for the same (s, N, order), `|unshared(f_a) − unshared(f_b)| ≤ 28 B × (ceil((f_max − 1)·N) + 1)` where `f_max = max(f_a, f_b)` (28 B is the per-slot cost without compressed oops; the bound term is the same for both lists, so the whole difference is array bytes).
- *Cluster, grows with N:* the memtable on-heap counter (`MemtableOnHeapDataSize`) rises at every checkpoint, and `last/first` lies within [0.6, 1.4] × (tombstones at the last checkpoint / tombstones at the first).
- *Cluster, the factor changes it only within the slack bound:* `|counter(f_a) − counter(f_b)| ≤ 28 B × |f_a − f_b| × T + 1 MiB` at the same checkpoint (T = tombstones written), and the live class histogram agrees in direction (`ClusteringBound[]` bytes ordered like the factor).
- *Plateau:* the last two checkpoints differ by less than 5 % while the tombstone counts differ by at least 1.5×.
- *On the order of X (B3f):* within [0.5 X, 2 X].
- *Flush-free cell:* `MemtableSwitchCount` is unchanged from the start of the cell to its last checkpoint. A main cell that flushed is invalid and is repeated with a larger `memtable_heap_space` (a defect, not a reading).

**R4 (cluster memory configuration; B3a, B3c arithmetic).** A memtable flush starts when the pool reaches `memtable_cleanup_threshold = 1/(1 + memtable_flush_writers)` of `memtable_heap_space`, 1/3 at the default two writers (`DatabaseDescriptor.java:761-764`, `conf/cassandra.yaml:794-812, 899-912`), not at the limit itself. The counter that the flush check reads also over-counts the bounds of every non-first `add()` (`RangeTombstoneList.java:178` after `setInternal` line 766 has counted them), so the filed estimate of about 250 B per tombstone understates the counter. With the filed N up to 500,000 per partition over 1, 10 and 100 partitions (up to 50 million tombstones, far more than the heap) and a 512 MiB limit (flush at about 170 MiB of counter) a flush would occur inside the main cells and reset the lists, which the claim's readings must not contain. The main cells therefore run with `MAX_HEAP_SIZE=8G` and `memtable_heap_space: 2048MiB` (flush at about 683 MiB of counter, more than twice the largest expected counter); the positive control keeps its filed small value (128MiB, flush at about 43 MiB). All other B3a settings stay.

**R5 (cluster workload and instruments; B3b, B3c, B3d, B3e).**
- *Workload sizes.* B3c's "N = 50_000, then 500_000 per partition, across 1, 10 and 100 partitions" contradicts its own arithmetic (500,000 × ~250 B ≈ 125 MB is one partition at 500,000; 100 partitions of 500,000 are 50 million tombstones) and each write copies the whole list (O(n)), so one partition of 500,000 costs about 2.5 TB of array copying. Replaced by tombstones **T in total, never more than 500,000**, with per-partition counts N: **M** = 10 partitions × 50,000 (the main shape), **S1** = 1 partition × 50,000, **S100** = 100 partitions × 5,000. Each run is checkpointed after 10 %, 20 %, 40 % and 100 % of its N (M and S1: 5k, 10k, 20k, 50k per partition; S100: 500, 1k, 2k, 5k), which gives the dependence on N inside one run. One CQL range delete per tombstone, one in flight per partition (so each partition receives its tombstones in ascending order: the sorted fast path), `DELETE FROM ks.t WHERE pk = ? AND ck > 2i AND ck < 2i+1` as filed (disjoint, never merged).
- *Cells.* M at f = 1.2, 1.5 and 5.0, each twice (B3h "run the load twice"), set in the yaml; S1 and S100 at f = 1.2 and 5.0; one runtime-change cell **J**: yaml 1.2, then `setRangeTombstoneListResizeGrowthFactor(5.0)` through JMX (B3b), read back, M shape. Positive control **C**: M at f = 1.5 with `memtable_heap_space: 128MiB`.
- *Instruments.* The harness `Jmx.java` replaces `nodetool`/jmxterm for the read-back and the runtime set. A Byteman rule on `RangeTombstoneList.growToFree` (observation only, `-javaagent=…=script:` without `listener`) logs capacity, `newLength` and the factor read by the line every 500th call, with the call counter: direct evidence that the knob is applied on the live node. At every checkpoint: `MemtableOnHeapDataSize`, `MemtableColumnsCount`, `MemtableSwitchCount` over JMX; `jcmd <pid> GC.class_histogram` (forces a full collection) for the live bytes and instance counts of `ClusteringBound[]`, `BufferClusteringBound`, `long[]`, `int[]`, and the histogram total; `RssAnon` from `/proc/<pid>/status`. The `ClusteringBound[]` rows give the allocated slots, the `BufferClusteringBound` count gives twice the live tombstones; both are real heap, the counter is the check's own estimate. A 250 ms heap-pool poll (`HeapPoll.java`) runs through each load.
- `tombstone_failure_threshold` stays 100000 (writes only; nothing reads).

**R6 (prediction wording that the source contradicts; B2f, B3c).** B2f "Final capacity ≥ N and < ceil(f·N)+1" holds for 1.2 ≤ f ≤ 5.0; for f = 1.0 and 0.5 the fallback grows by ×1.5+1, so the bound there is `capacity < 1.5·N + 2`. B2f "heap is lower by exactly the slack" means: after `copy()` the array bytes are exactly `sizeOfArray` of arrays of length `size`, so the drop equals the difference of the array bytes (the bound term is copied unchanged). B3c's "Duration: until all deletes are acknowledged plus 60 s" stays; the memtable arithmetic is replaced by R4.

**R7 (controls made explicit; B2h, B2g, B3h).** Unit: the cells with `s = 1024` and `N = 1,000` never call `growToFree`, so capacity stays 1,024 whatever f is (the initial allocation binds): this is the positive control that the probe can see a bound, in addition to the `copy()` zero-slack baseline. It is a control for the instruments (capacity and size read correctly and move when a binding condition holds), not a claim about the factor. Cluster: `memtable_heap_space` (cell C) is the positive control of B3b. `nodetool disableautocompaction` is issued at the start of every lifetime and the start-up option `autocompaction_on_startup_enabled: false` is set (B3h "pause compaction"), so compaction does not change the histograms.


**R8 (cluster-tier definitions and one wording fix, written after the unit tier ran and before any cluster reading; B3f, B3g, B3h).** Nothing here depends on a reading: the first item is arithmetic, the rest define words.
- *B3f "Multi-partition runs: slack is per partition, so the absolute difference is smaller per tombstone"* is replaced by: for the same total number of tombstones T, the slack difference between two factors is `(f_a − f_b) × T` slots whatever the partition count (each partition's list carries `(f − 1) × n_p` spare slots after a merge, and `Σ n_p = T`), so the difference per tombstone of M, S1 and S100 is expected equal within [0.5, 2]×. The single-partition bound "at most (5.0−1.2) × N × 20-28 B, about 4 MB for N = 50,000" stays.
- *"small compared with the bound objects"* := `|counter(5.0) − counter(1.2)| < 25 %` of `counter(1.2)` at the same checkpoint of the same shape.
- *"on-heap size stays under about 128MiB plus transient"* (control C) := the largest value of the 2-second counter series is at most 1.5 × 128 MiB; *"the memtable flushes"* := `MemtableSwitchCount` rises above its value at the start of the cell.
- *B3g row "Heap rises with N at all factors; factor changes it only within the slack bound"* uses R3's two cluster definitions; *"plateau"* is R3's, applied to the main cells only (a control that flushes saw-tooths by design).

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/db/RangeTombstoneList.java` (lines 40-199, 195-344, 600-779)
- `src/java/org/apache/cassandra/config/Config.java` (lines 792-807; grep for 534-535)
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (grep, lines 4639-4657)
- `src/java/org/apache/cassandra/service/StorageService.java` (lines 6890-6934)
- `src/java/org/apache/cassandra/service/StorageServiceMBean.java` (grep, lines 1166-1175)
- `src/java/org/apache/cassandra/db/MutableDeletionInfo.java` (lines 100-130; grep for 83, 91, 142)
- `src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java` (lines 105-130)
- `src/java/org/apache/cassandra/db/ReadCommand.java` (grep only)
- `test/unit/org/apache/cassandra/db/RangeTombstoneListTest.java` (lines 570-615)

## D. Stage-4 feedback

**Stage 4, 2026-10-23 (autonomous stage-4 session, `pc07`): Confirmed — does not cap, both tiers. Outcome class: true negative.** Results: `stage4-runtime-verification/results/range_tombstone_list_growth_factor-addInternal-capacity--autonomous.md` (run 1, self-checked, no run 2). Frozen versions: sha256 `0e6e683af59b440b5eab693b839115c0ae66df183b7717e5718fd452449122a0` (unit; audit amendments R1–R7), `58d5c501fc983d797874aa66d192b001e5c4e7748d0bf008777ecea6c5fd0f92` (cluster; plus R8 before any cluster reading). Case file not committed (no commit to cite).

- **Unit (B2).** 324 runs; capacity, event count and array lengths equal the iterated `ceil(c·f)` / `c·3/2+1` expression in every run (s = 1, N = 100,000: 57, 28, 17, 8 events at f = 1.2, 1.5, 2.0, 5.0, capacity 105,776 / 138,254 / 131,072 / 390,625); `unsharedHeapSize()` scales ×99.8 – ×102.9 for ×100 in N; f = 5.0 against 1.2 differs by 5,696,992 B (array bytes only); `copy()` trims to capacity == size and the drop equals the array bytes; the s = 1024, N = 1,000 control never grows. **One frozen criterion did not hold as written**: the R3 slack bound for pairs that contain f = 0.5 or 1.0 against 1.2 (4 of 135 pairs, 649,552 B against 560,028 B), because f ≤ 1.0 applies the fallback `cap·3/2 + 1` (effective factor 1.5); with the effective factor it holds, and for every legal factor it holds as written. Reported, not amended after the reading. Stage 3 note: B2f's "(f − 1) × N" slack bound is for the legal range 1.2 – 5.0; for f ≤ 1.0 use 0.5 × N.
- **Cluster (B3).** One node, 8 GiB heap, `memtable_heap_space` 2048 MiB (cell C: 128 MiB). M = 10 × 50,000, S1 = 1 × 50,000, S100 = 100 × 5,000 range deletes; all 5.1 million acknowledged, no error. Counter ∝ N (25 MB → 252 MB at f = 1.2, ×10); the live heap holds exactly the written tombstones; allocated slots per live tombstone are 1.200, 1.500, 5.000 for f = 1.2, 1.5, 5.0 (raw histograms); counter(5.0) − counter(1.2) = 76.0 B per tombstone (37,999,195 B for M, 3,799,919 B for S1 — "about 4 MB" as filed — and 37,992,000 B for S100: equal per tombstone), 15.1 % of the f = 1.2 counter. Runtime change to 5.0 over JMX (cell J) behaves as the yaml 5.0 (counter 289,976,640 B in both). Control C at 128 MiB: 5 memtable-limit flushes, counter ≤ 40.5 MiB, factor unchanged. The Byteman trace shows `newLength = ceil(cap·f)` at the cell factor in 5,085 sampled `grow` calls.
- **Amendments to this file (section B5, dated 2026-10-23, none depends on a reading).** R1 working tree and storage; R2 test-JVM facts (Jamm present, 1024 MiB heap); R3 definitions of the vague words; R4 flush threshold (1/3 of `memtable_heap_space`) and the 8 GiB / 2048 MiB main configuration (the filed 512 MiB would flush inside the main cells); R5 cluster shapes (500,000 per partition over 100 partitions is 50 million tombstones and O(n²) copying, replaced by T ≤ 500,000) and instruments; R6 two wording fixes; R7 controls made explicit; R8 (before the cluster tier) the "smaller per tombstone" wording replaced by the arithmetic (the difference per tombstone is (f₂ − f₁) × 20 B whatever the partition count) and the cluster definitions.
- **Stage 3 notes.** B3c's arithmetic ignored the flush trigger and the counter's double count; the JMX setter is a write-only attribute, not an operation. Not run: one partition of 500,000 tombstones.

Side finding (not part of the claim, from the unit and cluster readings of all three sibling files): the `boundaryHeapSize` bookkeeping counts the bounds twice on the `add()` path (`RangeTombstoneList.java:178` after `setInternal` line 766). `boundaryHeapSize` is 2.000 × the true sum of the bound sizes and `unsharedHeapSize()` minus Jamm `measureDeep` equals the true bound sizes (N = 100,000, f = 1.5: 23,999,872 B against 24,000,000 B). In a node the memtable counter reads about 504 B per tombstone at f = 1.2 (580 B at f = 5.0) where the live heap above the baseline is about 270 – 280 B (340 – 370 B), so the memtable limit and the flush trigger are reached at roughly half the real tombstone volume. This is an accounting overestimate, not a cap tied to the factor. (A JIRA search was not done.)
