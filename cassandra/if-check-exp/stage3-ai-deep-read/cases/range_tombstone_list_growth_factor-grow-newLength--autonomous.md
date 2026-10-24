# range_tombstone_list_growth_factor — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/RangeTombstoneList.java:696` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (version not exposed to the agent), 2026-10-23 |
| Estimate | `negative`. The knob only sets the over-allocation ratio when a `RangeTombstoneList`'s backing arrays are enlarged. It sets no maximum on list size or on memory. |
| Ground | The knob is a growth multiplier, not a cap. (1) Nothing compares `unsharedHeapSize()` or `size` against it, so the list can grow without bound whatever its value. (2) At the target line 696, `grow(int newLength)` is called only by `copyArrays` with `newLength = src.size`, so the factor is not used there at all. (3) The factor changes only the slack of the capacity, about `(f-1)*n` slots, and the memtable counts that slack as used memory without bounding it. The real caps on memtable memory are other settings (`memtable_heap_space`, `memtable_cleanup_threshold`). |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `range_tombstone_list_growth_factor`. Companion knob: `initial_range_tombstone_list_allocation_size`.
- **Kind:** configuration entry. It is a `volatile double` field read at runtime.
- **Declared:** `src/java/org/apache/cassandra/config/Config.java:802`.
- **Unit:** dimensionless multiplier on the array capacity (slots).
- **Default:** `1.5`, a literal initialiser with no derivation. The companion default is 1 (`Config.java:798`).
- **Setting it:**
  - yaml key `range_tombstone_list_growth_factor`. It is commented out in the shipped `conf/cassandra.yaml` (I grepped for `range_tombstone_list` in `conf/cassandra.yaml` and the grep tool reported no match), so the yaml value is not documented there.
  - JMX `StorageService.setRangeTombstoneListResizeGrowthFactor(double)` (`service/StorageService.java:6903-6915`). It accepts only `[1.2, 5.0]` and throws `IllegalStateException` otherwise. No restart is needed.
  - The yaml/Config path has no range check. `DatabaseDescriptor.setRangeTombstoneListGrowthFactor` (`DatabaseDescriptor.java:4654-4657`) assigns without validation. I found no validation in `DatabaseDescriptor` or `Config`, but I did not read the whole of `applyConfig`.

**A2. What it caps.** Nothing; the claim is that it caps nothing. The resource it influences is heap. The quantity involved is the capacity of the four parallel arrays `starts`, `ends`, `markedAts` and `delTimesUnsignedIntegers` (`RangeTombstoneList.java:60-63`). A compressed-oops JVM spends about 4+4+8+4 = 20 bytes per slot on them. Their total size is included in `unsharedHeapSize()` (`:770-778`), alongside the bound objects counted in `boundaryHeapSize`. There is no compare-against-limit step.

**A3. Mechanism.**
1. `MutableDeletionInfo.add(RangeTombstone, comparator)` lazily creates the list with capacity `initial_range_tombstone_list_allocation_size` (`MutableDeletionInfo.java:117-120`), then calls `ranges.add(tombstone)`.
2. `RangeTombstoneList.add` (`:157-179`) goes to `addInternal` (`:664-675`). If `size == capacity()` it calls `growToFree(i)`. Otherwise it shifts elements with `moveElements`.
3. `growToFree` (`:680-689`) computes `newLength = ceil(capacity * factor)`. If `newLength <= capacity` (factor ≤ 1, a zero capacity, or a tiny factor) it falls back to `capacity*3/2 + 1`. It then calls `grow(i, newLength)`, which reallocates all four arrays (`:700-739`).
4. The **target line 696** is the overload `grow(int newLength)`: `if (capacity() < newLength) grow(-1, newLength)`. Its only caller is `copyArrays` (`:520-529`, call at `:522`), reached from `addAll` when the destination list is empty (`:189-192`). It grows to exactly `src.size`, so the factor plays no part. The entry pointer therefore sits on a path that does not read the factor. The factor is read only at `:683`.
5. Outcome at the "limit": none. Growth always succeeds, and the only possible failure is a JVM `OutOfMemoryError`. In principle a very large factor can request a very large array: the `(int)` cast saturates at `Integer.MAX_VALUE`, which in practice gives an `OutOfMemoryError`.
6. In a memtable, `BTreePartitionUpdater.merge` (`partitions/BTreePartitionUpdater.java:106-123`) does `existing.mutableCopy().add(update.clone(...))`. `copy()` (`RangeTombstoneList.java:106-114`) trims the arrays to `size`, and `clone()` (`:116-133`) also allocates exactly `size`. The next added tombstone then lands on a full array and grows it by the factor. The slack is added to the memtable's on-heap accounting through `onAllocatedOnHeap(newInfo.unsharedHeapSize() - existing.unsharedHeapSize())` (`:121`, via `MutableDeletionInfo.unsharedHeapSize()` at `:249-254`).
7. Overshoot and accounting oddity: `add()` adds `start.unsharedHeapSize() + end.unsharedHeapSize()` to `boundaryHeapSize` at `:178` after the insertion, and `setInternal` (`:766`) adds it again. If that is right, `unsharedHeapSize()` over-counts the bounds for every add after the first. The unit tier checks this (B2g).

