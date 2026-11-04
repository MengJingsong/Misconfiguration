# range_tombstone_list_growth_factor — verification solution  <!-- file: cases/range_tombstone_list_growth_factor-growToFree-newLength--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/RangeTombstoneList.java:685` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (`claude-sonnet-5-5`), Claude Code CLI (version not exposed to the agent), 2026-10-23 |
| Estimate | `negative`. The factor only sets how much spare array capacity a `RangeTombstoneList` gets each time it grows. It is not a limit on how many tombstones or bytes a node holds. |
| Ground | The factor is a growth multiplier, validated only to [1.2, 5.0], and nothing compares a usage value against it. It changes the slack (allocated minus used slots) of one per-partition object and the number of re-allocations. The number of tombstones is set by the workload and by `tombstone_warn_threshold` / `tombstone_failure_threshold`, which are read-side limits. Total memtable memory is capped by `memtable_heap_space` / `memtable_offheap_space`, not by this factor. |

Note: the line given as the target (685) is the fallback guard `if (newLength <= capacity())`. It is not the main enforcement point of any limit. It only prevents a non-growing size when `ceil(capacity * factor)` does not exceed `capacity` (for example capacity 0 or 1 with a small factor).

## A. Constraint trace

**A1. The constraint.**
- Name: `range_tombstone_list_growth_factor` (a `double`). It is a configuration entry, and a related one is `initial_range_tombstone_list_allocation_size`.
- Declared at `src/java/org/apache/cassandra/config/Config.java:802`, `public volatile double range_tombstone_list_growth_factor = 1.5;`. The initial size is declared at `Config.java:798` with default `1`.
- Unit: a dimensionless multiplier on the array capacity (slot count).
- Default: 1.5, a literal in `Config.java:802`. It is not derived from anything. The code's fallback `(capacity*3)/2 + 1` (`RangeTombstoneList.java:686`) matches the older hard-coded 1.5 growth.
- How to set it:
  - yaml key `range_tombstone_list_growth_factor`. It is absent from the shipped `conf/cassandra.yaml` (grep of `conf/` found no match), but `Config` fields are loadable from yaml by name. The key appears in `test/data/config/version=5.0-alpha1.yml:479`.
  - JMX `StorageServiceMBean.setRangeTombstoneListResizeGrowthFactor(double)` (`StorageServiceMBean.java:1172`, implemented at `StorageService.java:6903`). It rejects values outside [1.2, 5.0] (`StorageService.java:6905`), so the JMX path cannot set a factor ≤ 1.
  - The getter is `getRangeTombstoneResizeListGrowthFactor` (`StorageService.java:6898`).
  - The field is `volatile` and read on every growth (`RangeTombstoneList.java:683`), so a change takes effect without a restart. The yaml value is validated only through the JMX setter. Whether the yaml path validates it is not checked here; the setter in `DatabaseDescriptor.java:4654` does not validate.

**A2. What it caps.** Nothing is capped. The resource affected is heap (JVM heap) only. The quantity it influences is `capacity()` (`starts.length`, `RangeTombstoneList.java:656-659`) of one `RangeTombstoneList`. It sets the ratio of allocated slots to used slots (`size`). Each slot costs `starts[i]` ref + `ends[i]` ref + 8-byte `markedAts` + 4-byte `delTimesUnsignedIntegers`, about 20 B with compressed oops. The factor is never compared with a usage value.

**A3. Mechanism.**
1. `MutableDeletionInfo.add(RangeTombstone, comparator)` creates the list lazily with `DatabaseDescriptor.getInitialRangeTombstoneListAllocationSize()` slots (`MutableDeletionInfo.java:117-118`), default 1.
2. `RangeTombstoneList.add(...)` (`RangeTombstoneList.java:157`) calls `addInternal` (line 664), or `insertFrom` for out-of-order input, which also ends in `addInternal`.
3. `addInternal` checks `size == capacity()` (line 668). If full, it calls `growToFree(i)`. Otherwise it shifts elements with `moveElements` (line 744).
4. `growToFree` (line 680) computes `newLength = ceil(capacity * factor)` (line 683). If `newLength <= capacity` (line 685) it falls back to `capacity*3/2 + 1` (line 686). It then calls `grow(i, newLength)` (line 700), which re-allocates all four arrays.
5. Outcome at the "limit": when the list is full, it is replaced by arrays `factor` times larger. Nothing is rejected or evicted, and no exception is thrown.
- Bypass and overshoot:
  - `copyArrays` (line 520), used by `addAll` into an empty list (line 191), grows to exactly `src.size` via `grow(int)` (line 694) and does not use the factor.
  - `copy()` (line 106) trims to `size`, and `clone()` (line 116) also allocates exactly `size`.
  - Worst-case slack is roughly `(factor-1) * size` slots, so for factor 5.0 up to about 4x the live entries are allocated.
  - `unsharedHeapSize()` (line 770) counts allocated array capacity, so slack is visible to the memtable accounting.
  - `boundaryHeapSize` appears to be added twice for in-order adds: `setInternal` adds it (line 766) and `add` adds again (line 178). This is an accounting quirk that overstates the reported size. It is noted here as a possible confound for any reading based on `unsharedHeapSize()`, and I did not confirm it by running.

