# none (hard-coded factor 10 in RangeTombstoneList.addAll) — verification solution  <!-- file: cases/none-addall-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`RangeTombstoneList.java:213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/RangeTombstoneList.java#L213) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: line 213 is a CPU-cost heuristic, not a memory or disk limit; both branches store the same merged tombstones, so the branch taken should not change retained size. |
| Ground | The condition compares two element counts (`size` and `tombstones.size`) against a hard-coded factor 10 to choose between per-element `add()` and a sorted merge. Neither branch evicts, rejects or truncates. The memory held by the list is set by how many non-overlapping tombstones exist and by the array capacity (growth factor and initial allocation), not by this condition. |

## A. Constraint trace

**A1. The constraint.** There is no resource constraint at the target line. The check is
[`if (size > 10 * tombstones.size)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/RangeTombstoneList.java#L213)
inside `addAll(RangeTombstoneList)` (declared at RangeTombstoneList.java:184). The comment at lines 196-211 states the purpose: choose between repeated `add()` (O(m*log n)) and a merge of two sorted lists (O(n+m)). Kind: hard-coded literal `10` (the declaration is the literal on the same line, [`RangeTombstoneList.java:213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/RangeTombstoneList.java#L213)); unit: dimensionless ratio of element counts; default: 10, not derived from anything; settable: no yaml key, `-D` property or JMX; changing it needs a code change and rebuild. The earlier trace was checked and holds (line 213 and line 184 confirmed).
Nearest memory-significant objects, used for the design below: the backing arrays of the list, whose capacity is governed by `range_tombstone_list_growth_factor` (default 1.5, [Config.java:802](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L802)) and `initial_range_tombstone_list_allocation_size` (default 1, Config.java:798), both volatile and settable through JMX (StorageServiceMBean.java:1166, 1172), and the memtable space limits `memtable_heap_space` / `memtable_offheap_space` (Config.java:187, 189). These are not what line 213 tests; they are used as the positive control.

**A2. What it caps.** Nothing. The operands are `size` (field, RangeTombstoneList.java:66) of this list and `tombstones.size` of the list being merged in. They select an algorithm; the quantity compared is a count, not bytes. Memory held by a list is reported by `unsharedHeapSize()` (RangeTombstoneList.java:770-778), which sums `EMPTY_SIZE`, `boundaryHeapSize` and the four array sizes, i.e. it depends on capacity and bound sizes, not on which branch ran.

**A3. Mechanism.**
1. `addAll` returns at once if the other list is empty (RangeTombstoneList.java:186-187).
2. If this list is empty, it copies the arrays with `copyArrays` (lines 189-192; copyArrays at 520-529, which calls `dst.grow(src.size)` and copies `boundaryHeapSize`).
3. Otherwise [`if (size > 10 * tombstones.size)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/RangeTombstoneList.java#L213):
   - true (this list more than 10 times bigger): loop calling `add(start, end, markedAt, delTime)` per element (lines 215-216), each of which may insert via `insertFrom` / `addInternal` and updates `boundaryHeapSize` (line 178).
   - false: two-pointer merge (lines 220-232), using `insertFrom` for overlapping starts and `addInternal(size, ...)` for the remainder.
4. Both branches reach `addInternal` (line 664), which calls `growToFree` (line 680) when `size == capacity()` (line 668). `growToFree` multiplies capacity by `DatabaseDescriptor.getRangeTombstoneListGrowthFactor()` (line 683) and falls back to `capacity()*3/2+1` if that does not grow (lines 685-686). So the only sizing logic is the growth factor, not line 213.
Outcomes: no outcome rejects, drops or flushes anything when a "limit" is reached; there is no limit. Overshoot/bypass: n/a. One difference worth testing: the merge branch calls `insertFrom` directly and the add() branch goes through `add`, whose `boundaryHeapSize` accounting is at line 178; whether `boundaryHeapSize` is updated identically on the merge path was not verified, and the unit tier reads it to check.


The check itself is the if statement at [`RangeTombstoneList.java:213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/RangeTombstoneList.java#L213).

**A4. Other consumers.** The only production caller found of `RangeTombstoneList.addAll` is `MutableDeletionInfo.add(DeletionInfo)` at MutableDeletionInfo.java:142, reached from memtable updates and from merges of responses (per the comment, lines 199-205). Lists are created at MutableDeletionInfo.java:118. The same heap holds memtable rows and cells, the key cache and others, outside this check. (Callers elsewhere not exhaustively searched: not verified.)

**A5. Evidence beyond the source.** The code comment at RangeTombstoneList.java:196-211. Existing unit tests for `addAll` are in test/unit/org/apache/cassandra/db/RangeTombstoneListTest.java (`addAllTest` at 235, `addAllSequentialTest` at 263, `addAllIncludedTest` at 281). No external documentation relied on.

## B. Verification solution

**B1. Claim under test.** The retained heap of a `RangeTombstoneList` after `addAll` does not depend on whether the `size > 10 * tombstones.size` branch is taken (for equal resulting content, `unsharedHeapSize()` differs only through array capacity), and no node-level memory or disk limit follows the factor 10. Refuted if, for the same resulting tombstones, the two branches give materially different retained size or if node memory changes in step with the ratio crossing 10.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c509/`), `cd $WORK/c509 && ant jar` (or `ant build-test`). Put a JUnit test or `main` class under `$WORK/c509/test/unit/org/apache/cassandra/db/` (model it on RangeTombstoneListTest). Run with `ant testsome -Dtest.name=RangeTombstoneListTest` style invocation or `java -cp build/classes/main:build/test/classes:lib/*:build/lib/jars/*`. JVM options `-Xmx1g -XX:+UseSerialGC`. Call `DatabaseDescriptor.daemonInitialization()` first, because `growToFree` reads the config (line 683).

**B2b. Knobs.** (1) Ratio `size : m` where n = this list size and m = other list size: n = 10*m (not above, merge branch), n = 10*m + 1 (above, add() branch), plus n = m. Why: these straddle the literal at line 213. (2) `DatabaseDescriptor.setRangeTombstoneListGrowthFactor(x)` for 1.5 (default) and 3.0, as positive control for something that does move retained size. Set in code before building lists.

**B2c. Workload.** Build list A with n non-overlapping tombstones `[2i, 2i+1)` over a single int clustering column, n = 10000. Build list B with m = 1000 (`size == 10*m`, merge branch) and m = 999 (`size > 10*m`, add() branch), with ranges interleaved and non-overlapping with A so the merged result has n+m elements in both runs. Also run the same pairs with B's ranges disjoint after A. Arithmetic: 10 * 1000 = 10000, so `10000 > 10000` is false (merge); `10000 > 9990` is true (add()).

**B2d. Observables and instruments.** `unsharedHeapSize()` of the result (RangeTombstoneList.java:770); `size()` (line 96); the capacity is private (`starts.length`, line 658), read by reflection; `ObjectSizes.measureDeep` is not assumed to exist in this tree: not verified, use a heap histogram (`jcmd <pid> GC.class_histogram` after `System.gc()`) as the independent measure. Cannot be observed directly: which branch ran; infer it from a debugger breakpoint or by counting calls to `add` with a subclass-free approach (jdb breakpoint at line 215).

**B2e. Procedure.**
1. Build as in B2a.
2. For each ratio case, construct A and B, call `A.addAll(B)`, record `size()`, `unsharedHeapSize()`, capacity.
3. `System.gc()`, take a class histogram, record bytes of `ClusteringBound` arrays and `long[]` / `int[]`.
4. Repeat with growth factor 3.0 (positive control).
5. Verify result equality across branches (`equals`, line 490 compares sizes) to confirm identical content.

**B2f. Predictions.** Result `size()` equals n+m in both branches. `unsharedHeapSize()` for the two branch cases differs by at most the difference in array capacity left by growth, which is bounded by the growth factor (at most 1.5x of the element count under the default); it does not jump at the 10x boundary. With growth factor 3.0 the capacity, and so `unsharedHeapSize()`, is larger than with 1.5 for the same content (control moves).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Same content, `unsharedHeapSize()` equal within the capacity slack, no step at the ratio 10 | Claim confirmed: line 213 does not govern retained size |
| `unsharedHeapSize()` differs materially (more than the capacity slack) between the add() and merge cases | Claim refuted: the branch affects memory (for example `boundaryHeapSize` differs) |
| Growth factor 3.0 raises `unsharedHeapSize()` while the ratio sweep does not | Claim confirmed with a working positive control |
| Growth factor change does not move `unsharedHeapSize()` | Control failed, not confirmed |
| Resulting `size()` differs from n+m, or the limit case was not reached (branch not verified by breakpoint) | Not confirmed, fix the workload |

**B2h. Controls.** Same content in both branches (equality check); fixed JVM and GC; fixed initial allocation size (set it to 1 as default); growth factor changed in one run only; ranges disjoint so no merging of overlaps changes the count.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy (`ant jar`), data, commitlog and hints directories on a local disk of known size (at least 20 GB free). `-Xms2g -Xmx2g`, `memtable_allocation_type: heap_buffers`, `memtable_heap_space: 512MiB`, `commitlog_sync: periodic`. Disable compaction on the test table via `nodetool disableautocompaction` so flushes do not change state.

**B3b. Knobs.** Cannot vary the literal 10 without a code change. The workload ratio is the knob: the memtable list size to the incoming list size. Also the control: JMX `setRangeTombstoneListResizeGrowthFactor` (StorageServiceMBean.java:1172) 1.5 vs 3.0. Optionally a rebuilt copy with `10` changed to `1` (local copy only) to force the merge branch always.

**B3c. Workload.** Table `ks.t (pk int, ck int, v int, primary key (pk, ck))`. Phase 1: with cqlsh or a driver script, issue 100000 `DELETE FROM ks.t WHERE pk=1 AND ck > 2*i AND ck < 2*i+1`-style disjoint range deletes into one partition (non-overlapping, e.g. `ck >= 3*i AND ck < 3*i+1`) one statement at a time, so each update adds a 1-element list into the memtable list of size n (add() branch once n > 10). Phase 2: batches of 100 range deletes per statement (m = 100), so the ratio crosses 10 repeatedly as n grows. Memtable stays under the 512MiB heap limit (100000 tombstones at roughly a few hundred bytes each is tens of MB; sizing estimate, not measured). Duration: a few minutes each phase.

**B3d. Observables and instruments.** `nodetool tablestats ks.t` (memtable data size, off-heap/heap memory used), JMX `org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=AllMemtablesHeapSize`, `jcmd <pid> GC.class_histogram` for `ClusteringBound` arrays, `du -sh` of the data directory after flush, sampled every 10 s. Not observable: the branch taken per call.

**B3e. Procedure.**
1. Build, start the node, create the schema.
2. Record baseline heap and memtable size.
3. Run phase 1 (single range deletes), sample every 10 s, record memtable heap size vs number of tombstones.
4. `nodetool flush`; record SSTable size on disk; truncate.
5. Run phase 2 (batches of 100) for the same total tombstone count; same sampling.
6. Control run: repeat phase 1 with growth factor 3.0 via JMX.
7. Stop the node, check no Java process remains, delete the data directories.

**B3f. Predictions.** For the same total number of disjoint tombstones, memtable heap size and flushed SSTable size are about equal between phase 1 and phase 2 (within array capacity slack); memory grows about linearly with the tombstone count, with no change in slope when n/m crosses 10. The growth factor 3.0 run shows a higher memtable heap size at equal count.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Phase 1 and phase 2 memtable heap size and SSTable size match for equal counts, slope unchanged across the 10 ratio | Claim confirmed: usage does not follow the factor |
| Systematic difference between phases beyond capacity slack | Claim refuted (or batching changes something else: check against controls) |
| Growth factor 3.0 raises memtable heap at equal count while phases still match | Positive control works; claim confirmed |
| Growth factor change has no effect | Control failed, not confirmed |
| Memtable flushed early (heap limit reached) or counts differ | Limit/workload not as intended, not confirmed |

**B3h. Controls.** Same schema, same tombstone count and content; compaction disabled; same heap and memtable settings; fresh node or truncate between runs; GC forced (`jcmd GC.run`) before each reading.

**B4. Risks and cleanup.** Unit tier: only the local copy under `$WORK`; delete it afterwards. Cluster tier: data on local disk of known size, tombstone count bounded at 100000 so disk use stays small; do not use the shared source tree; stop the node (`nodetool drain`, then kill the process), check with `ps` / `jps` that no Cassandra or test JVM remains, remove the data, commitlog and hints directories.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/RangeTombstoneList.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/MutableDeletionInfo.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java and StorageServiceMBean.java (grep only)
- /users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/db/RangeTombstoneListTest.java (grep only)

## D. Stage-4 feedback

`none yet`