**A4. Other consumers.**
- The memtable's own limits are `memtable_heap_space` and `memtable_cleanup_threshold` (`conf/cassandra.yaml:794-812`).
- The rows, cells and partition keys in the same partition use the same heap.
- The old list is garbage after each merge and is collected. Each write to a partition with n range tombstones allocates an O(n) copy.
- Read and compaction paths build their own `RangeTombstoneList`s with the same knobs.
- The per-query `tombstone_warn_threshold` and `tombstone_failure_threshold` (`conf/cassandra.yaml:1814-1815`) limit tombstones scanned on reads. They do not limit writes.

**A5. Evidence beyond the source.**
- Test `RangeTombstoneListTest.testSetResizeFactor` (`test/unit/org/apache/cassandra/db/RangeTombstoneListTest.java:579-605`) covers only the JMX range check.
- I did not consult external documentation or JIRA. If the original ticket matters, the code comments "Introduce getRangeTombstoneResizeFactor" (`:682`) and "Introduce getInitialRangeTombstoneAllocationSize" (`MutableDeletionInfo.java:117`) are the leads. I did not read the JIRA text.

## B. Verification solution

**B1. Claim under test.** `range_tombstone_list_growth_factor` does not cap the memory a `RangeTombstoneList` or a memtable uses. Changing it from 1.2 to 5.0 changes the capacity slack (about `(f-1)*n` slots) but sets no maximum, and memtable heap use per tombstone follows `f` rather than being bounded by it. The same workload at the same `f` is limited only by `memtable_heap_space`, which is the positive control.

### B2. Unit tier

> Amended 2026-10-23 (stage-4 step 0): see B5 R1, R2, R3, R6, R7.

**B2a. Environment and build.**
- Linux, JDK 11, Ant. Copy the tree to local disk first: `cp -r ~/cassandra-5.0.9 /local/scratch/c509-unit` (never build in the shared tree). Run `cd /local/scratch/c509-unit && ant jar` (or `ant build-test` to run via the test harness).
- Put the test at `test/unit/org/apache/cassandra/db/RangeTombstoneGrowthProbeTest.java` in the copy, in package `org.apache.cassandra.db` so it can reach the package-private pieces. Run it with `ant testsome -Dtest.name=org.apache.cassandra.db.RangeTombstoneGrowthProbeTest`.
- Because the fields `starts`, `ends`, `markedAts` and `delTimesUnsignedIntegers` are private, read the capacity by reflection (`setAccessible(true)`).
- JVM options: the default test options (`-Xmx` as set in `build.xml`), plus `-XX:+UseCompressedOops` (default) so the 20 B/slot arithmetic applies.
- Use `ObjectSizes.measureDeep` (`org.apache.cassandra.utils.ObjectSizes`, JAMM-based) as an independent check on `unsharedHeapSize()`. Add the JAMM agent through the harness's existing JVM args. If that is not possible, use array lengths only and mark the deep check as not run.