**A4. Other consumers.**
- Heap used by the memtable (`memtable_heap_space`, `memtable_allocation_type: heap_buffers`, `conf/cassandra.yaml:797-825`) includes the list through `MutableDeletionInfo.unsharedHeapSize` (`MutableDeletionInfo.java:249-254`) and `PartitionUpdate.unsharedHeapSize` (`PartitionUpdate.java:357-360`).
- Read-path lists: `ReadCommand` counts tombstone-related size at `ReadCommand.java:694-708`.
- The `ClusteringBound` objects themselves (counted in `boundaryHeapSize`) and the tombstone count come from the workload, not from this factor.
- Read-side limits `tombstone_warn_threshold: 1000` and `tombstone_failure_threshold: 100000` (`conf/cassandra.yaml:1814-1815`) bound how many tombstones one query scans, not the size of a memtable list.

**A5. Evidence beyond the source.**
- Unit test for the setter: `test/unit/org/apache/cassandra/db/RangeTombstoneListTest.java:579-605` (bounds [1.2, 5.0]).
- `test/data/config/version=5.0-alpha1.yml:479` shows the yaml field type.
- No external web sources were consulted.

## B. Verification solution

**B1. Claim under test.** Memory used by range tombstones does not follow `range_tombstone_list_growth_factor` as a cap. Raising the factor from 1.2 to 5.0 enlarges allocated capacity per list (slack) and changes allocation counts, but the number of tombstones and the memory they use stay set by the workload, and nothing stops the list from growing at any factor. Falsified if tombstone growth halts or is rejected at a factor-dependent size, or if total tombstone memory is bounded independently of workload size at a fixed factor.

### B2. Unit tier

> Amended 2026-10-23 (stage-4 step 0): see B5 R1, R2, R3, R6, R7.

**B2a. Environment and build.**
- JDK 11, Ant. Copy the tree to local disk first: `rsync -a <src>/cassandra-5.0.9/ /tmp/ct/cassandra-5.0.9/` (do not build in the shared tree).
- Build in the copy: `ant jar` (or `ant build-test`).
- Put the test at `/tmp/ct/cassandra-5.0.9/test/unit/org/apache/cassandra/db/RtlGrowthFactorProbeTest.java`, in the copy only.
- Run: `ant testsome -Dtest.name=org.apache.cassandra.db.RtlGrowthFactorProbeTest`.
- JVM options: the stock test options plus `-Xmx2g`. Use `-XX:+UseCompressedOops` (the default at this heap size) so slot size is the 20 B in A2.

**B2b. Knobs.**
- `DatabaseDescriptor.setRangeTombstoneListGrowthFactor(f)` with f in {1.2, 1.5, 2.0, 5.0}. These are the bounds, the default and a mid value, and they also exercise the JMX range.
- `DatabaseDescriptor.setInitialRangeTombstoneListAllocationSize(n)` with n in {0, 1, 1024}, as a second knob to separate initial capacity from growth.
- Both are set directly in the test JVM.

**B2c. Workload.**
- Build `new RangeTombstoneList(comparator, n0)` and add N non-overlapping tombstones in sorted order: `[2i, 2i+1]` on a one-int-column `ClusteringComparator`.
- N in {10, 1000, 100000}. Sorted adds take the `addInternal(size, ...)` fast path (line 170).
- N = 100000 gives many growth steps (about 30 at 1.5) so the capacity series is well defined.
- For the bypass check, also run `addAll` from a filled list into an empty one.

