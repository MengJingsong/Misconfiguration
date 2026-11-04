# memtable_heap_space — verification solution  <!-- file: cases/memtable_heap_space-LeafBuilder-allocated--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BTree.java:2682`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/btree/BTree.java#L2682) (`redistributeAndDrain`) and `src/java/org/apache/cassandra/utils/btree/BTree.java:2735#1` (`LeafBuilder.propagateOverflow`); both are `if (allocated >= 0)` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code CLI, 2026-10-26 |
| Estimate | `positive`. The two checks decide whether the heap of newly built BTree leaf arrays goes into `allocated`. On the memtable write path that total is reported to the memtable allocator, and `memtable_heap_space` caps it: writers block when the pool is full, and a flush starts at the cleanup threshold. The accounting is an estimate, and one branch is imprecise (A3, step 6). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `memtable_heap_space`, a configuration entry
([`Config.java:187`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L187), `DataStorageSpec.IntMebibytesBound`, unit MiB). The default is
derived in [`DatabaseDescriptor.java:586-587`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L586-L587): if unset it is `Runtime.maxMemory()/4`
(1/4 of the heap). A value of 0 is rejected ([`DatabaseDescriptor.java:588-589`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L588-L589)). It is
set in `cassandra.yaml` (commented out by default, `conf/cassandra.yaml:797`) or via the
old name `memtable_heap_space_in_mb`. It is read once into the static
`AbstractAllocatorMemtable.MEMORY_POOL` (`AbstractAllocatorMemtable.java:59,81`), so a
change needs a restart. The companion entry `memtable_cleanup_threshold` defaults to
`1/(1+memtable_flush_writers)` ([`DatabaseDescriptor.java:761-763`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L761-L763)).