**B2b. Knobs.**
- `DatabaseDescriptor.setRangeTombstoneListGrowthFactor(f)` at f ∈ {1.2, 1.5, 2.0, 5.0}. The JMX bounds are 1.2 and 5.0; the setter takes any value, so also run f ∈ {1.0, 0.5} (fallback path, `:685-686`) and f = 100.0 (outside the JMX range, to show the value is not capped at the code level).
- `setInitialRangeTombstoneListAllocationSize(c)` with c ∈ {1, 1024} (the JMX range is [0, 1024]).
- Both are plain static setters, so no restart is involved.

**B2c. Workload.**
- Build a list from `new RangeTombstoneList(comparator, c)` using a `ClusteringComparator` over one `Int32Type` column, adding n disjoint sorted tombstones `[2i, 2i+1]` (use `ClusteringBound.inclusiveStartOf` / `inclusiveEndOf` with a one-value clustering). Use n ∈ {1, 10, 1_000, 100_000}. The sorted-append case takes the `size, start, end` path in `addInternal`.
- Second shape (memtable-like): `copy()` the list then add one more tombstone, repeated 1_000 times. This models `BTreePartitionUpdater.merge` (`copy()` trims capacity to `size`, so the next add grows by `f`).
- Third shape: `addAll` into an empty list (target line 696 path) for n = 1_000, to show the factor is not used there.
- Limit-reach arithmetic: there is no limit to reach. Sorted-append capacity after n adds is the iterated `c -> ceil(c*f)`. For f = 2, c = 1 the capacities are 1, 2, 4, 8, ..., so n = 100_000 ends at 131_072 slots (131_072 × 20 B ≈ 2.6 MB plus headers). For f = 5.0, c = 1 the capacities are 1, 5, 25, 125, 625, ..., so n = 100_000 ends at 3_125 × 5³ = 390_625 slots (≈ 7.8 MB).

**B2d. Observables and instruments.**
- `capacity()`-equivalent: reflected `starts.length`, and the other three arrays' lengths.
- `list.unsharedHeapSize()` and `list.size()`.
- `ObjectSizes.measureDeep(list)` as the independent reading.
- Not observable directly: the JVM's real allocation for the temporary copies (no GC or allocation sampler is used in this tier).

**B2e. Procedure.**
1. Copy and build as in B2a.
2. For each (f, c, n): set the knobs, build the list per B2c, record `size`, the four array lengths, `unsharedHeapSize()` and (if available) `measureDeep`. Restore the original knob values in a `finally` block.
3. For the `copy()+add` shape, record capacity after each iteration.
4. For the `addAll` shape, record capacity right after the call.
5. Print one CSV row per run to stdout and compare with B2f.

**B2f. Predictions (written before any run).**
- Sorted appends, c = 1: capacity after n adds is the iterated `c -> ceil(c*f)`.
  - f = 1.5: 1, 2, 3, 5, 8, 12, 18, 27, ... (first step `ceil(1.5) = 2`, then `ceil(3) = 3`, `ceil(4.5) = 5`).
  - f = 2.0: powers of two.
  - f = 1.2: 1, 2, 3, 4, 5, 6, 8, ...
- For n = 100_000, final capacity / n lies in [1, f] and is below `f` by construction.
- Slack is `capacity - size` and grows roughly linearly with n for fixed f (about `(f-1)*n` at worst).
- f ≤ 1.0 behaves as the fallback `cap*3/2 + 1`: 1, 2, 4, 7, 11, ...
- f = 100.0 is accepted with no error at the setter, and capacity grows by ×100 each time (1, 100, 10_000, 1_000_000).
- `copy()+add` loop: after each `copy()` capacity equals `size`; after the add it equals `ceil(size*f)` (about 1.5 × size at f = 1.5). It does not stay bounded.
- `addAll` into an empty list: capacity equals the source `size` exactly and is the same for every f. This is the target-line path and confirms the factor is not read there.
- `unsharedHeapSize()` ≥ 20 B × total capacity, and rises with capacity. If `boundaryHeapSize` is double counted (A3 step 7), then `unsharedHeapSize()` minus `measureDeep` is positive and grows with n.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Capacity follows the iterated `ceil(c*f)` and slack grows with n and f; no value of f stops growth | Claim confirmed: the knob is a growth rate and caps nothing. |
| `unsharedHeapSize()` rises with n beyond any f-derived bound (e.g. n = 100_000 at f = 1.2 uses far more memory than at n = 1_000) | Usage follows n, not f: confirmed. |
| Capacity or heap is flat across f at the same n | Claim refuted only if the positive-control variation (below) does move it. Otherwise the probe is wrong; recheck that the tombstones really go through `growToFree`. |
| `addAll` capacity is the same across f | Target line 696 does not use the factor: confirmed. |
| Setting f = 100.0 or 0.5 throws or is clamped | Contradicts A1's "no validation" at the `DatabaseDescriptor` level. |
| Capacity is bounded by something that depends on f, for example a hard max of size | Claim refuted. |
| Capacity never grows (e.g. list never reaches `capacity()`) or the control does not move | Not confirmed: the limit was never reached; fix the workload. |