**B2d. Observables and instruments.**
- `size()` (public). Capacity is private, so read `starts.length` by reflection on field `starts` and record it after every add. Record `capacity - size` as slack.
- `unsharedHeapSize()` (line 770).
- Independent measure: `org.github.jamm.MemoryMeter` (`ObjectSizes`) on the list, to check `unsharedHeapSize()` against real size, including the possible double count of `boundaryHeapSize`.
- Count growth events as the number of times capacity changes.
- Not observable directly: real GC retention. The cluster tier covers that.

**B2e. Procedure.**
1. Copy the tree, build (B2a).
2. For each (f, n0, N): set knobs, build the list, add N tombstones, and log the capacity series, the growth-event count and final `unsharedHeapSize()` and MemoryMeter size.
3. Repeat the adds of N+1 tombstones after the last growth to confirm the list accepts them (no rejection).
4. Run the `addAll` bypass case and compare capacity with `src.size`.
5. Positive control: run the same adds on a structure with a known bound. Use `ThreadLocal`-free `ArrayList` with a fixed `ensureCapacity`, or a `LinkedHashMap` with `removeEldestEntry` at M entries, and show its size plateaus at M while the list does not.
6. Clean up: `rm -rf /tmp/ct`.

**B2f. Predictions (before any run).**
- Capacity after a growth at factor f is `ceil(cap*f)`, or `cap*3/2 + 1` when `ceil(cap*f) <= cap`. With n0 = 0 and f = 1.2: `ceil(0*1.2) = 0 <= 0`, so the fallback gives 1, then `ceil(1.2) = 2`, then `ceil(2.4) = 3`, and so on.
- Growth events for N = 100000 are about ln(N)/ln(f): roughly 63 at f=1.2, 28 at f=1.5, 17 at f=2.0, 8 at f=5.0.
- Final slack is at most `(f-1)*size`. Final `unsharedHeapSize()` rises with f for a fixed N, by up to about 4x the array part (20 B × slots) at f=5.0 versus the exact size. The array part is a smaller share of the total than `boundaryHeapSize` when the bound objects are large.
- All N adds succeed at every f. Size is N in every case.
- `addAll` into empty gives capacity exactly `src.size`, independent of f.
- Positive control plateaus at M; the list does not.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Size reaches N at every f and keeps accepting adds; slack and heap vary with f but total entries match the workload | Claim confirmed: the factor shapes slack only, it does not cap usage |
| Adds fail, throw, or the list stops growing at a size that depends on f | Claim refuted: the factor acts as a cap |
| `unsharedHeapSize()` stays flat as N rises (at fixed f) while the control moves | Claim refuted |
| `unsharedHeapSize()` rises with N at every f, while the positive control plateaus | Claim confirmed |
| Growth counts or capacities differ from the formula in B2f | The mechanism was traced wrongly; re-read lines 683-686 |
| Largest N never reaches a growth beyond the initial capacity, or the control does not plateau | Not confirmed, the workload or control is invalid |
| `unsharedHeapSize()` and MemoryMeter disagree by about `boundaryHeapSize` | The double count at lines 178/766 is real; reading by `unsharedHeapSize()` is biased and MemoryMeter should be used |

**B2h. Controls.**
- Fix the comparator and clustering values across runs so only f changes.
- Run each cell in a fresh JVM, or after a GC, to avoid carry-over.
- Run with the default f=1.5 to match the shipped behaviour.
- Check the n0 knob alone with N small (the first growth) to separate it from f.

### B3. Cluster tier

> Amended 2026-10-23 (stage-4 step 0): see B5 R1, R3, R4, R5, R7, R8.

**B3a. Environment and build.**
- One node is enough (RF=1), on a Linux host with JDK 11. Build the local copy with `ant jar` in `/tmp/ct/cassandra-5.0.9` and run from `bin/cassandra -f` in that copy.
- Put `data_file_directories`, `commitlog_directory`, `hints_directory` and `saved_caches_directory` under a local directory of known size, for example `/tmp/ct/data`, with at least 10 GB free.
- JVM options: `-Xms2g -Xmx2g`, G1 or CMS as the default config provides, and `-XX:+HeapDumpOnOutOfMemoryError` pointed at local disk.
- `cassandra.yaml` changes: `memtable_allocation_type: heap_buffers` (default), `memtable_heap_space: 1024MiB`, and `tombstone_failure_threshold: 1000000` so the workload is not cut short by the read-side limit.
- Disable background flush noise for the measurement window by leaving the defaults but sizing the workload below the flush trigger (B3c).