The target lines test the sentinel `allocated >= 0` ([`BTree.java:2517`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/btree/BTree.java#L2517)). It is `-1`
(tracking off) for `FastBuilder` ([`BTree.java:3338`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/btree/BTree.java#L3338)), for transformers (`3642`), and for
`Updater` when the update function is `UpdateFunction.Simple`/noOp (`3446`). It is `0`
(tracking on) for non-simple update functions such as `BTreePartitionUpdater` and
`ColumnData.Reconciler`.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** JVM heap used by memtables. The quantity compared is
`MemtablePool.SubPool.allocated` for the on-heap sub-pool
(`MemtablePool.java:151-158`). That sum is built from per-write `heapSize` deltas, and
the BTree leaf arrays added at `BTree.java:2683` and `2736` are part of those deltas.

**A3. Mechanism.**
1. A write to a SkipList, ShardedSkipList or Trie memtable creates a `BTreePartitionUpdater`
   ([`SkipListMemtable.java:130`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java#L130) via `AtomicBTreePartition.addAll`, [`AtomicBTreePartition.java:120`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L120);
   [`TrieMemtable.java:460`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/TrieMemtable.java#L460)).
2. `BTreePartitionUpdater` calls `BTree.update(current.tree, update.tree, comparator, this)`
   ([`BTreePartitionUpdater.java:89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java#L89)). Rows inside are merged through `ColumnData.Reconciler`
   ([`BTreeRow.java:621`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/BTreeRow.java#L621), [`ColumnData.java:153`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/ColumnData.java#L153)), whose `onAllocatedOnHeap` forwards to the
   updater ([`ColumnData.java:160-162`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/ColumnData.java#L160-L162)).
3. If either tree is a branch (more than `MAX_KEYS` = 31 rows at the default
   `cassandra.btree.branchshift` = 5, [`BTree.java:66-70`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/btree/BTree.java#L66-L70)), `Updater.update` runs with
   `allocated = 0` ([`BTree.java:3446`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/btree/BTree.java#L3446)), because the update function is not simple.
4. New leaves are built in `LeafBuilder`:
   - On a second overflow, `propagateOverflow` adds `sizeOfReferenceArray(MAX_KEYS)`
     ([`BTree.java:2735-2736`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/btree/BTree.java#L2735-L2736)). A second overflow happens when one update writes 63 or more
     keys into one leaf position.
   - On underflow after an overflow, `redistributeAndDrain` adds the new predecessor array
     size ([`BTree.java:2682-2683`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/btree/BTree.java#L2682-L2683)). This is the common path when one row is appended to a
     full last leaf.
   - The final leaf adds its size minus the replaced node ([`BTree.java:2773-2774`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/btree/BTree.java#L2773-L2774)), and
     branches add theirs (`2880-2881`, `2937-2938`).
5. At the end, if `allocated > 0`, it calls `updateF.onAllocatedOnHeap(allocated)`
   ([`BTree.java:3457-3458`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/btree/BTree.java#L3457-L3458)), which adds to `heapSize` ([`BTreePartitionUpdater.java:175-178`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java#L175-L178)).
   After the CAS succeeds, `reportAllocatedMemory` calls
   `allocator.onHeap().adjust(heapSize, writeOp)` ([`BTreePartitionUpdater.java:180-183`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java#L180-L183);
   [`AtomicBTreePartition.java:173`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java#L173)). `adjust` calls `allocate`
   ([`MemtableAllocator.java:160-166`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L160-L166)), and `allocate` loops on `parent.tryAllocate(size)`
   ([`MemtableAllocator.java:169-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L197)). `tryAllocate` fails when `allocated + size > limit`
   ([`MemtablePool.java:155`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L155)), and the writer then waits on `hasRoom`. Separately,
   `maybeClean` triggers `flushLargestMemtable` when `used() > limit*cleanThreshold`
   ([`MemtablePool.java:121-149`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L121-L149); `AbstractAllocatorMemtable.java:84,249`).
6. Bypasses and overshoots:
   - If the `OpOrder` group is blocking (a flush barrier is waiting), the allocation is
     recorded beyond the limit without waiting ([`MemtableAllocator.java:180-184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L180-L184)).
   - The accounting is an estimate from `ObjectSizes`, not a measurement.
   - When `drainAndPropagate` takes the `mustRedistribute` branch ([`BTree.java:2753-2757`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/btree/BTree.java#L2753-L2757)),
     the returned `newLeaf` (`new Object[MIN_KEYS]`, [`BTree.java:2673`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/btree/BTree.java#L2673)) is not added and the
     replaced `unode` is not subtracted. By my reading this over-counts by about
     `sizeOnHeapOfLeaf(unode) - sizeOfReferenceArray(MIN_KEYS)` (about 64 B with compressed
     oops) per redistribute event. Over-counting makes the cap stricter; it does not break it.
   - BTree garbage from replaced (CAS-lost or superseded) trees is not counted after it is
     released.

**A4. Other consumers.** Off-heap memtable pool (`memtable_offheap_space`), key/row
caches, bloom filters and index structures, read-path and compaction garbage, and network
buffers. In `heap_buffers` mode the slab regions are counted by the slab allocator, not
the BTree path.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:792-799`: "Cassandra will stop accepting writes when the limit is
  exceeded until a flush completes".
- `test/unit/org/apache/cassandra/db/memtable/MemtableSizeTestBase.java`: asserts that
  accounted `ownsOnHeap` is within 3% of `MemoryMeter.measureDeep`, but only with 4 rows
  per partition (`:62`). Those partitions are single leaves, so the target lines are never
  exercised.

## B. Verification solution

**B1. Claim under test.**
- (a) For wide partitions (more than 31 rows), the memtable's accounted on-heap usage,
  including the leaf arrays counted at `BTree.java:2683/2736`, matches the measured
  retained heap of the memtable within a few percent.
- (b) Total memtable heap stays at or below `memtable_heap_space`: writes block or a flush
  occurs, so live heap does not grow past the limit plus one in-flight memtable's
  overshoot.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11, Ant. `git clone /Users/yangwang/cassandra-src /local/c509 && cd /local/c509 && git checkout cassandra-5.0.9 && ant jar build-test`.
- Add `test/unit/org/apache/cassandra/db/memtable/WideMemtableSizeTest.java` in the local
  clone only. It is a copy of `MemtableSizeTestBase` + `MemtableSizeUnslabbedTest` with
  `memtable_allocation_type = unslabbed_heap_buffers` (no slab slack, so every heap object
  is accounted individually), and the changes listed below.
- Change 1, partitions and rows: `partitions = 5_000` and `rowsPerPartition` a parameter,
  with the delete phases removed.
- Change 2, write mode: a write-mode parameter `single` or `batch`.
  - `single`: one `INSERT` per row, in ascending `picid`.
  - `batch`: per partition, `UNLOGGED BATCH` statements of 128 rows each, all to the same
    `userid`.
- Run: `ant testsome -Dtest.name=org.apache.cassandra.db.memtable.WideMemtableSizeTest`.
  The test JVM uses the build's default `-Xmx` (1 GiB in `build.xml` test targets); raise it
  to 2 GiB if needed with `-Dtest.jvm.args`.

> **Amendment U1 (2026-10-27, stage-4 audit; host, build variant V1, heap).** On the advisor's Mac (no `/local`, no `mkdir` in
> `$HOME`): V0 clone `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run61` (`W=~/Library/Caches/stage4`);
> V1 in a second clone `$W/cassandra-run61v1`, patched by `harness/memtable_heap_space-LeafBuilder-allocated--autonomous/v1-patch.sh`,
> which replaces the statements at `BTree.java:2683` and `:2736` by `allocated += 0;` (a no-op that keeps bytecode on the same
> line, so the counters of U2 still fire there; line numbers unchanged). Both built with `ant -Dlocal.repository=$W/m2 build-test`;
> the patch is reverted (`v1-patch.sh <clone> revert`) at the end, replacing B2e steps 3-4 (no rebuild back and forth, and no
> `ant` in a clone a node later runs from). The test sources (`WideMemtableSizeTest.java`, `WideLeafCounters.java`) are in the
> harness folder and copied into `test/unit/org/apache/cassandra/db/memtable/` of both clones by `unit-run.sh`.
> **Heap.** The forked test JVM gets `-Xmx1024m` from `maxmemory="1024m"` (`build.xml:1153`), and Ant appends it after
> `-Dtest.jvm.args` (checked with `ant -verbose`: `'-Xmx4g'` then `'-Xmx1024m'`), so `-Dtest.jvm.args=-Xmx2G` does not take
> effect. The heap is set with `_JAVA_OPTIONS=-Xmx4g` (the JVM applies it after the command line; each JVM prints `Picked up
> _JAVA_OPTIONS`; the test prints `maxMemory`). Size from source: one row of this schema costs about 316 B on heap (BTreeRow 32,
> BufferClustering 24 + `ByteBuffer[1]` 24 + HeapByteBuffer 48 + `byte[8]` 24, LivenessInfo 24, cell tree `Object[1]` 24,
> BufferCell 40 + value 48 + 24, tree slot 4, compressed oops), so 1.28 M rows are about 386 MiB, more than the flush point of a
> 1 GiB heap (1/4 x 0.8 = 204.8 MiB) and 94% of a 2 GiB heap's (409.6 MiB); 4 GiB gives a 1,024 MiB default limit and an
> 819.2 MiB flush point. `memtable_heap_space` stays at its default (1/4 heap, now 1,024 MiB), as B2b says.

**B2b. Knobs.**
- `rowsPerPartition`: 4 (single leaf; the target lines are never reached) and 256 (about 8
  leaves per partition).
- Write mode: `single` reaches `2682` on every 32nd append; `batch` (128 rows) also reaches
  `2735`.
- Build variant:
  - V0: unmodified.
  - V1: lines `2683` and `2736` replaced by no-ops (a local patch) to isolate their
    contribution.
- `memtable_heap_space` stays at the default (1/4 heap). `memtable_cleanup_threshold = 0.8`
  as in the base test, so no flush happens during the run. The test asserts that the
  memtable did not change.

**B2c. Workload.**
- 5,000 partitions × 256 rows = 1.28 M rows, about 8.3 leaves per partition.
- Single mode: each partition goes through 7 overflow/redistribute events
  (`floor((256-1)/31)` ≈ 8). That is about 35,000 executions of `2682`.
- Batch mode: each 128-row batch into the tail overflows at least 3 times, so `2735` runs
  about 2 times per batch. That is about 20,000 executions.
- Per-event amounts with compressed oops: `sizeOfReferenceArray(31)` = 16+124 → 144 B, and
  `sizeOfReferenceArray(17)` = 16+68 → 88 B. The V0−V1 difference is therefore about
  35,000×88 ≈ 3 MB (single) or about 20,000×144 ≈ 2.9 MB plus the `2682` share (batch).
- Total memtable heap is about 1.28 M rows × ~100–150 B ≈ 130–190 MB, under 1/4 of 2 GiB
  heap × 0.8.

> **Amendment U3 (2026-10-27, stage-4 audit; corrected event counts and amounts, before any reading).** B2c's counts are
> re-derived from source (`BTree.java:341-398, 3446, 3536-3590, 2629-2643, 2663-2686, 2731-2775`):
> - `single`, 256 rows: rows 1-31 stay one leaf (`updateLeaves`, untracked); row 32 builds two leaves of 16 and 15 keys through
>   `FastBuilder` (`allocated = -1`, not counted). From then on each append goes through `Updater`; the last leaf grows from 15
>   to 31 keys in 16 appends and the 17th overflows it with `count = 0`, so `drainAndPropagate` takes `mustRedistribute` and
>   `redistributeAndDrain` runs line 2683 once (new predecessor of 16 keys, `sizeOfReferenceArray(17)` = 88 B). Events at rows
>   32 + 17k, k = 1..13: **13 per partition, n2683 = 65,000, n2736 = 0** (B2c said about 7 per partition and 35,000).
> - `batch`, 256 rows: the first 128-row batch goes into an empty partition (`BTree.update` → `transform`, untracked); the second
>   merges 15-31 old keys of the last leaf plus 128 new keys: four overflows of 32 keys; overflows 2-4 call `propagateOverflow`
>   and the final `drainAndPropagate` (15-31 keys left, not `mustRedistribute`) calls it once more: **n2736 = 4 per partition =
>   20,000, n2683 = 0** (B2c: about 20,000, and it expected some line-2683 share).
> - 4 rows: single leaves only: **n2683 = n2736 = 0**. Known answers (U2): `ka single256` 13 / 0, `ka batch2x128` 0 / 4.
> - **V0 − V1 (B2f) is exact:** with one writing thread the two builds differ only by the removed additions, so
>   `owns(V0) - owns(V1) = 88 x n2683 + 144 x n2736`: **5,720,000 B (single)** and **2,880,000 B (batch)** per memtable class
>   (B2f said about 3 MB and 3-6 MB).
> - **Traced error of the BTree structure alone (information, not a verdict condition):** per single-mode event the real change is
>   +88 (new predecessor) +80 (new last leaf `Object[15]`) −144 (old `Object[31]`) = +24 B while 88 B is counted (+64 B, the
>   A3-step-6 over-count: 65,000 x 64 = 4.16 MB, not 2.2 MB), and the rebuilt root branch (`BTree.java:3057-3063, 3100`) is never
>   counted, so its growth of 8 B (+0 or 8 B size map) per event is missed: net about +3.4 MB (V0) and −2.3 MB (V1). Batch: the
>   four leaves are counted exactly; the root's growth (48 B per partition) is missed: −0.24 MB (V0), −3.12 MB (V1). The other
>   components' accuracy is what the 4-row control measures. B2f's remaining statements (4 rows within ±3%; 256 single `owns >=
>   expected`; 256 batch within ±3%; V1 under-counts relative to `expected`) are unchanged.

**B2d. Observables and instruments.**
- `Memtable.getMemoryUsage(memtable).ownsOnHeap`: the check's operand at the memtable level.
- `MemoryMeter.measureDeep(memtable)` before and after: retained heap.
- `memtable.getAllocator().onHeap().owns()`, and `AbstractAllocatorMemtable.MEMORY_POOL.onHeap.used()`.
- One reading of each at the end of each run, logged.
- Not observable directly: per-event counts. If wanted, add a static `AtomicLong` counter at
  the two lines in a third variant.

> **Amendment U2 (2026-10-27, stage-4 audit; the test and the per-event counters).** `WideMemtableSizeTest` keeps the base's
> parameterisation over the three memtable classes (`skiplist`, `skiplist_sharded`, `trie`) and adds `rowsPerPartition` {4, 256}
> and mode {`single`, `batch`} as parameters: 12 cases per V0 run, 6 per V1 run (256 rows only). Statements are fully
> qualified; a batch holds `min(128, rowsPerPartition)` rows of one partition with bound values. Per case it prints one line
> `STAGE4 reading variant= class= rows= mode= partitions= ops= owns= trieOverhead= actual= deepBefore= deepAfter= expected= diff=
> pct= n2683= n2736= allocOwns= poolUsed= flushed=`, where `actual = owns + trieOverhead` and `expected = deepAfter - deepBefore`
> exactly as the base test computes them, `pct = 100 x (actual - expected) / expected`, and `flushed` says whether the current
> memtable changed. It also prints `STAGE4 value config` (maxMemory, allocation type, limit, cleanup threshold, pool class) and
> `STAGE4 value btree` (`MIN_KEYS`, `MAX_KEYS`, `sizeOfReferenceArray(15/17/31)`). **Per-event counts (B2d's optional third
> variant, done without a patch):** observe-only Byteman rules (`unit-counters.btm`, loaded with `-javaagent` in every V0 and V1
> run, so the JVM flags are the same) fire `AT LINE 2683` and `AT LINE 2736`, i.e. only when `if (allocated >= 0)` passed, and
> count events on the test thread only (CQLTester applies mutations on the calling thread), giving `n2683` and `n2736` per case.
> A synthetic known-answer check in `@BeforeClass` prints `STAGE4 ka single256` (256 single-key `BTree.update`s with a non-simple
> update function) and `STAGE4 ka batch2x128` (an update of an empty tree by keys 0-127, then by keys 128-255); U3 gives the
> expected counts. The rules were type-checked with Byteman's `TestScript` on both clones before the freeze (no errors).

**B2e. Procedure.**
1. Build V0 and run all four combinations: rowsPerPartition {4, 256} × mode {single, batch}.
2. Record `ownsOnHeap`, `expected = deepAfter-deepBefore`, and the ratio.
3. Apply the V1 patch, rebuild with `ant jar build-test`, and rerun 256×single and
   256×batch.
4. Revert the patch.

> **Amendment U5 (2026-10-27, stage-4 audit; exact sequence).** `unit-run.sh instrument` (copy, build both clones, `TestScript`),
> `unit-run.sh shake` (V0, 200 partitions, 12 cases; harness shakedown, not judged), `unit-run.sh v0` (V0, 5,000 partitions, 12
> cases), `unit-run.sh v1` (V1, 5,000 partitions, 6 cases), then `v1-patch.sh $W/cassandra-run61v1 revert`. Stop condition: a
> case that cannot run (test error) stops the tier and is a runbook defect. Raw output: `stage4.out` and the copied
> `TEST-...WideMemtableSizeTest-<V>.log` under `$W/logs/memtable_heap_space-LeafBuilder-allocated--autonomous/unit-<mode>/`.

**B2f. Predictions.**
- V0, 4 rows: |owns−expected| ≤ 3% (as the existing test asserts).
- V0, 256 rows, single: owns ≥ expected. The excess comes from the redistribute
  over-count (≈ 35,000 × 64 B ≈ 2.2 MB) and is still within about 3%.
- V0, 256 rows, batch: |owns−expected| ≤ 3%.
- V1: owns(V1) < owns(V0) by about 3 MB (single) and about 3–6 MB (batch), and V1
  under-counts relative to `expected`.

> **Amendment U3 applies here (2026-10-27):** the line-2683 count is 65,000 (single) and the V0 − V1 amounts are exactly 5,720,000 B
> (single) and 2,880,000 B (batch); the traced over-count is 4.16 MB. See U3 under B2c.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| V0 within ±3% and V1 lower by about the predicted amount | Target lines feed the operand correctly; claim (a) holds |
| V0 owns < expected by >3% for 256 rows | Accounting misses wide-partition BTree heap; claim (a) wrong |
| V0 owns > expected by more than the ~64 B/event estimate | Over-count is larger than traced; cap is conservative |
| V0 == V1 | Lines not reached (wrong path) or the accounting is overwritten; recheck the workload |
| Memtable flushed during the run | Run invalid; lower the row count |

> **Amendment U4 (2026-10-27, stage-4 audit; verdict words, order and tolerances; no prediction changed).** Checked in this order,
> per memtable class and over all classes:
> 1. **Invalid** — any case with `flushed=true`, a missing reading, `maxMemory` not 4 GiB, a pool that is not `HeapPool`, or
>    `allocation_type` not `unslabbed_heap_buffers` (B2g row 5).
> 2. **Not confirmed (control)** — a 4-row V0 case outside ±3% (`|pct| > 3`), or a 4-row case with a non-zero count: the copied
>    test does not reproduce the base test's known pass (B2h).
> 3. **Not confirmed (lines not reached)** — B2g row 4: in a 256-row case `n2683 + n2736 = 0`, or `owns(V0) = owns(V1)`.
> 4. **Refuted (under-count)** — B2g row 2: a 256-row V0 case with `pct < -3`.
> 5. **Refuted (over-count beyond the band; cap conservative)** — B2g row 3 in its strong form: a 256-row V0 case with `pct > +3`.
> 6. **Confirmed** — B2g row 1: every V0 case within ±3%, and for each class and 256-row mode `owns(V0) - owns(V1)` within ±1% of
>    `88 x n2683 + 144 x n2736` (counts of the V0 run; the V1 run's counts must be equal), with `n > 0`.
> 7. **Not confirmed** — anything else (for example V1 lower by an amount outside ±1% of the traced one).
> B2g row 3 in its weak form (V0 above `expected` by more than the traced 64 B per event but within +3%) is recorded as a finding
> under row 6. Counts that differ from U3's derivation are recorded as a derivation finding; the verdict uses the measured counts.

> **Runbook-defect fix D1 (2026-10-27, found by the unit shakedown, before run 1; amends U1 and U4 row 1).** The forked test JVM
> runs CMS (`build.xml` JDK 11 test args, `-XX:+UseConcMarkSweepGC -XX:SurvivorRatio=8`), whose `Runtime.maxMemory()` excludes one
> survivor space: with `-Xmx4g` it reports 4,277,534,720 B, so the default limit is `maxMemory/4` = 1,019 MiB (not 1,024 MiB) and
> the flush point 815.2 MiB, still above U1's 386 MiB. U1's "1,024 MiB default limit and 819.2 MiB flush point" reads "`maxMemory/4`
> (1,019 MiB) and 815.2 MiB"; U4 row 1's "`maxMemory` not 4 GiB" reads "`maxMemory` below 4 GiB − 64 MiB, or
> `memtable_heap_space_MiB` ≠ `floor(maxMemory / 2^22)`". B2f/B2g and every prediction unchanged; the unit tier restarts from its
> shakedown.

> **Amendment 2026-10-27 (after run 1, authorised by the user) — B2a/U1/U5, B2h and U4 rows 1 and 6 (the per-JVM skiplist
> partition charge).** This follows run 1's readings: V0 − V1 was exactly 88·n2683 + 144·n2736 for `trie` and 35,000 B short for
> both skiplist classes, and the two JVMs logged different "Estimated SkipListMemtable row overhead" values (results §4.1).
> *Source.* A skiplist memtable charges each new partition `token.getHeapSize() + ROW_OVERHEAD_HEAP_SIZE` once
> (`SkipListMemtable.java:121-125`; `ShardedSkipListMemtable.java:366` uses the same constant). `ROW_OVERHEAD_HEAP_SIZE` is fixed
> at class initialisation (`SkipListMemtable.java:72-80`): the property `cassandra.memtable.row_overhead_size`
> (`CassandraRelevantProperties.java:356`, default −1) is used if it is > 0; otherwise `estimateRowOverhead` measures a
> `ConcurrentSkipListMap` of `cassandra.memtable_row_overhead_computation_step` random keys (`SkipListMemtable.java:216-240`;
> the test JVM passes 100, `build.xml:1174`). The JDK 11 map adds index nodes to a new key with probability 1/4 and a geometric
> number of them (`java/util/concurrent/ConcurrentSkipListMap.java:658-672` in the JDK's `src.zip`), so the estimate is a random
> variable that differs between JVMs, and it enters `owns` as P × (its value) in V0 and in V1 separately: V0 − V1 then contains
> P × (o_V0 − o_V1), a term outside the target lines. The `trie` memtable has no such term. *Design change.* Both JVMs (every
> V0 and V1 run, shakedowns included) get `-Dcassandra.memtable.row_overhead_size=190` in `-Dtest.jvm.args`, so
> `ROW_OVERHEAD_HEAP_SIZE` = 190 in both and the per-partition charge P × (24 + 190) is identical and cancels exactly in
> V0 − V1; with one writing thread nothing else differs between the builds (U3). *Why 190.* The value does not enter V0 − V1. It
> is the estimator's expectation from source, so that the unchanged ±3% band against jamm keeps its meaning: per key the map
> holds a `Node` (24 B), a `BufferDecoratedKey` (24 B), a `LongToken` (24 B) and the cloned 8-byte heap buffer measured in
> `SLAB_ALLOCATION_NO_SLICE` mode (48 + 24 B; `ObjectSizes.java:242-244`, `ByteBufferCloner.java:44-46,70-82`), 144 B, plus
> 0.5 × 24 B of index nodes and about 2 B of per-map objects (map, head index column, header node, counter, shared value) over
> 100 keys: about 158 B (`SkipListMemtable.java:229-230`); then − 24 (token, `SkipListMemtable.java:231`, `Murmur3Partitioner.java:54,195-197`),
> plus 32 (`AtomicBTreePartition.EMPTY_SIZE`, five reference fields, `:232`) + 32 (`BTreePartitionData.UNSHARED_HEAP_SIZE`, five reference
> fields, `:233`) − 8 (`:234-235`) = **190 B**. *Test change (harness).* `STAGE4 value config` also prints
> `row_overhead_property=` (the system property) and `skiplist_row_overhead=` (`SkipListMemtable.ROW_OVERHEAD_HEAP_SIZE`, read
> in the test's package). *U4 row 1 (Invalid) adds:* either JVM's config line without `row_overhead_property=190
> skiplist_row_overhead=190`, or an "Estimated SkipListMemtable row overhead" line in either test log (the estimate ran). *U4 row 6
> (Confirmed), restated:* every V0 case within ±3%, and for each class and 256-row mode `owns(V0) − owns(V1)` within ±1% of
> `88 × n2683 + 144 × n2736` (counts of the V0 run; the V1 run's counts equal), with `n > 0`, **both JVMs charging the same pinned
> per-partition overhead (190 B)** — the per-JVM term cannot enter. Rows 2–5 and 7, B2f and B2g unchanged. *B2h* "the same JVM
> flags in every run" includes the pinned property. *Runbook (U1/U5).* Fresh clones `$W/cassandra-run70` (V0) and
> `$W/cassandra-run70v1` (V1, `v1-patch.sh`), raw logs under `$W/logs/memtable_heap_space-LeafBuilder-allocated--autonomous/unit-run2/`;
> sequence instrument, shake (V0 and V1, 200 partitions), v0, v1, revert. *What was known of run 1 when writing this:* all of run 1's
> unit readings, including the logged estimates 187 B (V0) and 194 B (V1); 190 is derived above and is not their mean (190.5).
> *Would run 1 pass?* Run 1 did not pin the property and its logs carry two estimate lines, so under the amended row 1 it is
> **Invalid**; with the logged per-JVM term subtracted, its six differences equal the traced amounts exactly, so run 1's
> skiplist readings would meet the restated relation; the re-run tests it on readings taken after the re-freeze.

**B2h. Controls.**
- The 4-row run is the baseline where the existing test is known to pass.
- V1 isolates the two lines.
- `unslabbed_heap_buffers` removes slab slack.
- Use the same JVM flags in every run.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node, built from the local clone (`ant jar`). Data, commitlog and hints go
  under `/local/c509-node/` on local disk with at least 20 GB free.
- `conf/jvm11-server.options` / `cassandra-env.sh`: `-Xms2G -Xmx2G`, G1, and the GC log
  enabled with `-Xlog:gc*:file=/local/c509-node/gc.log`.
- `cassandra.yaml`:
  - `memtable_allocation_type: unslabbed_heap_buffers`
  - `memtable_heap_space: <knob>`
  - `memtable_cleanup_threshold: 0.5`
  - `memtable_flush_writers: 1`
  - `commitlog_segment_size: 32MiB`
  - `concurrent_writes: 32`
- The commitlog is the default size; it is not limiting here.

> **Amendment C1 (2026-10-27, stage-4 audit; host node).** One node on this Mac at 127.0.0.1, run from `$W/cassandra-run61` (V0)
> or `$W/cassandra-run61v1` (V1, U1), data, commitlog, hints and logs under `$W/node-mhslb` (wiped before and after each run),
> started by `harness/.../cluster-run.sh` as a tracked background process (`MAX_HEAP_SIZE=2G`: `-Xms2G -Xmx2G`; G1 is the default
> of `conf/jvm11-server.options:63`; `cassandra-env.sh:83` already writes `gc.log` in the log directory, used in place of
> `/local/c509-node/gc.log`). The yaml lines are B3a's, appended to a copy of the clone's `conf/cassandra.yaml`. The table is
> created with `compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}` (B3h's optional step, done as a table
> option because each run starts a fresh node).

**B3b. Knobs.**
- `memtable_heap_space` ∈ {64MiB, 256MiB}. Both are well under the 512 MiB default, so the
  knob binds and its effect shows on a 2 GiB heap.
- Build V0 vs V1 (as in B2) at 64MiB.
- Restart after every change.

> **Amendment C2 (2026-10-27, stage-4 audit; the default added; runs).** Group A needs the default among the values: with `-Xmx2G`
> the default is `Runtime.maxMemory()/4` = 512 MiB (`DatabaseDescriptor.java:586-587`; read back from the start-up line "Global
> memtable on-heap threshold is enabled at ..."). Runs, each on a fresh node and in this order: V0 64MiB single, V0 64MiB batch,
> V0 256MiB single, V0 256MiB batch, V0 default single, V0 default batch, V1 64MiB single, V1 64MiB batch.

**B3c. Workload.**
- Schema: `CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk bigint, ck bigint, v bigint, PRIMARY KEY(pk, ck)) WITH compression={'enabled':false};`
- `cassandra-stress user profile=wide.yaml ops(insert=1) n=5000000 -rate threads=32`,
  where `wide.yaml` sets:
  - `pk` population `uniform(1..20000)`
  - `ck` cluster `fixed(256)`
  - `insert: partitions: fixed(1), select: fixed(1)/256, batchtype: UNLOGGED` (one row per
    op, so the `2682` path)
- Second run: `select: fixed(128)/256`, giving 128-row batches (the `2735` path).
- 5 M rows at about 150 B accounted each is about 750 MB, which is more than 64 MiB×0.5 and
  256 MiB×0.5. That forces about 20 and 5 flushes respectively.
- Duration is about 5–10 min per run.

> **Amendment C3 (2026-10-27, stage-4 audit; workload that reaches the target lines and the limit).** As written the workload
> cannot reach the target lines: a memtable flushes at 0.5 x limit, which holds about 0.5 x 64 MiB / 316 B ≈ 106,000 rows
> (U1's row size), spread over 20,000 partitions ≈ 5 rows each, and ≈ 21 each at 256 MiB, so no partition in a memtable grows past
> one leaf (31 rows) and `Updater` never runs (U3). And 5,000,000 ops of 128-row batches would be 640 M rows. Amended:
> `pk population: uniform(1..1000)` and `ck cluster: fixed(8192)` (1,000 partitions, 8.2 M distinct rows, so ≈ 106 rows per
> partition per memtable at 64 MiB and ≈ 850 at the default, and in-memtable overwrites stay under ≈ 10% at the default).
> Profiles `harness/.../wide-single.yaml` (`select: fixed(1)/8192`) and `wide-batch.yaml` (`select: fixed(128)/8192`), both
> `partitions: fixed(1)`, `batchtype: UNLOGGED`, schema of B3c. Commands: `tools/bin/cassandra-stress user profile=<yaml>
> "ops(insert=1)" n=<n> cl=ONE no-warmup -rate threads=32 -node 127.0.0.1`; `n = 5,000,000` (single) and `n = 40,000` (batch,
> ≈ 5.12 M rows); `no-warmup` so that `n` is the whole workload. About 5 M x 316 B ≈ 1.5 GB accounted per run: ≈ 47, 12 and 6
> flushes at 64, 256 and 512 MiB.

**B3d. Observables and instruments.**
- JMX via `nodetool sjk mx -b "org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=<M>" -f Value -mg`,
  every 2 s, for `AllMemtablesOnHeapDataSize` and `MemtableSwitchCount`.
- `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation` (count).
- Actual heap: `jcmd <pid> GC.class_histogram` taken immediately before and after a forced
  flush at the end. The `[Ljava.lang.Object;` and `BTreeRow`/`BufferCell` deltas give the
  memtable's retained heap.
- Old-gen occupancy after each mixed/full GC, from the GC log.
- Not observable: heap per object owner during the run.

> **Amendment C4 (2026-10-27, stage-4 audit; instruments).** `nodetool sjk` is replaced by a JMX client (`Sampler.java`, one
> connection, every 2 s): `type=Table,keyspace=ks,scope=t` `AllMemtablesOnHeapDataSize` and `MemtableOnHeapDataSize` (Value),
> `MemtableSwitchCount` (Count); the all-tables `type=Table,name=AllMemtablesOnHeapDataSize`; `type=MemtablePool`
> `BlockedOnAllocation` (Count) and `PendingFlushTasks`; heap used. The "Flushing largest ... Used total: on/off, live: on/off,
> flushing, this" lines (`AbstractAllocatorMemtable.java:290-293`) give the pool's used ratio at each cleanup trigger. Retained
> heap: `jcmd <pid> GC.class_histogram` total bytes (forces a full GC, live objects only). Lines reached: observe-only Byteman rules
> (`node-counters.btm`, `-javaagent` in `JVM_EXTRA_OPTS` for every run) count executions of lines 2683 and 2736 on the node and print
> the running totals (`STAGE4BM switch ks.t ... c2683= c2736=`) at each `Tracker.switchMemtable` of ks.t. Old-gen occupancy:
> post-GC heap from `gc.log` (information).

**B3e. Procedure.**
1. Start the node and create the schema.
2. Start the samplers and run the stress single-row mode.
3. At the end, without flushing, take `jcmd <pid> GC.class_histogram`.
4. Run `nodetool flush ks t`, then take `GC.class_histogram` again; the difference is the
   memtable's retained heap.
5. Repeat for batch mode, then for the 256MiB setting, then for V1 at 64MiB.
6. `nodetool drain` and stop.

> **Amendment C5 (2026-10-27, stage-4 audit; exact procedure).** Per run (`cluster-run.sh <label> <V> <knob> <mode> <n_main>
> <n_tail>`): start, wait for `UN` and `statusbinary running`; sampler on; main stress (C3); wait idle (`nodetool tpstats`
> MemtableFlushWriter, MemtablePostFlush, MemtableReclaimMemory active + pending = 0 twice, 2 s apart, at most 600 s);
> `nodetool flush ks t`, idle; **idle control**: histogram `idle1`, `nodetool flush ks t` on the empty memtable, idle, histogram
> `idle2` (noise `|idle2 - idle1|`); **tail**: a fresh memtable filled to about 0.25 x limit with the same profile, `n_tail` =
> 0.25 x limit / 316 B rows: single 53,000 / 212,000 / 425,000 ops, batch 415 / 1,660 / 3,320 ops at 64 / 256 / 512 MiB (B3e step
> 3 read the memtable at a random fill, which can be near empty, where a 5% band is below the noise); idle; one JMX row `ENDTAIL`
> (G_end = ks.t `AllMemtablesOnHeapDataSize`); histogram `end1`; `nodetool flush ks t`; idle; histogram `end2`; retained delta =
> `end1 - end2`; then `nodetool drain`, stop, check no daemon is left, wipe `$W/node-mhslb`.

**B3f. Predictions.**
- `AllMemtablesOnHeapDataSize` never exceeds `memtable_heap_space` (64 MiB or 256 MiB) by
  more than one in-flight write's delta. It oscillates, with flushes at about 0.5×limit.
- `MemtableSwitchCount` ≈ total accounted / (0.5×limit), so about 4× more switches at
  64MiB than at 256MiB.
- The retained-heap delta at the end is ≤ limit and within about 5% of the last
  `AllMemtablesOnHeapDataSize` reading.
- V1: the reported size is lower than the histogram delta by about 2–3% of rows-in-memtable
  × (88/31) B, and there are slightly fewer switches for the same workload.

> **Amendment C6 (2026-10-27, stage-4 audit; exact predictions; no filed relation changed).** For every run: (1) every sample of
> ks.t `AllMemtablesOnHeapDataSize` and of the all-tables gauge is ≤ limit + 2 MiB (one in-flight write per concurrent writer:
> 32 x 128 rows x 512 B = 2 MiB), and every "Flushing largest" line shows `Used total` on-heap ≤ 1.00; (2) flushes start at the
> threshold: every "Flushing largest" line for ks.t shows `live` on-heap ≥ 0.50; (3) switch counts during the main stress scale as
> 1/limit: `s64/s256` in [3.0, 5.0], `s256/s512` in [1.4, 2.8], `s64/s512` in [6, 10] (±25% around 4, 2, 8, for ±1 switch of
> quantisation and the overwrite differences), per mode; (4) the tail adds no switch, and the retained delta satisfies
> `delta ≤ limit` and `|delta - G_end| ≤ 5% x G_end + |idle2 - idle1|`. V1 (64 MiB): the node counts of lines 2683/2736 are > 0
> in the V0 and the V1 runs; V1's tail gap `G_end - delta` is compared with V0's and with `88 x Δc2683 + 144 x Δc2736` of the tail
> epoch (information: the removed amount is ≈ 2% of G_end); V1 switches ≤ V0 switches + 1 (B3f's "slightly fewer"; information).

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| Reported ≤ limit, retained delta ≈ reported, switches scale ~1/limit | `memtable_heap_space` caps the memtable heap; claim (b) holds |
| Retained delta ≫ reported (>10%) for the wide workload only | BTree heap escapes accounting; cap is leaky; claim (a) wrong |
| Reported exceeds limit persistently with `BlockedOnAllocation` = 0 | Enforcement bypassed; claim (b) wrong |
| No flushes at 64MiB | Workload did not reach the limit; not confirmed; increase n |
| V1 switches == V0 and reported equal | Target lines not reached on this workload |

> **Amendment C7 (2026-10-27, stage-4 audit; verdict words and order).** Checked in this order over the eight runs:
> 1. **Invalid** — a node that does not start or dies, stress errors, a missing reading, or a tail that switched the memtable.
> 2. **Not confirmed (limit never reached)** — B3g row 4: no switch at 64 MiB during the main stress.
> 3. **Refuted (enforcement bypassed)** — B3g row 3: two consecutive samples above limit + 2 MiB, or a `Used total` above 1.00
>    (with `BlockedOnAllocation` recorded either way).
> 4. **Refuted (accounting leaky)** — B3g row 2: `delta > 1.10 x G_end + |idle2 - idle1|` in a run.
> 5. **Not confirmed (lines not reached)** — B3g row 5: node counts c2683 + c2736 = 0 in a run.
> 6. **Confirmed** — B3g row 1: C6 (1)-(4) hold in every run.
> 7. **Not confirmed** — anything else (for example a delta between the 5% and the 10% bands, or a switch ratio outside its band).

> **Amendment 2026-10-27 (after run 1, authorised by the user) — C6 (4) and C7 row 6 (the rewrite term), C1/C5 (paths).** This
> follows run 1's readings: in `v0-def-single` the tail's retained delta was 8.5% below the gauge (`delta/G_end` 0.915), with more
> rows written than live rows added (425,000 ops, 382,008 `BTreeRow`s added); the other seven runs met C6 (4) (results §4.1).
> *Source: what a rewritten row costs the gauge and the live heap.* A tail write to a (pk, ck) already in the tail memtable carries a
> newer server timestamp and is merged, not inserted: `BTreePartitionUpdater.merge(Row, Row)` (`BTreePartitionUpdater.java:136-142`)
> → `BTreeRow.merge` (`BTreeRow.java:583-623`), which builds a new `BTreeRow` with the existing clustering and the winning
> `LivenessInfo` (the update's, same class), and a new one-cell tree through `BTree.update` of two leaves, charged
> `sizeOnHeapOf(merged) - sizeOnHeapOf(toUpdate)` = 0 (`BTree.java:362-374`). The cell goes through `ColumnData.Reconciler.merge`
> (`ColumnData.java:111-118`) and `Cells.reconcile` (newer timestamp wins, `Cells.java:79-84`) to
> `BTreePartitionUpdater.merge(Cell, Cell)` (`:144-157`): the winning cell is cloned through the allocator's cloner
> (`AbstractCell.java:108-111`, `ByteBufferCloner.java:70-82`, `MemtableBufferAllocator.java:33-43`), whose `allocate` charges the
> value's length to the on-heap pool (`HeapPool.java:52-55`) — 8 B for `v bigint` (B3c schema) — and `heapSize` changes by
> `unsharedHeapSizeExcludingData` of the new cell minus the old, 0 for the same layout (`BufferCell.java:156-158`). The partition
> leaf that holds the row is rebuilt at the same size and charged net 0 (`BTree.java:2773-2774`, or `:373` for a leaf-only
> partition); branch rebuilds are never charged (R2), at the same size. Nothing is released for the replaced row, liveness, cell
> tree, cell and value buffer: they become garbage, the same sizes as their replacements. **So a rewritten row raises the gauge by
> exactly 8 B and leaves the live heap unchanged** (an over-count of 8 B per rewrite); a new row is charged as before. *Amended C6
> (4):* the tail adds no switch, `delta ≤ limit`, and
> `-(5% x G_end + |idle2 - idle1|) ≤ G_end - delta ≤ 5% x G_end + |idle2 - idle1| + 8 x W_tail`,
> where `W_tail` = rows written by the tail = `n_tail` x rows per op (1 single, 128 batch), an upper bound on the rewrites because
> their number is not observed directly: `8 x W_tail` = 424,000 / 1,696,000 / 3,400,000 B (single) and 424,960 / 1,699,840 /
> 3,399,680 B (batch) at 64 / 256 / 512 MiB. The term widens only the over-count side, because rewrites can only over-count.
> *C7:* row 6 (Confirmed) reads C6 (1)–(3) and the amended (4) in every run; row 4 (leaky, the under-count side) and the other rows
> unchanged. *Why a term, not a redesign:* the workload stays as frozen (C3, C5), so the switch ratios, trigger lines and the V1
> comparison keep their meaning, and the term bounds the only extra charge a rewrite makes; a rewrite-free tail would need a
> different key generator than cassandra-stress's user mode. *Paths (C1, C5):* V0 node from a fresh clone `$W/cassandra-run70`, V1
> from `$W/cassandra-run70v1` (the unit tier's V1 clone, no `ant` there while a node runs), node dir `$W/node-mhslb`, raw logs
> `$W/logs/memtable_heap_space-LeafBuilder-allocated--autonomous/cluster-run2/<label>/`; shakedowns first (64 MiB single 400,000 /
> 53,000 ops and batch 4,000 / 415 ops), then C2's eight runs. *What was known of run 1 when writing this:* all of run 1's cluster
> readings (results §4.1–§5), including `delta/G_end` 0.915 and the 333 vs 310–319 accounted B per live row, and, while looking for
> the rewrite count, the `BTreeRow` lines of run 1's raw histograms (12,000–42,000 `BTreeRow`s live at `idle2` with an empty
> memtable, and in `v0-def-single` 11,896 fewer at `end2` than at `idle2`); those counts are not used here. *Would run 1 pass?*
> **No:** in `v0-def-single` `G_end - delta` = 10,822,080 B > 6,365,994 + 4,576 + 3,400,000 = 9,770,570 B, so run 1 stays at C7
> row 7; the other seven runs meet the amended (4). The source term cannot account for run 1's excess (at most 3.4 MB even if every
> tail row were a rewrite), so this amendment does not settle that excess; the re-run reports what it shows.

> **Runbook-defect fix D3 (2026-10-27, found by the re-run's cluster shakedown, before any re-run reading; amends `W_tail` in the
> amendment above).** The amendment took one row per single-mode op; cassandra-stress writes more. For each op the user-mode
> iterator walks the partition's 8,192 rows once (`PartitionIterator.java:280-283`, window `1 + maxRowCount` for one visit), emits each
> row with the select chance p (`:259-261`, `:569-570`; p = 1/8,192 single, 128/8,192 batch), and, if it reaches the window's last row
> with none emitted, emits that row anyway (`forceReturnOne`, `:444-450`, `:562`); every emitted row is one bound statement
> (`SchemaInsert.java:80-86`). Rows per op = 8,192·p + (1 − p)^8,192: **1.367857 (single)** and 128 (batch). So `W_tail` =
> `n_tail` x 1.367857 (single), `n_tail` x 128 (batch): `8 x W_tail` = 579,971 / 2,319,885 / 4,650,714 B (single) and 424,960 /
> 1,699,840 / 3,399,680 B (batch) at 64 / 256 / 512 MiB. The definition ("rows written by the tail", an upper bound on rewrites)
> and every other part of the amendment are unchanged. Found because the shakedown's stress log reported 13,742 rows/s at
> 10,054 ops/s (ratio 1.367, as derived); run 1's stress logs show the same ratio. Because the clustering values derive from the
> partition key (`PartitionIterator.java:87-101`), the forced last row is one of 1,000 rows, so about 37% of single-mode ops rewrite
> a row already in the memtable. **This changes the answer to "would run 1 pass?":** with the corrected `W_tail`, run 1's
> `v0-def-single` gives `G_end - delta` = 10,822,080 B ≤ 6,370,570 + 4,650,714 = 11,021,284 B, so **run 1 would meet the amended
> C6 (4) in all eight runs, and C7 row 6**. It passes by the bound's slack: `8 x W_tail` assumes that every tail row is a rewrite;
> the expected number of rewrites from the same generator (forced rows beyond the first per key plus random repeats, about 166,000 in
> that tail, 1.33 MB) is not enough to explain the 10.8 MB excess, so this fix does not show that rewrites explain it. Correction of
> the amendment's statement on run 1's histograms: `idle2` held 4,920–41,779 live `BTreeRow`s (not 12,000–42,000).

> **Runbook-defect fix D2 (2026-10-27, found by the cluster shakedowns, before run 1; amends C5's retained delta, used by C6 (4) and
> C7 row 4).** `end1 - end2` is not the memtable's retained heap: the flush between the two histograms also adds the new SSTable's
> on-heap reader structures to `end2` (`end2 - idle2` = +0.99 MB and +0.86 MB in the two shakedowns, where the idle control's flush
> of an empty memtable writes no SSTable), so `end1 - end2` under-reads the memtable by that amount. The retained delta is
> `end1 - idle2`: the live heap after the tail minus the live heap of the same node, idle and with an empty memtable, just before
> the tail (both full-GC histograms); `end1 - end2` and `end2 - idle2` are reported as information. Bands, rows and every
> prediction are unchanged; the cluster tier starts at run 1 with this definition.

**B3h. Controls.**
- The 256MiB vs 64MiB run is the positive control: the same workload with a binding cap of
  a different size.
- The single vs batch modes cover each target line.
- V1 isolates the lines.
- `unslabbed_heap_buffers` avoids slab rounding.
- RF=1, one node, and compaction is irrelevant to the heap measurement (optionally run
  `nodetool disableautocompaction ks t`).

**B4. Risks and cleanup.**
- Build only in `/local/c509`, never in the shared clone.
- Node directories go under `/local/c509-node` (5 M small rows is about 1 GB of sstables).
- After each run, `nodetool drain`, then kill the pid and run `pgrep -f CassandraDaemon`
  and `pgrep -f cassandra-stress` to confirm that nothing is left.
- `rm -rf /local/c509-node` at the end.
- Unit-tier forked JVMs exit with Ant. Check `pgrep -f junit`.

> **Amendment C8 (2026-10-27, stage-4 audit; host cleanup).** Paths per C1; after each run `nodetool drain`, stop, `ps -eo command
> | grep '[C]assandraDaemon'` empty, `$W/node-mhslb` removed; after the tier, the V1 patch reverted and the copied test files
> removed so both clones' `git status` is clean.

## C. Sources read

src/java/org/apache/cassandra/utils/btree/BTree.java (lines 40-77, 150-230, 330-385, 1090-1440, 1470-1900, 2040-2310, 2490-2885, 3325-3470, 3635-3645)
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:77
src/java/org/apache/cassandra/config/Config.java:186-190,524
src/java/org/apache/cassandra/config/DatabaseDescriptor.java:583-594,761-774
src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java
src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:115-200
src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:59-92,249
src/java/org/apache/cassandra/db/memtable/Memtable.java:247-263
src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:150-215
src/java/org/apache/cassandra/utils/memory/MemtablePool.java:40-200
src/java/org/apache/cassandra/metrics/TableMetrics.java:492-512
src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsPrinter.java:109-138
conf/cassandra.yaml:790-826
test/unit/org/apache/cassandra/db/memtable/MemtableSizeTestBase.java
test/unit/org/apache/cassandra/db/memtable/MemtableSizeUnslabbedTest.java
test/unit/org/apache/cassandra/utils/btree/BTreeTest.java:36-60,450-470

## D. Stage-4 feedback

Stage 4 run 1, 2026-10-27, advisor's Mac ([results](../../stage4-runtime-verification/results/memtable_heap_space-LeafBuilder-allocated--autonomous.md)).
Audit: Ready after amendments U1–U5, C1–C8 (frozen `943cd61e…`); runbook-defect fixes D1 (the CMS test JVM reports `maxMemory`
4,277,534,720 B for `-Xmx4g`, so the default limit is 1,019 MiB) and D2 (the retained delta is `end1 - idle2`, because the flush
adds the new SSTable's reader objects to `end2`), both found by shakedowns before run 1; both tiers ran at `1f881f11…`.

- **Unit: Not confirmed — caps** (U4 row 7). Counts exactly as U3 derived (13 line-2683 events per partition in single mode, 4
  line-2736 events per partition in batch mode); every V0 case within ±0.81% of jamm's deep size; V0 − V1 = 88·n2683 + 144·n2736
  exactly for the trie memtable, and 35,000 B short for both skiplist classes (−0.61% single, −1.22% batch), which is the per-JVM
  `SkipListMemtable` row-overhead estimate (187 B vs 194 B, x 5,000 partitions); the ±1% band fails on the two batch pairs.
- **Cluster: Not confirmed — caps** (C7 row 7). At 64 / 256 / 512 MiB: flushes start at `live` 0.50 in all 213 trigger lines, the
  pool's used ratio never exceeded 0.99, writers blocked at 64 MiB, switch counts 46 / 11 / 5 (single) and 45 / 11 / 5 (batch) scale
  as 1/limit, the target lines ran on the node in every run; the retained heap of a 0.25 x limit tail matched the gauge within 5% in
  seven runs and was 8.5% below it (an over-count) in the 512 MiB single-mode run.
- **Findings for stage 3:** A3 step 4's "every 32nd append" is every 17th append after row 32 (B2c's 35,000 events are 65,000); the
  branch nodes rebuilt by `BranchBuilder.drain`/`drainAndPropagate` (`BTree.java:3040, 3057-3063, 3100`) are never counted, so a wide
  partition's root growth (8–16 B per added child) is missed — the measured net errors are +52 B per line-2683 event (V0) and −48 B per
  128-row merge, as traced; B2c's 100–150 B per row is about 326 B per row as accounted.

Stage 4 re-run ("run 1b"), 2026-10-27/28, advisor's Mac, **authorised by the user (Yang, the advisor) on 2026-10-27** ([results §7](../../stage4-runtime-verification/results/memtable_heap_space-LeafBuilder-allocated--autonomous.md)). Two dated amendments `Amendment 2026-10-27 (after run 1, authorised by the user)` (B2: `-Dcassandra.memtable.row_overhead_size=190` in every V0/V1 JVM so the skiplist per-partition charge, otherwise a per-JVM random estimate, cancels in V0 − V1; U4 rows 1 and 6. B3: a rewritten row raises the gauge by its 8-B value and leaves the live heap unchanged, so C6 (4) allows `+ 8 x W_tail` on the over-count side) re-frozen at `fe0ac095…`; runbook-defect fix D3 (cassandra-stress writes 1.367857 rows per single-mode op, so `W_tail` = 1.367857 x `n_tail`), found by the cluster shakedown before any re-run reading, re-frozen at `cde29303…`. Written knowing all of run 1's readings; run 1's unit is Invalid under the pin check (its differences are exact once the logged term is subtracted), and after D3 run 1's cluster would meet the amended band (through the allowance's slack). Fresh clones `$W/cassandra-run70`/`run70v1`, both tiers from the beginning.

- **Unit: Confirmed — caps** (U4 row 6 as amended). Both JVMs charged 190 B per partition; V0 − V1 = 88·n2683 + 144·n2736 exactly for `skiplist`, `skiplist_sharded` and `trie` (5,720,000 / 2,880,000 B); every V0 case within −0.058 … +0.804 % of jamm.
- **Cluster: Confirmed — caps** (C7 row 6 with the amended C6 (4)). Flushes at `live` 0.50 in all 213 trigger lines, used ≤ 0.52, switches 46/11/5 and 45/11/5; tail accounting within 3.9 % of the live-heap change in seven runs and 7.2 % above it in `v0-256-batch`, inside the amended band only through its rewrite allowance (the generator predicts about 2,700 rewrites there, 22 kB), so that lead is not explained by rewrites.
- **Findings for stage 3 (new):** cassandra-stress user mode with `select: fixed(1)/N` writes 1 + (1 − 1/N)^N ≈ 1.37 rows per op and forces the partition's last row in about 37 % of ops, so rewrites are systematic; the idle node holds 5,000–49,000 live `BTreeRow`s outside the memtable that change between full-GC histograms, which moves a live-heap delta by several MB; the skiplist memtables' per-partition charge is a per-JVM random estimate unless `cassandra.memtable.row_overhead_size` is set.