Positive control (a cap known to bind): the same adds with `c` large and `n < c` never call `growToFree`. Capacity then equals `c`, whatever f is. Initial allocation does bind capacity for this workload, so it shows the probe can see a bound.

**B2h. Controls.**
- Re-run every case with a fixed `c` and vary only f, then the reverse.
- Run each shape twice to check the capacity sequence is deterministic.
- Reflect on each of the four arrays to confirm they have equal length (the constructor asserts it at `:76`).

### B3. Cluster tier

> Amended 2026-10-23 (stage-4 step 0): see B5 R1, R3, R4, R5, R7, R8.

**B3a. Environment and build.**
- One node is enough. Copy the tree: `cp -r ~/cassandra-5.0.9 /local/scratch/c509-node && cd /local/scratch/c509-node && ant jar`, JDK 11.
- Point `data_file_directories`, `commitlog_directory`, `saved_caches_directory` and `hints_directory` at a local disk path with at least 20 GB free (for example `/local/scratch/c509-data`).
- JVM: `-Xms4G -Xmx4G` (fixed heap) and G1.
- `cassandra.yaml` changes:
  - `memtable_allocation_type: heap_buffers` (the default, `conf/cassandra.yaml:825`) so the memtable's on-heap accounting is the whole story.
  - `memtable_heap_space: 1024MiB`.
  - `memtable_flush_writers: 2` and `commitlog_sync: periodic`.
- Disable the other tombstone limits as needed: `tombstone_failure_threshold: 100000000` (`:1815`) only matters for reads, so leave it for write-only runs.
- Never run against production data.

**B3b. Knobs.**
- `range_tombstone_list_growth_factor` via `nodetool` is not exposed, so use JMX: `setRangeTombstoneListResizeGrowthFactor` on `org.apache.cassandra.db:type=StorageService` (a `jmxterm` or `jcmd`-attached JMX call; `jmxterm` must be installed locally). Values: 1.2, 1.5 (default), 2.0, 5.0.
- Restart-free, so all four values can run on one node. Between runs, flush and drop the table's memtable (`nodetool flush`) so each run starts from an empty memtable.
- Positive control knob: `memtable_heap_space` (a restart is needed), 256MiB versus 1024MiB, to show a binding cap moves memtable behaviour.

**B3c. Workload.**
- Schema: `CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int, ck int, v int, PRIMARY KEY (pk, ck));`
- Writes through cqlsh or the Python driver:
  `DELETE FROM ks.t WHERE pk = 1 AND ck > ? AND ck < ?` with disjoint ranges `(4i, 4i+2)`, i = 0..N-1, so each delete is a separate range tombstone in one partition. N = 20_000 per run. Each write does an O(n) copy, so N = 20_000 is ≈ 2×10⁸ element copies in total, which is manageable.
- Arithmetic: at f = 1.5 the capacity after the n-th merge is `ceil(1.5·(n-1))` ≈ 1.5 × n at most, about 30_000 slots × 20 B ≈ 0.6 MB per list. At f = 5.0 it is about 100_000 slots ≈ 2 MB per list. The difference is small against a 1 GiB memtable but visible in a histogram. To make it large, run 50 partitions (pk = 1..50) with N = 20_000 each, so the aggregate slack is about 50 × (5.0 − 1.2) × 20_000 × 20 B ≈ 76 MB.
- Duration: a few minutes per run. Stop writes after the target N and sample before the next flush.