**B3b. Knobs.**
- `range_tombstone_list_growth_factor` in {1.2, 1.5, 5.0}, set at runtime by JMX `StorageService.setRangeTombstoneListResizeGrowthFactor` (for example with `jmxterm` or `bin/nodetool` if exposed) and read back with the getter. A node restart is not needed, but restart between cells so the memtable starts empty.
- Optionally `initial_range_tombstone_list_allocation_size` in {1, 1024}.

**B3c. Workload.**
- Table `CREATE TABLE ks.t (pk int, ck int, v int, PRIMARY KEY (pk, ck))`, RF=1.
- Write range deletions into few partitions so that each partition's list gets large: for P = 20 partitions, issue `DELETE FROM ks.t WHERE pk=? AND ck > ? AND ck < ?` with disjoint ranges, K = 50,000 per partition, so 1,000,000 tombstones in total.
- Arithmetic: each stored tombstone costs about 20 B of array slot plus two bound objects (about 40-80 B each), so about 100-180 MB for 1M, which is under `memtable_heap_space` (1024 MiB), so no flush occurs during measurement. If flushes happen, they are noted and the cell is repeated.
- Drive with `cassandra-stress` user mode or a small Python-driver script with 64 concurrent async writers. Duration is until all 1M deletes are acknowledged, about minutes.
- Positive control: replace the range deletes with ordinary writes of the same bytes into a table and set `memtable_heap_space` to 64MiB; show that flushes then bound the memtable (heap use plateaus while the written volume keeps growing).

**B3d. Observables and instruments.**
- Heap after forced GC: `jcmd <pid> GC.run` and then `jcmd <pid> GC.class_histogram`, and read the `[Lorg.apache.cassandra.db.ClusteringBound;`, `[J`, `[I` rows.
- `nodetool gcstats` or `jstat -gc <pid> 1000` for heap use over time.
- Memtable size: `nodetool tablestats ks.t` ("Memtable data size", "Memtable cell count") or the JMX metric `org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=MemtableOnHeapDataSize`.
- Write throughput and latency from the client.
- Not observable directly: per-list capacity inside the live JVM. Use the heap histogram and a heap dump (`jcmd <pid> GC.heap_dump`) for array lengths if needed.

**B3e. Procedure.**
1. Build and configure (B3a); start the node; confirm with `nodetool status`.
2. Create the schema. Set f via JMX and read it back.
3. Run `jcmd <pid> GC.run`, then record the baseline heap and histogram.
4. Run the workload for f=1.2; after it finishes, run `GC.run`, then record the histogram, the MemtableOnHeapDataSize and the peak heap.
5. Stop the node, wipe `/tmp/ct/data`, restart, repeat for f=1.5 and f=5.0 (and the n0 variants if used).
6. Run the positive control.
7. Stop the node (`kill` the PID; check with `pgrep -f CassandraDaemon`), and remove `/tmp/ct`.

**B3f. Predictions (before any run).**
- At every f all 1,000,000 deletes are accepted and the cell count equals the workload.
- The `ClusteringBound[]` array bytes in the histogram rise with f for the same workload: at f=5.0 the array-slot bytes (20 B per slot) are up to 3 to 4 times the f=1.2 value, while the bound objects (the larger share) are roughly equal across cells. The total memtable heap difference between f=1.2 and f=5.0 is therefore well under the total (a modest percentage), and it does not scale with a cap.
- No cell shows a plateau of tombstone memory before the workload ends, and no writes are rejected.
- The positive control plateaus near `memtable_heap_space` (flush-driven) while written volume continues.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Tombstone count and heap grow with workload at all f; only the array bytes differ with f | Claim confirmed: the factor is not a cap |
| Writes rejected or tombstone memory plateaus at an f-dependent value | Claim refuted |
| Heap tracks f proportionally (overall heap scales like f) rather than only the array part | Claim refuted or the factor drives more than the arrays; examine the histogram |
| Heap flat across the workload while the positive control moves | Check the instruments; not confirmed until fixed |
| Positive control (flush-bound memtable) plateaus while the range-delete runs do not (below the flush trigger) | Confirms the instruments can see a binding cap and that f is not one |
| The memtable never grows past the baseline, or the control does not plateau | Not confirmed (workload too small or control invalid) |