**B3d. Observables and instruments.**
- Heap: `jcmd <pid> GC.class_histogram` taken twice (before the workload and after the last write), reading the byte totals for `[J` (long[]), `[I` (int[]) and the `ClusteringBound[]` array classes.
- Memtable accounting: JMX `org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=MemtableOnHeapDataSize` (`metrics/TableMetrics.java:493`), also `MemtableColumnsCount` (`:489`). Sample after the last write and before any flush.
- Process RSS: `ps -o rss= -p <pid>` (cross-check only; G1 does not return memory promptly).
- Not directly observable: the per-list capacity inside a live node. The histogram is the proxy.
- Also record `nodetool tablestats ks.t` ("Memtable data size", "Memtable cell count") and `nodetool gcstats`.

**B3e. Procedure.**
1. Build and configure per B3a. Start the node, confirm `nodetool status` shows UN.
2. Create the schema (B3c).
3. For f in {1.2, 5.0, 1.5, 2.0} (interleave to counter drift): set f over JMX and read it back; flush; run `jcmd <pid> GC.run` followed by a `GC.class_histogram` baseline; run the delete workload; record the histogram, `MemtableOnHeapDataSize` and `MemtableColumnsCount`; flush.
4. Positive control: at f = 1.5 restart with `memtable_heap_space: 256MiB` and rerun, expecting an earlier flush (flush count in `nodetool tablestats` or the log) and a lower peak `MemtableOnHeapDataSize` ceiling.
5. Stop the node cleanly (`nodetool drain`, then `kill <pid>`), verify no `CassandraDaemon` is left with `pgrep -f CassandraDaemon`, and remove the data directory.

**B3f. Predictions.**
- `MemtableOnHeapDataSize` for the same N and partitions rises with f. For the 50 × 20_000 workload I expect the difference between f = 5.0 and f = 1.2 to be on the order of the 76 MB arithmetic above. If `boundaryHeapSize` is double counted, the reported absolute value is also inflated by about the bound sizes. I do not state a number for that.
- The primitive-array byte totals (`[J`, `[I`) in the histogram follow the same ordering, and the long[] part is about 8 B per slot.
- No error or cap appears at any f: the writes all succeed until the memtable limit forces a flush.
- With `memtable_heap_space: 256MiB` the node flushes earlier and its memtable size stays under that ceiling, at any f. This is the binding cap.
- What would show the claim wrong: memtable or histogram size flat across f for the same N, or a ceiling that depends on f.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `MemtableOnHeapDataSize` and the histogram arrays rise with f for the same N, with no ceiling tied to f | Claim confirmed: usage follows the workload and f changes only the slack; it does not cap. |
| Usage follows f in a way that saturates at a value set by f | Claim refuted: the knob would act as a cap. |
| Usage is flat in f while the positive control (`memtable_heap_space`) moves flush timing and ceiling | Usage does not follow f, which also supports the claim, but then the slack arithmetic needs re-checking (the merge path might not allocate as traced). |
| Flat in f and the positive control does not move either | Not confirmed: the workload never reached the memtable limit or the instrument is wrong. |
| `memtable_heap_space` has no effect on flush timing | The control failed; fix the workload (more data) before judging the claim. |
| Node `OutOfMemoryError` at some f (e.g. 5.0 with a large N) | The knob does not prevent heap exhaustion: consistent with the claim. |

**B3h. Controls.**
- Repeat each f twice and interleave the order to rule out GC timing.
- Take the histogram right after `GC.run` so garbage copies do not pollute the totals.
- Keep every other knob (`initial_range_tombstone_list_allocation_size`, heap, flush writers) identical across runs.
- Use the same N and partitions, with no reads in between.
- A control table without range deletes (plain inserts of the same count) shows the arrays come from the range tombstones.

**B4. Risks and cleanup.**
- **Disk:** the data directories live on local disk of known size (≥ 20 GB), and the flushed SSTables are small. Remove them with `rm -rf /local/scratch/c509-data` after the run, once you have checked the path.
- **Shared storage:** nothing is written to the shared source tree, and the unit and node copies are under `/local/scratch`.
- **Processes:** stop the node (`nodetool drain`, then kill); the unit tier's JVM exits on its own. Check with `pgrep -fl 'CassandraDaemon|ant'` that nothing is left.
- **Heap:** a very large f (like 100.0 in the unit tier) can request huge arrays and cause an `OutOfMemoryError`. Run that case last and in its own JVM, with a modest `-Xmx` (e.g. 512m).
- **Restore:** the JMX knob returns to 1.5 after a restart.

### B5. Step-0 audit amendments (2026-10-23, stage 4, before the freeze and before any reading)

Each item says which filed text it changes. The case's claim (B1), the estimate and the *meaning* of every B2g/B3g row are unchanged; R3 only defines words, and the control designations make explicit what the filed controls already were.

**R1 (environment; B2a, B3a, B4).** Every working tree is made by `stage4-runtime-verification/copy-source.sh` from this repository's `cassandra/cassandra-5.0.9/` (README safety rules), here `~/cassandra-rtl-n` (built with `ant build-test`; this file's tiers both use it). The `cp -r ~/cassandra-5.0.9 …`, `rsync … /tmp/ct` and `/local/...` paths of B2a, B3a and B4 are replaced by that tree and by node data under `~/stage4-rtl-n/` (local `/dev/sda3`, not `/proj`). Cleanup (B4) is therefore `rm -rf ~/stage4-rtl-n` and removing the test file from the tree; the tree stays on the node and is listed in the results file.

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

**R4 (cluster memory configuration; B3a, B3c arithmetic).** A memtable flush starts when the pool reaches `memtable_cleanup_threshold = 1/(1 + memtable_flush_writers)` of `memtable_heap_space`, 1/3 at the default two writers (`DatabaseDescriptor.java:761-764`, `conf/cassandra.yaml:794-812, 899-912`), not at the limit itself. The counter that the flush check reads also over-counts the bounds of every non-first `add()` (`RangeTombstoneList.java:178` after `setInternal` line 766 has counted them), so the filed estimate of about 250 B per tombstone understates the counter. With the filed 50 partitions × 20,000 = 1,000,000 tombstones with a 1024 MiB limit (flush at about 341 MiB of counter) and a 4 GiB heap a flush would occur inside the main cells and reset the lists, which the claim's readings must not contain. The main cells therefore run with `MAX_HEAP_SIZE=8G` and `memtable_heap_space: 3072MiB` (flush at about 1024 MiB of counter, more than twice the largest expected counter); the positive control keeps its filed small value (256MiB, flush at about 85 MiB). All other B3a settings stay.

**R5 (cluster workload and instruments; B3a, B3b, B3c, B3d, B3e).**
- *Heap and limit.* B3a's `-Xms4G -Xmx4G` and `memtable_heap_space: 1024MiB` are replaced by `MAX_HEAP_SIZE=8G` and the R4 value; the positive-control restart uses the filed 256 MiB. `memtable_flush_writers: 2` and `commitlog_sync: periodic` stay.
- *Workload.* As filed: 50 partitions × 20,000 range deletes = 1,000,000 tombstones, `DELETE FROM ks.t WHERE pk = ? AND ck > 4i AND ck < 4i+2`. Driven by the bundled Python driver, one request in flight per partition (50 concurrent), each partition ascending. Checkpoints at 5,000, 10,000 and 20,000 deletes per partition (250,000, 500,000, 1,000,000 tombstones): the dependence on N inside one run; a forced collection plus histogram at each.
- *Cells.* One node lifetime for the four factors, interleaved as B3e step 3 says: f = 1.2, 5.0, 1.5, 2.0, then the same four reversed (2.0, 1.5, 5.0, 1.2, B3h "repeat each f twice and interleave"). Each cell: set f through JMX and read it back; `nodetool flush`; histogram baseline after a forced collection; the load; the checkpoints; `nodetool flush`. The positive control is a second lifetime with `memtable_heap_space: 256MiB` at f = 1.5 (B3e step 4). The B3h control table (ordinary inserts of the same count into `ks.t2`, f = 1.5) is one more cell in the first lifetime.
- *Instruments.* The harness `Jmx.java` replaces jmxterm and `jcmd` for the read-back and the runtime set. At each checkpoint: `MemtableOnHeapDataSize`, `MemtableColumnsCount`, `MemtableSwitchCount`, the class histogram rows of `ClusteringBound[]`, `BufferClusteringBound`, `long[]`, `int[]` and the total, `RssAnon`; during the load a 2-second counter series and a 250 ms heap-pool poll. A Byteman rule on `growToFree` (observation only) logs capacity and `newLength` every 1000th call, with the call counter, so the factor read by the traced line is seen directly. Autocompaction is disabled (R7).