**B3h. Controls.**
- Same hardware, JVM flags and schema for all cells; fresh data directory per cell.
- Forced GC before each reading so floating garbage does not hide the arrays.
- Keep the workload under the flush trigger so memtable flushes do not reset the lists, and record any flush that occurs.
- Check that `tombstone_failure_threshold` did not interfere (no `TombstoneOverwhelmingException` in the logs).
- Read the factor back through JMX before each cell.

**B4. Risks and cleanup.**
- Disk: all data, commit log and hints under `/tmp/ct/data` (local, at least 10 GB free). The workload is far below that; heap dumps can reach about 2 GB each, so delete them after use.
- Do not build in or write to the shared source tree. Do not use shared storage.
- Processes: the node JVM, `jmxterm`, stress clients. After the run check `pgrep -fl 'CassandraDaemon|jmxterm|cassandra-stress'` returns nothing.
- Cleanup: `rm -rf /tmp/ct`.
- The unit tier needs no running node, and its test file lives only in the local copy.

### B5. Step-0 audit amendments (2026-10-23, stage 4, before the freeze and before any reading)

Each item says which filed text it changes. The case's claim (B1), the estimate and the *meaning* of every B2g/B3g row are unchanged; R3 only defines words, and the control designations make explicit what the filed controls already were.

**R1 (environment; B2a, B3a, B4).** Every working tree is made by `stage4-runtime-verification/copy-source.sh` from this repository's `cassandra/cassandra-5.0.9/` (README safety rules), here `~/cassandra-rtl-g` (built with `ant build-test`; this file's tiers both use it). The `cp -r ~/cassandra-5.0.9 …`, `rsync … /tmp/ct` and `/local/...` paths of B2a, B3a and B4 are replaced by that tree and by node data under `~/stage4-rtl-g/` (local `/dev/sda3`, not `/proj`). Cleanup (B4) is therefore `rm -rf ~/stage4-rtl-g` and removing the test file from the tree; the tree stays on the node and is listed in the results file.

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

**R4 (cluster memory configuration; B3a, B3c arithmetic).** A memtable flush starts when the pool reaches `memtable_cleanup_threshold = 1/(1 + memtable_flush_writers)` of `memtable_heap_space`, 1/3 at the default two writers (`DatabaseDescriptor.java:761-764`, `conf/cassandra.yaml:794-812, 899-912`), not at the limit itself. The counter that the flush check reads also over-counts the bounds of every non-first `add()` (`RangeTombstoneList.java:178` after `setInternal` line 766 has counted them), so the filed estimate of about 250 B per tombstone understates the counter. With the filed 20 partitions × 50,000 = 1,000,000 tombstones and `memtable_heap_space: 1024MiB` (flush at about 341 MiB of counter) a flush would occur inside the main cells and reset the lists, which the claim's readings must not contain. The main cells therefore run with `MAX_HEAP_SIZE=8G` and `memtable_heap_space: 3072MiB` (flush at about 1024 MiB of counter, more than twice the largest expected counter); the positive control keeps its filed small value (64MiB, flush at about 21 MiB). All other B3a settings stay.

**R5 (cluster workload and instruments; B3a, B3b, B3d, B3e).**
- *Heap and limit.* B3a's `-Xms2g -Xmx2g` and `memtable_heap_space: 1024MiB` are replaced by 8 GiB and the R4 value; `tombstone_failure_threshold: 1000000` stays. `-XX:+HeapDumpOnOutOfMemoryError` is not set (a heap dump of 8 GiB is not wanted on the node); an OutOfMemoryError would be a reading and is caught in `system.log`.
- *Workload.* As filed: 20 partitions × 50,000 range deletes = 1,000,000 tombstones, `DELETE FROM ks.t WHERE pk = ? AND ck > 4i AND ck < 4i+2` (disjoint ranges), 64-way parallelism replaced by one in flight per partition (20 concurrent; each partition receives ascending tombstones, the sorted path, and the per-partition copy-then-grow is not retried). Checkpoints after 10,000, 25,000 and 50,000 deletes per partition (200,000, 500,000, 1,000,000 tombstones), which gives the dependence on N inside one run. A forced collection plus histogram at each checkpoint.
- *Cells.* A fresh lifetime per factor f = 1.2, 1.5 and 5.0, in that order, each set at runtime through JMX `setRangeTombstoneListResizeGrowthFactor` and read back (B3b), plus the positive control: 1,000,000 ordinary `INSERT INTO ks.t2 (pk, ck, v)` rows over the same 20 partitions (same number of mutations, same schema, per-partition ascending) at f = 1.5 with `memtable_heap_space: 64MiB`. The optional `initial_range_tombstone_list_allocation_size` variants are not run.
- *Instruments.* The harness `Jmx.java` replaces jmxterm and `nodetool`. At each checkpoint: `MemtableOnHeapDataSize`, `MemtableColumnsCount`, `MemtableSwitchCount` over JMX, `jcmd <pid> GC.class_histogram` for `ClusteringBound[]`, `BufferClusteringBound`, `long[]`, `int[]` and the total, `RssAnon`. During the load the counter and the switch count are polled every 2 s (the peak, and the plateau test of the control), and a 250 ms heap-pool poll runs (`HeapPoll.java`; `nodetool gcstats`/`jstat` cannot attach under `-XX:+PerfDisableSharedMem`). A Byteman rule on `growToFree` (observation only) logs capacity and `newLength` every 1000th call with the call counter. Autocompaction is disabled (R7).