**R6 (prediction wording that the source contradicts; B2f, B2g).** (1) B2f "`addAll` into an empty list: capacity equals the source `size` exactly and is the same for every f" is false for `c = 1024`: `grow(int)` grows only `if (capacity() < newLength)` (`RangeTombstoneList.java:694-698`), so the capacity after `copyArrays` is `max(c, src.size)`: 1,000 for c = 1 and 1,024 for c = 1,024 (source of 1,000 tombstones). It is the same for every f in both cases, so the B2g row "`addAll` capacity is the same across f" and the bypass conclusion are unchanged. (2) B2f "`f = 100.0`, … 1, 100, 10_000, 1_000_000" is the capacity sequence at `c = 1` and is tested as such. (3) B3a's 4 GiB heap and 1024 MiB limit are replaced by R4/R5; B3c's "N = 20_000 … ≈ 2×10⁸ element copies" is per partition (about 10¹⁰ in total) and is accepted.

**R7 (controls made explicit; B2g, B3h).** Unit: the filed positive control (`c = 1024`, `n < c`, capacity stays 1,024 whatever f is) is run at f = 1.2, 1.5, 2.0 and 5.0; the cells `c = 1024` with `n = 1, 10, 1000` are the same control. Cluster: `memtable_heap_space: 256MiB` is the positive control; the plain-insert table is the instrument check that the `ClusteringBound[]` rows come from range tombstones. `nodetool disableautocompaction` is issued at the start of the lifetime (compaction would build its own lists), and `autocompaction_on_startup_enabled: false` is set.


**R8 (cluster-tier definitions, written after the unit tier ran and before any cluster reading; B3f, B3g, B3h).** Nothing here depends on a reading; each item defines a word.
- *"on the order of the 76 MB arithmetic"* is R3's [0.5, 2] × 76 MB = [38, 152] MB, applied to `counter(5.0) − counter(1.2)` at the last checkpoint (the mean over the repeats of each factor).
- *"The primitive-array byte totals (`[J`, `[I`) follow the same ordering, and the `long[]` part is about 8 B per slot"* := the live `long[]` bytes after the last checkpoint are ordered like f, and `long[](5.0) − long[](1.2)` lies in [0.5, 2] × 8 B × (extra slots), the extra slots being `(ClusteringBound[](5.0) − ClusteringBound[](1.2)) / 8` (two arrays of 4-byte references per list).
- *Control "expecting an earlier flush … and a lower peak `MemtableOnHeapDataSize` ceiling"* := `MemtableSwitchCount` rises above its start value in the 256 MiB lifetime while it does not in the main cells, and the largest value of the 2-second counter series is at most 256 MiB.
- *B3h plain-insert table*: the live `ClusteringBound[]` bytes after its last checkpoint exceed the cell's baseline by less than 64 KiB.
- *JMX setter note (instrument, not a design change):* `setRangeTombstoneListResizeGrowthFactor(double)` has no matching getter name, so JMX exposes it as the write-only attribute `RangeTombstoneListResizeGrowthFactor`; the harness sets it with `setAttribute` and reads `RangeTombstoneResizeListGrowthFactor`.

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/db/RangeTombstoneList.java`
- `src/java/org/apache/cassandra/db/MutableDeletionInfo.java`
- `src/java/org/apache/cassandra/config/Config.java`
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`
- `src/java/org/apache/cassandra/service/StorageService.java`
- `src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java`
- `src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java` and `PartitionUpdate.java` (grep hits only)
- `src/java/org/apache/cassandra/metrics/TableMetrics.java` (grep hits only)
- `conf/cassandra.yaml` (grep hits only)
- `test/unit/org/apache/cassandra/db/RangeTombstoneListTest.java`

## D. Stage-4 feedback