**R6 (prediction wording that the source contradicts; B2f, B2g, B3f).** (1) B2f "`addAll` into empty gives capacity exactly `src.size`, independent of f" is false for `n0 = 1024`: `copyArrays` calls `dst.grow(src.size)`, and `grow(int)` grows only `if (capacity() < newLength)` (`RangeTombstoneList.java:694-698`), so the capacity after the call is `max(n0, src.size)`, independent of f. The unit rows that test this use that expression (for the source of 1,000 tombstones: 1,000 at n0 = 0 and 1, and 1,024 at n0 = 1,024). The bypass conclusion (the factor is not read there) is unchanged. (2) B2f "growth events ≈ ln(N)/ln(f), roughly 63, 28, 17, 8" is the continuous approximation counted from capacity 1; with n0 = 1024 or 0 the event count differs, so the exact count is the iterated one (R3) and the approximation is the tolerance of R3. (3) B3a "Disable background flush noise … by leaving the defaults" is replaced by R4 (the defaults flush inside the cell).

**R7 (controls made explicit; B2e step 5, B2g, B3h).** Unit: the `LinkedHashMap` with `removeEldestEntry` at M = 1,000 entries is the filed control; it shows a bound the probe can see is a plateau of size, while the list's size keeps rising. The cells with `n0 = 1024` and `N = 10` or `N = 1000` never call `growToFree`; their capacity stays at 1,024 whatever f is, a second binding-bound control. Cluster: the 64 MiB cell is the positive control; the filed "heap use plateaus while the written volume keeps growing" is tested as the plateau definition of R3 on the 2-second counter series plus `MemtableSwitchCount > 0`.