**Stage 4, 2026-10-23 (autonomous stage-4 session, `pc07`): Confirmed — does not cap, both tiers. Outcome class: true negative.** Results: `stage4-runtime-verification/results/range_tombstone_list_growth_factor-grow-newLength--autonomous.md` (run 1, self-checked, no run 2). Frozen versions: sha256 `bec115be93c9515da3a9f5aa140e30ee86e352d9524f2e9b5b47550630db67fa` (unit; audit amendments R1–R7), `ecc4706fca98352c6adb93d3328a3644d962d52c0d175f0b566fc59fc95f3eea` (cluster; plus R8 before any cluster reading). Case file not committed (no commit to cite).

- **Unit (B2).** 112 runs (7 factors incl. 1.0, 0.5, 100.0 × c ∈ {1, 1024} × n ∈ {1, 10, 1,000, 100,000} × 2): capacity follows the iterated expression in every run, f = 100.0 from capacity 1 gives 100, 10,000, 1,000,000 (the setter takes it without error); `copy()` + add × 1,000: capacity == size after `copy()` and `ceil(size·f)` after the add in all 1,000 iterations of 8 runs; `addAll` into an empty list reaches `max(c, src.size)` for every f (the target line 696 path does not read the factor); the c = 1024, n < c control keeps 1,024 at f = 1.2 – 5.0. **One frozen criterion did not hold as written**: the R3 slack bound for the 2 of 168 pairs that contain f = 0.5 or 1.0 against 1.2 (c = 1, n = 100,000: 649,552 B against 560,028 B), because f ≤ 1.0 applies the fallback `cap·3/2 + 1` (effective factor 1.5); with the effective factor it holds, and for every legal factor it holds as written. Reported, not amended after the reading. **Prediction fixed before the cluster tier (R6):** B2f's "`addAll` capacity equals the source `size` exactly" is wrong for c = 1024 (`grow(int)` only grows `if (capacity() < newLength)`): it is `max(c, src.size)`; the B2g row "same across f" is unchanged.
- **Cluster (B3).** One lifetime, eight cells in the order 1.2, 5.0, 1.5, 2.0, 2.0, 1.5, 5.0, 1.2 (JMX), 50 × 20,000 = 1,000,000 range deletes each, `memtable_heap_space` 3072 MiB, 8 GiB heap: all 10 million acknowledged; counter 504 / 510 / 520 / 580 MB at f = 1.2 / 1.5 / 2.0 / 5.0, identical between repeats; counter(5.0) − counter(1.2) = 76.0 MB (the filed "order of 76 MB"), `long[]` difference 30.4 MB = 8 B × 3.8 M extra slots; the plain-insert table adds 0 B of `ClusteringBound[]`; control at 256 MiB: 5 memtable-limit flushes, counter ≤ 84.6 MiB. Byteman: `newLength = ceil(cap·f)` in 8,986 sampled `grow` calls.
- **Amendments to this file (section B5, dated 2026-10-23, none depends on a reading).** R1 working tree; R2 test-JVM facts; R3 definitions; R4 flush threshold and the 8 GiB / 3072 MiB main configuration (the filed 4 GiB / 1024 MiB would flush inside the main cells); R5 workload, cell order and instruments; R6 the `addAll` wording and the sizes; R7 controls made explicit, autocompaction off; R8 (before the cluster tier) cluster definitions and the note that the setter is a write-only JMX attribute.
- **Stage 3 notes.** B3c's "≈ 2×10⁸ element copies" is per partition (≈ 10¹⁰ in total) and was accepted; the filed JVM option `-Xmx512m` for the f = 100.0 cell does not apply to `ant testsome` (1024 MiB), and that cell needed no more than 20 MB.

Side finding (not part of the claim, from the unit and cluster readings of all three sibling files): the `boundaryHeapSize` bookkeeping counts the bounds twice on the `add()` path (`RangeTombstoneList.java:178` after `setInternal` line 766). `boundaryHeapSize` is 2.000 × the true sum of the bound sizes and `unsharedHeapSize()` minus Jamm `measureDeep` equals the true bound sizes (N = 100,000, f = 1.5: 23,999,872 B against 24,000,000 B). In a node the memtable counter reads about 504 B per tombstone at f = 1.2 (580 B at f = 5.0) where the live heap above the baseline is about 270 – 280 B (340 – 370 B), so the memtable limit and the flush trigger are reached at roughly half the real tombstone volume. This is an accounting overestimate, not a cap tied to the factor. (A JIRA search was not done.)