**R8 (cluster-tier definitions, written after the unit tier ran and before any cluster reading; B3f, B3g).** Nothing here depends on a reading; each item defines a word.
- *"`ClusteringBound[]` array bytes rise with f: at f = 5.0 up to 3 to 4 times the f = 1.2 value"* := `bytes(5.0) / bytes(1.2)` of the live `ClusteringBound[]` rows after the last checkpoint lies in [2.5, 4.5] and the three cells are ordered like f.
- *"the bound objects (the larger share) are roughly equal across cells"* := the live `BufferClusteringBound` counts after the last checkpoint differ by at most 2 % between cells.
- *"The total memtable heap difference … a modest percentage"* := `|counter(5.0) − counter(1.2)| < 50 %` of `counter(1.2)` at the last checkpoint.
- *Control "plateaus near `memtable_heap_space`"* := `MemtableSwitchCount` ends at 3 or more, and the largest value of the 2-second counter series is within [0.25, 1.0] × 64 MiB; *"while written volume continues"* := all 1,000,000 inserts are acknowledged. The R3 plateau definition is for the main cells (a control that flushes saw-tooths by design).

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/db/RangeTombstoneList.java`
- `src/java/org/apache/cassandra/db/MutableDeletionInfo.java` (lines 105-130)
- `src/java/org/apache/cassandra/config/Config.java` (lines 792-808)
- `src/java/org/apache/cassandra/service/StorageService.java` (lines 6890-6930)
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (grep, lines 4639-4656)
- `src/java/org/apache/cassandra/service/StorageServiceMBean.java` (grep)
- `test/unit/org/apache/cassandra/db/RangeTombstoneListTest.java` (lines 570-620)
- `conf/cassandra.yaml` (grep: memtable and tombstone settings)
- `test/data/config/version=5.0-alpha1.yml` (grep)
- Grep results over `src/java` for `unsharedHeapSize` consumers (`PartitionUpdate.java`, `ReadCommand.java`, `MutableDeletionInfo.java`)

## D. Stage-4 feedback

**Stage 4, 2026-10-23 (autonomous stage-4 session, `pc07`): Confirmed — does not cap, both tiers. Outcome class: true negative.** Results: `stage4-runtime-verification/results/range_tombstone_list_growth_factor-growToFree-newLength--autonomous.md` (run 1, self-checked, no run 2). Frozen versions: sha256 `14d83758276c72fe32260e58b2646b9ce3a7f5bf5fe09d0dc93aba3bea297b52` (unit; audit amendments R1–R7), `7b7eb4fe1faa5472682db662885efb99e44d0eb4660c523085dee41a8455d453` (cluster; plus R8 before any cluster reading). Case file not committed (no commit to cite).

- **Unit (B2).** 36 runs (4 factors × n0 ∈ {0, 1, 1024} × N ∈ {10, 1,000, 100,000}): capacity series, events and array lengths equal the iterated expression in every run; events at N = 100,000, n0 = 1: 57, 28, 17, 8 (the filed "roughly 63, 28, 17, 8" is the continuous ln(N)/ln(f), within the R3 tolerance); the N + 1-th add is accepted in all 36 runs; `unsharedHeapSize()` ∝ N (×99.8 – ×102.9); the `LinkedHashMap` control stays at 1,000 entries while the list grows to 100,000. All frozen criteria held. **Prediction fixed before the cluster tier (R6, no reading involved):** B2f's "`addAll` into empty gives capacity exactly `src.size`" is wrong for n0 = 1024: `grow(int)` grows only `if (capacity() < newLength)`, so the capacity is `max(n0, src.size)` (1,000 or 1,024), the same for every f; the bypass conclusion is unchanged.
- **Cluster (B3).** 20 × 50,000 = 1,000,000 range deletes per factor, `memtable_heap_space` 3072 MiB, 8 GiB heap; all acknowledged at f = 1.2, 1.5, 5.0; counter 504 / 510 / 580 MB (101 → 504 MB over N ×5 at f = 1.2); live tombstones == written; allocated slots per live tombstone 1.200 / 1.500 / 5.000; `ClusteringBound[]` bytes 9.6 / 12.0 / 40.0 MB (ratio 4.17, filed "3 to 4 times" as defined by R8: [2.5, 4.5]); counter difference 76.0 MB (15.1 %), live heap difference 84 MB. Control (1,000,000 plain inserts at 64 MiB): 12 memtable-limit flushes, counter ≤ 21.2 MiB. Byteman: `newLength = ceil(cap·f)` in 2,997 sampled `grow` calls.
- **Amendments to this file (section B5, dated 2026-10-23, none depends on a reading).** R1 working tree; R2 test-JVM facts; R3 definitions; R4 flush threshold and the 8 GiB / 3072 MiB main configuration (the filed 1024 MiB would flush at about 341 MiB of counter, inside the main cells); R5 workload, cells and instruments (one request in flight per partition instead of 64 concurrent writers; no heap-dump option); R6 the `addAll` capacity wording, the continuous event-count approximation, and B3a's configuration; R7 controls made explicit, autocompaction off; R8 (before the cluster tier) cluster definitions.
- **Stage 3 notes.** B3a's arithmetic ("100 – 180 MB … under `memtable_heap_space`") ignored the 1/3 flush trigger and the counter's double count (about 500 B per tombstone, not 100 – 180 B).

Side finding (not part of the claim, from the unit and cluster readings of all three sibling files): the `boundaryHeapSize` bookkeeping counts the bounds twice on the `add()` path (`RangeTombstoneList.java:178` after `setInternal` line 766). `boundaryHeapSize` is 2.000 × the true sum of the bound sizes and `unsharedHeapSize()` minus Jamm `measureDeep` equals the true bound sizes (N = 100,000, f = 1.5: 23,999,872 B against 24,000,000 B). In a node the memtable counter reads about 504 B per tombstone at f = 1.2 (580 B at f = 5.0) where the live heap above the baseline is about 270 – 280 B (340 – 370 B), so the memtable limit and the flush trigger are reached at roughly half the real tombstone volume. This is an accounting overestimate, not a cap tied to the factor. (A JIRA search was not done.)
